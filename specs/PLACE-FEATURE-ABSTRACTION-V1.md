# PLACE-FEATURE-ABSTRACTION-V1 — the compositional axis (place ∧ feature)

**Status:** Implemented; Cx-reviewed (064 YELLOW → blockers pinned; 065 fix:
identity-aware CONSTITUTIVE conflict). Additive on porcelain-v0.1.
Build item 2 of the awareness-and-shape plan (round-robin conclusion 060/061;
Kernos 053 #5 + Cx 055 #5 named it a build-now concrete read). The El.4 "open
part": a sub-place that is both a **place** and a **feature** of a larger place.

## Problem
A place can be a structural sub-part of a larger place — a **burrow** dug into a
hillside, an alcove in a saloon, a hidden compartment in a desk. The host needs to
model it as **one entity** that answers both lenses coherently:
- *as a place* — you can route to it, be inside it, it has contents and state;
- *as a feature* — it is part of the hillside's structure.

This is the **compositional analogue of AKA-CORRELATION-V1**: AKA unified *identity*
facets (one identity, two faces); this unifies a *place* with its *composition*
(one entity, two access lenses). It is **not** the general structure-polymorphism
framework (deferred until a third shape forces it) — just the one concrete
compositional axis the burrow/saloon-hole class needs.

## Why a new axis, not reuse of containment
Containment (`in`/`within`/`held_by`) is **movable location** — the cup is *in* the
room and can leave; it folds STATE-ish for movables and drives `locate` (the
protagonist's where-am-I chain). **Composition is constitutive structure** — the
burrow is *part of* the hillside; it does not "move out," and it must NOT pollute
`locate()` (an actor isn't "located in" every structure their location is part of).
So `part_of` is a **separate axis** with its own reads — mirroring locate/contents
mechanically, but semantically distinct.

## §1 `part_of` — the compositional relation
Entity-valued: `place:burrow · part_of · place:hillside` ("burrow is part of the
hillside's structure").
- **Functional / single-parent** (a sub-part is part of one whole; like `in`'s
  single-container fold). Coexisting different parents at one time → conflicted
  (existing fold semantics), not silently picked.
- **Valid-timed** — dynamic structure: the burrow is dug at T (`valid_from=T`) and
  can be filled/boarded (`valid_to`), exactly like a severed `connects_to`. As-of
  before T, the burrow is not yet part of the hillside.
- **A core structural primitive (Cx 064 #2):** `part_of` joins the fixed
  `STRUCTURAL_PREDICATES` (and thus `INVIOLABLE_CORE`) — it is PB's compositional
  axis, not host vocabulary a host may redeclare. A built-in
  `COMPOSITION_FAMILY = {"part_of"}` helper marks the axis for the classifier and
  reads. Classified **CONSTITUTIVE** (it is what the sub-place structurally *is*).
  Aliases like `feature_of`/`component_of` are **canonicalization receipts only**
  (`feature_of → part_of` at the gate) — the aliases themselves are NOT made
  structural (a structural alias would bypass `_canonicalize`); only the canonical
  `part_of` is core. One fold key, no fragmentation.
- **Not** a containment-family member: `locate`/`contents`/`route`/`path`/
  `aggregate(recursive=True)`/establishing-scope ignore it; it never appears in the
  actor's location chain.
- **For identity triage** `part_of` is an ordinary **non-containment relating edge**
  (evidence *against* identity — a part and its whole are distinct), **not** a
  containment merge-veto. It is already picked up by `relating_edges_between` (it's
  entity-valued, not in the containment family, not an identity/meta attr), so no
  special handling — just must NOT be added to the containment family.

## §2 The two abstraction reads (mirror locate/contents on the compositional axis)
- **`composition(entity, frame, valid_as_of, asserted_as_of) -> list[str]`** — the
  `part_of` chain upward, nearest whole first (the "abstraction up": the burrow's
  place-in-the-structure). Mirror of `locate` over `part_of`. Single-parent walk,
  cycle-guarded. `composition(place:burrow)` → `[place:hillside]`.
- **`features(place, frame, valid_as_of, asserted_as_of) -> list[str]`** — the
  entity's `part_of`-children: the sub-features that are part of it (the
  "abstraction down"). Inverse of `composition`. Per Cx 064: a child is included iff
  its **folded, non-conflicted current `part_of` winner resolves to `place`** (not
  "all visible rows with value=place") — so valid-time, identity closure,
  retractions, and conflict-handling all align. Identity-resolved; ordered
  first-seen/log order, lexical tie-break (stable output).
- **Conflict halts traversal (Cx 064 #1 — the load-bearing rule).** Neither read
  ever silently picks among co-existing parents. If a node's `part_of` fold is
  `conflicted` (two parents at one valid-time), `composition` **stops** at that node
  (does not follow a winner) and `features` does **not** treat the conflicted child
  as belonging to either parent. The conflict is surfaced through
  `state(child, "part_of")` (`conflicted=True`, both ids) and ordinary truth-
  maintenance — not buried in the list read. `locate`'s walk-the-winner pattern is
  deliberately NOT mirrored here.

Both are deterministic reads (zero model calls, zero writes), `as_of`-aware
(`valid_as_of` applies only when supplied; a no-bound read is not a substitute for
"later than `valid_to`").

## §3 The duality / retrieval-invariance
The sub-place is **one entity**, so the two lenses are inherently consistent:
- *Place lens:* `locate`/`contents`/`route`/`state` operate on `place:burrow`
  unchanged — it's a full place (route to it via its `connects_to`, look inside via
  `contents`, read its `state`).
- *Feature lens:* `features(hillside)` surfaces it; `composition(burrow)` gives its
  whole. Same entity, same facts, two access paths.

The host chooses the shape from the fiction (standalone place vs part_of-feature);
the engine makes both lenses resolve to the same entity coherently. This is
structural invariance (one entity, two paths) — the compositional sibling of AKA's
identity union — **not** cross-authoring convergence (two different authorings
returning identical results = the deferred general framework).

## §4 Porcelain + World (additive)
```python
p.composition(entity, frame="canon", as_of=None) -> [entity_id]   # part_of chain up
p.features(place, frame="canon", as_of=None) -> [entity_id]        # part_of children
```
World mirrors (`world.composition`, `world.features`) via the existing pass-through
pattern; `as_of` → `valid_as_of`.

## §5 Explicitly OUT of V1
- A unified **projection** (`materialize(..., expand_features=True)` showing a place
  with its features inline) — deferred to V1.1, same restraint as AKA's deferred
  `snapshot(mode="correlated")`; the `features`/`composition` reads provide the
  capability per-call.
- Cross-authoring shape-invariance (feature-as-attribute-string vs feature-as-entity
  returning identical results) — that is the general structure-polymorphism
  framework, deferred until a third shape forces it (round-robin restraint).
- Multi-parent composition (a shared wall part_of two rooms) — V1 is single-parent;
  coexisting parents conflict, surfaced for host adjudication, not silently merged.

## §6 Tests (tests/test_place_feature.py)
1. `part_of` relation: `features(hillside)` == `[burrow]`; `composition(burrow)` ==
   `[hillside]`.
2. Duality: the burrow is independently a place — `contents`/`route`/`state` work on
   it; `locate(actor in burrow)` returns the burrow's **containment** chain and does
   **NOT** include `part_of` parents (axis separation).
3. `locate`/`contents` ignore `part_of`; `composition`/`features` ignore `in`
   (the two axes never cross-contaminate).
4. Valid-timed: burrow dug at T — `composition(burrow, as_of < T)` == `[]`;
   `as_of >= T` == `[hillside]`. Boarded-up (`valid_to`) drops it at later as-of.
5. `part_of` classified CONSTITUTIVE; canonicalization (`feature_of` → `part_of`).
6. **Conflict halts (Cx 064 #1):** two parents at the same valid-time →
   `state(burrow,"part_of").conflicted` is True with both ids, AND
   `composition(burrow)` returns `[]` (does not pick the earliest) AND
   `features(parent)` excludes the conflicted child for each candidate parent.
7. `part_of` is a relating edge for identity triage (downgrades an auto-merge of
   part↔whole to a proposal) but NOT a containment merge-veto.
8. Reads write nothing; full suite green.
