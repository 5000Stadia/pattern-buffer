"""WORLD-SERVICE-V1 §7: World.snapshot(), resolve(perceive_in=), verdict_version.

One test per engine check of specs/WORLD-SERVICE-V1.md (Checks 1a, 3 (the seam),
4a, 7), plus the engine-core boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading

import pytest

from patternbuffer import AtomicAbort, ReadOnlyWorld, World
from patternbuffer.codec import encode_out
from patternbuffer.model import TASK_RESOLVE

from service_fixture import SAMPLE_CALLS, VF, Recorder, build_world, sample_args


def _file_hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tables(conn: sqlite3.Connection, *names: str) -> dict[str, list]:
    return {n: conn.execute(f"SELECT * FROM {n} ORDER BY 1").fetchall() for n in names}


def _dump(r):
    return json.dumps(encode_out(r), sort_keys=True, default=str)


# ------------------------------------------------------------ the seal (1a)


def test_every_log_write_raises_read_only_world(tmp_path):
    w = build_world(tmp_path)
    snap = w.snapshot()
    head = snap.buffer.head()
    try:
        item = {"entity": "obj:x", "attribute": "kind", "value": "thing", "timeless": True}
        for write in (
            lambda: snap.buffer.append(entity="obj:x", attribute="kind", value="t",
                                       role=snap.ingestor._role, status="stated"),
            lambda: snap.ingest_structured([item]),
            lambda: snap.ingest_structured([]),        # the gate, even with nothing
            lambda: snap.ingest("text"),
            lambda: snap.commit_set([{"op": "assert", "item": item}]),
            lambda: snap.porcelain.ingest_structured([item]),
            lambda: snap.porcelain.commit_set([{"op": "assert", "item": item}]),
            lambda: snap.porcelain.retract("a:1", "no"),
            lambda: snap.truth.retract("a:1", "no"),
            lambda: snap.buffer.atomic_unit(lambda: 1),
        ):
            with pytest.raises(ReadOnlyWorld):
                write()
        # planting is an append: a resolve that would invent refuses too
        with pytest.raises(ReadOnlyWorld):
            snap.porcelain.resolve("person:barmaid", "wears")
        assert snap.buffer.head() == head
    finally:
        snap.close()
        w.close()


def test_derived_sidecars_stay_writable(tmp_path):
    w = build_world(tmp_path)
    snap = w.snapshot()
    try:
        before = _tables(snap.buffer.raw_connection(), "sidecar_salience")
        snap.salience("person:barmaid")           # writes its sidecar on read
        after = _tables(snap.buffer.raw_connection(), "sidecar_salience")
        assert len(after["sidecar_salience"]) == len(before["sidecar_salience"]) + 1
        row = snap.buffer.visible(entity="person:barmaid", attribute="gold")[0]
        snap.classifier.set(row.id, "STATE")      # a verdict, sidecar only
    finally:
        snap.close()
        w.close()


def test_the_copy_is_row_for_row_the_source_and_the_source_is_untouched(tmp_path):
    w = build_world(tmp_path)
    path = tmp_path / "w.world"
    observer = sqlite3.connect(path)               # sees the file's data_version
    observer.execute("SELECT 1 FROM assertions LIMIT 1").fetchall()
    dv_observer = observer.execute("PRAGMA data_version").fetchone()[0]
    dv_source = w.buffer._read_data_version()
    digest = _file_hash(path)
    src_tables = _tables(w.buffer.raw_connection(), "assertions", "world_meta")

    snap = w.snapshot()
    try:
        # construction + first reads, salience included (it writes its sidecar)
        for verb in SAMPLE_CALLS:
            getattr(snap.porcelain, verb)(**sample_args(verb))
        snap.porcelain.salience("person:mara")
        copy_tables = _tables(snap.buffer.raw_connection(), "assertions", "world_meta")
        assert copy_tables == src_tables
        # the source: file bytes, data_version (own and a separate observer's)
        assert _file_hash(path) == digest
        assert w.buffer._read_data_version() == dv_source
        assert observer.execute("PRAGMA data_version").fetchone()[0] == dv_observer
        # the source still works: SecondWriter never tripped
        assert w.porcelain.state("person:mara", "gold")["status"] == "known"
        w.ingest_structured([{"entity": "person:mara", "attribute": "gold", "value": 4,
                              "valid_from": 5.0}], classify="rules")
        assert snap.buffer.head() == w.buffer.head() - 1   # the copy stays at backup time
    finally:
        snap.close()
        observer.close()
        w.close()


def test_snapshot_refused_inside_an_open_unit(tmp_path):
    w = build_world(tmp_path)
    try:
        with pytest.raises(RuntimeError, match="atomic unit"):
            w.buffer.atomic_unit(lambda: w.snapshot())
    finally:
        w.close()


@pytest.mark.parametrize("verb", sorted(SAMPLE_CALLS))
def test_snapshot_answers_every_viewer_read_like_its_source(tmp_path, verb):
    w = build_world(tmp_path)
    snap = w.snapshot()
    try:
        args = sample_args(verb)
        assert _dump(getattr(snap.porcelain, verb)(**args)) == \
            _dump(getattr(w.porcelain, verb)(**args))
    finally:
        snap.close()
        w.close()


def test_the_copy_is_usable_from_another_thread(tmp_path):
    w = build_world(tmp_path)
    snap = w.snapshot()
    box = {}

    def read() -> None:
        try:
            box["r"] = snap.porcelain.state("person:mara", "gold", frame=VF)
        except BaseException as exc:    # noqa: BLE001
            box["e"] = exc

    try:
        t = threading.Thread(target=read, daemon=True)
        t.start()
        t.join(10)
        assert not t.is_alive() and "e" not in box and box["r"]["status"] == "known"
    finally:
        snap.close()
        w.close()


# --------------------------------------------------------- verdict_version (7c)


def test_verdict_version_moves_at_each_verdict_write_and_is_never_stored(tmp_path):
    w = build_world(tmp_path)
    try:
        c = w.classifier
        v0 = c.verdict_version
        row = w.buffer.visible(entity="person:mara", attribute="gold", frame=VF)[0]
        c.set(row.id, "STATE")
        assert c.verdict_version == v0 + 1
        c.classify(row)
        assert c.verdict_version == v0 + 2
        w.buffer.raw_connection().execute("SELECT 1").fetchall()
        assert c.verdict_version == v0 + 2                 # a read moves nothing
        c.rebuild()
        assert c.verdict_version > v0 + 2
        # not stored: no sidecar column or key carries it
        keys = [r[0] for r in w.buffer.raw_connection().execute(
            "SELECT key FROM sidecar_classifier_meta").fetchall()]
        assert keys == ["version"]
    finally:
        w.close()
    reopened = World(tmp_path / "w.world", "w:svc")
    try:
        assert reopened.classifier.verdict_version == 0    # a reopen starts again
    finally:
        reopened.close()


# --------------------------------------------------- the resolve seam (7b)


def _declared_world(tmp_path, **kw):
    return build_world(tmp_path, **kw)


def test_perceive_in_runs_plant_force_and_mirror_in_one_unit(tmp_path):
    model = Recorder()
    w = _declared_world(tmp_path, model=model)
    calls = []
    real = w.buffer.atomic_unit
    w.buffer.atomic_unit = lambda body: (calls.append(1), real(body))[1]
    try:
        out = w.porcelain.resolve("person:barmaid", "wears", at=5.0, perceive_in=VF)
        assert len(calls) == 1                             # ONE unit, not two
        assert out["planted"] is True and out["status"] == "resolved"
        canon = w.buffer.visible(entity="person:barmaid", attribute="wears", frame="canon")
        assert [r.status for r in canon] == ["generated", "generated"]   # placeholder + value
        view = w.buffer.visible(entity="person:barmaid", attribute="wears", frame=VF)
        assert [(r.status, r.value, r.valid_from) for r in view] == \
            [("observed", "a red wool kirtle", 5.0)]
        assert out["perceived"]["frame"] == VF
        assert [f["provenance"]["status"] for f in out["perceived"]["facts"]] == ["observed"]
    finally:
        w.close()


def test_a_memoized_perceived_resolve_mirrors_only_what_the_frame_lacks(tmp_path):
    model = Recorder()
    w = _declared_world(tmp_path, model=model)
    try:
        first = w.porcelain.resolve("person:barmaid", "wears", at=5.0, perceive_in=VF)
        head, calls = w.buffer.head(), len(model.resolves)
        again = w.porcelain.resolve("person:barmaid", "wears", at=6.0, perceive_in=VF)
        assert w.buffer.head() == head and len(model.resolves) == calls
        assert again["perceived"]["facts"] == first["perceived"]["facts"]
        # a frame that holds none of it gets the whole mirror, once
        other = w.porcelain.resolve("person:barmaid", "wears", at=6.0,
                                    perceive_in="knows:person:stranger")
        assert len(other["perceived"]["facts"]) == 1 and w.buffer.head() == head + 1
        assert w.buffer.head() == head + 1
        w.porcelain.resolve("person:barmaid", "wears", at=6.0,
                            perceive_in="knows:person:stranger")
        assert w.buffer.head() == head + 1
    finally:
        w.close()


def test_contents_are_mirrored_with_their_kind_and_name(tmp_path):
    w = _declared_world(tmp_path)
    try:
        out = w.porcelain.resolve("place:attic", "contents", at=2.0, perceive_in=VF)
        assert out["status"] == "resolved"
        names = {(f["entity"], f["attribute"]) for f in out["perceived"]["facts"]}
        minted = {e for e, a in names if a == "in"}
        assert len(minted) == 1
        eid = minted.pop()
        assert {(eid, "kind"), (eid, "name"), (eid, "in")} <= names
        # the view frame can name what it perceives
        assert w.porcelain.state(eid, "name", frame=VF)["fact"]["value"] == "a red wool kirtle"
        assert w.contents("place:attic", frame=VF) == [eid]
    finally:
        w.close()


def test_a_mirror_refused_at_the_gate_rolls_back_plant_force_and_mirror(tmp_path):
    model = Recorder()
    w = _declared_world(tmp_path, model=model)
    head = w.buffer.head()
    cursor = w.ingestor.cursor.position
    try:
        # a non-finite time passes the buffer's direct appends (plant, force) but
        # is refused by the gate that writes the mirror
        with pytest.raises(AtomicAbort) as caught:
            w.porcelain.resolve("person:barmaid", "wears", at=float("inf"), perceive_in=VF)
        assert caught.value.cause == "gate_skip"
        assert len(model.resolves) == 1                    # the force did run ...
        assert w.buffer.head() == head                     # ... and left nothing
        assert w.buffer.visible(entity="person:barmaid", attribute="wears") == []
        assert w.ingestor.cursor.position == cursor        # the pose is restored
        # and the world is healthy afterwards
        ok = w.porcelain.resolve("person:barmaid", "wears", at=5.0, perceive_in=VF)
        assert ok["status"] == "resolved" and not w.buffer.poisoned
    finally:
        w.close()


def test_a_model_failure_on_the_perceived_path_stays_a_model_failure(tmp_path):
    w = _declared_world(tmp_path, model=Recorder(fail=True))
    head = w.buffer.head()
    try:
        with pytest.raises(RuntimeError, match="went away"):
            w.porcelain.resolve("person:barmaid", "wears", perceive_in=VF)
        assert w.buffer.head() == head
    finally:
        w.close()


def test_perceive_in_must_name_another_frame(tmp_path):
    w = _declared_world(tmp_path)
    try:
        for bad in ("", "canon"):
            with pytest.raises(ValueError):
                w.porcelain.resolve("person:barmaid", "wears", perceive_in=bad)
    finally:
        w.close()


def test_world_resolve_accepts_perceive_in_and_at(tmp_path):
    w = _declared_world(tmp_path)
    try:
        rows = w.resolve("person:barmaid", "wears", at=4.0, perceive_in=VF)
        assert [r.value for r in rows] == ["a red wool kirtle"]
        assert w.buffer.visible(entity="person:barmaid", attribute="wears",
                                frame=VF)[0].valid_from == 4.0
    finally:
        w.close()


def test_without_perceive_in_behavior_is_e1s_including_the_nested_refusal(tmp_path):
    w = _declared_world(tmp_path)
    try:
        # (4a) a nested atomic_unit is still refused, as ever ...
        with pytest.raises(RuntimeError, match="nested atomic unit"):
            w.buffer.atomic_unit(lambda: w.buffer.atomic_unit(lambda: 1))
        # ... including the resolver's own plant-and-force inside a caller's unit
        head = w.buffer.head()
        with pytest.raises(RuntimeError, match="nested atomic unit"):
            w.buffer.atomic_unit(lambda: w.resolve("person:barmaid", "wears"))
        assert w.buffer.head() == head
        # the explicit flag is unusable outside a unit
        with pytest.raises(RuntimeError, match="open unit"):
            w.resolver.resolve_planted("person:barmaid", "wears", "canon", joined=True)
        # the plain path plants, forces and writes no mirror
        out = w.porcelain.resolve("person:barmaid", "wears")
        assert out["planted"] is True and "perceived" not in out
        assert w.buffer.visible(entity="person:barmaid", attribute="wears", frame=VF) == []
    finally:
        w.close()


# --------------------------------------------------------- the boundary (7)


def test_the_engine_core_never_imports_the_service():
    src = os.path.join(os.path.dirname(__file__), "..", "src")
    code = ("import sys, patternbuffer; from patternbuffer import World; "
            "assert 'patternbuffer.service' not in sys.modules; "
            "assert 'patternbuffer.mcp' not in sys.modules")
    done = subprocess.run([sys.executable, "-c", code], timeout=60,
                          env={**os.environ, "PYTHONPATH": src},
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_resolve_task_schema_is_unchanged_by_the_seam(tmp_path):
    model = Recorder()
    w = _declared_world(tmp_path, model=model)
    try:
        w.porcelain.resolve("person:barmaid", "wears", perceive_in=VF)
        assert model.resolves[0][1]["title"] == TASK_RESOLVE
    finally:
        w.close()
