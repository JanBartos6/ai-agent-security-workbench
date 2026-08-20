"""Build an attack.py variant from a git ref with explicit constant overrides.

This is a safety helper for hosted Kaggle submissions.  It avoids manually
changing production defaults when preparing one-off experiments:

    ./.venv/Scripts/python.exe scripts/build_attack_variant.py \
        --git-ref eca381f \
        --source attacks/05_validation_fill/attack.py \
        --out runs/variants/gpt-duplicate-baseline/attack.py \
        --set USE_GPT_DUPLICATE_K8=True \
        --expect SLOW_MULTIPOST_TEMPLATE='"current"' \
        --expect USE_GEMMA_K8_O=False

The generated file lives under ignored ``runs/`` by convention.  The source ref,
sets, expects, and resolved constants are written to a neighboring manifest.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ASSIGN_RE = re.compile(r"^(?P<indent>\s*)(?P<name>[A-Z][A-Z0-9_]*)\s*=\s*(?P<rhs>.*?)(?P<comment>\s+#.*)?$")


def _parse_literal(raw: str) -> Any:
    raw = raw.strip()
    try:
        return ast.literal_eval(raw)
    except Exception:
        if raw == "True":
            return True
        if raw == "False":
            return False
        if raw == "None":
            return None
        raise ValueError(f"not a Python literal: {raw!r}") from None


def _split_name_value(item: str) -> tuple[str, str, Any]:
    if "=" not in item:
        raise ValueError(f"expected NAME=VALUE, got {item!r}")
    name, raw_value = item.split("=", 1)
    name = name.strip()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
        raise ValueError(f"not an all-caps constant name: {name!r}")
    return name, raw_value.strip(), _parse_literal(raw_value)


def _read_source(source: Path, git_ref: str | None) -> tuple[str, str]:
    rel_source = source.as_posix()
    if git_ref:
        text = subprocess.check_output(
            ["git", "show", f"{git_ref}:{rel_source}"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )
        resolved_ref = subprocess.check_output(
            ["git", "rev-parse", "--short", git_ref],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        ).strip()
        return text, resolved_ref
    return (ROOT / source).read_text(encoding="utf-8"), "working-tree"


def _constant_values(text: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for line in text.splitlines():
        match = ASSIGN_RE.match(line)
        if not match:
            continue
        rhs = match.group("rhs").strip()
        try:
            values[match.group("name")] = _parse_literal(rhs)
        except ValueError:
            continue
    return values


def _apply_sets(text: str, sets: dict[str, str]) -> str:
    remaining = set(sets)
    out_lines: list[str] = []
    for line in text.splitlines():
        match = ASSIGN_RE.match(line)
        if match and match.group("name") in sets:
            name = match.group("name")
            comment = match.group("comment") or ""
            out_lines.append(f"{match.group('indent')}{name} = {sets[name]}{comment}")
            remaining.remove(name)
        else:
            out_lines.append(line)
    if remaining:
        raise ValueError(f"constants not found for --set: {sorted(remaining)}")
    return "\n".join(out_lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--git-ref", help="Read source from this git ref instead of working tree")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--set", dest="sets", action="append", default=[], help="Override NAME=VALUE")
    parser.add_argument(
        "--expect",
        dest="expects",
        action="append",
        default=[],
        help="Assert NAME=VALUE after overrides",
    )
    args = parser.parse_args()

    set_items = [_split_name_value(item) for item in args.sets]
    expect_items = [_split_name_value(item) for item in args.expects]
    set_raw = {name: raw for name, raw, _ in set_items}
    expect_values = {name: value for name, _, value in expect_items}

    text, resolved_ref = _read_source(args.source, args.git_ref)
    text = _apply_sets(text, set_raw)
    values = _constant_values(text)

    missing_expects = [name for name in expect_values if name not in values]
    if missing_expects:
        raise ValueError(f"constants not found for --expect: {missing_expects}")
    mismatches = {
        name: {"expected": expected, "actual": values[name]}
        for name, expected in expect_values.items()
        if values[name] != expected
    }
    if mismatches:
        raise ValueError(f"expectation mismatch: {mismatches}")

    out_path = (ROOT / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    compile(text, str(out_path), "exec")

    manifest = {
        "source": args.source.as_posix(),
        "git_ref": args.git_ref,
        "resolved_ref": resolved_ref,
        "out": args.out.as_posix(),
        "sets": {name: value for name, _, value in set_items},
        "expects": expect_values,
        "resolved_constants": {
            name: values.get(name)
            for name in sorted(set(expect_values) | {name for name, _, _ in set_items})
        },
    }
    manifest_path = out_path.with_suffix(out_path.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"wrote {manifest_path}")
    print(json.dumps(manifest["resolved_constants"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
