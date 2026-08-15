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
    t4_s = prefill_s * prompt_tokens + decode_s * completion_tokens + overhead_s
    predicted = min(1000, 0.09 * fire_rate * min(8750 / t4_s, 2000))

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
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "runs" / "prompt-db.jsonl"
REPLAY_BUDGET_S = 8750.0
HARD_N_CAP = 2000
SEVERITY_5_W = 16.0
CELL_BONUS = 2.0

# T4 priors (seconds per token / per candidate).  Recalibrate from submissions.
DEFAULTS = {
    "gpt_oss": {"prefill_s": 0.003, "decode_s": 0.09, "overhead_s": 1.0},
    "gemma": {"prefill_s": 0.002, "decode_s": 0.09, "overhead_s": 1.0},
}


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
                "fired": 0,
                "posts": 0,
                "n": 0,
            },
        )
        slot["prompt"].append(rec.get("prompt_tokens") or 0)
        slot["completion"].append(rec.get("completion_tokens") or 0)
        slot["generations"].append(rec.get("generations") or 0)
        slot["n"] += 1
        slot["fired"] += 1 if rec.get("fired") else 0
        slot["posts"] += int(rec.get("posts") or 0)
    return agg


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefill-s", type=float, help="override prefill s/token (all models)")
    parser.add_argument("--decode-s", type=float, help="override decode s/token (all models)")
    parser.add_argument("--overhead-s", type=float, help="override per-candidate overhead s")
    args = parser.parse_args()

    agg = load_db()
    if not agg:
        print(f"no data in {DB}; run scripts/measure_tokens.py first")
        return 1

    rows = []
    for (model, variant), slot in agg.items():
        coef = DEFAULTS.get(model, DEFAULTS["gpt_oss"])
        prefill_s = args.prefill_s if args.prefill_s is not None else coef["prefill_s"]
        decode_s = args.decode_s if args.decode_s is not None else coef["decode_s"]
        overhead_s = args.overhead_s if args.overhead_s is not None else coef["overhead_s"]

        prompt = statistics.median(slot["prompt"])
        completion = statistics.median(slot["completion"])
        generations = statistics.median(slot["generations"])
        fire_rate = slot["fired"] / slot["n"] if slot["n"] else 0.0
        posts_per_fired = slot["posts"] / slot["fired"] if slot["fired"] else 1.0
        # raw per firing candidate = 16 * posts + 2 (one cell per candidate).
        raw_per_fired = SEVERITY_5_W * posts_per_fired + CELL_BONUS

        t4_s = prefill_s * prompt + decode_s * completion + overhead_s
        n_completed = min(REPLAY_BUDGET_S / t4_s, HARD_N_CAP)
        predicted = min(1000.0, 0.09 * fire_rate * n_completed)
        # Hardware-independent throughput ranking: points per 1k tokens.
        pts_per_1k_tokens = (
            1000.0 * (raw_per_fired * fire_rate) / (prompt + completion)
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
                "fire_rate": fire_rate,
                "posts_per_fired": posts_per_fired,
                "raw_per_fired": raw_per_fired,
                "t4_s": t4_s,
                "predicted_score": predicted,
                "pts_per_1k_tokens": pts_per_1k_tokens,
            }
        )

    rows.sort(key=lambda r: (-r["predicted_score"], r["model"], r["variant"]))
    print("=== predicted T4 score per template (priors, recalibrate from submissions) ===")
    print(
        f"{'model':<9} {'variant':<14} {'prompt':>7} {'comp':>6} {'fire':>5} "
        f"{'t4_s':>7} {'pred':>7} {'pts/1k':>8}"
    )
    for r in rows:
        print(
            f"{r['model']:<9} {r['variant']:<14} {r['prompt']:>7.0f} "
            f"{r['completion']:>6.0f} {r['fire_rate']:>5.2f} {r['t4_s']:>7.1f} "
            f"{r['predicted_score']:>7.1f} {r['pts_per_1k_tokens']:>8.2f}"
        )
    print(
        "\npts/1k = points per 1000 tokens (hardware-independent ranking); "
        "t4_s/predicted use the --prefill-s/--decode-s/--overhead-s priors."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
