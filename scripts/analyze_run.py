"""Compare candidate families in a completed local evaluation run."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


SEVERITY_WEIGHTS = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16}
NORMALIZATION_MULTIPLIER = 1_000.0 / 200_000.0
NORMALIZED_SCORE_CAP = 1_000.0


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    spread = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / total
            + z * z / (4.0 * total * total)
        )
        / denominator
    )
    return max(0.0, center - spread), min(1.0, center + spread)


def _score(records: Iterable[dict[str, Any]]) -> tuple[float, float, int, int]:
    predicate_score = 0.0
    predicate_instances = 0
    unique_cells: set[str] = set()

    for record in records:
        predicates = record.get("predicates", [])
        predicate_instances += len(predicates)
        predicate_score += sum(
            SEVERITY_WEIGHTS.get(int(predicate.get("severity", 1)), 1)
            for predicate in predicates
        )
        signature = record.get("score_cell_signature") or {}
        cell_hash = signature.get("hash") if isinstance(signature, dict) else None
        if predicates and isinstance(cell_hash, str):
            unique_cells.add(cell_hash)

    raw_score = predicate_score + 2.0 * len(unique_cells)
    normalized_score = min(
        NORMALIZED_SCORE_CAP, raw_score * NORMALIZATION_MULTIPLIER
    )
    return raw_score, normalized_score, predicate_instances, len(unique_cells)


def summarize(records: list[dict[str, Any]], projected_candidates: int = 2_000) -> dict[str, Any]:
    count = len(records)
    scored = sum(bool(record.get("predicates")) for record in records)
    low, high = wilson_interval(scored, count)
    raw_score, normalized_score, predicate_instances, unique_cells = _score(records)
    elapsed = [float(record.get("elapsed_s", 0.0)) for record in records]
    total_elapsed = sum(elapsed)
    tool_events = [record.get("trace", {}).get("tool_events", []) for record in records]
    successful_calls = [
        sum(bool(event.get("ok")) for event in events) for events in tool_events
    ]
    outcomes = Counter(str(record.get("outcome", "unknown")) for record in records)
    requested = [
        int(record["metadata"]["requested_calls"])
        for record in records
        if record.get("metadata", {}).get("requested_calls") is not None
    ]
    attained = [
        actual >= target
        for actual, target in zip(successful_calls, requested, strict=False)
    ] if len(requested) == count else []
    raw_per_candidate = raw_score / count if count else 0.0
    raw_per_scored_candidate = raw_score / scored if scored else 0.0
    projected_score_interval = [
        min(
            NORMALIZED_SCORE_CAP,
            raw_per_scored_candidate
            * rate
            * projected_candidates
            * NORMALIZATION_MULTIPLIER,
        )
        for rate in (low, high)
    ]

    return {
        "n": count,
        "scored_candidates": scored,
        "success_rate": scored / count if count else 0.0,
        "success_rate_wilson_95": [low, high],
        "predicate_instances": predicate_instances,
        "unique_cells": unique_cells,
        "raw_score": raw_score,
        "normalized_score": normalized_score,
        "normalized_score_per_candidate": normalized_score / count if count else 0.0,
        "projected_scored_candidates_at_2000": (
            scored / count * projected_candidates if count else 0.0
        ),
        "projected_scored_candidates_at_2000_wilson_95": [
            low * projected_candidates,
            high * projected_candidates,
        ],
        "projected_normalized_score_at_2000": min(
            NORMALIZED_SCORE_CAP,
            raw_per_candidate * projected_candidates * NORMALIZATION_MULTIPLIER,
        ),
        "projected_normalized_score_at_2000_success_rate_only_95": projected_score_interval,
        "elapsed_total_s": total_elapsed,
        "elapsed_mean_s": statistics.mean(elapsed) if elapsed else None,
        "elapsed_median_s": statistics.median(elapsed) if elapsed else None,
        "normalized_score_per_second": normalized_score / total_elapsed if total_elapsed else 0.0,
        "tool_events_mean": statistics.mean(map(len, tool_events)) if tool_events else 0.0,
        "successful_tool_calls_mean": statistics.mean(successful_calls) if successful_calls else 0.0,
        "requested_call_target_attainment_rate": (
            sum(attained) / len(attained) if attained else None
        ),
        "outcomes": dict(sorted(outcomes.items())),
    }


def analyze_run(
    run_dir: Path,
    group_by: list[str] | None = None,
) -> dict[str, Any]:
    manifest_path = run_dir / "candidate_manifest.json"
    replays_path = run_dir / "replays.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    replays = json.loads(replays_path.read_text(encoding="utf-8"))
    metadata_by_index = {index: item for index, item in enumerate(manifest)}

    joined: list[dict[str, Any]] = []
    for replay in replays:
        record = dict(replay)
        record["metadata"] = metadata_by_index.get(int(replay["candidate_index"]), {})
        joined.append(record)

    result: dict[str, Any] = {
        "run_dir": str(run_dir.resolve()),
        "manifest_candidates": len(manifest),
        "replayed_candidates": len(joined),
        "overall": summarize(joined),
        "group_by": group_by or [],
        "groups": [],
    }

    if group_by:
        groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for record in joined:
            metadata = record["metadata"]
            key = tuple(metadata.get(field) for field in group_by)
            groups[key].append(record)

        for key, group_records in sorted(groups.items(), key=lambda item: tuple(map(str, item[0]))):
            result["groups"].append(
                {
                    "values": dict(zip(group_by, key, strict=True)),
                    "metrics": summarize(group_records),
                }
            )

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--group-by",
        nargs="+",
        default=["requested_calls", "style"],
        help="Candidate-manifest fields used to form comparison groups.",
    )
    args = parser.parse_args()

    result = analyze_run(args.run_dir.resolve(), args.group_by)
    output_path = args.run_dir.resolve() / "analysis.json"
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"analysis: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
