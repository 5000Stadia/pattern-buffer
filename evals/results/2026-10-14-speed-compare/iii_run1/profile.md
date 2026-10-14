# Build profile: iii_run1

Total wall: 112.4 s. Percentiles are nearest-rank. Stage wall seconds are rounded to 0.1 s by the receipt.
- NOTE: no objectives.jsonl: turns, floors and what-ifs are unmeasured

## Per stage

| stage | wall s | share | workers | calls | objectives | latency sum s | utilization | p50 s | p90 s | max s | tokens in | tokens out | cached | out tok/s median | out tok/s p10 | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| commit | 18.9 | 16.8% | 1 | 8 | unmeasured | 65.3 | 345.4% | 8.2 | 8.6 | 8.6 | 24 | 6123 | 0 | 94.0 | 85.1 | 0.1666 |
| extract | 79.1 | 70.4% | 1 | 6 | unmeasured | 339.2 | 428.8% | 49.4 | 79.1 | 79.1 | 18 | 28910 | 0 | 83.5 | 78.4 | 0.5536 |
| registry | 14.4 | 12.8% | 1 | 4 | unmeasured | 38.1 | 264.9% | 9.2 | 14.4 | 14.4 | 12 | 1643 | 0 | 43.1 | 17.1 | 0.1833 |

### CLI turns and API time (claude shim only)

| stage | turns/call median | turns/call max | API time share of latency | harness overhead s (latency minus API) | max concurrent calls |
|---|---|---|---|---|---|
| commit | 1.0 | 1.0 | 81.5% | 12.1 | 4 |
| extract | 1.0 | 1.0 | 97.0% | 10.3 | 6 |
| registry | 1.0 | 1.0 | 82.5% | 6.7 | 4 |

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
| all | R2 0.987, 11.29 s per 1k tokens, n=18 | R2 0.003, 0.64 s per 1k tokens, n=18 |
| registry | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |
| extract | R2 0.968, 10.56 s per 1k tokens, n=6 | R2 0.175, 30.15 s per 1k tokens, n=6 |
| commit | R2 0.782, 6.10 s per 1k tokens, n=8 | R2 0.767, 7.41 s per 1k tokens, n=8 |

## Which stages matter for quality (ablation)

Measured by ablation runs against the answer key (`grade_book.py`): metered runs, not part of this report. Filled from `ablation.json` (stage to result) when it exists.

| stage | ablation result |
|---|---|
| commit | not measured |
| extract | not measured |
| registry | not measured |
