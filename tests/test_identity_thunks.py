"""Identity (late binding, merges-as-events) and thunks (the drawer test)."""

import pytest

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import Classifier
from patternbuffer.identity import IdentityRegistry
from patternbuffer.indexes import Indexes
from patternbuffer.roles import _make_engine_roles
from patternbuffer.testing import StubModel
from patternbuffer.thunks import (
    DENY,
    INVENT_UNDER_CANON,
    OBSERVE_OR_UNKNOWN,
    UNKNOWN,
    Resolver,
    ResolutionDenied,
)


def make_parts(tmp_path, policy=INVENT_UNDER_CANON, name="w.world"):
    buf = PatternBuffer(tmp_path / name, world_id="w:test")
    stub = StubModel()
    classifier = Classifier(buf, stub)
    indexes = Indexes(buf, classifier)
    roles = _make_engine_roles()
    registry = IdentityRegistry(buf, roles["ingestor"])
    indexes.set_identity_resolver(registry.resolve)
    resolver = Resolver(buf, classifier, indexes, roles["resolver"], stub, policy)
    return buf, stub, classifier, indexes, roles, registry, resolver


class TestIdentity:
    def test_late_binding_reaches_old_rows(self, tmp_path):
        buf, stub, classifier, indexes, roles, registry, _ = make_parts(tmp_path)
        ing = roles["ingestor"]
        # Chapter 2: the unnamed clerk gets rows under a provisional id.
        buf.append(entity="person:clerk_tin_ear", attribute="kind", value="person",
                   status="stated", role=ing)
        registry.add_alias("person:clerk_tin_ear", "the clerk with the tin ear")
        buf.append(entity="person:clerk_tin_ear", attribute="deaf_side", value="left",
                   valid_from=1.0, status="stated", role=ing)
        # Chapter 3: named.
        buf.append(entity="person:ilsa_renn", attribute="name", value="Ilsa Renn",
                   status="stated", role=ing)
        registry.merge("person:clerk_tin_ear", "person:ilsa_renn",
                       evidence="ch3 naming: 'her name was Ilsa Renn'")
        stub.enqueue({"durability": "CONSTITUTIVE", "class_confidence": 0.9})  # deaf_side
        classifier.classify_all()

        canonical = registry.resolve("person:ilsa_renn")
        assert canonical == registry.resolve("person:clerk_tin_ear")
        # Every chapter-2 row is reachable through the merged identity.
        state = indexes.current_state(canonical)
        assert state["deaf_side"].winner.value == "left"
        assert registry.by_alias("The Clerk With The Tin Ear") == {canonical}
        assert registry.by_alias("ilsa renn") == {canonical}

    def test_merge_is_an_event_and_reversible(self, tmp_path):
        buf, stub, classifier, indexes, roles, registry, _ = make_parts(tmp_path)
        registry.merge("e:a", "e:b", evidence="weak hunch")
        assert registry.resolve("e:b") == registry.resolve("e:a")
        # Repair forward: retract the same_as edge; history rewrites never.
        edge = next(r for r in buf.all_rows() if r.attribute == "same_as")
        buf.append(entity=edge.id, attribute="retracts", value="bad merge",
                   status="retracted", role=roles["truth_maintenance"])
        assert registry.resolve("e:b") == "e:b"
        assert buf.get(edge.id) is not None  # the edge survives in the log

    def test_maybe_same_as_survives_unforced(self, tmp_path):
        buf, stub, classifier, indexes, roles, registry, _ = make_parts(tmp_path)
        registry.maybe_same_as("obj:drawer_1", "obj:desk_drawer", "grew finer entities")
        registry.maybe_same_as("obj:drawer_1", "obj:kitchen_drawer", "grew finer entities")
        assert registry.candidates("obj:drawer_1") == {"obj:desk_drawer", "obj:kitchen_drawer"}
        assert registry.resolve("obj:drawer_1") == "obj:drawer_1"  # not collapsed


class TestDrawer:
    """Whitepaper §1, literally: place, silence, retrieve identical."""

    def test_silence_is_persistence(self, tmp_path):
        buf, stub, classifier, indexes, roles, registry, _ = make_parts(tmp_path)
        ing = roles["ingestor"]
        buf.append(entity="obj:pipe", attribute="in", value="obj:drawer",
                   value_type="entity", valid_from=12.0, status="stated", role=ing)
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        classifier.classify_all()
        # Two hundred sessions of silence: nothing appended about the pipe.
        for i in range(200):
            buf.append(entity=f"event:session_{i}", attribute="kind", value="session",
                       status="stated", role=ing)
        assert indexes.fold_key("obj:pipe", "in", valid_as_of=212.0).winner.value == "obj:drawer"
        assert indexes.contents("obj:drawer") == ["obj:pipe"]

    def test_force_once_stable_across_instances(self, tmp_path):
        buf, stub, classifier, indexes, roles, registry, resolver = make_parts(tmp_path)
        ing = roles["ingestor"]
        buf.append(entity="obj:drawer", attribute="contents",
                   value={"policy": INVENT_UNDER_CANON}, value_type="unresolved",
                   valid_from=1.0, status="assumed", role=ing)
        classifier.classify_all()
        stub.enqueue({"items": [{"value": "a brass key"}, {"value": "two matchbooks"}]})
        first = resolver.resolve("obj:drawer", "contents")
        values = sorted(a.value for a in first)
        assert values == ["a brass key", "two matchbooks"]
        assert all(a.status == "generated" for a in first)

        # Second force: served from the memo, zero model calls.
        n = len(stub.calls)
        again = resolver.resolve("obj:drawer", "contents")
        assert sorted(a.value for a in again) == values
        assert len(stub.calls) == n

        # A cold instance over the same file serves the identical contents.
        buf2 = PatternBuffer(tmp_path / "w.world", world_id="w:test")
        stub2 = StubModel()
        cls2 = Classifier(buf2, stub2)
        idx2 = Indexes(buf2, cls2)
        resolver2 = Resolver(buf2, cls2, idx2, _make_engine_roles()["resolver"], stub2)
        cold = resolver2.resolve("obj:drawer", "contents")
        assert sorted(a.value for a in cold) == values
        assert stub2.calls == []
        buf2.close()

    def test_thunk_moves_without_resolving(self, tmp_path):
        buf, stub, classifier, indexes, roles, registry, resolver = make_parts(tmp_path)
        ing = roles["ingestor"]
        buf.append(entity="obj:footlocker", attribute="in", value="place:bazaar",
                   value_type="entity", valid_from=7.0, status="stated", role=ing)
        buf.append(entity="obj:footlocker", attribute="contents",
                   value={"policy": DENY, "constraints": ["sealed under crimp 0447"]},
                   value_type="unresolved", valid_from=7.0, status="assumed", role=ing)
        buf.append(entity="obj:footlocker", attribute="in", value="place:condenser_station",
                   value_type="entity", valid_from=21.0, status="stated", role=ing)
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        classifier.classify_all()

        # Moved, still sealed: the thunk rode along untouched.
        assert indexes.fold_key("obj:footlocker", "in").winner.value == "place:condenser_station"
        table = resolver.thunk_table()
        assert [(t.entity, t.aspect) for t in table] == [("obj:footlocker", "contents")]
        with pytest.raises(ResolutionDenied):
            resolver.resolve("obj:footlocker", "contents")

    def test_observe_or_unknown_never_invents(self, tmp_path):
        buf, stub, classifier, indexes, roles, registry, resolver = make_parts(
            tmp_path, policy=OBSERVE_OR_UNKNOWN
        )
        ing = roles["ingestor"]
        buf.append(entity="obj:box", attribute="contents",
                   value={"policy": OBSERVE_OR_UNKNOWN}, value_type="unresolved",
                   valid_from=1.0, status="assumed", role=ing)
        classifier.classify_all()
        assert resolver.resolve("obj:box", "contents") is UNKNOWN
        assert resolver.resolve("obj:never_seen", "contents") is UNKNOWN
        assert stub.calls == []  # no invention path was even attempted

    def test_constraint_inheritance_reaches_invention(self, tmp_path):
        buf, stub, classifier, indexes, roles, registry, resolver = make_parts(tmp_path)
        ing = roles["ingestor"]
        buf.append(entity="place:office", attribute="kind", value="detective_office",
                   status="stated", role=ing)
        buf.append(entity="place:office", attribute="era", value="c.1928 San Francisco",
                   status="stated", role=ing)
        buf.append(entity="obj:desk", attribute="in", value="place:office",
                   value_type="entity", valid_from=1.0, status="stated", role=ing)
        buf.append(entity="obj:desk", attribute="contents",
                   value={"policy": INVENT_UNDER_CANON}, value_type="unresolved",
                   valid_from=1.0, status="assumed", role=ing)
        stub.enqueue({"durability": "CONSTITUTIVE", "class_confidence": 0.9})  # era
        stub.enqueue({"durability": "CONSTITUTIVE", "class_confidence": 0.9})  # desk fixture
        classifier.classify_all()
        stub.enqueue({"items": [{"value": "a bottle of rye"}]})
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})  # feedback classify
        resolver.resolve("obj:desk", "contents")
        prompt = next(p for p, _ in stub.calls if p.startswith("Resolve an unestablished"))
        assert "c.1928 San Francisco" in prompt  # inherited from the containing scope
