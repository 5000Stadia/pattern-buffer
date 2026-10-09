"""EVENTS-ONE-READER-V1: every event read goes through one reader.

One test per oracle in specs/EVENTS-ONE-READER-V1.md, by section, plus the
spec's two cross-cutting tests (classification-independence and parity).

An event is an entity whose rows are its record. One reader,
`Indexes.event_records`, returns records — grouped by resolved id, without the
sidecar, as of both time axes — and `events()`, `in_transit()`, `state()` on an
event, the `what_happened` and `situation` lenses and `neighborhood()`'s event
edges all read through it. The fold never sees an event row, classified or not.

Where an oracle says an existing test passes unchanged, the full test lives in
its own module and runs there; the test here is one representative case.
"""

from __future__ import annotations

import json

import pytest

from patternbuffer import World
from patternbuffer.classify import EVENT, STATE
from patternbuffer.model import is_event_row
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "events.world", world_id="w:events", model=stub)
    w._stub = stub
    yield w
    w.close()


def _ingest(w: World, items: list[dict], classify: str = "rules", **kw) -> None:
    w.porcelain.ingest_structured(items, classify=classify, **kw)


def _ids(events: list[dict]) -> list[str]:
    return [e["id"] for e in events]


def _rows_of(record) -> set[tuple[str, str, object]]:
    return {(r.entity, r.attribute, json.dumps(r.value)) for r in record}


def _seed_rooms(w: World) -> None:
    """A hall and a yard, and Mara standing in the hall since t=1."""
    _ingest(w, [
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:yard", "attribute": "kind", "value": "yard", "timeless": True},
        {"entity": "person:mara", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:mara", "attribute": "in", "value": "place:hall", "valid_from": 1.0},
    ])


def _walk(eid: str = "event:walk_1", t: float = 5.0, **extra) -> list[dict]:
    """A move of Mara from the hall to the yard, every row stamped `t`."""
    stamp = {"valid_from": t, **extra}
    return [
        {"entity": eid, "attribute": "kind", "value": "moved", **stamp},
        {"entity": eid, "attribute": "agent", "value": "person:mara",
         "value_type": "entity", **stamp},
        {"entity": eid, "attribute": "origin", "value": "place:hall",
         "value_type": "entity", **stamp},
        {"entity": eid, "attribute": "destination", "value": "place:yard",
         "value_type": "entity", **stamp},
    ]


def _seed_pseudo(w: World) -> None:
    """O1b/O2b (probe EV2): a subject-level `caused_by` naming an event, an
    identity edge pointing at an event, and the identity edge of a thing
    contained in an event."""
    _ingest(w, [
        {"entity": "event:fire", "attribute": "kind", "value": "fire", "valid_from": 3.0},
        {"entity": "obj:barn", "attribute": "kind", "value": "barn", "timeless": True},
        {"entity": "obj:barn", "attribute": "caused_by", "value": "event:fire",
         "value_type": "entity", "valid_from": 3.0},
        {"entity": "doc:note", "attribute": "kind", "value": "note", "timeless": True},
        {"entity": "event:convoy", "attribute": "kind", "value": "convoy", "valid_from": 2.0},
        {"entity": "person:ilsa", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:ilsa", "attribute": "in", "value": "event:convoy",
         "valid_from": 2.0},
        {"entity": "person:bo", "attribute": "kind", "value": "person", "timeless": True},
    ])
    assert w.porcelain.reject("doc:note", "event:fire")["outcome"] == "rejected"
    assert w.porcelain.reject("person:ilsa", "person:bo")["outcome"] == "rejected"
    w.classifier.classify_all()


def _seed_wedding(w: World) -> None:
    """O1c/O2c (probe EV3): one ceremony under two stored ids, then merged."""
    _ingest(w, [
        {"entity": "event:wedding", "attribute": "kind", "value": "wedding", "valid_from": 9.0},
        {"entity": "event:the_wedding", "attribute": "agent", "value": "person:ines",
         "value_type": "entity", "valid_from": 9.0},
        {"entity": "person:ines", "attribute": "kind", "value": "person", "timeless": True},
    ])
    assert w.porcelain.merge("event:wedding", "event:the_wedding",
                             evidence="same ceremony")["outcome"] == "merged"
    w.classifier.classify_all()


def _seed_window(w: World) -> None:
    """O1d/O2d (probe EV4): a siege with its kind at 5 and an agent at 7; a
    summons with a timeless kind and a patient at 8."""
    _ingest(w, [
        {"entity": "event:siege", "attribute": "kind", "value": "siege", "valid_from": 5.0},
        {"entity": "event:siege", "attribute": "agent", "value": "person:k",
         "value_type": "entity", "valid_from": 7.0},
        {"entity": "event:summons", "attribute": "kind", "value": "summons", "timeless": True},
        {"entity": "event:summons", "attribute": "patient", "value": "person:k",
         "value_type": "entity", "valid_from": 8.0},
        {"entity": "person:k", "attribute": "kind", "value": "person", "timeless": True},
    ])


def _seed_meeting_pick(w: World) -> None:
    """O1g/O4c: a stated kind and a later assumed one, both at 2."""
    _ingest(w, [
        {"entity": "event:gathering", "attribute": "kind", "value": "meeting",
         "valid_from": 2.0},
    ])
    _ingest(w, [
        {"entity": "event:gathering", "attribute": "kind", "value": "assembly",
         "valid_from": 2.0, "status": "assumed"},
    ])


# ===================================================== §1 the event record


def test_s1_o1a_a_deferred_move_has_its_record(world):
    """§1 O1a (EV1): a move ingested with classify="defer" has its record, and
    after classify_all() the records are equal."""
    w = world
    _seed_rooms(w)
    _ingest(w, _walk(), classify="defer")
    before = w.indexes.event_records()
    assert list(before) == ["event:walk_1"]
    assert {r.attribute for r in before["event:walk_1"]} == {
        "kind", "agent", "origin", "destination"}
    assert all(w.classifier.get(r.id) is None for r in before["event:walk_1"])
    w.classifier.classify_all()
    assert all(w.classifier.durability(r.id) == EVENT for r in before["event:walk_1"])
    assert w.indexes.event_records() == before


def test_s1_o1b_rows_on_other_subjects_never_make_an_event(world):
    """§1 O1b (EV2): a `caused_by` naming an event, an identity edge pointing
    at one and the identity edge of a thing contained in one: the records are
    keyed event:fire and event:convoy only."""
    w = world
    _seed_pseudo(w)
    records = w.indexes.event_records()
    assert sorted(records) == ["event:convoy", "event:fire"]
    assert [(r.entity, r.attribute) for r in records["event:fire"]] == [
        ("event:fire", "kind")]
    assert [(r.entity, r.attribute) for r in records["event:convoy"]] == [
        ("event:convoy", "kind")]


def test_s1_o1c_a_merged_event_is_one_record(world):
    """§1 O1c (EV3): event:wedding (kind) merged with event:the_wedding
    (agent): one record, keyed event:wedding, holding both ids' rows."""
    w = world
    _seed_wedding(w)
    records = w.indexes.event_records()
    assert "event:the_wedding" not in records
    assert {(r.entity, r.attribute) for r in records["event:wedding"]} == {
        ("event:wedding", "kind"), ("event:the_wedding", "agent")}
    # either stored id names the one record
    for eid in ("event:wedding", "event:the_wedding"):
        assert list(w.indexes.event_records(ids=[eid])) == ["event:wedding"]


def test_s1_o1d_the_valid_axis_rule(world):
    """§1 O1d: event:summons (a timeless kind and a patient at 8) has no record
    as of 6, and both rows as of 8; event:siege (kind at 5, agent at 7) as of 6
    is the kind row."""
    w = world
    _seed_window(w)
    at6 = w.indexes.event_records(valid_as_of=6.0)
    assert "event:summons" not in at6
    assert [r.attribute for r in at6["event:siege"]] == ["kind"]
    at8 = w.indexes.event_records(valid_as_of=8.0)
    assert [r.attribute for r in at8["event:summons"]] == ["kind", "patient"]
    assert [r.attribute for r in at8["event:siege"]] == ["kind", "agent"]
    # no bound: the whole record
    assert [r.attribute for r in w.indexes.event_records()["event:summons"]] == [
        "kind", "patient"]


def test_s1_o1e_a_zero_duration_move_stays_history(world):
    """§1 O1e: a zero-duration move [5,5) has a record as of 5 and as of 9,
    and none as of 4 — `valid_to` never hides an event row."""
    w = world
    _seed_rooms(w)
    _ingest(w, _walk(valid_to=5.0))
    assert "event:walk_1" in w.indexes.event_records(valid_as_of=5.0)
    assert "event:walk_1" in w.indexes.event_records(valid_as_of=9.0)
    assert "event:walk_1" not in w.indexes.event_records(valid_as_of=4.0)
    assert len(w.indexes.event_records(valid_as_of=5.0)["event:walk_1"]) == 4


def test_s1_o1f_identity_edges_ride_beside_the_record(world):
    """§1 O1f: an event's same_as, maybe_same_as and distinct_from rows are
    not in its record; facts(entity=) still lists them."""
    w = world
    _ingest(w, [
        {"entity": "event:raid", "attribute": "kind", "value": "raid", "valid_from": 3.0},
        {"entity": "event:the_raid", "attribute": "agent", "value": "person:k",
         "value_type": "entity", "valid_from": 3.0},
        {"entity": "event:feint", "attribute": "kind", "value": "feint", "valid_from": 3.0},
        {"entity": "event:storm", "attribute": "kind", "value": "storm", "valid_from": 1.0},
        {"entity": "person:k", "attribute": "kind", "value": "person", "timeless": True},
    ])
    assert w.porcelain.merge("event:raid", "event:the_raid", evidence="one raid")["outcome"] \
        == "merged"
    w.registry.maybe_same_as("event:raid", "event:feint", evidence="perhaps")
    assert w.porcelain.reject("event:raid", "event:storm")["outcome"] == "rejected"
    w.classifier.classify_all()
    record = w.indexes.event_records()["event:raid"]
    assert {r.attribute for r in record} == {"kind", "agent"}
    listed = {f["attribute"] for f in w.porcelain.facts("canon", entity="event:raid")}
    assert {"same_as", "maybe_same_as", "distinct_from"} <= listed


def test_s1_o1g_the_pick_ranks_before_recency(world):
    """§1 O1g: kind "meeting" (stated) and a later "assembly" (assumed), both
    at 2, give "meeting"."""
    w = world
    _seed_meeting_pick(w)
    record = w.indexes.event_records()["event:gathering"]
    assert [r.value for r in record] == ["meeting", "assembly"]
    assert w.indexes.event_payload("event:gathering", record)["kind"] == "meeting"


def _old_event_guardrail(row) -> tuple[str, float] | None:
    """The classifier's event guardrail before this spec, verbatim in effect."""
    if row.value_type == "delta":
        return STATE, 1.0
    if row.entity.startswith("event:") or row.attribute == "caused_by":
        return EVENT, 1.0
    return None


def test_s1_o1h_classifier_verdicts_unchanged(world):
    """§1 O1h: every classifier verdict is unchanged — `is_event_row` is the
    guardrail's existing test. (The pinned corpus sidecar in
    tests/test_gate_authority.py, and the whole suite, run unchanged too.)"""
    w = world
    _seed_rooms(w)
    _ingest(w, [
        {"entity": "attr:gold", "attribute": "fold_policy", "value": "accrue",
         "timeless": True},
        {"entity": "event:fair", "attribute": "kind", "value": "fair", "valid_from": 2.0},
        {"entity": "event:fair", "attribute": "name", "value": "The Fair", "timeless": True},
        {"entity": "event:fair", "attribute": "in", "value": "place:yard",
         "valid_from": 2.0},
        {"entity": "event:fair", "attribute": "gold", "value": 5, "value_type": "delta",
         "valid_from": 2.0},
        {"entity": "obj:stall", "attribute": "kind", "value": "stall", "timeless": True},
        {"entity": "obj:stall", "attribute": "in", "value": "place:yard",
         "valid_from": 2.0, "caused_by": "event:fair"},
        {"entity": "obj:stall", "attribute": "caused_by", "value": "event:fair",
         "value_type": "entity", "valid_from": 2.0},
    ], classify="defer")
    w.porcelain.merge("event:fair", "event:the_fair", evidence="one fair")
    rows = w.buffer.all_rows()
    w.classifier.classify_rows(rows, model=False)
    checked = 0
    for row in rows:
        expected = _old_event_guardrail(row)
        if expected is None:
            continue
        verdict = w.classifier.get(row.id)
        assert (verdict.durability, verdict.class_confidence) == expected, row
        assert is_event_row(row) == (row.entity.startswith("event:")
                                     and row.value_type != "delta")
        checked += 1
    assert checked >= 8
    # the delta on an event is STATE, and is not an event row
    delta = next(r for r in rows if r.value_type == "delta")
    assert w.classifier.durability(delta.id) == STATE and not is_event_row(delta)

