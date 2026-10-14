# Build profile: full_iii

Total wall: 225.4 s. Percentiles are nearest-rank. Stage wall seconds are rounded to 0.1 s by the receipt.
- NOTE: no objectives.jsonl: turns, floors and what-ifs are unmeasured

## Per stage

| stage | wall s | share | workers | calls | objectives | latency sum s | utilization | p50 s | p90 s | max s | tokens in | tokens out | cached | out tok/s median | out tok/s p10 | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| commit | 49.4 | 21.9% | 1 | 20 | unmeasured | 167.6 | 339.2% | 8.3 | 8.6 | 9.2 | 60 | 15598 | 0 | 92.8 | 88.6 | 0.4276 |
| extract | 158.4 | 70.3% | 1 | 18 | unmeasured | 1081.9 | 683.0% | 56.8 | 101.6 | 104.3 | 54 | 89543 | 0 | 81.7 | 75.8 | 1.7168 |
| registry | 17.6 | 7.8% | 1 | 4 | unmeasured | 48.6 | 275.9% | 12.0 | 17.5 | 17.5 | 12 | 2370 | 0 | 42.4 | 42.3 | 0.4380 |

### CLI turns and API time (claude shim only)

| stage | turns/call median | turns/call max | API time share of latency | harness overhead s (latency minus API) | max concurrent calls |
|---|---|---|---|---|---|
| commit | 1.0 | 1.0 | 81.2% | 31.5 | 4 |
| extract | 1.0 | 1.0 | 97.4% | 28.0 | 8 |
| registry | 1.0 | 1.0 | 88.4% | 5.7 | 4 |

## Turns to an objective

unmeasured: no objectives.jsonl.

## Ceilings

Floor = the stage's longest single objective, the most parallelism can buy. Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

unmeasured: no objectives.jsonl.

### Whole-build totals

unmeasured

### Overlapped pipeline (hypothetical)

Dependency model (hypothetical, not today's code): a pass-1 chunk's facts can be classified as soon as that chunk is accepted. The commit's K classification batches are spread over the N accepted chunks in acceptance order; batch j becomes ready when chunk ceil(j*N/K) has finished (facts per chunk assumed even). Batches run, with their measured durations, one at a time on a separate worker. Escape repair, the commit's other work (its wall minus the summed batch durations) and the audit stay serial after the last chunk and the last batch, as today. Pass-0 stays as measured.

unmeasured: needs pass-1 chunk and classification-batch objectives and stage walls.

## Is a call slow because of what it writes or what it reads?

Least squares of latency on tokens (input counts cached tokens). A fit under 5 calls, or with zero variance, is unmeasured.

| scope | vs output tokens | vs input tokens |
|---|---|---|
| all | R2 0.991, 11.97 s per 1k tokens, n=42 | R2 0.001, -0.18 s per 1k tokens, n=42 |
| registry | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |
| extract | R2 0.977, 11.62 s per 1k tokens, n=18 | R2 0.111, 27.84 s per 1k tokens, n=18 |
| commit | R2 0.044, 2.91 s per 1k tokens, n=20 | R2 0.011, 0.56 s per 1k tokens, n=20 |

## Which stages matter for quality (ablation)

Measured by ablation runs against the answer key (`grade_book.py`): metered runs, not part of this report. Filled from `ablation.json` (stage to result) when it exists.

| stage | ablation result |
|---|---|
| commit | not measured |
| extract | not measured |
| registry | not measured |
