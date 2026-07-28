"""MOVED-EVENT-V1 acceptance oracles (spec §Oracles).

Movement as a `kind=moved` event: coordinate-free extraction, the engine-authored
coordinate pass (prose mode), the strict payload/containment split, the never-
invent literal endpoint, `in_transit()`, and the additive `events()` payload.

The prose-fidelity oracles (2/3/4/9 — does the real model extract a moved event
from a probe passage) live with the Construct probe corpus under evals/; here the
gate/read INVARIANTS are exercised deterministically, stub-driven exactly as the
spec's oracle 5b prescribes ("feed a model stub that RETURNS a bogus coordinate").
"""

import pytest

from patternbuffer import World
from patternbuffer.ingest import _EXTRACT_RULES_FULL, _EXTRACT_RULES_LEAN
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "m.world", world_id="w:m", model=stub,
              stance="fiction", title="Moved Test World")
    w._stub = stub
    yield w
    w.close()


def _seed(w):
    """Two rooms and a person standing in the first (timeless placement)."""
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:garden", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "person:mara", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:mara", "attribute": "in", "value": "place:hall", "timeless": True},
    ])


def _rows(w, entity):
    return [r for r in w.buffer.all_rows() if r.entity == entity]


def _norm(rows):
    """Row identity minus physical-append allocation (seq / asserted_at / id)."""
    return sorted((r.entity, r.attribute, r.value, r.value_type,
                   r.valid_from, r.valid_to, r.frame) for r in rows)


# --------------------------------------------------------------------------- 1

def test_oracle1_prompt_pins_full_and_lean():
    # both rule blobs are single (implicitly-concatenated) strings
    for blob in (_EXTRACT_RULES_FULL, _EXTRACT_RULES_LEAN):
        assert "moved" in blob                          # the movement rule exists
        # the exact keys are pinned verbatim (not the synonyms actor/from/to/mode)
        for key in ("agent", "origin", "destination", "manner"):
            assert key in blob
    # person-typed condition lives in the full rule (movement is person motion)
    assert "person" in _EXTRACT_RULES_FULL


# ----------------------------------------------------------- 5 / 5a / 5e prose

def _moved_items(eid, agent, origin, destination, complete, *, bogus=False,
                 arrival=True, manner="walk"):
    """The coordinate-free shape a model emits in prose mode."""
    ev = [
        {"entity": eid, "attribute": "kind", "value": "moved", "complete": complete},
        {"entity": eid, "attribute": "agent", "value": agent, "value_type": "entity"},
        {"entity": eid, "attribute": "origin", "value": origin, "value_type": "entity"},
        {"entity": eid, "attribute": "destination", "value": destination,
         "value_type": "entity"},
        {"entity": eid, "attribute": "manner", "value": manner},
    ]
    if bogus:
        for it in ev:
            it["valid_from"] = 999.0
            it["valid_to"] = 1234.0
    if complete and arrival:
        arr = {"entity": agent, "attribute": "in", "value": destination,
               "value_type": "entity"}
        if bogus:
            arr["valid_from"] = 999.0
            arr["valid_to"] = 1234.0
        ev.append(arr)
    return ev


def test_oracle5a_5e_complete_prose_split_and_locate(world):
    w = world
    _seed(w)
    w.ingestor.cursor.advance(5.0)
    w.ingest_structured(_moved_items("event:m1", "person:mara", "place:hall",
                                     "place:garden", complete=True), extracted=True)
    # event PAYLOAD rows are zero-duration [5,5); arrival `in` is standing (no valid_to)
    for r in _rows(w, "event:m1"):
        assert r.valid_from == 5.0 and r.valid_to == 5.0
    arrival = [r for r in _rows(w, "person:mara")
               if r.attribute == "in" and r.value == "place:garden"]
    assert len(arrival) == 1
    assert arrival[0].valid_from == 5.0 and arrival[0].valid_to is None  # standing
    # 5e: locate flips at t AND t+1 (the r5-bug's exact inverse); before → origin
    assert w.locate("person:mara", valid_as_of=4.0) == ["place:hall"]
    assert w.locate("person:mara", valid_as_of=5.0) == ["place:garden"]
    assert w.locate("person:mara", valid_as_of=6.0) == ["place:garden"]
    # 5e: events() shows the zero-duration history; in_transit returns NONE
    ev = next(e for e in w.porcelain.events() if e["id"] == "event:m1")
    assert ev["valid_to"] == 5.0
    assert w.in_transit(agent="person:mara", as_of=5.0) == []


def test_oracle5b_prose_strips_bogus_structured_keeps(world, tmp_path):
    w = world
    _seed(w)
    w.ingestor.cursor.advance(5.0)
    # extracted=True → engine authors coordinates; the model's bogus numbers vanish
    w.ingest_structured(_moved_items("event:b1", "person:mara", "place:hall",
                                     "place:garden", complete=True, bogus=True),
                        extracted=True)
    for r in _rows(w, "event:b1"):
        assert r.valid_from == 5.0 and r.valid_to == 5.0     # cursor, not 999/1234
    arrival = [r for r in _rows(w, "person:mara")
               if r.attribute == "in" and r.value == "place:garden"][0]
    assert arrival.valid_from == 5.0 and arrival.valid_to is None  # NOT rewritten to t
    assert not any(r.valid_from == 999.0 or r.valid_to == 1234.0
                   for r in w.buffer.all_rows())            # no bogus reaches the log

    # a STRUCTURED caller (extracted=False) passing the same numerics KEEPS them
    stub2 = StubModel(fallback=rule_classifier_fallback())
    ws = World(tmp_path / "s.world", world_id="w:s", model=stub2, stance="fiction")
    _seed(ws)
    ws.ingest_structured([
        {"entity": "event:s1", "attribute": "kind", "value": "moved",
         "valid_from": 10.0, "valid_to": 20.0},
    ])
    kept = _rows(ws, "event:s1")[0]
    assert kept.valid_from == 10.0 and kept.valid_to == 20.0
    ws.close()


def test_oracle5b_ingest_recipe_byte_identical(tmp_path):
    items = _moved_items("event:j1", "person:mara", "place:hall", "place:garden",
                         complete=True)

    def build(path, wid, via_recipe):
        stub = StubModel(fallback=rule_classifier_fallback())
        w = World(path, world_id=wid, model=stub, stance="fiction")
        _seed(w)                                         # seed first (uses fallback)
        w.ingestor.cursor.advance(5.0)
        stub.enqueue({"items": [dict(i) for i in items]})  # THEN script the extract
        if via_recipe:
            got = w.ingestor.extract("K walked from the hall to the garden.")
            w.ingest_structured(got, extracted=True)
        else:
            w.ingest("K walked from the hall to the garden.")
        rows = _norm([r for r in w.buffer.all_rows()
                      if r.entity in ("event:j1", "person:mara")])
        w.close()
        return rows

    assert build(tmp_path / "a.world", "w:a", via_recipe=False) == \
           build(tmp_path / "b.world", "w:b", via_recipe=True)


def test_oracle5b_valid_to_without_valid_from_skipped(world):
    w = world
    _seed(w)
    w.ingest_structured([
        # timeless carries no story-time, so valid_from stays genuinely absent;
        # a closing coordinate with no opening one is skip-receipted (§ B.2b).
        {"entity": "event:x1", "attribute": "kind", "value": "moved",
         "timeless": True, "valid_to": 20.0},
    ])
    assert not _rows(w, "event:x1")
    assert any(s.reason == "valid_to_without_valid_from"
               for s in w.ingestor.last_skipped)


# --------------------------------------------------------------- 5c markers

@pytest.mark.parametrize("markers", [
    [],                                                  # missing
    ["true"],                                            # non-boolean
])
def test_oracle5c_marker_fail_closed(world, markers):
    w = world
    _seed(w)
    w.ingestor.cursor.advance(5.0)
    kind = {"entity": "event:c1", "attribute": "kind", "value": "moved"}
    if markers:
        kind["complete"] = markers[0]
    w.ingest_structured([
        kind,
        {"entity": "event:c1", "attribute": "agent", "value": "person:mara",
         "value_type": "entity"},
        {"entity": "event:c1", "attribute": "destination", "value": "place:garden",
         "value_type": "entity"},
        {"entity": "person:mara", "attribute": "in", "value": "place:garden",
         "value_type": "entity"},
    ], extracted=True)
    assert not _rows(w, "event:c1")                      # whole group dropped
    # the matched arrival `in` is dropped too — no orphan
    assert not [r for r in _rows(w, "person:mara")
                if r.attribute == "in" and r.value == "place:garden"]
    assert any(s.reason == "moved_marker_invalid" for s in w.ingestor.last_skipped)


def test_oracle5c_attribute_complete_row_is_dropped(world):
    w = world
    _seed(w)
    w.ingestor.cursor.advance(5.0)
    w.ingest_structured([
        {"entity": "event:c2", "attribute": "kind", "value": "moved",
         "complete": True},
        {"entity": "event:c2", "attribute": "agent", "value": "person:mara",
         "value_type": "entity"},
        {"entity": "event:c2", "attribute": "complete", "value": True},   # malformed
    ], extracted=True)
    # a well-formed group commits; the `attribute=complete` row never persists
    assert any(r.attribute == "kind" for r in _rows(w, "event:c2"))
    assert not any(r.attribute == "complete" for r in _rows(w, "event:c2"))


# --------------------------------------------------------------- 5d arrival

def test_oracle5d_exact_arrival_match_no_synthesis(world):
    w = world
    _seed(w)
    w.ingest_structured([
        {"entity": "person:seer", "attribute": "kind", "value": "person",
         "timeless": True},
    ])
    w.ingestor.cursor.advance(5.0)
    w.ingest_structured([
        {"entity": "event:d1", "attribute": "kind", "value": "moved",
         "complete": True},
        {"entity": "event:d1", "attribute": "agent", "value": "person:mara",
         "value_type": "entity"},
        {"entity": "event:d1", "attribute": "destination", "value": "place:garden",
         "value_type": "entity"},
        # the real arrival
        {"entity": "person:mara", "attribute": "in", "value": "place:garden",
         "value_type": "entity"},
        # a decoy: different entity, must be untouched
        {"entity": "person:seer", "attribute": "in", "value": "place:hall",
         "value_type": "entity"},
    ], extracted=True)
    arr = [r for r in _rows(w, "person:mara")
           if r.attribute == "in" and r.value == "place:garden"][0]
    assert arr.valid_from == 5.0 and arr.valid_to is None
    # the decoy (different entity) is NOT consumed as the arrival: it stays a
    # single standing row to its own place, never re-pointed to the destination
    decoys = [r for r in _rows(w, "person:seer") if r.attribute == "in"]
    assert len(decoys) == 1 and decoys[0].value == "place:hall"
    assert decoys[0].valid_to is None                   # standing, not a [t,t) event row


def test_oracle5d_literal_destination_no_arrival_no_invention(world):
    w = world
    _seed(w)
    w.ingestor.cursor.advance(5.0)
    w.ingest_structured([
        {"entity": "event:d2", "attribute": "kind", "value": "moved",
         "complete": False},
        {"entity": "event:d2", "attribute": "agent", "value": "person:mara",
         "value_type": "entity"},
        {"entity": "event:d2", "attribute": "destination", "value": "the misty moor",
         "value_type": "literal"},
    ], extracted=True)
    dest = [r for r in _rows(w, "event:d2") if r.attribute == "destination"][0]
    assert dest.value == "the misty moor" and dest.value_type == "literal"
    # never-invent: no entity minted for the literal name
    assert not any(r.value == "the misty moor" and r.value_type == "entity"
                   for r in w.buffer.all_rows())


def test_oracle5d_duplicate_arrival_all_sanitized_valid(world):
    # M1: TWO exact arrival rows (model duplicated it) on a complete move — BOTH
    # get the cursor split, neither retains a model-authored coordinate.
    w = world
    _seed(w)
    w.ingestor.cursor.advance(5.0)
    w.ingest_structured([
        {"entity": "event:dup", "attribute": "kind", "value": "moved", "complete": True},
        {"entity": "event:dup", "attribute": "agent", "value": "person:mara",
         "value_type": "entity"},
        {"entity": "event:dup", "attribute": "destination", "value": "place:garden",
         "value_type": "entity"},
        {"entity": "person:mara", "attribute": "in", "value": "place:garden",
         "value_type": "entity", "valid_from": 888.0, "valid_to": 999.0},
        {"entity": "person:mara", "attribute": "in", "value": "place:garden",
         "value_type": "entity", "valid_from": 111.0, "valid_to": 222.0},
    ], extracted=True)
    arrivals = [r for r in _rows(w, "person:mara")
                if r.attribute == "in" and r.value == "place:garden"]
    assert len(arrivals) == 2
    for a in arrivals:                                  # every match sanitized
        assert a.valid_from == 5.0 and a.valid_to is None
    assert not any(r.valid_from in (888.0, 111.0) or r.valid_to in (999.0, 222.0)
                   for r in w.buffer.all_rows())        # no bogus coordinate survives


def test_oracle5c_duplicate_arrival_all_dropped_on_invalid_marker(world):
    # M1: two exact arrival rows + an INVALID marker → the whole group AND BOTH
    # arrival rows drop; no duplicate orphan survives with invented coordinates.
    w = world
    _seed(w)
    w.ingestor.cursor.advance(5.0)
    w.ingest_structured([
        {"entity": "event:dbad", "attribute": "kind", "value": "moved"},  # no marker
        {"entity": "event:dbad", "attribute": "agent", "value": "person:mara",
         "value_type": "entity"},
        {"entity": "event:dbad", "attribute": "destination", "value": "place:garden",
         "value_type": "entity"},
        {"entity": "person:mara", "attribute": "in", "value": "place:garden",
         "value_type": "entity", "valid_from": 888.0, "valid_to": 999.0},
        {"entity": "person:mara", "attribute": "in", "value": "place:garden",
         "value_type": "entity", "valid_from": 111.0, "valid_to": 222.0},
    ], extracted=True)
    assert not _rows(w, "event:dbad")
    assert not [r for r in _rows(w, "person:mara")
                if r.attribute == "in" and r.value == "place:garden"]
    assert any(s.reason == "moved_marker_invalid" for s in w.ingestor.last_skipped)


def test_oracle5d_open_move_arrival_shaped_row_dropped(world):
    # M2: a valid complete=false event with an exact arrival-shaped `in` row is
    # contradictory (an open move has NO arrival). The row is dropped+receipted;
    # no invented coordinate survives and locate() stays at last-known origin.
    w = world
    _seed(w)
    # place mara somewhere first (a standing origin to stay put at)
    w.ingest_structured([
        {"entity": "person:mara", "attribute": "in", "value": "place:hall",
         "value_type": "entity", "timeless": True},
    ])
    w.ingestor.cursor.advance(5.0)
    w.ingest_structured([
        {"entity": "event:open", "attribute": "kind", "value": "moved", "complete": False},
        {"entity": "event:open", "attribute": "agent", "value": "person:mara",
         "value_type": "entity"},
        {"entity": "event:open", "attribute": "destination", "value": "place:garden",
         "value_type": "entity"},
        {"entity": "person:mara", "attribute": "in", "value": "place:garden",
         "value_type": "entity", "valid_from": 999.0, "valid_to": 1234.0},
    ], extracted=True)
    # the contradictory arrival row is gone (no bogus coordinate, no locate flip)
    assert not [r for r in _rows(w, "person:mara")
                if r.attribute == "in" and r.value == "place:garden"]
    assert not any(r.valid_from == 999.0 or r.valid_to == 1234.0
                   for r in w.buffer.all_rows())
    assert any(s.reason == "moved_open_with_arrival" for s in w.ingestor.last_skipped)
    assert w.locate("person:mara", valid_as_of=5.0) == ["place:hall"]  # last-known
    # the open event itself still stands and is in transit
    assert len(w.in_transit(agent="person:mara", as_of=5.0)) == 1


# --------------------------------------------------------------- 6 intervals

def test_oracle6a_open_event_last_known_origin(world):
    w = world
    _seed(w)
    w.ingestor.cursor.advance(5.0)
    w.ingest_structured(_moved_items("event:o1", "person:mara", "place:hall",
                                     "place:garden", complete=False, arrival=False),
                        extracted=True)
    # no valid_to authored on an open event
    assert all(r.valid_to is None for r in _rows(w, "event:o1"))
    # locate stays last-known origin; in_transit returns the event w/ origin head
    assert w.locate("person:mara", valid_as_of=5.0) == ["place:hall"]
    it = w.in_transit(agent="person:mara", as_of=5.0)
    assert len(it) == 1 and it[0]["last_known_containment"] == "place:hall"
    assert it[0]["origin"] == "place:hall" and it[0]["destination"] == "place:garden"


def test_oracle6b_structured_interval_flip_and_in_transit_boundary(world):
    w = world
    _seed(w)
    # structured closed interval [10,20]; caller authors the arrival at 20
    w.ingest_structured([
        {"entity": "event:i1", "attribute": "kind", "value": "moved",
         "valid_from": 10.0, "valid_to": 20.0},
        {"entity": "event:i1", "attribute": "agent", "value": "person:mara",
         "value_type": "entity", "valid_from": 10.0, "valid_to": 20.0},
        {"entity": "event:i1", "attribute": "origin", "value": "place:hall",
         "value_type": "entity", "valid_from": 10.0, "valid_to": 20.0},
        {"entity": "event:i1", "attribute": "destination", "value": "place:garden",
         "value_type": "entity", "valid_from": 10.0, "valid_to": 20.0},
        {"entity": "person:mara", "attribute": "in", "value": "place:garden",
         "value_type": "entity", "valid_from": 20.0},
    ])
    # containment flips to destination only at/after valid_to
    assert w.locate("person:mara", valid_as_of=15.0) == ["place:hall"]
    assert w.locate("person:mara", valid_as_of=20.0) == ["place:garden"]
    # in_transit returns it strictly inside; stops exactly at valid_to
    assert len(w.in_transit(agent="person:mara", as_of=15.0)) == 1
    assert w.in_transit(agent="person:mara", as_of=20.0) == []


def test_oracle6c_zero_duration_invisible_to_asof_visible_in_events(world):
    w = world
    _seed(w)
    w.ingestor.cursor.advance(5.0)
    w.ingest_structured(_moved_items("event:z1", "person:mara", "place:hall",
                                     "place:garden", complete=True), extracted=True)
    # [5,5) is invisible to any as-of valid-time read at t (exclusive bound)
    at_t = w.buffer.visible(entity="event:z1", valid_as_of=5.0)
    assert at_t == []
    # but events() reads history without valid-time filtering
    assert any(e["id"] == "event:z1" for e in w.porcelain.events())
    assert w.in_transit(agent="person:mara", as_of=5.0) == []


def test_oracle6d_inverted_interval_rejected(world):
    w = world
    _seed(w)
    w.ingest_structured([
        {"entity": "event:v1", "attribute": "kind", "value": "moved",
         "valid_from": 20.0, "valid_to": 10.0},          # inverted
    ])
    assert not _rows(w, "event:v1")
    assert any(s.reason == "valid_to_before_valid_from"
               for s in w.ingestor.last_skipped)


# --------------------------------------------------------------- 7 two moves

def test_oracle7_two_moves_one_person_distinct(world):
    w = world
    _seed(w)
    w.ingestor.cursor.advance(5.0)
    w.ingest_structured(_moved_items("event:t1", "person:mara", "place:hall",
                                     "place:garden", complete=True), extracted=True)
    w.ingestor.cursor.advance(9.0)
    w.ingest_structured(_moved_items("event:t2", "person:mara", "place:garden",
                                     "place:hall", complete=True), extracted=True)
    e1 = {r.attribute: r.value for r in _rows(w, "event:t1")}
    e2 = {r.attribute: r.value for r in _rows(w, "event:t2")}
    assert e1["origin"] == "place:hall" and e1["destination"] == "place:garden"
    assert e2["origin"] == "place:garden" and e2["destination"] == "place:hall"
    ids = {e["id"] for e in w.porcelain.events()}
    assert {"event:t1", "event:t2"} <= ids


# --------------------------------------------------------------- 8 global safety

def test_oracle8_unrelated_predicates_untouched(world):
    w = world
    _seed(w)
    # a document with its OWN origin, and other entities carrying the movement
    # attribute names as plain facts — none of this is a moved event
    w.ingest_structured([
        {"entity": "doc:charter", "attribute": "kind", "value": "document",
         "timeless": True},
        {"entity": "doc:charter", "attribute": "origin", "value": "the archive",
         "timeless": True},
        {"entity": "person:mara", "attribute": "actor", "value": "guild",
         "timeless": True},
    ])
    doc = [r for r in _rows(w, "doc:charter") if r.attribute == "origin"][0]
    assert doc.value == "the archive"                    # unchanged, no coordinate pass
    assert w.in_transit() == []                          # nothing is in transit


# --------------------------------------------------------------- 10 no doorway

def test_oracle10_no_second_doorway(world):
    w = world
    _seed(w)
    w.ingestor.cursor.advance(5.0)
    # a complete move to a bound destination but NO arrival `in` item in the batch
    w.ingest_structured(_moved_items("event:n1", "person:mara", "place:hall",
                                     "place:garden", complete=True, arrival=False),
                        extracted=True)
    # nothing synthesizes an arrival — mara stays in the hall (last-known)
    assert w.locate("person:mara", valid_as_of=6.0) == ["place:hall"]
    assert not [r for r in _rows(w, "person:mara")
                if r.attribute == "in" and r.value == "place:garden"]


# --------------------------------------------------------------- 11 read/join

def test_oracle11_events_six_key_byte_shape(world):
    w = world
    _seed(w)
    w.ingestor.cursor.advance(5.0)
    # a plain (non-moved) event must ALSO carry the six keys, None-defaulted
    w.ingest_structured([
        {"entity": "event:plain", "attribute": "kind", "value": "theft",
         "valid_from": 5.0},
    ])
    plain = next(e for e in w.porcelain.events() if e["id"] == "event:plain")
    for key in ("origin", "destination", "manner", "valid_to",
                "origin_bound", "destination_bound"):
        assert key in plain and plain[key] is None
    # a moved event with a literal destination: destination_bound is False
    w.ingest_structured([
        {"entity": "event:mv", "attribute": "kind", "value": "moved",
         "complete": False},
        {"entity": "event:mv", "attribute": "agent", "value": "person:mara",
         "value_type": "entity"},
        {"entity": "event:mv", "attribute": "origin", "value": "place:hall",
         "value_type": "entity"},
        {"entity": "event:mv", "attribute": "destination", "value": "far off",
         "value_type": "literal"},
    ], extracted=True)
    mv = next(e for e in w.porcelain.events() if e["id"] == "event:mv")
    assert mv["origin_bound"] is True                    # entity-valued
    assert mv["destination_bound"] is False              # literal
    assert mv["destination"] == "far off" and mv["origin"] == "place:hall"


def test_oracle11_in_transit_fixed_five_key_shape(world):
    w = world
    _seed(w)
    w.ingestor.cursor.advance(5.0)
    w.ingest_structured(_moved_items("event:it", "person:mara", "place:hall",
                                     "place:garden", complete=False, arrival=False),
                        extracted=True)
    [rec] = w.in_transit(as_of=5.0)
    assert set(rec) == {"agent", "origin", "destination", "manner",
                        "last_known_containment"}
    assert rec["agent"] == "person:mara"
    assert rec["last_known_containment"] == "place:hall"
    # World and porcelain signatures agree; porcelain result mirrors keys
    assert w.porcelain.in_transit(as_of=5.0)[0].keys() == rec.keys()


def test_oracle11_in_transit_agent_filter_identity_aware(world):
    w = world
    _seed(w)
    # a same_as-merged id resolves to the head; the filter (like events') resolves
    # before comparing, so any identity alias of the agent selects the event
    w.ingest_structured([
        {"entity": "person:maid", "attribute": "same_as", "value": "person:mara",
         "value_type": "entity"},
    ])
    w.ingestor.cursor.advance(5.0)
    w.ingest_structured(_moved_items("event:af", "person:mara", "place:hall",
                                     "place:garden", complete=False, arrival=False),
                        extracted=True)
    by_alias = w.in_transit(agent="person:maid", as_of=5.0)
    assert len(by_alias) == 1 and by_alias[0]["agent"] == "person:mara"


# --------------------------------------------------------------- 11a anchor

def test_oracle11a_anchor_decision_invariant_under_permutation(tmp_path):
    """The include/exclude DECISION is stable when payload-row order changes and
    a first-use attr:* declaration is inserted — the anchor is (valid_from, min
    asserted_at over payload rows), not a physical-append accident."""
    def decision(order, seed_extra):
        stub = StubModel(fallback=rule_classifier_fallback())
        w = World(tmp_path / f"anch{order[0]}{seed_extra}.world",
                  world_id=f"w:anch{order[0]}{int(seed_extra)}", model=stub,
                  stance="fiction")
        _seed(w)
        if seed_extra:
            # a first-use attr:* declaration lands before the event's rows
            w.ingest_structured([{"entity": "misc:thing", "attribute": "hue",
                                  "value": "grey", "timeless": True}])
        w.ingestor.cursor.advance(5.0)
        base = _moved_items("event:p1", "person:mara", "place:hall",
                            "place:garden", complete=False, arrival=False)
        rows = [base[i] for i in order]                  # permuted payload identities
        w.ingest_structured(rows, extracted=True)
        out = bool(w.in_transit(agent="person:mara", as_of=5.0))
        w.close()
        return out
    # origin-before-event (the timeless hall `in` from _seed) → IN TRANSIT, stable
    assert decision([0, 1, 2, 3, 4], False) is True
    assert decision([4, 3, 2, 1, 0], True) is True
    assert decision([2, 0, 4, 1, 3], True) is True


# --------------------------------------------------------------- 12 no-degrade

def test_oracle12_location_clause_still_fires_non_moved(world):
    w = world
    _seed(w)
    # an ordinary containment change (not a moved event) still ingests normally
    w.ingestor.cursor.advance(3.0)
    w.ingest_structured([
        {"entity": "person:mara", "attribute": "in", "value": "place:garden",
         "valid_from": 3.0},
    ])
    assert w.locate("person:mara", valid_as_of=3.0) == ["place:garden"]
