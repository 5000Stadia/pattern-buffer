"""PLACE-FEATURE-ABSTRACTION-V1: the compositional axis (place ∧ feature).

`part_of` is structural composition — a burrow part_of a hillside — distinct from
movable containment (`in`). composition()/features() mirror locate()/contents() on
this axis but HALT on a conflicted parent (never silently pick). The sub-place is
one entity: it answers both the place lens (locate/contents/route/state) and the
feature lens (composition/features).
"""

import json

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback
from patternbuffer.classify import CONSTITUTIVE


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "pf.world", world_id="w:pf", model=stub)
    yield w
    w.close()


def _burrow(w):
    w.ingest_structured([
        {"entity": "place:hillside", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:burrow", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:burrow", "attribute": "part_of", "value": "place:hillside",
         "value_type": "entity", "valid_from": 1.0},
    ])


def test_features_and_composition_basic(world):
    _burrow(world)
    assert world.features("place:hillside") == ["place:burrow"]
    assert world.composition("place:burrow") == ["place:hillside"]


def test_duality_burrow_is_a_full_place(world):
    # the sub-place answers the PLACE lens too: contents + locate work, and an
    # actor IN the burrow is NOT located in the hillside (axis separation)
    _burrow(world)
    world.ingest_structured([
        {"entity": "person:mole", "attribute": "in", "value": "place:burrow",
         "value_type": "entity", "valid_from": 2.0},
    ])
    assert world.contents("place:burrow") == ["person:mole"]
    assert world.locate("person:mole") == ["place:burrow"]   # NOT [burrow, hillside]


def test_axes_do_not_cross_contaminate(world):
    # locate/contents ignore part_of; composition/features ignore in
    _burrow(world)
    world.ingest_structured([
        {"entity": "obj:rock", "attribute": "in", "value": "place:hillside",
         "value_type": "entity", "valid_from": 2.0},
    ])
    # rock is IN hillside (containment), burrow is PART_OF hillside (composition)
    assert world.contents("place:hillside") == ["obj:rock"]       # not burrow
    assert world.features("place:hillside") == ["place:burrow"]   # not rock
    assert world.composition("obj:rock") == []                   # in != part_of


def test_part_of_is_constitutive_and_canonicalizes(world):
    # part_of hits the structural guardrail -> CONSTITUTIVE (model never asked);
    # feature_of canonicalizes to part_of
    world.ingest_structured([
        {"entity": "place:office", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:desk", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:desk", "attribute": "feature_of", "value": "place:office",
         "value_type": "entity", "valid_from": 1.0},
    ])
    row = next(r for r in world.buffer.all_rows() if r.attribute == "part_of")
    assert world.classifier.durability(row.id) == CONSTITUTIVE
    assert world.composition("place:desk") == ["place:office"]    # feature_of -> part_of


def test_valid_timed_composition(world):
    # a temporary structure: dug at t=1, boarded up at t=8 (a single bounded
    # part_of edge). Composition is empty before, present during, empty after.
    world.ingest_structured([
        {"entity": "place:hill2", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:den", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:den", "attribute": "part_of", "value": "place:hill2",
         "value_type": "entity", "valid_from": 1.0, "valid_to": 8.0},
    ])
    assert world.composition("place:den", valid_as_of=0.5) == []          # before dug
    assert world.composition("place:den", valid_as_of=5.0) == ["place:hill2"]  # while open
    assert world.composition("place:den", valid_as_of=10.0) == []         # after boarded


def test_conflict_halts_never_picks(world):
    # two parents at the same valid-time => conflicted; the reads must NOT pick
    world.ingest_structured([
        {"entity": "place:h1", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:h2", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:nook", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:nook", "attribute": "part_of", "value": "place:h1",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "place:nook", "attribute": "part_of", "value": "place:h2",
         "value_type": "entity", "valid_from": 1.0},
    ])
    assert world.state("place:nook", "part_of").conflicted is True
    assert world.composition("place:nook") == []          # not [h1] (earliest)
    assert world.features("place:h1") == []               # conflicted child excluded
    assert world.features("place:h2") == []


def test_late_parent_merge_resolves_false_conflict(world):
    # Cx 065: two part_of rows to what turn out to be the SAME parent (merged
    # after the rows were written) must NOT stay a conflict — entity-valued
    # CONSTITUTIVE conflict is identity-aware.
    world.ingest_structured([
        {"entity": "place:h1", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:h1_alias", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:nook", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:nook", "attribute": "part_of", "value": "place:h1",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "place:nook", "attribute": "part_of", "value": "place:h1_alias",
         "value_type": "entity", "valid_from": 1.0},
    ])
    # before merge: a genuine two-parent conflict
    assert world.state("place:nook", "part_of").conflicted is True
    assert world.composition("place:nook") == []
    # the two parents turn out to be one whole
    world.registry.merge("place:h1", "place:h1_alias", evidence="same hillside")
    canonical = world.registry.resolve("place:h1")
    assert world.state("place:nook", "part_of").conflicted is False
    assert world.composition("place:nook") == [canonical]
    assert world.features(canonical) == ["place:nook"]


def test_part_of_is_relating_edge_not_veto(world):
    # part_of is evidence AGAINST identity (a relating edge) but NOT a containment
    # merge-veto
    _burrow(world)
    reg = world.registry
    assert reg.relating_edges_between("place:burrow", "place:hillside")   # non-empty
    assert reg.containment_block("place:burrow", "place:hillside") == []  # not a veto


def test_reads_write_nothing(world):
    _burrow(world)
    head = world.buffer.head()
    json.dumps(world.porcelain.composition("place:burrow"))
    json.dumps(world.porcelain.features("place:hillside"))
    assert world.buffer.head() == head
