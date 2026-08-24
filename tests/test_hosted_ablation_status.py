from __future__ import annotations

from pathlib import Path

from scripts import build_kaggle_notebook
from scripts import check_hosted_ablation_status as status
from scripts.check_hosted_ablation_status import SubmissionStatus, _decision


def row(ref: int, status: str, score: float | None) -> SubmissionStatus:
    return SubmissionStatus(
        ref=ref,
        status=status,
        score=score,
        description="",
        date="",
        url="",
        tracked_label="tracked",
    )


def test_decision_waits_while_any_tracked_ref_is_pending() -> None:
    decision = _decision(
        [
            row(55717477, "COMPLETE", 110.0),
            row(55718913, "PENDING", None),
            row(55720868, "COMPLETE", 108.0),
            row(55721360, "COMPLETE", 107.0),
        ],
        anchor_score=109.770,
    )

    assert decision.startswith("WAIT:")
    assert "55718913" in decision


def test_decision_promotes_best_completed_tracked_ref_above_anchor() -> None:
    decision = _decision(
        [
            row(55717477, "COMPLETE", 110.5),
            row(55718913, "COMPLETE", 109.0),
            row(55720868, "COMPLETE", 111.25),
            row(55721360, "COMPLETE", 110.0),
        ],
        anchor_score=109.770,
    )

    assert decision.startswith("PROMOTE:")
    assert "55720868" in decision
    assert "111.250" in decision


def test_decision_keeps_anchor_when_all_tracked_refs_miss_anchor() -> None:
    decision = _decision(
        [
            row(55717477, "COMPLETE", 112.650),
            row(55718913, "COMPLETE", 109.0),
            row(55720868, "COMPLETE", 100.0),
            row(55721360, "COMPLETE", 107.5),
        ],
        anchor_score=112.970,
    )

    assert decision.startswith("KEEP_ANCHOR:")
    assert "55727872" in decision


def test_local_package_annotation_marks_current_notebook(
    tmp_path: Path,
    monkeypatch,
) -> None:
    attack_path = tmp_path / "attack.py"
    attack_path.write_text("def run(env):\n    return []\n", encoding="utf-8")
    package_dir = tmp_path / "runs" / "kaggle-current"
    notebook_path = package_dir / "current.ipynb"
    build_kaggle_notebook.build_notebook(attack_path, notebook_path, "Current")

    monkeypatch.setattr(status, "ROOT", tmp_path)
    monkeypatch.setattr(status, "CURRENT_ATTACK", attack_path)
    monkeypatch.setattr(status, "LOCAL_NOTEBOOK_FOLDERS", {123: "runs/kaggle-current"})

    annotated = status._annotate_local_package_status(row(123, "COMPLETE", 1.0))

    assert annotated.local_attack_matches_current is True
    assert annotated.local_attack_sha256 == annotated.current_attack_sha256
    assert status._local_source_label(annotated) == "source=current"


def test_local_package_annotation_marks_stale_notebook(
    tmp_path: Path,
    monkeypatch,
) -> None:
    attack_path = tmp_path / "attack.py"
    attack_path.write_text("def run(env):\n    return ['old']\n", encoding="utf-8")
    package_dir = tmp_path / "runs" / "kaggle-stale"
    notebook_path = package_dir / "stale.ipynb"
    build_kaggle_notebook.build_notebook(attack_path, notebook_path, "Stale")
    attack_path.write_text("def run(env):\n    return ['new']\n", encoding="utf-8")

    monkeypatch.setattr(status, "ROOT", tmp_path)
    monkeypatch.setattr(status, "CURRENT_ATTACK", attack_path)
    monkeypatch.setattr(status, "LOCAL_NOTEBOOK_FOLDERS", {123: "runs/kaggle-stale"})

    annotated = status._annotate_local_package_status(row(123, "COMPLETE", 1.0))

    assert annotated.local_attack_matches_current is False
    assert annotated.local_attack_sha256 != annotated.current_attack_sha256
    assert status._local_source_label(annotated) == "source=stale"
