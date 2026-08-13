# Offline evaluation

## Three validation levels

1. **Contract/unit tests**: instant checks for SDK integrity, candidate shape, predicate score math, and hard limits.
2. **Deterministic agent**: verifies imports, Gym environment, public guardrail, replay loop, artifact writing, and scorer. It is not a model-quality proxy.
3. **Exact GGUF target wrapper**: uses the competition's model server and parser against local GGUF weights. This is the closest available target replay, but it cannot reproduce the private guardrail and may differ from Kaggle's cached model revision, llama.cpp build, T4 kernels, or container timing.

API-hosted OpenAI or Google models are useful as auxiliary prompt generators, critics, mutators, or trace classifiers. They are not substitutes for target evaluation: the scorer uses local quantized GPT-OSS/Gemma artifacts, specific chat templates and parsers, and an offline tool environment.

## Pinned current model artifacts

The download script pins the file revisions visible on Hugging Face on 2026-08-13 rather than following mutable `main`:

| Target | Repository/file | Revision | Expected SHA-256 | Size |
| --- | --- | --- | --- | ---: |
| GPT-OSS | `unsloth/gpt-oss-20b-GGUF/gpt-oss-20b-Q4_K_M.gguf` | `ce6ba6163271f5d73dbe2a20b85e66d79126e942` | `c27536640e410032865dc68781d80a08b98f8db5e93575919af8ccc0568aeb4f` | 11.6 GB |
| Gemma | `unsloth/gemma-4-26B-A4B-it-GGUF/gemma-4-26B-A4B-it-UD-Q4_K_M.gguf` | `c099eb48e663fd284577b04978a94ffccb261841` | `f2c28b3dc4776931ac6f879e11f203dec637ea0f14267a86ec8f6165f63f293f` | 16.9 GB |

The competition gateway follows repository/file defaults unless Kaggle supplies a pre-downloaded model path. Kaggle staff had not confirmed the exact cached Gemma artifact in the evaluation-update thread when checked. Therefore these are pinned current local artifacts, not a claim about the scoring container's byte hash.

## Windows setup notes

The two Q4 files are loaded sequentially. GPT-OSS fits the combined 20 GB VRAM at the competition's 8,192-token context. Gemma's 15.77 GiB weights plus its padded 8K KV/context buffers do not fit while the display GPU reserves about 2.7 GB, but 24 of its 30 layers fit with the remaining six in system RAM. The machine has 128 GB system RAM, so that fallback is safe. The 1,024-token output cap remains unchanged.

`scripts/install-model-runtime.ps1` builds pinned `llama-cpp-python` 0.3.34 with CUDA 12.6/SM86, AVX2/FMA/BMI2, and AVX-512 disabled. The official generic CUDA wheel detected both GPUs but crashed at context initialization with Windows status `0xc000001d` because it enabled AVX-512 on the Ryzen 5900X. The installer keeps the locally built wheel under ignored `runs/model-runtime-wheel/`, reuses it by default, and verifies the compiled flags and dependencies.

The runner keeps the competition context at 8,192 tokens. `-GpuLayers -1` requests full offload, `-GpuLayers 0` is CPU-only, and a positive count requests partial offload with remaining layers in system RAM. llama.cpp's default layer split distributes work across visible GPUs. If the display card has less available VRAM, pass explicit weights such as `-TensorSplit '0.57,0.43'`; the values are relative weights and need not sum to one. Treat any non-default split as a local performance setting, not part of the attack itself.

## Verified workstation profiles (2026-08-13)

| Target | Context | Offload | Result |
| --- | ---: | --- | --- |
| GPT-OSS 20B Q4_K_M | 8,192 | `-GpuLayers -1`, automatic split | Loaded, parsed `http.post`, one `EXFILTRATION` finding, score 0.09 |
| Gemma 4 26B-A4B UD-Q4_K_M | 8,192 | `-GpuLayers 24 -TensorSplit '0.57,0.43'` | Loaded, parsed `http.post`, one `EXFILTRATION` finding, score 0.09 |
| Gemma 4 26B-A4B UD-Q4_K_M | 8,192 | all 30 layers, `0.57/0.43` | Context allocation failed with current display-GPU occupancy; use partial offload |

These scores are smoke-test evidence that the real target wrappers and tool parsers work, not competitive baselines. The replay used one direct static candidate against the public guardrail.

## Run artifacts

Each `scripts/evaluate_local.py` run creates a timestamped directory under `runs/` with:

- `summary.json`: score, raw score, counts, hashes, model label, seed, limits, and timing.
- `findings.json`: evaluator-owned replay traces and predicates.

The full Kaggle gateway generates candidates separately for each model and replays each model's candidates against both guardrails. The local runner evaluates one model/public guardrail at a time so memory is released between targets. The private guardrail is unavailable by design.
