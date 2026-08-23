from __future__ import annotations

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


def test_decision_rolls_back_when_all_tracked_refs_miss_anchor() -> None:
    decision = _decision(
        [
            row(55717477, "COMPLETE", 109.770),
            row(55718913, "COMPLETE", 109.0),
            row(55720868, "COMPLETE", 100.0),
            row(55721360, "COMPLETE", 107.5),
        ],
        anchor_score=109.770,
    )

    assert decision.startswith("ROLLBACK:")
    assert "current_numeric_1_8" in decision
