"""Build a compact full-K8 prompt bank from profile_k8 artifacts.

This is intentionally read-only: it prints a ready-to-paste K8_BANK tuple for
attacks/05_validation_fill/attack.py, but does not edit attack.py.  Input rows
must come from scripts/profile_k8.py --mode bank artifacts.

Usage:
    ./.venv/Scripts/python scripts/build_k8_bank.py \
        runs/tmp/k8-bank-gpt-oss-current-300s.json \
        runs/tmp/k8-bank-gpt-oss-slotlabels-120s.json \
        runs/tmp/k8-bank-gpt-oss-allvariants-120s.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CODE_BY_TEMPLATE = {
    "current": "C",
    "slotlabels": "S",
    "compact": "P",
}


def load_rows(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("rows")
    if not isinstance(rows, list):
        raise ValueError(f"{path} does not contain a list at rows")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="+", type=Path)
    parser.add_argument("--k", type=int, default=8)
    args = parser.parse_args()

    seen: dict[tuple[str, int], tuple[float, int]] = {}
    rejected_templates: Counter[str] = Counter()
    for raw_path in args.artifacts:
        path = (ROOT / raw_path).resolve() if not raw_path.is_absolute() else raw_path
        for row in load_rows(path):
            if row.get("kind") != "k8":
                continue
            template = str(row.get("template") or "current")
            if template not in CODE_BY_TEMPLATE:
                rejected_templates[template] += 1
                continue
            if int(row.get("posts") or 0) != args.k:
                continue
            key = (template, int(row["index"]))
            value = (float(row.get("elapsed_s") or 0.0), int(row.get("completion_tokens") or 0))
            if key not in seen or value < seen[key]:
                seen[key] = value

    items = [
        (elapsed, CODE_BY_TEMPLATE[template], index, completion_tokens, template)
        for (template, index), (elapsed, completion_tokens) in seen.items()
    ]
    items.sort()
    counts = Counter(item[4] for item in items)
    print(f"full_k_unique={len(items)}")
    print(f"counts={dict(counts)}")
    if rejected_templates:
        print(f"ignored_templates={dict(rejected_templates)}")
    print("K8_BANK: tuple[tuple[str, int], ...] = (")
    chunks = [f"('{code}',{index})" for _, code, index, _, _ in items]
    for start in range(0, len(chunks), 8):
        print("    " + ", ".join(chunks[start : start + 8]) + ",")
    print(")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
