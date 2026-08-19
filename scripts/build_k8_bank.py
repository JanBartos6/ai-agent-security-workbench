"""Build a compact full-K8 prompt bank from profile_k8 artifacts.

This is intentionally read-only: it prints a ready-to-paste K8_BANK tuple for
attacks/05_validation_fill/attack.py, but does not edit attack.py.  Input rows
must come from scripts/profile_k8.py --mode bank artifacts.

Usage:
    ./.venv/Scripts/python scripts/build_k8_bank.py \
        runs/tmp/k8-bank-gpt-oss-current-300s.json \
        runs/tmp/k8-bank-gpt-oss-slotlabels-120s.json \
        runs/tmp/k8-bank-gpt-oss-allvariants-120s.json

    ./.venv/Scripts/python scripts/build_k8_bank.py ... \
        --out-json attacks/05_validation_fill/k8_bank_review.json \
        --out-md attacks/05_validation_fill/k8_bank_review.md
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
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
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args()

    seen: dict[tuple[str, int], dict[str, Any]] = {}
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
            value = {
                "template": template,
                "code": CODE_BY_TEMPLATE[template],
                "index": int(row["index"]),
                "sample_no": row.get("sample_no"),
                "source_artifact": str(path.relative_to(ROOT)),
                "elapsed_s": float(row.get("elapsed_s") or 0.0),
                "raw_per_s": float(row.get("raw_per_s") or 0.0),
                "completion_tokens": int(row.get("completion_tokens") or 0),
                "prompt_tokens": int(row.get("prompt_tokens") or 0),
                "posts": int(row.get("posts") or 0),
                "message": row.get("message") or "",
                "tool_urls": [
                    ((event.get("args") or {}).get("url"))
                    for event in (row.get("tool_events") or [])
                    if event.get("name") == "http.post" and event.get("ok") is True
                ],
            }
            current = seen.get(key)
            if current is None or (
                value["elapsed_s"],
                value["completion_tokens"],
            ) < (
                current["elapsed_s"],
                current["completion_tokens"],
            ):
                seen[key] = value

    items = [
        value
        for value in seen.values()
    ]
    items.sort(key=lambda item: (item["elapsed_s"], item["completion_tokens"]))
    counts = Counter(str(item["template"]) for item in items)
    print(f"full_k_unique={len(items)}")
    print(f"counts={dict(counts)}")
    if rejected_templates:
        print(f"ignored_templates={dict(rejected_templates)}")
    print("K8_BANK: tuple[tuple[str, int], ...] = (")
    chunks = [f"('{item['code']}',{item['index']})" for item in items]
    for start in range(0, len(chunks), 8):
        print("    " + ", ".join(chunks[start : start + 8]) + ",")
    print(")")
    print("K8_BANK_CODE_CSV = (")
    code_chunks = [f"{item['code']}:{item['index']}" for item in items]
    for start in range(0, len(code_chunks), 40):
        prefix = "" if start == 0 else ","
        print('    "' + prefix + ",".join(code_chunks[start : start + 40]) + '"')
    print(")")

    if args.out_json is not None:
        out_json = (ROOT / args.out_json).resolve() if not args.out_json.is_absolute() else args.out_json
        out_json.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "k": args.k,
            "count": len(items),
            "counts_by_template": dict(counts),
            "ignored_templates": dict(rejected_templates),
            "artifacts": [
                str(((ROOT / path).resolve() if not path.is_absolute() else path).relative_to(ROOT))
                for path in args.artifacts
            ],
            "items": items,
        }
        out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {out_json}")

    if args.out_md is not None:
        out_md = (ROOT / args.out_md).resolve() if not args.out_md.is_absolute() else args.out_md
        out_md.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# K8 verified prompt bank",
            "",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            f"Full-K rows: {len(items)}",
            f"Counts by template: {dict(counts)}",
            "",
            "| rank | template | code | index | elapsed_s | raw_per_s | completion_tokens | prompt |",
            "|---:|---|---|---:|---:|---:|---:|---|",
        ]
        for rank, item in enumerate(items, start=1):
            prompt = str(item["message"]).replace("|", "\\|").replace("\n", " ")
            if len(prompt) > 180:
                prompt = prompt[:177] + "..."
            lines.append(
                f"| {rank} | {item['template']} | {item['code']} | {item['index']} "
                f"| {item['elapsed_s']:.3f} | {item['raw_per_s']:.3f} "
                f"| {item['completion_tokens']} | `{prompt}` |"
            )
        out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
