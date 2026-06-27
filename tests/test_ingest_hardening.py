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


# --------------------------------------- Part A on the TEXT path (HD 079)

def test_text_ingest_batch_one_classify_call(tmp_path):
    # p.ingest(text, classify="batch") => one batch durability call for the whole
    # passage, not one per extracted row (the per-turn live-play latency lever).
    extraction = {"items": [
        {"entity": f"person:p{i}", "attribute": "mood", "value": "x", "valid_from": 1.0}
        for i in range(4)
    ]}
    stub = StubModel(responses=[extraction], fallback=rule_classifier_fallback())
    w = World(tmp_path / "t.world", world_id="w:t", model=stub)
    w.porcelain.ingest("some prose", classify="batch")
    classify_calls = [c for c in stub.calls if c[0].startswith("Classify the lifetime")]
    assert len(classify_calls) == 1                       # one batch, not four
    assert len([c for c in stub.calls if "Extract world-state" in c[0]]) == 1
    for i in range(4):
        assert w.state(f"person:p{i}", "mood").winner.value == "x"
    w.close()


def test_text_ingest_defer_no_classify_call(tmp_path):
    extraction = {"items": [
        {"entity": "person:p", "attribute": "mood", "value": "x", "valid_from": 1.0}]}
    stub = StubModel(responses=[extraction], fallback=rule_classifier_fallback())
    w = World(tmp_path / "d.world", world_id="w:d", model=stub)
    w.porcelain.ingest("prose", classify="defer")
    assert not [c for c in stub.calls if c[0].startswith("Classify the lifetime")]
    assert w.state("person:p", "mood").winner.value == "x"   # folds (unclassified -> STATE)
    w.close()


# --------------------------------------- INGEST-LATENCY-V2 (HD 083/084)

def test_classify_rules_zero_lm_calls(tmp_path):
    from patternbuffer.classify import CONSTITUTIVE, STATE
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "r.world", world_id="w:r", model=stub)
    w.porcelain.ingest_structured([
        {"entity": "place:a", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "obj:box", "attribute": "in", "value": "place:a",
         "value_type": "entity", "valid_from": 1.0},          # ambiguous obj containment
        {"entity": "obj:box", "attribute": "color", "value": "red", "valid_from": 1.0},
    ], classify="rules")
    assert not [c for c in stub.calls if c[0].startswith("Classify the lifetime")]  # zero LM
    kind = next(r for r in w.buffer.all_rows() if r.attribute == "kind")
    assert w.classifier.durability(kind.id) == CONSTITUTIVE   # guardrail
    box_in = next(r for r in w.buffer.all_rows() if r.attribute == "in")
    assert w.classifier.durability(box_in.id) == STATE        # ambiguous -> STATE (supersedes)
    color = next(r for r in w.buffer.all_rows() if r.attribute == "color")
    assert w.classifier.durability(color.id) == STATE
    w.close()


def test_extract_read_only_and_composes(tmp_path):
    ext = {"items": [
        {"entity": "person:p", "attribute": "mood", "value": "x", "valid_from": 1.0}]}
    stub = StubModel(responses=[ext], fallback=rule_classifier_fallback())
    w = World(tmp_path / "x.world", world_id="w:x", model=stub)
    head = w.buffer.head()
    items = w.extract("prose")
    assert items == ext["items"]                              # raw items
    assert w.buffer.head() == head                           # extract writes NOTHING
    w.ingest_structured(items, classify="defer")             # host ingests serially
    assert w.state("person:p", "mood").winner.value == "x"
    w.close()


def test_cursor_authoritative_governs_valid_from(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "c.world", world_id="w:c", model=stub)
    w.ingestor.cursor.advance(8.0)
    w.ingest_structured([
        {"entity": "event:opening", "attribute": "mood", "value": "tense", "valid_from": 612.0},
        {"entity": "event:opening", "attribute": "kind", "value": "event", "timeless": True},
    ], classify="defer", cursor_authoritative=True)
    mood = next(r for r in w.buffer.all_rows() if r.attribute == "mood")
    assert mood.valid_from == 8.0                            # cursor, NOT 612
    svf = [r for r in w.buffer.all_rows() if r.attribute == "source_valid_from"]
    assert len(svf) == 1 and svf[0].value == 612.0          # 612 preserved (not lost)
    kind = next(r for r in w.buffer.all_rows() if r.attribute == "kind")
    assert kind.valid_from is None                           # timeless unaffected, no demote
    m = w.materialize(["event:opening"])
    assert not any(r.attribute == "source_valid_from" for r in m.assertions)  # meta-hidden
    w.close()


def test_cursor_authoritative_monotone_across_chunks(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "m.world", world_id="w:m", model=stub)
    w.ingestor.cursor.advance(5.0)
    w.ingest_structured([{"entity": "event:a", "attribute": "x", "value": "1",
                          "valid_from": 612.0}], classify="defer", cursor_authoritative=True)
    w.ingestor.cursor.advance(10.0)
    w.ingest_structured([{"entity": "event:b", "attribute": "x", "value": "2",
                          "valid_from": 3.0}], classify="defer", cursor_authoritative=True)
    a = next(r for r in w.buffer.all_rows() if r.entity == "event:a" and r.attribute == "x")
    b = next(r for r in w.buffer.all_rows() if r.entity == "event:b" and r.attribute == "x")
    assert a.valid_from == 5.0 and b.valid_from == 10.0     # monotone by chunk order
    w.close()


def test_cursor_authoritative_default_off(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "o.world", world_id="w:o", model=stub)
    w.ingest_structured([{"entity": "event:a", "attribute": "x", "value": "1",
                          "valid_from": 612.0}], classify="defer")
    a = next(r for r in w.buffer.all_rows() if r.attribute == "x")
    assert a.valid_from == 612.0                             # default: per-item wins
    assert not [r for r in w.buffer.all_rows() if r.attribute == "source_valid_from"]
    w.close()


# --------------------------------------- lean extraction prompt (HD 082)

def test_lean_extraction_trims_prompt_keeps_loadbearing(tmp_path):
    ext = {"items": [
        {"entity": "person:p", "attribute": "mood", "value": "x", "valid_from": 1.0}]}
    stub = StubModel(responses=[ext, ext], fallback=rule_classifier_fallback())
    w = World(tmp_path / "e.world", world_id="w:e", model=stub)
    # classify="defer" so the scripted responses map 1:1 to the two extractions
    # (no inline classify calls consuming them); the extract prompt is what we test.
    w.porcelain.ingest("prose one", extract="full", classify="defer")
    w.porcelain.ingest("prose two", extract="lean", classify="defer")
    extract_prompts = [c[0] for c in stub.calls if c[0].startswith("Extract world-state")]
    full_p, lean_p = extract_prompts[0], extract_prompts[1]
    assert len(lean_p) < len(full_p)                      # trimmed
    assert "DOCUMENT CLAIMS" in full_p and "DOCUMENT CLAIMS" not in lean_p  # rare rule dropped
    # load-bearing rules survive in lean
    for keep in ("namespaced", "connects_to", "knows:", "NEVER invent", "timeless"):
        assert keep in lean_p
    assert w.state("person:p", "mood").winner.value == "x"  # extraction still works
    w.close()


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
