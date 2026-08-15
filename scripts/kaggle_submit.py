"""Push a Kaggle notebook with SAVE_AND_RUN_ALL, then (optionally) submit it.

The stock ``kernels_push`` saves a version without running it, so the
notebook never produces the ``submission.csv`` output file that a code
competition submission requires (the submit endpoint rejects with
"Did not find provided Notebook Output File").  This replicates
``kernels_push`` but sets ``kernel_execution_type = SAVE_AND_RUN_ALL`` so the
notebook executes and emits its output file.

Usage:
    ./.venv/Scripts/python scripts/kaggle_submit.py runs/kaggle-validation-fill \
        --submit --message "..."
"""

from __future__ import annotations

import argparse
import json
import os
import time

from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.services.kernels_api_service import ApiSaveKernelRequest
from kagglesdk.kernels.types.kernels_enums import KernelExecutionType

COMPETITION = "ai-agent-security-multi-step-tool-attacks"


def push_with_run(api: KaggleApi, folder: str) -> dict:
    meta_file = os.path.join(folder, api.KERNEL_METADATA_FILE)
    with open(meta_file, encoding="utf-8") as f:
        meta = json.load(f)
    code_path = meta["code_file"]
    with open(os.path.join(folder, code_path), encoding="utf-8") as f:
        script_body = f.read()
    # kernels_push normalizes notebook source the same way before saving.
    json_body = json.loads(script_body)
    for cell in json_body.get("cells", []):
        if "outputs" in cell and cell["cell_type"] == "code":
            cell["outputs"] = []
        if "source" in cell and isinstance(cell["source"], list):
            cell["source"] = "".join(cell["source"])
    script_body = json.dumps(json_body)

    with api.build_kaggle_client() as kaggle:
        req = ApiSaveKernelRequest()
        req.slug = meta["id"]
        req.new_title = meta.get("title")
        req.text = script_body
        req.language = meta["language"]
        req.kernel_type = meta["kernel_type"]
        req.is_private = meta.get("is_private", True)
        req.enable_gpu = meta.get("enable_gpu", False)
        req.enable_tpu = meta.get("enable_tpu", False)
        req.enable_internet = meta.get("enable_internet", False)
        req.dataset_data_sources = meta.get("dataset_sources", [])
        req.competition_data_sources = meta.get("competition_sources", [])
        req.kernel_data_sources = meta.get("kernel_sources", [])
        req.model_data_sources = meta.get("model_sources", [])
        req.category_ids = meta.get("keywords", [])
        req.docker_image = meta.get("docker_image")
        req.machine_shape = meta.get("machine_shape")
        req.kernel_execution_type = KernelExecutionType.SAVE_AND_RUN_ALL
        resp = kaggle.kernels.kernels_api_client.save_kernel(req)
    result = {
        "ref": resp.ref,
        "url": resp.url,
        "version": resp.version_number,
        "kernel_id": resp.kernel_id,
    }
    print("pushed+run:", json.dumps(result))
    return result


def wait_until_done(api: KaggleApi, kernel: str, timeout_s: float = 60 * 30) -> str:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = api.kernels_status(kernel)
        state = normalize_status(getattr(status, "status", None))
        print("kernel status:", state)
        if state in ("complete", "error"):
            return state
        time.sleep(30)
    return "timeout"


def normalize_status(state) -> str:
    value = getattr(state, "value", state)
    return str(value).split(".")[-1].lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--timeout-s", type=float, default=60 * 30)
    parser.add_argument("--message", default="")
    args = parser.parse_args()

    api = KaggleApi()
    api.authenticate()
    result = push_with_run(api, args.folder)
    kernel = f"janbartos/{result['ref'].split('/')[-1]}"
    print("kernel:", kernel, "version:", result["version"])

    if args.wait or args.submit:
        wait_state = wait_until_done(api, kernel, timeout_s=args.timeout_s)
        if wait_state != "complete":
            raise SystemExit(f"kernel did not complete cleanly; status={wait_state}")

    if args.submit:
        resp = api.competition_submit_code(
            file_name="submission.csv",
            message=args.message,
            competition=COMPETITION,
            kernel=kernel,
            kernel_version=int(result["version"]),
        )
        print("submit response:", json.dumps(resp.to_dict() if hasattr(resp, "to_dict") else str(resp)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
