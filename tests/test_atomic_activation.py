"""ATOMIC-ACTIVATION-V1 acceptance oracles (spec §Oracles).

All-or-none visibility for a multi-row set: the buffer's unit-of-work behind a
deny-by-default capability facade + a provenance-gated SQLite authorizer, the
`atomic=True` sugar, the typed `commit_set` door, the snapshot/restore abort, the
shared-path retract validation, and the frozen `AtomicAbort` failure contract.
"""

import sqlite3
import sys

import pytest

from patternbuffer import AtomicAbort, World
from patternbuffer.buffer import PoisonedConnection
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "a.world", world_id="w:a", model=stub, stance="fiction")
    w._stub = stub
    yield w
    if not w.buffer.poisoned:
        w.close()


@pytest.fixture
def mkworld(tmp_path):
    """A factory for fresh, independently-seeded worlds (fault-matrix sweeps
    need a clean world per injected boundary)."""
    made = []

    def make(tag):
        stub = StubModel(fallback=rule_classifier_fallback())
        w = World(tmp_path / f"{tag}.world", world_id=f"w:{tag}", model=stub,
                  stance="fiction")
        _seed(w)
        made.append(w)
        return w

    yield make
    for w in made:
        if not w.buffer.poisoned:
            w.close()


def _seed(w):
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:old", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "person:mara", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "obj:desk", "attribute": "kind", "value": "desk", "timeless": True},
        {"entity": "obj:desk", "attribute": "in", "value": "place:old",
         "value_type": "entity", "timeless": True},
    ])


def _second_conn_new_rows(w, head0):
    """Rows a fresh SQLite connection can see above head0 (cross-conn isolation)."""
    c2 = sqlite3.connect(w.buffer.path)
    try:
        return c2.execute("SELECT COUNT(*) FROM assertions WHERE seq > ?",
                          (head0,)).fetchone()[0]
    finally:
        c2.close()


# --------------------------------------------------------------- 1 fault matrix

_MATRIX_ITEMS = [
    # `located_in` canonicalizes → a `canonicalized_from` receipt meta-row rides
    # the unit too, so the sweep injects at meta-row boundaries, not just data.
    {"entity": "person:mara", "attribute": "located_in", "value": "place:hall",
     "value_type": "entity", "valid_from": 5.0},
    {"entity": "person:mara", "attribute": "mood", "value": "wary", "valid_from": 5.0},
    {"entity": "person:mara", "attribute": "carrying", "value": "a lamp", "valid_from": 5.0},
]


def test_oracle1_fault_at_every_physical_boundary_rolls_back(mkworld):
    # how many physical inserts does the unfaulted set make?
    counter = mkworld("count")
    n = {"c": 0}
    real = counter.buffer._insert
    counter.buffer._insert = lambda r: (n.__setitem__("c", n["c"] + 1), real(r))[1]
    head_count = counter.buffer.head()
    counter.ingest_structured(_MATRIX_ITEMS, classify="rules", atomic=True)
    total_inserts = n["c"]
    assert total_inserts >= 4                          # data rows + ≥1 meta-row
    # inject a fault at EACH physical insert boundary k, fresh world each time
    for k in range(1, total_inserts + 1):
        w = mkworld(f"fault{k}")
        head0 = w.buffer.head()
        pre = w.buffer.all_rows()
        real_insert = w.buffer._insert
        seen = {"c": 0, "iso": None}

        def faulting(row, _k=k, _s=seen, _ri=real_insert, _w=w, _h=head0):
            _s["c"] += 1
            if _s["c"] == _k:
                _s["iso"] = _second_conn_new_rows(_w, _h) == 0
                raise RuntimeError(f"fault at insert {_k}")
            return _ri(row)

        w.buffer._insert = faulting
        with pytest.raises(AtomicAbort) as ei:
            w.ingest_structured(_MATRIX_ITEMS, classify="rules", atomic=True)
        w.buffer._insert = real_insert
        assert seen["iso"] is True                     # nothing visible mid-unit
        assert ei.value.cause == "exception"
        assert w.buffer.head() == head0
        assert w.buffer.all_rows() == pre
        assert _second_conn_new_rows(w, head0) == 0
    # the unfaulted run commits whole, contiguous seq
    w = mkworld("clean")
    rows = w.ingest_structured(_MATRIX_ITEMS, classify="rules", atomic=True)
    committed = {(r.entity, r.attribute) for r in rows}
    assert {("person:mara", "in"), ("person:mara", "mood"),
            ("person:mara", "carrying")} <= committed          # all authored facts
    seqs = [r.seq for r in w.buffer.all_rows()]
    assert seqs == list(range(1, len(seqs) + 1))               # contiguous, no gaps


def test_oracle1_salience_ensure_schema_path_during_unit(world):
    w = world
    _seed(w)
    head0 = w.buffer.head()
    probe = {"ddl_error": None, "isolation_ok": None}

    def body():
        w.buffer.append(entity="obj:desk", attribute="state", value="x",
                        role=w.ingestor._role, status="stated", valid_from=5.0)
        # force the salience read path (was executescript-on-every-read) inside
        # the open unit — must be DDL-free (create-once) and stay isolated
        try:
            w.salience_index.salience("obj:desk")
        except RuntimeError as e:
            probe["ddl_error"] = str(e)
        probe["isolation_ok"] = _second_conn_new_rows(w, head0) == 0
        raise RuntimeError("abort to prove rollback removes the staged prefix")

    with pytest.raises(AtomicAbort):
        w.ingestor._run_atomic(body)
    assert probe["ddl_error"] is None            # no DDL attempted mid-unit
    assert probe["isolation_ok"] is True
    assert w.buffer.head() == head0
    assert _second_conn_new_rows(w, head0) == 0


# --------------------------------------------------------------- 2 skip aborts

def test_oracle2_one_skip_aborts_whole_set(world):
    w = world
    _seed(w)
    head0 = w.buffer.head()
    good = {"entity": "obj:desk", "attribute": "state", "value": "clean", "valid_from": 5.0}
    bad = {"entity": "person:/bad", "attribute": "in", "value": "place:hall",
           "value_type": "entity", "valid_from": 5.0}
    with pytest.raises(AtomicAbort) as ei:
        w.ingest_structured([good, bad], classify="rules", atomic=True)
    assert ei.value.cause == "gate_skip"
    assert ei.value.error is None
    assert [s["reason"] for s in ei.value.skipped] == ["malformed_id"]
    assert w.buffer.head() == head0
    # the same set minus the bad edge commits whole
    rows = w.ingest_structured([good], classify="rules", atomic=True)
    assert len(rows) == 1


# --------------------------------------------------------------- 3 G3 mixed set

def test_oracle3_g3_ancestry_insertion_mixed_set(world):
    w = world
    _seed(w)
    old_edge = next(r for r in w.buffer.all_rows()
                    if r.entity == "obj:desk" and r.attribute == "in")
    assert w.locate("obj:desk") == ["place:old"]
    w.commit_set([
        {"op": "retract", "assertion_id": old_edge.id, "reason": "region inserted"},
        {"op": "assert", "item": {"entity": "place:region", "attribute": "kind",
                                  "value": "region", "timeless": True}},
        {"op": "assert", "item": {"entity": "place:region", "attribute": "in",
                                  "value": "place:old", "value_type": "entity",
                                  "timeless": True}},
        {"op": "assert", "item": {"entity": "obj:desk", "attribute": "in",
                                  "value": "place:region", "value_type": "entity",
                                  "timeless": True}},
    ], classify="rules")
    assert w.locate("obj:desk") == ["place:region", "place:old"]
    assert w.locate("place:region") == ["place:old"]


def test_oracle3_bare_append_negative_fixture(tmp_path):
    # the pbr probe captured as the negative: a bare append (no retract) leaves
    # locate(desk) at the OLD parent — constitutive containment does not supersede
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "neg.world", world_id="w:neg", model=stub, stance="fiction")
    _seed(w)
    w.ingest_structured([
        {"entity": "place:region", "attribute": "kind", "value": "region", "timeless": True},
        {"entity": "obj:desk", "attribute": "in", "value": "place:region",
         "value_type": "entity", "timeless": True},
    ])
    assert "place:old" in w.locate("obj:desk")        # old parent still reachable
    w.close()


# --------------------------------------------------------------- 4 order

def test_oracle4_recency_within_set_no_sort(world):
    # recency is world-time progression (person:mara is STATE): the later
    # valid_from wins. Equal-valid_from with a different value is a deliberate
    # simultaneous-contradiction flag (indexes._fold_state, "log order alone must
    # never pick a truth"), so the ordering contract rides valid_from, and the
    # engine never SORTS — the winner follows the AUTHORED coordinates, not order.
    w = world
    _seed(w)
    w.commit_set([
        {"op": "assert", "item": {"entity": "person:mara", "attribute": "mood", "value": 1, "valid_from": 5.0}},
        {"op": "assert", "item": {"entity": "person:mara", "attribute": "mood", "value": 2, "valid_from": 6.0}},
    ], classify="rules")
    assert w.state("person:mara", "mood").winner.value == 2


def test_oracle4_reversed_leaves_one(world):
    # author order reversed AND value 1 carries the later coordinate → 1 wins:
    # the engine follows the authored valid_from, never re-sorts by op order.
    w = world
    _seed(w)
    w.commit_set([
        {"op": "assert", "item": {"entity": "person:mara", "attribute": "mood", "value": 2, "valid_from": 5.0}},
        {"op": "assert", "item": {"entity": "person:mara", "attribute": "mood", "value": 1, "valid_from": 6.0}},
    ], classify="rules")
    assert w.state("person:mara", "mood").winner.value == 1


def test_oracle4_physical_append_order_follows_op_list(world):
    # pbr: a winner-only test would also pass a valid_from-sorting impl. Prove the
    # engine applies ops in AUTHOR ORDER — the returned rows and their physical
    # seq follow the op list, regardless of the coordinates carried.
    w = world
    _seed(w)
    rows = w.commit_set([
        {"op": "assert", "item": {"entity": "person:mara", "attribute": "beat", "value": "c", "valid_from": 9.0}},
        {"op": "assert", "item": {"entity": "person:mara", "attribute": "beat", "value": "a", "valid_from": 5.0}},
        {"op": "assert", "item": {"entity": "person:mara", "attribute": "beat", "value": "b", "valid_from": 7.0}},
    ], classify="rules")
    beats = [r for r in rows if r.attribute == "beat"]
    assert [r.value for r in beats] == ["c", "a", "b"]        # author order, not sorted
    assert [r.seq for r in beats] == sorted(r.seq for r in beats)  # monotonic append


def test_oracle4b_retract_staged_id_is_exception_abort(world):
    w = world
    _seed(w)
    head0 = w.buffer.head()
    staged_id = f"a:{head0 + 1}"          # the id the assert below would mint
    with pytest.raises(AtomicAbort) as ei:
        w.commit_set([
            {"op": "assert", "item": {"entity": "obj:desk", "attribute": "mark",
                                      "value": 1, "valid_from": 5.0}},
            {"op": "retract", "assertion_id": staged_id, "reason": "staged"},
        ], classify="rules")
    assert ei.value.cause == "exception"
    assert w.buffer.head() == head0


# --------------------------------------------------------------- 5 adoption set

def _adoption_ops(w):
    main_row = next(r for r in w.buffer.all_rows()
                    if r.entity == "world:manifest" and r.attribute == "main")
    return [
        {"op": "retract", "assertion_id": main_row.id, "reason": "switch main"},
        {"op": "assert", "item": {"entity": "arc:new", "attribute": "kind",
                                  "value": "arc", "timeless": True}},
        {"op": "assert", "item": {"entity": "world:manifest", "attribute": "main",
                                  "value": "arc:new", "value_type": "entity",
                                  "timeless": True}},
    ]


def _seed_adoption(w):
    # a "main" control row (constitutive) plus its manifest
    w.ingest_structured([
        {"entity": "arc:old", "attribute": "kind", "value": "arc", "timeless": True},
        {"entity": "world:manifest", "attribute": "main", "value": "arc:old",
         "value_type": "entity", "timeless": True},
    ])


def test_oracle5_adoption_mixed_set_all_or_none(mkworld):
    # count inserts on a clean run
    counter = mkworld("adopt_count")
    _seed_adoption(counter)
    n = {"c": 0}
    real = counter.buffer._insert
    counter.buffer._insert = lambda r: (n.__setitem__("c", n["c"] + 1), real(r))[1]
    counter.commit_set(_adoption_ops(counter), classify="rules")
    total = n["c"]
    assert total >= 3
    # a fault at each boundary leaves the OLD main fully readable
    for k in range(1, total + 1):
        w = mkworld(f"adopt{k}")
        _seed_adoption(w)
        head0 = w.buffer.head()
        real_insert = w.buffer._insert
        seen = {"c": 0}

        def faulting(row, _k=k, _s=seen, _ri=real_insert):
            _s["c"] += 1
            if _s["c"] == _k:
                raise RuntimeError("boundary fault")
            return _ri(row)

        w.buffer._insert = faulting
        with pytest.raises(AtomicAbort):
            w.commit_set(_adoption_ops(w), classify="rules")
        w.buffer._insert = real_insert
        assert w.state("world:manifest", "main").winner.value == "arc:old"
        assert w.buffer.head() == head0
    # success: exactly one loadable new main
    w = mkworld("adopt_ok")
    _seed_adoption(w)
    w.commit_set(_adoption_ops(w), classify="rules")
    assert w.state("world:manifest", "main").winner.value == "arc:new"


def test_oracle5_unknown_retract_aborts(world):
    w = world
    _seed(w)
    head0 = w.buffer.head()
    with pytest.raises(AtomicAbort) as ei:
        w.commit_set([
            {"op": "assert", "item": {"entity": "arc:x", "attribute": "kind",
                                      "value": "arc", "timeless": True}},
            {"op": "retract", "assertion_id": "a:9999", "reason": "nope"},
        ], classify="rules")
    assert ei.value.cause == "exception"
    assert w.buffer.head() == head0


# --------------------------------------------------------------- 6 snapshot

def test_oracle6_snapshot_restore_on_abort(world):
    w = world
    _seed(w)
    alias_before = dict(w.ingestor._alias_map)
    checked_before = set(w.ingestor._attribute_default_checked)
    cursor_before = w.ingestor.cursor.position
    rebuild_called = {"n": 0}
    orig_rebuild = w.classifier.rebuild
    w.classifier.rebuild = lambda *a, **k: (rebuild_called.__setitem__("n", rebuild_called["n"] + 1), orig_rebuild(*a, **k))[1]
    # a set that adds a manual alias, trips a default-check, advances the cursor,
    # then faults
    real_insert = w.buffer._insert
    calls = {"n": 0}

    def faulting(row):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("fault after some appends")
        return real_insert(row)

    w.buffer._insert = faulting
    try:
        with pytest.raises(AtomicAbort):
            w.porcelain.ingest_structured([
                {"entity": "obj:desk", "attribute": "brandnew_attr", "value": "v", "valid_from": 5.0},
                {"entity": "obj:desk", "attribute": "another_attr", "value": "w", "valid_from": 5.0},
                {"entity": "obj:desk", "attribute": "third_attr", "value": "z", "valid_from": 5.0},
            ], classify="rules", at=9.0, atomic=True)
    finally:
        w.buffer._insert = real_insert
    assert w.ingestor._alias_map == alias_before
    assert w.ingestor._attribute_default_checked == checked_before
    assert w.ingestor.cursor.position == cursor_before      # §B4 pin (a)
    assert rebuild_called["n"] == 0                          # rebuild NOT invoked
    # a post-abort retry of a clean set behaves as a first run
    w.classifier.rebuild = orig_rebuild
    rows = w.ingest_structured(
        [{"entity": "obj:desk", "attribute": "state", "value": "ok", "valid_from": 5.0}],
        classify="rules", atomic=True)
    assert len(rows) == 1


# --------------------------------------------------------------- 7 standalone

def test_oracle7_standalone_retract_missing_raises(world):
    w = world
    _seed(w)
    head0 = w.buffer.head()
    with pytest.raises(ValueError):
        w.truth.retract("a:9999", "missing")
    assert w.buffer.head() == head0               # no orphan retracts row
    # a valid target still retracts
    target = next(r for r in w.buffer.all_rows() if r.entity == "obj:desk"
                  and r.attribute == "in")
    w.truth.retract(target.id, "ok")
    assert w.buffer.head() == head0 + 1


# --------------------------------------------------------------- 8 crash sim

def test_oracle8_crash_precommit_reopen_empty(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    path = tmp_path / "crash.world"
    w = World(path, world_id="w:crash", model=stub, stance="fiction")
    _seed(w)
    head0 = w.buffer.head()
    # simulate a crash before commit: fault at the last insert, then reopen
    real_insert = w.buffer._insert
    calls = {"n": 0}
    w.buffer._insert = lambda row: (real_insert(row) if (calls.__setitem__("n", calls["n"] + 1) or calls["n"] < 2) else (_ for _ in ()).throw(RuntimeError("crash")))
    with pytest.raises(AtomicAbort):
        w.ingest_structured([
            {"entity": "obj:desk", "attribute": "state", "value": "a", "valid_from": 5.0},
            {"entity": "obj:desk", "attribute": "hue", "value": "b", "valid_from": 5.0},
        ], classify="rules", atomic=True)
    w.buffer._insert = real_insert
    w.close()
    # reopen → nothing from the aborted set
    w2 = World(path, world_id="w:crash", model=stub, stance="fiction")
    assert w2.buffer.head() == head0
    rows = w2.ingest_structured(
        [{"entity": "obj:desk", "attribute": "state", "value": "a", "valid_from": 5.0}],
        classify="rules", atomic=True)
    assert len(rows) == 1
    w2.close()


def test_oracle8_non_idempotent_rerun_duplicates(world):
    w = world
    _seed(w)
    op = [{"op": "assert", "item": {"entity": "obj:desk", "attribute": "note",
                                    "value": "hi", "valid_from": 5.0}}]
    w.commit_set(op, classify="rules")
    w.commit_set(op, classify="rules")            # blind re-run
    notes = [r for r in w.buffer.all_rows()
             if r.entity == "obj:desk" and r.attribute == "note"]
    assert len(notes) == 2                        # documents non-idempotence


# --------------------------------------------------------------- 9 model-free

def test_oracle9_model_free_enforcement(world):
    w = world
    _seed(w)
    item = [{"entity": "obj:desk", "attribute": "state", "value": "x", "valid_from": 5.0}]
    with pytest.raises(ValueError):               # omitted classify => inline
        w.ingest_structured(item, atomic=True)
    with pytest.raises(ValueError):
        w.ingest_structured(item, classify="batch", atomic=True)
    with pytest.raises(ValueError):
        w.ingest_structured(item, classify="inline", atomic=True)
    # explicit model-free composes
    assert len(w.ingest_structured(item, classify="rules", atomic=True)) == 1
    assert len(w.ingest_structured(
        [{"entity": "obj:desk", "attribute": "state", "value": "y", "valid_from": 6.0}],
        classify="defer", atomic=True)) == 1
    # ingest() (extraction path) exposes no atomic param
    import inspect
    assert "atomic" not in inspect.signature(w.ingestor.ingest).parameters


# --------------------------------------------------------------- 10 default path

def test_oracle10_default_path_byte_identical(world):
    w = world
    _seed(w)
    # atomic=False keeps per-row visibility + receipt-and-continue skips
    r = w.porcelain.ingest_structured([
        {"entity": "obj:desk", "attribute": "state", "value": "clean", "valid_from": 5.0},
        {"entity": "person:/bad", "attribute": "in", "value": "place:hall", "valid_from": 5.0},
    ], classify="rules")            # non-atomic
    assert w.state("obj:desk", "state").winner.value == "clean"   # good row visible
    assert any(s["reason"] == "malformed_id" for s in r.skipped)  # bad row receipted


def test_oracle10_isolation_level_unchanged_and_post_unit_writers(world):
    w = world
    _seed(w)
    iso_before = w.buffer._conn.isolation_level
    # an atomic success, then an atomic confirmed-abort, then ordinary work
    w.ingest_structured(
        [{"entity": "obj:desk", "attribute": "state", "value": "one", "valid_from": 5.0}],
        classify="rules", atomic=True)
    with pytest.raises(AtomicAbort):
        w.ingest_structured(
            [{"entity": "person:/bad", "attribute": "in", "value": "x", "valid_from": 5.0}],
            classify="rules", atomic=True)
    assert w.buffer._conn.isolation_level == iso_before           # unchanged (§F1.a)
    # ordinary non-atomic writers work normally after both (authorizer restored)
    w.ingest_structured(
        [{"entity": "obj:desk", "attribute": "state", "value": "two", "valid_from": 6.0}])
    assert w.state("obj:desk", "state").winner.value == "two"


# --------------------------------------------------------------- 11 meta-rows

def test_oracle11_meta_rows_ride_the_unit(world):
    w = world
    _seed(w)
    head0 = w.buffer.head()
    # `located_in` canonicalizes → the data row PLUS a `canonicalized_from`
    # receipt meta-row; a fault after the meta-row rolls BOTH back (no orphan
    # receipt survives).
    real_insert = w.buffer._insert
    calls = {"n": 0}

    def faulting(row):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("fault after the canonicalization receipt")
        return real_insert(row)

    w.buffer._insert = faulting
    try:
        with pytest.raises(AtomicAbort):
            w.ingest_structured(
                [{"entity": "person:mara", "attribute": "located_in",
                  "value": "place:hall", "value_type": "entity", "valid_from": 5.0}],
                classify="rules", atomic=True)
    finally:
        w.buffer._insert = real_insert
    assert w.buffer.head() == head0
    assert not any(r.attribute == "canonicalized_from"
                   for r in w.buffer.all_rows())


# --------------------------------------------------------------- 12 taxonomy

def test_oracle12_failure_taxonomy_matches_non_atomic(world):
    w = world
    _seed(w)
    # authority violation: generated-into-canon RAISES on both paths
    gen = [{"entity": "obj:desk", "attribute": "state", "value": "x",
            "valid_from": 5.0, "status": "generated"}]
    with pytest.raises(Exception) as non_atomic:
        w.ingest_structured(gen, classify="rules")
    assert not isinstance(non_atomic.value, AtomicAbort)     # raw raise, non-atomic
    with pytest.raises(AtomicAbort) as atomic:
        w.ingest_structured(gen, classify="rules", atomic=True)
    assert atomic.value.cause == "exception"                 # wrapped, not gate_skip
    # the wrapped error names the SAME original exception type as the raw raise
    assert atomic.value.error["type"] == type(non_atomic.value).__name__
    # malformed id is gate_skip
    with pytest.raises(AtomicAbort) as skip:
        w.ingest_structured(
            [{"entity": "person:/bad", "attribute": "in", "value": "x", "valid_from": 5.0}],
            classify="rules", atomic=True)
    assert skip.value.cause == "gate_skip"


# --------------------------------------------------------------- 14 facade

def test_oracle14_facade_deny_by_default_and_leak_closed(world):
    w = world
    _seed(w)
    facade = w.buffer.raw_connection()
    head0 = w.buffer.head()
    probe = {}

    def body():
        # borrowed transaction-control SQL is denied at phase=none
        for sql in ("COMMIT", "ROLLBACK", "END", "SAVEPOINT s", "BEGIN"):
            try:
                facade.execute(sql)
                probe[sql] = "ALLOWED"
            except sqlite3.DatabaseError:
                probe[sql] = "denied"
        # DDL / ATTACH / mutating pragma denied
        for sql in ("CREATE TABLE x (i)", "ATTACH DATABASE ':memory:' AS m"):
            try:
                facade.execute(sql)
                probe[sql] = "ALLOWED"
            except (sqlite3.DatabaseError, RuntimeError):
                probe[sql] = "denied"
        # leak-closed: no chain recovers the raw connection
        probe["exec_conn_is_facade"] = facade.execute("SELECT 1").connection is facade
        probe["cursor_conn_is_facade"] = facade.cursor().execute("SELECT 1").connection is facade
        probe["enter_is_facade"] = (facade.__enter__() is facade)
        # executescript during a unit is rejected
        try:
            facade.executescript("SELECT 1")
            probe["executescript"] = "ALLOWED"
        except RuntimeError:
            probe["executescript"] = "denied"
        # autocommit set + close through a borrowed handle rejected mid-unit
        try:
            facade.autocommit = True
            probe["autocommit"] = "ALLOWED"
        except RuntimeError:
            probe["autocommit"] = "denied"
        try:
            facade.close()
            probe["close"] = "ALLOWED"
        except RuntimeError:
            probe["close"] = "denied"
        # a normal sidecar-style read/insert still works inside the unit
        facade.execute("SELECT COUNT(*) FROM assertions").fetchone()
        probe["isolation_ok"] = _second_conn_new_rows(w, head0) == 0
        raise RuntimeError("roll back the probe unit")

    with pytest.raises(AtomicAbort):
        w.ingestor._run_atomic(body)
    for sql in ("COMMIT", "ROLLBACK", "END", "SAVEPOINT s", "BEGIN",
                "CREATE TABLE x (i)", "ATTACH DATABASE ':memory:' AS m"):
        assert probe[sql] == "denied", (sql, probe[sql])
    assert probe["exec_conn_is_facade"] and probe["cursor_conn_is_facade"]
    assert probe["enter_is_facade"]
    assert probe["executescript"] == "denied"
    assert probe["autocommit"] == "denied"
    assert probe["close"] == "denied"
    assert probe["isolation_ok"] is True
    # after the unit, ordinary DML and DDL-bearing rebuild resume
    assert w.buffer.head() == head0
    w.salience_index.rebuild()                    # DDL recreate allowed OUTSIDE a unit


def test_oracle14_deny_by_default_unknown_attribute(world):
    facade = world.buffer.raw_connection()
    with pytest.raises(AttributeError):
        facade.set_authorizer(None)               # not on the allowlist
    with pytest.raises(AttributeError):
        _ = facade.iterdump                       # arbitrary sqlite surface denied


def test_oracle14_fail_closed_poison_on_unconfirmable_rollback(world):
    w = world
    _seed(w)
    # make ROLLBACK itself fail → the connection must be poisoned + the raw error
    # propagated unwrapped (NOT AtomicAbort)
    orig_run_phase = w.buffer._run_phase

    def broken_phase(phase, sql):
        if phase == "rollback":
            raise sqlite3.OperationalError("rollback cannot be confirmed")
        return orig_run_phase(phase, sql)

    w.buffer._run_phase = broken_phase

    def body():
        w.buffer.append(entity="obj:desk", attribute="state", value="x",
                        role=w.ingestor._role, status="stated", valid_from=5.0)
        raise RuntimeError("trigger abort")

    with pytest.raises(sqlite3.OperationalError):     # raw error, unwrapped (§B6)
        w.ingestor._run_atomic(body)
    assert w.buffer.poisoned is True
    # every later operation raises — uncertain state can never be finalized
    with pytest.raises((PoisonedConnection, sqlite3.ProgrammingError)):
        w.buffer.raw_connection().execute("SELECT 1")


def _assert_raises_attr(obj, name):
    """Direct attribute access — by ANY spelling, mangled included — must raise
    AttributeError (a real allowlist, not name renaming; pbr r2 A1)."""
    try:
        getattr(obj, name)
    except AttributeError:
        return
    raise AssertionError(f"{name!r} is reachable on {type(obj).__name__} — leak")


def test_oracle14_a1_full_escape_exploit_fails(world):
    # A1: the exact exploit pbr reproduced must not recover a raw connection by
    # ANY attribute spelling, including the mangled ones.
    w = world
    _seed(w)
    head0 = w.buffer.head()
    facade = w.buffer.raw_connection()
    proxy = facade.execute("SELECT 1")

    # every raw-returning path on the borrowed surface raises — ASSERTED, incl.
    # the mangled spellings pbr named
    for spelling in ("_raw", "_b", "_buffer", "_conn",
                     "_ConnectionFacade__raw", "_ConnectionFacade__buffer",
                     "_ConnectionFacade__b"):
        _assert_raises_attr(facade, spelling)
    for spelling in ("_cursor", "_facade", "_native",
                     "_CursorProxy__cursor", "_CursorProxy__facade",
                     # the poison re-check: allowlisting it as a METHOD handed
                     # callers `proxy._live().connection` = the raw connection
                     "_live", "_live_cursor", "_CursorProxy__live"):
        _assert_raises_attr(proxy, spelling)
    # iter(proxy).connection is the FACADE, never the native cursor's connection
    assert iter(facade.execute("SELECT 1")).connection is facade

    caught = {}

    def body():
        # the full disable-authorizer/commit exploit, run through each path
        for getter in (
            lambda: iter(facade.execute("SELECT 1")).connection,
            lambda: facade.execute("SELECT 1").connection,
            lambda: facade.cursor().connection,
        ):
            recovered = getter()
            # `.connection` yields the facade — attempting to disable the
            # authorizer or commit through it is denied (not on the allowlist) or
            # inert (gated); it can NEVER reach the native handle.
            try:
                recovered.set_authorizer(None)
                caught["disable"] = "ALLOWED"      # would be a leak
                break
            except AttributeError:
                caught["disable"] = "denied"
            recovered.commit()                     # gated → inert during the unit
        w.buffer.append(entity="obj:desk", attribute="state", value="x",
                        role=w.ingestor._role, status="stated", valid_from=5.0)
        caught["iso"] = _second_conn_new_rows(w, head0) == 0
        raise RuntimeError("abort the probe unit")

    with pytest.raises(AtomicAbort):
        w.ingestor._run_atomic(body)
    assert caught["disable"] == "denied"                    # exploit dead
    assert caught["iso"] is True                            # nothing visible mid-unit
    # zero durable prefix despite every exploit attempt (all-or-none holds)
    assert w.buffer.head() == head0
    assert _second_conn_new_rows(w, head0) == 0


class _ConnWrapper:
    """Forwards to the real connection but fails the Nth set_authorizer call —
    the native attribute is read-only, so wrap to inject the post-commit fault."""

    def __init__(self, real, fail_on):
        self._real = real
        self._fail_on = fail_on
        self._n = 0

    def set_authorizer(self, cb):
        self._n += 1
        if self._n == self._fail_on:
            raise sqlite3.OperationalError("authorizer restore failed post-commit")
        return self._real.set_authorizer(cb)

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_oracle14_a2_post_commit_fault_is_not_atomic_abort(world):
    # A2: a fault AFTER a confirmed COMMIT (injected in the outer authorizer
    # restore, the 2nd set_authorizer) is the ambiguous post-commit outcome — the
    # raw error propagates, never AtomicAbort; views are NOT restored; DURABLE.
    w = world
    _seed(w)
    head0 = w.buffer.head()
    real = w.buffer._conn
    alias_before = dict(w.ingestor._alias_map)
    w.buffer._conn = _ConnWrapper(real, fail_on=2)   # install ok, restore fails
    try:
        with pytest.raises(sqlite3.OperationalError):        # NOT AtomicAbort
            w.ingest_structured(
                [{"entity": "obj:desk", "attribute": "state", "value": "durable",
                  "valid_from": 5.0}], classify="rules", atomic=True)
    finally:
        w.buffer._conn = real
        real.set_authorizer(None)                            # clear lingering cb
    assert w.buffer.unit_committed is True
    assert _second_conn_new_rows(w, head0) >= 1              # the set is durable
    # views were NOT restored (the set committed — restoring would be a lie)
    assert w.ingestor._alias_map == alias_before             # (unchanged here anyway)


def test_oracle14_a3_setup_fault_cleans_up(world):
    # A3: a fault during unit SETUP (head() before BEGIN) still runs the outer
    # cleanup — _unit_open cleared, authorizer removed — so the next ordinary
    # non-atomic INSERT is unaffected.
    w = world
    _seed(w)
    real_head = w.buffer.head
    fire = {"armed": True}

    def flaky_head():
        if fire["armed"]:
            fire["armed"] = False
            raise sqlite3.OperationalError("setup fault in head()")
        return real_head()

    w.buffer.head = flaky_head
    try:
        with pytest.raises(AtomicAbort):
            w.ingest_structured(
                [{"entity": "obj:desk", "attribute": "state", "value": "x",
                  "valid_from": 5.0}], classify="rules", atomic=True)
    finally:
        w.buffer.head = real_head
    assert w.buffer._unit_open is False
    # the next ordinary non-atomic write works (authorizer was restored)
    w.ingest_structured(
        [{"entity": "obj:desk", "attribute": "state", "value": "ok", "valid_from": 6.0}])
    assert w.state("obj:desk", "state").winner.value == "ok"


def test_oracle14_a4_facade_context_manager_outside_unit(world):
    # A4: outside a unit, `with facade:` mirrors sqlite context semantics —
    # commit on clean exit, rollback on exception.
    w = world
    _seed(w)
    facade = w.buffer.raw_connection()
    path = w.buffer.path

    def rows_with_key(k):
        c2 = sqlite3.connect(path)
        try:
            return c2.execute("SELECT COUNT(*) FROM world_meta WHERE key=?",
                              (k,)).fetchone()[0]
        finally:
            c2.close()

    # clean exit commits
    with facade:
        facade.execute("INSERT INTO world_meta (key, value) VALUES ('ctx_ok', '1')")
    assert rows_with_key("ctx_ok") == 1
    # exceptional exit rolls back
    with pytest.raises(ValueError):
        with facade:
            facade.execute("INSERT INTO world_meta (key, value) VALUES ('ctx_bad', '1')")
            raise ValueError("boom")
    assert rows_with_key("ctx_bad") == 0


# --------------------------------------------------------------- 15 no-degrade

def test_oracle15_sidecar_writers_defer_under_unit(world):
    w = world
    _seed(w)
    head0 = w.buffer.head()
    # a classifier _store inside an open unit defers its commit; the second
    # connection sees nothing until the terminal commit
    probe = {}

    def body():
        row = w.buffer.append(entity="obj:desk", attribute="state", value="x",
                              role=w.ingestor._role, status="stated", valid_from=5.0)
        w.classifier.set(row.id, "STATE", 0.5)        # sidecar write via facade
        probe["mid_unit_isolated"] = _second_conn_new_rows(w, head0) == 0
        return row

    w.ingestor._run_atomic(body)
    assert probe["mid_unit_isolated"] is True
    assert w.buffer.head() == head0 + 1               # committed as a unit
    # outside a unit the same sidecar writer commits normally
    row = w.buffer.append(entity="obj:desk", attribute="hue", value="red",
                          role=w.ingestor._role, status="stated", valid_from=6.0)
    w.classifier.set(row.id, "STATE", 0.5)
    assert _second_conn_new_rows(w, head0) >= 2


# --------------------------------------------------------------- 13 MCP wire

@pytest.mark.anyio
async def test_oracle13_mcp_wire_atomic_abort_envelope(tmp_path):
    pytest.importorskip("mcp.types")
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    world_path = tmp_path / "wire.world"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "patternbuffer.mcp",
              "--world", str(world_path), "--world-id", "w:wire"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            before = await session.call_tool("entities", {"frame": "canon"})
            baseline = before.structuredContent["result"]

            # gate_skip: a malformed-id assert → structuredContent.skipped set,
            # error null
            gs = await session.call_tool("commit_set", {"ops": [
                {"op": "assert", "item": {"entity": "person:/bad", "attribute": "in",
                                          "value": "place:x", "valid_from": 1.0}}]})
            assert gs.isError
            sc = gs.structuredContent
            assert sc["cause"] == "gate_skip"
            assert sc["error"] is None
            assert sc["skipped"] and sc["skipped"][0]["reason"] == "malformed_id"

            # exception: an unknown retract target → cause exception, skipped [],
            # error {type,message}
            ex = await session.call_tool("commit_set", {"ops": [
                {"op": "retract", "assertion_id": "a:9999", "reason": "nope"}]})
            assert ex.isError
            sc2 = ex.structuredContent
            assert sc2["cause"] == "exception"
            assert sc2["skipped"] == []
            assert set(sc2["error"]) == {"type", "message"}

            # both left the world byte-identical to pre-call
            after = await session.call_tool("entities", {"frame": "canon"})
            assert after.structuredContent["result"] == baseline

            # a clean commit_set still succeeds over the wire
            ok = await session.call_tool("commit_set", {"ops": [
                {"op": "assert", "item": {"entity": "place:deck", "attribute": "kind",
                                          "value": "place", "timeless": True}}]})
            assert not ok.isError
            assert len(ok.structuredContent["result"]["rows"]) >= 1


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ============================================================ pbr code review
# ATOMIC-ACTIVATION-V1 code verdict <8f99e09b…> — F1 (HIGH), F2 (MEDIUM).

class TestPoisonIsASoftwareGate:
    """F1 — §B6's fail-closed guarantee must not depend on the physical
    `close()` succeeding.

    pbr's reproduction: wrap the connection so BOTH `ROLLBACK` and `close()`
    raise while the underlying SQLite connection stays live. The buffer
    poisoned, but `head()` and a cursor cached before the abort both still
    worked — an uncertain transaction remained observable and finalizable.
    """

    def _poisoned_buffer(self, tmp_path):
        """A buffer whose rollback AND close both fail, leaving SQLite live."""
        from patternbuffer.buffer import PatternBuffer

        buf = PatternBuffer(tmp_path / "poison.world", world_id="w:poison")
        cached = buf.raw_connection().execute("SELECT 1")   # cached BEFORE abort

        real = buf._conn

        class Hostile:
            """Live connection; ROLLBACK and close() raise."""
            def __getattr__(self, name):
                return getattr(real, name)

            def execute(self, sql, *a, **k):
                if sql.strip().upper().startswith("ROLLBACK"):
                    raise sqlite3.OperationalError("rollback failed")
                return real.execute(sql, *a, **k)

            def close(self):
                raise sqlite3.OperationalError("close failed")

        buf._conn = Hostile()

        def body():
            raise RuntimeError("force abort")

        try:
            buf.atomic_unit(body)          # takes a callable, not a CM
        except Exception:
            pass
        return buf, cached

    def test_poison_blocks_buffer_read_paths(self, tmp_path):
        buf, _ = self._poisoned_buffer(tmp_path)
        assert buf.poisoned is True
        with pytest.raises(PoisonedConnection):
            buf.head()

    def test_poison_blocks_a_cursor_cached_before_the_abort(self, tmp_path):
        """The decisive one — a handle obtained before the abort must die too."""
        buf, cached = self._poisoned_buffer(tmp_path)
        with pytest.raises(PoisonedConnection):
            cached.execute("SELECT COUNT(*) FROM assertions")

    def test_poison_blocks_newly_obtained_paths(self, tmp_path):
        buf, _ = self._poisoned_buffer(tmp_path)
        with pytest.raises(PoisonedConnection):
            buf.raw_connection().execute("SELECT 1")

    def test_cached_rowcount_and_description_are_gated(self, tmp_path):
        """Every native-cursor state read is poison-checked, not just
        `lastrowid` — `rowcount`/`description` used to stay readable."""
        buf, cached = self._poisoned_buffer(tmp_path)
        with pytest.raises(PoisonedConnection):
            cached.rowcount
        with pytest.raises(PoisonedConnection):
            cached.description

    def test_poison_recheck_helper_is_not_borrowable(self, tmp_path):
        """The per-operation poison re-check must not itself be an escape.

        Making it an allowlisted METHOD handed callers
        `facade.execute(...)._live().connection` — the raw connection, and so
        `set_authorizer(None)` and unmediated transaction control. It is a
        module function now, reachable from module code and nowhere else.
        """
        from patternbuffer.buffer import PatternBuffer

        buf = PatternBuffer(tmp_path / "escape.world", world_id="w:escape")
        cur = buf.raw_connection().execute("SELECT 1")
        with pytest.raises(AttributeError):
            cur._live
        for spelling in ("_live", "_live_cursor", "_cursor", "_facade"):
            with pytest.raises(AttributeError):
                getattr(cur, spelling)
        buf.close()


class TestCommitSetOpSchemaIsExact:
    """F2 — the Python door enforces §C1's exact vocabulary, matching the
    published MCP schema instead of being laxer than it."""

    def test_assert_op_rejects_outer_role_key(self, world):
        """Authority is held internally and never taken from the op."""
        with pytest.raises(ValueError, match="accepts exactly"):
            world.commit_set([{
                "op": "assert", "role": "truth",
                "item": {"entity": "o:1", "attribute": "k", "value": "v",
                         "valid_from": 1.0},
            }])

    def test_assert_op_rejects_outer_status_key(self, world):
        with pytest.raises(ValueError, match="accepts exactly"):
            world.commit_set([{
                "op": "assert", "status": "observed",
                "item": {"entity": "o:1", "attribute": "k", "value": "v",
                         "valid_from": 1.0},
            }])

    def test_retract_reason_must_be_a_string(self, world):
        rows = world.ingest_structured([
            {"entity": "o:1", "attribute": "k", "value": "v", "valid_from": 1.0},
        ])
        rid = [r.id for r in rows if getattr(r, "attribute", None) == "k"][0]
        with pytest.raises(ValueError, match="reason.*string"):
            world.commit_set([
                {"op": "retract", "assertion_id": rid, "reason": {"why": "bad"}},
            ])

    def test_valid_ops_are_unaffected(self, world):
        """The narrowing must never reject a contract-valid call."""
        rows = world.commit_set([
            {"op": "assert", "item": {"entity": "o:1", "attribute": "k",
                                      "value": "v", "valid_from": 1.0}},
        ])
        assert rows
        rid = [r.id for r in rows if getattr(r, "attribute", None) == "k"][0]
        world.commit_set([
            {"op": "retract", "assertion_id": rid, "reason": "superseded"},
        ])
