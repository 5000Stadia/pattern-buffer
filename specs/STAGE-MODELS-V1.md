# STAGE-MODELS-V1: a model and an effort per build stage, and grading a partial book

**Status:** r1, for pbr review. Author: pb, 2026-10-13. Harness only.
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
  - a map that isn't a JSON object.

  The run stops with the reason.
- **Receipts.** Each `usage.jsonl` call line records its `model` (already there) and a new
  `effort` field. `profile_build.py` groups each stage's table by (model, effort) when a stage used
  more than one. `meta.json` records the map's content and its sha256.
- **Codex** (`PB_EVAL_PROVIDER=codex`) is out of scope for V1. Per-stage routing there is a later
  item, if wanted.

### 2. Grading a partial book: `grade_book.py --through-chapter N`

A build of chapters 1..N is graded only against the key entries a reader of chapters 1..N could
know. `book_gold` and `grade_book` apply this filter before scoring:
- **entities:** those whose `first_chapter ≤ N`. Aliases are kept only where
  `alias_first_chapter ≤ N`, when the field exists; otherwise all aliases are kept.
- **same_as:** reveals with a reveal chapter ≤ N.
- **not_same:** pairs whose two entities both have `first_chapter ≤ N`.
- **locations and holdings:** entries with `from_chapter ≤ N`, with `to_chapter` clipped to N.
- **containers:** reveals with `revealed_chapter ≤ N`.
- **knowledge, false_beliefs and corrections:** entries whose chapter (`chapter` or
  `from_chapter`) is ≤ N. A belief whose `corrected_chapter > N` is graded as still held, with its
  correction outside the window.
- **"final" reads:** at chapter N's exposure-clock position (GRADE-LEAKS-V1), not at a full book's
  end.

The report states the window (`through_chapter: N`) on its first line. Without the flag, grading is
byte-identical to today.

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
   Unlisted stages and unlabelled calls use `"default"`. The argv ends with `--effort low` exactly
   when effort is set.
3. **Refusals at load:** an unknown stage, a bad effort, an empty model and a non-object map are
   refused before any call, naming the reason.
4. **Receipts:** call lines carry `effort`, and `meta.json` holds the map and its sha256. The
   profile groups by (model, effort) when a stage mixes them.
5. **Legacy:** `PB_SHIM_LEGACY=1` ignores the map.
6. **Partial grading:**
   - on a hand-built key with entries across chapters 1–4, `--through-chapter 2` keeps exactly the
     entries the rules above select;
   - a belief corrected in chapter 3 is graded as held through chapter 2;
   - final reads come from chapter 2's position;
   - without the flag, the output is byte-identical to the current grader on R27's key and a
     hand-built world.
7. Full suite green.
