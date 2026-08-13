# AI Agent Security Workbench

Reproducible local research for Kaggle's [AI Agent Security - Multi-Step Tool Attacks](https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks/overview) competition.

The downloaded competition directory is deliberately treated as an immutable external input. It is excluded from Git, checked against `sdk-integrity.lock.json`, and imported through `PYTHONPATH`/`sys.path`. Our attacks, tests, runners, notes, and experiment records live outside it.

## Current status

- Competition SDK inspected: vendored `aicomp-sdk` 3.1.2, 145 files.
- Live rules and the August 2026 evaluator update reviewed.
- Deterministic offline evaluator and exact-GGUF runner scaffolded.
- Initial static replay baseline included at `attacks/00_static_marker/attack.py`.
- Model weights are intentionally not downloaded automatically (about 28.5 GB total).

## Quick start on Windows

```powershell
./scripts/bootstrap.ps1
./scripts/verify.ps1
./scripts/run.ps1 -Agent deterministic -BudgetSeconds 30
```

The deterministic agent is a harness smoke test, not a leaderboard proxy. A zero from it can coexist with a useful prompt for GPT-OSS/Gemma because its hard-coded parser does not preserve arbitrary `http.post` payloads.

For exact target-model replay, install a CUDA-capable `llama-cpp-python`, download the pinned GGUFs, then run one model at a time:

```powershell
./scripts/download-models.ps1 -Model all
./scripts/run.ps1 -Agent gpt_oss -BudgetSeconds 300
./scripts/run.ps1 -Agent gemma -BudgetSeconds 300
```

The model runner reuses the competition's own GGUF server, target-specific agent wrapper, Gemma parser patch, Gym environment, public guardrail, predicates, cell calculation, and scoring code. See [docs/OFFLINE_EVALUATION.md](docs/OFFLINE_EVALUATION.md) for the remaining parity caveats.

## Repository map

- `attacks/` — one self-contained `attack.py` per experiment.
- `scripts/` — bootstrap, integrity, model download, evaluation, and PowerShell wrappers.
- `tests/` — contract, scoring, and bundle-integrity checks.
- `docs/COMPETITION.md` — mechanics and scoring, grounded in the live page and SDK.
- `docs/STRATEGY.md` — prioritized research plan.
- `runs/` — generated JSON reports and traces; ignored until deliberately promoted.

## Research discipline

Every comparison should record the SDK tree hash, attack file hash, target model revision/hash, agent, guardrail, seed, candidate count, replay count, wall time, predicate counts, and normalized score. Change one experimental variable at a time. Do not compare pre-update and post-update Kaggle scores as though they came from the same evaluator.

This project is for the competition's deterministic sandbox. It does not target live services or real credentials.

