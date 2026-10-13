# BUILD-PROFILE-V1: where a book build's time, turns and tokens go, per model call

**Status:** r1, for pbr review. Author: pb, 2026-10-13. Harness only: the engine is untouched.
**Source:** Kabe on gate g10c3af (2026-10-13): "I want to put a little pause right here now, to
consider optimization for speed of building that story. Do you have thorough benchmarks and
logging to determine what element takes up what amount of time during the build process? And
within that information, how many turns it takes to reach objectives on the way and how many tokens
are used in token costs … if it takes three hours I wanna know what's taking that time and if it is
critical for quality."
**Builds on:** BOOK-RUN-V1 (`run_book.py`, per-stage receipts), the usage ledger (TOKEN-RECEIPTS),
BUILD-TIMINGS-V1 (R26's stage split).

## Need

**What we have.**
- Per-stage wall time: `timings.json`, R26.
- Per-stage tokens and cost: `receipt.json`.
- One JSON line per call with tokens: `usage.jsonl`.

**What is missing.** Kabe's questions can't be answered from that:
- **Per-call latency.** Without it there's no tokens-per-second figure, and nothing to show whether
  calls are output-bound.
- **Which stage and unit a call served.** `usage.jsonl` lines carry no stage, no chunk, and no
  attempt number.
- **Turns to an objective.** How many attempts a chunk needed before its extraction was accepted
  (the reject-rate retry), how many glean rounds pass-0 took, and how many escape repairs ran.
- **How busy the parallel stages are.** Four workers can sit idle behind one slow chunk.
- **The ceiling.** How fast each stage could go with more parallelism, judged from the calls it
  actually made.

## The shape

### 1. Every call is labelled and timed

- **Labels.** `usage_ledger.label(stage=..., unit=..., attempt=...)` is a context manager on a
  `contextvars.ContextVar`.
  - Every `record(...)` inside it writes the label into its JSON line.
  - Calls outside any label get `stage: null`. They are counted, never dropped.
- **Worker threads.** `ThreadPoolExecutor` does not carry context into its workers. The pipeline's
  submits therefore wrap each task in `contextvars.copy_context().run`, so a pass-1 worker's calls
  carry their chunk's label.
- **Timing.** `record(...)` gains `started` (epoch seconds) and `latency_s`. Each shim measures
  around its own subprocess or HTTP call: `model_shim` (claude), `codex_shim`, and the merge gate's
  calls through the injected model.
  - A timeout records its `latency_s` up to the timeout, with `outcome: "timeout"`.
  - A non-zero exit records `outcome: "error"`.
  - Otherwise the outcome is `"ok"`.
- **The JSON line, fully:**

  ```json
  {"t": …, "started": …, "latency_s": …, "provider": …, "model": …,
   "stage": "pass1", "unit": "chunk:07", "attempt": 2, "outcome": "ok",
   "input_tokens": …, "output_tokens": …, "cache_read_tokens": …,
   "cache_write_tokens": …, "cost_usd": …, "usage_reported": true}
  ```

  `prompt_chars` and `response_chars` are added too, from data the shim already holds. They give a
  size measure for providers that report no tokens.

### 2. Objectives: how many turns each unit took

- An **objective** is one unit of work the pipeline needs accepted:
  - a pass-0 segment, with its glean rounds as attempts;
  - a pass-1 chunk, whose attempts are 1 and 2 and whose acceptance is the reject-rate check;
  - an escape repair;
  - a classification batch;
  - a merge-gate batch;
  - the audit.
- The pipeline writes one line per objective to the same log when it settles:

  ```json
  {"event": "objective", "stage": "pass1", "unit": "chunk:07", "attempts": 2,
   "accepted": true, "seconds": 241.3, "reason": null}
  ```

  `reason` is the rejection text when `accepted` is false: the reject rate, a parse failure or a
  timeout.
- Nothing in the pipeline's behaviour changes. It only reports what it already decides.

### 3. The profile report: `evals/harness/profile_build.py RUN_DIR`

It reads `usage.jsonl`, `timings.json` and `receipt.json`. It is deterministic, makes no model
call, and writes `profile.json` and `profile.md`.

- **Per stage:**
  - wall seconds and share of the total;
  - calls and objectives;
  - the sum of call latency;
  - **utilization**: summed latency ÷ (wall × the stage's workers);
  - p50, p90 and maximum latency;
  - tokens in, out and cached;
  - **output tokens per second** per call (median and p10);
  - cost.
- **Turns:** for each stage, the attempts-per-objective histogram, the units that needed a retry
  (with reasons), and the seconds spent on retries.
- **Ceilings, computed from the measured calls with no new run:**
  - the stage's **floor**: its longest single objective, which is the most parallelism can buy;
  - **what-if wall times**, from a list-scheduling replay of the measured objective durations
    under:
    - pass-0 parallel (4 workers);
    - pass-1 with 8 workers;
    - classification and audit overlapped with pass-1's tail;
    - no retries.

  The replay assumes call latency doesn't change with concurrency. The report says so, because R26
  measured that four parallel pass-0 calls each ran slower.
- **The output-bound test:** a fit of latency against output tokens and against input tokens, with
  R² for each. It answers whether calls are slow because of what they write or what they read.
- **Old runs:** the report reads R25-metered and R26 directories too.
  - R26's lines have no `latency_s` or labels, so it falls back to stage totals and marks the
    fields as unmeasured.
  - It never invents a value.

### 4. Quality: what is critical

This spec measures time and turns; it doesn't measure quality. Which stages matter for quality is
measured by ablation, and that is a metered run, so it goes to Kabe. The profile report has a
place for it:
- `profile.md` ends with a table of the stages, with a column for each stage's ablation result
  (accuracy against the answer key with the stage cut or swapped, from `grade_book.py`);
- that column is filled when such runs exist;
- otherwise it says "not measured".

## Not in this spec

- Any change to what a build does, how it calls the model, or its prompts. Speed changes come
  after the profile, the prior-art read and the consult. Kabe chooses among them.
- Any metered run. The acceptance below uses a fake model with sleeps.

## Tests (the build's acceptance; no model calls)

1. **Labels.**
   - A fake model with set sleeps and token counts runs `run_book` on the three-chapter toy book
     with 4 pass-1 workers.
   - Every `usage.jsonl` call line has the right stage, unit and attempt, including lines from
     worker threads.
   - A call outside any label has `stage: null` and is counted.
2. **Timing.** `latency_s` is within 50 ms of the fake's sleep. A fake timeout records
   `outcome: "timeout"` and an error records `outcome: "error"`, both still counted by the receipt.
3. **Objectives.**
   - A chunk whose first parse fails the reject check has `attempts: 2, accepted: true`.
   - One that fails twice has `accepted: false` with its reason, and the run aborts as today.
   - The objective lines' count equals the units the run planned.
4. **Report.** On the fake run:
   - stage shares sum to 1 (±0.01);
   - utilization is in (0, 1];
   - p50 and p90 match the fake latencies;
   - the floor is the longest objective;
   - the list-scheduling what-if for 8 workers equals a hand-computed schedule;
   - the latency fit gives R² near 1 for output tokens on a fake whose sleep is proportional to
     output.
5. **Old runs.** `profile_build.py` on `evals/results/2026-10-10-r26-build-timings/seq` writes a
   report with stage totals, and marks per-call fields "unmeasured". It doesn't fail.
6. **The ledger.** `snapshot()` and the receipt are unchanged by the new fields, and the existing
   `tests/test_usage_ledger.py` and `tests/test_book_run.py` pass unchanged.
7. **Full suite green.**
