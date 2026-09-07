"""Audit locally prepared Kaggle notebook packages without submitting them.

The competition workflow creates many ignored ``runs/kaggle-*`` folders.  A
folder name alone is not reliable evidence of what will be submitted: notebooks
embed a full copy of ``attack.py`` and can become stale as the working tree
moves.  This helper inventories those local packages and reports:

- the embedded attack SHA-256,
- whether notebook metadata matches the embedded source,
- whether the embedded source still matches its declared source path, and
- whether the embedded source matches the current production attack.py.

It is read-only and never calls the Kaggle API.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_kaggle_notebook_attack import (  # noqa: E402
    DEFAULT_ATTACK,
    extract_embedded_attack,
    read_notebook_metadata,
    sha256_text,
)

CONSTANTS_OF_INTEREST = (
    "USE_GPT_DUPLICATE_K8",
    "GPT_DUPLICATE_K8_TEMPLATE",
    "GPT_DUPLICATE_K8_BANK_INDEX",
    "GPT_ONLINE_SELECT_K8",
    "GPT_ONLINE_SELECT_TEMPLATES",
    "GPT_ONLINE_SELECT_STRATEGY",
    "GPT_ONLINE_SELECT_HALVING_PROBES",
    "USE_GEMMA_K8_O",
    "GEMMA_K8_O_VARIANT",
    "USE_GPT_DEPUTY_HEDGE",
    "GPT_DEPUTY_HEDGE_N",
    "GPT_DEPUTY_HEDGE_POSITION",
)


@dataclass(frozen=True)
class PackageAudit:
    folder: str
    notebook: str | None
    title: str | None
    kernel_id: str | None
    embedded_sha256: str | None
    metadata_sha256: str | None
    metadata_matches_embedded: bool | None
    declared_attack_path: str | None
    declared_attack_exists: bool | None
    declared_attack_matches_embedded: bool | None
    current_attack_matches_embedded: bool | None
    constants: dict[str, Any]
    error: str | None = None


def _read_kernel_metadata(folder: Path) -> dict[str, Any]:
    metadata_path = folder / "kernel-metadata.json"
    if not metadata_path.is_file():
        return {}
    raw = json.loads(metadata_path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _notebook_path_from_folder(folder: Path) -> Path | None:
    metadata = _read_kernel_metadata(folder)
    code_file = metadata.get("code_file")
    if isinstance(code_file, str) and code_file:
        candidate = folder / code_file
        if candidate.is_file():
            return candidate
    notebooks = sorted(folder.glob("*.ipynb"))
    return notebooks[0] if notebooks else None


def _resolve_declared_attack_path(notebook_path: Path) -> Path | None:
    metadata = read_notebook_metadata(notebook_path).get("attack_source", {})
    if not isinstance(metadata, dict):
        return None
    raw_path = metadata.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return None
    declared = Path(raw_path)
    return declared if declared.is_absolute() else ROOT / declared


def _literal_constants(source: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    try:
        module = ast.parse(source)
    except SyntaxError:
        return values
    for node in module.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        name = target.id
        if name not in CONSTANTS_OF_INTEREST:
            continue
        try:
            values[name] = ast.literal_eval(node.value)
        except Exception:
            continue
    return values


def audit_package_folder(
    folder: Path,
    *,
    current_attack: Path = DEFAULT_ATTACK,
) -> PackageAudit:
    folder = folder.resolve()
    notebook_path = _notebook_path_from_folder(folder)
    kernel_metadata = _read_kernel_metadata(folder)
    title = kernel_metadata.get("title")
    kernel_id = kernel_metadata.get("id")
    if notebook_path is None:
        return PackageAudit(
            folder=str(folder),
            notebook=None,
            title=str(title) if title is not None else None,
            kernel_id=str(kernel_id) if kernel_id is not None else None,
            embedded_sha256=None,
            metadata_sha256=None,
            metadata_matches_embedded=None,
            declared_attack_path=None,
            declared_attack_exists=None,
            declared_attack_matches_embedded=None,
            current_attack_matches_embedded=None,
            constants={},
            error="no notebook found",
        )

    try:
        embedded_source = extract_embedded_attack(notebook_path)
        embedded_sha = sha256_text(embedded_source)
        notebook_metadata = read_notebook_metadata(notebook_path).get("attack_source", {})
        if not isinstance(notebook_metadata, dict):
            notebook_metadata = {}
        metadata_sha = notebook_metadata.get("sha256")
        declared_attack = _resolve_declared_attack_path(notebook_path)
        declared_exists = declared_attack.is_file() if declared_attack is not None else None
        declared_matches = None
        if declared_attack is not None and declared_attack.is_file():
            declared_matches = (
                sha256_text(declared_attack.read_text(encoding="utf-8")) == embedded_sha
            )
        current_matches = None
        if current_attack.is_file():
            current_matches = (
                sha256_text(current_attack.read_text(encoding="utf-8")) == embedded_sha
            )
        return PackageAudit(
            folder=str(folder),
            notebook=str(notebook_path.resolve()),
            title=str(title) if title is not None else None,
            kernel_id=str(kernel_id) if kernel_id is not None else None,
            embedded_sha256=embedded_sha,
            metadata_sha256=str(metadata_sha) if metadata_sha is not None else None,
            metadata_matches_embedded=metadata_sha in (None, embedded_sha),
            declared_attack_path=(
                str(declared_attack.resolve()) if declared_attack is not None else None
            ),
            declared_attack_exists=declared_exists,
            declared_attack_matches_embedded=declared_matches,
            current_attack_matches_embedded=current_matches,
            constants=_literal_constants(embedded_source),
            error=None,
        )
    except Exception as exc:  # noqa: BLE001
        return PackageAudit(
            folder=str(folder),
            notebook=str(notebook_path.resolve()),
            title=str(title) if title is not None else None,
            kernel_id=str(kernel_id) if kernel_id is not None else None,
            embedded_sha256=None,
            metadata_sha256=None,
            metadata_matches_embedded=None,
            declared_attack_path=None,
            declared_attack_exists=None,
            declared_attack_matches_embedded=None,
            current_attack_matches_embedded=None,
            constants={},
            error=f"{type(exc).__name__}: {exc}",
        )


def audit_packages(
    runs_dir: Path = ROOT / "runs",
    *,
    current_attack: Path = DEFAULT_ATTACK,
    pattern: str = "kaggle-*",
) -> list[PackageAudit]:
    if not runs_dir.is_dir():
        return []
    folders = sorted(path for path in runs_dir.glob(pattern) if path.is_dir())
    return [
        audit_package_folder(folder, current_attack=current_attack)
        for folder in folders
    ]


def _short_sha(value: str | None) -> str:
    return "-" if not value else value[:12]


def _state(value: bool | None) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "-"


def _relative(path: str | None) -> str:
    if not path:
        return "-"
    try:
        return str(Path(path).resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return path


def print_table(rows: list[PackageAudit]) -> None:
    print(
        "folder | sha | metadata | declared | current | GPT template | selector | Gemma | hedge"
    )
    print("--- | --- | --- | --- | --- | --- | --- | --- | ---")
    for row in rows:
        constants = row.constants
        print(
            " | ".join(
                (
                    _relative(row.folder),
                    _short_sha(row.embedded_sha256),
                    _state(row.metadata_matches_embedded),
                    _state(row.declared_attack_matches_embedded),
                    _state(row.current_attack_matches_embedded),
                    str(constants.get("GPT_DUPLICATE_K8_TEMPLATE", "-")),
                    str(constants.get("GPT_ONLINE_SELECT_K8", "-")),
                    str(constants.get("GEMMA_K8_O_VARIANT", "-")),
                    str(constants.get("GPT_DEPUTY_HEDGE_N", "-")),
                )
            )
        )
        if row.error:
            print(f"  error: {row.error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "runs")
    parser.add_argument("--current-attack", type=Path, default=DEFAULT_ATTACK)
    parser.add_argument("--pattern", default="kaggle-*")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()

    runs_dir = args.runs_dir if args.runs_dir.is_absolute() else ROOT / args.runs_dir
    current_attack = (
        args.current_attack
        if args.current_attack.is_absolute()
        else ROOT / args.current_attack
    )
    rows = audit_packages(runs_dir, current_attack=current_attack, pattern=args.pattern)
    if args.json:
        print(json.dumps([asdict(row) for row in rows], indent=2, sort_keys=True))
    else:
        print_table(rows)
    if args.fail_on_error and any(row.error for row in rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
