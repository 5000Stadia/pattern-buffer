"""BUILD-SESSION-V1: begin_build/seal_build/abort_build + the build() sugar.

The session defers classification for everything ingested inside it and
seals with one pass; exceptions abort without classifying; World.close()
never leaves a session live; per-call rules/batch choices compose.
"""

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "bs.world", world_id="w:bs", model=stub)
    yield w
    w.close()


def _items(n, prefix="obj:thing"):
    out = []
    for i in range(n):
        out.append({"entity": f"{prefix}_{i}", "attribute": "kind",
                    "value": "object", "timeless": True})
        out.append({"entity": f"{prefix}_{i}", "attribute": "state",
                    "value": "dusty", "valid_from": float(i + 1)})
    return out


def test_session_defers_then_seal_classifies(world):
    p = world.porcelain
    receipt = p.begin_build(at=0.0)
    assert receipt["outcome"] == "build_open"
    p.ingest_structured(_items(3))          # default classify= — session wins
    rows = [r for r in world.buffer.all_rows() if r.seq > receipt["since_seq"]]
    assert rows and all(world.classifier.get(r.id) is None for r in rows)
    sealed = p.seal_build()
    assert sealed["outcome"] == "sealed" and sealed["scope"] == "session"
    assert sealed["classified"] == len(rows)
    assert all(world.classifier.get(r.id) is not None for r in rows)
    assert world.ingestor.classify_inline is True      # toggle restored


def test_double_begin_and_bare_seal_raise(world):
    p = world.porcelain
    p.begin_build()
    with pytest.raises(RuntimeError, match="already open"):
        p.begin_build()
    p.abort_build()
    with pytest.raises(RuntimeError, match="no build session"):
        p.seal_build()


def test_sugar_seals_on_clean_exit_aborts_on_exception(world):
    p = world.porcelain
    with p.build(at=0.0):
        p.ingest_structured(_items(1, prefix="obj:clean"))
    row = world.buffer.visible(attribute="state")[0]
    assert world.classifier.get(row.id) is not None    # sealed

    with pytest.raises(RuntimeError, match="boom"):
        with p.build():
            p.ingest_structured(_items(1, prefix="obj:crash"))
            raise RuntimeError("boom")
    crash_rows = [r for r in world.buffer.visible()
                  if r.entity == "obj:crash_0" and r.attribute == "state"]
    assert crash_rows and world.classifier.get(crash_rows[0].id) is None  # NOT classified
    assert world.ingestor.classify_inline is True      # toggle restored
    assert p.abort_build()["outcome"] == "no_session"  # session closed


def test_per_call_rules_inside_session_composes(world):
    p = world.porcelain
    p.begin_build()
    p.ingest_structured(_items(1, prefix="obj:early"), classify="rules")
    early = [r for r in world.buffer.visible() if r.entity == "obj:early_0"]
    assert all(world.classifier.get(r.id) is not None for r in early)  # local choice won
    p.ingest_structured(_items(1, prefix="obj:late"))
    sealed = p.seal_build()
    # seal classified only the still-pending rows (no double work)
    assert sealed["classified"] < sealed["seq_range"][1] - sealed["seq_range"][0] + 1


def test_scope_all_sweeps_presession_deferred(world):
    p = world.porcelain
    p.ingest_structured(_items(1, prefix="obj:pre"), classify="defer")
    pre = [r for r in world.buffer.visible() if r.entity == "obj:pre_0"]
    assert all(world.classifier.get(r.id) is None for r in pre)
    p.begin_build()
    p.ingest_structured(_items(1, prefix="obj:in"))
    p.seal_build(scope="all")
    assert all(world.classifier.get(r.id) is not None for r in pre)   # swept


def test_close_aborts_open_session(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "close.world", world_id="w:close", model=stub)
    p = w.porcelain
    p.begin_build()
    p.ingest_structured(_items(1, prefix="obj:orphan"))
    w.close()                                   # aborts, never classifies
    assert p._build_head is None                # session state cleared


def test_prior_inline_false_restores_false(world):
    world.ingestor.classify_inline = False      # a host running deferred anyway
    p = world.porcelain
    p.begin_build()
    p.seal_build()
    assert world.ingestor.classify_inline is False   # prior value, not blind True
    world.ingestor.classify_inline = True
