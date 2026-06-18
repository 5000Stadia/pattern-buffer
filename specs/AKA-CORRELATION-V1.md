# AKA-CORRELATION-V1 — non-collapsing identity correlation + the opt-in union read

**Status:** DRAFT → Cx GREEN before implementation (founder's standing loop:
1 Codex between final spec and implement, 1 Codex for final review). Additive on
porcelain-v0.1. Concludes the awareness-and-shape round-robin keystone (C 037,
Kernos 053, Cx 054 YELLOW, PB 060). Honors the ratified wall — *engine owns what
shapes exist + invariant retrieval; host owns which shape fits + what it means* —
and the hard build invariant from leg 3:

> **The correlation relation lives entirely outside the `same_as` identity
> closure and every default fold/read. It is an explicit, valid-time-gated read
> mode, or it does not ship.**

## Problem
"The masked figure" and the person they turn out to be are two richly-attributed
entities. A destructive `same_as` merge erases the mystery: an as-of-*before* read
would retroactively show the revealed identity. We need the third identity stance
— neither collapse (`same_as`) nor permanent separation (`distinct_from`) but
**correlation**: two entities are facets of one identity, *as of the reveal*,
with each entity's prior rows untouched and as-of-before-the-reveal still showing
two strangers. "The unknown of identity," sibling to RFC-002's unknown of facts.

## §1 `aka` — the non-collapsing correlation primitive

Add **`aka`**, an authored entity-valued edge: "these two entities are facets of
one identity." Symmetric in meaning; stored as written (the walker treats it
undirected). Chosen over a directional `revealed_as` because the relation must
also cover dual-personas (day John Smith / night Stupendous Man) and amalgamation,
which are not reveals; `revealed_as` stays a host-facing narration concept.

**Primitive placement** — `aka` joins exactly the sets `same_as`/`distinct_from`
occupy, with one deliberate exclusion:
- `INVIOLABLE_CORE` (model.py) — joins `same_as`/`distinct_from` here so a host
  cannot redeclare its semantics (this set guards core-attribute *semantics*, not
  writes; writes stay governed by engine-minted roles/status — Cx 056). Raw
  `ingest_structured` appends of `aka` remain allowed (append-only authored truth);
  do **not** add a hard write-block.
- `META_ATTRIBUTES` — **meta-hidden**: never materializes as a fact, exactly like
  `same_as`/`distinct_from` (the membrane fix already skips these in
  `current_state`/`materialize`).
- `SET_VALUED_ATTRIBUTES` — one entity may be `aka` many; coexisting values are
  data, never a recency conflict.
- `_IDENTITY_ATTRS` (identity.py) — so V2's `relating_edges_between` and the
  triage exclude it (an identity edge is not a domain relating edge, and must not
  feed individuation heuristics in either direction).
- **NOT** read by `registry.resolve()` / `registry.closure()`. Those are union-find
  over `attribute="same_as"` only (verified: identity.py:242). `aka` is naturally
  excluded as long as no code adds it there — this spec forbids adding it.

**What `aka` is NOT** (the invariants a reviewer must check):
- It never triggers, contributes to, or downgrades an auto-merge. The merger is
  neutral to it.
- It never canonicalizes an id. There is no `aka` analogue of `resolve()` — the
  union read gathers a *set*, it does not elect a winner.
- It never participates in any default fold or read (§5).

## §2 The valid-timed reveal
The `aka` edge is an ordinary assertion carrying `valid_from = reveal_time` (and
optionally `valid_to` if a correlation is later retracted as mistaken — additive,
not required for V1). Consequences, all free from existing two-axis semantics:
- An as-of read with `valid_as_of < reveal_time` does **not** see the edge → the
  correlation set is `{entity}` alone → mystery intact.
- `valid_as_of >= reveal_time` sees it → correlated.
- "Revealed late about earlier history" works without rewriting prior rows: the
  edge's `valid_from` is the reveal; the *facts* it unions keep their own
  valid-times. The union read filters the edge on `valid_as_of` (world truth) and
  honors `asserted_as_of` (audit) like every other read.

## §3 The correlation set + the opt-in union read

**Correlation set** `C(entity, valid_as_of, asserted_as_of)`: the
connected component of `entity` over `aka` edges **each independently filtered**
by the as-of axes — i.e. the transitive closure across edges valid at the asked
time. Transitivity is safe because an edge not yet valid is never traversed, so no
future reveal leaks backward. Computed fresh per read; never stored; never elects a
canonical id. Default (no aka edges visible) → `{entity}`.

**Inspection read** — `correlations(entity, valid_as_of=None, asserted_as_of=None,
frame="canon") -> list[str]`: the correlation set minus `entity` itself (the
facets), as-of. **Ordering: first-seen/log order with lexical tie-break** (never a
canonical election). Zero model calls, zero writes.

**Union read** — the explicit, opt-in retrieval-invariant view. Two surfaces:
- `state_union(entity, attribute, valid_as_of=None, asserted_as_of=None,
  frame="canon") -> FoldResult`: fold `attribute` over the union of subject rows
  across `C(...)`, in the given frame, as-of. Returns the same view whether the
  facts were authored on one entity or split across correlated facets —
  retrieval-invariance.
- Porcelain `snapshot(scope, ..., mode="correlated")` / a `state_union` porcelain
  verb (§6): the correlated projection of a scope.

Conflict-handling inside the union: **existing fold conflict semantics apply** —
nothing new. The governing invariant is retrieval-invariance: a `state_union`
result must match what the normal fold would have served had the same rows been
authored on one entity / one `same_as` closure. So divergent functional values
report `conflicted` exactly when the existing machinery already would
(constitutive disagreement, same-valid-time STATE disagreement, cross-source
disagreement) — and **not** otherwise. There is **no** blanket "different values on
different facets always conflict" rule: time-sequential STATE rows still
recency-supersede as normal (a blanket rule would turn ordinary supersession into
permanent correlation noise — Cx 056 #4). Set-valued attributes union as usual.

## §4 `distinct_from` interaction — guarded correlate, never silent
`distinct_from(a,b)` asserts "definitely different entities"; `aka(a,b)` asserts
"facets of one identity" — a genuine conflict. Mirror the guarded-merge discipline:

`correlate(a, b, evidence) -> Receipt` (the host's correlate verb):
- if `distinct_from` relates a's closure to b's (reuse `distinct_block`) →
  `Receipt{outcome: "vetoed_distinct", blocking_edges: [...]}`, **no append**.
- if `aka` already relates them (already correlated) → `Receipt{outcome:
  "noop_already_correlated"}`.
- else append the `aka` edge (role-authored) → `Receipt{outcome: "correlated",
  aka_assertion_id, ...}`.

A raw `aka` row authored directly via `ingest_structured` is appended (append-only;
we do not block authored truth), but coexisting `aka`+`distinct_from` on the same
pair is surfaced for adjudication by `correlation_conflicts() -> [(a,b,
distinct_edge, aka_edge)]` (an inspection read) so the host can `retract` one. This
conflict read is **`same_as`-closure-aware, bidirectional, and frame/as-of-aware**
— it reuses `distinct_block` semantics (closure-to-closure), not literal row-pair
matching (Cx 056 #3). The guarded `correlate()` verb is the recommended path and
prevents the conflict at the source.

## §5 The membrane invariant + acceptance gate (Cx's leak tests)
**Default reads are byte-for-byte unchanged.** `state`, `snapshot`, `materialize`,
`ask`, `refer`, `where`, `frame_diff`, `confidence`, `neighborhood`, `salience`,
and identity `resolve`/`closure` MUST NOT consult `aka`. The union is reachable
only through the explicit `state_union` / `correlations` / `mode="correlated"`
surfaces. Acceptance tests (the gate — all must pass):
1. **Pre-reveal isolation:** before `reveal_time`, default `state`/`snapshot` of
   each side sees only its own facts; `state_union(..., valid_as_of=before)`
   returns the single-entity view.
2. **No default union post-reveal:** after `reveal_time`, default reads of either
   side *still* do not union the other's facts.
3. **Explicit union only:** only `state_union(..., valid_as_of=after)` (or
   `mode="correlated"`) returns the combined view.
4. **As-of-before never leaks:** `state_union(..., valid_as_of=before)` returns
   the pre-reveal (uncorrelated) view even when the edge exists asserted-later.
5. **`resolve()`/`closure()` ignore `aka`:** an `aka(a,b)` does not place a,b in
   one `same_as` closure; the merger does not auto-merge them.
6. **`distinct_from` veto:** `correlate(a,b)` over a `distinct_from(a,b)` returns
   `vetoed_distinct` and appends nothing.
7. **Writes-nothing reads:** `correlations`/`state_union` leave `buffer.head()`
   unchanged.
8. **`aka` never surfaces in the PROJECTION** (the real membrane invariant):
   `snapshot`/`materialize`/`current_state` skip `META_ATTRIBUTES`, so `aka`
   never appears among served facts — exactly like `same_as`/`distinct_from`.
   The only inspection surface is `correlations()`. (Correction to the Cx-056
   spot-check: an *explicit* single-key fold `state(_, "aka")` does return the
   raw edge, because `fold_key` folds any named attribute — but `state(_,
   "same_as")` behaves identically, so `aka` introduces no new read behavior. We
   deliberately do NOT change the frozen `fold_key` path to hide `META` from
   explicit folds, which would silently alter `same_as`/`distinct_from`; if that
   engine-wide change is wanted it is a separate, deliberate spec.)

## §6 Porcelain surface (additive on porcelain-v0.1)
```python
p.correlate(a, b, evidence) -> Receipt
   # outcomes: correlated | noop_already_correlated | vetoed_distinct
p.correlations(entity, as_of=None, frame="canon") -> [entity_id]      # facets as-of
p.state_union(entity, attribute, frame="canon", as_of=None) -> {status, fact, conflicting?}
p.correlation_conflicts(as_of=None, frame="canon") -> [{a, b, aka_edge, distinct_edges}]   # adjudication aid
```
World-level mirrors (`world.correlate`, `world.correlations`, `world.state_union`,
`world.correlation_conflicts`) follow the existing pass-through pattern. `as_of`
maps to `valid_as_of`.

**Deferred to V1.1:** `snapshot(scope, ..., mode="correlated")` — the
full correlated *projection* over a scope. `state_union` already delivers the
retrieval-invariance capability per key (and satisfies every §5 gate test); the
scope-wide projector wrapper is a larger materialize change with a wider membrane
surface, so it lands as a focused follow-on, not in V1. Default `snapshot` is
untouched.

## §7 Explicitly OUT of V1
Looping/non-monotonic time (host illusion via as-of + per-iteration frames);
stored `known_by` (separate WHO-KNOWS-INVERSE-V1); stored derived rates / formula
engine; the general structure-polymorphism framework; place/feature abstraction
read (triggered later by a concrete El.4 case). `valid_to` on `aka`
(correlation-retraction) is allowed by the schema but not a V1 deliverable.

## Test plan
`tests/test_aka_correlation.py`: the seven §5 gate tests, plus — transitive
correlation set across two `aka` hops valid as-of; divergent-facet union reports
`conflicted`; set-valued facet union; `noop_already_correlated`; meta-hidden
(`aka` never appears in `materialize`/`current_state`); `correlation_conflicts`
surfaces a raw aka+distinct_from pair. Full suite stays green (no default-path
regressions — the membrane invariant).
