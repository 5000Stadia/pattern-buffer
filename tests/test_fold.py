"""Durability-aware fold, walks, and truth maintenance (spec §7, §12)."""

import pytest

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import Classifier
from patternbuffer.indexes import Indexes
from patternbuffer.roles import _make_engine_roles
from patternbuffer.testing import StubModel
from patternbuffer.tmaint import TruthMaintenance


@pytest.fixture
def world_parts(tmp_path):
    buf = PatternBuffer(tmp_path / "w.world", world_id="w:test")
    stub = StubModel()
    classifier = Classifier(buf, stub)
    indexes = Indexes(buf, classifier)
    roles = _make_engine_roles()
    tm = TruthMaintenance(buf, classifier, indexes, roles["truth_maintenance"])
    yield buf, stub, classifier, indexes, tm, roles
    buf.close()


def _stated(buf, roles, entity, attribute, value, **kw):
    kw.setdefault("value_type", "entity" if isinstance(value, str) and ":" in value else "literal")
    return buf.append(
        entity=entity, attribute=attribute, value=value, status="stated",
        role=roles["ingestor"], **kw,
    )


class TestContainmentFamilyMove:
    def test_worn_by_supersedes_in_as_one_operation(self, world_parts):
        buf, stub, classifier, indexes, tm, roles = world_parts
        _stated(buf, roles, "obj:jacket", "in", "obj:box", valid_from=1.0)
        _stated(buf, roles, "obj:jacket", "worn_by", "person:morpheus", valid_from=2.0)
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})  # movable in box
        classifier.classify_all()

        # One parent: the family folds as one key; the box derives to empty.
        result = indexes.fold_key("obj:jacket", "in")
        assert result.winner.value == "person:morpheus"
        assert indexes.contents("obj:box") == []
        assert indexes.contents("person:morpheus") == ["obj:jacket"]
        # Both rows remain in the log.
        assert len(buf.all_rows()) == 2
        # And as-of t=1 the jacket is still in the box.
        assert indexes.fold_key("obj:jacket", "in", valid_as_of=1.5).winner.value == "obj:box"

    def test_no_llm_on_deterministic_reads(self, world_parts):
        buf, stub, classifier, indexes, tm, roles = world_parts
        _stated(buf, roles, "obj:pipe", "in", "obj:drawer", valid_from=1.0)
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        classifier.classify_all()
        # Classification spent the only scripted response; every read
        # below must make no model call at all.
        indexes.locate("obj:pipe")
        indexes.contents("obj:drawer")
        indexes.current_state("obj:pipe")
        indexes.path("obj:pipe", "obj:drawer")
        assert stub.calls != []  # classification consulted the model...
        n = len(stub.calls)
        indexes.locate("obj:pipe")
        assert len(stub.calls) == n  # ...but reads never do (P7)


class TestLocate:
    def test_tree_walk(self, world_parts):
        buf, stub, classifier, indexes, tm, roles = world_parts
        _stated(buf, roles, "obj:pipe", "in", "obj:drawer", valid_from=1.0)
        _stated(buf, roles, "obj:drawer", "in", "place:study", valid_from=1.0)
        _stated(buf, roles, "place:study", "in", "place:home", valid_from=1.0)
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})    # pipe in drawer
        stub.enqueue({"durability": "CONSTITUTIVE", "class_confidence": 0.9})  # drawer fixture
        stub.enqueue({"durability": "CONSTITUTIVE", "class_confidence": 0.9})  # study fixture
        classifier.classify_all()
        assert indexes.locate("obj:pipe") == ["obj:drawer", "place:study", "place:home"]


class TestConstitutiveConflict:
    def test_flagged_coexistence_never_silent_merge(self, world_parts):
        buf, stub, classifier, indexes, tm, roles = world_parts
        a1 = _stated(buf, roles, "place:anchor", "working_reactors", 2, value_type="literal")
        a2 = _stated(buf, roles, "place:anchor", "working_reactors", 3, value_type="literal")
        stub.enqueue({"durability": "CONSTITUTIVE", "class_confidence": 0.9})
        stub.enqueue({"durability": "CONSTITUTIVE", "class_confidence": 0.9})
        classifier.classify_all()

        result = indexes.fold_key("place:anchor", "working_reactors")
        assert result.conflicted
        assert result.winner.id == a1.id  # earliest-established served
        assert set(result.conflicting) == {a1.id, a2.id}  # both coexist

        conflicts = tm.scan()
        assert len(conflicts) == 1
        assert conflicts[0].kind == "constitutive_contradiction"
        # The flag persists in the sidecar and both rows survive the log.
        assert tm.open_conflicts()[0].assertion_ids == conflicts[0].assertion_ids
        assert buf.get(a1.id) and buf.get(a2.id)

    def test_resolution_is_an_explicit_append(self, world_parts):
        buf, stub, classifier, indexes, tm, roles = world_parts
        a1 = _stated(buf, roles, "place:anchor", "working_reactors", 2)
        a2 = _stated(buf, roles, "place:anchor", "working_reactors", 3)
        stub.enqueue({"durability": "CONSTITUTIVE", "class_confidence": 0.9})
        stub.enqueue({"durability": "CONSTITUTIVE", "class_confidence": 0.9})
        classifier.classify_all()
        tm.retract(a1, "author correction: three reactors")
        assert indexes.fold_key("place:anchor", "working_reactors").winner.id == a2.id
        assert tm.scan() == []


class TestCrossSource:
    def _letter_then_core(self, world_parts, core_value):
        buf, stub, classifier, indexes, tm, roles = world_parts
        claim = _stated(
            buf, roles, "place:anchor", "reserve_gap_liters", {"gte": 40000},
            value_type="literal", valid_from=2.0,
        )
        buf.append(  # document trust chain: the claim's source is the letter
            entity=claim.id, attribute="source", value="doc:tovan_letter",
            status="stated", role=roles["ingestor"],
        )
        confirm = _stated(
            buf, roles, "place:anchor", "reserve_gap_liters", core_value,
            value_type="literal", valid_from=3.0,
        )
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        classifier.classify_all()
        return claim, confirm

    def test_agreeing_value_corroborates(self, world_parts):
        buf, stub, classifier, indexes, tm, roles = world_parts
        claim, confirm = self._letter_then_core(world_parts, 41200)
        result = indexes.fold_key("place:anchor", "reserve_gap_liters")
        assert not result.conflicted
        assert result.winner.id == confirm.id  # the more precise value serves
        assert result.corroborated_by == (confirm.id,)
        assert tm.scan() == []  # converging chains: no flag, no ask

    def test_disagreeing_value_flags_and_keeps_incumbent(self, world_parts):
        buf, stub, classifier, indexes, tm, roles = world_parts
        claim, confirm = self._letter_then_core(world_parts, 12000)  # < gte bound
        result = indexes.fold_key("place:anchor", "reserve_gap_liters")
        assert result.conflicted
        assert result.winner.id == claim.id  # never silent last-write-wins
        assert any(c.kind == "cross_source" for c in tm.scan())


class TestDispositionalAndRebuild:
    def test_dispositional_defeasible_by_recency(self, world_parts):
        buf, stub, classifier, indexes, tm, roles = world_parts
        _stated(buf, roles, "person:dale", "restocks", "mondays", value_type="literal", valid_from=1.0)
        _stated(buf, roles, "person:dale", "restocks", "tuesdays", value_type="literal", valid_from=9.0)
        stub.enqueue({"durability": "DISPOSITIONAL", "class_confidence": 0.9})
        stub.enqueue({"durability": "DISPOSITIONAL", "class_confidence": 0.9})
        classifier.classify_all()
        assert indexes.fold_key("person:dale", "restocks").winner.value == "tuesdays"

    def test_sidecar_rebuild_equals_original(self, world_parts):
        buf, stub, classifier, indexes, tm, roles = world_parts
        _stated(buf, roles, "place:room", "kind", "room", value_type="literal")
        _stated(buf, roles, "obj:cup", "in", "place:room", valid_from=1.0)
        stub.enqueue({"durability": "STATE", "class_confidence": 0.8})
        classifier.classify_all()
        before = {r.id: classifier.durability(r.id) for r in buf.all_rows()}
        stub.enqueue({"durability": "STATE", "class_confidence": 0.8})
        classifier.rebuild()
        after = {r.id: classifier.durability(r.id) for r in buf.all_rows()}
        assert before == after


class TestLateralGraph:
    def test_path_and_non_connection(self, world_parts):
        buf, stub, classifier, indexes, tm, roles = world_parts
        for a, b in [
            ("place:council_tier", "place:gallery_stairs"),
            ("place:gallery_stairs", "place:bazaar"),
            ("place:bazaar", "place:service_gate"),
            ("place:service_gate", "place:dead_stairs"),
            ("place:dead_stairs", "place:seed_vault"),
        ]:
            _stated(buf, roles, a, "connects_to", b)
        classifier.classify_all()  # all guardrail-classified, no model calls
        long_way = indexes.path("place:council_tier", "place:seed_vault")
        assert long_way is not None and len(long_way) == 6
        # Vertical proximity is not connectivity: no edge, no path.
        assert indexes.path("place:council_tier", "place:wellhead") is None
        assert stub.calls == []


class TestAssumptionQuarantine:
    def test_assumed_yields_to_observed(self, world_parts):
        """An explicitly-provisional assumption never holds incumbency
        against later direct observation (whitepaper §7/§15)."""
        buf, stub, classifier, indexes, tm, roles = world_parts
        ing = roles["ingestor"]
        buf.append(entity="obj:core", attribute="in", value="place:theory_vault",
                   value_type="entity", valid_from=7.0, status="assumed", role=ing)
        buf.append(entity="obj:core", attribute="in", value="place:seed_vault",
                   value_type="entity", valid_from=9.0, status="observed", role=ing)
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        classifier.classify_all()
        result = indexes.fold_key("obj:core", "in", valid_as_of=10.0)
        assert not result.conflicted
        assert result.winner.value == "place:seed_vault"
        # Before the observation, the assumption still serves (it is the
        # only thing known) — provisional, but honest.
        early = indexes.fold_key("obj:core", "in", valid_as_of=8.0, asserted_as_of=1)
        assert early.winner.value == "place:theory_vault"

    def test_inference_yields_to_stated_canon(self, world_parts):
        """Evidence rank: a wrong inference never outholds later authored
        truth (chapter-test run-3 finding, generalizing the quarantine)."""
        buf, stub, classifier, indexes, tm, roles = world_parts
        ing = roles["ingestor"]
        buf.append(entity="obj:core", attribute="in", value="place:wrong_vault",
                   value_type="entity", valid_from=0.0, status="inferred", role=ing)
        buf.append(entity="obj:core", attribute="in", value="place:seed_vault",
                   value_type="entity", valid_from=3.0, valid_to=8.0,
                   status="stated", role=ing)
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        classifier.classify_all()
        result = indexes.fold_key("obj:core", "in", valid_as_of=4.5)
        assert not result.conflicted          # correction, not a conflict
        assert result.winner.value == "place:seed_vault"
        # The inference still serves where it is all that exists:
        early = indexes.fold_key("obj:core", "in", valid_as_of=1.0,
                                 asserted_as_of=1)
        assert early.winner.value == "place:wrong_vault"
