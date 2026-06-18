"""MERGE-RECONCILE-VERB-V1: the host-reconciliation porcelain surface.

p.reconcile / p.proposals / p.confirm / p.merge over the guarded path:
containment veto absolute, soft heuristic host-overridable, receipts actionable.
"""

import json

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "verb.world", world_id="w:verb", model=stub)
    yield w
    w.close()


def _R(w, e):
    return w.registry.resolve(e)


def _seed_red(w):
    w.ingest_structured([
        {"entity": "person:p1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p1", "attribute": "alias", "value": "red"},
        {"entity": "person:p2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p2", "attribute": "alias", "value": "red"},
    ])


def test_reconcile_returns_merges_and_proposals(world):
    world.ingest_structured([
        {"entity": "obj:mc1", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:mc1", "attribute": "alias", "value": "memory core"},
        {"entity": "obj:mc2", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:mc2", "attribute": "alias", "value": "memory core"},
    ])
    _seed_red(world)
    r = world.porcelain.reconcile()
    assert r["merges"] >= 1                                  # mc1~mc2 merged
    pairs = {tuple(sorted((p["a"], p["b"]))) for p in r["proposals"]}
    assert (_R(world, "person:p1"), _R(world, "person:p2")) in {
        tuple(sorted(p)) for p in pairs
    } or any("p1" in p["a"] + p["b"] or "p2" in p["a"] + p["b"] for p in r["proposals"])


def test_proposal_reason_alias_not_specific(world):
    _seed_red(world)
    world.registry.maybe_same_as("person:p1", "person:p2", evidence="seed")
    props = world.porcelain.proposals()
    red = [p for p in props if {p["a"], p["b"]} == {"person:p1", "person:p2"}]
    assert red and red[0]["auto_decline_reason"] == "alias_not_specific"


def test_proposal_reason_kind_conflict_carries_pair(world):
    world.ingest_structured([
        {"entity": "obj:v", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:v", "attribute": "alias", "value": "records vault"},
        {"entity": "place:v", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:v", "attribute": "alias", "value": "records vault"},
    ])
    world.registry.maybe_same_as("obj:v", "place:v", evidence="seed")
    props = world.porcelain.proposals()
    pr = [p for p in props if {p["a"], p["b"]} == {"obj:v", "place:v"}][0]
    assert pr["auto_decline_reason"] == "kind_conflict: object↔place"


def test_kind_conflict_pair_surfaces_contested_set(world):
    # C-015: a contested kind side must not collapse to "contested" and hide a
    # same-kind (person↔person) overlap — a real confirm candidate.
    world.ingest_structured([
        {"entity": "person:tovan", "attribute": "kind", "value": "person", "valid_from": 1.0},
        {"entity": "person:tovan", "attribute": "kind", "value": "narrator", "valid_from": 1.0},
        {"entity": "person:tovan", "attribute": "alias", "value": "the chronicler"},
        {"entity": "person:tovan_voss", "attribute": "kind", "value": "person", "valid_from": 1.0},
        {"entity": "person:tovan_voss", "attribute": "alias", "value": "the chronicler"},
    ])
    world.registry.maybe_same_as("person:tovan", "person:tovan_voss", evidence="seed")
    props = world.porcelain.proposals()
    pr = [p for p in props if {p["a"], p["b"]} == {"person:tovan", "person:tovan_voss"}][0]
    assert pr["auto_decline_reason"] == "kind_conflict: narrator/person↔person"


def test_proposal_reason_containment(world):
    world.ingest_structured([
        {"entity": "obj:drawer", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:core", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:core", "attribute": "in", "value": "obj:drawer", "valid_from": 1.0},
    ])
    world.registry.maybe_same_as("obj:core", "obj:drawer", evidence="extractor")
    props = world.porcelain.proposals()
    pr = [p for p in props if {p["a"], p["b"]} == {"obj:core", "obj:drawer"}][0]
    assert pr["auto_decline_reason"] == "containment"


def test_confirm_merges_a_proposal(world):
    _seed_red(world)
    world.registry.maybe_same_as("person:p1", "person:p2", evidence="seed")
    rec = world.porcelain.confirm("person:p1", "person:p2")
    assert rec["outcome"] == "merged"
    assert rec["merge_event_id"] is not None
    assert _R(world, "person:p1") == _R(world, "person:p2")


def test_confirm_overrides_soft_heuristic(world):
    # the auto-gate declined "red" (alias_not_specific); the host confirm wins
    _seed_red(world)
    world.registry.maybe_same_as("person:p1", "person:p2", evidence="seed")
    assert world.registry._mergeable("person:p1", "person:p2") is False
    rec = world.porcelain.confirm("person:p1", "person:p2")
    assert rec["outcome"] == "merged"


def test_merge_asserts_without_a_proposal(world):
    world.ingest_structured([
        {"entity": "obj:a", "attribute": "kind", "value": "thing", "timeless": True},
        {"entity": "obj:b", "attribute": "kind", "value": "thing", "timeless": True},
    ])
    rec = world.porcelain.merge("obj:a", "obj:b", evidence="gazetteer")
    assert rec["outcome"] == "merged"
    assert _R(world, "obj:a") == _R(world, "obj:b")


def test_merge_idempotent_noop(world):
    world.ingest_structured([
        {"entity": "obj:a", "attribute": "kind", "value": "thing", "timeless": True},
        {"entity": "obj:b", "attribute": "kind", "value": "thing", "timeless": True},
    ])
    world.porcelain.merge("obj:a", "obj:b", evidence="first")
    rec = world.porcelain.merge("obj:a", "obj:b", evidence="again")
    assert rec["outcome"] == "noop_already_merged"
    assert rec["merge_event_id"] is None


def test_merge_vetoed_names_the_blocking_edge(world):
    world.ingest_structured([
        {"entity": "obj:drawer", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:core", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:core", "attribute": "in", "value": "obj:drawer", "valid_from": 1.0},
    ])
    rec = world.porcelain.merge("obj:core", "obj:drawer", evidence="bad late binding")
    assert rec["outcome"] == "vetoed"
    assert rec["reason"] == "containment"
    assert "obj:core·in·obj:drawer" in rec["blocking_edges"]
    assert _R(world, "obj:core") != _R(world, "obj:drawer")


def test_confirm_no_proposal_is_branchable(world):
    world.ingest_structured([
        {"entity": "obj:a", "attribute": "kind", "value": "thing", "timeless": True},
        {"entity": "obj:b", "attribute": "kind", "value": "thing", "timeless": True},
    ])
    rec = world.porcelain.confirm("obj:a", "obj:b")
    assert rec["outcome"] == "no_proposal"
    assert _R(world, "obj:a") != _R(world, "obj:b")


def test_confirm_already_merged_is_noop_not_no_proposal(world):
    # Codex post-impl: an already-merged pair (even with a stale proposal row)
    # is noop_already_merged, the truthful outcome — never no_proposal.
    _seed_red(world)
    world.registry.maybe_same_as("person:p1", "person:p2", evidence="seed")
    assert world.porcelain.confirm("person:p1", "person:p2")["outcome"] == "merged"
    rec = world.porcelain.confirm("person:p1", "person:p2")   # the stale proposal lingers
    assert rec["outcome"] == "noop_already_merged"


def test_enumerate_skips_a_proposal_that_since_merged(world):
    # stale-skip + dedup: once a proposal merges, it drops from the residue
    world.ingest_structured([
        {"entity": "obj:a", "attribute": "kind", "value": "thing", "timeless": True},
        {"entity": "obj:b", "attribute": "kind", "value": "thing", "timeless": True},
    ])
    world.registry.maybe_same_as("obj:a", "obj:b", evidence="seed")
    assert any({p["a"], p["b"]} == {"obj:a", "obj:b"} for p in world.porcelain.proposals())
    world.porcelain.confirm("obj:a", "obj:b")
    assert not any({p["a"], p["b"]} == {"obj:a", "obj:b"}
                   for p in world.porcelain.proposals())


def test_receipts_and_proposals_are_json(world):
    _seed_red(world)
    world.registry.maybe_same_as("person:p1", "person:p2", evidence="seed")
    json.dumps(world.porcelain.reconcile())
    json.dumps(world.porcelain.proposals())
    json.dumps(world.porcelain.merge("person:p1", "person:p2", evidence="x"))
    json.dumps(world.porcelain.confirm("person:p1", "person:p2"))
