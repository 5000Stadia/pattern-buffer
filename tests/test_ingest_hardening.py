"""INGEST-HARDENING-V1: batched durability mode + edge-granular cycle rejection.

Part A — `p.ingest_structured(items, classify="batch")` defers classification and
runs ONE batch model call per ingest call (the first-class form of the manual
classify_inline=False + classify_all recipe). Part B — a single structurally-
invalid edge is skipped with a typed receipt, not aborting the chunk.
"""

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "ih.world", world_id="w:ih", model=stub)
    yield w
    w.close()


# --------------------------------------------------- Part A: batched classify

def test_batch_mode_one_model_call(tmp_path):
    # N model-needing rows -> ONE batch model call (vs N per-row inline)
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "b.world", world_id="w:b", model=stub)
    items = [{"entity": f"person:p{i}", "attribute": "mood", "value": "x", "valid_from": 1.0}
             for i in range(5)]
    w.porcelain.ingest_structured(items, classify="batch")
    classify_calls = [c for c in stub.calls if c[0].startswith("Classify the lifetime")]
    assert len(classify_calls) == 1                      # one batch, not five
    # all rows classified on return
    for i in range(5):
        row = next(r for r in w.buffer.all_rows()
                   if r.entity == f"person:p{i}" and r.attribute == "mood")
        assert w.classifier.get(row.id) is not None
        assert w.state(f"person:p{i}", "mood").winner.value == "x"
    w.close()


def test_inline_default_is_per_row(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "i.world", world_id="w:i", model=stub)
    items = [{"entity": f"person:p{i}", "attribute": "mood", "value": "x", "valid_from": 1.0}
             for i in range(3)]
    w.porcelain.ingest_structured(items)                 # default classify="inline"
    classify_calls = [c for c in stub.calls if c[0].startswith("Classify the lifetime")]
    assert len(classify_calls) == 3                      # one per row
    w.close()


def test_batch_guardrail_rows_make_no_model_call(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "g.world", world_id="w:g", model=stub)
    # all-structural rows (kind / place containment) classify via guardrails
    w.porcelain.ingest_structured([
        {"entity": "place:a", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:b", "attribute": "kind", "value": "place", "timeless": True},
    ], classify="batch")
    assert not [c for c in stub.calls if c[0].startswith("Classify the lifetime")]
    w.close()


def test_batch_self_edge_still_skipped(world):
    # the durability-independent self-edge guard fires even under batch
    r = world.porcelain.ingest_structured([
        {"entity": "place:loop", "attribute": "in", "value": "place:loop", "timeless": True},
        {"entity": "place:loop", "attribute": "kind", "value": "place", "timeless": True},
    ], classify="batch")
    assert any("self-edge" in s["reason"] for s in r.skipped)
    assert world.state("place:loop", "in").winner is None


# --------------------------------------------------- Part B: edge-granular skip

def test_good_rows_survive_one_bad_edge(world):
    # one cycle-forming edge in a chunk does NOT discard the good rows
    world.ingest_structured([
        {"entity": "obj:a", "attribute": "in", "value": "obj:b", "valid_from": 1.0},
    ])
    r = world.porcelain.ingest_structured([
        {"entity": "obj:b", "attribute": "color", "value": "red", "valid_from": 2.0},     # good
        {"entity": "obj:b", "attribute": "in", "value": "obj:a", "valid_from": 2.0},       # cycle
        {"entity": "obj:b", "attribute": "size", "value": "small", "valid_from": 2.0},     # good
    ])
    assert world.state("obj:b", "color").winner.value == "red"
    assert world.state("obj:b", "size").winner.value == "small"
    assert world.state("obj:b", "in").winner is None                  # the cycle edge dropped
    assert len(r.skipped) == 1 and "ancestor" in r.skipped[0]["reason"]


def test_skip_record_shape(world):
    r = world.porcelain.ingest_structured([
        {"entity": "place:x", "attribute": "in", "value": "place:x", "timeless": True},
    ])
    s = r.skipped[0]
    assert s["entity"] == "place:x" and s["attribute"] == "in" and s["value"] == "place:x"
    assert "self-edge" in s["reason"]


def test_other_gate_failures_still_raise(world):
    # generated-into-canon is a genuine authority failure — still raises, not skipped
    with pytest.raises(ValueError, match="generated"):
        world.ingest_structured([
            {"entity": "obj:y", "attribute": "state", "value": "x",
             "status": "generated", "frame": "canon"},
        ])


def test_generated_self_edge_raises_not_skipped(world):
    # Cx final: an authority violation (generated-into-canon) must RAISE even
    # when the row is ALSO a structurally-invalid edge — the skip must not
    # swallow it.
    with pytest.raises(ValueError, match="generated"):
        world.ingest_structured([
            {"entity": "place:z", "attribute": "in", "value": "place:z",
             "status": "generated", "frame": "canon", "timeless": True},
        ])


def test_last_skipped_not_stale_after_raise(world):
    # Cx final: a skip in one call must not linger in last_skipped after a later
    # call raises mid-batch.
    world.porcelain.ingest_structured([
        {"entity": "place:x", "attribute": "in", "value": "place:x", "timeless": True},
    ])
    assert len(world.ingestor.last_skipped) == 1
    with pytest.raises(ValueError, match="generated"):
        world.ingest_structured([
            {"entity": "obj:ok", "attribute": "color", "value": "red", "valid_from": 1.0},
            {"entity": "obj:bad", "attribute": "state", "value": "x",
             "status": "generated", "frame": "canon"},
        ])
    assert world.ingestor.last_skipped == []   # this call had no skips; no stale carryover


def test_last_skipped_resets_each_call(world):
    world.porcelain.ingest_structured([
        {"entity": "place:x", "attribute": "in", "value": "place:x", "timeless": True},
    ])
    assert len(world.ingestor.last_skipped) == 1
    r = world.porcelain.ingest_structured([
        {"entity": "place:y", "attribute": "kind", "value": "place", "timeless": True},
    ])
    assert r.skipped == []                               # reset; no stale carryover
    assert world.ingestor.last_skipped == []
