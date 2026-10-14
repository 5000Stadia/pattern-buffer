# Build profile: i_run1

Total wall: 356.5 s. Percentiles are nearest-rank. Stage wall seconds are rounded to 0.1 s by the receipt.
- NOTE: no objectives.jsonl: turns, floors and what-ifs are unmeasured

## Per stage

| stage | wall s | share | workers | calls | objectives | latency sum s | utilization | p50 s | p90 s | max s | tokens in | tokens out | cached | out tok/s median | out tok/s p10 | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| commit | 58.9 | 16.5% | 1 | 7 | unmeasured | 55.5 | 94.3% | 8.1 | 8.6 | 8.6 | 21 | 5180 | 0 | 95.0 | 71.3 | 0.1423 |
| extract | 283.9 | 79.6% | 1 | 5 | unmeasured | 455.9 | 160.6% | 84.7 | 142.0 | 142.0 | 15 | 37803 | 0 | 82.6 | 75.2 | 0.6932 |
| registry | 13.7 | 3.8% | 1 | 4 | unmeasured | 38.3 | 279.4% | 9.6 | 13.7 | 13.7 | 12 | 1687 | 0 | 40.7 | 27.6 | 0.1840 |

### CLI turns and API time (claude shim only)

| stage | turns/call median | turns/call max | API time share of latency | harness overhead s (latency minus API) | max concurrent calls |
|---|---|---|---|---|---|
| commit | 1.0 | 1.0 | 81.5% | 10.3 | 1 |
| extract | 1.0 | 1.0 | 98.5% | 6.6 | 4 |
| registry | 1.0 | 1.0 | 82.3% | 6.8 | 4 |

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
| all | R2 0.990, 11.64 s per 1k tokens, n=16 | R2 0.074, 5.66 s per 1k tokens, n=16 |
| registry | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |
| extract | R2 0.975, 10.96 s per 1k tokens, n=5 | R2 0.844, 41.17 s per 1k tokens, n=5 |
| commit | R2 0.924, 5.82 s per 1k tokens, n=7 | R2 0.815, 4.62 s per 1k tokens, n=7 |

## Which stages matter for quality (ablation)

Measured by ablation runs against the answer key (`grade_book.py`): metered runs, not part of this report. Filled from `ablation.json` (stage to result) when it exists.

| stage | ablation result |
|---|---|
| commit | not measured |
| extract | not measured |
| registry | not measured |
