"""Print GPT duplicate-K8 selector rounds against a real local model.

This is a local-only diagnostic for the hosted selector.  It mirrors the
successive-halving race in ``attacks/05_validation_fill/attack.py`` but prints
per-arm posts/elapsed samples and the survivor set after every round.

It does not edit submission code and does not push or submit to Kaggle.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = ROOT / "ai-agent-security-multi-step-tool-attacks"
if not SDK_ROOT.exists() and os.environ.get("AICOMP_SDK_ROOT"):
    SDK_ROOT = Path(os.environ["AICOMP_SDK_ROOT"]).resolve()
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from aicomp_sdk.core.env.api import EnvSelection  # noqa: E402
from aicomp_sdk.evaluation.ops import build_attack_env, resolve_fixtures_dir  # noqa: E402
from aicomp_sdk.guardrails.optimal import Guardrail as OptimalGuardrail  # noqa: E402
from scripts.evaluate_local import configure_model_server, resolve_model  # noqa: E402
from scripts.profile_k8 import load_attack_helpers  # noqa: E402


def _template_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in str(value or "").split(",") if item.strip())


def _p75(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    idx = min(len(ordered) - 1, max(0, ((3 * len(ordered) + 3) // 4) - 1))
    return ordered[idx]


def _probe(
    attack: Any,
    env: Any,
    *,
    template: str,
    bank_index: int,
    hops: int,
    probes: int,
    warmup_probes: int,
) -> dict[str, Any] | None:
    messages = attack._gpt_duplicate_k8_messages(template, int(bank_index), 8)
    min_posts = min(8, max(1, int(hops))) * len(messages)
    elapsed_samples: list[float] = []
    posts_samples: list[int] = []

    for probe_idx in range(max(1, int(probes))):
        t0 = time.perf_counter()
        try:
            env.reset()
            for message in messages:
                env.interact(message, max_tool_hops=hops)
            posts = attack.AttackAlgorithm._posts_fired(env)
        except Exception as err:  # noqa: BLE001
            elapsed = time.perf_counter() - t0
            print(
                f"    probe {probe_idx + 1}/{probes}: ERROR {type(err).__name__}: {err} "
                f"elapsed={elapsed:.3f}s",
                flush=True,
            )
            return None
        elapsed = time.perf_counter() - t0
        elapsed_samples.append(elapsed)
        posts_samples.append(posts)
        print(
            f"    probe {probe_idx + 1}/{probes}: posts={posts} "
            f"elapsed={elapsed:.3f}s",
            flush=True,
        )
        if posts < min_posts:
            print(
                f"    reject: posts {posts} < required {min_posts}",
                flush=True,
            )
            return None

    warmup = max(0, min(int(warmup_probes), len(elapsed_samples) - 1))
    scored_elapsed = elapsed_samples[warmup:] or elapsed_samples
    scored_posts = posts_samples[warmup:] or posts_samples
    utility = min(scored_posts) / max(_p75(scored_elapsed), 1e-9)
    raw_per_s = ((16 * min(scored_posts)) + 2) / max(_p75(scored_elapsed), 1e-9)
    return {
        "template": template,
        "messages": len(messages),
        "required_posts": min_posts,
        "posts_samples": posts_samples,
        "elapsed_samples": elapsed_samples,
        "scored_posts": scored_posts,
        "scored_elapsed": scored_elapsed,
        "utility": utility,
        "raw_per_s_p75": raw_per_s,
        "median_elapsed_s": statistics.median(elapsed_samples),
        "p75_elapsed_s": _p75(scored_elapsed),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attack", type=Path, default=Path("attacks/05_validation_fill/attack.py"))
    parser.add_argument("--agent", choices=["gpt_oss"], default="gpt_oss")
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--gpu-layers", type=int, default=-1)
    parser.add_argument("--tensor-split", default=None)
    parser.add_argument("--bank-index", type=int, default=11565)
    parser.add_argument("--hops", type=int, default=8)
    parser.add_argument("--warmup-probes", type=int, default=1)
    parser.add_argument("--schedule", default="3,4,5,5")
    parser.add_argument(
        "--templates",
        default="",
        help="Comma-separated challenger templates. Defaults to attack.py selector templates.",
    )
    parser.add_argument("--default-template", default="")
    parser.add_argument("--out", type=Path, default=Path("runs/tmp/gpt-selector-rounds.json"))
    args = parser.parse_args()

    attack_path = (ROOT / args.attack).resolve() if not args.attack.is_absolute() else args.attack
    attack = load_attack_helpers(attack_path)
    default_template = args.default_template or attack.GPT_DUPLICATE_K8_TEMPLATE
    challenger_templates = _template_csv(args.templates or attack.GPT_ONLINE_SELECT_TEMPLATES)
    ordered: list[str] = []
    for template in (default_template, *challenger_templates):
        if template and template not in ordered:
            ordered.append(template)

    factory, label, model_server, model_path = resolve_model(args.agent, args.model_path)
    del label, model_path
    if model_server is not None:
        split = (
            tuple(float(x.strip()) for x in str(args.tensor_split).split(","))
            if args.tensor_split
            else None
        )
        configure_model_server(model_server, gpu_layers=args.gpu_layers, tensor_split=split)

    fixtures_dir = resolve_fixtures_dir(SDK_ROOT / "aicomp_sdk" / "fixtures")
    env = build_attack_env(
        seed=123,
        fixtures_dir=fixtures_dir,
        agent_factory=factory,
        guardrail=OptimalGuardrail(),
        env_selection=EnvSelection.GYM,
        max_tool_hops=args.hops,
    )

    schedule = tuple(int(item) for item in args.schedule.split(",") if item.strip())
    contenders = tuple(ordered)
    rounds: list[dict[str, Any]] = []
    try:
        for round_idx, round_probes in enumerate(schedule):
            print(
                f"round {round_idx + 1}/{len(schedule)} probes={round_probes} "
                f"contenders={json.dumps(contenders)}",
                flush=True,
            )
            round_results: list[dict[str, Any]] = []
            for template in contenders:
                print(f"  arm={template}", flush=True)
                result = _probe(
                    attack,
                    env,
                    template=template,
                    bank_index=args.bank_index,
                    hops=args.hops,
                    probes=round_probes,
                    warmup_probes=args.warmup_probes,
                )
                if result is not None:
                    round_results.append(result)
                    print(
                        f"    keep utility={result['utility']:.3f} "
                        f"raw/s_p75={result['raw_per_s_p75']:.3f} "
                        f"p75_elapsed={result['p75_elapsed_s']:.3f}s",
                        flush=True,
                    )
            round_results.sort(key=lambda item: float(item["utility"]), reverse=True)
            rounds.append({"round": round_idx + 1, "results": round_results})
            if not round_results:
                print(f"selected={default_template} reason=no_complete_round", flush=True)
                break
            if round_idx == len(schedule) - 1:
                print(f"selected={round_results[0]['template']} reason=last_round", flush=True)
                break
            keep_n = 1 if len(round_results) <= 2 else max(2, (len(round_results) + 1) // 2)
            contenders = tuple(str(item["template"]) for item in round_results[:keep_n])
            print(f"  survivors={json.dumps(contenders)}", flush=True)
    finally:
        if model_server is not None:
            model_server._unload_model()

    out_path = (ROOT / args.out).resolve() if not args.out.is_absolute() else args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"ordered": ordered, "rounds": rounds}, indent=2), encoding="utf-8")
    print(f"wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

