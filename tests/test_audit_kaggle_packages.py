from __future__ import annotations

from pathlib import Path

from scripts import audit_kaggle_packages
from scripts import build_kaggle_notebook


ATTACK_SOURCE = """\
USE_GPT_DUPLICATE_K8 = True
GPT_DUPLICATE_K8_TEMPLATE = "current_numeric_1_8"
GPT_ONLINE_SELECT_K8 = True
USE_GEMMA_K8_O = True
GEMMA_K8_O_VARIANT = "r57"
USE_GPT_DEPUTY_HEDGE = False
GPT_DEPUTY_HEDGE_N = 0
"""


def test_audit_packages_reports_matching_declared_and_current_source(
    tmp_path: Path,
) -> None:
    attack_path = tmp_path / "attack.py"
    attack_path.write_text(ATTACK_SOURCE, encoding="utf-8")
    package_dir = tmp_path / "runs" / "kaggle-package"
    notebook_path = package_dir / "package.ipynb"
    build_kaggle_notebook.build_notebook(attack_path, notebook_path, "Audit Package")

    rows = audit_kaggle_packages.audit_packages(
        tmp_path / "runs",
        current_attack=attack_path,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.error is None
    assert row.metadata_matches_embedded is True
    assert row.declared_attack_exists is True
    assert row.declared_attack_matches_embedded is True
    assert row.current_attack_matches_embedded is True
    assert row.constants["GPT_DUPLICATE_K8_TEMPLATE"] == "current_numeric_1_8"
    assert row.constants["GEMMA_K8_O_VARIANT"] == "r57"
    assert row.constants["GPT_DEPUTY_HEDGE_N"] == 0


def test_audit_packages_detects_stale_declared_source(tmp_path: Path) -> None:
    attack_path = tmp_path / "attack.py"
    attack_path.write_text(ATTACK_SOURCE, encoding="utf-8")
    package_dir = tmp_path / "runs" / "kaggle-stale"
    notebook_path = package_dir / "stale.ipynb"
    build_kaggle_notebook.build_notebook(attack_path, notebook_path, "Audit Stale")

    attack_path.write_text(
        ATTACK_SOURCE.replace('"current_numeric_1_8"', '"current_numeric_system_low"'),
        encoding="utf-8",
    )

    rows = audit_kaggle_packages.audit_packages(
        tmp_path / "runs",
        current_attack=attack_path,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.error is None
    assert row.metadata_matches_embedded is True
    assert row.declared_attack_exists is True
    assert row.declared_attack_matches_embedded is False
    assert row.current_attack_matches_embedded is False
    assert row.constants["GPT_DUPLICATE_K8_TEMPLATE"] == "current_numeric_1_8"
