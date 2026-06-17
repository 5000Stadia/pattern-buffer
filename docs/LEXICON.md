# Lexicon

The working vocabulary for pattern-buffer. One name per concept, used identically in code, docs, tests, and specs. A term not in this file is added here before it is used twice.

## The two rules

1. **The double-read test.** Every exported name (class, function, CLI command) must parse correctly for an engineer with zero Star Trek context. Canon homage that only works as fan service stays out of the code and lives in doc prose.
2. **Nouns carry the flavor; verbs stay boring.** The operation algebra (`set`, `relate`, `event`, `resolve`, `retract`, `merge`, `refer`) and the role matrix (Ingestor, Classifier, Resolver, Projector, Renderer) keep plain engineering names — they are authority boundaries and must be instantly legible.

## Working terms (code symbols)

| Term | Definition | Double-read |
|---|---|---|
| **`World`** | The named, individual unit: one PatternBuffer + its physics (resolution policy + decay configuration) + derived indexes. The thing hosts bind to, name, and ship. | Universal. |
| **`PatternBuffer`** | The append-only assertion log — the only truth (P1). Each World owns exactly one; a buffer never holds two worlds; a world never spans two buffers (the 1:1 invariant). `world_id` is lineage/identity; the file is the buffer instance — never-joined playthrough forks may share a `world_id` (whitepaper A5). | Trek: holds the pattern between materializations. Systems: a buffer of patterns (cf. protocol buffers). |
| **`materialize()` / `Materialization`** | The projector's read: `(scope, as_of, frame, lens, budget)` → the world served from pattern. | Trek: rematerialization — re-entry exactly as left. Databases: a materialized view is the canonical term for a derived, disposable projection over a log. Both readings are precisely correct. |
| **`neighborhood()`** | A bounded read around one entity: folded subject state plus identity-closed structural neighbors across containment, lateral, relation, and event axes. | Plain graph/search vocabulary; kept bounded, not a query language. |
| **`salience()`** | A derived projection-time ranking score used to order neighborhoods and budgeted materializations. It never changes validity and is never stored as truth. | Plain attention/retrieval vocabulary. |
| **`aggregate()`** | A bounded collection rollup: `sum`, `count`, `min`, `max`, or `avg` over numeric folded values on a container's `contents()`, optionally recursive. | Plain analytics vocabulary; computed from present facts, never stored. |
| **`confidence()`** | A derived trust score for one functional folded key: `provenance × recency × corroboration` (halved if conflicted), plus `last_observed_at` for host-side staleness. `frame` may be a list — trust over the read-union of frames (an observer's effective knowledge, `knows:O ∪ public`), where cross-frame agreement raises corroboration and disagreement is conflict. Validity is untouched; never stored (the membrane). | Plain; the temporal-trust sibling of `salience` (relevance). |
| **`situation` lens** | A `materialize`/`snapshot` lens for re-entry: the standing-truth fold ∪ only the **live** events anchored to the scope, with closed history dropped. The middle path between `current_state` (no events) and `what_happened` (all events). Derived every read, nothing stored. | Plain; "what's the situation here" reads in fiction and reality alike. |
| **live thread** | An event still worth surfacing on re-entry: one with an **open thread** (an unresolved winner with no `resolved_by`) **or** a **surviving effect** (a state it produced still un-superseded). The exhaustive partition of engine-knowable present relevance — a settled current fact or an open current question; anything else is host judgment. Anchored by where the live effect sits (walk back via `caused_by`), never by who participated. Computed, never stored; "dead" means "left no surviving effect," so suppressing it is correct, not lossy. | Plain. |
| **`Degradation`** | The named failure class: served state contradicting the buffer — drift, contradiction, mutated canon. The test suite's core negative assertion is "no degradation." | Trek: buffer/holomatrix degradation. Systems: data degradation. |
| **`Frame`** | Perspective scope on every assertion: `canon`, `knows:<entity>`, named frames. Carries knowledge, contested truth, and privacy by structural absence. | RDF named-graph heritage; kept plain deliberately. |
| **`Thunk`** | An explicitly unresolved aspect with a resolution policy. Forced exactly once; memoized forever. Thunks can move without resolving. | CS-canonical (lazy evaluation). |
| **`deny` thunk** | The *established-unknowable* state of the unknown: an `unresolved` aspect whose policy refuses resolution, carrying a reason. A positive assertion that a thing is canonically unknown (the mystery box). Distinct from an absent row (unestablished) and a stored tag (a membrane breach). | Plain. |
| **relational absence** | The doctrine (whitepaper A6) that the unknown is never stored or inferred — only the computed gap between two populations of present facts, across **frames** (`frame_diff`; the N-observer knowledge lattice) and **time** (freshness = `now − t`). | Plain. |
| **membrane-test** | The guard: *could the engine recompute this row from other present facts? then it is derived and must never be stored — only an irreducible observation may be a fact.* Sibling to RFC-001's rejection-test. | Plain (cell membrane: derived stays out of the log). |
| **`frontier`** | The explicitly-unresolved region: the thunk table plus everything below the resolution floor. Where nothing has been established, the system serves no invented detail. | Robotics-canonical (occupancy-grid mapping); heritage is the lidar ingestion parallel. |
| **`delta`** | A `value_type` for a signed numeric increment. It is admitted like any other row and only folds into totals for attributes declared `accrue`. | Plain math/database vocabulary. |
| **`accrue`** | A fold policy for fungible quantities: latest absolute numeric baseline plus later signed deltas. | Accounting-canonical. |
| **`quantity` / `ledger`** | The derived numeric total / the append-only rows that produced it. Totals surface through `FoldResult.quantity` and `Materialization.quantities`; the ledger remains ordinary assertions. | Plain accounting. |
| **`Anchor`** | Composite identity signals on an entity: names/aliases, roles, recurring locations, distinguishing features. | Plain. |
| **`Scene cursor`** | The ingest-time "where is the narrated action happening" pose. The largest single precision multiplier in ingestion. | Heritage: lidar pose estimation, not Trek. |
| **`arch`** | The operator's inspection CLI: dump the buffer, query as-of, audit provenance — without touching the world. | Trek: "Computer, arch!" — the operator's control interface inside the simulation. Allowed in code as a tool nickname, not an API symbol. |

## Doc glosses (metaphor layer — docs and README only, never code)

| Gloss | Maps to | Canon note |
|---|---|---|
| *a pattern buffer that never degrades* | The project thesis | *Relics*: Scotty survives 75 years suspended in a pattern buffer rigged against degradation, rematerialized exactly as he entered. The drawer test, personified. |
| *a holomatrix* | A `World` | The complete structured representation of one program; see *The Swarm* for what degradation does to one. Rejected as a code symbol (fails the double-read); preserved here as the canon mapping. |
| *a ship in a bottle* | The portable `.world` file | *Ship in a Bottle*: Moriarty's entire persistent universe, self-contained in one box. A world's durable identity is one file plus its policy row — copy it, ship it, archive it. |
| *you see the grid* | The `frontier` | The empty holodeck grid: bare substrate visible wherever nothing is materialized. "Where nothing has been established, you don't get invented detail — you see the grid." |

## The decoder paragraph (for the README)

> The buffer holds the pattern; materialization is re-entry; degradation is the failure we exist to prevent; the arch is how the operator steps outside the world to inspect it; and where nothing has been established, you see the grid.
