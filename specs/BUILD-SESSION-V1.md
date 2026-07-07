# BUILD-SESSION-V1 — `begin_build()` / `seal_build()` (the last sub-porcelain reach)

**Status:** Cx deliberation done (verbs+sugar AGREED; exception behavior AGREED;
3 fixes adopted: `seal_build(scope="session"|"all")` — "all" preserves the
whole-log pending sweep for pre-session deferred rows; `World.close()` on an open
session = restore-toggle + clear-session + skip-classify + close-buffer, via an
explicit `abort_build()` the sugar and close both use; the session-vs-per-call
interaction is documented — session suppresses `inline`, explicit `batch`/`rules`
still classify locally and seal skips them. Manual `Porcelain(world)` second
handles are declared unsupported — `World.porcelain` is the one handle.) →
SHIPPED: impl reviewed GREEN first pass (416 green). Trigger (HD 088 item 3, upgraded by 093):
Construct's build path is the LAST thing keeping the first host off a
pure-porcelain integration. It reaches into three engine internals:
`world.ingestor.classify_inline = False` (global toggle), a finalize sweep
`world.classifier.classify_rows(world.buffer.all_rows(), model=False)` (+
`buffer.all_rows()` ×3), and `ingestor.cursor.advance` — the enter-build /
defer-everything / seal-once recipe, hand-rolled. The porcelain names it.

## The shape — two verbs + Python sugar
- **`p.begin_build(at=None) -> dict`** — enter build mode: save + disable
  `classify_inline` (every subsequent ingest defers classification, regardless
  of per-call `classify=` — the session wins by the same mechanism per-call
  modes already use), record the log head (the session's low-water mark), and
  optionally place the scene cursor (`at`). Raises if a session is already
  open (double-enter is a host bug, not a nesting feature).
- **`p.seal_build(model=False, scope="session") -> dict`** — finalize: one
  classification pass over the session's rows (seq > the recorded head;
  `classify_rows` already skips already-classified rows, so per-call
  `batch`/`rules` choices inside the session compose). **`scope="all"`** (Cx)
  sweeps the whole log instead — preserving the current
  `classify_all()`-style behavior when pre-session deferred rows exist.
  Restores the toggle, closes the session. `model=False` (rules-only, their
  current recipe) default; `model=True` runs the batch LM call for ambiguous
  rows. Returns `{"outcome": "sealed", "classified": n, "seq_range": [lo,
  hi], "scope": scope}`. Raises if no session is open.
- **`p.abort_build() -> dict`** — restore the toggle, close the session,
  classify NOTHING (idempotent; `no_session` outcome when none is open). The
  sugar's exception path and `World.close()` both route through it — a
  `World.close()` with an open session aborts it (Cx: never leave the session
  state live past the buffer).
- **`with p.build(at=None, model=False):`** — context-manager sugar over the
  pair. On exception: the toggle is restored but the classify sweep is
  SKIPPED and the exception re-raised (a half-built world is the host's to
  inspect; classifying wreckage helps nobody) — the session is closed either
  way.

## Semantics settled up front
- Session state lives on the **Porcelain instance** (the session is a host
  workflow concept; the engine parts stay dumb — the toggle and the classifier
  don't know a "session" exists).
- Per-call `classify="batch"/"rules"` INSIDE a session still classifies that
  call's rows at call end (a stronger local choice composes; seal skips them).
- `cursor_authoritative=` per call is orthogonal and unchanged.
- The membrane: nothing new is stored; `seal_build` writes only what
  `classify_rows` already writes (sidecar verdicts). No new roles, no schema.

## Non-goals
- No nested sessions; no per-frame sessions; no auto-seal on World.close()
  (silent classification at teardown is a surprise, not a convenience). No
  "build transaction"/rollback — append-only worlds don't roll back; a failed
  build is inspected or discarded whole (the dump/build seam already covers
  discard-and-replay).

## Cx deliberation questions
1. Two verbs + sugar vs context-manager-only: the verbs are the portable
   surface (a non-Python MCP host can't hold a `with`); agree?
2. seal on exception: skip-classify-and-close (spec'd) vs seal-anyway vs
   leave-open — which is least surprising for a host mid-crash?
3. The since-head slice vs their current whole-log `all_rows()` sweep: any
   correctness gap (e.g. pre-session deferred rows a host EXPECTED the sweep
   to catch)? Should seal offer `scope="session"|"all"`?
4. Anything else the build path reaches that this misses (HD names
   `all_rows()` ×3 — do all three fold into the seal, or does one serve a
   different read that needs its own surface)?

## Tests
- begin/seal happy path: rows ingested inside the session are unclassified
  until seal; seal classifies exactly the session's rows (rules mode);
  toggle restored; receipt carries count + seq_range.
- Double-begin raises; seal-without-begin raises; sugar seals on clean exit,
  restores-without-classifying on exception (and the session is closed).
- Per-call `classify="rules"` inside a session classifies immediately; seal
  skips those rows (no double work, count reflects it).
- `at=` places the cursor (rows stamp from it); prior `classify_inline=False`
  worlds restore to their prior value, not blindly True.
- Full suite green; defaults unchanged.
