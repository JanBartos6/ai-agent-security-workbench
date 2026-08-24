from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_sdk import compute_tree


ROOT = Path(__file__).resolve().parents[1]


def test_competition_bundle_is_unchanged() -> None:
    lock = json.loads((ROOT / "sdk-integrity.lock.json").read_text(encoding="utf-8"))
    from scripts.verify_sdk import resolve_bundle

    actual = compute_tree(resolve_bundle(lock))
    expected = (lock["file_count"], lock["total_bytes"], lock["tree_sha256"])
    assert actual == expected

