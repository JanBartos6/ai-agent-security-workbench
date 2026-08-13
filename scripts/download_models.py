from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from huggingface_hub import hf_hub_download


@dataclass(frozen=True)
class ModelSpec:
    name: str
    repo: str
    filename: str
    revision: str
    sha256: str


SPECS = {
    "gpt_oss": ModelSpec(
        name="gpt_oss",
        repo="unsloth/gpt-oss-20b-GGUF",
        filename="gpt-oss-20b-Q4_K_M.gguf",
        revision="ce6ba6163271f5d73dbe2a20b85e66d79126e942",
        sha256="c27536640e410032865dc68781d80a08b98f8db5e93575919af8ccc0568aeb4f",
    ),
    "gemma": ModelSpec(
        name="gemma",
        repo="unsloth/gemma-4-26B-A4B-it-GGUF",
        filename="gemma-4-26B-A4B-it-UD-Q4_K_M.gguf",
        revision="c099eb48e663fd284577b04978a94ffccb261841",
        sha256="f2c28b3dc4776931ac6f879e11f203dec637ea0f14267a86ec8f6165f63f293f",
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def download(spec: ModelSpec, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = Path(
        hf_hub_download(
            repo_id=spec.repo,
            filename=spec.filename,
            revision=spec.revision,
            local_dir=output_dir,
        )
    )
    actual_hash = sha256_file(path)
    if actual_hash != spec.sha256:
        raise RuntimeError(
            f"Hash mismatch for {path.name}: expected {spec.sha256}, got {actual_hash}"
        )
    print(f"verified {spec.name}: {path} ({actual_hash})")
    return {**asdict(spec), "path": str(path.resolve())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["gpt_oss", "gemma", "all"], default="all")
    parser.add_argument("--output-dir", type=Path, default=Path("models"))
    args = parser.parse_args()

    selected = list(SPECS) if args.model == "all" else [args.model]
    manifest = [download(SPECS[name], args.output_dir) for name in selected]
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

