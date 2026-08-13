from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import sys
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = ROOT / "ai-agent-security-multi-step-tool-attacks"
sys.dont_write_bytecode = True
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from aicomp_sdk.agents import AgentSelection  # noqa: E402
from aicomp_sdk.attacks import AttackAlgorithmBase, AttackRunConfig  # noqa: E402
from aicomp_sdk.core.env.api import EnvSelection  # noqa: E402
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


def load_attack(path: Path) -> type[AttackAlgorithmBase]:
    spec = importlib.util.spec_from_file_location("workbench_attack", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import attack: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    attack_cls = getattr(module, "AttackAlgorithm", None)
    if not isinstance(attack_cls, type) or not issubclass(attack_cls, AttackAlgorithmBase):
        raise TypeError("attack.py must define AttackAlgorithm(AttackAlgorithmBase)")
    return attack_cls


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
    attack_cls = load_attack(attack_path)
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

    try:
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
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "findings.json").write_text(json.dumps(attack.findings, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"artifacts: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
