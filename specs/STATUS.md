# specs/ — status index (authoritative)

The per-file `**Status:**` line in each spec is an **authoring-time snapshot** (where
the spec stood mid-review) and is preserved for its review lineage. **This index is
the authoritative current state.** A spec marked *Shipped* has its feature live in
`src/patternbuffer/` with tests; browse the spec for the design and the whitepaper
§25 for the consolidated architecture.

_Last reconciled: 2026-07-09._

## Shipped — feature live in the engine
| Spec | What it shipped |
|---|---|
| SPIKE-V1 | The engine spike: `PatternBuffer` + derived indexes + classifier + projector + resolver + `refer()` tier 1 |
| INGEST-V2 | Registry-first ingestion (whole-doc scaffold → parallel extraction → audited single commit) |
| INGEST-LATENCY-V2 | `classify` modes, the read-only `extract()` seam, cursor-authoritative ingest |
| INGEST-HARDENING-V1 | Edge-granular skip receipts; the authority-gate ordering |
| NUMERIC-QUANTITIES-V1 | `accrue` fold, `delta` rows, numeric predicates |
| EXACT-DECIMAL-QUANTITIES-V1 | `Decimal` + the `$decimal` tagged scalar; exact-money folds |
| ATTRIBUTE-SEMANTICS-V1 | Declared attribute semantics as data (the RFC-001 mechanism) |
| CLASSIFIER-EVENT-SAFETY-V1 | EVENT assigned structurally; the model restricted to non-erasing classes |
| CONFIDENCE-V1 / CONFIDENCE-MULTIFRAME-V1 | Derived trust over a functional key; multi-frame effective-knowledge |
| SITUATION-LENS-V1 | The re-entry lens (standing truth ∪ live threads) |
| WORLD-RETRIEVAL-V1 / V2 | `neighborhood`, salience read, `aggregate`, multi-frame `frame_diff` |
| AKA-CORRELATION-V1 | The non-collapsing `aka` identity relation + `state_union` |
| IDENTITY-RECALL-V1 | The global `reconcile()` finalize pass |
| MERGE-RECONCILE-VERB-V1 / V2 | Host `merge`/`confirm`/`reject`/`distinct_from`, structure-first individuation |
| TRIAGE-CONTEXT-V1 | Structured `auto_decline` context on proposals |
| SHAPE-FIX-V1 | `adjudicate_deferred`, `retype`/`typing_conflicts`, durable-contradiction veto, malformed-id gate, `pov` |
| PLACE-FEATURE-ABSTRACTION-V1 | The `part_of` composition axis (`features`/`composition`) |
| WHO-KNOWS-INVERSE-V1 | `who_knows` (the frame-transpose read) |
| AWARENESS-READS-V1.1 | `snapshot(correlated=/features=)` projection flags |
| PATH-TEMPORAL-V1 | As-of-aware `path()` |
| PORCELAIN-V1 | The frozen host contract (`porcelain-v0.1`, additive-only) |
| BOUNDED-READS-V1 | `entities()` roster + `facts()` frame-scan |
| BUILD-SESSION-V1 | `begin_build`/`seal_build`/`abort_build` + the `build()` sugar |
| AXIS-HEAD-V1 | `axis_heads()` (two-axis high-water mark) + `ingest_structured(at=)` |
| INGESTION-FIDELITY-V1 | `fidelity_audit()` — the structural-gap read (coreference metric + gaps) |

## Ratified RFCs — decisions in effect
| RFC | State |
|---|---|
| RFC-001 attribute-semantics-as-data | Ratified → shipped as ATTRIBUTE-SEMANTICS-V1 |
| RFC-002 the-unknown | **Ratified** (Kernos + Construct + Codex); the doctrine of the unknown (whitepaper A6) |
| RFC-003 edge-traversability | Ratified → shipped as `route`/portal/traversal-policy |

## Eval / process docs — executed, not features
| Doc | State |
|---|---|
| MICRO-EVAL-V1 | Executed — **10/10** on the reality-divergence battery (2026-06-12) |
| LIVE-FINDINGS-V1 | Addressed — a host live-findings batch, folded into the shipped fixes |

## Open — drafted, not yet implemented
| Spec | State |
|---|---|
| MCP-WRAPPER-V1 | **DRAFT** — the porcelain over MCP (engine-independence proof, non-Python). Awaiting greenlight → Cx review → implement. |
