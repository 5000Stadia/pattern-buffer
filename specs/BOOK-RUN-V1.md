# BOOK-RUN-V1: build any book and grade it against its answer key (roadmap R27)

**Status:** r2.2 (2026-10-13). An entity is judged on its graded fields only (kind and aliases). A reader may re-judge an entity on those fields in `entities_fields`, which stands in for the whole-entry verdict (§1.2, marked *(r2.2)*). This came from the novella's gold build: four entities, Vey among them, were dropped for a `first_chapter` objection, a field the grader never reads. r2.1 answers pbr's r2 RED (m on b9b20a44): it defines the book normalizer exactly, gives each run a fresh usage log, and adds a head read when no row is timed (marked *(r2.1)*). r2 answers pbr's r1 RED (m on 19ea6444): the key and verdict schemas, stable item ids, the terminal marker, the gold file's shape, receipt deltas and the ordering of timeless rows are now defined (marked *(r2)*). r1 was for pbr's spec review. Author: pb.
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

### 1.1 `key.json` *(r2)*

The writer's format, as the novella's key has it:

```json
{"title": "…",
 "chapters": [{"n": 1, "file": "ch01.md", "words": 2127}],
 "entities": {"<key_id>": {"kind": "person|place|object|group",
                           "aliases": ["…"], "first_chapter": 1}},
 "same_as":   [["<key_id>", "<pre-reveal alias>", <reveal chapter>]],
 "not_same":  [["<key_id>", "<key_id>", "<why>"]],
 "locations": [{"entity": "<key_id>", "in": "<key_id>", "from_chapter": 1,
                "to_chapter": <int or null>, "evidence": "…"}],
 "holdings":  [{"entity": "<key_id>", "held_by": "<key_id>", "from_chapter": 1,
                "to_chapter": <int or null>, "evidence": "…"}],
 "containers": [{"container": "<key_id>", "contents": ["<key_id>"],
                 "revealed_chapter": 3, "evidence": "…"}],
 "knowledge": […], "false_beliefs": […], "corrections": […],
 "do_not_grade": […]}
```

- **Key ids** are the `entities` keys. Every id-valued field (`entity`, `in`, `held_by`,
  `container`, `contents`, and the ids in `same_as` and `not_same`) must name one of them, or the
  gold builder refuses the key.
- **Item ids.** An item outside `entities` is identified as `<section>[<index>]`, its position in
  `key.json` (for example `locations[12]`). An entity is identified as `entities.<key_id>`.
  `key.json` is never edited after the readers have seen it. A later edit is a new key with a new
  hash, and it needs new verdicts.
- **`to_chapter: null` means through the end of the book.** It is the terminal marker that §3.4's
  `final` uses.
- *(r2.1)* `aliases` and the world's `name`/`alias` strings are both matched by
  `book_normalize(s) = grade_registry.normalize(fold_quotes(s))`. `fold_quotes` maps ’ and ‘ to
  `'` and “ and ” to `"`, and changes nothing else. `grade_registry.normalize` stays as it is:
  lowercase, collapse whitespace, trim, drop one leading article. So "The woman with the copper
  hand" and "the woman with the copper hand" both become "woman with the copper hand", and
  "Or’s spoon" matches "Or's spoon". `grade_registry.grade` is called with both sides already
  folded by `fold_quotes`, so its own `normalize` produces the same keys.

### 1.2 The readers' verdict files *(r2)*

```json
{"key_sha256": "<sha256 of key.json's bytes>",
 "reader": "<label>",
 "entities": {"<key_id>": {"verdict": "ok|wrong|unclear", "note": "", "bad_aliases": []}},
 "same_as": [{"i": 0, "verdict": "ok|wrong|unclear", "note": ""}],
 "not_same": […], "locations": […], "holdings": […], "containers": […],
 "knowledge": […], "false_beliefs": […], "corrections": […],
 "missing": ["…"], "text_contradictions": ["…"]}
```

- `ok` means the text confirms the entry. `wrong` means the text contradicts it. `unclear` means a
  careful reader cannot settle it.
- `bad_aliases` lists aliases of an otherwise-ok entity that also name something else, or nothing.
- *(r2.2)* An entity is graded by its `kind` and `aliases` alone. `first_chapter` is never graded.
  A reader may add `"entities_fields": {"<key_id>": {"verdict", "note", "bad_aliases"}}`, which
  re-judges that entity on kind and aliases only. When present, it is that reader's verdict for the
  entity, both for keeping or dropping it and for its `bad_aliases`. Its whole-entry verdict stays
  in the file, unchanged, for the record. An `entities_fields` key that names no entity, or an
  entry with no valid verdict, is refused.
- `i` is the item's index in that section of `key.json`.
- A verdict file whose `key_sha256` is not the hash of the `key.json` beside it is refused.
  Readers are pointed at a frozen copy of the key and write no hash. pb stamps each file with the
  hash of that frozen copy, which is the file committed as `key.json`, and the README records the
  hash.
- A verdict file that misses any item, or gives one twice, is refused.

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
  each stage. *(r2)* A stage's receipt is the difference between the snapshot after it and the
  snapshot before it, field by field: calls, `calls_without_usage`, the four token counts and
  `cost_usd`. Its `cost_known` is False if any call in that stage left the price unknown (the
  ledger's `cost_known` is cumulative, so a stage's flag is computed from the per-call log,
  `usage.jsonl`). The total is the final snapshot.
  *(r2.1)* The log must hold only this run. Before the build, the runner moves any existing
  `DIR/usage.jsonl` to `DIR/usage.jsonl.<n>` (the next free n) and starts an empty one. Each
  stage's flag reads only the lines that stage appended: the runner records the line count before
  and after the stage and slices between them. `receipt.json` holds wall-clock seconds per stage plus calls, tokens in, out and
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
   `carried_by`, `worn_by`) in canon, mapped to key entities and collapsed the same way. *(r2)* The
   rows are ordered by `(timed, valid_from, assertion order)`, so timeless rows come first, then
   timed rows by valid time, and ties fall to the order they were asserted. The expected sequence
   is ordered by `(from_chapter, section, index)`, where `locations` sorts before `holdings`.
   A world value that maps to no key entity is kept as an unmatched element: it lowers the score
   only through the LCS, and is listed. The score per object is the longest common subsequence
   divided by the expected length. Also reported:
   - **final:** for each object whose last expected entry has `to_chapter: null`, does the
     world's folded containment at the end (`state(e, "in")`, as of the greatest valid time in the
     log; the engine folds the whole containment family under `in`) resolve to that entry's
     container or holder? *(r2.1)* If no canon row in the log has a `valid_from`, the read is the
     head read, `state(e, "in")` with no `as_of`. An object whose last entry ends before the book does is not scored
     here.
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
(`evals/harness/book_gold.py`) that is committed with its inputs. Its output *(r2)*:

```json
{"key_sha256": "…", "readers": ["A", "B"],
 "entities": {"<key_id>": {"kind": "…", "aliases": ["…"]}},
 "same_as": [{"id": "same_as[0]", "entity": "…", "alias": "…", "chapter": 8}],
 "not_same": [{"id": "not_same[0]", "a": "…", "b": "…"}],
 "moves": {"<key_id>": [{"id": "locations[3]", "to": "<key_id>", "from_chapter": 1,
                         "to_chapter": null}]},
 "containers": [{"id": "containers[0]", "container": "…", "contents": ["…"]}],
 "dropped": [{"id": "locations[7]", "verdicts": {"A": "wrong", "B": "ok"},
              "notes": {"A": "…", "B": ""}}],
 "dropped_aliases": [{"entity": "…", "alias": "…", "by": ["B"]}],
 "ungraded_counts": {"knowledge": 28, "false_beliefs": 13, "corrections": 10}}
```

- Lists are in key order, and `dropped` is sorted by id. The JSON is written with sorted keys, so
  the same inputs give the same bytes.
- An item whose entity was dropped is dropped with it. Its `dropped` entry says
  `"verdicts": {"entity": "dropped"}`.
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
