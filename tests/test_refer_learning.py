"""REFER-LEARNING-V1: refer learns a word, never a pick.

One test per oracle in the spec's §2–§8, plus its no-growth invariant: an
ambiguous reference read N times leaves the log head where it was.

The worlds are small. A kitchen and a garage each hold one cabinet, and
"the old cupboard" is nobody's name, so it is a vocabulary miss that tier 2
maps onto whichever cabinet the scene holds.
"""

from __future__ import annotations

import json

import pytest

from patternbuffer import World
from patternbuffer.classify import EVENT
from patternbuffer.model import TASK_REFER
from patternbuffer.refer import RESOLVED
from patternbuffer.testing import StubModel, rule_classifier_fallback

ALICE = "knows:person:alice"
WORD = "the old cupboard"


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "w.world", world_id="w:refer-learning", model=stub)
    w._stub = stub  # test handle
    yield w
    w.close()


def _two_rooms(w: World) -> None:
    """A kitchen and a garage, each holding one cabinet (canon)."""
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:kitchen", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:garage", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "obj:kitchen_cabinet", "attribute": "kind", "value": "cabinet",
         "timeless": True},
        {"entity": "obj:kitchen_cabinet", "attribute": "in", "value": "place:kitchen"},
        {"entity": "obj:garage_cabinet", "attribute": "kind", "value": "cabinet",
         "timeless": True},
        {"entity": "obj:garage_cabinet", "attribute": "in", "value": "place:garage"},
    ])


def _judge(w: World, entity_id: str, confidence: float = 0.9) -> None:
    """Script one tier-2 answer."""
    w._stub.enqueue({"entity_id": entity_id, "confidence": confidence,
                     "signals": ["synonym"]})


def _since(w: World, head: int) -> list:
    """The rows appended after `head`, in log order."""
    return [r for r in w.buffer.all_rows() if r.seq > head]


def _learn_kitchen_word(w: World) -> None:
    """§2's first oracle as setup: the kitchen learns "the old cupboard"."""
    _two_rooms(w)
    _judge(w, "obj:kitchen_cabinet")
    r = w.refer(WORD, scope="place:kitchen")
    assert r.status == RESOLVED and r.receipt["tier"] == 2


def _learned_rows(w: World) -> list:
    return [r for r in w.buffer.all_rows() if r.attribute == "learned_alias"]


# ---------------------------------------------------------------- §2 writing


class TestWriting:
    """§2: only a vocabulary miss learns, and it learns a word."""

    def test_miss_appends_one_word_and_its_receipt(self, world):
        _two_rooms(world)
        _judge(world, "obj:kitchen_cabinet")
        head = world.buffer.head()
        r = world.refer(WORD, scope="place:kitchen")
        assert r.status == RESOLVED and r.entity_id == "obj:kitchen_cabinet"
        assert r.receipt["tier"] == 2
        word, source = _since(world, head)  # exactly two rows
        assert (word.entity, word.attribute, word.value) == (
            "obj:kitchen_cabinet", "learned_alias", WORD)
        assert word.frame == "canon" and word.status == "inferred"
        assert word.valid_from is None and word.valid_to is None  # timeless
        assert (source.entity, source.attribute) == (word.id, "source")
        assert source.value == "refer:tier2:" + json.dumps(["synonym"])

    def test_miss_makes_one_model_call(self, world):
        _two_rooms(world)
        _judge(world, "obj:kitchen_cabinet")
        n = len(world._stub.calls)
        world.refer(WORD, scope="place:kitchen")
        # The tier-2 judgment only: no classifier call for the learned row.
        assert [schema["title"] for _, schema in world._stub.calls[n:]] == [TASK_REFER]

    def test_learned_row_is_event(self, world):
        _learn_kitchen_word(world)
        (word,) = _learned_rows(world)
        assert world.classifier.durability(word.id) == EVENT
        # So it never folds, stands as a fact, or counts as unstamped.
        assert world.state("obj:kitchen_cabinet", "learned_alias").winner is None
        assert "learned_alias" not in world.indexes.current_state("obj:kitchen_cabinet")
        assert not [u for u in world.fidelity_audit()["unstamped_timed"]
                    if u["attribute"] == "learned_alias"]

    def test_pinned_read_never_writes(self, world):
        _two_rooms(world)
        _judge(world, "obj:kitchen_cabinet")
        head = world.buffer.head()
        r = world.refer(WORD, scope="place:kitchen", asserted_as_of=head)
        assert r.status == RESOLVED and r.entity_id == "obj:kitchen_cabinet"
        assert world.buffer.head() == head

    def test_learn_false_never_writes(self, world):
        _two_rooms(world)
        _judge(world, "obj:kitchen_cabinet")
        head = world.buffer.head()
        r = world.refer(WORD, scope="place:kitchen", learn=False)
        assert r.status == RESOLVED and r.entity_id == "obj:kitchen_cabinet"
        assert world.buffer.head() == head

    def test_word_lands_in_the_calls_frame(self, world):
        _two_rooms(world)
        # Alice's own kitchen rows: her scene is computed in her frame.
        world.ingest_structured([
            {"entity": "obj:kitchen_cabinet", "attribute": "in", "value": "place:kitchen"},
        ], frame=ALICE)
        _judge(world, "obj:kitchen_cabinet")
        r = world.refer(WORD, scope="place:kitchen", frame=ALICE)
        assert r.status == RESOLVED and r.entity_id == "obj:kitchen_cabinet"
        (word,) = _learned_rows(world)
        assert word.frame == ALICE and word.entity == "obj:kitchen_cabinet"

    # -- guards the section states (not oracles of their own) --

    def test_gate_skip_is_not_an_error(self, world):
        """§2: an empty gate return is logged and the resolution stands
        (the retired accrual path raised on rows[0])."""
        _two_rooms(world)
        _judge(world, "Obj:Odd")  # a scope root the gate's id grammar refuses
        head = world.buffer.head()
        r = world.refer(WORD, scope="Obj:Odd")
        assert r.status == RESOLVED and r.entity_id == "Obj:Odd"
        assert world.buffer.head() == head
        assert [s.reason for s in world.ingestor.last_skipped] == ["malformed_id"]

    def test_word_is_written_once(self, world):
        """§2's guard, called directly: the cascade cannot reach it at the
        head (an in-scope word is a tier-1d hit)."""
        _two_rooms(world)
        receipt = {"signals": ["synonym"]}
        world.refer._learn(WORD, "obj:kitchen_cabinet", receipt, "canon")
        head = world.buffer.head()
        world.refer._learn("  The Old Cupboard ", "obj:kitchen_cabinet", receipt, "canon")
        assert world.buffer.head() == head
        world.refer._learn(WORD, "obj:kitchen_cabinet", receipt, ALICE)  # another frame
        assert [w.frame for w in _learned_rows(world)] == ["canon", ALICE]


# ---------------------------------------------------------------- §3 reading


class TestReading:
    """§3: tier 1d reads a learned word back on a vocabulary miss, in scope."""

    def test_kitchen_again_is_tier1(self, world):
        _learn_kitchen_word(world)
        n, head = len(world._stub.calls), world.buffer.head()
        r = world.refer(WORD, scope="place:kitchen")
        assert r.status == RESOLVED and r.entity_id == "obj:kitchen_cabinet"
        assert r.receipt == {"tier": 1, "signals": ["learned_alias"]}
        assert len(world._stub.calls) == n and world.buffer.head() == head

    def test_garage_is_rejudged_and_learns_its_own_word(self, world):
        _learn_kitchen_word(world)
        _judge(world, "obj:garage_cabinet")
        head = world.buffer.head()
        r = world.refer(WORD, scope="place:garage")
        assert r.status == RESOLVED and r.entity_id == "obj:garage_cabinet"
        assert r.receipt["tier"] == 2
        # The kitchen cabinet is out of scope, so not a candidate.
        assert r.receipt["candidates"] == ["obj:garage_cabinet", "place:garage"]
        learned = [(x.entity, x.value) for x in _since(world, head)
                   if x.attribute == "learned_alias"]
        assert learned == [("obj:garage_cabinet", WORD)]

    def test_unscoped_two_referents_go_to_tier2_unwritten(self, world):
        _learn_kitchen_word(world)
        _judge(world, "obj:garage_cabinet")
        world.refer(WORD, scope="place:garage")
        _judge(world, "obj:garage_cabinet")
        head = world.buffer.head()
        r = world.refer(WORD)
        assert r.receipt["tier"] == 2
        assert r.receipt["candidates"] == ["obj:garage_cabinet", "obj:kitchen_cabinet"]
        assert world.buffer.head() == head

    def test_learned_words_are_not_identity(self, world, tmp_path):
        _learn_kitchen_word(world)
        _judge(world, "obj:garage_cabinet")
        world.refer(WORD, scope="place:garage")
        assert len(_learned_rows(world)) == 2
        head = world.buffer.head()
        assert world.registry.reconcile() == 0
        assert world.buffer.head() == head  # no merge, no proposal
        assert not [g for g in world.registry.name_collisions() if g["anchor"] == WORD]
        # Control: were the words `alias` rows, these two cabinets would merge.
        control = World(tmp_path / "control.world", world_id="w:control",
                        model=StubModel(fallback=rule_classifier_fallback()))
        try:
            _two_rooms(control)
            control.ingest_structured([
                {"entity": e, "attribute": "alias", "value": WORD, "timeless": True}
                for e in ("obj:kitchen_cabinet", "obj:garage_cabinet")
            ])
            assert control.registry.reconcile() == 1
        finally:
            control.close()

    def test_unique_kind_in_scope_outranks_a_learned_word(self, world):
        _two_rooms(world)
        _judge(world, "obj:kitchen_cabinet")
        world.refer("the cupboard", scope="place:kitchen")  # no cupboard here yet
        assert [(x.entity, x.value) for x in _learned_rows(world)] == [
            ("obj:kitchen_cabinet", "the cupboard")]
        world.ingest_structured([
            {"entity": "obj:pantry", "attribute": "kind", "value": "cupboard",
             "timeless": True},
            {"entity": "obj:pantry", "attribute": "in", "value": "place:kitchen"},
        ])
        r = world.refer("the cupboard", scope="place:kitchen")
        assert r.status == RESOLVED and r.entity_id == "obj:pantry"
        assert r.receipt["signals"] == ["unique_kind_in_scope"]


# ------------------------------------------------- the no-growth invariant


class TestReadsNeverGrowTheLog:
    """Spec Tests: on each ambiguous path, N identical reads leave the head
    unchanged, however confidently tier 2 picks."""

    N = 5

    def _read_n(self, world, *args, pick: str, **kw) -> None:
        head = world.buffer.head()
        for _ in range(self.N):
            _judge(world, pick)
            r = world.refer(*args, **kw)
            assert r.status == RESOLVED and r.entity_id == pick and r.receipt["tier"] == 2
        assert world.buffer.head() == head

    def test_tier1a_alias_collision(self, world):
        _two_rooms(world)
        world.ingest_structured([
            {"entity": e, "attribute": "alias", "value": "the lamp", "timeless": True}
            for e in ("obj:kitchen_cabinet", "obj:garage_cabinet")
        ])
        self._read_n(world, "the lamp", pick="obj:kitchen_cabinet")

    def test_tier1c_kind_pick(self, world):
        _two_rooms(world)
        world.ingest_structured([
            {"entity": "obj:spare_cabinet", "attribute": "kind", "value": "cabinet",
             "timeless": True},
            {"entity": "obj:spare_cabinet", "attribute": "in", "value": "place:kitchen"},
        ])
        self._read_n(world, "the cabinet", scope="place:kitchen",
                     pick="obj:kitchen_cabinet")

    def test_tier1d_learned_collision(self, world):
        _learn_kitchen_word(world)
        _judge(world, "obj:garage_cabinet")
        world.refer(WORD, scope="place:garage")
        self._read_n(world, WORD, pick="obj:kitchen_cabinet")
