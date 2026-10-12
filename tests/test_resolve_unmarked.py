"""RESOLVE-UNMARKED-V1: resolve a declared aspect nobody marked open.

One test per check of specs/RESOLVE-UNMARKED-V1.md (Checks 1-8; Check 8's full
suite is the suite itself), plus the declaration's own gate behavior.
"""

from __future__ import annotations

import pytest

from patternbuffer import World
from patternbuffer.model import TASK_RESOLVE
from patternbuffer.roles import RoleViolation


class Recorder:
    """A model callable that records every call and answers each task."""

    def __init__(self, answer=None, fail=False):
        self.calls = []
        self.answer = answer or {"items": [{"value": "a red wool kirtle"}]}
        self.fail = fail

    def __call__(self, prompt, schema):
        self.calls.append((prompt, schema))
        if schema.get("title") == TASK_RESOLVE:
            if self.fail:
                raise RuntimeError("the model went away")
            return self.answer
        return {"durability": "STATE", "class_confidence": 0.9, "verdicts": []}

    @property
    def resolves(self):
        return [c for c in self.calls if c[1].get("title") == TASK_RESOLVE]


def _world(tmp_path, model=None, name="u.world", **kw):
    return World(tmp_path / name, "w:unmarked", model=model or Recorder(), **kw)


def _declare(w, aspect, *kinds, **extra):
    items = [{"entity": f"attr:{aspect}", "attribute": "resolvable_for", "value": k,
              "timeless": True} for k in kinds]
    items += [{"entity": f"attr:{aspect}", "attribute": a, "value": v, "timeless": True}
              for a, v in extra.items()]
    return w.porcelain.ingest_structured(items, classify="rules")


def _seed(w):
    w.ingest_structured([
        {"entity": "place:tavern", "attribute": "kind", "value": "tavern", "timeless": True},
        {"entity": "person:barmaid", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:barmaid", "attribute": "in", "value": "place:tavern",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "obj:anvil", "attribute": "kind", "value": "object", "timeless": True},
    ], classify="rules")


def _rows(w, entity, attribute):
    return [r for r in w.buffer.visible(entity=entity, attribute=attribute)]


# ------------------------------------------------------------ the declaration

def test_declaration_is_set_valued_and_readable(tmp_path):
    w = _world(tmp_path)
    try:
        r = _declare(w, "wears", "person", "statue")
        assert r.skipped == []
        assert w.semantics.resolvable_kinds("wears") == frozenset({"person", "statue"})
        assert w.semantics.resolvable_kinds("hair") == frozenset()
        # It is apart from the axes: a resolvable attribute is not "declared".
        assert not w.semantics.is_declared("wears")
    finally:
        w.close()


@pytest.mark.parametrize("bad", ["Person", "two words", "", 3, None, ["person"]])
def test_invalid_kind_value_is_skipped(tmp_path, bad):
    w = _world(tmp_path)
    try:
        head = w.buffer.head()
        r = w.porcelain.ingest_structured(
            [{"entity": "attr:wears", "attribute": "resolvable_for", "value": bad,
              "timeless": True}], classify="rules")
        assert [s["reason"] for s in r.skipped] == ["invalid_semantics_declaration"]
        assert w.buffer.head() == head
        assert w.semantics.resolvable_kinds("wears") == frozenset()
    finally:
        w.close()


def test_declaration_after_data_exists_is_allowed(tmp_path):
    """Opening an aspect to invention changes no fold, so data does not lock it."""
    w = _world(tmp_path)
    try:
        w.ingest_structured([{"entity": "person:ann", "attribute": "wears",
                              "value": "a hood", "valid_from": 1.0}], classify="rules")
        assert _declare(w, "wears", "person").skipped == []
        assert w.semantics.resolvable_kinds("wears") == frozenset({"person"})
    finally:
        w.close()


def test_attribute_default_supplies_it(tmp_path):
    seen = []

    def default(attribute):
        seen.append(attribute)
        return {"resolvable_for": ["person", "statue"]} if attribute == "wears" else None

    w = _world(tmp_path, attribute_default=default)
    try:
        w.porcelain.ingest_structured(
            [{"entity": "person:ann", "attribute": "wears", "value": "a hood",
              "valid_from": 1.0}], classify="rules")
        assert w.semantics.resolvable_kinds("wears") == frozenset({"person", "statue"})
        assert w.semantics.has_resolvable()
        # A single kind as a bare string works the same way.
        w2 = _world(tmp_path, name="two.world",
                    attribute_default=lambda a: {"resolvable_for": "tavern"})
        try:
            w2.porcelain.ingest_structured(
                [{"entity": "place:inn", "attribute": "colour", "value": "red",
                  "valid_from": 1.0}], classify="rules")
            assert w2.semantics.resolvable_kinds("colour") == frozenset({"tavern"})
        finally:
            w2.close()
    finally:
        w.close()


def test_attribute_default_with_an_invalid_kind_skips_the_item(tmp_path):
    w = _world(tmp_path, attribute_default=lambda a: {"resolvable_for": ["Person"]})
    try:
        r = w.porcelain.ingest_structured(
            [{"entity": "person:ann", "attribute": "wears", "value": "a hood",
              "valid_from": 1.0}], classify="rules")
        assert [s["reason"] for s in r.skipped] == ["invalid_semantics_declaration"]
        assert not w.semantics.has_resolvable()
    finally:
        w.close()


def test_a_model_written_item_cannot_declare_it(tmp_path):
    """The hint keys carry no `resolvable_for`: only the host opens an aspect."""
    w = _world(tmp_path)
    try:
        w.porcelain.ingest_structured(
            [{"entity": "person:ann", "attribute": "wears", "value": "a hood",
              "valid_from": 1.0, "resolvable_for": "person"}], classify="rules")
        assert not w.semantics.has_resolvable()
    finally:
        w.close()


# ------------------------------------------------------------------- Check 1

def test_check1_plants_and_forces_in_one_call_then_memoizes(tmp_path):
    model = Recorder()
    w = _world(tmp_path, model)
    try:
        _seed(w)
        _declare(w, "wears", "person")
        first = w.porcelain.resolve("person:barmaid", "wears")
        assert first["status"] == "resolved" and first["planted"] is True
        assert [f["value"] for f in first["facts"]] == ["a red wool kirtle"]
        assert len(model.resolves) == 1
        (planted,) = _rows(w, "person:barmaid", "wears")[:1]
        assert planted.value_type == "unresolved" and planted.status == "generated"
        assert planted.value == {"policy": "invent_under_canon", "planted": "resolve"}

        second = w.porcelain.resolve("person:barmaid", "wears")
        assert "planted" not in second
        assert second["facts"] == first["facts"]
        assert len(model.resolves) == 1            # no second model call
        # The request rides the call as any forced placeholder's does.
        from patternbuffer import task_request
        req = task_request(model.resolves[0][1])
        assert (req.entity, req.aspect, req.kind) == ("person:barmaid", "wears", "person")
        assert req.declared == ()
    finally:
        w.close()


def test_check1_the_role_authority_holds(tmp_path):
    """Both the placeholder and its resolution are the resolver's `generated`."""
    w = _world(tmp_path)
    try:
        _seed(w)
        _declare(w, "wears", "person")
        w.porcelain.resolve("person:barmaid", "wears")
        rows = [r for r in w.buffer.visible(entity="person:barmaid", attribute="wears")]
        assert rows and {r.status for r in rows} == {"generated"}
        marker = [r for r in w.buffer.all_rows() if r.attribute == "resolved_by"]
        assert marker and all(m.status == "generated" for m in marker)
    finally:
        w.close()


# ------------------------------------------------------------------- Check 2

def test_check2_a_world_with_no_declarations_is_unchanged(tmp_path):
    model = Recorder()
    w = _world(tmp_path, model)
    try:
        _seed(w)
        head = w.buffer.head()
        out = w.porcelain.resolve("person:barmaid", "wears")
        assert out["status"] == "resolved" and out["facts"] == []
        assert "planted" not in out and "reason" not in out
        assert w.buffer.head() == head and model.resolves == []
    finally:
        w.close()


def test_check2_opted_in_world_reports_undeclared(tmp_path):
    model = Recorder()
    w = _world(tmp_path, model)
    try:
        _seed(w)
        _declare(w, "wears", "person")
        head = w.buffer.head()
        undeclared = w.porcelain.resolve("person:barmaid", "hair")
        assert undeclared["status"] == "undeclared" and undeclared["facts"] == []
        assert "hair" in undeclared["reason"]
        unlisted = w.porcelain.resolve("obj:anvil", "wears")
        assert unlisted["status"] == "undeclared" and "object" in unlisted["reason"]
        assert w.buffer.head() == head and model.resolves == []
    finally:
        w.close()


def test_check2_a_tracking_world_returns_unknown(tmp_path):
    model = Recorder()
    w = _world(tmp_path, model, name="t.world", policy="observe_or_unknown")
    try:
        _seed(w)
        _declare(w, "wears", "person")
        assert w.porcelain.resolve("person:barmaid", "wears")["status"] == "unknown"
        assert w.porcelain.resolve("person:barmaid", "hair")["status"] == "unknown"
        assert model.resolves == []
    finally:
        w.close()


def test_check2_a_deny_world_never_plants(tmp_path):
    model = Recorder()
    w = _world(tmp_path, model, name="d.world", policy="deny")
    try:
        _seed(w)
        _declare(w, "wears", "person")
        out = w.porcelain.resolve("person:barmaid", "wears")
        assert out["status"] == "resolved" and out["facts"] == []
        assert model.resolves == [] and _rows(w, "person:barmaid", "wears") == []
    finally:
        w.close()


def test_check2_a_concrete_value_answers_without_invention(tmp_path):
    model = Recorder()
    w = _world(tmp_path, model)
    try:
        _seed(w)
        _declare(w, "wears", "person")
        w.ingest_structured([{"entity": "person:barmaid", "attribute": "wears",
                              "value": "an apron", "valid_from": 2.0}], classify="rules")
        out = w.porcelain.resolve("person:barmaid", "wears")
        assert [f["value"] for f in out["facts"]] == ["an apron"]
        assert "planted" not in out and model.resolves == []
    finally:
        w.close()


def test_check2_a_host_planted_placeholder_is_forced_as_ever(tmp_path):
    model = Recorder()
    w = _world(tmp_path, model)
    try:
        _seed(w)
        _declare(w, "wears", "person")
        w.ingest_structured([{"entity": "person:barmaid", "attribute": "wears",
                              "value": {"policy": "invent_under_canon"},
                              "value_type": "unresolved", "valid_from": 2.0}],
                            classify="rules")
        out = w.porcelain.resolve("person:barmaid", "wears")
        assert out["status"] == "resolved" and "planted" not in out
        assert len(model.resolves) == 1
    finally:
        w.close()


# ------------------------------------------------------------------ Check 2a

def test_check2a_at_poses_the_cursor_on_the_planting_path(tmp_path):
    w = _world(tmp_path)
    try:
        _seed(w)
        _declare(w, "wears", "person")
        w.ingestor.cursor.advance(5.0)
        out = w.porcelain.resolve("person:barmaid", "wears", at=9.0)
        assert out["planted"] is True
        assert w.ingestor.cursor.position == 9.0                 # stays at `at`
        assert _rows(w, "person:barmaid", "wears")[0].valid_from == 9.0
    finally:
        w.close()


@pytest.mark.parametrize("path", ["memo", "concrete", "host_planted", "undeclared", "deny"])
def test_check2a_at_poses_the_cursor_on_every_non_planting_path(tmp_path, path):
    w = _world(tmp_path, name=f"{path}.world",
               policy="deny" if path == "deny" else None)
    try:
        _seed(w)
        _declare(w, "wears", "person")
        entity, aspect = "person:barmaid", "wears"
        if path == "memo":
            w.porcelain.resolve(entity, aspect)
        elif path == "concrete":
            w.ingest_structured([{"entity": entity, "attribute": "wears", "value": "x",
                                  "valid_from": 2.0}], classify="rules")
        elif path == "host_planted":
            w.ingest_structured([{"entity": entity, "attribute": "wears",
                                  "value": {"policy": "invent_under_canon"},
                                  "value_type": "unresolved", "valid_from": 2.0}],
                                classify="rules")
        elif path == "undeclared":
            aspect = "hair"
        w.ingestor.cursor.advance(5.0)
        w.porcelain.resolve(entity, aspect, at=7.0)
        assert w.ingestor.cursor.position == 7.0
        w.porcelain.resolve(entity, aspect)                       # no `at`: no pose
        assert w.ingestor.cursor.position == 7.0
    finally:
        w.close()


def test_check2a_a_raising_call_restores_the_cursor(tmp_path):
    model = Recorder(fail=True)
    w = _world(tmp_path, model)
    try:
        _seed(w)
        _declare(w, "wears", "person")
        w.ingestor.cursor.advance(5.0)
        head = w.buffer.head()
        with pytest.raises(RuntimeError, match="went away"):
            w.porcelain.resolve("person:barmaid", "wears", at=9.0)
        assert w.buffer.head() == head
        assert w.ingestor.cursor.position == 5.0                  # restored
    finally:
        w.close()


# -------------------------------------------------------------------- Check 3

def test_check3_contents_mint_objects_in_the_entity_once(tmp_path):
    model = Recorder(answer={"items": [{"value": "a tankard", "kind": "object"},
                                       {"value": "a stool", "kind": "object"}]})
    w = _world(tmp_path, model)
    try:
        _seed(w)
        _declare(w, "contents", "tavern")
        out = w.porcelain.resolve("place:tavern", "contents")
        assert out["planted"] is True and len(out["facts"]) == 2
        held = w.contents("place:tavern")
        assert len(held) == 2 and all(h.startswith("obj:gen_") for h in held)
        again = w.porcelain.resolve("place:tavern", "contents")
        assert "planted" not in again and len(model.resolves) == 1
        assert w.contents("place:tavern") == held
    finally:
        w.close()


def test_check3_contents_never_plant_over_something_already_held(tmp_path):
    model = Recorder()
    w = _world(tmp_path, model)
    try:
        _seed(w)
        _declare(w, "contents", "tavern")
        w.ingest_structured([{"entity": "obj:keg", "attribute": "in", "value": "place:tavern",
                              "value_type": "entity", "valid_from": 1.0}], classify="rules")
        out = w.porcelain.resolve("place:tavern", "contents")
        assert out["status"] == "resolved" and out["facts"] == []
        assert "planted" not in out and model.resolves == []
    finally:
        w.close()


# -------------------------------------------------------------------- Check 4

@pytest.mark.parametrize("pin", ["CONSTITUTIVE", "DISPOSITIONAL"])
def test_check4_a_constitutive_or_dispositional_pin_plants_timeless(tmp_path, pin):
    w = _world(tmp_path)
    try:
        _seed(w)
        _declare(w, "complexion", "person", durability=pin)
        w.ingestor.cursor.advance(5.0)
        w.porcelain.resolve("person:barmaid", "complexion", at=9.0)
        (planted, *_) = _rows(w, "person:barmaid", "complexion")
        assert planted.valid_from is None and planted.value_type == "unresolved"
        assert w.ingestor.cursor.position == 9.0       # the pose still applies
    finally:
        w.close()


def test_check4_otherwise_the_placeholder_sits_at_at_or_the_cursor(tmp_path):
    w = _world(tmp_path)
    try:
        _seed(w)
        _declare(w, "wears", "person")
        _declare(w, "mood", "person", durability="STATE")
        w.ingestor.cursor.advance(5.0)
        w.porcelain.resolve("person:barmaid", "wears")
        w.porcelain.resolve("person:barmaid", "mood", at=8.0)
        assert _rows(w, "person:barmaid", "wears")[0].valid_from == 5.0
        assert _rows(w, "person:barmaid", "mood")[0].valid_from == 8.0
    finally:
        w.close()


# -------------------------------------------------------------------- Check 5

def test_check5_a_model_failure_leaves_no_placeholder_and_no_row(tmp_path):
    model = Recorder(fail=True)
    w = _world(tmp_path, model)
    try:
        _seed(w)
        _declare(w, "wears", "person")
        head, version = w.buffer.head(), w.buffer.log_version
        with pytest.raises(RuntimeError, match="went away"):
            w.porcelain.resolve("person:barmaid", "wears")
        assert w.buffer.head() == head
        assert _rows(w, "person:barmaid", "wears") == []
        assert not w.resolver.has_thunk("person:barmaid", "wears", "canon")
        assert w.resolver.thunk_table() == []
        # The world is whole and the next call, with a working model, succeeds.
        model.fail = False
        out = w.porcelain.resolve("person:barmaid", "wears")
        assert out["planted"] is True and len(out["facts"]) == 1
    finally:
        w.close()


def test_check5_a_model_failure_in_contents_leaves_nothing(tmp_path):
    model = Recorder(fail=True)
    w = _world(tmp_path, model)
    try:
        _seed(w)
        _declare(w, "contents", "tavern")
        head = w.buffer.head()
        with pytest.raises(RuntimeError):
            w.porcelain.resolve("place:tavern", "contents")
        assert w.buffer.head() == head and w.contents("place:tavern") == []
    finally:
        w.close()


# -------------------------------------------------------------------- Check 6

def test_check6_a_forged_generated_placeholder_is_refused_at_the_gate(tmp_path):
    w = _world(tmp_path)
    try:
        _seed(w)
        head = w.buffer.head()
        with pytest.raises(RoleViolation, match="letter 029"):
            w.ingest_structured([{
                "entity": "person:barmaid", "attribute": "wears",
                "value": {"policy": "invent_under_canon", "planted": "resolve"},
                "value_type": "unresolved", "status": "generated", "valid_from": 2.0,
            }], classify="rules")
        assert w.buffer.head() == head
        assert _rows(w, "person:barmaid", "wears") == []
    finally:
        w.close()


# -------------------------------------------------------------------- Check 7

@pytest.mark.parametrize("core", ["in", "kind", "connects_to", "same_as", "aka",
                                  "name", "alias", "superseded_by"])
def test_check7_a_core_attribute_cannot_be_declared_resolvable(tmp_path, core):
    w = _world(tmp_path)
    try:
        head = w.buffer.head()
        r = w.porcelain.ingest_structured(
            [{"entity": f"attr:{core}", "attribute": "resolvable_for", "value": "person",
              "timeless": True}], classify="rules")
        assert [s["reason"] for s in r.skipped] == ["invalid_semantics_declaration"]
        assert r.skipped[0]["detail"]["conflicts_with"] == "core"
        assert w.buffer.head() == head
        assert w.semantics.resolvable_kinds(core) == frozenset()
    finally:
        w.close()


def test_check7_the_buffer_still_refuses_a_core_declaration_row(tmp_path):
    """Beneath the gate, a direct append on a core attribute still raises."""
    from patternbuffer.roles import _make_engine_roles
    w = _world(tmp_path)
    try:
        with pytest.raises(ValueError, match="inviolable core"):
            w.buffer.append(entity="attr:in", attribute="resolvable_for", value="person",
                            status="inferred", role=_make_engine_roles()["ingestor"])
    finally:
        w.close()


# ------------------------------------------------------- the world's own memory

def test_a_reopened_world_reads_the_declarations_and_the_memo(tmp_path):
    model = Recorder()
    w = _world(tmp_path, model)
    try:
        _seed(w)
        _declare(w, "wears", "person")
        first = w.porcelain.resolve("person:barmaid", "wears")
    finally:
        w.close()
    model2 = Recorder()
    w = _world(tmp_path, model2)
    try:
        assert w.semantics.resolvable_kinds("wears") == frozenset({"person"})
        again = w.porcelain.resolve("person:barmaid", "wears")
        assert again["facts"] == first["facts"] and model2.resolves == []
    finally:
        w.close()
