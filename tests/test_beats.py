"""BEATS-V1 (r1.1): author frames are sealed, and beats are written in one shared shape.

One group per numbered test of specs/BEATS-V1.md section 5. No model is called: the
worlds here use the engine's rule fallback. Nothing imports construct; the pinned
fixture (tests/fixtures/construct_conditions.json) was written by hand from its grammar.
"""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path

import pytest

from patternbuffer import World, beats, mirror, service
from patternbuffer.beats import (ATOMS, CONDITION_SCHEMA, OPERATORS, Finding,
                                 author_references, validate_condition)
from patternbuffer.model import AUTHOR_FRAME_PREFIX, is_author_frame
from patternbuffer.service import Runner, WorldService
from patternbuffer.testing import StubModel, rule_classifier_fallback

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_FILE = ROOT / "schemas" / "patternbuffer.condition-1.json"
FIXTURE_FILE = Path(__file__).parent / "fixtures" / "construct_conditions.json"

PLOT = "plot:main"
VF = "knows:person:mara"
KEY = b"beats-test-key-0123456789"


def T(entity, attribute, value, value_type="literal", **extra):
    item = {"entity": entity, "attribute": attribute, "value": value,
            "value_type": value_type, "timeless": True}
    item.update(extra)
    return item


def E(entity, attribute, value, **extra):
    return T(entity, attribute, value, "entity", **extra)


def open_world(tmp_path, name="b"):
    model = StubModel(fallback=rule_classifier_fallback())
    return World(tmp_path / f"{name}.world", world_id=f"w:{name}", model=model)


def put(w, *items):
    receipt = w.porcelain.ingest_structured(list(items))
    assert not receipt.skipped, receipt.skipped
    return receipt


def beat_rows(beat_id="beat:find_body", arc_id="arc:main", frame=PLOT):
    """A beat's rows in construct's `_beat_rows` shape (arc/io.py), in an author frame."""
    cond = {"op": "all_of", "operands": [
        {"op": "located", "entity": "person:mara", "place": "place:study"},
        {"op": "turns_quiet", "at_least": 2}]}
    return [
        T(beat_id, "kind", "beat", frame=frame),
        E(beat_id, "part_of", arc_id, frame=frame),
        T(beat_id, "beat_phase", "rising", frame=frame),
        T(beat_id, "weight", "major", frame=frame),
        T(beat_id, "achievable_via", json.dumps(cond), frame=frame),
        {"entity": beat_id, "attribute": "status", "value": "pending", "valid_from": 1.0,
         "frame": frame},
        T(beat_id, "unreachable_if", json.dumps({"op": "turns_elapsed", "at_least": 99}),
          frame=frame),
        T(beat_id, "correlates", json.dumps(["beat:other"]), frame=frame),
    ]


def base_items():
    """Canon and the player's frame: a small study world, no plot."""
    return [
        T("place:study", "kind", "study"),
        T("person:mara", "kind", "person"),
        T("person:mara", "name", "Mara"),
        E("person:mara", "in", "place:study", timeless=False, valid_from=1.0),
        T("person:mara", "kind", "person", frame=VF),
        E("person:mara", "in", "place:study", timeless=False, valid_from=1.0, frame=VF),
        T("place:study", "kind", "study", frame=VF),
    ]


@pytest.fixture
def world(tmp_path):
    w = open_world(tmp_path)
    put(w, *base_items())
    try:
        yield w
    finally:
        w.close()


# ------------------------------------------------------------ 1. author frames


def test_author_frame_predicate():
    assert AUTHOR_FRAME_PREFIX == "plot:"
    assert is_author_frame("plot:main") and is_author_frame("plot:arc2")
    # session:* is bookkeeping the host reads every turn; it is not an author frame
    for frame in ("session:main", "canon", "knows:person:mara", "plot", "Plot:main", "", None, 3):
        assert not is_author_frame(frame), frame


def _refuses(call):
    with pytest.raises(ValueError, match="author frame"):
        call()


def test_attach_refuses_an_author_frame_before_anything_opens(world, monkeypatch):
    svc = WorldService()

    def boom(*a, **k):
        raise AssertionError("a reader snapshot opened before the refusal")

    monkeypatch.setattr(svc, "_refresh", boom)
    monkeypatch.setattr(svc, "_take_snapshot", boom)
    _refuses(lambda: svc.attach(world, PLOT))
    assert not svc.attached and svc.view_frame is None
    assert svc._reader is None and svc._published is None
    monkeypatch.undo()
    svc.attach(world, VF)             # the refused service is still a service
    try:
        assert svc.attached and svc.view_frame == VF
    finally:
        svc.detach()


def test_runner_refuses_in_its_constructor():
    opened: list[object] = []

    def open_it(gated):
        opened.append(gated)
        raise AssertionError("the runner must refuse before it opens a world")

    _refuses(lambda: Runner(open_it, PLOT))
    assert not opened


def test_set_view_frame_refuses_and_keeps_the_frame(world):
    svc = WorldService()
    svc.attach(world, VF)
    try:
        _refuses(lambda: svc.set_view_frame(PLOT))
        _refuses(lambda: svc.set_view_frame("plot:arc2"))
        assert svc.view_frame == VF                      # nothing was stored
    finally:
        svc.detach()


def test_mirror_functions_refuse_an_author_frame(world):
    _refuses(lambda: mirror.export(world, PLOT))
    _refuses(lambda: mirror.export(world, PLOT, key=KEY))
    _refuses(lambda: mirror.feed(world, PLOT, None))
    _refuses(lambda: mirror.feed(world, PLOT, None, key=KEY))
    _refuses(lambda: mirror.present_handles(world, PLOT, at=None, key=KEY))
    _refuses(lambda: mirror.present_handles(world, PLOT, at=None, key=None))


def test_other_views_are_unchanged(world):
    put(world, T("note:x", "kind", "note", frame="session:main"))
    for frame in ("canon", VF, "session:main"):
        doc = mirror.export(world, frame, key=KEY)
        assert doc["view_frame"] == frame
        assert mirror.feed(world, frame, None, key=KEY)["ops"]
        assert isinstance(mirror.present_handles(world, frame, at=None, key=KEY), dict)
    for frame in ("canon", VF, "session:main"):
        svc = WorldService()
        svc.attach(world, frame)
        try:
            assert svc.view_frame == frame
            svc.set_view_frame(VF)
            svc.set_view_frame("session:main")
            assert svc.view_frame == "session:main"
        finally:
            svc.detach()


def _public_view_frame_callables():
    """Every public function, class constructor and method of `service` and
    `mirror` that takes a `view_frame` (and the `set_view_frame` setter, whose
    parameter is `frame`), as `module.Name[.method]`."""
    found = set()

    def takes_view(fn) -> bool:
        return "view_frame" in inspect.signature(fn).parameters

    for mod in (service, mirror):
        for name, obj in vars(mod).items():
            if name.startswith("_") or getattr(obj, "__module__", None) != mod.__name__:
                continue
            short = mod.__name__.rsplit(".", 1)[-1]
            if inspect.isfunction(obj) and takes_view(obj):
                found.add(f"{short}.{name}")
            elif inspect.isclass(obj):
                for mname, member in vars(obj).items():
                    if not inspect.isfunction(member):
                        continue
                    if mname.startswith("_") and mname != "__init__":
                        continue
                    if takes_view(member) or mname == "set_view_frame":
                        found.add(f"{short}.{name}.{mname}")
    return found


def test_every_public_view_frame_entry_point_refuses(world):
    """The guard the spec asks for: list every public callable that takes a view
    frame, and fail if one has no refusal here (a new unguarded function lands as
    a missing recipe, not as silence)."""
    attached = WorldService()
    attached.attach(world, VF)

    recipes = {
        "service.WorldService.attach": lambda: WorldService().attach(world, PLOT),
        "service.WorldService.set_view_frame": lambda: attached.set_view_frame(PLOT),
        "service.Runner.__init__": lambda: Runner(lambda gated: None, PLOT),
        "mirror.feed": lambda: mirror.feed(world, PLOT, None),
        "mirror.export": lambda: mirror.export(world, PLOT),
        "mirror.present_handles": lambda: mirror.present_handles(world, PLOT, at=None, key=KEY),
    }
    try:
        assert _public_view_frame_callables() == set(recipes)
        for name, call in recipes.items():
            with pytest.raises(ValueError, match="author frame"):
                call()
        assert attached.view_frame == VF
    finally:
        attached.detach()


# ------------------------------------- 2. a beat's plot rows reach no player read


def _text(obj) -> str:
    return json.dumps(obj, default=str, sort_keys=True)


PLOT_WORDS = ("beat:find_body", "arc:main", "achievable_via", "unreachable_if",
              "beat_phase", "turns_quiet", "beat:other")


def test_beat_rows_in_the_plot_frame_reach_no_player_read(world):
    put(world, *beat_rows())
    # the plot really is there, in plot:main
    in_plot = {r.attribute for r in world.buffer.visible(frame=PLOT, entity="beat:find_body")}
    assert {"kind", "part_of", "achievable_via", "status"} <= in_plot
    p = world.porcelain
    p.continue_frame("person:mara_old", "person:mara", "the same woman")
    put(world, T("person:mara_old", "kind", "person", frame="knows:person:mara_old"))

    seen = []
    for frame in ("canon", VF):
        for scope in ("exact", "continued", "merged") if frame != "canon" else ("exact",):
            seen.append(p.facts(frame, frame_scope=scope, include_meta=True))
            seen.append(p.facts(frame, entity="beat:find_body", frame_scope=scope))
            seen.append(p.entities(frame))
            seen.append(p.state("beat:find_body", "status", frame=frame, frame_scope=scope))
            seen.append(p.state_union("beat:find_body", "status", frame=frame, frame_scope=scope))
            seen.append(p.snapshot(["person:mara", "place:study"], frame=frame))
    assert p.facts("canon", entity="beat:find_body") == []
    assert p.entities("canon") and "beat:find_body" not in p.entities("canon")
    assert p.snapshot(["beat:find_body"], frame=VF).get("error")       # unknown in this frame
    for payload in seen:
        for word in PLOT_WORDS:
            assert word not in _text(payload), word

    # no mirror export, at any frame a viewer can hold, carries a plot row
    for frame in ("canon", VF, "session:main"):
        for key in (None, KEY):
            for scope in ("exact", "continued", "merged") if frame == VF else ("exact",):
                doc = mirror.export(world, frame, key=key, frame_scope=scope)
                for word in PLOT_WORDS:
                    assert word not in _text(doc), (frame, word)
    # nor the rows themselves, by id, in any non-author frame
    ids = {r.id for r in world.buffer.visible(frame=PLOT)}
    for frame in ("canon", VF):
        assert not ids & {r.id for r in world.buffer.visible(frame=frame)}


def test_a_hosted_viewer_never_reads_a_beat(world):
    put(world, *beat_rows())
    svc = WorldService(read_timeout=10)
    svc.attach(world, VF)
    try:
        from service_fixture import pump_until_done, run_async
        sess = svc.session("holo-emitter")

        def ask(verb, **args):
            t, box = run_async(sess.call, verb, **args)
            pump_until_done(svc, t)
            assert "e" not in box, box
            return box["r"]

        for answer in (ask("facts"), ask("entities")):
            for word in PLOT_WORDS:
                assert word not in _text(answer), word
        assert ask("state", entity="beat:find_body", attribute="status") == {"status": "unknown"}
        # the id it asked about is echoed back as unknown; nothing of the beat is served
        assert ask("snapshot", scope=["beat:find_body"])["bad"] == ["beat:find_body"]
    finally:
        svc.detach()


# ---------------------------------------------------------- 3. author_references


def test_the_canon_value_naming_a_plot_only_id_is_reported(world):
    put(world,
        T("person:culprit", "kind", "person", frame=PLOT),
        E("person:culprit", "in", "place:study", frame=PLOT, timeless=False, valid_from=1.0),
        E("person:mara", "suspects", "person:culprit"))
    found = author_references(world)
    assert [(f.kind, f.entity, f.attribute, f.target) for f in found] == [
        ("author_frame_reference", "person:mara", "suspects", "person:culprit")]
    f = found[0]
    assert isinstance(f, Finding) and f.row_id.startswith("a:") and f.detail
    assert author_references(world, frames=("canon",)) == found


def test_a_plot_id_that_canon_also_holds_is_not_a_reference(world):
    put(world,
        T("person:mara", "secret_goal", "find the body", frame=PLOT),
        E("person:mara", "trusts", "place:study"))
    assert author_references(world) == []


def test_a_canon_effect_caused_by_a_canon_event_is_clean(world):
    # construct's clock effect: the firing is a canon event (its kind row is written
    # to canon in the same ingest) and the effect names it; plot keeps only the status
    put(world,
        T("event:dawn_fired_3", "kind", "clock_fired", timeless=False, valid_from=3.0),
        T("obj:alarm", "state", "ringing", timeless=False, valid_from=3.0,
          caused_by="event:dawn_fired_3"),
        T("clock:dawn", "status", "fired", frame=PLOT))
    caused = [r for r in world.buffer.visible(attribute="caused_by")]
    assert caused and caused[0].frame == "canon"           # the edge is in the data
    assert author_references(world) == []


def test_a_caused_by_with_no_canon_row_is_dangling(world):
    put(world, T("obj:alarm", "state", "ringing", timeless=False, valid_from=3.0,
                 caused_by="event:ghost"))
    found = author_references(world)
    assert [(f.kind, f.attribute, f.target) for f in found] == [
        ("dangling_caused_by", "caused_by", "event:ghost")]
    assert "obj" in found[0].detail and "alarm" in found[0].detail     # names the effect


def test_a_caused_by_into_the_plot_is_dangling_and_a_plot_reference(world):
    put(world,
        T("event:twist", "kind", "twist", frame=PLOT, timeless=False, valid_from=2.0),
        T("obj:alarm", "state", "ringing", timeless=False, valid_from=3.0,
          caused_by="event:twist"))
    found = author_references(world)
    assert sorted((f.kind, f.target) for f in found) == [
        ("author_frame_reference", "event:twist"), ("dangling_caused_by", "event:twist")]
    assert found[0].row_id == found[1].row_id


def test_a_knows_row_naming_a_plot_only_id_needs_knows_star(world):
    put(world,
        T("person:culprit", "kind", "person", frame=PLOT),
        E("person:mara", "suspects", "person:culprit", frame=VF))
    assert author_references(world) == []                              # canon only
    assert author_references(world, frames=("canon", "knows:*")) == \
        author_references(world, frames=(VF,))
    found = author_references(world, frames=("canon", "knows:*"))
    assert [(f.kind, f.target) for f in found] == [("author_frame_reference", "person:culprit")]
    put(world, E("person:other", "suspects", "person:culprit", frame="knows:person:other"))
    wide = author_references(world, frames=("knows:*",))
    assert len(wide) == 2
    assert len(author_references(world, frames=("knows:person:other",))) == 1


def test_a_knows_frame_may_hold_a_plot_only_entity(world):
    put(world, T("person:culprit", "kind", "person", frame=PLOT),
        T("person:culprit", "seen", "yes", frame=VF))
    found = author_references(world, frames=("knows:*",))
    assert [(f.kind, f.entity, f.target) for f in found] == [
        ("author_frame_reference", "person:culprit", "person:culprit")]


def test_author_references_writes_nothing(world):
    put(world,
        T("person:culprit", "kind", "person", frame=PLOT),
        E("person:mara", "suspects", "person:culprit"),
        T("obj:alarm", "state", "ringing", timeless=False, valid_from=3.0,
          caused_by="event:ghost"))
    before = [(r.id, r.entity, r.attribute, r.value, r.frame) for r in world.buffer.all_rows()]
    head = world.buffer.head()
    assert author_references(world, frames=("canon", "knows:*"))
    assert world.buffer.head() == head
    assert [(r.id, r.entity, r.attribute, r.value, r.frame)
            for r in world.buffer.all_rows()] == before


def test_author_references_refuses_what_it_cannot_lint(world):
    with pytest.raises(ValueError, match="author frame"):
        author_references(world, frames=(PLOT,))
    with pytest.raises(TypeError):
        author_references(world, frames="canon")
    with pytest.raises(ValueError):
        author_references(world, frames=("",))
    assert beats.FINDING_KINDS == ("author_frame_reference", "dangling_caused_by")


# ----------------------------------------------------------- 4. validate_condition


def _schema():
    return json.loads(SCHEMA_FILE.read_text())


def _fixture():
    return json.loads(FIXTURE_FILE.read_text())


MINIMAL = {
    "state_is": {"op": "state_is", "entity": "e:a", "attribute": "x", "value": 1},
    "located": {"op": "located", "entity": "e:a", "place": "p:b"},
    "in_frame": {"op": "in_frame", "frame": "canon", "entity": "e:a", "attribute": "x",
                 "value": "v"},
    "occurred": {"op": "occurred", "kind": "theft"},
    "beat_achieved": {"op": "beat_achieved", "beat_id": "beat:a"},
    "clock_fired": {"op": "clock_fired", "clock_id": "clock:a"},
    "turns_elapsed": {"op": "turns_elapsed", "at_least": 3},
    "turns_quiet": {"op": "turns_quiet", "at_least": 3},
    "quantity": {"op": "quantity", "entity": "e:a", "attribute": "x", "cmp": "<",
                 "value": 2.5},
    "not": {"op": "not", "operand": {"op": "turns_elapsed", "at_least": 1}},
    "all_of": {"op": "all_of", "operands": []},
    "any_of": {"op": "any_of", "operands": [{"op": "turns_quiet", "at_least": 1}]},
    "at_least": {"op": "at_least", "k": 1, "operands": [{"op": "turns_quiet", "at_least": 1}]},
}


def test_the_condition_version_is_pinned():
    assert CONDITION_SCHEMA == "patternbuffer.condition/1"
    schema = _schema()
    assert schema["title"] == CONDITION_SCHEMA
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert _fixture()["schema"] == CONDITION_SCHEMA


def test_every_atom_and_operator_validates():
    assert set(MINIMAL) == set(ATOMS) | set(OPERATORS)
    assert len(ATOMS) == 9 and set(OPERATORS) == {"not", "all_of", "any_of", "at_least"}
    for name, obj in MINIMAL.items():
        assert validate_condition(obj) == [], name
    for cmp in (">=", ">", "<=", "<", "==", "!="):
        assert validate_condition({**MINIMAL["quantity"], "cmp": cmp}) == []


_KIND_OF = {"str": {"type": "string"}, "int": {"type": "integer"},
            "int?": {"type": ["integer", "null"]}, "number": {"type": "number"},
            "strs": {"type": "array", "items": {"type": "string"}},
            "cmp": {"enum": [">=", ">", "<=", "<", "==", "!="]}, "any": True}


def _strip_default(prop):
    return {k: v for k, v in prop.items() if k != "default"} if isinstance(prop, dict) else prop


def test_the_hand_written_rules_are_the_committed_schema():
    """beats.py carries no jsonschema dependency, so its table is pinned to the
    published file: every atom's fields, required vs defaulted, and their types."""
    defs = _schema()["$defs"]
    assert set(defs["expr"]["oneOf"][i]["$ref"].rsplit("/", 1)[-1]
               for i in range(len(defs["expr"]["oneOf"]))) == set(ATOMS) | set(OPERATORS)
    for op, (required, optional) in ATOMS.items():
        d = defs[op]
        assert d["properties"]["op"] == {"const": op} and d["additionalProperties"] is False
        assert d["required"] == ["op", *required], op
        assert set(d["properties"]) == {"op", *required, *optional}, op
        for name, kind in {**required, **optional}.items():
            assert _strip_default(d["properties"][name]) == _KIND_OF[kind], (op, name)
        assert all("default" in d["properties"][n] for n in optional), op
    for op, (scalars, child) in OPERATORS.items():
        d = defs[op]
        assert d["required"] == ["op", *scalars, child], op
        assert set(d["properties"]) == {"op", *scalars, child}
        for name, kind in scalars.items():
            assert d["properties"][name] == _KIND_OF[kind]
        if child == "operand":
            assert d["properties"][child] == {"$ref": "#/$defs/expr"}
        else:
            assert d["properties"][child] == {"type": "array", "items": {"$ref": "#/$defs/expr"}}


def test_the_pinned_fixture_of_construct_conditions_validates():
    fixture = _fixture()
    names = {c["name"] for c in fixture["conditions"]}
    ops = set()

    def walk(o):
        ops.add(o["op"])
        for child in o.get("operands", []) + ([o["operand"]] if "operand" in o else []):
            walk(child)

    for c in fixture["conditions"]:
        assert validate_condition(c["condition"]) == [], c["name"]
        walk(c["condition"])
        # a beat stores it as a JSON string, exactly as construct writes it
        assert json.loads(json.dumps(c["condition"])) == c["condition"]
    assert ops == set(ATOMS) | set(OPERATORS)
    assert {f"quantity_{s}" for s in ("ge", "gt", "le", "lt", "eq", "ne")} <= names


def test_a_defaulted_field_may_be_omitted_and_a_serialized_one_is_accepted():
    assert validate_condition({"op": "occurred", "kind": "x"}) == []
    assert validate_condition({"op": "occurred", "kind": "x", "participants": ["a:b"],
                               "since": 1, "until": None, "min_count": 2}) == []
    assert validate_condition({"op": "quantity", "entity": "e:a", "attribute": "x",
                               "cmp": ">=", "value": 1, "frame": "canon"}) == []
    assert validate_condition({"op": "occurred", "kind": "x", "since": 2.0}) == []   # JSON 2.0


def test_each_fault_gives_one_named_problem():
    cases = {
        "unknown_op": ({"op": "xor", "operands": []}, "xor"),
        "missing_op": ({"entity": "e:a"}, "'op'"),
        "missing_field": ({"op": "located", "entity": "e:a"}, "'place'"),
        "wrong_type": ({"op": "turns_elapsed", "at_least": "3"}, "at_least"),
        "bad_cmp": ({**MINIMAL["quantity"], "cmp": "=>"}, "cmp"),
        "bool_is_not_an_integer": ({"op": "turns_quiet", "at_least": True}, "at_least"),
        "fraction_is_not_an_integer": ({"op": "turns_quiet", "at_least": 1.5}, "at_least"),
        "bool_is_not_a_number": ({**MINIMAL["quantity"], "value": False}, "value"),
        "participants_not_strings": ({"op": "occurred", "kind": "x", "participants": [1]},
                                     "participants"),
        "since_a_string": ({"op": "occurred", "kind": "x", "since": "now"}, "since"),
        "operands_not_an_array": ({"op": "all_of", "operands": {}}, "operands"),
        "extra_field": ({"op": "located", "entity": "e:a", "place": "p:b", "plce": "x"}, "plce"),
        "not_an_object": ("{}", "object"),
        "a_list": ([], "object"),
    }
    for name, (obj, word) in cases.items():
        problems = validate_condition(obj)
        assert len(problems) == 1, (name, problems)
        assert word in problems[0], (name, problems)


def test_a_fault_is_named_with_its_path():
    nested = {"op": "all_of", "operands": [
        {"op": "turns_elapsed", "at_least": 1},
        {"op": "not", "operand": {"op": "quantity", "entity": "e:a", "attribute": "x",
                                  "cmp": "approx", "value": 1}}]}
    problems = validate_condition(nested)
    assert len(problems) == 1
    assert problems[0].startswith("$.operands[1].operand.cmp:")
    assert validate_condition({"op": "not"}) == ["$: not is missing the required field 'operand'"]
    deep = {"op": "turns_elapsed", "at_least": 1}
    for _ in range(250):
        deep = {"op": "not", "operand": deep}
    assert any("deeper" in p for p in validate_condition(deep))    # never a RecursionError


def test_validation_evaluates_nothing_and_reads_no_world():
    obj = copy.deepcopy(MINIMAL["at_least"])
    snapshot = copy.deepcopy(obj)
    assert validate_condition(obj) == []
    assert obj == snapshot                                 # not mutated
    assert "world" not in inspect.signature(validate_condition).parameters


def test_the_hand_rules_agree_with_a_json_schema_validator_when_one_is_installed():
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(_schema())
    jsonschema.Draft202012Validator.check_schema(_schema())
    good = [c["condition"] for c in _fixture()["conditions"]] + list(MINIMAL.values())
    bad = [
        {"op": "xor", "operands": []}, {"entity": "e:a"}, {"op": "located", "entity": "e:a"},
        {"op": "turns_elapsed", "at_least": "3"}, {**MINIMAL["quantity"], "cmp": "=>"},
        {"op": "turns_quiet", "at_least": True}, {"op": "turns_quiet", "at_least": 1.5},
        {**MINIMAL["quantity"], "value": False},
        {"op": "occurred", "kind": "x", "participants": [1]},
        {"op": "occurred", "kind": "x", "since": "now"},
        {"op": "all_of", "operands": {}}, {"op": "located", "entity": "e:a", "place": "p",
                                           "plce": "x"},
        {"op": "not"}, {"op": "all_of", "operands": [{"op": "nope"}]}, [], "x", None,
    ]
    for obj in good:
        assert validator.is_valid(obj), obj
        assert validate_condition(obj) == [], obj
    for obj in bad:
        assert not validator.is_valid(obj), obj
        assert validate_condition(obj), obj
