# Build profile: iii_run2

Total wall: 118.5 s. Percentiles are nearest-rank. Stage wall seconds are rounded to 0.1 s by the receipt.
- NOTE: no objectives.jsonl: turns, floors and what-ifs are unmeasured

## Per stage

| stage | wall s | share | workers | calls | objectives | latency sum s | utilization | p50 s | p90 s | max s | tokens in | tokens out | cached | out tok/s median | out tok/s p10 | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| commit | 19.2 | 16.2% | 1 | 8 | unmeasured | 64.3 | 335.0% | 8.2 | 8.5 | 8.5 | 24 | 5859 | 0 | 93.6 | 56.1 | 0.1607 |
| extract | 85.2 | 71.9% | 1 | 6 | unmeasured | 409.4 | 480.6% | 63.7 | 85.2 | 85.2 | 18 | 34480 | 0 | 83.3 | 78.9 | 0.6364 |
| registry | 14.1 | 11.9% | 1 | 4 | unmeasured | 37.4 | 265.4% | 9.1 | 14.0 | 14.0 | 12 | 1624 | 0 | 39.0 | 27.4 | 0.1830 |

### CLI turns and API time (claude shim only)

| stage | turns/call median | turns/call max | API time share of latency | harness overhead s (latency minus API) | max concurrent calls |
|---|---|---|---|---|---|
| commit | 1.0 | 1.0 | 80.0% | 12.8 | 4 |
| extract | 1.0 | 1.0 | 97.6% | 9.7 | 6 |
| registry | 1.0 | 1.0 | 82.4% | 6.6 | 4 |

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
| all | R2 0.989, 11.70 s per 1k tokens, n=18 | R2 0.002, 0.72 s per 1k tokens, n=18 |
| registry | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |
| extract | R2 0.937, 12.91 s per 1k tokens, n=6 | R2 0.254, 35.51 s per 1k tokens, n=6 |
| commit | R2 0.891, 4.28 s per 1k tokens, n=8 | R2 0.879, 4.61 s per 1k tokens, n=8 |

## Which stages matter for quality (ablation)

Measured by ablation runs against the answer key (`grade_book.py`): metered runs, not part of this report. Filled from `ablation.json` (stage to result) when it exists.

| stage | ablation result |
|---|---|
| commit | not measured |
| extract | not measured |
| registry | not measured |
