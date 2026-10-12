"""Shared builders for the WORLD-SERVICE-V1 tests (not a test module)."""

from __future__ import annotations

import threading
from typing import Any

from patternbuffer import World
from patternbuffer.model import TASK_RESOLVE

VF = "knows:person:mara"          # the player's view frame
OTHER = "knows:person:barmaid"    # a second knows: frame, never the viewer's


class Recorder:
    """A model callable that records every call and answers each task."""

    def __init__(self, value: str = "a red wool kirtle", fail: bool = False) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.value = value
        self.fail = fail

    def __call__(self, prompt: str, schema: dict) -> Any:
        self.calls.append((prompt, schema))
        if schema.get("title") == TASK_RESOLVE:
            if self.fail:
                raise RuntimeError("the model went away")
            return {"items": [{"value": self.value, "kind": "mug"}]}
        return {"durability": "STATE", "class_confidence": 0.9, "verdicts": []}

    @property
    def resolves(self) -> list[tuple[str, dict]]:
        return [c for c in self.calls if c[1].get("title") == TASK_RESOLVE]


def build_world(tmp_path, model=None, name: str = "w.world") -> World:
    """A small tavern world: canon, the player's view frame, a second knows:
    frame, and two declared-resolvable aspects."""
    w = World(tmp_path / name, "w:svc", model=model or Recorder())
    canon = [
        {"entity": "place:tavern", "attribute": "kind", "value": "tavern", "timeless": True},
        {"entity": "place:cellar", "attribute": "kind", "value": "cellar", "timeless": True},
        {"entity": "place:attic", "attribute": "kind", "value": "attic", "timeless": True},
        {"entity": "place:road", "attribute": "kind", "value": "road", "timeless": True},
        {"entity": "place:tavern", "attribute": "connects_to", "value": "place:road",
         "value_type": "entity", "timeless": True},
        {"entity": "place:cellar", "attribute": "in", "value": "place:tavern",
         "value_type": "entity", "timeless": True},
        {"entity": "obj:anvil", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:anvil", "attribute": "in", "value": "place:cellar",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:mara", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:mara", "attribute": "name", "value": "Mara", "timeless": True},
        {"entity": "person:mara", "attribute": "in", "value": "place:tavern",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:mara", "attribute": "gold", "value": 3, "valid_from": 1.0},
        {"entity": "person:barmaid", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:barmaid", "attribute": "name", "value": "Barmaid", "timeless": True},
        {"entity": "person:barmaid", "attribute": "in", "value": "place:tavern",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:barmaid", "attribute": "gold", "value": 5, "valid_from": 1.0},
        # canon-only: the player has not perceived either of these
        {"entity": "person:stranger", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:stranger", "attribute": "in", "value": "place:cellar",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:barmaid", "attribute": "secret", "value": "owes a debt",
         "valid_from": 1.0},
        {"entity": "event:brawl", "attribute": "kind", "value": "brawl", "valid_from": 3.0},
        {"entity": "event:brawl", "attribute": "agent", "value": "person:mara",
         "value_type": "entity", "valid_from": 3.0},
    ]
    view = [
        {"entity": "place:tavern", "attribute": "kind", "value": "tavern", "timeless": True},
        {"entity": "place:attic", "attribute": "kind", "value": "attic", "timeless": True},
        {"entity": "person:mara", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:mara", "attribute": "in", "value": "place:tavern",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:mara", "attribute": "gold", "value": 3, "valid_from": 1.0},
        {"entity": "person:barmaid", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:barmaid", "attribute": "name", "value": "Barmaid", "timeless": True},
        {"entity": "person:barmaid", "attribute": "in", "value": "place:tavern",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:barmaid", "attribute": "gold", "value": 5, "valid_from": 1.0},
        {"entity": "event:brawl", "attribute": "kind", "value": "brawl", "valid_from": 3.0},
    ]
    other = [{"entity": "person:barmaid", "attribute": "mood", "value": "sour",
              "valid_from": 2.0}]
    w.ingest_structured(canon, classify="rules")
    w.ingest_structured(view, frame=VF, classify="rules")
    w.ingest_structured(other, frame=OTHER, classify="rules")
    w.porcelain.ingest_structured(
        [{"entity": "attr:wears", "attribute": "resolvable_for", "value": "person",
          "timeless": True},
         {"entity": "attr:contents", "attribute": "resolvable_for", "value": "attic",
          "timeless": True}], classify="rules")
    return w


# One sample call per allowlisted read (the view frame is injected / passed).
SAMPLE_CALLS: dict[str, dict[str, Any]] = {
    "snapshot": {"scope": ["person:mara", "person:barmaid"]},
    "state": {"entity": "person:barmaid", "attribute": "gold"},
    "state_union": {"entity": "person:barmaid", "attribute": "gold"},
    "where": {"attribute": "gold", "op": ">=", "value": 4},
    "aggregate": {"container": "place:tavern", "member_attribute": "gold", "op": "sum"},
    "confidence": {"entity": "person:barmaid", "attribute": "gold"},
    "locate": {"entity": "person:mara"},
    "contents": {"container": "place:tavern"},
    "composition": {"entity": "place:tavern"},
    "features": {"place": "place:tavern"},
    "path": {"a": "person:mara", "b": "person:barmaid"},
    "route": {"a": "place:tavern", "b": "place:attic"},
    "neighborhood": {"entity": "person:mara"},
    "salience": {"entity": "person:barmaid"},
    "events": {},
    "in_transit": {},
    "entities": {},
    "facts": {},
    "refer": {"description": "the barmaid"},
    "canonical_attribute": {"name": "located_in"},
}


def sample_args(verb: str, frame: str = VF) -> dict[str, Any]:
    """``SAMPLE_CALLS[verb]`` as a direct porcelain call in ``frame``."""
    args = dict(SAMPLE_CALLS[verb])
    if verb != "canonical_attribute":
        args["frame"] = frame
    if verb == "facts":
        args["include_meta"] = False
    if verb == "refer":
        args.update(model=False, learn=False)
    return args


def run_async(fn, *args, **kwargs):
    """Run ``fn`` on a helper thread; returns (thread, box). ``box['r']`` /
    ``box['e']`` hold the result or the error."""
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["r"] = fn(*args, **kwargs)
        except BaseException as exc:   # noqa: BLE001 - reported to the test
            box["e"] = exc

    t = threading.Thread(target=target, daemon=True)
    t.start()
    return t, box


def pump_until_done(svc, thread: threading.Thread, limit: float = 15.0) -> None:
    """Pump on the calling (owner) thread until ``thread`` finishes; fail the
    test, never hang, past ``limit`` seconds."""
    import time
    end = time.monotonic() + limit
    while thread.is_alive():
        svc.pump()
        thread.join(0.01)
        assert time.monotonic() < end, "helper thread did not finish: hung call"
    thread.join(1)
