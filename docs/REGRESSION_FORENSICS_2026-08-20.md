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

## Third-probe wait-gate override

The earlier wait gate was conservative because hosted submissions are scarce and
the two pending probes already isolate the main Gemma-vs-GPT question.  The user
later clarified that quota was not tight before reset, so a third controlled
probe is justified if it tests a distinct hypothesis rather than mixing changes.

New local evidence from `runs/tmp/sequence-arena-gpt-current-vs-slot-n10.json`:

| arm | hosted relevance | local result |
| --- | --- | --- |
| `slot_duplicate` | same topology as `55649067`, but prompt family already failed once when used as GPT default | `10/10` K8, `62.262 raw/s` |
| `current_duplicate` | duplicate topology, but using the hosted-proven current-template prompt family | `10/10` K8, `61.491 raw/s` |

Production-path smoke for the generated current-template duplicate variant:

```text
candidates_returned=3
unique_cells=1
score_raw=386.0
score_normalized=1.9300000000000002
attack_elapsed_s=20.846015453338623
```

Interpretation: this is still a GPT-only probe with Gemma off, not a final mixed
submission. It tests whether the hosted failure is specific to slot-label prompt
shape rather than duplicate K8 topology itself.

Hosted submission:

| submission ref | source ref | description | status at submit time |
| --- | --- | --- | --- |
| `55652403` | `8a15cbd` + `USE_GPT_DUPLICATE_K8=True`, `GPT_DUPLICATE_K8_TEMPLATE="current"` | GPT current-duplicate K8 on safe baseline; Gemma off | `PENDING` |

Interpretation rule: compare `55652403` mainly against `55649067`.  If
`55649067` fails but `55652403` recovers, the slot-label prompt family is the
hosted-transfer problem.  If both fail, duplicate GPT K8 topology itself is
likely not transferable.  If both work, prefer the faster or more stable hosted
score and then test a combined submission only with separately proven Gemma
changes.

## Fourth controlled probe: Gemma r57 token-shaved K8-O

Round 57 is the conservative token-shaved Gemma K8-O prompt documented in
`docs/gemma_k8_luna/RESULTS.md`.  The pending `55648851` isolated Gemma probe
uses the default `r53` prompt; `r57` is a distinct fast-row hypothesis, so it is
worth a separate hosted check while quota is available.

Fresh production-path smoke:

```text
candidates_returned=3
unique_cells=1
score_raw=386.0
score_normalized=1.9300000000000002
attack_elapsed_s=109.66317772865295
```

Hosted submission:

| submission ref | source ref | description | status at submit time |
| --- | --- | --- | --- |
| `55652559` | `32f9395` + `USE_GEMMA_K8_O=True`, `GEMMA_K8_O_VARIANT="r57"` | Gemma K8-O r57 isolated on safe GPT baseline | `PENDING` |

Interpretation rule: compare `55652559` against `55648851`.  If both transfer,
prefer the faster/higher hosted score.  If `r53` transfers but `r57` does not,
keep the longer r53 scaffolding.  If neither transfers, keep Gemma K8-O off and
inspect raw local failure modes before submitting more Gemma variants.

## Fifth controlled probe: GPT current-duplicate index 745

The `55652403` GPT current-duplicate probe used index `11565`, inherited from
the earlier slot-label topology.  A follow-up local screen showed that
current-template duplicate performance is index-sensitive and that index `745`
is a stronger local choice:

| index | local posts | local raw/s | note |
| ---: | --- | ---: | --- |
| `11565` | `8/8/8` | `62.444` | submitted current-duplicate control |
| `745` | `8/8/8` | `68.911` | best local index-screen result |
| `10566` | `7/7/7` | `54.973` | example of unique-bank index failing in duplicate mode |

Fresh production-path smoke for generated index-745 variant:

```text
candidates_returned=3
unique_cells=1
score_raw=386.0
score_normalized=1.9300000000000002
attack_elapsed_s=19.388829469680786
```

Hosted submission:

| submission ref | source ref | description | status at submit time |
| --- | --- | --- | --- |
| `55652649` | `908af9f` + `USE_GPT_DUPLICATE_K8=True`, `GPT_DUPLICATE_K8_TEMPLATE="current"`, `GPT_DUPLICATE_K8_BANK_INDEX=745` | GPT current-duplicate K8 index 745 on safe baseline; Gemma off | `PENDING` |

Interpretation rule: compare `55652649` against `55652403`.  If both transfer,
prefer index `745`; if only `11565` transfers, duplicate-index stability matters
more than local speed and index `745` should not be promoted.  If neither
transfers, keep GPT duplicate K8 off.

## Post-submit hardening: index 745 is cache-sensitive

After submitting `55652649`, a candidate-cold local run contradicted the grouped
index screen:

| index | candidate-cold posts | candidate-cold raw/s | interpretation |
| ---: | --- | ---: | --- |
| `11565` | `8/8/8/8/8` | `57.594` | stable control |
| `745` | `5/5/5/5/5` | `48.188` | grouped-only false lead |
| `499` | `8/8/8/8/8` | `58.393` | safer optimized index |
| `938` | `8/8/8/8/8` | `55.323` | stable but slower |

This means `55652649` should be treated as a risky probe, not the preferred
optimized variant.  The next safer GPT current-duplicate candidate is index
`499`, which also passed a production-path smoke:

```text
candidates_returned=3
unique_cells=1
score_raw=386.0
score_normalized=1.9300000000000002
attack_elapsed_s=20.329851388931274
```

Prepared variant, not submitted in this note:
`runs/variants/gpt-current-duplicate-i499-967d30b/attack.py`.

Attempted hosted submission for index `499` was blocked by Kaggle quota, not by
notebook execution:

```text
Submission not allowed: Your team has used its daily Submission allowance (5)
today, please try again tomorrow UTC (5.1 hours from now).
```

The notebook `janbartos/gpt-current-dup-i499-967d30b` did run to `complete`; it
just was not accepted as a competition submission.

## Candidate-cold batch 2: index 312 is stronger than 499

A second candidate-cold screen found several stable indices faster than `499`.
The best local result was index `312`:

| index | candidate-cold posts | candidate-cold raw/s | median completion/eval tokens |
| ---: | --- | ---: | --- |
| `11565` | `8/8/8` | `57.478` | `245 / 1481` |
| `499` | `8/8/8` | `58.905` | `239 / 1476` |
| `5735` | `8/8/8` | `61.329` | `225 / 1461` |
| `8325` | `8/8/8` | `61.267` | `221 / 1457` |
| `148` | `8/8/8` | `61.147` | `227 / 1463` |
| `312` | `8/8/8` | `61.483` | `217 / 1451` |

Index `312` also passed production-path smoke:

```text
candidates_returned=3
unique_cells=1
score_raw=386.0
score_normalized=1.9300000000000002
attack_elapsed_s=20.572217226028442
```

Prepared variant and notebook, not submitted due to quota:

- `runs/variants/gpt-current-duplicate-i312-ab369f2/attack.py`
- `runs/kaggle-gpt-current-dup-i312-ab369f2/gpt-current-dup-i312-ab369f2.ipynb`

Next-reset rule: if GPT current-duplicate transfer remains worth testing, submit
index `312` before index `499`, unless a larger candidate-cold scan finds a
better stable index.

## Candidate-cold confirmation: keep index 312 as next-reset choice

A top-index confirmation run reinforced index `312` as the current best local
GPT current-duplicate candidate:

| index | candidate-cold posts | candidate-cold raw/s | median completion/eval tokens |
| ---: | --- | ---: | --- |
| `11565` | `8/8/8/8/8` | `57.208` | `245 / 1481` |
| `499` | `8/8/8/8/8` | `58.190` | `239 / 1476` |
| `312` | `8/8/8/8/8` | `62.382` | `217 / 1451` |
| `8325` | `8/8/8/8/8` | `61.684` | `221 / 1457` |
| `5735` | `8/8/8/8/8` | `60.841` | `225 / 1461` |
| `408` | `8/8/8/8/8` | `60.793` | `224 / 1458` |
| `148` | `8/8/8/8/8` | `60.254` | `227 / 1463` |

Index `312` is therefore still the preferred next-reset GPT current-duplicate
probe if hosted results justify continuing this family.

Local-only follow-up batch 4 did not change this choice.  Later current-bank
indices all stayed below the `312` control, and index `522` underfired to K5 in
candidate-cold mode.  Keep `312` as the preferred next-reset candidate unless a
future candidate-cold screen beats it, not merely a grouped/cache-warm screen.
