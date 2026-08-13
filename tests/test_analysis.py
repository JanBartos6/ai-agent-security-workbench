from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_analyzer():
    path = ROOT / "scripts" / "analyze_run.py"
    spec = importlib.util.spec_from_file_location("analyze_run", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_analyzer_counts_predicates_cells_and_target_attainment() -> None:
    module = _load_analyzer()
    records = [
        {
            "elapsed_s": 2.0,
            "outcome": "scored",
            "predicates": [{"severity": 5}, {"severity": 5}],
            "score_cell_signature": {"hash": "a"},
            "trace": {"tool_events": [{"ok": True}, {"ok": True}]},
            "metadata": {"requested_calls": 2},
        },
        {
            "elapsed_s": 1.0,
            "outcome": "no_tool_call",
            "predicates": [],
            "score_cell_signature": {"hash": "b"},
            "trace": {"tool_events": []},
            "metadata": {"requested_calls": 2},
        },
    ]

    summary = module.summarize(records)

    assert summary["scored_candidates"] == 1
    assert summary["predicate_instances"] == 2
    assert summary["unique_cells"] == 1
    assert summary["raw_score"] == 34.0
    assert summary["normalized_score"] == 0.17
    assert summary["requested_call_target_attainment_rate"] == 0.5
    assert summary["projected_normalized_score_at_2000"] == 170.0
    projected_low, projected_high = summary[
        "projected_normalized_score_at_2000_success_rate_only_95"
    ]
    assert projected_low < 170.0 < projected_high


def test_wilson_interval_contains_observed_rate() -> None:
    module = _load_analyzer()
    low, high = module.wilson_interval(7, 10)
    assert 0.0 < low < 0.7 < high < 1.0
