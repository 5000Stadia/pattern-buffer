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


# ===================================================== §2 events() reads records


def test_s2_o2a_events_needs_no_sweep(world):
    """§2 O2a (EV1): a move ingested with classify="defer": events() lists it,
    as in_transit() does; classify_all() then changes neither."""
    w = world
    _seed_rooms(w)
    _ingest(w, _walk(), classify="defer")
    p = w.porcelain
    events, moving = p.events(), p.in_transit()
    assert _ids(events) == ["event:walk_1"]
    assert events[0]["kind"] == "moved" and events[0]["agents"] == ["person:mara"]
    assert [m["agent"] for m in moving] == ["person:mara"]
    w.classifier.classify_all()
    assert p.events() == events
    assert p.in_transit() == moving


def test_s2_o2b_no_pseudo_events(world):
    """§2 O2b (EV2), in O1b's world: today five events (doc:note, person:ilsa
    and obj:barn with kind null, plus the two real ones); after, event:convoy
    and event:fire."""
    w = world
    _seed_pseudo(w)
    events = w.porcelain.events()
    assert _ids(events) == ["event:convoy", "event:fire"]
    assert [e["kind"] for e in events] == ["convoy", "fire"]
    assert all(e["caused_by"] == [] for e in events)


def test_s2_o2c_a_merged_event_is_listed_once(world):
    """§2 O2c (EV3), in O1c's world, leaving aside the merge's own
    identity_merge event: one event, event:wedding, kind wedding, agents
    ["person:ines"]; events(participants="person:ines") returns it."""
    w = world
    _seed_wedding(w)
    p = w.porcelain
    events = [e for e in p.events() if e["kind"] != "identity_merge"]
    assert [(e["id"], e["kind"], e["agents"]) for e in events] == [
        ("event:wedding", "wedding", ["person:ines"])]
    assert _ids(p.events(participants="person:ines")) == ["event:wedding"]
    merges = [e for e in p.events() if e["kind"] == "identity_merge"]
    assert len(merges) == 1 and merges[0]["t"] is None


def test_s2_o2d_the_window_reads_whole_records(world):
    """§2 O2d (EV4), in O1d's world: `since` no longer cuts an event's earlier
    or timeless rows, and `until` no longer lists an event before its first
    stamped row."""
    w = world
    _seed_window(w)
    p = w.porcelain

    def shape(events):
        return [(e["id"], e["kind"], e["agents"], e["patients"], e["t"]) for e in events]

    assert shape(p.events(since=6.0)) == [
        ("event:siege", "siege", ["person:k"], [], 7.0),
        ("event:summons", "summons", [], ["person:k"], 8.0)]
    assert shape(p.events(since=6.0, kind="summons")) == [
        ("event:summons", "summons", [], ["person:k"], 8.0)]
    assert shape(p.events(until=6.0)) == [("event:siege", "siege", [], [], 5.0)]
    # the window's inclusion is otherwise the per-row one: [since, until]
    assert shape(p.events(since=5.0, until=5.0)) == [("event:siege", "siege", [], [], 5.0)]
    assert _ids(p.events(since=7.5, until=8.0)) == ["event:summons"]
    assert p.events(since=8.5) == []


def test_s2_o2e_existing_events_reads_unchanged(tmp_path):
    """§2 O2e: the existing events() tests pass unchanged (test_porcelain's
    events and ask tests, test_tracking_mode B3, test_moved_event 6c and 11).
    Representative here: B3 — a future event is filtered by `until`."""
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "b3.world", world_id="w:b3", model=stub)
    try:
        _ingest(w, [{"entity": "event:inspection", "attribute": "kind",
                     "value": "inspection", "valid_from": 500.0}])
        assert w.porcelain.events(until=100.0) == []
        assert _ids(w.porcelain.events(until=600.0)) == ["event:inspection"]
    finally:
        w.close()


def test_s2_o2f_no_model_call_and_no_write(world):
    """§2 O2f: events() makes no model call and no write."""
    w = world
    _seed_rooms(w)
    _ingest(w, _walk(), classify="defer")
    _seed_window(w)
    head, calls = w.buffer.head(), len(w._stub.calls)
    for kw in ({}, {"since": 6.0}, {"until": 6.0}, {"kind": "moved"},
               {"participants": "person:k"}, {"frame": "knows:person:k"},
               {"asserted_as_of": 3}):
        json.dumps(w.porcelain.events(**kw))
    assert w.buffer.head() == head and len(w._stub.calls) == calls


def test_s2_byte_identical_classified_single_id_event(world):
    """§2 byte-identical: a canon event whose rows are all classified, with
    one stored id and no timeless row beside stamped ones, reads the same
    twelve-key dict in any window that admits it."""
    w = world
    _seed_rooms(w)
    _ingest(w, [
        *_walk(valid_to=5.0),
        {"entity": "event:walk_1", "attribute": "manner", "value": "stroll",
         "valid_from": 5.0, "valid_to": 5.0},
        {"entity": "event:walk_1", "attribute": "caused_by", "value": "event:bell",
         "value_type": "entity", "valid_from": 5.0},
        {"entity": "event:bell", "attribute": "kind", "value": "bell", "valid_from": 4.0},
    ])
    walk = {"id": "event:walk_1", "kind": "moved", "agents": ["person:mara"],
            "patients": [], "t": 5.0, "caused_by": ["event:bell"],
            "origin": "place:hall", "destination": "place:yard", "manner": "stroll",
            "valid_to": 5.0, "origin_bound": True, "destination_bound": True}
    bell = {"id": "event:bell", "kind": "bell", "agents": [], "patients": [], "t": 4.0,
            "caused_by": [], "origin": None, "destination": None, "manner": None,
            "valid_to": None, "origin_bound": None, "destination_bound": None}
    p = w.porcelain
    assert p.events() == [bell, walk]
    assert list(p.events()[1]) == list(walk)          # the key order too
    assert p.events(since=4.5) == [walk]
    assert p.events(until=4.5) == [bell]
    assert p.events(since=5.0, until=5.0) == [walk]
    assert p.events(kind="moved", participants=["person:mara"]) == [walk]


# ===================================================== §3 in_transit() reads records


def test_s3_o3a_one_parse(world):
    """§3 O3a (EV5): a move whose origin is asserted twice at one stamp (hall,
    then barn): events() and in_transit() both say barn."""
    w = world
    _seed_rooms(w)
    _ingest(w, [{"entity": "place:barn", "attribute": "kind", "value": "barn",
                 "timeless": True}])
    _ingest(w, _walk())
    _ingest(w, [{"entity": "event:walk_1", "attribute": "origin", "value": "place:barn",
                 "value_type": "entity", "valid_from": 5.0}])
    p = w.porcelain
    assert [e["origin"] for e in p.events()] == ["place:barn"]
    assert [m["origin"] for m in p.in_transit()] == ["place:barn"]
    assert [m["origin"] for m in w.in_transit(as_of=6.0)] == ["place:barn"]


def test_s3_o3b_moved_event_oracles_unchanged(world):
    """§3 O3b: MOVED-EVENT-V1's oracles 5e, 6a-6c, 11 and 11a pass unchanged
    (tests/test_moved_event.py). Representative here: 6b's boundary — a closed
    move [10,20] is in transit strictly inside and stops at valid_to — and the
    fixed five-key shape."""
    w = world
    _seed_rooms(w)
    _ingest(w, [
        *_walk("event:i1", t=10.0, valid_to=20.0),
        {"entity": "person:mara", "attribute": "in", "value": "place:yard",
         "value_type": "entity", "valid_from": 20.0},
    ])
    assert w.in_transit(agent="person:mara", as_of=9.0) == []
    [rec] = w.in_transit(agent="person:mara", as_of=15.0)
    assert rec == {"agent": "person:mara", "origin": "place:hall",
                   "destination": "place:yard", "manner": None,
                   "last_known_containment": "place:hall"}
    assert w.in_transit(agent="person:mara", as_of=20.0) == []
    assert w.in_transit() == []                    # closed: never open at as_of=None


def test_s3_o3c_in_transit_as_of_a_log_position(world):
    """§3 O3c: in_transit(asserted_as_of=H) with H before the move's rows gives
    []; at the head, the move. World and porcelain signatures stay identical,
    `asserted_as_of` appended last."""
    import inspect
    w = world
    _seed_rooms(w)
    h = w.buffer.head()
    _ingest(w, _walk())
    p = w.porcelain
    assert p.in_transit(asserted_as_of=h) == []
    assert p.in_transit(as_of=6.0, asserted_as_of=h) == []
    assert [m["agent"] for m in p.in_transit(asserted_as_of=w.buffer.head())] == [
        "person:mara"]
    assert [m["agent"] for m in p.in_transit(as_of=6.0)] == ["person:mara"]
    world_sig = inspect.signature(w.in_transit)
    porcelain_sig = inspect.signature(p.in_transit)
    assert list(world_sig.parameters) == list(porcelain_sig.parameters) == [
        "agent", "as_of", "frame", "asserted_as_of"]
    assert porcelain_sig.parameters["asserted_as_of"].default is None
    from patternbuffer.mcp import build_registry
    schema = build_registry()["in_transit"]["inputSchema"]["properties"]
    assert schema["asserted_as_of"] == {"type": ["integer", "null"]}


def test_s3_the_containment_comparison_runs_as_of_the_log(world):
    """§3: the containment comparison also runs at `asserted_as_of` — an
    arrival written after H does not end the move in a read as of H."""
    w = world
    _seed_rooms(w)
    _ingest(w, _walk())
    h = w.buffer.head()
    _ingest(w, [{"entity": "person:mara", "attribute": "in", "value": "place:yard",
                 "value_type": "entity", "valid_from": 5.0}])
    assert w.porcelain.in_transit() == []                       # arrived
    assert [m["last_known_containment"] for m in w.porcelain.in_transit(
        asserted_as_of=h)] == ["place:hall"]
