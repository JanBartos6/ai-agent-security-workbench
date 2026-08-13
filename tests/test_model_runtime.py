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


@pytest.mark.parametrize("value", ["", "0,0", "-1,1", "one,two"])
def test_parse_tensor_split_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        EVALUATE_LOCAL.parse_tensor_split(value)
