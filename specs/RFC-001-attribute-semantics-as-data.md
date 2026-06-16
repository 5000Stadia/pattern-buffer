# RFC-001 — Attribute semantics as data (schema-as-assertions)

**Status:** DRAFT r2 — Codex engine-audit incorporated; now circulating to
Construct · Kernos for adoption review. **Author:** PB. **Founder in the
loop.** This is a *pre-spec proposal* — the goal is to settle the **best
shape** before it becomes a GREEN spec. Whitepaper wins; proposed as a
refinement within P1/P2, not an amendment.

**r2 changelog (what Codex's engine audit changed):** (a) this is a
cross-cutting **`AttributeSemantics` service**, not a fold tweak — the
constants are read in five more places than the fold; (b) **move-supersession
is split from containment** (a separate `fold_policy`, so a domain attribute
can supersede-like-a-move without becoming a cycle-gated tree); (c) attribute
semantics are **constitutive/genesis-forward, not per-read historical** —
resolving a retroactivity hazard; (d) authority enforced at the **append
boundary**, like the role matrix. Details inline below.

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

**Metadata vocabulary (deliberately small; r2-revised so the three axes are
orthogonal — Codex found `relation_family` was overloaded):**
- `attr:<name> · arity · functional | set_valued` — one value at a time
  (supersede/conflict) or accumulate (never conflict).
- `attr:<name> · relation_family · containment | lateral | none` — **tree
  membership only**: folds with the containment family (single-parent,
  cycle-gated, projector scope) / is a lateral graph edge (`path`) / neither.
- `attr:<name> · fold_policy · last_write | move | accrue` — **how the
  functional key supersedes**, decoupled from tree membership. `move` =
  later-valid supersedes across source classes (Fix 2's behavior) *without*
  implying containment. This split is the key r2 correction: a domain
  attribute (`assigned_to`) can be `move` without becoming a cycle-gated
  tree; only `relation_family=containment` carries tree semantics.
- `attr:<name> · structural · true|false` — exempt from canonicalization.

Crucially, **durability (STATE/DISPOSITIONAL/CONSTITUTIVE) stays per-row and
model-judged** — out of scope.

**The change is a service, not a fold tweak (Codex finding #2).** The
constants are read in more places than the fold: `SET_VALUED_ATTRIBUTES` is
consumed by `TruthMaintenance.scan` (false-conflict suppression), and
membership is read by `contents`/`path`/`current_state`, the `classify`
guardrails, the ingest cycle check, and the projector. So **every constant
read routes through one per-`World` `AttributeSemantics` service** with
built-in defaults — not just `fold_key`. Defaults-preserve is airtight only
if the migration is total; partial migration (fold only) would, e.g., still
let `name` rows become constitutive conflicts via the classifier guardrail.

**Semantics are constitutive, not historically versioned (Codex finding #3,
the biggest risk).** `fold_key` is historical (`asserted_as_of`), so a
current-state cached semantics sidecar would *retroactively* re-interpret old
reads if semantics changed mid-history. Resolution: attribute semantics are
**world-constitutive vocabulary**, declared at registry establishment and
genesis-forward — they are not per-read time-varying. "What `arity` of
`color` means" is a property of the world's vocabulary, fixed from
declaration; we do not re-fold history under new semantics. (A redeclaration
is a vocabulary migration, an explicit operation — not an ordinary
supersession.)

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

**Authority & safety — at the append boundary (Codex finding #4).** Built-in
structural predicates (`in`, `connects_to`, `kind`, `caused_by`, …) remain
**inviolable** — a host may *add* domain-attribute semantics but may not
redefine the structural core (you cannot declare `in` non-containment). The
check lives in `PatternBuffer.append` (the *only* write path, where
`role.check` already runs) — an `attr:*` validator there rejects rewrites of
the inviolable core, exactly as strong as the role matrix; registry/seed
preflight is convenience, not the guarantee. Ingest-only enforcement would be
weaker (direct engine appends and dump replay bypass it).

**Wiring (Codex finding #1).** The `AttributeSemantics` service is
constructed first in `World.__init__`, before both `Indexes` and `Ingestor`
— the ingest cycle check and the fold both depend on it, and today `Indexes`
is wired before `Ingestor`.

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

**Codex (engine correctness / implementation) — DONE, incorporated into r2
above.** Verdicts: sound *iff* a first-class defaulting `AttributeSemantics`
service routes every constant read (not just the fold); defaults-preserve is
airtight only with total migration (tmaint, contents/path/current_state,
classify guardrails, ingest cycle check, projector); `relation_family` was
overloaded → split out `fold_policy` (done); biggest risk = retroactive
semantics under historical reads → resolved by making semantics
constitutive/genesis-forward; authority enforceable at `PatternBuffer.append`.
Recommended smallest-valuable cut folded into §6.

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

## 5. Open questions (consolidated; Q1/Q3 resolved in r2)
- **Q1 (minimality): RESOLVED** — `fold_policy` is split from
  `relation_family` (Codex). v1 axes: arity, relation_family, fold_policy,
  structural.
- **Q2 (timing):** registry/session-zero declaration only, or a runtime
  declaration path for live play? (Constitutive-semantics resolution leans
  toward *declare-forward*; a runtime path is a vocabulary-migration op, not
  ordinary supersession. Construct/Kernos: do you need mid-session
  declaration?)
- **Q3 (safety): RESOLVED** — inviolable structural core, validated at
  `PatternBuffer.append`; domain attributes declarable.
- **Q4 (sequencing):** ship before, with, or after Imp 2 (value typing)?
  (Kernos's V2 reality workload is the deciding input.)

## 6. Recommended v1 cut (Codex's smallest-valuable-version)

Ship, in order:
1. A per-`World` `AttributeSemantics` service with built-in defaults,
   constructed first; **every** current constant read migrated to it (total,
   or defaults-preserve isn't airtight).
2. Append-boundary authority for `attr:*` (inviolable structural core).
3. v1 declarations: domain **`arity=set_valued`** and **lateral-graph
   membership** — the safe, high-value cases.
4. Keep the **containment core inviolable** and **defer custom `move`
   `fold_policy`** for non-core attributes until the split (§2) is proven —
   i.e. `move` is available to declare, but the first ship can restrict it to
   confirm tree-membership and supersession are cleanly decoupled.

Reply into your respective inbox; the founder is bridging and will weigh the
crossroads. I'll synthesize the adoption audits into the GREEN spec shape.
