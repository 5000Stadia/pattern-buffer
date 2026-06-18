"""PATH-TEMPORAL-V1: as-of-aware path() — the removed/severed edge.

A dead edge is one whose connectivity ended in time (valid_to). path(valid_as_of=now)
routes around it; an earlier as-of still shows it (history preserved). Derived,
never a stored flag.
"""

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "path.world", world_id="w:path", model=stub)
    yield w
    w.close()


def _seed_severed(w):
    # a↔b joined by an edge that fails at t=5 (the dead elevator)
    w.ingest_structured([
        {"entity": "place:a", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:b", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:a", "attribute": "connects_to", "value": "place:b",
         "valid_from": 1.0, "valid_to": 5.0},
    ])


def test_severed_edge_drops_at_now(world):
    _seed_severed(world)
    # after the breach the direct link is gone
    assert world.path("place:a", "place:b", valid_as_of=10.0) is None


def test_history_preserved_before_the_breach(world):
    _seed_severed(world)
    assert world.path("place:a", "place:b", valid_as_of=3.0) == ["place:a", "place:b"]


def test_default_unbounded_is_unchanged(world):
    _seed_severed(world)
    # no bound = today's behavior: the edge is present regardless of valid_to
    assert world.path("place:a", "place:b") == ["place:a", "place:b"]


def test_future_edge_excluded_until_valid(world):
    world.ingest_structured([
        {"entity": "place:a", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:c", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:a", "attribute": "connects_to", "value": "place:c", "valid_from": 20.0},
    ])
    assert world.path("place:a", "place:c", valid_as_of=10.0) is None     # not yet
    assert world.path("place:a", "place:c", valid_as_of=25.0) == ["place:a", "place:c"]
    assert world.path("place:a", "place:c") == ["place:a", "place:c"]     # default no bound


def test_frame_honored_with_and_without_as_of(world):
    world.ingest_structured([
        {"entity": "place:a", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:b", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:a", "attribute": "connects_to", "value": "place:b", "timeless": True},
    ], frame="knows:scout")
    assert world.path("place:a", "place:b", frame="knows:scout") == ["place:a", "place:b"]
    assert world.path("place:a", "place:b", frame="knows:scout", valid_as_of=10.0) \
        == ["place:a", "place:b"]
    assert world.path("place:a", "place:b") is None       # canon never saw the edge


def test_porcelain_path_as_of_passthrough(world):
    _seed_severed(world)
    p = world.porcelain
    assert p.path("place:a", "place:b", as_of=10.0) is None
    assert p.path("place:a", "place:b", as_of=3.0) == ["place:a", "place:b"]
    assert p.path("place:a", "place:b") == ["place:a", "place:b"]


def test_path_writes_nothing(world):
    _seed_severed(world)
    head = world.buffer.head()
    world.path("place:a", "place:b", valid_as_of=10.0)
    world.porcelain.path("place:a", "place:b", as_of=3.0)
    assert world.buffer.head() == head
