# ATTRIBUTE-SEMANTICS-V1 — attribute semantics as data (the GREEN-candidate spec)

**Status:** SPEC r2 — Codex build-review RED (r1) addressed; re-review
pending. Synthesis of RFC-001 (r3) and its three adoption audits. **Whitepaper
wins; a refinement within P1/P2.** RFC-001 is the rationale; this is the build.

**r2 changelog (Codex RED r1 → fixes):** (a) **`set_valued` needs a real
multi-value fold** — today it only suppresses conflict flagging; the fold
still serves a single winner. Added `FoldResult.values` (additive; `.winner`
preserved for compat) as the actual fix the cigarette-tin bug requires. (b)
**Authority hole closed** — `dump.build` bypasses `append()` via private
`_insert`; the `attr:*` guard now lives in a **shared insert validator** both
paths call. (c) Three missed migration call sites added
(`ingest._canonicalize`, the `_ingest_item` containment read, the
`classify` durability guardrail). (d) **Emit-order rule** added (declaration
appends before its first data row). (e) `attr:*` entities declared
engine-meta (excluded from world-fact enumeration). (f) Fixture corrected:
the tin bug is fixed via the multi-value fold (`state(tin,"contains").values`),
**not** `contents()` (which is `in`/child→parent and unchanged);
inverse-containment unification is explicitly out of v1.

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

- **`arity` ∈ {`functional`, `set_valued`}** — one value at a time vs
  accumulate. *Default:* `functional`, **except** the built-in set-valued
  names (below). **Read shape (new — Codex r1 #2/#6):** today `set_valued`
  only suppresses conflict flagging while the fold still serves *one*
  winner; that is why the cigarette tin loses four rows. v1 adds a genuine
  multi-value fold: `FoldResult` gains **`values: tuple`** carrying *all*
  current members for a `set_valued` key (per-source recency still applies —
  a member superseded by a later row at its own key drops out). This is
  **additive**: `.winner` is unchanged (still the most-recent member, so
  every existing `.winner` reader — `current_state["name"]`, etc. — behaves
  bit-for-bit as today); new consumers read `.values`. `functional` keys
  leave `.values` empty and read `.winner` as now.
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
defaults-preserve guarantee (Codex). Complete call-site list (r2: + the three
Codex r1 #1 found missed):**
- `indexes.fold_attribute` / `fold_key` (family key; the Fix 2 `is_containment`
  branch → `relation_family == containment`).
- `indexes._fold_state` (arity gate: `set_valued` keys never conflict **and**
  now populate `FoldResult.values`).
- `tmaint.scan` false-conflict suppression (today reads `SET_VALUED_ATTRIBUTES`).
- `indexes.contents` / `path` / `current_state` (family/lateral membership).
- `classify` guardrails — **both** the structural classification of
  structural keys **and** the containment-family durability subrule
  (`classify.py` "held by agents are movable → STATE"), which reads
  `CONTAINMENT_FAMILY` today.
- `ingest._canonicalize` (reads `STRUCTURAL_PREDICATES` to bypass alias
  canonicalization for structural names).
- `ingest._ingest_item` (the containment-family read that gates the
  `_reject_cycle` call — the actual read site).
- `project` (projector containment scope).

**`attr:*` meta-assertions are engine-meta.** The new metadata predicates
(`arity`/`relation_family`/`fold_policy`/`structural`) live on `attr:<name>`
entities and must be excluded from world-fact enumeration exactly as `a:`
assertion-meta rows are (`materialize`/`snapshot`/`current_state`/`refer`
scope walks skip the `attr:` namespace; the predicates join `META_ATTRIBUTES`
treatment). They are vocabulary declarations, never world facts.

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

**Emit-order rule (Codex r1 #3, required for correctness):** when an undeclared
non-core attribute is first seen in `_ingest_item`, the `attr:*` declaration
is appended **before** the triggering data row. So at the moment the data row
lands, the semantics already exist and the immutability check (§5) sees no
prior folded row for that attribute. Within a single `ingest_structured`
batch this makes first-declaration-plus-first-use coherent and order-stable;
on rebuild, the declaration's lower `seq` guarantees it is replayed first.

## 5. Authority, safety, immutability (Codex + Kernos Q2/Q3)

- **Inviolable structural core.** A fixed set (`in`, `connects_to`,
  `adjacent_to`, `kind`, `caused_by`, the containment family, identity
  predicates) cannot be redeclared. A host may *add* domain-attribute
  semantics, never redefine a constitutional primitive (you cannot make `in`
  non-containment).
- **Enforced in a shared insert validator (Codex r1 #4 — the critical fix).**
  `append()` is *not* the only insert path: `dump.build` validates the
  builder role then calls private `_insert` directly, bypassing `append`. So
  the `attr:*` guard (core-redefinition + immutability) must live in a shared
  validator that **both** `append` and `_insert` call — otherwise a tampered
  dump could inject a forbidden `attr:*` row on replay. Replay of a *valid*
  log passes by construction: it contains no core-redefining `attr:*` rows
  (they were rejected at original append), and the emit-order rule put each
  legitimate declaration at a lower `seq` than its data, so re-insertion in
  `seq` order re-satisfies immutability. Registry/ingest preflight stays as a
  convenience; the shared validator is the guarantee.
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
   migration of all §3 call sites; `attr:*` engine-meta exclusion.
2. The multi-value fold: `FoldResult.values` populated for `set_valued` keys
   (additive; `.winner` preserved) — this is the actual cigarette-tin fix.
3. Shared insert validator (`append` + `dump._insert`) enforcing the
   inviolable core + immutability for `attr:*`.
4. Declaration: explicit hint **and** the `attribute_default` hook (both —
   the hook is what makes it usable for a live-IF host), with the emit-order
   rule.
5. Wire `arity=set_valued` and `relation_family=lateral` end to end. Keep the
   containment core inviolable; `fold_policy=move` honored only for the core
   (custom non-core `move` recorded-but-deferred).

No porcelain signature changes (additive: `attribute_default` is a new
optional `World` kwarg; hints are optional item keys). `accrue` and
non-core `move` wiring, vocabulary-migration ops, and value-typing (Imp 2,
the founder-ruled next spec) are explicitly out.

## 7. Tests (assert invariants, not just returns)

- **Defaults-preserve:** the full existing suite passes with zero
  declarations (bit-for-bit behavior).
- **The motivating bug (multi-value fold):** `obj:tin · contains · {a,b,c,d,e}`
  with `contains` declared `set_valued` → `state(tin,"contains").values`
  returns **all five**; without the declaration → today's single `.winner`
  (documents the bug and the fix). **Note:** this is the multi-value fold,
  **not** `contents()` — `contents()` is `in`/child→parent and is unchanged;
  inverse-containment unification (making `contains` feed `contents`) is out
  of v1.
- **`.winner` compat:** `current_state["name"]` for a multi-name entity still
  returns the single most-recent name in `.winner` (unchanged), while
  `.values` now carries all names — proving the read-shape addition is
  non-breaking.
- **Hook path:** an `attribute_default` returning `set_valued` for `contains`
  → a model-minted `contains` row folds set-valued with no manual per-attr
  step; the `attr:contains` meta-assertion is materialized once, lands at a
  lower `seq` than the data row (emit-order), and is rebuildable.
- **Immutability:** declaring/hinting a different arity after a folded row
  exists → rejected (migration error), original semantics hold.
- **Inviolable core, both paths:** `attr:in · relation_family · none` →
  rejected at `append`; **and** the same row injected into a dump → rejected
  on `dump.build` replay (the shared-validator test — guards Codex r1 #4).
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
