"""BOUNDED-READS-V1: entities() roster + facts() frame-scan + lean person.in.

Both reads are frame-bounded by construction (every read fixes perspective);
facts() serves raw visible rows for audited scans, never folds; the lean
extract path carries location changes end-to-end.
"""

import json

import pytest

from patternbuffer import World
from patternbuffer.ingest import _EXTRACT_RULES_LEAN
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "br.world", world_id="w:br", model=stub)
    w.ingest_structured([
        {"entity": "place:yard", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:street", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "person:nell", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:nell", "attribute": "in", "value": "place:yard",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:nell", "attribute": "suspects", "value": "the mate",
         "frame": "knows:person_maud", "valid_from": 2.0},
        {"entity": "place:late_pier", "attribute": "kind", "value": "place",
         "valid_from": 50.0},
    ])
    yield w
    w.close()


# ------------------------------------------------------------- entities()

def test_entities_roster_by_prefix(world):
    assert world.porcelain.entities("canon", prefix="place:") == [
        "place:late_pier", "place:street", "place:yard"]


def test_entities_frame_is_required_and_scopes(world):
    with pytest.raises(TypeError):
        world.porcelain.entities()          # no bare enumeration
    with pytest.raises(ValueError, match="frame"):
        world.porcelain.entities(None)      # explicit None must not scan all frames
    with pytest.raises(ValueError, match="frame"):
        world.porcelain.facts(None)
    assert world.porcelain.entities("knows:person_maud") == ["person:nell"]
    assert "person:nell" in world.porcelain.entities("canon")


def test_entities_as_of_gates_and_meta_excluded(world):
    early = world.porcelain.entities("canon", prefix="place:", as_of=10.0)
    assert "place:late_pier" not in early and "place:yard" in early
    assert not [e for e in world.porcelain.entities("canon")
                if e.startswith(("a:", "attr:"))]


# ---------------------------------------------------------------- facts()

def test_facts_scans_one_frame_only(world):
    knows = world.porcelain.facts("knows:person_maud")
    assert [f["attribute"] for f in knows] == ["suspects"]
    canon_attrs = {f["attribute"] for f in world.porcelain.facts("canon")}
    assert "suspects" not in canon_attrs and "in" in canon_attrs


def test_facts_narrowing_and_meta(world):
    rows = world.porcelain.facts("canon", entity="person:nell", attribute="in")
    assert len(rows) == 1 and rows[0]["value"] == "place:yard"
    # frame-wide scans exclude meta rows unless include_meta
    wide = world.porcelain.facts("canon")
    assert not [f for f in wide if f["entity"].startswith(("a:", "attr:"))]
    with_meta = world.porcelain.facts("canon", include_meta=True)
    assert len(with_meta) >= len(wide)
    # an exact receipt-chain target is always served
    rid = world.buffer.visible(attribute="in")[0].id
    world.ingest_structured([
        {"entity": rid, "attribute": "source", "value": "doc:log", "timeless": True}])
    chain = world.porcelain.facts("canon", entity=rid)
    assert chain and chain[0]["entity"] == rid


def test_facts_prefix_and_asof_and_json(world):
    places = world.porcelain.facts("canon", prefix="place:")
    assert {f["entity"] for f in places} <= {
        "place:yard", "place:street", "place:late_pier"}
    early = world.porcelain.facts("canon", prefix="place:", as_of=10.0)
    assert "place:late_pier" not in {f["entity"] for f in early}
    json.dumps(places)                       # plain-JSON contract holds


# ------------------------------------------- lean person.in (path check)

def test_lean_rules_carry_location_spine(world):
    assert "ALWAYS extract location changes" in _EXTRACT_RULES_LEAN


def test_lean_ingest_carries_departure_end_to_end(tmp_path):
    # a scripted model narrates a departure through the LEAN path; canon
    # presence must update (person-location is core state, not trimmable)
    def scripted(prompt, schema):
        if "PASSAGE:" in prompt:
            assert "ALWAYS extract location changes" in prompt   # lean block rode in
            return {"items": [
                {"entity": "person:maud", "attribute": "in", "value": "place:dark",
                 "value_type": "entity", "valid_from": 5.0},
            ]}
        return {"durability": "STATE", "class_confidence": 0.9}

    w = World(tmp_path / "lean.world", world_id="w:lean", model=scripted)
    try:
        w.ingest_structured([
            {"entity": "person:maud", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "place:inn", "attribute": "kind", "value": "place",
             "timeless": True},
            {"entity": "place:dark", "attribute": "kind", "value": "place",
             "timeless": True},
            {"entity": "person:maud", "attribute": "in", "value": "place:inn",
             "value_type": "entity", "valid_from": 1.0},
        ])
        w.porcelain.ingest("Maud steps out into the wet dark.", extract="lean",
                           classify="rules")
        assert w.locate("person:maud")[0] == "place:dark"    # presence moved
    finally:
        w.close()
