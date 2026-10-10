# PORCELAIN-V1 — the frozen host surface

**Status:** draft for Codex review. **Authority:** letter 008 (verb set),
028 (frame-targeted writes), 029 (generated guard; what_happened windows),
030/031 (freeze gates HD; read surface consumer-validated with zero gaps),
034 (post-freeze roadmap separate). The engine beneath does not change;
porcelain is a typed, JSON-serializable wrapper over shipped plumbing.

**Freeze semantics:** on GREEN + tag `porcelain-v0.1`, this surface is
**additive-only**: parameters may be added with defaults; verbs may be
added; nothing is renamed, removed, or re-typed. Hosts build against it.

## 1. Module

`src/patternbuffer/porcelain.py` — class `Porcelain(world: World)`; also
`World.porcelain` lazy property. All I/O JSON-serializable (dataclasses
with `.to_dict()`); no engine import changes.

## 2. The verbs

### Writes
- `ingest(text, source=None, scene=None, at=None, frame=None) -> Receipt`
  — model-backed extraction via the gate. **Wrapper translations, exact
  (review r1 — zero engine changes):** `at` (a timeline position) →
  `cursor.advance(at)` before extraction; `scene` (a place/scope hint) →
  appended to the extraction context string, never spatial-anchoring by
  itself (cursor humility); `source` → after extraction returns its fact
  rows, the wrapper appends one `source` meta-assertion per fact row
  (entity=<assertion id>, attribute=source, value=<source>) through the
  same gate — the §7.1 chain post-applied, identical fold semantics to
  inline `src=`; `frame` per 028.
- `ingest_structured(items, frame=None) -> Receipt` — the no-model gate.
- `resolve(entity, aspect, frame="canon") -> Resolved` — thunk forcing
  per world policy; typed: `{status: resolved|unknown|denied, facts,
  receipt}` (UNKNOWN/Denied as values, never exceptions — 008).
- `retract(assertion_id, reason) -> Receipt` — truth-maintenance append.

`Receipt = {world_id, seq_range: [first, last], rows: [{assertion_id,
entity, attribute, frame}], frames: [..], canonicalization_receipts,
warnings}` — per-assertion accounting (review r1: per-item frames win
over the default, so a single frame field would lie); every write
answers "what exactly did you do to the log."

### Reads (LLM-free, contractual)
- `snapshot(scope, frame="canon", as_of=None, lens="current_state",
  budget=None, since=None) -> dict` — materialize, serialized: facts with
  per-fact `{entity, attribute, value, valid: [from, to], provenance:
  {status, source_chain, assertion_id}}`, plus `unresolved`, `conflicted`,
  `defaults`, `charter`. **Contractually zero model calls AND zero
  writes** (review r1): `scope` accepts entity ids / lists ONLY — no
  free-text references (use `ask` for that); the projector is verified
  resolver-free (it returns thunks as `unresolved`, never forces); no
  refer of any tier runs inside snapshot.
- `state(entity, attribute, frame, as_of) -> Fact | Unknown | Conflicted`
  — single-key fold, typed. *(Note 2026-10-09, READ-SURFACE-V1 §4: a fourth
  status, `Unresolved` — the served row is an unresolved placeholder, whose
  value is the thunk spec, never a known value. The field stays a string; a
  host treats a status it does not recognize as not known. The payload also
  gains `values` (a set's members), `conflicting_facts` and, given `value=`,
  `matches` (§5); every Fact gains `value_type`.)* *(Note 2026-10-09,
  EVENTS-ONE-READER-V1 §4: on an event, whose rows never fold, `state()` reads
  the event's record: `kind` and the movement keys answer what `events()`
  reports — `conflicted` when two disagree at one stamp — a set-valued key
  lists its members in `values` as for any entity, any other description key
  with several rows lists them all, and every key is `unknown` until the event
  has occurred.)*
- `locate / contents / path` — frozen as shipped, JSON-listified. *(Note
  2026-10-09, READ-SURFACE-V1 §8: additive `frame=` after `as_of`, and
  `asserted_as_of=` on these and every other read with a valid-time bound.)*
- `events(kind=None, participants=None, since=None, until=None,
  frame="canon") -> list[Event]` — `participants: str | list[str]`,
  ALL-of matching (review r1: HD's atoms are plural) — what_happened, filtered; Event =
  `{id, kind, agents, patients, t, caused_by}` (agents/patients read from
  the entity-valued `agent`/`patient` convention). *(Note 2026-10-09,
  EVENTS-ONE-READER-V1 §2: "what_happened, filtered" now means the event
  records: every event entity, classified or not, once per resolved id; `until`
  lists an event once it has occurred and `since` keeps whole records.)*
- **`frame_diff(a, b, scope, as_of=None) -> list[Fact]`** — the sixth
  read, shipping at freeze (letter 029 soft-ask; HD first consumer; the
  dramatic-irony instrument). **Comparison semantics, exact (review r1 —
  frames are sparse copies; assertion ids NEVER compare):** for each
  (canonical entity, fold-attribute) key with a folded winner in frame
  `a` at `as_of` (defaults and unresolved excluded), the Fact is in the
  diff iff frame `b` has NO folded winner on that key, OR `b`'s winner
  value is not value-equivalent (entity values compared
  identity-resolved; literals by equality). "B believes the wrong thing"
  is therefore IN the diff, marked `{divergent: true, b_value: ...}`.

### Ask (the one LLM-at-boundary read)
- `ask(question, frame="canon", as_of=None) -> Answer` — **new
  porcelain-native code, not a wrapper** (review r1): one model call
  parses the question into a typed query plan `{refer_targets, keys,
  events?, as_of?}` (strict schema). **Model budget, exact (review r2):**
  that one parse call, PLUS refer's own cascade for each refer_target —
  which may add tier-2 calls and accrued-alias writes per 018's
  documented behavior (those writes are refer's, receipted as such, and
  are the ONLY writes ask can cause). *(Note 2026-10-08,
  REFER-LEARNING-V1 §8: ask now writes nothing. Its refer calls pass
  `learn=False`; the model budget above stands.)* *(Note 2026-10-09,
  READ-SURFACE-V1 §6: in a non-canon frame each target is first bound by
  that frame's own tier 1, with no model call and no write; only if that
  does not resolve does refer's canon cascade run, as above.)* Fold and event
  execution after resolution is fully deterministic. `Answer = {answered: bool, facts: [...], prose: str|None,
  unknown_reason, asks: [...]}` — provenance on every fact; an
  underdetermined reference returns candidates as `asks`, never a guess;
  every fact traces to a fold, never to the parser. *(Note 2026-10-09,
  READ-SURFACE-V1 §4: `Answer` gains `unresolved` and `conflicted`,
  `[[entity, attribute]]` each. A placeholder key is named, never served as
  a fact; a set-valued key serves one fact per member; a conflicted key
  serves its winner and is named.)*

## 3. Out of scope at freeze
MCP wrapper + `arch` CLI (mechanical mirrors, post-freeze); the 034
roadmap (accrual promotion, inclusion edges); host-side anything.

## 4. Tests
Typed-outcome coverage per verb (incl. unknown/denied/conflicted paths);
snapshot zero-model contract (StubModel with no scripted responses across
every snapshot/read call); frame_diff against the mystery shape (canon
minus knows:player yields the planted irony delta); Receipt completeness
(every write's rows accounted); JSON round-trip on every payload; the
existing 119-test suite untouched.


## 5. Post-impl clarifications (review r4; part of the frozen contract)

- Snapshot scope ids must match `^[a-z][a-z0-9_]*:[a-z0-9_:]+$` AND be known entities (identity-resolved, at least one row) — an unknown id is an error value, never an empty snapshot.
- `Receipt.seq_range` is `null` for empty writes (no sentinel values).
- `resolve()` returns `receipt` on every path (empty receipt when nothing
  was appended).
- `events(until=)` is INCLUSIVE: window `[since, until]`.
- Event causality convention: event-level causality is direct rows
  (`event:x · caused_by · event:y`) and is what `events()` serves;
  row-level `caused_by` item fields produce provenance meta on the
  assertion id (establishing-set machinery), a different concern.
- `ask` location facts carry an additional `chain` key; event results
  appear as `{event: {...}}` entries — consumers must tolerate both
  extensions of the Fact shape.
- `ask` executes `wants_events` (participants = resolved targets,
  bounded by the plan's or caller's as_of) and honors the plan's `as_of`.
  *(Note 2026-10-09, READ-SURFACE-V1 §6: "honors the plan's `as_of` up to
  the caller's". One effective time — the caller's `as_of`, lowered but
  never raised by a valid plan `as_of` (a finite number; anything else is
  ignored) — governs every step, the events window included.)*
