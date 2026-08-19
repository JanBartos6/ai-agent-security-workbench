"""Run gemma_lab with SDK-generated protobuf stubs already on sys.path.

This is a local sandbox convenience wrapper.  The public SDK normally compiles
protobuf stubs into a temp directory on first import.  Under Codex's restricted
filesystem sandbox that temp write can fail, so this wrapper exposes the SDK's
checked-in generated stubs and makes that first-import compilation step a no-op.
It does not change model parsing, guardrails, tools, or history rendering.
"""

from __future__ import annotations

import sys
import tempfile
import types
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = ROOT / "ai-agent-security-multi-step-tool-attacks"
GENERATED_PROTO_DIR = SDK_ROOT / "kaggle_evaluation" / "core" / "generated"
CORE_DIR = SDK_ROOT / "kaggle_evaluation" / "core"

sys.path[:0] = [str(ROOT), str(SDK_ROOT), str(GENERATED_PROTO_DIR)]

WORKSPACE_TEMP_DIR = ROOT / "codex_tmp" / "python_temp"
WORKSPACE_TEMP_DIR.mkdir(parents=True, exist_ok=True)


def _workspace_mkdtemp(
    suffix: str | None = None,
    prefix: str | None = None,
    dir: str | None = None,
) -> str:
    del dir
    safe_prefix = prefix or "tmp"
    safe_suffix = suffix or ""
    path = WORKSPACE_TEMP_DIR / f"{safe_prefix}{uuid.uuid4().hex}{safe_suffix}"
    path.mkdir(parents=True, exist_ok=False)
    return str(path)


tempfile.mkdtemp = _workspace_mkdtemp

core_module = types.ModuleType("kaggle_evaluation.core")
core_module.__path__ = [str(CORE_DIR)]  # type: ignore[attr-defined]
sys.modules.setdefault("kaggle_evaluation.core", core_module)

proto_compiler_module = types.ModuleType("kaggle_evaluation.core.proto_compiler")
proto_compiler_module.ensure_compiled = lambda: None  # type: ignore[attr-defined]
sys.modules.setdefault("kaggle_evaluation.core.proto_compiler", proto_compiler_module)

from scripts.gemma_lab import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
