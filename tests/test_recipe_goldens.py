"""RECIPE-VOCAB-V1 §6, lane 1: the three recipe goldens (no model call).

Each `evals/recipes/<name>.facts.json` loads into a fresh world opened under the
recipe vocabulary (`attribute_default` and `apply_aliases`), and then: every
attribute is a RECIPE term or engine-canonical, `vocab.check()` is clean, and a
few reads answer as the recipe says. The lane-2 runner's free parts (its
manifest, its grader, and its scripted-oracle wiring check) are tested here too.
"""

from __future__ import annotations

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
            assert fact["source"] == {"manifest": True}


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
        "study", "hall", "doorway", "study_table", "book", "page", "hall_table"]
    assert unseeded == []
    assert [e.key for e in manifest.entries if e.fixture] == ["doorway"]


def test_lane2_a_manifest_fixture_row_makes_the_entry_a_fixture():
    golden = lane.load_golden("switched-light")
    golden["facts"].append({"entity": "obj:switch", "attribute": "fixture", "value": True,
                            "value_type": "literal", "frame": "canon", "valid_from": 0,
                            "source": {"manifest": True}})
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
    assert report["passed"] and report["ok"] == report["total"] > 10
    assert report["extra"] == []


def test_lane2_a_different_value_a_missing_key_and_a_missing_entity_fail(tmp_path):
    def mutate(w):
        w.porcelain.ingest_structured([
            {"entity": "obj:light", "attribute": "state", "value": "on", "valid_from": 5},
            {"entity": "obj:ghost", "attribute": "kind", "value": "object", "timeless": True},
            {"entity": "obj:ghost", "attribute": "colour", "value": "grey", "valid_from": 5}])
    report = _graded(tmp_path, "switched-light", mutate)
    failed = {(k["entity"], k["attribute"]) for k in report["keys"] if not k["ok"]}
    assert failed == {("obj:light", "state")} and not report["passed"]
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
        spelled["facts"][-1].update({"attribute": "within"})    # the same container, said another way
        lane.load_into(other, spelled)
        names = lane.world_names(other)
        report = lane.grade(golden, reference, other, lane.ids_by_name(golden, names))
        assert report["passed"], report["keys"]
    finally:
        reference.close()
        other.close()


def test_lane2_the_scripted_oracle_runs_the_whole_lane_with_no_model(tmp_path):
    """A free wiring check of manifest -> extract (with the vocabulary) -> commit
    -> grade. code-lock's door and outside are not in its text, so the oracle
    (which declares no escapes) cannot seed them: exactly those keys fail."""
    def refuse(prompt, schema):
        raise AssertionError("the oracle run made a model call")

    reports = {n: lane.run_recipe(n, tmp_path, refuse, oracle=True) for n in lane.RECIPES}
    assert reports["switched-light"]["passed"] and reports["take-and-drop"]["passed"]
    for name in ("switched-light", "take-and-drop"):
        assert reports[name]["findings"] == []
    code_lock = reports["code-lock"]
    failed = {(k["entity"], k["attribute"]) for k in code_lock["keys"] if not k["ok"]}
    assert failed and all(e in code_lock["unseeded"] or a == "controls" for e, a in failed)
    assert ("obj:keypad", "controls") in failed
    prompt = (tmp_path / "switched-light" / "prompt.txt").read_text()
    assert "Use these attribute names where they fit:" in prompt
    baseline = lane.run_recipe("switched-light", tmp_path / "plain", refuse, vocabulary=None,
                               oracle=True)
    assert "Use these attribute names" not in (tmp_path / "plain" / "switched-light" / "prompt.txt").read_text()
    assert baseline["vocabulary"] is None


def test_lane2_dry_run_calls_no_model_and_writes_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert lane.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "code-lock: 5 manifest entries" in out and "more)" in out
    assert list(tmp_path.iterdir()) == []


def test_lane2_a_paid_run_needs_the_metered_flag(tmp_path):
    with pytest.raises(SystemExit):
        lane.main([str(tmp_path / "out")])
