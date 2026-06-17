"""Durability-aware fold, walks, and truth maintenance (spec §7, §12)."""

import pytest

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import Classifier
from patternbuffer.indexes import Indexes
from patternbuffer.roles import _make_engine_roles
from patternbuffer.testing import StubModel, rule_classifier_fallback
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


class TestContainmentCrossSourceMove:
    """HD 002 finding 2: a later move supersedes an earlier cross-source
    placement (movement is time-sequential) — only a same-latest-valid-time
    cross-source disagreement is a genuine contradiction."""

    def _doc(self, buf, roles, entity, value, vf, doc="doc:letter"):
        row = _stated(buf, roles, entity, "in", value, valid_from=vf)
        buf.append(entity=row.id, attribute="source", value=doc,
                   status="stated", role=roles["ingestor"])
        return row

    def test_later_direct_move_supersedes_document(self, world_parts):
        buf, stub, classifier, indexes, tm, roles = world_parts
        self._doc(buf, roles, "person:marn", "place:council_tier", 4.0)  # document
        direct = _stated(buf, roles, "person:marn", "in", "place:wellhead",
                         valid_from=1003.0)  # direct narration, no source
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        classifier.classify_all()
        result = indexes.fold_key("person:marn", "in")
        assert not result.conflicted and result.winner.id == direct.id
        # History intact, no retraction needed: as-of t=4 still council_tier.
        early = indexes.fold_key("person:marn", "in", valid_as_of=4.0)
        assert early.winner.value == "place:council_tier"

    def test_same_valid_time_cross_source_still_flags(self, world_parts):
        buf, stub, classifier, indexes, tm, roles = world_parts
        self._doc(buf, roles, "person:marn", "place:council_tier", 10.0)  # document
        _stated(buf, roles, "person:marn", "in", "place:wellhead",
                valid_from=10.0)  # direct, same valid-time -> real contradiction
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        classifier.classify_all()
        result = indexes.fold_key("person:marn", "in")
        assert result.conflicted and len(result.conflicting) == 2


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

    def test_same_valid_time_contradiction_flags(self, world_parts):
        """Supersession requires world-time progression: two same-class rows
        tied on valid_from with different values are a simultaneous
        contradiction — flagged, never silently ordered by log sequence
        (run-4 finding)."""
        buf, stub, classifier, indexes, tm, roles = world_parts
        ing = roles["ingestor"]
        a1 = buf.append(entity="place:anchor", attribute="working_reactors",
                        value=2, valid_from=3.0, status="stated", role=ing)
        a2 = buf.append(entity="place:anchor", attribute="working_reactors",
                        value=3, valid_from=3.0, status="stated", role=ing)
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        classifier.classify_all()
        result = indexes.fold_key("place:anchor", "working_reactors")
        assert result.conflicted
        assert result.winner.id == a1.id  # earliest-asserted served
        assert set(result.conflicting) == {a1.id, a2.id}
        # Genuine progression (later valid_from) still supersedes silently:
        buf.append(entity="place:anchor", attribute="working_reactors",
                   value=3, valid_from=9.0, status="stated", role=ing)
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        classifier.classify_all()
        later = indexes.fold_key("place:anchor", "working_reactors", valid_as_of=10.0)
        assert later.winner.value == 3 and not later.conflicted

    def test_set_valued_attributes_never_conflict(self, world_parts):
        """Two names are data, not a dispute: conflict detection requires a
        functional key (run-4 finding)."""
        buf, stub, classifier, indexes, tm, roles = world_parts
        ing = roles["ingestor"]
        buf.append(entity="obj:meter", attribute="name", value="master meter",
                   status="stated", role=ing)
        buf.append(entity="obj:meter", attribute="name", value="the master meter",
                   status="stated", role=ing)
        classifier.classify_all()
        assert tm.scan() == []

    def test_stated_supersedes_observed_in_movement(self, world_parts):
        """stated and observed without document chains are one supersession
        class — ordinary movement supersedes across them (run-4 finding)."""
        buf, stub, classifier, indexes, tm, roles = world_parts
        ing = roles["ingestor"]
        buf.append(entity="obj:case", attribute="in", value="place:seed_vault",
                   value_type="entity", valid_from=8.0, status="observed", role=ing)
        buf.append(entity="obj:case", attribute="in", value="place:records_vault",
                   value_type="entity", valid_from=12.0, status="stated", role=ing)
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        classifier.classify_all()
        result = indexes.fold_key("obj:case", "in", valid_as_of=16.0)
        assert not result.conflicted
        assert result.winner.value == "place:records_vault"

    def test_accrual_promotion(self, world_parts):
        """Whitepaper 5.1: 3+ same-value STATE observations at distinct
        valid times promote to DISPOSITIONAL — the world learns a habit."""
        buf, stub, classifier, indexes, tm, roles = world_parts
        ing = roles["ingestor"]
        for day in (1.0, 8.0, 15.0):
            buf.append(entity="person:dale", attribute="restocks_on", value="monday",
                       valid_from=day, status="observed", role=ing)
        buf.append(entity="person:dale", attribute="mood", value="tired",
                   valid_from=1.0, status="observed", role=ing)
        buf.append(entity="person:dale", attribute="mood", value="tired",
                   valid_from=2.0, status="observed", role=ing)
        for _ in range(5):
            stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        classifier.classify_all()
        n = classifier.promote_accruals(threshold=3)
        assert n == 3  # the three restock observations; mood (2x) stays STATE
        assert classifier.durability(
            next(r.id for r in buf.all_rows() if r.attribute == "restocks_on")
        ) == "DISPOSITIONAL"
        assert classifier.durability(
            next(r.id for r in buf.all_rows() if r.attribute == "mood")
        ) == "STATE"
        # The fold now treats the habit as dispositional (defeasible).
        fold = indexes.fold_key("person:dale", "restocks_on")
        assert fold.winner.value == "monday"

    def test_read_path_scales_with_closure_not_log(self, world_parts):
        """037 (HD live finding): a fold deserializes O(closure) rows, never
        O(log). Grow-and-requery must not compound."""
        buf, stub, classifier, indexes, tm, roles = world_parts
        ing = roles["ingestor"]
        buf.append(entity="obj:pipe", attribute="in", value="obj:drawer",
                   value_type="entity", valid_from=1.0, status="stated", role=ing)
        stub.enqueue({"durability": "STATE", "class_confidence": 0.9})
        classifier.classify_all()
        # Grow the log with 1500 unrelated rows (a long play session).
        for i in range(1500):
            buf.append(entity=f"obj:filler_{i}", attribute="hue", value=i,
                       valid_from=float(i), status="stated", role=ing)
        before = buf.rows_read
        result = indexes.fold_key("obj:pipe", "in")
        cost = buf.rows_read - before
        assert result.winner.value == "obj:drawer"
        assert cost < 50, f"fold deserialized {cost} rows on a 1500-row log"
        # And contents() — the value-indexed walk — stays closure-cheap too.
        before = buf.rows_read
        assert indexes.contents("obj:drawer") == ["obj:pipe"]
        assert buf.rows_read - before < 50


class TestAttributeSemanticsMultiValue:
    def _world(self, tmp_path, **kw):
        from patternbuffer import World
        from patternbuffer.testing import rule_classifier_fallback

        return World(
            tmp_path / "sem.world",
            world_id="w:sem",
            model=StubModel(fallback=rule_classifier_fallback()),
            **kw,
        )

    def test_declared_set_valued_contains_keeps_all_members(self, tmp_path):
        w = self._world(tmp_path)
        try:
            w.ingest_structured([
                {
                    "entity": "obj:tin",
                    "attribute": "contains",
                    "value": f"obj:cig_{i}",
                    "arity": "set_valued",
                }
                for i in range(1, 6)
            ])
            fold = w.state("obj:tin", "contains")
            assert fold.winner.value == "obj:cig_5"
            assert set(fold.values) == {f"obj:cig_{i}" for i in range(1, 6)}
        finally:
            w.close()


class TestNumericQuantities:
    def _world(self, tmp_path, name="qty"):
        from patternbuffer import World

        return World(
            tmp_path / f"{name}.world",
            world_id=f"w:{name}",
            model=StubModel(fallback=rule_classifier_fallback()),
        )

    def test_gold_ledger_folds_to_quantity(self, tmp_path):
        w = self._world(tmp_path, "gold")
        try:
            w.ingest_structured([
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
            fold = w.state("person:you", "gold")
            assert fold.quantity == 480
            assert isinstance(fold.quantity, int)
            assert fold.winner.value == -20
            assert len(fold._ledger_rows) == 2
            assert fold._value_rows == ()

            early = w.state("person:you", "gold", valid_as_of=1.5)
            assert early.quantity == 500
            assert len(early._ledger_rows) == 1
        finally:
            w.close()

    def test_stray_delta_does_not_suppress_unresolved_thunk(self, tmp_path):
        # Post-impl review #1: a value_type=delta on a NON-accrue attribute
        # must be dropped BEFORE the thunk filter, or it makes an unresolved
        # placeholder look resolved and the key folds to nothing.
        from patternbuffer.thunks import INVENT_UNDER_CANON

        w = self._world(tmp_path, "thunk")
        try:
            w.ingest_structured([
                {"entity": "obj:box", "attribute": "contents",
                 "value": {"policy": INVENT_UNDER_CANON}, "value_type": "unresolved",
                 "valid_from": 1.0, "status": "assumed"},
                {"entity": "obj:box", "attribute": "contents",
                 "value": -1, "value_type": "delta", "valid_from": 2.0},
            ])
            fold = w.state("obj:box", "contents")
            assert fold.winner is not None
            assert fold.winner.value_type == "unresolved"  # thunk survived
        finally:
            w.close()

    def test_delta_composition_and_retraction_correction(self, tmp_path):
        w = self._world(tmp_path, "compose")
        try:
            rows = w.ingest_structured([
                {
                    "entity": "person:you",
                    "attribute": "gold",
                    "value": 500,
                    "value_type": "delta",
                    "fold_policy": "accrue",
                    "valid_from": 1.0,
                },
                {
                    "entity": "person:you",
                    "attribute": "gold",
                    "value": 300,
                    "value_type": "delta",
                    "valid_from": 2.0,
                },
                {
                    "entity": "person:you",
                    "attribute": "gold",
                    "value": -20,
                    "value_type": "delta",
                    "valid_from": 3.0,
                },
            ])
            assert w.state("person:you", "gold").quantity == 780
            spend = next(r for r in rows if r.attribute == "gold" and r.value == -20)
            w.truth.retract(spend.id, "correction: spend did not happen")
            assert w.state("person:you", "gold").quantity == 800
        finally:
            w.close()

    def test_concurrent_deltas_same_valid_time_both_count(self, tmp_path):
        w = self._world(tmp_path, "concurrent")
        try:
            w.ingest_structured([
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
                {
                    "entity": "person:you",
                    "attribute": "gold",
                    "value": -20,
                    "value_type": "delta",
                    "valid_from": 2.0,
                },
            ])
            fold = w.state("person:you", "gold")
            assert fold.quantity == 460
            assert [r.value for r in fold._ledger_rows] == [500, -20, -20]
        finally:
            w.close()

    def test_int_and_float_quantities(self, tmp_path):
        w = self._world(tmp_path, "float")
        try:
            w.ingest_structured([
                {
                    "entity": "place:cistern",
                    "attribute": "liters",
                    "value": 40000.0,
                    "fold_policy": "accrue",
                    "valid_from": 1.0,
                },
                {
                    "entity": "place:cistern",
                    "attribute": "liters",
                    "value": -1250.5,
                    "value_type": "delta",
                    "valid_from": 2.0,
                },
            ])
            fold = w.state("place:cistern", "liters")
            assert fold.quantity == 38749.5
            assert isinstance(fold.quantity, float)
        finally:
            w.close()

    def test_delta_on_non_accrue_is_ignored_not_rejected(self, tmp_path):
        w = self._world(tmp_path, "nonaccrue")
        try:
            w.ingest_structured([
                {
                    "entity": "obj:meter",
                    "attribute": "charge",
                    "value": 5,
                    "value_type": "delta",
                    "valid_from": 1.0,
                },
            ])
            ignored = w.state("obj:meter", "charge")
            assert ignored.winner is None
            assert ignored.quantity is None

            w.ingest_structured([
                {
                    "entity": "obj:meter",
                    "attribute": "charges",
                    "value": 5,
                    "value_type": "delta",
                    "fold_policy": "accrue",
                    "valid_from": 1.0,
                },
            ])
            assert w.state("obj:meter", "charges").quantity == 5
        finally:
            w.close()

    def test_functional_with_data_cannot_become_accrue(self, tmp_path):
        w = self._world(tmp_path, "immutable_accrue")
        try:
            w.ingest_structured([
                {"entity": "person:you", "attribute": "score", "value": 10},
            ])
            with pytest.raises(ValueError, match="after folded data"):
                w.ingest_structured([
                    {
                        "entity": "person:you",
                        "attribute": "score",
                        "value": 5,
                        "value_type": "delta",
                        "fold_policy": "accrue",
                    },
                ])
        finally:
            w.close()

    def test_undeclared_contains_remains_single_winner(self, tmp_path):
        w = self._world(tmp_path)
        try:
            w.ingest_structured([
                {"entity": "obj:tin", "attribute": "contains", "value": f"obj:cig_{i}"}
                for i in range(1, 6)
            ])
            fold = w.state("obj:tin", "contains")
            assert fold.winner is not None
            assert fold.winner.value in {f"obj:cig_{i}" for i in range(1, 6)}
            assert fold.values == ()
        finally:
            w.close()

    def test_builtin_set_valued_name_preserves_winner_and_exposes_values(self, tmp_path):
        w = self._world(tmp_path)
        try:
            w.ingest_structured([
                {"entity": "obj:meter", "attribute": "name", "value": "master meter", "timeless": True},
                {
                    "entity": "obj:meter",
                    "attribute": "name",
                    "value": "the master meter",
                    "timeless": True,
                },
            ])
            fold = w.indexes.current_state("obj:meter")["name"]
            assert fold.winner.value == "the master meter"
            assert fold.values == ("master meter", "the master meter")
            materialized = w.materialize(["obj:meter"])
            assert {
                r.value for r in materialized.assertions if r.attribute == "name"
            } == {"master meter", "the master meter"}
        finally:
            w.close()
