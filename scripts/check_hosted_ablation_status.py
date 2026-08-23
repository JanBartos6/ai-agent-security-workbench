"""Check hosted Kaggle ablations against the current public anchor.

This is a read-only helper.  It does not push kernels, submit notebooks, or edit
attack code.  The goal is to turn the pending hosted GPT ablation set into a
clear promotion/rollback decision as soon as Kaggle scoring completes.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Any

from kaggle.api.kaggle_api_extended import KaggleApi


COMPETITION = "ai-agent-security-multi-step-tool-attacks"
ANCHOR_REF = 55702490
ANCHOR_SCORE = 109.770

# These are the hosted ablations currently deciding whether to keep the
# local-best selector/bare/system-low branch or roll GPT back to the proven
# numeric template.
TRACKED_REFS: dict[int, str] = {
    55717477: "system-low numeric duplicate K8 + Gemma R57",
    55718913: "online select numeric/system-low K8 + Gemma R57",
    55720868: "online select system-low/proto/numeric K8 + Gemma R57",
    55721360: "bare-opaque selector K8 + Gemma R57",
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
        f"ROLLBACK: all tracked ablations completed at or below anchor {anchor_score:.3f}. "
        "Set GPT fallback/default back to current_numeric_1_8 and preserve 55702490."
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
    rows = [_to_status(submission) for submission in submissions]
    tracked_rows = [row for row in rows if row.ref in TRACKED_REFS or row.ref == ANCHOR_REF]
    decision = _decision(rows, anchor_score=args.anchor_score)

    if args.json:
        print(
            json.dumps(
                {
                    "anchor_ref": ANCHOR_REF,
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

    print(f"Anchor: {ANCHOR_REF} @ {args.anchor_score:.3f}")
    for ref in [*TRACKED_REFS, ANCHOR_REF]:
        row = next((candidate for candidate in rows if candidate.ref == ref), None)
        label = TRACKED_REFS.get(ref, "confirmed anchor")
        if row is None:
            print(f"{ref}: MISSING from recent API page - {label}")
            continue
        score = "-" if row.score is None else f"{row.score:.3f}"
        print(f"{row.ref}: {row.status:8s} score={score:>7s}  {label}")
    print(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
