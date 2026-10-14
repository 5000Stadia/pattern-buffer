# Build profile: a_low_run2

Total wall: 246.1 s. Percentiles are nearest-rank. Stage wall seconds are rounded to 0.1 s by the receipt.
- NOTE: no objectives.jsonl: turns, floors and what-ifs are unmeasured

## Per stage

| stage | wall s | share | workers | calls | objectives | latency sum s | utilization | p50 s | p90 s | max s | tokens in | tokens out | cached | out tok/s median | out tok/s p10 | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| commit | 57.6 | 23.4% | 1 | 7 | unmeasured | 53.9 | 93.5% | 8.1 | 8.4 | 8.4 | 21 | 4992 | 0 | 95.8 | 55.0 | 0.1388 |
| extract | 170.4 | 69.2% | 1 | 4 | unmeasured | 358.6 | 210.5% | 73.8 | 170.4 | 170.4 | 12 | 29345 | 0 | 79.1 | 76.2 | 0.5357 |
| registry | 18.1 | 7.3% | 1 | 4 | unmeasured | 41.7 | 230.2% | 9.3 | 18.0 | 18.0 | 12 | 1628 | 0 | 39.7 | 18.0 | 0.1831 |

### CLI turns and API time (claude shim only)

| stage | turns/call median | turns/call max | API time share of latency | harness overhead s (latency minus API) | max concurrent calls |
|---|---|---|---|---|---|
| commit | 1.0 | 1.0 | 82.2% | 9.6 | 1 |
| extract | 1.0 | 1.0 | 98.2% | 6.5 | 4 |
| registry | 1.0 | 1.0 | 83.2% | 7.0 | 4 |

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
| all | R2 0.994, 11.75 s per 1k tokens, n=15 | R2 0.047, 4.45 s per 1k tokens, n=15 |
| registry | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |
| extract | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |
| commit | R2 0.993, 6.84 s per 1k tokens, n=7 | R2 0.897, 6.19 s per 1k tokens, n=7 |

## Which stages matter for quality (ablation)

Measured by ablation runs against the answer key (`grade_book.py`): metered runs, not part of this report. Filled from `ablation.json` (stage to result) when it exists.

| stage | ablation result |
|---|---|
| commit | not measured |
| extract | not measured |
| registry | not measured |
