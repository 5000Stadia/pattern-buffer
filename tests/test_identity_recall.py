"""IDENTITY-RECALL-V1: global coreference finalize pass (reconcile()).

Raise recall (merge true cross-chunk coreferents) without dropping precision
(casual shared aliases must not fuse). One unified gate; proper-name merges
preserved; alias merges require specificity + equal kind; containment vetoed.
"""

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "recall.world", world_id="w:recall", model=stub)
    yield w
    w.close()


def _R(w, e):
    return w.registry.resolve(e)


def test_recall_merges_core_x3_specific_alias_same_kind(world):
    # the headline case: three closures for one object, never co-occurring
    world.ingest_structured([
        {"entity": "obj:mc1", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:mc1", "attribute": "alias", "value": "memory core"},
        {"entity": "obj:mc2", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:mc2", "attribute": "alias", "value": "memory core"},
        {"entity": "obj:mc3", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:mc3", "attribute": "alias", "value": "memory core"},
    ])
    world.registry.reconcile()
    assert _R(world, "obj:mc1") == _R(world, "obj:mc2") == _R(world, "obj:mc3")


def test_casual_single_token_alias_proposes_not_merges(world):
    world.ingest_structured([
        {"entity": "person:p1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p1", "attribute": "alias", "value": "red"},
        {"entity": "person:p2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p2", "attribute": "alias", "value": "red"},
    ])
    world.registry.reconcile()
    assert _R(world, "person:p1") != _R(world, "person:p2")
    assert world.registry._has_proposal("person:p1", "person:p2")


def test_the_core_one_content_token_proposes(world):
    world.ingest_structured([
        {"entity": "obj:x1", "attribute": "kind", "value": "thing", "timeless": True},
        {"entity": "obj:x1", "attribute": "alias", "value": "the core"},
        {"entity": "obj:x2", "attribute": "kind", "value": "thing", "timeless": True},
        {"entity": "obj:x2", "attribute": "alias", "value": "the core"},
    ])
    world.registry.reconcile()
    assert _R(world, "obj:x1") != _R(world, "obj:x2")     # "the core" -> 1 content token
    assert world.registry._has_proposal("obj:x1", "obj:x2")


def test_containment_vetoes_even_specific_alias(world):
    world.ingest_structured([
        {"entity": "obj:drawer", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:core3", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:core3", "attribute": "in", "value": "obj:drawer", "valid_from": 1.0},
        {"entity": "obj:drawer", "attribute": "alias", "value": "memory core"},
        {"entity": "obj:core3", "attribute": "alias", "value": "memory core"},
    ])
    world.registry.reconcile()
    assert _R(world, "obj:drawer") != _R(world, "obj:core3")


def test_kind_conflict_different_values_blocks(world):
    world.ingest_structured([
        {"entity": "obj:a", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:a", "attribute": "alias", "value": "memory core"},
        {"entity": "obj:b", "attribute": "kind", "value": "drawer", "timeless": True},
        {"entity": "obj:b", "attribute": "alias", "value": "memory core"},
    ])
    world.registry.reconcile()
    assert _R(world, "obj:a") != _R(world, "obj:b")


def test_conflicted_kind_fold_blocks(world):
    # two kind values at the same valid_from -> conflicted fold -> not a basis
    world.ingest_structured([
        {"entity": "obj:cf", "attribute": "kind", "value": "core", "valid_from": 1.0},
        {"entity": "obj:cf", "attribute": "kind", "value": "relic", "valid_from": 1.0},
        {"entity": "obj:cf", "attribute": "alias", "value": "memory core"},
        {"entity": "obj:cf2", "attribute": "kind", "value": "core", "valid_from": 1.0},
        {"entity": "obj:cf2", "attribute": "alias", "value": "memory core"},
    ])
    assert world.state("obj:cf", "kind").conflicted is True
    world.registry.reconcile()
    assert _R(world, "obj:cf") != _R(world, "obj:cf2")


def test_alias_kind_absent_proposes(world):
    world.ingest_structured([
        {"entity": "obj:k1", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:k1", "attribute": "alias", "value": "memory core"},
        {"entity": "obj:k2", "attribute": "alias", "value": "memory core"},  # no kind
    ])
    world.registry.reconcile()
    assert _R(world, "obj:k1") != _R(world, "obj:k2")
    assert world.registry._has_proposal("obj:k1", "obj:k2")


def test_proper_name_merges_kind_present(world):
    world.ingest_structured([
        {"entity": "person:f1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:f1", "attribute": "name", "value": "Frodo"},
        {"entity": "person:f2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:f2", "attribute": "name", "value": "Frodo"},
    ])
    world.registry.reconcile()
    assert _R(world, "person:f1") == _R(world, "person:f2")


def test_proper_name_merges_kind_absent(world):
    # single-token name, neither has kind, no conflict -> merge (no regression)
    world.ingest_structured([
        {"entity": "person:g1", "attribute": "name", "value": "Gandalf"},
        {"entity": "person:g2", "attribute": "name", "value": "Gandalf"},
    ])
    world.registry.reconcile()
    assert _R(world, "person:g1") == _R(world, "person:g2")


def test_cross_type_name_alias_same_text_merges(world):
    # name:"Alice" vs alias:"Alice" -> name-strength -> merge (Codex r3)
    world.ingest_structured([
        {"entity": "person:a1", "attribute": "name", "value": "Alice"},
        {"entity": "person:a2", "attribute": "alias", "value": "Alice"},
    ])
    world.registry.reconcile()
    assert _R(world, "person:a1") == _R(world, "person:a2")


def test_proposed_casual_pair_not_promoted_on_second_cycle(world):
    world.ingest_structured([
        {"entity": "person:p1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p1", "attribute": "alias", "value": "red"},
        {"entity": "person:p2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p2", "attribute": "alias", "value": "red"},
    ])
    world.registry.reconcile()
    # non-vacuous: the proposal must actually exist before the second cycle
    assert world.registry._has_proposal("person:p1", "person:p2")
    world.registry.promote_identity_proposals()      # the second cycle
    assert _R(world, "person:p1") != _R(world, "person:p2")


def test_entity_valued_kind_resolves_through_identity(world):
    # two objects whose kind VALUES are entities that later merge: their kinds
    # are then the same, so a shared specific alias should merge them (Codex
    # post-impl finding 1).
    world.ingest_structured([
        {"entity": "obj:r1", "attribute": "kind", "value": "kind:robot_a"},
        {"entity": "obj:r1", "attribute": "alias", "value": "memory core"},
        {"entity": "obj:r2", "attribute": "kind", "value": "kind:robot_b"},
        {"entity": "obj:r2", "attribute": "alias", "value": "memory core"},
    ])
    # kinds differ as raw ids -> would conflict -> no merge yet
    world.registry.reconcile()
    assert _R(world, "obj:r1") != _R(world, "obj:r2")
    # merge the kind entities; now the two objects share one kind
    world.registry.merge("kind:robot_a", "kind:robot_b", evidence="same model")
    world.registry.reconcile()
    assert _R(world, "obj:r1") == _R(world, "obj:r2")


def test_reconcile_writes_only_identity_machinery(world):
    # membrane: reconcile appends merge events / proposals (log evidence), never
    # derived facts.
    world.ingest_structured([
        {"entity": "obj:mc1", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:mc1", "attribute": "alias", "value": "memory core"},
        {"entity": "obj:mc2", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:mc2", "attribute": "alias", "value": "memory core"},
        {"entity": "person:p1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p1", "attribute": "alias", "value": "red"},
        {"entity": "person:p2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p2", "attribute": "alias", "value": "red"},
    ])
    head = world.buffer.head()
    world.registry.reconcile()
    allowed = {"same_as", "maybe_same_as", "kind", "evidence", "caused_by"}
    new_rows = [r for r in world.buffer.visible() if r.seq > head]
    assert new_rows  # it did something
    assert all(r.attribute in allowed for r in new_rows)
    # the only "kind" rows written are identity_merge event markers
    assert all(r.value == "identity_merge" for r in new_rows if r.attribute == "kind")


def test_reconcile_is_idempotent(world):
    world.ingest_structured([
        {"entity": "obj:mc1", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:mc1", "attribute": "alias", "value": "memory core"},
        {"entity": "obj:mc2", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:mc2", "attribute": "alias", "value": "memory core"},
        {"entity": "person:p1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p1", "attribute": "alias", "value": "red"},
        {"entity": "person:p2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p2", "attribute": "alias", "value": "red"},
    ])
    world.registry.reconcile()
    head = world.buffer.head()
    again = world.registry.reconcile()
    assert again == 0
    assert world.buffer.head() == head               # zero appends (no dup merges/proposals)
