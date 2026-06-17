"""PORCELAIN-V1 contract tests (spec §4)."""

import json

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, StubModelExhausted, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "p.world", world_id="w:p", model=stub,
              stance="fiction", title="Porcelain Test World")
    w._stub = stub
    yield w
    w.close()


def _seed(w):
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "obj:desk", "attribute": "kind", "value": "desk", "timeless": True},
        {"entity": "obj:desk", "attribute": "in", "value": "place:study", "timeless": True},
        {"entity": "obj:pipe", "attribute": "kind", "value": "pipe", "timeless": True,
         "aliases": ["the pipe"]},
        {"entity": "obj:pipe", "attribute": "in", "value": "obj:desk"},
        {"entity": "fact:secret", "attribute": "kind", "value": "proposition", "timeless": True},
        {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"},
        {"entity": "person:rival", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "event:theft", "attribute": "kind", "value": "theft", "valid_from": 5.0},
        {"entity": "event:theft", "attribute": "agent", "value": "person:rival",
         "value_type": "entity", "valid_from": 5.0},
    ])
    # The player knows the pipe but not the culprit (frame copy):
    w.ingest_structured([
        {"entity": "obj:pipe", "attribute": "in", "value": "obj:desk"},
    ], frame="knows:person:player")


def _seed_gold(w):
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {
            "entity": "person:you",
            "attribute": "kind",
            "value": "person",
            "timeless": True,
            "aliases": ["you"],
        },
        {
            "entity": "person:you",
            "attribute": "gold",
            "value": 500,
            "fold_policy": "accrue",
            "valid_from": 1.0,
        },
        {
            "entity": "person:you",
            "attribute": "gold",
            "value": -20,
            "value_type": "delta",
            "valid_from": 2.0,
        },
    ])


class TestReceipts:
    def test_per_assertion_accounting(self, world):
        r = world.porcelain.ingest_structured([
            {"entity": "obj:cup", "attribute": "kind", "value": "cup", "timeless": True},
            {"entity": "obj:cup", "attribute": "located_in", "value": "place:study",
             "frame": "knows:person:player"},
        ], frame="canon")
        d = r.to_dict()
        assert d["world_id"] == "w:p"
        assert {row["frame"] for row in d["rows"]} >= {"canon", "knows:person:player"}
        assert any("located_in->in" in c for c in d["canonicalization_receipts"])
        json.dumps(d)  # JSON round-trip

    def test_ingest_source_post_application(self, world):
        _seed(world)
        world._stub.enqueue({"items": [
            {"entity": "obj:pipe", "attribute": "condition", "value": "scratched"},
        ]})
        r = world.porcelain.ingest("the pipe is scratched", source="person:dale", at=3.0)
        fact = next(x for x in r.rows if x["attribute"] == "condition")
        chain = world.buffer.visible(entity=fact["assertion_id"], attribute="source")
        assert chain and chain[0].value == "person:dale"
        cond = world.state("obj:pipe", "condition")
        # Speaker-source class engaged (027 machinery via post-applied chain):
        assert world.indexes._source_class(cond.winner, None) == "speaker:person:dale"


class TestZeroModelReads:
    def test_snapshot_contract(self, tmp_path):
        stub = StubModel()  # NO fallback: any model call raises
        w = World(tmp_path / "z.world", world_id="w:z", model=stub)
        w.ingestor.classify_inline = False
        w.ingest_structured([
            {"entity": "place:room", "attribute": "kind", "value": "room", "timeless": True},
            {"entity": "obj:box", "attribute": "kind", "value": "box", "timeless": True},
            {"entity": "obj:box", "attribute": "in", "value": "place:room", "timeless": True},
        ])
        for row in w.buffer.all_rows():
            w.classifier.set(row.id, "CONSTITUTIVE", 1.0)
        head = w.buffer.head()
        snap = w.porcelain.snapshot("place:room")
        assert snap["charter"]["stance"] == "fiction"
        assert any(f["entity"] == "obj:box" for f in snap["facts"])
        assert stub.calls == []          # zero model calls
        assert w.buffer.head() == head   # zero writes
        json.dumps(snap)
        w.close()

    def test_snapshot_rejects_references(self, world):
        out = world.porcelain.snapshot("the study")
        assert "error" in out

    def test_state_typed(self, world):
        _seed(world)
        assert world.porcelain.state("obj:pipe", "in")["status"] == "known"
        assert world.porcelain.state("obj:pipe", "smell")["status"] == "unknown"


class TestEventsAndDiff:
    def test_events_participants_all_of(self, world):
        _seed(world)
        evs = world.porcelain.events(kind="theft", participants="person:rival")
        assert len(evs) == 1 and evs[0]["agents"] == ["person:rival"]
        assert world.porcelain.events(participants=["person:rival", "person:nobody"]) == []

    def test_frame_diff_dramatic_irony(self, world):
        _seed(world)
        diff = world.porcelain.frame_diff("canon", "knows:person:player", ["fact:secret", "obj:pipe"])
        keys = {(f["entity"], f["attribute"]) for f in diff}
        assert ("fact:secret", "culprit") in keys      # the player doesn't know
        assert ("obj:pipe", "in") not in keys          # the player knows this
        # Divergence: player believes the pipe moved; canon disagrees.
        world.ingest_structured([
            {"entity": "obj:pipe", "attribute": "in", "value": "place:study",
             "valid_from": 6.0},
        ], frame="knows:person:player")
        diff2 = world.porcelain.frame_diff("canon", "knows:person:player", ["obj:pipe"])
        divergent = [f for f in diff2 if f["divergent"]]
        assert divergent and divergent[0]["b_value"] == "place:study"

    def test_frame_diff_set_valued_is_membership_not_winner(self, world):
        # A set-valued key diffs by membership: a member present in both
        # frames is NOT divergent (pre-fix it compared each member to B's
        # single winner, so every member but B's latest read as false
        # divergence). Only a member absent from B's set is reported.
        world.ingest_structured([
            {"entity": "obj:box", "attribute": "kind", "value": "container",
             "timeless": True},
            {"entity": "obj:box", "attribute": "tag", "value": "red",
             "arity": "set_valued"},
            {"entity": "obj:box", "attribute": "tag", "value": "blue"},
        ])
        world.ingest_structured([
            {"entity": "obj:box", "attribute": "tag", "value": "red"},
            {"entity": "obj:box", "attribute": "tag", "value": "blue"},
        ], frame="knows:person:player")
        tags = lambda: [f for f in world.porcelain.frame_diff(
            "canon", "knows:person:player", ["obj:box"]) if f["attribute"] == "tag"]
        assert tags() == []  # both members present in B -> no diff, no false divergence
        world.ingest_structured([
            {"entity": "obj:box", "attribute": "tag", "value": "green"}])
        out = tags()
        assert {f["value"] for f in out} == {"green"}     # only the canon-only member
        assert all(not f["divergent"] for f in out)       # absence, not divergence


class TestNumericQuantities:
    def test_snapshot_surfaces_quantity_not_ledger_rows(self, world):
        _seed_gold(world)
        snap = world.porcelain.snapshot("person:you")
        assert snap["quantities"] == [
            {"entity": "person:you", "attribute": "gold", "value": 480}
        ]
        assert not [f for f in snap["facts"] if f["attribute"] == "gold"]
        json.dumps(snap)

    def test_frame_diff_compares_accrue_quantities(self, world):
        _seed_gold(world)
        world.ingest_structured([
            {
                "entity": "person:you",
                "attribute": "gold",
                "value": 500,
                "valid_from": 1.0,
            },
        ], frame="knows:person:player")
        diff = world.porcelain.frame_diff(
            "canon", "knows:person:player", ["person:you"]
        )
        gold = [f for f in diff if (f["entity"], f["attribute"]) == ("person:you", "gold")]
        assert len(gold) == 1
        assert gold[0]["value"] == 480
        assert gold[0]["b_value"] == 500
        assert gold[0]["divergent"] is True
        assert all(f["value"] != -20 for f in gold)

    def test_ask_returns_accrue_total(self, world):
        _seed_gold(world)
        world._stub.enqueue({
            "refer_targets": ["you"],
            "keys": [{"target_index": 0, "attribute": "gold"}],
            "wants_location": False,
            "wants_events": False,
        })
        answer = world.porcelain.ask("how much gold do I have?")
        assert answer.answered
        assert answer.facts[0]["attribute"] == "gold"
        assert answer.facts[0]["value"] == 480

    def test_where_numeric_predicate_folds_before_compare(self, world):
        world.ingest_structured([
            {
                "entity": "person:rich",
                "attribute": "gold",
                "value": 150,
                "fold_policy": "accrue",
                "valid_from": 1.0,
            },
            {
                "entity": "person:rich",
                "attribute": "gold",
                "value": -20,
                "value_type": "delta",
                "valid_from": 2.0,
            },
            {
                "entity": "person:poor",
                "attribute": "gold",
                "value": 90,
                "valid_from": 1.0,
            },
            {
                "entity": "person:future",
                "attribute": "gold",
                "value": 150,
                "valid_from": 10.0,
            },
            {"entity": "person:wordy", "attribute": "rank", "value": "high"},
            {"entity": "person:boolean", "attribute": "score", "value": True},
            {"entity": "person:numeric", "attribute": "score", "value": 3},
        ])
        assert world.porcelain.where("gold", ">=", 100, as_of=5.0) == ["person:rich"]
        assert world.porcelain.where("gold", ">=", 100) == [
            "person:future",
            "person:rich",
        ]
        assert world.porcelain.where("rank", ">=", 0) == []
        assert world.porcelain.where("score", ">", 0) == ["person:numeric"]


class TestResolveAndAsk:
    def test_resolve_typed_denied(self, world):
        _seed(world)
        world.ingest_structured([
            {"entity": "obj:locker", "attribute": "kind", "value": "locker", "timeless": True},
            {"entity": "obj:locker", "attribute": "contents",
             "value": {"policy": "deny"}, "value_type": "unresolved"},
        ])
        out = world.porcelain.resolve("obj:locker", "contents")
        assert out["status"] == "denied"

    def test_ask_with_provenance_and_asks(self, world):
        _seed(world)
        world._stub.enqueue({"refer_targets": ["the pipe"], "keys": [],
                             "wants_location": True})
        a = world.porcelain.ask("where is the pipe?")
        assert a.answered and a.facts[0]["provenance"]["assertion_id"]
        assert a.facts[0]["chain"] == ["place:study"] or a.facts[0]["value"] == "obj:desk"
        json.dumps(a.to_dict())


class TestReviewR4:
    def test_snapshot_id_grammar(self, world):
        assert "error" in world.porcelain.snapshot("the:study")
        assert "error" in world.porcelain.snapshot("Place:Study")

    def test_resolve_receipt_on_all_paths(self, world):
        _seed(world)
        out = world.porcelain.resolve("obj:never_seen", "contents")
        assert "receipt" in out and out["receipt"]["seq_range"] is None

    def test_ask_wants_events(self, world):
        _seed(world)
        world._stub.enqueue({"refer_targets": ["person:rival"], "keys": [],
                             "wants_events": True})
        a = world.porcelain.ask("what has the rival done?")
        evs = [f for f in a.facts if "event" in f]
        assert evs and evs[0]["event"]["kind"] == "theft"


def _seed_spoon(w):
    """marn in a room; a brass measuring spoon on a table in that room."""
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:room", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "person:marn", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:marn", "attribute": "in", "value": "place:room"},
        {"entity": "obj:table", "attribute": "kind", "value": "table", "timeless": True},
        {"entity": "obj:table", "attribute": "in", "value": "place:room"},
        {"entity": "obj:spoon", "attribute": "kind", "value": "spoon", "timeless": True,
         "aliases": ["brass measuring spoon"]},
        {"entity": "obj:spoon", "attribute": "in", "value": "obj:table"},
    ])
    # marn knows where the spoon is (sparse knowledge-frame copy):
    w.ingest_structured([
        {"entity": "obj:spoon", "attribute": "in", "value": "obj:table"},
    ], frame="knows:person:marn")


class TestAskReferParity:
    """HD 003: ask()-path reference binding reaches observe-path parity."""

    def test_possessive_named_reference_binds(self, world):
        _seed_spoon(world)
        world._stub.enqueue({"refer_targets": ["my brass measuring spoon"],
                             "keys": [], "wants_location": True})
        a = world.porcelain.ask("Where is my brass measuring spoon?",
                                frame="knows:person:marn")
        assert a.answered and a.facts[0]["value"] == "obj:table"

    def test_possessive_kind_reference_binds_via_scope(self, world):
        _seed_spoon(world)
        world._stub.enqueue({"refer_targets": ["my spoon"],
                             "keys": [], "wants_location": True})
        a = world.porcelain.ask("Where is my spoon?", frame="knows:person:marn")
        assert a.answered and a.facts[0]["value"] == "obj:table"

    def test_strip_determiner(self, world):
        strip = world.refer._strip_determiner
        for det in ("the", "a", "an", "my", "your", "his", "her", "its",
                    "their", "our"):
            assert strip(f"{det} spoon") == "spoon"
        assert strip("brass measuring spoon") == "brass measuring spoon"

    def test_knowledge_absence_no_leak(self, world):
        # A spoon marn does NOT know about: binds in canon, no in-frame fact.
        _seed_spoon(world)
        world.ingest_structured([
            {"entity": "obj:fork", "attribute": "kind", "value": "fork",
             "timeless": True, "aliases": ["silver fork"]},
            {"entity": "obj:fork", "attribute": "in", "value": "obj:table"},
        ])  # canon only; not copied into knows:person:marn
        world._stub.enqueue({"refer_targets": ["my silver fork"],
                             "keys": [], "wants_location": True})
        a = world.porcelain.ask("Where is my silver fork?",
                                frame="knows:person:marn")
        assert not a.answered  # no knows:marn fact about the fork's location
