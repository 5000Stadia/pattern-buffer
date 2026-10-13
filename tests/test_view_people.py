"""VIEW-PEOPLE-V1: persons' canon whereabouts and host-named facts on the device.

One test (or group) per numbered check of specs/VIEW-PEOPLE-V1.md (Tests 1-10, 7a).
Every wait has a timeout, so a hung call fails instead of hanging the suite.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import mirror_corpus
from make_view_people_vectors import VECTORS, build_vectors, render
from make_view_vectors import VECTORS as OFF_VECTORS
from make_view_vectors import build_vectors as build_off_vectors
from make_view_vectors import render as render_off
from manor_fixture import KEY, build_manor, canon, view
from manor_fixture import VF as MANOR_VF
from manor_fixture import E, T
from patternbuffer import World, mirror
from patternbuffer.service import Refused, Runner, WorldService, make_runner_callable
from people_fixture import ATTRS, SECRET_WORDS, UNSEEN, VF, WORLD_ID, build_people
from test_view_export import _construct_files

CJ = mirror.canonical_json


def h(ident: str, key: bytes = KEY) -> str:
    return mirror.handle_for(key, WORLD_ID, ident)


def is_reset(answer: dict) -> bool:
    return any(o["op"] == "clear" for o in answer["ops"])


def ops_of(answer: dict) -> list[tuple]:
    return [(o["op"], o.get("layer"), o.get("key", o.get("handle"))) for o in answer["ops"]]


def follow(w, doc: dict, key: bytes | None = KEY, people=ATTRS, **kw) -> tuple[dict, dict]:
    """(feed answer, the document a client gets by applying it to `doc`)."""
    answer = mirror.feed(w, VF, doc["cursor"], key=key, people=people, **kw)
    return answer, mirror.apply(doc, answer)


def assert_defining_property(w, doc: dict, key: bytes | None = KEY, people=ATTRS,
                             **kw) -> dict:
    answer, got = follow(w, doc, key, people, **kw)
    assert CJ(got) == CJ(mirror.export(w, VF, key=key, people=people, **kw))
    return answer


def retract(w, entity: str, attribute: str) -> None:
    for row in w.buffer.visible(entity=entity, attribute=attribute):
        w.porcelain.retract(row.id, "gone")


@pytest.fixture
def house(tmp_path):
    w = build_people(tmp_path)
    try:
        yield w
    finally:
        w.close()


def people_of(w, key: bytes | None = KEY, attrs=ATTRS, **kw) -> dict:
    return mirror.export(w, VF, key=key, people=attrs, **kw)["people"]


# --------------------------------------------------------- 1. off is unchanged


def test_1_off_regenerates_the_committed_vectors_byte_identically(tmp_path):
    assert OFF_VECTORS.read_text(encoding="utf-8") == render_off(build_off_vectors(tmp_path))


def test_1_off_has_no_people_key_no_people_on_and_no_q(house):
    for key in (KEY, None):
        doc = mirror.export(house, VF, key=key, people=None)
        assert "people" not in doc
        assert CJ(doc) == CJ(mirror.export(house, VF, key=key))
        body = mirror._read_cursor(key, doc["cursor"])
        assert "q" not in body
        answer = mirror.feed(house, VF, doc["cursor"], key=key, people=None)
        assert "people_on" not in answer and answer["ops"] == []
        assert "people_on" not in mirror.feed(house, VF, None, key=key)
        # the digest covers {known, present} only, as today
        want = hashlib.sha256(CJ({"known": doc["known"],
                                  "present": doc["present"]}).encode("utf-8")).hexdigest()
        assert body["d"] == want


def test_1_a_cursor_minted_before_this_spec_feeds_with_no_reset(tmp_path):
    """A cursor out of the committed (pre-spec) vectors, on a rebuilt manor."""
    vectors = json.loads(OFF_VECTORS.read_text(encoding="utf-8"))
    step = vectors["sequences"][0]["steps"][1]               # "nothing changed"
    w = build_manor(tmp_path)
    try:
        answer = mirror.feed(w, MANOR_VF, step["expect"]["cursor"], key=KEY)
        assert answer["ops"] == [] and not is_reset(answer)
    finally:
        w.close()


# ------------------------------------------------------------- 2. on, position


def test_2_a_person_in_an_unseen_room_has_that_room_as_place(house):
    for key in (KEY, None):
        crowd = people_of(house, key)
        assert crowd["person:cook"]["place"] == "place:kitchen"
        assert crowd["npc:smuggler"]["place"] == "place:hall"        # a kind-person only
        assert crowd["npc:thief"]["place"] == "place:hall"           # a frame owner only


def test_2_the_nearest_place_is_chosen_and_a_wardrobe_crosses_as_a_handle(house):
    crowd = people_of(house)
    butler = crowd["person:butler"]
    assert butler["place"] == "place:bedroom"                        # not place:house
    assert butler["in"] == ["in", h("obj:wardrobe")]
    assert "obj:wardrobe" not in CJ(mirror.export(house, VF, key=KEY, people=ATTRS))


def test_2_without_a_key_a_wardrobe_is_omitted_entirely(house):
    butler = people_of(house, None)["person:butler"]
    assert butler["place"] == "place:bedroom" and "in" not in butler


def test_2_a_child_carried_by_a_parent_has_that_parent_as_in(house):
    for key in (KEY, None):
        baby = people_of(house, key)["person:baby"]
        assert baby["place"] == "place:kitchen"
        assert baby["in"] == ["carried_by", "person:nanny"]


def test_2_a_person_with_no_parent_has_no_place(house):
    drifter = people_of(house)["person:drifter"]
    assert "place" not in drifter and "in" not in drifter


def test_2_an_unattached_safe_is_not_a_place_and_its_id_never_crosses(house):
    for key in (KEY, None):
        doc = mirror.export(house, VF, key=key, people=ATTRS)
        guard = doc["people"].get("person:guard")
        assert "obj:safe" not in CJ(doc)
        if key is None:
            assert "in" not in guard
            assert not any(f[0] == "heading" for f in guard["facts"])
        else:
            assert "place" not in guard
            assert guard["in"] == ["in", h("obj:safe")]
            # the entity fact pointing at the safe crosses as the same handle
            assert ["heading", h("obj:safe"), "id"] in guard["facts"]


def test_2_a_root_whose_canon_kind_is_place_counts_as_a_place(house):
    assert people_of(house)["person:ghost"] == {"facts": [], "place": "obj:annex"}


def test_2_the_slot_rides_on_in_like_a_present_record(house):
    canon(house, T("person:butler", "slot", "top shelf"))
    assert people_of(house)["person:butler"]["in"] == ["in", h("obj:wardrobe"), "top shelf"]


def test_2_the_relation_is_the_winning_containment_rows_attribute(house):
    canon(house, E("person:butler", "held_by", "person:cook", timeless=False, valid_from=4.0))
    butler = people_of(house)["person:butler"]
    assert butler["in"] == ["held_by", "person:cook"] and butler["place"] == "place:kitchen"


def test_2_known_persons_the_player_and_a_frame_owner_are_in_the_layer(house):
    crowd = people_of(house)
    assert "person:mara" in crowd and crowd["person:mara"]["place"] == "place:study"
    assert "npc:thief" in crowd


def test_2_a_person_with_an_empty_record_is_left_out(house):
    crowd = people_of(house, KEY, ("activity",))
    assert "person:drifter" not in crowd                 # no place, no in, no fact
    assert "person:cook" in crowd and "person:mara" in crowd


def test_2_a_cycle_or_a_too_long_chain_gives_no_place_and_a_warning(house, monkeypatch, caplog):
    real = mirror._Reader._parent

    def cyclic(self, ident):
        if ident == "place:kitchen":
            return ("in", "person:cook")
        return real(self, ident)

    monkeypatch.setattr(mirror._Reader, "is_place",
                        lambda self, ident: ident == "place:never")
    monkeypatch.setattr(mirror._Reader, "_parent", cyclic)
    with caplog.at_level(logging.WARNING, logger="patternbuffer.mirror"):
        crowd = people_of(house)
    assert "place" not in crowd["person:cook"]
    assert "cycle" in caplog.text
    caplog.clear()

    def endless(self, ident):
        return ("in", ident + "x") if len(ident) < 200 else None

    monkeypatch.setattr(mirror._Reader, "_parent", endless)
    with caplog.at_level(logging.WARNING, logger="patternbuffer.mirror"):
        crowd = people_of(house)
    assert "place" not in crowd["person:cook"]
    assert "longer than 32" in caplog.text


def test_2_a_place_exactly_32_ancestors_up_still_counts(house, monkeypatch):
    # obj:c0 .. obj:c30 are ancestors 1-31 of the cook, place:far is the 32nd
    chain = {f"obj:c{i}": f"obj:c{i + 1}" for i in range(30)}
    chain["person:cook"] = "obj:c0"
    real = mirror._Reader._parent
    monkeypatch.setattr(mirror._Reader, "_parent", lambda self, ident: (
        ("in", chain[ident]) if ident in chain else
        (("in", "place:far") if ident == "obj:c30" else real(self, ident))))
    assert people_of(house)["person:cook"]["place"] == "place:far"


# --------------------------------------------------------------- 3. on, facts


def test_3_named_literal_facts_cross_and_are_sorted(house):
    cook = people_of(house)["person:cook"]
    assert ["activity", "peeling", "lit"] in cook["facts"]
    assert ["posture", "sitting", "lit"] in cook["facts"]
    keyed = sorted(cook["facts"], key=lambda r: (r[0], r[2], CJ(r[1])))
    assert cook["facts"] == keyed


def test_3_an_entity_fact_crosses_as_an_id_for_a_place_a_person_or_a_known_thing(house):
    for key in (KEY, None):
        cook = people_of(house, key)["person:cook"]
        assert ["heading", "place:hall", "id"] in cook["facts"]       # a place
        assert ["pursuing", "person:butler", "id"] in cook["facts"]   # a person
        assert ["watching", "obj:desk", "id"] in cook["facts"]        # a known thing


def test_3_an_entity_fact_to_an_unseen_thing_is_a_handle_with_a_key_else_omitted(house):
    cook = people_of(house)["person:cook"]
    assert ["holding", h("obj:cup"), "id"] in cook["facts"]
    keyless = people_of(house, None)["person:cook"]
    assert not any(f[0] == "holding" for f in keyless["facts"])


def test_3_a_set_valued_key_crosses_as_one_tuple_per_member(house):
    names = [f for f in people_of(house)["person:cook"]["facts"] if f[0] == "name"]
    assert names == [["name", "Cookie", "lit"], ["name", "Mrs Cook", "lit"]]


def test_3_an_accrue_keys_total_crosses_as_a_literal(house):
    assert ["gold", 15, "lit"] in people_of(house)["person:nanny"]["facts"]


def test_3_conflicted_unresolved_and_structured_facts_are_omitted(house):
    crowd = people_of(house)
    assert crowd["person:twin"]["facts"] == []                  # conflicted posture
    cook = crowd["person:cook"]
    assert not any(f[0] in ("plan", "gear") for f in cook["facts"])
    # and the raw state really is what the test says it is
    assert house.porcelain.state("person:twin", "posture")["status"] == "conflicted"
    assert house.porcelain.state("person:cook", "plan")["status"] == "unresolved"
    assert isinstance(house.porcelain.state("person:cook", "gear")["fact"]["value"], dict)


def test_3_a_fact_the_host_did_not_name_never_appears(house):
    doc = mirror.export(house, VF, key=KEY, people=("posture",))
    cook = doc["people"]["person:cook"]
    assert cook["facts"] == [["posture", "sitting", "lit"]]
    text = CJ(doc)
    for word in ("peeling", "Cookie", "scarred", "place:hall\",\"id"):
        assert word not in text


def test_3_position_only_when_no_names_are_given(house):
    doc = mirror.export(house, VF, key=KEY, people=())
    assert doc["people"]["person:cook"] == {"facts": [], "place": "place:kitchen"}
    assert "person:drifter" not in doc["people"]


# -------------------------------------------------------- 4. still never crosses


@pytest.mark.parametrize("key", [KEY, None], ids=["keyed", "keyless"])
def test_4_what_a_person_carries_and_what_is_unnamed_appears_nowhere(house, key):
    doc = mirror.export(house, VF, key=key, people=ATTRS)
    text = CJ(doc)
    for ident in UNSEEN:
        assert ident not in text, ident                       # gun, wardrobe, safe, cup
    for word in SECRET_WORDS:                                 # a face, another frame's rows
        assert word not in text, word
    assert "obj:gun" not in text and "carried_by\",\"person:cook" not in text


def test_4_the_walk_never_descends_into_a_person(house):
    """The gun is carried by the cook; no ref, key or fact names it, even when a
    host names an attribute the gun has."""
    doc = mirror.export(house, VF, key=KEY, people=ATTRS)
    assert "obj:gun" not in CJ(doc)
    assert not [k for k in (doc["present"] or {}) if "gun" in k]


def test_4_a_known_person_never_enters_the_present_layer(house):
    doc = mirror.export(house, VF, key=KEY, people=ATTRS)
    assert doc["present"] == {}


# ------------------------------------------------------------------- 5. feed


def _history(w):
    return [
        lambda w: canon(w, E("person:cook", "in", "place:bedroom", timeless=False,
                             valid_from=5.0)),
        lambda w: canon(w, T("person:mara", "posture", "sitting", timeless=False,
                             valid_from=6.0)),
        lambda w: canon(w, E("person:nanny", "in", "obj:wardrobe", timeless=False,
                             valid_from=7.0)),
        lambda w: view(w, T("obj:desk", "colour", "oak")),
        lambda w: canon(w, T("person:maid", "kind", "person"),
                        E("person:maid", "in", "place:hall"),
                        T("person:maid", "posture", "dusting")),
        lambda w: retract(w, "person:drifter", "posture"),
        lambda w: canon(w, E("person:cook", "heading", "obj:safe", timeless=False,
                             valid_from=9.0)),
        lambda w: canon(w, E("person:butler", "in", "place:study", timeless=False,
                             valid_from=10.0)),
        lambda w: view(w, T("obj:wardrobe", "kind", "wardrobe"),
                       E("obj:wardrobe", "in", "place:bedroom")),
        lambda w: canon(w, T("person:cook", "posture", "standing", timeless=False,
                             valid_from=12.0)),
    ]


def test_5_an_author_moving_a_person_is_one_put_people_and_no_known_op(house):
    doc = mirror.export(house, VF, key=KEY, people=ATTRS)
    canon(house, E("person:cook", "in", "place:bedroom", timeless=False, valid_from=5.0))
    answer, got = follow(house, doc)
    assert ops_of(answer) == [("put", "people", "person:cook")]
    assert answer["people_on"] is True
    assert got["people"]["person:cook"]["place"] == "place:bedroom"
    assert CJ(got) == CJ(mirror.export(house, VF, key=KEY, people=ATTRS))


def test_5_a_persons_last_recorded_row_retracted_gives_del_people(house):
    doc = mirror.export(house, VF, key=KEY, people=ATTRS)
    retract(house, "person:drifter", "posture")
    answer, got = follow(house, doc)
    assert ops_of(answer) == [("del", "people", "person:drifter")]
    assert "person:drifter" not in got["people"]


def test_5_a_moved_carrier_moves_the_carried_person_too(house):
    doc = mirror.export(house, VF, key=KEY, people=ATTRS)
    canon(house, E("person:nanny", "in", "place:bedroom", timeless=False, valid_from=7.0))
    answer = assert_defining_property(house, doc)
    assert sorted(o["key"] for o in answer["ops"]) == ["person:baby", "person:nanny"]


@pytest.mark.parametrize("key", [KEY, None], ids=["keyed", "keyless"])
@pytest.mark.parametrize("at", [None, 20.0], ids=["at-latest", "at-fixed"])
def test_5_defining_property_over_a_fixture_history(house, key, at):
    kw = {"at": at} if at is not None else {}
    docs = [mirror.export(house, VF, key=key, people=ATTRS, **kw)]
    seen: set[tuple] = set()
    resets = 0
    for mutate in _history(house):
        mutate(house)
        for old in docs:                                  # every position a client could hold
            answer = assert_defining_property(house, old, key, ATTRS, **kw)
            resets += is_reset(answer)
            seen |= {(o["op"], o.get("layer")) for o in answer["ops"]}
        docs.append(mirror.export(house, VF, key=key, people=ATTRS, **kw))
    assert resets == 0, "a pure log history never needs a reset"
    assert {("put", "people"), ("del", "people"), ("put", "known")} <= seen


def test_5_the_digest_covers_people_so_a_changed_past_view_resets(house, monkeypatch):
    doc = mirror.export(house, VF, key=KEY, people=ATTRS)
    body = mirror._read_cursor(KEY, doc["cursor"])
    want = hashlib.sha256(CJ({"known": doc["known"], "present": doc["present"],
                              "people": doc["people"]}).encode("utf-8")).hexdigest()
    assert body["d"] == want
    # something the log position cannot capture changes the people layer's past
    real = mirror._Reader._person_record

    def drifted(self, person, known, key, attrs):
        out = real(self, person, known, key, attrs)
        if person == "person:cook" and self.head == body["h"]:
            out = {**out, "place": "place:hall"}
        return out

    monkeypatch.setattr(mirror._Reader, "_person_record", drifted)
    canon(house, T("obj:cup", "colour", "white"))
    assert is_reset(mirror.feed(house, VF, doc["cursor"], key=KEY, people=ATTRS))


def _worlds_sample() -> list[Path]:
    files = _construct_files()
    if not os.environ.get("PB_CONSTRUCT_ALL"):
        files = files[:: max(1, len(files) // 6)][:6]
    return files


# the names construct's play worlds really carry on persons
_CONSTRUCT_ATTRS = ("alias", "role", "state", "feel", "age")


@pytest.mark.skipif(not _construct_files(),
                    reason="corpus check: construct's world folder is absent "
                           "(set PB_CONSTRUCT_WORLDS to a directory of host world files)")
def test_5_defining_property_on_copies_of_constructs_play_worlds_with_people_on():
    """20 log positions per world, keyed and keyless, over read-only backup copies."""
    checks = resets = 0
    for path in _worlds_sample():
        result = mirror_corpus.check_world(path, KEY, 20, people=_CONSTRUCT_ATTRS)
        assert result["mismatches"] == [], result
        checks += result["checks"]
        resets += result["resets"]
    assert checks > 0
    logging.getLogger(__name__).info(
        "construct worlds with people on: %d checks, %d resets", checks, resets)


# --------------------------------------------------- the cursor's `q` (spec §3)


def test_q_is_the_sha256_of_the_canonical_json_of_the_normalized_names(house):
    doc = mirror.export(house, VF, key=KEY, people=("Posture", "activity"))
    body = mirror._read_cursor(KEY, doc["cursor"])
    want = hashlib.sha256(CJ(["activity", "posture"]).encode("utf-8")).hexdigest()
    assert body["q"] == want
    assert body["q"] == mirror._people_q(("activity", "posture"))
    assert mirror._read_cursor(KEY, mirror.export(house, VF, key=KEY, people=())["cursor"]
                               )["q"] == hashlib.sha256(b"[]").hexdigest()


def test_q_is_read_when_absent_or_64_hex_and_nothing_else(house):
    doc = mirror.export(house, VF, key=KEY)
    body = mirror._read_cursor(KEY, doc["cursor"])
    assert "q" not in body
    for q in ("a" * 64, "0" * 64):
        assert mirror._read_cursor(KEY, mirror._mint_cursor(KEY, {**body, "q": q})) is not None
    for q in ("a" * 63, "A" * 64, "g" * 64, "", 5, None, ["a" * 64]):
        assert mirror._read_cursor(KEY, mirror._mint_cursor(KEY, {**body, "q": q})) is None


# ------------------------------------------------------- 6. mode changes reset


def test_6_on_to_off_off_to_on_and_a_changed_list_each_answer_clear(house):
    on = mirror.export(house, VF, key=KEY, people=ATTRS)
    off = mirror.export(house, VF, key=KEY)
    narrower = mirror.export(house, VF, key=KEY, people=("posture",))
    to_off = mirror.feed(house, VF, on["cursor"], key=KEY)
    assert is_reset(to_off) and "people_on" not in to_off
    assert "people" not in mirror.apply(on, to_off)
    assert CJ(mirror.apply(on, to_off)) == CJ(off)
    to_on = mirror.feed(house, VF, off["cursor"], key=KEY, people=ATTRS)
    assert is_reset(to_on) and to_on["people_on"] is True
    assert CJ(mirror.apply(off, to_on)) == CJ(on)
    changed = mirror.feed(house, VF, on["cursor"], key=KEY, people=("posture",))
    assert is_reset(changed)
    assert CJ(mirror.apply(on, changed)) == CJ(narrower)
    # the same list again (an alias and a repeat) is no change
    assert mirror.feed(house, VF, narrower["cursor"], key=KEY,
                       people=("Posture", "posture"))["ops"] == []


def test_6_a_reset_puts_every_person_after_the_other_layers(house):
    canon(house, T("obj:desk", "kind", "desk"))
    answer = mirror.feed(house, VF, None, key=KEY, people=ATTRS)
    layers = [o.get("layer") for o in answer["ops"][1:]]
    assert layers == sorted(layers, key=("known", "present", "people").index)
    assert layers[-1] == "people" and "known" in layers


def test_6_a_diff_orders_each_kind_of_op_by_layer_then_key(house):
    doc = mirror.export(house, VF, key=KEY, people=ATTRS)
    view(house, T("obj:desk", "colour", "oak"))
    canon(house, E("person:cook", "in", "place:hall", timeless=False, valid_from=5.0),
          E("person:butler", "in", "place:hall", timeless=False, valid_from=5.0))
    retract(house, "person:drifter", "posture")
    answer = mirror.feed(house, VF, doc["cursor"], key=KEY, people=ATTRS)
    kinds = [o["op"] for o in answer["ops"]]
    assert kinds == sorted(kinds, key={"reveal": 0, "del": 1, "put": 2}.get)
    for kind in ("del", "put"):
        pairs = [(o["layer"], o["key"]) for o in answer["ops"] if o["op"] == kind]
        assert pairs == sorted(pairs)
    assert not [o for o in answer["ops"] if o["op"] == "reveal" and "people" in str(o)]


def test_6_apply_adds_and_removes_the_people_key_and_refuses_a_mismatch(house):
    on = mirror.export(house, VF, key=KEY, people=ATTRS)
    off = mirror.export(house, VF, key=KEY)
    # an answer with no clear must keep the people mode
    with pytest.raises(ValueError):
        mirror.apply(on, {"cursor": "x", "at": None, "present_on": True, "ops": []})
    with pytest.raises(ValueError):
        mirror.apply(off, {"cursor": "x", "at": None, "present_on": True,
                           "people_on": True, "ops": []})
    # del / put to people while the document has no people key
    for op in ({"op": "put", "layer": "people", "key": "person:x", "value": {"facts": []}},
               {"op": "del", "layer": "people", "key": "person:x"}):
        with pytest.raises(ValueError):
            mirror.apply(off, {"cursor": "x", "at": None, "present_on": True,
                               "ops": [op]})
    # clear: people becomes {} (people_on) or the key goes
    cleared = mirror.apply(on, {"cursor": "x", "at": None, "present_on": True,
                                "people_on": True, "ops": [{"op": "clear"}]})
    assert cleared["people"] == {}
    gone = mirror.apply(on, {"cursor": "x", "at": None, "present_on": True,
                             "ops": [{"op": "clear"}]})
    assert "people" not in gone


# --------------------------------------------------------- 7. refused names


BARRED = ("in", "within", "held_by", "worn_by", "carried_by", "kind", "same_as",
          "maybe_same_as", "distinct_from", "superseded_by", "retracts", "source",
          "fold_policy", "resolvable_for", "frame_continues_as")


@pytest.mark.parametrize("name", BARRED)
def test_7_a_barred_name_is_refused_at_the_call(house, name):
    with pytest.raises(ValueError):
        mirror.export(house, VF, key=KEY, people=(name,))
    with pytest.raises(ValueError):
        mirror.feed(house, VF, None, key=KEY, people=("posture", name))


@pytest.mark.parametrize("spelling", ["Located In", "type", "  KIND ", "Carried By"])
def test_7_an_alias_spelling_of_a_barred_name_is_refused_too(house, spelling):
    with pytest.raises(ValueError):
        mirror.export(house, VF, key=KEY, people=(spelling,))


@pytest.mark.parametrize("name", BARRED)
def test_7_a_barred_name_is_refused_at_service_construction(name):
    with pytest.raises(ValueError):
        WorldService(people=(name,))


def test_7_an_alias_of_a_barred_name_is_refused_at_attach(house):
    svc = WorldService(people=("type",))          # no world yet: it passes the plain check
    with pytest.raises(ValueError):
        svc.attach(house, VF)
    assert not svc.attached


@pytest.mark.parametrize("name", ["in", "carried_by", "kind", "same_as", "superseded_by"])
def test_7_a_barred_name_is_refused_at_runner_start(tmp_path, name):
    build_people(tmp_path, "r.world").close()
    model, route = make_runner_callable(None)
    with pytest.raises(ValueError):
        Runner(lambda gated: World(tmp_path / "r.world", WORLD_ID, model=gated(model)),
               VF, port=0, model_route=route, people=(name,))


def test_7_an_alias_of_a_barred_name_fails_the_runners_start(tmp_path):
    build_people(tmp_path, "r.world").close()
    model, route = make_runner_callable(None)
    runner = Runner(lambda gated: World(tmp_path / "r.world", WORLD_ID, model=gated(model)),
                    VF, port=0, model_route=route, people=("type",))
    with pytest.raises(ValueError):
        runner.start()


def test_7_a_blank_name_and_a_non_string_are_refused(house):
    with pytest.raises(ValueError):
        mirror.export(house, VF, people=("",))
    with pytest.raises(ValueError):
        mirror.export(house, VF, people=("  ",))
    with pytest.raises(TypeError):
        mirror.export(house, VF, people=("posture", 3))


def test_7_the_runner_flags(tmp_path):
    from patternbuffer import service
    build_people(tmp_path, "f.world").close()
    started: dict = {}

    class FakeRunner:
        def __init__(self, open_world, view_frame, **kw):
            started.update(kw)
            self.port = 0

        def start(self):
            return self

        def stop(self):
            pass

    class FakeEvent:
        def wait(self):
            return True

        def set(self):
            pass

    import unittest.mock as mock
    base = ["--world", str(tmp_path / "f.world"), "--world-id", WORLD_ID,
            "--view-frame", VF]

    def run(*extra: str) -> None:
        with mock.patch.object(service, "Runner", FakeRunner), \
                mock.patch.object(service.threading, "Event", FakeEvent), \
                mock.patch.object(service.signal, "signal"):
            service.main(base + list(extra))

    run()
    assert started["people"] is None
    run("--people")
    assert started["people"] == ()
    run("--people", "--people-attr", "posture", "--people-attr", "activity")
    assert started["people"] == ("posture", "activity")
    with pytest.raises(SystemExit):                    # an attribute without --people
        run("--people-attr", "posture")
    with pytest.raises(SystemExit):                    # a barred one
        run("--people", "--people-attr", "carried_by")


def test_7_the_mirror_cli_flags(tmp_path, capfd):
    path = tmp_path / "c.world"
    build_people(tmp_path, "c.world").close()
    base = ["export", "--world", str(path), "--world-id", WORLD_ID, "--view-frame", VF]
    assert mirror.main(base) == 0
    assert "people" not in json.loads(capfd.readouterr().out)
    assert mirror.main(base + ["--people"]) == 0
    doc = json.loads(capfd.readouterr().out)
    assert doc["people"]["person:cook"] == {"facts": [], "place": "place:kitchen"}
    assert mirror.main(base + ["--people", "--people-attr", "posture",
                               "--people-attr", "Posture"]) == 0
    doc = json.loads(capfd.readouterr().out)
    assert doc["people"]["person:cook"]["facts"] == [["posture", "sitting", "lit"]]
    with pytest.raises(SystemExit):
        mirror.main(base + ["--people-attr", "posture"])
    with pytest.raises(SystemExit):
        mirror.main(base + ["--people", "--people-attr", "kind"])
    capfd.readouterr()


# ------------------------------------------------------------ 7a. normalization


def test_7a_aliases_repeats_and_order_give_one_document_and_one_q(house):
    docs = [mirror.export(house, VF, key=KEY, people=p) for p in (
        ("Posture", "posture"), ("posture",), ["posture", "posture"], ("POSTURE ",))]
    assert len({CJ(d) for d in docs}) == 1
    assert len({mirror._read_cursor(KEY, d["cursor"])["q"] for d in docs}) == 1
    cook = docs[0]["people"]["person:cook"]
    assert [f for f in cook["facts"] if f[0] == "posture"] == [["posture", "sitting", "lit"]]
    assert mirror.normalize_people(("Posture", "posture", "activity")) == ("activity", "posture")
    assert mirror.normalize_people(()) == () and mirror.normalize_people(None) is None
    one = mirror.export(house, VF, key=KEY, people=("posture", "activity"))
    two = mirror.export(house, VF, key=KEY, people=["activity", "Posture"])
    assert CJ(one) == CJ(two)


@pytest.mark.parametrize("bad", ["posture", b"posture", {"posture"}, 5, ("posture", None)])
def test_7a_a_bare_string_or_a_non_sequence_is_refused(house, bad):
    with pytest.raises(TypeError):
        mirror.export(house, VF, key=KEY, people=bad)
    with pytest.raises(TypeError):
        mirror.feed(house, VF, None, key=KEY, people=bad)


def test_7a_the_service_refuses_a_bare_string_too():
    with pytest.raises(TypeError):
        WorldService(people="posture")


# ----------------------------------------------------------------- 8. service


@pytest.fixture
def hosted(tmp_path):
    w = build_people(tmp_path)
    svc = WorldService(read_timeout=10, mirror_key=KEY, people=("Posture", "heading"))
    svc.attach(w, VF)
    try:
        yield w, svc, svc.session("holo-emitter")
    finally:
        svc.detach()
        w.close()


@pytest.mark.parametrize("verb", ["export", "feed"])
@pytest.mark.parametrize("value", [("posture",), (), None, "posture", ["kind"]])
def test_8_a_viewer_naming_people_is_refused(hosted, verb, value):
    _, _, sess = hosted
    with pytest.raises(Refused):
        sess.call(verb, people=value)


def test_8_export_and_feed_serve_the_hosts_setting_from_the_snapshot(hosted, monkeypatch):
    w, svc, sess = hosted
    want = mirror.export(w, VF, at=svc.now(), key=KEY, people=("heading", "posture"))

    def boom(*a, **k):
        raise AssertionError("a viewer service verb touched the live World")
    monkeypatch.setattr(w.buffer, "visible", boom)
    monkeypatch.setattr(w.buffer, "head", boom)
    doc = sess.call("export")
    assert CJ(doc) == CJ(want) and "people" in doc
    answer = sess.call("feed", since=doc["cursor"])
    assert answer["ops"] == [] and answer["people_on"] is True
    assert sess.call("feed")["ops"][0] == {"op": "clear"}


def test_8_a_viewer_sees_a_moved_person_after_the_next_pump(hosted):
    w, svc, sess = hosted
    doc = sess.call("export")
    canon(w, E("person:cook", "in", "place:hall", timeless=False, valid_from=5.0))
    assert sess.call("feed", since=doc["cursor"])["ops"] == []         # not pumped yet
    svc.pump()
    answer = sess.call("feed", since=doc["cursor"])
    assert ops_of(answer) == [("put", "people", "person:cook")]
    assert CJ(mirror.apply(doc, answer)) == CJ(sess.call("export"))


def test_8_a_service_with_no_people_serves_none(tmp_path):
    w = build_people(tmp_path)
    svc = WorldService(read_timeout=10, mirror_key=KEY)
    svc.attach(w, VF)
    try:
        doc = svc.session("c").call("export")
        assert "people" not in doc
        assert "people_on" not in svc.session("c").call("feed")
    finally:
        svc.detach()
        w.close()


def test_8_the_service_canonicalizes_names_at_attach(hosted):
    _, svc, _ = hosted
    assert svc._people == ("heading", "posture")


def _post(port, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/call", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_8_the_runner_serves_the_layer_over_post_call_and_refuses_people(tmp_path):
    build_people(tmp_path, "run.world").close()
    model, route = make_runner_callable(None)
    r = Runner(lambda gated: World(tmp_path / "run.world", WORLD_ID, model=gated(model)),
               VF, port=0, model_route=route, mirror_key=KEY, people=("posture",)).start()
    try:
        code, raw = _post(r.port, {"session": "v", "verb": "export", "args": {}})
        doc = json.loads(raw)["result"]
        assert code == 200 and doc["people"]["person:cook"]["facts"] == [
            ["posture", "sitting", "lit"]]
        code, raw = _post(r.port, {"session": "v", "verb": "feed",
                                   "args": {"since": doc["cursor"]}})
        assert code == 200 and json.loads(raw)["result"]["ops"] == []
        code, raw = _post(r.port, {"session": "v", "verb": "export",
                                   "args": {"people": ["kind"]}})
        assert code == 400 and json.loads(raw)["error"]["type"] == "refused"
    finally:
        r.stop()


# ------------------------------------------------------------------ 9. vectors


def test_9_the_committed_people_vectors_are_what_the_generator_makes(tmp_path):
    assert VECTORS.read_text(encoding="utf-8") == render(build_vectors(tmp_path)), \
        "run `python tests/make_view_people_vectors.py` after a deliberate change"


def test_9_python_apply_replays_the_people_vectors():
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert vectors["schema"] == mirror.SCHEMA and vectors["sequences"]
    ops_seen: set[tuple] = set()
    for seq in vectors["sequences"]:
        doc = seq["start"]
        for step in seq["steps"]:
            doc = mirror.apply(doc, step["answer"])
            assert doc == step["expect"], (seq["name"], step["name"])
            assert ("people" in doc) == (step["answer"].get("people_on") is True)
            ops_seen |= {(o["op"], o.get("layer")) for o in step["answer"]["ops"]}
    assert {("clear", None), ("put", "known"), ("put", "people"),
            ("del", "people")} <= ops_seen


# --------------------------------------------------------------------- 10. cost


@pytest.mark.skipif(not _construct_files(),
                    reason="corpus check: construct's world folder is absent")
def test_10_cost_on_the_largest_construct_world_with_people_on(capsys):
    path = max(_construct_files(), key=lambda p: p.stat().st_size)
    conn = mirror_corpus.copy_read_only(path)
    wid = mirror_corpus.world_id_of(conn)
    frame = mirror_corpus.busiest_knows_frame(conn)
    assert frame
    head = mirror_corpus.head_of(conn)
    full = mirror_corpus.full_world(conn, wid)
    old = mirror_corpus.truncated(conn, head // 2, wid)
    try:
        start = time.perf_counter()
        doc = mirror.export(full, frame, key=KEY, people=_CONSTRUCT_ATTRS)
        export_s = time.perf_counter() - start
        size = len(CJ(doc).encode("utf-8"))
        old_doc = mirror.export(old, frame, key=KEY, people=_CONSTRUCT_ATTRS)
        start = time.perf_counter()
        answer = mirror.feed(full, frame, old_doc["cursor"], key=KEY,
                             people=_CONSTRUCT_ATTRS)
        feed_s = time.perf_counter() - start
        assert CJ(mirror.apply(old_doc, answer)) == CJ(doc)
        with capsys.disabled():
            print(f"\n[cost people] {path.name} ({path.stat().st_size} B, head {head}): "
                  f"export {export_s:.3f} s, feed {feed_s:.3f} s "
                  f"({'reset' if is_reset(answer) else 'diff'}), document {size} B, "
                  f"{len(doc['known'])} known, {len(doc['present'])} present, "
                  f"{len(doc['people'])} people")
        assert feed_s < 5.0, f"a feed took {feed_s:.2f} s (> 5 s)"
        assert export_s < 5.0
    finally:
        old.close()
        full.close()
        conn.close()
