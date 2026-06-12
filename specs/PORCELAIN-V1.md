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
  — single-key fold, typed.
- `locate / contents / path` — frozen as shipped, JSON-listified.
- `events(kind=None, participants=None, since=None, until=None,
  frame="canon") -> list[Event]` — `participants: str | list[str]`,
  ALL-of matching (review r1: HD's atoms are plural) — what_happened, filtered; Event =
  `{id, kind, agents, patients, t, caused_by}` (agents/patients read from
  the entity-valued `agent`/`patient` convention).
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
  are the ONLY writes ask can cause). Fold and event execution after
  resolution is fully deterministic. `Answer = {answered: bool, facts: [...], prose: str|None,
  unknown_reason, asks: [...]}` — provenance on every fact; an
  underdetermined reference returns candidates as `asks`, never a guess;
  every fact traces to a fold, never to the parser.

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
