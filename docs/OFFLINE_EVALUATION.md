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

The two Q4 files fit the machine's combined 20 GB VRAM only sequentially, and Gemma leaves little headroom. The machine has 128 GB system RAM, so partial CPU offload is safe if full multi-GPU offload is unstable. Keep the 8,192-token context and 1,024-token output cap from the gateway.

`llama-cpp-python` must be CUDA-enabled and recent enough to recognize both architectures and their chat templates. A CPU-only wheel can look installed while making realistic replay impractically slow. Verify backend logs and at least one parsed tool call for each target before collecting experimental results.

## Run artifacts

Each `scripts/evaluate_local.py` run creates a timestamped directory under `runs/` with:

- `summary.json`: score, raw score, counts, hashes, model label, seed, limits, and timing.
- `findings.json`: evaluator-owned replay traces and predicates.

The full Kaggle gateway generates candidates separately for each model and replays each model's candidates against both guardrails. The local runner evaluates one model/public guardrail at a time so memory is released between targets. The private guardrail is unavailable by design.

