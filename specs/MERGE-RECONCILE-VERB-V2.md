# MERGE-RECONCILE-VERB-V2 — structure-first individuation (distinct_from, reject, precision merger)

**Status:** DRAFT → Codex + Conduit GREEN before implementation. Extends
MERGE-RECONCILE-VERB-V1. Additive on porcelain-v0.1. Honors the round-robin
precedent (*engine surfaces structure; host supplies meaning*) and the founder's
individuation principle:

> **The author individuates through structure; the engine preserves distinctness
> and only auto-merges the obvious. It never auto-decides two ambiguous things
> are one.**

## Foundation (not in question)
The substrate already represents two distinct same-named entities — two Clays
(`person:clay1`, `person:clay2`, both `name:"Clay"`), two bedrooms
(`place:bedroom1`, `place:bedroom2`, each `in:house` with its own contents). They
are distinct by **id and structure**. The only thing that could collapse them is
the auto-merger fusing them by mistake. V2 makes the merger **precision-biased**
so it can never destroy authored distinctness, and adds the explicit "these are
different" record so a separation decision sticks. The engine is **not** asked to
solve general individuation — only to preserve what the author mapped and to
*propose* (not merge) when distinctness is plausible.

## §1 `distinct_from` — the anti-merge primitive (the mirror of `same_as`)
The log can assert `same_as` ("these are one") but has no inverse. Add
**`distinct_from`** — an authored entity-valued edge: "definitively not the same."
- **Primitive placement (Codex r1 #2):** `distinct_from` joins exactly the sets
  `same_as` is in — `INVIOLABLE_CORE` (buffer guard protects it; only the
  ingestor/resolver role may write it), `META_ATTRIBUTES` (meta-hidden from
  materialization), and `SET_VALUED_ATTRIBUTES` (one entity may be distinct from
  many; coexisting values are data, never a conflict). It is appended as a single
  entity-valued `status="stated"` row via the ingestor role.
- `distinct_block(a,b) -> list[str]` — visible `distinct_from` edges relating
  `closure(a)↔closure(b)` (`a·distinct_from·b`). Mirror of `containment_block`.
- **Hard veto** (like containment): `merge()`/`guarded_merge()` refuse when
  `distinct_block` is non-empty; `_mergeable` False; `reconcile`/`promote` skip
  the pair (never merge AND never re-propose — settled).
- **Contradiction guard:** if a,b already share a closure (`same_as`), asserting
  `distinct_from` is surfaced as a conflict at `reject()` — the host retracts the
  `same_as` first (never silently resolved). Append-only; membrane-clean.

## §2 `reject(a, b)` — sticky separation (the complement of confirm/merge)
- **`p.reject(a, b) -> Receipt`** asserts `distinct_from(a, b)` through the gate.
- Outcomes:
  - `rejected` — one `distinct_from` row appended.
  - `noop_already_distinct` — a `distinct_from` already relates the closures.
  - `conflict_already_merged` — **path-aware** (Codex r1 #3): `resolve(a) ==
    resolve(b)`, so they already share a `same_as` closure; the receipt names the
    visible `same_as` assertion id(s) **and** merge-event id(s) on a path between
    them (so the host knows what to retract) and **writes nothing**.
- Effect: a "different entities" call becomes **permanent** — `reconcile()` /
  `proposals()` never re-surface the pair. The two Clays stay apart on every run.

## §3 Precision-biased merger — structure downgrades auto-merge to *propose*
The auto-merger (`reconcile`/`promote`) keeps merging the obvious, but **any
distinctness signal downgrades to a proposal** (the host then confirms / rejects /
defers). Two new downgrades beyond the shipped containment veto + kind gate:

- **(a) Relating-edge downgrade** (round-robin "*any relating edge between two
  candidates is evidence against identity*"): if any visible **non-identity,
  entity-valued** edge relates `closure(a)↔closure(b)` — i.e. attribute ∉
  {`same_as`, `maybe_same_as`, `distinct_from`} and not a meta row — do **not**
  auto-merge → propose. This spans the lateral family (`connects_to`,
  `adjacent_to`) **and** generic relations (`father_of`, `custodian`, `ally_of`,
  `owns`, …, which fold as `relation_family="none"`). Catches
  `clay1·father_of·clay2`. (Codex r1 #1: the **containment** family —
  `in`/`held_by`/`worn_by`/`carried_by`/`within` — is the *hard* veto, already
  shipped, so `footlocker·held_by·sela` is *already* vetoed; this soft downgrade
  is for the remaining relating edges. Soft = propose, host may still confirm;
  hard = never.)
- **(b) Non-distinctive-anchor downgrade** (the bedroom case): a shared anchor
  whose **normalized text equals the entity's folded `kind` value** is the *type
  word*, not a distinguishing name (`name:"bedroom"` on `kind:bedroom`) → does not
  drive auto-merge → propose. Two bedrooms named "bedroom" never silent-merge;
  distinctive proper names (`"Frodo"` ≠ kind `person`; `"memory core"` ≠ kind
  `core`) still auto-merge with corroboration. Compares two **authored facts**
  (name vs kind) — structural, not host vocabulary.

Net: recall preserved for distinctive, unrelated, corroborated corefs (one Frodo
across chunks); every ambiguous/related/generic pair becomes a proposal the host
adjudicates — confirm, `reject`→`distinct_from`, or defer. Precision over recall:
when in doubt, stay distinct.

## §4 Tests (invariants)
1. `distinct_from` hard-vetoes `merge`/`guarded_merge` (`vetoed`, reason
   `distinct_from`, edges named); resolve stays distinct.
2. `reconcile`/`promote` never merge a `distinct_from` pair AND never re-propose it.
3. `reject(a,b)` → `rejected` (writes distinct_from); second → `noop_already_distinct`;
   `reconcile` no longer lists the pair.
4. `reject` on an already-merged pair → `conflict_already_merged`, names the
   same_as, writes nothing.
5. **Relating-edge (soft):** `clay1·father_of·clay2` (generic relation) sharing
   name "Clay" → **proposed, not merged**; likewise an `adjacent_to`/`ally_of`
   edge between two same-named closures. (Separately: a `held_by`/containment edge
   is **hard-vetoed** by the shipped containment veto — both paths leave them
   distinct, by different mechanisms.)
6. **Two bedrooms:** `bedroom1`/`bedroom2`, both `in:house`, `name:"bedroom"`,
   `kind:bedroom` → **proposed, not merged** (name==kind non-distinctive).
7. **Recall preserved:** two closures sharing distinctive `name:"Frodo"` (≠ kind),
   no relating edge, compatible kind → still auto-merge.
8. **core-×3 preserved:** shared `"memory core"` (≠ kind) still merges.
9. membrane: reads write nothing; `reject` appends only the `distinct_from` edge.

## Follows (separate lean spec, same round-robin)
The structured `auto_decline` triage payload (round-robin (C): `code`-first,
`related_rows` decisive, `hard_veto` incl. `distinct_from`, structural
`relation_family` only) ships next as TRIAGE-CONTEXT-V1 — read-side enrichment of
proposals, surfacing exactly the §3 structural signals so the host's
confirm/reject/defer is a glance.
