"""WHO-KNOWS-INVERSE-V1: the computed "given fact X, who knows it" read.

The inverse of frame_diff — which `knows:*` observer frames know a fact. Computed
from the frames that exist (NO stored `known_by`); folded-not-raw so a superseded
or retracted belief no longer counts; identity-aware value matching.
"""

import json

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "wk.world", world_id="w:wk", model=stub)
    yield w
    w.close()


def test_who_knows_basic(world):
    # the culprit's identity is known to alice and bob, not carol
    world.ingest_structured([
        {"entity": "person:culprit", "attribute": "identity", "value": "the killer",
         "frame": "knows:alice", "valid_from": 1.0},
        {"entity": "person:culprit", "attribute": "identity", "value": "the killer",
         "frame": "knows:bob", "valid_from": 1.0},
    ])
    assert world.who_knows("person:culprit", "identity") == ["knows:alice", "knows:bob"]


def test_value_matching(world):
    # who believes the culprit IS ilsa, vs marn
    world.ingest_structured([
        {"entity": "person:culprit", "attribute": "is", "value": "person:ilsa",
         "value_type": "entity", "frame": "knows:alice", "valid_from": 1.0},
        {"entity": "person:culprit", "attribute": "is", "value": "person:marn",
         "value_type": "entity", "frame": "knows:bob", "valid_from": 1.0},
    ])
    assert world.who_knows("person:culprit", "is", "person:ilsa") == ["knows:alice"]
    assert world.who_knows("person:culprit", "is", "person:marn") == ["knows:bob"]
    assert world.who_knows("person:culprit", "is") == ["knows:alice", "knows:bob"]


def test_folded_not_raw_supersede_and_retract(world):
    # alice updates her belief; the old value no longer counts, the new one does
    world.ingest_structured([
        {"entity": "obj:cabinet", "attribute": "lock_status", "value": "locked",
         "frame": "knows:alice", "valid_from": 1.0},
        {"entity": "obj:cabinet", "attribute": "lock_status", "value": "open",
         "frame": "knows:alice", "valid_from": 5.0},
    ])
    assert world.who_knows("obj:cabinet", "lock_status", "open") == ["knows:alice"]
    assert world.who_knows("obj:cabinet", "lock_status", "locked") == []   # superseded
    # bob asserts then it is retracted -> bob no longer knows
    rows = world.ingest_structured([
        {"entity": "obj:cabinet", "attribute": "lock_status", "value": "locked",
         "frame": "knows:bob", "valid_from": 1.0},
    ])
    assert "knows:bob" in world.who_knows("obj:cabinet", "lock_status")
    world.truth.retract(rows[0], reason="bob was wrong")
    assert "knows:bob" not in world.who_knows("obj:cabinet", "lock_status")


def test_identity_aware_value_match(world):
    # alice believes culprit is person:i; later person:i merges with person:ilsa
    world.ingest_structured([
        {"entity": "person:culprit", "attribute": "is", "value": "person:i",
         "value_type": "entity", "frame": "knows:alice", "valid_from": 1.0},
        {"entity": "person:i", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:ilsa", "attribute": "kind", "value": "person", "timeless": True},
    ])
    world.registry.merge("person:i", "person:ilsa", evidence="same person")
    # querying by the merged id still matches alice's belief
    assert world.who_knows("person:culprit", "is", "person:ilsa") == ["knows:alice"]


def test_value_none_is_anyone_who_knows_the_key(world):
    world.ingest_structured([
        {"entity": "obj:safe", "attribute": "combination", "value": "12-34",
         "frame": "knows:alice", "valid_from": 1.0},
        {"entity": "obj:safe", "attribute": "combination", "value": "99-99",
         "frame": "knows:bob", "valid_from": 1.0},
    ])
    assert world.who_knows("obj:safe", "combination") == ["knows:alice", "knows:bob"]


def test_canon_and_nonknows_frames_excluded(world):
    # a canon fact + a named (non-knows) frame are NOT returned (V1 own-knows scope)
    world.ingest_structured([
        {"entity": "obj:door", "attribute": "state", "value": "shut", "valid_from": 1.0},  # canon
        {"entity": "obj:door", "attribute": "state", "value": "shut",
         "frame": "plot:main", "valid_from": 1.0},
        {"entity": "obj:door", "attribute": "state", "value": "shut",
         "frame": "knows:alice", "valid_from": 1.0},
    ])
    assert world.who_knows("obj:door", "state") == ["knows:alice"]


def test_who_knows_writes_nothing(world):
    world.ingest_structured([
        {"entity": "person:culprit", "attribute": "identity", "value": "x",
         "frame": "knows:alice", "valid_from": 1.0},
    ])
    head = world.buffer.head()
    json.dumps(world.porcelain.who_knows("person:culprit", "identity"))
    assert world.buffer.head() == head
