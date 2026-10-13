# Build profile: run1

Total wall: 2023.7 s. Percentiles are nearest-rank. Stage wall seconds are rounded to 0.1 s by the receipt.

## Per stage

| stage | wall s | share | workers | calls | objectives | latency sum s | utilization | p50 s | p90 s | max s | tokens in | tokens out | cached | out tok/s median | out tok/s p10 | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pass0 | 786.0 | 38.8% | 1 | 3 | 2 | 771.0 | 98.1% | 239.8 | 300.1 | 300.1 | 6 | 32590 | 0 | 67.4 | 67.4 | 0.5273 (lower bound) |
| pass1 | 1237.7 | 61.2% | 4 | 7 | 4 | 1732.9 | 35.0% | 292.2 | 300.2 | 300.2 | 12 | 63478 | 0 | 68.8 | 65.6 | 1.1091 (lower bound) |
| escape_repair | unmeasured | unmeasured | 1 | 5 | 1 | 1369.4 | unmeasured | 300.1 | 300.1 | 300.1 | 3 | 11796 | 0 | 69.8 | 69.8 | 0.1979 (lower bound) |

### CLI turns and API time (claude shim only)

| stage | turns/call median | turns/call max | API time share of latency | harness overhead s (latency minus API) | max concurrent calls |
|---|---|---|---|---|---|
| pass0 | 1.0 | 1.0 | 99.4% | 3.0 | 1 |
| pass1 | 1.0 | 1.0 | 99.4% | 5.3 | 4 |
| escape_repair | 1.0 | 1.0 | 99.2% | 1.3 | 1 |

## Turns to an objective

- **pass0**: 2 objectives, 2 accepted; attempts per objective {'1': 2}; retry seconds 0.0.
- **pass1**: 4 objectives, 4 accepted; attempts per objective {'1': 3, '2': 1}; retry seconds 292.2.
  - chunk:00 (accepted: True): ["model call failed after retries: Command '['claude', '-p', '--model', 'claude-sonnet-4-6', '--output-format', 'json', '--max-turns', '1', '--tools', '', '--strict-mcp-config', '--setting-sources', '', '--no-session-persistence', '--system-prompt', 'You answer with one JSON object that matches the schema in the user message. No prose, no code fences, no tools.']' timed out after 300 seconds"]
- **escape_repair**: 1 objectives, 1 accepted; attempts per objective {'1': 1}; retry seconds 0.0.

## Ceilings

Floor = the stage's longest single objective, the most parallelism can buy. Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### pass0: 2 objectives, measured wall 786.0 s, 1 worker(s) today
Floor 546.21 s (segment:01); serial sum 785.99 s.

| workers | list-scheduling replay s | no retries s |
|---|---|---|
| 1 (today) | 785.99 | 785.99 |
| 4 | 546.21 | 546.21 |
| 8 | 546.21 | 546.21 |

No-retries replay: each objective's first attempt's duration, as if accepted. Never accepted, shown separately (would still fail: 0): none. Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### pass1: 4 objectives, measured wall 1237.7 s, 4 worker(s) today
Floor 1237.70 s (chunk:00); serial sum 1777.94 s.

| workers | list-scheduling replay s | no retries s |
|---|---|---|
| 1 | 1777.94 | 1485.74 |
| 4 (today) | 1237.70 | 945.50 |
| 8 | 1237.70 | 945.50 |

No-retries replay: each objective's first attempt's duration, as if accepted. Never accepted, shown separately (would still fail: 0): none. Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### escape_repair: 1 objectives, measured wall unmeasured s, 1 worker(s) today
Floor 168.91 s (registry_extend); serial sum 168.91 s.

Serial in the code, so no worker what-if. Never accepted, shown separately (would still fail: 0): none.


### Whole-build totals

| scenario | total s |
|---|---|
| measured | 2023.7 |
| pass0 on 4 worker(s) | 1783.9 |
| pass0 on 8 worker(s) | 1783.9 |
| pass0 with unlimited workers (floor) | 1783.9 |
| pass1 on 1 worker(s) | 2563.9 |
| pass1 on 8 worker(s) | 2023.7 |
| pass1 with unlimited workers (floor) | 2023.7 |
| pass1 without retries (first attempts only) | 1731.5 |

Lower bound: call latency is assumed not to change with concurrency. R26 measured four parallel pass-0 calls each running slower.

### Overlapped pipeline (hypothetical)

Dependency model (hypothetical, not today's code): a pass-1 chunk's facts can be classified as soon as that chunk is accepted. The commit's K classification batches are spread over the N accepted chunks in acceptance order; batch j becomes ready when chunk ceil(j*N/K) has finished (facts per chunk assumed even). Batches run, with their measured durations, one at a time on a separate worker. Escape repair, the commit's other work (its wall minus the summed batch durations) and the audit stay serial after the last chunk and the last batch, as today. Pass-0 stays as measured.

unmeasured: needs pass-1 chunk and classification-batch objectives and stage walls.

## Is a call slow because of what it writes or what it reads?

Least squares of latency on tokens (input counts cached tokens). A fit under 5 calls, or with zero variance, is unmeasured.

| scope | vs output tokens | vs input tokens |
|---|---|---|
| all | R2 0.968, 11.09 s per 1k tokens, n=7 | R2 0.033, 6.75 s per 1k tokens, n=7 |
| pass0 | unmeasured (fewer than 5 calls (2)) | unmeasured (fewer than 5 calls (2)) |
| pass1 | unmeasured (fewer than 5 calls (4)) | unmeasured (fewer than 5 calls (4)) |
| escape_repair | unmeasured (fewer than 5 calls (1)) | unmeasured (fewer than 5 calls (1)) |

## Which stages matter for quality (ablation)

Measured by ablation runs against the answer key (`grade_book.py`): metered runs, not part of this report. Filled from `ablation.json` (stage to result) when it exists.

| stage | ablation result |
|---|---|
| pass0 | not measured |
| pass1 | not measured |
| escape_repair | not measured |
