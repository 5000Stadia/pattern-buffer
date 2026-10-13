# STAGE-MODELS-V1: a model and an effort per build stage, and grading a partial book

**Status:** r1.3, narrowing after pbr's code-review RED: a partial grade covers a build of exactly chapters 1..N, read at the run's head, with no horizon reads and no private engine call. Windowing a longer build at an earlier chapter waits for a public engine read (a later item). r1.2, answering pbr's r1.1 RED: the window is cut in `book_gold`, where the full key is; identity is read as of `hi(N)`; and not-yet-corrected corrections are pending and outside the scores. r1.1, answering pbr's r1 RED: the correction window; locations are half-open and stay open at the horizon; the partial read bound; a missing `default`; and a routing test across workers. For pbr review. Author: pb, 2026-10-13. Harness only.
**Source:** the profiling build (`evals/results/2026-10-13-profile-lhm2/REPORT.md`): about 96% of
output tokens are hidden thinking, and latency is output-bound (R² 0.97). Kabe, asked whether to
test effort settings (2026-10-13): "Yes and further consider alternative models and speed. We may
want to initially index complex concepts like motive and dynamics escellating on a plot, but mostly
gathering details accurately already established should be fast chore work, much of which can be
batched for speed and much of which can be parallelized". See `docs/SPEED-PLAN-2026-10-13.md`,
step 1b.
**Builds on:** BARE-CALL-V1 (the shim's argv), BUILD-PROFILE-V1 (the call labels), BOOK-RUN-V1 and
GRADE-LEAKS-V1 (the grader).

## Need

Every build call today uses one model (`PB_EVAL_MODEL`, default `claude-sonnet-4-6`) at the CLI's
default effort. To tier the work, extraction of stated detail cheap and interpretation deep, each
stage needs its own model and effort. To judge a setting, a short build must be gradable against
the part of the key it covers.

## The shape

### 1. A stage map, read by the shim

- **The map.** `PB_EVAL_STAGE_MODELS` names a JSON file:

  ```json
  {"default": {"model": "claude-sonnet-4-6", "effort": null},
   "pass0":   {"model": "claude-sonnet-4-6", "effort": "low"},
   "pass1":   {"model": "claude-haiku-4-5",  "effort": null},
   "commit":  {"model": "claude-haiku-4-5",  "effort": null},
   "audit":   {"model": "claude-sonnet-4-6", "effort": "medium"}}
  ```

  - **Keys** are the BUILD-PROFILE-V1 stage labels (`pass0`, `pass1`, `escape_repair`, `commit`,
    `audit`), plus `"default"` for anything unlabelled or unlisted.
  - **`effort`** is `null` (the CLI default, no flag) or one of `low`, `medium`, `high`, `xhigh`
    and `max`.
  - **`model`** is any model string the CLI accepts.
- **Choosing per call.** `claude_model` reads the current label (`usage_ledger`'s context
  variable) and picks that stage's entry, falling back to `"default"`.
  - `bare_argv(model, effort=None)` appends `--effort <effort>` when it is set. Nothing else in
    the argv changes.
  - The legacy argv (`PB_SHIM_LEGACY=1`) ignores the map.
- **No map means no change.** Without `PB_EVAL_STAGE_MODELS`, every call is exactly today's:
  `PB_EVAL_MODEL`, no `--effort`.
- **Refused at load, before any call:**
  - an unknown stage key;
  - an effort outside the set;
  - an empty model;
  - a map that isn't a JSON object;
  - *(r1.1)* an unreadable file, invalid JSON, or a `model` or `effort` that is neither a string
    nor (for `effort`) `null`.

  The run stops with the reason.
- *(r1.1)* **A missing `"default"`** means `{"model": PB_EVAL_MODEL, "effort": null}`, today's
  call. So `{}` is a valid map that changes nothing, and a map listing one stage changes only that
  stage.
- **Receipts.** Each `usage.jsonl` call line records its `model` (already there) and a new
  `effort` field. `profile_build.py` groups each stage's table by (model, effort) when a stage used
  more than one. `meta.json` records the map's content and its sha256.
- **Codex** (`PB_EVAL_PROVIDER=codex`) is out of scope for V1. Per-stage routing there is a later
  item, if wanted.

### 2. Grading a partial book: `--through-chapter N`

A build of chapters 1..N is graded only against the key entries a reader of chapters 1..N could
know.

**Where the window is cut** *(r1.2, pbr)*. `graded.json` doesn't carry the chapter fields the
window needs, so the cut happens where the full key is:
- `book_gold.py --through-chapter N` reads the full key and both verified verdict files, applies
  the rules below, and writes a **windowed** `graded.json` stamped `"through_chapter": N`.
- `grade_book.py --through-chapter N` consumes that artifact and uses N only for its read bounds.
- `grade_book` refuses before grading when:
  - it is given `--through-chapter` but the `graded.json` has no stamp, or a different N;
  - it is given a stamped `graded.json` without the flag;
  - N is not in `1..` the book's chapter count;
  - *(r1.3)* **N is not the last chapter the run built** (the last chapter in its
    `chunk_spans.json`, and `meta.json`'s chapter count when present).
- **A partial grade is a grade of a short build** *(r1.3)*. The run built exactly chapters 1..N,
  so everything it wrote belongs to those chapters, its gate and audit rows included. Reads happen
  at the run's head, as for a full book. Identity, reveals, look-alikes, final and every belief or
  point-of-view read are the existing grader's, unchanged, against the windowed gold.
- **Grading a longer build at an earlier chapter is out of V1** *(r1.3)*. It would need every fold,
  including the engine's internal entity comparisons, to see identity as of a past log position.
  No public engine read does that today, and the harness must not reach into private engine
  methods for it (pbr). It becomes a roadmap item for a public "identity as of" read, through its
  own spec, if it's ever needed.

The selection rules, applied by `book_gold`:
- **entities:** those whose `first_chapter ≤ N`. Aliases are kept only where
  `alias_first_chapter ≤ N`, when the field exists; otherwise all aliases are kept.
- **same_as:** reveals with a reveal chapter ≤ N.
- **not_same:** pairs whose two entities both have `first_chapter ≤ N`.
- **locations and holdings** *(r1.1)*: ranges are half-open, `[from_chapter, to_chapter)`.
  - An entry is in the window when `from_chapter ≤ N`.
  - If its `to_chapter` is null or greater than N, it stays **open** in the window
    (`to_chapter: null`): the fact is still active at the horizon and counts for `final`.
  - If its `to_chapter` is N or less, it stays closed as written.
  - Nothing is clipped.
- **containers:** reveals with `revealed_chapter ≤ N`.
- **knowledge:** entries with `chapter ≤ N`.
- **false_beliefs:** entries with `from_chapter ≤ N`. If `corrected_chapter` is null or greater
  than N, the belief is graded as still held through N (the believer window ends at N).
- **corrections** *(r1.1, r1.2)*: graded only when `corrected_chapter ≤ N`.
  - An entry with `stated_chapter ≤ N < corrected_chapter` is **pending**: it is left out of the
    correction items and every correction denominator, and counted only in an informational
    `pending_corrections` number. The matching false belief, if any, is graded as held.
  - The denominators are therefore deterministic.
- **Reads** *(r1.3)*: as for a full book, at the run's head. The windowed gold, not a bounded
  read, is what limits a partial grade.

### 3. The comparison it enables (a measurement, not part of this spec's build)

The first two chapters of the practice book, *The Address That Hummed*, about 3.9k words with
verified gold, are built under three maps:
- (a) Sonnet at low effort throughout;
- (b) Sonnet at medium effort throughout;
- (c) Haiku for `pass1` and `commit` (the chore stages), and Sonnet at medium for `pass0`,
  `escape_repair` and `audit`.

Each is graded with `--through-chapter 2` and profiled. The default-effort baseline is the
2-chapter profile already taken on *The Last Honest Meter*. That book is a different text, so its
time is a reference only; a same-book default run is added if the comparison needs one.

Kabe approved the comparison (2026-10-13). Its report gives:
- wall time, calls, output tokens and thinking share per stage;
- every grade section, with the run count. One run per setting means "unmeasured" for any tail.

## Not in this spec

- Batching changes, prompt changes and the registry-first pipeline (speed plan step 4).
- Choosing a default. Defaults change only after the comparison, through a later spec.

## Tests (no model calls)

1. **No map:** the argv is exactly BARE-CALL-V1's, with no `--effort`, under every label.
2. **Routing:** under a map, a call inside `label(stage="pass1")` uses pass1's model and effort.
   Unlisted stages and unlabelled calls use `"default"`, or today's call when it is absent. `{}`
   changes nothing. The argv ends with `--effort low` exactly when effort is set.
2a. *(r1.1, pbr P2)* **Routing across workers:** a fake-shim toy build runs parallel pass-0
    (4 workers) and pass-1 (4 workers), with one pass-1 retry and the `ObjectiveModel` wrapping
    commit's classification. Every recorded call's argv carries its own stage's model and effort.
3. **Refusals at load:** an unknown stage, a bad effort, an empty model and a non-object map are
   refused before any call, naming the reason.
4. **Receipts:** call lines carry `effort`, and `meta.json` holds the map and its sha256. The
   profile groups by (model, effort) when a stage mixes them.
5. **Legacy:** `PB_SHIM_LEGACY=1` ignores the map.
6. **Partial grading:**
   - on a hand-built key with entries across chapters 1–4, `--through-chapter 2` keeps exactly the
     entries the rules above select;
   - a belief corrected in chapter 3 is graded as held through chapter 2;
   - *(r1.1)* a correction with `stated_chapter` 1 and `corrected_chapter` 3: at N = 2 its
     correction checks are absent and the belief is held; at N = 3 they are made;
   - *(r1.1)* a move open from chapter 1 to null, and one from chapter 1 to 4, are both open at
     N = 2 and both count for `final`, while one from 1 to 2 is closed;
   - *(r1.2, r1.3)* the refusals: a flag without a stamped artifact, a stamped artifact without
     the flag, a mismatched N, N = 0, and **N different from the run's last built chapter** (both
     below it and beyond it);
   - *(r1.3)* a 2-chapter build graded with `--through-chapter 2` equals the existing grader's
     output on the same world against the same windowed gold. No horizon code runs, and no
     private engine method is called (a test asserts `_fold_over_closure` is never reached).
   - *(r1.2)* a pending correction is absent from items and denominators, and counted in
     `pending_corrections`;
   - without the flag, the output is byte-identical to the current grader on R27's key and a
     hand-built world.
7. Full suite green.
