# specs/ — status index (authoritative)

The per-file `**Status:**` line in each spec is an **authoring-time snapshot** (where
the spec stood mid-review) and is preserved for its review lineage. **This index is
the authoritative current state.** A spec marked *Shipped* has its feature live in
`src/patternbuffer/` with tests; browse the spec for the design and the whitepaper
§25 for the consolidated architecture.

_Last reconciled: 2026-07-29 (all three of that day's tracks pbr-GREEN on spec and code)._

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
| MOVED-EVENT-V1 | Movement as a reified `kind=moved` event (`agent`/`origin`/`destination`/`manner`), `literal` never-invent endpoints, the prose-mode coordinate pass, `in_transit()`, the additive six-key `events()` payload. MCP verb 38 |
| ATOMIC-ACTIVATION-V1 | All-or-none activation: `commit_set(ops)` + `ingest_structured(atomic=True)` over a unit-of-work behind a deny-by-default capability facade and a provenance-gated SQLite authorizer; `AtomicAbort{cause,skipped,error}`; fail-closed poison as an independent software gate. MCP verb 39 |
| SOURCE-IDENTITY-V1 | A source class carries its source's *identity* — distinct documents corroborate when agreeing and raise §7.2 cross-source flags when disagreeing instead of silently last-write-wins. Ids canonicalize through the identity closure; the class is a canonical composite, never a spelling-selected member; conflict parties are computed against the served value |
| MCP-WRAPPER-V1 | The porcelain over MCP: 39 deterministic tools (37 at authoring; `in_transit` and `commit_set` added by the two tracks below), `[mcp]` extra, `patternbuffer-mcp` stdio server (engine-independence beyond Python) |

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
| *(none)* | — |

## Open design questions — no spec, awaiting a founder disposition
| Question | Where it came from |
|---|---|
| **Undeclared-origin pooling** (SOURCE-IDENTITY-V1 §6) | Rows with no declared `source` all pool into one `direct` class, so N independent observations agreeing score `corroboration 0`. Pooling undercounts; per-row origin would *overcount* wherever echoes are undeclared. Construct confirms no host leans on corroboration scoring yet, so it can be decided on merit |
| **pbeo take-back: take 3 / adapt 3 / add 1** | A closed external programme's findings — coreference-by-declaration as *prevention*, decline-decays-like-a-claim, `explicitly_declined_by_source`, retraction-vs-supersession, premise decay, attestation value-scoping. Not adopted; Construct has logged the host-shaped ones against its own roadmap |

**Settled since, not open** — recorded so neither is reopened from this index:

- **`corroborated_by` listing the winner as its own corroborator** (pbr `<1766884f…>`): leave as
  is. The resulting `corroboration: 0` on a two-row refinement pair is **intended, not an
  undercount** — CONFIDENCE-V1 defines corroboration as *strict same-value* evidence, pinned by
  `test_confidence.py::test_corroboration_is_strict_not_approximate`. The self-reference is
  acknowledged as awkward representation only; if ever cleaned up, decouple refinement lineage
  from strict-value confidence rather than redefining the tuple in place.
- **Empty retract `reason`** (pbr `<ba11caff…>`): `str` including `""` is contract-valid. The
  shared `TruthMaintenance.retract` path accepts it and the MCP schema has no `minLength`, so
  tightening only `commit_set` would break shared-path fidelity. If revisited, it goes as one
  spec across standalone retract, `commit_set` and MCP together, with an explicit whitespace
  ruling.

*(MCP-WRAPPER-V1 moved to Shipped: spec GREEN via inbox-Cx 529 after a BLOCKED
round; implemented as `patternbuffer.mcp` + the `[mcp]` extra + the
`patternbuffer-mcp` entry point.)*
