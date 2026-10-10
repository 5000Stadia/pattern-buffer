# BUILD-TIMINGS-V1: where a book build's time goes, and parallel pass-0 (roadmap R26)

**Status:** r1 (2026-10-10). Harness only: no engine change. Research note
technique 3 (`docs/research/book-to-world-extraction-2026-10.md`), sized by
the monitor's note n7df1c6: at most **4 full runs**, then stop and report.

## Why

The research note's "not verified" list starts with how a build's time splits
by stage; technique 3 (parallel pass-0) should not be judged without that.
June's run 4 gave a rough split (pass-0 22.7 min sequential, pass-1 12.1,
commit classification 5.6, audit 3.3, ~51 min in all) on an older model and
before the slash-id fix, so nothing current exists.

## What is built

All in `evals/harness/`; every default leaves today's behaviour unchanged.

1. **Stage timings.** `run_chapter_test_v2.py` already times pass-0, pass-1,
   escape repair, commit and audit. Add the battery, and split commit into
   its parts (seed, replay, `classify_all`, identity promotion, truth scan)
   via a `timings` dict that `Pipeline.commit` fills. Per-segment pass-0 call
   times too. Written to `timings.json` in the run directory.
2. **Parallel pass-0.** `Pipeline.pass0(segments=..., parallel=False)`. With
   `parallel=True`, each segment is established on its own (no prior) on the
   pipeline's worker pool, and the segment registries are reduced in segment
   order with `WorldRegistry.merge` (same id, one card). No model-judged
   merges in the reduce: that is R25's verified gate, which waits on g3bf5da.
   The engine's own reconcile still runs at commit, as it does today.
3. **Gleaning (optional).** `glean=False`. With it on, after a segment's
   registry is made, one more call shows the model that segment and its
   registry and asks only for missed `E|` lines, merged in.
4. **Runner options.** `run_chapter_test_v2.py` takes `--out`,
   `--pass0 sequential|parallel` and `--glean`; the run directory name is no
   longer hard-coded to run4. The R23 grader (raw and seeded) and the R24
   alias index run on each run's registry.

## The runs (at most 4)

All with the eval shim's default model (`claude-sonnet-4-6`, as R23), under
`evals/results/2026-10-10-r26-build-timings/`:

1. **seq**: full chapter test, sequential pass-0 (today's default). Gives the
   current split per stage and the first chapter-test score since the id fix.
2. **par1**, 3. **par2**: full chapter test, parallel pass-0.
4. **par-glean**: parallel pass-0 with gleaning. Measured, not graded
   against the pass mark. Run only if 1 to 3 finished cleanly; if one of them
   failed for a reason outside the pipeline (shim timeout storm, quota), the
   fourth run repeats it instead.

## Pass mark (written before any run)

Parallel pass-0 passes when **both** par1 and par2 meet all of:

- **Time:** pass-0 wall time at most **60%** of the sequential reference, the
  mean of R23's two pass-0 runs and seq's pass-0 (R23: 1479 s and 1780 s).
- **Quality, raw registry:** B3 F1 at least **0.715** (R23's lower run,
  0.735, less the 0.02 noise floor).
- **Quality, seeded (identity as the engine leaves it):** B3 F1 at least
  **0.710** (R23's lower seeded run, 0.730, less 0.02), and no fused gold
  pair beyond the one R23 already shows (Records Vault / Seed Vault).

The chapter-test battery score is reported for every run, but it is not part
of the pass mark: one sequential run gives it no noise floor.

Stage timings pass when `timings.json` exists for every completed run with
each stage above, and the report names the slowest stage.

## Done means

1. The code above, with unit tests on stub models (the parallel reduce,
   gleaning's merge, the commit timings, defaults unchanged); full suite
   green.
2. Up to 4 runs, each with `timings.json`, registry, raw and seeded
   scorecards, alias index, battery scorecard and meta.
3. `REPORT.md`: the split per stage, the pass mark verdict with the numbers,
   gleaning's effect, and what to do next.
4. Then stop and report (n7df1c6). ROADMAP R26 updated by pb.

Not in scope: engine changes, R25's merge gate, any change to pass-1.
