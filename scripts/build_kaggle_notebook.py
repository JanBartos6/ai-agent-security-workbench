"""Build a Kaggle submission notebook embedding a local attack.py.

The notebook writes ``attack.py`` to ``/kaggle/working/attack.py`` and then
serves the competition inference server.  On the non-rerun (Save & Run All)
path it writes a placeholder ``submission.csv``; the real scoring happens
during Kaggle's competition rerun.

Usage:
    ./.venv/Scripts/python scripts/build_kaggle_notebook.py \
        attacks/05_validation_fill/attack.py \
        runs/kaggle-validation-fill/validation-fill.ipynb \
        "Validation Fill + Latency-Split Forge"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Kept byte-for-byte identical to the successfully-pushed diagnostic notebook,
# so the new push inherits the exact T4 runtime configuration that worked.
DOCKER_IMAGE = (
    "gcr.io/kaggle-private-byod/python@"
    "sha256:57e612b484cf3df5026ee4dcc3cb176974b22b2bc0937fb1e16132a8be4cb13c"
)
MACHINE_SHAPE = "NvidiaTeslaT4"

_CELL_HEADER = (
    "import glob, sys\n"
    "from pathlib import Path\n"
    "sys.argv = [sys.argv[0]]\n"
    "for candidate in glob.glob('/kaggle/input/**/kaggle_evaluation', recursive=True):\n"
    "    root = str(Path(candidate).parent)\n"
    "    if root not in sys.path: sys.path.insert(0, root)\n"
    "    break\n"
    "attack_code = r'''"
)

_CELL_FOOTER = (
    "'''\n"
    "Path('/kaggle/working/attack.py').write_text(attack_code, encoding='utf-8')\n"
    "import csv, os\n"
    "import kaggle_evaluation.jed_attack_134815.jed_attack_inference_server as server\n"
    "if os.getenv('KAGGLE_IS_COMPETITION_RERUN'):\n"
    "    server.JEDAttackInferenceServer().serve()\n"
    "else:\n"
    "    with open('/kaggle/working/submission.csv', 'w', newline='') as f:\n"
    "        w = csv.writer(f); w.writerow(['Id', 'Score'])\n"
    "        [w.writerow([r, 0.0]) for r in "
    "('gpt_oss_public', 'gpt_oss_private', 'gemma_public', 'gemma_private')]\n"
)


def build_notebook(attack_path: Path, out_path: Path, title: str) -> None:
    source = attack_path.read_text(encoding="utf-8")
    if "'''" in source:
        raise ValueError("attack.py contains ''' which would break the raw-string embed")
    if source.rstrip().endswith("\\"):
        raise ValueError("attack.py ends with a backslash which would break the raw-string embed")

    cell_source = _CELL_HEADER + source + _CELL_FOOTER
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": cell_source.splitlines(keepends=True),
            }
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(notebook, indent=1), encoding="utf-8")

    # kernel-metadata.json: same fields as the pushed diagnostic.
    metadata = {
        "id": f"janbartos/{out_path.stem}",
        "title": title,
        "code_file": out_path.name,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": False,
        "keywords": [],
        "dataset_sources": [],
        "kernel_sources": [],
        "competition_sources": ["ai-agent-security-multi-step-tool-attacks"],
        "model_sources": [],
        "docker_image": DOCKER_IMAGE,
        "machine_shape": MACHINE_SHAPE,
    }
    (out_path.parent / "kernel-metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(f"wrote {out_path}")
    print(f"wrote {out_path.parent / 'kernel-metadata.json'}")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    attack_path = (ROOT / sys.argv[1]).resolve()
    out_path = (ROOT / sys.argv[2]).resolve()
    title = sys.argv[3] if len(sys.argv) > 3 else out_path.stem
    build_notebook(attack_path, out_path, title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
