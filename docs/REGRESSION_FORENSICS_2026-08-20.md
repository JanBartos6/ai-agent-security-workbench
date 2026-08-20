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
