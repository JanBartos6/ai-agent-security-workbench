# Kaggle regression forensics — 2026-08-20

## Confirmed hosted results

Fetched from the Kaggle submissions API on 2026-08-20.

| submission ref | commit | description | public score |
| --- | --- | --- | ---: |
| `55584698` | `9aab298` | current-only verified K8 bank 859 | `96.010` |
| `55625367` | `134b63f` | GPT slot-label K8 bank | `66.425` |
| `55627349` | `575e48b` | Gemma K8-O live bank 500 + GPT slotlabels K8 | `65.210` |
| `55628612` | `ba79bcc` | Gemma K8-O duplicate bank 500 + GPT slotlabels K8 | `65.210` |
| `55562414` | `14111ce` | earlier broad K8 multipost attempt | `65.070` |

## Primary diagnosis

The large failure happened before Gemma K8-O was enabled.

`55625367` changed the slow GPT-OSS row from the hosted-proven current-template
K8 bank to the local slot-label K8 bank and dropped from `96.010` to `66.425`.
That is a `29.585` public-point drop, or about `329` single-post-equivalent
candidates on the public mean (`29.585 / 0.09`). The later Gemma K8-O submissions
dropped only another `1.215` public points from `66.425` to `65.210`, so Gemma
K8-O is not the primary regression.

The relevant `9aab298 -> 134b63f` production-path changes were:

- added `SLOW_MULTIPOST_TEMPLATE = "slotlabels"`;
- changed the slow-row multipost builder from `_forge_plan_msg(...)` to
  `_multipost_plan_msg(..., "slotlabels")`;
- added `_slot_plan_msg()` / `_slot_url()` (`a11565.co`, `b11565.co`, ...);
- replaced the appended K8 bank with the slot-label bank
  (`K8_BANK = _parse_k8_bank(K8_BANK_CODE_CSV)`).

Local profiler runs made slot-label prompts look better, but the hosted T4
replay score says that advantage did not transfer. This repeats the earlier
lesson from `55562414`: local K8 raw/s is not enough; hosted validation-fill
throughput and replay behavior are authoritative.

## Secondary diagnosis

The Gemma K8-O hosted rows were not isolated because they both kept the broken
GPT slot-label default. Their `65.210` score only proves that the combined
slot-label-GPT + Gemma-K8 configuration failed. It does not prove Gemma K8-O
alone would fail against the 96.010 GPT baseline, but it also did not provide a
visible rescue.

Given the evidence, Gemma K8-O must remain opt-in until it is tested on top of a
restored GPT current-template baseline.

## Fix applied

`attacks/05_validation_fill/attack.py` defaults were restored to the 96.010
baseline shape:

- `SLOW_MULTIPOST_TEMPLATE = "current"`;
- `K8_BANK = CURRENT_K8_BANK`, the current-template bank from `9aab298`;
- slot-label prompts and `SLOT_K8_BANK` remain available only when explicitly
  configured with `slow_multipost_template=slotlabels`;
- `USE_GEMMA_K8_O = False` by default;
- Gemma K8-O and Round 57 remain config-gated experiments.

## Next safe submission rule

Do not submit slot-label GPT defaults again. The next candidate submission should
start from the restored `9aab298`-style GPT current-template path. Any Gemma K8-O
test should change only the fast row while preserving the hosted-proven GPT row.

## Follow-up isolated submission

Submitted after restoring the baseline:

| submission ref | commit | description | status at submit time |
| --- | --- | --- | --- |
| `55648851` | `cd97a2e` | Isolated Gemma K8-O on restored GPT current baseline | `PENDING` |

This submission intentionally changes one production default from `eca381f`:
`USE_GEMMA_K8_O=True`.  The GPT slow row remains on
`SLOW_MULTIPOST_TEMPLATE="current"` with the hosted-proven current-template K8
bank.  Interpret the score as a Gemma K8-O transfer test only; do not attribute
the result to GPT slot-labels, which are not enabled in this commit.

## Submission safety guardrail

Use `scripts/build_attack_variant.py` for future hosted variants instead of
hand-editing production defaults in `attacks/05_validation_fill/attack.py`.
The helper reads an attack file from an explicit git ref, applies named constant
overrides, asserts the intended final constants, writes the generated attack
under ignored `runs/`, and records a manifest next to it.

Prepared and later submitted while `55648851` was still pending:

```powershell
G:\kaggle_competition\.venv\Scripts\python.exe scripts\build_attack_variant.py `
  --git-ref eca381f `
  --source attacks/05_validation_fill/attack.py `
  --out runs/variants/gpt-duplicate-on-safe-baseline/attack.py `
  --set USE_GPT_DUPLICATE_K8=True `
  --expect SLOW_MULTIPOST_TEMPLATE='"current"' `
  --expect USE_GEMMA_K8_O=False `
  --expect USE_GPT_DUPLICATE_K8=True `
  --expect GPT_DUPLICATE_K8_BANK_N=500 `
  --expect GPT_DUPLICATE_K8_BANK_INDEX=11565
```

This GPT duplicate-topology variant starts from the restored safe baseline
(`eca381f`) and does not include Gemma K8-O.

Local smoke evidence for the generated variant:

```powershell
G:\kaggle_competition\.venv\Scripts\python.exe scripts\verify_fill.py `
  --attack runs\variants\gpt-duplicate-on-safe-baseline\attack.py `
  --agent gpt_oss `
  --model-path G:\kaggle_competition\models\gpt-oss-20b-Q4_K_M.gguf `
  --gpu-layers -1 `
  --tensor-split 0.57,0.43 `
  --budget-s 90 `
  --attack-config-file runs\tmp\verify-fill-gpt-duplicate-safe-config.json
```

Result: `candidates_returned=3`, `unique_cells=1`, `score_raw=386.0`,
`score_normalized=1.93`, `attack_elapsed_s=23.268`.  The raw score matches
`3 * 8 * 16 + 2`, confirming the generated variant enters the duplicate GPT K8
path locally.  This is still not hosted evidence.

Hosted submission:

| submission ref | source ref | description | status at submit time |
| --- | --- | --- | --- |
| `55649067` | `eca381f` + `USE_GPT_DUPLICATE_K8=True` | GPT duplicate K8 topology on safe baseline; Gemma off | `PENDING` |

Interpretation rule: compare `55649067` against the `96.010` control and the
`66.425` slot-label failure.  If it drops like slot-labels, duplicate GPT K8
does not hosted-transfer despite the local smoke.  If it lands near or above
`96.010`, the local duplicate topology is viable and can later be combined only
with a separately proven Gemma result.

## Current wait gate

As of the latest API poll, both controlled probes are pending:

- `55648851`: Gemma K8-O isolated on restored GPT current baseline.
- `55649067`: GPT duplicate K8 topology on restored safe baseline, Gemma off.

Backing notebook kernels for both probes report `COMPLETE` with no failure
message (`janbartos/gemma-k8o-isolated-cd97a2e` and
`janbartos/gpt-duplicate-safe-eca381f`).  The unresolved state is therefore the
competition rerun/scoring queue, not notebook execution.

Do not submit a third hosted variant until at least one of these completes.
The next action depends on the first completed score:

- `55648851 > 96.010`: Gemma K8-O transfers; keep it as a candidate fast-row
  improvement, but still do not combine it with GPT duplicate K8 unless the GPT
  probe also transfers.
- `55648851 <= 96.010`: keep Gemma K8-O off by default.
- `55649067 >= 96.010`: GPT duplicate topology is viable enough for a follow-up
  combined or repeat/noise-check submission.
- `55649067` near the `65-66` failures: duplicate GPT K8 does not hosted-transfer
  and should stay experimental.
