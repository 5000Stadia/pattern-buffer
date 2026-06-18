# ADOPTION.md — integrating pattern-buffer

**Audience:** agents (and humans) wiring this library into a host.
**Status: pre-1.0.** Signatures below are the current plumbing surface and
are exact as of this commit. The porcelain layer (letter-008 direction:
`ingest` / `snapshot` / `ask` as the complete host integration, all I/O
JSON-serializable) is the post-chapter-test polish target and is marked
PLANNED where it appears.

## The contract in one paragraph

The engine is a library below your host, not a peer beside it. It imports
nothing of yours and never calls you. You hand `World(...)` one callable
`(prompt: str, schema: dict) -> json` at construction — that is the entire
harness interface. From the engine's side every host is indistinguishable;
from your side the engine is indistinguishable from sqlite3.

## The three seams a host supplies

1. **The model shim** — two lines around your provider:
   ```python
   def shim(prompt: str, schema: dict) -> dict:
       return your_provider.complete(prompt, json_schema=schema)
   world = World("campaign.world", world_id="w:campaign", model=shim)
   ```
2. **The binding table** — your scoping unit (workspace, channel, space) →
   `world_id`. Many scopes → one world is allowed; one scope → many worlds is
   not. Fiction scopes bind to private worlds; all real-life scopes bind to
   *the* member's one world, with frames doing the scoping you expect.
3. **Frame entitlement** — which consumer sees which frames. Your existing
   disclosure machinery acts as one consumer policy over frames; frames remain
   the storage mechanism.

## Current surface (exact, pre-porcelain)

```python
World(path, world_id, model=None, policy="invent_under_canon", clock=time.time)
  # policy: "invent_under_canon" (fiction) | "observe_or_unknown" (tracking) | "deny"

# Writes — each behind its enforced role; you cannot mint write authority:
world.ingest(text, context="", frame=None) -> list[Assertion]   # LLM extraction via the gate
world.ingest_structured(items, frame=None) -> list[Assertion]   # pre-extracted items, same gate
#   frame= targets a NAMED frame (knows:<id> seeding, plot: arcs) — letter
#   028: frame is a write TARGET through full gate discipline, never an
#   authority escape; per-item frames win over the default.
world.resolve(entity, aspect, frame="canon", access=None)  # force a thunk per policy
world.truth.retract(assertion_or_id, reason) -> Assertion  # corrections append

# Reads — deterministic, zero model calls (P7):
world.locate(entity) -> list[str]              # containment chain, nearest first
world.contents(container) -> list[str]         # emptiness is [] — derived, never stored
world.state(entity, attribute, frame="canon", valid_as_of=None, asserted_as_of=None) -> FoldResult
world.path(a, b, valid_as_of=None) -> list[str] | None   # None = not connected; proximity is not connectivity
#   valid_as_of=T routes as the lateral graph stood at T: a SEVERED edge (its
#   connects_to/adjacent_to given a valid_to at the failure) drops from current
#   routing, while an earlier as-of still shows it (history preserved). Removal
#   is temporal, never a stored flag. NOTE: connects_to is a many-to-many
#   passage edge (path unions all current edges, no recency-fold) — to retire an
#   edge, end it with valid_to; a later connects_to does NOT supersede an old one.
world.salience(entity, frame="canon", as_of=None) -> float
world.neighborhood(entity, depth=1, frame="canon", as_of=None,
                   edge_kinds=None, max_fanout=64, budget=None) -> dict
world.materialize(scope, as_of=None, frame="canon",
                  lens="current_state",        # | establishing_set | what_happened | character_sheet | situation
                  budget=None, asserted_as_of=None) -> Materialization
#   lens="situation" (re-entry): standing-truth fold ∪ only the LIVE events
#   anchored to the scope, closed history dropped. Live = an open thread OR a
#   still-served (un-superseded) produced effect; anchored by where the live
#   effect sits (walk back via caused_by), not by who participated. The
#   standing-truth floor is never truncated by budget; live events yield to it
#   by recency. Derived every read, nothing stored.
#   ADOPTER NOTE: the lens is only as live as your caused_by links. An event
#   with no caused_by-bound surviving effect (or open thread) about a scope
#   entity reads as DEAD and won't surface — fail-safe, not an error, but it
#   means situation returns the standing floor only until you wire durable
#   consequences to their causing event. Model the residue, link it, it lights up.
world.confidence(entity, attribute, frame="canon", as_of=None,
                 asserted_as_of=None) -> dict
#   frame accepts str | list[str]: a list is trust over an observer's EFFECTIVE
#   knowledge = the read-union of those frames (knows:O ∪ public), mirroring
#   multi-frame frame_diff. Derived; functional-only.
world.refer(description, scope=None, frame="canon",
            constraints=None, as_of=None) -> Resolution
```

### Typed outcomes, not exceptions

Domain outcomes are values you must branch on:

- `Resolution.status` ∈ `resolved | candidates | underdetermined` — an
  underdetermined reference is YOUR ask to deliver to the user; the engine
  never guesses below its confidence floor.
- `FoldResult.conflicted` — the key is under an open truth-maintenance flag;
  `winner` is the engine's holding answer, `conflicting` lists both sides.
- `FoldResult.quantity` — for attributes declared `fold_policy="accrue"`,
  the folded numeric total. The `winner` is provenance for the latest ledger
  row, not the value a host should read.
- `resolve()` returns the module-level sentinel `UNKNOWN` in
  `observe_or_unknown` worlds when nothing was observed. "I don't know" is a
  representable answer; treat it as one.
- `Materialization.unresolved` names the frontier in scope; `defaults` are
  render-coherence fills marked `default` — never facts.
- `Materialization.quantities` carries derived totals as `(entity,
  attribute, value)` tuples. These totals are not stored assertions.

### Numeric quantities

For fungible counts such as gold, ammo, liters, or charges, declare the
attribute with `fold_policy="accrue"` before its first data row. A `literal`
numeric row is an absolute baseline; a `value_type="delta"` row is a signed
increment. The fold computes `baseline + later deltas`, with the ledger
available as `FoldResult._ledger_rows` for audit. `int` and `float` are
supported; exact decimal/fixed-point money is deferred.

## MUST / NEVER

- **MUST** route every write through the gate (`ingest` / `ingest_structured`
  / `resolve` / `truth.retract`). There is no other write path; do not look
  for one.
- **NEVER** let your renderer/narrator append. The component that speaks must
  not decide what is true. Resolution-as-a-tool is fine — the tool's
  implementation is the resolver, which holds the append authority.
- **NEVER** map a host scope to more than one world, or split one world
  across buffers (the 1:1 invariant). Bind scopes; don't partition.
- **MUST** preserve frame absence: serve consumers only frames they are
  entitled to; out-of-frame content is absent from the payload already — do
  not re-add it from caches.
- **NEVER** store anything derivable (location, emptiness, age, staleness,
  salience) on your side as truth; query it.
- **MUST** treat `generated`/`default` provenance as non-promotable; in
  tracking mode kind-defaults may render but never become facts.
- **MUST**, in `observe_or_unknown` worlds, let the gate stamp wall-clock
  learned-at meta-assertions (it does this automatically; do not strip them —
  staleness decay computes from them).

## THE PORCELAIN (frozen at porcelain-v0.1; additive-only henceforth)

`world.porcelain` — the typed, JSON-serializable host surface
(specs/PORCELAIN-V1.md is the contract):

```python
p = world.porcelain
p.ingest(text, source=None, scene=None, at=None, frame=None) -> Receipt
p.ingest_structured(items, frame=None) -> Receipt
p.resolve(entity, aspect, frame="canon") -> {status: resolved|unknown|denied, facts}
p.retract(assertion_id, reason) -> Receipt
p.snapshot(scope_ids, frame=, as_of=, lens=, budget=, since=) -> dict
   # contractually ZERO model calls and ZERO writes; id-only scopes; includes quantities
   # lens="situation": re-entry view — standing truth ∪ live threads, closed history dropped
p.state(entity, attribute, frame=, as_of=) -> {status: known|unknown|conflicted, fact, quantity?}
p.where(attribute, op, value, frame="canon", as_of=None) -> [entity_id]
   # op in >=, >, <=, <, ==; compares folded numeric values
p.aggregate(container, member_attribute, op, frame="canon", as_of=None, recursive=False) -> dict
   # op in sum, count, min, max, avg; numeric rollup over contents()
p.locate / p.contents / p.path
p.route(a, b, frame="canon", as_of=None) -> {route, status, segments}
   # passability-aware routing (RFC-003). status/segment: clear|blocked|obscured
   # (removed is temporal/diagnostic, in former_passages). A blocked segment
   # carries obstructing-fact `evidence`; an obscured one a computed
   # `unknown_basis`. Two-pass: a clear route if one exists, else a structural
   # route with flagged segments, else no_path. Obstruction = ordinary facts on a
   # PORTAL entity (a door's state, a guarded_by relation); traversability is
   # DERIVED, never stored. A portal kind gates passage only under a host-declared
   # `traversal:<kind>` policy (blocks_when_state / blocks_when_relation), scoped
   # to the kind; no policy => clear (no engine guess). The host supplies the words.
p.confidence(entity, attribute, frame=, as_of=) -> {score, status, last_observed_at, corroboration, conflicted}
   # derived trust over a functional key; never stored; functional-only (set/accrue -> score None)
   # frame is str | list[str]: a list = trust over the read-union (knows:O ∪ public);
   # cross-frame agreement raises corroboration, disagreement is conflict (score halved)
p.salience(entity, frame=, as_of=) -> float
p.neighborhood(entity, depth=, frame=, as_of=, edge_kinds=, max_fanout=, budget=) -> dict
p.events(kind=, participants=str|list, since=, until=, frame=) -> [Event]
p.frame_diff(a, b, scope, as_of=) -> [Fact]   # b is str|list[str]; divergent values marked
p.ask(question, frame=, as_of=) -> Answer      # 1 parse call + refer's cascade; facts from folds only
```

Every write returns a per-assertion Receipt; every fact carries
`{status, source_chain, assertion_id}` provenance. MCP wrapper and the
`arch` CLI follow as mechanical mirrors.
