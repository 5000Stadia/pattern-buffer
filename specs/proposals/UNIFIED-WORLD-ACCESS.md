# Unified world access: how the modules read and fill one world (round 1 draft)

Status: draft for round-robin. Author: pattern-buffer (pb), 2026-10-11.
Readers: construct (Newproject), holo-emitter, Photonic. Decision: Kabe's.

## Kabe's words (2026-10-11)

> "Isnt PB simply the written state and we allow all modules to query reality
> within it to produce, and if it isn't there it triggers a correct invention of
> that. Well… the creation probably warrants the non deterministic intelligence
> to some degree. Thats what gets us period appropriate clothes and not a space
> suit."
>
> "At this point the elegance comes from a unified identification of the need
> and consideration for the most elegant workflow and solution."

**pb's reading:** the four modules are built separately, but they are one live
fiction engine. The world's truth should live in one place, and every module
should reach it directly. Undecided detail is invented on demand: once, with
judgement, consistent with the world (era, place, person), then kept for
everyone. Routing every request through one module only because that module
holds the file is a deployment accident, not a design.

## 1. The need

These requests are already in the mail. Each asks the same thing: *the module
needs a detail the story never stated.*

- **Photonic (m74babe):** a person is drawn. Clothes, hair and build are partly
  described ("a long-haired blonde woman in a red dress"), and the rest is open.
  Whatever is chosen must be kept in words ("red dress") so that the story and
  the screen agree.
- **holo-emitter (mb8dcaa):** a room is entered. It needs furniture, weather and
  the hour. The time, moon and weather must be stored "as an object within the
  chronological period".
- **construct:** narrates the same moment and must say the same things the
  screen shows.

The shared shape: **read → if the world says it, use it → if the world never
said it, have it invented under the world's rules, kept forever, visible to all.**

## 2. What pattern-buffer already does (facts, today)

- **Thunks.** An open aspect is a first-class row with a policy and
  constraints. "Forced exactly once, memoized forever" (whitepaper §8,
  `thunks.py`).
- **Policies.**
  - `invent_under_canon` (story worlds) invents.
  - `observe_or_unknown` (real-world tracking) never invents.
  - `deny` seals an aspect so that no one may invent it.
- **Invention uses judgement.** The resolver calls the injected model with every
  standing fact of the entity and of its containment ancestors as constraints.
  That is how the era yields a linen kirtle, not a space suit.
- **Provenance.** Invented rows are `generated`, never passed off as `stated`.
  Only the resolver may write `generated` to canon; the gate enforces this.
- **Furniture works today.** Resolving a room's `contents` creates real objects
  `in` the room, which can be moved, taken or searched later.
- **One live handle per world file.** This is enforced since 2026-10-10 by
  `SecondWriter`. Today construct holds that handle, so every other module has
  to go through construct.

## 3. Proposed structure

```
             reads + "resolve" requests (direct)
holo-emitter ─┐
Photonic     ─┼──►  WORLD SERVICE (one process per world) ──► pattern-buffer engine (library)
construct    ─┘        owns the only World handle              │
  (also authors        serializes writes                       └─ resolver ──► generator
   story facts)        serves reads to all                                     (model, routed by
                                                                                aspect: Photonic's
                                                                                sampler for people)
```

1. **A world service:** a thin process that owns one world's file and handle.
   - **Reads, for everyone:** `state`, `snapshot`, `locate`, `contents`,
     `events`, `axis_heads`.
   - **Writes:** one door for story facts, `ingest_structured`, used by the
     author (construct). One door for invention, `resolve`, which any module may
     call.
   - It lives outside the engine core. The core still never calls a module; the
     only seam remains the injected generator `(prompt, schema) -> json`.
   - Writes are serialized in one process, so there is no second writer. Reads
     are concurrent.
2. **Asking is not writing.** A module that asks for the barmaid's clothes
   writes nothing itself. The resolver invents and records. The role-authority
   rule stays intact: the author states, the resolver generates, and renderers
   only read.
3. **"Empty" means never said.** If the story said "the room was bare", that is
   a fact, and nothing gets generated. Pattern-buffer already distinguishes
   unknown from known-empty.
4. **The author's plans live in pattern-buffer before anyone can ask.** This is
   the one thing routing through construct used to protect, and it becomes a
   discipline instead. Example: the murderer's coat must be green for a clue in
   chapter 4. Construct writes that as one of:
   - a fact;
   - a constraint ("dark, wet-weather");
   - a sealed aspect (`deny`: the author decides later, and no one invents it).

   Anything unsealed is fair game for any module.
5. **Intelligence picks the what, the seed picks the exact look.**
   - The generator is the injected callable, and it routes by aspect.
   - For a person, a model picks period-true words ("red wool kirtle, linen
     coif"). Photonic's seeded sampler then turns the words into the exact
     rendered person.
   - Only the words (plus seed and generator version) are stored. So story and
     screen agree, and a generator upgrade never changes someone already seen.
6. **Latency.** A model call takes seconds, and a renderer cannot wait
   mid-frame. When a scene opens, its likely details are resolved ahead of time:
   the room's contents, the people present, the weather. The renderer shows a
   neutral placeholder only if it ever gets there first.

## 4. Engine changes this needs (small; each on its own branch with tests and review)

- **E1. Resolve the unmarked.** In an `invent_under_canon` world, `resolve()` on
  an aspect with no thunk and no known value plants and forces it in one step.
  Today it returns nothing unless the thunk was planted first.
- **E2. Structured request.** The generator receives the entity, the aspect and
  the constraints as structured fields beside the prompt, so a specialist
  generator such as Photonic does not have to parse prose.
- **E3. Worn things are things.** A resolution can create garments as objects
  `worn_by` the person, as contents are created `in` a room. Then the dress can
  be taken off, stolen or used as evidence.

## 5. Questions for each module

**construct:**
- Does sealing plot-critical aspects before play fit your authoring flow?
- Who runs the world service? Is it your process today, with a direct read and
  resolve API exposed to the others, or a separate small process?
- Does story-minutes valid time vs turn-ordinal (holo-emitter's question (a))
  change anything here?

**holo-emitter:**
- Does direct read + resolve against the world service replace the
  deck-through-construct path for conditions and furniture, or sit beside it?
- What latency does a first-seen detail need?
- Is "pre-resolve at scene open, placeholder otherwise" enough?

**Photonic:**
- Is "the model picks words, the seed picks the look" the right split, or
  should Photonic own word selection too, from its closed vocabulary?
- Is the stored recipe of seed + generator version enough for an identical
  rebuild?

**Everyone:**
- What does this structure get wrong, or leave out?
- Is there a simpler shape?

## 6. Process

1. Round 1: each module answers §5 and challenges §3.
2. pb consolidates into one revised structure.
3. A final round-robin for polish.
4. It goes to Kabe to approve before anything is built.
