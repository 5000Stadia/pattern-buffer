# R26: where a build's time goes, and parallel pass-0 (2026-10-10)

Spec: `specs/BUILD-TIMINGS-V1.md` (pass mark written before any run). Model:
`claude-sonnet-4-6` via the eval shim, as R23. Four runs, the monitor's cap
(n7df1c6); engine untouched.

## The runs

| run | pass-0 | outcome |
|---|---|---|
| seq | sequential | complete: 1,921 s, battery 20/33 |
| par1 | parallel, 300 s shim cap | failed in pass-0: all four parallel chapter calls hit the shim's 300 s cap (sequential calls take 175 to 282 s; four at once run slower). Counted as a run |
| par1b | parallel, 900 s cap | pass-0 complete (449 s), then crashed: the reduced registry aliased `holds`, which the engine refuses. Harness fixed (`3d99d11`: a refused alias is skipped) |
| par2b | parallel, 900 s cap, fix in | pass-0 complete (517 s); pass-1 chunk 8 failed its reject-rate check (21 rejects), so the runner stopped before commit, by design |

Two partial starts (par2 at the 300 s cap, par2b before the fix) were stopped
by pb inside pass-0 and are not counted. Gleaning was not run: the fourth run
went to repeating the parallel measurement.

## Where the time goes (seq, the one complete run)

| stage | seconds | share |
|---|---|---|
| pass-0 (4 chapter calls, in series: 210, 282, 215, 176) | 884 | 46% |
| pass-1 (11 chunks, 4 workers) | 564 | 29% |
| commit: classification (`classify_all`, model calls) | 256 | 13% |
| audit (one model call) | 201 | 10% |
| commit: seed, replay, promotion, truth scan | 5 | <1% |
| battery | 12 | <1% |
| **total** | **1,921 (32 min)** | |

Everything but the model calls is negligible: the engine's own work (seed,
replay, reconcile, truth scan, battery) is under 20 s. Pass-0 is the slowest
stage and the only serial one.

## Pass mark

Sequential reference: the mean of R23's two pass-0 runs and seq's, (1,479 +
1,780 + 884) / 3 = 1,381 s; 60% of it is 829 s.

| | par1b | par2b | mark | |
|---|---|---|---|---|
| pass-0 wall time | 449 s (33%) | 517 s (37%) | at most 829 s | met |
| raw B3 F1 | 0.832 | 0.796 | at least 0.715 | met |
| seeded B3 F1 | 0.826 | 0.791 | at least 0.710 | met |
| fused gold pairs, seeded | vault pair only | vault pair only | none beyond R23's vault pair | met |

**By the letter, parallel pass-0 passes.** But the pass mark measured the
wrong thing for this change, and the numbers it did not include say not to
adopt it alone:

| | seq | par1b | par2b |
|---|---|---|---|
| registry ids | 98 | 159 | 167 |
| fragmented gold entities, raw | 0 | 13 | 13 |
| fragmented gold entities, seeded | 0 | 4 | 7 |
| attribute canonicals | 28 | 59 | 63 |
| timeline anchors | 9 | 24 | 29 |
| pass-1 | all chunks ok | (crashed before) | chunk 8 failed (reject rate) |

- **Why F1 rose while identity got worse.** Independent chapters list more
  names, so more gold mentions resolve (recall up). The grader's B3 links two
  mentions when they share *any* id, so a gold entity split across two ids
  still scores as linked when its names appear on both. Fragmentation is
  visible only in the fragmentation count, which the pass mark left out. In
  seeded form, Ilsa Renn, her desk, the Wellhead, the memory core, the false
  drawer, Tovan's letter and the aquifer maps each end as two or more ids.
- **Attribute canonicals double.** Each chapter coins its own names for the
  same quantity; nothing reconciles them, so fold keys fragment (the hazard
  CLAUDE.md names: `in` vs `inside` vs `located_in`).
- **Timelines disagree.** Each chapter picks its own day 0 (par1b's origin is
  Sela's visit, par2b's the night the meter went dark), and the reduce keeps
  chapter 1's origin with every other chapter's anchors on their own scales.
- **Pass-1 got slower and failed once.** par2b's pass-1 took 773 s against
  seq's 564 s, and chunk 8 failed its reject check. One run cannot pin the
  cause, but a registry of 167 ids with 26 ambiguous strings (alias index) is
  the obvious suspect.
- The battery could not be scored for any parallel run, so the end-to-end
  effect is unmeasured.

## What to do next

1. **Keep `parallel=False` the default.** Parallel pass-0 saves about 6 to 7
   minutes of a 32-minute build, but it hands pass-1 a fragmented registry.
   This matches the research note's order: land the alias pass (R24) and the
   verified merge gate (R25) first, because parallel mapping raises
   fragmentation. R24 Part B and R25 wait on g3bf5da.
2. **Grade fragmentation in the pass mark.** The next pass-0 change should be
   judged on the seeded fragmentation count (and a split-penalizing score)
   alongside F1. A one-line change to the pass mark, not to the grader.
3. **The other half of the time is model calls after pass-0.** Classification
   at commit (4.3 min) and the audit (3.4 min) are each one stage of serial
   calls; they are cheaper targets than pass-0 and touch no identity.
4. **Harness timeouts.** The shim's 300 s cap is too short for four
   concurrent chapter calls. `PB_EVAL_TIMEOUT=900` worked; any parallel run
   needs it.

## Files

`seq/`, `par1b/`, `par2b/`: `timings.json` (par1b's pass-0 time is from its
log), `registry_pass0.json`, raw and seeded registry scorecards, alias index,
and for seq the battery `scorecard.*` and `meta.json`. `par1/` holds only its
log line in this report. World files, dumps and staging are not committed.
