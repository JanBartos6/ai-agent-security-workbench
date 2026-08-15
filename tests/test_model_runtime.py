from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "evaluate_local",
    ROOT / "scripts" / "evaluate_local.py",
)
assert SPEC is not None and SPEC.loader is not None
EVALUATE_LOCAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATE_LOCAL)


def test_parse_tensor_split() -> None:
    assert EVALUATE_LOCAL.parse_tensor_split("0.57, 0.43") == (0.57, 0.43)


def test_resolve_guardrail_private_surrogate() -> None:
    spec = EVALUATE_LOCAL.resolve_guardrail("private-surrogate")

    assert spec is not None
    assert spec.id == "private-provenance-surrogate"
    assert spec.guardrail_factory().__class__.__name__ == "PrivateProvenanceSurrogate"


def test_replay_diagnostics_distinguish_outcomes() -> None:
    no_call = {"tool_events": []}
    blocked = {
        "tool_events": [
            {
                "name": "http.post",
                "args": {},
                "ok": False,
                "output": None,
                "side_effect": "SHARE",
                "scope": "external",
                "source": "tool",
                "error": "denied:test",
            },
        ]
    }
    successful = {
        "tool_events": [
            {
                "name": "fs.read",
                "args": {"path": "notes.txt"},
                "ok": True,
                "output": "notes",
                "side_effect": "READ",
                "scope": "workspace",
                "source": "tool",
                "error": None,
            },
        ]
    }

    assert EVALUATE_LOCAL.classify_trace(no_call) == "no_tool_call"
    assert EVALUATE_LOCAL.classify_trace(blocked) == "guardrail_block"
    assert EVALUATE_LOCAL.classify_trace(successful) == "successful_no_predicate"


@pytest.mark.parametrize("value", ["", "0,0", "-1,1", "one,two"])
def test_parse_tensor_split_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        EVALUATE_LOCAL.parse_tensor_split(value)
