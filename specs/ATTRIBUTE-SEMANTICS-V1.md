# ATTRIBUTE-SEMANTICS-V1 — attribute semantics as data (the GREEN-candidate spec)

**Status:** SPEC, pre-Codex-GREEN. Synthesis of RFC-001 (r3) and its three
adoption audits — Codex (engine), Kernos (V2/philosophy), Construct
(live-IF). All three GREEN on shape; every crossroads ruled. This spec is
the implementable form; it goes to Codex for GREEN before implementation per
the standing loop. **Whitepaper wins; a refinement within P1/P2, not an
amendment.** RFC-001 is the rationale and the audit record; this is the build.

## 1. Goal & the bug it fixes

Lift attribute-level *behavior* out of engine code constants
(`CONTAINMENT_FAMILY`, `SET_VALUED_ATTRIBUTES`, `STRUCTURAL_PREDICATES`) into
per-world, rebuildable, declared semantics that **every** semantics consumer
reads through one service — so domain vocabulary carries its own fold
behavior without engine edits, resolving the substrate's latent
domain-blindness contradiction.

**Motivating bug (shipped, live in Construct's `anchor` world):** model-minted
relations not in the built-in frozensets fold as functional/last-write and
silently drop data. `obj:flat_steel_tin · contains · {cig_1..5}` keeps **one**
cigarette; four are lost. The cigarette tin is the v1 regression fixture
(Construct supplies it).

## 2. The model — three orthogonal attribute-level axes

Declared as ordinary assertions about an `attr:<name>` entity (the
canonicalization-as-receipts pattern generalized), rebuilt into a sidecar:

- **`arity` ∈ {`functional`, `set_valued`}** — one value at a time
  (supersede/conflict) vs accumulate (never conflict). *Default:*
  `functional`, **except** the built-in set-valued names (below).
- **`relation_family` ∈ {`containment`, `lateral`, `none`}** — **tree
  membership only**: folds with the containment family key (single-parent,
  cycle-gated, projector containment scope) / is a lateral graph edge
  (`path`) / neither. *Default:* per the built-in families.
- **`fold_policy` ∈ {`last_write`, `move`}** — how a *functional* key
  supersedes. `move` = later-valid supersedes across source classes
  (LIVE-FINDINGS Fix 2's behavior). *Default:* `last_write`; an attribute
  with `relation_family=containment` is `move` (this is how Fix 2's
  `is_containment` becomes data). **v1 restriction:** `move` is *only*
  honored for the inviolable containment core; declaring `move` on a
  non-core attribute is accepted and recorded but not yet wired (deferred
  until the family/policy split is proven live — Construct confirms it needs
  no non-core `move` today). `accrue` is reserved, not wired in v1.

**Durability (STATE/DISPOSITIONAL/CONSTITUTIVE) stays per-row and
model-judged — out of scope.** The seam (Kernos): attribute-level metadata
is only for what is *genuinely invariant about the vocabulary*; lifting an
instance-contingent property (durability above all) to attribute level would
be schema rigidity and is forbidden.

**The philosophy guardrail (Kernos rejection-test), binding on this spec:** a
declaration must never cause an assertion to be *rejected or dropped* — it
governs how a fact *folds*, never whether it is *admitted*. The only
rejection in this spec is the inviolable-core authority guard (§5), which is
authority-on-vocabulary, not schema-on-facts.

## 3. The `AttributeSemantics` service (total migration — Codex)

A per-`World` service, **constructed first** in `World.__init__` (before
`Indexes` and `Ingestor`, both of which depend on it). It answers
`semantics(attribute) -> {arity, relation_family, fold_policy, structural}`,
returning built-in defaults for any attribute with no declaration.

**Every current constant read migrates to it — partial migration breaks the
defaults-preserve guarantee (Codex).** Exact call sites:
- `indexes.fold_attribute` / `fold_key` (family key; the Fix 2 `is_containment`
  branch → `relation_family == containment`).
- `indexes._fold_state` (arity gate: `set_valued` keys never conflict).
- `tmaint.scan` false-conflict suppression (today reads `SET_VALUED_ATTRIBUTES`).
- `indexes.contents` / `path` / `current_state` (family/lateral membership).
- `classify` guardrails (structural classification of `name`/structural keys).
- `ingest._reject_cycle` (containment-family cycle gate).
- `project` (projector containment scope).

**Rebuild:** scan visible `attr:*` meta-assertions into the sidecar on load,
exactly like the canonicalization map and the durability sidecar.
Deterministic; rebuildable; append-only-clean.

**Built-in defaults (preserve today's behavior bit-for-bit):**
| Default source | Maps to |
|---|---|
| `CONTAINMENT_FAMILY` (`in`,`within`,`held_by`,`worn_by`,`carried_by`) | `relation_family=containment`, `fold_policy=move`, `arity=functional` (single-parent) |
| `SET_VALUED_ATTRIBUTES` (`name`,`alias`,`connects_to`,`adjacent_to`,`same_as`,`maybe_same_as`) | `arity=set_valued`; `connects_to`/`adjacent_to` also `relation_family=lateral` |
| `STRUCTURAL_PREDICATES` | `structural=true` |
| everything else | `arity=functional`, `relation_family=none`, `fold_policy=last_write` (unchanged from today) |

Defaults-preserve is verified by running the **entire existing suite green**
with zero declarations present.

## 4. Declaration — cheap at the ingest boundary (Construct, load-bearing)

A live-IF host's vocabulary is **model-minted at play time**, so declaration
cannot be session-zero-only or per-attribute-manual. Two paths, both
producing the same ground-truth `attr:*` meta-assertion:

1. **Explicit hint.** An `ingest_structured` item (or registry entry) may
   carry optional `arity` / `relation_family` / `fold_policy`. The **first**
   time an undeclared, non-core attribute is seen with a hint, the gate emits
   its `attr:*` meta-assertion (under ingestor authority). Later hints on an
   already-folded attribute are ignored (immutability, §5).
2. **Host default policy.** `World(..., attribute_default=fn)` where
   `fn(attribute_name) -> dict | None`. Consulted **once**, at first sight of
   an undeclared non-core attribute (at ingest), to materialize its semantics
   as a meta-assertion. This is the live-IF ergonomic: the host states a
   rule (`"container/part/possession relations default set_valued"`) and the
   engine applies it to model-minted vocabulary automatically — **the engine
   never decides arity; the host's rule does.** `fn` returning `None` →
   built-in defaults. Pure function of the name; result is logged, so it is
   rebuildable and immutable thereafter.

Resolution order at first sight: existing declaration → explicit hint →
`attribute_default` hook → built-in default. The core (§5) short-circuits
all of these.

## 5. Authority, safety, immutability (Codex + Kernos Q2/Q3)

- **Inviolable structural core.** A fixed set (`in`, `connects_to`,
  `adjacent_to`, `kind`, `caused_by`, the containment family, identity
  predicates) cannot be redeclared. A host may *add* domain-attribute
  semantics, never redefine a constitutional primitive (you cannot make `in`
  non-containment).
- **Enforced at the append boundary** (the sole write path, where
  `role.check` already runs): `PatternBuffer.append` rejects an `attr:*`
  meta-assertion that targets a core attribute. Registry/ingest preflight is
  convenience; the append check is the guarantee (direct appends and dump
  replay also pass through it).
- **Immutability (Kernos Q2).** *An attribute's semantics are immutable once
  its first folded (non-`attr:`) row exists.* First-declaration of a
  previously-unseen attribute is allowed at any wall-clock moment
  (genesis-forward for that attribute's own timeline — no retroactivity,
  since no prior folded history). Redeclaration over folded history is a
  distinct, explicit **vocabulary-migration op** (out of v1 scope; v1 rejects
  it at the append boundary with a clear error), never an ordinary
  supersession. This preserves Codex's retroactivity fix while giving live-IF
  its runtime declaration.

## 6. v1 cut (ship exactly this)

1. `AttributeSemantics` service + built-in defaults, constructed first; total
   migration of all §3 call sites.
2. Append-boundary authority for `attr:*` (inviolable core; immutability).
3. Declaration: explicit hint **and** the `attribute_default` hook (both —
   the hook is what makes it usable for a live-IF host).
4. Wire `arity=set_valued` and `relation_family=lateral` end to end. Keep the
   containment core inviolable; `fold_policy=move` honored only for the core
   (custom non-core `move` recorded-but-deferred).

No porcelain signature changes (additive: `attribute_default` is a new
optional `World` kwarg; hints are optional item keys). `accrue` and
non-core `move` wiring, vocabulary-migration ops, and value-typing (Imp 2,
the founder-ruled next spec) are explicitly out.

## 7. Tests (assert invariants, not just returns)

- **Defaults-preserve:** the full existing suite passes with zero
  declarations (bit-for-bit behavior).
- **The motivating bug:** `obj:tin · contains · {a,b,c,d,e}` with `contains`
  declared `set_valued` → `contents`/fold return **all five**; without the
  declaration → today's last-write (documents the bug and the fix).
- **Hook path:** an `attribute_default` returning `set_valued` for `contains`
  → a model-minted `contains` row folds set-valued with no manual per-attr
  step; the `attr:contains` meta-assertion is materialized once and is
  rebuildable.
- **Immutability:** declaring/hinting a different arity after a folded row
  exists → rejected at append (migration error), original semantics hold.
- **Inviolable core:** `attr:in · relation_family · none` → rejected at
  append; `in` stays containment.
- **Lateral membership:** a declared `lateral` domain relation participates
  in `path`; `arity=set_valued` accumulates.
- **Rebuild:** drop the sidecar, rebuild from the log → identical semantics
  (parity with canonicalization/durability rebuild).
- **Frame/as-of unaffected:** semantics are world-constitutive, not
  frame/time-scoped; historical reads fold under the (immutable) declared
  semantics.

## 8. Out of scope / sequencing
- **Imp 2 — value typing/indexing** (range predicates over scalars): the
  founder-ruled *next* spec, back-to-back, kept separate (001 = fold
  behavior; Imp 2 = value comparability). No value-typing hints here.
- Frame inheritance (#15.3), the correlation-sweep verb (Fork A — host
  recipe until a forbidden host-side full-log scan appears), salience (Fork
  B). Unchanged.
- Adjacent finding (Construct): lateral self-loops (`X connects_to X`) are
  extraction noise the containment self-edge gate doesn't cover. Noted; a
  separate small gate item, not this spec.
