"""AWARENESS-READS-V1.1: projection-level correlation + composition (opt-in).

snapshot/materialize(correlated=True) folds each entity over its `aka` correlation
union (the whole reveal scene in one call); (features=True) inlines each place's
part_of-feature children. Both opt-in; the default projection is unchanged.
"""

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "ap.world", world_id="w:ap", model=stub)
    yield w
    w.close()


# ----------------------------------------------- Win 1: correlated projection

def _reveal_world(w):
    w.ingest_structured([
        {"entity": "person:masked", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:masked", "attribute": "mood", "value": "grim", "valid_from": 1.0},
        {"entity": "person:ilsa", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:ilsa", "attribute": "occupation", "value": "clerk", "valid_from": 1.0},
    ])
    w.correlate("person:masked", "person:ilsa", evidence="reveal", valid_from=10.0)


def test_correlated_snapshot_includes_facets(world):
    _reveal_world(world)
    snap = world.porcelain.snapshot(["person:masked"], correlated=True, as_of=15.0)
    values = {f["value"] for f in snap["facts"]}
    assert "grim" in values and "clerk" in values         # masked's + ilsa's facets


def test_default_snapshot_does_not_correlate(world):
    _reveal_world(world)
    snap = world.porcelain.snapshot(["person:masked"], as_of=15.0)   # default
    values = {f["value"] for f in snap["facts"]}
    assert "grim" in values and "clerk" not in values     # ilsa's facet NOT pulled in


def test_correlated_as_of_before_reveal_is_uncorrelated(world):
    _reveal_world(world)
    snap = world.porcelain.snapshot(["person:masked"], correlated=True, as_of=5.0)
    values = {f["value"] for f in snap["facts"]}
    assert "clerk" not in values        # before the reveal: no leak (valid-time gate)


def test_correlated_is_lens_orthogonal_situation(world):
    # Cx final: correlated must take effect under the situation lens too (the
    # boolean is lens-orthogonal), not silently drop.
    _reveal_world(world)
    snap = world.porcelain.snapshot(["person:masked"], lens="situation",
                                    correlated=True, as_of=15.0)
    assert "clerk" in {f["value"] for f in snap["facts"]}    # facet in the standing floor
    plain = world.porcelain.snapshot(["person:masked"], lens="situation", as_of=15.0)
    assert "clerk" not in {f["value"] for f in plain["facts"]}   # default still uncorrelated


def test_correlated_establishing_set_is_guarded(world):
    # correlated + establishing_set is incoherent (the creation view predates
    # reveals) -> a clean raise, not a silent half-applied flag.
    _reveal_world(world)
    with pytest.raises(ValueError, match="establishing_set"):
        world.materialize(["person:masked"], lens="establishing_set", correlated=True)


def test_correlated_is_lens_orthogonal_character_sheet(world):
    # Cx final #2: character_sheet folds standing state too -> must honor correlated
    # (a dual-persona sheet).
    _reveal_world(world)
    snap = world.porcelain.snapshot(["person:masked"], lens="character_sheet",
                                    correlated=True, as_of=15.0)
    assert "clerk" in {f["value"] for f in snap["facts"]}
    plain = world.porcelain.snapshot(["person:masked"], lens="character_sheet", as_of=15.0)
    assert "clerk" not in {f["value"] for f in plain["facts"]}


# ----------------------------------------------- Win 2: features projection

def _burrow_world(w):
    w.ingest_structured([
        {"entity": "place:hillside", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:burrow", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:burrow", "attribute": "state", "value": "dug", "valid_from": 1.0},
        {"entity": "place:burrow", "attribute": "part_of", "value": "place:hillside",
         "value_type": "entity", "valid_from": 1.0},
    ])


def test_features_snapshot_inlines_children(world):
    _burrow_world(world)
    snap = world.porcelain.snapshot(["place:hillside"], features=True)
    entities = {f["entity"] for f in snap["facts"]}
    assert "place:burrow" in entities         # the feature child is projected
    assert "dug" in {f["value"] for f in snap["facts"]}


def test_default_snapshot_omits_features(world):
    _burrow_world(world)
    snap = world.porcelain.snapshot(["place:hillside"])    # default
    assert "place:burrow" not in {f["entity"] for f in snap["facts"]}


def test_features_excludes_conflicted_child(world):
    # a burrow with two part_of parents at one valid-time => conflicted => not
    # inlined under either (conflict-halt inherited from features())
    world.ingest_structured([
        {"entity": "place:h1", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:h2", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:nook", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:nook", "attribute": "part_of", "value": "place:h1",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "place:nook", "attribute": "part_of", "value": "place:h2",
         "value_type": "entity", "valid_from": 1.0},
    ])
    snap = world.porcelain.snapshot(["place:h1"], features=True)
    assert "place:nook" not in {f["entity"] for f in snap["facts"]}


def test_correlated_and_features_default_off_unchanged(world):
    # the two flags default off; a plain snapshot is byte-identical to no-flags
    _burrow_world(world)
    a = world.porcelain.snapshot(["place:hillside"])
    b = world.porcelain.snapshot(["place:hillside"], correlated=False, features=False)
    assert a == b
