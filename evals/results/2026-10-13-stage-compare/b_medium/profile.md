# Build profile: b_medium

Total wall: 541.1 s. Percentiles are nearest-rank. Stage wall seconds are rounded to 0.1 s by the receipt.

## Per stage

| stage | wall s | share | workers | calls | objectives | latency sum s | utilization | p50 s | p90 s | max s | tokens in | tokens out | cached | out tok/s median | out tok/s p10 | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pass0 | 183.5 | 33.9% | 1 | 2 | 2 | 183.5 | 100.0% | 75.9 | 107.6 | 107.6 | 6 | 12246 | 0 | 63.7 | 63.7 | 0.2353 |
| pass1 | 199.5 | 36.9% | 4 | 4 | 4 | 539.8 | 67.6% | 118.1 | 199.5 | 199.5 | 12 | 41784 | 0 | 69.7 | 68.4 | 0.7781 |
| escape_repair | 158.1 | 29.2% | 1 | 2 | 2 | 158.1 | 100.0% | 51.3 | 106.8 | 106.8 | 6 | 12503 | 0 | 62.6 | 62.6 | 0.2462 |
| commit | 0.0 | 0.0% | 1 | 0 | 0 | unmeasured | unmeasured | unmeasured | unmeasured | unmeasured | 0 | 0 | 0 | unmeasured | unmeasured | 0 |

### CLI turns and API time (claude shim only)

| stage | turns/call median | turns/call max | API time share of latency | harness overhead s (latency minus API) | max concurrent calls |
|---|---|---|---|---|---|
| pass0 | 1.0 | 1.0 | 98.4% | 2.9 | 1 |
| pass1 | 1.0 | 1.0 | 99.0% | 5.4 | 4 |
| escape_repair | 1.0 | 1.0 | 98.3% | 2.7 | 1 |
| commit | unmeasured | unmeasured | unmeasured | unmeasured | unmeasured |

## Turns to an objective

- **pass0**: 2 objectives, 2 accepted; attempts per objective {'1': 2}; retry seconds 0.0.
- **pass1**: 4 objectives, 4 accepted; attempts per objective {'1': 4}; retry seconds 0.0.
- **escape_repair**: 2 objectives, 2 accepted; attempts per objective {'1': 2}; retry seconds 0.0.

## Ceilings

Floor = the stage's longest single objective, the most parallelism can buy. Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### pass0: 2 objectives, measured wall 183.5 s, 1 worker(s) today
Floor 107.63 s (segment:00); serial sum 183.50 s.

| workers | list-scheduling replay s | no retries s |
|---|---|---|
| 1 (today) | 183.50 | 183.50 |
| 4 | 107.63 | 107.63 |
| 8 | 107.63 | 107.63 |

No-retries replay: each objective's first attempt's duration, as if accepted. Never accepted, shown separately (would still fail: 0): none. Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### pass1: 4 objectives, measured wall 199.5 s, 4 worker(s) today
Floor 199.52 s (chunk:02); serial sum 539.81 s.

| workers | list-scheduling replay s | no retries s |
|---|---|---|
| 1 | 539.81 | 539.81 |
| 4 (today) | 199.52 | 199.52 |
| 8 | 199.52 | 199.52 |

No-retries replay: each objective's first attempt's duration, as if accepted. Never accepted, shown separately (would still fail: 0): none. Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### escape_repair: 2 objectives, measured wall 158.1 s, 1 worker(s) today
Floor 106.84 s (chunk:03); serial sum 158.10 s.

Serial in the code, so no worker what-if. Never accepted, shown separately (would still fail: 0): none.


### Whole-build totals

| scenario | total s |
|---|---|
| measured | 541.1 |
| pass0 on 4 worker(s) | 465.2 |
| pass0 on 8 worker(s) | 465.2 |
| pass0 with unlimited workers (floor) | 465.2 |
| pass1 on 1 worker(s) | 881.4 |
| pass1 on 8 worker(s) | 541.1 |
| pass1 with unlimited workers (floor) | 541.1 |
| pass1 without retries (first attempts only) | 541.1 |
| escape_repair with unlimited workers (floor) | 489.8 |

Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### Overlapped pipeline (hypothetical)

Dependency model (hypothetical, not today's code): a pass-1 chunk's facts can be classified as soon as that chunk is accepted. The commit's K classification batches are spread over the N accepted chunks in acceptance order; batch j becomes ready when chunk ceil(j*N/K) has finished (facts per chunk assumed even). Batches run, with their measured durations, one at a time on a separate worker. Escape repair, the commit's other work (its wall minus the summed batch durations) and the audit stay serial after the last chunk and the last batch, as today. Pass-0 stays as measured.

unmeasured: needs pass-1 chunk and classification-batch objectives and stage walls.

## Is a call slow because of what it writes or what it reads?

Least squares of latency on tokens (input counts cached tokens). A fit under 5 calls, or with zero variance, is unmeasured.

| scope | vs output tokens | vs input tokens |
|---|---|---|
| all | R2 0.954, 10.71 s per 1k tokens, n=8 | R2 0.445, 21.71 s per 1k tokens, n=8 |
| pass0 | unmeasured (fewer than 5 calls (2)) | unmeasured (fewer than 5 calls (2)) |
| pass1 | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |
| escape_repair | unmeasured (fewer than 5 calls (2)) | unmeasured (fewer than 5 calls (2)) |

## Which stages matter for quality (ablation)

Measured by ablation runs against the answer key (`grade_book.py`): metered runs, not part of this report. Filled from `ablation.json` (stage to result) when it exists.

| stage | ablation result |
|---|---|
| pass0 | not measured |
| pass1 | not measured |
| escape_repair | not measured |
| commit | not measured |
