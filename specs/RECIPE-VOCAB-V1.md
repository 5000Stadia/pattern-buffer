# RECIPE-VOCAB-V1: one declared vocabulary for the coherence recipes, and their goldens

**Status:** r1.4.1 (pbr's r1.4 RED: the Kabe author is exactly `Kabe YYYY-MM-DD` with a real calendar date, and each source form's keys are exact, so the loader can tell an allowed author from an unknown one). r1.4 (the metered lane-2 run, `evals/results/2026-10-14-recipe-lane/REPORT.md`, and holo-emitter mdeb447: every golden fact's `source` is either text, which cites a sentence, or authored, which names who authored it; lane 2 grades only text facts. The `exits` gloss says it is only ever `none`). r1.3.1 (on pb's build review: two glosses reworded for the model, since a gloss is prompt text; no behaviour change). r1.3 (pbr's r1.2 RED: `locked` leaves `state`'s values, and `check()` tests the folded pair: a locked door must read `state · shut`). r1.2 (holo-emitter's shape read mfb985e: a lock is its own boolean `locked`, `state` is a thing's one main setting, a part with its own setting is its own entity, and sitting is `sits_on`). r1.1 (construct's shape read m132fd6: `mode` becomes `control_mode`, since construct writes `mode` on its drift events; the aliases that are entity-valued in the wild, `outside`, `exit`, `way_out` and `pin`, are dropped, since an alias can't depend on the value type). r1, for a shape read by holo-emitter and construct, then pbr. Author: pb, 2026-10-14.
ROADMAP R56. Outside the engine core: a vocabulary is data, declared through the engine's existing
seams, with no engine change.
**Source:**
- **Kabe approved the coherence recipes** on 2026-10-13, via holo-emitter m3a6670 and m2c1f42:
  "Yes to all".
- **Holo-emitter's golden lane** already plays two recipes from facts in this shape:
  `lab/recipes/switched-light.facts.json` and `code-lock.facts.json`, drafted from pb's rows
  m046211.
- **The shape points settled on 2026-10-14** (m5f3da8, m342c1a):
  - `outdoors` is a timeless literal fact;
  - a code is a canon row plus the same row in `knows:<who>`;
  - `fixture` comes from the host's manifest;
  - held things are `held_by`, graded on the folded location.

## Need

Three projects write facts about the same small worlds: holo-emitter's demo, construct's
seeding and play, and this library's extraction from story text. Today nothing names the
attributes these recipes need.
- One writer says `controls` and another `operates`, or `disposition` and another `temperament`.
  The fold key then fragments, and a read for one misses the other.
- The engine's own canonical list covers only structure (`in`, `connects_to`, `kind`, …;
  `ingest.py` `_BUILTIN_ALIASES`), and says "domain vocabulary emerges freely".
- RFC-001 made an attribute's behaviour declarable as data (`attr:<name>` rows) so that domain
  vocabulary needn't be engine code. Nobody has declared any yet.

## The shape

### 1. A vocabulary is data: `patternbuffer.vocab`

A new module beside `patternbuffer.build`, outside the core, reaching the engine only through
public seams.

- **`Term(attribute, value_type, values, open_values, semantics, aliases, gloss)`**:
  - `attribute`: the canonical name;
  - `value_type`: `"entity"` or `"literal"`;
  - `values`: the canonical literal values (empty for entity-valued terms);
  - `open_values`: `False` when `values` is the whole set, `True` when it is a recommended list;
  - `semantics`: the `attr:` declaration (RFC-001 axes, and READ-SURFACE-V1's durability pin)
    as a dict, possibly empty;
  - `aliases`: the variant names that canonicalize to it;
  - `gloss`: one line, used verbatim in a prompt.
- **`Vocabulary(name, terms)`**, and **`RECIPE`**, the vocabulary below.
- **Declared semantics never reject a fact** (RFC-001's rejection test). The engine applies only
  the `semantics` and the aliases. A value outside `values` is still written; `vocab.check()`
  (§3) reports it.

### 2. Applying a vocabulary to a world: two existing seams

- **`vocab.attribute_default(vocabulary, fallback=None)`** returns a callable for
  `World(..., attribute_default=...)`.
  - The engine asks it once per attribute, at that attribute's first row, so a declaration
    always precedes data (the authority rule in `buffer.check_declaration_authority`).
  - It returns the term's `semantics` for a term, and otherwise `fallback(attribute)` or None.
  - A host with its own `attribute_default` passes it as the fallback.
- **`vocab.apply_aliases(world, vocabulary)`** calls `world.ingestor.add_attribute_alias(alias,
  canonical)` for every term alias.
  - A host calls it each time it opens a world: the alias map is in memory, and only aliases
    the gate has applied are rebuilt from their receipts.
  - It raises, naming the pair, when an alias is an inverse key (`holds`, `wearing`) or already
    maps elsewhere.
- **Nothing else changes.** A world opened without these behaves exactly as today.
- **A world that already has rows** for an attribute keeps that attribute's behaviour, by the
  engine's existing rule. `vocab.check()` names such attributes, so a host can tell when a term's
  semantics did not take.

### 3. `vocab.check(world, vocabulary, *, frame="canon") -> list[Finding]`

A read-only lint. It writes nothing and calls no model. One `Finding(kind, entity, attribute,
value, detail)` for each of:
- `off_vocabulary_value`: a literal outside a closed term's `values`;
- `wrong_value_type`: an entity value on a literal term, or the reverse;
- `alias_in_log`: a row stored under a term alias, which means it was written before
  `apply_aliases` ran;
- `undeclared_semantics`: a term whose `semantics` the world does not carry, because rows came
  first.

### 4. The recipe vocabulary, `RECIPE`

| attribute | type | values | semantics | aliases | gloss |
|---|---|---|---|---|---|
| `controls` | entity | n/a | `arity: set_valued`, `durability: CONSTITUTIVE` | `operates`, `powers` | what a switch, lever, plate, button or keypad works: `<switch> controls <light>` |
| `link_type` | literal | closed: `switch`, `lever`, `plate`, `button`, `keypad`, `dial` | `durability: CONSTITUTIVE` | `control_type` | what kind of control the source is |
| `control_mode` | literal | closed: `latching`, `momentary` | `durability: CONSTITUTIVE` | `mode` is **not** taken (construct's drift events use it), `switch_mode` | latching stays as set; momentary acts only while held |
| `state` | literal | open: `on`, `off`, `open`, `shut` (*r1.3:* never `locked`, which is `locked · true`) | none (model-judged, as today) | `status` is **not** taken (hosts use it) | a thing's one main setting now: a door's or lid's open or shut, a light's or switch's on or off; never locked (*r1.3.1:* the glosses are model-facing, so no spec names) |
| `locked` | literal | closed: `true`, `false` | `durability: STATE` | none | true while a lock is engaged; a locked door is also state shut *(r1.2, r1.3.1)* |
| `lit` | literal | closed: `dark`, `dim`, `lit`, `day`, `night` | none | `light_level`, `lighting`, `illumination` | how much light a place has now |
| `outdoors` | literal | closed: `true`, `false` | `durability: CONSTITUTIVE` | `is_outdoors` | a place open to the sky; written timeless |
| `exits` | literal | closed: `none` | none | none | an observed "no way out": only ever the word none; ways out are connects_to (*r1.4*) |
| `disposition` | literal | open: `friendly`, `wary`, `hostile`, `timid`, `playful`, `indifferent` | `durability: DISPOSITIONAL` | `temperament`, `demeanor`, `demeanour` | a being's temperament |
| `code` | literal | open (digits or a word) | none | `passcode`, `combination` | what a keypad or lock opens to |

- **`exits · none`** is RFC-002's legitimate negation: an observed positive fact with a
  negative-sounding value, never inferred from missing rows. The ways out of a place remain
  `connects_to` edges (the engine's lateral graph).
  - A place carrying both `exits · none` and a `connects_to` edge is served as written.
    `vocab.check()` reports it as `exits_none_with_edge`.
  - `none` is the only value: there is no `exits · <place>`.
- *(r1.2, holo-emitter)* **One main setting per thing.** `state` is a thing's main setting: a
  door's or lid's leaf (`open`, `shut`), or a light or switch (`on`, `off`).
  - A lock is `locked · true|false`, so a door can be shut and locked without two values
    colliding on one key.
  - **A locked door is also `state · shut`.** RFC-003's route traversal reads a portal's `state`
    against its kind's `blocks_when_state`, and doesn't read `locked`. Writing both keeps routes
    right.
  - *(r1.3, pbr)* `vocab.check()` tests the **folded current pair** per entity (the served
    `locked` and `state` at the head, in the checked frame):
    - `locked · true` with a served `state` other than `shut` is `locked_but_open` when that
      state is `open`, and **`locked_not_shut`** otherwise;
    - `locked · true` with no served `state` at all, or a conflicted one, is
      **`locked_state_missing`**;
    - a `state · locked` row anywhere is **`state_locked_legacy`**: the recipe spelling is
      `locked · true` plus `state · shut`. Older prose (RFC-003's examples, tests) keeps its
      meaning; only the lint flags it.
  - **A part with its own setting is its own entity.** A press's third drawer is
    `obj:press:drawer_3 · part_of · obj:press`, with its own `state · open`. The id grammar
    allows `:` but not `#`.
  - A keypad's accepted code isn't written as a state of the keypad: the door's `locked` carries
    the outcome.
- **Sitting** is the person's `sits_on <seat>` (VIEW-PEOPLE-V1), not a state of the chair. It is
  already canonical and is not redeclared.
- **`outdoors` is a literal `true`,** a JSON boolean. Its closed values are the booleans, not
  strings.
- **Excluded from the aliases:**
  - `status` (hosts use it for their own bookkeeping);
  - `light` (the object `obj:light` and the attribute must not collide in readers' minds);
  - `works` and `opens` for `controls` ("works at", "opens onto" mean other things).
  - *(r1.1, construct)* `outside`, `exit`, `way_out` and `pin`: each is entity-valued in the
    wild (`X outside place:Y`, `place:A exit place:B`, `obj:plate pin obj:lower_pin`). An alias
    renames the attribute whatever the value, so aliasing them onto a literal term would turn
    relations into `wrong_value_type` rows.
- **Already canonical and not redeclared:** `in`, `held_by`, `worn_by`, `connects_to`,
  `part_of`, `kind`, `role`, `fixture` (host-only, CONTAINMENT-DURABILITY-V1), and `posture`
  and `sits_on` (VIEW-PEOPLE-V1).

### 5. Extraction learns the vocabulary (build library, opt-in)

- `extract(..., vocabulary=None)`. When given, the prompt gains one section after the rules:
  "Use these attribute names where they fit:", then one line per term, `<attribute>: <gloss>`
  with its values when closed.
  - Without a vocabulary, the prompt is byte-identical to today's, so no existing build changes
    and no metered check is needed to merge.
  - A build that passes `RECIPE` changes its prompt, so its first use is a metered check (lane 2,
    §6) and waits for Kabe's yes.
- The engine's own Ingestor prompt is unchanged: the engine stays host-blind.

### 6. The goldens, in two lanes

- **Files:** `evals/recipes/<name>.facts.json` for `switched-light`, `code-lock` and
  `take-and-drop`, schema `patternbuffer.recipe-facts/1`. The shape is holo-emitter's files'
  shape:
  - `entities` carry only `id`, `kind` and `names`;
  - `facts` carry `entity`, `attribute`, `value`, `value_type`, `frame`, `valid_from` or
    `timeless`, and a `source`.
  - *(r1.4, holo-emitter mdeb447)* **Every fact has exactly one of two source forms**, never
    none:
    - **text:** exactly the keys `{"chapter": <int>, "sentence": <int>}`. The story states it,
      and lane 2 grades it;
    - **authored:** exactly `{"authored": "<who>"}` or `{"authored": "<who>", "note": "<why>"}`,
      with `note` a string. The story doesn't state it (the code's digits, an unnamed door,
      start states the text only implies). Lane 2 doesn't grade it: a build gets it from the
      manifest or the host, not from the text.
    - *(r1.4.1, pbr)* **`<who>` is one of exactly three forms:**
      - `"manifest"`: a host declaration such as `fixture`;
      - `"holo-emitter planner"`;
      - `"Kabe YYYY-MM-DD"`: a person's own choice, where the date is a real calendar date
        (`date.fromisoformat` accepts it and it is written back unchanged, so `Kabe 2026-02-30`
        and `Kabe 2026-1-5` are refused).
  - r1.3's `{"manifest": true}` becomes `{"authored": "manifest"}`.
  - **The golden loader refuses, naming the fact:**
    - a fact with no source;
    - a source with keys from both forms, or any key outside its form (*r1.4.1*);
    - a text source whose `chapter` or `sentence` isn't an integer;
    - an `authored` value that isn't one of the three forms.

    That's holo-emitter's rule, "cites its sentence or its author".
- **Lane 1, every change, no model** (`tests/test_recipe_goldens.py`): each golden loads into a
  fresh world opened with `attribute_default(RECIPE)` and `apply_aliases`, and then:
  - every attribute is a `RECIPE` term or engine-canonical;
  - `vocab.check()` returns no findings;
  - a handful of reads per recipe answer as the recipe says. For example:
    - switched-light: the light is off at 0, and the room is `dark` with `exits · none`;
    - code-lock: the dog knows the code (`knows:person:dog`); the door is a fixture
      (CONSTITUTIVE, from the manifest row); the keypad `controls` the door; outside is
      `outdoors`;
    - take-and-drop: an object `held_by person:player`, then `in` the scene, folds to the
      scene.
- **Lane 2, on demand, metered** (`evals/harness/recipe_lane.py`):
  - the recipe's story text goes through `patternbuffer.build` with `vocabulary=RECIPE`;
  - it is graded against the golden's **text** facts only *(r1.4)*, on folded reads.
    Containment is compared on the folded location, so any containment-family spelling of the
    same container matches. The report gives the matched count over text facts, and lists the
    authored facts it skipped, with their authors;
  - each lane-2 run waits for Kabe's yes, like every paid run.
- **Holo-emitter's drafts** are imported as the first goldens, corrected by the settled points.
  The take-and-drop golden is written from its recipe text.

## Not in this spec

- Behaviour: what `controls` *does* when a switch flips (a resolver or host rule). This spec
  names facts, it doesn't animate them.
- Closing `state`, `disposition` or `code` to fixed sets.
- Any engine change. If one proves necessary, it gets its own spec.

## Tests (no model calls)

0. *(r1.4)* **Sources:**
   - every fact in the three goldens has exactly one valid source form;
   - the loader refuses a fact with none, with both, or with an unknown `authored` value;
   - *(r1.4.1)* it refuses `Kabe 2026-02-30`, `Kabe 2026-1-5`, `Kabe` and `kabe 2026-10-14`,
     and accepts `Kabe 2026-10-14`;
   - *(r1.4.1)* it refuses an extra key on either form (`{"chapter", "sentence", "note"}`,
     `{"authored", "why"}`), a mixed source (`{"chapter", "authored"}`) and a non-integer
     `sentence`;
   - lane 2 in `--oracle` mode grades only text facts and lists the authored ones it skipped;
   - the `exits` gloss text is pinned.

1. **`Term` and `Vocabulary`:** an unknown `value_type`, a closed term with no values, a
   duplicate attribute, or an alias claimed by two terms is refused at construction, naming it.
2. **`attribute_default`:**
   - in a fresh world, the first `controls` row writes `attr:controls · arity · set_valued` and
     its CONSTITUTIVE pin before the data row, and the row classifies CONSTITUTIVE 1.0 with no
     model call;
   - `disposition` pins DISPOSITIONAL;
   - a non-term attribute falls through to the host's fallback.
3. **`apply_aliases`:**
   - `temperament` canonicalizes to `disposition`, with the gate's receipt;
   - `holds` as an alias raises;
   - reopening the world and applying again is idempotent.
4. **`check`:** each finding kind on a hand-built world, and none on a clean one, with
   `exits_none_with_edge` and `locked_but_open` included. *(r1.2)* A locked, shut door blocks a
   route under `traversal:door · blocks_when_state · shut`. *(r1.3)* These lane-1 cases are
   flagged:
   - `door state locked` alone is `state_locked_legacy`;
   - `door locked true` with no state is `locked_state_missing`;
   - with `state · ajar` it is `locked_not_shut`;
   - with `state · open` it is `locked_but_open`;
   - shut and locked is clean, and still blocks the route.
5. **Extract prompt:** with `vocabulary=None` it is byte-identical to today's (pinned). With
   `RECIPE`, the vocabulary section is present and lists every term once.
6. **Lane 1:** the three goldens load clean and their reads pass.
7. **Full suite green.**
