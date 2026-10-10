# Proposal for Kabe: splitting `indexes.py` (roadmap R21)

**Status:** proposal, 2026-10-10. Nothing built. Your audit note asked that a
rewrite come back to you as a proposal with a recommendation; this is that.

## The problem

`src/patternbuffer/indexes.py` is every derived read in one file: 2,161 lines,
one class, 71 methods. The audit called it "five modules in one file"; tonight's
batches made it eight sections:

| Section | Lines (about) | What it does |
|---|---|---|
| helpers and wiring | 290 | caches, identity resolution, row access |
| fold | 680 | the current-value rule for every key (batch A's work) |
| walks | 55 | `locate`, `contents`, `path` |
| composition | 65 | `part_of` features |
| who-knows | 175 | `who_knows`, `frame_diff` |
| event records | 285 | R22's one event reader |
| neighborhood | 295 | the awareness read |
| traversability | 250 | `route` and its policies |

Five other modules reach into its private methods (8 places, e.g.
`_recency_key`, `_is_event_effect`). The size makes every review harder: each
audit batch touched the fold and something else in the same file, and the merge
conflicts tonight all fell there or in the whitepaper table.

## What I propose

Turn `indexes.py` into a package, `patternbuffer/indexes/`, one module per
section, with **`Indexes` kept as the one class every caller uses**:
`from patternbuffer.indexes import Indexes, FoldResult` keeps working, and no
porcelain verb, payload or host call changes.

- Each section becomes a mixin class in its own module (`fold.py`, `walks.py`,
  `events.py`, `knowledge.py`, `neighborhood.py`, `routes.py`), and `Indexes`
  inherits them all over a small core (`_core.py`: wiring, caches, helpers).
- The 8 private reach-ins become named, documented methods.
- **Behaviour unchanged, byte-identical.** The full suite passes before and
  after with no test edited, and reads on copies of construct's 52 worlds are
  compared call by call (the same harness that measured batches A to E).
  Because it is byte-identical it would not need a pbr behaviour review, but I
  would still send it to pbr for a structural read.

**Why mixins rather than separate objects:** the sections share caches and call
each other constantly (the fold is used by every other section). Mixins move the
code without changing a single call, so the split is mechanical and the diff
can be read as "moved". Separate objects with explicit interfaces are the
cleaner end state, but would rewrite every internal call. That can come later,
section by section, if it ever earns its cost.

## The rest of R21, for context

The audit's other structure items are smaller and independent of the split:
- one merge-veto table in `identity.py` instead of eight hand-written copies (a
  400-pair regression test already exists in the audit's notes);
- one "rows between two closures" scan instead of eight;
- one kind profile instead of five readers with three normalizations;
- one classifier rubric (this one needs a model eval run to show it doesn't
  change verdicts, so it costs usage).

## Recommendation and what I need from you

Build the split as above (about half a day of work plus the comparison run),
then the merge-veto table, then the other two scans. Leave the classifier rubric
until M3 needs it. M3's measurement work (R23) is underway meanwhile and doesn't
touch these files.

If you'd rather not restructure now, R21 can wait: nothing is broken, it only
makes the next changes slower to review.
