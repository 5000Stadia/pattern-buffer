# BUILD-SPEED-V1: classification batches in parallel, and smaller chunks on request

**Status:** r1.1 (pbr's r1 RED: with `workers > 1`, `batch_size` must be an exact positive int, checked before any work; pbr confirmed the store-after-all-calls boundary and that verdict handling has no race). r1, for pbr review. Author: pb, 2026-10-14. An opt-in engine change (classification)
and a harness option. Defaults are unchanged.
**Source:** the library comparison (`evals/results/2026-10-13-library-compare/REPORT.md`). Its
one complete build took 246 s:
- **extract: 170 s.** Four chunk calls ran in parallel, so the wall was the slowest chunk.
- **commit: 58 s.** That was the post-commit `classify_all(batch_size=40)`: seven batch calls,
  about 8 s each, run one after another.

Kabe asked for the build-time drivers and how to cut them, adding "much of which can be
parallelized". The report proposed both changes here. Measuring them is a paid run, gate g460a1c.
**Builds on:** INGEST-HARDENING-V1 (`classify_rows`), BUILD-PROFILE-V1 (call labels),
BUILD-LIBRARY-V1 (`plan(max_words=)`).

## 1. Classification batches in parallel (engine, opt-in)

- **The change:** `Classifier.classify_rows(rows, batch_size=None, model=True, *, workers=1)` and
  `classify_all(batch_size=None, *, workers=1)`.
  - With `workers=1`, the default, behaviour is exactly today's: batches are called and stored
    one after another.
  - With `workers > 1` and `batch_size` set, the model-needing rows are split into batches as
    today, and each batch's **model call** runs in a thread pool of `workers`.
- **What runs in parallel is only the injected model call**
  (`self._model(prompt, task_schema(_BATCH_SCHEMA))`). The rest stays on the calling thread:
  - building each batch's prompt;
  - the guardrail pass, which already runs before batching and makes no model call;
  - reading the verdicts;
  - the asymmetric default for a failed or missing verdict;
  - every `_store` and sidecar write.

  Storage happens on the calling thread **in batch order** once all calls have returned, so
  the stored classes are exactly those of the serial path given the same verdicts. The engine's
  SQLite world stays bound to its owner thread.
- **A failed call** (an exception from the model) defaults its batch, exactly as the serial path
  does today (logged; every row falls to the asymmetric default). It doesn't affect the other
  batches.
- **Labels:** each submission runs in `contextvars.copy_context().run(...)`, taken on the calling
  thread, so a host's context variables follow the call into the worker. That includes the
  harness's usage label (`stage="commit"`). Standard library only; the engine imports nothing
  from the build library.
- **Contract for the host:** `workers > 1` means the injected model callable may be called from
  several threads at once. The host opts in only with a thread-safe callable. The harness shim
  already is (extract calls it from four workers). The docstring says so.
- **Bounds:** `workers` is an exact int of at least 1, and a bool is refused, the same as
  BUILD-LIBRARY-V1's `workers`. Anything else raises `ValueError` before any call.
  - *(r1.1, pbr)* When `workers > 1`, `batch_size` must be an **exact positive int**:
    `type(batch_size) is int and batch_size >= 1`. `None`, `0`, negatives, `True` and non-ints
    each raise `ValueError`.
  - Both checks run **before any work**: no guardrail pass, no store, no model call. With
    nothing to split into batches, there is nothing to parallelize.
  - Today's `step = batch_size or len(deferred)` stays as it is for `workers=1`, so existing
    callers are unaffected. Under `workers > 1` there is no way to collapse into one serial
    batch, or to skip rows with a negative step.
- **Not changed:**
  - the classify prompt and its schema;
  - `classify="batch"` inside `ingest_structured`, which is a single batch per call;
  - the `rules` path;
  - the single-row `classify()`.

## 2. Smaller chunks on request (harness)

- `run_book.py --max-words N` (an int of at least 100) passes `max_words=N` to `build.plan` for
  the library pipeline, and `meta.json` records it. It defaults to `LIBRARY_MAX_WORDS` (1500),
  unchanged.
- `run_book.py --classify-workers N` (default 1) passes `workers=N` to the post-commit
  `classify_all`.
- `--extract-workers N` (default 4, today's value) is added beside them, so a run can match more,
  smaller chunks with more workers.
- No prompt changes.

## 3. The measurement this enables (not part of the build)

Under Kabe's yes on g460a1c: Sonnet low, two runs each, chapters 1–2 of the practice book,
graded with `--through-chapter 2`:
- (i) today's settings;
- (ii) `--classify-workers 4`;
- (iii) `--max-words 750 --extract-workers 8 --classify-workers 4`.

Plus one 6-chapter build at the best setting. The report gives each stage's wall time and checks
that the grade doesn't drop, since smaller chunks see less context per call.

## Tests (no model calls)

1. **Same results:** a stub model with fixed verdicts. `classify_all(batch_size=3, workers=4)`
   over a 20-row world stores exactly the classes, confidences and `needs_review` flags of
   `workers=1`, and the sidecar dumps are equal.
2. **Really parallel:** a stub whose call blocks on a barrier of 4 completes with `workers=4` and
   times out with `workers=1`. The barrier has a timeout, so no test hangs.
3. **Failure isolation:** a stub raising on batch 2 of 5. Batch 2's rows get the asymmetric
   default, the other batches their verdicts, the same as the serial path with the same stub.
4. **Stores on the owner thread:** every `_store` call is recorded with its thread id, and all
   are the caller's.
5. **Context:** a context variable set by the caller is visible inside every model call, in each
   worker.
6. **Bounds:**
   - `workers` of 0, -1, `True`, 1.5 and `"2"` each raise `ValueError` with zero calls;
   - *(r1.1)* with `workers=2`, a `batch_size` of `None`, 0, -3, `True`, 2.0 and `"40"` each
     raise `ValueError`, with no model call, no store and the sidecar unchanged;
   - with `workers=1`, today's `batch_size` handling is unchanged (pinned).
7. **Harness:**
   - `--max-words 750` reaches `plan`, and `meta.json` records it;
   - `--classify-workers` and `--extract-workers` reach their calls (fake shim);
   - the defaults reproduce today's argv and behaviour.
8. **Full suite green.**
