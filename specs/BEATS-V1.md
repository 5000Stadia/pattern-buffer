# BEATS-V1: author frames are sealed, and beats are written in one shared shape

**Status:** r0, a shape read for construct and holo-emitter before pbr. Author: pb, 2026-10-14.
ROADMAP R53.
**Source:**
- **Kabe** (holo-emitter's R79 gate, 2026-10-13, relayed in mf409d7): beats should be "assimilated
  and ingested functionally at the same time that pattern buffer ingest its objects", and he
  asked whether they "should actually exist as a tracking mechanism in pattern buffer itself".
- **Kabe again** (via holo-emitter m17d4f4): "Fine if its elegant to the architectural direction
  but if were encrypting things and stuff thats silly", and "We don't want watson to just "know"
  who did it though ... if the pattern buffer call internally is with Watsons framing and cant
  touch the events of the night murder itself that seems mechanistically helpful."
- **Two surveys this session** (summarized in §6):
  - prior art: storylets, Inform 7 scenes, Ink and Yarn, quest stages, puzzle dependency charts,
    Façade, narrative planners;
  - what exists locally: construct's arc layer, holo-emitter's beats design, and the engine's
    frames, events, routes and mirror.

## The finding that shapes this spec

**Construct already tracks beats, well, on the host side** (`construct/arc/`, design
`docs/design/ARC-LAYER.md`):
- a nine-atom condition grammar with `Not`, `AllOf`, `AnyOf` and `AtLeast`, serialized as JSON;
- three-valued evaluation, where unknown never collapses to false;
- an `explain` tree that says which condition is missing;
- beats, clocks with declared effects, and a delete-relaxed solvability check;
- all of it read through the engine's public porcelain at a horizon. Beat state lives in
  `plot:main` and pacing in `session:main`.
- ARC-LAYER §11 says beat evaluation, clocks and pacing are "explicitly NOT needed engine-side".
- Holo-emitter's JS narrator is a port of the same model (`design/case/narrator.md`).

Moving evaluation into the engine would duplicate working host code and make the engine read
story logic. So the engine takes only what **no host can guarantee alone**:
- **sealing the author frames**, so that beats and plot never reach a player's view, a
  character's knowledge, an export or a phone ("Watson can't touch the night of the murder");
- **one written shape for a beat**, so that construct, holo-emitter and later readers share it.

Evaluation stays host-side, with construct's evaluator as the reference.

## 1. Author frames (engine)

- **Definition.** An **author frame** is a frame whose name starts with `plot:`. Construct
  already uses `plot:main`. This adds a frame class to the lexicon, not a new frame.
  - *Open for the shape read:* should construct's `session:` frames be author frames too? They
    hold pacing, not plot. I lean no. Construct says.
- **Never a view.** The read surfaces that serve a player or a device refuse an author frame as
  their frame, with `ValueError` naming the rule:
  - `mirror.feed` and `mirror.export` (`view_frame`);
  - `WorldService.set_view_frame`;
  - a `Session` read.

  Today the exclusion holds only because nobody passes `plot:*`. `set_view_frame` checks only
  that the name is non-empty (`service.py:355`).
- **Never widened, never a character's frame.** These already hold and are pinned by tests:
  - FRAME-CONTINUITY-V1 widens only `knows:` frames;
  - frames filter at source, so a `knows:` read never sees `plot:` rows;
  - an author `record` refuses `plot:*` (AUTHOR-RECORD-V1).
- **Where the plot can still leak: references from outside.** A canon or `knows:` row that names
  an id existing only in an author frame carries plot into a player-reachable frame. Examples are
  a clock effect's `caused_by` pointing at a firing event in `plot:main`, or an effect whose
  value is a beat id.
  - *Proposal for the shape read:* the gate skips such a row (`author_frame_reference`), and
    `caused_by` from a canon effect points at a canon event instead.
  - Construct's clock commits write effects to canon with `caused_by=<firing id>` today
    (`arc/executor.py:78–98`), so this needs construct's view before it's specced.
  - The alternative is a lint (a read that lists such rows) instead of a gate rule.
- **Readers that may see author frames:**
  - the host's own reads (porcelain with an explicit `frame="plot:…"`);
  - the MCP wrapper, a fully trusted principal (MCP-WRAPPER-V1);
  - construct's navigator.

  The narrator lane stays blind to `plot:`, by the existing whitepaper A4 pattern.

## 2. The beat shape (a written convention; no engine code)

- **Where it lives:** a beat is an ordinary `beat:<id>` entity in an author frame. Its
  declaration rows are:
  - `kind beat`;
  - `achievable_via <condition>` and `unreachable_if <condition>`;
  - `phase`, `weight`;
  - `effects <list of fact templates>`, optional.
- **Conditions** use **construct's grammar and JSON serialization** (`arc/io.py`): the atoms
  `state_is`, `located`, `in_frame`, `occurred`, `beat_achieved`, `clock_fired`, `quantity` and
  the host counters, plus `not`, `all_of`, `any_of` and `at_least`.
  - A condition is stored as one JSON-valued literal.
  - The schema name `patternbuffer.condition/1` points at construct's serialization, versioned
    with it.
- **Effects** are declarative fact templates (entity, attribute, value, frame), never code. That
  keeps a dependency graph (effect to condition) derivable for solvability (the survey: Gilbert's
  charts, planner reachability). The host writes them when it decides a beat happened. The engine
  never fires an effect.
- **"Happened"** is the host's `status achieved` row (or event) in the author frame, as construct
  writes it. Repeats are counted from those rows, never kept as hidden "used" state.
- **Availability** ("available, or which condition is missing") is the host evaluator's `explain`
  over the engine's reads at an explicit horizon (valid time, asserted time, frame). The engine
  stores no availability.

## 3. Not in this spec

- An engine-side condition evaluator or availability read. It gets revisited only when a host
  that can't run construct's evaluator needs one; holo-emitter's JS port is its own.
- Pacing, drama management, clocks firing (whitepaper §14: unsolved, and the host's).
- Multi-arc frames (`plot:<arc>`), which already fit the `plot:` prefix.

## 4. Tests (for the engine part, once shaped)

1. `mirror.export(world, "plot:main")`, `feed`, `WorldService.set_view_frame("plot:main")` and a
   session read in `plot:main` each raise, naming the author-frame rule. `knows:` and canon views
   are unchanged.
2. A beat row in `plot:main` is absent from every canon and `knows:` read, every mirror export
   and every widened read (pinning what already holds).
3. *(If the reference rule is adopted)* a canon row naming a `plot:`-only id is skipped
   `author_frame_reference`, and the world is unchanged.

## 5. Questions for the shape read

- **Construct:**
  - `session:` frames author or not?
  - The `caused_by` reference rule: a gate rule, a lint, or neither?
  - Is `arc/io.py`'s JSON the right shared serialization to name as `patternbuffer.condition/1`?
- **Holo-emitter:**
  - Does "never a view" cover your phone and mirror needs?
  - Is a written beat shape enough for your narrator port, or do you need an engine-side
    availability read (and for what)?

## 6. What the surveys contributed

- **Adopted:**
  - effects as declarative templates, so solvability is derivable (Gilbert, planners);
  - availability as a per-atom pass/fail report, not a boolean (Yarn's saliency tally; construct
    already does this);
  - repeats counted from happened rows, never hidden state (against Ink's `*`, Bethesda's stage
    integers);
  - author goals kept apart from character beliefs (narrative planners: Shirvani et al. 2017,
    Sabre).
- **Rejected:**
  - imperative effects (Bethesda result scripts, Inform rulebooks: they can't be analysed);
  - engine-side selection or firing (Façade's tension-arc matching belongs to a host);
  - one unique flag per storylet ("time caves").
- **Pitfall kept in view:** effect rows must not carry beat ids into player-reachable frames.
  That's §1's open reference rule.
