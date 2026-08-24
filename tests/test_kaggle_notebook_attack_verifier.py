from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_notebook_records_and_verifies_attack_hash(tmp_path: Path) -> None:
    builder = _load_script("build_kaggle_notebook")
    verifier = _load_script("verify_kaggle_notebook_attack")

    attack_path = tmp_path / "attack.py"
    attack_path.write_text("def run(env):\n    return []\n", encoding="utf-8")
    notebook_path = tmp_path / "submission.ipynb"

    builder.build_notebook(attack_path, notebook_path, "Verifier Test")
    result = verifier.compare_notebook_attack(notebook_path, attack_path)

    assert result["matches"] is True
    assert result["metadata_matches_embedded"] is True
    assert result["metadata_sha256"] == result["expected_sha256"]


def test_verifier_detects_stale_embedded_attack(tmp_path: Path) -> None:
    builder = _load_script("build_kaggle_notebook")
    verifier = _load_script("verify_kaggle_notebook_attack")

    attack_path = tmp_path / "attack.py"
    attack_path.write_text("def run(env):\n    return ['old']\n", encoding="utf-8")
    notebook_path = tmp_path / "submission.ipynb"
    builder.build_notebook(attack_path, notebook_path, "Verifier Test")

    attack_path.write_text("def run(env):\n    return ['new']\n", encoding="utf-8")
    result = verifier.compare_notebook_attack(notebook_path, attack_path)

    assert result["matches"] is False
    assert result["metadata_matches_embedded"] is True
    assert result["embedded_sha256"] != result["expected_sha256"]
