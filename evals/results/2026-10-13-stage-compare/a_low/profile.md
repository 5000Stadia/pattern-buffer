# Build profile: a_low

Total wall: 103.1 s. Percentiles are nearest-rank. Stage wall seconds are rounded to 0.1 s by the receipt.

## Per stage

| stage | wall s | share | workers | calls | objectives | latency sum s | utilization | p50 s | p90 s | max s | tokens in | tokens out | cached | out tok/s median | out tok/s p10 | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pass0 | 53.0 | 51.4% | 1 | 2 | 2 | 53.0 | 100.1% | 24.5 | 28.5 | 28.5 | 6 | 2868 | 0 | 51.6 | 51.6 | 0.0942 |
| pass1 | 18.4 | 17.8% | 4 | 4 | 4 | 59.6 | 81.0% | 13.9 | 18.4 | 18.4 | 12 | 3806 | 0 | 62.9 | 53.3 | 0.1784 |
| escape_repair | 0.0 | 0.0% | 1 | 0 | 0 | unmeasured | unmeasured | unmeasured | unmeasured | unmeasured | 0 | 0 | 0 | unmeasured | unmeasured | 0 |
| commit | 29.0 | 28.1% | 1 | 4 | 4 | 27.4 | 94.5% | 8.0 | 8.0 | 8.0 | 886 | 2512 | 0 | 96.9 | 41.0 | 0.0683 |
| audit | 2.7 | 2.6% | 1 | 1 | 1 | 2.6 | 98.1% | 2.6 | 2.6 | 2.6 | 3 | 8 | 0 | 3.0 | 3.0 | 0.0364 |

### CLI turns and API time (claude shim only)

| stage | turns/call median | turns/call max | API time share of latency | harness overhead s (latency minus API) | max concurrent calls |
|---|---|---|---|---|---|
| pass0 | 1.0 | 1.0 | 95.3% | 2.5 | 1 |
| pass1 | 1.0 | 1.0 | 90.4% | 5.7 | 4 |
| escape_repair | unmeasured | unmeasured | unmeasured | unmeasured | unmeasured |
| commit | 1.0 | 1.0 | 79.6% | 5.6 | 1 |
| audit | 1.0 | 1.0 | 38.8% | 1.6 | 1 |

## Turns to an objective

- **pass0**: 2 objectives, 2 accepted; attempts per objective {'1': 2}; retry seconds 0.0.
- **pass1**: 4 objectives, 4 accepted; attempts per objective {'1': 4}; retry seconds 0.0.
- **commit**: 4 objectives, 4 accepted; attempts per objective {'1': 4}; retry seconds 0.0.
- **audit**: 1 objectives, 1 accepted; attempts per objective {'1': 1}; retry seconds 0.0.

## Ceilings

Floor = the stage's longest single objective, the most parallelism can buy. Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### pass0: 2 objectives, measured wall 53.0 s, 1 worker(s) today
Floor 28.52 s (segment:00); serial sum 53.04 s.

| workers | list-scheduling replay s | no retries s |
|---|---|---|
| 1 (today) | 53.04 | 53.04 |
| 4 | 28.52 | 28.52 |
| 8 | 28.52 | 28.52 |

No-retries replay: each objective's first attempt's duration, as if accepted. Never accepted, shown separately (would still fail: 0): none. Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### pass1: 4 objectives, measured wall 18.4 s, 4 worker(s) today
Floor 18.37 s (chunk:02); serial sum 59.65 s.

| workers | list-scheduling replay s | no retries s |
|---|---|---|
| 1 | 59.65 | 59.65 |
| 4 (today) | 18.37 | 18.37 |
| 8 | 18.37 | 18.37 |

No-retries replay: each objective's first attempt's duration, as if accepted. Never accepted, shown separately (would still fail: 0): none. Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### commit: 4 objectives, measured wall 29.0 s, 1 worker(s) today
Floor 8.02 s (classify:02); serial sum 27.41 s.

Serial in the code, so no worker what-if. Never accepted, shown separately (would still fail: 0): none.

### audit: 1 objectives, measured wall 2.7 s, 1 worker(s) today
Floor 2.65 s (audit); serial sum 2.65 s.

Serial in the code, so no worker what-if. Never accepted, shown separately (would still fail: 0): none.


### Whole-build totals

| scenario | total s |
|---|---|
| measured | 103.1 |
| pass0 on 4 worker(s) | 78.6 |
| pass0 on 8 worker(s) | 78.6 |
| pass0 with unlimited workers (floor) | 78.6 |
| pass1 on 1 worker(s) | 144.4 |
| pass1 on 8 worker(s) | 103.1 |
| pass1 with unlimited workers (floor) | 103.1 |
| pass1 without retries (first attempts only) | 103.1 |
| commit with unlimited workers (floor) | 82.1 |
| audit with unlimited workers (floor) | 103.0 |
| overlapped pipeline (hypothetical) | 98.0 |

Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### Overlapped pipeline (hypothetical)

Dependency model (hypothetical, not today's code): a pass-1 chunk's facts can be classified as soon as that chunk is accepted. The commit's K classification batches are spread over the N accepted chunks in acceptance order; batch j becomes ready when chunk ceil(j*N/K) has finished (facts per chunk assumed even). Batches run, with their measured durations, one at a time on a separate worker. Escape repair, the commit's other work (its wall minus the summed batch durations) and the audit stay serial after the last chunk and the last batch, as today. Pass-0 stays as measured.

Pass-1 plus classification phase 40.72 s (last chunk 18.37 s, classification done 40.72 s); build total 98.0 s against measured 103.1 s (saves 5.1 s). Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

## Is a call slow because of what it writes or what it reads?

Least squares of latency on tokens (input counts cached tokens). A fit under 5 calls, or with zero variance, is unmeasured.

| scope | vs output tokens | vs input tokens |
|---|---|---|
| all | R2 0.834, 16.24 s per 1k tokens, n=11 | R2 0.150, 1.69 s per 1k tokens, n=11 |
| pass0 | unmeasured (fewer than 5 calls (2)) | unmeasured (fewer than 5 calls (2)) |
| pass1 | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |
| commit | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |
| audit | unmeasured (fewer than 5 calls (1)) | unmeasured (fewer than 5 calls (1)) |

## Which stages matter for quality (ablation)

Measured by ablation runs against the answer key (`grade_book.py`): metered runs, not part of this report. Filled from `ablation.json` (stage to result) when it exists.

| stage | ablation result |
|---|---|
| pass0 | not measured |
| pass1 | not measured |
| escape_repair | not measured |
| commit | not measured |
| audit | not measured |
