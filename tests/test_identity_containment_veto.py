"""Containment veto on identity merge (Construct finding 010).

A container is never identical to its contents: a visible in/contains/holds
edge between two entities is a hard bar to merging them. The veto lives at
merge() (non-bypassable) and promote_identity_proposals() consults it.
"""

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "idveto.world", world_id="w:idveto", model=stub)
    yield w
    w.close()


def test_direct_merge_is_vetoed_when_containment_relates(world):
    # the 010 repro: a core located IN a drawer must never fuse with the drawer
    world.ingest_structured([
        {"entity": "obj:drawer", "attribute": "kind", "value": "drawer", "timeless": True},
        {"entity": "obj:core", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:core", "attribute": "in", "value": "obj:drawer", "valid_from": 1.0},
    ])
    ev = world.registry.merge("obj:core", "obj:drawer", evidence="extractor late binding")
    assert ev is None                                          # vetoed, no merge event
    assert world.registry.resolve("obj:drawer") == "obj:drawer"
    assert world.registry.resolve("obj:core") == "obj:core"   # still distinct


def test_veto_holds_in_either_direction(world):
    # container->contents edge direction must not matter
    world.ingest_structured([
        {"entity": "obj:box", "attribute": "kind", "value": "box", "timeless": True},
        {"entity": "obj:gem", "attribute": "kind", "value": "gem", "timeless": True},
        {"entity": "obj:gem", "attribute": "in", "value": "obj:box", "valid_from": 1.0},
    ])
    assert world.registry.merge("obj:box", "obj:gem", evidence="reverse order") is None


def test_legitimate_coreference_merge_still_works(world):
    # two aliases of one object, no containment edge between them -> merges
    world.ingest_structured([
        {"entity": "obj:core", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:core_alias", "attribute": "kind", "value": "core", "timeless": True},
    ])
    ev = world.registry.merge("obj:core", "obj:core_alias", evidence="true coref")
    assert ev is not None
    assert world.registry.resolve("obj:core") == world.registry.resolve("obj:core_alias")


def test_promotion_skips_a_containment_related_proposal(world):
    # the exact 010 trap: a shared non-title alias would normally promote, but
    # the containment edge must veto it
    world.ingest_structured([
        {"entity": "obj:drawer", "attribute": "kind", "value": "drawer", "timeless": True},
        {"entity": "obj:core", "attribute": "kind", "value": "core", "timeless": True},
        {"entity": "obj:core", "attribute": "in", "value": "obj:drawer", "valid_from": 1.0},
        {"entity": "obj:drawer", "attribute": "alias", "value": "the core"},
        {"entity": "obj:core", "attribute": "alias", "value": "the core"},
    ])
    world.registry.maybe_same_as("obj:core", "obj:drawer", evidence="shape-of-a-case trap")
    promoted = world.registry.promote_identity_proposals()
    assert promoted == 0
    assert world.registry.resolve("obj:core") != world.registry.resolve("obj:drawer")
