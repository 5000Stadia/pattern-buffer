"""WORLD-SERVICE-V1: the service, its sessions, the rate cap and the runner.

One test per check of specs/WORLD-SERVICE-V1.md (Checks 1, 1b, 1c, 2, 3, 4, 5, 6;
the engine checks 1a, 4a and 7 live in test_world_snapshot.py). Every wait has
a timeout, so a hung call fails the test instead of hanging the suite.
"""

from __future__ import annotations

import inspect
import json
import threading
import urllib.error
import urllib.request

import pytest

from patternbuffer import World
from patternbuffer.mcp import V1_READS
from patternbuffer.model import TASK_RESOLVE, task_request
from patternbuffer.porcelain import Porcelain
from patternbuffer.service import (
    ADAPTERS,
    VIEWER_EXCLUDED,
    VIEWER_READS,
    NoModel,
    RateCap,
    Refused,
    Runner,
    WorldService,
    make_runner_callable,
)

from service_fixture import (
    OTHER,
    SAMPLE_CALLS,
    VF,
    Recorder,
    build_world,
    pump_until_done,
    run_async,
)


@pytest.fixture
def hosted(tmp_path):
    """(world, service, viewer session) attached on the test thread."""
    model = Recorder()
    w = build_world(tmp_path, model=model)
    svc = WorldService(read_timeout=10)
    svc.attach(w, VF)
    try:
        yield w, svc, svc.session("holo-emitter"), model
    finally:
        svc.detach()
        w.close()


def _resolve(svc, sess, entity="person:barmaid", aspect="wears", **kw):
    t, box = run_async(sess.call, "resolve", entity=entity, aspect=aspect, wait=10, **kw)
    pump_until_done(svc, t)
    if "e" in box:
        raise box["e"]
    return box["r"]


# ------------------------------------------------------------ (1) the owner


def test_owner_jobs_run_inside_pump_on_the_attaching_thread(hosted):
    w, svc, sess, model = hosted
    t, box = run_async(sess.call, "resolve", entity="person:barmaid", aspect="wears", wait=10)
    # nothing runs until the host pumps
    t.join(0.3)
    assert t.is_alive() and not model.resolves
    ran_on = []
    real = w.porcelain.resolve
    w.porcelain.resolve = lambda *a, **k: (ran_on.append(threading.get_ident()),
                                           real(*a, **k))[1]
    pump_until_done(svc, t)
    assert box["r"]["status"] == "resolved"
    assert ran_on == [threading.get_ident()]               # the test (owner) thread


def test_pump_and_detach_refuse_a_foreign_thread(hosted):
    _, svc, _, _ = hosted
    for fn in (svc.pump, svc.detach):
        t, box = run_async(fn)
        t.join(10)
        assert isinstance(box.get("e"), RuntimeError)


def test_a_job_that_did_not_run_in_its_wait_is_deferred_and_cancelled(hosted):
    w, svc, sess, model = hosted
    head = w.buffer.head()
    out = sess.call("resolve", entity="person:barmaid", aspect="wears", wait=0.05)
    assert out["status"] == "deferred" and out["retry_after"] > 0
    svc.pump()                                              # the late pump runs nothing
    assert w.buffer.head() == head and not model.resolves


def test_after_detach_jobs_and_reads_answer_detached(tmp_path):
    w = build_world(tmp_path)
    svc = WorldService(read_timeout=10)
    svc.attach(w, VF)
    sess = svc.session("x")
    queued, box = run_async(sess.call, "resolve", entity="person:barmaid",
                            aspect="wears", wait=10)
    queued.join(0.2)
    assert queued.is_alive()
    svc.detach()                                            # answers the queued job
    queued.join(10)
    assert box["r"] == {"status": "detached"}
    assert sess.call("resolve", entity="person:barmaid", aspect="wears") == \
        {"status": "detached"}
    assert sess.call("state", entity="person:mara", attribute="gold") == \
        {"status": "detached"}
    head = w.buffer.head()
    w.close()                                               # closing after detach is safe
    assert head > 0


def test_reattach_after_a_swap(tmp_path):
    w1 = build_world(tmp_path, name="a.world")
    svc = WorldService(read_timeout=10)
    svc.attach(w1, VF)
    sess = svc.session("x")
    assert sess.call("state", entity="person:mara", attribute="gold")["status"] == "known"
    svc.detach()
    w1.close()
    w2 = build_world(tmp_path, name="b.world")
    svc.attach(w2, VF)
    try:
        assert sess.call("state", entity="person:mara", attribute="gold")["status"] == "known"
    finally:
        svc.detach()
        w2.close()


# ------------------------------------------- (1b) readers never wait on a turn


def test_a_viewer_read_during_an_open_author_unit_returns_at_once(hosted):
    w, svc, sess, _ = hosted
    seen = {}

    def author_turn() -> None:
        # the owner sits inside a long unit with uncommitted writes; the
        # reader thread must answer from the last snapshot regardless
        w.ingest_structured([{"entity": "person:mara", "attribute": "gold", "value": 99,
                              "valid_from": 8.0}], classify="rules")
        t, box = run_async(sess.call, "state", entity="person:mara", attribute="gold")
        t.join(10)
        assert not t.is_alive(), "a viewer read waited on the author's unit"
        seen.update(box)

    w.buffer.atomic_unit(author_turn)
    assert "e" not in seen and seen["r"]["fact"]["value"] == 3      # the last commit
    svc.pump()                                              # now the turn is committed
    assert sess.call("state", entity="person:mara", attribute="gold")["fact"]["value"] == 3
    assert w.porcelain.state("person:mara", "gold")["fact"]["value"] == 99


def test_a_viewer_sees_the_world_as_of_the_last_pump(hosted):
    w, svc, sess, _ = hosted
    w.ingest_structured([{"entity": "person:mara", "attribute": "gold", "value": 7,
                          "valid_from": 6.0}], frame=VF, classify="rules")
    assert sess.call("state", entity="person:mara", attribute="gold")["fact"]["value"] == 3
    svc.pump()
    assert sess.call("state", entity="person:mara", attribute="gold")["fact"]["value"] == 7


# ----------------------------------------------------- (1c) snapshot cadence


def test_snapshot_cadence_keys_on_head_and_verdict_version(hosted):
    w, svc, sess, _ = hosted
    assert svc.snapshot_count == 1                          # taken at attach
    for _ in range(3):
        svc.pump()
    assert svc.snapshot_count == 1                          # idle pumps copy nothing
    # reads (even the salience read, which writes its sidecar) copy nothing
    sess.call("salience", entity="person:mara")
    w.porcelain.salience("person:mara")
    svc.pump()
    assert svc.snapshot_count == 1
    # a rollback moves log_version but not the committed head: no copy
    with pytest.raises(ZeroDivisionError):
        w.buffer.atomic_unit(lambda: (_ for _ in ()).throw(ZeroDivisionError()))
    svc.pump()
    assert svc.snapshot_count == 1
    # a commit: a copy
    w.ingest_structured([{"entity": "person:mara", "attribute": "gold", "value": 4,
                          "valid_from": 5.0}], classify="rules")
    svc.pump()
    assert svc.snapshot_count == 2
    svc.pump()
    assert svc.snapshot_count == 2
    # a sidecar-only change (a later verdict on an existing row): a copy, and the
    # viewer reads the new class
    row = w.buffer.visible(entity="person:mara", attribute="gold", frame=VF)[0]
    w.classifier.set(row.id, "DISPOSITIONAL")
    svc.pump()
    assert svc.snapshot_count == 3
    seen = svc._published.classifier.durability(row.id)
    assert seen == "DISPOSITIONAL"


def test_retired_snapshots_are_closed(hosted):
    w, svc, sess, _ = hosted
    first = svc._published
    sess.call("state", entity="person:mara", attribute="gold")      # the reader takes it
    w.ingest_structured([{"entity": "obj:cup", "attribute": "kind", "value": "cup",
                          "timeless": True}], classify="rules")
    svc.pump()
    sess.call("state", entity="person:mara", attribute="gold")      # takes the newer one
    with pytest.raises(Exception):
        first.buffer.head()                                          # closed, retired


# ---------------------------------------- (2) a viewer cannot read canon etc.


def test_every_porcelain_verb_is_allowlisted_or_excluded():
    public = {n for n, m in inspect.getmembers(Porcelain, inspect.isfunction)
              if not n.startswith("_")}
    classified = set(VIEWER_READS) | set(VIEWER_EXCLUDED)
    assert public - classified == set(), \
        f"unclassified porcelain verbs (excluded until classified): {public - classified}"
    assert not (set(VIEWER_READS) & set(VIEWER_EXCLUDED))
    assert set(VIEWER_READS) <= public and set(VIEWER_EXCLUDED) <= public
    assert set(VIEWER_READS) <= set(V1_READS)
    assert set(ADAPTERS) == set(VIEWER_READS) == set(SAMPLE_CALLS)


def test_the_allowlist_is_exactly_the_specs():
    assert set(VIEWER_READS) == {
        "snapshot", "state", "state_union", "where", "aggregate", "confidence",
        "locate", "contents", "composition", "features", "path", "route",
        "neighborhood", "salience", "events", "in_transit", "entities",
        "facts", "refer", "canonical_attribute"}
    for verb in ("frame_diff", "who_knows", "proposals", "identity_conflicts",
                 "typing_conflicts", "correlations", "correlation_conflicts",
                 "fidelity_audit", "axis_heads"):
        assert verb in VIEWER_EXCLUDED


@pytest.mark.parametrize("verb", sorted(SAMPLE_CALLS))
@pytest.mark.parametrize("frame", ["canon", OTHER, VF, "plot:secret"])
def test_naming_a_frame_is_refused_on_every_viewer_read(hosted, verb, frame):
    _, _, sess, _ = hosted
    with pytest.raises(Refused):
        sess.call(verb, **SAMPLE_CALLS[verb], frame=frame)


@pytest.mark.parametrize("verb", sorted(SAMPLE_CALLS))
def test_frame_scope_is_refused_on_every_viewer_read(hosted, verb):
    _, _, sess, _ = hosted
    with pytest.raises(Refused):
        sess.call(verb, **SAMPLE_CALLS[verb], frame_scope=["canon"])


@pytest.mark.parametrize("verb", sorted(SAMPLE_CALLS))
def test_every_viewer_read_is_served_from_the_view_frame_alone(hosted, verb):
    w, svc, sess, _ = hosted
    got = sess.call(verb, **SAMPLE_CALLS[verb])
    from service_fixture import sample_args
    want = json.loads(json.dumps(getattr(w.porcelain, verb)(**sample_args(verb))))
    assert json.loads(json.dumps(got)) == want


def test_nothing_of_canon_or_another_frame_reaches_a_viewer(hosted):
    _, _, sess, _ = hosted
    # a canon-only fact and a canon-only entity
    assert sess.call("state", entity="person:barmaid", attribute="secret")["status"] == "unknown"
    assert "person:stranger" not in sess.call("entities")
    assert sess.call("state", entity="person:barmaid", attribute="mood")["status"] == "unknown"
    blob = json.dumps(sess.call("facts")) + json.dumps(sess.call("events"))
    assert "owes a debt" not in blob
    assert '"sour"' not in blob
    assert "stranger" not in blob
    for rows in (sess.call("facts"),):
        assert {f["provenance"]["status"] for f in rows} <= {"stated", "observed"}


@pytest.mark.parametrize("verb", sorted(set(VIEWER_EXCLUDED) - {"resolve"}))
def test_every_excluded_verb_is_refused(hosted, verb):
    _, _, sess, _ = hosted      # (resolve is the service's own pinned verb)
    with pytest.raises(Refused):
        sess.call(verb)


def test_unknown_verbs_and_unknown_arguments_are_refused(hosted):
    _, _, sess, _ = hosted
    with pytest.raises(Refused):
        sess.call("drop_table")
    with pytest.raises(ValueError):
        sess.call("state", entity="person:mara", attribute="gold", color="red")


def test_forced_parameters_are_refused_not_ignored(hosted):
    _, _, sess, _ = hosted
    for args in ({"model": True}, {"learn": True}, {"model": False}):
        with pytest.raises(Refused):
            sess.call("refer", description="the barmaid", **args)
    with pytest.raises(Refused):
        sess.call("facts", include_meta=True)
    # facts carry no meta rows
    assert all(not f["entity"].startswith(("a:", "attr:")) for f in sess.call("facts"))


# ------------------------------------------------------------ (3) resolve


def test_resolve_plants_forces_and_mirrors_in_one_unit(hosted):
    w, svc, sess, model = hosted
    svc.set_now(5.0)
    out = _resolve(svc, sess)
    assert out["status"] == "resolved" and set(out) == {"status", "facts", "receipt"}
    assert [f["value"] for f in out["facts"]] == ["a red wool kirtle"]
    assert out["facts"][0]["provenance"]["status"] == "observed"
    # only the view frame's rows left the service: no canon id, no canon frame
    canon_ids = {r.id for r in w.buffer.visible(frame="canon", attribute="wears")}
    assert not canon_ids & {r["assertion_id"] for r in out["receipt"]["rows"]}
    assert out["receipt"]["frames"] == [VF]
    # the engine: canon placeholder + value, the mirror in the view frame at `now`
    view = w.buffer.visible(entity="person:barmaid", attribute="wears", frame=VF)
    assert [(r.status, r.valid_from) for r in view] == [("observed", 5.0)]
    canon = w.buffer.visible(entity="person:barmaid", attribute="wears", frame="canon")
    assert {r.status for r in canon} == {"generated"} and len(model.resolves) == 1
    # visible to the viewer's reads after the pump that ran the job
    assert sess.call("state", entity="person:barmaid", attribute="wears")["status"] == "known"


def test_resolve_is_memoized_and_writes_nothing_the_second_time(hosted):
    w, svc, sess, model = hosted
    first = _resolve(svc, sess)
    head = w.buffer.head()
    second = _resolve(svc, sess)
    assert second["facts"] == first["facts"]
    assert w.buffer.head() == head and len(model.resolves) == 1


def test_resolve_is_refused_when_the_entity_is_absent_from_the_view_frame(hosted):
    w, svc, sess, model = hosted
    head = w.buffer.head()
    out = _resolve(svc, sess, entity="person:stranger")     # canon only
    assert out["status"] == "not_perceptible"
    assert _resolve(svc, sess, entity="person:nobody")["status"] == "not_perceptible"
    assert w.buffer.head() == head and not model.resolves


def test_the_perceptible_hook_decides_and_a_raising_hook_fails_closed(tmp_path):
    model = Recorder()
    w = build_world(tmp_path, model=model)
    seen = []

    def hook(world, entity, aspect):
        seen.append((world is w, entity, aspect))
        return aspect != "mood"

    svc = WorldService(read_timeout=10)
    svc.attach(w, VF, perceptible=hook)
    sess = svc.session("x")
    try:
        head = w.buffer.head()
        refused = _resolve(svc, sess, aspect="mood")
        assert refused["status"] == "not_perceptible" and w.buffer.head() == head
        assert _resolve(svc, sess, aspect="wears")["status"] == "resolved"
        assert seen == [(True, "person:barmaid", "mood"), (True, "person:barmaid", "wears")]
    finally:
        svc.detach()
        w.close()
    w = build_world(tmp_path, model=Recorder(), name="b.world")
    svc = WorldService(read_timeout=10)
    svc.attach(w, VF, perceptible=lambda *_: 1 / 0)
    try:
        assert _resolve(svc, svc.session("y"))["status"] == "not_perceptible"
    finally:
        svc.detach()
        w.close()


@pytest.mark.parametrize("extra", [
    {"frame": "canon"}, {"frame": OTHER}, {"frame": VF}, {"perceive_in": OTHER},
    {"perceive_in": "canon"}, {"at": 3.0}, {"frame_scope": ["canon"]}, {"color": 1},
])
def test_a_viewer_resolve_takes_entity_aspect_and_wait_only(hosted, extra):
    w, svc, sess, model = hosted
    head = w.buffer.head()
    with pytest.raises(Refused):
        sess.call("resolve", entity="person:barmaid", aspect="wears", **extra)
    assert w.buffer.head() == head and not model.resolves


def test_a_placeholder_planted_only_in_a_hidden_frame_is_never_forced_by_a_viewer(hosted):
    w, svc, sess, model = hosted
    w.ingest_structured([{"entity": "person:barmaid", "attribute": "wears",
                          "value": {"policy": "invent_under_canon",
                                    "constraints": ["a hidden constraint"]},
                          "value_type": "unresolved", "valid_from": 2.0}],
                        frame=OTHER, classify="rules")
    hidden_before = w.buffer.visible(frame=OTHER)
    head = w.buffer.head()
    for extra in ({"frame": OTHER}, {"perceive_in": OTHER}):
        with pytest.raises(Refused):
            sess.call("resolve", entity="person:barmaid", aspect="wears", **extra)
    assert w.buffer.head() == head and not model.resolves
    # the honest viewer resolve acts on canon only: it never touches the hidden one
    out = _resolve(svc, sess)
    assert out["status"] == "resolved"
    assert w.buffer.visible(frame=OTHER) == hidden_before
    assert all("a hidden constraint" not in p for p, _ in model.resolves)


def test_a_mirror_refused_at_the_gate_rolls_back_the_whole_viewer_resolve(hosted):
    w, svc, sess, model = hosted
    head = w.buffer.head()
    svc.set_now(float("inf"))
    out = _resolve(svc, sess)
    assert out == {"status": "failed", "reason": "gate_skip"}
    assert w.buffer.head() == head
    assert w.buffer.visible(entity="person:barmaid", attribute="wears") == []
    svc.set_now(5.0)
    assert _resolve(svc, sess)["status"] == "resolved"


def test_a_model_failure_is_reported_and_leaves_nothing(tmp_path):
    w = build_world(tmp_path, model=Recorder(fail=True))
    svc = WorldService(read_timeout=10)
    svc.attach(w, VF)
    sess = svc.session("x")
    try:
        head = w.buffer.head()
        assert _resolve(svc, sess) == {"status": "failed", "reason": "RuntimeError"}
        assert w.buffer.head() == head
    finally:
        svc.detach()
        w.close()


def test_undeclared_and_unknown_answers_carry_no_canon_reason(hosted):
    w, svc, sess, _ = hosted
    out = _resolve(svc, sess, aspect="haircolour")          # not declared resolvable
    assert out == {"status": "undeclared", "facts": []}


def test_contents_resolve_is_perceived_whole(hosted):
    w, svc, sess, _ = hosted
    out = _resolve(svc, sess, entity="place:attic", aspect="contents")
    assert out["status"] == "resolved"
    attrs = {f["attribute"] for f in out["facts"]}
    assert {"kind", "name", "in"} <= attrs
    assert sess.call("contents", container="place:attic")


# -------------------------------------------------------- the rate cap


class _Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def _resolve_route(schema) -> str:
    return "model" if schema.get("title") == TASK_RESOLVE else "code"


def test_the_rate_cap_defers_model_routed_viewer_resolves_and_writes_nothing(tmp_path):
    model = Recorder()
    clock = _Clock()
    svc = WorldService(model_route=_resolve_route, rate=RateCap(1, 60.0, clock),
                       read_timeout=10)
    w = build_world(tmp_path, model=svc.gated(model))
    handle = w.resolver._model
    svc.attach(w, VF)
    sess = svc.session("x")
    try:
        assert _resolve(svc, sess, entity="person:barmaid")["status"] == "resolved"
        head = w.buffer.head()
        out = _resolve(svc, sess, entity="person:mara")
        assert out["status"] == "deferred" and out["retry_after"] >= 59.0
        assert w.buffer.head() == head                      # nothing written
        assert w.buffer.visible(entity="person:mara", attribute="wears") == []
        assert len(model.resolves) == 1                     # the second never reached it
        # the service never swaps the engine's handles: the gated callable the
        # host injected is the one in place, before, during and after
        assert w.resolver._model is handle and w.classifier._model is handle
        # a memoized resolve is never capped
        assert _resolve(svc, sess, entity="person:barmaid")["status"] == "resolved"
        # author work is never capped
        author = w.porcelain.resolve("person:mara", "wears")
        assert author["status"] == "resolved" and author["planted"] is True
        # the window moves on
        clock.t += 61
        assert _resolve(svc, sess, entity="place:attic", aspect="contents")["status"] == "resolved"
    finally:
        svc.detach()
        w.close()


def test_a_code_route_is_never_capped(tmp_path):
    svc = WorldService(model_route=lambda schema: "code", rate=RateCap(0, 60.0),
                       read_timeout=10)
    w = build_world(tmp_path, model=svc.gated(Recorder()))
    svc.attach(w, VF)
    sess = svc.session("x")
    try:
        assert _resolve(svc, sess, entity="person:barmaid")["status"] == "resolved"
        assert _resolve(svc, sess, entity="person:mara")["status"] == "resolved"
    finally:
        svc.detach()
        w.close()


def test_no_model_route_means_every_call_counts(tmp_path):
    svc = WorldService(rate=RateCap(0, 60.0), read_timeout=10)
    w = build_world(tmp_path, model=svc.gated(Recorder()))
    svc.attach(w, VF)
    try:
        assert _resolve(svc, svc.session("x"))["status"] == "deferred"
    finally:
        svc.detach()
        w.close()


# ------------------------------------------- r5: no hook, only inventing

def _with_hook(tmp_path, hook, name="h.world", model=None):
    w = build_world(tmp_path, model=model or Recorder(), name=name)
    svc = WorldService(read_timeout=10)
    svc.attach(w, VF, perceptible=hook)
    return w, svc, svc.session("x")


def test_without_a_hook_a_viewer_cannot_read_a_canon_concrete_value(hosted):
    w, svc, sess, model = hosted
    head = w.buffer.head()
    out = _resolve(svc, sess, aspect="secret")          # canon: "owes a debt"
    assert out["status"] == "not_perceptible"
    assert w.buffer.head() == head and not model.resolves
    assert w.buffer.visible(entity="person:barmaid", attribute="secret", frame=VF) == []


def test_with_a_hook_that_says_yes_the_canon_value_is_served_and_mirrored(tmp_path):
    w, svc, sess = _with_hook(tmp_path, lambda world, e, a: True)
    try:
        out = _resolve(svc, sess, aspect="secret")
        assert out["status"] == "resolved"
        assert [f["value"] for f in out["facts"]] == ["owes a debt"]
        assert [f["provenance"]["status"] for f in out["facts"]] == ["observed"]
        mirrored = w.buffer.visible(entity="person:barmaid", attribute="secret", frame=VF)
        assert [r.status for r in mirrored] == ["observed"]
    finally:
        svc.detach()
        w.close()


def test_a_spent_memo_not_yet_in_the_view_needs_a_hook(tmp_path):
    w, svc, sess = _with_hook(tmp_path, None)
    try:
        # the author resolved it in canon; the player has not perceived it
        w.porcelain.resolve("person:barmaid", "wears")
        head = w.buffer.head()
        assert _resolve(svc, sess)["status"] == "not_perceptible"
        assert w.buffer.head() == head
        # a host that says yes serves and mirrors it ...
        svc._perceptible = lambda world, e, a: True
        assert _resolve(svc, sess)["status"] == "resolved"
        # ... after which the view holds it, and a no-hook repeat ask is plain memo
        svc._perceptible = None
        again = _resolve(svc, sess)
        assert again["status"] == "resolved" and again["facts"][0]["value"] == "a red wool kirtle"
    finally:
        svc.detach()
        w.close()


def test_without_a_hook_a_viewer_may_still_plant_and_force_or_force_an_unspent_placeholder(
        tmp_path):
    model = Recorder()
    w, svc, sess = _with_hook(tmp_path, None, model=model)
    try:
        assert _resolve(svc, sess)["status"] == "resolved"              # E1 plant-and-force
        w.ingest_structured([{"entity": "person:mara", "attribute": "wears",
                              "value": {"policy": "invent_under_canon"},
                              "value_type": "unresolved", "valid_from": 1.0}],
                            classify="rules")                           # a host-planted one
        assert _resolve(svc, sess, entity="person:mara")["status"] == "resolved"
        assert len(model.resolves) == 2
    finally:
        svc.detach()
        w.close()


def test_resolver_preview_agrees_with_resolve(tmp_path):
    model = Recorder()
    w = build_world(tmp_path, model=model)
    try:
        r = w.resolver
        assert r.preview("person:barmaid", "wears")[0] == "invent"
        assert r.preview("person:barmaid", "haircolour")[0] == "nothing"
        kind, rows = r.preview("person:barmaid", "secret")
        assert kind == "served" and [x.value for x in rows] == ["owes a debt"]
        assert not model.resolves and w.buffer.head() == w.buffer.head()
        w.porcelain.resolve("person:barmaid", "wears")
        kind, rows = r.preview("person:barmaid", "wears")
        assert kind == "served" and [x.value for x in rows] == ["a red wool kirtle"]
    finally:
        w.close()


# ------------------------------------------- r5: existence is perspectival


def _bytes(x) -> str:
    return json.dumps(x)


def test_a_canon_only_id_and_a_nonexistent_id_answer_identically_on_snapshot(hosted):
    _, _, sess, _ = hosted
    for canon_only, nowhere in (("person:stranger", "person:nobody"),
                                ("place:cellar", "place:nowhere")):
        a = sess.call("snapshot", scope=[canon_only])
        b = sess.call("snapshot", scope=[nowhere])
        assert "error" in a and "error" in b
        assert _bytes(a).replace(canon_only, "<ID>") == _bytes(b).replace(nowhere, "<ID>")
        a = sess.call("snapshot", scope=canon_only)
        b = sess.call("snapshot", scope=nowhere)
        assert _bytes(a).replace(canon_only, "<ID>") == _bytes(b).replace(nowhere, "<ID>")
        # mixed with a real one: only the bad id is listed, as for a nonexistent
        mixed_a = sess.call("snapshot", scope=["person:mara", canon_only])
        mixed_b = sess.call("snapshot", scope=["person:mara", nowhere])
        assert mixed_a["bad"] == [canon_only] and mixed_b["bad"] == [nowhere]
    # an id the view frame holds is served
    ok = sess.call("snapshot", scope=["person:mara"])
    assert "error" not in ok and ok["facts"]
    # the engine's own error text is the one used
    assert sess.call("snapshot", scope=["person:nobody"])["error"].startswith(
        "snapshot scope must be KNOWN entity ids")


def test_every_other_viewer_read_already_answers_canon_only_like_nowhere(hosted):
    """The walk: for each allowlisted verb that takes an id, a canon-only id and
    a nonexistent one differ in nothing but the echoed id. Only `snapshot`
    needed the adapter's normalization."""
    _, _, sess, _ = hosted
    arg_names = {"state": ["entity"], "state_union": ["entity"], "confidence": ["entity"],
                 "locate": ["entity"], "contents": ["container"],
                 "composition": ["entity"], "features": ["place"], "neighborhood": ["entity"],
                 "salience": ["entity"], "in_transit": ["agent"], "facts": ["entity"],
                 "aggregate": ["container"]}
    pairs = (("person:stranger", "person:nobody"), ("place:cellar", "place:nowhere"))
    for verb, names in arg_names.items():
        for canon_only, nowhere in pairs:
            outs = []
            for ident in (canon_only, nowhere):
                args = {**SAMPLE_CALLS[verb], **{n: ident for n in names}}
                outs.append(_bytes(sess.call(verb, **args)).replace(ident, "<ID>"))
            assert outs[0] == outs[1], (verb, canon_only)
    for verb, key in (("path", "a"), ("route", "a")):
        for canon_only, nowhere in pairs:
            outs = [_bytes(sess.call(verb, **{**SAMPLE_CALLS[verb], key: i})).replace(i, "<ID>")
                    for i in (canon_only, nowhere)]
            assert outs[0] == outs[1], verb
    for canon_only, nowhere in pairs:
        for mk in (lambda i: {"description": "the person", "scope": i},
                   lambda i: {"description": "the thing", "constraints": [["contains", i]]}):
            outs = [_bytes(sess.call("refer", **mk(i))).replace(i, "<ID>")
                    for i in (canon_only, nowhere)]
            assert outs[0] == outs[1]


# ------------------------------------------------- r5: the gated model


def test_gated_is_transparent_to_the_host_and_applies_the_cap_only_in_viewer_jobs(tmp_path):
    model = Recorder()
    svc = WorldService(model_route=_resolve_route, rate=RateCap(0, 60.0), read_timeout=10)
    handle = svc.gated(model)
    assert handle("p", {"title": TASK_RESOLVE}) == model("p", {"title": TASK_RESOLVE})
    w = build_world(tmp_path, model=handle)
    svc.attach(w, VF)
    sess = svc.session("x")
    try:
        # the cap is zero: a viewer job is deferred; the author's resolve is not
        assert _resolve(svc, sess)["status"] == "deferred"
        assert w.porcelain.resolve("person:barmaid", "wears")["status"] == "resolved"
        assert not getattr(svc._job, "viewer", False)          # the flag never leaks
        # and a failing job clears it too
        svc.set_now(float("inf"))
        assert _resolve(svc, sess, entity="person:mara")["status"] in ("failed", "deferred")
        assert not getattr(svc._job, "viewer", False)
    finally:
        svc.detach()
        w.close()
    with pytest.raises(TypeError):
        svc.gated(None)


def test_an_ungated_world_with_rate_logs_and_answers_no_rate_cap(tmp_path, caplog):
    model = Recorder()
    w = build_world(tmp_path, model=model)                    # NOT svc.gated(...)
    svc = WorldService(rate=RateCap(5, 60.0), read_timeout=10)
    with caplog.at_level("WARNING", logger="patternbuffer.service"):
        svc.attach(w, VF)
    assert any("rate cap is inactive" in r.message for r in caplog.records)
    sess = svc.session("x")
    try:
        head = w.buffer.head()
        assert _resolve(svc, sess)["status"] == "no_rate_cap"
        assert w.buffer.head() == head and not model.resolves
        # what never reaches the model is unaffected
        assert _resolve(svc, sess, aspect="haircolour")["status"] == "undeclared"
        # a code route is not a model call
        svc._model_route = lambda schema: "code"
        assert _resolve(svc, sess)["status"] == "resolved"
    finally:
        svc.detach()
        w.close()


def test_an_ungated_world_without_rate_proceeds_uncapped(hosted):
    w, svc, sess, model = hosted
    assert not svc._gated
    assert _resolve(svc, sess)["status"] == "resolved" and len(model.resolves) == 1


def test_the_service_never_writes_the_engines_model_handles():
    import pathlib
    import re
    src = (pathlib.Path(__file__).parent.parent / "src" / "patternbuffer" / "service.py"
           ).read_text()
    assert not re.search(r"\._model\s*(,[^=\n]*)?=[^=]", src), "a write to a ._model handle"


# ------------------------------------------------ FRAME-CONTINUITY-V1 §5


@pytest.mark.parametrize("verb", ["state", "state_union", "facts"])
@pytest.mark.parametrize("scope", ["exact", "continued", "merged", "bogus"])
def test_a_viewer_cannot_name_a_frame_scope_on_the_three_widenable_reads(hosted, verb, scope):
    _, _, sess, _ = hosted
    with pytest.raises(Refused):
        sess.call(verb, **SAMPLE_CALLS[verb], frame_scope=scope)


def test_the_hosts_frame_scope_is_the_one_the_service_uses(tmp_path):
    w = build_world(tmp_path)
    w.ingest_structured([{"entity": "person:barmaid", "attribute": "hat", "value": "felt",
                          "valid_from": 2.0}], frame="knows:person:daniel", classify="rules")
    w.porcelain.continue_frame("person:daniel", "person:mara", "the same man; host decision")
    try:
        for scope, expect_daniel in (("exact", False), ("continued", True)):
            svc = WorldService(read_timeout=10)
            svc.attach(w, VF, frame_scope=scope)
            try:
                sess = svc.session("x")
                frames = {f["provenance"]["frame"] for f in sess.call("facts")}
                assert ("knows:person:daniel" in frames) is expect_daniel
                assert (sess.call("state", entity="person:barmaid",
                                  attribute="hat")["status"] == "known") is expect_daniel
            finally:
                svc.detach()
        with pytest.raises(ValueError):
            WorldService().attach(w, VF, frame_scope="all")
    finally:
        w.close()


def test_continue_frame_is_excluded_and_served_facts_carry_the_view_frame(hosted):
    _, _, sess, _ = hosted
    assert "continue_frame" in VIEWER_EXCLUDED
    with pytest.raises(Refused):
        sess.call("continue_frame", source="person:a", into="person:b", evidence="x")
    assert {f["provenance"]["frame"] for f in sess.call("facts")} == {VF}


# --------------------------------------------------------------- (5) now


def test_viewer_writes_land_at_the_hosts_coordinate(hosted):
    w, svc, sess, _ = hosted
    assert sess.call("now") == {"now": 3.0}                 # no author: the valid head
    svc.set_now(12.5)
    assert sess.call("now") == {"now": 12.5}
    _resolve(svc, sess)
    placeholder_and_value = w.buffer.visible(entity="person:barmaid", attribute="wears",
                                             frame="canon")
    mirror = w.buffer.visible(entity="person:barmaid", attribute="wears", frame=VF)
    assert {r.valid_from for r in placeholder_and_value} == {12.5}
    assert [r.valid_from for r in mirror] == [12.5]


def test_set_view_frame_moves_the_viewpoint(hosted):
    w, svc, sess, _ = hosted
    assert sess.call("state", entity="person:barmaid", attribute="mood")["status"] == "unknown"
    svc.set_view_frame(OTHER)
    assert sess.call("state", entity="person:barmaid", attribute="mood")["status"] == "known"
    assert sess.call("state", entity="person:barmaid", attribute="gold")["status"] == "unknown"
    with pytest.raises(ValueError):
        svc.set_view_frame("")


# ---------------------------------------------------------- (4) record


def _standalone(tmp_path, model=None, name="r.world"):
    w = build_world(tmp_path, model=model or Recorder(), name=name)
    svc = WorldService(standalone=True, read_timeout=10)
    svc.attach(w, VF)
    return w, svc


def _record(svc, sess, items, at=None):
    t, box = run_async(sess.call, "record", items=items, **({"at": at} if at else {}))
    pump_until_done(svc, t)
    if "e" in box:
        raise box["e"]
    return box["r"]


def test_record_exists_only_on_the_standalone_runner(hosted):
    _, svc, sess, _ = hosted
    with pytest.raises(Refused):
        svc.session("holo", role="recorder")
    with pytest.raises(Refused):
        sess.call("record", items=[{"entity": "obj:x", "attribute": "kind", "value": "t"}])


def test_record_writes_observed_rows_to_canon_and_the_view_in_one_unit(tmp_path):
    w, svc = _standalone(tmp_path)
    sess = svc.session("holo", role="recorder")
    units = []
    real = w.buffer.atomic_unit
    w.buffer.atomic_unit = lambda body: (units.append(1), real(body))[1]
    try:
        head = w.buffer.head()
        out = _record(svc, sess, [{"entity": "person:mara", "attribute": "mood",
                                   "value": "angry"}], at=9.0)
        assert out == {"status": "recorded"} and len(units) == 1
        receipt = svc.last_record_outcome["receipt"]                 # the host's, not the wire's
        assert {row["frame"] for row in receipt["rows"]} == {"canon", VF}
        canon = w.buffer.visible(entity="person:mara", attribute="mood", frame="canon")
        view = w.buffer.visible(entity="person:mara", attribute="mood", frame=VF)
        assert [(r.status, r.valid_from, r.value) for r in canon] == [("observed", 9.0, "angry")]
        assert [(r.status, r.valid_from, r.value) for r in view] == [("observed", 9.0, "angry")]
        assert w.buffer.head() > head
        # a viewer reads it after the pump
        assert sess.call("state", entity="person:mara", attribute="mood")["fact"]["value"] \
            == "angry"
    finally:
        svc.detach()
        w.close()


@pytest.mark.parametrize("bad", [
    {"frame": "canon"}, {"frame": OTHER}, {"frame": VF}, {"frame": None},
    {"status": "stated"}, {"status": "generated"}, {"status": "observed"},
    {"aliases": ["Mar"]}, {"durability": "CONSTITUTIVE"}, {"confidence": 1.0},
    {"value_type": "unresolved"},
])
def test_record_refuses_item_keys_the_service_sets_itself_and_writes_nothing(tmp_path, bad):
    w, svc = _standalone(tmp_path)
    sess = svc.session("holo", role="recorder")
    try:
        head = w.buffer.head()
        good = {"entity": "person:mara", "attribute": "mood", "value": "angry"}
        out = sess.call("record", items=[good, {**good, "attribute": "tone", **bad}])
        assert out == {"status": "refused"}                 # the bare answer (S2 §5 r3)
        assert svc.last_record_outcome["status"] == "refused"
        assert w.buffer.head() == head                      # the whole call, nothing
    finally:
        svc.detach()
        w.close()


@pytest.mark.parametrize("item", [
    {"entity": "attr:wears", "attribute": "resolvable_for", "value": "person"},
    {"entity": "a:3", "attribute": "kind", "value": "x"},
    {"entity": "person:mara", "attribute": "same_as", "value": "person:barmaid",
     "value_type": "entity"},
    {"entity": "person:mara", "attribute": "retracts", "value": "a:1"},
])
def test_record_is_for_play_events_not_bookkeeping(tmp_path, item):
    w, svc = _standalone(tmp_path)
    sess = svc.session("holo", role="recorder")
    try:
        head = w.buffer.head()
        assert sess.call("record", items=[item]) == {"status": "refused"}
        assert svc.last_record_outcome["cause"] == "invalid"
        assert w.buffer.head() == head
    finally:
        svc.detach()
        w.close()


def test_record_is_all_or_none_when_the_gate_refuses_an_item(tmp_path):
    w, svc = _standalone(tmp_path)
    sess = svc.session("holo", role="recorder")
    try:
        head = w.buffer.head()
        out = _record(svc, sess, [
            {"entity": "person:mara", "attribute": "mood", "value": "angry"},
            {"entity": "person:mara", "attribute": "in", "value": 7, "value_type": "entity"},
        ])
        assert out == {"status": "refused"}
        assert svc.last_record_outcome["cause"] == "gate_skip"
        assert w.buffer.head() == head
    finally:
        svc.detach()
        w.close()


# -------------------------------------------- the runner and its HTTP surface


def _http(port, method, path, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, method=method,
        headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _generator(prompt, schema):
    """A code generator: answers from the request, never a model."""
    request = task_request(schema)
    assert request is not None
    return {"items": [{"value": f"generated {request.aspect}", "kind": "mug"}]}


@pytest.fixture
def runner(tmp_path):
    build_world(tmp_path, name="run.world").close()          # a world file to host
    model, route = make_runner_callable(_generator)
    r = Runner(lambda gated: World(tmp_path / "run.world", "w:svc", model=gated(model)), VF,
               port=0, recorders=("holo-emitter",), model_route=route).start()
    try:
        yield r
    finally:
        r.stop()


def test_the_runner_binds_loopback_only_and_serves_a_round_trip(runner):
    assert runner.httpd.server_address[0] == "127.0.0.1"
    port = runner.port
    # read
    code, body = _http(port, "POST", "/call", {
        "session": "holo-emitter", "verb": "state",
        "args": {"entity": "person:barmaid", "attribute": "gold"}})
    assert code == 200 and body["result"]["fact"]["value"] == 5
    # resolve (code route: the generator answers from the request)
    code, body = _http(port, "POST", "/call", {
        "session": "holo-emitter", "verb": "resolve",
        "args": {"entity": "person:barmaid", "aspect": "wears"}})
    assert code == 200 and body["result"]["status"] == "resolved"
    assert body["result"]["facts"][0]["value"] == "generated wears"
    # record, then read it back (the runner pumps on its own)
    code, body = _http(port, "POST", "/call", {
        "session": "holo-emitter", "verb": "record",
        "args": {"items": [{"entity": "person:mara", "attribute": "mood",
                            "value": "wary"}], "at": 4.5}})
    assert code == 200 and body["result"] == {"status": "recorded"}
    for _ in range(100):
        code, body = _http(port, "POST", "/call", {
            "session": "holo-emitter", "verb": "state",
            "args": {"entity": "person:mara", "attribute": "mood"}})
        if body["result"]["status"] == "known":
            break
        threading.Event().wait(0.05)
    assert body["result"]["fact"]["value"] == "wary"
    # /now
    code, body = _http(port, "GET", "/now")
    assert code == 200 and body["now"] == 4.5
    # the feed goes through POST /call; the old placeholder door is gone (S2)
    assert _http(port, "GET", "/changes?since=0")[0] == 404


def test_the_runner_refuses_frames_and_non_recorders_over_the_wire(runner):
    port = runner.port
    code, body = _http(port, "POST", "/call", {
        "session": "holo-emitter", "verb": "state",
        "args": {"entity": "person:barmaid", "attribute": "secret", "frame": "canon"}})
    assert code == 400 and body["error"]["type"] == "refused"
    code, body = _http(port, "POST", "/call", {
        "session": "renderer", "verb": "record",                # not a recorder
        "args": {"items": [{"entity": "person:mara", "attribute": "mood", "value": "x"}]}})
    assert code == 400 and body["error"]["type"] == "refused"
    code, body = _http(port, "POST", "/call", {
        "session": "holo-emitter", "verb": "record",
        "args": {"items": [{"entity": "person:mara", "attribute": "mood", "value": "x",
                            "frame": "canon"}]}})
    assert code == 200 and body == {"result": {"status": "refused"}}    # S2 §5 r3
    code, body = _http(port, "POST", "/call", {
        "session": "renderer", "verb": "resolve",
        "args": {"entity": "person:barmaid", "aspect": "wears", "frame": "canon"}})
    assert code == 400
    assert _http(port, "POST", "/call", {"session": "x"})[0] == 400       # bad shape
    assert _http(port, "GET", "/nope")[0] == 404


def test_the_runner_rejects_cross_origin_shaped_requests(runner):
    port = runner.port
    body = {"session": "x", "verb": "now", "args": {}}
    # not application/json (the only type a cross-origin page can send unpreflighted)
    code, _ = _http(port, "POST", "/call", body, headers={"Content-Type": "text/plain"})
    assert code == 415
    # a Host that is not loopback (DNS rebinding)
    code, _ = _http(port, "POST", "/call", body, headers={"Host": "evil.example"})
    assert code == 403
    code, _ = _http(port, "GET", "/now", headers={"Host": "evil.example:80"})
    assert code == 403


def test_without_a_generator_model_routed_resolves_answer_no_model(tmp_path):
    build_world(tmp_path, name="nm.world").close()
    model, route = make_runner_callable(None)
    r = Runner(lambda gated: World(tmp_path / "nm.world", "w:svc", model=gated(model)),
               VF, port=0,
               model_route=route).start()
    try:
        code, body = _http(r.port, "POST", "/call", {
            "session": "x", "verb": "resolve",
            "args": {"entity": "person:barmaid", "aspect": "wears"}})
        assert code == 200 and body["result"] == {"status": "no_model"}
        # reads still work
        code, body = _http(r.port, "POST", "/call", {
            "session": "x", "verb": "state",
            "args": {"entity": "person:barmaid", "attribute": "gold"}})
        assert body["result"]["status"] == "known"
    finally:
        r.stop()


def test_the_runner_callable_routes_resolve_to_code_and_everything_else_to_no_model():
    model, route = make_runner_callable(_generator)
    assert route({"title": TASK_RESOLVE}) == "code"
    assert route({"title": "classify"}) == "model"
    with pytest.raises(NoModel):
        model("p", {"title": "classify"})
    _, route_none = make_runner_callable(None)
    assert route_none({"title": TASK_RESOLVE}) == "model"


def test_concurrent_clients_do_not_corrupt_the_service(runner):
    port = runner.port
    results: list = []
    lock = threading.Lock()

    def client(i: int) -> None:
        for verb, args in (("state", {"entity": "person:mara", "attribute": "gold"}),
                           ("resolve", {"entity": "person:barmaid", "aspect": "wears"}),
                           ("entities", {})):
            code, body = _http(port, "POST", "/call",
                               {"session": f"c{i}", "verb": verb, "args": args})
            with lock:
                results.append((code, verb))

    threads = [threading.Thread(target=client, args=(i,), daemon=True) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
        assert not t.is_alive(), "a client hung"
    assert len(results) == 18 and all(code == 200 for code, _ in results)


# ---------------------------------------- r5.1: the opt-in loopback CORS grant

def _raw(port, method, path, headers):
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, body=None, headers=headers)
    resp = conn.getresponse()
    resp.read()
    conn.close()
    return resp.status, {k.lower(): v for k, v in resp.getheaders()}


def _granted_runner(tmp_path, loopback_origins):
    build_world(tmp_path, name="cors.world").close()
    model, route = make_runner_callable(_generator)
    return Runner(lambda gated: World(tmp_path / "cors.world", "w:svc", model=gated(model)), VF,
                  port=0, recorders=("holo-play",), model_route=route,
                  loopback_origins=loopback_origins).start()


PREFLIGHT = {"Access-Control-Request-Method": "POST",
             "Access-Control-Request-Headers": "content-type"}


def test_r5_1_a_loopback_page_is_granted_only_when_opted_in(tmp_path):
    r = _granted_runner(tmp_path, True)
    try:
        for origin in ("http://127.0.0.1:8798", "http://localhost:3000", "http://localhost"):
            code, hdrs = _raw(r.port, "OPTIONS", "/call", {"Origin": origin, **PREFLIGHT})
            assert code == 204
            assert hdrs["access-control-allow-origin"] == origin
            assert hdrs["access-control-allow-methods"] == "POST"
            assert hdrs["access-control-allow-headers"] == "Content-Type"
            assert "access-control-allow-credentials" not in hdrs
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", r.port, timeout=10)
        conn.request("POST", "/call", body=json.dumps(
            {"session": "holo-play", "verb": "state",
             "args": {"entity": "person:barmaid", "attribute": "gold"}}),
            headers={"Origin": "http://127.0.0.1:8798", "Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        assert resp.status == 200
        assert resp.getheader("Access-Control-Allow-Origin") == "http://127.0.0.1:8798"
        assert resp.getheader("Vary") == "Origin"
    finally:
        r.stop()


def test_r5_1_everything_else_is_refused(tmp_path):
    r = _granted_runner(tmp_path, True)
    try:
        for origin in ("https://127.0.0.1:8798", "http://evil.example", "http://127.0.0.2",
                       "http://localhost.evil.example", "null"):
            code, hdrs = _raw(r.port, "OPTIONS", "/call", {"Origin": origin, **PREFLIGHT})
            assert code == 403 and "access-control-allow-origin" not in hdrs
        good = {"Origin": "http://localhost:3000"}
        # pbr: a refused preflight, or a forged Host, carries no CORS header at all
        for headers in ({**good, "Access-Control-Request-Method": "PUT"},
                        {**good, **PREFLIGHT,
                         "Access-Control-Request-Headers": "content-type, authorization"},
                        {**good, **PREFLIGHT, "Host": "evil.example"}):
            code, hdrs = _raw(r.port, "OPTIONS", "/call", headers)
            assert code == 403
            assert "access-control-allow-origin" not in hdrs and "vary" not in hdrs
        code, hdrs = _raw(r.port, "POST", "/call", {**good, "Host": "evil.example",
                                                   "Content-Type": "application/json"})
        assert code == 403 and "access-control-allow-origin" not in hdrs
        assert _raw(r.port, "OPTIONS", "/now", {**good, **PREFLIGHT})[0] == 404
        code, hdrs = _raw(r.port, "GET", "/now", good)
        assert code == 200 and "access-control-allow-origin" not in hdrs
    finally:
        r.stop()


def test_r5_1_off_by_default(tmp_path):
    r = _granted_runner(tmp_path, False)
    try:
        code, hdrs = _raw(r.port, "OPTIONS", "/call",
                          {"Origin": "http://127.0.0.1:8798", **PREFLIGHT})
        assert code == 403 and "access-control-allow-origin" not in hdrs
    finally:
        r.stop()
