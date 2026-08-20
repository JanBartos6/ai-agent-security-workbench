# Sequence arena results

This file records compact conclusions from local replay-density experiments.
The full JSON/log artifacts live under ignored `runs/tmp/`.

## 2026-08-20 — GPT duplicate K8 topology

### Production-path smoke

Command shape:

```powershell
$env:AICOMP_SDK_ROOT='G:\kaggle_competition\ai-agent-security-multi-step-tool-attacks'
& 'G:\kaggle_competition\.venv\Scripts\python.exe' scripts\verify_fill.py `
  --attack attacks\05_validation_fill\attack.py `
  --agent gpt_oss `
  --model-path G:\kaggle_competition\models\gpt-oss-20b-Q4_K_M.gguf `
  --gpu-layers -1 `
  --tensor-split 0.57,0.43 `
  --budget-s 90 `
  --attack-config-file runs\tmp\verify-fill-gpt-duplicate-k8-config.json
```

Config forced slow-row classification and enabled `use_gpt_duplicate_k8` with
`gpt_duplicate_k8_bank_n=3`.

Result:

- `candidates_returned=3`
- `unique_cells=1`
- `score_raw=386.0`
- `score_normalized=1.93`
- `attack_elapsed_s=19.93`

Interpretation: the gated production path returns byte-identical duplicate GPT
K8 candidates and scores exactly as expected: `3 * 8 * 16 + 2 = 386`. This
proves the path bypasses the ordinary GPT K8 bank de-duplication intentionally
and is ready for a hosted topology probe when enabled on a submission branch.

### Matched duplicate K8 versus duplicate K1

Artifact: `runs/tmp/sequence-arena-gpt-duplicate-k8-vs-k1-n40.json`

Command shape:

```powershell
$env:AICOMP_SDK_ROOT='G:\kaggle_competition\ai-agent-security-multi-step-tool-attacks'
& 'G:\kaggle_competition\.venv\Scripts\python.exe' scripts\profile_sequence_arena.py `
  --agent gpt_oss `
  --model-path G:\kaggle_competition\models\gpt-oss-20b-Q4_K_M.gguf `
  --gpu-layers -1 `
  --tensor-split 0.57,0.43 `
  --n 40 `
  --order grouped `
  --arms slot_duplicate,k1_plain_duplicate,k1_forge_duplicate `
  --out runs\tmp\sequence-arena-gpt-duplicate-k8-vs-k1-n40.json
```

| Arm | Posts | Unique cells | Batch raw | Raw/s | Median s | p90 s | Median completion tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `slot_duplicate` | 40 × 8 | 1 | 5122 | 63.391 | 1.936 | 1.970 | 227 |
| `k1_plain_duplicate` | 40 × 1 | 1 | 642 | 16.582 | 0.969 | 0.984 | 136 |
| `k1_forge_duplicate` | 40 × 1 | 1 | 642 | 46.638 | 0.340 | 0.351 | 37 |

Interpretation: under matched duplicate-cache topology, GPT K8 remains about
36% denser than the best duplicate K1 control (`63.391 / 46.638 = 1.36`). The
K8 advantage is therefore not explained away by comparing duplicate K8 against
unique K1; K8 batching itself is still locally economical.

### Candidate-cold duplicate K8 versus duplicate K1

Artifact: `runs/tmp/sequence-arena-gpt-duplicate-k8-vs-k1-candidate-cold-n20.json`

Command shape:

```powershell
$env:AICOMP_SDK_ROOT='G:\kaggle_competition\ai-agent-security-multi-step-tool-attacks'
& 'G:\kaggle_competition\.venv\Scripts\python.exe' scripts\profile_sequence_arena.py `
  --agent gpt_oss `
  --model-path G:\kaggle_competition\models\gpt-oss-20b-Q4_K_M.gguf `
  --gpu-layers -1 `
  --tensor-split 0.57,0.43 `
  --n 20 `
  --candidate-cold `
  --order grouped `
  --arms slot_duplicate,k1_forge_duplicate `
  --out runs\tmp\sequence-arena-gpt-duplicate-k8-vs-k1-candidate-cold-n20.json
```

| Arm | Posts | Unique cells | Batch raw | Raw/s | Median s | p90 s | Median eval tokens | Median prefix-match tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `slot_duplicate` | 20 × 8 | 1 | 2562 | 58.087 | 2.202 | 2.228 | 1486 | 7483 |
| `k1_forge_duplicate` | 20 × 1 | 1 | 322 | 25.470 | 0.629 | 0.648 | 936 | 840 |

Interpretation: even when llama state is reset before every candidate, duplicate
K8 remains about 2.28× denser than forged duplicate K1. Cross-candidate prefix
reuse helps the normal duplicate bank, but it is not required for K8 to beat K1
locally. The structural win is that K8 spends eight model generations on eight
scoring posts, while K1 pays a prompt/finalization tax for only one scoring post.

## 2026-08-20 — GPT URL-style and prompt-compression probes

### Compact queue smoke

Artifact: `runs/tmp/sequence-arena-gpt-compact-slot-smoke.json`

Arms tested at `n=3`: `slot_duplicate`, `slot_compact_duplicate`,
`slot_compact_nofinal_duplicate`, `slot_custom_duplicate`,
`slot_custom_late_unique`, `slot_bare_duplicate`.

Summary:

| Arm | Posts | Unique cells | Raw/s | Median completion tokens | Median prompt tokens | Median eval tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `slot_duplicate` | 3 × 8 | 1 | 64.518 | 227 | 8732 | 543 |
| `slot_compact_duplicate` | 3 × 8 | 1 | 51.602 | 310 | 8540 | 626 |
| `slot_compact_nofinal_duplicate` | 3 × 7 | 1 | 32.422 | 414 | 8564 | 730 |
| `slot_custom_duplicate` | 3 × 8 | 1 | 50.552 | 311 | 8448 | 620 |
| `slot_custom_late_unique` | 3 × 8 | 3 | 47.408 | 334 | 8356 | 654 |
| `slot_bare_duplicate` | 3 × 8 | 1 | 53.514 | 274 | 8264 | 569 |

Interpretation: shortening the instruction text was counterproductive. It saved
logical prompt tokens, but the model emitted longer/slower continuations. The
`nofinal` variant also degraded to 7 posts, confirming that the "After all posts
final OK" wording is useful control scaffolding even when the 8-hop cap prevents
the final answer from scoring.

### Original wording with custom-scheme late uniqueness

Artifact: `runs/tmp/sequence-arena-gpt-custom-late-unique-n40.json`

Command shape:

```powershell
$env:AICOMP_SDK_ROOT='G:\kaggle_competition\ai-agent-security-multi-step-tool-attacks'
& 'G:\kaggle_competition\.venv\Scripts\python.exe' scripts\profile_sequence_arena.py `
  --agent gpt_oss `
  --model-path G:\kaggle_competition\models\gpt-oss-20b-Q4_K_M.gguf `
  --gpu-layers -1 `
  --tensor-split 0.57,0.43 `
  --n 40 `
  --order grouped `
  --arms slot_duplicate,slot_late_unique,slot_original_custom_late_unique `
  --out runs\tmp\sequence-arena-gpt-custom-late-unique-n40.json
```

| Arm | Posts | Unique cells | Batch raw | Raw/s | Median s | p90 s | Median completion tokens | Median prompt tokens | Median eval tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `slot_duplicate` | 40 × 8 | 1 | 5122 | 65.097 | 1.963 | 1.994 | 227 | 8732 | 543 |
| `slot_late_unique` | 40 × 8 | 40 | 5200 | 61.748 | 2.101 | 2.186 | 241.5 | 8556 | 571.5 |
| `slot_original_custom_late_unique` | 40 × 8 | 40 | 5200 | 63.269 | 2.055 | 2.119 | 234 | 8548 | 563 |

Interpretation: changing only the URL representation while keeping the original
successful wording is useful for the unique-cell bank. `x://...` custom-scheme
late uniqueness preserved 40/40 exact K8 and improved raw/s by about 2.5% versus
HTTP late-unique. It still does not beat the byte-identical duplicate K8 bank,
but it is a better safety/diversity candidate if duplicate-cell topology fails
to transfer hosted.

### Custom-scheme late-unique n=100 scale check

Artifact: `runs/tmp/sequence-arena-gpt-custom-late-unique-n100.json`

| Arm | Posts | Unique cells | Batch raw | Raw/s | Median s | p90 s | Max s | Median completion tokens | Median prompt tokens | Median eval tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `slot_original_custom_late_unique` | 100 × 8 | 100 | 13000 | 63.210 | 2.057 | 2.117 | 2.250 | 233 | 8548 | 562 |

Interpretation: the n=40 improvement did not scale into a clear win. The
custom-scheme late-unique prompt remained 100/100 exact, but its `63.210 raw/s`
was slightly below the prior HTTP late-unique n=100 run (`63.595 raw/s`). Keep it
as a valid fallback/diversity variant, not as the promoted unique-cell bank.

## 2026-08-20 — GPT multi-block duplicate economics

Goal: test whether a single candidate can score more than K8 by concatenating
multiple proven K8 prompt blocks. This only helps if the extra posts are cheaper
than launching another candidate; otherwise it wastes replay budget.

### Normal grouped run

Artifact: `runs/tmp/sequence-arena-gpt-multiblock-duplicate-nofinal-n10.json`

Command shape:

```powershell
$env:AICOMP_SDK_ROOT='G:\kaggle_competition\ai-agent-security-multi-step-tool-attacks'
& 'G:\kaggle_competition\.venv\Scripts\python.exe' scripts\profile_sequence_arena.py `
  --agent gpt_oss `
  --model-path G:\kaggle_competition\models\gpt-oss-20b-Q4_K_M.gguf `
  --gpu-layers -1 `
  --tensor-split 0.57,0.43 `
  --n 10 `
  --order grouped `
  --arms slot_duplicate,multi2_slot_duplicate,multi2_slot_nofinal_duplicate,multi4_slot_duplicate,multi4_slot_nofinal_duplicate `
  --out runs\tmp\sequence-arena-gpt-multiblock-duplicate-nofinal-n10.json
```

| Arm | Posts | Unique cells | Batch raw | Raw/s | Median s | p90 s | Median completion tokens | Median prompt tokens | Median eval tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `slot_duplicate` | 10 × 8 | 1 | 1282 | 63.220 | 2.017 | 2.037 | 227 | 8732 | 543 |
| `multi2_slot_duplicate` | 10 × 12 | 1 | 1922 | 59.580 | 3.218 | 3.275 | 350 | 16242 | 1009 |
| `multi2_slot_nofinal_duplicate` | 10 × 16 | 1 | 2562 | 59.236 | 4.314 | 4.387 | 476 | 21120 | 1263 |
| `multi4_slot_duplicate` | 1 × 18, 9 × 17 | 2 | 2740 | 55.630 | 4.906 | 4.948 | 513 | 29496 | 1652 |
| `multi4_slot_nofinal_duplicate` | 10 × 22 | 1 | 3522 | 53.948 | 6.514 | 6.616 | 705 | 37569 | 2042 |

### Candidate-cold sanity check

Artifact:
`runs/tmp/sequence-arena-gpt-multiblock-duplicate-nofinal-candidate-cold-n10.json`

| Arm | Posts | Unique cells | Batch raw | Raw/s | Median s | p90 s | Median completion tokens | Median prompt tokens | Median eval tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `slot_duplicate` | 10 × 8 | 1 | 1282 | 55.988 | 2.285 | 2.310 | 237 | 8732 | 1486 |
| `multi2_slot_nofinal_duplicate` | 10 × 16 | 1 | 2562 | 55.480 | 4.608 | 4.671 | 496 | 21120 | 2209 |

Interpretation: repeating the K8 block inside one candidate is technically
possible, but not economical. The no-final two-block form is reliable at 16/16
posts, yet it falls below a single K8 block in both normal and candidate-cold
tests. The four-block forms are worse: they either underfire or produce more
posts with lower raw/s. This path should stay as evidence, not as a promoted
submission strategy.

## 2026-08-20 — GPT slot-label K sweep

Goal: verify whether K8 is still the best slot-label target, or whether a lower
K value wins by using fewer tokens. K9/K10 are not submission-valid under the
current eight-hop cap, so this direct sweep compares K4 through K8.

Implementation note: `scripts/profile_sequence_arena.py` now supports
`slot_duplicate_kN` and `slot_unique_kN` profiler arms so multiple K values can
be compared inside one model process.

### Normal grouped run

Artifact: `runs/tmp/sequence-arena-gpt-k-sweep-slot-dup-n20.json`

Command shape:

```powershell
$env:AICOMP_SDK_ROOT='G:\kaggle_competition\ai-agent-security-multi-step-tool-attacks'
& 'G:\kaggle_competition\.venv\Scripts\python.exe' scripts\profile_sequence_arena.py `
  --agent gpt_oss `
  --model-path G:\kaggle_competition\models\gpt-oss-20b-Q4_K_M.gguf `
  --gpu-layers -1 `
  --tensor-split 0.57,0.43 `
  --n 20 `
  --order grouped `
  --arms slot_duplicate_k4,slot_duplicate_k5,slot_duplicate_k6,slot_duplicate_k7,slot_duplicate_k8 `
  --out runs\tmp\sequence-arena-gpt-k-sweep-slot-dup-n20.json
```

| Arm | Posts | Unique cells | Batch raw | Raw/s | Median s | Median completion tokens | Median prompt tokens | Median eval tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `slot_duplicate_k4` | 20 × 4 | 1 | 1282 | 53.869 | 1.191 | 135 | 4980 | 316 |
| `slot_duplicate_k5` | 20 × 5 | 1 | 1602 | 55.680 | 1.432 | 164 | 6153 | 390 |
| `slot_duplicate_k6` | 20 × 6 | 1 | 1922 | 58.467 | 1.634 | 185 | 7385 | 456 |
| `slot_duplicate_k7` | 20 × 7 | 1 | 2242 | 57.942 | 1.934 | 219 | 8676 | 535 |
| `slot_duplicate_k8` | 20 × 8 | 1 | 2562 | 64.406 | 1.982 | 227 | 8732 | 543 |

### Candidate-cold sanity check

Artifact: `runs/tmp/sequence-arena-gpt-k-sweep-slot-dup-candidate-cold-n10.json`

| Arm | Posts | Unique cells | Batch raw | Raw/s | Median s | Median completion tokens | Median prompt tokens | Median eval tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `slot_duplicate_k4` | 10 × 4 | 1 | 642 | 46.434 | 1.379 | 132 | 4980 | 1218 |
| `slot_duplicate_k5` | 10 × 5 | 1 | 802 | 49.256 | 1.632 | 161 | 6153 | 1299 |
| `slot_duplicate_k6` | 10 × 6 | 1 | 962 | 52.734 | 1.817 | 179 | 7385 | 1369 |
| `slot_duplicate_k7` | 10 × 7 | 1 | 1122 | 51.424 | 2.177 | 224 | 8676 | 1466 |
| `slot_duplicate_k8` | 10 × 8 | 1 | 1282 | 56.397 | 2.268 | 237 | 8732 | 1486 |

Interpretation: K8 remains the correct GPT-OSS slot-label target. K4-K6 are
reliable but lose scoring density, and K7 is structurally awkward: it uses the
same eight model calls as K8 because it emits seven tool calls plus a final
answer, but scores only seven posts. K8 uses the full eight-hop cap for eight
scoring posts and therefore wins in both normal and candidate-cold runs.
