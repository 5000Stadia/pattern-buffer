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
   The engine calls this callable **synchronously and unbounded** — every model
   path (extraction, classification, thunk resolution, `refer` tier-2, `ask`)
   blocks until your shim returns. **Bounding the call is yours, not the
   engine's** (see MUST/NEVER): a hung provider read will wedge the calling
   build until *your* timeout fires, so wrap the shim in your own runtime's
   deadline (and recycle the worker — a blocked socket read can't be cancelled
   in-thread, only abandoned). The engine cannot bound it for you without
   reaching into process-global signal state or leaking the very thread it
   couldn't kill — both worse than honest blocking, both violations of "the
   engine never reaches into the host." Best of all, avoid the call: rows you
   know are durable should be declared `structural` via `attribute_default` so
   the classifier skips the model entirely.
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
supported for game-grade quantities.

**Exact decimal (money, real ledgers).** When a quantity must fold exactly
(`0.10 + 0.20 == 0.30`, never `0.30000000000000004`), author it as a Python
`Decimal` (in-process) or the tag form `{"$decimal": "12.50"}` (JSON) — both
normalize to the same stored row. Rules that follow from append-only fidelity:

- **Pick one representation per attribute.** A fold mixing exact-decimal and
  `float` **raises** (an authoring smell, surfaced not silently promoted);
  `Decimal` + `int` folds exactly.
- **Authored scale is preserved.** `12.50` round-trips as `12.50`; a
  `visible(value=...)` match is scale-sensitive (`12.5` does not match `12.50`).
- **Porcelain payloads carry the tag dict**, never a raw `Decimal` — every
  verb's return stays plain-`json.dumps`-able. Core reads (`World.state`,
  `materialize`) return real `Decimal` objects; if you re-serialize those
  yourself, use `patternbuffer.codec.encode_out` (or `json_default`).
- `avg` over decimals divides under a fixed context (prec=50, HALF_EVEN) —
  deterministic; sums are exact. Currency codes, units, and rounding *policy*
  are host meaning — model them as ordinary facts, not value forms.

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
- **MUST** bound the model callable in your own runtime. The engine invokes it
  synchronously and unbounded on every model path; it deliberately adds no
  timeout (a real cancellable deadline can only live where you own the
  worker/process — the engine could only abandon-and-leak the thread or hijack
  process signals, both forbidden). A flaky provider's blocked read otherwise
  hangs the build indefinitely. Prefer declaring known-durable rows `structural`
  so the classifier never calls the model at all. A wedged build is **truth-safe
  but not atomic**: `ingest_structured` appends a row then classifies it inline,
  so a timed-out classifier can leave a committed log prefix and an unclassified
  sidecar row. Truth is intact (the log is append-only, the sidecar rebuildable,
  unclassified reads fall back to `STATE`) — but a killed bulk build is **not** an
  all-or-nothing artifact. If atomic scenario publication matters, build in a
  staging world; after recycling a timed-out model worker, finish classification
  before serving or swapping the world.

## THE PORCELAIN (frozen at porcelain-v0.1; additive-only henceforth)

`world.porcelain` — the typed, JSON-serializable host surface
(specs/PORCELAIN-V1.md is the contract):

```python
p = world.porcelain
p.extract(text, scene=None, extract="full"|"lean", pov=None) -> [item dict]
   # INGEST-LATENCY-V2: READ-ONLY extraction (no write). Parallelize N extract() calls
   # in YOUR runtime (your concurrency cap), then ingest_structured() the results SERIALLY
   # (append-only writes stay serial). The engine doesn't add concurrency (membrane).
   # pov (SHAPE-FIX-V1): the viewpoint entity id — first/second-person pronouns (I/you)
   #   bind to it instead of minting a phantom person:you. Id-validated before the prompt.
p.ingest(text, source=None, scene=None, at=None, frame=None,
         classify="inline"|"batch"|"defer"|"rules", extract="full"|"lean",
         cursor_authoritative=False, pov=None) -> Receipt
   # classify (HD 079/083): "batch" = ONE durability call/passage; "rules" = guardrails +
   #   STATE default, ZERO LM calls (fast+deterministic, eval-guard quality); "defer" skips.
   # extract (HD 082): "lean" trims the prompt (marginal input-side lever; eval-guard).
   # cursor_authoritative (HD 084): the cursor governs valid_from for all rows — bible
   #   source-ingest, so a diegetic year can't invert the story-time axis; the overridden
   #   per-item valid_from is preserved losslessly as a `source_valid_from` meta (host
   #   promotes to a typed year/era fact if wanted). Default off = per-item valid_from wins.
p.ingest_structured(items, frame=None, classify="inline"|"batch"|"defer"|"rules",
                    cursor_authoritative=False, at=None) -> Receipt
   # INGEST-HARDENING-V1: classify="batch" defers durability + runs ONE batch model
   # call per ingest call (the first-class form of classify_inline=False + classify_all;
   # ~65% build-time cut on generate-path builds) — use it for bulk/scenario ingest.
   # "inline" (default) = per-row; "defer" = no classify (host runs classify_all later);
   # "rules" = guardrails+STATE, zero LM.
   # at (AXIS-HEAD-V1): places the scene cursor before the commit — the per-chunk pose for
   #   parallel-extract/serial-commit paths (mirrors ingest(at=)).
   # frame= is a DEFAULT for unframed items, NOT an override (letter 028) — per-item frame
   #   keys WIN, which mixed batches require (a telling scene's knows:B rows must survive).
   #   NOTE: extract() returns RAW model output, and extracted items MAY carry their own
   #   frame (the schema declares it optional; live providers commonly stamp canon
   #   explicitly) — never ASSUME extraction output is unframed. To quarantine/
   #   stage a batch wholesale, apply YOUR policy to a COPY first (strip or reject item
   #   frames — retaining knows:* bypasses your quarantine; stripping erases knowledge
   #   semantics; which is right is your world-policy call, not the engine's or the
   #   model's). When frame= is given and items keep a different own frame, the Receipt
   #   carries a warning (never silent — HD 121).
   # The Receipt's `skipped: [{entity, attribute, value, reason}]` lists rows dropped at
   # the gate — edge-granular (containment cycle / self-edge / lateral self-loop) AND
   # `malformed_id` (SHAPE-FIX-V1: a stray-slash phantom id like person:/you, rejected not
   # normalized; runs AFTER the authority gate so a violation still raises). One bad row is
   # skipped, the rest of the chunk still ingests (no silent cap; other gate failures raise).
p.resolve(entity, aspect, frame="canon") -> {status: resolved|unknown|denied, facts}
p.retract(assertion_id, reason) -> Receipt
p.snapshot(scope_ids, frame=, as_of=, lens=, budget=, since=, correlated=False, features=False) -> dict
   # contractually ZERO model calls and ZERO writes; id-only scopes; includes quantities
   # lens="situation": re-entry view — standing truth ∪ live threads, closed history dropped
   # correlated=True (AWARENESS-READS-V1.1): fold each entity over its `aka` correlation
   #   union — the whole reveal scene (masked-figure ∪ revealed identity) in one snapshot;
   #   as-of-before a reveal returns the uncorrelated view (no leak). The scene-wide state_union.
   # features=True: inline each scope place's `part_of`-feature children (the burrow under the
   #   hillside) one level. Both opt-in, orthogonal to `lens`; default off = unchanged.
p.state(entity, attribute, frame=, as_of=) -> {status: known|unknown|conflicted, fact, quantity?}
p.where(attribute, op, value, frame="canon", as_of=None) -> [entity_id]
   # op in >=, >, <=, <, ==; compares folded numeric values
p.aggregate(container, member_attribute, op, frame="canon", as_of=None, recursive=False) -> dict
   # op in sum, count, min, max, avg; numeric rollup over contents()
p.locate / p.contents / p.path
p.composition(entity, frame="canon", as_of=None) -> [entity_id]
   # PLACE-FEATURE-ABSTRACTION-V1: the `part_of` chain up (the entity's place in the
   # structure) — compositional sibling of locate(). A separate axis from containment:
   # a burrow part_of a hillside does NOT put an actor in the burrow "in" the hillside.
p.features(place, frame="canon", as_of=None) -> [entity_id]
   # the place's `part_of`-children (its structural sub-features) — sibling of contents().
   # The sub-place is ONE entity answering both lenses (place: locate/contents/route/state;
   # feature: these). part_of is valid-timed; both reads HALT on a conflicted parent
   # (never silently pick) — the conflict surfaces via state(child,"part_of").
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
p.correlate(a, b, evidence, at=None) -> Receipt
   # AKA-CORRELATION-V1: link two entities as facets of one identity (non-collapsing
   # `aka`) WITHOUT merging — reveals, dual personas, amalgamation. `at` = the reveal's
   # valid_from. Outcomes: correlated | noop_already_correlated | vetoed_distinct
   # (the hard distinct_from veto is absolute). NOT a merge: resolve()/closure() and
   # every DEFAULT read ignore aka; each entity keeps its own rows.
p.correlations(entity, as_of=None, frame="canon") -> [entity_id]
   # the facets correlated with entity as-of (first-seen ordered). Empty before a
   # reveal's valid_from — the mystery is intact. Zero writes.
p.state_union(entity, attribute, frame="canon", as_of=None) -> {status, fact, quantity?, conflicting?}
   # the EXPLICIT correlated read: fold attribute over entity ∪ its aka facets, as-of.
   # Same shape as p.state. Returns the SAME view whether facts were on one entity or
   # split across correlated facets (retrieval-invariance). NOT a default read —
   # state/snapshot/ask never union; as-of-before a reveal returns the uncorrelated view.
   # Divergent facets use existing fold conflict semantics (no new blanket rule).
p.correlation_conflicts(as_of=None, frame="canon") -> [{a, b, aka_edge, distinct_edges}]
   # raw aka authored over a distinct_from (a contradiction) surfaced for adjudication;
   # the guarded correlate() prevents it at the source.
p.reconcile() -> {merges, proposals}                      # global finalize; host-invoked
p.proposals() -> [{a, b, evidence, auto_decline_reason, auto_decline}]
   # open maybe_same_as with a structured auto_decline (gate-failure code + evidence);
   # code "durable_contradiction" names contradictory standing facts (SHAPE-FIX-V1 Win 4)
p.confirm(a, b) / p.merge(a, b, evidence) / p.reject(a, b) -> Receipt
   # confirm = promote a proposal; merge = assert (guarded, hard vetoes absolute);
   # reject = distinct_from (sticky anti-merge)
p.adjudicate_deferred() -> {merged: [Receipt], residue: [proposal]}
   # SHAPE-FIX-V1: merge only the structurally-DECISIVE open proposals (anchor subsumption:
   # a pure fragment whose whole distinctive anchor set ⊆ the other's — tovin ⊆ tovin beck).
   # Blocked: relating edges, aka correlation, kind conflict, durable contradiction. The
   # semantic trap (two individuated things sharing a token) stays residue. reconcile()
   # unchanged; zero model calls; idempotent.
p.typing_conflicts() -> [{spurious, target, kinds, shared_anchor, asymmetry, artifact_edges}]
   # SHAPE-FIX-V1: read-only surfacing of typing slips (same-anchor cross-kind pairs with the
   # slip signature: an outgoing-bare spurious twin beside a structurally real entity —
   # person:harth beside place:harth). Proposals can't show these; adjudicate with retype().
p.retype(entity, to_kind, evidence, absorb=None) -> Receipt
   # SHAPE-FIX-V1: typing correction, DISTINCT from merge (the containment veto blocks a
   # merge, never a kind fix). absorb=None: correct one mistyped entity's kind (wrong kind
   # rows retracted, correct kind appended + classified). absorb=<target>: absorb a spurious
   # duplicate — slip signature verified, ONLY inter-closure artifact edges retracted (child
   # containment preserved), then guarded merge. Non-slip => vetoed_not_a_slip; distinct_from
   # absolute. Outcomes: retyped | merged | vetoed_not_a_slip | vetoed | noop_*.
p.entities(frame, prefix=None, as_of=None) -> [entity_id]
   # BOUNDED-READS-V1: the roster read — entity ids carried by ONE frame's rows, resolved +
   # sorted. frame REQUIRED (a prefix-only enumeration leaks cross-frame existence; every
   # read fixes perspective). Your place roster is entities("canon", prefix="place:").
p.facts(frame, entity=None, attribute=None, prefix=None, as_of=None, include_meta=False) -> [Fact]
   # BOUNDED-READS-V1: the frame-scan — ONE frame's visible rows as Fact dicts (provenance
   # included). RAW log reads for AUDITED scans (receipt trails, knowledge digests, marker
   # rows), NOT folds (folded truth = state/snapshot). frame REQUIRED. An exact a:<n>
   # receipt-chain target is always served; wide scans exclude a:*/attr:* unless include_meta.
p.begin_build(at=None) / p.seal_build(model=False, scope="session"|"all") / p.abort_build() -> dict
   # BUILD-SESSION-V1: a build session defers durability classification for everything
   # ingested inside it (the session wins over per-call classify=), then seal runs ONE pass
   # (scope="all" sweeps the whole log for pre-session deferred rows). abort/World.close()
   # restore the toggle and classify NOTHING. `with p.build(at=, model=, scope=):` is sugar
   # (seals on clean exit, aborts on exception). Retires the classify_inline / classify_all
   # / cursor.advance reach — use it for scenario/source builds.
p.fidelity_audit(frame="canon", as_of=None) -> {name_collisions, unstamped_timed, orphan_entities, open_conflicts, summary}
   # INGESTION-FIDELITY-V1: structural ingestion gaps as a queryable checklist, DERIVED
   # (zero writes; run AFTER seal + truth.scan()). name_collisions groups = {anchor, entities,
   # kinds (FOLDED, parallel to entities — weight cross-kind person<->place highest; the id
   # namespace can lie), pairs:[{a,b,status,reason?}], live}. status = WHY the pair isn't
   # merged (correlated | hard_blocked | typing_slip | auto_declined+reason | unlinked) — route
   # repair by it: reject() genuine homonyms (harth person<->place), adjudicate_deferred/retype
   # true same-kind splits. summary.name_collisions counts LIVE groups only (the tracked number).
   # unstamped_timed = classified STATE/EVENT rows with no valid_from (off the time spine).
   # orphan_entities = unanchored obj:/person:. open_conflicts = the truth-maintenance flags.
   # The engine SURFACES gaps keyed by entity; the HOST joins arc/cast severity and drives
   # targeted re-extraction of the flagged spans (membrane: engine never repairs).
p.axis_heads() -> {asserted_head: int, valid_head: float|None}
   # AXIS-HEAD-V1: the log's two-axis high-water mark. valid_head = MAX(valid_from) over ALL
   # rows, ALL frames — the entry-epoch read (a pre-play coordinate must sit above every
   # seeded row wherever it landed). A coordinate scalar, never content.
p.salience(entity, frame=, as_of=) -> float
p.neighborhood(entity, depth=, frame=, as_of=, edge_kinds=, max_fanout=, budget=) -> dict
p.events(kind=, participants=str|list, since=, until=, frame=) -> [Event]
p.frame_diff(a, b, scope, as_of=) -> [Fact]   # b is str|list[str]; divergent values marked
p.who_knows(entity, attribute, value=None, as_of=None) -> [frame_id]
   # WHO-KNOWS-INVERSE-V1: the knows:* frames that KNOW a fact — the computed inverse of
   # frame_diff (no stored known_by). A frame qualifies iff its FOLDED winner is present and
   # (value given) value-matches, identity-aware; superseded/retracted beliefs drop. V1 is
   # own-knows:-frame membership (the hidden-secret case); knows:O ∪ public union is V1.1.
p.ask(question, frame=, as_of=) -> Answer      # 1 parse call + refer's cascade; facts from folds only
```

Every write returns a per-assertion Receipt; every fact carries
`{status, source_chain, assertion_id}` provenance.

## THE MCP SERVER (non-Python hosts)

`pip install patternbuffer[mcp]` →
`patternbuffer-mcp --world w.world --world-id w:id` (env:
`PATTERNBUFFER_WORLD`, `PATTERNBUFFER_WORLD_ID`) serves ONE world over stdio
(the 1:1 invariant; multi-world = multiple servers). The 37 deterministic
porcelain verbs are MCP tools; results arrive as
`structuredContent = {"result": <the porcelain return>}` (Receipts as dicts;
exact-decimals as `{"$decimal": …}` tags) with the same object serialized in
the text block.

MCP-specific narrowings (the genuinely model-free subset — the server's World
has no model callable): `ingest_structured.classify` accepts `"rules"|"defer"`
only (default `"rules"`); `seal_build` takes no `model` argument (always
rules-only). Model-backed verbs (`extract`/`ingest`-prose/`ask`/`resolve`) are
V1.1 via MCP sampling. Trust boundary: a connected MCP client is a **fully
trusted world principal** — it can name any frame; tool annotations are hints,
never authorization. Put untrusted consumers (players, NPCs) behind YOUR
host-mediated surface; frame entitlement is a host concern.
