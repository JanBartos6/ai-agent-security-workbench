from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_kaggle_submit():
    path = ROOT / "scripts" / "kaggle_submit.py"
    spec = importlib.util.spec_from_file_location("kaggle_submit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _EnumLike:
    value = "COMPLETE"


class _DottedStatus:
    def __str__(self) -> str:
        return "KernelWorkerStatus.ERROR"


def test_normalize_status_accepts_kaggle_enum_values() -> None:
    module = _load_kaggle_submit()

    assert module.normalize_status(_EnumLike()) == "complete"
    assert module.normalize_status(_DottedStatus()) == "error"
    assert module.normalize_status("running") == "running"
