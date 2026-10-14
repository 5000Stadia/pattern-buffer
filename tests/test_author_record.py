"""AUTHOR-RECORD-V1: an author session writes canon or a character's knowledge,
never the player's view.

One test (or group) per numbered test of specs/AUTHOR-RECORD-V1.md (1-11).
Every wait has a timeout, so a hung call fails the test instead of hanging it.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request

import pytest

from manor_fixture import KEY, VF as MANOR_VF, WORLD_ID, build_manor
from patternbuffer import World, mirror
from patternbuffer.mcp import V1_READS, build_registry
from patternbuffer.service import (VIEWER_EXCLUDED, Refused, Runner, WorldService,
                                   main, make_runner_callable)
from service_fixture import (SAMPLE_CALLS, VF, build_world, pump_until_done,
                             run_async)

MOOD = {"entity": "person:mara", "attribute": "mood", "value": "wary"}
BRAM = "knows:person:bram"
BARE_RECORDED = {"status": "recorded"}
BARE_REFUSED = {"status": "refused"}


def _call(svc, sess, verb, **args):
    t, box = run_async(sess.call, verb, **args)
    pump_until_done(svc, t)
    if "e" in box:
        raise box["e"]
    return box["r"]


@pytest.fixture
def hosted(tmp_path):
    """(world, service, author session) on a hosted (non-standalone) service."""
    w = build_world(tmp_path)
    svc = WorldService(read_timeout=10)
    svc.attach(w, VF)
    try:
        yield w, svc, svc.session("photonic", role="author")
    finally:
        svc.detach()
        w.close()


def _scoped(tmp_path, scope: str, name: str):
    w = build_world(tmp_path, name=name)
    svc = WorldService(read_timeout=10)
    svc.attach(w, VF, frame_scope=scope)
    return w, svc, svc.session("photonic", role="author")


def _rows(w, frame, **kw):
    return w.buffer.visible(entity="person:mara", attribute="mood", frame=frame, **kw)


# ------------------------------------------------------------- 1. canon only


def test_1_an_author_record_writes_each_item_once_into_canon_as_stated(tmp_path):
    w = build_manor(tmp_path)
    svc = WorldService(read_timeout=10, mirror_key=KEY)
    svc.attach(w, MANOR_VF)
    sess = svc.session("photonic", role="author")
    try:
        doc = sess.call("export")
        head = w.buffer.head()
        out = _call(svc, sess, "record", items=[
            {"entity": "person:mara", "attribute": "mood", "value": "wary"},
            {"entity": "person:mara", "attribute": "gait", "value": "slow"}], at=7.0)
        assert out == BARE_RECORDED
        assert w.buffer.head() == head + 2                   # two rows, no copies
        for attribute in ("mood", "gait"):
            rows = w.buffer.visible(entity="person:mara", attribute=attribute)
            assert [(r.frame, r.status, r.valid_from) for r in rows] == \
                [("canon", "stated", 7.0)]
        assert not w.buffer.visible(entity="person:mara", attribute="mood", frame=MANOR_VF)
        svc.pump()
        answer = sess.call("feed", since=doc["cursor"])
        assert [o for o in answer["ops"] if o.get("layer") == "known"] == []
    finally:
        svc.detach()
        w.close()


def test_1_the_default_valid_from_is_at_then_now_and_timeless_is_kept(hosted):
    w, svc, sess = hosted
    svc.set_now(11.0)
    _call(svc, sess, "record", items=[
        MOOD, {**MOOD, "attribute": "trade", "value": "smith", "timeless": True},
        {**MOOD, "attribute": "gait", "value": "slow", "valid_from": 2.0}])
    got = {r.attribute: r.valid_from for r in w.buffer.visible(entity="person:mara",
                                                               frame="canon")
           if r.attribute in ("mood", "trade", "gait")}
    assert got["mood"] == 11.0 and got["gait"] == 2.0 and got["trade"] is None


# ----------------------------------------------------- 2. a character's knowledge


def test_2_a_knows_frame_outside_the_view_is_written_there_only(hosted):
    w, svc, sess = hosted
    out = _call(svc, sess, "record", items=[MOOD], at=3.0, frame=BRAM)
    assert out == BARE_RECORDED
    rows = _rows(w, BRAM)
    assert [(r.frame, r.status, r.value) for r in rows] == [(BRAM, "stated", "wary")]
    assert not _rows(w, "canon") and not _rows(w, VF)


# ------------------------------------------------ 3. the view, under each scope


def test_3_the_view_frame_itself_is_refused_with_nothing_written(hosted):
    w, svc, sess = hosted
    head = w.buffer.head()
    assert _call(svc, sess, "record", items=[MOOD], frame=VF) == BARE_REFUSED
    assert svc.last_record_outcome["cause"] == "invalid"
    assert "player's view" in svc.last_record_outcome["reason"]
    assert w.buffer.head() == head


def test_3_a_frame_continued_into_the_view_is_refused_under_continued(tmp_path):
    w, svc, sess = _scoped(tmp_path, "continued", "c.world")
    try:
        w.porcelain.continue_frame("person:marie", "person:mara", "the same woman")
        head = w.buffer.head()
        assert _call(svc, sess, "record", items=[MOOD],
                     frame="knows:person:marie") == BARE_REFUSED
        assert w.buffer.head() == head
        assert _call(svc, sess, "record", items=[MOOD], frame=BRAM) == BARE_RECORDED
    finally:
        svc.detach()
        w.close()


def test_3_a_same_as_members_frame_is_refused_under_merged(tmp_path):
    w, svc, sess = _scoped(tmp_path, "merged", "m.world")
    try:
        assert w.porcelain.merge("person:mara", "person:barmaid",
                                 "the same woman")["outcome"] == "merged"
        head = w.buffer.head()
        assert _call(svc, sess, "record", items=[MOOD],
                     frame="knows:person:barmaid") == BARE_REFUSED
        assert w.buffer.head() == head
        assert _call(svc, sess, "record", items=[MOOD], frame=BRAM) == BARE_RECORDED
    finally:
        svc.detach()
        w.close()


def test_3_the_scope_is_read_at_the_head_when_the_job_runs(tmp_path):
    w, svc, sess = _scoped(tmp_path, "continued", "h.world")
    try:
        marie = "knows:person:marie"
        assert _call(svc, sess, "record", items=[MOOD], frame=marie) == BARE_RECORDED
        w.porcelain.continue_frame("person:marie", "person:mara", "the same woman")
        head = w.buffer.head()
        assert _call(svc, sess, "record", items=[MOOD], frame=marie) == BARE_REFUSED
        assert w.buffer.head() == head
    finally:
        svc.detach()
        w.close()


# ------------------------------------------------------------ 4. other frames


@pytest.mark.parametrize("frame", [
    "plot:x", "scene:y", "", 42, None, ["canon"], "Canon", "canon ",
    "knows:", "knows:mara", "knows:Person:x", "knows:person:", "knows:person:x\n",
    "knows:person:x y"])
def test_4_every_other_frame_is_refused_in_a_batch_with_a_valid_item(hosted, frame):
    w, svc, sess = hosted
    head = w.buffer.head()
    out = sess.call("record", items=[MOOD, {**MOOD, "attribute": "gait", "value": "x"}],
                    frame=frame)
    assert out == BARE_REFUSED
    assert svc.last_record_outcome["cause"] == "invalid"
    assert w.buffer.head() == head


# --------------------------------------------------------------- 5. item rules


@pytest.mark.parametrize("bad", [
    {"frame": "canon"}, {"frame": BRAM}, {"status": "stated"}, {"status": "observed"},
    {"aliases": ["Mar"]}, {"confidence": 1.0}, {"value_type": "unresolved"},
])
def test_5_an_item_naming_its_own_keys_is_refused_writing_nothing(hosted, bad):
    w, svc, sess = hosted
    head = w.buffer.head()
    assert sess.call("record", items=[{**MOOD, **bad}]) == BARE_REFUSED
    assert svc.last_record_outcome["cause"] == "invalid"
    assert w.buffer.head() == head


HANDLE = "h:" + "a" * 20


@pytest.mark.parametrize("item", [
    {"entity": "attr:wears", "attribute": "resolvable_for", "value": "person"},
    {"entity": "a:3", "attribute": "kind", "value": "x"},
    {"entity": "person:mara", "attribute": "same_as", "value": "person:barmaid",
     "value_type": "entity"},
    {"entity": "person:mara", "attribute": "retracts", "value": "a:1"},
    {"entity": HANDLE, "attribute": "opened", "value": True},
    {"entity": "person:mara", "attribute": "holds", "value": HANDLE,
     "value_type": "entity"},
])
def test_5_bookkeeping_barred_attributes_and_handles_are_refused(hosted, item):
    w, svc, sess = hosted
    head = w.buffer.head()
    assert sess.call("record", items=[MOOD, item]) == BARE_REFUSED
    assert svc.last_record_outcome["cause"] == "invalid"
    assert w.buffer.head() == head


def test_5_a_handle_shaped_literal_value_is_only_text(hosted):
    w, svc, sess = hosted
    assert _call(svc, sess, "record", items=[{**MOOD, "value": HANDLE}]) == BARE_RECORDED


def test_5_the_recorders_other_item_rules_hold(hosted):
    _, svc, sess = hosted
    for items in ([], "x", [1], [{**MOOD, "value_type": "set"}]):
        assert sess.call("record", items=items) == BARE_REFUSED
    assert sess.call("record", items=[MOOD], at="soon") == BARE_REFUSED
    assert sess.call("record", items=[MOOD], at=True) == BARE_REFUSED
    with pytest.raises(Refused):
        sess.call("record", items=[MOOD], status="stated")        # an unknown argument
    with pytest.raises(Refused):
        sess.call("record")


# -------------------------------------------------------------------- 6. atomic


def test_6_a_batch_with_one_bad_item_writes_nothing(hosted):
    w, svc, sess = hosted
    head = w.buffer.head()
    # a shape refusal, before the owner job
    assert sess.call("record", items=[MOOD, {**MOOD, "frame": "canon"}]) == BARE_REFUSED
    assert w.buffer.head() == head
    # a gate refusal, inside the one commit_set
    out = _call(svc, sess, "record", items=[
        MOOD, {"entity": "person:mara", "attribute": "in", "value": 7,
               "value_type": "entity"}], frame=BRAM)
    assert out == BARE_REFUSED
    assert svc.last_record_outcome["cause"] == "gate_skip"
    assert w.buffer.head() == head


def test_6_one_call_is_one_unit(hosted):
    w, svc, sess = hosted
    units = []
    real = w.buffer.atomic_unit
    w.buffer.atomic_unit = lambda body: (units.append(1), real(body))[1]
    _call(svc, sess, "record", items=[MOOD, {**MOOD, "attribute": "gait", "value": "x"}])
    assert len(units) == 1


# ---------------------------------------------------------------- 7. bare answer


def test_7_a_commit_answers_exactly_recorded_and_keeps_the_receipt(hosted, caplog):
    w, svc, sess = hosted
    with caplog.at_level(logging.INFO, logger="patternbuffer.service"):
        out = _call(svc, sess, "record", items=[MOOD], at=4.0, frame=BRAM)
    assert out == BARE_RECORDED and set(out) == {"status"}
    outcome = svc.last_record_outcome
    assert outcome["status"] == "recorded"
    assert {row["frame"] for row in outcome["receipt"]["rows"]} == {BRAM}
    assert any(r.levelno == logging.INFO and "record committed" in r.message
               for r in caplog.records)


def test_7_every_refusal_answers_exactly_refused_and_keeps_the_reason(hosted, caplog):
    w, svc, sess = hosted
    batches = [
        dict(items=[MOOD], frame="plot:x"),                       # a bad frame
        dict(items=[MOOD], frame=VF),                             # the view
        dict(items=[{**MOOD, "status": "stated"}]),               # a bad item
        dict(items=[{"entity": HANDLE, "attribute": "opened", "value": 1}]),
        dict(items=[{"entity": "person:mara", "attribute": "in", "value": 7,
                     "value_type": "entity"}]),                   # the gate
    ]
    causes = []
    with caplog.at_level(logging.INFO, logger="patternbuffer.service"):
        for batch in batches:
            out = _call(svc, sess, "record", **batch)
            assert out == BARE_REFUSED and set(out) == {"status"}
            causes.append(svc.last_record_outcome["cause"])
    assert causes == ["invalid", "invalid", "invalid", "invalid", "gate_skip"]
    assert svc.last_record_outcome["status"] == "refused"
    assert sum(r.levelno == logging.WARNING and "record refused" in r.message
               for r in caplog.records) == 5


def test_7_no_pump_in_time_is_a_bare_refusal_writing_nothing(hosted, monkeypatch):
    import patternbuffer.service as service_module
    w, svc, sess = hosted
    monkeypatch.setattr(service_module, "DEFAULT_WAIT", 0)
    head = w.buffer.head()
    assert sess.call("record", items=[MOOD]) == BARE_REFUSED
    svc.pump()                                          # the cancelled job never runs
    assert w.buffer.head() == head
    assert svc.last_record_outcome["cause"] == "deferred"


# --------------------------------------------------------------------- 8. roles


def test_8_a_viewer_cannot_record(hosted):
    _, svc, _ = hosted
    with pytest.raises(Refused):
        svc.session("viewer").call("record", items=[MOOD])


def test_8_a_recorder_is_unchanged_and_still_refuses_frame(tmp_path):
    w = build_world(tmp_path, name="rec.world")
    svc = WorldService(standalone=True, read_timeout=10)
    svc.attach(w, VF)
    rec = svc.session("holo", role="recorder")
    try:
        assert _call(svc, rec, "record", items=[MOOD], at=9.0) == BARE_RECORDED
        rows = _rows(w, "canon") + _rows(w, VF)
        assert sorted((r.frame, r.status) for r in rows) == \
            [("canon", "observed"), (VF, "observed")]
        with pytest.raises(Refused):
            rec.call("record", items=[MOOD], frame=BRAM)
        with pytest.raises(Refused):
            rec.call("record", items=[MOOD], frame="canon")
        assert not _rows(w, BRAM)
        # an author on the same standalone service is allowed too
        author = svc.session("photonic", role="author")
        assert _call(svc, author, "record", items=[{**MOOD, "value": "calm"}],
                     at=10.0) == BARE_RECORDED
    finally:
        svc.detach()
        w.close()


def test_8_the_author_role_works_hosted_where_the_recorder_stays_refused(hosted):
    _, svc, _ = hosted
    assert svc.session("a", role="author").role == "author"
    with pytest.raises(Refused):
        svc.session("holo", role="recorder")
    with pytest.raises(ValueError):
        svc.session("x", role="owner")


def test_8_an_author_holds_every_viewer_verb_and_its_reads_are_the_views(hosted):
    w, svc, author = hosted
    viewer = svc.session("viewer")
    for verb, args in SAMPLE_CALLS.items():
        assert author.call(verb, **args) == viewer.call(verb, **args), verb
    assert author.call("now") == viewer.call("now")
    with pytest.raises(Refused):
        author.call("state", entity="person:mara", attribute="mood", frame="canon")
    with pytest.raises(Refused):
        author.call("frame_diff")                          # no canon read surface
    # writing canon gives it no canon read
    _call(svc, author, "record", items=[{**MOOD, "value": "hidden"}], at=5.0)
    svc.pump()
    assert author.call("state", entity="person:mara", attribute="mood")["status"] == "unknown"
    assert viewer.call("facts") == author.call("facts")


# -------------------------------------------------------------------- 9. runner


def _post(port, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/call", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, resp.read()


@pytest.fixture
def runner(tmp_path):
    build_world(tmp_path, name="run.world").close()
    model, route = make_runner_callable(None)
    r = Runner(lambda gated: World(tmp_path / "run.world", "w:svc", model=gated(model)), VF,
               port=0, recorders=("holo",), authors=("photonic",),
               model_route=route).start()
    try:
        yield r
    finally:
        r.stop()


def test_9_an_author_name_opens_an_author_session_over_http(runner):
    assert runner.session("photonic").role == "author"
    assert runner.session("holo").role == "recorder"
    assert runner.session("anyone").role == "viewer"
    code, raw = _post(runner.port, {"session": "photonic", "verb": "record", "args": {
        "items": [MOOD], "at": 4.0, "frame": BRAM}})
    assert (code, raw) == (200, b'{"result": {"status": "recorded"}}')
    # a viewer cannot; a recorder naming frame stays refused
    for session, extra in (("anyone", {}), ("holo", {"frame": "canon"})):
        try:
            _post(runner.port, {"session": session, "verb": "record",
                                "args": {"items": [MOOD], **extra}})
            raise AssertionError("expected a 400")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400


def test_9_the_http_answers_are_byte_identical_to_the_recorders(runner):
    commit_a = _post(runner.port, {"session": "photonic", "verb": "record",
                                   "args": {"items": [MOOD], "at": 4.0}})
    commit_r = _post(runner.port, {"session": "holo", "verb": "record",
                                   "args": {"items": [{**MOOD, "value": "x"}], "at": 5.0}})
    assert commit_a == commit_r == (200, b'{"result": {"status": "recorded"}}')
    bad_a = _post(runner.port, {"session": "photonic", "verb": "record",
                                "args": {"items": [MOOD], "frame": VF}})
    bad_r = _post(runner.port, {"session": "holo", "verb": "record",
                                "args": {"items": [{**MOOD, "frame": "canon"}]}})
    assert bad_a == bad_r == (200, b'{"result": {"status": "refused"}}')
    for forbidden in (b"receipt", b"frame", b"canon", b"rows", b"assertion", b"reason"):
        assert forbidden not in commit_a[1] + bad_a[1]


def test_9_a_name_in_both_author_and_recorder_fails_at_start(tmp_path):
    with pytest.raises(ValueError, match="photonic"):
        Runner(lambda gated: None, VF, recorders=("photonic", "holo"),
               authors=("photonic",))
    with pytest.raises(SystemExit) as exc:
        main(["--world", str(tmp_path / "x.world"), "--world-id", "w:x",
              "--view-frame", VF, "--recorder", "photonic", "--author", "photonic"])
    assert exc.value.code == 2


def test_9_the_author_flag_is_repeatable_and_reaches_the_runner(tmp_path, monkeypatch):
    import patternbuffer.service as service_module
    seen = {}

    class Stub:
        port = 0

        def __init__(self, *args, **kw):
            seen.update(kw)

        def start(self):
            return self

        def stop(self):
            pass

    monkeypatch.setattr(service_module, "Runner", Stub)
    stop = threading.Event()
    stop.set()
    monkeypatch.setattr(service_module.threading, "Event", lambda: stop)
    assert main(["--world", str(tmp_path / "x.world"), "--world-id", "w:x",
                 "--view-frame", VF, "--author", "photonic", "--author", "scribe",
                 "--recorder", "holo"]) == 0
    assert seen["authors"] == ("photonic", "scribe") and seen["recorders"] == ("holo",)


# ---------------------------------------------------------------- 10. the mirror


def test_10_a_canon_move_into_a_known_drawer_feeds_a_present_put_and_no_known_op(tmp_path):
    w = build_manor(tmp_path)
    svc = WorldService(read_timeout=10, mirror_key=KEY)
    svc.attach(w, MANOR_VF)
    sess = svc.session("photonic", role="author")
    try:
        doc = sess.call("export")
        out = _call(svc, sess, "record", items=[
            {"entity": "obj:coin", "attribute": "kind", "value": "coin", "timeless": True},
            {"entity": "obj:coin", "attribute": "in", "value": "obj:desk",
             "value_type": "entity", "timeless": True}], at=5.0)
        assert out == BARE_RECORDED
        svc.pump()
        answer = sess.call("feed", since=doc["cursor"])
        handle = mirror.handle_for(KEY, WORLD_ID, "obj:coin")
        assert [(o["op"], o.get("layer"), o.get("key")) for o in answer["ops"]] == \
            [("put", "present", handle)]
        assert not [o for o in answer["ops"] if o.get("layer") == "known"]
        assert "obj:coin" not in json.dumps(answer)
    finally:
        svc.detach()
        w.close()


# --------------------------------------------------------------- 11. the surface


def test_11_the_author_verb_is_a_service_verb_not_a_porcelain_one():
    reg = build_registry()
    assert len(reg) == 46 and "record" not in reg
    assert "record" not in VIEWER_EXCLUDED and "record" not in V1_READS
