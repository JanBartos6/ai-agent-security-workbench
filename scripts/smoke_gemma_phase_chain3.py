"""Smoke test Gemma multi-message continuation economics.

This is a local-only follow-up to ``search_gemma_phase_chain.py``.  The exact
2xK8 continuation search has repeatedly plateaued at +6 posts from the S1
snapshot, so this script asks a narrower question:

    If block 2 stops at +5/+6, does a third user message cheaply recover another
    dense block, or does the longer history make it uneconomical?

It is not submission code.  It writes a compact JSON artifact under runs/tmp.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
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
from scripts.profile_k8 import MODEL_CONFIG, parse_tensor_split  # noqa: E402
from scripts.profile_sequence_arena import (  # noqa: E402
    _count_marker_posts,
    _gemma_k8_o_local_msg,
    make_sequence_llama,
)
from scripts.search_gemma_phase_chain import _phase_msg, _summarize, _trace_row  # noqa: E402

RAW_PER_EXFIL = 16
RAW_CELL_BONUS = 2


def _messages() -> dict[str, str]:
    return {
        "r57": _gemma_k8_o_local_msg("r57"),
        "phase_a_url_a": _phase_msg(phase="a", data_phase="a", url="a"),
        "phase_w_url_w": _phase_msg(phase="w", data_phase="w", url="w"),
        "phase_z_url_i": _phase_msg(phase="Z", data_phase="Z", url="i"),
        "phase_z_url_x": _phase_msg(phase="Z", data_phase="Z", url="x"),
    }


def _raw_per_s(posts: int, elapsed_s: float) -> float:
    if elapsed_s <= 0:
        return 0.0
    return (RAW_PER_EXFIL * posts + RAW_CELL_BONUS) / elapsed_s


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--gpu-layers", type=int, default=-1)
    parser.add_argument("--tensor-split", type=parse_tensor_split)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--max-tool-hops", type=int, default=8)
    parser.add_argument(
        "--second",
        default="phase_a_url_a,phase_w_url_w,phase_z_url_i",
        help="Comma-separated second-block labels.",
    )
    parser.add_argument(
        "--third",
        default="r57,phase_a_url_a,phase_w_url_w,phase_z_url_i",
        help="Comma-separated third-block labels.",
    )
    parser.add_argument("--out", type=Path, default=Path("runs/tmp/gemma-phase-chain3-smoke.json"))
    args = parser.parse_args()

    variants = _messages()
    second_labels = [item.strip() for item in args.second.split(",") if item.strip()]
    third_labels = [item.strip() for item in args.third.split(",") if item.strip()]
    missing = [label for label in second_labels + third_labels if label not in variants]
    if missing:
        raise SystemExit(f"unknown labels: {missing}; available={sorted(variants)}")

    model_config = MODEL_CONFIG["gemma"]
    model_path = (args.model_path or ROOT / "models" / model_config["filename"]).resolve()
    if not model_path.is_file():
        raise SystemExit(f"missing model: {model_path}")
    os.environ[model_config["env"]] = str(model_path)
    print(f"Using pre-downloaded GGUF at: {model_path}", flush=True)

    server = importlib.import_module(model_config["module"])
    remote_agent = importlib.import_module("kaggle_evaluation.jed_attack_134815.remote_agent")
    token_records: list[dict[str, Any]] = []
    server._server.spec = replace(server._server.spec, n_gpu_layers=args.gpu_layers)
    server._server._llama_cls = make_sequence_llama(args.tensor_split, token_records, force_cold=False)

    factory = lambda: remote_agent.RemoteAgent(server.predict)
    fixtures_dir = resolve_fixtures_dir(SDK_ROOT / "aicomp_sdk" / "fixtures")
    env = build_attack_env(
        seed=args.seed,
        fixtures_dir=fixtures_dir,
        agent_factory=factory,
        guardrail=OptimalGuardrail(),
        env_selection=EnvSelection.GYM,
        max_tool_hops=args.max_tool_hops,
    )

    block1 = variants["r57"]
    block2_rows: list[dict[str, Any]] = []
    chain3_rows: list[dict[str, Any]] = []
    started = time.perf_counter()

    try:
        env.reset()
        env.interact("warmup", max_tool_hops=1)
        token_records.clear()

        env.reset()
        t0 = time.perf_counter()
        start_calls = len(token_records)
        env.interact(block1, max_tool_hops=args.max_tool_hops)
        block1_elapsed = time.perf_counter() - t0
        block1_trace = env.export_trace_dict()
        block1_posts = _count_marker_posts(block1_trace)
        block1_snapshot = env.snapshot()
        block1_row = _trace_row(
            label="block1_r57",
            trace=block1_trace,
            elapsed_s=block1_elapsed,
            start_posts=0,
            calls=token_records[start_calls:],
        )
        print(f"block1_r57 posts={block1_posts} elapsed={block1_elapsed:.3f}s", flush=True)
        if block1_posts != 8:
            raise SystemExit(f"R57 block1 did not reach K8; posts={block1_posts}")

        block2_snapshots: dict[str, tuple[dict[str, Any], int, float]] = {}
        for second in second_labels:
            env.restore(block1_snapshot)
            start_calls = len(token_records)
            t0 = time.perf_counter()
            error = None
            trace: dict[str, Any] = {}
            try:
                env.interact(variants[second], max_tool_hops=args.max_tool_hops)
                trace = env.export_trace_dict()
            except Exception as err:  # noqa: BLE001
                error = f"{type(err).__name__}: {err}"
            elapsed = time.perf_counter() - t0
            row = _trace_row(
                label=second,
                trace=trace,
                elapsed_s=elapsed,
                start_posts=block1_posts,
                calls=token_records[start_calls:],
                error=error,
            )
            block2_rows.append(row)
            total_posts = int(row["posts_total"])
            block2_snapshots[second] = (env.snapshot(), total_posts, elapsed)
            print(
                f"block2 {second} inc={row['posts_incremental']} "
                f"total={total_posts} elapsed={elapsed:.3f}s error={error}",
                flush=True,
            )

        for second, (snapshot, posts_after_second, second_elapsed) in block2_snapshots.items():
            for third in third_labels:
                env.restore(snapshot)
                start_calls = len(token_records)
                t0 = time.perf_counter()
                error = None
                trace = {}
                try:
                    env.interact(variants[third], max_tool_hops=args.max_tool_hops)
                    trace = env.export_trace_dict()
                except Exception as err:  # noqa: BLE001
                    error = f"{type(err).__name__}: {err}"
                elapsed = time.perf_counter() - t0
                row = _trace_row(
                    label=f"{second} -> {third}",
                    trace=trace,
                    elapsed_s=elapsed,
                    start_posts=posts_after_second,
                    calls=token_records[start_calls:],
                    error=error,
                )
                total_posts = int(row["posts_total"])
                total_elapsed = block1_elapsed + second_elapsed + elapsed
                row["second_label"] = second
                row["third_label"] = third
                row["posts_after_second"] = posts_after_second
                row["total_elapsed_s_est"] = total_elapsed
                row["total_raw_per_s_est"] = _raw_per_s(total_posts, total_elapsed)
                chain3_rows.append(row)
                print(
                    f"chain3 {second} -> {third} inc3={row['posts_incremental']} "
                    f"total={total_posts} elapsed3={elapsed:.3f}s "
                    f"raw/s_est={row['total_raw_per_s_est']:.3f} error={error}",
                    flush=True,
                )

    finally:
        server._unload_model()

    out = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "agent": "gemma",
        "model_path": str(model_path),
        "seed": args.seed,
        "max_tool_hops": args.max_tool_hops,
        "elapsed_wall_s": time.perf_counter() - started,
        "block1": block1_row if "block1_row" in locals() else None,
        "variant_messages": variants,
        "summary_block2": _summarize(block2_rows),
        "summary_chain3_incremental": _summarize(chain3_rows),
        "block2_rows": block2_rows,
        "chain3_rows": chain3_rows,
    }
    out_path = (ROOT / args.out).resolve() if not args.out.is_absolute() else args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
