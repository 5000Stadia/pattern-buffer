# BOOK-RUN-V1: build any book and grade it against its answer key (roadmap R27)

**Status:** r1 (2026-10-13), for pbr's spec review. Author: pb.
**Source:** R27 as Kabe revised it on 2026-10-13: "Make chatgpt write the fiction so its
anonymous and original - tell it to try to make something out there and original." The test book
is a new novella written by ChatGPT, *The Weather That Would Not Leave* (12 chapters, about 25,300
words), with a hidden answer key (`key.json`). Two independent readers checked the key against the
text, and only entries both confirm are graded (the monitor's exit rule, note n0a0c92). The builds
themselves wait on Kabe's gate g10c3af; this spec only prepares them.
**Builds on:** INGEST-V2 (`Pipeline`: pass-0, pass-1, escape repair, commit, audit), R24 Part B
and R25 (finalization and the merge gate), PASS0-GRADER-V1 (`grade_registry.grade`), the token
receipts (`usage_ledger`).

## Need

The only build runner, `run_chapter_test_v2.py`, is tied to *The Last Honest Meter*: its story
path, hand-set chapter days and fixture battery. R27 needs:
1. a runner that takes **any book directory** (`ch01.md` … `chNN.md`) and builds it with the same
   pipeline, writing a time and cost receipt;
2. a grader that scores the built world against **that book's answer key**, with no model call.

## 1. The book directory

```
evals/books/<slug>/
  ch01.md … chNN.md     the text, each starting "# Chapter N: <title>"
  key.json              the answer key (format below), never read by the build
  graded.json           the entries both readers confirmed (see §4); the grader reads only this
  README.md             provenance: who wrote it, the brief, the revisions, the readers' verdicts
```

- The build reads only the chapter files, never `key.json` or `graded.json`. The runner refuses a
  chapter file that contains a key marker (`"same_as"`, `"not_same"`, `answer key`), the same
  guard as `BIBLE_MARKERS`.

## 2. The runner: `evals/harness/run_book.py`

```
PYTHONPATH=src python evals/harness/run_book.py --book evals/books/<slug> --out DIR
    [--pass0 sequential|parallel] [--merge-gate] [--glean] [--dry-run]
```

- **Segments and chunks.** One pass-0 segment per chapter. Pass-1 chunks are scenes, split on
  blank-line-separated `* * *` or `---` lines when a chapter has them, and otherwise into
  paragraphs grouped to about 1,200 words. Each chunk's cursor is its chapter number. The
  pipeline's own timeline (pass-0's `O|` origin and anchors) is unchanged: the runner adds no time
  convention to the prompts.
- **The build** is exactly `run_chapter_test_v2`'s sequence: pass-0, registry reports, pass-1,
  escape repair, commit (`finalize_identity`, plus the merge gate when `--merge-gate` is given),
  audit. There is no battery, because the grader replaces it.
- **The receipt.** `usage_ledger.reset()` runs before the build, and the snapshot is taken after
  each stage. `receipt.json` holds wall-clock seconds per stage plus calls, tokens in, out and
  cached, and cost (with `cost_known`), per stage and in total. `PB_EVAL_USAGE_LOG` is set to
  `DIR/usage.jsonl`.
- **`--dry-run`** reads the book and prints the segment and chunk counts, with a token estimate
  scaled from R26's measured build. It imports no model.
- Like R26's runner, it rewrites `timings.json` and `receipt.json` as each stage finishes, so a
  failed run keeps what it spent.

## 3. The grader: `evals/harness/grade_book.py` (deterministic, no model)

`grade_book(world, registry, graded) -> dict`, written as `book_scorecard.json` and `.md`.

**Mapping key entities to world ids.** A key entity maps to the closure that its aliases resolve to
through the world's canon `name`/`alias` rows (the same mention rule as `grade_registry`).
- If its aliases land in more than one closure, it is **split**, and every one of those closures
  counts as it.
- If none land, it is **missing**.
- A closure reached by aliases of two key entities is **fused**.

**Measures:**
1. **Identity:** B³ precision, recall and F1, plus split, fused and missing, by
   `grade_registry.grade` with `gold = {key: aliases}`, over persons, places and objects.
2. **Reveals (`same_as`):** for each pair, are the pre-reveal alias and the entity in one closure
   at the end?
3. **Look-alikes (`not_same`):** for each pair, are the two kept apart (different closures)? A
   merged pair is a fusion and is listed by name.
4. **Where things are, as order, not dates.** The model's story-day numbering is its own, so a
   chapter number cannot be compared with a valid time. For each object or person the key moves
   (`locations` and `holdings` together, ordered by `from_chapter`), the expected sequence is its
   containers or holders: the key's `in` or `held_by` values, with consecutive repeats collapsed.
   The world's sequence is the object's containment-family rows (`in`, `within`, `held_by`,
   `carried_by`, `worn_by`) in canon, ordered by valid time and then by assertion order, mapped to
   key entities and collapsed the same way. The score per object is the longest common subsequence
   divided by the expected length. Also reported:
   - **final:** does the world's state at the end (`state(e, "in")` as of the last valid time in
     the log) match the key's last entry, when that entry runs to the end of the book?
   - **ever:** the share of expected containers that appear anywhere in the world's sequence.
5. **Containers:** for each revealed container, the share of its listed contents that the world
   ever places in it (`in` or `within` the container, by closure).
6. **Not graded in V1:** `knowledge`, `false_beliefs` and `corrections`. They are natural-language
   statements, and grading them needs a judge model. They are listed in the scorecard as counts
   only. A judged pass is a separate, metered item, and comes to Kabe first.

Everything is computed over closures, so a merge the gate makes is credited or charged where it
lands.

## 4. Two readers, one gold (the monitor's exit rule)

`graded.json` is built from `key.json` and the two readers' final verdict files, by a small script
(`evals/harness/book_gold.py`) that is committed with its inputs:
- An entity is graded if both readers marked it `ok`. Aliases either reader listed in
  `bad_aliases` are dropped from it.
- A `same_as`, `not_same`, `locations`, `holdings` or `containers` item is graded if both readers
  marked it `ok`.
- Everything dropped is listed, with each reader's note, in `graded.json["dropped"]` and in the
  README. Nothing is silently lost.

## Tests (the build's acceptance; no model)

1. **The runner without a model.** `--dry-run` on the novella reports 12 segments and the chunk
   count, and imports no model. A scripted model (the existing test doubles) runs the whole
   sequence on a three-chapter toy book, and writes `receipt.json` with every stage present.
2. **The key guard.** A chapter that contains `"same_as"` is refused before any call.
3. **The grader on a hand-built world:**
   - a perfect world scores 1.0 everywhere;
   - a world that splits one person shows the split, and lowers that entity's recall;
   - a world that merges a `not_same` pair shows the fusion by name;
   - a world whose object goes A → B → A scores 1.0 against key A → B → A, and 2/3 against
     A → C → A;
   - day numbers that differ from chapter numbers do not change the order score.
4. **`book_gold.py`:** on toy verdicts, an entry one reader marked `wrong` is dropped and listed; a
   `bad_aliases` alias is dropped from the entity; the output is deterministic.
5. **Isolation:** the build never opens `key.json` or `graded.json`.

## Not in this spec

- Running anything metered. The builds wait on g10c3af.
- Judging knowledge, beliefs and corrections (above).
- Changing the pipeline's prompts or its timeline.
