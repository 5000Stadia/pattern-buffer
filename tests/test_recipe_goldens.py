"""RECIPE-VOCAB-V1 §6, lane 1: the three recipe goldens (no model call).

Each `evals/recipes/<name>.facts.json` loads into a fresh world opened under the
recipe vocabulary (`attribute_default` and `apply_aliases`), and then: every
attribute is a RECIPE term or engine-canonical, `vocab.check()` is clean, and a
few reads answer as the recipe says. The lane-2 runner's free parts (its
manifest, its grader, and its scripted-oracle wiring check) are tested here too.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "evals" / "harness"))

import recipe_lane as lane  # noqa: E402

from patternbuffer.testing import StubModel, rule_classifier_fallback  # noqa: E402
from patternbuffer.vocab import RECIPE, check  # noqa: E402


@pytest.fixture
def loaded(tmp_path):
    """name -> the golden loaded into a fresh world (closed after the test)."""
    worlds = []

    def load(name):
        golden = lane.load_golden(name)
        silent = StubModel(fallback=rule_classifier_fallback())
        w = lane.open_world(tmp_path / f"{name}.world", f"w:{name}", model=silent)
        worlds.append(w)
        lane.load_into(w, golden)
        return golden, w

    yield load
    for w in worlds:
        w.close()


def state(w, entity, attribute, frame="canon", **kw):
    return w.porcelain.state(entity, attribute, frame, **kw)


def value(w, entity, attribute, frame="canon", **kw):
    served = state(w, entity, attribute, frame, **kw)
    assert served["status"] == "known", (entity, attribute, served)
    return served["fact"]["value"]


# ------------------------------------------------------ the files


@pytest.mark.parametrize("name", lane.RECIPES)
def test_6_the_golden_has_the_recipe_facts_shape(name):
    golden = json.loads(lane.golden_path(name).read_text())
    assert golden["schema"] == "patternbuffer.recipe-facts/1" and golden["recipe"] == name
    assert lane.golden_problems(golden) == []
    for fact in golden["facts"]:
        assert set(fact) <= {"entity", "attribute", "value", "value_type", "frame",
                             "valid_from", "timeless", "source"}, fact
        if fact["attribute"] == "fixture":
            assert fact["source"].get("authored") == "manifest"


def test_6_a_malformed_golden_is_named():
    problems = lane.golden_problems({
        "schema": "x", "entities": [{"id": "a:b", "kind": "k", "names": [], "extra": 1}],
        "facts": [{"entity": "nope", "attribute": "in", "value": "x", "value_type": "text",
                   "frame": "canon", "valid_from": 0, "timeless": True, "source": {}}]})
    assert len(problems) == 6


@pytest.mark.parametrize("name", lane.RECIPES)
def test_6_every_attribute_is_a_term_or_engine_canonical_and_the_world_is_clean(loaded, name):
    golden, w = loaded(name)
    terms = {t.attribute for t in RECIPE.terms}
    for fact in golden["facts"]:
        assert fact["attribute"] in terms | lane.ENGINE_CANONICAL, fact
        assert w.canonical_attribute(fact["attribute"]) == fact["attribute"], \
            f"{fact['attribute']} is an alias, not the canonical name"
    assert check(w, RECIPE) == []
    assert check(w, RECIPE, frame="knows:person:dog") == []


# ------------------------------------------- sources (r1.4, r1.4.1)

FIVE = {  # a tiny golden: 3 sentences, one fact whose source each test swaps
    "schema": "patternbuffer.recipe-facts/1", "recipe": "t",
    "story": "A room. A lamp. A dog.",
    "entities": [{"id": "place:room", "kind": "place", "names": ["room"]}],
    "facts": [{"entity": "place:room", "attribute": "lit", "value": "dark",
               "value_type": "literal", "frame": "canon", "valid_from": 0}]}


def with_source(source):
    golden = copy.deepcopy(FIVE)
    if source is not ...:
        golden["facts"][0]["source"] = source
    return golden


def problems_for(source):
    return lane.golden_problems(with_source(source))


def test_0_the_story_has_the_sentences_the_loader_counts():
    assert len(lane.Book({1: FIVE["story"]}).sentences(1)) == 3


@pytest.mark.parametrize("name", lane.RECIPES)
def test_0_every_golden_fact_has_exactly_one_valid_source_form(name):
    golden = json.loads(lane.golden_path(name).read_text())
    count = len(lane.Book({1: golden["story"]}).sentences(1))
    for fact in golden["facts"]:
        source = fact["source"]
        assert lane.source_problem(source, count) is None, fact
        assert (set(source) == {"chapter", "sentence"}) != ("authored" in source)
        if "authored" in source:
            assert isinstance(source.get("note", ""), str) and source["note"], fact


def test_0_the_goldens_split_into_text_and_authored_as_the_lane_report_found():
    counts = {}
    for name in lane.RECIPES:
        facts = lane.load_golden(name)["facts"]
        counts[name] = (sum(lane.is_text(f) for f in facts),
                        sorted({f["source"]["authored"] for f in facts if not lane.is_text(f)}))
    assert counts == {
        "switched-light": (9, ["holo-emitter planner"]),
        "code-lock": (10, ["holo-emitter planner", "manifest"]),
        "take-and-drop": (13, ["holo-emitter planner", "manifest"])}


def test_0_the_loader_refuses_none_both_and_an_unknown_author_naming_the_fact():
    for source in (..., None, {}, {"manifest": True}, {"chapter": 1, "sentence": 1, "authored": "manifest"},
                   {"authored": "somebody"}, {"authored": 3}):
        problems = problems_for(source)
        assert len(problems) == 1 and "fact 0 (place:room lit)" in problems[0], (source, problems)
    assert problems_for({"authored": "manifest"}) == []
    assert problems_for({"authored": "holo-emitter planner", "note": "why"}) == []


def test_0_the_kabe_author_is_exactly_kabe_and_a_real_date():
    for refused in ("Kabe 2026-02-30", "Kabe 2026-1-5", "Kabe", "kabe 2026-10-14",
                    "Kabe  2026-10-14", "Kabe 20261014", "Kabe 2026-10-14 "):
        assert len(problems_for({"authored": refused})) == 1, refused
    assert problems_for({"authored": "Kabe 2026-10-14"}) == []


def test_0_an_extra_key_a_mixed_source_and_a_non_integer_sentence_are_refused():
    for source in ({"chapter": 1, "sentence": 1, "note": "n"}, {"authored": "manifest", "why": "n"},
                   {"chapter": 1, "authored": "manifest"}, {"chapter": 1},
                   {"authored": "manifest", "sentence": 1}, {"note": "only a note"},
                   {"chapter": 1, "sentence": "1"}, {"chapter": 1, "sentence": 1.0},
                   {"chapter": "1", "sentence": 1}, {"authored": "manifest", "note": 7}):
        assert len(problems_for(source)) == 1, source


def test_0_a_text_source_cites_a_sentence_that_exists():
    for source in ({"chapter": 0, "sentence": 1}, {"chapter": 2, "sentence": 1},
                   {"chapter": True, "sentence": 1}, {"chapter": 1, "sentence": 0},
                   {"chapter": 1, "sentence": -1}, {"chapter": 1, "sentence": True},
                   {"chapter": 1, "sentence": 4}):
        assert len(problems_for(source)) == 1, source
    assert problems_for({"chapter": 1, "sentence": 1}) == []
    assert problems_for({"chapter": 1, "sentence": 3}) == []     # the last sentence itself


def test_0_the_exits_gloss_text_is_pinned():
    exits = RECIPE.term("exits")
    assert exits.gloss == ('an observed "no way out": only ever the word none; '
                           'ways out are connects_to')


# ----------------------------------------------------- switched-light


def test_6_switched_light_reads(loaded):
    _, w = loaded("switched-light")
    assert value(w, "obj:light", "state", as_of=0) == "off"
    assert value(w, "place:room", "lit", as_of=0) == "dark"
    assert value(w, "place:room", "exits") == "none"
    assert value(w, "obj:switch", "controls") == "obj:light"
    assert value(w, "obj:switch", "link_type") == "switch"
    assert value(w, "obj:switch", "control_mode") == "latching"
    assert value(w, "person:dog", "disposition") == "friendly"
    assert w.porcelain.locate("person:dog") == ["place:room"]
    assert sorted(w.porcelain.contents("place:room")) == ["obj:light", "obj:switch", "person:dog"]
    assert w.porcelain.path("place:room", "place:elsewhere") is None   # no exits, no edge


def test_6_switched_light_attributes_are_pinned_without_a_model(loaded):
    _, w = loaded("switched-light")
    for row in w.buffer.all_rows():
        if row.attribute in ("controls", "link_type", "control_mode"):
            verdict = w.classifier.get(row.id)
            assert (verdict.durability, verdict.class_confidence) == ("CONSTITUTIVE", 1.0)
        if row.attribute == "disposition":
            assert w.classifier.get(row.id).durability == "DISPOSITIONAL"
    assert w.semantics.is_set_valued("controls")


# ---------------------------------------------------------- code-lock


def test_6_code_lock_reads(loaded):
    _, w = loaded("code-lock")
    assert value(w, "obj:keypad", "code") == "4071"
    assert value(w, "obj:keypad", "code", "knows:person:dog") == "4071"
    assert w.who_knows("obj:keypad", "code") == ["knows:person:dog"]
    assert value(w, "obj:keypad", "controls") == "obj:door"
    assert value(w, "obj:keypad", "link_type") == "keypad"
    assert value(w, "place:outside", "outdoors") is True
    assert state(w, "place:outside", "outdoors")["fact"]["valid"] == [None, None]   # timeless
    assert value(w, "place:outside", "lit") == "day"
    assert value(w, "obj:door", "locked") is True
    assert value(w, "obj:door", "state") == "shut"
    assert state(w, "obj:door", "state", frame="knows:person:dog")["status"] == "unknown"


def test_6_code_lock_the_door_is_a_fixture_from_the_manifest(loaded):
    golden, w = loaded("code-lock")
    fixture = next(r for r in w.buffer.all_rows()
                   if r.entity == "obj:door" and r.attribute == "fixture")
    verdict = w.classifier.get(fixture.id)
    assert fixture.value is True and fixture.valid_from is None and fixture.frame == "canon"
    assert (verdict.durability, verdict.class_confidence) == ("CONSTITUTIVE", 1.0)
    door_in = next(r for r in w.buffer.all_rows()
                   if r.entity == "obj:door" and r.attribute == "in")
    verdict = w.classifier.get(door_in.id)
    assert (verdict.durability, verdict.class_confidence) == ("CONSTITUTIVE", 1.0)


def test_6_code_lock_a_locked_shut_door_blocks_the_route_under_a_door_policy(loaded):
    _, w = loaded("code-lock")
    w.porcelain.ingest_structured([
        {"entity": "traversal:door", "attribute": "blocks_when_state", "value": "shut",
         "timeless": True},
        {"entity": "place:room", "attribute": "connects_to", "value": "obj:door", "timeless": True}])
    assert check(w, RECIPE) == []
    route = w.route("place:room", "place:outside")
    assert route["status"] == "blocked"


# ------------------------------------------------------ take-and-drop


def test_6_take_and_drop_the_standing_world(loaded):
    _, w = loaded("take-and-drop")
    assert w.porcelain.locate("obj:page") == ["obj:book", "obj:study_table", "place:study"]
    assert w.porcelain.locate("obj:hall_table") == ["place:hall"]
    assert value(w, "obj:doorway", "state") == "open"
    fixture = next(r for r in w.buffer.all_rows()
                   if r.entity == "obj:doorway" and r.attribute == "fixture")
    assert fixture.valid_from is None and w.classifier.get(fixture.id).durability == "CONSTITUTIVE"
    assert w.route("place:study", "place:hall")["route"] == [
        "place:study", "obj:doorway", "place:hall"]


def test_6_take_and_drop_the_book_taken_then_put_down_folds_to_the_hall_table(loaded):
    """The play is not golden canon: the test writes it. Held is `held_by`, never
    a state of the book; `in` stays the word for 'on a table'."""
    _, w = loaded("take-and-drop")
    w.porcelain.ingest_structured([
        {"entity": "person:player", "attribute": "in", "value": "place:study", "valid_from": 0},
        {"entity": "obj:book", "attribute": "held_by", "value": "person:player", "valid_from": 1},
        {"entity": "obj:book", "attribute": "in", "value": "obj:hall_table", "valid_from": 2},
    ])
    p = w.porcelain
    assert p.locate("obj:book") == ["obj:hall_table", "place:hall"]
    assert p.locate("obj:book", as_of=0.5) == ["obj:study_table", "place:study"]
    assert p.locate("obj:book", as_of=1.5) == ["person:player", "place:study"]
    assert p.locate("obj:page") == ["obj:book", "obj:hall_table", "place:hall"]    # it rode along
    assert state(w, "obj:book", "held_by", as_of=1.5)["fact"]["value"] == "person:player"
    assert state(w, "obj:book", "state")["status"] == "unknown"
    assert "obj:book" in p.contents("obj:hall_table")
    assert "obj:book" not in p.contents("obj:study_table")
    assert check(w, RECIPE) == []


# ------------------------------------------- lane 2's free parts


def test_lane2_the_manifest_seeds_only_what_the_story_names():
    manifest, unseeded = lane.manifest_for(lane.load_golden("code-lock"))
    assert [e.key for e in manifest.entries] == ["room", "switch", "light", "dog", "keypad"]
    assert unseeded == ["place:outside", "obj:door"]
    manifest, unseeded = lane.manifest_for(lane.load_golden("take-and-drop"))
    assert [e.key for e in manifest.entries] == [
        "study", "hall", "doorway", "study_table", "book", "page", "hall_table",
        "steward", "steward_doublet", "steward_band"]
    assert unseeded == []
    assert [e.key for e in manifest.entries if e.fixture] == ["doorway"]


def test_lane2_a_manifest_fixture_row_makes_the_entry_a_fixture():
    golden = lane.load_golden("switched-light")
    golden["facts"].append({"entity": "obj:switch", "attribute": "fixture", "value": True,
                            "value_type": "literal", "frame": "canon", "valid_from": 0,
                            "source": {"authored": "manifest"}})
    manifest, _ = lane.manifest_for(golden)
    assert [e.key for e in manifest.entries if e.fixture] == ["switch"]


def _graded(tmp_path, name, mutate=None):
    golden = lane.load_golden(name)
    reference = lane.open_world(tmp_path / "ref.world", "w:ref")
    built = lane.open_world(tmp_path / "built.world", "w:built")
    try:
        lane.load_into(reference, golden)
        lane.load_into(built, golden)
        if mutate:
            mutate(built)
        return lane.grade(golden, reference, built, lane.ids_by_name(golden, lane.world_names(built)))
    finally:
        reference.close()
        built.close()


def test_lane2_the_golden_graded_against_itself_passes(tmp_path):
    report = _graded(tmp_path, "code-lock")
    assert report["passed"] and report["ok"] == report["total"] == 10
    assert report["extra"] == []


def test_lane2_a_different_value_a_missing_key_and_a_missing_entity_fail(tmp_path):
    def mutate(w):
        w.porcelain.ingest_structured([
            {"entity": "place:room", "attribute": "lit", "value": "lit", "valid_from": 5},
            {"entity": "obj:light", "attribute": "state", "value": "on", "valid_from": 5},
            {"entity": "obj:ghost", "attribute": "kind", "value": "object", "timeless": True},
            {"entity": "obj:ghost", "attribute": "colour", "value": "grey", "valid_from": 5}])
    report = _graded(tmp_path, "switched-light", mutate)
    failed = {(k["entity"], k["attribute"]) for k in report["keys"] if not k["ok"]}
    # the room's light level (a text fact) is graded; the light's state (authored) is not
    assert failed == {("place:room", "lit")} and not report["passed"]
    assert ("obj:light", "state") not in {(k["entity"], k["attribute"]) for k in report["keys"]}
    assert {"entity": "obj:ghost", "attribute": "colour", "value": "grey"} in report["extra"]


def test_lane2_containment_is_graded_on_the_folded_location(tmp_path):
    """The built key spelled held_by, the golden's `in`: the same folded place
    (the player stands in the room, so a thing it holds is, folded, held)."""
    golden = lane.load_golden("take-and-drop")
    reference = lane.open_world(tmp_path / "r.world", "w:r")
    other = lane.open_world(tmp_path / "o.world", "w:o")
    try:
        lane.load_into(reference, golden)
        spelled = json.loads(json.dumps(golden))
        table = next(f for f in spelled["facts"]
                     if f["entity"] == "obj:hall_table" and f["attribute"] == "in")
        table.update({"attribute": "within"})    # the same container, said another way
        lane.load_into(other, spelled)
        names = lane.world_names(other)
        report = lane.grade(golden, reference, other, lane.ids_by_name(golden, names))
        assert report["passed"], report["keys"]
    finally:
        reference.close()
        other.close()


def test_lane2_the_scripted_oracle_runs_the_whole_lane_with_no_model(tmp_path):
    """A free wiring check of manifest -> extract (with the vocabulary) -> commit
    -> grade. The oracle emits lines for text facts only, and lane 2 grades text
    facts only, so all three recipes pass; code-lock's door and outside are
    authored (its text never names them), and the report lists what it skipped."""
    def refuse(prompt, schema):
        raise AssertionError("the oracle run made a model call")

    reports = {n: lane.run_recipe(n, tmp_path, refuse, oracle=True) for n in lane.RECIPES}
    assert all(r["passed"] for r in reports.values())
    for name in lane.RECIPES:
        assert reports[name]["findings"] == []
        facts = lane.load_golden(name)["facts"]
        assert reports[name]["text_facts"] == sum(lane.is_text(f) for f in facts)
        assert reports[name]["authored_facts"] == sum(not lane.is_text(f) for f in facts)
    code_lock = reports["code-lock"]
    graded = {(k["entity"], k["attribute"]) for k in code_lock["keys"]}
    assert ("obj:door", "state") not in graded and ("obj:keypad", "code") not in graded
    assert ("obj:keypad", "controls") not in graded and ("obj:light", "state") not in graded
    skipped = {(s["entity"], s["attribute"], s["frame"]): s["authored"]
               for s in code_lock["skipped_authored"]}
    assert len(skipped) == 13
    assert skipped[("obj:door", "fixture", "canon")] == "manifest"
    assert skipped[("obj:keypad", "code", "knows:person:dog")] == "holo-emitter planner"
    prompt = (tmp_path / "switched-light" / "prompt.txt").read_text()
    assert "Use these attribute names where they fit:" in prompt
    baseline = lane.run_recipe("switched-light", tmp_path / "plain", refuse, vocabulary=None,
                               oracle=True)
    assert "Use these attribute names" not in (tmp_path / "plain" / "switched-light" / "prompt.txt").read_text()
    assert baseline["vocabulary"] is None


def test_lane2_the_oracle_speaks_only_text_facts_and_grading_ignores_authored_ones(tmp_path):
    golden = lane.load_golden("code-lock")
    manifest, _ = lane.manifest_for(golden)
    registry = lane.build.Registry.from_manifest(manifest, {1: golden["story"]})
    lines = lane.oracle_model(golden, registry)("", {})["lines"]
    assert len(lines) == 10      # the 10 text facts, none authored (all 10 are on seeded entities)
    keypad = next(e for e in registry.identities if "keypad" in e.names).id
    assert not any(f"|{keypad}|controls|" in line or "|4071" in line or '"4071"' in line
                   for line in lines)
    assert not any(line.split("|")[2] in ("state", "locked", "posture", "code") for line in lines)
    report = _graded(tmp_path, "code-lock")
    assert report["text_facts"] == 10 and report["authored_facts"] == 13
    assert {k["attribute"] for k in report["keys"]} == {
        "lit", "location", "controls", "link_type", "control_mode", "disposition"}


def test_lane2_dry_run_calls_no_model_and_writes_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert lane.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "code-lock: 5 manifest entries" in out and "more)" in out
    assert list(tmp_path.iterdir()) == []


def test_lane2_a_paid_run_needs_the_metered_flag(tmp_path):
    with pytest.raises(SystemExit):
        lane.main([str(tmp_path / "out")])


def test_0a_r1_5_the_steward_wears_a_black_doublet_and_a_white_falling_band(tmp_path):
    """RECIPE-VOCAB-V1 r1.5 (holo-emitter m228b7b): a person in the hall and what
    they wear, all six facts stated by sentence 4; `color` folds to `colour`."""
    golden = lane.load_golden("take-and-drop")
    steward = [f for f in golden["facts"] if f["entity"].startswith(("person:steward",
                                                                      "obj:steward_"))]
    assert len(steward) == 6
    assert all(f["source"] == {"chapter": 1, "sentence": 4} for f in steward)
    w = lane.open_world(tmp_path / "s.world", "w:s")
    try:
        lane.load_into(w, golden)
        assert w.porcelain.locate("person:steward") == ["place:hall"]
        for thing, colour in (("obj:steward_doublet", "black"), ("obj:steward_band", "white")):
            assert w.porcelain.locate(thing)[0] == "person:steward"
            assert value(w, thing, "colour") == colour
        assert value(w, "person:steward", "posture") == "standing"
        assert w.canonical_attribute("color") == "colour"
    finally:
        w.close()
