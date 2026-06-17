"""CONFIDENCE-MULTIFRAME-V1: confidence over an observer's effective knowledge.

`frame` accepts a list: trust over the read-union of those frames
(`knows:O ∪ public`), mirroring multi-frame `frame_diff`. Derived, never
stored. A deduped single-frame list reduces to the str path byte-for-byte.
"""

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "cmf.world", world_id="w:cmf", model=stub)
    yield w
    w.close()


def test_single_frame_list_reduces_to_str_path(world):
    world.ingest_structured([
        {"entity": "obj:ring", "attribute": "bearer", "value": "frodo",
         "valid_from": 5.0, "frame": "knows:olwe"},
    ])
    as_list = world.confidence("obj:ring", "bearer", frame=["knows:olwe"], as_of=5.0)
    as_str = world.confidence("obj:ring", "bearer", frame="knows:olwe", as_of=5.0)
    assert as_list == as_str
    # a duplicate-laden list collapses to the same single frame
    dup = world.confidence("obj:ring", "bearer", frame=["knows:olwe", "knows:olwe"], as_of=5.0)
    assert dup == as_str


def test_cross_frame_agreement_corroborates_and_lifts_score(world):
    # the same value, held privately AND seen publicly from distinct sources
    world.ingest_structured([
        {"entity": "obj:ring", "attribute": "bearer", "value": "frodo",
         "valid_from": 5.0, "source_doc": "person:olwe", "frame": "knows:olwe"},
        {"entity": "obj:ring", "attribute": "bearer", "value": "frodo",
         "valid_from": 5.0, "source_doc": "person:crowd", "frame": "public"},
    ])
    single = world.confidence("obj:ring", "bearer", frame="knows:olwe", as_of=5.0)
    union = world.confidence(
        "obj:ring", "bearer", frame=["knows:olwe", "public"], as_of=5.0
    )
    assert single["corroboration"] == 0
    assert union["corroboration"] >= 1            # the public source corroborates
    assert union["conflicted"] is False
    assert union["score"] > single["score"]       # agreement raises trust


def test_cross_frame_disagreement_is_conflicted_and_halved(world):
    world.ingest_structured([
        {"entity": "obj:ring", "attribute": "bearer", "value": "frodo",
         "valid_from": 5.0, "frame": "knows:olwe"},
        {"entity": "obj:ring", "attribute": "bearer", "value": "bilbo",
         "valid_from": 5.0, "frame": "public"},
    ])
    union = world.confidence(
        "obj:ring", "bearer", frame=["knows:olwe", "public"], as_of=5.0
    )
    # the private belief and the public claim disagree -> a contested belief
    assert union["conflicted"] is True
    # halving: strictly below the same key read in a single, unconflicted frame
    single = world.confidence("obj:ring", "bearer", frame="knows:olwe", as_of=5.0)
    assert single["conflicted"] is False
    assert union["score"] < single["score"]


def test_union_recency_uses_the_freshest_observation(world):
    # private belief is stale; the public frame refreshed it recently
    world.ingest_structured([
        {"entity": "obj:torch", "attribute": "state", "value": "lit",
         "valid_from": 1.0, "frame": "knows:olwe"},
        {"entity": "obj:torch", "attribute": "state", "value": "lit",
         "valid_from": 50.0, "frame": "public"},
    ])
    union = world.confidence(
        "obj:torch", "state", frame=["knows:olwe", "public"], as_of=50.0
    )
    stale = world.confidence("obj:torch", "state", frame="knows:olwe", as_of=50.0)
    # effective winner is the freshest observation across frames
    assert union["last_observed_at"] == 50.0
    assert stale["last_observed_at"] == 1.0
    assert union["score"] > stale["score"]        # recency lifts the union


def test_absent_in_all_frames_is_empty(world):
    world.ingest_structured([
        {"entity": "obj:ring", "attribute": "bearer", "value": "frodo",
         "valid_from": 5.0, "frame": "knows:olwe"},
    ])
    out = world.confidence(
        "obj:ring", "bearer", frame=["knows:nobody", "knows:noone"], as_of=5.0
    )
    assert out["score"] is None
    assert out["status"] is None


def test_set_and_accrue_keys_return_none_under_a_frame_list(world):
    world.ingest_structured([
        {"entity": "attr:carries", "attribute": "arity", "value": "set_valued", "timeless": True},
        {"entity": "attr:gold", "attribute": "fold_policy", "value": "accrue", "timeless": True},
        {"entity": "person:olwe", "attribute": "carries", "value": "torch",
         "valid_from": 1.0, "frame": "knows:olwe"},
        {"entity": "person:olwe", "attribute": "gold", "value": 10,
         "valid_from": 1.0, "frame": "knows:olwe"},
    ])
    s = world.confidence("person:olwe", "carries", frame=["knows:olwe", "public"], as_of=1.0)
    g = world.confidence("person:olwe", "gold", frame=["knows:olwe", "public"], as_of=1.0)
    assert s["score"] is None
    assert g["score"] is None


def test_multiframe_read_writes_nothing(world):
    world.ingest_structured([
        {"entity": "obj:ring", "attribute": "bearer", "value": "frodo",
         "valid_from": 5.0, "frame": "knows:olwe"},
        {"entity": "obj:ring", "attribute": "bearer", "value": "frodo",
         "valid_from": 5.0, "frame": "public"},
    ])
    head = world.buffer.head()
    world.confidence("obj:ring", "bearer", frame=["knows:olwe", "public"], as_of=5.0)
    assert world.buffer.head() == head
