from __future__ import annotations

import importlib.util
from pathlib import Path

from aicomp_sdk.attacks import AttackAlgorithmBase, AttackRunConfig
from aicomp_sdk.core.env.api import DEFAULT_MAX_TOOL_HOPS, MAX_USER_MESSAGE_CHARS
from aicomp_sdk.evaluation.ops import MAX_REPLAY_FINDINGS, MAX_REPLAY_MESSAGES_PER_FINDING


ROOT = Path(__file__).resolve().parents[1]


def test_current_executable_limits() -> None:
    assert MAX_REPLAY_FINDINGS == 2_000
    assert MAX_REPLAY_MESSAGES_PER_FINDING == 32
    assert MAX_USER_MESSAGE_CHARS == 2_000
    assert DEFAULT_MAX_TOOL_HOPS == 8


def test_static_baseline_contract() -> None:
    path = ROOT / "attacks" / "00_static_marker" / "attack.py"
    spec = importlib.util.spec_from_file_location("static_baseline", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert issubclass(module.AttackAlgorithm, AttackAlgorithmBase)

    candidates = module.AttackAlgorithm({"candidate_count": 4}).run(
        object(), AttackRunConfig(time_budget_s=1)
    )
    assert len(candidates) == 4
    assert all(1 <= len(candidate.user_messages) <= 32 for candidate in candidates)
    assert all(len(message) <= 2_000 for candidate in candidates for message in candidate.user_messages)

