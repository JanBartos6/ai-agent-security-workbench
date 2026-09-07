from __future__ import annotations

import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SDK_BUNDLE_NAME = "ai-agent-security-multi-step-tool-attacks"


def resolve_sdk_root() -> Path:
    local_bundle = ROOT / SDK_BUNDLE_NAME
    if local_bundle.is_dir():
        return local_bundle

    env_root = os.environ.get("AICOMP_SDK_ROOT")
    if env_root:
        candidate = Path(env_root).resolve()
        if candidate.is_dir() and candidate.name == SDK_BUNDLE_NAME:
            return candidate
        nested = candidate / SDK_BUNDLE_NAME
        if nested.is_dir():
            return nested

    workstation_bundle = Path("G:/kaggle_competition") / SDK_BUNDLE_NAME
    if workstation_bundle.is_dir():
        return workstation_bundle

    return local_bundle


SDK_ROOT = resolve_sdk_root()
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))
