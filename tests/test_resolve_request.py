"""RESOLVE-REQUEST-V1: a resolve call carries its purpose as data, and every
host that forwards the schema sends exactly what it sent before."""

import copy
import json

from patternbuffer import ResolveRequest, World, task_request
from patternbuffer.model import TASK_RESOLVE, TaskSchema, task_schema
from patternbuffer.thunks import _RESOLVE_SCHEMA


class Recorder:
    """A model callable that records every call and answers each task."""

    def __init__(self, answer=None):
        self.calls = []
        self.answer = answer or {"items": [{"value": "a red wool kirtle"}]}

    def __call__(self, prompt, schema):
        self.calls.append((prompt, schema))
        if schema.get("title") == TASK_RESOLVE:
            return self.answer
        return {"durability": "CONSTITUTIVE", "class_confidence": 0.9, "verdicts": []}


def _seed(w):
    w.ingest_structured([
        {"entity": "place:tavern", "attribute": "kind", "value": "tavern", "timeless": True},
        {"entity": "place:tavern", "attribute": "era", "value": "1660", "timeless": True},
        {"entity": "person:barmaid", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:barmaid", "attribute": "in", "value": "place:tavern",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:barmaid", "attribute": "wears",
         "value": {"policy": "invent_under_canon", "constraints": ["period-true"]},
         "value_type": "unresolved", "valid_from": 2.0},
    ])


def _resolve_calls(model):
    return [(p, s) for p, s in model.calls if s.get("title") == TASK_RESOLVE]


def test_resolve_call_carries_the_request(tmp_path):
    model = Recorder()
    w = World(tmp_path / "r.world", "w:req", model=model)
    _seed(w)
    out = w.porcelain.resolve("person:barmaid", "wears")
    assert out["status"] == "resolved"
    (prompt, schema), = _resolve_calls(model)
    req = task_request(schema)
    assert isinstance(req, ResolveRequest)
    assert req.world_id == "w:req"
    assert (req.entity, req.aspect, req.kind) == ("person:barmaid", "wears", "person")
    assert req.declared == ("period-true",)
    assert ("place:tavern", "era", "1660") in req.inherited
    assert req.as_of == 2.0 and req.frame == "canon"
    assert req.policy == "invent_under_canon"


def test_request_matches_the_prompt_lines(tmp_path):
    """The request is the prompt's constraint list as data, in the same order."""
    model = Recorder()
    w = World(tmp_path / "r.world", "w:req", model=model)
    _seed(w)
    w.porcelain.resolve("person:barmaid", "wears")
    (prompt, schema), = _resolve_calls(model)
    req = task_request(schema)
    lines = [f"{h} · {a} · {json.dumps(v)}" for h, a, v in req.inherited] + list(req.declared)
    assert prompt.endswith("Constraints (canon, in force):\n- " + "\n- ".join(lines))


def test_schema_serializes_byte_identically(tmp_path):
    model = Recorder()
    w = World(tmp_path / "r.world", "w:req", model=model)
    _seed(w)
    w.porcelain.resolve("person:barmaid", "wears")
    (_, schema), = _resolve_calls(model)
    assert isinstance(schema, dict)
    assert json.dumps(schema, sort_keys=True) == json.dumps(_RESOLVE_SCHEMA, sort_keys=True)
    assert schema == _RESOLVE_SCHEMA


def test_other_tasks_carry_no_request(tmp_path):
    model = Recorder()
    w = World(tmp_path / "r.world", "w:req", model=model)
    _seed(w)
    w.porcelain.resolve("person:barmaid", "wears")
    others = [s for _, s in model.calls if s.get("title") != TASK_RESOLVE]
    assert all(task_request(s) is None and type(s) is dict for s in others)


def test_a_code_generator_answers_from_the_request(tmp_path):
    """A seeded sampler routes on the title and reads the request: no prose parsed."""
    def sampler(prompt, schema):
        req = task_request(schema)
        if req is not None:
            return {"items": [{"value": f"{req.aspect} chosen for {req.entity}"}]}
        return {"durability": "CONSTITUTIVE", "class_confidence": 0.9, "verdicts": []}

    w = World(tmp_path / "r.world", "w:req", model=sampler)
    _seed(w)
    out = w.porcelain.resolve("person:barmaid", "wears")
    assert [f["value"] for f in out["facts"]] == ["wears chosen for person:barmaid"]
    # Memoized: the second force serves the same row, with no new call.
    again = w.porcelain.resolve("person:barmaid", "wears")
    assert [f["value"] for f in again["facts"]] == ["wears chosen for person:barmaid"]


def test_copies_keep_the_request_and_rebuilds_drop_it():
    req = ResolveRequest(world_id="w", entity="e:x", aspect="a", kind=None, inherited=(),
                         declared=(), as_of=None, frame="canon", policy="invent_under_canon")
    s = task_schema(_RESOLVE_SCHEMA, req)
    assert isinstance(s, TaskSchema) and task_request(s) is req
    assert task_request(copy.deepcopy(s)) == req
    assert task_request(dict(s)) is None  # an adapter's rebuild is a plain schema
    assert task_request(task_schema(_RESOLVE_SCHEMA)) is None
