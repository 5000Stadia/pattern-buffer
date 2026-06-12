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
world.path(a, b) -> list[str] | None           # None = not connected; proximity is not connectivity
world.materialize(scope, as_of=None, frame="canon",
                  lens="current_state",        # | establishing_set | what_happened | character_sheet
                  budget=None, asserted_as_of=None) -> Materialization
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
- `resolve()` returns the module-level sentinel `UNKNOWN` in
  `observe_or_unknown` worlds when nothing was observed. "I don't know" is a
  representable answer; treat it as one.
- `Materialization.unresolved` names the frontier in scope; `defaults` are
  render-coherence fills marked `default` — never facts.

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

## PLANNED (post-chapter-test; letter-008 direction)

Porcelain: `world.ingest(text) -> Receipt`, `world.snapshot(scope) -> JSON`
(contractually LLM-free; refer tier-1 only), `world.ask(question) -> Answer`
(provenance on every answer). MCP wrapper and the `arch` CLI as mechanical
mirrors of the same five verbs. Build adapters against these names.
