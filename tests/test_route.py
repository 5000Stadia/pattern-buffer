"""RFC-003: passability-aware route() — traversability derived from portal facts.

clear|blocked|obscured derived under a host-declared, portal-scoped traversal
policy; removed is temporal/diagnostic. Engine surfaces structure + status; host
supplies the words. Nothing stored.
"""

import json

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "route.world", world_id="w:route", model=stub)
    yield w
    w.close()


def _door_policy(w):
    # host-declared traversal policy, scoped to kind=door
    w.ingest_structured([
        {"entity": "traversal:door", "attribute": "blocks_when_state", "value": "shut", "timeless": True},
        {"entity": "traversal:door", "attribute": "blocks_when_state", "value": "locked", "timeless": True},
        {"entity": "traversal:door", "attribute": "blocks_when_relation", "value": "guarded_by", "timeless": True},
    ])


def _link(a, b):
    return {"entity": a, "attribute": "connects_to", "value": b, "timeless": True}


def test_clear_when_door_open(world):
    _door_policy(world)
    world.ingest_structured([
        {"entity": "obj:door1", "attribute": "kind", "value": "door", "timeless": True},
        {"entity": "obj:door1", "attribute": "state", "value": "open", "valid_from": 1.0},
        _link("place:a", "obj:door1"), _link("obj:door1", "place:b"),
    ])
    r = world.route("place:a", "place:b")
    assert r["status"] == "clear"
    assert r["route"] == ["place:a", "obj:door1", "place:b"]


def test_blocked_by_state(world):
    _door_policy(world)
    world.ingest_structured([
        {"entity": "obj:door1", "attribute": "kind", "value": "door", "timeless": True},
        {"entity": "obj:door1", "attribute": "state", "value": "shut", "valid_from": 1.0},
        _link("place:a", "obj:door1"), _link("obj:door1", "place:b"),
    ])
    r = world.route("place:a", "place:b")
    assert r["status"] == "blocked"
    assert r["route"] == ["place:a", "obj:door1", "place:b"]   # not no_path
    seg = next(s for s in r["segments"] if s["node"] == "obj:door1")
    assert seg["status"] == "blocked"
    assert any(e["attribute"] == "state" and e["value"] == "shut" for e in seg["evidence"])


def test_blocked_by_relation_guard(world):
    _door_policy(world)
    world.ingest_structured([
        {"entity": "obj:door1", "attribute": "kind", "value": "door", "timeless": True},
        {"entity": "obj:door1", "attribute": "state", "value": "open", "valid_from": 1.0},
        {"entity": "person:bjorn", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "obj:door1", "attribute": "guarded_by", "value": "person:bjorn", "valid_from": 1.0},
        _link("place:a", "obj:door1"), _link("obj:door1", "place:b"),
    ])
    r = world.route("place:a", "place:b")
    assert r["status"] == "blocked"
    seg = next(s for s in r["segments"] if s["node"] == "obj:door1")
    assert any(e["attribute"] == "guarded_by" and e["value"] == "person:bjorn" for e in seg["evidence"])


def test_obscured_when_gating_door_has_no_state(world):
    _door_policy(world)
    world.ingest_structured([
        {"entity": "obj:door1", "attribute": "kind", "value": "door", "timeless": True},
        _link("place:a", "obj:door1"), _link("obj:door1", "place:b"),
    ])
    r = world.route("place:a", "place:b")
    assert r["status"] == "obscured"
    seg = next(s for s in r["segments"] if s["node"] == "obj:door1")
    assert seg["unknown_basis"]["kind"] == "relational_absence"
    assert seg["unknown_basis"]["required_attribute"] == "state"


def test_no_policy_no_guess_is_clear(world):
    # a stateless portal with NO declared traversal policy -> engine does not
    # guess obscured; it's clear (no false-clear burden without a policy)
    world.ingest_structured([
        {"entity": "obj:arch", "attribute": "kind", "value": "archway", "timeless": True},
        _link("place:a", "obj:arch"), _link("obj:arch", "place:b"),
    ])
    assert world.route("place:a", "place:b")["status"] == "clear"


def test_clear_route_preferred_over_blocked(world):
    _door_policy(world)
    world.ingest_structured([
        {"entity": "obj:door1", "attribute": "kind", "value": "door", "timeless": True},
        {"entity": "obj:door1", "attribute": "state", "value": "shut", "valid_from": 1.0},
        _link("place:a", "obj:door1"), _link("obj:door1", "place:b"),
        # an alternate clear way (a plain hallway, no gating policy)
        {"entity": "place:hall", "attribute": "kind", "value": "hallway", "timeless": True},
        _link("place:a", "place:hall"), _link("place:hall", "place:b"),
    ])
    r = world.route("place:a", "place:b")
    assert r["status"] == "clear"
    assert "place:hall" in r["route"] and "obj:door1" not in r["route"]


def test_no_path_surfaces_former_passages(world):
    _door_policy(world)
    world.ingest_structured([
        # a passage that died at t=5 and no other connection
        {"entity": "place:a", "attribute": "connects_to", "value": "place:b",
         "valid_from": 1.0, "valid_to": 5.0},
    ])
    r = world.route("place:a", "place:b", valid_as_of=10.0)
    assert r["status"] == "no_path"
    assert r["route"] is None
    assert any(fp["valid_to"] == 5.0 for fp in r["former_passages"])
    # before the breach, it routes (porcelain as_of -> valid_as_of)
    assert world.porcelain.route("place:a", "place:b", as_of=3.0)["status"] == "clear"


def test_destination_portal_blocked_is_not_clear(world):
    # Cx final review #1: a clear route requires clear endpoints — routing TO a
    # shut door must read blocked, not clear.
    _door_policy(world)
    world.ingest_structured([
        {"entity": "obj:door1", "attribute": "kind", "value": "door", "timeless": True},
        {"entity": "obj:door1", "attribute": "state", "value": "shut", "valid_from": 1.0},
        _link("place:a", "obj:door1"),
    ])
    r = world.route("place:a", "obj:door1")
    assert r["status"] == "blocked"
    assert r["route"] == ["place:a", "obj:door1"]


def test_unrelated_traversal_metadata_is_not_gating(world):
    # Cx final review #3: a traversal:<kind> entity with only non-policy metadata
    # is NOT a gating policy; a stateless portal of that kind stays clear.
    world.ingest_structured([
        {"entity": "traversal:archway", "attribute": "note", "value": "decorative", "timeless": True},
        {"entity": "obj:arch", "attribute": "kind", "value": "archway", "timeless": True},
        _link("place:a", "obj:arch"), _link("obj:arch", "place:b"),
    ])
    assert world.route("place:a", "place:b")["status"] == "clear"


def test_future_edge_is_not_a_former_passage(world):
    # Cx final review #2: an edge valid in the future must not be reported as a
    # former passage at an earlier as-of.
    world.ingest_structured([
        {"entity": "place:a", "attribute": "connects_to", "value": "place:b",
         "valid_from": 10.0, "valid_to": 20.0},
    ])
    r = world.route("place:a", "place:b", valid_as_of=5.0)
    assert r["status"] == "no_path"
    assert r["former_passages"] == []        # valid_to=20 is not <= as_of=5


def test_route_to_self_reflects_node_status(world):
    # Cx final review: a==b must reflect the node's own status, never a forced clear
    _door_policy(world)
    world.ingest_structured([
        {"entity": "obj:door1", "attribute": "kind", "value": "door", "timeless": True},
        {"entity": "obj:door1", "attribute": "state", "value": "shut", "valid_from": 1.0},
    ])
    assert world.route("obj:door1", "obj:door1")["status"] == "blocked"
    # a plain place to itself is clear
    world.ingest_structured([{"entity": "place:x", "attribute": "kind", "value": "room", "timeless": True}])
    assert world.route("place:x", "place:x")["status"] == "clear"


def test_route_writes_nothing(world):
    _door_policy(world)
    world.ingest_structured([
        {"entity": "obj:door1", "attribute": "kind", "value": "door", "timeless": True},
        {"entity": "obj:door1", "attribute": "state", "value": "shut", "valid_from": 1.0},
        _link("place:a", "obj:door1"), _link("obj:door1", "place:b"),
    ])
    head = world.buffer.head()
    json.dumps(world.porcelain.route("place:a", "place:b"))
    assert world.buffer.head() == head
