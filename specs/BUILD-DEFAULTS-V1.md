# BUILD-DEFAULTS-V1: the library pipeline's harness defaults become the measured fastest setting

**Status:** r1, for pbr review. Author: pb, 2026-10-14. A harness-only change to
`evals/harness/run_book.py`. No engine or library change, and no model call to build it.
**Source:** the speed comparison (`evals/results/2026-10-14-speed-compare/REPORT.md`, Kabe's gate
g460a1c). Setting (iii), `--max-words 750 --extract-workers 8 --classify-workers 4`, was the
fastest at equal quality:
- two chapters in 112–119 s, against 224–357 s on today's defaults;
- the whole 6-chapter practice book in 225 s for $2.58;
- zero wrong merges and zero leaks in every run, and identity F1 0.775–0.784 across all settings.

The report recommended making it the default through a small spec. The monitor, for Kabe, asked
for this spec on 2026-10-14 (note n1b57a5).
**Builds on:** BUILD-SPEED-V1 (the three options), BUILD-LIBRARY-V1 §7 (`--pipeline library`).

## The change

1. **`run_book.py`'s library-pipeline defaults** become:
   - `LIBRARY_MAX_WORDS = 750` (was 1500);
   - `LIBRARY_EXTRACT_WORKERS = 8` (was a literal 4);
   - `LIBRARY_CLASSIFY_WORKERS = 4` (was a literal 1).

   The two worker defaults become named constants beside `LIBRARY_MAX_WORDS`. `run_book()`,
   `_run_library()` and `parse_args()` take their defaults from the three constants, and the
   `--help` texts print them.
2. **INGEST-V2's refusal** of the library options compares against the three constants, not
   the literal `(1500, 1, 4)`. Its behaviour is unchanged: a value other than the default is
   refused on INGEST-V2, and the defaults pass. (As today, passing the default value explicitly
   can't be told from leaving it out.)
3. **Re-planning an older run keeps its own chunking.**
   - `library_chunks()` re-plans a run from its `manifest.json` and `meta.json`, falling back to
     `LIBRARY_MAX_WORDS` when `meta.json` has no `max_words`.
   - A run without that key was built before BUILD-SPEED-V1 recorded it, so it was cut at
     1500 words. With the new default, the fallback would re-cut it at 750 and grade the wrong
     chunks.
   - So the fallback becomes a named `PRE_SPEED_MAX_WORDS = 1500`, the chunk size of every run
     that didn't record one. A run that recorded `max_words` is re-planned with its own value,
     as today.
4. **A library run's `meta.json` records the worker counts** beside `max_words`, as
   `extract_workers` and `classify_workers`. Today it records only `max_words`, so once the
   defaults change a receipt couldn't show which worker setting a run used.
5. **Nothing else.** These stay as they are:
   - the library's own function defaults (`plan(max_words=1500)`, `extract(workers=4)`,
     `classify_all(workers=1)`). Hosts call these directly. A chunk-size change alters what a
     host's build extracts, and worker counts bear on a host's rate limits, so each host
     chooses. The ship notice gives construct and holo-emitter the measured numbers;
   - the INGEST-V2 pipeline, which remains the harness's default pipeline;
   - `estimate()` and the dry run, which scale R26's measured INGEST-V2 build and don't read
     these options.

## Tests (no model calls)

In `tests/test_build_speed.py`, test 7 is re-pinned:
1. With no flags, `parse_args` gives `(750, 4, 8)` for `(max_words, classify_workers,
   extract_workers)`, equal to the three constants.
2. Explicit flags still override: `--max-words 1500 --classify-workers 1 --extract-workers 4`
   gives `(1500, 1, 4)`. That is today's setting, still reachable.
3. `run_book(..., pipeline="ingest-v2")` with no speed options isn't refused (the stubbed
   pipeline reaches its first stage). With `max_words=1500` it is refused, naming the options.
4. `library_chunks()` on a run directory whose `meta.json` has no `max_words` re-plans at 1500
   words: a stub book whose chapter is between 750 and 1500 words gives one chunk, not two. With
   `max_words: 750` recorded, the same book gives two.
5. A library run with no speed flags records `max_words: 750`, `extract_workers: 8` and
   `classify_workers: 4` in `meta.json`, and calls `extract` and `classify_all` with those values
   (scripted model, as in the existing library-run tests).
6. Full suite green.
