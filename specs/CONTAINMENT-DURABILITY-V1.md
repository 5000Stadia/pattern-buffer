# CONTAINMENT-DURABILITY-V1: a movable's location is never made permanent by a guess

**Status:** r1, for pbr review. Author: pb, 2026-10-13. An engine change to the classifier.
**Source:** construct's measurement on run 10's played world (m72c587).
- At low effort, the classifier judged clearly portable objects' containment rows CONSTITUTIVE:
  - `obj:execution_page in obj:book`;
  - `obj:split_seal in obj:execution_page`;
  - `obj:wedge in obj:fall_board`.

  That was among 39 movable-family CONSTITUTIVE rows; the rest were real fixtures, such as a barred
  door and a window in a cell.
- At effort "none", 6 more portable objects were made permanent.
- Construct's run 9 showed objects flickering back to their old places.
- Corpus: construct's effort-probe archive, read-only.

**Builds on:** the durability doctrine (whitepaper §7) and the classifier's guardrails
(`classify.py` `_guardrails`); FOLD-CORRECTNESS-V1 §4 (a CONSTITUTIVE row outranks STATE and
DISPOSITIONAL rows on its key); READ-SURFACE-V1 §1 (durability pins); PERSON-ROLES-V1 (the person
test).

## Need

**The mechanism.** A CONSTITUTIVE row outranks every STATE row on its key ("structure is never
superseded by recency", `indexes/fold.py`). So when a portable object's `in` row is judged
CONSTITUTIVE:
- every later move of that object (a take, a drop) is a STATE row that never serves;
- reads keep showing the object where it first was.

That is right for a fixture, a door in a wall, and wrong for a page in a book.

**Today's guardrails:**
- `held_by`, `worn_by` and `carried_by` are STATE;
- a `place:` subject's containment is CONSTITUTIVE;
- every other containment row goes to the model, including an **object's** `in` and a **person's**
  `in`;
- the model is told "ambiguous fixture containment -> CONSTITUTIVE".

So a guess, and at low effort a frequent one, can freeze a movable thing, or a person, in place.

## The shape

Four rules, all in `Classifier._guardrails` and the classifier's prompts. Nothing changes in the
fold.

1. **Beings move.** A containment-family row whose subject is a being is **STATE, 0.95**, by
   guardrail, with no model call. A being is PERSON-ROLES-V1's person test: a `person:` closure
   member, or a canon kind folded to `person`.
2. **Declared fixtures stay.** A host may declare a thing a fixture: `<entity> · fixture · true`, in
   canon.
   - `fixture` is added to the **structural predicates**, so its own row is CONSTITUTIVE by
     guardrail and never model-judged.
   - A containment-family row whose subject has a visible canon `fixture = true` row (read directly
     from the buffer, as of the row being classified, with no fold) is **CONSTITUTIVE, 1.0**.
3. **No guessed permanence for movables.** For every other non-place subject (objects and anything
   unnamespaced), the model still judges. But a **CONSTITUTIVE verdict with confidence below
   `CONTAINMENT_CONSTITUTIVE_FLOOR`** is stored as **STATE**, with the model's confidence kept and a
   `demoted: "containment_floor"` mark on the classification record.
   - The floor is **0.9** by default, set from construct's corpus (test 6), and can be overridden per
     world by a durability-pin-style declaration on `attr:in`:
     `attr:in · constitutive_floor · <0..1>`.
4. **The prompt.** Both classifier prompts replace "ambiguous fixture containment -> CONSTITUTIVE"
   with "an object's location is STATE unless the object is clearly built into the place (a door, a
   window, a fixed fitting); when unsure, STATE."

**Unchanged:**
- places' containment (CONSTITUTIVE);
- held, worn and carried (STATE);
- every other attribute;
- the fold;
- verdicts already stored. The classification sidecar is rebuildable: a host can reclassify a world
  under the new rules, and existing worlds are otherwise untouched.

## Why this shape

- **Precision first, the engine's standing rule.** A wrong STATE on a real fixture costs little: a
  door with no later move rows still folds to its only location. A wrong CONSTITUTIVE on a movable
  freezes it, and every later move silently fails.
- **The fixture declaration** lets a host make permanence certain without a model judgement.
- **The floor**, rather than a blanket STATE for objects, keeps the model's high-confidence fixtures
  (the barred door, the cell window).

## Tests

1. **Beings:** `person:mara in place:hall` and a `kind = person` NPC's `in` are STATE by guardrail,
   with no model call.
2. **Fixtures:** with `obj:door · fixture · true`, `obj:door in place:cell` is CONSTITUTIVE 1.0 with
   no model call. Without the declaration it goes to the model.
3. **The floor:**
   - a model verdict of CONSTITUTIVE 0.7 on `obj:execution_page in obj:book` is stored STATE, with
     the confidence and the demoted mark;
   - CONSTITUTIVE 0.95 on `obj:barred_door in place:cell` stays CONSTITUTIVE;
   - a world pin of `constitutive_floor = 0.6` keeps the 0.7 verdict CONSTITUTIVE.
4. **The flicker, end to end:** a page in a book, then a take (`held_by person:player`), then a drop
   (`in place:hall`). With the demotion, the page reads `in place:hall`. Without it (the old rule,
   simulated), it reads `in obj:book`.
5. **The prompt text:** both prompts contain the new sentence, and neither contains "ambiguous
   fixture containment -> CONSTITUTIVE".
6. **Construct's corpus** (read-only copies of the effort-probe rows, through a fake model returning
   the archived verdicts):
   - none of the named portable objects ends CONSTITUTIVE;
   - the barred door and the cell window stay CONSTITUTIVE.

   The report lists every demoted row and its confidence, which is the evidence for the 0.9
   default.
7. **Unchanged elsewhere:** the chapter-test battery and the ingestion-fidelity numbers either don't
   move, or every movement is listed and explained.
8. Full suite green.

## Lexicon and whitepaper (with the build)

- **fixture:** a host's declaration that a thing is built into its container; its containment is
  CONSTITUTIVE without a model call.
- **Whitepaper decision row:** the durability doctrine's containment sub-rule is restated.
  Ambiguity about whether a thing is a fixture now means STATE, and permanence needs a declaration
  or high confidence.
