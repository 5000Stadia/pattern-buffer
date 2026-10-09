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


# ===================================================== §4 event rows never fold


def _seed_meeting(w: World) -> None:
    """O4a (EV6): a meeting in the study at 2, its rows ingested unclassified."""
    _ingest(w, [{"entity": "place:study", "attribute": "kind", "value": "room",
                 "timeless": True}])
    _ingest(w, [
        {"entity": "event:meeting", "attribute": "kind", "value": "meeting", "valid_from": 2.0},
        {"entity": "event:meeting", "attribute": "in", "value": "place:study",
         "value_type": "entity", "valid_from": 2.0},
    ], classify="defer")


def _meeting_reads(w: World) -> dict:
    p = w.porcelain
    kind, where = p.state("event:meeting", "kind"), p.state("event:meeting", "in")
    return {
        "kind": (kind["status"], kind.get("fact", {}).get("value")),
        "in": (where["status"], where.get("fact", {}).get("value")),
        "contents": p.contents("place:study"),
        "locate": p.locate("event:meeting"),
        "snapshot": p.snapshot("event:meeting")["facts"],
        "study": [(f["entity"], f["attribute"]) for f in p.snapshot("place:study")["facts"]],
        "events": _ids(p.events()),
    }


def test_s4_o4a_state_reads_the_record_before_and_after_a_sweep(world):
    """§4 O4a (EV6): before and after the sweep alike, state(kind) is known
    "meeting" and state(in) known "place:study"; contents is []; the snapshot
    has no facts; events() lists the meeting."""
    w = world
    _seed_meeting(w)
    expected = {
        "kind": ("known", "meeting"),
        "in": ("known", "place:study"),
        "contents": [],
        "locate": [],
        "snapshot": [],
        "study": [("place:study", "kind")],
        "events": ["event:meeting"],
    }
    assert _meeting_reads(w) == expected
    w.classifier.classify_all()
    assert _meeting_reads(w) == expected


def test_s4_o4b_an_event_not_yet_occurred_is_unknown(world):
    """§4 O4b: a move stamped 5: state(kind, as_of=4) is unknown; at 5 it is
    "moved", for a zero-duration move too."""
    w = world
    _seed_rooms(w)
    _ingest(w, _walk("event:walk_1"))
    _ingest(w, _walk("event:walk_2", valid_to=5.0))
    p = w.porcelain
    for eid in ("event:walk_1", "event:walk_2"):
        assert p.state(eid, "kind", as_of=4.0) == {"status": "unknown"}
        at5 = p.state(eid, "kind", as_of=5.0)
        assert at5["status"] == "known" and at5["fact"]["value"] == "moved"
        assert p.state(eid, "kind", as_of=9.0)["fact"]["value"] == "moved"
        assert p.state(eid, "agent", as_of=4.0) == {"status": "unknown"}


def test_s4_o4c_same_stamp_disagreement(world):
    """§4 O4c: two stated kinds at one stamp (or both timeless) are conflicted,
    serving the later with both ids in `conflicting`; a stated kind outranks a
    later assumed one; two `participants` rows are known, the later as the
    fact and both in `values`."""
    w = world
    rows = []
    for eid, stamp in (("event:fog_hour", {"valid_from": 4.0}),
                       ("event:mending", {"timeless": True})):
        _ingest(w, [{"entity": eid, "attribute": "kind", "value": "custom", **stamp}])
        _ingest(w, [{"entity": eid, "attribute": "kind", "value": "time period", **stamp}])
        rows = [r for r in w.buffer.all_rows() if r.entity == eid and r.attribute == "kind"]
        out = w.porcelain.state(eid, "kind")
        assert out["status"] == "conflicted"
        assert out["fact"]["value"] == "time period"
        assert out["conflicting"] == [r.id for r in rows]       # log order
        assert [f["value"] for f in out["conflicting_facts"]] == ["custom", "time period"]
    _seed_meeting_pick(w)
    pick = w.porcelain.state("event:gathering", "kind")
    assert pick["status"] == "known" and pick["fact"]["value"] == "meeting"
    _ingest(w, [
        {"entity": "event:gathering", "attribute": "participants", "value": "the guild",
         "valid_from": 2.0},
        {"entity": "event:gathering", "attribute": "participants", "value": "the watch",
         "valid_from": 3.0},
    ])
    many = w.porcelain.state("event:gathering", "participants")
    assert many["status"] == "known" and many["fact"]["value"] == "the watch"
    assert [f["value"] for f in many["values"]] == ["the guild", "the watch"]
    assert w.porcelain.state("event:gathering", "participants", value="the guild")["matches"]
    # one description row: known, served without `values`
    _ingest(w, [{"entity": "event:gathering", "attribute": "weather", "value": "rain",
                 "valid_from": 2.0}])
    single = w.porcelain.state("event:gathering", "weather")
    assert single["status"] == "known" and "values" not in single


def test_s4_o4d_machinery_is_never_a_point_read(world):
    """§4 O4d: state(event:x, "same_as") is unknown, as for any entity."""
    w = world
    _seed_wedding(w)
    assert w.porcelain.state("event:wedding", "same_as") == {"status": "unknown"}
    assert w.porcelain.state("event:the_wedding", "same_as") == {"status": "unknown"}
    # the merged record still answers the event's own keys, under either id
    assert w.porcelain.state("event:the_wedding", "kind")["fact"]["value"] == "wedding"
    assert w.porcelain.state("event:wedding", "agent")["fact"]["value"] == "person:ines"


def test_s4_o4e_ask_reads_an_event_key_from_its_record(world):
    """§4 O4e: `ask` with a plan key on an event target serves the record's
    fact (today: "no folded facts on the asked keys")."""
    w = world
    _ingest(w, [
        {"entity": "person:rival", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "event:theft", "attribute": "kind", "value": "theft", "valid_from": 5.0,
         "aliases": ["the theft"]},
        {"entity": "event:theft", "attribute": "agent", "value": "person:rival",
         "value_type": "entity", "valid_from": 5.0},
    ])
    w._stub.enqueue({"refer_targets": ["the theft"],
                     "keys": [{"target_index": 0, "attribute": "agent"}],
                     "wants_location": False, "wants_events": False})
    a = w.porcelain.ask("who did the theft?")
    assert a.answered and [f["value"] for f in a.facts] == ["person:rival"]
    assert a.facts[0]["entity"] == "event:theft"


def test_s4_o4f_a_delta_on_an_event_still_folds(world):
    """§4 O4f: a `delta` on an event's accrue attribute: the total is served —
    a delta is not an event row."""
    w = world
    _ingest(w, [
        {"entity": "attr:takings", "attribute": "fold_policy", "value": "accrue",
         "timeless": True},
        {"entity": "event:fair", "attribute": "kind", "value": "fair", "valid_from": 1.0},
        {"entity": "event:fair", "attribute": "takings", "value": 5, "value_type": "delta",
         "valid_from": 2.0},
        {"entity": "event:fair", "attribute": "takings", "value": 7, "value_type": "delta",
         "valid_from": 3.0},
    ], classify="defer")
    for _ in range(2):
        out = w.porcelain.state("event:fair", "takings")
        assert out["status"] == "known" and out["quantity"] == 12
        w.classifier.classify_all()


def test_s4_o4g_cross_entity_reads_stay_standing_only(world):
    """§4 O4g: where, who_knows and aggregate never return an event because
    of its record."""
    w = world
    _seed_meeting(w)
    _ingest(w, [
        {"entity": "event:meeting", "attribute": "attendance", "value": 30, "valid_from": 2.0},
        {"entity": "event:meeting", "attribute": "kind", "value": "meeting",
         "valid_from": 2.0, "frame": "knows:person:ann"},
    ], classify="defer")
    p = w.porcelain
    for _ in range(2):
        assert p.state("event:meeting", "attendance")["fact"]["value"] == 30
        assert p.where("attendance", ">=", 0) == []
        assert p.who_knows("event:meeting", "kind") == []
        assert p.aggregate("place:study", "attendance", "sum")["count"] == 0
        w.classifier.classify_all()


def _seed_wren(w: World, *, build: bool) -> None:
    p = w.porcelain
    if build:
        p.begin_build(at=1.0)
    _ingest(w, [
        {"entity": "person:wren", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:wren", "attribute": "name", "value": "Wren Hollis",
         "timeless": True},
        {"entity": "event:wren", "attribute": "kind", "value": "storm", "valid_from": 3.0},
        {"entity": "event:wren", "attribute": "name", "value": "Wren Hollis",
         "timeless": True},
    ], classify="defer" if build else "rules")


@pytest.mark.parametrize("build", [True, False], ids=["build_session", "swept"])
def test_s4_o4h_identity_sees_an_events_kind(tmp_path, build):
    """§4 O4h (EV10): event:wren (kind storm, at 3) and person:wren (kind
    person) share the name "Wren Hollis". In a build session (every row
    unclassified) and in the same world swept alike, reconcile() makes a
    proposal and no merge; the proposal names the event's kind."""
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "wren.world", world_id="w:wren", model=stub)
    try:
        _seed_wren(w, build=build)
        event_rows = [r for r in w.buffer.all_rows() if r.entity == "event:wren"]
        assert all((w.classifier.get(r.id) is None) == build for r in event_rows)
        out = w.porcelain.reconcile()
        assert out["merges"] == 0
        assert w.registry.resolve("event:wren") != w.registry.resolve("person:wren")
        [proposal] = [pr for pr in out["proposals"]
                      if {pr["a"], pr["b"]} == {"event:wren", "person:wren"}]
        assert "storm" in json.dumps(proposal)
        assert w.registry._kind_state("event:wren", "person:wren") == "conflict"
    finally:
        w.close()


def test_s4_o4i_classification_independence(world):
    """§4 O4i: on O4a's world, state() and contents() give the same answers
    before and after classify_all()."""
    w = world
    _seed_meeting(w)
    p = w.porcelain

    def reads():
        return (p.state("event:meeting", "kind"), p.state("event:meeting", "in"),
                p.state("event:meeting", "kind", as_of=1.0), p.contents("place:study"))

    before = reads()
    w.classifier.classify_all()
    assert reads() == before


def test_s4_state_union_reads_the_records_of_the_aka_union(world):
    """§4 Rule B: state_union reads the records of the `aka` union, as
    current_state(correlated=) does."""
    w = world
    _ingest(w, [
        {"entity": "event:raid", "attribute": "kind", "value": "raid", "valid_from": 3.0},
        {"entity": "event:night_attack", "attribute": "agent", "value": "person:k",
         "value_type": "entity", "valid_from": 3.0},
        {"entity": "person:k", "attribute": "kind", "value": "person", "timeless": True},
    ])
    assert w.porcelain.correlate("event:raid", "event:night_attack",
                                 evidence="the raid was the night attack",
                                 at=1.0)["outcome"] == "correlated"
    p = w.porcelain
    assert p.state("event:raid", "agent") == {"status": "unknown"}
    union = p.state_union("event:raid", "agent")
    assert union["status"] == "known" and union["fact"]["value"] == "person:k"
    assert p.state_union("event:raid", "agent", as_of=0.5) == {"status": "unknown"}


def test_s4_a_standing_entity_merged_with_an_event_keeps_its_fold(world):
    """§4 Rule B: for a closure that merges an event with a standing entity,
    standing keys keep their fold, and only the event's own attributes come
    from the record."""
    w = world
    _ingest(w, [
        {"entity": "person:tide", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:tide", "attribute": "mood", "value": "calm", "valid_from": 1.0},
        {"entity": "event:tide", "attribute": "kind", "value": "flood", "valid_from": 2.0},
        {"entity": "event:tide", "attribute": "agent", "value": "person:tide",
         "value_type": "entity", "valid_from": 2.0},
    ])
    w.registry.merge("person:tide", "event:tide", evidence="a bad merge")
    p = w.porcelain
    assert p.state("event:tide", "kind")["fact"]["value"] == "person"     # the fold
    assert p.state("event:tide", "mood")["fact"]["value"] == "calm"
    assert p.state("person:tide", "agent")["fact"]["value"] == "person:tide"   # the record


def test_s4_read_surface_last_write_meets_the_record(world):
    """§4 meets READ-SURFACE-V1 §2 O2f: an event row on a declared last_write
    attribute is still never served by the fold, and `state()` answers it from
    the event's record (the pick: rank, then recency — never conflicted)."""
    w = world
    _ingest(w, [{"entity": "attr:arc_phase", "attribute": "fold_policy",
                 "value": "last_write", "timeless": True}])
    _ingest(w, [
        {"entity": "event:bell", "attribute": "arc_phase", "value": "setup",
         "valid_from": 3.0},
        {"entity": "event:bell", "attribute": "arc_phase", "value": "climax",
         "valid_from": 3.0},
    ])
    assert w.state("event:bell", "arc_phase").winner is None
    out = w.porcelain.state("event:bell", "arc_phase")
    assert out["status"] == "known" and out["fact"]["value"] == "climax"
    assert [f["value"] for f in out["values"]] == ["setup", "climax"]


# ===================================================== §5 the lenses read records


def _facts(snapshot: dict) -> list[tuple[str, str, object]]:
    return [(f["entity"], f["attribute"], f["value"]) for f in snapshot["facts"]]


def test_s5_o5a_what_happened_serves_whole_events(world):
    """§5 O5a (EV7): snapshot(person:rival, lens="what_happened") is the
    theft's whole record — not the one row naming the rival plus the rival's
    identity edges."""
    w = world
    _ingest(w, [
        {"entity": "person:rival", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:other", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "obj:pipe", "attribute": "kind", "value": "pipe", "timeless": True},
        {"entity": "event:theft", "attribute": "kind", "value": "theft", "valid_from": 5.0},
        {"entity": "event:theft", "attribute": "agent", "value": "person:rival",
         "value_type": "entity", "valid_from": 5.0},
        {"entity": "event:theft", "attribute": "patient", "value": "obj:pipe",
         "value_type": "entity", "valid_from": 5.0},
    ])
    assert w.porcelain.reject("person:rival", "person:other")["outcome"] == "rejected"
    w.classifier.classify_all()
    assert _facts(w.porcelain.snapshot("person:rival", lens="what_happened")) == [
        ("event:theft", "kind", "theft"),
        ("event:theft", "agent", "person:rival"),
        ("event:theft", "patient", "obj:pipe"),
    ]


def test_s5_o5b_a_place_lists_what_happened_in_it(world):
    """§5 O5b: snapshot(place:study, lens="what_happened") lists every event
    that happened `in` the study, whole, in the listing order."""
    w = world
    _ingest(w, [
        {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "person:ann", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "event:quarrel", "attribute": "kind", "value": "quarrel", "valid_from": 3.0},
        {"entity": "event:quarrel", "attribute": "in", "value": "place:study",
         "value_type": "entity", "valid_from": 3.0},
        {"entity": "event:quarrel", "attribute": "agent", "value": "person:ann",
         "value_type": "entity", "valid_from": 3.0},
        {"entity": "event:toast", "attribute": "kind", "value": "toast", "valid_from": 1.0},
        {"entity": "event:toast", "attribute": "in", "value": "place:study",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "event:dance", "attribute": "kind", "value": "dance", "valid_from": 2.0},
        {"entity": "event:dance", "attribute": "in", "value": "place:hall",
         "value_type": "entity", "valid_from": 2.0},
    ])
    assert _facts(w.porcelain.snapshot("place:study", lens="what_happened")) == [
        ("event:toast", "kind", "toast"),
        ("event:toast", "in", "place:study"),
        ("event:quarrel", "kind", "quarrel"),
        ("event:quarrel", "in", "place:study"),
        ("event:quarrel", "agent", "person:ann"),
    ]
    # since keeps an event whose t is >= since; as_of reads records as of it
    m = w.materialize(["place:study"], lens="what_happened", since=2.0)
    assert {r.entity for r in m.assertions} == {"event:quarrel"}
    m = w.materialize(["place:study"], lens="what_happened", as_of=2.0)
    assert {r.entity for r in m.assertions} == {"event:toast"}


def test_s5_o5c_what_happened_window_unchanged(world):
    """§5 O5c: test_what_happened_window (tests/test_world.py) passes
    unchanged; its window, run here as well."""
    w = world
    _ingest(w, [
        {"entity": "event:theft", "attribute": "kind", "value": "theft", "valid_from": 5.0},
        {"entity": "event:theft", "attribute": "agent", "value": "person:rival",
         "value_type": "entity", "valid_from": 5.0},
        {"entity": "event:return", "attribute": "kind", "value": "return", "valid_from": 9.0},
        {"entity": "person:rival", "attribute": "kind", "value": "person", "timeless": True},
    ])
    m = w.materialize(["event:theft", "event:return", "person:rival"],
                      lens="what_happened", since=4.0, as_of=6.0)
    assert {r.value for r in m.assertions if r.attribute == "kind"} == {"theft"}
    assert [r.value for r in m.assertions if r.attribute == "agent"] == ["person:rival"]


def _seed_hall_door(w: World) -> None:
    _ingest(w, [
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "obj:door", "attribute": "kind", "value": "door", "timeless": True},
        {"entity": "obj:door", "attribute": "in", "value": "place:hall", "timeless": True},
    ])


def _situation_events(w: World, scope: str = "place:hall") -> list[tuple]:
    return [f for f in _facts(w.porcelain.snapshot(scope, lens="situation"))
            if f[0].startswith("event:") or f[1] in {"distinct_from", "same_as"}]


def test_s5_o5d_situation_emits_an_unclassified_live_event(world):
    """§5 O5d (EV8): a door broken at 4, caused_by event:kick, whose rows are
    unclassified: the situation bucket holds the kick's record."""
    w = world
    _seed_hall_door(w)
    _ingest(w, [{"entity": "event:kick", "attribute": "kind", "value": "kick",
                 "valid_from": 4.0}], classify="defer")
    _ingest(w, [{"entity": "obj:door", "attribute": "state", "value": "broken",
                 "valid_from": 4.0, "caused_by": "event:kick"}])
    assert _situation_events(w) == [("event:kick", "kind", "kick")]
    w.classifier.classify_all()
    assert _situation_events(w) == [("event:kick", "kind", "kick")]


def test_s5_o5e_a_non_event_cause_emits_nothing(world):
    """§5 O5e: a served row caused_by person:lysa: the bucket emits nothing
    (today: person:lysa's identity edges)."""
    w = world
    _seed_hall_door(w)
    _ingest(w, [
        {"entity": "person:lysa", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:mo", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "obj:door", "attribute": "state", "value": "broken",
         "valid_from": 4.0, "caused_by": "person:lysa"},
    ])
    assert w.porcelain.reject("person:lysa", "person:mo")["outcome"] == "rejected"
    w.classifier.classify_all()
    floor = _facts(w.porcelain.snapshot("place:hall", lens="current_state"))
    assert _facts(w.porcelain.snapshot("place:hall", lens="situation")) == floor
    assert _situation_events(w) == []


def test_s5_o5f_situation_lens_unchanged(world):
    """§5 O5f: SITUATION-LENS-V1's tests (tests/test_situation_lens.py) pass
    unchanged. Representative here: a live effect keeps its event, a
    superseded one drops it, and the bucket yields to budget by recency."""
    w = world
    _ingest(w, [
        {"entity": "place:tavern", "attribute": "kind", "value": "building", "timeless": True},
        {"entity": "obj:bar", "attribute": "kind", "value": "fixture", "timeless": True},
        {"entity": "obj:bar", "attribute": "in", "value": "place:tavern", "valid_from": 1.0},
        {"entity": "event:brawl", "attribute": "kind", "value": "brawl", "valid_from": 2.0},
        {"entity": "obj:bar", "attribute": "condition", "value": "dented",
         "valid_from": 2.0, "caused_by": "event:brawl"},
        {"entity": "event:repair", "attribute": "kind", "value": "repair", "valid_from": 4.0},
        {"entity": "obj:bar", "attribute": "condition", "value": "fixed",
         "valid_from": 4.0, "caused_by": "event:repair"},
        {"entity": "event:stash", "attribute": "kind", "value": "stash", "valid_from": 3.0},
        {"entity": "obj:chest", "attribute": "kind", "value": "chest", "timeless": True},
        {"entity": "obj:chest", "attribute": "in", "value": "place:tavern",
         "valid_from": 3.0, "caused_by": "event:stash"},
    ])
    m = w.materialize("place:tavern", lens="situation")
    events = [(r.entity, r.value) for r in m.assertions if r.entity.startswith("event:")]
    assert events == [("event:stash", "stash"), ("event:repair", "repair")]
    floor = len(m.assertions) - len(events)
    one = w.materialize("place:tavern", lens="situation", budget=floor + 1)
    assert [r.entity for r in one.assertions if r.entity.startswith("event:")] == [
        "event:repair"]
    assert one.truncated == 1


# ===================================================== §6 neighborhood's event edges


def _event_neighbours(w: World, entity: str, as_of: float | None) -> list[str]:
    out = w.porcelain.neighborhood(entity, edge_kinds=["events"], as_of=as_of)
    return sorted(n["entity"] for n in out["neighbors"])


def test_s6_o6a_a_zero_duration_event_stays_reachable(world):
    """§6 O6a (EV9): event:wave [5,5) with agent person:mara: an event
    neighbour at as_of 5 and 9 (today none), and at None; none at 4."""
    w = world
    _ingest(w, [
        {"entity": "person:mara", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "event:wave", "attribute": "kind", "value": "wave", "valid_from": 5.0,
         "valid_to": 5.0},
        {"entity": "event:wave", "attribute": "agent", "value": "person:mara",
         "value_type": "entity", "valid_from": 5.0, "valid_to": 5.0},
    ])
    assert _event_neighbours(w, "person:mara", None) == ["event:wave"]
    assert _event_neighbours(w, "person:mara", 5.0) == ["event:wave"]
    assert _event_neighbours(w, "person:mara", 9.0) == ["event:wave"]
    assert _event_neighbours(w, "person:mara", 4.0) == []


def test_s6_o6b_a_cause_on_a_merged_events_stored_id_is_reached(world):
    """§6 O6b: test_world_retrieval's event tests pass unchanged; a cause on a
    merged event's stored id is still reached (run here as well)."""
    w = world
    _ingest(w, [
        {"entity": "person:marn", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "event:gift", "attribute": "kind", "value": "gift", "valid_from": 1.0},
        {"entity": "event:gift", "attribute": "agent", "value": "person:marn",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "event:rumor", "attribute": "kind", "value": "rumor", "valid_from": 0.5},
        {"entity": "event:gift_alias", "attribute": "caused_by", "value": "event:rumor",
         "value_type": "entity", "valid_from": 1.0},
    ])
    w.registry.merge("event:gift", "event:gift_alias", "same gift event")
    out = w.neighborhood("person:marn", depth=2, edge_kinds=["events"])
    assert {"event:gift", "event:rumor"} <= {n["entity"] for n in out["neighbors"]}


def test_s6_an_agent_row_on_another_subject_is_not_an_event(world):
    """§6: a non-event subject with an `agent` row is not an event neighbour;
    the edges follow the records as of the read."""
    w = world
    _ingest(w, [
        {"entity": "person:mara", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "obj:puppet", "attribute": "kind", "value": "puppet", "timeless": True},
        {"entity": "obj:puppet", "attribute": "agent", "value": "person:mara",
         "value_type": "entity", "valid_from": 2.0},
        {"entity": "event:show", "attribute": "kind", "value": "show", "valid_from": 3.0},
        {"entity": "event:show", "attribute": "agent", "value": "person:mara",
         "value_type": "entity", "valid_from": 6.0},
        {"entity": "event:show", "attribute": "caused_by", "value": "event:booking",
         "value_type": "entity", "valid_from": 6.0},
        {"entity": "event:booking", "attribute": "kind", "value": "booking", "valid_from": 1.0},
    ])
    assert w.indexes.event_participation("person:mara") == ["event:show"]
    # as of 4 the show has occurred, but its agent row is stamped 6
    assert w.indexes.event_participation("person:mara", valid_as_of=4.0) == []
    assert w.indexes.event_participation("person:mara", valid_as_of=6.0) == ["event:show"]
    assert w.indexes.caused_by_of(["event:show"], valid_as_of=4.0) == []
    assert w.indexes.caused_by_of(["event:show"], valid_as_of=6.0) == ["event:booking"]
    # the show is an event neighbour and so is its cause; the puppet is not
    assert _event_neighbours(w, "person:mara", None) == ["event:booking", "event:show"]
    assert _event_neighbours(w, "person:mara", 4.0) == []
