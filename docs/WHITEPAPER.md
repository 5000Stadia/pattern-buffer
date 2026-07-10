# pattern-buffer

> **A pattern buffer that never degrades.** One append-only log of perspective-scoped, time-indexed assertions about entities; every other structure — current state, space, knowledge, history, the rendered world — is a disposable projection over it. Fiction simulation and real-world tracking are the same machine under one policy switch.

**Status:** Founding white paper. This is the canonical, comprehensive design reference: the framework-agnostic Assertion-World Model design (June 2026) integrated with every refinement from the subsequent design sessions. It supersedes the earlier standalone design documents; their lineage is noted in §24.

**Genesis note:** This design originated from a domain-neutral question — *what database structure models a dynamic world's details, from a real household to a holodeck?* — and independently converged on the substrate principles of the Kernos project (append-only truth, derived disposable views, provenance discipline, perspective by structural absence). That convergence from an unrelated starting point is treated as evidence the architecture is load-bearing rather than stylistic.

---

## 1. What this system is

A storage and retrieval substrate that lets a language model maintain a **complete, queryable, durable model of a world** — its places, objects, people, relationships, histories, and unknowns — such that:

- Any state question ("what is in the drawer," "where was the badge at 23:40," "what does Marn know") is answered by a **deterministic query**, never by re-reading or re-inferring over prose.
- The world **accretes**: details established once are canon forever; details never established are explicitly unresolved, not silently absent.
- The world is **re-enterable**: a cold instance with no history can load a materialization and stand inside the world coherently.
- The same substrate serves **authored fiction** (where the model *is* the truth) and **real-world tracking** (where the model is a *belief about* the truth), differing only in resolution policy and provenance discipline.

The governing insight: **a narrative is a lossy serialization of world-state plus voice; ingestion is deserialization.** Prose was never the world — it was a transmission format for one. After deserialization, the source text is demoted from retrieval substrate to texture asset. The refined claim: **state-complete, style-anchored, meaning-lossy** — and meaning-lossy is acceptable because the renderer regenerates meaning at read time the way a musician regenerates music from a score.

The defining demonstration (the **drawer test**): a player places a pipe in a drawer in session 12 of a campaign. Two hundred sessions pass without mention. At retirement, the player opens the drawer — and the pipe is there, exactly as placed, retrievable in milliseconds with the original moment's full history behind it. No maintenance was ever performed; in this architecture, **silence is persistence**, because state is folded from the log, never re-inferred or kept alive by mention.

---

## 2. Foundational principles

These are load-bearing. Every later mechanism is a consequence of one of them.

**P1 — The log is the only thing that exists.** One append-only assertion log per world is the sole source of truth. Current state, containment trees, durability classes, identity tables, knowledge frames, rendered briefings — all are derived, disposable, and rebuildable from the log. No judgment (classification, identity matching, gap-filling) can corrupt canon, because judgments live only in derived layers.

**P2 — Store only what cannot be derived; derive everything else.** Location is one containment edge; "the box is empty" and "Morpheus is wearing the jacket" are query results, never stored fields. The moment a derivable fact is stored, two sources of truth exist and desynchronization becomes possible. This single discipline eliminates the dominant failure mode of stateful systems.

**P3 — Nothing exists until referenced; once referenced, it is canon forever.** Unreferenced detail is a memoized lazy thunk: an explicitly stored *unresolved* aspect. Reference forces resolution exactly once; the result is cached permanently. The world condenses where observed and stays condensed. Deliberately unobserved branches (the door the protagonist walked away from) are legitimate, stable states — not gaps to fill.

**P4 — Perspective is structural, not behavioral.** What an agent knows is defined by which assertions exist in its frame, not by instructions about what it may say. An agent cannot leak what was never in its window. The same mechanism carries character knowledge, contested canon, and privacy.

> **The doctrine of the unknown (A6, sharpening P2/P3/P4; RFC-002, ratified Kernos+Construct+Codex).** The system discovers what *is* there; it never presumes, invents, or stores what is not. The unknown has three positive states — *unestablished* (no row → an honest `unknown`), *established-deferred* (an `unresolved` thunk), and *established-unknowable* (a `deny` thunk + reason, e.g. the mystery box). **Absence is relational, never absolute:** it is never stored or inferred, only ever the computed *gap between two populations of present facts* — across **frames** (every observer is a frame; `frame_diff` between any two gives the who-knows-what lattice for N observers, computed never stored) **and across time** (freshness/staleness is `now − t`, derived never stored). The guard is the **membrane-test**: *could the engine recompute this row from other present facts? then it is derived and must never be stored — only an irreducible observation may be a fact.* Staleness, current-confidence, salience, "X doesn't know Y," presumed-empty are all recomputable → none stored. **Non-goal:** no materialized multidimensional knowledge grid; knowledge is opt-in and sparse, recorded only where load-bearing.

**P5 — Provenance is the immune system.** Every assertion carries how it came to be known. Authored canon, observation, inference, assumption, and system-generated fill are permanently distinguishable. The only unforgivable operation in the entire system is a fabrication entering the log marked as stated truth.

**P6 — Events are scaffolding; the world is the precipitate.** A plot, a conversation, a sensor stream — these are authoring traces. What the system keeps and serves is the residue they leave: the furnished, re-enterable world. The trace is preserved (as EVENT rows and provenance) but the deliverable is the fold.

**P7 — LLMs at the boundaries only.** Extraction-in, reference resolution, thunk resolution, and rendering-out are language-model operations. Everything between — storage, supersession, graph walks, folds, identity bookkeeping — is deterministic code. State questions cost milliseconds, not tokens.

**P8 — The log doesn't care where truth comes from; the gate does.** *(Added in design sessions.)* All mutation — user statement, agent tool result, ingested document, scheduled process, NPC off-screen action, GM improvisation — enters through the same small set of authorized writer roles (ingestor for evidence, resolver for invention, deterministic executor for pre-authored effects). New sources add provenance vocabulary, **never** new write authority. Source diversity lives in provenance; the trust surface never multiplies.

---

## 3. The two primitives

Everything reduces to two primitives. Every domain concept — place, person, object, era, status, relationship, story thread, belief, rule — is a *pattern over* them, never a third primitive. (Three maximally different worked products in Appendix A required zero new primitives; this is the standing proof-of-shape.)

### 3.1 Entity

A stable, namespaced identifier with a kind.

```
entity_id : "person:marn" | "place:kitchen" | "obj:ml350" | "event:badge_entry_2340"
            | "prop:heaven" | "process:cistern_depletion"
kind      : the type. Carries default expectations (a room has walls and lighting;
            a person has a build; a cantina has a bar) used only for rendering fill,
            never asserted as fact.
```

Anything referenceable is an entity — including events, propositions, and processes. Reifying occurrences and claims as entities is what lets causality, belief, and dispute be ordinary edges.

### 3.2 Assertion

One fact. Append-only. Never edited.

```
assertion:
  id          : stable assertion ID — assertions are themselves addressable entities
  entity      : subject entity ID
  attribute   : predicate ("kind", "in", "connects_to", "color", "held_by",
                "caused_by", "discoverable_via", …)
  value       : a literal (number+unit, string, interval) OR an entity ID
  valid_time  : interval during which the fact holds in the world (omitted = timeless)
  frame       : "canon" | "knows:<entity_id>" | named frame   (default: canon)
  provenance  : { source pointer; status; confidence }        (see §7)
  asserted_at : transaction time — when the system learned it
```

**Metadata is reified (assertions about assertions).** Because assertions have IDs, everything *about* an assertion is itself an assertion:

```
A1: (jacket · in · box)
A2: (A1 · superseded_by · A9)
A3: (A1 · source · "ch.2 ¶4")
A4: (A1 · confidence · 0.85)
A5: (A1 · last_confirmed · 2026-05-30)
```

Consequences: retraction, supersession, confidence decay, classification revisions, document trust chains (§7.1), and any future unanticipated metadata are ordinary appends — never schema changes, never edits. (Implementation note: hot fields — time, frame, status — are denormalized into columns for query speed; the *model* remains triples-on-triples, so nothing is ever special-cased.)

**Two time axes.** `valid_time` is when the fact holds in the world; `asserted_at` is when the system learned it. They diverge constantly (a delivery that happened Thursday, read from email Monday; a past event learned today; a future scheduled process asserted now) and both are required for as-of queries and audit.

**Amendment (A1, 2026-06-11):** `asserted_at` is the **log sequence number, permanently** — learn order *is* log order, the total order is what as-of-asserted queries need, and deterministic world builds require byte-identical dumps that wall clock would break. Wall-clock learned-at, where it matters, is an ordinary reified meta-assertion on the row. **Rider (load-bearing):** in `observe_or_unknown` worlds the ingest gate **must** stamp the wall-clock learned-at meta-assertion on every STATE/EVENT write — staleness decay (§15) computes from real time and silently breaks without it; this is a gate invariant with a test, not a convention. Fiction worlds may omit wall-clock entirely.

---

## 4. Relations: the spatial spine

Two relation families over the same nodes, distinguished by cardinality:

**Containment (`in` / `within`) — a tree.** Single parent: a thing is in exactly one place. Location is derived by walking up the tree to a root. Because containment is single-parent, **moving is the only operation**: `relate(jacket, worn_by, morpheus)` detaches the jacket from the box automatically (the new edge supersedes the old). Two descriptions change — the box derives to empty, Morpheus derives to clothed — and neither was written. There is only ever one source of truth for "where is the jacket," so dependent descriptions cannot disagree.

**Passage (`connects_to` / `adjacent_to`) — a lateral graph.** Many-to-many: the hallway touches four rooms. Containment answers "where is X"; the lateral graph answers "can you walk from here to there." A world with the tree but not the graph is furnished but untraversable.

Fixtures vs. movables: containment of a movable is mutable state; containment of a fixture (the fireplace in the wall, the staircase) is part of what the place *is*. This distinction is adjudicated by the durability classifier (§5), with a named sub-rule, because it is the single most common ambiguity.

**Absence is free.** Under the projection's closed-world stance (§13), "Morpheus has no jacket" is never stored — not-present-in-the-wearing-relation *is* the absence. When he puts one on, the absence ends because the relation now has a member. (Distinguish this from **stated absence** in tracking mode — "I don't have the nipples in the van" is real observed information and is stored as an explicit negative STATE, distinct from unknown. See Appendix A.1.)

---

## 5. Durability: the four lifetime classes

Every assertion is classified by lifetime. The classes are orthogonal to attribute and frame; they answer "how long does this kind of fact live, and which materializations want it?"

| Class | Answers | Examples | Lifetime semantics |
|---|---|---|---|
| `CONSTITUTIVE` | what the thing **is** | "221B is a room"; the fireplace in the wall; era = Victorian | Permanent unless the world is re-authored. Never compacted out of a materialization. |
| `DISPOSITIONAL` | what it **tends** to be | Holmes plays violin; the cantina serves no droids; Dale restocks PEX on Mondays | Long-lived, defeasible, overridable by stronger later evidence. |
| `STATE` | what it is **right now** | the window is open; Holmes is agitated; the car is in the driveway | Valid-time bounded; superseded by a later assertion on the same (entity, attribute, frame) key. |
| `EVENT` | what **happened** | the dollar handoff; the badge entry at 23:40 | Immutable past point/interval; causes state transitions; carries `caused_by` edges. |

**Durability is an index, not truth (P1).** The class is a judgment *about* a fact. It lives in a rebuildable sidecar keyed by assertion ID — never baked into the log. A misclassification is repaired by re-running the classifier over the untouched log.

### 5.1 Classifier

`classify(assertion, world_context) → { durability, class_confidence }` — largely an LLM judgment over linguistic signals, with deterministic guardrails:

- **Signals:** copula of identity/kind and structural containment → CONSTITUTIVE. Habitual present / role language → DISPOSITIONAL. Stative-at-a-moment → STATE. **The model judges only this standing-durability spectrum.** (Amendment A8, 2026-06-18: occurrence-ness — EVENT — is assigned **structurally**, never sampled by the model: `event:`-reified entities, `caused_by` edges, and host event/structural declarations are the deterministic guardrails that mark EVENT. EVENT is the one class that *erases* a row from every fold, so a model flip STATE→EVENT is a silent read-completeness failure; the model is therefore restricted to the non-erasing classes, with ambiguity defaulting to STATE. Genuine occurrences arriving as flat non-`event:` rows are an ingestion/host-structure gap to fix at the source, not something the durability model should repair by disappearing the row. See CLASSIFIER-EVENT-SAFETY-V1.)
- **The mutability test** resolves most ambiguity: *could one event flip this without re-authoring the world?* → STATE. *True at every moment unless rewritten?* → CONSTITUTIVE. *Generally true but defeasible?* → DISPOSITIONAL.
- **Containment sub-rule:** movable → STATE; fixture → CONSTITUTIVE. (The box on the passenger seat vs. the glovebox in the dashboard.)
- **Accrual promotion:** repeated STATE observations of the same (entity, attribute, value) promote to DISPOSITIONAL. Promotion frequency is also the source of the *salience baseline* — "today he seems beat up" is only computable against a stored normal. Classification is therefore a maintained index, re-derived as evidence accrues, not a write-once stamp.
- **Asymmetric-cost defaults.** Misclassification costs are not symmetric. STATE-misread-as-CONSTITUTIVE bakes a transient into the permanent set (Holmes agitated forever); CONSTITUTIVE-misread-as-STATE risks supersession of structure (the room loses its fireplace). Defaults: ambiguous *properties* → STATE; ambiguous *fixture containment* → CONSTITUTIVE; low `class_confidence` on CONSTITUTIVE verdicts triggers review, because those silently corrupt every future materialization.
- **`world_defining` escape hatch.** Some STATE is constitutive *for a given world* ("a city under siege," "post-collapse era"). An explicit pin lets the establishing materialization always include it. The CONSTITUTIVE/STATE line is sometimes an authorial choice, not a linguistic one; the system represents the choice rather than guessing it.
- **Re-classification is monotonic-safe only upward.** STATE→DISPOSITIONAL accrual is silent. New text *contradicting* a CONSTITUTIVE assertion raises a truth-maintenance flag — never a silent rewrite — so the world cannot mutate between reloads without a trace.

---

## 6. Frames: one mechanism for perspective, dispute, and privacy

The `frame` field scopes every assertion. Four needs, one mechanism:

1. **Canon** — the default frame; the world's ground truth (in fiction, the author's truth; in tracking, best-evidence reality).
2. **Knowledge frames** — `knows:marn` holds exactly what Marn knows. An agent's epistemic state *is* the set of assertions in its frame. Mystery, secrecy, dramatic irony, and information asymmetry are structured data, not renderer discipline (P4). An agent instantiated with only its frame **cannot** leak canon.
3. **Contested truth** — the same (entity, attribute) holds different values in different frames with zero contradiction: an official story vs. actual events; the 1977 vs. 1997 cut of a scene; two characters' irreconcilable beliefs about the afterlife. Nothing overwrites anything; the projector serves whichever frame is loaded.
4. **Privacy** — a frame boundary is an access boundary. Sensitive rows (occupancy, schedules, valuables) are frame-scoped, and consumers receive only frames they are entitled to.

**The absence discipline:** when a consumer is served a frame, out-of-frame assertions are *absent* — not redacted, not marked, simply not present. Filtering happens at source. This is what makes the guarantee structural rather than behavioral.

**Dramatic irony is a computable quantity** *(added in design sessions)*: the canon-minus-player-frame delta is an ordinary query. What the player doesn't yet know is enumerable — which is the closest thing to a real instrument the unsolved pacing problem (§14) has.

Belief assertions interact with truth maintenance: an inferred belief carries its justification (`believes(linda, assault(man), justified_by=injured(man), status=hypothesis)`); if the justification is later retracted, the belief is flagged for retraction — a justification-based truth-maintenance discipline, applied only within frames.

---

## 7. Provenance: the vocabulary of how-known

Every assertion carries a status:

| Status | Meaning | Who may write it |
|---|---|---|
| `stated` | Authored canon: the source text or the authoritative user said it | **Ingestor only** |
| `observed` | Directly perceived (tracking mode: a confirmed observation; includes document observation, §7.1) | Ingestor only |
| `inferred` | Derived from evidence, with a justification pointer | Ingestor / truth-maintenance |
| `assumed` | A working assumption, explicitly provisional | Ingestor, flagged |
| `generated` | Invented by the resolver under canon constraints (fiction fill) | **Resolver only** |
| `default` | Kind-default used for rendering coherence; never a fact claim | Projector only, render-time |
| `retracted` | Withdrawn; preserved in the log, excluded from folds | Truth-maintenance |

Plus a confidence value, and — in tracking mode — `last_confirmed` with time-decaying confidence (§15).

Hard rules: `generated` and `default` never masquerade as `stated`; promotions across statuses are explicit meta-assertions; and in tracking mode kind-defaults may *render* but are never *promoted* — the store must always be able to say "unknown" rather than confabulate reality.

### 7.1 Document trust chains *(added in design sessions)*

Non-conversational evidence (an email order confirmation, a calendar entry, a sensor reading) is a **provenance refinement, not a new status.** The system *observed the document*; the document *claims* the fact — a two-hop trust chain, represented as ordinary reified metadata:

```
(part:fittings_34 · stock(garage) · 20)        STATE  observed
  valid_from: Thu (delivery date)    asserted_at: Mon (when read)
  (↑ · source · doc:email_8841)
  (doc:email_8841 · authored_by · supply_house)
(event:stock_update · requested_by · dale)      ← the ingestion itself is auditable
```

Document-sourced confidence may sit lower than first-person observation and decay differently. The reified-metadata model absorbs each new evidence class with zero schema change — that is what it is for.

### 7.2 Cross-source conflicts *(added in design sessions)*

Supersession-by-key is automatic only within a source class. **Conflicting observations from different source classes on the same key raise a truth-maintenance flag and an ask** ("supply house says 20 arrived Thursday — did that order actually land?"), never a silent last-write-wins. This is proportional caution applied to the write side: routine updates flow; genuine contradictions earn a question.

---

## 8. Thunks and resolution: the lazy world

Unresolved detail is first-class:

```
(obj:box · contents · ⊥ · status=unresolved · policy=<policy> [· constraints…])
```

When a consumer **forces** an unresolved aspect (opens the drawer, asks what's behind the door), the **resolver** evaluates it exactly once and memoizes the result into the log. Future references serve the cache.

**Resolution policy — the one switch.** Set per world (or per subtree):

| Policy | On force | Mode |
|---|---|---|
| `invent_under_canon` | LLM authors content consistent with every CONSTITUTIVE and DISPOSITIONAL constraint inherited from the containing scope (era, genre, owner's character); committed as `generated` | Fiction / holodeck |
| `observe_or_unknown` | Never invents. Resolves only from observation; otherwise remains explicitly unknown | Real-world tracking |
| `deny` / `reserve` | Refuses resolution (e.g., a slot reserved for the player; a sealed authorial gap) | Special cases |

This switch is the entire difference between a worldbuilder and a digital twin. Everything else — the log, the classes, the frames, the projector — is shared.

**Constraint inheritance** is what keeps invention canonical: a resolved drawer in Sam Spade's office inherits "c.1928 San Francisco," "private detective's office," and the owner's dispositions before the LLM writes a word. **Access gating** is what keeps resolution honest: detail resolves only to the level the observer's position grants (police seen at a distance resolve coarsely; the room behind the door they're breaking down stays unresolved if the witness walks away). The narrative instinct to over-resolve — to invent who's behind the door — is the system's most dangerous failure mode and is leashed here, at resolution, and again at rendering (§13).

**Thunks move without resolving** *(added in design sessions)*: an unresolved aspect can change hands, location, or scope while staying unresolved. The BBEG steals the buried cache: the cache entity gets a new containment edge; its *contents* remain a thunk, policy intact, now inheriting new constraints (the hoard, the theft history). When the players eventually recover and force it, the resolver invents under canon that *includes* the theft. Lazy evaluation composes with off-screen action; P3 never bends.

**Resolution floor.** Worlds are fractal; a home decomposes into drawers into objects into components. Each world (or subtree) sets a deliberate floor — rooms / surfaces / drawers — below which thunks are not even instantiated. The floor is a use-case decision made on purpose, not an emergent accident of sprawl.

---

## 9. Reference resolution: `refer()` *(added in design sessions)*

The no-LLM read claim (P7) covers state queries *given an entity ID* — fold, walk, history are deterministic. The step before that — mapping a natural-language referring expression ("the drawer," "the thing he took from the car") onto an entity ID — is **reference resolution**, a genuine fourth boundary operation:

```
refer(description, scope, frame, constraints) → entity_id | candidate_set | underdetermined
```

The read path is `refer → walk`; only the walk is free. `refer()` runs as a **three-tier cascade, cheapest first**:

1. **Deterministic tier (most cases, no model call):** exact name/alias hit; unique-kind-in-scope ("the drawer" when the current scene contains exactly one); and **constraint inversion** — "the drawer with the golden spoon" never resolves "the drawer" linguistically: the spoon's containment edge *is* the answer. Resolve the container by the contained, the owner by the possession, the room by the fixture. A large share of seemingly-ambiguous references carry a constraint that makes them deterministic if the lookup direction is flipped.
2. **Lightweight model tier (only when tier 1 returns >1 or 0):** a strict-contract cheap call judging candidates against anchors, recency, possession, discourse context — returning a **resolution receipt** (candidates considered, signals used, confidence).
3. **Ask tier:** low confidence does not guess — "the desk drawer or the kitchen drawer?" In fiction the clarify is free flavor (any GM does it constantly); in tracking mode a wrong resolution means acting on the wrong reality, so the ask is mandatory. Proportional caution, applied to reads.

**Historical reference:** descriptions whose anchors have drifted ("the blacksmith's boy," now an adult smith) must resolve against *historical* state — an as-of query over the identity anchors themselves, not just current state. The machinery supports it; the tier-2 cohort must know to attempt it.

Resolution events may themselves be logged as discourse-scoped aliases (this conversation's "the drawer" = the desk drawer), with bounded lifetime.

---

## 10. Ingestion discipline: the lidar principles *(added in design sessions)*

The orienting analogy is a lidar unit on a robot vacuum: it maps **only what it actually hits**, with high precision, always knowing **its own pose** — and the map grows as a connected component, inch by inch, from wherever it started. Unscanned space is never painted as wall or floor; it is explicit frontier. Translated into ingestion rules:

- **The scene cursor is the pose.** Ingestion carries a "where is the narrated action happening" cursor at all times. This is the single biggest precision multiplier available, because most referring expressions are scope-local — "the drawer" almost always means *the drawer here*. Discourse scope is part of the observation.
- **Anchor at observed precision, never deeper.** Every new entity attaches to the frontier of the existing map (contained-in or connected-to something already canonical) at exactly the precision observed — never floating, never guessed-finer. "She put the pipe in the drawer," scene cursor at the study → the drawer anchors under the study. No scene context → it anchors under the home, honestly coarse.
- **The frontier is explicit.** Unscanned isn't empty — it's the thunk table plus everything below the resolution floor. Where nothing has been established, the system serves no invented detail. *(Doc gloss: you see the grid.)*
- **Attribute canonicalization at the gate.** An LLM extractor will emit `in` / `inside` / `located_in` across turns, silently splitting one fluent into three supersession keys. Structural predicates are fixed (`kind`, `in`, `connects_to`); domain vocabulary emerges freely (the Cyc lesson) — but **through a maintained attribute-alias canonicalization at the ingest boundary, with receipts.** Centralized name repair; the fold key must never fragment.

**Amendment (A2, 2026-06-11):** the fixed structural predicate set is `kind`, the **containment family** (`in`, `within`, `held_by`, `worn_by`, `carried_by` — declared as one logical fold key, so the single-parent move semantics span the family), `connects_to`/`adjacent_to`, **`caused_by`**, and **`world_defining`**. Anything the §18.1 survival checklist references cannot ride on free vocabulary. The bar for any future addition is the same: checklist semantics depend on it.

---

## 11. Identity: the registry

Identity across non-adjacent references is the hardest problem in the system and the place such systems break in practice. The design gives it a home; it does not pretend to solve it.

- **Anchors.** Each entity carries composite identity signals: names/aliases, roles, recurring locations, distinguishing features. Single-anchor identity (location only) is brittle by design review: the day the man isn't on the stoop, appearance and recurrence must carry the match.
- **Ambiguity is represented, not forced.** Uncertain matches are stored as explicit maybe-same-as edges with the evidence that suggested them, surviving until resolved.
- **Merges are events.** A merge is itself a logged event — auditable and reversible by retraction. A bad merge never rewrites history; it is repaired forward.
- **Late binding.** "A man entered" in chapter 1 merges with the named character of chapter 3 by appending identity assertions, leaving every chapter-1 row intact and now reachable through the merged identity.
- **Splits and underdetermined anchors** *(added in design sessions)*: the dual of merging. A coarsely-anchored entity ("the drawer," anchored only to the home) is **a spatial thunk** — not wrong, *underdetermined*, recorded at exactly the precision the language transmitted. When the world later grows finer entities (desk drawer, kitchen drawer), the coarse entity becomes a candidate-set holder (`MAYBE_SAME_AS` both) and collapses the way thunks always collapse — on forcing, exactly once: the player retrieves the pipe from the desk drawer, the identity event commits `drawer_1 SAME_AS desk_drawer`, and the kitchen drawer provably never held it. Until forced, the honest answer is available and natural: "your pipe's in a drawer at home — you never said which room." The system refuses to claim precision the language never transmitted.

The registry's shipped surface has grown well past this founding sketch — a third **non-collapsing** identity relation (`aka` correlation, for reveals and dual personas), an explicit **anti-merge** primitive (`distinct_from`), a host-invoked reconciliation/adjudication/**retype** family, and a **durable-contradiction veto** that keeps two entities with contradictory standing facts from auto-merging. The full catalogue is §25.2.

---

## 12. The operation algebra and the role authority matrix

The complete write surface is small:

```
assert(entity, kind)                      bring a thing into existence
set(entity, attribute, value, …)          attach a fact (one assertion)
delta(entity, attribute, signed_number)   append a numeric change for an accrue fold
relate(subject, relation, object)         add an edge; for single-parent relations
                                          this IS the move operation (supersedes prior)
event(kind, agents, patients, t, effects) reify an occurrence; effects are relates/sets
believe(frame, assertion, justification)  write into a knowledge frame
resolve(entity, aspect)                   force a thunk per policy; memoize
retract(assertion_id, reason)             append a retraction meta-assertion
merge(entity_a, entity_b, evidence)       identity merge, logged as an event
refer(description, scope, frame, constraints)   resolve a referring expression (§9)
```

Reads are queries over derived indexes: `locate(x)` (walk the tree), `contents(x)`, `state(e, a, as_of, frame)`, `history(e)`, `path(a, b)` (lateral graph), `describe(e, frame)`, and `materialize(…)` (§13).

**Five roles, strict authority** (roles, not necessarily five processes):

| Role | LLM? | May write |
|---|---|---|
| **Ingestor** | yes | `stated`, `observed`, `inferred`, `assumed` — the *only* path for stated truth; owns identity resolution, the scene cursor, attribute canonicalization, and provenance discipline at the gate |
| **Classifier** | yes | the durability sidecar only — never the log |
| **Resolver** | yes | `generated` only, under inherited constraints; the only invention path |
| **Projector** | no | nothing durable; emits materializations; may mark render-time `default` fills |
| **Renderer** | yes | **nothing.** Prose out, under the leash (§13). New canon never enters through the renderer. |

The separation between resolver and renderer is the design's central guard: the component that *speaks* is never the component that *decides what is true*. A narrator that could mint canon would drift the world a little with every enthusiastic sentence — the precise failure of unstructured LLM roleplay.

### 12.1 Write-path taxonomy for non-user mutation *(added in design sessions; consequence of P8)*

- **Pre-authored clock/process effects** (`fires_when` conditions written at authoring time): the judgment already happened; firing is a **deterministic executor** performing deferred ingestor writes. No new authority.
- **Improvised off-screen developments** (the GM deciding the villain got greedy): routed through the **resolver**, landing as `generated`. Authored-then-fired and invented-under-canon stay permanently distinguishable — which matters years later when someone asks "was that always the plan?"
- **External data streams** (email, calendar, sensors): new *feeds into the singular ingest gate*, carrying document trust chains (§7.1). Never a new write path.

---

## 13. Projection: serving the world

```
materialize(scope, as_of, frame, lens, budget) → materialization
```

*(Naming note: the verb is `materialize` — correct twice over: a database materialized view **is** a derived, disposable projection over a log, and rematerialization is what re-entry is.)*

**Lenses** select durability classes:

- `establishing_set` — CONSTITUTIVE + DISPOSITIONAL + the *establishing* STATE: the first non-event-effect value per (entity, attribute) — the world at rest, before the plot perturbs it. The default for re-entry ("221B at rest," not "221B mid-confrontation"). Honors `world_defining` pins.
- `current_state` — adds STATE folded to `as_of`.
- `what_happened` — the EVENT chain in scope, time-ordered, with causality; the backstory digest.
- `character_sheet` — one entity's accumulated card, frame-respecting.
- `situation` — standing truth folded to `as_of` **∪** the live EVENT activity since a `since` cursor: the re-entry lens for "what's true here now, and what just happened" in one read (SITUATION-LENS-V1; catalogued in §25).

**Algorithm:** select in-scope, in-frame assertions valid at `as_of` per lens → fold STATE by supersession per (entity, attribute, frame) key — *per frame; a belief fold never overwrites canon* → walk the containment tree for the spatial spine, ordered by depth and salience → fill gaps from kind-defaults, every fill marked `default` → resolve forced thunks via the resolver (which feeds new assertions back through classification — the system is closed under its own operations) → shape to budget.

**Numeric quantities:** an attribute may declare `fold_policy=accrue`. Its
fold ignores durability and computes a derived total from the latest numeric
`literal` baseline plus later signed `delta` rows. The total is served as a
quantity, not as a stored assertion; the append-only ledger remains the audit
trail. Integers and floats serve game-grade quantities; **exact-decimal
arithmetic (money, real ledgers) is shipped** — an opt-in `Decimal` value that
folds without float drift, carried through every JSON boundary as a tagged
scalar (EXACT-DECIMAL-QUANTITIES-V1, catalogued in §25).

**The budget invariant:** the CONSTITUTIVE spine is budget-exempt. Compress DISPOSITIONAL color, summarize peripheral STATE, digest EVENT chains — never compact identity and structure. (Anchored summarization with the anchor formally bound to the constitutive layer.)

**Salience is a projection-time ranking, never a stored truth:** recency + reinforcement count + reference frequency + delta-from-baseline, computed from the log, cacheable in a derived index, never authoritative. Durability and salience are different axes: a fact unmentioned for three campaign-years has zero salience and full validity — ranked low until the drawer opens, then served at full confidence.

**Open-world store, closed-world projection.** The store never claims the unstated is false — unknown is unknown (mandatory in tracking mode). The projector commits to closed-world defaults to render one coherent scene (the unasserted lamp is off, drawn off). The reconciliation is positional: open for truth, closed for the briefing, with every closed-world commitment marked `default` so it can never harden into canon.

**The render leash.** The renderer receives the materialization under a fixed contract: describe only what these assertions support; dress `default` fills as ambient detail; introduce **no new named entities or events**; route any forced unknown through the resolver. Two cold instances over the same store must produce *compatible* worlds — identical bound facts, freely varying wording. **Freeze facts; regenerate prose.** Stored wording calcifies retellings; understored facts let retellings contradict. The binding layer is the asserted facts; the free layer is the words.

**Correctness criterion (testable):** `materialize(classify(ingest(W))) ≈ W` — round-trip compatibility up to prose freedom and resolved gaps. Test suites are written against this approximate inverse.

---

## 14. The narrative layer (fiction mode)

Four vocabularies on top of the same row shape — no new primitives:

1. **Character engines.** An NPC is an agent instantiated with: its DISPOSITIONAL rows — drives with priorities, fears, constraints, breaking conditions (`(marn · drive · prevent_panic > protect_self)`, `(marn · breaks_if · confronted_with(door_log + ledger_gap))`); its voice anchors; and **only its `knows:` frame as its entire world context**. Secrecy by structural absence (P4). Without this layer, NPCs are furniture that talks; with it, the renderer improvises in-character behavior down any path the player takes.
2. **The evidence graph.** A mystery is a dependency graph of revelations: `(fact:X · discoverable_via · inspect(obj) | press(person))`, `(fact:Y · derivable_from · {…})`, with a solution sufficiency set (`solution · derivable_from · any_2_of{…}`). Canon is **path-independent**: the original plot is just one traversal; the player can assemble the same truth in any order with equal richness. Discovery moves assertions *into* a knowledge frame; it never changes canon.
3. **Clocks and autonomous processes.** Scheduled and conditional events (`fires_when`) make the world move without the player: the cover-up escalates if the player is observed at the wellhead; the cisterns deplete regardless. Player inaction becomes meaningful — and a fired clock can close a solution path forever.
4. **Style anchors.** Short source excerpts attached to entities as render exemplars — the source prose demoted to texture asset (P6/§1). State queries never touch them; voice quality leans on them.

Honestly open even with all four: **pacing / drama management** — making escalation land and dilemmas arrive with weight — is unsolved in the field. The pragmatic stance: the renderer acts as GM with the evidence graph as its map, the dramatic-irony delta (§6) as its instrument, and a light nudge policy (surface an unwalked thread when momentum stalls). A behavior spec, not a data row.

**The GM-renderer soft spot** *(named honestly)*: NPC agents are frame-scoped structurally — they *cannot* leak. But the GM-side renderer must see canon to run the world, so its no-spoilers guarantee is the render leash: behavioral, not structural. It is the one place in the design where mystery integrity depends on a prompt instead of an absence. Mitigation: discovery (what enters `knows:player`) is gated by the evidence graph, which *is* structural; only narration flavor rests on the leash.

**Amendment (A4, 2026-06-12) — host-side structural mitigation, credited to Construct (the first host):** split the GM into two lanes. A *navigator* reads `plot:`/canon and emits a deterministic direction — it writes nothing and **speaks nothing**; a *narrator* receives a briefing containing zero `plot:` rows (grep-verifiable per turn) — it speaks, and cannot leak the arc because the arc is not in its window. The agent that can leak no longer holds the secret; the residual behavioral surface shrinks to one logged nudge-content pick. This is P4 applied to the GM itself — a design pattern, not an engine change; recorded because it materially shrinks the one hole this section admits.

---

## 15. The tracking layer (real-world mode)

The same substrate under `observe_or_unknown`, with three additions:

- **Staleness.** Mutable STATE carries `last_confirmed` and a confidence that decays on a per-attribute schedule (a parked car's location decays in hours; a couch's position in months). A tracking record is only as good as its last confirmation. Staleness is part of the answer, not hidden behind it: *"last confirmed on the garage shelf June 19 — that's three weeks unconfirmed."* `last_confirmed` is derivable from the transaction time of the latest confirming assertion; decay is computed at materialization time, **never stored** — a judgment, living in the rebuildable layer like all judgments. **Decay is mode-scoped, never engine-global:** fiction worlds run no staleness policy at all; the page is always true. (This is precisely why fiction is the cheap, ground-truthed test mode.)
- **Assumption quarantine.** Kind-defaults render but never promote; wrong assumptions about reality make agents act on falsehoods, so "I don't actually know" is always a representable answer.
- **Privacy frames.** Occupancy, schedules, valuables are frame-scoped from the moment of ingestion; access is structural.

The physical/relational/story triad a real place requires is carried natively: physical = CONSTITUTIVE assertions with metric/material values; relational = entity-valued edges (tree + lateral graph + occupancy/ownership); story = STATE@t + EVENT + recurring DISP. One store, read three ways; a minimum bar for a complete record is one metric per space, the lateral graph overlaid on the tree, and at least one dated event anchored to a place.

---

## 16. Worlds: the unit of everything

*(Consolidated from design sessions.)*

A **World** is the named, individual unit — `eastmere`, `dale_reality`, `okafor_case` — and it is slightly more than its log:

```
World  =  PatternBuffer (the truth: one append-only assertion log)
        + resolution policy  (the one switch: invent / observe / deny)
        + decay configuration (on for tracking, off for fiction)
        + derived indexes    (disposable, rebuilt from the buffer)
```

Policy + decay are, in effect, the world's *physics* — fiction and reality are the same matter under different laws.

**The 1:1 invariant (load-bearing):** every world owns exactly one PatternBuffer; a buffer never holds two worlds; a world never spans two buffers. `world_id` is the partition key for everything. Violating this in either direction produces the two canonical fragmentation failures: the campaign bleeding into the household, or the kitchen existing twice.

**Amendment (A5, 2026-06-16) — lineage vs instance; forks share a `world_id`:** the invariant forbids *co-mingling* (two worlds' rows in one buffer) and *splitting* (one world's log across buffers) — it does not require `world_id` to be globally unique per buffer. A *playthrough fork* (a file copy of a pristine world, diverging at the moment of copy and never re-joined) is a distinct world **instance**, not a second buffer for one world; N such forks may carry the same `world_id`. The id denotes a world's **identity/lineage** (which scenario this descends from); **instance identity is the file**. Isolation is the file boundary, not id uniqueness. `world_id` is a partition key *within and at the boundary of* a buffer — every row carries it, every write is guarded against foreign rows (the `WorldMismatch` check), and a dump is refused if its rows span ids — but the engine keys **no** process-wide cache, registry, resolver, or snapshot index on it (audited). So concurrent same-`world_id` buffers on different files cannot collide, alias, or serve one instance's state to another: they share no in-memory state and each touches only its own file. The fragmentation failures the invariant guards against are intra-buffer (the household and campaign in one log) — never two honest, separate fork files.

**Hosts bind; they never own.** A host's scoping units (workspaces, context spaces, channels) bind to worlds via an adapter-layer binding table (many scopes → one world allowed). Fiction scopes bind to private worlds — hard isolation is *correct* for stories; each story is its own universe. All real-life scopes bind to *the* member's one world, with frames doing the scoping the host expects. (See §17 and hazard §18.1.)

**Worlds are shippable.** A world's durable identity is one file plus its policy row — copy it, send a campaign to a friend, archive a finished mystery. *(Doc gloss: a ship in a bottle.)*

---

## 17. Architecture: the engine and its hosts

```
┌─ INGEST (LLM boundary; the gate) ─────────────────────────────┐
│  scene cursor → extract → canonicalize attributes →           │
│  identity-resolve → classify-confidence → append              │
│  (the ONLY path that can write provenance=stated/observed)    │
└──────────────────┬────────────────────────────────────────────┘
                   ▼
   THE PATTERNBUFFER (append-only; the only truth; SQLite)
   assertions + meta-assertions; one per world
                   │   everything below: derived, disposable, rebuildable
                   ▼
   DERIVED INDEXES (deterministic, no LLM)
   · current-state view  — latest non-superseded per (entity, attribute, frame)
   · containment tree + lateral connects_to graph
   · durability sidecar  — the classifier's rebuildable output
   · identity registry   — anchors, aliases, SAME_AS/MAYBE_SAME_AS, merge/split log
   · thunk table         — unresolved aspects + policies (the frontier)
                   ▼
┌─ SERVE ───────────────────────────────────────────────────────┐
│  refer() (three-tier, §9)  ·  materialize() (lens × frame ×   │
│  as_of × budget, §13)  ·  resolve() (inline, with append      │
│  authority, §8)  ·  render (leashed, writes nothing)          │
└───────────────────────────────────────────────────────────────┘
```

### 17.1 The engine is a library below the host, not a peer beside it

The engine is a self-contained Python package: dataclasses, one SQLite file per world, the operation algebra, derived indexes, the projector. **Zero agent concepts anywhere in it** — no cohorts, no members, no scopes, no turns. There is nothing in it to be host-specific.

**The one thing it needs from outside:** the LLM-boundary roles (ingestor extraction, classifier, resolver invention, refer tier-2) take a single injected callable at construction:

```python
world = World("campaign.world", model=some_callable)   # (prompt, schema) -> json
```

That is the entire harness interface — a parameter, not a framework. A host hands it a two-line shim around its own provider; a script hands it an SDK; a test hands it a stub.

**The discipline that keeps integration simple:** *the engine never calls the host.* The dependency arrow points one way. All host concepts are mapped onto engine concepts by an adapter living in the host's repo, written in the host's idiom. From the engine's side, every host is indistinguishable; from the host's side, the engine is indistinguishable from sqlite3.

### 17.2 Host adapter pattern (reference: the Kernos binding)

What a host adapter supplies — all host-side, none of it in the engine:

- **Binding table:** host scope → `world_id` (many-to-one allowed; see §16).
- **Ingest scheduling:** an async post-turn worker calls `world.ingest(transcript)` on action-bearing turns (turn-cadence, off the hot path), plus a boundary-time reconciliation sweep that catches what turn-time missed. Two cadences, complementary.
- **Read scheduling:** a per-turn push snapshot (entities referenced in the message via `refer()`, their state cards, containment context, active thunks in scope — deterministic, budget-shaped) plus a pull tool for as-of queries, event chains, and forced resolution.
- **The model shim** and frame-entitlement policy (which consumer sees which frames — the host's existing disclosure machinery acting as one consumer policy over frames).
- **Resolution as a tool with role-guarded implementation:** the host's agent may *force* a thunk; it cannot phrase canon into existence — the tool's implementation is the resolver, holding the append authority. The tool boundary is the role boundary.

A later optional wrapper — an MCP server over the same API — makes the engine usable by non-Python hosts and proves the framework-agnostic claim by demonstration. No host requires it; Python hosts import directly.

---

## 18. Embedding hazards: what must survive integration

Cataloged from a deliberate exercise: designing the system first in Kernos-shaped terms, then re-deriving it with no host concessions and diffing the two. Each item names the pressure a host exerts, the failure if yielded to, and the required handling. *(Written host-generically; learned against a real host.)*

1. **Partition unit.** Hosts partition everything by their native scoping unit; one-world-per-scope looks harmless at spike scale and is ruinous at fused-stream scale (one vehicle becomes three partial entities). **Worlds are first-class; scopes bind** (§16). The single most damaging compromise to accept silently.
2. **Write authority vs. the turn pipeline.** Letting the principal/integration agent append directly makes the narrator and the canon-writer the same agent — the render-leash violation. Integration *proposes*; the ingestor *commits*. Role boundaries matter more than process boundaries; distinct auditable pipeline stages with distinct prompts suffice.
3. **The resolver vs. cost invariants.** Hosts push LLM operations out of always-on paths; the resolver gets demoted to an optional depth tool, and either resolution doesn't happen at the moment of forcing (broken experience) or the renderer quietly does it (canon poisoning). The cost invariant correctly applies to the *push snapshot* (deterministic walks); resolution is different in kind — an LLM operation **with append authority** that must run inline when forced. Architect it as a peer of ingest and materialize, with its own budget accounting. (Note: the tension is fiction-only in practice; `observe_or_unknown` never invents.)
4. **Durability vs. existing host labels.** A host's lifecycle vocabulary (identity/structural/habitual/contextual) tempts label-copying — but durability's definition is **operational** (supersession keys, lens selection, budget exemption), not nominal. Implement the contract, map labels after. Hosts typically lack EVENT; it must be added, never approximated by a contextual catch-all, because EVENT carries causality and immutability semantics no fluent class has.
5. **Frames vs. host disclosure machinery.** Flattening frames into member-visibility loses contested canon and NPC knowledge (an NPC is not a member; a canon dispute is not a sensitivity tier); duplicating beside it churns. Recognize the host's gate as a *special case* of frames; frames are the storage mechanism, the host's gate one consumer policy. Preserve the absence discipline — filter at source; absent, not redacted.
6. **Store boundary.** Extending a host's facts store with typed edges remixes two jobs with different cadences (boundary-harvest vs. action-time), different reconciliation (LLM prose merge vs. deterministic supersession-by-key), and different query surfaces (semantic search vs. graph walk) — recreating the stale-sentence RAG failure. Third store, own write path, own indexes; bridging facts are explicit cross-references, never automatic mirrors.
7. **Cadence.** Deferring world writes to the host's boundary-time harvest makes state lag reality by a full compaction span — fatal for games, silently corrosive for tracking. Two cadences, complementary (§17.2).
8. **Salience.** Host roadmaps specify stored salience weights; stored salience hardens judgment into truth (violates P1). Projection-time ranking, cacheable in the sidecar, never authoritative.
9. **Roadmap vocabulary drift.** "A current-state abstraction, not a log" read literally produces a mutable store and unrecoverably loses as-of, audit, and rebuildability (a log cannot be reconstructed from a mutable store after the fact). The deliverable is *a current-state abstraction **served from** an assertion log.* One sentence; the whole architecture rides on it.

### 18.1 The survival checklist

If any item is compromised, a real element of the design is lost, not an implementation detail:

1. Append-only log as the only truth; everything else derived and rebuildable (P1).
2. Derive-don't-store; single-parent move semantics (P2, §4).
3. Thunks as first-class with per-world resolution policy — the one-switch unification (P3, §8) — including thunks-move-without-resolving.
4. Frames with the absence discipline; NPC knowledge by structural absence (P4, §6).
5. The provenance vocabulary with its writer-authority matrix; `generated`/`default` never promotable (P5, §7, §12).
6. Resolver as an inline first-class operation, separate from the renderer; renderer writes nothing (§12, §18.2–3).
7. Worlds as the partition unit; the 1:1 world↔buffer invariant; host scopes bind (§16, §18.1).
8. EVENT as a real class with causality, not a catch-all (§18.4).
9. Two time axes and as-of queries (§3.2).
10. The budget invariant: the constitutive spine is never compacted out (§13).
11. Open-world store / closed-world projection, with `default` marking (§13).
12. `refer()` as a first-class boundary operation with the three-tier cascade and the ask tier (§9).
13. The singular ingest gate (P8): new sources add provenance vocabulary, never write authority (§12.1).
14. The chapter test as the acceptance gate before any real-world stream connects (§19).

Everything not on this list — storage engine, index layouts, worker contracts, naming of host-side components — is legitimately negotiable plumbing.

---

## 19. Evaluation

### 19.1 The chapter test (the spike's acceptance gate)

Fiction is the only domain where a world model grades against printed ground truth:

1. **Ingest** one complete short fiction (seed: *The Last Honest Meter* — entity registry, event spine, frames, thunk table, and evidence-graph sketch drafted in the original design session; **the seed artifact must be recovered and committed to this repo** — it is the chapter test's ground truth).
2. **Delete the prose.** The store is all that remains.
3. **Interrogate** with a cold instance: every tracked object's location at three timestamps; each character's knowledge frame at the climax; one state fact that changed mid-story; two never-opened-drawer resolutions checked for canon consistency; one as-of query over the event spine.
4. **Score** against the text. Failures classify as *extraction* (engineering, fixable) vs. *shape* (theory — revisit this document).

**Scope honesty:** the chapter test validates the **substrate** (store + classification + projection + resolution), not the product. Fiction ingestion reads clean authored prose; tracking-mode ingestion reads sloppy conversational fragments. The honest bridge before any host commitment: a second, tiny eval — ingest a transcript of messy household dialogue, run the same interrogation battery.

### 19.2 Interactive criteria (a later milestone, not the spike)

Across multiple sessions: (a) resolved thunks stay stable — the drawer's contents never change; (b) frame-scoped NPCs never leak out-of-frame canon; (c) the mystery solves by at least two distinct evidence-graph traversals; (d) clocks fire on player inaction. These require the §14 narrative layers and are explicitly **not** spike scope.

### 19.3 Known inelegance: where natural-language retrieval will strain

Named honestly, with classification:

| # | Edge case | Class |
|---|---|---|
| 1 | Vague reference with no discriminating constraint ("where did I put that thing?") — candidate flood, degrades to dialogue | Cohort engineering (fixable) |
| 2 | Fungible quantities ("do I have enough 3/4 fittings for a repipe?") — *stuff* vs. individuated objects; quantity-ledger overlay (stock as numeric STATE, events as deltas) works but is the weakest natural fit in the design | Informational limit |
| 3 | Negation over an open world ("anything dangerous in the basement?") — the store certifies observations and names the frontier; it cannot certify absence beyond observation. Honest, never confident | Informational limit (by design) |
| 4 | Narrative-time expressions ("back before the fire") — as-of needs an instant; resolving fuzzy time = EVENT-spine anchor search with interval slop | Cohort engineering (fixable) |
| 5 | Descriptions with drifted anchors ("the blacksmith's boy," now grown) — `refer()` must resolve against historical state; easy to miss | Cohort engineering (fixable) |
| 6 | Counterfactual spatial-temporal feasibility ("could Vance have made the 23:40 entry from the wellhead?") — needs travel-time attributes prose rarely states | Informational limit |
| 7 | The GM-renderer soft spot (§14) — the one behavioral (not structural) guarantee in the design | Structural compromise, confined to one mode |

---

## 20. Prior art (assembly, not research)

Every component is individually proven; the composition is the novel part. **Datomic** (append-only datoms, as-of) — the log shape. **RDF-star + named graphs + temporal RDF** — reified provenance, frames, valid time. **ECS (game engines)** — entity minimalism at world scale; a save file as a serialized assertion set. **Event sourcing / CQRS** — store events, serve projections (and "materialized view" is the industry's own name for the read side). **Inform 7 / Z-machine / TADS** — tiny relation sets, the containment tree, the single move operation. **BookNLP** — fiction extraction (the weak front end). **Generative Agents** — frame-scoped NPC memory. **PDDL / event calculus** — action effects. **JTMS** — justification-based belief maintenance. **SLAM / occupancy-grid mapping (robotics)** — the ingestion discipline: pose-anchored observation, connected growth, explicit frontier (§10). **Cyc** — the forty-year cautionary tale against pre-enumerating a universal vocabulary: fix only structural predicates; let domain predicates emerge (through the canonicalization gate). **AI Dungeon** — the anti-example this design exists to prevent: generation without persistent state drifts and contradicts itself. A degraded buffer.

**Versus RAG**, the industry default: retrieval over prose serves *descriptions* and re-infers state per query — it can serve chapter 2's location after chapter 9 moved the object, re-pays inference every time, and has no write-back for discoveries. This design is **deserialize-once, query-forever, append-on-discovery**.

**Survey addendum (2026-06; full mechanism detail in `docs/reference/prior-art-survey-2026-06.md`).** Nearest neighbors found: **Graphiti/Zep** (bitemporal knowledge-graph agent memory; four timestamps per edge, episode-backed provenance — but supersession *stored* onto the old edge rather than derived, and no conflict handling: timestamp-wins by design). **XTDB** — the bitemporal database peer; both axes first-class, corrections as new documents (independent confirmation of the §3.2 time model; a database, not a world engine). **Cyc microtheories** — the strongest frames precedent: context-scoped assertions with `genlMt` inheritance, sibling contexts contradicting freely (distinct from the §10 Cyc vocabulary cautionary). **ATMS** (de Kleer) — contested canon as first-class: all consistent worldviews held simultaneously, contradictions as minimal nogood sets (a future shape for conflict *explanations*). **AriGraph** — LLM-built KG world models beating raw-context play in text games: the ingestion thesis in eval form. **Versu/Praxis, Ceptre, Comme il Faut, Façade, storylets, lorebooks** — the fiction-state lineage, uniformly overwritten-current or static-canon: no as-of, no provenance, no frames, no unknowns (Ceptre's linear logic — facts *consumed* by transitions — is the principled opposite of a log; lorebooks demonstrate community-scale demand for hand-maintained canon injection, a folk registry without a log). **Intra** (Bicking, 2025 design notes) — independent convergence on an immutable event log, perspective-scoped visibility, and explicit unknowns. **Bounded novelty claim:** every individual mechanism here has a precedent somewhere in the surveyed art; the four-axis combination (history, provenance, structural frames, explicit unknowns) under one append-only log was found in no surveyed system, and explicit unresolved state with per-world resolution policy — including thunks moving without resolving — has **no precedent found in the surveyed art**.

---

## 21. Lexicon

The working vocabulary is maintained in [`LEXICON.md`](LEXICON.md) — two layers under two rules (every exported name must double-read for an engineer with zero source-material context; canon flavor lives in nouns and docs, verbs stay plain). Core entries: **World**, **PatternBuffer**, **Materialization**, **Degradation**, **frontier**, **arch**, the *ship in a bottle* doc metaphor. A term not in the lexicon is added there before it is used twice.

---

## 22. Sequencing

**Spike, not arc.** Scope: the engine (PatternBuffer + derived indexes + classifier + projector + resolver + `refer()` tier 1) + the chapter test, in this repo, with a stub/direct model callable. Explicitly stubbed in the spike: clocks, the evidence graph, character engines, staleness decay schedules, `deny/reserve` policy, the `arch` CLI, MCP wrapper.

**Must-honor even at spike scale** (cheap now, unrecoverable later): `world_id` partitioning from day one; two time axes; append-only log + rebuildable sidecar; the full provenance vocabulary; the frame field; single-parent move semantics; attribute canonicalization at the gate.

**Order of work:**
1. Recover and commit the *Last Honest Meter* seed (ground truth for the chapter test).
2. Engine spike → chapter test → score.
3. Extraction-class failures: fix and re-run. Shape-class failures: revise this document before writing more code.
4. The messy-dialogue micro-eval (§19.1 scope honesty).
5. Only then: host integration spec (the Kernos adapter, per §17.2) and/or the interactive milestone (§19.2).

**Process:** spec-first with independent review to GREEN before implementation, multi-round post-implementation review on substantive batches. §18 doubles as the reviewer's rubric.

---

## 23. Explicitly out of scope

- Embedding/vector retrieval over world state (state is graph-queried, not semantically searched; source prose is a texture asset, not a retrieval substrate).
- 3D/spatial-geometric simulation; this is symbolic state, not geometry.
- Drama management beyond the nudge policy (named unsolved, §14).
- Universal predicate ontology (the Cyc lesson; §10's canonicalization gate is the entire concession).
- Replacing or modifying any host's existing memory stores.
- Production multi-member frame entitlements beyond the adapter's consumer policy.

---

## 24. Decision record

| Decision | Resolution | Rationale |
|---|---|---|
| Standalone project vs. host feature | **Standalone repo; hosts integrate via adapter** | The engine has zero host concepts; repo boundary makes §18 structurally enforced; preserves the host project's (Kernos v1.0) closure narrative; the engine has standalone product surface (fiction/holodeck/mystery); two legible portfolio artifacts beat one sprawling one |
| Engine↔host coupling | **One-way dependency; injected model callable; host-side adapter** | Neutrality by absence of host knowledge, not by plugin framework; "from the engine's side every host is indistinguishable; from the host's side the engine is indistinguishable from sqlite3" |
| Name | **pattern-buffer** (package `patternbuffer`) | Canonical to the persistence claim (the store that holds a complete pattern between materializations; *Relics*: 75 years, zero degradation, perfect retrieval — the drawer test personified); double-reads as a sober systems name (cf. protocol buffers); names the project after its essence per P1 (the log is the only thing that exists). PyPI open; GitHub collisions dormant and trivially distinct. Runner-up `holomatrix` rejected for the repo (single flashy reading) and for the World class (fails double-read); retained as a lexicon footnote |
| World unit naming | **`World` = PatternBuffer + physics (policy + decay) + derived indexes; 1:1 world↔buffer invariant** | A world is its truth plus its laws of nature; the invariant forecloses both fragmentation failures permanently |
| Projection verb | **`materialize()`** | Doubly canonical: database materialized views *and* rematerialization |
| First milestone | **The chapter test, engine-only** | Cheapest possible ground-truthed validation of the hardest properties; interactive criteria and host integration both gated behind its score |

### 24.1 Amendment log

| # | Date | Amendment | Origin |
|---|---|---|---|
| A1 | 2026-06-11 | `asserted_at` = log sequence number permanently; wall-clock learned-at as reified meta-assertion, mandatory at the gate for STATE/EVENT in `observe_or_unknown` worlds (§3.2) | SPIKE-V1 Codex review r1–r4; Kernos CC endorsement (letter 007) |
| A2 | 2026-06-11 | Fixed structural predicates extended: containment family as one fold key; `caused_by` and `world_defining` added (§10) | SPIKE-V1 Codex review r1–r4; Kernos CC endorsement (letter 007) |
| A3 | 2026-06-12 | §20 survey addendum: Graphiti/Zep, XTDB, microtheories, ATMS, AriGraph, the fiction-state lineage, Intra; bounded novelty claim | Founder-requested prior-art survey; Kernos CC green-light (letter 024) |
| A4 | 2026-06-12 | §14 GM soft spot: host-side structural mitigation (navigator/narrator two-lane split; narrator blind to `plot:`) | Construct (first host), relayed by Kernos CC (letter 035) |
| A5 | 2026-06-16 | §16 1:1 invariant clarified: `world_id` = lineage/identity, file = instance; never-joined playthrough forks may share a `world_id` (engine keys nothing process-wide on it, audited) | Construct per-player fork model, relayed by Kernos CC (letter 041); PB engine audit |
| A6 | 2026-06-16 | The doctrine of the unknown (sharpening P2/P3/P4): three positive states (unestablished / deferred-thunk / deny-thunk); absence is relational (frame + time axes), never absolute; the membrane-test (never store the recomputable); no materialized knowledge grid | RFC-002, founder-originated; ratified Kernos CC (044) + Construct (007) + Codex engine audit |

The instructor rulings of dev_inbox letter 002 (containment-family fold key, self-contained frames with optional inclusion edges, establishing-set qualification, mandatory STATE/EVENT `valid_time` stamping, file+`world_id` double partitioning, canonicalization receipts-in-log/map-in-sidecar) carry spike authority and are encoded in `specs/SPIKE-V1.md`; A1/A2 are the two that amend this document's text.

Amendments **A7–A12** — the post-spike subsystems (the read layer, the full identity model, spatial composition and traversability, ingestion hardening, exact decimals, the frozen porcelain and build lifecycle) — are logged in **§25.9**, alongside the catalogue of the shipped surface they document.

**Lineage:** this white paper integrates (a) the framework-agnostic Assertion-World Model design document (June 2026), which itself superseded an earlier host-shaped design frame by re-deriving the system with no concessions and cataloging the diff as §18; and (b) the subsequent design sessions that produced P8, `refer()` and the three-tier cascade, constraint inversion, the scene cursor and lidar disciplines, splits/underdetermined anchors, thunks-move-without-resolving, document trust chains, cross-source conflict handling, the write-path taxonomy, mode-scoped decay, dramatic irony as a computable delta, the worlds/binding model, the naming decisions, and the lexicon.

---

## 25. The shipped surface (implementation currency)

Sections 1–24 are the founding design and remain canonical; every principle,
primitive, and invariant above is load-bearing in the running engine. This
section catalogues the subsystems **built past the spike** — the work that
carried the engine from the chapter-test spike to a first host running entirely
on its public contract. Nothing here contradicts §1–§24; each item is a
consequence of a founding principle, named so the design reference is complete.
Each subsystem has a spec under `specs/` and tests asserting its invariants; the
integrator's how-to is [`ADOPTION.md`](ADOPTION.md).

Milestone (2026-07): the first live host, **Construct** (an interactive-fiction
engine), runs with **zero** engine-internal reaches — entirely on the porcelain
(§25.1). The framework-agnostic claim of §17 is demonstrated, not asserted.

### 25.1 The porcelain — the frozen host contract

The operation algebra (§12) is the engine's internal surface; the **porcelain**
(`porcelain-v0.1`, tagged and **frozen**) is the typed, JSON-serializable verb
set a host actually integrates against. Freeze semantics are **additive-only**:
parameters gain defaults and verbs are added; nothing is renamed, removed, or
re-typed — so a host built against the tag never breaks. Everything a host needs
is here; a host that reaches below it (into `buffer`/`ingestor`/`classifier`) is
a signal a legitimate need isn't yet expressible on the surface, and the fix is
to add the verb (that is how §25.4–§25.7 came to exist). The verb families:

- **Write:** `ingest` / `ingest_structured` / `extract` (the read-only
  extraction seam) / `resolve` / `retract`.
- **Standing reads:** `snapshot` (scope × frame × lens × as_of × budget),
  `state`, `state_union`, `where`, `aggregate`, `confidence`.
- **Spatial reads:** `locate`, `contents`, `composition`, `features`, `path`,
  `route`, `neighborhood`, `salience`.
- **Knowledge/diff reads:** `frame_diff`, `who_knows`, `events`.
- **Identity:** `reconcile`, `proposals`, `confirm`, `merge`, `reject`,
  `correlate`, `correlations`, `correlation_conflicts`, `adjudicate_deferred`,
  `typing_conflicts`, `retype`.
- **Roster/scan reads:** `entities`, `facts`.
- **Build lifecycle:** `begin_build` / `seal_build` / `abort_build` (+ the
  `build()` context manager), `axis_heads`.
- **Reference:** `ask` (natural-language question → grounded facts), `refer`.

Every read that can carry a value is **plain-JSON-safe** at the boundary
(exact-decimals leave as tagged scalars, never raw `Decimal`); the core returns
native Python objects, the porcelain encodes.

### 25.2 The full identity model

§11's registry shipped as four relations plus a host adjudication surface. The
relations, by collapsing behaviour:

- **`same_as`** — collapses two ids to one closure (the merge of §11). A logged,
  reversible event.
- **`maybe_same_as`** — the represented-ambiguity proposal; carries its
  evidence; survives until adjudicated.
- **`distinct_from`** — the explicit **anti-merge** primitive: a sticky "these
  are definitively two things" that every future reconcile honours (keeps two
  same-named Clays apart). A **hard veto** on merge.
- **`aka` (correlation)** — a **non-collapsing** third relation: two ids are
  *facets of one identity* (the masked figure **is** Ilsa; a dual persona; an
  amalgamation) without merging their rows. As-of-scoped, so a reveal at t=10
  does not leak backward before it. `state_union`/`snapshot(correlated=True)`
  fold an entity over its correlation set for the whole reveal scene in one read.

The **host reconciliation surface** (all guarded; the hard vetoes —
containment, `distinct_from` — are absolute):

- **`reconcile()`** — the global finalize pass: merges confident cross-chunk
  coreferents by shared anchor through the auto-gate; the rest become adjudicable
  proposals.
- **`adjudicate_deferred()`** — merges only the structurally-**decisive** open
  proposals (anchor **subsumption**: a pure fragment whose entire distinctive
  anchor set is contained in the other's — `tovin` ⊆ `tovin beck`), returning
  receipts + the residue for host judgment. The semantic trap (two individuated
  things sharing a token) stays a proposal by construction.
- **`retype(entity, to_kind, evidence, absorb=)`** — a typing correction
  **distinct from merge**: the containment veto correctly blocks *merges* but
  must not block fixing a kind slip (a relic mis-typed `person:`; a
  `person:harth` shadowing the real `place:harth`). Append-only: wrong `kind`
  rows are retracted, the correct one appended and classified; in the absorb
  case only the inter-closure *artifact* edges are retracted (real child
  containment is preserved), then a guarded merge. A non-slip invocation is
  refused (`vetoed_not_a_slip`) — retype is never a veto bypass.
- **`typing_conflicts()`** — read-only surfacing of the slip candidates
  (`reconcile` never re-proposes hard-blocked pairs, so without this they are
  invisible).
- **The durable-contradiction veto** — the kind-check generalized to *every
  standing fact*: two entities whose shared, present, **durable**
  (CONSTITUTIVE/DISPOSITIONAL) attributes hold contradictory values are probably
  two things; auto-merge soft-declines to a proposal (a retrieval lead and a
  defense apprentice do not fuse just because they share a first name). A
  live-play defect made this concrete.

`proposals()` returns each open proposal with a structured `auto_decline`
context (the precise gate-failure code + evidence), so a host can adjudicate
with meaning it has and the engine doesn't.

### 25.3 Spatial composition — the `part_of` axis

§4 gives the containment tree (where a movable *is*) and the lateral graph (what
connects). Composition adds a third structural axis: **`part_of`** — a feature is
*structurally part of* a place without being *located in* it the way a movable
is (the burrow under the hillside, the alcove of a hall). `features(place)`
reads the `part_of`-children; `composition(entity)` reads the chain up;
`snapshot(features=True)` inlines a place with its sub-features in one read.
Identity-resolved and conflict-halting (a two-parent feature is excluded), one
level deep — the general recursive framework is deliberately deferred until a
third shape proves it needed.

### 25.4 The retrieval and awareness read layer

Reads that surface *the relevant neighbourhood* of a subject, not just one key:

- **`neighborhood(entity, depth, edge_kinds, budget)`** — the salience-ranked
  local subgraph across containment, lateral, and relation edges: the "what's
  around this and what matters" read for host briefings.
- **`salience(entity)`** — the projection-time ranking of §13, exposed as a read
  (recency + reinforcement + reference frequency + delta-from-baseline;
  computed, cached in the sidecar, never authoritative — P1 preserved).
- **`aggregate(container, attribute, op)`** — bounded `sum`/`count`/`min`/`max`/
  `avg` over a container's members' folded values (recursive optional).
- **`confidence(entity, attribute, frame)`** — derived trust over a functional
  key (provenance rank + recency + corroboration), computable over a **list** of
  frames (an observer's effective knowledge = `knows:O` ∪ `public`).
- **`who_knows(entity, attribute, value?)`** — the frame-transpose of
  `frame_diff`: which `knows:*` frames hold a given fact. Private knowers are
  enumerated; a *public* fact is not (public ⇒ host-assumed universal — a host
  heuristic the engine deliberately does not enumerate).
- **`state_union` / `snapshot(correlated=, features=)`** — the correlation- and
  composition-aware projections of §25.2/§25.3, opt-in, default-off (existing
  reads byte-unchanged).
- **`entities(frame, prefix=, as_of=)` and `facts(frame, …)`** — the bounded
  roster and frame-scan reads. **Frame is required** on both (a prefix-only
  enumeration would leak cross-frame entity existence — every read fixes
  perspective, the §6 absence discipline applied to enumeration). `facts()`
  serves raw visible rows for **audited scans** (receipt trails, knowledge
  digests), never folds — folded truth stays `state`/`snapshot`.
- **`fidelity_audit(frame, as_of)`** — the ingestion self-check: derives where a
  freshly-built log is structurally incomplete (coreference **`name_collisions`** —
  distinct ids sharing an anchor, each pair annotated with *why* it isn't merged;
  `unstamped_timed`; `orphan_entities`; `open_conflicts`) as a queryable checklist.
  The unknown-as-computed-gap (A6) applied to ingestion quality: the engine
  surfaces the gaps keyed by entity, the host joins arc/cast **severity** (host
  meaning) and drives targeted re-extraction; the engine never repairs (membrane).
  The headline `name_collisions` count is the fidelity metric a host drives down
  build-over-build. Ingestion fidelity is the engine's stated open front (§19); this
  makes it *measurable*.

### 25.5 Traversability — passable space (RFC-003)

§4's lateral graph answers "is there a way"; **`route(a, b, frame, as_of)`**
answers "is the way *passable*." Each portal segment (a door, gate, hatch) is
classified `clear` / `blocked` / `obscured` under a host-declared, kind-scoped
**traversal policy** (a shut *door* blocks; a shut *cabinet* does not) — the
engine reads the declaration as data (the RFC-001 pattern), never host
vocabulary. A blocked way is *derived world-detail on the portal* (its state and
obstruction relations), inspectable and sticky, **never a stored edge label**;
`blocked` carries the obstructing evidence, `obscured` a computed
`unknown_basis` (the §A6 unknown doctrine, never a fake row). `path()` stays
purely structural and is now **as-of-aware** (a severed edge drops at the time it
was severed; history preserved).

### 25.6 Ingestion hardening and latency

The gate (§10) gained the disciplines that lived testing demanded:

- **Malformed-id gate** — an id that violates the grammar (`person:/you`, a
  stray-slash phantom minted from narration) is **skipped with a typed receipt**,
  never normalized (guessing `person:you` would manufacture the phantom
  well-formed). Runs *after* the authority gate, so an authority violation still
  raises — a skip never swallows it.
- **`pov=` deixis binding** — the viewpoint entity id (validated before it ever
  reaches the prompt); first/second-person pronouns bind to it instead of minting
  a phantom person. Plus an extractor rule suppressing narrative-voice entities
  (the narrator is not a person). This kills the `person:you` class at the source.
- **Edge-granular skip receipts** — a single invalid edge (containment cycle,
  self-edge, lateral self-loop) is dropped with a typed `SkipRecord` while the
  rest of the chunk ingests; the host audits exactly what fell (no silent cap).
- **Classify modes** — `ingest(classify="inline"|"batch"|"defer"|"rules")`:
  per-row (default), one batched model call, none (host sweeps later), or
  guardrails-only zero-LM. The build-time latency lever.
- **Cursor-authoritative ingest** — for bible/source builds the scene cursor
  governs the story-time axis; a per-item `valid_from` is demoted to a lossless
  `source_valid_from` meta so a diegetic year can't invert the timeline.
- **`extract()`** — the read-only extraction seam: a host parallelizes N
  `extract()` calls in its own runtime, then `ingest_structured()`s the results
  serially (writes stay serial, append-only intact).

### 25.7 The build lifecycle

Two porcelain reads name what a source build needs from the engine's shape:

- **Build sessions** — `begin_build(at=)` / `seal_build(model=, scope=)` /
  `abort_build()` (+ the `build()` context manager): enter defer-classification
  mode, ingest a whole world, then run one classification pass at the seal
  (`scope="session"` for the session's rows, `"all"` for a whole-log sweep). An
  exception or `World.close()` aborts cleanly (a half-built world is the host's to
  inspect; classifying wreckage helps nobody). The session is a host-workflow
  concept and lives on the porcelain; the engine's classifier and toggle stay
  ignorant of it.
- **`axis_heads()`** — the log's two-axis high-water mark: `asserted_head` (the
  seq head) and `valid_head` (`MAX(valid_from)` over **all** rows, all frames —
  the entry-epoch read: a pre-play coordinate must sit above every seeded row
  wherever it landed). A coordinate scalar, never content — no
  entity/attribute/value/frame crosses.

### 25.8 Exact-decimal quantities

The §13 accrue fold serves fiction quantities as `int`/`float`. For **money and
any exact ledger**, float accrual is silently lossy (`0.1 + 0.2 ≠ 0.3`,
compounding across a delta chain). An exact quantity is a Python **`Decimal`** in
memory and a reserved **tagged scalar** `{"$decimal": "12.50"}` on every JSON
boundary (storage, dump, host payloads); a single value **codec** owns the
tagging so authored scale is preserved (`12.50` stays `12.50`) and no float ever
touches the number. Fold arithmetic runs under a fixed decimal context, so builds
stay byte-deterministic (P7). Mixing exact-decimal with float in one fold
**raises** (an authoring smell surfaced, never silently promoted); `Decimal` +
`int` is exact. Opt-in per value: fiction floats stay floats, and a world that
never authors a decimal is byte-identical to before. Currency codes, units, and
rounding *policy* remain host meaning (ordinary facts) — the engine stores an
exact number, the host owns what it denominates.

### 25.9 Amendment log (continued)

| # | Date | Amendment | Origin |
|---|---|---|---|
| A7 | 2026-06→07 | The retrieval/awareness read layer: `neighborhood`, `salience` read, `aggregate`, multi-frame `confidence`, `who_knows`, the `situation` lens, `state_union`, `snapshot(correlated=/features=)` (§25.4; §13 lens list) | WORLD-RETRIEVAL-V1/V2, SITUATION-LENS-V1, CONFIDENCE-V1/MULTIFRAME, WHO-KNOWS-INVERSE-V1, AWARENESS-READS-V1.1 |
| A8 | 2026-06→07 | The full identity model: `aka` correlation (non-collapsing), `distinct_from` (anti-merge), the reconcile/`adjudicate_deferred`/`retype`/`typing_conflicts` surface, the durable-contradiction veto (§25.2; §11) | AKA-CORRELATION-V1, MERGE-RECONCILE-VERB-V1/V2, IDENTITY-RECALL-V1, TRIAGE-CONTEXT-V1, SHAPE-FIX-V1 |
| A9 | 2026-06→07 | Spatial composition (`part_of`/`features`/`composition`, §25.3) and traversability (`route`/portal/policy, as-of `path`, §25.5) | PLACE-FEATURE-ABSTRACTION-V1, RFC-003, PATH-TEMPORAL-V1 |
| A10 | 2026-06→07 | Ingestion hardening + latency: malformed-id gate, `pov` deixis binding, edge-granular skip receipts, classify modes, cursor-authoritative ingest, the `extract()` seam (§25.6) | INGEST-HARDENING-V1, INGEST-LATENCY-V2, SHAPE-FIX-V1 |
| A11 | 2026-07 | Exact-decimal quantities: `Decimal` + the `$decimal` tagged scalar, one value codec, fixed-context folds, raise-on-mix (§25.8; §13 numeric) | EXACT-DECIMAL-QUANTITIES-V1 |
| A12 | 2026-07 | The frozen porcelain contract (`porcelain-v0.1`, additive-only) + the build lifecycle (`begin_build`/`seal_build`/`abort_build`, `axis_heads`) + bounded roster/scan reads (`entities`/`facts`); first host runs entirely on the porcelain (§25.1, §25.7, §25.4) | PORCELAIN-V1, BUILD-SESSION-V1, AXIS-HEAD-V1, BOUNDED-READS-V1 |
| A13 | 2026-07 | `fidelity_audit()` — the ingestion self-check that makes the open front (§19) *measurable*: coreference `name_collisions` (the tracked metric) + `unstamped_timed`/`orphan_entities`/`open_conflicts`, derived and host-severity-joined (§25.4). Co-designed with the first host | INGESTION-FIDELITY-V1 |
| A14 | 2026-07 | The MCP wrapper (§17.2's reserved "later optional wrapper", built): `patternbuffer[mcp]` serves the frozen porcelain's 37 deterministic verbs over stdio — the genuinely model-free subset (classify narrowed to `rules`/`defer`; no `seal_build(model)`), explicit registry (never reflective), `{"result": …}` wire envelope, exact ToolAnnotations, one server ↔ one world. A connected client is a fully **trusted world principal**; entitlement stays host-mediated. The engine-independence claim now demonstrated beyond Python | MCP-WRAPPER-V1 |
