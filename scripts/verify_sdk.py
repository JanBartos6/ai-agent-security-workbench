from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "sdk-integrity.lock.json"


def compute_tree(bundle: Path) -> tuple[int, int, str]:
    rows: list[str] = []
    total_bytes = 0
    files = sorted((path for path in bundle.rglob("*") if path.is_file()), key=lambda p: p.as_posix())
    for path in files:
        payload = path.read_bytes()
        total_bytes += len(payload)
        relative = path.relative_to(ROOT).as_posix()
        rows.append(f"{hashlib.sha256(payload).hexdigest()}  {relative}")
    digest = hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()
    return len(files), total_bytes, digest


def main() -> int:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    bundle = ROOT / lock["bundle"]
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

