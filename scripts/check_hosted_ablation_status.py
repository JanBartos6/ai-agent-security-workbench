"""Check hosted Kaggle ablations against the current public anchor.

This is a read-only helper.  It does not push kernels, submit notebooks, or edit
attack code.  The goal is to turn the pending hosted GPT ablation set into a
clear promotion/rollback decision as soon as Kaggle scoring completes.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from kaggle.api.kaggle_api_extended import KaggleApi


COMPETITION = "ai-agent-security-multi-step-tool-attacks"
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_kaggle_notebook_attack import compare_notebook_attack  # noqa: E402

CURRENT_ATTACK = ROOT / "attacks" / "05_validation_fill" / "attack.py"
ANCHOR_REF = 55727872
ANCHOR_SCORE = 112.970
ANCHOR_LABEL = "successive-halving selector + Gemma R57"

# Completed hosted ablations that explain the current GPT choice.  Keep these in
# the status page so future decisions are made against the real 112.970 anchor,
# not the older 109.770 numeric checkpoint.
TRACKED_REFS: dict[int, str] = {
    55717477: "system-low numeric duplicate K8 + Gemma R57",
    55718913: "online select numeric/system-low K8 + Gemma R57",
    55720868: "online select system-low/proto/numeric K8 + Gemma R57",
    55721360: "bare-opaque selector K8 + Gemma R57",
    55740467: "system-medium numeric duplicate K8 + Gemma R57",
}

# Local package folders for tracked hosted submissions.  Kaggle scores should be
# interpreted against the notebook's embedded attack hash, not the current
# working-tree source, because research commits can move quickly after a submit.
LOCAL_NOTEBOOK_FOLDERS: dict[int, str] = {
    55717477: "runs/kaggle-gpt-system-low-numeric-gemma-r57",
    55718913: "runs/kaggle-gpt-online-select-gemma-r57",
    55720868: "runs/kaggle-gpt-selector-proto-literal-gemma-r57",
    55721360: "runs/kaggle-gpt-bare-opaque-selector-gemma-r57",
    55727872: "runs/kaggle-gpt-halving-gemma-r57",
    55740467: "runs/kaggle-gpt-system-medium-gemma-r57",
}


@dataclass(frozen=True)
class SubmissionStatus:
    ref: int
    status: str
    score: float | None
    description: str
    date: str
    url: str
    tracked_label: str | None = None
    local_notebook: str | None = None
    local_attack_matches_current: bool | None = None
    local_attack_sha256: str | None = None
    current_attack_sha256: str | None = None
    local_attack_metadata_sha256: str | None = None
    local_attack_error: str | None = None


def _public_score(submission: Any) -> float | None:
    raw = getattr(submission, "publicScore", None) or submission.__dict__.get("_public_score")
    if raw in (None, ""):
        return None
    return float(raw)


def _status_name(submission: Any) -> str:
    status = getattr(submission, "status", None) or submission.__dict__.get("_status")
    return getattr(status, "name", str(status))


def _to_status(submission: Any) -> SubmissionStatus:
    ref = int(getattr(submission, "ref", None) or submission.__dict__.get("_ref"))
    return SubmissionStatus(
        ref=ref,
        status=_status_name(submission),
        score=_public_score(submission),
        description=str(getattr(submission, "description", "") or ""),
        date=str(getattr(submission, "date", "") or ""),
        url=str(submission.__dict__.get("_url") or ""),
        tracked_label=TRACKED_REFS.get(ref),
    )


def _local_notebook_path(ref: int) -> Path | None:
    folder_name = LOCAL_NOTEBOOK_FOLDERS.get(int(ref))
    if not folder_name:
        return None
    folder = ROOT / folder_name
    metadata_path = folder / "kernel-metadata.json"
    if not metadata_path.is_file():
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    code_file = metadata.get("code_file")
    if not isinstance(code_file, str) or not code_file:
        return None
    return folder / code_file


def _annotate_local_package_status(row: SubmissionStatus) -> SubmissionStatus:
    notebook_path = _local_notebook_path(row.ref)
    if notebook_path is None:
        return row
    try:
        result = compare_notebook_attack(notebook_path, CURRENT_ATTACK)
    except Exception as exc:  # noqa: BLE001
        return replace(
            row,
            local_notebook=str(notebook_path),
            local_attack_error=f"{type(exc).__name__}: {exc}",
        )
    return replace(
        row,
        local_notebook=str(notebook_path),
        local_attack_matches_current=bool(result["matches"]),
        local_attack_sha256=str(result["embedded_sha256"]),
        current_attack_sha256=str(result["expected_sha256"]),
        local_attack_metadata_sha256=(
            None if result.get("metadata_sha256") is None else str(result["metadata_sha256"])
        ),
    )


def _local_source_label(row: SubmissionStatus) -> str:
    if row.local_notebook is None:
        return "source=untracked"
    if row.local_attack_error:
        return "source=error"
    if row.local_attack_matches_current is True:
        return "source=current"
    if row.local_attack_matches_current is False:
        return "source=stale"
    return "source=unknown"


def _decision(rows: list[SubmissionStatus], *, anchor_score: float) -> str:
    tracked = [row for row in rows if row.ref in TRACKED_REFS]
    pending = [row for row in tracked if row.status != "COMPLETE"]
    complete = [row for row in tracked if row.status == "COMPLETE" and row.score is not None]

    if pending:
        refs = ", ".join(str(row.ref) for row in pending)
        best = max(complete, key=lambda row: row.score or float("-inf"), default=None)
        best_text = (
            f" Best completed tracked ref so far is {best.ref} at {best.score:.3f}."
            if best is not None
            else ""
        )
        return f"WAIT: tracked refs still pending: {refs}.{best_text}"

    if not complete:
        return "WAIT: no tracked ablation has a completed public score yet."

    best = max(complete, key=lambda row: row.score or float("-inf"))
    if (best.score or 0.0) > anchor_score:
        return (
            f"PROMOTE: ref {best.ref} ({best.tracked_label}) scored {best.score:.3f}, "
            f"beating anchor {anchor_score:.3f}. Promote that exact submitted family."
        )

    return (
        f"KEEP_ANCHOR: all tracked ablations completed at or below anchor {anchor_score:.3f}. "
        f"Preserve hosted anchor {ANCHOR_REF} until a newer controlled probe beats it."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competition", default=COMPETITION)
    parser.add_argument("--anchor-score", type=float, default=ANCHOR_SCORE)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Number of recent submissions to fetch/print from the Kaggle API response.",
    )
    args = parser.parse_args()

    api = KaggleApi()
    api.authenticate()
    submissions = api.competition_submissions(args.competition)[: args.limit]
    rows = [_annotate_local_package_status(_to_status(submission)) for submission in submissions]
    tracked_rows = [row for row in rows if row.ref in TRACKED_REFS or row.ref == ANCHOR_REF]
    decision = _decision(rows, anchor_score=args.anchor_score)

    if args.json:
        print(
            json.dumps(
                {
                    "anchor_ref": ANCHOR_REF,
                    "anchor_label": ANCHOR_LABEL,
                    "anchor_score": args.anchor_score,
                    "tracked_refs": TRACKED_REFS,
                    "tracked_rows": [asdict(row) for row in tracked_rows],
                    "decision": decision,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    print(f"Anchor: {ANCHOR_REF} @ {args.anchor_score:.3f}  {ANCHOR_LABEL}")
    for ref in [*TRACKED_REFS, ANCHOR_REF]:
        row = next((candidate for candidate in rows if candidate.ref == ref), None)
        label = TRACKED_REFS.get(ref, ANCHOR_LABEL)
        if row is None:
            print(f"{ref}: MISSING from recent API page - {label}")
            continue
        score = "-" if row.score is None else f"{row.score:.3f}"
        print(
            f"{row.ref}: {row.status:8s} score={score:>7s}  "
            f"{_local_source_label(row):14s}  {label}"
        )
    print(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
