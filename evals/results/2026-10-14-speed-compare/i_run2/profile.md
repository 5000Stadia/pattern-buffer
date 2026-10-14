# Build profile: i_run2

Total wall: 223.5 s. Percentiles are nearest-rank. Stage wall seconds are rounded to 0.1 s by the receipt.
- NOTE: no objectives.jsonl: turns, floors and what-ifs are unmeasured

## Per stage

| stage | wall s | share | workers | calls | objectives | latency sum s | utilization | p50 s | p90 s | max s | tokens in | tokens out | cached | out tok/s median | out tok/s p10 | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| commit | 57.6 | 25.8% | 1 | 7 | unmeasured | 54.0 | 93.8% | 8.1 | 8.4 | 8.4 | 21 | 5078 | 0 | 96.0 | 64.7 | 0.1408 |
| extract | 151.0 | 67.6% | 1 | 5 | unmeasured | 401.0 | 265.6% | 67.6 | 145.8 | 145.8 | 15 | 31957 | 0 | 82.1 | 65.5 | 0.6027 |
| registry | 14.9 | 6.7% | 1 | 4 | unmeasured | 39.1 | 262.7% | 9.9 | 14.9 | 14.9 | 12 | 1664 | 0 | 38.3 | 18.7 | 0.1836 |

### CLI turns and API time (claude shim only)

| stage | turns/call median | turns/call max | API time share of latency | harness overhead s (latency minus API) | max concurrent calls |
|---|---|---|---|---|---|
| commit | 1.0 | 1.0 | 82.5% | 9.4 | 1 |
| extract | 1.0 | 1.0 | 98.0% | 8.0 | 4 |
| registry | 1.0 | 1.0 | 81.7% | 7.2 | 4 |

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
| all | R2 0.993, 12.16 s per 1k tokens, n=16 | R2 0.046, 4.11 s per 1k tokens, n=16 |
| registry | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |
| extract | R2 0.991, 11.76 s per 1k tokens, n=5 | R2 0.265, 25.41 s per 1k tokens, n=5 |
| commit | R2 0.969, 6.68 s per 1k tokens, n=7 | R2 0.920, 6.26 s per 1k tokens, n=7 |

## Which stages matter for quality (ablation)

Measured by ablation runs against the answer key (`grade_book.py`): metered runs, not part of this report. Filled from `ablation.json` (stage to result) when it exists.

| stage | ablation result |
|---|---|
| commit | not measured |
| extract | not measured |
| registry | not measured |
