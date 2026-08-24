"""Audit optional GPT CONFUSED_DEPUTY hedge placement without model inference.

This helper reconstructs the GPT duplicate-K8 replay list that `attack.py` would
return after the GPT route has selected a template, then applies the optional
hedge insertion helper.  It is for submission review: verify that a hedge budget
puts only the intended number of private hedge candidates near the replay head,
and quantify the public-score cost using `scripts/hedge_economics.py`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
SDK_BUNDLE_NAME = "ai-agent-security-multi-step-tool-attacks"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.hedge_economics import (  # noqa: E402
    breakeven_exfil_survival,
    evaluate_hedge_scenario,
)


def resolve_sdk_root() -> Path:
    local_bundle = ROOT / SDK_BUNDLE_NAME
    if local_bundle.is_dir():
        return local_bundle
    env_root = os.environ.get("AICOMP_SDK_ROOT")
    if env_root:
        candidate = Path(env_root).resolve()
        if candidate.is_dir() and candidate.name == SDK_BUNDLE_NAME:
            return candidate
        nested = candidate / SDK_BUNDLE_NAME
        if nested.is_dir():
            return nested
    workstation_bundle = Path("G:/kaggle_competition") / SDK_BUNDLE_NAME
    if workstation_bundle.is_dir():
        return workstation_bundle
    return local_bundle


def load_attack_module(attack_path: Path) -> Any:
    sdk_root = resolve_sdk_root()
    if str(sdk_root) not in sys.path:
        sys.path.insert(0, str(sdk_root))
    resolved = (ROOT / attack_path).resolve() if not attack_path.is_absolute() else attack_path
    spec = importlib.util.spec_from_file_location("hedge_mix_attack", resolved)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load attack module from {resolved}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _message_text(messages: Sequence[str]) -> str:
    return "\n".join(str(message) for message in messages)


def classify_messages(messages: Sequence[str]) -> str:
    text = _message_text(messages)
    lowered = text.lower()
    if "external-recipient tool with fields to, subject, body" in text:
        return "confused_deputy_hedge"
    if "SECRET_MARKER" in text and ("http.post" in text or "post data=" in lowered):
        if len(messages) > 1:
            return "exfil_k8_multi_message"
        return "exfil_k8"
    return "other"


def _candidate_messages(candidate: Any) -> tuple[str, ...]:
    messages = getattr(candidate, "user_messages", ())
    return tuple(str(message) for message in messages)


def summarize_candidates(candidates: Iterable[Any], *, preview_n: int = 12) -> dict[str, Any]:
    rows = []
    counts: Counter[str] = Counter()
    for idx, candidate in enumerate(candidates):
        messages = _candidate_messages(candidate)
        kind = classify_messages(messages)
        counts[kind] += 1
        if idx < max(0, int(preview_n)):
            first_message = messages[0] if messages else ""
            rows.append(
                {
                    "index": idx,
                    "kind": kind,
                    "message_count": len(messages),
                    "contains_secret_marker": "SECRET_MARKER" in _message_text(messages),
                    "first_message_prefix": first_message[:160],
                }
            )
    return {"counts": dict(counts), "preview": rows}


def build_gpt_hedge_mix(
    attack: Any,
    *,
    template: str,
    bank_index: int,
    bank_n: int,
    hedge_count: int,
    cap: int,
    position: str,
) -> list[Any]:
    base_messages = attack._gpt_duplicate_k8_messages(template, int(bank_index), 8)
    base_candidates = [
        attack.AttackCandidate.from_messages(base_messages)
        for _ in range(max(0, int(bank_n)))
    ]
    return attack._with_gpt_deputy_hedge(
        base_candidates,
        count=int(hedge_count),
        cap=int(cap),
        position=str(position),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--attack",
        type=Path,
        default=Path("attacks/05_validation_fill/attack.py"),
    )
    parser.add_argument("--template", default="current_numeric_1_8")
    parser.add_argument("--bank-index", type=int, default=11565)
    parser.add_argument("--bank-n", type=int, default=500)
    parser.add_argument("--hedges", type=int, default=1)
    parser.add_argument("--cap", type=int, default=2000)
    parser.add_argument("--position", choices=["head", "tail"], default="head")
    parser.add_argument("--exfil-survival", type=float, default=0.15)
    parser.add_argument("--hedge-survival", type=float, default=0.60)
    parser.add_argument("--preview-n", type=int, default=12)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    attack = load_attack_module(args.attack)
    candidates = build_gpt_hedge_mix(
        attack,
        template=args.template,
        bank_index=args.bank_index,
        bank_n=args.bank_n,
        hedge_count=args.hedges,
        cap=args.cap,
        position=args.position,
    )
    summary = summarize_candidates(candidates, preview_n=args.preview_n)
    economics = evaluate_hedge_scenario(
        hedge_count=int(summary["counts"].get("confused_deputy_hedge", 0)),
        exfil_survival_prior=args.exfil_survival,
        hedge_survival_prior=args.hedge_survival,
    )
    payload = {
        "attack": str((ROOT / args.attack).resolve() if not args.attack.is_absolute() else args.attack),
        "template": args.template,
        "bank_index": args.bank_index,
        "bank_n": args.bank_n,
        "hedges_requested": args.hedges,
        "cap": args.cap,
        "position": args.position,
        "candidate_count": len(candidates),
        "summary": summary,
        "economics": {
            **economics.__dict__,
            "breakeven_exfil_survival": breakeven_exfil_survival(
                hedge_survival_prior=args.hedge_survival
            ),
        },
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print("=== GPT hedge mix audit ===")
    print(
        f"template={args.template} bank_index={args.bank_index} "
        f"bank_n={args.bank_n} hedges={args.hedges} position={args.position} "
        f"cap={args.cap}"
    )
    print(f"candidate_count={len(candidates)} counts={summary['counts']}")
    print(
        "public_lb_loss="
        f"{economics.public_leaderboard_loss:.3f}; "
        "private_mean_delta="
        f"{economics.private_mean_delta_if_two_rows:.3f}; "
        "breakeven_exfil_survival="
        f"{payload['economics']['breakeven_exfil_survival']:.3f}"
    )
    for row in summary["preview"]:
        print(
            f"{row['index']:>3}: {row['kind']:<24} "
            f"messages={row['message_count']} secret={row['contains_secret_marker']} "
            f"{row['first_message_prefix']!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
