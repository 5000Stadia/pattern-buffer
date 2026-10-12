# RESOLVE-UNMARKED-V1: resolve a declared aspect nobody marked open

**Status:** r1, spec for pbr review, before code. Author: pb, 2026-10-12.
**Source:** roadmap R38, E1 of `specs/proposals/UNIFIED-WORLD-ACCESS.md`, approved by Kabe 2026-10-12
(gate gde97f3). Builds on RESOLVE-REQUEST-V1 (E2).

## Need

A module asks for a detail the story never decided: the barmaid's clothes, a room's contents. Today
`resolve(entity, aspect)` invents only when a placeholder (`value_type: unresolved`) was planted
first. With nothing planted, a story world returns nothing. Construct works around this in two steps
(`furnish_scene`: plant, then resolve). Every module would have to copy that, and each copy decides
on its own what may be invented.

The round-robin also set three guardrails:
- **construct C:** only declared aspects, so hair / hair_colour / haircolor never appear side by
  side;
- **construct E:** old worlds untouched;
- **holo-emitter (b):** the engine never invents where code should decide.

## Rule

1. **Declaring what may be invented.** A new semantics predicate, `resolvable_for`, on an
   `attr:<aspect>` subject, with a kind as its value. For example `attr:wears · resolvable_for ·
   person` and `attr:contents · resolvable_for · tavern`.
   - It is set-valued: one row per kind.
   - It is validated at the gate like the other declarations (GATE-AUTHORITY-V1 §5): the value must
     be a non-empty string in the id-safe name grammar.
   - It is read through `AttributeSemantics` as `resolvable_kinds(aspect) -> frozenset[str]`.
   - The inviolable core (structural predicates, identity predicates, `kind`, `name`, `alias`, and
     the containment family other than via `contents`) cannot be declared resolvable. The gate skips
     such a row with the existing `invalid_semantics_declaration` reason.
   - A host may also supply it through `attribute_default`, as it does the durability pin.
2. **Resolving the unmarked.** `resolve(entity, aspect)` gains one case. It applies only when **all**
   of these hold:
   - the world's physics is `invent_under_canon`;
   - no placeholder for `(entity, aspect)` exists in the frame;
   - the key has no concrete value (the fold has no winner), and for `contents`, the entity
     contains nothing;
   - the entity's folded `kind` is in `resolvable_kinds(aspect)`.

   The resolver then **plants and forces in one unit** (ATOMIC-ACTIVATION-V1: all or none):
   - It appends the placeholder itself: status `generated`, value `{"policy": <world policy>,
     "planted": "resolve"}`.
   - The placeholder's `valid_from`:
     - none (timeless) when the aspect's durability pin is CONSTITUTIVE or DISPOSITIONAL;
     - otherwise the call's `at`, which defaults to the scene cursor's position.
   - It then forces the placeholder exactly as a host-planted one. The resolved_by memo spends it,
     so a second call returns the identical rows forever.
3. **Every other case is unchanged:**
   - an undeclared aspect, a kind not listed, a world with no `resolvable_for` row, or another
     physics: `resolve` answers as today (`[]` in a story world, `UNKNOWN` in tracking);
   - a planted placeholder is forced exactly as today;
   - a concrete value answers without invention;
   - `deny` still refuses.

   Old worlds hold no `resolvable_for` row, so **nothing changes for them** until a host declares
   one. That is the opt-in.
4. **The porcelain.**
   - `resolve(entity, aspect, frame=CANON, at=None)`: `at` poses the cursor for this call only, as
     `ingest_structured(at=)` does.
   - The result gains `"planted": true` when the placeholder was planted by this call.
   - An undeclared or unlisted aspect returns `{"status": "undeclared", "facts": [], "receipt": …,
     "reason": …}`, so a module learns why nothing came back. This is only in a story world, and only
     when no placeholder or value exists; tracking worlds keep answering `unknown`.
5. **Role authority.**
   - The placeholder and its resolution are both the resolver's rows (`generated`), and no other
     component writes them.
   - The gate still refuses `generated` items into canon (letter 029), so a host cannot forge an
     invention.
6. **The request.** The planted call carries the same `ResolveRequest` (E2), so a code generator
   answers it like any other. The routing (code first, model as fallback) lives in the host's
   callable, never in the engine.

## Not in scope

- Rate caps and budgets: the WorldService (S1).
- Worn objects: E3.
- Which aspects each module declares: construct, holo-emitter and Photonic supply their own lists
  (§8 of the proposal).

## Checks

1. A declared aspect on a matching kind plants and forces in one call. The second call is memoized
   with no model call.
2. An undeclared aspect, an unlisted kind, a tracking world, or a world with no declarations
   returns as today, plus `undeclared` on the porcelain in a story world.
3. `contents` mints objects `in` the entity, as today, but only when it contains nothing yet.
4. A durability pin of DISPOSITIONAL plants timeless; otherwise the placeholder is at `at`, or the
   cursor.
5. Atomic: a model failure leaves neither the placeholder nor any row.
6. A forged `generated` placeholder item is refused at the gate.
7. A `resolvable_for` declaration on a core attribute is skipped as `invalid_semantics_declaration`.
8. The full suite passes with no test edited, and construct's suite passes on the branch.
