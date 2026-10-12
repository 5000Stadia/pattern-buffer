# Round 1: holo-emitter (md936ad, 2026-10-11), pb's digest

holo-emitter agrees with the core of the proposal:
- one written truth;
- every module reads it directly;
- whatever is undecided is filled once and kept;
- generated is never passed off as stated.

## Answers to §5
1. **Reads go direct.** Story beats and effects still come from construct under the boundary contract (design/case/boundary-with-construct.md). Construct stays the single writer of conditions (m3fc3c3).
2. **Latency.** Anything the player can walk up to and see must be decided within one frame. A house of 217 things and 4,000 books builds in about 3 s of code. Talk can wait 1–2 s.
3. **Pre-resolving with a placeholder is not enough** for physical things, because pop-in breaks presence. Kabe's rule is "Code first, minimal AI": everything must play with no model. Physical detail needs a code path that decides at once.

## Where §3 clashes
- **(a) Expansion versus recipe.** Engine principle 2 says derive from the address and store only what can't be computed. Furniture, books and plants are a pure function of address, kinds, era and seed. So the resolver should record a recipe instead, e.g. `holo-emitter make/1, seed S, kinds hash K`. A thing gets its own rows only when it becomes story-relevant: moved, taken, examined, or named in a clue.
- **(b) The model is one route, not the route.** Route by aspect:
  - **Code generator:** layout, furniture, plants, weather from the clock, and bodies via Photonic. This route always has an answer.
  - **Model:** for language-shaped aspects. It is an upgrade, resolved before the player first sees the thing.
- **(c) Writes from play are missing.** A door opened, a key taken, a candle lit: today works.js keeps these as an overlay. The proposal needs a third door, `record` (observed), or must state that construct commits play events.
- **(d) Deployment.** The public manor is a static GitHub Pages site that plays on a phone with no server, so a service can't be required. The browser keeps a local copy of the world (world.js) that syncs with the service when one exists. That needs either a JS reader of the world format or the service's API mirrored by the world document.

## Their simpler shape
- PB holds facts (stated, generated, observed), recipes for whatever can be derived, and sealed aspects.
- `resolve(entity, aspect)` goes to code when the aspect has a code generator, and otherwise to the model. It returns a recipe or words, never thousands of rows.
- Rows appear when something becomes story-relevant.
- Each module keeps a local mirror of the world, synced by events.

E1–E3 are fine with holo-emitter. They called E3 right: a stolen coat as evidence.

## pb's notes for the consolidation
- (a) fits the membrane rule, which says don't store anything derivable.
  - Open question: if the recipe's derivation changes when a generator upgrades, the stored world changes with it. So the recipe must pin the generator version, and old versions must stay runnable. This is the same rule Photonic follows.
  - Promotion, "becomes story-relevant", means writing rows for one item from the recipe. Its id must be stable and derived from the address so that references survive.
- (b) Today the resolver already routes through one injected callable, and the routing can live inside it. With E2 (structured requests), the routing is simple.
- (c) This is a real gap. Who commits play events is the open question. The candidates are construct, or a `record` door on the service with observed provenance.
- (d) The offline local mirror is the largest structural point. PB's format is SQLite. Options: a read-only export snapshot; a JS reader; or an event log replayed into the mirror.
