from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "sdk-integrity.lock.json"


def _relative_for_hash(path: Path, bundle: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return (Path(bundle.name) / path.relative_to(bundle)).as_posix()


def resolve_bundle(lock: dict[str, object]) -> Path:
    bundle_name = str(lock["bundle"])
    local_bundle = ROOT / bundle_name
    if local_bundle.is_dir():
        return local_bundle

    env_root = os.environ.get("AICOMP_SDK_ROOT")
    if env_root:
        candidate = Path(env_root).resolve()
        if candidate.is_dir() and candidate.name == bundle_name:
            return candidate
        nested = candidate / bundle_name
        if nested.is_dir():
            return nested

    return local_bundle


def compute_tree(bundle: Path) -> tuple[int, int, str]:
    bundle = bundle.resolve()
    rows: list[str] = []
    total_bytes = 0
    files = sorted(
        (
            path
            for path in bundle.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in {".pyc", ".pyo"}
        ),
        key=lambda p: p.as_posix(),
    )
    for path in files:
        payload = path.read_bytes()
        total_bytes += len(payload)
        relative = _relative_for_hash(path.resolve(), bundle)
        rows.append(f"{hashlib.sha256(payload).hexdigest()}  {relative}")
    digest = hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()
    return len(files), total_bytes, digest


def main() -> int:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    bundle = resolve_bundle(lock)
    if not bundle.is_dir():
        raise SystemExit(f"Competition bundle missing: {bundle}")

    actual = compute_tree(bundle)
    expected = (lock["file_count"], lock["total_bytes"], lock["tree_sha256"])
    if actual != expected:
        print("SDK INTEGRITY FAILURE")
        print(f"expected files={expected[0]} bytes={expected[1]} sha256={expected[2]}")
        print(f"actual   files={actual[0]} bytes={actual[1]} sha256={actual[2]}")
        return 1

    print(f"SDK intact: files={actual[0]} bytes={actual[1]} sha256={actual[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

