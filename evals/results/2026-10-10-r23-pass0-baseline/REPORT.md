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
- **Id-format bug in the fresh runs (not harmless; fixed after this
  baseline).** Ids came out as `person:/ilsa_renn` where the older registry has
  `person:ilsa_renn`, because the pass-0 prompt listed the namespaces as
  "person:/place:/obj:/...". The grader ignores id spelling, but the engine
  does not: its id grammar refuses every such id, so seeding a fresh registry
  skips every row, and the chapter test could not have built a world with
  today's model. Fixed on `fix/pass0-id-shape`: the prompt now gives
  `person:ilsa_renn` as the shape, and the registry parser repairs a slash
  after the namespace. The numbers above are unchanged by the fix (the grader
  never read the id).
- **The split happens despite the prompt asking for the opposite.** Pass-0's
  rules say "someone unnamed early who is named later is ONE entry", and the
  clerk's id lists `ilsa renn` as an alias, yet a second id is minted. The
  engine's own reconcile closes it downstream (next section).

## After seeding: identity as the engine leaves it

The registry is not the last word on identity: the commit seeds it into the
world, and the engine's promotion and `reconcile` merge ids that share names.
`grade_registry.seeded_registry()` does exactly that on a scratch world (stub
model, no pass-1, ids repaired) and folds each merged group into one card.
Scorecards: `*/scorecard_seeded.md`.

| metric | run1 | run2 | older |
|---|---|---|---|
| ids after merges | 92 | 88 | 106 |
| fragmented gold entities | **0** | **0** | **0** |
| fused ids | **1** | **1** | 0 |
| B3 precision | 0.984 | 0.984 | 1.000 |
| B3 recall | 0.602 | 0.581 | 0.567 |
| B3 F1 | 0.747 | 0.730 | 0.724 |

- **Reconcile closes the Ilsa split in all three.** The clerk and Ilsa Renn
  end as one id.
- **Reconcile fuses the Records Vault with the Seed Vault in both fresh runs.**
  This is the story's planted coarse-then-split container (bible feature 3).
  Both vault cards carry the alias "the vault", and a third card,
  `place:vault`, is named "the vault"; reconcile merges each vault into it,
  which chains the two vaults into one place. Nothing marks them distinct,
  and nothing vetoes a merge between two cards with different proper names.
  It is engine behaviour (identity, `reconcile`), the same class as the
  automatic merges that fused a protagonist with an NPC in construct's worlds,
  so it is evidence for gate g3bf5da's point P3 (identity's root causes,
  through pbr), not something R23 or R24 changes. The older registry had no
  `place:vault` card, so it escaped.
- So the identity number that matters for M3 is the seeded one, and its
  failure today is a fusion, not a fragmentation.
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
`older-examples-anchor/`: scorecards only. Each directory also has
`scorecard_seeded.md/.json`. Rerun:
`PYTHONPATH=src python evals/harness/run_pass0_baseline.py OUT_DIR`.
