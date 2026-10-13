# GRADE-LEAKS-V1: grading that sees the ending leak, false beliefs and points of view

**Status:** r1, for pbr review. Author: pb, 2026-10-13. Harness only (grader, keys, commit
bookkeeping); no engine change.
**Source:** consult c4bb1f2 point 3, accepted by Kabe on gate g936be9. Redesigned after round two
(ce0ba1f); see `docs/SPEED-PLAN-2026-10-13.md` step 2.
**Builds on:** BOOK-RUN-V1 (`grade_book.py`, `book_gold.py`, the key schema, two-reader gold),
BUILD-PROFILE-V1.

## Need

Every speed lever accepted on g936be9 adds foresight: parallel calls, a whole-book cast. Today's
grader can't see what foresight does:
- **Identity.** It reads identity through closures only. Canon identity is timeless, and rightly
  so: the hooded visitor *is* Mara at every time. A build that binds chapter 2's "hooded visitor"
  to Mara's id before the reveal scores the same as one that learns it at chapter 8.
- **Beliefs.** The key's `false_beliefs` (13 in R27's book), `corrections` (10) and `knowledge`
  (28) are never graded (`book_gold.py`). A build that writes "Mara Senn is dead", one character's
  belief until chapter 7, as canon loses nothing.

So a design that knows the ending, or one that swallows the book's deceptions, can score best.

## The shape

### 1. The commit records where each row came from
- `Pipeline.commit` records the log head before and after each chunk's items:
  `RUN_DIR/chunk_spans.json`, `{"chunks": [{"chunk": 7, "chapter": 4, "seq": [lo, hi]}]}`.
- A row's **source chunk** is the chunk whose span holds its `seq`. Seed and gate rows outside any
  span have none.
- Commit's behaviour is otherwise unchanged. This is bookkeeping only.

### 2. Keys gain structured forms, verified like every graded entry
- **The new fields:**
  - `alias_first_chapter` per entity: for each alias, the first chapter whose text uses it.
  - `as_fact` on every `false_beliefs`, `corrections` and `knowledge` entry that can be stated as
    one fact: `{"entity": "<key>", "attribute": "<plain attribute>", "value": "<key or literal>"}`.
    Corrections also get `corrected_as_fact`, the true fact after the correction.
  - An entry that can't be put as one fact gets `"as_fact": null`. It is listed in `dropped.md`,
    never guessed.
- **Who writes them:** the book's author, ChatGPT through the Codex CLI, as for the key itself.
- **Who verifies them:** both readers (BOOK-RUN-V1 §1.2), per field. Only a structured form both
  readers mark `ok` is graded. The others are listed in `dropped.md` with the readers' notes.
- **Attribute matching:** a key's plain attribute matches built rows through the world's
  `canonical_attribute`, the same normalization the build used. A world that spelled the
  attribute differently doesn't match. The report counts that as unmatched, never as a pass.

### 3. Three new grade sections (deterministic, no model calls, read-only copies)

**`leaks`: what was written before the text could know it.**
- **Alias leaks.** A `name` or `alias` row whose source chunk's chapter is earlier than that
  alias's `alias_first_chapter`.
- **Identity leaks.** For each `same_as` entry (key entity, the pre-reveal alias, reveal chapter),
  find the ids the built world gave that alias's mentions. A leak is any row from a source chunk
  earlier than the reveal chapter that is:
  - written on the revealed entity's own id (the id bound to its post-reveal names);
  - and about a subject the chunk could only know as the pre-reveal alias.

  "Could only know" is read from the key: the chunk's chapter has the pre-reveal alias in use, and
  none of the entity's other aliases have `alias_first_chapter` ≤ that chapter.
- **Reported:** per reveal, the leaking row count and the first leaking chapter, plus totals.
- **The target is zero,** with no tolerance. A leak is foresight, whatever it does to F1.

**`beliefs`: deceptions never become canon.**
- **A false belief** with a verified `as_fact` scores two checks:
  - canon never folds to the believed value as the winner at any valid time in
    `[from_chapter, end]` (checked at each chapter's time anchor);
  - the believer's `knows:` frame holds the belief at some time in
    `[from_chapter, corrected_chapter)`.
  - Two scores result: `false_in_canon` (the target is 0) and `held_by_believer` (a recall rate).
- **A correction** with verified forms: canon at the end folds to `corrected_as_fact`, and never
  to the stated claim after `corrected_chapter`.
- **Chapter to time:** the build's per-chunk valid time (the cursor each chunk was committed
  under), recorded in `chunk_spans.json` next to its chapter. "A chapter's time" is the latest
  cursor of its chunks.

**`point_of_view`: who knows what.**
- **A knowledge entry** with a verified `as_fact`: the learner's `knows:` frame holds the fact by
  the end (exact entity, matched attribute, value), and does not hold it at a time before the
  entry's chapter.
- **The score** is the share of verified entries held, with "learned too early" counted separately.

### 4. Reporting
- `grade_book.py` writes the three sections into its existing output, beside identity, reveals,
  look-alikes, order, final, ever and containers.
- The report states each section's entry count, verified count and dropped count.
- A run without `chunk_spans.json` (an older run) gets `leaks: "unmeasured"`, and the time-based
  checks are marked unmeasured. Nothing is inferred.
- The headline judging order (`docs/SPEED-PLAN-2026-10-13.md`):
  1. zero wrong merges across look-alike pairs;
  2. zero leaks;
  3. zero false beliefs in canon;
  4. then the existing scores;
  5. then time and cost.

## Not in this spec

- Any change to how a build extracts or what chunks see. That is step 4's time-sliced cast.
- Engine changes: canon identity stays timeless, and `aka` is not used by the grader.
- Writing the structured forms for the two books. That is the authoring pass below, run with
  Codex and two readers, as R27's key was.

## Authoring pass (follows this spec's GREEN)
1. **The practice book** (being written): Codex adds `alias_first_chapter` and `as_fact` fields to
   its key. Two readers verify.
2. **R27's book:** the same pass on `the-weather-that-would-not-leave/key.json`. Its verified
   gold changes only by additions; existing graded entries are untouched.

## Tests (no model calls)

1. **chunk_spans:** a fake-model toy build writes spans covering every chunk row, in order,
   each with its chapter and cursor. Seed rows fall outside every span.
2. **Alias leak:** a hand-built world where a chapter-1 chunk writes `alias "the duke"` (first
   chapter 3) is flagged with chapter 1; the same row from a chapter-3 chunk is not.
3. **Identity leak:**
   - a reveal at chapter 4, where a chapter-2 chunk's row about "the hooded visitor" is written on
     Mara's id: one leak;
   - the same world with that row on a separate visitor id, merged at the end: no leak, and
     identity B³ is unchanged.
4. **False belief:**
   - canon folding to "Mara Senn is dead" is `false_in_canon = 1`;
   - the belief only in `knows:person:oruva`, between from and corrected, is
     `false_in_canon = 0, held_by_believer = 1`.
5. **Correction:** canon ending at the corrected value passes; canon still at the claim after
   `corrected_chapter` fails.
6. **Point of view:** a fact in the learner's frame from their chapter on counts as held; one
   present before that chapter counts as too early.
7. **Unverified and null:** a structured form that only one reader marked `ok`, or an `as_fact` of
   null, is not graded and is listed as dropped.
8. **Old runs:** grading the stored R25 and R26 runs (no spans) writes `leaks: "unmeasured"` and
   the existing sections unchanged.
9. **Byte-stable existing sections:** for R27's key and a hand-built world, every existing section
   is byte-identical before and after this change.
10. Full suite green.
