# BEATS-V1: author frames are sealed, and beats are written in one shared shape

**Status:** r1.1 (pbr's r1 RED: `WorldService.attach(world, view_frame)` also installs a view frame and is guarded too; the rule now covers every public function that takes a view frame, `mirror.present_handles` included). r1, for pbr review. It folds in the shape reads of construct (m3a85eb) and holo-emitter (meb1f95):
- `session:*` frames are not author frames;
- the reference rule is a read-only lint, never a gate;
- `patternbuffer.condition/1` is construct's `arc/io.py` JSON, pinned and round-trip tested on both sides;
- holo-emitter's narrator parses that shape verbatim and needs no engine-side availability read.

r0 was the shape read. Author: pb, 2026-10-14.
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
  - *(r1, construct)* **`session:*` is not an author frame.** It holds construct's
    bookkeeping (turns, transcript, the episode cast), and play reads it every turn.
  - `model.AUTHOR_FRAME_PREFIX = "plot:"` and `is_author_frame(frame)` are the single test.
- **Never a view.** *(r1.1, pbr)* **Every public function that takes a view frame** refuses an
  author frame, with `ValueError` naming the rule, before it stores or uses the frame:
  - `WorldService.attach(world, view_frame)`, the ordinary entry point;
  - `Runner(open_world, view_frame, ...)`, **in its constructor**. The runner attaches on its
    own pump thread, where a refusal from `attach` would surface late and off the caller's
    thread, so it refuses up front as well;
  - `WorldService.set_view_frame(frame)`;
  - `mirror.feed`, `mirror.export` and `mirror.present_handles`. `present_handles` builds the
    presentation layer a viewer sees, so it is guarded, not left as host-only.

  Session reads use the service's installed frame, so they are covered by the two setters. The
  build lists every public function in `service.py` and `mirror.py` that takes a `view_frame`,
  and fails a test if one is unguarded. Today `set_view_frame` checks only that the name is
  non-empty (`service.py:355`), and `attach` checks nothing.
- **Never widened, never a character's frame.** These already hold and are pinned by tests:
  - FRAME-CONTINUITY-V1 widens only `knows:` frames;
  - frames filter at source, so a `knows:` read never sees `plot:` rows;
  - an author `record` refuses `plot:*` (AUTHOR-RECORD-V1).
- **Where the plot can still leak: references from outside.** A canon or `knows:` row can name
  an id that exists only in an author frame. That carries plot into a frame a player can reach.
  - *(r1, construct and holo-emitter)* **A lint, never a gate.** A gate that skipped such a row
    would drop real world consequences.
  - Construct's clock effects are fine. Their `caused_by` names a canon event
    (`event:<clock>_fired_<turn>`, whose kind row is written to canon in the same ingest);
    `plot:main` keeps only the firing's status.
  - **`beats.author_references(world, *, frames=("canon",)) -> list[Finding]`** is read-only:
    no writes, no model. It returns one `Finding(kind, row_id, entity, attribute, target,
    detail)` per row in the given frames (and every `knows:` frame, when `"knows:*"` is
    listed), of two kinds:
    - `author_frame_reference`: the row's entity, entity-valued value or `caused_by` target
      has rows in an author frame and none in canon;
    - `dangling_caused_by` *(construct's guard)*: a `caused_by` whose target has no canon row
      at all. This catches a host that chains into `plot:`.
  - Holo-emitter runs it at build time, before the export ships to an offline phone. Construct
    may run it in its build lint.
- **Readers that may see author frames:**
  - the host's own reads (porcelain with an explicit `frame="plot:…"`);
  - the MCP wrapper, a fully trusted principal (MCP-WRAPPER-V1);
  - construct's navigator.

  The narrator lane stays blind to `plot:`, by the existing whitepaper A4 pattern.

## 2. The beat shape (a written convention; no engine code)

- **Where it lives:** a beat is an ordinary entity in an author frame. Construct's
  `arc/io.py` `_beat_rows` are the reference serialization:
  - `kind beat` and `part_of <arc>`;
  - `beat_phase` and `weight`;
  - `achievable_via <condition>` and, optional, `unreachable_if <condition>` and `correlates`;
  - `status` (`pending`, `achieved`, `closed`).

  Everything is timeless except `status`.
- **Conditions: `patternbuffer.condition/1`** *(r1: pinned)*. A condition is stored as a JSON
  **string** literal (`json.dumps` of the object), exactly as construct writes it.
  - The object grammar is construct's `expr_to_obj`. An atom is `{"op": <atom>, ...its fields}`:
    - `state_is {entity, attribute, value}`;
    - `located {entity, place}`;
    - `in_frame {frame, entity, attribute, value}`;
    - `occurred {kind, participants=[], since=null, until=null, min_count=1}`;
    - `beat_achieved {beat_id, plot_frame="plot:main"}`;
    - `clock_fired {clock_id, n=1, plot_frame="plot:main"}`;
    - `turns_elapsed {at_least}` and `turns_quiet {at_least}` (host counters);
    - `quantity {entity, attribute, cmp, value, frame="canon"}`, with `cmp` one of `>=`, `>`,
      `<=`, `<`, `==`, `!=`.
  - The operators are `not {operand}`, `all_of {operands}`, `any_of {operands}` and
    `at_least {k, operands}`.
  - The schema is committed as `schemas/patternbuffer.condition-1.json` (JSON Schema
    2020-12). `beats.validate_condition(obj)` returns the list of problems, empty when valid.
    It is a shape check only, and evaluates nothing.
  - **The version string is pinned:** `CONDITION_SCHEMA = "patternbuffer.condition/1"`. A change
    to either side's grammar is a `/2`. Construct adds a round-trip test against this schema,
    and pattern-buffer pins a fixture of construct's serialized conditions, so a drift on
    either side fails a test.
  - Holo-emitter's narrator parses the same shape verbatim and refuses, with the reason, what it
    can't evaluate (meb1f95).
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

## 4. Where the code goes

- **Engine core:**
  - `model.is_author_frame`;
  - *(r1.1)* the refusals in `WorldService.attach` and `set_view_frame`, and in `mirror.feed`,
    `export` and `present_handles`.

  That is the only engine change.
- **Outside the core:** `patternbuffer.beats`, beside `vocab` and `build`, holding
  `CONDITION_SCHEMA`, `validate_condition` and `author_references`, plus the schema file.

## 5. Tests

1. *(r1.1)* `WorldService().attach(world, "plot:main")`, `Runner(..., "plot:main")`,
   `set_view_frame("plot:main")`, `mirror.export`, `mirror.feed` and `mirror.present_handles`
   with `"plot:main"` each raise `ValueError`, naming the author-frame rule.
   - `attach` refuses before any reader snapshot opens, and the service stays unattached.
   - `canon`, `knows:` and `session:main` views are unchanged.
   - An introspection test enumerates the public `service`/`mirror` callables with a
     `view_frame` parameter and asserts each refuses.
2. A beat's rows in `plot:main` (construct's `_beat_rows` shape) are absent from every canon and
   `knows:` read, every mirror export and every widened read. This pins what already holds.
3. `author_references`:
   - a canon row whose value is a `plot:`-only id is reported as `author_frame_reference`;
   - a canon effect whose `caused_by` names a canon event is clean (construct's shape);
   - a `caused_by` naming an id with no canon row is reported as `dangling_caused_by`;
   - a `knows:` row naming a `plot:`-only id is reported when `"knows:*"` is listed;
   - nothing is written.
4. `validate_condition`:
   - every atom and operator round-trips through the schema;
   - a pinned fixture of construct-serialized conditions validates;
   - an unknown `op`, a missing field, a wrong type and a bad `cmp` each give one named problem.
5. Full suite green.

## 6. The shape-read answers (r1)

- **Construct** (m3a85eb):
  - `session:*` is not an author frame;
  - the reference check is a lint, never a gate;
  - naming `arc/io.py`'s JSON as `patternbuffer.condition/1` is fine. Pin it, and construct adds
    a round-trip test.
- **Holo-emitter** (meb1f95):
  - "never a view" covers the phone and the mirror;
  - a build-time lint of plot references is enough;
  - a written shape is enough: its narrator evaluates offline in the page, where no engine read
    is possible.

## 7. What the surveys contributed

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
