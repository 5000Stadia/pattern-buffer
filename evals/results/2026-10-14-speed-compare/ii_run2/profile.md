# Build profile: ii_run2

Total wall: 180.4 s. Percentiles are nearest-rank. Stage wall seconds are rounded to 0.1 s by the receipt.
- NOTE: no objectives.jsonl: turns, floors and what-ifs are unmeasured

## Per stage

| stage | wall s | share | workers | calls | objectives | latency sum s | utilization | p50 s | p90 s | max s | tokens in | tokens out | cached | out tok/s median | out tok/s p10 | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| commit | 18.8 | 10.4% | 1 | 7 | unmeasured | 56.2 | 299.2% | 8.4 | 8.7 | 8.7 | 21 | 5102 | 0 | 94.7 | 62.4 | 0.1401 |
| extract | 146.4 | 81.2% | 1 | 4 | unmeasured | 383.6 | 262.0% | 70.7 | 146.4 | 146.4 | 12 | 31448 | 0 | 83.0 | 78.4 | 0.5664 |
| registry | 15.2 | 8.4% | 1 | 4 | unmeasured | 37.7 | 247.9% | 9.1 | 15.1 | 15.1 | 12 | 1657 | 0 | 41.0 | 20.0 | 0.1835 |

### CLI turns and API time (claude shim only)

| stage | turns/call median | turns/call max | API time share of latency | harness overhead s (latency minus API) | max concurrent calls |
|---|---|---|---|---|---|
| commit | 1.0 | 1.0 | 79.4% | 11.6 | 4 |
| extract | 1.0 | 1.0 | 98.1% | 7.3 | 4 |
| registry | 1.0 | 1.0 | 83.3% | 6.3 | 4 |

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
| all | R2 0.995, 12.22 s per 1k tokens, n=15 | R2 0.039, 3.83 s per 1k tokens, n=15 |
| registry | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |
| extract | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |
| commit | R2 0.941, 5.87 s per 1k tokens, n=7 | R2 0.769, 5.39 s per 1k tokens, n=7 |

## Which stages matter for quality (ablation)

Measured by ablation runs against the answer key (`grade_book.py`): metered runs, not part of this report. Filled from `ablation.json` (stage to result) when it exists.

| stage | ablation result |
|---|---|
| commit | not measured |
| extract | not measured |
| registry | not measured |
