# Build profile: c_tiered

Total wall: 1178.7 s. Percentiles are nearest-rank. Stage wall seconds are rounded to 0.1 s by the receipt.

## Per stage

| stage | wall s | share | workers | calls | objectives | latency sum s | utilization | p50 s | p90 s | max s | tokens in | tokens out | cached | out tok/s median | out tok/s p10 | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pass0 | 358.3 | 30.4% | 1 | 2 | 2 | 358.3 | 100.0% | 139.6 | 218.7 | 218.7 | 6 | 22749 | 0 | 59.7 | 59.7 | 0.3936 |
| pass1 | 327.7 | 27.8% | 4 | 5 | 4 | 801.1 | 61.1% | 162.3 | 183.5 | 183.5 | 50 | 99539 | 0 | 126.2 | 119.0 | 0.5751 |
| escape_repair | 492.7 | 41.8% | 1 | 4 | 4 | 492.7 | 100.0% | 89.8 | 216.1 | 216.1 | 12 | 38371 | 0 | 78.8 | 64.4 | 0.7688 |
| commit | 0.0 | 0.0% | 1 | 0 | 0 | unmeasured | unmeasured | unmeasured | unmeasured | unmeasured | 0 | 0 | 0 | unmeasured | unmeasured | 0 |

### CLI turns and API time (claude shim only)

| stage | turns/call median | turns/call max | API time share of latency | harness overhead s (latency minus API) | max concurrent calls |
|---|---|---|---|---|---|
| pass0 | 1.0 | 1.0 | 99.2% | 2.8 | 1 |
| pass1 | 1.0 | 1.0 | 99.2% | 6.7 | 4 |
| escape_repair | 1.0 | 1.0 | 99.0% | 4.8 | 1 |
| commit | unmeasured | unmeasured | unmeasured | unmeasured | unmeasured |

## Turns to an objective

- **pass0**: 2 objectives, 2 accepted; attempts per objective {'1': 2}; retry seconds 0.0.
- **pass1**: 4 objectives, 4 accepted; attempts per objective {'1': 3, '2': 1}; retry seconds 144.3.
  - chunk:00 (accepted: True): ['reject rate over threshold (38 rejects)']
- **escape_repair**: 4 objectives, 4 accepted; attempts per objective {'1': 4}; retry seconds 0.0.

## Ceilings

Floor = the stage's longest single objective, the most parallelism can buy. Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### pass0: 2 objectives, measured wall 358.3 s, 1 worker(s) today
Floor 218.71 s (segment:00); serial sum 358.33 s.

| workers | list-scheduling replay s | no retries s |
|---|---|---|
| 1 (today) | 358.33 | 358.33 |
| 4 | 218.71 | 218.71 |
| 8 | 218.71 | 218.71 |

No-retries replay: each objective's first attempt's duration, as if accepted. Never accepted, shown separately (would still fail: 0): none. Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### pass1: 4 objectives, measured wall 327.7 s, 4 worker(s) today
Floor 327.74 s (chunk:00); serial sum 801.11 s.

| workers | list-scheduling replay s | no retries s |
|---|---|---|
| 1 | 801.11 | 656.84 |
| 4 (today) | 327.74 | 183.47 |
| 8 | 327.74 | 183.47 |

No-retries replay: each objective's first attempt's duration, as if accepted. Never accepted, shown separately (would still fail: 0): none. Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### escape_repair: 4 objectives, measured wall 492.7 s, 1 worker(s) today
Floor 216.05 s (chunk:02); serial sum 492.70 s.

Serial in the code, so no worker what-if. Never accepted, shown separately (would still fail: 0): none.


### Whole-build totals

| scenario | total s |
|---|---|
| measured | 1178.7 |
| pass0 on 4 worker(s) | 1039.1 |
| pass0 on 8 worker(s) | 1039.1 |
| pass0 with unlimited workers (floor) | 1039.1 |
| pass1 on 1 worker(s) | 1652.1 |
| pass1 on 8 worker(s) | 1178.7 |
| pass1 with unlimited workers (floor) | 1178.7 |
| pass1 without retries (first attempts only) | 1034.5 |
| escape_repair with unlimited workers (floor) | 902.1 |

Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### Overlapped pipeline (hypothetical)

Dependency model (hypothetical, not today's code): a pass-1 chunk's facts can be classified as soon as that chunk is accepted. The commit's K classification batches are spread over the N accepted chunks in acceptance order; batch j becomes ready when chunk ceil(j*N/K) has finished (facts per chunk assumed even). Batches run, with their measured durations, one at a time on a separate worker. Escape repair, the commit's other work (its wall minus the summed batch durations) and the audit stay serial after the last chunk and the last batch, as today. Pass-0 stays as measured.

unmeasured: needs pass-1 chunk and classification-batch objectives and stage walls.

## Is a call slow because of what it writes or what it reads?

Least squares of latency on tokens (input counts cached tokens). A fit under 5 calls, or with zero variance, is unmeasured.

| scope | vs output tokens | vs input tokens |
|---|---|---|
| all | R2 0.516, 5.36 s per 1k tokens, n=11 | R2 0.036, -5.70 s per 1k tokens, n=11 |
| pass0 | unmeasured (fewer than 5 calls (2)) | unmeasured (fewer than 5 calls (2)) |
| pass1 | R2 0.952, 7.83 s per 1k tokens, n=5 | R2 0.103, 34.88 s per 1k tokens, n=5 |
| escape_repair | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |

## Which stages matter for quality (ablation)

Measured by ablation runs against the answer key (`grade_book.py`): metered runs, not part of this report. Filled from `ablation.json` (stage to result) when it exists.

| stage | ablation result |
|---|---|
| pass0 | not measured |
| pass1 | not measured |
| escape_repair | not measured |
| commit | not measured |
