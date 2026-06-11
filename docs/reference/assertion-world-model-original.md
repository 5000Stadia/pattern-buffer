> **Lineage note:** This is the framework-agnostic Assertion-World Model design document (June 2026), preserved verbatim as the founding artifact of pattern-buffer. It is superseded as a working reference by [docs/WHITEPAPER.md](../WHITEPAPER.md), which integrates it with the subsequent design-session refinements. Section numbering below is the original's; the whitepaper's §18 corresponds to §16 here.

# The Assertion-World Model

> A native design reference. One append-only log of perspective-scoped, time-indexed assertions about entities; every other structure — current state, space, knowledge, history, the rendered world — is a disposable projection over it. Fiction simulation and real-world tracking are the same machine under one policy switch.

**Status:** Canonical design document, framework-agnostic. This describes the system in its first-best shape, with no concessions to any host architecture. A closing section (§16) catalogs the hazards of converting this design into a host system and the features that must be handled delicately to avoid sacrificing real elements.

-----

## 1. What this system is

A storage and retrieval substrate that lets a language model maintain a **complete, queryable, durable model of a world** — its places, objects, people, relationships, histories, and unknowns — such that:

- Any state question ("what is in the drawer," "where was the badge at 23:40," "what does Marn know") is answered by a **deterministic query**, never by re-reading or re-inferring over prose.
- The world **accretes**: details established once are canon forever; details never established are explicitly unresolved, not silently absent.
- The world is **re-enterable**: a cold instance with no history can load a projection and stand inside the world coherently.
- The same substrate serves **authored fiction** (where the model is the truth) and **real-world tracking** (where the model is a belief about the truth), differing only in resolution policy and provenance discipline.

The governing insight: **a narrative is a lossy serialization of world-state plus voice; ingestion is deserialization.** Prose was never the world — it was a transmission format for one. After deserialization, the source text is demoted from retrieval substrate to texture asset. The refined claim of the system: **state-complete, style-anchored, meaning-lossy** — and meaning-lossy is acceptable because the renderer regenerates meaning at read time the way a musician regenerates music from a score.

## 2. Foundational principles

These are load-bearing. Every later mechanism is a consequence of one of them.

**P1 — The log is the only thing that exists.** One append-only assertion log per world is the sole source of truth. Current state, containment trees, durability classes, identity tables, knowledge frames, rendered briefings — all are derived, disposable, and rebuildable from the log. No judgment (classification, identity matching, gap-filling) can corrupt canon, because judgments live only in derived layers.

**P2 — Store only what cannot be derived; derive everything else.** Location is one containment edge; "the box is empty" and "Morpheus is wearing the jacket" are query results, never stored fields. The moment a derivable fact is stored, two sources of truth exist and desynchronization becomes possible. This single discipline eliminates the dominant failure mode of stateful systems.

**P3 — Nothing exists until referenced; once referenced, it is canon forever.** Unreferenced detail is a memoized lazy thunk: an explicitly stored *unresolved* aspect. Reference forces resolution exactly once; the result is cached permanently. The world condenses where observed and stays condensed. Deliberately unobserved branches (the door the protagonist walked away from) are legitimate, stable states — not gaps to fill.

**P4 — Perspective is structural, not behavioral.** What an agent knows is defined by which assertions exist in its frame, not by instructions about what it may say. An agent cannot leak what was never in its window. The same mechanism carries character knowledge, contested canon, and privacy.

**P5 — Provenance is the immune system.** Every assertion carries how it came to be known. Authored canon, observation, inference, assumption, and system-generated fill are permanently distinguishable. The only unforgivable operation in the entire system is a fabrication entering the log marked as stated truth.

**P6 — Events are scaffolding; the world is the precipitate.** A plot, a conversation, a sensor stream — these are authoring traces. What the system keeps and serves is the residue they leave: the furnished, re-enterable world. The trace is preserved (as EVENT rows and provenance) but the deliverable is the fold.

**P7 — LLMs at the boundaries only.** Extraction-in, resolution, and rendering-out are language-model operations. Everything between — storage, supersession, graph walks, folds, identity bookkeeping — is deterministic code. State questions cost milliseconds, not tokens.

## 3. The two primitives

Everything reduces to two primitives. Every domain concept — place, person, object, era, status, relationship, story thread, belief, rule — is a *pattern over* them, never a third primitive.

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

Consequences: retraction, supersession, confidence decay, classification revisions, and any future unanticipated metadata are ordinary appends — never schema changes, never edits. (Implementation note: hot fields — time, frame, status — are denormalized into columns for query speed; the *model* remains triples-on-triples, so nothing is ever special-cased.)

**Two time axes.** `valid_time` is when the fact holds in the world; `asserted_at` is when the system learned it. They diverge constantly (a past event learned today; a future scheduled process asserted now) and both are required for as-of queries and audit.

## 4. Relations: the spatial spine

Two relation families over the same nodes, distinguished by cardinality:

**Containment (`in` / `within`) — a tree.** Single parent: a thing is in exactly one place. Location is derived by walking up the tree to a root. Because containment is single-parent, **moving is the only operation**: `relate(jacket, worn_by, morpheus)` detaches the jacket from the box automatically (the new edge supersedes the old). Two descriptions change — the box derives to empty, Morpheus derives to clothed — and neither was written. There is only ever one source of truth for "where is the jacket," so dependent descriptions cannot disagree.

**Passage (`connects_to` / `adjacent_to`) — a lateral graph.** Many-to-many: the hallway touches four rooms. Containment answers "where is X"; the lateral graph answers "can you walk from here to there." A world with the tree but not the graph is furnished but untraversable.

Fixtures vs. movables: containment of a movable is mutable state; containment of a fixture (the fireplace in the wall, the staircase) is part of what the place *is*. This distinction is adjudicated by the durability classifier (§5), with a named sub-rule, because it is the single most common ambiguity.

**Absence is free.** Under the projection's closed-world stance (§11), "Morpheus has no jacket" is never stored — not-present-in-the-wearing-relation *is* the absence. When he puts one on, the absence ends because the relation now has a member.

## 5. Durability: the four lifetime classes

Every assertion is classified by lifetime. The classes are orthogonal to attribute and frame; they answer "how long does this kind of fact live, and which projections want it?"

|Class          |Answers                 |Examples                                                                               |Lifetime semantics                                                                             |
|---------------|------------------------|---------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
|`CONSTITUTIVE` |what the thing **is**   |"221B is a room"; the fireplace in the wall; era = Victorian                           |Permanent unless the world is re-authored. Never compacted out of a projection.                |
|`DISPOSITIONAL`|what it **tends** to be |Holmes plays violin; the cantina serves no droids; the man is usually on the blue stoop|Long-lived, defeasible, overridable by stronger later evidence.                                |
|`STATE`        |what it is **right now**|the window is open; Holmes is agitated; the car is in the driveway                     |Valid-time bounded; superseded by a later assertion on the same (entity, attribute, frame) key.|
|`EVENT`        |what **happened**       |the dollar handoff; the badge entry at 23:40                                           |Immutable past point/interval; causes state transitions; carries `caused_by` edges.            |

**Durability is an index, not truth (P1).** The class is a judgment *about* a fact. It lives in a rebuildable sidecar keyed by assertion ID — never baked into the log. A misclassification is repaired by re-running the classifier over the untouched log.

### 5.1 Classifier

`classify(assertion, world_context) → { durability, class_confidence }` — largely an LLM judgment over linguistic signals, with deterministic guardrails:

- **Signals:** copula of identity/kind and structural containment → CONSTITUTIVE. Habitual present / role language → DISPOSITIONAL. Stative-at-a-moment → STATE. Past perfective with an agent, reifiable as an occurrence → EVENT.
- **The mutability test** resolves most ambiguity: *could one event flip this without re-authoring the world?* → STATE. *True at every moment unless rewritten?* → CONSTITUTIVE. *Generally true but defeasible?* → DISPOSITIONAL.
- **Containment sub-rule:** movable → STATE; fixture → CONSTITUTIVE. (The box on the passenger seat vs. the glovebox in the dashboard.)
- **Accrual promotion:** repeated STATE observations of the same (entity, attribute, value) promote to DISPOSITIONAL. Promotion frequency is also the source of the *salience baseline* — "today he seems beat up" is only computable against a stored normal. Classification is therefore a maintained index, re-derived as evidence accrues, not a write-once stamp.
- **Asymmetric-cost defaults.** Misclassification costs are not symmetric. STATE-misread-as-CONSTITUTIVE bakes a transient into the permanent set (Holmes agitated forever); CONSTITUTIVE-misread-as-STATE risks supersession of structure (the room loses its fireplace). Defaults: ambiguous *properties* → STATE; ambiguous *fixture containment* → CONSTITUTIVE; low `class_confidence` on CONSTITUTIVE verdicts triggers review, because those silently corrupt every future projection.
- **`world_defining` escape hatch.** Some STATE is constitutive *for a given world* ("a city under siege," "post-collapse era"). An explicit pin lets the establishing projection always include it. The CONSTITUTIVE/STATE line is sometimes an authorial choice, not a linguistic one; the system represents the choice rather than guessing it.
- **Re-classification is monotonic-safe only upward.** STATE→DISPOSITIONAL accrual is silent. New text *contradicting* a CONSTITUTIVE assertion raises a truth-maintenance flag — never a silent rewrite — so the world cannot mutate between reloads without a trace.

## 6. Frames: one mechanism for perspective, dispute, and privacy

The `frame` field scopes every assertion. Four needs, one mechanism:

1. **Canon** — the default frame; the world's ground truth (in fiction, the author's truth; in tracking, best-evidence reality).
1. **Knowledge frames** — `knows:marn` holds exactly what Marn knows. An agent's epistemic state *is* the set of assertions in its frame. Mystery, secrecy, dramatic irony, and information asymmetry are structured data, not renderer discipline (P4). An agent instantiated with only its frame **cannot** leak canon.
1. **Contested truth** — the same (entity, attribute) holds different values in different frames with zero contradiction: an official story vs. actual events; the 1977 vs. 1997 cut of a scene; two characters' irreconcilable beliefs about the afterlife. Nothing overwrites anything; the projector serves whichever frame is loaded.
1. **Privacy** — a frame boundary is an access boundary. Sensitive rows (occupancy, schedules, valuables) are frame-scoped, and consumers receive only frames they are entitled to.

**The absence discipline:** when a consumer is served a frame, out-of-frame assertions are *absent* — not redacted, not marked, simply not present. Filtering happens at source. This is what makes the guarantee structural rather than behavioral.

Belief assertions interact with truth maintenance: an inferred belief carries its justification (`believes(linda, assault(man), justified_by=injured(man), status=hypothesis)`); if the justification is later retracted, the belief is flagged for retraction — a justification-based truth-maintenance discipline, applied only within frames.

## 7. Provenance: the vocabulary of how-known

Every assertion carries a status:

|Status     |Meaning                                                          |Who may write it            |
|-----------|-----------------------------------------------------------------|----------------------------|
|`stated`   |Authored canon: the source text or the authoritative user said it|**Ingestor only**           |
|`observed` |Directly perceived (tracking mode: a confirmed observation)      |Ingestor only               |
|`inferred` |Derived from evidence, with a justification pointer              |Ingestor / truth-maintenance|
|`assumed`  |A working assumption, explicitly provisional                     |Ingestor, flagged           |
|`generated`|Invented by the resolver under canon constraints (fiction fill)  |**Resolver only**           |
|`default`  |Kind-default used for rendering coherence; never a fact claim    |Projector only, render-time |
|`retracted`|Withdrawn; preserved in the log, excluded from folds             |Truth-maintenance           |

Plus a confidence value, and — in tracking mode — `last_confirmed` with time-decaying confidence (§13).

Hard rules: `generated` and `default` never masquerade as `stated`; promotions across statuses are explicit meta-assertions; and in tracking mode kind-defaults may *render* but are never *promoted* — the store must always be able to say "unknown" rather than confabulate reality.

## 8. Thunks and resolution: the lazy world

Unresolved detail is first-class:

```
(obj:box · contents · ⊥ · status=unresolved · policy=<policy> [· constraints…])
```

When a consumer **forces** an unresolved aspect (opens the drawer, asks what's behind the door), the **resolver** evaluates it exactly once and memoizes the result into the log. Future references serve the cache.

**Resolution policy — the one switch.** Set per world (or per subtree):

|Policy              |On force                                                                                                                                                                         |Mode               |
|--------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------|
|`invent_under_canon`|LLM authors content consistent with every CONSTITUTIVE and DISPOSITIONAL constraint inherited from the containing scope (era, genre, owner's character); committed as `generated`|Fiction / holodeck |
|`observe_or_unknown`|Never invents. Resolves only from observation; otherwise remains explicitly unknown                                                                                              |Real-world tracking|
|`deny` / `reserve`  |Refuses resolution (e.g., a slot reserved for the player; a sealed authorial gap)                                                                                                |Special cases      |

This switch is the entire difference between a worldbuilder and a digital twin. Everything else — the log, the classes, the frames, the projector — is shared.

**Constraint inheritance** is what keeps invention canonical: a resolved drawer in Sam Spade's office inherits "c.1928 San Francisco," "private detective's office," and the owner's dispositions before the LLM writes a word. **Access gating** is what keeps resolution honest: detail resolves only to the level the observer's position grants (police seen at a distance resolve coarsely; the room behind the door they're breaking down stays unresolved if the witness walks away). The narrative instinct to over-resolve — to invent who's behind the door — is the system's most dangerous failure mode and is leashed here, at resolution, and again at rendering (§11).

**Resolution floor.** Worlds are fractal; a home decomposes into drawers into objects into components. Each world (or subtree) sets a deliberate floor — rooms / surfaces / drawers — below which thunks are not even instantiated. The floor is a use-case decision made on purpose, not an emergent accident of sprawl.

## 9. Identity: the registry

Identity across non-adjacent references — "the thing he took from the car" resolving to the same jacket-node; "the man on the blue stoop" being the same man two blocks away — is the hardest problem in the system and the place such systems break in practice. The design gives it a home; it does not pretend to solve it.

- **Anchors.** Each entity carries composite identity signals: names/aliases, roles, recurring locations, distinguishing features. Single-anchor identity (location only) is brittle by design review: the day the man isn't on the stoop, appearance and recurrence must carry the match.
- **Ambiguity is represented, not forced.** Uncertain matches are stored as explicit maybe-same-as edges with the evidence that suggested them, surviving until resolved.
- **Merges are events.** A merge (or split) is itself a logged event — auditable and reversible by retraction. A bad merge never rewrites history; it is repaired forward.
- **Late binding.** "A man entered" in chapter 1 merges with the named character of chapter 3 by appending identity assertions, leaving every chapter-1 row intact and now reachable through the merged identity.

## 10. The operation algebra and the role authority matrix

The complete write surface is small:

```
assert(entity, kind)                      bring a thing into existence
set(entity, attribute, value, …)          attach a fact (one assertion)
relate(subject, relation, object)         add an edge; for single-parent relations
                                          this IS the move operation (supersedes prior)
event(kind, agents, patients, t, effects) reify an occurrence; effects are relates/sets
believe(frame, assertion, justification)  write into a knowledge frame
resolve(entity, aspect)                   force a thunk per policy; memoize
retract(assertion_id, reason)             append a retraction meta-assertion
merge(entity_a, entity_b, evidence)       identity merge, logged as an event
```

Reads are queries over derived indexes: `locate(x)` (walk the tree), `contents(x)`, `state(e, a, as_of, frame)`, `history(e)`, `path(a, b)` (lateral graph), `describe(e, frame)`.

**Five roles, strict authority** (roles, not necessarily five processes):

|Role          |LLM?|May write                                                                                                                                     |
|--------------|----|----------------------------------------------------------------------------------------------------------------------------------------------|
|**Ingestor**  |yes |`stated`, `observed`, `inferred`, `assumed` — the *only* path for stated truth; owns identity resolution and provenance discipline at the gate|
|**Classifier**|yes |the durability sidecar only — never the log                                                                                                   |
|**Resolver**  |yes |`generated` only, under inherited constraints; the only invention path                                                                        |
|**Projector** |no  |nothing durable; emits briefings; may mark render-time `default` fills                                                                        |
|**Renderer**  |yes |**nothing.** Prose out, under the leash (§11). New canon never enters through the renderer.                                                   |

The separation between resolver and renderer is the design's central guard: the component that *speaks* is never the component that *decides what is true*. A narrator that could mint canon would drift the world a little with every enthusiastic sentence — the precise failure of unstructured LLM roleplay.

## 11. Projection: serving the world

```
project(scope, as_of, frame, lens, budget) → briefing
```

**Lenses** select durability classes:

- `establishing_set` — CONSTITUTIVE + DISPOSITIONAL + the *establishing* STATE: the first non-event-effect value per (entity, attribute) — the world at rest, before the plot perturbs it. The default for re-entry ("221B at rest," not "221B mid-confrontation"). Honors `world_defining` pins.
- `current_state` — adds STATE folded to `as_of`.
- `what_happened` — the EVENT chain in scope, time-ordered, with causality; the backstory digest.
- `character_sheet` — one entity's accumulated card, frame-respecting.

**Algorithm:** select in-scope, in-frame assertions valid at `as_of` per lens → fold STATE by supersession per (entity, attribute, frame) key — *per frame; a belief fold never overwrites canon* → walk the containment tree for the spatial spine, ordered by depth and salience → fill gaps from kind-defaults, every fill marked `default` → resolve forced thunks via the resolver (which feeds new assertions back through classification — the system is closed under its own operations) → shape to budget.

**The budget invariant:** the CONSTITUTIVE spine is budget-exempt. Compress DISPOSITIONAL color, summarize peripheral STATE, digest EVENT chains — never compact identity and structure. (Anchored summarization with the anchor formally bound to the constitutive layer.)

**Open-world store, closed-world projection.** The store never claims the unstated is false — unknown is unknown (mandatory in tracking mode). The projector commits to closed-world defaults to render one coherent scene (the unasserted lamp is off, drawn off). The reconciliation is positional: open for truth, closed for the briefing, with every closed-world commitment marked `default` so it can never harden into canon.

**The render leash.** The renderer receives the briefing under a fixed contract: describe only what these assertions support; dress `default` fills as ambient detail; introduce **no new named entities or events**; route any forced unknown through the resolver. Two cold instances over the same store must produce *compatible* worlds — identical bound facts, freely varying wording. **Freeze facts; regenerate prose.** Stored wording calcifies retellings; understored facts let retellings contradict. The binding layer is the asserted facts; the free layer is the words.

**Correctness criterion (testable):** `project(classify(ingest(W))) ≈ W` — round-trip compatibility up to prose freedom and resolved gaps. Test suites are written against this approximate inverse.

## 12. The narrative layer (fiction mode)

Four vocabularies on top of the same row shape — no new primitives:

1. **Character engines.** An NPC is an agent instantiated with: its DISPOSITIONAL rows — drives with priorities, fears, constraints, breaking conditions (`(marn · drive · prevent_panic > protect_self)`, `(marn · breaks_if · confronted_with(door_log + ledger_gap))`); its voice anchors; and **only its `knows:` frame as its entire world context**. Secrecy by structural absence (P4). Without this layer, NPCs are furniture that talks; with it, the renderer improvises in-character behavior down any path the player takes.
1. **The evidence graph.** A mystery is a dependency graph of revelations: `(fact:X · discoverable_via · inspect(obj) | press(person))`, `(fact:Y · derivable_from · {…})`. Canon is **path-independent**: the original plot is just one traversal; the player can assemble the same truth in any order with equal richness. Discovery moves assertions *into* a knowledge frame; it never changes canon.
1. **Clocks and autonomous processes.** Scheduled and conditional events (`fires_when`) make the world move without the player: the replacement meter finishes calibrating; the cover-up escalates if the player is observed at the wellhead; the cisterns deplete regardless. Player inaction becomes meaningful.
1. **Style anchors.** Short source excerpts attached to entities as render exemplars — the source prose demoted to texture asset (P6/§1). State queries never touch them; voice quality leans on them.

Honestly open even with all four: **pacing / drama management** — making escalation land and dilemmas arrive with weight — is unsolved in the field. The pragmatic stance: the renderer acts as GM with the evidence graph as its map and a light nudge policy (surface an unwalked thread when momentum stalls). A behavior spec, not a data row.

## 13. The tracking layer (real-world mode)

The same substrate under `observe_or_unknown`, with three additions:

- **Staleness.** Mutable STATE carries `last_confirmed` and a confidence that decays on a per-attribute schedule (a parked car's location decays in hours; a couch's position in months). A tracking record is only as good as its last confirmation; fiction's page is always true, which is exactly why fiction is the cheap test mode.
- **Assumption quarantine.** Kind-defaults render but never promote; wrong assumptions about reality make agents act on falsehoods, so "I don't actually know" is always a representable answer.
- **Privacy frames.** Occupancy, schedules, valuables are frame-scoped from the moment of ingestion; access is structural.

The physical/relational/story triad a real place requires is carried natively: physical = CONSTITUTIVE assertions with metric/material values; relational = entity-valued edges (tree + lateral graph + occupancy/ownership); story = STATE@t + EVENT + recurring DISP. One store, read three ways; a minimum bar for a complete record is one metric per space, the lateral graph overlaid on the tree, and at least one dated event anchored to a place.

## 14. Evaluation: fiction as the ground-truthed harness

Fiction is the only domain where a world model grades against printed truth. **The chapter test:** ingest one complete short fiction → **delete the prose** → interrogate a cold instance: every tracked object's location at three timestamps; each character's knowledge frame at the climax; one state fact that changed mid-story; two never-opened-drawer resolutions checked for canon consistency; one as-of query over the event spine → score against the text. Failures classify as *extraction* (engineering, fixable) vs. *shape* (theory — revisit this document).

Interactive criteria, across multiple sessions: resolved thunks stay stable (the drawer never changes); frame-scoped NPCs never leak out-of-frame canon; the mystery solves by at least two distinct evidence-graph traversals; clocks fire on player inaction.

## 15. Honest hard problems and prior art

**Hard problems**, in order of severity: (1) **identity resolution** — the registry gives merges an audit trail; it does not make matching correct; expect a review loop. (2) **extraction fidelity** — coreference over long prose, stated-vs-implied discipline, not papering over authorial gaps; the graph is only ever as good as the front door. (3) **atmosphere/qualia** — mood rows are the least falsifiable assertions and the renderer's largest uncredited workload; tolerated as low-confidence DISP plus style anchors, named as a soft spot. (4) **natural boundaries** — where the garden ends is a decision prose never made; the tree forces deliberate arbitrary cuts. (5) **pacing** (§12).

**Prior art** — every component is individually proven; the composition is the novel part. Datomic (append-only datoms, as-of) — the log shape. RDF-star + named graphs + temporal RDF — reified provenance, frames, valid time. ECS — entity minimalism at world scale; a save file as a serialized assertion set. Event sourcing / CQRS — store events, serve projections. Inform 7 / Z-machine / TADS — tiny relation sets, the containment tree, the single move operation. BookNLP — fiction extraction (the weak front end). Generative Agents — frame-scoped NPC memory. PDDL / event calculus — action effects. JTMS — justification-based belief maintenance. Cyc — the forty-year cautionary tale against pre-enumerating a universal vocabulary: fix only structural predicates (`kind`, `in`, `connects_to`); let domain predicates emerge. AI Dungeon — the anti-example this design exists to prevent: generation without persistent state drifts and contradicts itself.

**Versus RAG**, the industry default: retrieval over prose serves *descriptions* and re-infers state per query — it can serve chapter 2's location after chapter 9 moved the object, re-pays inference every time, and has no write-back for discoveries. This design is **deserialize-once, query-forever, append-on-discovery**.

-----

## 16. Conversion hazards: shaping this into a host system

What follows catalogs what goes wrong when this design is embedded into a host agent platform (any platform with its own memory stores, turn pipeline, worker contracts, and scoping units — the observations are written generally but were learned against a real host). Each item names the pressure, the failure if yielded to, and the delicate handling required.

### 16.1 Partition unit: worlds vs. the host's scoping unit

**Pressure.** Hosts have a native scoping unit (a workspace, a context space, a channel) and every subsystem partitions by it; the path of least resistance is one world per scope.
**Failure.** Tracked reality fragments: one vehicle becomes three partial entities across three scopes, identity federates badly, and the "single world model per member" goal is structurally precluded.
**Delicate handling.** **Worlds are first-class; scopes bind to worlds.** Fiction scopes bind to private worlds (hard isolation is *correct* for stories — each story is its own universe). All real-life scopes bind to *the* member's one world, with frames doing the scoping the host expects. Binding, not ownership. This is the single most damaging compromise to accept silently, because it looks harmless at spike scale and is ruinous at fused-stream scale.

### 16.2 Write authority vs. the host's turn pipeline

**Pressure.** The host's principal/integration agent is where turn-time writes naturally happen; letting it append world assertions directly is the easy wiring.
**Failure.** The narrator and the canon-writer become the same agent — the exact render-leash violation the role matrix (§10) exists to prevent. The world drifts a little with every fluent sentence.
**Delicate handling.** Keep the authority matrix intact across the conversion: integration *proposes*; an ingestor role *commits*; only the ingestor writes `stated`/`observed`; only the resolver writes `generated`; the renderer writes nothing. If the host can't afford a separate process, keep the separation as distinct, auditable pipeline stages with distinct prompts — the role boundary matters more than the process boundary.

### 16.3 The resolver vs. the host's cost invariants

**Pressure.** Hosts enforce per-turn cost ceilings (e.g., "no LLM calls in always-on workers"), pushing LLM operations to boundaries or opt-in tools. The resolver gets demoted to a depth tool.
**Failure.** The system's most distinctive operation — inline, synchronous, canon-constrained invention when the player opens the drawer — becomes an optional convenience, and either resolution doesn't happen at the moment of forcing (broken experience) or the renderer quietly does it instead (canon poisoning).
**Delicate handling.** The cost invariant correctly applies to the *push snapshot* (reads are deterministic graph walks — they satisfy a no-LLM rule better than embedding retrieval does). Resolution is different in kind: an LLM operation **with append authority** that must run inline when forced. Architect it as a peer of ingest and project, with its own budget accounting, not as a pull tool.

### 16.4 Durability taxonomy vs. the host's existing labels

**Pressure.** The host has a similar-looking lifecycle vocabulary (e.g., identity/structural/habitual/contextual on its fact records); the cheap move is copying labels across.
**Failure.** Durability gets implemented as *labels* when its definition is **operational** — supersession keys, lens selection, budget exemption, establishing-set membership. Labels without the operational semantics produce a projector that can't keep its invariants.
**Delicate handling.** Treat any mapping to host vocabulary as a migration hint, not an equivalence. Implement durability from its operational contract (§5, §11), then map labels afterward. Also: the host vocabulary likely lacks EVENT — it must be added, not approximated by a "contextual" catch-all, because EVENT carries causality and immutability semantics no fluent class has.

### 16.5 Frames vs. the host's disclosure/visibility machinery

**Pressure.** The host already has visibility gating (per-member disclosure, sensitivity tiers); the temptation runs both directions — reimplement frames beside it (duplication) or flatten frames *into* it (loss).
**Failure.** If flattened: contested canon and per-NPC knowledge frames don't fit a member-visibility model (an NPC is not a member; a 1977-vs-1997 dispute is not a sensitivity tier), and the narrative half of the system silently dies.
**Delicate handling.** Recognize the host's gate as a *special case* of frames (privacy frames) and generalize in that direction: frames are the storage-level mechanism; the host's gate becomes one consumer policy over them. Preserve the absence discipline (filter at source; absent, not redacted) — it is the property that makes the guarantee structural.

### 16.6 Store boundary: the third store vs. extending an existing one

**Pressure.** The host has a structured-facts store; extending it with typed edges looks cheaper than a new store.
**Failure.** The two jobs remix: prose-truths-about-members and entity-state-over-time have different write cadences (boundary-harvest vs. action-time), different reconciliation (LLM add/update/reinforce vs. deterministic supersession-by-key), and different query surfaces (semantic search vs. graph walk). One store doing both re-creates the mixed-failure-mode problem that store separation exists to solve — including the specific RAG failure (stale sentence served confidently after the state changed).
**Delicate handling.** Third store, own write path, own indexes. Define the seam explicitly: which facts *bridge* (a member's stated preference that is also a world disposition), and make bridging an explicit cross-reference, never an automatic mirror.

### 16.7 Cadence: turn-time state vs. boundary-time harvest

**Pressure.** The host's extraction runs at compaction boundaries for good reasons (cost, noise, reconciliation); the world writes get deferred there too.
**Failure.** State lags reality by up to a full compaction span. The dollar that moved at turn 3 is still in the old hand at turn 40. For a game this is immediately fatal; for tracking it's silently corrosive.
**Delicate handling.** Two cadences, complementary: action-bearing turns append through the write-gate at turn time; a boundary-time reconciliation sweep catches what turn-time missed. Neither replaces the other.

### 16.8 Salience: stored weights vs. projection-time ranking

**Pressure.** Host roadmaps often specify salience *weights* as stored fields.
**Failure.** Salience hardens into truth — a judgment baked into the log (violating P1), going stale, and biasing every future projection.
**Delicate handling.** Salience is a projection-time ranking (recency + reinforcement count + reference frequency), computed from the log, cacheable in a derived index, never authoritative. If the host insists on stored weights, store them in the rebuildable sidecar with the classifier's outputs.

### 16.9 Vocabulary drift in roadmap language

**Pressure.** Host design documents describe the goal in current-state language ("a current-state abstraction, not a log").
**Failure.** An implementer reads it literally and builds a mutable state store — losing as-of queries, audit, rebuildability, and the entire P1 guarantee, unrecoverably (you cannot reconstruct a log from a mutable store after the fact).
**Delicate handling.** Resolve the phrasing *before* any spec drafts: the deliverable is *a current-state abstraction **served from** an assertion log* — the abstraction is the derived index, the log is the truth. One sentence in the spec; the whole architecture rides on it.

### 16.10 What must survive conversion intact — the checklist

If any item below is compromised, a real element of the design is lost, not merely an implementation detail:

1. Append-only log as the only truth; everything else derived and rebuildable (P1).
1. Derive-don't-store discipline; single-parent move semantics (P2, §4).
1. Thunks as first-class with per-world resolution policy — the one-switch fiction/tracking unification (P3, §8).
1. Frames with the absence discipline; NPC knowledge by structural absence (P4, §6).
1. The provenance vocabulary with its writer-authority matrix; `generated`/`default` never promotable to `stated` (P5, §7, §10).
1. Resolver as an inline first-class operation, separate from the renderer; renderer writes nothing (§10, 16.2, 16.3).
1. Worlds as the partition unit; host scopes bind (16.1).
1. EVENT as a real class with causality, not a catch-all (16.4).
1. Two time axes (valid/asserted) and as-of queries (§3.2).
1. The budget invariant: the constitutive spine is never compacted out (§11).
1. Open-world store / closed-world projection, with `default` marking (§11).
1. The chapter test as the acceptance gate before any real-world stream connects (§14).

Everything not on this list — storage engine, index layouts, worker contracts, cohort shapes, naming — is legitimately negotiable plumbing.
