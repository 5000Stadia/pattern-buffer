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


class TestContainmentCycleGate:
    """HD 002 finding 1: cycle-forming containment edges are rejected at
    the gate (a write-time invariant), not merely caught at read time."""

    def test_self_edge_rejected(self, world):
        # The reported bug: transit prose extracted `X in X`.
        with pytest.raises(ValueError, match="self-edge"):
            world.ingest_structured([
                {"entity": "place:council_tier", "attribute": "in",
                 "value": "place:council_tier", "timeless": True},
            ])
        assert not [r for r in world.buffer.all_rows()
                    if r.entity == "place:council_tier" and r.attribute == "in"]

    def test_transitive_cycle_rejected(self, world):
        world.ingest_structured([
            {"entity": "obj:a", "attribute": "in", "value": "obj:b", "valid_from": 1.0},
        ])
        with pytest.raises(ValueError, match="ancestor"):
            world.ingest_structured([
                {"entity": "obj:b", "attribute": "in", "value": "obj:a", "valid_from": 2.0},
            ])

    def test_plain_reparent_accepted(self, world):
        # A B C chain then A reparented under C — no cycle, must pass.
        world.ingest_structured([
            {"entity": "obj:a", "attribute": "in", "value": "obj:b", "valid_from": 1.0},
            {"entity": "obj:b", "attribute": "in", "value": "obj:c", "valid_from": 1.0},
            {"entity": "obj:a", "attribute": "in", "value": "obj:c", "valid_from": 2.0},
        ])
        assert world.state("obj:a", "in", valid_as_of=3.0).winner.value == "obj:c"

    def test_noncontainment_self_reference_allowed(self, world):
        # Only the containment family is a tree; a self-edge elsewhere is data.
        rows = world.ingest_structured([
            {"entity": "person:x", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:x", "attribute": "rival_of", "value": "person:x"},
        ])
        assert any(r.attribute == "rival_of" for r in rows)

    def test_backdated_cycle_is_documented_residual(self, world):
        # A single write-time check cannot see a cycle that forms only at a
        # later valid-time; the read-time locate() guard remains the
        # backstop. Gate accepts; locate() terminates (no hang) (spec Fix 1).
        world.ingest_structured([
            {"entity": "obj:a", "attribute": "in", "value": "obj:b", "valid_from": 10.0},
        ])
        world.ingest_structured([  # back-dated: invisible to the vf=1 walk
            {"entity": "obj:b", "attribute": "in", "value": "obj:a", "valid_from": 1.0},
        ])
        chain = world.locate("obj:a", valid_as_of=12.0)  # must not loop forever
        assert isinstance(chain, list) and len(chain) <= 2

    def test_deferred_classification_residual(self, world):
        # Second documented bound (spec Fix 1): with classification deferred,
        # the transitive walk folds unclassified rows by STATE-recency and
        # can miss a cycle; the self-edge check still holds, and read-time
        # locate() stays bounded. (Live play uses classify_inline=True, where
        # the transitive check is accurate.)
        world.ingestor.classify_inline = False
        world.ingest_structured([
            {"entity": "place:a", "attribute": "in", "value": "place:b", "valid_from": 1.0},
            {"entity": "place:a", "attribute": "in", "value": "place:c", "valid_from": 2.0},
            {"entity": "place:b", "attribute": "in", "value": "place:a", "valid_from": 3.0},
        ])  # accepted at the gate (deferred-classify residual)
        world.classifier.classify_all()
        # The self-edge guarantee is unaffected even when deferred:
        with pytest.raises(ValueError, match="self-edge"):
            world.ingest_structured([
                {"entity": "place:b", "attribute": "in", "value": "place:b", "valid_from": 4.0},
            ])
        # Read-time guard stays bounded (no hang) despite the slipped cycle:
        assert isinstance(world.locate("place:a", valid_as_of=5.0), list)


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


class TestRefer018Extensions:
    def test_zero_candidate_escalation_scope_bounded(self, world):
        """A synonym (zero tier-1 hits) escalates to tier 2 with the scope's
        members — vocabulary miss is not absence (letter 018 m.1)."""
        _seed_study(world)
        world.ingest_structured([
            {"entity": "obj:cabinet", "attribute": "kind", "value": "cabinet",
             "timeless": True},
            {"entity": "obj:cabinet", "attribute": "in", "value": "place:study"},
        ])
        world._stub.enqueue({"entity_id": "obj:cabinet", "confidence": 0.9,
                             "signals": ["synonym:cupboard~cabinet"]})
        world._stub.enqueue({"durability": "CONSTITUTIVE", "class_confidence": 0.9})
        r = world.refer("the cupboard", scope="place:study")
        assert r.status == RESOLVED and r.entity_id == "obj:cabinet"
        assert r.receipt["tier"] == 2

        # Second use: tier 1a via the accrued alias — zero model calls.
        n = len(world._stub.calls)
        r2 = world.refer("the cupboard")
        assert r2.status == RESOLVED and r2.entity_id == "obj:cabinet"
        assert r2.receipt["signals"] == ["alias_exact"]
        assert len(world._stub.calls) == n
        # Both receipts in the log: the alias row is inferred + sourced.
        alias_rows = [x for x in world.buffer.all_rows()
                      if x.attribute == "alias" and x.value == "the cupboard"]
        assert len(alias_rows) == 1 and alias_rows[0].status == "inferred"
        src = world.buffer.visible(entity=alias_rows[0].id, attribute="source")
        assert src and "refer:tier2" in str(src[0].value)

    def test_no_world_scope_escalation(self, world):
        """Zero candidates WITHOUT a scope stays underdetermined — the
        escalation path is scope-bounded only (018 guard)."""
        _seed_study(world)
        r = world.refer("the doohickey")
        assert r.status == UNDERDETERMINED

    def test_learned_alias_never_outranks_exact_name(self, world):
        _seed_study(world)
        world.ingest_structured([
            {"entity": "obj:cabinet", "attribute": "kind", "value": "cabinet",
             "timeless": True, "aliases": ["the cupboard"]},  # learned earlier
            {"entity": "obj:real_cupboard", "attribute": "kind", "value": "cupboard",
             "timeless": True, "aliases": ["the cupboard"]},  # exact-named entity
        ])
        # Alias collision, but one entity IS kind=cupboard: the exact-kind
        # entity wins deterministically — the learned alias never outranks
        # the exact name/kind (the 018 guard, satisfied at tier 1c).
        r = world.refer("the cupboard")
        assert r.status == RESOLVED and r.entity_id == "obj:real_cupboard"
        assert r.receipt["signals"] == ["unique_kind_in_scope"]


class TestFrameTargetedWrites:
    """Letter 028: named-frame authoring through the gate — target, not escape."""

    def test_default_frame_param(self, world):
        _seed_study(world)
        rows = world.ingest_structured([
            {"entity": "fact:gap", "attribute": "known", "value": True},
            {"entity": "fact:gap", "attribute": "suspected", "value": True,
             "frame": "knows:person:marn"},  # per-item frame wins
        ], frame="knows:person:pell")
        assert rows[0].frame == "knows:person:pell"
        assert rows[1].frame == "knows:person:marn"
        # The gate's discipline applied unchanged: role-checked, stamped.
        assert rows[0].status == "stated" and rows[0].valid_from is not None

    def test_plot_frame_is_just_a_named_frame(self, world):
        _seed_study(world)
        world.ingest_structured([
            {"entity": "arc:destiny", "attribute": "next_beat", "value": "the reveal"},
        ], frame="plot:hidden_arc")
        m = world.materialize(["arc:destiny"], frame="plot:hidden_arc")
        assert {r.frame for r in m.assertions} == {"plot:hidden_arc"}
        canon = world.materialize(["arc:destiny"])
        assert all(r.frame == "canon" for r in canon.assertions)  # absent, not redacted


class TestGeneratedThroughGate:
    """Letter 029: generated via ingest_structured — resolver authority
    composed behind the gate; never canon, never knows:*."""

    def test_generated_into_plot_frame(self, world):
        _seed_study(world)
        rows = world.ingest_structured([
            {"entity": "arc:beat_7", "attribute": "summary",
             "value": "repaired: the rival arrives early", "status": "generated"},
        ], frame="plot:hidden_arc")
        assert rows[0].status == "generated" and rows[0].frame == "plot:hidden_arc"

    def test_generated_into_canon_refused(self, world):
        _seed_study(world)
        with pytest.raises(ValueError, match="029 guard"):
            world.ingest_structured([
                {"entity": "obj:pipe", "attribute": "color", "value": "gold",
                 "status": "generated"},
            ])

    def test_generated_into_knows_refused(self, world):
        _seed_study(world)
        with pytest.raises(ValueError, match="029 guard"):
            world.ingest_structured([
                {"entity": "fact:x", "attribute": "known", "value": True,
                 "status": "generated", "frame": "knows:person:marn"},
            ])

    def test_matrix_intact_at_buffer_layer(self, world):
        """The ingestor ROLE still cannot append generated — the doorway
        composes resolver authority; it does not widen the matrix."""
        from patternbuffer.roles import RoleViolation, _make_engine_roles
        with pytest.raises(RoleViolation):
            world.buffer.append(entity="e:x", attribute="y", value=1,
                                status="generated",
                                role=_make_engine_roles()["ingestor"])


def test_what_happened_window(world):
    """occurred(kind, participants, window) composes deterministically:
    the lens takes since+as_of; kind/agent/patient are structured rows."""
    _seed_study(world)
    world.ingest_structured([
        {"entity": "event:theft", "attribute": "kind", "value": "theft", "valid_from": 5.0},
        {"entity": "event:theft", "attribute": "agent", "value": "person:rival",
         "value_type": "entity", "valid_from": 5.0},
        {"entity": "event:return", "attribute": "kind", "value": "return", "valid_from": 9.0},
        {"entity": "person:rival", "attribute": "kind", "value": "person", "timeless": True},
    ])
    m = world.materialize(["event:theft", "event:return", "person:rival"],
                          lens="what_happened", since=4.0, as_of=6.0)
    kinds = {r.value for r in m.assertions if r.attribute == "kind"
             and r.entity.startswith("event:")}
    assert kinds == {"theft"}  # window excludes the day-9 event
    agents = [r for r in m.assertions if r.attribute == "agent"]
    assert agents and agents[0].value == "person:rival"  # structured fields
