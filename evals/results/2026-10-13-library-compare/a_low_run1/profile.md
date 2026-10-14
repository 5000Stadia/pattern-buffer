# Build profile: a_low_run1

Total wall: 119.8 s. Percentiles are nearest-rank. Stage wall seconds are rounded to 0.1 s by the receipt.
- NOTE: no objectives.jsonl: turns, floors and what-ifs are unmeasured

## Per stage

| stage | wall s | share | workers | calls | objectives | latency sum s | utilization | p50 s | p90 s | max s | tokens in | tokens out | cached | out tok/s median | out tok/s p10 | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| extract | 105.1 | 87.7% | 1 | 4 | unmeasured | 327.2 | 311.3% | 68.0 | 105.1 | 105.1 | 12 | 27072 | 0 | 81.8 | 80.6 | 0.5010 |
| registry | 14.7 | 12.3% | 1 | 4 | unmeasured | 39.3 | 267.2% | 9.5 | 14.7 | 14.7 | 12 | 1624 | 0 | 38.5 | 23.8 | 0.1830 |

### CLI turns and API time (claude shim only)

| stage | turns/call median | turns/call max | API time share of latency | harness overhead s (latency minus API) | max concurrent calls |
|---|---|---|---|---|---|
| extract | 1.0 | 1.0 | 98.2% | 5.8 | 4 |
| registry | 1.0 | 1.0 | 78.4% | 8.5 | 4 |

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
| all | R2 0.997, 11.48 s per 1k tokens, n=8 | R2 0.495, -18.67 s per 1k tokens, n=8 |
| registry | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |
| extract | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |

## Which stages matter for quality (ablation)

Measured by ablation runs against the answer key (`grade_book.py`): metered runs, not part of this report. Filled from `ablation.json` (stage to result) when it exists.

| stage | ablation result |
|---|---|
| extract | not measured |
| registry | not measured |
