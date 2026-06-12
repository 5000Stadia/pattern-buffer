"""World wiring, projector lenses, frame absence, refer() tier 1, the gate."""

import pytest

from patternbuffer import World
from patternbuffer.refer import RESOLVED, UNDERDETERMINED
from patternbuffer.testing import StubModel, rule_classifier_fallback
from patternbuffer.thunks import OBSERVE_OR_UNKNOWN


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "w.world", world_id="w:test", model=stub)
    w._stub = stub  # test handle
    yield w
    w.close()


def _seed_study(w):
    """A small canon: home > study > desk > drawer > pipe; hallway graph."""
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:home", "attribute": "kind", "value": "building", "timeless": True},
        {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:study", "attribute": "in", "value": "place:home", "timeless": True},
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:study", "attribute": "connects_to", "value": "place:hall", "timeless": True},
        {"entity": "obj:desk", "attribute": "kind", "value": "desk", "timeless": True},
        {"entity": "obj:desk", "attribute": "in", "value": "place:study", "timeless": True},
        {"entity": "obj:drawer", "attribute": "kind", "value": "drawer", "timeless": True},
        {"entity": "obj:drawer", "attribute": "in", "value": "obj:desk", "timeless": True},
        {"entity": "obj:pipe", "attribute": "kind", "value": "pipe", "timeless": True},
        {"entity": "obj:pipe", "attribute": "located_in", "value": "obj:drawer"},
    ])


class TestGate:
    def test_canonicalization_with_receipt(self, world):
        _seed_study(world)
        # located_in fragmented nowhere: the fold key is 'in'.
        assert world.state("obj:pipe", "in").winner.value == "obj:drawer"
        receipts = [r for r in world.buffer.all_rows() if r.attribute == "canonicalized_from"]
        assert len(receipts) == 1 and receipts[0].value == "located_in->in"

    def test_cursor_stamps_state_rows(self, world):
        _seed_study(world)
        pipe_row = next(r for r in world.buffer.all_rows()
                        if r.entity == "obj:pipe" and r.attribute == "in")
        assert pipe_row.valid_from == 1.0

    def test_observe_mode_stamps_wallclock(self, tmp_path):
        ticks = iter([1718000000.0, 1718000001.0])
        w = World(tmp_path / "t.world", world_id="w:track", model=StubModel(),
                  policy=OBSERVE_OR_UNKNOWN, clock=lambda: next(ticks))
        w.ingest_structured([
            {"entity": "obj:car", "attribute": "in", "value": "place:driveway",
             "status": "observed"},
        ])
        row = next(r for r in w.buffer.all_rows()
                   if r.entity == "obj:car" and r.attribute == "in")
        stamps = w.buffer.visible(entity=row.id, attribute="learned_at_wallclock")
        assert len(stamps) == 1 and stamps[0].value == 1718000000.0  # the A2 rider
        w.close()

    def test_fiction_mode_omits_wallclock(self, world):
        _seed_study(world)
        assert not [r for r in world.buffer.all_rows()
                    if r.attribute == "learned_at_wallclock"]


class TestFrames:
    def test_absence_is_structural(self, world):
        _seed_study(world)
        world.ingest_structured([
            {"entity": "person:marn", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "fact:gap", "attribute": "kind", "value": "proposition", "timeless": True},
            {"entity": "fact:gap", "attribute": "liters", "value": 41200},
            {"entity": "fact:gap", "attribute": "known", "value": True,
             "frame": "knows:person:marn"},
        ])
        # The canon payload holds no knows:-frame rows; the frame payload
        # holds ONLY its rows. Absent, not redacted: scan the payloads.
        canon = world.materialize(["fact:gap"], lens="current_state")
        assert all(r.frame == "canon" for r in canon.assertions)
        marn = world.materialize(["fact:gap"], lens="current_state", frame="knows:person:marn")
        assert all(r.frame == "knows:person:marn" for r in marn.assertions)
        assert {r.attribute for r in marn.assertions} == {"known"}
        # Self-contained: canon facts do not leak into the sparse frame.
        assert "liters" not in {r.attribute for r in marn.assertions}


class TestProjector:
    def test_establishing_vs_current_state(self, world):
        _seed_study(world)
        world.ingest_structured([
            {"entity": "event:theft", "attribute": "kind", "value": "theft", "valid_from": 5.0},
            {"entity": "obj:pipe", "attribute": "in", "value": "place:hall",
             "valid_from": 5.0, "caused_by": "event:theft"},
        ])
        current = world.materialize("place:home", as_of=9.0, lens="current_state")
        establishing = world.materialize("place:home", as_of=9.0, lens="establishing_set")
        def pipe_loc(m):
            rows = [r for r in m.assertions if r.entity == "obj:pipe" and r.attribute == "in"]
            return rows[0].value if rows else None
        # The plot perturbed the world; establishing serves it at rest.
        assert pipe_loc(establishing) == "obj:drawer"
        # Current state: the pipe moved to the hall — but note the hall is
        # outside the home subtree, so the scope walk no longer carries it.
        in_home = {r.entity for r in current.assertions}
        assert "obj:pipe" not in in_home

    def test_budget_never_compacts_the_spine(self, world):
        _seed_study(world)
        m = world.materialize("place:home", lens="current_state", budget=3)
        kept = {(r.entity, r.attribute) for r in m.assertions}
        # kind rows (CONSTITUTIVE) all survive even at budget 3.
        assert {e for e, a in kept if a == "kind"} >= {"place:home", "place:study", "obj:desk"}
        assert m.truncated > 0

    def test_unresolved_is_frontier_not_painted(self, world):
        _seed_study(world)
        world.ingest_structured([
            {"entity": "obj:drawer", "attribute": "contents",
             "value": {"policy": "invent_under_canon"}, "value_type": "unresolved"},
        ])
        m = world.materialize("place:home", lens="current_state")
        assert ("obj:drawer", "contents") in m.unresolved
        assert all(r.value_type != "unresolved" for r in m.assertions)

    def test_default_fills_marked_payload_only(self, world):
        _seed_study(world)
        m = world.materialize("place:home", lens="current_state")
        fills = {(f.entity, f.attribute) for f in m.defaults}
        assert ("place:study", "lighting") in fills  # room kind-default
        assert all(f.status == "default" for f in m.defaults)
        # And nothing 'default' ever entered the log.
        assert not [r for r in world.buffer.all_rows() if r.status == "default"]


class TestRefer:
    def test_alias_hit(self, world):
        _seed_study(world)
        world.ingest_structured([
            {"entity": "person:ilsa", "attribute": "kind", "value": "person",
             "timeless": True, "aliases": ["the clerk with the tin ear"]},
        ])
        r = world.refer("the clerk with the tin ear")
        assert r.status == RESOLVED and r.entity_id == "person:ilsa"
        assert r.receipt["signals"] == ["alias_exact"]

    def test_unique_kind_in_scope(self, world):
        _seed_study(world)
        r = world.refer("the drawer", scope="place:study")
        assert r.status == RESOLVED and r.entity_id == "obj:drawer"

    def test_constraint_inversion(self, world):
        _seed_study(world)
        # "the drawer with the pipe": the pipe's containment IS the answer.
        r = world.refer("the drawer with the pipe",
                        constraints=[("contains", "obj:pipe")])
        assert r.status == RESOLVED and r.entity_id == "obj:drawer"
        assert "constraint_inversion" in r.receipt["signals"][0]

    def test_ambiguity_does_not_guess(self, world):
        _seed_study(world)
        world.ingest_structured([
            {"entity": "obj:kitchen_drawer", "attribute": "kind", "value": "drawer",
             "timeless": True},
        ])
        # Two drawers in world scope; tier-2 stub returns low confidence.
        world._stub.enqueue({"entity_id": "obj:drawer", "confidence": 0.3, "signals": ["recency"]})
        r = world.refer("the drawer")
        assert r.status == UNDERDETERMINED
        assert set(r.candidates) == {"obj:drawer", "obj:kitchen_drawer"}

    def test_no_llm_on_deterministic_resolution(self, world):
        _seed_study(world)
        n = len(world._stub.calls)
        world.refer("the drawer", scope="place:study")
        world.locate("obj:pipe")
        world.path("place:study", "place:hall")
        assert len(world._stub.calls) == n


class TestWorldCharter:
    def test_genesis_charter_and_reader(self, tmp_path):
        from patternbuffer import World
        w = World(tmp_path / "c.world", world_id="w:c", model=StubModel(),
                  stance="reality", title="Dale's Reality",
                  description="The household, tracked.")
        c = w.charter()
        assert c["stance"] == "reality" and c["title"] == "Dale's Reality"
        assert c["kind"] == "world"
        # Ordinary appended rows — amendable history, not config.
        rows = [r for r in w.buffer.all_rows() if r.entity == "world:self"]
        assert all(r.status == "stated" for r in rows)
        w.close()

    def test_stance_enum_fixed(self, tmp_path):
        from patternbuffer import World
        with pytest.raises(ValueError, match="stance"):
            World(tmp_path / "x.world", world_id="w:x", model=StubModel(),
                  stance="dreamscape")

    def test_existing_world_not_recharted(self, tmp_path):
        from patternbuffer import World
        w = World(tmp_path / "c.world", world_id="w:c", model=StubModel(),
                  stance="fiction", title="One")
        n = w.buffer.head()
        w.close()
        w2 = World(tmp_path / "c.world", world_id="w:c", model=StubModel(),
                   stance="reality", title="Two")  # ignored: not genesis
        assert w2.buffer.head() == n
        assert w2.charter()["stance"] == "fiction"
        w2.close()
