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


def test_factorial_seed_is_balanced_and_within_contract() -> None:
    path = ROOT / "attacks" / "01_factorial_seed" / "attack.py"
    spec = importlib.util.spec_from_file_location("factorial_seed", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    candidate_specs = module.build_candidate_specs(32)
    candidates = module.AttackAlgorithm({"candidate_count": 32}).run(
        object(), AttackRunConfig(time_budget_s=1)
    )

    assert len(candidate_specs) == len(candidates) == 32
    assert len({item["candidate_id"] for item in candidate_specs}) == 32
    assert len({item["domain"] for item in candidate_specs}) == 32
    assert len({candidate.user_messages for candidate in candidates}) == 32
    assert all(len(candidate.user_messages) == 1 for candidate in candidates)
    assert all(len(candidate.user_messages[0]) <= 2_000 for candidate in candidates)

    for factor in module.FACTOR_NAMES:
        values = [item["factors"][factor] for item in candidate_specs]
        assert len(set(values)) == 2
        assert all(values.count(value) == 16 for value in set(values))


def test_scaled_baseline_returns_two_thousand_unique_candidates() -> None:
    path = ROOT / "attacks" / "02_scaled_baseline" / "attack.py"
    spec = importlib.util.spec_from_file_location("scaled_baseline", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    candidate_specs = module.build_candidate_specs()
    candidates = module.AttackAlgorithm({}).run(
        object(), AttackRunConfig(time_budget_s=1)
    )

    assert len(candidate_specs) == len(candidates) == 2_000
    assert len({item["candidate_id"] for item in candidate_specs}) == 2_000
    assert len({item["domain"] for item in candidate_specs}) == 2_000
    assert len({candidate.user_messages for candidate in candidates}) == 2_000
    assert all(len(candidate.user_messages) == 1 for candidate in candidates)
    assert all(len(candidate.user_messages[0]) <= 2_000 for candidate in candidates)

    templates = [item["template"] for item in candidate_specs]
    assert set(templates) == set(module.TEMPLATE_NAMES)
    assert all(templates.count(name) == 500 for name in module.TEMPLATE_NAMES)
