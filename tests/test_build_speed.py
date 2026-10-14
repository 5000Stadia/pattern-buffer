"""BUILD-SPEED-V1: classification batches in parallel (opt-in) and the harness options.

Every test is the spec's Tests section (numbers in the test names) or a detail
it fixes. Only stub models are used; no model is called.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "evals" / "harness"))
sys.path.insert(0, str(Path(__file__).parent))

from patternbuffer import World, build as b
from patternbuffer.classify import CONSTITUTIVE, DISPOSITIONAL, STATE, Classifier

import run_book as rb
import test_book_run as tb
import usage_ledger
from test_build_library import TOY_CATEGORIES, TOY_EXTRACT, FakeModel

CLASSES = (CONSTITUTIVE, DISPOSITIONAL, STATE)
FACT = re.compile(r"^\d+\. (.+?) · (a\d+) · ", re.M)


def verdict_for(k: int) -> tuple[str, float]:
    """The stub's fixed verdict for the row whose attribute is ``a<k>``: some
    CONSTITUTIVE ones fall below the review floor."""
    return CLASSES[k % 3], 0.4 + (k % 6) / 10


class BatchStub:
    """A thread-safe batch classifier with fixed verdicts keyed by attribute.
    ``fail_on`` names an attribute whose batch raises; ``barrier`` is waited on
    inside each call (a broken barrier is recorded, then re-raised)."""

    def __init__(self, *, fail_on: str | None = None,
                 barrier: threading.Barrier | None = None,
                 var: contextvars.ContextVar | None = None) -> None:
        self.fail_on, self.barrier, self.var = fail_on, barrier, var
        self.calls = 0
        self.threads: list[int] = []
        self.seen_var: list[object] = []
        self.broken = 0
        self._lock = threading.Lock()

    def __call__(self, prompt: str, schema: dict) -> dict:
        assert "verdicts" in schema["properties"], "only batch calls expected"
        with self._lock:
            self.calls += 1
            self.threads.append(threading.get_ident())
            if self.var is not None:
                self.seen_var.append(self.var.get(None))
        if self.barrier is not None:
            try:
                self.barrier.wait()
            except threading.BrokenBarrierError:
                with self._lock:
                    self.broken += 1
                raise
        facts = FACT.findall(prompt)
        if self.fail_on is not None and any(a == self.fail_on for _, a in facts):
            raise RuntimeError("stub failure")
        out = []
        for i, (_, attr) in enumerate(facts):
            durability, confidence = verdict_for(int(attr[1:]))
            out.append({"index": i, "durability": durability, "class_confidence": confidence})
        return {"verdicts": out}


def make_world(tmp_path: Path, model, name: str = "w", rows: int = 20) -> World:
    """A world with ``rows`` model-needing rows ``a0``..., plus a ``name`` row
    a guardrail resolves, none of them classified yet (``rows + 1`` pending)."""
    w = World(tmp_path / f"{name}.world", world_id="w:speed", model=model)
    w.ingestor.classify_inline = False
    items = [{"entity": f"thing:t{k}", "attribute": f"a{k}", "value": f"v{k}",
              "valid_from": 1.0} for k in range(rows)]
    items.append({"entity": "thing:t0", "attribute": "name", "value": "Tee", "valid_from": 1.0})
    w.ingest_structured(items)
    # ingest classified the guardrail row inline; unclassify it so the guardrail
    # pass has something to store (rebuildable sidecar, test setup only)
    conn = w.buffer.raw_connection()
    gid = next(r.id for r in w.buffer.all_rows() if r.attribute == "name")
    conn.execute("DELETE FROM sidecar_classification WHERE assertion_id = ?", (gid,))
    conn.commit()
    return w


def sidecar_dump(w: World) -> list[tuple]:
    """The sidecar keyed by what the row says (ids are not comparable across worlds)."""
    out = []
    for r in w.buffer.all_rows():
        c = w.classifier.get(r.id)
        out.append((r.entity, r.attribute, json.dumps(r.value),
                    None if c is None else (c.durability, c.class_confidence, c.needs_review)))
    return sorted(out, key=repr)


def sidecar_state(w: World) -> tuple:
    conn = w.buffer.raw_connection()
    return (conn.execute("SELECT * FROM sidecar_classification ORDER BY assertion_id").fetchall(),
            conn.execute("SELECT * FROM sidecar_classifier_meta").fetchall())


@pytest.fixture
def worlds(tmp_path):
    opened: list[World] = []

    def make(model, name="w", rows=20):
        w = make_world(tmp_path, model, name, rows)
        opened.append(w)
        return w

    yield make
    for w in opened:
        w.close()


# ----------------------------------------------------------- 1. same results


def test_1_parallel_stores_exactly_the_serial_classes(worlds):
    serial, parallel = BatchStub(), BatchStub()
    ws, wp = worlds(serial, "s"), worlds(parallel, "p")
    assert ws.classifier.classify_all(batch_size=3, workers=1) == 21
    assert wp.classifier.classify_all(batch_size=3, workers=4) == 21
    assert serial.calls == parallel.calls == 7
    assert sidecar_dump(ws) == sidecar_dump(wp)
    assert all(row[-1] is not None for row in sidecar_dump(wp))
    assert any(row[-1][2] for row in sidecar_dump(wp)), "some rows need review"
    assert set(parallel.threads) - {threading.get_ident()}, "calls ran in workers"


def test_1_classify_rows_is_the_same_core(worlds):
    ws, wp = worlds(BatchStub(), "s"), worlds(BatchStub(), "p")
    ws.classifier.classify_rows(ws.buffer.all_rows(), 4)
    wp.classifier.classify_rows(wp.buffer.all_rows(), 4, workers=3)
    assert sidecar_dump(ws) == sidecar_dump(wp)


# ------------------------------------------------------- 2. really parallel


def test_2_four_calls_meet_at_a_barrier_with_four_workers(worlds):
    barrier = threading.Barrier(4, timeout=20)
    stub = BatchStub(barrier=barrier)
    w = worlds(stub, rows=8)
    w.classifier.classify_all(batch_size=2, workers=4)        # 4 batches, all meet
    assert (stub.calls, stub.broken) == (4, 0)
    assert len(set(stub.threads)) == 4


def test_2_the_same_barrier_times_out_serially(worlds):
    barrier = threading.Barrier(4, timeout=0.3)
    stub = BatchStub(barrier=barrier)
    w = worlds(stub, rows=8)
    w.classifier.classify_all(batch_size=2, workers=1)
    assert stub.broken == 4                                    # no call ever met another
    assert {t for t in stub.threads} == {threading.get_ident()}


# ------------------------------------------------------ 3. failure isolation


def test_3_a_raising_call_defaults_only_its_batch(worlds, caplog):
    # 10 deferred rows in batches of 2: batch index 1 (rows a2, a3) raises
    ws = worlds(BatchStub(fail_on="a2"), "s", rows=10)
    wp = worlds(BatchStub(fail_on="a2"), "p", rows=10)
    with caplog.at_level(logging.ERROR, logger="patternbuffer.classify"):
        ws.classifier.classify_all(batch_size=2, workers=1)
        serial_logs = [r.getMessage() for r in caplog.records]
        caplog.clear()
        wp.classifier.classify_all(batch_size=2, workers=4)
        parallel_logs = [r.getMessage() for r in caplog.records]
    assert sidecar_dump(ws) == sidecar_dump(wp)
    assert serial_logs == parallel_logs == ["batch classification failed; defaulting batch"]
    assert all(r.exc_info for r in caplog.records)
    by_attr = {a: c for _, a, _, c in sidecar_dump(wp)}
    for k in (2, 3):
        assert by_attr[f"a{k}"] == (STATE, 0.5, False)
    for k in (0, 1, 4, 5, 6, 7, 8, 9):
        durability, confidence = verdict_for(k)
        assert by_attr[f"a{k}"] == (durability, confidence,
                                    durability == CONSTITUTIVE and confidence < 0.6)


# ----------------------------------------------- 4. stores on the owner thread


def test_4_every_store_is_on_the_calling_thread(worlds, monkeypatch):
    stub = BatchStub()
    w = worlds(stub)
    stores: list[tuple[int, str]] = []
    original = Classifier._store

    def recording(self, c):
        stores.append((threading.get_ident(), c.assertion_id))
        return original(self, c)

    monkeypatch.setattr(Classifier, "_store", recording)
    w.classifier.classify_all(batch_size=3, workers=4)
    assert len(stores) == 21
    assert {t for t, _ in stores} == {threading.get_ident()}
    assert set(stub.threads) - {threading.get_ident()}


def test_4_stores_follow_batch_order_after_all_calls_return(worlds, monkeypatch):
    events: list[str] = []
    stub = BatchStub()

    def late_first(prompt, schema):                 # batch 0 returns last
        if "· a0 ·" in prompt:
            while events.count("call-done") < 3:
                threading.Event().wait(0.005)
        out = stub(prompt, schema)
        events.append("call-done")
        return out

    w = worlds(late_first, rows=8)
    attr_of = {r.id: r.attribute for r in w.buffer.all_rows()}
    original = Classifier._store

    def recording(self, c):
        events.append(f"store:{attr_of[c.assertion_id]}")
        return original(self, c)

    monkeypatch.setattr(Classifier, "_store", recording)
    w.classifier.classify_all(batch_size=2, workers=4)
    model_stores = [e for e in events if e.startswith("store:a")]
    assert model_stores == [f"store:a{k}" for k in range(8)]     # batch order, row order
    last_call = max(i for i, e in enumerate(events) if e == "call-done")
    assert events.index(model_stores[0]) > last_call              # stores only after all calls


# ---------------------------------------------------------------- 5. context


def test_5_a_context_variable_is_visible_in_every_worker_call(worlds):
    var: contextvars.ContextVar = contextvars.ContextVar("speed_label")
    barrier = threading.Barrier(4, timeout=20)
    stub = BatchStub(barrier=barrier, var=var)
    w = worlds(stub, rows=8)
    token = var.set({"stage": "commit"})
    try:
        w.classifier.classify_all(batch_size=2, workers=4)
    finally:
        var.reset(token)
    assert stub.seen_var == [{"stage": "commit"}] * 4
    assert len(set(stub.threads)) == 4 and threading.get_ident() not in stub.threads


# ----------------------------------------------------------------- 6. bounds


BAD_WORKERS = [0, -1, True, 1.5, "2"]
BAD_BATCH = [None, 0, -3, True, 2.0, "40"]


@pytest.mark.parametrize("workers", BAD_WORKERS)
def test_6_bad_workers_raise_before_any_work(worlds, workers):
    stub = BatchStub()
    w = worlds(stub)
    before = sidecar_state(w)
    for call in (lambda: w.classifier.classify_all(batch_size=3, workers=workers),
                 lambda: w.classifier.classify_all(workers=workers),
                 lambda: w.classifier.classify_rows(w.buffer.all_rows(), 3, workers=workers)):
        with pytest.raises(ValueError):
            call()
    assert stub.calls == 0 and sidecar_state(w) == before


@pytest.mark.parametrize("batch_size", BAD_BATCH)
def test_6_bad_batch_size_with_workers_raises_before_any_work(worlds, batch_size):
    stub = BatchStub()
    w = worlds(stub)
    before = sidecar_state(w)                        # a guardrail row would store if reached
    with pytest.raises(ValueError):
        w.classifier.classify_all(batch_size=batch_size, workers=2)
    with pytest.raises(ValueError):
        w.classifier.classify_rows(w.buffer.all_rows(), batch_size, workers=2)
    assert stub.calls == 0 and sidecar_state(w) == before


def test_6_workers_one_keeps_todays_batch_size_handling(worlds):
    def run(batch_size, via_all=True):
        stub = BatchStub()
        w = worlds(stub, f"w{batch_size}{via_all}")
        if via_all:
            n = w.classifier.classify_all(batch_size, workers=1)
        else:
            n = w.classifier.classify_rows(w.buffer.all_rows(), batch_size, workers=1)
        return stub.calls, n, sum(1 for r in sidecar_dump(w) if r[-1] is not None)

    assert run(None, via_all=False) == (1, 21, 24)       # one batch for everything
    assert run(0, via_all=False) == (1, 21, 24)
    assert run(7, via_all=False) == (3, 21, 24)
    assert run(3) == (7, 21, 24)
    # classify_all with no batch_size classifies row by row (per-row schema, not the batch stub)
    per_row = []

    def row_model(prompt, schema):
        per_row.append(schema["title"])
        return {"durability": STATE, "class_confidence": 0.7}

    w = worlds(row_model, "perrow")
    assert w.classifier.classify_all() == 21 and len(per_row) == 20
    # a negative step has always skipped the model-needing rows; pinned, not endorsed
    stub = BatchStub()
    w = worlds(stub, "neg")
    assert w.classifier.classify_rows(w.buffer.all_rows(), -3, workers=1) == 21
    assert stub.calls == 0


# ---------------------------------------------------------------- 7. harness


def test_7_defaults_reproduce_todays_argv_and_calls():
    args = rb.parse_args(["--book", "x", "--out", "y"])
    assert (args.max_words, args.classify_workers, args.extract_workers) == (1500, 1, 4)
    assert args.max_words == rb.LIBRARY_MAX_WORDS
    args = rb.parse_args(["--book", "x", "--out", "y", "--max-words", "750",
                          "--classify-workers", "4", "--extract-workers", "8"])
    assert (args.max_words, args.classify_workers, args.extract_workers) == (750, 4, 8)


@pytest.mark.parametrize("flags", [["--max-words", "99"], ["--max-words", "x"],
                                   ["--classify-workers", "0"], ["--extract-workers", "0"]])
def test_7_bad_options_are_refused_by_the_parser(flags):
    with pytest.raises(SystemExit):
        rb.parse_args(["--book", "x", "--out", "y", *flags])


@pytest.fixture
def spies(monkeypatch):
    seen: dict = {}
    real_plan, real_extract = b.plan, b.extract
    real_classify = Classifier.classify_all

    def plan(*a, **kw):
        seen["plan"] = kw
        return real_plan(*a, **kw)

    def extract(*a, **kw):
        seen["extract"] = kw
        return real_extract(*a, **kw)

    def classify_all(self, *a, **kw):
        seen["classify_all"] = (a, kw)
        return real_classify(self, *a, **kw)

    monkeypatch.setattr(b, "plan", plan)
    monkeypatch.setattr(b, "extract", extract)
    monkeypatch.setattr(Classifier, "classify_all", classify_all)
    monkeypatch.delenv(rb.USAGE_ENV, raising=False)
    usage_ledger.reset()
    yield seen
    usage_ledger.reset()


def library_run(tmp_path, *flags):
    book, out = tb.write_book(tmp_path / "toybook"), tmp_path / "out"
    model = FakeModel(chunks=TOY_EXTRACT, categories=TOY_CATEGORIES)
    assert rb.main(["--book", str(book), "--out", str(out), "--pipeline", "library", *flags],
                   model=model) == 0
    return json.loads((out / "meta.json").read_text())


def test_7_the_options_reach_their_calls(tmp_path, spies):
    meta = library_run(tmp_path, "--max-words", "750", "--classify-workers", "4",
                       "--extract-workers", "8")
    assert spies["plan"] == {"max_words": 750}
    assert spies["extract"] == {"workers": 8}
    assert spies["classify_all"] == ((), {"batch_size": 40, "workers": 4})
    assert meta["max_words"] == 750


def test_7_the_defaults_reach_the_same_calls_as_before(tmp_path, spies):
    meta = library_run(tmp_path)
    assert spies["plan"] == {"max_words": 1500}
    assert spies["extract"] == {"workers": 4}
    assert spies["classify_all"] == ((), {"batch_size": 40, "workers": 1})
    assert meta["max_words"] == 1500


def test_7_run_book_refuses_bad_values_before_any_call(tmp_path):
    book = tb.write_book(tmp_path / "toybook")
    model = FakeModel(chunks=TOY_EXTRACT, categories=TOY_CATEGORIES)
    for kw in ({"max_words": 99}, {"max_words": True}, {"classify_workers": 0},
               {"extract_workers": 1.5}):
        with pytest.raises(rb.BookRefused):
            rb.run_book(book, tmp_path / "o", model, pipeline="library", **kw)
    with pytest.raises(rb.BookRefused, match="--pipeline library options"):
        rb.run_book(book, tmp_path / "o", model, max_words=750)
    assert model.prompts == [] and not (tmp_path / "o").exists()
