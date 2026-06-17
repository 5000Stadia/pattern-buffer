"""WORLD-RETRIEVAL-V1: salience and bounded neighborhood reads."""

import json

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "retrieval.world", world_id="w:retrieval", model=stub)
    yield w
    w.close()


def _seed_neighborhood(w):
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:home", "attribute": "kind", "value": "building", "timeless": True},
        {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:study", "attribute": "in", "value": "place:home", "timeless": True},
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:study", "attribute": "connects_to", "value": "place:hall", "timeless": True},
        {"entity": "person:marn", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:marn", "attribute": "in", "value": "place:study", "valid_from": 1.0},
        {"entity": "person:ilsa", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:marn", "attribute": "ally_of", "value": "person:ilsa"},
        {"entity": "obj:lantern", "attribute": "kind", "value": "lantern", "timeless": True},
        {"entity": "obj:lantern", "attribute": "held_by", "value": "person:marn", "valid_from": 1.0},
        {"entity": "event:gift", "attribute": "kind", "value": "gift", "valid_from": 2.0},
        {"entity": "event:gift", "attribute": "agent", "value": "person:marn", "value_type": "entity", "valid_from": 2.0},
        {"entity": "event:gift", "attribute": "patient", "value": "person:ilsa", "value_type": "entity", "valid_from": 2.0},
        {"entity": "event:rumor", "attribute": "kind", "value": "rumor", "valid_from": 1.5},
        {"entity": "event:gift", "attribute": "caused_by", "value": "event:rumor", "value_type": "entity", "valid_from": 2.0},
    ])


def _neighbor_ids(out):
    return [n["entity"] for n in out["neighbors"]]


class TestAggregate:
    def test_numeric_ops_over_direct_members(self, world):
        world.ingest_structured([
            {"entity": "obj:backpack", "attribute": "kind", "value": "container",
             "timeless": True},
            {"entity": "obj:anvil", "attribute": "kind", "value": "item",
             "timeless": True},
            {"entity": "obj:anvil", "attribute": "in", "value": "obj:backpack",
             "valid_from": 1.0},
            {"entity": "obj:anvil", "attribute": "weight", "value": 7,
             "valid_from": 1.0},
            {"entity": "obj:book", "attribute": "kind", "value": "item",
             "timeless": True},
            {"entity": "obj:book", "attribute": "in", "value": "obj:backpack",
             "valid_from": 1.0},
            {"entity": "obj:book", "attribute": "weight", "value": 3,
             "valid_from": 1.0},
            {"entity": "obj:feather", "attribute": "kind", "value": "item",
             "timeless": True},
            {"entity": "obj:feather", "attribute": "in", "value": "obj:backpack",
             "valid_from": 1.0},
            {"entity": "obj:feather", "attribute": "weight", "value": 2,
             "valid_from": 1.0},
        ])
        assert world.aggregate("obj:backpack", "weight", "sum") == {
            "op": "sum",
            "value": 12,
            "count": 3,
            "members": ["obj:anvil", "obj:book", "obj:feather"],
            "container": "obj:backpack",
        }
        assert world.aggregate("obj:backpack", "weight", "count")["value"] == 3
        assert world.aggregate("obj:backpack", "weight", "min")["value"] == 2
        assert world.aggregate("obj:backpack", "weight", "max")["value"] == 7
        assert world.aggregate("obj:backpack", "weight", "avg")["value"] == 4.0

    def test_empty_container_returns_empty_rollups(self, world):
        world.ingest_structured([
            {"entity": "obj:empty", "attribute": "kind", "value": "container",
             "timeless": True},
        ])
        assert world.aggregate("obj:empty", "weight", "sum") == {
            "op": "sum",
            "value": 0,
            "count": 0,
            "members": [],
            "container": "obj:empty",
        }
        assert world.aggregate("obj:empty", "weight", "count")["value"] == 0
        assert world.aggregate("obj:empty", "weight", "min")["value"] is None
        assert world.aggregate("obj:empty", "weight", "max")["value"] is None
        assert world.aggregate("obj:empty", "weight", "avg")["value"] is None

    def test_recursive_subtree_is_opt_in(self, world):
        world.ingest_structured([
            {"entity": "obj:bag", "attribute": "kind", "value": "container",
             "timeless": True},
            {"entity": "obj:pouch", "attribute": "kind", "value": "container",
             "timeless": True},
            {"entity": "obj:pouch", "attribute": "in", "value": "obj:bag",
             "valid_from": 1.0},
            {"entity": "obj:apple", "attribute": "kind", "value": "item",
             "timeless": True},
            {"entity": "obj:apple", "attribute": "in", "value": "obj:bag",
             "valid_from": 1.0},
            {"entity": "obj:apple", "attribute": "weight", "value": 2,
             "valid_from": 1.0},
            {"entity": "obj:ring", "attribute": "kind", "value": "item",
             "timeless": True},
            {"entity": "obj:ring", "attribute": "in", "value": "obj:pouch",
             "valid_from": 1.0},
            {"entity": "obj:ring", "attribute": "weight", "value": 5,
             "valid_from": 1.0},
        ])
        direct = world.aggregate("obj:bag", "weight", "sum")
        recursive = world.aggregate("obj:bag", "weight", "sum", recursive=True)
        assert direct["value"] == 2
        assert direct["members"] == ["obj:apple"]
        assert recursive["value"] == 7
        assert recursive["members"] == ["obj:apple", "obj:ring"]

    def test_accrue_member_uses_folded_quantity(self, world):
        world.ingest_structured([
            {"entity": "place:party", "attribute": "kind", "value": "room",
             "timeless": True},
            {"entity": "person:rich", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:rich", "attribute": "in", "value": "place:party",
             "valid_from": 1.0},
            {"entity": "person:rich", "attribute": "gold", "value": 100,
             "fold_policy": "accrue", "valid_from": 1.0},
            {"entity": "person:rich", "attribute": "gold", "value": -25,
             "value_type": "delta", "valid_from": 2.0},
            {"entity": "person:poor", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:poor", "attribute": "in", "value": "place:party",
             "valid_from": 1.0},
            {"entity": "person:poor", "attribute": "gold", "value": 10,
             "valid_from": 1.0},
        ])
        out = world.aggregate("place:party", "gold", "sum")
        assert out["value"] == 85
        assert out["count"] == 2
        assert out["members"] == ["person:poor", "person:rich"]

    def test_non_numeric_missing_and_set_valued_members_are_skipped(self, world):
        world.ingest_structured([
            {"entity": "obj:box", "attribute": "kind", "value": "container",
             "timeless": True},
            {"entity": "obj:numeric", "attribute": "in", "value": "obj:box",
             "valid_from": 1.0},
            {"entity": "obj:numeric", "attribute": "weight", "value": 4,
             "valid_from": 1.0},
            {"entity": "obj:wordy", "attribute": "in", "value": "obj:box",
             "valid_from": 1.0},
            {"entity": "obj:wordy", "attribute": "weight", "value": "heavy",
             "valid_from": 1.0},
            {"entity": "obj:boolean", "attribute": "in", "value": "obj:box",
             "valid_from": 1.0},
            {"entity": "obj:boolean", "attribute": "weight", "value": True,
             "valid_from": 1.0},
            {"entity": "obj:missing", "attribute": "in", "value": "obj:box",
             "valid_from": 1.0},
            {"entity": "obj:numeric", "attribute": "tag", "value": 10,
             "arity": "set_valued", "valid_from": 1.0},
            {"entity": "obj:wordy", "attribute": "tag", "value": 20,
             "valid_from": 1.0},
        ])
        assert world.aggregate("obj:box", "weight", "sum") == {
            "op": "sum",
            "value": 4,
            "count": 1,
            "members": ["obj:numeric"],
            "container": "obj:box",
        }
        assert world.aggregate("obj:box", "tag", "sum") == {
            "op": "sum",
            "value": 0,
            "count": 0,
            "members": [],
            "container": "obj:box",
        }

    def test_frame_and_as_of_are_honored(self, world):
        world.ingest_structured([
            {"entity": "obj:bag", "attribute": "kind", "value": "container",
             "timeless": True},
            {"entity": "obj:stone", "attribute": "in", "value": "obj:bag",
             "valid_from": 1.0},
            {"entity": "obj:stone", "attribute": "weight", "value": 5,
             "valid_from": 1.0},
            {"entity": "obj:gem", "attribute": "in", "value": "obj:bag",
             "valid_from": 10.0},
            {"entity": "obj:gem", "attribute": "weight", "value": 7,
             "valid_from": 10.0},
        ])
        world.ingest_structured([
            {"entity": "obj:stone", "attribute": "in", "value": "obj:bag",
             "valid_from": 1.0},
            {"entity": "obj:stone", "attribute": "weight", "value": 2,
             "valid_from": 1.0},
        ], frame="knows:person:marn")
        assert world.aggregate(
            "obj:bag", "weight", "sum", frame="knows:person:marn"
        )["value"] == 2
        assert world.aggregate("obj:bag", "weight", "sum", as_of=5.0)["value"] == 5
        assert world.aggregate("obj:bag", "weight", "sum", as_of=11.0)["value"] == 12


class TestNeighborhood:
    def test_one_hop_returns_subject_location_contents_and_relations(self, world):
        _seed_neighborhood(world)
        out = world.neighborhood("person:marn", depth=1)
        ids = set(_neighbor_ids(out))
        assert out["subject"]["entity"] == "person:marn"
        assert out["subject"]["location"] == ["place:study", "place:home"]
        assert "place:study" in ids
        assert "obj:lantern" in ids
        assert "person:ilsa" in ids
        scores = [n["salience"] for n in out["neighbors"]]
        assert scores == sorted(scores, reverse=True)
        json.dumps(out)

    def test_depth_two_reaches_second_hop_and_events_causes(self, world):
        _seed_neighborhood(world)
        out = world.neighborhood("person:marn", depth=2)
        ids = set(_neighbor_ids(out))
        assert "place:hall" in ids        # marn -> study -> hall
        assert "event:rumor" in ids       # marn -> event:gift -> caused_by

    def test_caused_by_reached_through_merged_event(self, world):
        # Post-impl review: caused_by_of must be identity-closure-scoped — a
        # cause on a merged event's alias id must still be reachable.
        world.ingest_structured([
            {"entity": "person:marn", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "event:gift", "attribute": "kind", "value": "gift",
             "valid_from": 1.0},
            {"entity": "event:gift", "attribute": "agent", "value": "person:marn",
             "value_type": "entity", "valid_from": 1.0},
            {"entity": "event:rumor", "attribute": "kind", "value": "rumor",
             "valid_from": 0.5},
            {"entity": "event:gift_alias", "attribute": "caused_by",
             "value": "event:rumor", "value_type": "entity", "valid_from": 1.0},
        ])
        world.registry.merge("event:gift", "event:gift_alias", "same gift event")
        out = world.neighborhood("person:marn", depth=2, edge_kinds=["events"])
        assert "event:rumor" in set(_neighbor_ids(out))

    def test_depth_cap_is_three(self, world):
        w = world
        w.ingest_structured([
            {"entity": "obj:token", "attribute": "kind", "value": "token", "timeless": True},
            {"entity": "obj:a", "attribute": "kind", "value": "box", "timeless": True},
            {"entity": "obj:b", "attribute": "kind", "value": "box", "timeless": True},
            {"entity": "obj:c", "attribute": "kind", "value": "box", "timeless": True},
            {"entity": "obj:d", "attribute": "kind", "value": "box", "timeless": True},
            {"entity": "obj:token", "attribute": "in", "value": "obj:a", "valid_from": 1.0},
            {"entity": "obj:a", "attribute": "in", "value": "obj:b", "valid_from": 1.0},
            {"entity": "obj:b", "attribute": "in", "value": "obj:c", "valid_from": 1.0},
            {"entity": "obj:c", "attribute": "in", "value": "obj:d", "valid_from": 1.0},
        ])
        out = w.neighborhood("obj:token", depth=99, edge_kinds=["containment"])
        ids = set(_neighbor_ids(out))
        assert {"obj:a", "obj:b", "obj:c"} <= ids
        assert "obj:d" not in ids

    def test_edge_kinds_restrict_axes(self, world):
        _seed_neighborhood(world)
        out = world.neighborhood("person:marn", edge_kinds=["containment"])
        assert set(_neighbor_ids(out)) == {"place:study", "obj:lantern"}

    def test_identity_merged_neighbor_appears_once(self, world):
        _seed_neighborhood(world)
        world.ingest_structured([
            {"entity": "person:marn", "attribute": "trusts", "value": "obj:lamp_alias"},
        ])
        world.registry.merge("obj:lantern", "obj:lamp_alias", "same lantern")
        world.classifier.classify_all()
        out = world.neighborhood(
            "person:marn", edge_kinds=["containment", "relations"], depth=1
        )
        assert _neighbor_ids(out).count(world.registry.resolve("obj:lantern")) == 1

    def test_frame_and_as_of_are_honored(self, world):
        _seed_neighborhood(world)
        world.ingest_structured([
            {"entity": "person:marn", "attribute": "in", "value": "place:hall", "valid_from": 10.0},
        ])
        world.ingest_structured([
            {"entity": "person:marn", "attribute": "in", "value": "place:study", "valid_from": 1.0},
        ], frame="knows:person:marn")

        knows = world.neighborhood("person:marn", frame="knows:person:marn")
        assert "person:ilsa" not in set(_neighbor_ids(knows))
        assert knows["subject"]["location"] == ["place:study"]

        early = world.neighborhood("person:marn", as_of=5.0, edge_kinds=["containment"])
        late = world.neighborhood("person:marn", as_of=11.0, edge_kinds=["containment"])
        assert early["subject"]["location"][0] == "place:study"
        assert late["subject"]["location"][0] == "place:hall"

    def test_budget_drops_lowest_salience_but_keeps_constitutive_spine(self, world):
        world.ingest_structured([
            {"entity": "place:home", "attribute": "kind", "value": "building", "timeless": True},
            {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
            {"entity": "place:study", "attribute": "in", "value": "place:home", "timeless": True},
            {"entity": "obj:desk", "attribute": "kind", "value": "desk", "timeless": True},
            {"entity": "obj:desk", "attribute": "in", "value": "place:study", "timeless": True},
            {"entity": "obj:note", "attribute": "kind", "value": "note", "timeless": True},
            {"entity": "place:study", "attribute": "mentions", "value": "obj:note"},
        ])
        out = world.neighborhood(
            "place:study",
            edge_kinds=["containment", "relations"],
            budget=0,
        )
        ids = set(_neighbor_ids(out))
        assert {"place:home", "obj:desk"} <= ids
        assert "obj:note" not in ids
        assert out["truncated"] > 0

    def test_unresolved_deny_thunk_surfaces_unpainted(self, world):
        world.ingest_structured([
            {"entity": "obj:locker", "attribute": "kind", "value": "locker", "timeless": True},
            {"entity": "obj:locker", "attribute": "contents",
             "value": {"policy": "deny"}, "value_type": "unresolved"},
        ])
        head = world.buffer.head()
        out = world.neighborhood("obj:locker")
        unresolved = [
            f for f in out["subject"]["facts"]
            if f["attribute"] == "contents" and f["value_type"] == "unresolved"
        ]
        assert unresolved and unresolved[0]["status"] == "unresolved"
        assert unresolved[0]["policy"] == "deny"
        assert world.buffer.head() == head


class TestSalience:
    def test_heavily_referenced_recent_entity_outranks_stale_unreferenced(self, world):
        w = world
        w.ingest_structured([
            {"entity": "obj:stale", "attribute": "kind", "value": "relic", "timeless": True},
            {"entity": "obj:stale", "attribute": "condition", "value": "dusty", "valid_from": 1.0},
        ])
        w.ingestor.cursor.advance(20.0)
        w.ingest_structured([
            {"entity": "obj:hot", "attribute": "kind", "value": "beacon", "timeless": True},
            {"entity": "obj:hot", "attribute": "condition", "value": "lit", "valid_from": 20.0},
            *[
                {"entity": f"fact:ref_{i}", "attribute": "about", "value": "obj:hot"}
                for i in range(6)
            ],
        ])
        assert w.salience("obj:hot") > w.salience("obj:stale")
        assert w.state("obj:stale", "condition").winner.value == "dusty"

    def test_salience_rebuild_parity(self, world):
        _seed_neighborhood(world)
        before = {
            eid: world.salience(eid)
            for eid in ["person:marn", "place:study", "obj:lantern", "person:ilsa"]
        }
        world.buffer.raw_connection().execute("DROP TABLE sidecar_salience")
        world.buffer.raw_connection().commit()
        world.salience_index.rebuild()
        after = {
            eid: world.salience(eid)
            for eid in ["person:marn", "place:study", "obj:lantern", "person:ilsa"]
        }
        assert after == before

    def test_porcelain_verbs_are_json_serializable(self, world):
        _seed_neighborhood(world)
        out = world.porcelain.neighborhood("person:marn")
        assert isinstance(world.porcelain.salience("person:marn"), float)
        json.dumps(out)
