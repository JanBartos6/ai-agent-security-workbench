# AI Agent Security Workbench

Reproducible local research for Kaggle's [AI Agent Security - Multi-Step Tool Attacks](https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks/overview) competition.

The downloaded competition directory is deliberately treated as an immutable external input. It is excluded from Git, checked against `sdk-integrity.lock.json`, and imported through `PYTHONPATH`/`sys.path`. Our attacks, tests, runners, notes, and experiment records live outside it.

## Current status

- Competition SDK inspected: vendored `aicomp-sdk` 3.1.2, 145 files.
- Live rules and the August 2026 evaluator update reviewed.
- Deterministic offline evaluator and exact-GGUF runner scaffolded.
- Initial static replay baseline included at `attacks/00_static_marker/attack.py`.
- Structured 32-candidate factorial seed included at `attacks/01_factorial_seed/attack.py`.
- Two-thousand-candidate replay-density baseline included at `attacks/02_scaled_baseline/attack.py`.
- Balanced 200-candidate call-multiplicity sweep included at `attacks/03_multiplicity_sweep/attack.py`.
- Sixty-candidate Kaggle-harness control included at `attacks/04_kaggle_60_control/attack.py`; verified 60/60 scored locally on both GPT-OSS (full offload) and Gemma (24/30 layers).
- Validation-fill + replay-safe sizing + latency-split forge included at `attacks/05_validation_fill/attack.py` (port of the proven ~84-89 public architecture); now also overfill, fastest-first ordering, and optional prompt-cost/private-surrogate tooling. Live-fill loop verified via `scripts/verify_fill.py`; per-candidate token/latency measurement via `scripts/measure_tokens.py`.
- Both exact, pinned competition-model GGUFs and a workstation-native CUDA runtime are locally verified.

## Quick start on Windows

```powershell
./scripts/bootstrap.ps1
./scripts/verify.ps1
./scripts/run.ps1 -Agent deterministic -BudgetSeconds 30
```

The deterministic agent is a harness smoke test, not a leaderboard proxy. A zero from it can coexist with a useful prompt for GPT-OSS/Gemma because its hard-coded parser does not preserve arbitrary `http.post` payloads.

For exact target-model replay, install the pinned CUDA runtime, download the pinned GGUFs, then run one model at a time:

```powershell
./scripts/install-model-runtime.ps1
./scripts/download-models.ps1 -Model all
./scripts/run.ps1 -Agent gpt_oss -BudgetSeconds 300
./scripts/run.ps1 -Agent gemma -BudgetSeconds 300 -GpuLayers 24 -TensorSplit '0.57,0.43'
```

The installer reuses its ignored local wheel unless `-Rebuild` is supplied. It compiles llama.cpp for the Ryzen 5900X and RTX 3080s because the generic CUDA wheel enables AVX-512 and crashes during context creation on this CPU.

`-GpuLayers -1` requests full offload and is the default. llama.cpp automatically distributes layers across visible GPUs; `-TensorSplit '0.57,0.43'` overrides the weights when display usage makes the cards asymmetric. Verified profiles on this PC are full automatic offload for GPT-OSS and 24/30 offloaded layers for Gemma. Close GPU-heavy display applications before retrying full Gemma offload.

The model runner reuses the competition's own GGUF server, target-specific agent wrapper, Gemma parser patch, Gym environment, public guardrail, predicates, cell calculation, and scoring code. See [docs/OFFLINE_EVALUATION.md](docs/OFFLINE_EVALUATION.md) for the remaining parity caveats.

After a completed local run, compare candidate families and project their score density with:

```powershell
.venv/Scripts/python.exe scripts/analyze_run.py runs/<run-id> --group-by requested_calls style
```

For prompt-level throughput and private-transfer triage, use the token database
and stricter surrogate guardrail:

```powershell
.venv/Scripts/python.exe scripts/cost_model.py --rank-by public
.venv/Scripts/python.exe scripts/cost_model.py --rank-by private
.venv/Scripts/python.exe scripts/run.ps1 -Agent deterministic -Attack attacks/05_validation_fill/attack.py -CandidateCount 2 -Guardrail private-surrogate
```

The private-surrogate path is a pessimistic local stress test, not hidden
leaderboard evidence. It is meant to keep public-code loophole dependence visible
while ranking prompt families by estimated prefill, decode, generation, and tool
cost.

## Repository map

- `attacks/` — one self-contained `attack.py` per experiment.
- `scripts/` — bootstrap, integrity, model download, evaluation, and PowerShell wrappers.
- `requirements-dev.lock.txt` — exact verified Python 3.12 environment.
- `tests/` — contract, scoring, and bundle-integrity checks.
- `docs/COMPETITION.md` — mechanics and scoring, grounded in the live page and SDK.
- `docs/STRATEGY.md` — prioritized research plan.
- `docs/EXPERIMENTS.md` — concise ledger of promoted experiment results.
- `runs/` — generated JSON reports and traces; ignored until deliberately promoted.

## Research discipline

Every comparison should record the SDK tree hash, attack file hash, target model revision/hash, agent, guardrail, seed, candidate count, replay count, wall time, predicate counts, and normalized score. Change one experimental variable at a time. Do not compare pre-update and post-update Kaggle scores as though they came from the same evaluator.

This project is for the competition's deterministic sandbox. It does not target live services or real credentials.
