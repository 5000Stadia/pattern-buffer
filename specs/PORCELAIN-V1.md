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
  — model-backed extraction via the gate. `source` → speaker/document
  chain (`src=`/`doc=` semantics); `scene` advances the cursor pose;
  `at` sets valid-time context; `frame` per 028.
- `ingest_structured(items, frame=None) -> Receipt` — the no-model gate.
- `resolve(entity, aspect, frame="canon") -> Resolved` — thunk forcing
  per world policy; typed: `{status: resolved|unknown|denied, facts,
  receipt}` (UNKNOWN/Denied as values, never exceptions — 008).
- `retract(assertion_id, reason) -> Receipt` — truth-maintenance append.

`Receipt = {world_id, seq_range: [first, last], assertion_ids,
canonicalization_receipts, frame, warnings}` — every write answers
"what exactly did you do to the log."

### Reads (LLM-free, contractual)
- `snapshot(scope, frame="canon", as_of=None, lens="current_state",
  budget=None, since=None) -> dict` — materialize, serialized: facts with
  per-fact `{entity, attribute, value, valid: [from, to], provenance:
  {status, source_chain, assertion_id}}`, plus `unresolved`, `conflicted`,
  `defaults`, `charter`. **Contractually zero model calls** (tier-1 refer
  only if a string scope needs resolving; underdetermined scope is an
  error value, not a guess).
- `state(entity, attribute, frame, as_of) -> Fact | Unknown | Conflicted`
  — single-key fold, typed.
- `locate / contents / path` — frozen as shipped, JSON-listified.
- `events(kind=None, participant=None, since=None, until=None,
  frame="canon") -> list[Event]` — what_happened, filtered; Event =
  `{id, kind, agents, patients, t, caused_by}` (agents/patients read from
  the entity-valued `agent`/`patient` convention).
- **`frame_diff(a, b, scope, as_of=None) -> list[Fact]`** — the sixth
  read, shipping at freeze (letter 029 soft-ask; HD first consumer; the
  dramatic-irony instrument): folded keys present in frame `a` and absent
  from frame `b`, set-difference over folds, deterministic.

### Ask (the one LLM-at-boundary read)
- `ask(question, frame="canon", as_of=None) -> Answer` — NL → refer +
  fold + (optionally) events; `Answer = {answered: bool, facts: [...],
  prose: str|None, unknown_reason, asks: [...]}` — provenance on every
  fact; an underdetermined reference returns the candidates as `asks`,
  never a guess. Uses the injected model for question parsing ONLY; all
  facts come from folds.

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
