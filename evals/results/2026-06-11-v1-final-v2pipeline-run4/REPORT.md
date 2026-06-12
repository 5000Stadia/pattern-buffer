# Milestone report: run 4, the anchor stamp, and four fold refinements

**For:** the founder and Kernos CC. Template: the adopted five-part shape +
the predicted-vs-actual section (letter 015). Seed v1-final; run of
2026-06-11/12 overnight under the founder's full-green grant.

## 1. The claim and the test

Queue items 1–3 (pass-0 compaction + spatial completeness, duplicate-only
audit) claimed they would raise the score and tame the pipeline's fat. Run 4
is their measurement — same seed, same battery, same grader; and per
decision C, its corrected output becomes the shipped `examples/anchor/`.

## 2. The number and its anatomy

| | Run 1 | Run 2 | Run 3 | **Run 4** |
|---|---|---|---|---|
| Score | 21/33 | 17/33 | 21/33 | **22/33** |
| Confirmed engine findings | 1 | 0 | 1 | **4** |
| Registry | n/a | n/a | 58 entities | **108 entities** |
| Grammar rejects | n/a | n/a | 0 | **0** |
| Destructive audit retracts | n/a | n/a | 16 | **0** |

22/33 is the new best, with the failures all extraction-class after dump
audit (Q26's "shape" label re-adjudicated: the engine resolved correctly
over registry content that lacked the shared alias — registry variance).
New passes vs run 3 include feature 9 (the dead-elevator non-connection —
the spatial rules worked) and feature 8 under the simultaneity guard.

**The run's real yield was engine truth.** Four fold refinements, each
found because denser extraction exercised a seam no synthetic test had:

1. **Namespace completion at parse** — frame ids emitted without namespace
   (`knows:narrator`) complete deterministically iff exactly one registry
   id matches the suffix; ambiguity stays an orphan. (Found by the commit
   refusal — which itself proved stage-all/commit-once: nothing landed,
   repair was a clean replay.)
2. **Simultaneity guard** — within-class supersession requires world-time
   progression; rows tied at the same valid_from with different values are
   a flagged contradiction, never silently ordered by log sequence. (Found
   because run 4's classifier marked the reactor rows STATE where run 3
   said CONSTITUTIVE — classification variance must not decide truth.)
3. **Set-valued attributes** — names, aliases, edges are multiplicity, not
   dispute; conflict detection applies to functional keys only. (62 of 77
   raw conflict flags were this misreading.)
4. **Direct-class merge** — `stated` and `observed` without document chains
   are one supersession class; the §7.1 boundary is document-vs-direct.
   (Ordinary narrative movement was false-flagging as cross-source dispute.)

All four: test added, spec amended, same session. The conflict census after
them: **8 honest open flags** — the planted reactor contradiction, the
cigarette-tin same-instant tie (the false-positive class the simultaneity
guard's spec note predicted, shipping visibly), and document-claim
disagreements.

## 3. Predicted vs actual (the 015 standing section)

| Prediction (stated before run 4) | Actual | Verdict |
|---|---|---|
| Score > 21 | 22 | **HIT** |
| Zero destructive audit retracts | 0 retracts (4 adds, 0 dropped) | **HIT** |
| Total wall < 25 min | ~51 min compute (+ one crash/restart) | **MISS** |
| Escapes < run 3's 15 | 18 raw — but 10 repaired deterministically | MISS/soft |

The wall-clock miss decomposes honestly: pass-0's 4-segment chain is
sequential by design (22.7 min — compaction killed the timeouts, not the
CLI's per-call floor); commit-time classification batches (5.6 min) and the
audit call (3.3 min) ride the same floor. The architecture's parallel half
(pass-1: 12.1 min, zero rejects) keeps its promise; every remaining minute
is CLI-shim overhead — the SDK-shim queue item is now the single biggest
lever on both wall clock and the max-turns failure class that crashed the
first attempt.

## 4. The demonstrable moment — now shipping

`examples/anchor/` is stamped (decision C): the bible-verified run-4 dump,
the classification cache, the pass-0 registry, a zero-key builder, and the
tour. A stranger with no API key runs two commands and gets:

```
core @ day 2          -> obj:ilsa_renn_desk_false_drawer
core @ the assembly   -> obj:steel_document_case   (in the Seed Vault)
core @ post-tribunal  -> the unified archive
footlocker 0447       -> no contents assertion exists, in any frame
reactors              -> OPEN FLAG: values [2, 3], both alive, nobody "fixed" it
```

Bible-verification corrections were applied through the write paths and are
visible in the log by design (a merge event, a case-level e41 move, one
retraction of an over-eager correction — the correction history is part of
the demo).

## 5. What this does not show, and what's next

- **The score's remaining ceiling is pass-0 consistency**, not architecture:
  identity still fragments at the registry level (two ids for the clerk,
  pass-0 run-to-run variance in aliases/kinds). Two candidate mechanics for
  the next cycle: a registry self-check pass (dedupe candidates by
  name/alias overlap → maybe_same_as), and an `M|a|b` identity line in the
  grammar so extraction can propose merges the registry missed.
- **Queue (standing):** micro-eval with the letter-018 refer() extensions
  (task #12) → 008 porcelain → SDK shim. Letter 018's synonym criterion is
  planted in the micro-eval design.
- **Conflict census shipped** (the run-3 "38 conflicts" item closes): the
  composition was 80% set-valued misreads, now structurally exempt; the
  remainder ships as the live demo.

**What changed in the canonical docs because of this milestone:**
SPIKE-V1 §7 gained the simultaneity guard, set-valued exemption, and
direct-class merge; the engine gained all four refinements with tests
(101 green); examples/anchor/ became real; INGEST-V2's audit §5.2 carries
duplicate-only retracts; the grammar spec carries namespace completion.

*Raw run artifacts (dumps, staging, binaries, scorecard.json) for runs 1–4
are preserved in git history at commit `2734ea2`; the working tree carries
reports and scorecards only (letter 017).*
