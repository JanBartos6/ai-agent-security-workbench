"""Verify that a Kaggle notebook embeds the expected attack.py source.

This catches the easy-to-miss failure mode where a generated notebook under
``runs/`` has the right name but still contains stale attack code.

Usage:
    ./.venv/Scripts/python scripts/verify_kaggle_notebook_attack.py \
        runs/kaggle-gpt-halving-gemma-r57/gpt-halving-gemma-r57.ipynb
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ATTACK = ROOT / "attacks" / "05_validation_fill" / "attack.py"

_ATTACK_START = "attack_code = r'''"
_ATTACK_END = "'''\nPath('/kaggle/working/attack.py').write_text(attack_code, encoding='utf-8')"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _cell_source_as_text(source: Any) -> str:
    if isinstance(source, list):
        return "".join(str(part) for part in source)
    if isinstance(source, str):
        return source
    return ""


def read_notebook_source(notebook_path: Path) -> str:
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    return "".join(_cell_source_as_text(cell.get("source", "")) for cell in notebook.get("cells", []))


def read_notebook_metadata(notebook_path: Path) -> dict[str, Any]:
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    metadata = notebook.get("metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def extract_embedded_attack(notebook_path: Path) -> str:
    source = read_notebook_source(notebook_path)
    start = source.find(_ATTACK_START)
    if start < 0:
        raise ValueError(f"{notebook_path} does not contain the attack_code raw-string marker")
    start += len(_ATTACK_START)
    end = source.find(_ATTACK_END, start)
    if end < 0:
        raise ValueError(f"{notebook_path} does not contain the attack_code write footer")
    return source[start:end]


def compare_notebook_attack(notebook_path: Path, attack_path: Path = DEFAULT_ATTACK) -> dict[str, Any]:
    notebook_path = notebook_path.resolve()
    attack_path = attack_path.resolve()
    expected_source = attack_path.read_text(encoding="utf-8")
    embedded_source = extract_embedded_attack(notebook_path)
    metadata = read_notebook_metadata(notebook_path).get("attack_source", {})
    if not isinstance(metadata, dict):
        metadata = {}
    expected_sha256 = sha256_text(expected_source)
    embedded_sha256 = sha256_text(embedded_source)
    metadata_sha256 = metadata.get("sha256")
    return {
        "notebook": str(notebook_path),
        "attack": str(attack_path),
        "expected_sha256": expected_sha256,
        "embedded_sha256": embedded_sha256,
        "metadata_sha256": metadata_sha256,
        "matches": embedded_source == expected_source,
        "metadata_matches_embedded": metadata_sha256 in (None, embedded_sha256),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("notebook", type=Path)
    parser.add_argument("--attack", type=Path, default=DEFAULT_ATTACK)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = compare_notebook_attack(args.notebook, args.attack)
    ok = bool(result["matches"] and result["metadata_matches_embedded"])
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = "OK" if ok else "STALE"
        print(f"{status}: {result['notebook']}")
        print(f"embedded: {result['embedded_sha256']}")
        print(f"expected: {result['expected_sha256']}")
        if result["metadata_sha256"] is not None:
            print(f"metadata: {result['metadata_sha256']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
