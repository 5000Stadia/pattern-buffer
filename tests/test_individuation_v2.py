"""MERGE-RECONCILE-VERB-V2: structure-first individuation.

The author individuates through structure; the engine preserves distinctness and
only auto-merges the obvious. distinct_from (anti-merge primitive) + sticky reject
+ precision-biased merger (relating-edge & non-distinctive-anchor downgrades).
"""

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "indiv.world", world_id="w:indiv", model=stub)
    yield w
    w.close()


def _R(w, e):
    return w.registry.resolve(e)


# ---- §1 distinct_from hard veto -------------------------------------------

def test_distinct_from_hard_vetoes_merge(world):
    world.ingest_structured([
        {"entity": "person:clay1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:clay2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:clay1", "attribute": "distinct_from", "value": "person:clay2"},
    ])
    rec = world.porcelain.merge("person:clay1", "person:clay2", evidence="gazetteer")
    assert rec["outcome"] == "vetoed"
    assert rec["reason"] == "distinct_from"
    assert "person:clay1·distinct_from·person:clay2" in rec["blocking_edges"]
    assert _R(world, "person:clay1") != _R(world, "person:clay2")


def test_reconcile_never_merges_or_reproposes_distinct_pair(world):
    world.ingest_structured([
        {"entity": "person:clay1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:clay1", "attribute": "name", "value": "Clay"},
        {"entity": "person:clay2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:clay2", "attribute": "name", "value": "Clay"},
        {"entity": "person:clay1", "attribute": "distinct_from", "value": "person:clay2"},
    ])
    world.registry.reconcile()
    assert _R(world, "person:clay1") != _R(world, "person:clay2")
    assert not world.registry._has_proposal("person:clay1", "person:clay2")


# ---- §2 sticky reject -----------------------------------------------------

def test_reject_writes_distinct_from_and_sticks(world):
    world.ingest_structured([
        {"entity": "person:clay1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:clay1", "attribute": "name", "value": "Clay"},
        {"entity": "person:clay2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:clay2", "attribute": "name", "value": "Clay"},
    ])
    rec = world.porcelain.reject("person:clay1", "person:clay2")
    assert rec["outcome"] == "rejected"
    again = world.porcelain.reject("person:clay1", "person:clay2")
    assert again["outcome"] == "noop_already_distinct"
    # sticky: reconcile won't merge or re-propose
    world.registry.reconcile()
    assert _R(world, "person:clay1") != _R(world, "person:clay2")
    assert not world.registry._has_proposal("person:clay1", "person:clay2")


def test_reject_on_already_merged_is_conflict_and_writes_nothing(world):
    world.ingest_structured([
        {"entity": "obj:a", "attribute": "kind", "value": "thing", "timeless": True},
        {"entity": "obj:b", "attribute": "kind", "value": "thing", "timeless": True},
    ])
    world.porcelain.merge("obj:a", "obj:b", evidence="same")
    head = world.buffer.head()
    rec = world.porcelain.reject("obj:a", "obj:b")
    assert rec["outcome"] == "conflict_already_merged"
    assert rec["blocking_edges"]                       # names the same_as / merge event
    assert world.buffer.head() == head                # wrote nothing


# ---- §3a relating-edge downgrade ------------------------------------------

def test_relating_edge_downgrades_to_proposal(world):
    # clay1 is clay2's father -> a relating edge -> they are distinct -> propose
    world.ingest_structured([
        {"entity": "person:clay1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:clay1", "attribute": "name", "value": "Clay"},
        {"entity": "person:clay2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:clay2", "attribute": "name", "value": "Clay"},
        {"entity": "person:clay1", "attribute": "father_of", "value": "person:clay2"},
    ])
    world.registry.reconcile()
    assert _R(world, "person:clay1") != _R(world, "person:clay2")     # not merged
    assert world.registry._has_proposal("person:clay1", "person:clay2")  # proposed


# ---- §3b non-distinctive anchor (the two bedrooms) ------------------------

def test_two_bedrooms_name_equals_kind_are_not_merged(world):
    world.ingest_structured([
        {"entity": "place:house", "attribute": "kind", "value": "building", "timeless": True},
        {"entity": "place:bedroom1", "attribute": "kind", "value": "bedroom", "timeless": True},
        {"entity": "place:bedroom1", "attribute": "name", "value": "bedroom"},
        {"entity": "place:bedroom1", "attribute": "in", "value": "place:house", "timeless": True},
        {"entity": "place:bedroom2", "attribute": "kind", "value": "bedroom", "timeless": True},
        {"entity": "place:bedroom2", "attribute": "name", "value": "bedroom"},
        {"entity": "place:bedroom2", "attribute": "in", "value": "place:house", "timeless": True},
    ])
    world.registry.reconcile()
    assert _R(world, "place:bedroom1") != _R(world, "place:bedroom2")   # name==kind -> not merged
    assert world.registry._has_proposal("place:bedroom1", "place:bedroom2")


# ---- recall preserved (precision didn't kill the obvious) -----------------

def test_distinctive_name_still_auto_merges(world):
    # one Frodo across chunks: distinctive name != kind, no relating edge -> merge
    world.ingest_structured([
        {"entity": "person:frodo_a", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:frodo_a", "attribute": "name", "value": "Frodo"},
        {"entity": "person:frodo_b", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:frodo_b", "attribute": "name", "value": "Frodo"},
    ])
    world.registry.reconcile()
    assert _R(world, "person:frodo_a") == _R(world, "person:frodo_b")


def test_core_x3_specific_alias_still_merges(world):
    world.ingest_structured([
        {"entity": "obj:mc1", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:mc1", "attribute": "alias", "value": "memory core"},
        {"entity": "obj:mc2", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:mc2", "attribute": "alias", "value": "memory core"},
    ])
    world.registry.reconcile()
    assert _R(world, "obj:mc1") == _R(world, "obj:mc2")


def test_reject_removes_a_preexisting_proposal_from_enumeration(world):
    # Codex post-impl: a maybe_same_as that existed BEFORE reject must not
    # re-surface in proposals() once the pair is settled distinct.
    world.ingest_structured([
        {"entity": "person:clay1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:clay2", "attribute": "kind", "value": "person", "timeless": True},
    ])
    world.registry.maybe_same_as("person:clay1", "person:clay2", evidence="seed")
    assert any({p["a"], p["b"]} == {"person:clay1", "person:clay2"}
               for p in world.porcelain.proposals())
    world.porcelain.reject("person:clay1", "person:clay2")
    assert not any({p["a"], p["b"]} == {"person:clay1", "person:clay2"}
                   for p in world.porcelain.proposals())


def test_identity_edges_do_not_materialize_as_facts(world):
    # Codex post-impl: same_as / distinct_from are machinery, never materialized
    # facts (membrane). Fixes a pre-existing same_as leak too.
    world.ingest_structured([
        {"entity": "obj:a", "attribute": "kind", "value": "thing", "timeless": True},
        {"entity": "obj:b", "attribute": "kind", "value": "thing", "timeless": True},
        {"entity": "obj:c", "attribute": "kind", "value": "thing", "timeless": True},
    ])
    world.porcelain.merge("obj:a", "obj:b", evidence="x")        # writes same_as
    world.porcelain.reject("obj:a", "obj:c")                     # writes distinct_from
    attrs = {a.attribute for a in world.materialize("obj:a", lens="current_state").assertions}
    assert "same_as" not in attrs
    assert "distinct_from" not in attrs
    assert "kind" in attrs                                       # real facts still served


def test_reject_appends_only_one_distinct_from_row(world):
    world.ingest_structured([
        {"entity": "person:clay1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:clay2", "attribute": "kind", "value": "person", "timeless": True},
    ])
    head = world.buffer.head()
    world.porcelain.reject("person:clay1", "person:clay2")
    new = [r for r in world.buffer.visible() if r.seq > head]
    assert len(new) == 1
    assert new[0].attribute == "distinct_from"
