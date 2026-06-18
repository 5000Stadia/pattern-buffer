"""TRIAGE-CONTEXT-V1: structured auto_decline context on proposals.

The engine surfaces structure (code + kinds + the decisive related_rows +
candidate_bindings); the host supplies meaning. Read-side only.
"""

import json

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "triage.world", world_id="w:triage", model=stub)
    yield w
    w.close()


def _ctx(w, a, b):
    for p in w.porcelain.proposals():
        if {p["a"], p["b"]} == {a, b}:
            return p
    return None


def test_code_containment(world):
    world.ingest_structured([
        {"entity": "obj:drawer", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:core", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:core", "attribute": "in", "value": "obj:drawer", "valid_from": 1.0},
    ])
    world.registry.maybe_same_as("obj:core", "obj:drawer", evidence="x")
    p = _ctx(world, "obj:core", "obj:drawer")
    assert p["auto_decline"]["code"] == "containment"
    rr = p["auto_decline"]["related_rows"]
    assert any(r["attribute"] == "in" and r["relation_family"] == "containment" for r in rr)


def test_code_relating_edge_with_family_none(world):
    world.ingest_structured([
        {"entity": "person:clay1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:clay1", "attribute": "name", "value": "Clay"},
        {"entity": "person:clay2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:clay2", "attribute": "name", "value": "Clay"},
        {"entity": "person:clay1", "attribute": "father_of", "value": "person:clay2"},
    ])
    world.registry.maybe_same_as("person:clay1", "person:clay2", evidence="x")
    p = _ctx(world, "person:clay1", "person:clay2")
    assert p["auto_decline"]["code"] == "relating_edge"
    assert p["auto_decline_reason"] == "relating_edge: father_of"
    rr = p["auto_decline"]["related_rows"]
    assert any(r["attribute"] == "father_of" and r["relation_family"] == "none" for r in rr)


def test_overlap_priority_relating_edge_beats_kind_conflict(world):
    # both a relating edge AND a kind conflict -> earlier gate (relating_edge) wins
    world.ingest_structured([
        {"entity": "person:clay1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:clay1", "attribute": "name", "value": "Clay"},
        {"entity": "obj:clay2", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:clay2", "attribute": "name", "value": "Clay"},
        {"entity": "person:clay1", "attribute": "father_of", "value": "obj:clay2"},
    ])
    world.registry.maybe_same_as("person:clay1", "obj:clay2", evidence="x")
    assert _ctx(world, "person:clay1", "obj:clay2")["auto_decline"]["code"] == "relating_edge"


def test_code_kind_conflict_carries_kinds(world):
    world.ingest_structured([
        {"entity": "obj:v", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:v", "attribute": "alias", "value": "records vault"},
        {"entity": "place:v", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:v", "attribute": "alias", "value": "records vault"},
    ])
    world.registry.maybe_same_as("obj:v", "place:v", evidence="x")
    p = _ctx(world, "obj:v", "place:v")
    assert p["auto_decline"]["code"] == "kind_conflict"
    kinds = {k["entity"]: k["value"] for k in p["auto_decline"]["kinds"]}
    assert kinds == {"obj:v": "object", "place:v": "place"}


def test_code_non_distinctive(world):
    world.ingest_structured([
        {"entity": "place:bedroom1", "attribute": "kind", "value": "bedroom", "timeless": True},
        {"entity": "place:bedroom1", "attribute": "name", "value": "bedroom"},
        {"entity": "place:bedroom2", "attribute": "kind", "value": "bedroom", "timeless": True},
        {"entity": "place:bedroom2", "attribute": "name", "value": "bedroom"},
    ])
    world.registry.maybe_same_as("place:bedroom1", "place:bedroom2", evidence="x")
    assert _ctx(world, "place:bedroom1", "place:bedroom2")["auto_decline"]["code"] == "non_distinctive"


def test_code_alias_not_specific(world):
    world.ingest_structured([
        {"entity": "person:p1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p1", "attribute": "alias", "value": "red"},
        {"entity": "person:p2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p2", "attribute": "alias", "value": "red"},
    ])
    world.registry.maybe_same_as("person:p1", "person:p2", evidence="x")
    assert _ctx(world, "person:p1", "person:p2")["auto_decline"]["code"] == "alias_not_specific"


def test_code_kind_absent(world):
    world.ingest_structured([
        {"entity": "obj:k1", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:k1", "attribute": "alias", "value": "memory core"},
        {"entity": "obj:k2", "attribute": "alias", "value": "memory core"},   # no kind
    ])
    world.registry.maybe_same_as("obj:k1", "obj:k2", evidence="x")
    assert _ctx(world, "obj:k1", "obj:k2")["auto_decline"]["code"] == "kind_absent"


def test_code_no_shared_anchor(world):
    world.ingest_structured([
        {"entity": "obj:x", "attribute": "kind", "value": "thing", "timeless": True},
        {"entity": "obj:x", "attribute": "name", "value": "Apple"},
        {"entity": "obj:y", "attribute": "kind", "value": "thing", "timeless": True},
        {"entity": "obj:y", "attribute": "name", "value": "Banana"},
    ])
    world.registry.maybe_same_as("obj:x", "obj:y", evidence="byother")
    assert _ctx(world, "obj:x", "obj:y")["auto_decline"]["code"] == "no_shared_anchor"


def test_kinds_conflicted_flag(world):
    world.ingest_structured([
        {"entity": "person:tovan", "attribute": "kind", "value": "person", "valid_from": 1.0},
        {"entity": "person:tovan", "attribute": "kind", "value": "narrator", "valid_from": 1.0},
        {"entity": "person:tovan", "attribute": "alias", "value": "the chronicler"},
        {"entity": "person:voss", "attribute": "kind", "value": "person", "valid_from": 1.0},
        {"entity": "person:voss", "attribute": "alias", "value": "the chronicler"},
    ])
    world.registry.maybe_same_as("person:tovan", "person:voss", evidence="x")
    p = _ctx(world, "person:tovan", "person:voss")
    flags = {k["entity"]: k["conflicted"] for k in p["auto_decline"]["kinds"]}
    assert flags["person:tovan"] is True
    assert flags["person:voss"] is False


def test_candidate_bindings_plural(world):
    world.ingest_structured([
        {"entity": "person:p1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p2", "attribute": "kind", "value": "person", "timeless": True},
    ])
    world.registry.maybe_same_as("person:p1", "person:p2", evidence="one")
    world.registry.maybe_same_as("person:p2", "person:p1", evidence="two")
    p = _ctx(world, "person:p1", "person:p2")
    assert len(p["auto_decline"]["candidate_bindings"]) == 2


def test_would_merge_pair_has_code_none(world):
    # Codex post-impl: a live maybe_same_as on a pair that WOULD auto-merge
    # (distinctive single-token name, same kind) must read code None, not a
    # false alias_not_specific.
    world.ingest_structured([
        {"entity": "person:b1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:b1", "attribute": "name", "value": "Bob"},
        {"entity": "person:b2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:b2", "attribute": "name", "value": "Bob"},
    ])
    world.registry.maybe_same_as("person:b1", "person:b2", evidence="x")
    p = _ctx(world, "person:b1", "person:b2")
    assert p["auto_decline"]["code"] is None
    assert p["auto_decline_reason"] is None


def test_proposals_are_json_serializable(world):
    world.ingest_structured([
        {"entity": "obj:k1", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:k1", "attribute": "alias", "value": "memory core"},
        {"entity": "obj:k2", "attribute": "alias", "value": "memory core"},
    ])
    world.registry.maybe_same_as("obj:k1", "obj:k2", evidence="x")
    head = world.buffer.head()
    json.dumps(world.porcelain.proposals())
    assert world.buffer.head() == head                 # membrane: read writes nothing
