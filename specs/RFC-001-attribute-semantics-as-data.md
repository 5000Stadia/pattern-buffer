# RFC-001 — Attribute semantics as data (schema-as-assertions)

**Status:** DRAFT for three-way deliberation (Codex · Construct · Kernos).
**Author:** PB. **Founder in the loop.** This is a *pre-spec proposal* — the
goal of circulating it is to settle the **best shape** before it becomes a
GREEN spec. Whitepaper wins; this is proposed as a refinement within P1/P2,
not an amendment to them.

## 0. Origin
Came out of a founder-requested architecture reflection on whether
pattern-buffer's data structure and engagement syntax are formed optimally
(see `docs/HOST-DISCIPLINE.md` for the disciplines that exposed the seam).
Verdict of that reflection: the core row + append-only + fold primitive is
right; the strongest improvement is making **attribute behavior** data-driven
rather than code-resident. This RFC is that improvement, plus the related
items it touches, framed for adoption review.

---

## 1. The problem

An attribute is a flat string, but its **behavior** is decided by frozensets
in `src/patternbuffer/model.py`:
- `CONTAINMENT_FAMILY` — which attributes fold as one containment key and get
  single-parent + move-supersession semantics.
- `SET_VALUED_ATTRIBUTES` — which attributes accumulate values instead of
  conflicting (name, alias, connects_to, …).
- `STRUCTURAL_PREDICATES` — which are structural vs domain.

The fold (`indexes.py`) branches on these constants. **Three consequences:**

1. **Not domain-extensible without engine code.** A host with domain
   vocabulary can't declare "`exits` is set-valued" or "`assigned_to`
   supersedes like a move" — it must edit the engine. That violates the
   spirit of "domain vocabulary emerges freely; the engine stays host-blind."
2. **The fold accretes attribute-kind branches.** LIVE-FINDINGS Fix 2 keyed
   move-supersession on `attribute ∈ CONTAINMENT_FAMILY` — a behavior switch
   on a code constant. Each such addition piles policy into one function.
   That is the canary: the fold *wants* attribute metadata it can read.
3. **Global, not per-world.** The constants are process-global; two worlds
   with different domain conventions can't differ.

Note the precedent that makes the fix obvious: attribute **canonicalization**
is *already* data — `canonicalized_from` receipts in the log, rebuilt into a
sidecar map (`ingest._rebuild_alias_map`). Arity/family are the same kind of
fact, still trapped in code.

## 2. Proposal — attribute semantics as rebuildable meta-assertions

Declare per-attribute semantics as ordinary assertions about an
`attr:<name>` entity, rebuilt into a sidecar the fold consults — exactly the
canonicalization-as-receipts pattern, generalized.

**Metadata vocabulary (deliberately small, fixed enum):**
- `attr:<name> · arity · functional | set_valued` — does the key hold one
  value at a time (supersede/conflict) or accumulate (never conflict)?
- `attr:<name> · relation_family · containment | lateral | none` — folds with
  the containment family (single-parent, move-supersession) / is a lateral
  graph edge (`path`) / neither.
- `attr:<name> · structural · true|false` — exempt from canonicalization, a
  fixed predicate.

That's it for v1. Crucially, **durability (STATE/DISPOSITIONAL/CONSTITUTIVE)
stays per-row and model-judged** — it is not attribute-level and is out of
scope here. We are only lifting the *attribute-level* switches the fold
already keys on.

**Defaults preserve today's behavior exactly.** The built-in frozensets
become the *default* semantics when no meta-assertion overrides:
unspecified attributes behave bit-identically to now. Existing worlds and
all current tests are unchanged. This is additive.

**Where declarations come from.** The registry already carries attribute
canonicalization (pass-0 establishes alias→canonical). Extend it to carry
arity/relation_family; `seed_items` emits them as meta-assertions at commit.
Live play can extend the registry turn-by-turn (same `establish`/`extend`
interface), so a new attribute's semantics can be declared when first seen.

**Rebuild.** On load, scan visible `attr:*` meta-assertions into an
attribute-semantics sidecar (alongside the canonicalization map and the
durability sidecar). The fold reads `attr_semantics(attribute)` instead of
the module constant. Rebuildable, derived, append-only-clean.

**Authority & safety (open — see Q3).** Proposed: built-in structural
predicates (`in`, `connects_to`, `kind`, `caused_by`, …) remain
**inviolable** — a host may *add* domain-attribute semantics but may not
redefine the structural core (you cannot declare `in` non-containment).
Domain attributes are declarable. Write authority sits with the ingestor at
registry establishment (these are constitutive vocabulary facts).

**Fold impact.** `fold_attribute()` and the set-valued/containment branches
read the sidecar. Fix 2's `is_containment` becomes
`relation_family == containment` *from data*. No porcelain signature changes
(additive internals).

## 3. Related items from the reflection (scope boundary, for the deliberation)

Not part of v1; listed so reviewers can weigh sequencing and whether the
spec's boundary is drawn right:

- **Imp 2 — typed/indexed value retrieval.** `value` is a JSON blob; reads
  into it are exact-match only. Range/comparison predicates over scalar
  literals (`temperature > 50`) aren't expressible — a real recall gap in
  **reality-tracking** mode. Candidate next, independent of this RFC.
- **Imp 3 — frame inheritance (#15.3, parked).** Generalizes the knowledge-
  correlation axis (`frame_diff`) into a fold. Already roadmapped.
- **Fork A — a general multi-hop / graph-pattern read verb.** The
  HOST-DISCIPLINE "correlation sweep" is a *host recipe* because the engine
  exposes only fixed walks. Promoting it to a verb risks P7 minimalism.
  Recommend: keep host-composed until a host proves it needs the primitive.
- **Fork B — salience/relevance ranking primitive.** Left to the host today.
  Pull down only if multiple hosts reimplement the same ranking.

## 4. The deliberation — what each reviewer is asked to audit

Please audit from your position and propose the **best shape going in**:

**Codex (engine correctness / implementation):**
- Is "schema-as-assertions rebuilt into a sidecar" sound and deterministic
  against the existing canonicalization/durability sidecar patterns?
- Fold-path integration: any case where reading semantics from data (vs the
  constant) changes a current fold result, i.e. is the defaults-preserve
  claim actually airtight against the test suite?
- The authority/inviolable-core boundary (Q3) — is it enforceable in code
  the way the role-authority matrix is?
- Is v1's metadata set (arity, relation_family, structural) the right
  minimal cut, or is something missing/excess?

**Construct (live IF host — adoption):**
- Do you hit the code-constant wall today? Concretely: would you *use*
  per-attribute `arity`/`relation_family` declarations (e.g. set-valued
  `exits`, a custom move-relation, domain functional keys)? Or does your
  current vocabulary fit the built-ins fine?
- Should declarations be establishable mid-session (live play) or is
  session-zero-only acceptable for you?
- Any read-path / `SnapshotReads` implications if fold semantics become
  data-driven?

**Kernos (V2 / World Model — adoption + philosophy):**
- Does a continuous, open-ended real-world World Model *need* data-driven
  attribute semantics (likely yes for unbounded vocabulary)? What's the
  shape that serves V2?
- Is "schema as assertions" the right philosophical fit, or does it risk
  reintroducing schema rigidity the substrate was meant to avoid? Where's the
  line between *declared semantics* (good) and *enforced schema* (against the
  grain)?
- Sequencing: this before/with Imp 2 (value typing), given V2's quantity-
  heavy reality workload?

## 5. Open questions (consolidated)
- **Q1 (minimality):** arity + relation_family + structural — enough, or do
  we need a first-class declarable `fold_policy` (move | last_write | accrue)
  per attribute, decoupled from relation_family?
- **Q2 (timing):** registry/session-zero declaration only, or a runtime
  declaration path for live play?
- **Q3 (safety):** inviolable structural core + declarable domain attributes
  — right boundary, and code-enforceable?
- **Q4 (sequencing):** ship before, with, or after Imp 2 (value typing)?

Reply into your respective inbox; the founder is bridging and will weigh the
crossroads. I'll synthesize the three audits into the GREEN spec shape.
