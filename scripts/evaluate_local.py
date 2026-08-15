from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import statistics
import sys
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = ROOT / "ai-agent-security-multi-step-tool-attacks"
sys.dont_write_bytecode = True
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from aicomp_sdk.agents import AgentSelection  # noqa: E402
from aicomp_sdk.attacks import AttackAlgorithmBase, AttackRunConfig  # noqa: E402
from aicomp_sdk.core.cells import cell_signature  # noqa: E402
from aicomp_sdk.core.env.api import EnvSelection  # noqa: E402
from aicomp_sdk.core.predicates import eval_predicates  # noqa: E402
from aicomp_sdk.evaluation import ops as evaluation_ops  # noqa: E402
from aicomp_sdk.evaluation.reports import ReportProfile, build_evaluation_report  # noqa: E402
from aicomp_sdk.evaluation.runner import evaluate_redteam  # noqa: E402


MODEL_CONFIG = {
    "gpt_oss": {
        "env": "GPT_OSS_MODEL_PATH",
        "filename": "gpt-oss-20b-Q4_K_M.gguf",
        "module": "kaggle_evaluation.jed_attack_134815.gpt_oss_model_server",
    },
    "gemma": {
        "env": "GEMMA_MODEL_PATH",
        "filename": "gemma-4-26B-A4B-it-UD-Q4_K_M.gguf",
        "module": "kaggle_evaluation.jed_attack_134815.gemma_model_server",
    },
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Persist one replay immediately so long model runs are observable."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")))
        handle.write("\n")


def load_attack(path: Path) -> tuple[type[AttackAlgorithmBase], ModuleType]:
    spec = importlib.util.spec_from_file_location("workbench_attack", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import attack: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    attack_cls = getattr(module, "AttackAlgorithm", None)
    if not isinstance(attack_cls, type) or not issubclass(attack_cls, AttackAlgorithmBase):
        raise TypeError("attack.py must define AttackAlgorithm(AttackAlgorithmBase)")
    return attack_cls, module


def classify_trace(trace: dict[str, Any]) -> str:
    events = list(trace.get("tool_events", []))
    predicates = eval_predicates(trace)
    if predicates:
        return "scored"
    if not events:
        return "no_tool_call"
    if any(
        str(event.get("error") or "").startswith(("denied:", "confirm_required:"))
        for event in events
    ):
        return "guardrail_block"
    if any(event.get("ok") for event in events):
        return "successful_no_predicate"
    return "tool_error"


def summarize_replays(records: list[dict[str, Any]]) -> dict[str, Any]:
    elapsed = [float(record["elapsed_s"]) for record in records]
    warm_elapsed = elapsed[1:]
    outcomes = Counter(str(record["outcome"]) for record in records)
    tool_call_count = sum(bool(record["trace"].get("tool_events")) for record in records)
    successful_tool_count = sum(
        any(event.get("ok") for event in record["trace"].get("tool_events", []))
        for record in records
    )
    blocked_count = sum(
        any(
            str(event.get("error") or "").startswith(("denied:", "confirm_required:"))
            for event in record["trace"].get("tool_events", [])
        )
        for record in records
    )

    return {
        "replayed_candidates": len(records),
        "tool_call_count": tool_call_count,
        "tool_call_rate": tool_call_count / len(records) if records else 0.0,
        "successful_tool_count": successful_tool_count,
        "successful_tool_rate": successful_tool_count / len(records) if records else 0.0,
        "guardrail_block_count": blocked_count,
        "outcomes": dict(sorted(outcomes.items())),
        "replay_elapsed_total_s": sum(elapsed),
        "first_replay_s": elapsed[0] if elapsed else None,
        "warm_replay_mean_s": statistics.mean(warm_elapsed) if warm_elapsed else None,
        "warm_replay_median_s": statistics.median(warm_elapsed) if warm_elapsed else None,
        "warm_replay_min_s": min(warm_elapsed) if warm_elapsed else None,
        "warm_replay_max_s": max(warm_elapsed) if warm_elapsed else None,
    }


def resolve_model(agent: str, model_path: Path | None) -> tuple[Any, str, Any | None, Path | None]:
    if agent == "deterministic":
        return None, "deterministic", None, None

    config = MODEL_CONFIG[agent]
    resolved_path = model_path or ROOT / "models" / config["filename"]
    if not resolved_path.is_file():
        raise FileNotFoundError(
            f"Missing {agent} model: {resolved_path}. Run scripts/download-models.ps1 first."
        )
    os.environ[config["env"]] = str(resolved_path.resolve())
    server = importlib.import_module(config["module"])
    remote_agent = importlib.import_module("kaggle_evaluation.jed_attack_134815.remote_agent")
    factory = lambda: remote_agent.RemoteAgent(server.predict)
    return factory, f"{agent}-competition-gguf", server, resolved_path


def parse_tensor_split(value: str) -> tuple[float, ...]:
    try:
        weights = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as err:
        raise argparse.ArgumentTypeError("tensor split must be comma-separated numbers") from err
    if not weights or any(weight < 0 for weight in weights) or sum(weights) <= 0:
        raise argparse.ArgumentTypeError("tensor split must contain non-negative weights with a positive sum")
    return weights


def configure_model_server(
    model_server: Any,
    *,
    gpu_layers: int,
    tensor_split: tuple[float, ...] | None,
) -> None:
    if gpu_layers < -1:
        raise ValueError("gpu_layers must be -1 (all), 0 (CPU), or a positive layer count")

    model_server._server.spec = replace(
        model_server._server.spec,
        n_gpu_layers=gpu_layers,
    )
    if tensor_split is None:
        return

    from llama_cpp import Llama

    class SplitConfiguredLlama(Llama):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("tensor_split", tensor_split)
            super().__init__(*args, **kwargs)

    model_server._server._llama_cls = SplitConfiguredLlama


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay an attack with the vendored scorer.")
    parser.add_argument("--attack", type=Path, default=Path("attacks/00_static_marker/attack.py"))
    parser.add_argument("--agent", choices=["deterministic", "gpt_oss", "gemma"], default="deterministic")
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--budget-s", type=float, default=30.0)
    parser.add_argument("--candidate-count", type=int, default=32)
    parser.add_argument(
        "--gpu-layers",
        type=int,
        default=-1,
        help="-1 offloads all layers, 0 is CPU-only, and a positive value enables partial offload.",
    )
    parser.add_argument(
        "--tensor-split",
        type=parse_tensor_split,
        help="Optional comma-separated GPU weights, for example 0.57,0.43. Default: llama.cpp auto split.",
    )
    args = parser.parse_args()

    attack_path = (ROOT / args.attack).resolve() if not args.attack.is_absolute() else args.attack.resolve()
    attack_cls, attack_module = load_attack(attack_path)
    metadata_builder = getattr(attack_module, "build_candidate_specs", None)
    candidate_manifest = (
        metadata_builder(args.candidate_count) if callable(metadata_builder) else []
    )
    progress_started_at = datetime.now(timezone.utc)
    progress_dir = ROOT / "runs" / "tmp" / "live-evaluations"
    progress_dir.mkdir(parents=True, exist_ok=True)
    progress_path = progress_dir / (
        f"{progress_started_at.strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}-"
        f"{args.agent}-{attack_path.parent.name}.jsonl"
    )
    progress_path.touch(exist_ok=False)
    print(f"live replay progress: {progress_path}", flush=True)
    factory, label, model_server, resolved_model_path = resolve_model(args.agent, args.model_path)
    if model_server is not None:
        configure_model_server(
            model_server,
            gpu_layers=args.gpu_layers,
            tensor_split=args.tensor_split,
        )
        split_label = args.tensor_split if args.tensor_split is not None else "auto"
        print(f"llama.cpp offload: gpu_layers={args.gpu_layers}, tensor_split={split_label}")
    run_config = AttackRunConfig(
        time_budget_s=args.budget_s,
        max_steps=10**9,
        max_tool_hops=8,
    )

    replay_records: list[dict[str, Any]] = []
    original_replay = evaluation_ops._replay_candidate_trace

    def capture_replay(**kwargs: Any) -> dict[str, Any]:
        started_at = time.perf_counter()
        trace = original_replay(**kwargs)
        elapsed_s = time.perf_counter() - started_at
        predicates = eval_predicates(trace)
        candidate_index = int(kwargs["index"])
        record = {
            "candidate_index": candidate_index,
            "elapsed_s": elapsed_s,
            "outcome": classify_trace(trace),
            "predicates": predicates,
            "score_cell_signature": cell_signature(trace.get("tool_events", [])),
            "trace": trace,
        }
        replay_records.append(record)
        progress_record = dict(record)
        progress_record["metadata"] = (
            candidate_manifest[candidate_index]
            if candidate_index < len(candidate_manifest)
            else {}
        )
        append_jsonl(progress_path, progress_record)
        return trace

    try:
        with patch.object(evaluation_ops, "_replay_candidate_trace", capture_replay):
            if args.agent == "deterministic":
                execution = evaluate_redteam(
                    attack_cls,
                    budget_s=args.budget_s,
                    agent_selection=AgentSelection.DETERMINISTIC,
                    env_selection=EnvSelection.GYM,
                    fixtures_dir=SDK_ROOT / "aicomp_sdk" / "fixtures",
                    attack_run_config=run_config,
                    attack_config={"candidate_count": args.candidate_count},
                )
            else:
                execution = evaluate_redteam(
                    attack_cls,
                    budget_s=args.budget_s,
                    agent_factory=factory,
                    agent_label=label,
                    env_selection=EnvSelection.GYM,
                    fixtures_dir=SDK_ROOT / "aicomp_sdk" / "fixtures",
                    attack_run_config=run_config,
                    attack_config={"candidate_count": args.candidate_count},
                )
    finally:
        if model_server is not None:
            model_server._unload_model()

    attack = execution.attack
    assert attack is not None
    now = datetime.now(timezone.utc)
    run_dir = ROOT / "runs" / now.strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=False)

    predicate_counts = Counter(
        predicate["predicate"]
        for finding in attack.findings
        for predicate in finding.get("predicates", [])
    )
    replay_summary = summarize_replays(replay_records)
    summary = build_evaluation_report(execution, profile=ReportProfile.EVALUATE)
    summary["workbench"] = {
        "timestamp_utc": now.isoformat(),
        "attack_path": str(attack_path),
        "attack_sha256": file_sha256(attack_path),
        "sdk_tree_lock": json.loads((ROOT / "sdk-integrity.lock.json").read_text(encoding="utf-8")),
        "candidate_count_requested": args.candidate_count,
        "max_tool_hops": run_config.max_tool_hops,
        "predicate_counts": dict(sorted(predicate_counts.items())),
        "model_path": str(resolved_model_path.resolve()) if resolved_model_path else None,
        "model_sha256": file_sha256(resolved_model_path) if resolved_model_path else None,
        "gpu_layers": args.gpu_layers if resolved_model_path else None,
        "tensor_split": list(args.tensor_split) if args.tensor_split is not None else None,
        "context_size": 8192 if resolved_model_path else None,
        "attack_elapsed_s": attack.time_taken,
        "live_replay_progress_path": str(progress_path.resolve()),
        "replay_diagnostics": replay_summary,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "findings.json").write_text(json.dumps(attack.findings, indent=2), encoding="utf-8")
    (run_dir / "replays.json").write_text(json.dumps(replay_records, indent=2), encoding="utf-8")
    if candidate_manifest:
        (run_dir / "candidate_manifest.json").write_text(
            json.dumps(candidate_manifest, indent=2), encoding="utf-8"
        )

    print(json.dumps(summary, indent=2))
    print(f"artifacts: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
