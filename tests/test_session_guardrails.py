"""SESSION-GUARDRAILS-V1: deferred classification still applies the guardrails
at the end of the ingest call, and a failed seal closes the session.

Rows a guardrail decides (zero model calls) are classified by the time a
deferred ingest call returns, whatever wrote them; ambiguous rows wait for the
seal / classify_all. Verdicts are identical to the old deferred-then-sealed
path -- only the moment differs.
"""

import re

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


def _stub():
    return StubModel(fallback=rule_classifier_fallback())


@pytest.fixture
def world(tmp_path):
    stub = _stub()
    w = World(tmp_path / "sg.world", world_id="w:sg", model=stub)
    w.stub = stub
    yield w
    w.close()


_FIXTURE = [
    {"entity": "person:ann", "attribute": "name", "value": "Ann Vey", "timeless": True,
     "aliases": ["the steward"]},                                 # name + alias rows
    {"entity": "person:ann", "attribute": "located_in", "value": "place:hall",
     "value_type": "entity", "valid_from": 1.0,
     "source_doc": "doc:ledger"},                  # canonicalized_from + source META rows
    {"entity": "person:ann", "attribute": "gold", "value": 100,
     "fold_policy": "accrue", "valid_from": 1.0},
    {"entity": "person:ann", "attribute": "gold", "value": -10,
     "value_type": "delta", "valid_from": 2.0},                   # a delta
    {"entity": "event:bell", "attribute": "kind", "value": "bell", "valid_from": 2.0},
    {"entity": "event:bell", "attribute": "caused_by", "value": "event:storm",
     "value_type": "entity", "valid_from": 2.0},                  # an event row
    {"entity": "obj:lamp", "attribute": "held_by", "value": "person:ann",
     "value_type": "entity", "valid_from": 2.0},                  # containment
    {"entity": "person:ann", "attribute": "mood", "value": "wary", "valid_from": 2.0},
    {"entity": "obj:lamp", "attribute": "glow", "value": "dim", "valid_from": 2.0},
]


def _rows(w, since=0):
    return [r for r in w.buffer.all_rows() if r.seq > since]


def _table(w):
    return {r.id: (c.durability, c.class_confidence, c.needs_review)
            for r in w.buffer.all_rows() if (c := w.classifier.get(r.id))}


def _guarded(w, rows):
    return [r for r in rows if w.classifier._guardrails(r) is not None]


def _ambiguous(w, rows):
    return [r for r in rows if w.classifier._guardrails(r) is None]


def _assert_only_side_rows_unclassified(w, head0):
    """Inline and per-call modes are unchanged by this spec: the rows they
    classify (or collect) are classified; side rows they never reached stay as
    before."""
    left = {r.attribute for r in _rows(w, head0) if w.classifier.get(r.id) is None}
    assert left <= {"alias", "canonicalized_from", "source", "fold_policy"}


# ------------------------------------------------------------------ 1 session

def test_session_guardrail_rows_classified_before_seal(world):
    p = world.porcelain
    since = p.begin_build(at=0.0)["since_seq"]
    p.ingest_structured(_FIXTURE)
    rows = _rows(world, since)
    attrs = {r.attribute for r in rows}
    # the writers the spec names all produced rows
    assert {"name", "alias", "source", "canonicalized_from", "caused_by",
            "held_by"} <= attrs
    assert any(r.value_type == "delta" for r in rows)

    guarded, ambiguous = _guarded(world, rows), _ambiguous(world, rows)
    assert guarded and ambiguous
    for r in guarded:
        got = world.classifier.get(r.id)
        assert got is not None, (r.entity, r.attribute)
        want = world.classifier._guardrails(r)
        assert (got.durability, got.class_confidence) == want
    for r in ambiguous:
        assert world.classifier.get(r.id) is None, (r.entity, r.attribute)

    # the aliases side key's rows (written by add_alias) and the META side rows
    assert all(world.classifier.get(r.id) for r in rows if r.attribute == "alias")
    for attr in ("source", "canonicalized_from"):
        meta = [r for r in rows if r.attribute == attr]
        assert meta and all(world.classifier.get(r.id) for r in meta)

    # the seal classifies only the ambiguous rest, with no model call for the
    # guardrail rows (rules-only here: no model call at all)
    sealed = p.seal_build()
    assert sealed["classified"] == len(ambiguous)
    assert world.stub.calls == []
    assert all(world.classifier.get(r.id) is not None for r in rows)


def test_seal_with_model_asks_only_about_ambiguous_rows(world):
    p = world.porcelain
    since = p.begin_build()["since_seq"]
    p.ingest_structured(_FIXTURE)
    ambiguous = _ambiguous(world, _rows(world, since))
    p.seal_build(model=True)
    asked = "\n".join(prompt for prompt, _ in world.stub.calls)
    assert len(world.stub.calls) == 1                          # one batch call
    assert "mood" in asked and "glow" in asked
    listed = [ln for ln in asked.splitlines() if re.match(r"\d+\. ", ln)]
    assert len(listed) == len(ambiguous) >= 2                  # only the ambiguous rows


# -------------------------------------------------- 2 defer and the toggle

def test_defer_classifies_guardrails_at_ingest_and_classify_all_finishes(world):
    head0 = world.buffer.head()
    world.ingest_structured(_FIXTURE, classify="defer")
    rows = _rows(world, head0)
    assert all(world.classifier.get(r.id) for r in _guarded(world, rows))
    assert all(world.classifier.get(r.id) is None for r in _ambiguous(world, rows))
    n = len(_ambiguous(world, rows))
    assert world.classifier.classify_all() == n
    assert all(world.classifier.get(r.id) for r in rows)


def test_harness_toggle_classifies_guardrails_at_ingest(world):
    world.ingestor.classify_inline = False
    head0 = world.buffer.head()
    world.ingest_structured(_FIXTURE)
    rows = _rows(world, head0)
    assert all(world.classifier.get(r.id) for r in _guarded(world, rows))
    assert all(world.classifier.get(r.id) is None for r in _ambiguous(world, rows))
    assert world.classifier.classify_all() == len(_ambiguous(world, rows))


def test_commit_set_defer_classifies_guardrails(world):
    ops = [{"op": "assert", "item": it} for it in _FIXTURE]
    head0 = world.buffer.head()
    world.commit_set(ops, classify="defer")
    rows = _rows(world, head0)
    assert all(world.classifier.get(r.id) for r in _guarded(world, rows))
    assert all(world.classifier.get(r.id) is None for r in _ambiguous(world, rows))


def test_inline_and_per_call_modes_unchanged(world):
    head0 = world.buffer.head()
    world.ingest_structured(_FIXTURE)                          # inline: all classified
    _assert_only_side_rows_unclassified(world, head0)


def test_per_call_rules_still_classifies_everything_collected(world):
    head0 = world.buffer.head()
    world.ingest_structured(_FIXTURE, classify="rules")
    _assert_only_side_rows_unclassified(world, head0)
    assert world.stub.calls == []


def test_raising_call_classifies_nothing_further(world):
    world.ingestor.classify_inline = False
    head0 = world.buffer.head()
    with pytest.raises(Exception):
        world.ingest_structured(_FIXTURE + [{"entity": 5}], atomic=True,
                                classify="defer")
    assert _rows(world, head0) == []                           # rolled back, nothing left


# ------------------------------------------------------- 3 same verdicts

def test_verdict_tables_identical_to_the_old_deferred_path(tmp_path):
    a = World(tmp_path / "a.world", world_id="w:sg", model=_stub())
    b = World(tmp_path / "b.world", world_id="w:sg", model=_stub())
    try:
        since = a.porcelain.begin_build()["since_seq"]
        a.porcelain.ingest_structured(_FIXTURE)
        a.porcelain.seal_build()

        # the pre-change path: deferred rows, the sidecar emptied of anything the
        # end-of-call hook wrote, then one rules-only classify_rows pass
        b.porcelain.begin_build()
        b.porcelain.ingest_structured(_FIXTURE)
        b.buffer.raw_connection().execute(
            "DELETE FROM sidecar_classification WHERE assertion_id IN"
            " (SELECT id FROM assertions WHERE seq > ?)", (since,))
        b.buffer.raw_connection().commit()
        b.classifier.classify_rows(_rows(b, since), model=False)

        ta = {k: v for k, v in _table(a).items() if int(k[2:]) > since}
        tb = {k: v for k, v in _table(b).items() if int(k[2:]) > since}
        assert ta and ta == tb
        assert len(ta) == len(_rows(a, since))
    finally:
        a.close()
        b.close()


# ----------------------------------------------------------- 4 a failed seal

def test_failed_seal_closes_the_session(world, monkeypatch):
    p = world.porcelain
    since = p.begin_build()["since_seq"]
    p.ingest_structured(_FIXTURE)
    rows = _rows(world, since)
    ambiguous = _ambiguous(world, rows)

    def boom(*a, **k):
        raise RuntimeError("sidecar exploded")

    monkeypatch.setattr(world.classifier, "classify_rows", boom)
    with pytest.raises(RuntimeError, match="sidecar exploded"):
        p.seal_build()
    monkeypatch.undo()

    assert p._build_head is None and p._build_prev_inline is None
    assert world.ingestor.classify_inline is True            # restored
    assert p.abort_build()["outcome"] == "no_session"
    assert all(world.classifier.get(r.id) is None for r in ambiguous)  # unreached
    p.begin_build()                                          # a new session opens
    p.abort_build()
    assert world.classifier.classify_all() == len(ambiguous)
    assert all(world.classifier.get(r.id) for r in rows)


def test_raising_model_still_seals_with_fallback_verdicts(tmp_path):
    def broken(prompt, schema):
        raise RuntimeError("model down")

    w = World(tmp_path / "m.world", world_id="w:sg", model=broken)
    try:
        p = w.porcelain
        since = p.begin_build()["since_seq"]
        p.ingest_structured(_FIXTURE)
        ambiguous = _ambiguous(w, _rows(w, since))
        sealed = p.seal_build(model=True)
        assert sealed["outcome"] == "sealed"
        assert sealed["classified"] == len(ambiguous)
        for r in ambiguous:
            c = w.classifier.get(r.id)
            want = ("CONSTITUTIVE" if w.classifier._semantics.is_containment(r.attribute)
                    else "STATE")
            assert (c.durability, c.class_confidence) == (want, 0.5)
        assert p._build_head is None and w.ingestor.classify_inline is True
        p.begin_build()
        p.abort_build()
    finally:
        w.close()


# --------------------------------------------------------------- 5 the sugar

def test_sugar_whose_seal_raises_leaves_no_session(world, monkeypatch):
    p = world.porcelain

    def boom(*a, **k):
        raise RuntimeError("seal pass failed")

    monkeypatch.setattr(world.classifier, "classify_rows", boom)
    with pytest.raises(RuntimeError, match="seal pass failed"):
        with p.build(model=True):
            p.ingest_structured(_FIXTURE)
    monkeypatch.undo()
    assert p._build_head is None
    assert world.ingestor.classify_inline is True
    p.begin_build()
    p.abort_build()
