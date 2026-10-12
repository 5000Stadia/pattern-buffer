# WORN-OBJECTS-V1: what a person wears is things, invented like a room's contents

**Status:** r1, for pbr's spec review and shape reads from Photonic and construct. Author: pb,
2026-10-12.
**Source:** roadmap R41, E3 of `specs/proposals/UNIFIED-WORLD-ACCESS.md`, which Kabe approved
(gde97f3). It was sequenced after the identity gate g3bf5da (decided, P1–P3) and R35 (merged). The
monitor queued it after R42a (note n7052ef).
**Builds on:** RESOLVE-UNMARKED-V1 (E1: plant and force a declared aspect), RESOLVE-REQUEST-V1
(E2), WORLD-SERVICE-V1 §7b (`perceive_in` mirroring), IDENTITY-ROOT-CAUSES-V1 (R35).

## Need

- **The round-1 statement:** "A resolution can create garments as objects `worn_by` the person,
  as contents are created `in` a room. Then the dress can be taken off, stolen or used as
  evidence." holo-emitter: "a stolen coat as evidence".
- **What exists today:** resolving `contents` on a place mints `obj:gen_N` entities. Each gets a
  `kind`, a `name` and an `in` edge, and the contents query serves them forever (P2: contents are
  derived, never a literal row).
- **What is missing:** a person's clothes resolve only as literal words on one key, such as
  `wears: "a grey wool coat"`. A literal can't be taken off, stolen, carried or found. E3 gives
  people the same minting path that rooms have.
- **Two further gaps that E3 makes worse:**
  1. **Minted things have no looks.** A minted item gets a `kind` and a `name` only. Photonic's
     wardrobe sampler and holo-emitter's room generators produce look words such as colour,
     material or condition. Today those have nowhere to land as the item's own facts, and S2's
     present layer has no `look` to draw for them.
  2. **Invention is counted as identity evidence.**
     - `reconcile()` gathers canon `name` and `alias` rows of any status as shared anchors. Two
       invented "red wool dress" items on two different women share a name-like anchor (R35:
       at most 5 words, no possessive), and the engine can merge them.
     - Contents minting has this hazard already. E3 multiplies it, since every person gets
       garments.
     - The proposal's own rule is that invention is never passed off as story. A generated name is
       not evidence that two things are one.

## The shape

### 1. Minting aspects

- The resolver's one special case becomes a table:

  ```python
  MINTING_ASPECTS = {"contents": "in", "attire": "worn_by"}
  ```

- A minting aspect, when forced, mints entities rather than writing literal rows on one key. Each
  item becomes `obj:gen_N` with a generated `kind`, a generated `name`, and a generated edge
  `<relation> → <entity>` at the placeholder's `valid_from`.
  - The edge is classified STATE, as contents edges are: a coat comes off.
  - The `kind` and `name` rows are classified CONSTITUTIVE, as today.
- **`attire`** is the aspect name. It reads plainly ("the attire of person:mara"), and it does not
  collide with the `wearing → worn_by` inverse alias at the gate.
  - A world opts in as with any E1 aspect: `attr:attire · resolvable_for · person`.
  - Photonic's people aspect list would include it.
- **The guard** extends `_may_plant`'s contents rule: `attire` plants only when nothing is
  `worn_by` the entity, as of the placeholder's time.
  - If the story already dressed the person, the stated garments stand, and nothing is invented
    around them.
  - The time check matters because what someone wears is state: the guard reads as of `at`, not
    head time.
- **Taking it off.** Once minted, a garment is an ordinary entity. The story moves it by writing a
  new containment edge (`in place:hall`, `carried_by person:thief`). The fold already serves the
  latest edge.
  - The `attire` memo still names the original rows. A later resolve serves the memo, and the memo
    rows are the generated edges. The fold for "what is she wearing now" is the containment
    family, which reads current edges, not the memo.
  - So a stolen coat is gone from her and present on the thief, with no special case.

### 2. Minted items carry their looks *(applies to `contents` too)*

- The item schema gains an optional `aspects` object, `{aspect: literal scalar}`.
- For each pair whose aspect is declared `resolvable_for` the item's minted kind (the world's
  closed vocabulary, E1), the resolver writes a generated row `obj:gen_N · aspect · value`. It is
  classified by the classifier as any row is.
- An undeclared aspect, or a non-scalar value, is **dropped** and logged at `WARNING`. It is never
  free text on the item. The resolve still succeeds, and the receipt counts what was dropped.
- Code generators fill this from E2's structured request: Photonic's sampler for garments,
  holo-emitter's generators for furniture. The model's prompt gains one sentence naming the
  declared aspects for the expected kinds, if any.
- **Why it belongs here:**
  - S2's present layer draws exactly these declared look aspects, so a drawer's invented key now
    arrives with its look.
  - The look rows are the item's own facts, so a later stated row overrides them by evidence rank
    (stated beats generated), as everywhere.

### 3. `perceive_in` mirrors the whole minted item

- `World._mirror` today mirrors a contents edge plus the minted `kind` and `name`.
- It now mirrors, for every minting aspect, the edge, `kind`, `name` and the item's generated look
  rows from §2.
- The perceiving frame therefore sees the coat's colour when it sees the coat. A host whose
  `perceptible` hook judges a look not perceptible (a coat under a cloak) controls that through
  the hook, as today.

### 4. Invention is not identity evidence

- `reconcile()` and the within-chunk anchor collection skip `name` and `alias` rows whose status is
  `generated`. A generated word never makes two closures candidates for a merge.
- **What still merges them:**
  - a stated or observed name: once the story names the dress "the red dress", that row is
    evidence like any other;
  - a host `merge`.
- **Corpus measurement (build acceptance):** reconcile on copies of construct's worlds, the
  current engine against the new rule, with the same harness as R35.
  - Expected: no change wherever no generated name was an anchor.
  - Any merge that disappears is listed with its anchor text.
  - Book grading is re-run and must not drop.

### 5. What does not change

- Literal-valued aspects (`wears` as words) work as before. A world that declares `wears` keeps
  getting words; `attire` is a separate, opt-in aspect.
- `contents` minting behaves as before when items carry no `aspects`, except that reconcile now
  ignores the minted names (§4).
- No change to ids (`obj:gen_N`), and no recipes or promotion by address. Those stay with
  holo-emitter's R75 and a later spec.

## Tests

1. **Attire mints garments.** In a world with `attr:attire · resolvable_for · person` and a stub
   generator answering two garments:
   - `resolve(person, "attire")` mints two `obj:gen_N`, each `worn_by` the person, with a kind and
     a name;
   - the second resolve serves the memo, with no new rows;
   - `contents(person)` includes them (the containment family).
2. **The guard.** A person with a stated garment `worn_by` them at `at` does not plant `attire`.
   A person who wore something only earlier, and has since changed, does plant it at `at`.
3. **Taking it off.**
   - A stated `obj:gen_N · carried_by · person:thief` after the resolve moves the coat;
   - `locate` and `contents` follow it;
   - the memo is unchanged;
   - a further `resolve(attire)` serves the memo rows, and a host reading worn things uses the
     containment read.
4. **Looks.**
   - Declared aspects become generated rows on the item, for `contents` as well as `attire`.
   - An undeclared aspect and a structured value are dropped, logged and counted.
   - A later stated colour overrides the generated one.
5. **Mirror.** `resolve(perceive_in=F)` writes the edge, kind, name and look rows into F as
   `observed`, in one unit; a gate refusal rolls back everything.
6. **Identity.**
   - Two women each minted a garment named "red wool dress": `reconcile()` merges nothing.
   - A stated `name` "red wool dress" on both still behaves as before R41.
   - Contents minted in two rooms with the same name also stay apart.
7. **Corpus.** The §4 measurement on construct's world copies: merges before and after, any
   difference listed, and book grading unchanged or better.
8. **E2 request.** The resolve request for `attire` carries `aspect="attire"`, the person's
   `kind` and the `current` facts (V1.1). Photonic's route needs nothing else.

## Not in this spec

- Recipes, address-derived ids and promotion (holo-emitter R75 and a later spec).
- Accessories carried rather than worn (`carried_by`). If wanted, it is one row in the table
  later.
- Disguise (perceived appearance as a separate entity), which waits on per-view identity
  (proposal §2).

## Lexicon (added with the build)

- **minting aspect**: an aspect whose resolution mints entities joined to the resolved entity by a
  containment relation (`contents` → `in`, `attire` → `worn_by`), instead of writing literal rows
  on one key.
- **attire**: the minting aspect for what a person wears. Its garments are entities `worn_by` the
  person, so they can be taken off, stolen or found.
