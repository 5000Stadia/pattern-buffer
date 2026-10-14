"""RESOLVE-REQUEST-V1.1: the request carries the entity's own current STATE
facts as of the placeholder's time — for code generators; the prompt is
unchanged."""

from patternbuffer import World, task_request
from patternbuffer.model import TASK_RESOLVE

_PINS = {"age": "STATE", "hair": "STATE", "sex": "DISPOSITIONAL"}


def _defaults(attribute):
    pin = _PINS.get(attribute)
    return {"durability": pin} if pin else None


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, prompt, schema):
        self.calls.append((prompt, schema))
        if schema.get("title") == TASK_RESOLVE:
            return {"items": [{"value": "a red wool kirtle"}]}
        return {"durability": "CONSTITUTIVE", "class_confidence": 0.9, "verdicts": []}


def _world(tmp_path):
    model = Recorder()
    w = World(tmp_path / "c.world", "w:cur", model=model, attribute_default=_defaults)
    w.ingest_structured([
        {"entity": "place:tavern", "attribute": "kind", "value": "tavern", "timeless": True},
        {"entity": "place:tavern", "attribute": "hair", "value": "not a person's", "valid_from": 1.0},
        {"entity": "person:barmaid", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:barmaid", "attribute": "sex", "value": "female", "timeless": True},
        {"entity": "person:barmaid", "attribute": "in", "value": "place:tavern",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:barmaid", "attribute": "age", "value": 24, "valid_from": 1.0},
        {"entity": "person:barmaid", "attribute": "hair", "value": "long, blonde", "valid_from": 1.0},
        {"entity": "person:barmaid", "attribute": "hair", "value": "short, blonde", "valid_from": 5.0},
    ])
    return w, model


def _request(model):
    (_, schema), = [(p, s) for p, s in model.calls if s.get("title") == TASK_RESOLVE]
    return task_request(schema)


def test_current_holds_own_state_as_of_the_placeholder(tmp_path):
    w, model = _world(tmp_path)
    w.ingest_structured([{"entity": "person:barmaid", "attribute": "wears",
                          "value": {"policy": "invent_under_canon"},
                          "value_type": "unresolved", "valid_from": 3.0}])
    w.porcelain.resolve("person:barmaid", "wears")
    req = _request(model)
    # As of 3.0 the haircut (at 5.0) has not happened; age is current; the
    # DISPOSITIONAL sex is inherited, not current; the tavern's rows never are.
    # A person's containment is STATE by guardrail (CONTAINMENT-DURABILITY-V1 §1:
    # beings move), so where she is stands is her own current fact too.
    assert req.current == (("age", 24), ("hair", "long, blonde"), ("in", "place:tavern"))
    assert ("person:barmaid", "sex", "female") in req.inherited
    assert all(attr != "sex" for attr, _ in req.current)


def test_current_follows_a_later_change(tmp_path):
    w, model = _world(tmp_path)
    w.ingest_structured([{"entity": "person:barmaid", "attribute": "wears",
                          "value": {"policy": "invent_under_canon"},
                          "value_type": "unresolved", "valid_from": 6.0}])
    w.porcelain.resolve("person:barmaid", "wears")
    assert dict(_request(model).current)["hair"] == "short, blonde"


def test_prompt_is_unchanged_by_current(tmp_path):
    w, model = _world(tmp_path)
    w.ingest_structured([{"entity": "person:barmaid", "attribute": "wears",
                          "value": {"policy": "invent_under_canon"},
                          "value_type": "unresolved", "valid_from": 3.0}])
    w.porcelain.resolve("person:barmaid", "wears")
    (prompt, _), = [(p, s) for p, s in model.calls if s.get("title") == TASK_RESOLVE]
    assert "24" not in prompt and "long, blonde" not in prompt
