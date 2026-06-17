"""SITUATION-LENS-V1: re-entry retrieval = standing truth ∪ live events.

Liveness is derived every read (open thread (a) OR surviving un-superseded
effect (b)); closed history is dropped; anchoring is effect-driven (an event
surfaces only because it produced a still-served fact about a scope entity,
never because a mobile participant stands in scope). Nothing is stored.
"""

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "situation.world", world_id="w:situation", model=stub)
    yield w
    w.close()


def _seed_tavern(w):
    """A tavern with: a live stash (chest still in the back room), a dead
    brawl (the bar's dent fixed since), a farm rumor whose effect is about an
    out-of-scope cousin though Barliman (in scope) is its agent.

    The damageable thing is an `obj:` (movable → STATE, recency-superseding);
    a `place:` attribute folds CONSTITUTIVE in the test classifier and would
    conflict rather than supersede."""
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        # structure
        {"entity": "place:tavern", "attribute": "kind", "value": "building", "timeless": True},
        {"entity": "place:backroom", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:backroom", "attribute": "in", "value": "place:tavern", "timeless": True},
        # standing truth
        {"entity": "place:tavern", "attribute": "owner", "value": "barliman", "valid_from": 1.0},
        {"entity": "person:barliman", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:barliman", "attribute": "in", "value": "place:tavern", "valid_from": 1.0},
        {"entity": "obj:bar", "attribute": "kind", "value": "fixture", "timeless": True},
        {"entity": "obj:bar", "attribute": "in", "value": "place:tavern", "valid_from": 1.0},
        # LIVE (b): the stash put the chest in the back room — still there
        {"entity": "event:stash", "attribute": "kind", "value": "stash", "valid_from": 3.0},
        {"entity": "obj:chest", "attribute": "kind", "value": "chest", "timeless": True},
        {"entity": "obj:chest", "attribute": "in", "value": "place:backroom",
         "valid_from": 3.0, "caused_by": "event:stash"},
        # DEAD: the brawl dented the bar; the repair fixed it (superseded)
        {"entity": "event:brawl", "attribute": "kind", "value": "brawl", "valid_from": 2.0},
        {"entity": "obj:bar", "attribute": "condition", "value": "dented",
         "valid_from": 2.0, "caused_by": "event:brawl"},
        {"entity": "event:repair", "attribute": "kind", "value": "repair", "valid_from": 4.0},
        {"entity": "obj:bar", "attribute": "condition", "value": "fixed",
         "valid_from": 4.0, "caused_by": "event:repair"},
        # OUT-OF-SCOPE effect: Barliman (in scope) is the agent, but the
        # surviving effect is about the cousin/farm, not the tavern
        {"entity": "event:farm", "attribute": "kind", "value": "news", "valid_from": 3.5},
        {"entity": "event:farm", "attribute": "agent", "value": "person:barliman", "valid_from": 3.5},
        {"entity": "person:cousin", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:cousin", "attribute": "role", "value": "farmer",
         "valid_from": 3.5, "caused_by": "event:farm"},
    ])


def _event_ids(m):
    return {a.entity for a in m.assertions if a.entity.startswith("event:")}


def _facts(m):
    return {
        (a.entity, a.attribute, a.value, a.value_type)
        for a in m.assertions
        if not a.entity.startswith("event:")
    }


class TestStandingTruthFloor:
    def test_floor_equals_current_state(self, world):
        _seed_tavern(world)
        situation = world.materialize("place:tavern", lens="situation")
        current = world.materialize("place:tavern", lens="current_state")
        # bucket 1 is current_state verbatim: identical non-event rows.
        assert _facts(situation) == _facts(current)
        # and the current condition is the fixed one, not the dented one.
        assert ("obj:bar", "condition", "fixed", "literal") in _facts(situation)
        assert ("obj:bar", "condition", "dented", "literal") not in _facts(situation)


class TestLiveness:
    def test_live_surviving_effect_is_kept(self, world):
        _seed_tavern(world)
        m = world.materialize("place:tavern", lens="situation")
        # the stash's effect (chest in back room) is still served -> live (b)
        assert "event:stash" in _event_ids(m)

    def test_dead_superseded_effect_is_dropped(self, world):
        _seed_tavern(world)
        m = world.materialize("place:tavern", lens="situation")
        # the brawl's effect (damaged) was superseded by the repair -> dead
        assert "event:brawl" not in _event_ids(m)
        # the repair, whose effect (repaired) is current, is itself live
        assert "event:repair" in _event_ids(m)

    def test_anchoring_is_effect_driven_not_participant(self, world):
        _seed_tavern(world)
        m = world.materialize("place:tavern", lens="situation")
        # Barliman is in scope and is the farm event's agent, but the farm
        # event's surviving effect is about the out-of-scope cousin -> excluded
        assert "event:farm" not in _event_ids(m)
        # contrast: the chest effect IS in scope -> its event is kept
        assert "event:stash" in _event_ids(m)

    def test_open_thread_is_kept(self, world):
        _seed_tavern(world)
        # an unresolved aspect of the tavern, caused by an omen event -> (a)
        world.ingest_structured([
            {"entity": "event:omen", "attribute": "kind", "value": "omen", "valid_from": 3.0},
            {"entity": "place:tavern", "attribute": "portent",
             "value": {"policy": "deny"}, "value_type": "unresolved",
             "caused_by": "event:omen"},
        ])
        m = world.materialize("place:tavern", lens="situation")
        assert "event:omen" in _event_ids(m)

    def test_open_thread_flips_dead_when_superseded(self, world):
        _seed_tavern(world)
        world.ingest_structured([
            {"entity": "event:omen", "attribute": "kind", "value": "omen", "valid_from": 3.0},
            {"entity": "place:tavern", "attribute": "portent",
             "value": {"policy": "deny"}, "value_type": "unresolved",
             "caused_by": "event:omen"},
        ])
        assert "event:omen" in _event_ids(world.materialize("place:tavern", lens="situation"))
        # a concrete value on the same key supersedes the unresolved thread;
        # the concrete row carries no caused_by -> the omen drops, no lens write
        world.ingestor.cursor.advance(5.0)
        world.ingest_structured([
            {"entity": "place:tavern", "attribute": "portent", "value": "clear", "valid_from": 5.0},
        ])
        assert "event:omen" not in _event_ids(world.materialize("place:tavern", lens="situation"))


class TestAccrueEffect:
    def test_accrue_ledger_row_keeps_its_event_live(self, world):
        world.ingestor.cursor.advance(1.0)
        world.ingest_structured([
            {"entity": "obj:vault", "attribute": "kind", "value": "container", "timeless": True},
            {"entity": "attr:gold", "attribute": "fold_policy", "value": "accrue", "timeless": True},
            {"entity": "event:deposit", "attribute": "kind", "value": "deposit", "valid_from": 2.0},
            {"entity": "obj:vault", "attribute": "gold", "value": 100, "valid_from": 1.0},
            {"entity": "obj:vault", "attribute": "gold", "value": 50, "value_type": "delta",
             "valid_from": 2.0, "caused_by": "event:deposit"},
        ])
        m = world.materialize("obj:vault", lens="situation")
        # the deposit's delta is a contributing ledger row (served) -> live
        assert "event:deposit" in _event_ids(m)


class TestOverflowAndMembrane:
    def test_budget_protects_floor_and_truncates_live_events(self, world):
        _seed_tavern(world)
        full = world.materialize("place:tavern", lens="situation")
        floor = len(_facts(full))
        # two live events in scope (stash @3.0, repair @4.0)
        assert {"event:stash", "event:repair"} <= _event_ids(full)
        # budget == floor leaves zero room for events: floor intact, events cut
        m = world.materialize("place:tavern", lens="situation", budget=floor)
        assert _facts(m) == _facts(full)          # floor never truncated
        assert _event_ids(m) == set()             # all live events yielded
        assert m.truncated > 0

    def test_overflow_keeps_the_most_recent_live_event(self, world):
        _seed_tavern(world)
        full = world.materialize("place:tavern", lens="situation")
        floor = len(_facts(full))
        # room for exactly one event row: recency keeps the newest (repair @4.0
        # over stash @3.0), never popularity
        m = world.materialize("place:tavern", lens="situation", budget=floor + 1)
        assert _facts(m) == _facts(full)
        assert _event_ids(m) == {"event:repair"}
        assert m.truncated > 0

    def test_read_writes_nothing(self, world):
        _seed_tavern(world)
        head = world.buffer.head()
        world.materialize("place:tavern", lens="situation")
        world.materialize("place:tavern", lens="situation", budget=1)
        assert world.buffer.head() == head


class TestFrameScoping:
    def test_non_canon_effect_reaches_its_event(self, world):
        # the effect and its event live in a named knower-frame; the caused_by
        # edge must ride in that frame too, or the event false-deads (Codex
        # post-impl finding 1).
        world.ingestor.cursor.advance(1.0)
        world.ingest_structured([
            {"entity": "place:trail", "attribute": "kind", "value": "path", "timeless": True},
            {"entity": "event:sighting", "attribute": "kind", "value": "sighting", "valid_from": 2.0},
            {"entity": "obj:track", "attribute": "kind", "value": "track", "timeless": True},
            {"entity": "obj:track", "attribute": "in", "value": "place:trail",
             "valid_from": 2.0, "caused_by": "event:sighting"},
        ], frame="knows:scout")
        m = world.materialize("place:trail", lens="situation", frame="knows:scout")
        assert "event:sighting" in _event_ids(m)
        # and it is absent from canon, where the effect was never asserted
        canon = world.materialize("place:trail", lens="situation")
        assert "event:sighting" not in _event_ids(canon)
