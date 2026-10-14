# CONTAINMENT-DURABILITY-V1: a movable's location is never made permanent by a guess

**Status:** r1.4 (pbr r1.3: `fixture` is typed exactly, round-trips through JSON, and travels to commit on the registry's identity record). r1.3 (pbr r1.2: the build library gets a host route for fixtures, and its model items are fixture-denied after the target world's canonicalization). r1.2 (pbr r1.1: `fixture` is host-only; model extraction can't write it). r1.1 answered pbr's r1 RED by narrowing:
- no per-world floor (`attr:in` is inviolable core);
- the being and fixture tests use only what the classifier can see, bounded at the row's own log position;
- no sidecar schema change;
- one floor helper for both classify paths.

For pbr review. Author: pb, 2026-10-13. An engine change to the classifier.
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
   guardrail, with no model call.
   - *(r1.1, pbr)* **A being** here is a subject id in the `person:` namespace, as written on the
     row. The classifier sees the buffer and attribute semantics only. Identity closure and the
     kind fold live elsewhere, and the fold reads the classifier, so they aren't used here.
   - Every being minted by `patternbuffer.build` and by construct is `person:`.
   - A being under another namespace still goes to the model, where rule 3's floor applies.
2. **Declared fixtures stay.** A host may declare a thing a fixture: `<entity> · fixture · true`, in
   canon.
   - `fixture` is added to the **structural predicates**, so its own row is CONSTITUTIVE by
     guardrail and never model-judged.
   - **Host-only** *(r1.2, pbr)*. A `fixture` item is **skipped**, with a typed receipt
     `fixture_not_host`, when the ingest call is in extracted (prose-authored) mode. That covers
     `ingest(text)`, which always runs `extracted=True`, and `ingest_structured(…, extracted=True)`.
     The skip happens at the gate, before anything is written. Structured host ingestion
     (`extracted=False`, the default) may write it.
   - **The build library** *(r1.3, pbr)*. Two changes to BUILD-LIBRARY-V1, made in this item's
     build:
     - **The host route.** `Entry` gains `fixture: bool = False`. It is valid only for the
       non-being types `object` and `place`. validate() refuses it on a being with
       `fixture_on_being`.
       - *(r1.4, pbr)* **Exact type.** validate() accepts only a real `bool` (`type(x) is bool`).
         A string, an int (including `1` and `0`), `None` or anything else is refused with
         `fixture_not_bool`, listed with the other problems in the one `ManifestError`.
       - *(r1.4)* **JSON round-trip.** `Manifest.to_dict()` writes `fixture` for every entry, and
         `from_dict()` reads it, defaulting to `false` when it is absent. So a manifest written
         before this change still loads. A fixture manifest round-trips equal and commits the same
         world.
       - *(r1.4)* **Transport to commit.** `Registry.from_manifest` copies the flag onto the
         entry's identity record (`Identity.fixture`, beside `id`, `type` and `species`).
         `entries()` reports it. Commit's manifest writer reads `Identity.fixture` by the entry's
         minted id, never by list position. Commit's manifest writer emits, after the entry's shape rows and before
       any chunk fact, one host row: `<id> · fixture · true`, timeless, canon, written through
       `ingest_structured` with `extracted=False` (host authority).
     - **The model route is closed after canonicalization.** For every model-result item (chunk
       facts and the facts on escape and pick handles), commit's pre-write check `_checked()`
       canonicalizes the item's attribute through the **target world's** `canonical_attribute`. That
       is the same alias map the gate will apply. Any item that canonicalizes to `fixture` is refused
       (`CommitRefused`) before any write.
     - So a world alias such as `fixed -> fixture` can't carry a model guess past the check.
       `grammar_problem()`'s literal refusal of `fixture` stays as the first, world-independent
       line.
     - Model items are **not** switched to `extracted=True`. That mode also runs the moved-event
       coordinate pass, which would change what the library writes. The canonicalized check is the
       narrower close.
   - So a model guess can never make a location permanent, whether by a CONSTITUTIVE verdict
     (rule 3) or by writing a fixture declaration.
   - **The exact check** *(r1.1, pbr)*:
     1. The classifier reads
        `buffer.visible(entity=row.entity, attribute="fixture", frame="canon", asserted_as_of=row.seq)`:
        the declarations visible when the containment row itself was written. Retractions are
        honoured, as `visible` already does.
     2. Of those, only timeless literal-boolean rows count. The **latest-asserted** one decides: if
        it is `true`, the row is **CONSTITUTIVE, 1.0**.
     3. A `false` row, or no row, means no fixture.
   - Because the read is bounded at `row.seq`, a declaration written after the containment row
     never reclassifies it, on first classification or on `rebuild()`. A later `fixture = false`
     governs only containment rows written after it.
   - The subject is the id as written, with no closure. A fixture declared on a merged twin
     doesn't count.
3. **No guessed permanence for movables.** For every other non-place subject (objects and anything
   unnamespaced), the model still judges.
   - **A low-confidence CONSTITUTIVE is stored as STATE.** A CONSTITUTIVE verdict with confidence
     below `CONTAINMENT_CONSTITUTIVE_FLOOR` (a module constant, **0.9**) is stored as **STATE**, with
     the model's confidence kept.
   - *(r1.1, pbr)* **One helper.** The normalization is a single function, applied in **both**
     `classify()` (single row) and `_classify_batch()`, so the two paths can't drift.
   - **No schema change.** The demotion adds no field to `Classification` or the sidecar, and stored
     records keep their current shape. Each demotion is logged at `INFO` with the row id and the
     model's confidence. The corpus test (test 6) recomputes demotions from the archived verdicts it
     feeds the fake model.
   - **No per-world floor.** `attr:in` is in the inviolable core, and every semantics declaration
     on it is refused (`check_declaration_authority`). A per-world floor would need a core exception
     nothing yet requires, so V1 has none.

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

1. **Beings:** `person:mara in place:hall` is STATE by guardrail, with no model call. *(r1.1)* An
   `npc:smuggler in place:hall` goes to the model, and a CONSTITUTIVE 0.7 verdict there is demoted
   by rule 3.
2. **Fixtures** *(r1.1)*:
   - with `obj:door · fixture · true` ingested **before** it, `obj:door in place:cell` is
     CONSTITUTIVE 1.0 with no model call. Without the declaration it goes to the model;
   - a `fixture = true` ingested **after** the containment row doesn't reclassify it, on first
     classification or on `rebuild()`;
   - `true` then `false` (both before the row): the latest decides, so no fixture;
   - a retracted `true` doesn't count;
   - *(r1.2, pbr)* `ingest_structured([obj:page · fixture · true], extracted=True)` and the prose
     `ingest()` path are skipped with `fixture_not_host`, writing nothing. A later
     `obj:page in obj:book` therefore goes to the model and the floor, never to the fixture
     guardrail;
   - *(r1.2)* the same item with `extracted=False` (a host) is written, and the guardrail applies;
   - *(r1.2)* a build-library extraction line with attribute `fixture` is refused by
     `grammar_problem()`;
   - *(r1.3, pbr)* in a world where the host declared an alias `fixed -> fixture`, a model item
     `obj:page · fixed · true` is refused by commit's `_checked()` with the world unchanged, and a
     later `obj:page in obj:book` goes to the model and the floor;
   - *(r1.3)* a manifest `Entry(..., type="object", fixture=True)` for `obj:barred_door` writes
     `fixture = true` as a host row before any chunk fact, and its containment row gets the fixture
     guardrail (CONSTITUTIVE 1.0, no model call);
   - *(r1.3)* `fixture=True` on a being is refused by validate() (`fixture_on_being`);
   - *(r1.4)* `fixture` set to `"yes"`, `1`, `0` and `None` is each refused with `fixture_not_bool`,
     and the int-shaped ones are not accepted as bools;
   - *(r1.4)* a manifest with a `fixture=True` entry survives `to_dict` then `from_dict` equal, and
     both commit byte-identical worlds (dumps equal). A dict without `fixture` loads as `false`;
   - *(r1.4)* `entries()` reports `fixture`, and reordering the manifest's entries still puts the
     fixture row on the right id.
3. **The floor:**
   - a model verdict of CONSTITUTIVE 0.7 on `obj:execution_page in obj:book` is stored STATE, with
     the confidence and the demoted mark;
   - CONSTITUTIVE 0.95 on `obj:barred_door in place:cell` stays CONSTITUTIVE;
   - *(r1.1)* the same verdicts through `_classify_batch` give the same stored classes (the
     single-row and batch paths agree);
   - *(r1.1)* each demotion logs one `INFO` record naming the row.
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
