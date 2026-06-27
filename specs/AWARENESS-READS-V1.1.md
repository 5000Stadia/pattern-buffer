# AWARENESS-READS-V1.1 — projection-level correlation + composition

**Status:** DRAFT → Cx GREEN. Completes two of the awareness reads at the projection
level (build-philosophy: notable improvement + elegant, not over-complicating). All
additive on porcelain-v0.1; **default reads unchanged** (opt-in, mirroring the per-key
versions). The general structure-polymorphism *framework* stays deferred (the
over-complication exception).

**Dropped — `who_knows(via_public=)` effective-knowledge (founder, 2026-06-27):**
"public facts should ~80% be assumed known by anyone." `who_knows` is about *private*
knowledge (who holds a secret). For a *public* fact you don't enumerate knowers —
the **host assumes universality** (a host heuristic). The engine already surfaces both
sides: `who_knows` (private knowers) and the public frame (`state(e, a,
frame="public")`) for public-ness; the host combines them. So `via_public` is unneeded
engine surface — dropped. (Membrane-clean: engine surfaces who privately knows + what's
public; host supplies the "public ⇒ assume universal" judgment.)

**Surface note (Cx):** the new behavior is exposed as **boolean params**
`correlated=False` / `features=False` on `materialize` and `snapshot` — orthogonal to
the existing `lens`, NOT a new `mode=`/`lens` value (avoids the `lens` clash).
`correlated` threads through every lens that folds standing state (current_state,
situation, character_sheet). **Exception:** `correlated=True` + `lens="establishing_set"`
**raises** — the world-at-creation view predates identity reveals, so the combination is
incoherent; a clean guard beats threading the flag through the specialized first-state
path (elegance over forced orthogonality). `what_happened` is event-only (no standing
fold) and is naturally unaffected.

## Win 1 — `materialize(scope, correlated=True)` / `snapshot(scope, correlated=True)`
**The gap:** AKA-CORRELATION-V1 ships per-key `state_union` (one folded key over an
entity ∪ its `aka` facets) but no scope-wide projection — to render the masked-figure
= Ilsa reveal in a scene, the host must call `state_union` key-by-key. **Win:** an
opt-in projection that folds each scope entity's keys over its correlation set, so a
whole correlated scene comes back in one call.
- When `correlated=True`, `_lens_state` folds each entity via the **correlation
  union** instead of the bare closure. Concretely (Cx): the per-entity key-discovery
  (today `indexes.current_state`, `indexes.py:775-793`) gains a correlated variant
  that discovers keys over the correlation set's union and folds each via
  `state_union` — returning the same `FoldResult` shape so the projection's
  quantities/conflicts/unresolved/defaults handling composes unchanged.
- **MUST preserve the `META_ATTRIBUTES` filter** in key-discovery (`indexes.py:782-786`)
  so `aka`/identity edges never leak into the correlated projection (same membrane as
  the default).
- **Opt-in ONLY:** default `materialize`/`snapshot` byte-for-byte unchanged; as-of-
  before a reveal returns the uncorrelated view (the valid-time gate on the `aka`
  walk). Reuse the shipped `state_union` fold — no new fold logic.

## Win 2 — `materialize(scope, features=True)` / `snapshot(scope, features=True)`
**The gap:** PLACE-FEATURE-ABSTRACTION-V1 ships per-place `features()`/`composition()`
but no projection that inlines a place's sub-features. **Win:** an opt-in projection
that, for each scope place, includes its `part_of`-children (the burrow under the
hillside) — the whole place-with-features in one read.
- When `features=True`, the projection's **entity list is augmented** before folding:
  for each scope place, append its `features()` children (a clean pre-projection
  entity-list addition — Cx confirmed the scope walk is containment-only via
  `_scope_entities`/`contents`, so this doesn't alter default scope). The children
  then project through the standard per-entity path (their own facts).
- One level deep; identity-resolved + conflict-halt inherited from `features()`.
- **Membrane:** opt-in; default scope/projection unchanged; no new fold logic. No
  recursive multi-level explosion (that would drift toward over-complication; a depth
  knob waits for a proven need).

## Non-goals (the over-complication line)
- The general entity/feature/facet/correlation **framework** — deferred until a third
  shape (inherent premature abstraction).
- Recursive multi-level feature explosion / arbitrary projection-union DSL — a depth
  knob or general union-projection waits for a proven need.
- No change to any default read, fold semantics, or the role/frame matrix.

## Tests
- Win 1: `snapshot(mode="correlated")` of a masked-figure scope after a reveal includes
  the correlated facets' facts; **default** `snapshot` does NOT; as-of-before-reveal
  correlated returns the uncorrelated view.
- Win 2: `snapshot(mode="features")` of a hillside includes the burrow's facts;
  default does not; one level only; a conflicted `part_of` child is excluded (halt).
- Booleans `correlated`/`features` are orthogonal to `lens`; default
  (`correlated=False, features=False`) is byte-unchanged.
- Full suite green; all default paths byte-unchanged.
