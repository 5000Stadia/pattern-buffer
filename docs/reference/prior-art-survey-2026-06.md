# Prior-art survey: systems near pattern-buffer's shape (2026-06)

**Status:** research note (reference, not canon). Method: three parallel
scouts (cheap-model, web/GitHub) over distinct hunting grounds — bitemporal
agent-memory graphs, historical narrative-state engines, recent LLM-fiction
world-state projects — synthesized here with novelty judgment applied by
the curating instance. Comparison axes: (a) history/as-of, (b) provenance,
(c) perspective frames, (d) explicit-unknown state. Whitepaper §20 covers
the already-known lineage; everything below is NEW relative to §20.

## Nearest neighbors, ranked by closeness

### 1. Graphiti / Zep (2024–25) — the closest living relative
Temporal knowledge graph for LLM agent memory; arXiv 2501.13956.
- **Four timestamps per edge**: `created_at`/`expired_at` (transaction
  window) + `valid_at`/`invalid_at` (world time). Genuine bitemporality.
- **Episodes** (immutable raw inputs) back every derived edge — a real
  provenance chain, structurally similar to our `source` meta-assertions.
- **Divergence 1 (load-bearing):** supersession is **stored** — the old
  edge gets `invalid_at` written onto it when a newer fact arrives. Ours
  is **derived** at fold time (P2): their invalidation judgment is baked
  and unrevisable without mutation; ours rebuilds from the untouched log.
- **Divergence 2:** "conflicts resolved by timestamp metadata alone" — no
  conflict detection at all. The silent last-write-wins our truth
  maintenance exists to refuse is their *design*.
- **Absent:** frames, explicit unknowns, fiction/invention mode, durability
  classes, the render/resolve role split.

### 2. XTDB (Crux) — the bitemporal database peer
Both axes first-class on every document; corrections are new docs with
past valid-time; as-of on either axis. The cleanest independent proof that
our §4.2 time model is sound engineering, not invention. It is a database,
not a world engine: no frames, no provenance vocabulary, no unknowns, no
identity machinery, no LLM boundaries.

### 3. Cyc microtheories — the frames precedent §20 missed
§20 cites Cyc only as the vocabulary cautionary. Its **microtheories** are
the strongest historical precedent for frames: assertions scoped to named
contexts; `#$genlMt` gives transitive inheritance between contexts;
sibling contexts may contradict freely (contradiction is scoped, not
resolved). This is letter-002's frame-inclusion-edges design, decades
early — cite it when inclusion edges land. Absent: time axes, absence
discipline (Cyc filters at query, not at serve), unknowns.

### 4. ATMS (de Kleer) — contested canon as first-class
Holds all consistent "environments" (assumption subsets) simultaneously;
contradictions become minimal **nogood sets** rather than failures; every
derived fact carries its minimal justifying assumptions. JTMS (already in
§20) keeps one worldview; ATMS keeps them all — the deeper precedent for
our contested-truth frames. Absent: persistence, time, entities.

### 5. AriGraph (2024) — the text-game cousin
LLM agent builds an episodic+semantic KG playing TextWorld: append-only
episodes, triplet extraction, bipartite episodic↔semantic links, location
queries by traversal to latest evidence. Single time axis, no corrections,
no frames, no unknowns — but it is the published proof that LLM-extracted
KG world models beat raw-context play, which is our ingestion thesis in
eval form.

### 6. Intra (Ian Bicking, 2025 design notes) — independent convergence
An indie LLM text-adventure design with an immutable event log, per-NPC
visibility scoping (same-room only), and explicitly modeled unknowns —
three of our four axes, arrived at independently. Design notes, not an
engine; visibility is behavioral filtering, not structural absence. The
same convergence-from-an-unrelated-start that the whitepaper's genesis
note treats as evidence of a load-bearing shape.

## The historical fiction-state lineage (the crisp negative result)

Versu/Praxis (modal exclusion logic, timeless facts), Ceptre (linear
logic: facts as resources *consumed* by transitions — the principled
opposite of a log), CiF/Prom Week (~3.5k social rules over scalar
relationship state, overwritten), Façade (transient drama metrics over a
beat tree), storylets/qualities (integer state vector, choices lost after
deltas apply), lorebooks/World Info (static hand-authored snippets with
syntactic triggers — canon injection with no state at all). **Every one
treats state as either overwritten-current or static-canon.** None has
as-of, provenance, frames, or unknowns. Ceptre and CiF remain worth
knowing for the §14 narrative layer (volition rules ≈ character engines;
linear-logic preconditions ≈ evidence-graph gating).

Lorebooks deserve one market note: tens of thousands of users hand-author
and hand-maintain keyword-triggered canon — a folk registry without a log.
The demand for exactly what the ingestion pipeline derives automatically
is already demonstrated at community scale.

## Verdict and what's worth stealing

**Novelty, stated precisely:** every individual mechanism has a precedent
(bitemporality: XTDB/Graphiti; scoped contradiction: microtheories/ATMS;
provenance chains: Graphiti episodes; containment trees: Inform). The
**combination** — one append-only log carrying all four axes, with derived
(never stored) supersession, structural (never behavioral) perspective,
and LLMs confined to four boundary roles — appears in no system found.
Two elements have **no precedent at all** in any hunted ground: explicit
unresolved state with per-world resolution policy (thunks + the one
switch), and thunks-moving-without-resolving.

**Worth stealing / citing:**
1. Graphiti's episode→edge linkage is good provenance UX; our reified
   `source` rows are equivalent but their "show me the episode behind
   this fact" framing is the right porcelain verb shape for `ask`.
2. ATMS **minimal nogood sets** are a future upgrade path for conflict
   *explanations*: today we flag conflicting assertion ids; nogoods would
   name the minimal set of assumptions that jointly conflict.
3. CiF's volition rules and Façade's beat preconditions are the citable
   prior art for §14's character engines and evidence graph respectively.
4. Intra is worth a citation (and possibly a hello) as independent
   convergence.

**Whitepaper §20 amendment candidates** (founder/K call, docs-lockstep):
add Graphiti/Zep, XTDB, microtheories (distinct from the Cyc cautionary),
ATMS, AriGraph, Versu/Ceptre/CiF/storylets as the fiction-state negative
lineage, lorebooks as the folk-demand signal, Intra as convergence.

*Method cost: ~100k tokens, all in three parallel cheap-model scouts;
curation and judgment in the main instance per the delegation directive.*
