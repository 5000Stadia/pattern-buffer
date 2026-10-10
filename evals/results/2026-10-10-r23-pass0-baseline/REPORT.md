# R23 pass-0 registry baseline (2026-10-10)

Grader: `evals/harness/grade_registry.py` against the gold `fixtures.ENTITIES`
(**28** gold entities, 62 deduplicated mentions; the spec's first draft said
29, corrected to 28). Runner: `evals/harness/run_pass0_baseline.py` (pass-0 only: the
`run_chapter_test_v2.py` segmentation, 4 chapter segments, `Pipeline.pass0`,
`establish`/extend prompt unchanged, shim `claude_model`).

Model: `claude-sonnet-4-6` (the shim default, via the local `claude` CLI). No
quota or CLI errors; each run hit several 300 s shim timeouts that the shim's
own retry absorbed. Wall time: run1 1479 s (24.7 min), run2 1780 s (29.7 min).

## Numbers

| metric | run1 | run2 | run-to-run diff | older (examples/anchor) |
|---|---|---|---|---|
| registry ids | 95 | 91 | 4 | 109 |
| coverage (of 28) | 26 | 25 | 1 | 27 |
| fragmented gold entities | 1 | 1 | 0 | 1 |
| fused registry ids | 0 | 0 | 0 | 0 |
| mentions unresolved (of 62) | 25 | 28 | 3 | 27 |
| B3 precision | 1.000 | 1.000 | 0 | 1.000 |
| B3 recall | 0.602 | 0.581 | 0.022 | 0.567 |
| B3 F1 | 0.752 | 0.735 | **0.017** | 0.724 |

**Noise floor: about 0.02 on B3 recall / F1, plus or minus 1 on coverage and 3
on unresolved mentions.** Two runs only, so treat it as a lower bound on the
spread; a technique should move F1 by clearly more than ~0.02 (and ideally
repeat) before it counts as an improvement.

## What the numbers say in plain words

- **Fusion is zero in all three registries.** Pass-0 never merges two gold
  entities into one id; B3 precision is 1.0 everywhere.
- **Fragmentation is one entity, the same one every time: Ilsa Renn.** She is
  minted as `person:/ilsa_renn` and as `person:/tin_ear_clerk` ("the clerk");
  the clerk id even carries `ilsa renn` as an alias (and `ilsa` in run2), yet
  the two ids stay separate. The older registry has the same split
  (`person:ilsa_renn` / `person:tin_ear_clerk`). This is the audit's named
  failure, reproduced deterministically in three independent runs.
- **Most of the recall loss is not fragmentation but missing gold aliases.**
  The metric is string-bound: a mention counts only if some registry id lists
  that exact (normalized) string. Gold phrasings such as "tin of cigarettes",
  "crate of twelve empty sample vials", "settlement of anchor", "detective",
  "assembly hall" are absent from the registry in every run. Whole entities
  fall out intermittently: `figs` (run1, run2), `archive` (all three),
  `condenser_station` (run2 only; run1 reached it via `place:/condenser_facility`,
  which lists "the condenser station"). Read recall as "does the registry know
  the bible's names", a registry-vocabulary measure, not only identity merging.
- **Run-to-run:** the same gold entities are lost or kept differently
  (condenser_station, the `maps`/`footlocker` alias sets), which is where the
  noise comes from.
- **Id-format artifact in the fresh runs:** ids come out as `person:/ilsa_renn`
  (with a slash) where the older registry has `person:ilsa_renn`. Harmless to
  the grader (it ignores id spelling). Cause: the pass-0 prompt in
  `evals/harness/registry.py` writes the namespaces as a slash-separated list,
  "Ids namespaced person:/place:/obj:/...", and today's model reads `person:/`
  as the prefix. Every fresh id has the slash (95 of 95). Not fixed here: R23
  measures pass-0 as it is; the wording fix belongs with the first pass-0
  change, and its run gets graded against this baseline.
- **The split happens despite the prompt asking for the opposite.** Pass-0's
  rules say "someone unnamed early who is named later is ONE entry", and the
  clerk's id lists `ilsa renn` as an alias, yet a second id is minted. A
  deterministic fold of ids that share a full name (the research note's
  alias-index pass) would close this one without a model call.

## The older data point

`examples/anchor/registry.json` is the pass-0 artifact of the stamped run-4
world (`w:anchor_v2`, 109 entities, seed v1-final). It was committed in
`2734ea2` (2026-06-12, "anchor.world stamped (run 4, bible-verified)"); its
STAMP.json names it the run4 INGEST-V2 pass-0 artifact (compact pass-0,
ns-completion). The run4 REPORT describes pass-0 as a sequential 4-segment
chain (22.7 min), the same shape as the fresh runs; the model name is not
recorded there. It is a single run, graded read-only and unmodified, in
`older-examples-anchor/`. It falls inside the fresh runs' range on every
metric (F1 0.724 vs 0.735 / 0.752; the gap to run1 is 0.028, slightly above
the two-run floor).

## Files

`run1/`, `run2/`: `registry.json`, `scorecard.md`, `scorecard.json`, `meta.json`.
`older-examples-anchor/`: scorecard only. Rerun:
`PYTHONPATH=src python evals/harness/run_pass0_baseline.py OUT_DIR`.
