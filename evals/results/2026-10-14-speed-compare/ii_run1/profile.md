# Build profile: ii_run1

Total wall: 164.1 s. Percentiles are nearest-rank. Stage wall seconds are rounded to 0.1 s by the receipt.
- NOTE: no objectives.jsonl: turns, floors and what-ifs are unmeasured

## Per stage

| stage | wall s | share | workers | calls | objectives | latency sum s | utilization | p50 s | p90 s | max s | tokens in | tokens out | cached | out tok/s median | out tok/s p10 | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| commit | 22.9 | 14.0% | 1 | 7 | unmeasured | 58.2 | 254.2% | 8.6 | 9.0 | 9.0 | 21 | 5244 | 0 | 89.6 | 77.6 | 0.1445 |
| extract | 128.7 | 78.4% | 1 | 5 | unmeasured | 372.3 | 289.3% | 74.7 | 128.7 | 128.7 | 15 | 29646 | 0 | 80.2 | 74.1 | 0.5590 |
| registry | 12.5 | 7.6% | 1 | 4 | unmeasured | 37.7 | 301.8% | 9.4 | 12.5 | 12.5 | 12 | 1681 | 0 | 40.9 | 32.0 | 0.1839 |

### CLI turns and API time (claude shim only)

| stage | turns/call median | turns/call max | API time share of latency | harness overhead s (latency minus API) | max concurrent calls |
|---|---|---|---|---|---|
| commit | 1.0 | 1.0 | 77.7% | 13.0 | 4 |
| extract | 1.0 | 1.0 | 98.2% | 6.7 | 4 |
| registry | 1.0 | 1.0 | 84.4% | 5.9 | 4 |

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
| all | R2 0.991, 12.82 s per 1k tokens, n=16 | R2 0.044, 3.73 s per 1k tokens, n=16 |
| registry | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |
| extract | R2 0.994, 14.12 s per 1k tokens, n=5 | R2 0.902, 41.25 s per 1k tokens, n=5 |
| commit | R2 0.884, 7.10 s per 1k tokens, n=7 | R2 0.629, 5.96 s per 1k tokens, n=7 |

## Which stages matter for quality (ablation)

Measured by ablation runs against the answer key (`grade_book.py`): metered runs, not part of this report. Filled from `ablation.json` (stage to result) when it exists.

| stage | ablation result |
|---|---|
| commit | not measured |
| extract | not measured |
| registry | not measured |
