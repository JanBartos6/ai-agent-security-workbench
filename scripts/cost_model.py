"""Internal cost model: predict T4 per-candidate time and LB score per template.

Token counts are hardware-independent and come from the prompt database
(``runs/prompt-db.jsonl``, populated by ``scripts/measure_tokens.py``).  The only
T4-specific quantities are the per-token time coefficients, which are priors
here and must be recalibrated from submission throughput:

    score / 0.09 = candidates completed before the 8,750s replay deadline
                 = 8,750s / per_candidate_cost

so a single timed-out submission of a known template backs out its T4 cost.
Local *seconds* never transfer (the 180->43 lesson); token counts do.

Model (per candidate):
    t4_s = prefill_s * prompt_tokens
           + decode_s * completion_tokens
           + generation_overhead_s * generations
           + tool_s * successful_tool_calls
           + overhead_s
    predicted = min(1000, normalized_score_per_fired * fire_rate * min(8750 / t4_s, 2000))

Decode is far more expensive per token than prefill on a T4 (sequential vs
parallel), which is exactly why the forge (fewer completion tokens) pays off.

Usage:
    ./.venv/Scripts/python scripts/cost_model.py
    ./.venv/Scripts/python scripts/cost_model.py --prefill-s 0.003 --decode-s 0.08
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DB = ROOT / "runs" / "prompt-db.jsonl"
REPLAY_BUDGET_S = 8750.0
HARD_N_CAP = 2000
SEVERITY_5_W = 16.0
CELL_BONUS = 2.0
SCORE_NORMALIZER = 200.0

# T4 priors (seconds per token / per candidate).  Recalibrate from submissions.
DEFAULTS = {
    "gpt_oss": {
        "prefill_s": 0.003,
        "decode_s": 0.09,
        "generation_overhead_s": 0.0,
        "tool_s": 0.05,
        "overhead_s": 1.0,
    },
    "gemma": {
        "prefill_s": 0.002,
        "decode_s": 0.09,
        "generation_overhead_s": 0.0,
        "tool_s": 0.05,
        "overhead_s": 1.0,
    },
}

from scripts.private_surrogate import infer_private_survival_prior  # noqa: E402


def load_db() -> dict[tuple[str, str], dict[str, Any]]:
    agg: dict[tuple[str, str], dict[str, Any]] = {}
    if not DB.is_file():
        return agg
    for line in DB.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = (rec.get("model"), rec.get("variant"))
        slot = agg.setdefault(
            key,
            {
                "prompt": [],
                "completion": [],
                "generations": [],
                "tool_calls": [],
                "successful_tool_calls": [],
                "fired": 0,
                "posts": 0,
                "n": 0,
                "records": [],
            },
        )
        slot["prompt"].append(rec.get("prompt_tokens") or 0)
        slot["completion"].append(rec.get("completion_tokens") or 0)
        slot["generations"].append(rec.get("generations") or 0)
        slot["tool_calls"].append(rec.get("tool_calls") or rec.get("posts") or 0)
        slot["successful_tool_calls"].append(
            rec.get("successful_tool_calls") or rec.get("posts") or 0
        )
        slot["n"] += 1
        slot["fired"] += 1 if rec.get("fired") else 0
        slot["posts"] += int(rec.get("posts") or 0)
        slot["records"].append(rec)
    return agg


def build_rows(
    agg: dict[tuple[str, str], dict[str, Any]],
    *,
    prefill_override: float | None = None,
    decode_override: float | None = None,
    generation_overhead_override: float | None = None,
    tool_override: float | None = None,
    overhead_override: float | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for (model, variant), slot in agg.items():
        coef = DEFAULTS.get(model, DEFAULTS["gpt_oss"])
        prefill_s = prefill_override if prefill_override is not None else coef["prefill_s"]
        decode_s = decode_override if decode_override is not None else coef["decode_s"]
        generation_overhead_s = (
            generation_overhead_override
            if generation_overhead_override is not None
            else coef["generation_overhead_s"]
        )
        tool_s = tool_override if tool_override is not None else coef["tool_s"]
        overhead_s = overhead_override if overhead_override is not None else coef["overhead_s"]

        prompt = statistics.median(slot["prompt"])
        completion = statistics.median(slot["completion"])
        generations = statistics.median(slot["generations"])
        tool_calls = statistics.median(slot.get("tool_calls") or [0])
        successful_tool_calls = statistics.median(
            slot.get("successful_tool_calls") or [0]
        )
        fire_rate = slot["fired"] / slot["n"] if slot["n"] else 0.0
        posts_per_fired = slot["posts"] / slot["fired"] if slot["fired"] else 1.0
        # raw per firing candidate = 16 * posts + 2 (one cell per candidate).
        raw_per_fired = SEVERITY_5_W * posts_per_fired + CELL_BONUS
        normalized_per_fired = raw_per_fired / SCORE_NORMALIZER

        private_survival = infer_private_survival_prior(
            model=str(model),
            variant=str(variant),
            fire_rate=fire_rate,
            records=slot.get("records") or (),
        )

        t4_s = (
            prefill_s * prompt
            + decode_s * completion
            + generation_overhead_s * generations
            + tool_s * successful_tool_calls
            + overhead_s
        )
        n_completed = min(REPLAY_BUDGET_S / t4_s, HARD_N_CAP)
        predicted = min(1000.0, normalized_per_fired * fire_rate * n_completed)
        private_predicted = predicted * private_survival
        expected_norm_per_s = (
            normalized_per_fired * fire_rate * private_survival / t4_s if t4_s else 0.0
        )
        # Hardware-independent throughput ranking: normalized points per 1k tokens.
        pts_per_1k_tokens = (
            1000.0 * normalized_per_fired * fire_rate / (prompt + completion)
            if (prompt + completion) > 0
            else 0.0
        )
        rows.append(
            {
                "model": model,
                "variant": variant,
                "prompt": prompt,
                "completion": completion,
                "generations": generations,
                "tool_calls": tool_calls,
                "successful_tool_calls": successful_tool_calls,
                "fire_rate": fire_rate,
                "private_survival": private_survival,
                "posts_per_fired": posts_per_fired,
                "raw_per_fired": raw_per_fired,
                "normalized_per_fired": normalized_per_fired,
                "t4_s": t4_s,
                "predicted_score": predicted,
                "private_predicted_score": private_predicted,
                "expected_norm_per_s": expected_norm_per_s,
                "pts_per_1k_tokens": pts_per_1k_tokens,
            }
        )
    rows.sort(key=lambda r: (-r["predicted_score"], r["model"], r["variant"]))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefill-s", type=float, help="override prefill s/token (all models)")
    parser.add_argument("--decode-s", type=float, help="override decode s/token (all models)")
    parser.add_argument(
        "--generation-overhead-s",
        type=float,
        help="override per-generation overhead seconds (all models)",
    )
    parser.add_argument("--tool-s", type=float, help="override per-successful-tool overhead seconds")
    parser.add_argument("--overhead-s", type=float, help="override per-candidate overhead s")
    parser.add_argument(
        "--rank-by",
        choices=["public", "private", "density"],
        default="public",
        help="Sort by public predicted score, private-weighted score, or private score/sec.",
    )
    args = parser.parse_args()

    agg = load_db()
    if not agg:
        print(f"no data in {DB}; run scripts/measure_tokens.py first")
        return 1

    rows = build_rows(
        agg,
        prefill_override=args.prefill_s,
        decode_override=args.decode_s,
        generation_overhead_override=args.generation_overhead_s,
        tool_override=args.tool_s,
        overhead_override=args.overhead_s,
    )
    if args.rank_by == "private":
        rows.sort(key=lambda r: (-r["private_predicted_score"], r["model"], r["variant"]))
    elif args.rank_by == "density":
        rows.sort(key=lambda r: (-r["expected_norm_per_s"], r["model"], r["variant"]))

    print("=== predicted T4 score per template (priors, recalibrate from submissions) ===")
    print(
        f"{'model':<9} {'variant':<14} {'prompt':>7} {'comp':>6} {'gen':>4} "
        f"{'tool':>4} {'fire':>5} {'priv':>5} {'t4_s':>7} {'pub':>7} {'pvt':>7}"
    )
    for r in rows:
        print(
            f"{r['model']:<9} {r['variant']:<14} {r['prompt']:>7.0f} "
            f"{r['completion']:>6.0f} {r['generations']:>4.1f} "
            f"{r['successful_tool_calls']:>4.1f} {r['fire_rate']:>5.2f} "
            f"{r['private_survival']:>5.2f} {r['t4_s']:>7.1f} "
            f"{r['predicted_score']:>7.1f} {r['private_predicted_score']:>7.1f}"
        )
    print(
        "\npriv is a heuristic private-transfer survival prior, not hidden-LB evidence. "
        "t4_s includes prefill, decode, per-generation overhead, successful tool calls, "
        "and fixed candidate overhead."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
