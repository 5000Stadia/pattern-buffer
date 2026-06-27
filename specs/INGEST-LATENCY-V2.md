# INGEST-LATENCY-V2 — rule-front durability + extraction seam + cursor-authoritative axis

**Status:** DRAFT → Cx GREEN before implementation. **Three** additive ingest-mode
knobs — two build-latency wins (HD 083) + one axis-governance fix (HD 084 / Kernos
074, the play-horizon linchpin); all on the ingest path; **default behavior
unchanged** (all three default to today's behavior).

## Win 1 — `classify="rules"`: deterministic durability, zero LM calls
**Today** `classify="batch"` runs the guardrails (structural/event/name/containment
short-circuits) deterministically, then sends the *ambiguous remainder* to the LM in
one batch. HD's profile: that LM batch is still 272s/build. **But the LM's own
failure-fallback is already a deterministic asymmetric default** — `is_containment →
CONSTITUTIVE, else STATE` (classify.py `_ask_model` except-path). So a rule-front
mode is just that documented fallback made explicit, no new semantics.

**Add `classify="rules"`:** the **guardrails** run as today (they already give
`place:` containment + structural → CONSTITUTIVE, `held_by`/`worn_by` → STATE,
`event:`/`caused_by` → EVENT, name/alias → CONSTITUTIVE), and **every row the
guardrails leave ambiguous gets STATE** — the doctrine's *primary* asymmetric default
("ambiguous property → STATE") — **without** an LM call. Implementation: in the rules
path, a deferred (non-guardrail) row is stored `(STATE, 0.5, needs_review=False)`
instead of being sent to `_classify_batch`.

**Deliberately STATE, NOT the `_ask_model` except-path's containment→CONSTITUTIVE
sub-rule (Cx fix):** that sub-rule defaults *object* containment to CONSTITUTIVE,
which does NOT movement-supersede — a movable object's `in` would then conflict
instead of recency-updating. STATE is the safe systematic default: a movable's `in`
supersedes correctly; a true fixture-object as STATE just sits with no competing
value (harmless). So rules-mode does **not** reuse the except default; the
`_ask_model` failure path is unchanged.

**Safety (engine-truth for HD's Q1):** durability is an index, not truth
(rebuildable); STATE is the non-erasing, correctable class; CLASSIFIER-EVENT-SAFETY
already bars the *erasing* EVENT from any model/default path; `needs_review` is never
raised (it flags only low-confidence CONSTITUTIVE — none here). So rule-front can only
*lose the LM's STATE-vs-DISPOSITIONAL/CONSTITUTIVE nuance* on ambiguous attrs (a
quality, not correctness, question) — **safe behind the eval**, the host A/B's it.
Default stays `"inline"`; `"rules"` is opt-in (HD's Q2: PB-side mode, host-driven).

## Win 2 — `world.extract(text) → items`: a read-only extraction seam for host parallelism
**Engine-truth for HD's Q (serial incidental?):** `World.ingest(text)` is ONE
extraction call; the 7 serial chunk extractions are Construct's pipeline calling
`ingest` 7×. They're **independent** (cross-chunk coreference is the Stage-2 reconcile
pass, not extraction-time), so serial order is incidental. The real constraint is that
the append-only **buffer writes** must stay serial (one SQLite connection, per-row
commit — not concurrent-safe). So: parallelize the *extraction model calls*, serialize
the *writes*.

**Add `world.extract(text, context="", extract="full") → list[dict]`** — the first
half of `ingest()`: build the prompt, call the model, return the raw extracted item
dicts. **Read-only, no buffer write, no canonicalization/cursor/resolution** (those
all live in `_ingest_item`) → safe to call concurrently. **`extract()` takes NO
`frame`** (Cx fix): the default-frame is applied in `ingest_structured` (an
ingest-time concern), so the host does `ingest_structured(extract(chunk), frame=F)`.
`ingest(text, frame=, classify=)` refactors to `ingest_structured(self.extract(text,
context, extract), frame=frame, classify=classify)` — behavior-identical (frame still
passed to ingest_structured). The host then: run N `extract(chunk)` calls concurrently
in its runtime (with ITS concurrency cap — HD's 600s-bound caveat is real), collect the
item lists, and `ingest_structured(items, frame=…)` them **serially** (fast writes). PB
owns the prompt+schema (incl. the lean variant); the host owns concurrency + cap. (PB
cannot parallelize itself — it calls the injected model synchronously; the test stub
even mutates `.calls`, so concurrency is unambiguously the host runtime's, behind the
membrane.)

## Win 3 — `cursor_authoritative=True`: the cursor governs `valid_from` (the play-horizon linchpin)
**The bug (HD 084 / Kernos 074):** bible source-ingest conflates two axes into
`valid_from`. Extraction reads "in the year 612 of the Alder Reckoning" and stamps
opening rows `valid_from=612`, while cursor-stamped later chapters land at 6, 8 →
**inverted story-time axis**, which breaks the as-of play-horizon (my 080). A diegetic
*date* (content) is being used as the story-time *coordinate* (the axis). This is the
same decoupling we shipped for diegetic time ("never stamp `valid_from` from the
diegetic minute") — source-ingest violates it with diegetic *years*.

**Engine-truth (bless Kernos's Option 1):** source-ingest and live-play have OPPOSITE
needs on the `valid_from` axis. Live play WANTS the model's per-item `valid_from` (a
Ch.3 revelation about Ch.1 correctly gets Ch.1's valid_from — "revealed late about
earlier history"). Bible source-ingest establishes a **monotone timeline by chunk
order** — the cursor IS the authoritative axis, and the model's diegetic-year
`valid_from` is *noise on that axis*. So the lever is **mode-specific** (a prompt fix
can't be — live needs the per-item valid_from; a post-pass retract+reassert is
write-churn). Option 1 stamps it right the first time.

**Add `cursor_authoritative=False` to `ingest`/`ingest_structured`.** When True: every
**non-timeless** row's `valid_from` is the **cursor** (`cursor.position`), overriding
any per-item `valid_from`. **Drop-vs-demote → DEMOTE-to-meta (lossless):** if an item
carried a `valid_from`, it is **not silently dropped** — it is preserved as a
`source_valid_from` meta-assertion on the row (status `inferred`, like
`canonicalized_from`). The engine can't know the value is a "year" on the right entity
(that's host meaning), so it keeps the raw coordinate auditable; the host promotes it
to a typed content fact (`year`/`era`) if it wants it queryable. Default `False`
(live-play behavior unchanged — per-item `valid_from` still wins).

**Implementation constraints (Cx):**
- The cursor override computes `valid_from` **before** `_edge_skip_reason` (the edge
  guard receives the computed `valid_from`). A **skipped** edge (cycle/self-edge) has
  no row, so it gets no `source_valid_from` — accepted (the edge is dropped anyway).
- **Timeless rows are unaffected**: they carry `valid_from=None` regardless, and a
  timeless item carrying a stray `valid_from` emits **no** `source_valid_from` (no
  story-time coordinate to demote).
- `source_valid_from` is a **row-id meta** following the `canonicalized_from`/`source`/
  `caused_by` pattern, and **MUST be added to `META_ATTRIBUTES`** (model.py) so it is
  meta-hidden from materialization and skipped by the classifier guardrail (like the
  other engine metas) — not folded as a world fact.

## Non-goals
- PB does **not** add concurrency itself (it calls the injected model synchronously;
  the async runtime + cap are the host's — same membrane as everywhere).
- No change to default `ingest`/`ingest_structured`/`classify="inline"` behavior.
- No change to the extraction prompt content (full/lean unchanged).

## Tests
- `classify="rules"`: a passage with mixed attrs → guardrail rows classified as today
  (place-containment/structural/name → CONSTITUTIVE; held_by → STATE; event:/caused_by
  → EVENT), and the **ambiguous remainder → STATE** (incl. object `in`, so a movable's
  containment recency-supersedes; `needs_review` never fires), with **zero** LM classify
  calls (assert via a counting stub). Rows fold.
- `world.extract`: returns the raw item dicts and writes nothing (`buffer.head()`
  unchanged); `ingest(text)` == `ingest_structured(extract(text))` (same rows);
  `extract(..., extract="lean")` uses the lean prompt.
- `cursor_authoritative=True`: items with explicit `valid_from` (e.g. 612) ingested
  after `cursor.advance(8)` get `valid_from == 8` (the cursor), not 612; the 612 is
  preserved as a `source_valid_from` meta on the row (not lost); timeless rows
  unaffected; two chunks advanced 5→10 produce monotone `valid_from` regardless of
  per-item values; default `False` leaves per-item `valid_from` winning.
- Full suite green; default paths unchanged.
