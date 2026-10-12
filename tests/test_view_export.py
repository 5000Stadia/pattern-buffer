"""VIEW-EXPORT-V1: the player's view as a document, kept in step by a feed.

One test (or group) per check of specs/VIEW-EXPORT-V1.md (Tests 1-12, 6a-6d).
Every wait has a timeout, so a hung call fails instead of hanging the suite.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import mirror_corpus
from make_view_vectors import VECTORS, build_vectors, render
from manor_fixture import (KEY, OTHER_FRAME, OTHER_KEY, SECRET_WORDS, UNPERCEIVED, VF,
                           WORLD_ID, E, T, _no_model, build_manor, canon, view)
from patternbuffer import World, mirror
from patternbuffer.porcelain import Porcelain
from patternbuffer.service import (VIEWER_EXCLUDED, VIEWER_READS, VIEWER_SERVICE_READS,
                                   Refused, Runner, WorldService, make_runner_callable)
from service_fixture import pump_until_done, run_async

CJ = mirror.canonical_json
HEXS = "0123456789abcdef"


def h(ident: str, key: bytes = KEY) -> str:
    return mirror.handle_for(key, WORLD_ID, ident)


def ops_of(answer: dict) -> list[tuple]:
    """(op, layer, key-or-handle) for each op, to compare shapes at a glance."""
    return [(o["op"], o.get("layer"), o.get("key", o.get("handle"))) for o in answer["ops"]]


def is_reset(answer: dict) -> bool:
    return any(o["op"] == "clear" for o in answer["ops"])


def follow(w, doc: dict, key: bytes | None = KEY, **kw) -> tuple[dict, dict]:
    """(feed answer, the document a client gets by applying it to `doc`)."""
    answer = mirror.feed(w, VF, doc["cursor"], key=key, **kw)
    return answer, mirror.apply(doc, answer)


def assert_defining_property(w, doc: dict, key: bytes | None = KEY, **kw) -> dict:
    answer, got = follow(w, doc, key, **kw)
    assert CJ(got) == CJ(mirror.export(w, VF, key=key, **kw))
    return answer


@pytest.fixture
def manor(tmp_path):
    w = build_manor(tmp_path)
    try:
        yield w
    finally:
        w.close()


def leaves(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from leaves(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from leaves(v)
    else:
        yield obj


# ------------------------------------------------------- 1. frame absence


def test_1_known_holds_only_the_views_facts(manor):
    doc = mirror.export(manor, VF, key=KEY)
    assert set(doc["known"]) == {"obj:desk", "obj:vase", "person:mara", "place:study"}
    assert doc["known"]["obj:desk"] == {
        "facts": [["in", "place:study", "id"], ["kind", "desk", "lit"]], "conflicted": []}
    text = CJ(doc)
    for word in SECRET_WORDS:
        assert word not in text
    # known equals what live reads of the same viewer answer
    for subject, entry in doc["known"].items():
        for attribute, value, kind in entry["facts"]:
            fact = manor.porcelain.state(subject, attribute, frame=VF)["fact"]
            assert fact["value"] == value
            assert (kind == "id") == (fact["value_type"] == "entity")


def test_1_present_has_only_declared_words_and_no_unperceived_id(manor):
    doc = mirror.export(manor, VF, key=KEY)
    text = CJ(doc)
    for ident in UNPERCEIVED:
        assert ident not in text, ident
    declared = {"material", "made_by", "tag", "points_to"}
    for handle, record in doc["present"].items():
        assert mirror.HANDLE_RE.fullmatch(handle)
        assert set(record) <= {"kind", "in", "address", "look"}
        assert {aspect for aspect, _ in record["look"]} <= declared
    # the only ids in a present record are a known id or a handle
    for record in doc["present"].values():
        ref = record["in"][1]
        assert ref in doc["known"] or ref in doc["present"]


def test_1_entity_structured_and_nonscalar_values_are_omitted(manor):
    doc = mirror.export(manor, VF, key=KEY)
    key_record = doc["present"][h("obj:key")]
    # made_by (entity), tag (structured) and points_to (entity) are declared but omitted
    assert key_record["look"] == [["material", "iron"]]
    # entity-valued slot / address / kind
    amulet = doc["present"][h("obj:amulet")]
    assert amulet["kind"] == "amulet" and len(amulet["in"]) == 2 and "address" not in amulet
    relic = doc["present"][h("obj:relic")]
    assert "kind" not in relic and relic["look"] == []
    assert "person:butler" not in CJ(doc) and "obj:vault" not in CJ(doc)


def test_1_a_float_bool_and_int_look_cross_but_a_decimal_does_not(manor):
    from decimal import Decimal
    manor.porcelain.ingest_structured(
        [T("attr:weight", "resolvable_for", "ring"), T("attr:cursed", "resolvable_for", "ring"),
         T("attr:carats", "resolvable_for", "ring"), T("attr:price", "resolvable_for", "ring")],
        classify="rules")
    canon(manor, T("obj:ring", "weight", 2.5), T("obj:ring", "cursed", True),
          T("obj:ring", "carats", 18), T("obj:ring", "price", Decimal("12.50")))
    look = dict(mirror.export(manor, VF, key=KEY)["present"][h("obj:ring")]["look"])
    assert look["weight"] == 2.5 and look["cursed"] is True and look["carats"] == 18
    assert "price" not in look


# ------------------------------------------------------------- 2. persons


def test_2_a_hidden_person_and_what_they_carry_appear_nowhere(manor):
    doc = mirror.export(manor, VF, key=KEY)
    kinds = {r.get("kind") for r in doc["present"].values()}
    assert not kinds & {"person", "pistol", "coat", "figure", "loot"}
    for ident in ("person:butler", "obj:gun", "obj:coat", "npc:thief", "obj:loot"):
        assert h(ident) not in doc["present"]
    text = CJ(doc)
    assert "pistol" not in text and "figure" not in text


def test_2_an_owner_of_a_knows_frame_is_a_person_even_without_the_namespace(manor):
    # npc:thief owns knows:npc:thief; a non-owner merged into it joins its closure
    canon(manor, T("obj:statue", "kind", "statue"), E("obj:statue", "in", "place:study"),
          E("obj:cap", "worn_by", "obj:statue"), T("obj:cap", "kind", "cap"))
    before = mirror.export(manor, VF, key=KEY)
    assert h("obj:cap") in before["present"] and h("obj:statue") in before["present"]
    receipt = manor.porcelain.merge("obj:statue", "npc:thief", "the same figure")
    assert receipt.get("status") != "vetoed", receipt
    after = mirror.export(manor, VF, key=KEY)
    rep = manor.registry.resolve("obj:statue")
    assert h(rep) not in after["present"] and h("obj:statue") not in after["present"]
    assert not {r.get("kind") for r in after["present"].values()} & {"cap", "statue"}


def test_2_a_canon_kind_of_person_makes_a_person_without_namespace_or_frame(manor):
    # r3.1: a hidden NPC with neither the person: namespace nor a knows: frame
    canon(manor, T("char:stranger", "kind", "person"), E("char:stranger", "in", "place:study"),
          E("obj:dagger", "carried_by", "char:stranger"), T("obj:dagger", "kind", "dagger"))
    doc = mirror.export(manor, VF, key=KEY)
    assert h("char:stranger") not in doc["present"] and h("obj:dagger") not in doc["present"]
    assert "dagger" not in CJ(doc)


# ------------------------------------------------------ 3. no key, no canon


def test_3_without_a_key_present_is_null_and_the_cursor_is_unsigned(manor):
    doc = mirror.export(manor, VF)
    assert doc["present"] is None and doc["cursor"].endswith(".")
    body = mirror._read_cursor(None, doc["cursor"])
    assert body["p"] is False and mirror._read_cursor(KEY, doc["cursor"]) is None


def test_3_the_keyless_document_is_the_same_whether_or_not_canon_holds_drawers(tmp_path):
    a = build_manor(tmp_path, "a.world", drawer=True)
    b = build_manor(tmp_path, "b.world", drawer=False)
    try:
        da, db = mirror.export(a, VF), mirror.export(b, VF)
        ca, cb = mirror._read_cursor(None, da["cursor"]), mirror._read_cursor(None, db["cursor"])
        assert ca["d"] == cb["d"]                       # the digest of known + present
        for d in (da, db):
            d["cursor"] = None                          # the heads differ; nothing else may
        assert CJ(da) == CJ(db)
    finally:
        a.close()
        b.close()


# -------------------------------------------------- 4. the defining property


def _history(w):
    """Mutations of the manor, each one visible to a different op."""
    def retract_vase(w):
        for r in w.buffer.visible(entity="obj:vase", frame=VF):
            w.porcelain.retract(r.id, "gone")
    return [
        lambda w: view(w, T("obj:desk", "colour", "oak")),
        lambda w: canon(w, T("obj:coin", "kind", "coin"), E("obj:coin", "in", "obj:desk"),
                        T("obj:coin", "slot", "left drawer")),
        lambda w: canon(w, T("obj:key", "material", "brass", timeless=False, valid_from=5.0)),
        lambda w: canon(w, E("obj:coin", "in", "place:hall", timeless=False, valid_from=6.0)),
        lambda w: view(w, T("obj:key", "kind", "key"), E("obj:key", "in", "obj:desk")),
        retract_vase,
        lambda w: view(w, T("person:mara", "mood", "calm", timeless=False, valid_from=2.0,
                            valid_to=7.0)),
        lambda w: canon(w, T("obj:cup", "kind", "cup"), E("obj:cup", "in", "obj:safe")),
        lambda w: canon(w, E("obj:cup", "in", "obj:desk", timeless=False, valid_from=8.0)),
        lambda w: view(w, T("obj:desk", "colour", "walnut", timeless=False, valid_from=9.0)),
    ]


@pytest.mark.parametrize("key", [KEY, None], ids=["keyed", "keyless"])
@pytest.mark.parametrize("at", [None, 20.0], ids=["at-latest", "at-fixed"])
def test_4_defining_property_over_a_fixture_history(manor, key, at):
    kw = {"at": at} if at is not None else {}
    docs = [mirror.export(manor, VF, key=key, **kw)]
    seen: set[tuple] = set()
    resets = 0
    for mutate in _history(manor):
        mutate(manor)
        for old in docs:                                  # every position a client could hold
            answer = assert_defining_property(manor, old, key, **kw)
            resets += is_reset(answer)
            seen |= {(o["op"], o.get("layer")) for o in answer["ops"]}
        docs.append(mirror.export(manor, VF, key=key, **kw))
    assert resets == 0, "a pure log history never needs a reset"
    expected = {("put", "known"), ("del", "known")}
    if key is not None:
        expected |= {("reveal", None), ("put", "present"), ("del", "present")}
    assert expected <= seen


def _construct_root() -> Path | None:
    env = os.environ.get("PB_CONSTRUCT_WORLDS")
    root = Path(env) if env else Path("/home/k/Newproject/worlds")
    return root if root.is_dir() else None


def _construct_files() -> list[Path]:
    root = _construct_root()
    return sorted(root.rglob("*.world")) if root else []


@pytest.mark.skipif(not _construct_files(),
                    reason="corpus check: construct's world folder is absent "
                           "(set PB_CONSTRUCT_WORLDS to a directory of host world files)")
def test_4_defining_property_on_copies_of_constructs_play_worlds(tmp_path):
    """20 log positions per world, with and without the present layer, over copies
    taken with the backup API from a `mode=ro` connection. By default a spread
    sample of the folder; PB_CONSTRUCT_ALL=1 runs every world."""
    files = _construct_files()
    if not os.environ.get("PB_CONSTRUCT_ALL"):
        files = files[:: max(1, len(files) // 6)][:6]
    checks = resets = 0
    for path in files:
        result = mirror_corpus.check_world(path, KEY, 20)
        assert result["mismatches"] == [], result
        checks += result["checks"]
        resets += result["resets"]
    assert checks > 0
    logging.getLogger(__name__).info(
        "construct worlds: %d worlds, %d checks, %d resets", len(files), checks, resets)


# ---------------------------------------------------------------- 5. resets


def _reset_cases(w):
    doc = mirror.export(w, VF, key=KEY)
    cursor = doc["cursor"]
    payload, mac = cursor.split(".")
    flipped = mac[:-2] + ("AA" if mac[-2:] != "AA" else "BB")
    other_scope = mirror.export(w, VF, key=KEY, frame_scope="continued")["cursor"]
    other_frame = mirror.export(w, OTHER_FRAME, key=KEY)["cursor"]
    future = mirror._mint_cursor(KEY, {**mirror._read_cursor(KEY, cursor),
                                       "h": w.buffer.head() + 3})
    wrong_world = mirror._mint_cursor(KEY, {**mirror._read_cursor(KEY, cursor),
                                            "w": "w:elsewhere"})
    return {
        "malformed text": "not-a-cursor", "no dot": payload, "empty": "",
        "bad payload": "!!!." + mac, "mac flipped": payload + "." + flipped,
        "unsigned in a keyed call": payload + ".",
        "another scope": other_scope, "another frame": other_frame,
        "another world": wrong_world, "head in the future": future,
        "not a string": 12345,
    }


def test_5_a_cursor_that_cannot_be_trusted_is_answered_with_clear(manor):
    for name, cursor in _reset_cases(manor).items():
        answer = mirror.feed(manor, VF, cursor, key=KEY)
        assert answer["ops"][0] == {"op": "clear"}, name
        assert answer["present_on"] is True
    # frame_scope differs ("continued" cursor, "exact" call) and the reverse
    other = mirror.export(manor, VF, key=KEY, frame_scope="merged")["cursor"]
    assert is_reset(mirror.feed(manor, VF, other, key=KEY, frame_scope="exact"))
    # the control: an honest cursor is not a reset
    honest = mirror.export(manor, VF, key=KEY)["cursor"]
    assert not is_reset(mirror.feed(manor, VF, honest, key=KEY))


def test_5_an_unsigned_cursor_with_a_future_at_is_answered_with_clear(manor):
    later = mirror.export(manor, VF, at=50.0)
    assert is_reset(mirror.feed(manor, VF, later["cursor"], at=10.0))
    assert not is_reset(mirror.feed(manor, VF, later["cursor"], at=50.0))
    assert not is_reset(mirror.feed(manor, VF, later["cursor"], at=60.0))


def test_5_a_signed_cursor_survives_the_host_rewinding_now(manor):
    doc = mirror.export(manor, VF, key=KEY, at=50.0)
    canon(manor, T("obj:coin", "kind", "coin"), E("obj:coin", "in", "obj:desk"))
    view(manor, T("obj:desk", "colour", "oak", timeless=False, valid_from=30.0))
    answer = assert_defining_property(manor, doc, KEY, at=10.0)
    assert not is_reset(answer)


def test_5_a_classifier_verdict_change_after_the_cursor_resets_through_the_digest(manor):
    view(manor, T("obj:desk", "colour", "oak"))
    doc = mirror.export(manor, VF, key=KEY)
    assert ["colour", "oak", "lit"] in doc["known"]["obj:desk"]["facts"]
    head = manor.buffer.head()
    row = manor.buffer.visible(entity="obj:desk", attribute="colour", frame=VF)[0]
    manor.classifier.set(row.id, "EVENT", 1.0)            # the log does not move
    assert manor.buffer.head() == head
    answer = assert_defining_property(manor, doc, KEY)
    assert is_reset(answer)
    after = mirror.apply(doc, answer)
    assert ["colour", "oak", "lit"] not in after["known"]["obj:desk"]["facts"]


# --------------------------------------------------------------- 6. reveal


def test_6_opening_the_drawer_reveals_then_puts_with_no_del(manor):
    doc = mirror.export(manor, VF, key=KEY)
    handle = h("obj:key")
    assert handle in doc["present"]
    view(manor, T("obj:key", "kind", "key"), E("obj:key", "in", "obj:desk"))
    answer, got = follow(manor, doc)
    assert answer["ops"][0] == {"op": "reveal", "handle": handle, "id": "obj:key"}
    assert ("del", "present", handle) not in ops_of(answer)
    assert ("put", "known", "obj:key") in ops_of(answer)
    assert ops_of(answer).index(("reveal", None, handle)) < ops_of(answer).index(
        ("put", "known", "obj:key"))
    assert "obj:key" in got["known"] and handle not in got["present"]
    assert CJ(got) == CJ(mirror.export(manor, VF, key=KEY))


# --------------------------------------------------------- 6a. both layers


def _one_step(w, mutate, key=KEY):
    doc = mirror.export(w, VF, key=key)
    mutate(w)
    answer = assert_defining_property(w, doc, key)
    assert not is_reset(answer)
    return answer


def test_6a_a_known_subjects_last_row_retracted_gives_del_known(manor):
    def retract(w):
        for r in w.buffer.visible(entity="obj:vase", frame=VF):
            w.porcelain.retract(r.id, "gone")
    answer = _one_step(manor, retract)
    assert ("del", "known", "obj:vase") in ops_of(answer)


def test_6a_a_known_subjects_changed_fact_gives_put_known(manor):
    answer = _one_step(manor, lambda w: view(w, T("obj:desk", "colour", "oak")))
    assert ops_of(answer) == [("put", "known", "obj:desk")]


def test_6a_a_new_item_in_a_covered_drawer_gives_put_present(manor):
    answer = _one_step(manor, lambda w: canon(
        w, T("obj:coin", "kind", "coin"), E("obj:coin", "in", "obj:desk")))
    assert ops_of(answer) == [("put", "present", h("obj:coin"))]


def test_6a_a_present_items_changed_look_gives_put_present(manor):
    answer = _one_step(manor, lambda w: canon(
        w, T("obj:key", "material", "brass", timeless=False, valid_from=4.0)))
    assert ops_of(answer) == [("put", "present", h("obj:key"))]
    assert answer["ops"][0]["value"]["look"] == [["material", "brass"]]


def test_6a_a_present_item_canon_moves_out_gives_del_present(manor):
    answer = _one_step(manor, lambda w: canon(
        w, E("obj:key", "in", "place:hall", timeless=False, valid_from=4.0)))
    assert ops_of(answer) == [("del", "present", h("obj:key"))]


def test_6a_ops_are_ordered_reveal_del_put_and_sorted_by_layer_then_key(manor):
    def several(w):
        view(w, T("obj:key", "kind", "key"), E("obj:key", "in", "obj:desk"))
        for r in w.buffer.visible(entity="obj:vase", frame=VF):
            w.porcelain.retract(r.id, "gone")
        canon(w, T("obj:coin", "kind", "coin"), E("obj:coin", "in", "obj:desk"))
        canon(w, E("obj:ring", "in", "place:hall", timeless=False, valid_from=4.0))
        view(w, T("obj:desk", "colour", "oak"))
    answer = _one_step(manor, several)
    kinds = [o["op"] for o in answer["ops"]]
    assert kinds == sorted(kinds, key=["reveal", "del", "put"].index)
    for kind in ("del", "put"):
        pairs = [(o["layer"], o["key"]) for o in answer["ops"] if o["op"] == kind]
        assert pairs == sorted(pairs) and len(pairs) > 1


# ------------------------------------------------------------ 6b. present_on


def test_6b_every_answer_carries_present_on(manor):
    reset = mirror.feed(manor, VF, None, key=KEY)
    doc = mirror.apply(mirror._empty_document(WORLD_ID, VF), reset)
    empty = mirror.feed(manor, VF, doc["cursor"], key=KEY)
    view(manor, T("obj:desk", "colour", "oak"))
    diff = mirror.feed(manor, VF, doc["cursor"], key=KEY)
    assert [a["present_on"] for a in (reset, empty, diff)] == [True, True, True]
    assert empty["ops"] == [] and not is_reset(diff)
    keyless = mirror.feed(manor, VF, None)
    assert keyless["present_on"] is False
    assert mirror.feed(manor, VF, keyless["cursor"])["present_on"] is False


def test_6b_a_mode_change_resets_and_apply_matches(manor):
    keyed = mirror.export(manor, VF, key=KEY)
    keyless = mirror.export(manor, VF)
    to_keyless = mirror.feed(manor, VF, keyed["cursor"])
    assert is_reset(to_keyless) and to_keyless["present_on"] is False
    assert mirror.apply(keyed, to_keyless)["present"] is None
    to_keyed = mirror.feed(manor, VF, keyless["cursor"], key=KEY)
    assert is_reset(to_keyed) and to_keyed["present_on"] is True
    got = mirror.apply(keyless, to_keyed)
    assert got["present"] is not None and CJ(got) == CJ(mirror.export(manor, VF, key=KEY))
    # apply refuses an answer that changes mode without a clear
    with pytest.raises(ValueError):
        mirror.apply(keyed, {"cursor": "x", "at": None, "present_on": False, "ops": []})
    with pytest.raises(ValueError):
        mirror.apply(keyless, {"cursor": "x", "at": None, "present_on": False,
                               "ops": [{"op": "put", "layer": "present", "key": "h:x",
                                        "value": {}}]})


# ------------------------------------------------------ 6c. handles back in


@pytest.fixture
def standalone(tmp_path):
    w = build_manor(tmp_path, "r.world")
    svc = WorldService(standalone=True, read_timeout=10, mirror_key=KEY)
    svc.attach(w, VF)
    try:
        yield w, svc, svc.session("holo", role="recorder")
    finally:
        svc.detach()
        w.close()


def _call(svc, sess, verb, **args):
    t, box = run_async(sess.call, verb, **args)
    pump_until_done(svc, t)
    if "e" in box:
        raise box["e"]
    return box["r"]


def test_6c_unhandle_maps_a_current_handle_to_its_id(standalone):
    w, svc, sess = standalone
    assert svc.unhandle(h("obj:key")) == "obj:key"
    assert svc.unhandle(h("obj:ring")) == "obj:ring"
    assert svc.unhandle(h("obj:safe")) == "obj:safe"


def test_6c_unhandle_answers_none_for_everything_else(standalone, tmp_path):
    w, svc, sess = standalone
    key_handle = h("obj:key")
    # forged, another key's, a person's, a known id's, garbage, non-strings
    for bad in ("h:" + "0" * 20, h("obj:key", OTHER_KEY), h("person:butler"),
                h("npc:thief"), h("obj:desk"), "obj:key", "h:xyz", "", None, 7):
        assert svc.unhandle(bad) is None, bad
    # stale: the item was perceived (now known), or moved away
    view(w, T("obj:key", "kind", "key"), E("obj:key", "in", "obj:desk"))
    svc.pump()
    assert svc.unhandle(key_handle) is None
    coin = h("obj:coin")
    canon(w, T("obj:coin", "kind", "coin"), E("obj:coin", "in", "obj:desk"))
    assert svc.unhandle(coin) == "obj:coin"
    canon(w, E("obj:coin", "in", "place:hall", timeless=False, valid_from=3.0))
    svc.set_now(4.0)
    assert svc.unhandle(coin) is None
    # a service with no key maps nothing
    other = WorldService(read_timeout=5)
    w2 = build_manor(tmp_path, "nokey.world")
    try:
        other.attach(w2, VF)
        assert other.unhandle(key_handle) is None
        other.detach()
    finally:
        w2.close()


def test_6c_unhandle_is_the_hosts_method_on_the_owner_thread(standalone):
    w, svc, sess = standalone
    assert "unhandle" not in VIEWER_READS and "unhandle" not in VIEWER_SERVICE_READS
    with pytest.raises(Refused):
        sess.call("unhandle", handle=h("obj:key"))
    t, box = run_async(svc.unhandle, h("obj:key"))
    t.join(5)
    assert isinstance(box.get("e"), RuntimeError)       # a foreign thread is refused


def test_6c_a_standalone_record_naming_a_handle_writes_the_event_and_the_feed_reveals(standalone):
    w, svc, sess = standalone
    doc = _call(svc, sess, "export")
    handle = h("obj:key")
    assert handle in doc["present"]
    head = w.buffer.head()
    out = _call(svc, sess, "record", items=[{"entity": handle, "attribute": "opened",
                                             "value": True}], at=9.0)
    assert out == {"status": "recorded"}
    assert w.buffer.head() > head
    rows = w.buffer.visible(entity="obj:key", attribute="opened")
    assert sorted(r.frame for r in rows) == sorted(["canon", VF])
    assert svc.last_record_outcome["status"] == "recorded"
    svc.pump()
    answer = _call(svc, sess, "feed", since=doc["cursor"])
    assert ops_of(answer)[0] == ("reveal", None, handle)
    assert answer["ops"][0]["id"] == "obj:key"
    assert ("put", "known", "obj:key") in ops_of(answer)
    assert mirror.apply(doc, answer)["present"].get(handle) is None


def test_6c_a_handle_as_an_entity_value_is_mapped_too(standalone):
    w, svc, sess = standalone
    out = _call(svc, sess, "record", items=[{"entity": "obj:desk", "attribute": "next_to",
                                             "value": h("obj:key"), "value_type": "entity"}])
    assert out == {"status": "recorded"}
    (row,) = w.buffer.visible(entity="obj:desk", attribute="next_to", frame=VF)
    assert row.value == "obj:key"


def test_6c_one_bad_handle_refuses_the_whole_batch_and_writes_nothing(standalone, caplog):
    w, svc, sess = standalone
    head = w.buffer.head()
    with caplog.at_level(logging.INFO, logger="patternbuffer.service"):
        out = _call(svc, sess, "record", items=[
            {"entity": h("obj:key"), "attribute": "opened", "value": True},
            {"entity": "h:" + "f" * 20, "attribute": "opened", "value": True}])
    assert out == {"status": "refused"}
    assert w.buffer.head() == head
    assert svc.last_record_outcome["cause"] == "unknown_handle"
    assert any(r.levelno == logging.WARNING and "refused" in r.getMessage()
               for r in caplog.records)
    # a person's handle is as unknown as a forged one
    out = _call(svc, sess, "record", items=[{"entity": h("person:butler"),
                                             "attribute": "opened", "value": True}])
    assert out == {"status": "refused"} and w.buffer.head() == head


def test_6c_the_public_record_answer_is_bare_for_every_batch(standalone, caplog):
    w, svc, sess = standalone
    batches = [
        [{"entity": "person:mara", "attribute": "mood", "value": "x"}],                # recorded
        [{"entity": "person:mara", "attribute": "in", "value": 7, "value_type": "entity"}],  # gate
        [{"entity": "person:mara", "attribute": "same_as", "value": "obj:x",
          "value_type": "entity"}],                                                    # barred
        [{"entity": "person:mara", "attribute": "mood", "value": "x", "frame": "canon"}],
        [{"entity": "h:" + "1" * 20, "attribute": "mood", "value": "x"}],
        [],                                                                            # empty
    ]
    seen = []
    with caplog.at_level(logging.INFO, logger="patternbuffer.service"):
        for batch in batches:
            out = _call(svc, sess, "record", items=batch)
            assert set(out) == {"status"} and out["status"] in ("recorded", "refused")
            seen.append(out["status"])
    assert seen == ["recorded", "refused", "refused", "refused", "refused", "refused"]
    assert any(r.levelno == logging.INFO and "committed" in r.getMessage()
               for r in caplog.records)


def test_6c_an_unexpected_record_failure_is_bare_and_names_nothing(standalone, monkeypatch):
    # r3.1: a failure other than AtomicAbort may name the id a handle mapped to
    w, svc, sess = standalone
    def boom(*a, **k):
        raise ValueError("cannot write obj:key")
    monkeypatch.setattr(w.porcelain, "commit_set", boom)
    out = _call(svc, sess, "record", items=[{"entity": h("obj:key"), "attribute": "opened",
                                             "value": True}])
    assert out == {"status": "refused"}
    assert "obj:key" in svc.last_record_outcome["error"]


def test_6c_a_non_recorder_calling_record_is_still_a_role_error(standalone):
    w, svc, sess = standalone
    viewer = svc.session("renderer")
    with pytest.raises(Refused):
        viewer.call("record", items=[{"entity": "obj:x", "attribute": "kind", "value": "t"}])
    with pytest.raises(Refused):                       # a call-shape error is not an outcome
        sess.call("record", items=[{"entity": "obj:x", "attribute": "kind", "value": "t"}],
                  frame="canon")


def _post(port, body):
    """(status, raw response bytes) of one POST /call."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/call", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _get(port, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


@pytest.fixture
def runner(tmp_path):
    build_manor(tmp_path, "run.world").close()
    model, route = make_runner_callable(None)
    r = Runner(lambda gated: World(tmp_path / "run.world", WORLD_ID, model=gated(model)), VF,
               port=0, recorders=("holo",), model_route=route, mirror_key=KEY).start()
    try:
        yield r
    finally:
        r.stop()


def _call_http(port, verb, session="holo", **args):
    code, raw = _post(port, {"session": session, "verb": verb, "args": args})
    return code, raw


def test_6c_over_http_a_handle_record_answers_exactly_recorded_and_the_feed_reveals(runner):
    port = runner.port
    code, raw = _call_http(port, "export")
    doc = json.loads(raw)["result"]
    handle = h("obj:key")
    assert code == 200 and handle in doc["present"]
    code, raw = _call_http(port, "record", items=[{"entity": handle, "attribute": "opened",
                                                    "value": True}], at=9.0)
    assert code == 200 and raw == b'{"result": {"status": "recorded"}}'
    for forbidden in (b"obj:key", b"receipt", b"frame", b"canon", b"assertion", b"rows"):
        assert forbidden not in raw
    for _ in range(100):                               # the runner pumps on its own
        code, raw = _call_http(port, "feed", since=doc["cursor"])
        answer = json.loads(raw)["result"]
        if answer["ops"]:
            break
        threading.Event().wait(0.05)
    assert [o["op"] for o in answer["ops"]][:2] == ["reveal", "put"]
    assert answer["ops"][0] == {"op": "reveal", "handle": handle, "id": "obj:key"}
    assert answer["ops"][1]["key"] == "obj:key"


def test_6c_a_bad_handle_and_a_barred_attribute_are_byte_identical_over_http(runner):
    port = runner.port
    bad_handle = [{"entity": "h:" + "a" * 20, "attribute": "opened", "value": True}]
    barred = [{"entity": "person:mara", "attribute": "same_as", "value": "obj:desk",
               "value_type": "entity"}]
    own_frame = [{"entity": "person:mara", "attribute": "mood", "value": "x",
                  "frame": "canon"}]
    not_object = ["nope"]
    answers = [_call_http(port, "record", items=items) for items in
               (bad_handle, barred, own_frame, not_object, [])]
    assert {a for a in answers} == {(200, b'{"result": {"status": "refused"}}')}


def test_6c_a_record_no_pump_runs_in_time_is_bare_refused_and_writes_nothing(
        standalone, monkeypatch):
    # pbr code review: a deferred (cancelled) job was a third public shape
    import patternbuffer.service as service_module
    w, svc, sess = standalone
    monkeypatch.setattr(service_module, "DEFAULT_WAIT", 0)
    head = w.buffer.head()
    out = sess.call("record", items=[{"entity": "person:mara", "attribute": "mood",
                                      "value": "x"}])
    assert out == {"status": "refused"}
    svc.pump()                                         # the cancelled job never runs
    assert w.buffer.head() == head
    assert svc.last_record_outcome["cause"] == "deferred"


def test_6c_a_handle_map_failure_is_the_same_bare_http_refusal(runner, monkeypatch):
    # pbr code review: an exception while mapping handles reached the wire as a 500
    def boom(*a, **k):
        raise ValueError("obj:key")
    monkeypatch.setattr(mirror, "present_handles", boom)
    code, raw = _call_http(runner.port, "record", items=[
        {"entity": h("obj:key"), "attribute": "opened", "value": True}])
    assert (code, raw) == (200, b'{"result": {"status": "refused"}}')
    assert b"obj:key" not in raw
    assert runner.service.last_record_outcome["cause"] == "error"


# ------------------------------------------------------- 6d. slot and address


def test_6d_a_canon_slot_and_address_cross_and_absent_ones_are_omitted(manor):
    doc = mirror.export(manor, VF, key=KEY)
    key_record = doc["present"][h("obj:key")]
    assert key_record["in"] == ["in", "obj:desk", "top drawer"]
    assert key_record["address"] == "manor/study/desk:0"
    ring = doc["present"][h("obj:ring")]
    assert ring["in"] == ["in", h("obj:safe")] and "address" not in ring
    canon(manor, T("obj:coin", "kind", "coin"), E("obj:coin", "in", "obj:desk"))
    assert mirror.export(manor, VF, key=KEY)["present"][h("obj:coin")]["in"] == [
        "in", "obj:desk"]


def test_6d_the_relation_is_the_winning_containment_rows_attribute(manor):
    canon(manor, E("obj:hat", "worn_by", "obj:vase"), T("obj:hat", "kind", "hat"),
          E("obj:gem", "carried_by", "obj:vase"), T("obj:gem", "kind", "gem"),
          E("obj:rug", "within", "place:study"), T("obj:rug", "kind", "rug"))
    present = mirror.export(manor, VF, key=KEY)["present"]
    assert present[h("obj:hat")]["in"] == ["worn_by", "obj:vase"]
    assert present[h("obj:gem")]["in"] == ["carried_by", "obj:vase"]
    assert present[h("obj:rug")]["in"] == ["within", "place:study"]


# ----------------------------------------------------------------- 7. handles


def test_7_the_same_key_gives_the_same_handles_and_a_different_key_gives_others(manor):
    a = mirror.export(manor, VF, key=KEY)["present"]
    b = mirror.export(manor, VF, key=KEY)["present"]
    c = mirror.export(manor, VF, key=OTHER_KEY)["present"]
    assert set(a) == set(b) and not set(a) & set(c) and len(a) == len(c)
    assert all(k.startswith("h:") and len(k) == 22 and set(k[2:]) <= set(HEXS) for k in a)
    assert h("obj:key") == "h:" + __import__("hmac").new(
        KEY, f"{WORLD_ID}\x00obj:key".encode(), hashlib.sha256).hexdigest()[:20]


def test_7_a_representative_change_gives_del_and_put(manor):
    canon(manor, T("obj:band", "kind", "ring"), E("obj:band", "in", "obj:safe"),
          T("obj:hoop", "kind", "ring"), E("obj:hoop", "in", "obj:safe"))
    manor.porcelain.merge("obj:band", "obj:hoop", "the same ring", representative="obj:band")
    doc = mirror.export(manor, VF, key=KEY)
    assert h("obj:band") in doc["present"] and h("obj:hoop") not in doc["present"]
    manor.porcelain.merge("obj:band", "obj:hoop", "re-point", representative="obj:hoop")
    answer = assert_defining_property(manor, doc)
    assert not is_reset(answer)
    assert ops_of(answer) == [("del", "present", h("obj:band")),
                              ("put", "present", h("obj:hoop"))]


def test_7_a_handle_collision_raises(manor, monkeypatch):
    monkeypatch.setattr(mirror, "handle_for", lambda key, wid, ident: "h:" + "0" * 20)
    with pytest.raises(ValueError):
        mirror.export(manor, VF, key=KEY)


@pytest.mark.parametrize("bad", ["a-string-key-of-sufficient-length", b"short", 12])
def test_7_a_key_is_bytes_of_at_least_16(manor, bad):
    with pytest.raises((TypeError, ValueError)):
        mirror.export(manor, VF, key=bad)
    with pytest.raises((TypeError, ValueError)):
        WorldService(mirror_key=bad)


# ------------------------------------------------------------ 8. determinism


def test_8_two_exports_of_one_state_are_byte_identical(manor, tmp_path):
    a, b = mirror.export(manor, VF, key=KEY), mirror.export(manor, VF, key=KEY)
    assert CJ(a).encode("utf-8") == CJ(b).encode("utf-8")
    twin = build_manor(tmp_path, "twin.world")
    try:
        assert CJ(mirror.export(twin, VF, key=KEY)) == CJ(a)
    finally:
        twin.close()


def test_8_canonical_json_is_sorted_compact_and_keeps_unicode():
    assert CJ({"b": 1, "a": ["é", None]}) == '{"a":["é",null],"b":1}'


# ----------------------------------------------------------------- 9. service


@pytest.fixture
def hosted(tmp_path):
    w = build_manor(tmp_path)
    svc = WorldService(read_timeout=10, mirror_key=KEY)
    svc.attach(w, VF)
    try:
        yield w, svc, svc.session("holo-emitter")
    finally:
        svc.detach()
        w.close()


def test_9_both_verbs_serve_from_the_snapshot_and_never_touch_the_world(hosted, monkeypatch):
    w, svc, sess = hosted
    want = mirror.export(w, VF, at=svc.now(), key=KEY)

    def boom(*a, **k):
        raise AssertionError("a viewer service verb touched the live World")
    monkeypatch.setattr(w.buffer, "visible", boom)
    monkeypatch.setattr(w.buffer, "head", boom)
    doc = sess.call("export")
    assert CJ(doc) == CJ(want)
    answer = sess.call("feed", since=doc["cursor"])
    assert answer["ops"] == [] and answer["present_on"] is True
    assert sess.call("feed")["ops"][0] == {"op": "clear"}


def test_9_a_viewer_sees_the_last_pump_and_the_feed_follows_it(hosted):
    w, svc, sess = hosted
    doc = sess.call("export")
    view(w, T("obj:desk", "colour", "oak"))
    assert sess.call("feed", since=doc["cursor"])["ops"] == []      # not pumped yet
    svc.pump()
    answer = sess.call("feed", since=doc["cursor"])
    assert ops_of(answer) == [("put", "known", "obj:desk")]
    assert CJ(mirror.apply(doc, answer)) == CJ(sess.call("export"))


def test_9_the_service_uses_its_now_and_its_frame_scope(tmp_path):
    w = build_manor(tmp_path)
    svc = WorldService(read_timeout=10, mirror_key=KEY)
    svc.attach(w, VF, frame_scope="merged")
    try:
        svc.set_now(33.0)
        sess = svc.session("c")
        doc = sess.call("export")
        assert doc["at"] == 33.0
        body = mirror._read_cursor(KEY, doc["cursor"])
        assert body["s"] == "merged" and body["t"] == 33.0
        svc.set_now(None)
        assert sess.call("export")["at"] == w.buffer.max_valid_from()
    finally:
        svc.detach()
        w.close()


@pytest.mark.parametrize("verb,extra", [
    ("export", {}), ("feed", {})])
@pytest.mark.parametrize("name,value", [
    ("frame", "canon"), ("frame", VF), ("frame_scope", "merged"), ("at", 3.0),
    ("key", "x" * 20), ("key", None), ("perceive_in", VF), ("anything", 1)])
def test_9_the_verbs_refuse_frame_scope_at_key_and_anything_else(hosted, verb, extra,
                                                                  name, value):
    _, _, sess = hosted
    with pytest.raises(Refused):
        sess.call(verb, **{name: value})


def test_9_export_takes_no_since_and_feed_takes_a_string_only(hosted):
    _, _, sess = hosted
    with pytest.raises(Refused):
        sess.call("export", since=None)
    for bad in (5, {"a": 1}, ["x"], True):
        with pytest.raises(Refused):
            sess.call("feed", since=bad)
    assert sess.call("feed", since=None)["ops"][0]["op"] == "clear"


def test_9_a_set_view_frame_resets_older_cursors(hosted):
    w, svc, sess = hosted
    doc = sess.call("export")
    assert not is_reset(sess.call("feed", since=doc["cursor"]))
    svc.set_view_frame(OTHER_FRAME)
    answer = sess.call("feed", since=doc["cursor"])
    assert is_reset(answer)
    other = mirror.apply(mirror._empty_document(WORLD_ID, OTHER_FRAME), answer)
    assert set(other["known"]) == {"obj:desk", "person:butler"}


def test_9_a_service_with_no_key_serves_no_present_layer(tmp_path):
    w = build_manor(tmp_path)
    svc = WorldService(read_timeout=10)
    svc.attach(w, VF)
    try:
        doc = svc.session("c").call("export")
        assert doc["present"] is None and doc["cursor"].endswith(".")
    finally:
        svc.detach()
        w.close()


def test_9_the_walk_covers_both_lists():
    public = {n for n in dir(Porcelain) if not n.startswith("_")}
    assert VIEWER_SERVICE_READS == ("export", "feed")
    classified = [set(VIEWER_READS), set(VIEWER_SERVICE_READS), set(VIEWER_EXCLUDED)]
    for i, a in enumerate(classified):
        for b in classified[i + 1:]:
            assert not a & b
    # the service verbs are not porcelain verbs: nothing reaches them by reflection
    assert not set(VIEWER_SERVICE_READS) & public
    # every porcelain verb is classified in a list, the service's own verbs
    # (`resolve`) apart; the three lists together are the whole door
    porcelain = {n for n, m in __import__("inspect").getmembers(Porcelain, __import__("inspect").isfunction)
                 if not n.startswith("_")}
    assert porcelain - set(VIEWER_READS) - set(VIEWER_EXCLUDED) == set()


def test_9_the_runners_post_call_serves_both_and_get_changes_is_404(runner):
    port = runner.port
    code, raw = _call_http(port, "export", session="viewer")
    doc = json.loads(raw)["result"]
    assert code == 200 and doc["schema"] == mirror.SCHEMA and doc["present"] is not None
    code, raw = _call_http(port, "feed", session="viewer", since=doc["cursor"])
    answer = json.loads(raw)["result"]
    assert code == 200 and answer["ops"] == [] and answer["present_on"] is True
    code, raw = _call_http(port, "feed", session="viewer", since=doc["cursor"], at=1)
    assert code == 400 and json.loads(raw)["error"]["type"] == "refused"
    assert _get(port, "/changes?since=0")[0] == 404
    assert _get(port, "/changes")[0] == 404


def test_9_the_runner_with_no_key_has_no_present_layer(tmp_path):
    build_manor(tmp_path, "nk.world").close()
    model, route = make_runner_callable(None)
    r = Runner(lambda gated: World(tmp_path / "nk.world", WORLD_ID, model=gated(model)), VF,
               port=0, model_route=route).start()
    try:
        code, raw = _call_http(r.port, "export", session="v")
        assert json.loads(raw)["result"]["present"] is None
    finally:
        r.stop()


def test_9_the_service_main_reads_a_mirror_key_file(tmp_path):
    from patternbuffer import service
    build_manor(tmp_path, "cli.world").close()
    keyfile = tmp_path / "key.bin"
    keyfile.write_bytes(KEY)
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
    with mock.patch.object(service, "Runner", FakeRunner), \
            mock.patch.object(service.threading, "Event", FakeEvent), \
            mock.patch.object(service.signal, "signal"):
        service.main(["--world", str(tmp_path / "cli.world"), "--world-id", WORLD_ID,
                      "--view-frame", VF, "--mirror-key-file", str(keyfile)])
    assert started["mirror_key"] == KEY


# --------------------------------------------------------------------- 10. CLI


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_10_the_cli_leaves_the_world_file_untouched_and_creates_no_journal(
        tmp_path, capfd):
    build_manor(tmp_path, "static.world").close()
    path = tmp_path / "static.world"
    keyfile = tmp_path / "key.bin"
    keyfile.write_bytes(KEY)
    before = (_sha(path), path.stat().st_mtime_ns, sorted(os.listdir(tmp_path)))
    # the directory and the file are read-only too: a write handle could not be opened
    path.chmod(0o444)
    tmp_path.chmod(0o555)
    try:
        code = mirror.main(["export", "--world", str(path), "--world-id", WORLD_ID,
                            "--view-frame", VF, "--mirror-key-file", str(keyfile)])
    finally:
        tmp_path.chmod(stat.S_IRWXU)
        path.chmod(0o644)
    out = capfd.readouterr().out
    assert code == 0
    after = (_sha(path), path.stat().st_mtime_ns, sorted(os.listdir(tmp_path)))
    assert after == before
    assert not [n for n in os.listdir(tmp_path) if n.endswith(("-journal", "-wal", "-shm"))]
    doc = json.loads(out)
    reopened = mirror.open_read_only_copy(path, WORLD_ID)
    try:
        assert CJ(doc) + "\n" == out
        assert CJ(doc) == CJ(mirror.export(reopened, VF, key=KEY))
    finally:
        reopened.close()
    assert doc["present"] and doc["schema"] == mirror.SCHEMA


def test_10_the_cli_options_and_the_module_entry_point(tmp_path):
    build_manor(tmp_path, "opt.world").close()
    path = tmp_path / "opt.world"
    env = {**os.environ, "PYTHONPATH": str(Path(mirror.__file__).resolve().parents[1])}
    run = subprocess.run(
        [sys.executable, "-m", "patternbuffer.mirror", "export", "--world", str(path),
         "--world-id", WORLD_ID, "--view-frame", VF, "--at", "4.5"],
        capture_output=True, env=env, timeout=60, check=True)
    doc = json.loads(run.stdout)
    assert doc["present"] is None and doc["at"] == 4.5 and doc["view_frame"] == VF
    assert not [n for n in os.listdir(tmp_path) if "journal" in n]


# -------------------------------------------------------------- 11. vectors


def test_11_the_committed_vectors_are_what_the_generator_makes(tmp_path):
    assert VECTORS.read_text(encoding="utf-8") == render(build_vectors(tmp_path)), \
        "run `python tests/make_view_vectors.py` after a deliberate change"


def test_11_python_apply_replays_the_shared_vectors():
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert vectors["schema"] == mirror.SCHEMA and vectors["sequences"]
    ops_seen: set[tuple] = set()
    for seq in vectors["sequences"]:
        doc = seq["start"]
        for step in seq["steps"]:
            doc = mirror.apply(doc, step["answer"])
            assert doc == step["expect"], (seq["name"], step["name"])
            ops_seen |= {(o["op"], o.get("layer")) for o in step["answer"]["ops"]}
    assert {("clear", None), ("reveal", None), ("put", "known"), ("put", "present"),
            ("del", "known"), ("del", "present")} <= ops_seen


# ------------------------------------------------------------------- 12. cost


@pytest.mark.skipif(not _construct_files(),
                    reason="corpus check: construct's world folder is absent")
def test_12_cost_on_the_largest_construct_world(capsys):
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
        doc = mirror.export(full, frame, key=KEY)
        export_s = time.perf_counter() - start
        size = len(CJ(doc).encode("utf-8"))
        old_doc = mirror.export(old, frame, key=KEY)
        start = time.perf_counter()
        answer = mirror.feed(full, frame, old_doc["cursor"], key=KEY)
        feed_s = time.perf_counter() - start
        assert CJ(mirror.apply(old_doc, answer)) == CJ(doc)
        with capsys.disabled():
            print(f"\n[cost] {path.name} ({path.stat().st_size} B, head {head}, {frame}): "
                  f"export {export_s:.3f} s, feed {feed_s:.3f} s "
                  f"({'reset' if is_reset(answer) else 'diff'}), document {size} B, "
                  f"{len(doc['known'])} known, {len(doc['present'])} present")
        assert feed_s < 5.0, f"a feed took {feed_s:.2f} s (> 5 s)"
        assert export_s < 5.0
    finally:
        old.close()
        full.close()
        conn.close()
