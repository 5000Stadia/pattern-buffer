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


def test_cross_frame_disagreement_is_conflicted_and_exactly_halved(world):
    # knows:olwe says frodo @5; public says bilbo @6 -> contested, and the
    # effective winner is the most-recent (bilbo @6).
    world.ingest_structured([
        {"entity": "obj:ring", "attribute": "bearer", "value": "frodo",
         "valid_from": 5.0, "frame": "knows:olwe"},
        {"entity": "obj:ring", "attribute": "bearer", "value": "bilbo",
         "valid_from": 6.0, "frame": "public"},
    ])
    union = world.confidence(
        "obj:ring", "bearer", frame=["knows:olwe", "public"], as_of=6.0
    )
    assert union["conflicted"] is True
    # the effective served value is bilbo (the freshest), with corroboration 0
    assert union["status"] == "stated"
    assert union["last_observed_at"] == 6.0
    assert union["corroboration"] == 0
    # exact halving: identical effective winner + corroboration read in a single
    # unconflicted frame (public alone) scores 2x the conflicted union.
    control = world.confidence("obj:ring", "bearer", frame="public", as_of=6.0)
    assert control["conflicted"] is False
    assert control["last_observed_at"] == 6.0
    assert union["score"] == pytest.approx(0.5 * control["score"])


def test_a_conflicting_frame_source_does_not_corroborate(world):
    # public agrees with the effective winner from a distinct source; knows:rk
    # backs a different value. Only the agreeing source corroborates.
    world.ingest_structured([
        {"entity": "obj:ring", "attribute": "bearer", "value": "bilbo",
         "valid_from": 6.0, "source_doc": "person:sam", "frame": "knows:olwe"},
        {"entity": "obj:ring", "attribute": "bearer", "value": "bilbo",
         "valid_from": 6.0, "source_doc": "person:rosie", "frame": "public"},
        {"entity": "obj:ring", "attribute": "bearer", "value": "gollum",
         "valid_from": 5.0, "source_doc": "person:liar", "frame": "knows:rk"},
    ])
    out = world.confidence(
        "obj:ring", "bearer", frame=["knows:olwe", "public", "knows:rk"], as_of=6.0
    )
    assert out["conflicted"] is True            # gollum disagrees with bilbo
    # sam + rosie attest bilbo (the served value); liar's gollum does NOT count
    assert out["corroboration"] == 1


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
    # TRACKING-MODE-V1 amendment: fiction recency is PERMANENT (the page is
    # true) — story-time age no longer changes trust, so both reads carry the
    # constant component; the freshest observation still selects the winner.
    assert union["recency"] == stale["recency"] == 1.0
    assert union["recency_status"] == stale["recency_status"] == "permanent"
    assert union["score"] == stale["score"]


_EMPTY = {"score": None, "status": None, "last_observed_at": None,
          "corroboration": 0, "conflicted": False,
          "recency": None, "recency_status": None,
          "last_confirmed_at_wallclock": None}


def test_absent_in_all_frames_is_empty(world):
    world.ingest_structured([
        {"entity": "obj:ring", "attribute": "bearer", "value": "frodo",
         "valid_from": 5.0, "frame": "knows:olwe"},
    ])
    out = world.confidence(
        "obj:ring", "bearer", frame=["knows:nobody", "knows:noone"], as_of=5.0
    )
    assert out == _EMPTY


def test_empty_frame_list_is_empty_not_canon(world):
    # a canon fact exists; an empty frame list names no knowledge and must NOT
    # fall through to a canon read (Codex post-impl finding 1).
    world.ingest_structured([
        {"entity": "obj:ring", "attribute": "bearer", "value": "frodo", "valid_from": 5.0},
    ])
    assert world.confidence("obj:ring", "bearer", frame=[], as_of=5.0) == _EMPTY
    # contrast: the canon str read does find it
    assert world.confidence("obj:ring", "bearer", as_of=5.0)["status"] == "stated"


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
    assert s == _EMPTY
    assert g == _EMPTY


def test_union_recency_branch_with_as_of_none(world):
    # exercises the as_of=None union-closure reference branch
    world.ingest_structured([
        {"entity": "obj:torch", "attribute": "state", "value": "lit",
         "valid_from": 1.0, "frame": "knows:olwe"},
        {"entity": "obj:torch", "attribute": "state", "value": "lit",
         "valid_from": 9.0, "frame": "public"},
    ])
    out = world.confidence("obj:torch", "state", frame=["knows:olwe", "public"])
    assert out["last_observed_at"] == 9.0      # freshest across frames
    assert out["score"] is not None            # no crash on the union ref


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
