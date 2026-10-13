# GRADE-LEAKS-V1: grading that sees the ending leak, false beliefs and points of view

**Status:** r2.4 (pbr's code-review ruling: beliefs and point of view are graded on the narrative-exposure clock, by log position, never by inferred story time; field verdicts are validated exactly). r2.3 (pbr r2.2 RED: chunk classification uses a tokenizer that keeps articles, since `book_normalize` drops a leading article). r2.2 (pbr r2.1 RED: binding by log position, not chapter; `map(R) = E` required; the exact tokenizer and stoplist; every row's position counts). r2.1 (pbr r2 RED: an id's binding is judged by when it became identifiable as E, from provenance; alias matching is whole-token, and common-word aliases are kept out of chunk classification). r2 (pbr r1 RED: a decidable raw-id leak algorithm, exact structured-form and per-field verdict schemas, `never_learns`, inclusive spans, and the scope of the byte-stability test). For pbr review. Author: pb, 2026-10-13. Harness only (grader, keys, commit
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
- `run_book` passes the plan's `(chunk_id, chapter)` pairs into `Pipeline.commit`. Commit records,
  per chunk, the first and last `seq` it appended, **inclusive**, and the cursor it committed
  under:
  `RUN_DIR/chunk_spans.json`, `{"chunks": [{"chunk": 7, "chapter": 4, "cursor": 4.0, "seq": [lo, hi]}]}`.
  A chunk that appended nothing has `"seq": null`.
- A row's **source chunk** is the chunk whose inclusive span holds its `seq`. Seed rows, gate rows
  and audit rows outside every span have none.
- Commit's behaviour is otherwise unchanged. This is bookkeeping only.

### 2. Keys gain structured forms, verified like every graded entry
- **The new fields** *(r2: exact schemas)*:
  - `alias_first_chapter` on each entity: an object mapping each string of that entity's `aliases`,
    exactly as listed, to the first chapter whose text uses it (an int). Matching against built
    rows uses `book_normalize` on both sides.
  - **A fact form** is
    `{"entity": "<entity key>", "attribute": "<plain attribute>", "value": {"entity": "<entity key>"} | {"literal": <JSON scalar>}}`.
    Every key named must be an entity of the same key.
  - `false_beliefs[i].as_fact`: the believed, false fact.
  - `corrections[i].as_fact`: the claim as first stated. `corrections[i].corrected_as_fact`: the
    true fact, or `null` when the correction only negates the claim.
  - `knowledge[i].as_fact`, for `learns` and for `never_learns` entries alike: the fact learned,
    or the fact never learned.
  - An entry that can't be put as one fact gets `"as_fact": null`. It is listed in `dropped.md`,
    never guessed.
- **Frames.** A `who` key maps to built ids as identity does (§3 raw-id mapping), and the grader
  reads that being's knowledge with `frame_scope="merged"` on the `knows:` frame of the closure
  representative at the end of the run.
- **Who writes them:** the book's author, ChatGPT through the Codex CLI, as for the key itself.
- **Who verifies them:** both readers (BOOK-RUN-V1 §1.2), **per field** *(r2)*.
  - Each reader's verdict file gains, beside its entry-level verdicts:

    ```json
    "fields": {
      "alias_first_chapter": {"<entity key>": {"<alias>": "ok" | "wrong: <why>"}},
      "false_beliefs":  {"<index>": {"as_fact": "ok" | "wrong: <why>"}},
      "corrections":    {"<index>": {"as_fact": "…", "corrected_as_fact": "…"}},
      "knowledge":      {"<index>": {"as_fact": "…"}}
    }
    ```

  - *(r2.4, pbr)* **A field verdict is exactly `"ok"`, or `"wrong: "` followed by a non-empty
    reason.** Any other value (`"okay"`, `"wrong"`, `"unclear"`, `""`, a non-string) refuses the
    verdict file, naming the field, before anything is graded. It is never silently dropped.

  - Only a field that both readers mark `ok` is graded. `book_gold.py` writes the confirmed fields
    into `graded.json` as new sections `alias_first_chapter`, `beliefs`, `corrections` and
    `knowledge`. Every other field goes to `dropped.md`, with both readers' notes.
  - The existing entry-level gold is unchanged.
- **Attribute matching:** a key's plain attribute matches built rows through the world's
  `canonical_attribute`, the same normalization the build used. A world that spelled the
  attribute differently doesn't match. The report counts that as unmatched, never as a pass.

### 3. Three new grade sections (deterministic, no model calls, read-only copies)

**`leaks`: what was written before the text could know it.**
- **Alias leaks.** A `name` or `alias` row whose source chunk's chapter is earlier than that
  alias's `alias_first_chapter`.
- **Identity leaks** *(r2: a decidable algorithm)*. Identity is read **raw**: a row's `entity`
  exactly as written, never resolved through the final closure.
  1. **Raw names.** `names(R)` is the set of `book_normalize`d values of raw id R's own canon
     `name` and `alias` rows.
  2. **Raw mapping.** `map(R)` is key entity E when every name in `names(R)` that matches any
     graded key alias matches one of E's, and at least one does. If the names match two or more
     key entities, R is **ambiguous**. If they match none, R is **unmapped**. Ambiguous and
     unmapped ids are never charged; their rows are counted in the report.
  3. **Pre-reveal chunks.** For a `same_as` entry (E, pre-alias P, reveal chapter r), chunk c is
     *pre-reveal for it* when:
     - c's chapter is earlier than r;
     - c's text contains P;
     - c's text contains no other graded alias of E.

     *(r2.2, exact)* **"Contains" is a whole-token match.**
     - **Tokenizer** *(r2.3)*:
       `tokens(x) = re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)*", fold_quotes(x).lower())`.
       It applies quote folding and lowercase, and **no article stripping**, so
       `tokens("The One") == ["the", "one"]`. `book_normalize`, which drops one leading article,
       stays the matcher for raw-name mapping (§3.1–3.2) and nowhere else.
     - An alias is contained when its token list occurs as a contiguous run in the chunk's token
       list.
     - **Common-word aliases** take no part in chunk classification:
       - an alias with exactly one token of three characters or fewer (R27's `Or`);
       - an alias with exactly one token in this stoplist, which is normative and complete: `a,
         about, after, all, an, and, any, as, at, be, before, but, by, can, for, from, he, her,
         here, him, his, i, if, in, is, it, its, me, my, no, nor, not, now, of, on, one, or, our,
         she, so, than, that, the, them, then, there, they, this, to, up, us, was, we, were, what,
         when, who, will, with, yet, you, your`.

       They still count in `names(R)`. The report lists the aliases left out.
  4. **When an id became E's** *(r2.2, by log position)*. Raw id R is **bound to E at seq b(R, E)**:
     the lowest `seq` of any `name` or `alias` row on R matching a graded alias of E other than P.
     - Every row counts by its own position, whatever wrote it: seed rows from the pass-0
       registry, chunk rows, gate rows and audit rows.
     - Positions are the log's total order. A row written in the same chunk as the binding name,
       but after it, comes after it.
     - A raw id never bound to E has no b.
  5. **A chunk leak** *(r2.2)* is a row with all three of:
     - its source chunk is pre-reveal for (E, P, r);
     - it is written on a raw id R with `map(R) = E` (an ambiguous or unmapped R is never
       charged, and is counted as before);
     - `b(R, E) ≤` the row's own `seq`.

     That includes the binding row itself, when a pre-reveal chunk names R as E unprompted.
     Whether R also holds P doesn't matter. Two cases stay safe:
     - **separate id, merged later:** a visitor id that gains an E name only at or after r, or
       only through a later `same_as` merge (which writes no name row on the raw id), was bound
       when a reader would bind it;
     - **id reused after the reveal:** the same raw id carried on with E's name added by a chunk
       at or after r is the same.
  6. **A registry leak** is a raw id in `registry_pass0.json` whose aliases include both P and
     another graded alias of E that the text first uses at or after r. Pass-0 joined them before
     any chunk ran. It is counted once per `same_as` entry.
- **Reported:** per `same_as` entry, chunk-leak rows, the first leaking chapter and the
  registry-leak flag; then totals, and the counts of ambiguous and unmapped rows.
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
- **The clock: narrative exposure, by log position** *(r2.4, pbr ruling)*.
  - "By chapter k" means **as the log stood after the build wrote chapter k's last chunk**: a read
    with `asserted_as_of = hi(k)`, where `hi(k)` is the greatest `seq` in the spans of chapter k's
    chunks.
    - A chapter that appended nothing takes the previous chapter's `hi`. Chapter 0 is the seed:
      the log head before the first chunk.
    - Valid time is not pinned: each read takes the latest valid state the log held at that
      position (`as_of=None`).
  - **Why not story time.** Valid times are story time, which the model chooses (pass-0's timeline
    anchors). Flashbacks make chapter times go backwards, and a chapter can state a future-dated
    fact, so any anchor inferred from emitted rows gives false early or late verdicts. The log's
    order is the order the build read the book in, which is what "known by chapter k" means.
  - **A diegetic clock is a separate check**, not V1. Grading "what was true on the night of the
    murder" would need a reader-verified `chapter_as_of` map in the key. Absent one, such checks
    are not made.
  - `chunk_spans.json` still records each chunk's cursor, for reference only. No check reads it.

**`point_of_view`: who knows what.**
- **A `learns` entry** with a verified `as_fact`: the learner's `knows:` frame holds the fact by
  the end (exact entity, matched attribute, value), and does not hold it before the entry's
  chapter.
- **A `never_learns` entry** *(r2)*: the learner's frame never holds the fact, at any chapter's
  time.
- **The scores:** the share of `learns` entries held, "learned too early" counted separately, and
  `never_learns` violations (the target is 0).
- **Matching:** a fact's entity and value keys map to built ids by the §3 raw mapping, compared
  after closure (a merged id still counts). An unmapped key makes the entry `unmatched`, which is
  reported and never passed.

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
4a. *(r2.4)* **The exposure clock under a flashback.** In a hand-built run, chapter 3's chunk
    writes a belief row with `valid_from` earlier than chapter 1's rows, and chapter 4's chunk
    states a future-dated fact. The verdicts follow the log positions: the belief counts as
    written by chapter 3, never earlier, and the future-dated fact counts as known from chapter 4,
    not from its valid time.
7. **Unverified and null:** a structured form that only one reader marked `ok`, or an `as_fact` of
   null, is not graded and is listed as dropped.
8. **Old runs:** grading the stored R25 and R26 runs (no spans) writes `leaks: "unmeasured"` and
   the existing sections unchanged.
9. **Byte-stable legacy payloads** *(r2)*: for R27's key and a hand-built world, the legacy
   section payloads (identity, reveals, look-alikes, order, final, ever, containers) are
   byte-identical before and after this change. `ungraded_counts` and the report text change by
   design.
3c. *(r2.1, pbr)* **Binding time:**
    - **Unsafe:** a chapter-1 chunk names raw id R "mara", and a chapter-3 pre-reveal chunk
      (text: "the hooded visitor" only) writes on R. That is a leak, even if R also gets
      `alias "the hooded visitor"`.
    - **Unsafe:** the same, with R's "mara" name coming from a seed row (chapter 0).
    - **Safe:** raw id V holds only "the hooded visitor" before r, a chapter-9 chunk adds
      `alias "mara"` on V, and V's chapter-3 rows are no leak.
    - **Safe:** V is merged into Mara's id by `same_as` after r. No leak.
3e. *(r2.2, pbr)* **Same-chunk binding:** Mara first appears in chapter 1, the reveal is chapter 4,
    and a chapter-3 chunk whose text holds only "the hooded visitor" writes `name "Mara"` on R and
    then `in place:x` on R. Both rows are leaks: b is the name row's position, and each row's
    position is at or after it.
3f. *(r2.2, pbr)* **Ambiguity holds.** An R named both by an early Mara alias and by another
    entity's alias is ambiguous, so its pre-reveal rows are counted as ambiguous and not charged.
3d. *(r2.1, pbr)* **Token matching:**
    - "Or" never classifies a chunk, and is listed as left out;
    - "the hooded visitor" matches as a phrase, and "hooded visitors" does not;
    - prose containing "or" doesn't make a chunk pre-reveal or not;
    - *(r2.2, r2.3)* an alias "The One" tokenizes as `["the", "one"]` (two tokens) and classifies
      chunks, while an alias "One" (one stoplisted token) does not;
    - the tokenizer keeps "o'brien" as one token and splits "copper-hand" into two.
3a. *(r2)* **Raw mapping:**
    - an id named both by "mara" and by an alias of another key entity is ambiguous, and its rows
      are counted and not charged;
    - a nameless id is unmapped;
    - a later merge of the visitor id into Mara's doesn't change a chunk leak's verdict, because
      raw ids are read as written.
3b. *(r2)* **Registry leak:** a `registry_pass0.json` id holding "the hooded visitor" and "mara"
    (first used at the reveal chapter) is flagged; separate ids aren't.
6a. *(r2)* **`never_learns`:** a learner's frame holding the fact at any time is one violation.
10. Full suite green.
