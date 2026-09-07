# AI Agent Security Workbench

Python tools I built for generating attack candidates, replaying them against tool-using AI agents, and analysing scoring and runtime in OpenAI's [AI Agent Security: Multi-Step Tool Attacks](https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks/overview) Kaggle competition.

**Result: 16th on the public leaderboard out of 4,251 teams.** [Public leaderboard](https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks/leaderboard?tab=public)

This is a public-leaderboard result, not a final overall placement. The approach did not transfer successfully to the private evaluation. The repository documents the implementation, experiments and limitations, rather than claiming general robustness from the public score.

## What I built

- **Local evaluation:** runners that load attack implementations, replay candidates through the competition SDK, and save scores, traces, configuration and timing.
- **Experiment analysis:** tools to compare candidate families, measure token use and latency, and investigate differences between local and hosted results.
- **Repeatability checks:** pinned Python dependencies and model revisions, file hashes, and tests for scoring, candidate contracts and SDK integrity.
- **Experiment implementations:** baseline variants and adaptations of public competition approaches, with local analysis and hosted-result notes.

The validation-fill implementation adapts public approaches credited to **pilkwang, canqiang and kaiwalya**, as documented in its [source header](attacks/05_validation_fill/attack.py). I do not claim to have originated those techniques. The competition SDK, target models and their components are external dependencies.

## Where to start

| Area | Code or documentation |
| --- | --- |
| Evaluation and saved run artifacts | [evaluate_local.py](scripts/evaluate_local.py) |
| Candidate-family comparisons | [analyze_run.py](scripts/analyze_run.py), [analysis tests](tests/test_analysis.py) |
| Scoring and SDK checks | [scoring tests](tests/test_scoring.py), [SDK integrity tests](tests/test_sdk_integrity.py) |
| Notebook packaging checks | [source verifier](scripts/verify_kaggle_notebook_attack.py), [package audit](scripts/audit_kaggle_packages.py) |
| Local versus hosted evaluation | [Offline evaluation](docs/OFFLINE_EVALUATION.md) |
| Experiment history | [Experiment log](docs/EXPERIMENTS.md), [hosted regression analysis](docs/REGRESSION_FORENSICS_2026-08-20.md) |

For a small example of what the tests verify, the [scoring tests](tests/test_scoring.py) check that a synthetic severity-five finding scores **0.09**, while two findings in the same score cell total **0.17**, not 0.18: the novelty bonus is not awarded twice. These are unit-test expectations, not measured attack success rates.

## Run locally

The documented setup is **Windows with PowerShell and Python 3.12**. A fresh clone is not self-contained: the competition bundle must be obtained separately through Kaggle. Target-model replay also requires large model downloads and a compatible local runtime.

### 1. Add the competition bundle

Clone the repository, open PowerShell in its root, and place the downloaded bundle at:

```text
ai-agent-security-multi-step-tool-attacks/
    aicomp_sdk/
    ...remaining competition files
```

Keep the complete bundle unchanged. It is excluded from Git and checked against [sdk-integrity.lock.json](sdk-integrity.lock.json). A different bundle version will fail that check; do not bypass it merely to make verification pass.

### 2. Install dependencies and verify

```powershell
./scripts/bootstrap.ps1
./scripts/verify.ps1
```

Verification checks the SDK bundle and runs the test suite. It requires the external bundle even if no target model is loaded.

### 3. Run a smoke test

```powershell
./scripts/run.ps1 -Agent deterministic -BudgetSeconds 30
```

The deterministic agent checks the evaluation plumbing, not LLM attack quality. Its score is not a leaderboard proxy, and a zero does not by itself indicate a broken setup.

Each completed run writes a timestamped directory under `runs/`, including `summary.json` and `findings.json`. To compare a run's candidate families, replace `<run-id>` below with that directory's name:

```powershell
.venv/Scripts/python.exe scripts/analyze_run.py runs/<run-id> --group-by requested_calls style
```

### 4. Optional: replay against the target models

Read the [runtime requirements and model details](docs/OFFLINE_EVALUATION.md) first. The supplied installer is tailored to a Windows workstation with a Ryzen 5900X and RTX 3080 GPUs; it requires Visual Studio 2022 C++ tools and CUDA. It is not a universal GPU installer.

```powershell
./scripts/install-model-runtime.ps1
./scripts/download-models.ps1 -Model all
./scripts/run.ps1 -Agent gpt_oss -BudgetSeconds 300
./scripts/run.ps1 -Agent gemma -BudgetSeconds 300 -GpuLayers 24 -TensorSplit '0.57,0.43'
```

These examples use the runner's static baseline by default, not the final competition submission. The Gemma offload settings are workstation-specific. Models are loaded one at a time; the pinned downloads total approximately 28.5 GB.

The local runner passes a fixed candidate count. For validation-fill implementations, this bypasses live candidate selection, so a fixed-count replay is not a reproduction of the full submission workflow.

## Evaluation limits

- **Notebook contents must match the intended source.** Build a fresh notebook when changing an implementation and verify the embedded source hash with the notebook verifier. An old notebook's title is not evidence that it contains the current code.
- **Local runs are not Kaggle submissions.** Model revisions, GPU hardware, runtime builds and time budgets can differ.
- **The private guardrail is unavailable.** The repository's `private-surrogate` option is a local stress test, not evidence about the hidden evaluator.
- **Public success did not establish private robustness.** Some approaches depended on behaviour specific to the public guardrail.
- **Historical results are configuration-specific.** Scores in the experiment log should be read with their corresponding artifacts and evaluator versions. The current checkout is not presented as a one-command reproduction of 16th place.

The model runner reuses the competition's model wrappers, tool environment, guardrail and scoring code. See [Offline evaluation](docs/OFFLINE_EVALUATION.md) for the remaining differences.

## Repository layout

- `attacks/`: self-contained experiment implementations.
- `scripts/`: setup, integrity verification, model downloads, evaluation and analysis.
- `tests/`: contract, scoring, analysis, runtime and integrity checks.
- `docs/`: competition notes, experiments and evaluation limitations.
- `requirements-dev.lock.txt`: pinned Python dependencies.
- `runs/`: generated reports, traces and local experiment data; ignored by Git.
- `models/`: downloaded model files; ignored by Git.

For meaningful comparisons, record the SDK and attack hashes, model revision, agent, guardrail, seed, candidate and replay counts, wall time and score. Do not treat scores from different evaluator versions as directly comparable.

This project is for the competition sandbox. It does not target live services or real credentials.
