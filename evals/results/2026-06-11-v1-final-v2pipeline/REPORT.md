# Milestone report: INGEST-V2's first measured run (chapter-test run 3)

**For:** the founder and Kernos CC. Template: the adopted five-part shape.
Seed v1-final; run of 2026-06-11 evening; pipeline INGEST-V2 (registry-first)
per the GREEN spec, on the same fixtures as runs 1–2.

## 1. The claim and the test

Decision A predicted that pinning identity and vocabulary up front
(registry-first) would beat iterating extraction prompts, and that the
architecture was "the cheapest test of itself." Run 3 is that test: same
novella, same battery, same grader — the only change is the ingestion
pipeline (three rounds, parallel extraction, compact grammar, staged
commit, audit).

## 2. The number and its anatomy

| | Run 1 (serial, v1) | Run 2 (serial, v2 contract) | **Run 3 (INGEST-V2)** |
|---|---|---|---|
| Scorecard | 21/33 | 17/33 | **21/33** |
| Confirmed engine failures | 1 (fixed) | 0 | **1 (fixed)** |
| Grammar/format rejects | n/a | n/a | **0 across 11 chunks** |
| Q11 — the e25 canon probe | FAIL | FAIL | **PASS** |
| Extraction wall clock | 36–77 min | ~96 min | 66 min (10 min of it pass-1) |

Equal on points with run 1 — but not the same 21. What changed underneath:

- **The headline probe finally passes.** "Where was the core during the
  assembly?" — answered correctly **in canon**, through the two-axis fold,
  off rows the extractor filed at true historical time (false drawer day
  0–3 → seed vault day 3–8). Runs 1–2 never got this into canon at all.
  The registry + the line grammar's `f=` discipline fixed the filing; an
  engine refinement (below) let the fold serve it.
- **Identity fragmentation is gone as a failure class.** No duplicate
  clerk entities, no fragmented reactor keys (the conflict fired correctly,
  feature 8 PASS), letter/core quantities converged (Q30 PASS), zero
  grammar rejects. The things registry-first was designed to kill are dead.
- **The remaining 12 failures are all extraction-class and concentrated in
  one place: pass-0 registry quality.** Shallow containment (max depth 3),
  a wrong connects_to pair through the defunct dead elevator (feature 9
  FAIL — the text says that shaft was never recut), "the vault" alias
  pinned to only one vault (so `refer` legitimately resolved instead of
  going underdetermined), no drawer entities for the desk, official-story
  and conditional-event rows not extracted. K's rider was prophetic:
  pass-0 is the single point of failure, and it is now the *only* point of
  failure that matters.

**The engine finding (run 3's equivalent of the assumption quarantine):**
run 3's correct canon rows exposed that a *wrong earlier inference* (the
narrator's "filed next to the books" theory, `inferred`) held cross-source
incumbency against later `stated` truth. Fixed as **evidence rank at the
fold** — `{stated, observed}` > `generated` > `inferred` > `assumed`;
provisional classes never outhold authoritative ones; the conflict-flag
machinery applies between peers only. Test added, spec amended, re-graded:
that single refinement is what turned Q11/Q14's probes green. Run 1 found
the `assumed` case; run 3 found the `inferred` case; the rule is now fully
general.

## 3. What the test caught beyond the score

- **The pass-2 auditor is destructive as prompted.** Its 16 retracts
  included *correct* rows (Pell's age, Cray's construction credits, the
  Seed Vault's original purpose). "When in doubt, emit nothing" did not
  hold against an anomaly digest that lists drift candidates — the model
  treats listed anomalies as instructions to act. The conflict-protection
  guard worked (zero dropped-op violations); the *judgment* didn't.
- **Timing truth vs the §E.2 estimate.** Pass-1 — the parallelism +
  compact-grammar claim — validated hard: the whole novella extracted in
  **10 minutes flat with zero rejects** (vs 48–96 serial), individual
  chunks returning in as little as 8 seconds. But total wall was 66 min,
  not 4–5: pass-0 took 29 min (two 600s timeouts before landing — its
  verbose JSON registry output is exactly the fat the line grammar removed
  from pass-1), and escape repair took 18 min (one extension call + 3
  re-extractions). The estimate was right about the architecture and wrong
  about the JSON rounds. Fix is known and mechanical: compact encodings
  for pass-0/extension output.
- **Registry escapes behaved as specified**: 15 orphans quarantined across
  4 chunks, zero entered the log, repair extended + re-extracted, commit
  refused nothing. K's first-class-failure-category design earned its keep
  on its first live run.

## 4. The demonstrable moment

```
core @ day 2.0 (canon) -> obj:false_drawer     (the four quiet days)
core @ day 4.5 (canon) -> place:seed_vault     (moved DURING the assembly —
                                                asserted three chapters later)
reactor conflict: OPEN FLAG, values [2, 3] both alive, nobody "fixed" it
footlocker 0447: no contents assertion exists, in any frame, ever
```

All four, milliseconds, zero model calls, prose deleted.

## 5. Future work (surfaced details, in dependency order)

1. **Pass-0/extension compaction** *(mechanical, high yield)*: registry
   and extension calls emit a compact line format like pass-1 (predicted
   to remove ~45 of the 66 minutes and most timeout exposure). Includes
   splitting pass-0 over chapter halves with `establish/extend` — already
   interface-supported.
2. **Pass-0 spatial completeness** *(the score lever)*: the registry
   prompt under-models space — needs explicit instructions for container
   hierarchies (rooms → furniture → compartments), non-traversable
   structures (the dead elevator), and shared aliases for split referents
   ("the vault" on both vaults). Most of the 12 remaining failures trace
   here; this is where the next points come from.
3. **Audit-pass redesign** *(needed before anchor.world stamps)*: retracts
   restricted to duplicates and orphan cleanup, never drift-list judgment;
   or pass-2 proposes and a human/instructor confirms. **Decision point:
   the run-3 dump is NOT stamped into examples/anchor/** — the destructive
   retracts disqualify it; the stamp waits for a verified pipeline run
   (scaffolding is committed and ready: builder + zero-key tour).
4. **The 38 open conflicts** need one classification pass (expected: mostly
   peer-class stated-vs-observed noise from the extractor's status choices;
   possibly another fold lesson hiding in them).
5. **Then the standing queue:** messy-dialogue micro-eval (gates tracking
   mode), 008 porcelain (gates the Kernos adapter), GitHub founding push
   (your token scope), SDK shim (cuts the CLI's per-call overhead everywhere).

**What changed in the canonical docs because of this milestone:**
SPIKE-V1 §7 — evidence rank at the fold (generalizing the assumption
quarantine); engine: `indexes._fold_state` + test; grader: two
hashable-value fixes; INGEST-V2 spec previously amended through its own
4-round review (raw_decode grammar rule, audit time policy).
