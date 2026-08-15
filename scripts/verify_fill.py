"""Local live-fill smoke test for validation-fill attacks.

Runs ``AttackAlgorithm.run()`` against a real local model env WITHOUT the
``candidate_count`` override (so the validation-fill loop actually probes),
then lets the harness replay + score the returned candidates.  Use a short
budget to keep it fast; this verifies the probe loop, fire detection, and
replay-safe sizing locally before a Kaggle submission.

Usage:
    PYTHONDONTWRITEBYTECODE=1 python scripts/verify_fill.py \
        --attack attacks/05_validation_fill/attack.py --agent gpt_oss --budget-s 60
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = ROOT / "ai-agent-security-multi-step-tool-attacks"
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from aicomp_sdk.agents import AgentSelection  # noqa: E402
from aicomp_sdk.attacks import AttackRunConfig  # noqa: E402
from aicomp_sdk.core.env.api import EnvSelection  # noqa: E402
from aicomp_sdk.evaluation.runner import evaluate_redteam  # noqa: E402

from scripts.evaluate_local import (  # noqa: E402
    configure_model_server,
    load_attack,
    resolve_model,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local live-fill smoke test.")
    parser.add_argument("--attack", type=Path, default=Path("attacks/05_validation_fill/attack.py"))
    parser.add_argument("--agent", choices=["deterministic", "gpt_oss", "gemma"], default="gpt_oss")
    parser.add_argument("--budget-s", type=float, default=60.0)
    parser.add_argument("--gpu-layers", type=int, default=-1)
    parser.add_argument("--tensor-split", type=str, default=None)
    args = parser.parse_args()

    attack_path = (ROOT / args.attack).resolve() if not args.attack.is_absolute() else args.attack.resolve()
    attack_cls, _ = load_attack(attack_path)

    factory, label, model_server, _ = resolve_model(args.agent, None)
    if model_server is not None:
        split = (
            tuple(float(x.strip()) for x in args.tensor_split.split(","))
            if args.tensor_split
            else None
        )
        configure_model_server(model_server, gpu_layers=args.gpu_layers, tensor_split=split)

    run_config = AttackRunConfig(
        time_budget_s=args.budget_s,
        max_steps=10**9,
        max_tool_hops=8,
    )
    kwargs: dict = {
        "budget_s": args.budget_s,
        "env_selection": EnvSelection.GYM,
        "fixtures_dir": SDK_ROOT / "aicomp_sdk" / "fixtures",
        "attack_run_config": run_config,
        # NOTE: empty config -> the attack runs its live validation-fill loop.
        "attack_config": {},
    }
    if args.agent == "deterministic":
        kwargs["agent_selection"] = AgentSelection.DETERMINISTIC
    else:
        kwargs["agent_factory"] = factory
        kwargs["agent_label"] = label

    try:
        execution = evaluate_redteam(attack_cls, **kwargs)
    finally:
        if model_server is not None:
            model_server._unload_model()

    attack = execution.attack
    assert attack is not None
    print(f"\ncandidates_returned={attack.findings_count}")
    print(f"unique_cells={attack.unique_cells}")
    print(f"score_raw={attack.score_raw}")
    print(f"score_normalized={execution.final_score}")
    print(f"attack_elapsed_s={attack.time_taken}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
