# specs/ — status index (authoritative)

The per-file `**Status:**` line in each spec is an **authoring-time snapshot** (where
the spec stood mid-review) and is preserved for its review lineage. **This index is
the authoritative current state.** A spec marked *Shipped* has its feature live in
`src/patternbuffer/` with tests; browse the spec for the design and the whitepaper
§25 for the consolidated architecture.

_Last reconciled: 2026-10-09 (the October self-audit's holds fix and batches A–E pbr-GREEN and merged, C without its §7; R22 merged; R23's pass-0 baseline recorded 2026-10-10 — `docs/AUDIT-2026-10.md`, `docs/HANDOFF-2026-10-09.md`)._

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
| FOLD-CORRECTNESS-V1 | Audit batch A: one recency key (0.0 is a time), identity-aware tie tests, stale ties never outvote a later move, evidence rank across every durability class (STATE ∪ DISPOSITIONAL in one fold; same-stamp STATE outranks a habit; tied habits coexist), the establishing view stays at rest, numeric time values at the gate, the private containment key kept inside. Whitepaper A18 |
| GATE-INVERSE-ALIAS-V1 | `holds`/`wearing` swap direction at the gate (entity values), stay literal for text, and never resurrect as plain renames; a porcelain-only recipe finds pre-fix inverted rows for host repair. Whitepaper A19 |
| GATE-AUTHORITY-V1 | Audit batch B: the gate decides by authority, settled before an item's first write; every other refusal is a typed skip receipt from one vocabulary; mechanism rows (`retracts`, `resolved_by`, `canonicalized_from`, `learned_at_wallclock`, `source_valid_from`, `correction_proposal`) count only with their owner's mark and are refused as items; a raw `same_as` is the guarded merge, canon-only (`same_as_not_canon`); one normalizer; declarations validated; id-shaped typos on entity-valued predicates skip; `p.ingest()` receipts its skips; one number rule for times and `confidence`. Whitepaper A20 |
| FRAME-SCOPED-IDENTITY-V1 | Audit batch C: identity is canon's (`same_as`/`maybe_same_as`/`distinct_from` canon-only at the gate; every identity decision reads canon), names and aliases are read in their own frame (`by_alias`/`refer` take a frame), `aka` vetoes act on whole correlation groups and block auto-merge, `identity_conflicts()` (MCP tool 40), `open_conflicts` computed on read, snapshot existence follows perspective, `retype(absorb=)` refuses a contradicting kind. §7 (`knows:` frames follow merges) is held for Kabe's gate g3bf5da; its r1 build is on `hold/frame-scoped-identity-v1-r1`. Whitepaper A21 |
| REFER-LEARNING-V1 | Audit batch D: `refer` learns a word, never a pick. Only a scoped vocabulary miss that tier 2 maps onto one entity writes, as a `learned_alias` in the call's frame (bookkeeping, never identity); tier 1d reads it back only after authored vocabulary found nothing and only where its entity is in scope; pinned reads, `learn=False` and `ask` never write; tier 1 reads as of the caller's log position; aliases match like names; `owned_by` returns the owner; legacy `refer:tier2:` aliases read as words. Whitepaper A22 |
| READ-SURFACE-V1 | Audit batch E: the porcelain reads what the gate writes. A host durability pin (`attr:<name> · durability`); `fold_policy: last_write` given its meaning and `move` removed; one attribute name on both sides of the gate (`canonical_attribute`); `state()` serves the whole key (`values`, `conflicting_facts`, status `unresolved` for a placeholder); `who_knows` matches the folded value; `ask()` has one effective time (the caller's `as_of` is a ceiling) and binds the asker's own words first; a world file carries its physics (an immutable physics row; reopening runs it, a mismatch raises); `frame=`/`asserted_as_of=` on the reads; a porcelain `refer`; MCP tools 41-42. `events()` from one reader is R22 (EVENTS-ONE-READER-V1). Whitepaper A23 |
| EVENTS-ONE-READER-V1 | Roadmap R22: every event read goes through one reader. Structural event rows become classification-independent records that `events()`, `in_transit()`, the lenses and `neighborhood()` share; event rows never fold; `state()` on an event entity answers from its record. Whitepaper A24 |
| PASS0-GRADER-V1 | Roadmap R23 (measurement only, no engine change): grades pass-0's registry against the gold `fixtures.ENTITIES` (coverage, fragmentation, fusion, B3 linking P/R/F1). First baseline, two runs: `evals/results/2026-10-10-r23-pass0-baseline/REPORT.md` |
| ALIAS-INDEX-V1 | Roadmap R24 Part A (harness only, engine unchanged): a deterministic alias index between pass-0 and pass-1 reporting ambiguous strings, a kinship/address stoplist, escape candidates, distinctness evidence and merge candidates; `Pipeline(alias_slice=)` off by default. Part B (identity rows) waits on gate g3bf5da |
| BUILD-TIMINGS-V1 | Roadmap R26 (harness only): per-stage build timings; `Pipeline.pass0(parallel=, glean=)`, both off by default. Measured: parallel pass-0 is ~2.7x faster but fragments the registry; stays off until the merge gate (R25) |
| SECOND-WRITER guard (fix) | One live World per file, enforced: a buffer that sees SQLite's `data_version` move (another connection committed) raises `SecondWriter`, latching; the unit authorizer admits only that read-only pragma. Not multi-writer support. pbr GREEN 2026-10-10 |
| RESOLVE-REQUEST-V1 | A `patternbuffer_resolve` call carries a `ResolveRequest` (entity, aspect, kind, inherited and declared constraints, as_of, frame, policy) on its schema object (`TaskSchema`, byte-identical JSON); code generators read it with `task_request()`. E2 of the unified world access structure. pbr GREEN 2026-10-12 |
| R21 indexes split | `indexes.py` becomes the package `indexes/` (`_core`, `fold`, `walks`, `knowledge`, `events`, `neighborhood`, `routes`), with one `Indexes` façade and every name re-exported. Five private reach-ins get public names, with aliases kept. Byte-identical: 165 construct worlds, about 1.79M reads, 0 differences. pbr GREEN 2026-10-12 |
| RESOLVE-UNMARKED-V1 | E1: `attr:<aspect> · resolvable_for · <kind>` opens an aspect to invention. `resolve()` in an opted-in story world plants the resolver's own `generated` placeholder and forces it in one atomic unit (timeless under a CONSTITUTIVE or DISPOSITIONAL pin, otherwise at the cursor). Porcelain `resolve(at=)` poses the cursor as the write verbs do; `planted` and `undeclared` appear only in opted-in worlds, and worlds with no declarations answer byte-identically. pbr GREEN 2026-10-12 |
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
