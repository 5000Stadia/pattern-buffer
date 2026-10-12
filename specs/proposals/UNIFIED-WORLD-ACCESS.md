# Unified world access: how the modules read and fill one world (final, for Kabe)

Status: FINAL. All three modules agreed in the polish round, and their changes are folded in
(marked *polish*). Author: pattern-buffer (pb), 2026-10-12.
Readers: construct (Newproject), holo-emitter, Photonic. Decision: Kabe's.
Round 1 is in git (57caa3c). Each module's input is digested in `unified-world-access-input/`;
Photonic's full text is `/home/k/Projects/colony/projects/Photonic/design/unified-world-access-photonic-r1.md`.

## Kabe's words (2026-10-11)

> "Isnt PB simply the written state and we allow all modules to query reality
> within it to produce, and if it isn't there it triggers a correct invention of
> that. Well… the creation probably warrants the non deterministic intelligence
> to some degree. Thats what gets us period appropriate clothes and not a space
> suit."
>
> "At this point the elegance comes from a unified identification of the need
> and consideration for the most elegant workflow and solution."

Kabe's standing rule, which holo-emitter and Photonic both cited: **"Code first, minimal AI."**
AI is used only where only language will do, kept narrow and checkable. Everything must play with
no model.

## What all four modules agreed in round 1

- **One written truth.** Every module reads it directly, and nothing passes through another
  module just because that module holds the file.
- **Undecided detail is filled once and kept.** Every module sees the same answer forever.
- **Invention is never passed off as story.** Invented rows are `generated`; what the story said
  is `stated`.
- **The first two engine changes are welcome.** These are E1 (fill an unmarked detail in one
  call) and E2 (send generators a structured request). E3 (worn things are real objects) is right,
  but it is sequenced later.

## The structure

### 1. One host per world: a WorldService library class
- **What it is:** a class shipped in the pattern-buffer repo, outside the engine core. It holds a
  world's single handle and puts all writes in one queue.
- **What it offers:** read calls and `resolve`, which fills in missing detail.
- **Who hosts it:** whoever opens the world. Today that is construct's session, which already
  holds the only handle, so construct's in-process reads stay in-process.
- **Running without construct:** a thin optional runner serves a world on its own, for example
  holo-emitter playing alone.
- **Other modules** reach it over the existing bridge (holo-bridge, the `?since=v` poll). That
  bridge is unmerged, and merging it is Kabe's call. One door for both the deck and the world
  removes code.
- *(construct's shape. holo-emitter and Photonic endorse it.)*

### 2. Renderers read through the player's view, never raw canon
- **Why:** canon holds secrets, such as the blood in the lining or who the murderer is.
  *(construct A)*
- **The lens:** the player's own view (frame), which pattern-buffer already filters at source.
  Construct keeps that view current, **at scene open and on every reveal, in the turn's commit**
  (a drawer opened, a coat examined, a hood pulled back), so the screen never lags the story.
  *(polish: construct)* At scene open it adds what is perceptible: visible furniture,
  the people present, and their **perceived** appearance. A hooded figure is perceived as
  "hooded figure, tall", not as who it is. *(Photonic 6)*
- **Concealment** therefore needs no special marker. Something is out of the player's view until
  it is perceived: the closed drawer's contents, the lining, the face under the hood.
- **What the view governs.** It controls what is narrated and what the panel and notebook show.
  It does not control which drawable bytes reach a renderer: see §7. *(polish: holo-emitter)*
- **Disguise** depends on Kabe's open identity gate (g3bf5da). Showing "the hooded figure" in the
  player's view as a separate entity from canon's "the murderer" needs identity that is scoped per
  view. Until that gate is decided, a disguise can be shown only as perceived-appearance words.

### 3. Code first; the model is an upgrade for words
Each aspect has a registered generator. The engine's single injected generator callable routes by
aspect. With E2 it receives `{entity, kind, aspect, constraints, as_of}` as structured fields.

| Aspect | Generator | Model? |
|---|---|---|
| Body and face (hair, nose, build, eyes, age look) | Photonic's sampler: words + look, seeded, instant | only to author a missing kind pack (a dragon, a new elf) once, at build time (Photonic's M6 trigger); play never *(polish: Photonic)* |
| Wardrobe | Photonic's sampler over the setting's period kit (by rank and trade), period-true by construction | only to author a missing setting's kit once, at build time |
| Room contents, furniture, books, plants | holo-emitter's generators, from address, kinds, era and seed | never |
| Weather and conditions | from the clock and calendar (code), or stated by the story | never |
| Language-shaped aspects (a description, an inscription, a line, a name) | the model, under the world's constraints | yes |
| Named, plot-relevant people at scene open | the model may refine the words, but only inside the closed vocabulary | optional |

**Rule:** every word written about a visible thing must be something its renderer can draw. A term
outside the vocabulary goes to `other`, which triggers a build. It is never free text. This holds for
**stated** rows too: when the narrator's prose says "a red dress", extraction maps it onto the
declared aspects (or `other`). *(polish: construct)*

**How the host runs a code generator.** *(polish: construct)*
- holo-emitter's and Photonic's generators are JavaScript, but the host (construct) is Python.
- The narrator must describe what the renderer will draw, so the host expands recipes and calls
  `describe()` itself, in the turn, before narration. This matters most with no renderer running
  (Telegram play).
- Each generator ships a **host-runnable form**: a `node` subprocess behind the registry. pb's lean
  is one implementation, not a port.
- Both sides' suites check a **shared table of test vectors** (seed, inputs → words).
- The content-hash version covers every form of a generator.

### 4. What pattern-buffer stores
- **Facts:**
  - `stated` rows come from the author;
  - `observed` rows are play events;
  - `generated` rows are words chosen by a generator.
- **Recipes, not expansions.** A street of 300 people, a shelf of 4,000 books or a room's furniture
  is stored as **one recipe row**: generator id, content-hash version (code **and** data packs),
  seed, and the as-of of the resolution.
- **Version policy.** *(polish: holo-emitter)*
  - Before a world's release, a generator change re-derives every recipe nothing has promoted;
    worlds in development start afresh.
  - From release on, the world pins its generator versions, and those versions are kept runnable.
  - Promotion always protects whatever the story has touched. Renderers expand recipes
  locally in milliseconds. This is pattern-buffer's own membrane rule: whatever can be derived is
  not stored. *(holo-emitter a, Photonic 2)*
- **Promotion.** One item from a recipe gets its own rows when it becomes story-relevant: moved,
  taken, examined in narration, or named in a clue. Its id is **derived from its address**, so a
  reference made before promotion still points at it.
- **Lifetimes decide what is stored as words.** *(Photonic 2c)*
  - **Identity** (nose shape, natural hair colour) is stored as DISPOSITIONAL.
  - **State** (the dress, a scar, dyed hair) is stored as timed STATE rows.
  - **Age-driven aspects** (greying, stoop) are derived at read time from identity, age and
    `as_of`, and never stored. Otherwise "blonde" goes stale across a time skip.
- **Seals.**
  - Plot-critical aspects carry **constraint seals** ("dark, wet-weather"), so the renderer still
    resolves within the plot's needs.
  - `deny` is only for what must stay unknown and unseen.
  - Construct may seal at any time, not only before play, because plot is also authored during
    play. *(construct 1)*

### 5. Who writes what
- **Construct is the author and owns "now".**
  - Construct's rows include story facts, seals, and the play events it receives from
    holo-emitter (as `observed`). *(construct; answers holo-emitter c)*
  - The service publishes construct's current coordinate. A resolve fired between turns lands at
    that coordinate.
  - Construct-side fix first: `commit_elapsed` writes without `at=`.
- **The resolver writes `generated`.** No other part of the system does.
- **Renderers write nothing.** They ask the service to resolve.
- **Author override already works in the engine.** Every fold first keeps only the best evidence
  rank present (stated or observed beats generated), so a later `stated` row overrides a generated
  one. Renderers follow the version change. *(construct 1(ii); verified in `indexes.py`
  `_top_evidence`.)*
- **The standalone runner has no author.** It needs its own `record` door that writes play events
  as `observed`. *(holo-emitter c)*

### 6. Timing: decide before sight, never pop in
- Code routes answer within a frame. That covers everything physical.
- **Construct triggers pre-resolution at scene open**, because it knows when a scene opens:
  - visible model-routed aspects are resolved **before narration**;
  - likely next scenes are pre-resolved during the settle.
- The narrator is briefed with the resolved words (Photonic's `describe()` for people) and told not
  to invent visible attributes. That ends the race between narrator and renderer. *(construct B,
  Photonic 3)*
- Talk may take 1–2 s, because the panel shows the person thinking.

### 7. Offline play: a local mirror of the player's view
- The public manor is a static page on a phone with no server. *(holo-emitter d)*
- The mirror is an **export of the player's view** plus **everything physically present in the
  places it covers**, as what to draw: recipe or promoted row, position and container,
  look-words. Opening a drawer shows its contents within a frame. *(polish: holo-emitter)*
- It carries **no meaning**. "The murder weapon" and "whose blood" are facts and relations, and
  those stay filtered.
- **Trade-off for Kabe:** a player who digs into the phone's storage can see an unopened drawer's
  contents, though not what they mean.
- It is synced by events since a log position, when a service exists.
- With no service, the code routes decide and the world still plays in full.
- Format: a JSON world document that pattern-buffer exports. holo-emitter's `world.js` already
  keeps one. No JS port of the SQLite engine is needed.

### 8. Guardrails
- **Closed aspect vocabulary.** E1 fills only aspects declared per kind and refuses the rest, so
  hair, hair_colour and haircolor never appear side by side. *(construct C)* Photonic supplies the
  people aspects, holo-emitter the room and condition aspects, and construct the narrative ones.
- **Budget.** The service holds a rate cap and a budget for model routes, so renderers can't fan
  out calls. All Codex consumers share one rate budget. *(construct D)*
- **Old worlds stay untouched** until Kabe decides. E1 is opt-in per world. *(construct E)*

## Engine and library changes (each on its own branch, with tests and pbr review)

| # | Change | Where | Order |
|---|---|---|---|
| E2 | Structured resolve request `{entity, kind, aspect, constraints, as_of}` to the generator | engine | 1st |
| E1 | Resolve the unmarked: plant and force in one call, declared aspects only, opt-in per world | engine | 2nd |
| S1 | WorldService library class + optional runner (one handle, write queue, read and resolve, rate cap, `record` door when standalone) | pb repo, outside core | 3rd |
| S2 | View export + change feed for mirrors (player's view as JSON, events since a log position) | pb repo | 4th |
| E3 | Worn things are objects (`worn_by`), promoted like furniture | engine | after g3bf5da |

**Other modules' sides, once Kabe approves:**
- **construct:**
  - host the service and keep the player's view current at scene open;
  - pre-resolve before narration;
  - the narrator briefing;
  - map extracted visible attributes onto the closed vocabulary *(polish)*;
  - run registered JS generators via `node` *(polish)*;
  - update the view on every reveal *(polish)*;
  - the `commit_elapsed` `at=` fix;
  - commit play events.
- **holo-emitter:**
  - register room and condition generators, each with a host-runnable form and test vectors;
  - read the mirror.
- **Photonic (R3):**
  - register `person.appearance.*`;
  - `describe()`;
  - the people aspect list;
  - content-hash versions.

## For Kabe to decide

1. **Approve this shape.** The default, if you skip it: nothing is built.
2. **The order:** E2 → E1 → S1 → S2, with E3 after the identity gate.
3. **Old worlds** stay untouched until you say otherwise.
4. **holo-bridge** (construct's branch) becomes the door for other modules. This was already your
   call.
5. **Mirror trade-off:** unopened contents can sit on the device, without their meaning. The
   default: accepted.

## Polish round

All three modules replied "agree" with small changes, all folded in above:
- holo-emitter: m2f6ad8;
- Photonic: m73d0b0;
- construct: md0b39b.
