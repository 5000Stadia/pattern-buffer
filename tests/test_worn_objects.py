"""WORN-OBJECTS-V1 (R41, E3): what a person wears is things, invented like a
room's contents. One test group per entry of specs/WORN-OBJECTS-V1.md's Tests
section (1-8), with every witness the spec names."""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

import pytest

from patternbuffer import AtomicAbort, World, task_request
from patternbuffer.identity import IdentityRegistry
from patternbuffer.model import TASK_RESOLVE

VF = "knows:person:watcher"


class Gen:
    """A model callable that answers each resolve from a queue (the last answer
    repeats) and records every resolve call; any other task is classified."""

    def __init__(self, *answers):
        self.answers = list(answers) or [{"items": [{"value": "a grey wool coat",
                                                      "kind": "garment"}]}]
        self.calls = []

    def __call__(self, prompt, schema):
        if schema.get("title") == TASK_RESOLVE:
            self.calls.append((prompt, schema))
            return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return {"durability": "CONSTITUTIVE", "class_confidence": 0.9, "verdicts": []}

    @property
    def requests(self):
        return [task_request(s) for _, s in self.calls]


def _world(tmp_path, *answers, name="worn.world"):
    model = Gen(*answers)
    w = World(tmp_path / name, "w:worn", model=model)
    return w, model


def _declare(w, aspect, *kinds):
    r = w.porcelain.ingest_structured(
        [{"entity": f"attr:{aspect}", "attribute": "resolvable_for", "value": k,
          "timeless": True} for k in kinds], classify="rules")
    assert r.skipped == []


def _seed(w):
    """A hall, and Mara (a person) standing in it."""
    w.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "person:mara", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:mara", "attribute": "in", "value": "place:hall",
         "value_type": "entity", "valid_from": 1.0},
    ], classify="rules")


def _edge(entity, attribute, value, valid_from=1.0):
    return {"entity": entity, "attribute": attribute, "value": value,
            "value_type": "entity", "valid_from": valid_from}


def _thing(entity, kind=None, names=(), valid_from=None):
    out = []
    if kind is not None:
        out.append({"entity": entity, "attribute": "kind", "value": kind,
                    "timeless": valid_from is None, **(
                        {} if valid_from is None else {"valid_from": valid_from})})
    for n in names:
        out.append({"entity": entity, "attribute": "name", "value": n,
                    "timeless": valid_from is None, **(
                        {} if valid_from is None else {"valid_from": valid_from})})
    return out


def _attire_world(tmp_path, *answers, name="worn.world"):
    w, model = _world(tmp_path, *answers, name=name)
    _seed(w)
    _declare(w, "attire", "person")
    return w, model


def _minted(w, owner="person:mara", frame="canon"):
    """The minted garments worn by ``owner``, in minting order."""
    return [r.entity for r in w.buffer.visible(attribute="worn_by", frame=frame)
            if r.status == "generated" and r.value == owner]


# ---------------------------------------------------------------- 1. mints

def test_1_attire_mints_garments_worn_by_the_person(tmp_path):
    w, model = _attire_world(tmp_path, {"items": [
        {"value": "a grey wool coat", "kind": "garment"},
        {"value": "mud-stiff boots", "kind": "footwear"}]})
    try:
        out = w.porcelain.resolve("person:mara", "attire", at=5.0)
        assert out["status"] == "resolved" and out["planted"] is True
        ids = _minted(w)
        assert len(ids) == 2 and all(i.startswith("obj:gen_") for i in ids)
        for eid, (kind, name) in zip(ids, [("garment", "a grey wool coat"),
                                          ("footwear", "mud-stiff boots")]):
            assert w.state(eid, "kind").winner.value == kind
            assert w.state(eid, "name").winner.value == name
            edge = w.buffer.visible(entity=eid, attribute="worn_by")[0]
            assert (edge.value, edge.value_type, edge.status, edge.valid_from) == \
                ("person:mara", "entity", "generated", 5.0)
            assert w.classifier.durability(edge.id) == "STATE"          # a coat comes off
            for attr in ("kind", "name"):
                row = w.buffer.visible(entity=eid, attribute=attr)[0]
                assert row.status == "generated"
                assert w.classifier.durability(row.id) == "CONSTITUTIVE"
        # the memo: a second resolve serves it, with no new rows and no model call
        head, calls = w.buffer.head(), len(model.calls)
        again = w.porcelain.resolve("person:mara", "attire")
        assert w.buffer.head() == head and len(model.calls) == calls
        assert [f["entity"] for f in again["facts"]] == ids
        assert "planted" not in again
        # the containment family serves them (P2: contents are derived)
        assert set(ids) <= set(w.contents("person:mara"))
        assert w.locate(ids[0]) == ["person:mara", "place:hall"]
    finally:
        w.close()


def test_1_the_attire_aspect_is_declared_or_nothing_is_invented(tmp_path):
    w, model = _world(tmp_path)
    try:
        _seed(w)
        _declare(w, "wears", "person")          # a different aspect: attire is not opened
        out = w.porcelain.resolve("person:mara", "attire")
        assert out["status"] == "undeclared" and model.calls == []
        assert _minted(w) == []
    finally:
        w.close()


# --------------------------------------------------- 2. existing, at `at`

def _request_for(model):
    (req,) = model.requests
    return req


def test_2_a_stated_hat_still_plants_attire_and_is_exactly_existing(tmp_path):
    w, model = _attire_world(tmp_path)
    try:
        w.ingest_structured(_thing("obj:hat", "garment", ["a red hat"])
                            + [_edge("obj:hat", "worn_by", "person:mara")], classify="rules")
        out = w.porcelain.resolve("person:mara", "attire", at=5.0)
        assert out["planted"] is True and len(_minted(w)) == 1        # no "nothing worn" guard
        req = _request_for(model)
        assert req.aspect == "attire" and req.kind == "person"
        assert req.existing == (("obj:hat", "garment", ("a red hat",)),)
    finally:
        w.close()


def test_2_decoys_taken_off_and_future_edges_are_not_existing(tmp_path):
    w, model = _attire_world(tmp_path)
    try:
        w.ingest_structured(
            [{"entity": "place:chest", "attribute": "kind", "value": "place", "timeless": True}]
            + _thing("obj:hat", "garment", ["a red hat"])
            + _thing("obj:bag", "bag", ["a leather bag"])
            + _thing("obj:satchel", "bag", ["a satchel"])
            + _thing("obj:cloak", "garment", ["a green cloak"])
            + _thing("obj:ring", "jewel", ["a silver ring"])
            + [_edge("obj:hat", "worn_by", "person:mara"),
               _edge("obj:bag", "held_by", "person:mara"),            # decoy: held
               _edge("obj:satchel", "carried_by", "person:mara"),     # decoy: carried
               _edge("obj:cloak", "worn_by", "person:mara", 1.0),     # worn earlier ...
               _edge("obj:cloak", "in", "place:chest", 3.0),          # ... then put in a chest
               _edge("obj:ring", "worn_by", "person:mara", 9.0)],     # worn later than `at`
            classify="rules")
        w.porcelain.resolve("person:mara", "attire", at=5.0)
        assert _request_for(model).existing == (("obj:hat", "garment", ("a red hat",)),)
        # the future edge is not counted, and the resolve still minted
        assert len(_minted(w)) == 1
    finally:
        w.close()


def test_2_contents_still_plants_only_into_an_empty_place_and_has_no_existing(tmp_path):
    w, model = _world(tmp_path, {"items": [{"value": "a rusted key", "kind": "key"}]})
    try:
        w.ingest_structured([
            {"entity": "place:attic", "attribute": "kind", "value": "attic", "timeless": True},
            {"entity": "place:cellar", "attribute": "kind", "value": "cellar", "timeless": True},
            {"entity": "obj:trunk", "attribute": "kind", "value": "trunk", "timeless": True},
            _edge("obj:trunk", "in", "place:cellar"),
        ], classify="rules")
        _declare(w, "contents", "attic", "cellar")
        busy = w.porcelain.resolve("place:cellar", "contents", at=5.0)
        assert busy["facts"] == [] and model.calls == []              # E1 guard, unchanged
        assert not w.resolver.has_thunk("place:cellar", "contents")
        empty = w.porcelain.resolve("place:attic", "contents", at=5.0)
        assert empty["planted"] is True and len(empty["facts"]) == 1
        assert _request_for(model).existing == ()
        assert [f["attribute"] for f in empty["facts"]] == ["in"]
    finally:
        w.close()


def test_2_a_non_minting_aspect_has_no_existing(tmp_path):
    w, model = _world(tmp_path)
    try:
        _seed(w)
        _declare(w, "wears", "person")
        w.ingest_structured(_thing("obj:hat", "garment", ["a red hat"])
                            + [_edge("obj:hat", "worn_by", "person:mara")], classify="rules")
        w.porcelain.resolve("person:mara", "wears", at=5.0)
        assert _request_for(model).existing == ()
    finally:
        w.close()


def test_2_shape_unkinded_unnamed_item_is_id_none_empty(tmp_path):
    w, model = _attire_world(tmp_path)
    try:
        w.ingest_structured([_edge("obj:plain", "worn_by", "person:mara")], classify="rules")
        w.porcelain.resolve("person:mara", "attire", at=5.0)
        assert _request_for(model).existing == (("obj:plain", None, ()),)
    finally:
        w.close()


def test_2_shape_two_names_are_both_given_sorted(tmp_path):
    w, model = _attire_world(tmp_path)
    try:
        w.ingest_structured(_thing("obj:coat", "garment", ["the old coat", "a brown coat"])
                            + [_edge("obj:coat", "worn_by", "person:mara")], classify="rules")
        w.porcelain.resolve("person:mara", "attire", at=5.0)
        assert _request_for(model).existing == (
            ("obj:coat", "garment", ("a brown coat", "the old coat")),)
    finally:
        w.close()


def test_2_shape_a_name_and_kind_valid_only_after_at_do_not_appear(tmp_path):
    def build(name):
        w, model = _attire_world(tmp_path, name=name)
        w.ingest_structured(
            [_edge("obj:cape", "worn_by", "person:mara", 1.0)]
            + _thing("obj:cape", "garment", ["a velvet cape"], valid_from=9.0), classify="rules")
        return w, model

    w, model = build("early.world")
    try:
        w.porcelain.resolve("person:mara", "attire", at=5.0)
        assert _request_for(model).existing == (("obj:cape", None, ()),)
    finally:
        w.close()
    later, model2 = build("late.world")           # a second world, resolved at the later time
    try:
        later.porcelain.resolve("person:mara", "attire", at=10.0)
        assert _request_for(model2).existing == (("obj:cape", "garment", ("a velvet cape",)),)
    finally:
        later.close()


def test_2_shape_an_edge_added_after_the_plant_but_before_the_force_is_given(tmp_path):
    w, model = _attire_world(tmp_path)
    try:
        # a host plants the placeholder at 3.0 ...
        w.ingest_structured([{"entity": "person:mara", "attribute": "attire",
                              "value": {"policy": "invent_under_canon"},
                              "value_type": "unresolved", "valid_from": 3.0}])
        # ... the story then states a garment, valid at 3.0, before anything forces it
        w.ingest_structured(_thing("obj:scarf", "garment", ["a blue scarf"])
                            + [_edge("obj:scarf", "worn_by", "person:mara", 2.0)],
                            classify="rules")
        out = w.porcelain.resolve("person:mara", "attire")
        assert "planted" not in out and len(_minted(w)) == 1
        assert _request_for(model).existing == (("obj:scarf", "garment", ("a blue scarf",)),)
    finally:
        w.close()


def test_2_shape_order_is_by_id_whatever_the_write_order(tmp_path):
    w, model = _attire_world(tmp_path)
    try:
        for eid in ("obj:zeta", "obj:alpha", "obj:mid"):
            w.ingest_structured(_thing(eid, "garment", [f"{eid[4:]} cloth"])
                                + [_edge(eid, "worn_by", "person:mara")], classify="rules")
        w.porcelain.resolve("person:mara", "attire", at=5.0)
        got = _request_for(model).existing
        assert [row[0] for row in got] == ["obj:alpha", "obj:mid", "obj:zeta"]
        assert got[0] == ("obj:alpha", "garment", ("alpha cloth",))
    finally:
        w.close()


# ------------------------------------------------------------ 3. taking off

def test_3_a_stolen_coat_moves_and_the_memo_stands(tmp_path):
    w, model = _attire_world(tmp_path, {"items": [{"value": "a grey wool coat",
                                                   "kind": "garment"}]})
    try:
        w.ingest_structured([
            {"entity": "person:thief", "attribute": "kind", "value": "person", "timeless": True},
            _edge("person:thief", "in", "place:hall"),
        ], classify="rules")
        first = w.porcelain.resolve("person:mara", "attire", at=5.0)
        (coat,) = _minted(w)
        marker_ids = [f["provenance"]["assertion_id"] for f in first["facts"]] \
            if "assertion_id" in first["facts"][0].get("provenance", {}) else None
        w.ingest_structured([_edge(coat, "carried_by", "person:thief", 7.0)], classify="rules")
        assert w.locate(coat)[0] == "person:thief"
        assert coat in w.contents("person:thief") and coat not in w.contents("person:mara")
        head, calls = w.buffer.head(), len(model.calls)
        again = w.porcelain.resolve("person:mara", "attire")
        # the memo rows are the original generated edges; nothing was rewritten
        assert [f["entity"] for f in again["facts"]] == [coat]
        assert [f["attribute"] for f in again["facts"]] == ["worn_by"]
        assert w.buffer.head() == head and len(model.calls) == calls
        assert marker_ids is None or marker_ids == [
            f["provenance"]["assertion_id"] for f in again["facts"]]
        # as of before the theft she still wears it
        assert coat in w.contents("person:mara", valid_as_of=6.0)
    finally:
        w.close()


# ----------------------------------------------------------------- 4. looks

_LOOK_ANSWER = {"items": [{"value": "a grey wool coat", "kind": "garment",
                           "aspects": {"colour": "grey", "weight": 2.5, "worn_out": True,
                                       "smell": "musty",                 # undeclared
                                       "pattern": {"stripe": "thin"},    # structured
                                       "fit": ["loose"]}}]}              # structured


def _look_world(tmp_path, answer=None):
    w, model = _attire_world(tmp_path, answer or _LOOK_ANSWER)
    for aspect in ("colour", "weight", "worn_out", "pattern", "fit"):
        _declare(w, aspect, "garment")
    # colour is the garment's own: pinned CONSTITUTIVE, so a generated colour is
    # timeless and a stated one (ingested in rules mode) folds against it by rank
    w.porcelain.ingest_structured(
        [{"entity": "attr:colour", "attribute": "durability", "value": "CONSTITUTIVE",
          "timeless": True}], classify="rules")
    return w, model


def test_4_declared_aspects_become_generated_rows_and_the_rest_are_dropped(tmp_path, caplog):
    w, model = _look_world(tmp_path)
    try:
        with caplog.at_level(logging.WARNING):
            out = w.porcelain.resolve("person:mara", "attire", at=5.0)
        (coat,) = _minted(w)
        looks = {r.attribute: r for r in w.buffer.visible(entity=coat)
                 if r.attribute in ("colour", "weight", "worn_out", "smell", "pattern", "fit")}
        assert {a: r.value for a, r in looks.items()} == \
            {"colour": "grey", "weight": 2.5, "worn_out": True}
        assert all(r.status == "generated" and r.value_type == "literal"
                   for r in looks.values())
        assert all(w.classifier.get(r.id) is not None for r in looks.values())  # classified
        assert looks["colour"].valid_from is None            # pinned CONSTITUTIVE: timeless
        assert looks["weight"].valid_from == 5.0             # unpinned: from the placeholder's time
        # dropped: undeclared and structured, three in all, logged and counted
        assert out["dropped_aspects"] == 3
        assert "3 item aspect pair(s) dropped" in out["receipt"]["warnings"][0]
        warned = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("'smell'" in m for m in warned) and any("'pattern'" in m for m in warned) \
            and any("'fit'" in m for m in warned)
        # never free text on the item
        assert w.buffer.visible(entity=coat, attribute="smell") == []
        # the memo serves again with no count
        again = w.porcelain.resolve("person:mara", "attire")
        assert "dropped_aspects" not in again
        # a clean resolve carries no count either
    finally:
        w.close()


def test_4_an_aspect_declared_for_another_kind_is_dropped(tmp_path):
    w, _ = _attire_world(tmp_path, {"items": [{"value": "a brass key", "kind": "key",
                                               "aspects": {"colour": "brass"}}]})
    try:
        _declare(w, "colour", "garment")              # not for a key
        out = w.porcelain.resolve("person:mara", "attire", at=5.0)
        (key,) = _minted(w)
        assert w.buffer.visible(entity=key, attribute="colour") == []
        assert out["dropped_aspects"] == 1
    finally:
        w.close()


def test_4_non_finite_floats_and_minting_aspects_are_not_looks(tmp_path):
    w, _ = _attire_world(tmp_path, {"items": [{"value": "a coat", "kind": "garment",
        "aspects": {"weight": float("nan"), "colour": None, "contents": "a key"}}]})
    try:
        for aspect in ("weight", "colour", "contents"):
            _declare(w, aspect, "garment")
        out = w.porcelain.resolve("person:mara", "attire", at=5.0)
        (coat,) = _minted(w)
        assert [r for r in w.buffer.visible(entity=coat)
                if r.attribute in ("weight", "colour", "contents")] == []
        assert out["dropped_aspects"] == 3
    finally:
        w.close()


def test_4_contents_items_carry_looks_too(tmp_path):
    w, _ = _world(tmp_path, {"items": [{"value": "a brass key", "kind": "key",
                                        "aspects": {"colour": "brass", "age": "old"}}]})
    try:
        w.ingest_structured([{"entity": "place:attic", "attribute": "kind",
                              "value": "attic", "timeless": True}], classify="rules")
        _declare(w, "contents", "attic")
        _declare(w, "colour", "key")
        out = w.porcelain.resolve("place:attic", "contents", at=2.0)
        (key,) = [f["entity"] for f in out["facts"]]
        rows = w.buffer.visible(entity=key, attribute="colour")
        assert [(r.value, r.status) for r in rows] == [("brass", "generated")]
        assert out["dropped_aspects"] == 1                           # age is undeclared
    finally:
        w.close()


def test_4_a_later_stated_colour_overrides_the_generated_one(tmp_path):
    w, _ = _look_world(tmp_path)
    try:
        w.porcelain.resolve("person:mara", "attire", at=5.0)
        (coat,) = _minted(w)
        assert w.state(coat, "colour").winner.value == "grey"
        w.ingest_structured([{"entity": coat, "attribute": "colour", "value": "crimson",
                              "valid_from": 6.0}], classify="rules")
        winner = w.state(coat, "colour").winner
        assert (winner.value, winner.status) == ("crimson", "stated")
    finally:
        w.close()


def test_4_a_resolve_that_mints_no_aspects_writes_no_count(tmp_path):
    w, _ = _attire_world(tmp_path)
    try:
        out = w.porcelain.resolve("person:mara", "attire", at=5.0)
        assert "dropped_aspects" not in out and out["receipt"]["warnings"] == []
    finally:
        w.close()


# ---------------------------------------------------------------- 5. mirror

def test_5_the_mirror_carries_edge_kind_name_and_looks_in_one_unit(tmp_path):
    w, model = _look_world(tmp_path)
    calls = []
    real = w.buffer.atomic_unit
    w.buffer.atomic_unit = lambda body: (calls.append(1), real(body))[1]
    try:
        out = w.porcelain.resolve("person:mara", "attire", at=5.0, perceive_in=VF)
        assert len(calls) == 1
        (coat,) = _minted(w)
        view = {(r.attribute, str(r.value)): r for r in w.buffer.visible(entity=coat, frame=VF)}
        assert set(view) == {("worn_by", "person:mara"), ("kind", "garment"),
                             ("name", "a grey wool coat"), ("colour", "grey"),
                             ("weight", "2.5"), ("worn_out", "True")}
        assert all(r.status == "observed" and r.frame == VF for r in view.values())
        assert {f["attribute"] for f in out["perceived"]["facts"]} == \
            {"worn_by", "kind", "name", "colour", "weight", "worn_out"}
        # the frame sees the coat's colour, and wears it
        assert w.porcelain.state(coat, "colour", frame=VF)["fact"]["value"] == "grey"
        assert coat in w.contents("person:mara", frame=VF)
        # a memo serve mirrors nothing more into a frame that holds it all
        head = w.buffer.head()
        w.porcelain.resolve("person:mara", "attire", at=6.0, perceive_in=VF)
        assert w.buffer.head() == head
    finally:
        w.close()


def test_5_a_gate_refusal_rolls_back_everything(tmp_path):
    w, model = _look_world(tmp_path)
    head = w.buffer.head()
    try:
        with pytest.raises(AtomicAbort) as caught:
            w.porcelain.resolve("person:mara", "attire", at=float("inf"), perceive_in=VF)
        assert caught.value.cause == "gate_skip"
        assert len(model.calls) == 1 and w.buffer.head() == head
        assert _minted(w) == [] and not w.buffer.poisoned
        assert w.buffer.visible(entity="person:mara", attribute="attire") == []
    finally:
        w.close()


def test_5_contents_are_mirrored_with_their_looks_too(tmp_path):
    w, _ = _world(tmp_path, {"items": [{"value": "a brass key", "kind": "key",
                                        "aspects": {"colour": "brass"}}]})
    try:
        w.ingest_structured([{"entity": "place:attic", "attribute": "kind",
                              "value": "attic", "timeless": True}], classify="rules")
        _declare(w, "contents", "attic")
        _declare(w, "colour", "key")
        out = w.porcelain.resolve("place:attic", "contents", at=2.0, perceive_in=VF)
        got = {(f["attribute"], f["value"]) for f in out["perceived"]["facts"]}
        assert {("kind", "key"), ("name", "a brass key"), ("colour", "brass")} <= got
    finally:
        w.close()


# -------------------------------------------------------------- 6. identity

def _two_dresses(tmp_path, name):
    """Two women, each wearing a minted "red wool dress"."""
    w, _ = _world(tmp_path, {"items": [{"value": "red wool dress", "kind": "garment"}]},
                  name=name)
    w.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "person:ann", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:bea", "attribute": "kind", "value": "person", "timeless": True},
        _edge("person:ann", "in", "place:hall"), _edge("person:bea", "in", "place:hall"),
    ], classify="rules")
    _declare(w, "attire", "person")
    w.porcelain.resolve("person:ann", "attire", at=5.0)
    w.porcelain.resolve("person:bea", "attire", at=5.0)
    ann, bea = _minted(w, "person:ann")[0], _minted(w, "person:bea")[0]
    return w, ann, bea


def _stated_dresses(tmp_path, name):
    """The same two dresses, with the names STATED by the story."""
    w, _ = _world(tmp_path, name=name)
    w.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "person:ann", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:bea", "attribute": "kind", "value": "person", "timeless": True},
        _edge("person:ann", "in", "place:hall"), _edge("person:bea", "in", "place:hall"),
        *_thing("obj:dress_a", "garment", ["red wool dress"]),
        *_thing("obj:dress_b", "garment", ["red wool dress"]),
        _edge("obj:dress_a", "worn_by", "person:ann"),
        _edge("obj:dress_b", "worn_by", "person:bea"),
    ], classify="rules")
    return w, "obj:dress_a", "obj:dress_b"


def _proposals(w):
    return w.buffer.visible(attribute="maybe_same_as")


def test_6_generated_shared_names_are_not_identity_evidence(tmp_path):
    w, ann, bea = _two_dresses(tmp_path, "gen.world")
    try:
        assert ann != bea
        assert w.registry.reconcile() == 0                      # no merge ...
        assert _proposals(w) == []                              # ... and no maybe_same_as
        assert w.registry.resolve(ann) != w.registry.resolve(bea)
        assert w.registry.name_collisions() == []
        assert w.registry.typing_conflicts() == []
        assert w.registry.typed_name_anchors(ann) == set()
        # the within-chunk proposal path: a proposal that exists is not promoted
        w.registry.maybe_same_as(ann, bea, evidence="a within-chunk guess")
        assert w.registry.promote_identity_proposals() == 0
        assert w.registry.resolve(ann) != w.registry.resolve(bea)
    finally:
        w.close()


def test_6_the_same_names_stated_behave_exactly_as_before(tmp_path):
    w, a, b = _stated_dresses(tmp_path, "stated.world")
    try:
        assert w.registry.typed_name_anchors(a) == {("name", "red wool dress")}
        collisions = w.registry.name_collisions()
        assert [c["anchor"] for c in collisions] == ["red wool dress"]
        assert collisions[0]["entities"] == [a, b]
        assert w.registry.reconcile() >= 1                      # stated names still merge
        assert w.registry.resolve(a) == w.registry.resolve(b)
    finally:
        w.close()


def test_6_generated_contents_names_across_two_rooms_make_no_evidence(tmp_path):
    w, _ = _world(tmp_path, {"items": [{"value": "a rusted key", "kind": "key"}]})
    try:
        w.ingest_structured([
            {"entity": "place:attic", "attribute": "kind", "value": "attic", "timeless": True},
            {"entity": "place:cellar", "attribute": "kind", "value": "attic", "timeless": True},
        ], classify="rules")
        _declare(w, "contents", "attic")
        w.porcelain.resolve("place:attic", "contents", at=2.0)
        w.porcelain.resolve("place:cellar", "contents", at=2.0)
        keys = sorted(r.entity for r in w.buffer.visible(attribute="name")
                      if r.status == "generated")
        assert len(keys) == 2
        assert w.registry.reconcile() == 0 and _proposals(w) == []
        assert w.registry.name_collisions() == []
        assert w.registry.resolve(keys[0]) != w.registry.resolve(keys[1])
    finally:
        w.close()


def _slip_world(tmp_path, name, minted: bool):
    """A street the story knows as a place, and a thing named "street" that sits
    in it: the typing-slip shape. The thing is invented, or stated."""
    w, _ = _world(tmp_path, {"items": [{"value": "street", "kind": "object"}]}, name=name)
    w.ingest_structured([
        {"entity": "place:street", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:street", "attribute": "name", "value": "street", "timeless": True},
        {"entity": "place:lane", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:street", "attribute": "connects_to", "value": "place:lane",
         "value_type": "entity", "valid_from": 1.0},
    ], classify="rules")
    if minted:
        _declare(w, "contents", "place")
        w.porcelain.resolve("place:street", "contents", at=2.0)
        (thing,) = [r.entity for r in w.buffer.visible(attribute="name")
                    if r.status == "generated"]
    else:
        thing = "obj:street"
        w.ingest_structured(_thing(thing, "object", ["street"])
                            + [_edge(thing, "in", "place:street", 2.0)], classify="rules")
    return w, thing


def test_6_a_generated_name_is_no_typing_slip_and_no_retype_witness(tmp_path):
    w, thing = _slip_world(tmp_path, "slip_gen.world", minted=True)
    try:
        assert w.registry.typing_conflicts() == []
        assert w.registry.name_collisions() == []
        receipt = w.registry.retype(thing, "place", "it is the street", absorb="place:street")
        assert receipt["outcome"] == "vetoed_not_a_slip"        # no shared stated anchor
    finally:
        w.close()


def test_6_the_same_slip_with_a_stated_name_is_found_as_before(tmp_path):
    w, thing = _slip_world(tmp_path, "slip_stated.world", minted=False)
    try:
        slips = w.registry.typing_conflicts()
        assert [(s["spurious"], s["target"], s["shared_anchor"]) for s in slips] == \
            [(thing, "place:street", "street")]
        (collision,) = w.registry.name_collisions()          # the thing sits in the street:
        assert collision["anchor"] == "street"                 # a collision, hard-blocked
        assert collision["pairs"][0]["reason"] == "containment"
        receipt = w.registry.retype(thing, "place", "it is the street", absorb="place:street")
        assert receipt["outcome"] != "vetoed_not_a_slip"
    finally:
        w.close()


def test_6_refer_still_finds_the_invented_dress(tmp_path):
    w, _ = _attire_world(tmp_path, {"items": [{"value": "red wool dress", "kind": "garment"}]})
    try:
        w.porcelain.resolve("person:mara", "attire", at=5.0)
        (dress,) = _minted(w)
        got = w.porcelain.refer("the red wool dress", model=False)
        assert got["status"] == "resolved" and got["entity_id"] == dress
    finally:
        w.close()


def test_6_a_stated_name_on_the_invented_dress_is_evidence_like_any_other(tmp_path):
    w, ann, bea = _two_dresses(tmp_path, "named.world")
    try:
        # the story names both "the red dress": that row is stated evidence
        w.ingest_structured([{"entity": ann, "attribute": "name", "value": "the red dress",
                              "timeless": True},
                             {"entity": bea, "attribute": "name", "value": "the red dress",
                              "timeless": True}], classify="rules")
        assert w.registry.typed_name_anchors(ann) == {("name", "the red dress")}
        assert [c["anchor"] for c in w.registry.name_collisions()] == ["the red dress"]
    finally:
        w.close()


# ---------------------------------------------------------------- 8. request

def test_8_the_attire_request_and_the_prompt(tmp_path):
    w, model = _attire_world(tmp_path)
    try:
        w.ingest_structured([{"entity": "person:mara", "attribute": "age", "value": 30,
                              "valid_from": 1.0}], classify="rules")
        w.porcelain.resolve("person:mara", "attire", at=5.0)
        (prompt, schema), = model.calls
        req = task_request(schema)
        assert (req.aspect, req.kind, req.entity, req.as_of) == \
            ("attire", "person", "person:mara", 5.0)
        assert dict(req.current).get("age") == 30
        assert req.existing == ()
        # no looks declared: the prompt is exactly the pre-E3 prompt
        assert "aspects" not in prompt
        assert prompt.startswith("Resolve an unestablished aspect of a fictional world: "
                                 "the attire of person:mara.\n")
        assert "Plain, concrete items only.\n\nConstraints (canon, in force):\n- " in prompt
    finally:
        w.close()


def test_8_the_prompt_gains_one_sentence_when_looks_are_declared(tmp_path):
    w, model = _attire_world(tmp_path)
    try:
        _declare(w, "colour", "garment", "chair")
        _declare(w, "wears", "person")             # for the entity's own kind: not a look
        _declare(w, "contents", "place")           # a minting aspect: not a look
        w.porcelain.resolve("person:mara", "attire", at=5.0)
        (prompt, _), = model.calls
        sentence = ('Each item may carry "aspects", an object of its looks, using only '
                    "these declared aspects (the kinds each is declared for) with plain "
                    "scalar values: colour (chair, garment).\n")
        assert "Plain, concrete items only.\n" + sentence + "\nConstraints" in prompt
    finally:
        w.close()


def test_8_a_non_minting_request_has_empty_existing_and_the_old_prompt(tmp_path):
    w, model = _world(tmp_path)
    try:
        _seed(w)
        _declare(w, "wears", "person")
        _declare(w, "colour", "garment")
        w.porcelain.resolve("person:mara", "wears", at=5.0)
        (prompt, schema), = model.calls
        assert task_request(schema).existing == () and "aspects" not in prompt
        assert "Plain, concrete items only.\n\nConstraints" in prompt
    finally:
        w.close()


def test_8_the_schema_item_gains_an_optional_aspects_object(tmp_path):
    w, model = _attire_world(tmp_path)
    try:
        w.porcelain.resolve("person:mara", "attire", at=5.0)
        (_, schema), = model.calls
        item = schema["properties"]["items"]["items"]
        assert item["properties"]["aspects"] == {"type": "object"}
        assert item["required"] == ["value"]
    finally:
        w.close()


# ---------------------------------------------------------------- 7. corpus

_CORPUS = Path(os.environ.get("PB_CORPUS_DIR", "/home/k/Newproject/worlds"))


def _legacy_anchor_row(row) -> bool:
    """The pre-R41 collector test: any status counts."""
    return (row.attribute in ("name", "alias") and isinstance(row.value, str))


def _reconcile_copy(src: Path, dst: Path, legacy: bool, monkeypatch) -> tuple[int, int]:
    """Reconcile a READ-ONLY copy of one world; (merges, proposals added)."""
    if not dst.exists():
        ro = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        out = sqlite3.connect(dst)
        try:
            ro.backup(out)
        finally:
            out.close()
            ro.close()
    probe = sqlite3.connect(dst)
    world_id = probe.execute(
        "SELECT value FROM world_meta WHERE key='world_id'").fetchone()[0]
    probe.close()
    with monkeypatch.context() as mp:
        if legacy:
            mp.setattr(IdentityRegistry, "_is_anchor_row", staticmethod(_legacy_anchor_row))
        w = World(dst, world_id)
        try:
            before = len(w.buffer.visible(attribute="maybe_same_as"))
            merged = w.registry.reconcile()
            return merged, len(w.buffer.visible(attribute="maybe_same_as")) - before
        finally:
            w.close()


def _generated_names(path: Path) -> int:
    ro = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return ro.execute("SELECT count(*) FROM assertions WHERE attribute IN "
                          "('name','alias') AND status='generated'").fetchone()[0]
    finally:
        ro.close()


@pytest.mark.skipif(not _CORPUS.exists(), reason="construct's worlds are not on this machine")
def test_7_corpus_a_merge_changes_only_where_a_generated_name_was_an_anchor(
        tmp_path, monkeypatch):
    """§4's measurement on READ-ONLY copies of construct's worlds (never a
    live one, which is the host owner's): reconcile under the pre-R41 predicate and the new one.
    The predicate is the only difference, so a world with no generated name or
    alias row cannot differ: by default the test runs every world that has one
    plus the eight smallest of the rest as a control, and ``PB_CORPUS_FULL=1``
    runs all of them (reconcile on the largest takes minutes)."""
    worlds = sorted(p for p in _CORPUS.rglob("*.world") if "live_" not in str(p))
    assert worlds
    generated = {p: _generated_names(p) for p in worlds}
    if os.environ.get("PB_CORPUS_FULL"):
        chosen = worlds
    else:
        rest = sorted((p for p in worlds if not generated[p]), key=lambda p: p.stat().st_size)
        chosen = [p for p in worlds if generated[p]] + rest[:8]
    differing = []
    for i, src in enumerate(chosen):
        old = _reconcile_copy(src, tmp_path / f"{i}_old.world", True, monkeypatch)
        new = _reconcile_copy(src, tmp_path / f"{i}_new.world", False, monkeypatch)
        if old != new:
            differing.append((i, old, new))
            assert generated[src] > 0, i            # a difference needs a generated name
        assert new[0] <= old[0], (i, old, new)   # never more merges than before
    logging.getLogger(__name__).info(
        "corpus: %d worlds, %d run, %d with a generated name, %d differ: %s",
        len(worlds), len(chosen), sum(1 for p in worlds if generated[p]),
        len(differing), differing)
