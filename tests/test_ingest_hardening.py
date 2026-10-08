"""INGEST-HARDENING-V1: batched durability mode + edge-granular cycle rejection.

Part A — `p.ingest_structured(items, classify="batch")` defers classification and
runs ONE batch model call per ingest call (the first-class form of the manual
classify_inline=False + classify_all recipe). Part B — a single structurally-
invalid edge is skipped with a typed receipt, not aborting the chunk.
"""

import math

import pytest

from patternbuffer import AtomicAbort, World
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


# ------------------------- FOLD-CORRECTNESS-V1 §6: time values are numbers

@pytest.mark.parametrize("field", ["valid_from", "valid_to"])
@pytest.mark.parametrize("bad", ["spring 1660", float("nan"), float("inf"), True],
                         ids=["text", "nan", "inf", "bool"])
def test_invalid_time_value_is_skipped_with_a_receipt(world, bad, field):
    r = world.porcelain.ingest_structured([
        {"entity": "person:anne", "attribute": "in", "value": "place:hall",
         "valid_from": 1.0},
        {"entity": "person:anne", "attribute": "in", "value": "place:garden",
         "valid_from": 2.0, field: bad},
    ])
    assert len(r.skipped) == 1
    s = r.skipped[0]
    assert s["reason"] == "invalid_valid_time"
    assert (s["entity"], s["attribute"], s["value"]) == ("person:anne", "in", "place:garden")
    if isinstance(bad, float) and math.isnan(bad):
        assert math.isnan(s["detail"])
    else:
        assert s["detail"] == bad and type(s["detail"]) is type(bad)
    assert not [row for row in world.buffer.all_rows() if row.value == "place:garden"]
    # reads on the key keep working (today: a text valid_from was admitted
    # and crashed state/locate/snapshot; NaN was stored as NULL — timeless)
    assert world.state("person:anne", "in").winner.value == "place:hall"
    assert world.locate("person:anne") == ["place:hall"]
    assert world.porcelain.snapshot("person:anne")["facts"]


def test_integer_year_is_admitted(world):
    r = world.porcelain.ingest_structured([
        {"entity": "person:anne", "attribute": "in", "value": "place:hall",
         "valid_from": 1660},
    ])
    assert r.skipped == []
    assert world.state("person:anne", "in").winner.valid_from == 1660
    assert world.locate("person:anne", valid_as_of=1661) == ["place:hall"]


def test_invalid_time_value_aborts_an_atomic_set(world):
    head = world.buffer.head()
    with pytest.raises(AtomicAbort) as exc:
        world.porcelain.ingest_structured([
            {"entity": "person:anne", "attribute": "in", "value": "place:hall",
             "valid_from": 1.0},
            {"entity": "person:anne", "attribute": "in", "value": "place:garden",
             "valid_from": "spring 1660"},
        ], classify="rules", atomic=True)
    assert exc.value.cause == "gate_skip"
    assert exc.value.skipped == [{
        "entity": "person:anne", "attribute": "in", "value": "place:garden",
        "reason": "invalid_valid_time", "detail": "spring 1660"}]
    assert world.buffer.head() == head               # nothing committed


def test_cursor_authoritative_text_time_is_demoted_not_skipped(world):
    # The check runs AFTER cursor stamping: a cursor-authoritative build keeps
    # its dated text losslessly in source_valid_from, as before.
    world.ingestor.cursor.advance(3.0)
    r = world.porcelain.ingest_structured([
        {"entity": "person:anne", "attribute": "in", "value": "place:hall",
         "valid_from": "spring 1660"},
    ], cursor_authoritative=True)
    assert r.skipped == []
    assert world.state("person:anne", "in").winner.valid_from == 3.0
    assert [row.value for row in world.buffer.all_rows()
            if row.attribute == "source_valid_from"] == ["spring 1660"]


def test_numeric_string_and_oversize_int_times_are_coerced(tmp_path) -> None:
    """FOLD-CORRECTNESS-V1 pre-review finding 3/nit: "1660" (SQLite used to
    coerce it silently) and an int past 64 bits are coordinates, not skips."""
    from patternbuffer import World

    w = World(tmp_path / "t.world", world_id="w:t")
    try:
        r = w.porcelain.ingest_structured([
            {"entity": "person:a", "attribute": "in", "value": "room:x",
             "valid_from": "1660"},
            {"entity": "person:b", "attribute": "in", "value": "room:x",
             "valid_from": 2 ** 70},
        ], classify="rules")
        assert r.skipped == []
        assert w.state("person:a", "in").winner.valid_from == 1660.0
        assert w.state("person:b", "in").winner.valid_from == float(2 ** 70)
    finally:
        w.close()


# ------------------------------------- GATE-INVERSE-ALIAS-V1: inverse predicates

def _receipts(w):
    return [r.value for r in w.buffer.visible(attribute="canonicalized_from")]


def _seed_prefix_row(w, entity, attribute, value, receipt, frame="canon"):
    """Build the PRE-FIX state honestly: the old gate renamed without swapping
    and left a forward receipt. The new gate cannot write this shape, so append
    the two rows through the buffer (GATE-INVERSE-ALIAS-V1 §4/§5 tests)."""
    role = w.ingestor._role
    row = w.buffer.append(entity=entity, attribute=attribute, value=value,
                          value_type="entity", valid_from=1.0, frame=frame,
                          status="stated", role=role)
    rec = w.buffer.append(entity=row.id, attribute="canonicalized_from",
                          value=receipt, status="inferred", role=role)
    return row, rec


def _reopen(path, wid):
    return World(path, world_id=wid, model=StubModel(fallback=rule_classifier_fallback()))


@pytest.mark.parametrize("inverse,forward", [("holds", "held_by"), ("wearing", "worn_by")])
def test_inverse_entity_value_swaps(world, inverse, forward):
    # GATE-INVERSE-ALIAS-V1 §2: (ralph holds key) is stored (key held_by ralph).
    world.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "person:ralph", "attribute": "in", "value": "place:hall", "valid_from": 1.0},
        {"entity": "person:ralph", "attribute": inverse, "value": "obj:key", "valid_from": 1.0},
    ])
    assert world.locate("obj:key") == ["person:ralph", "place:hall"]
    assert world.locate("person:ralph") == ["place:hall"]          # unchanged
    assert f"{inverse}->{forward} (inverse)" in _receipts(world)
    assert not any(r.attribute == inverse for r in world.buffer.all_rows())


def test_inverse_follow_up_not_refused_as_cycle(world):
    # §2 again: the correctly-directed follow-up is admitted, not a cycle.
    world.ingest_structured([
        {"entity": "person:ralph", "attribute": "holds", "value": "obj:key", "valid_from": 1.0},
    ])
    r = world.porcelain.ingest_structured([
        {"entity": "obj:key", "attribute": "held_by", "value": "person:ralph", "valid_from": 2.0},
    ])
    assert r.skipped == []


def test_inverse_item_identity_data_stays_with_original_subject(world):
    # §2 identity data: aliases describe the item's subject (ralph), not the key.
    world.ingest_structured([
        {"entity": "person:ralph", "attribute": "holds", "value": "obj:key",
         "valid_from": 1.0, "aliases": ["the keeper"]},
    ])
    alias_rows = [r for r in world.buffer.all_rows() if r.attribute == "alias"]
    assert [(r.entity, r.value) for r in alias_rows] == [("person:ralph", "the keeper")]


@pytest.mark.parametrize("inverse", ["holds", "wearing"])
def test_inverse_text_value_is_not_aliased(world, inverse):
    # §3: a text value stays a literal domain fact; ralph keeps his location.
    world.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "person:ralph", "attribute": "in", "value": "place:hall", "valid_from": 1.0},
        {"entity": "person:ralph", "attribute": inverse, "value": "a lantern", "valid_from": 1.0},
    ])
    assert world.locate("person:ralph") == ["place:hall"]
    row = next(r for r in world.buffer.all_rows()
               if r.entity == "person:ralph" and r.attribute == inverse)
    assert row.value == "a lantern"
    assert _receipts(world) == []


def test_old_forward_receipt_does_not_resurrect_alias(tmp_path):
    # §4: a world carrying an old `holds->held_by` receipt, after reopen, still
    # swaps new holds items (built-ins beat replayed receipts).
    path = tmp_path / "old.world"
    w = _reopen(path, "w:old")
    _seed_prefix_row(w, "person:ann", "held_by", "obj:ring", "holds->held_by")
    w.close()
    w = _reopen(path, "w:old")
    assert "holds" not in w.ingestor._alias_map
    w.ingest_structured([
        {"entity": "person:ralph", "attribute": "holds", "value": "obj:key", "valid_from": 5.0},
    ])
    assert w.locate("obj:key") == ["person:ralph"]
    assert "holds->held_by (inverse)" in _receipts(w)
    w.close()


def test_inverse_receipt_is_not_a_map_entry(tmp_path):
    # §4: "(inverse)" receipts are records, never replayed as map entries.
    path = tmp_path / "rec.world"
    w = _reopen(path, "w:rec")
    w.ingest_structured([
        {"entity": "person:ralph", "attribute": "wearing", "value": "obj:coat", "valid_from": 1.0},
    ])
    w.close()
    w = _reopen(path, "w:rec")
    assert "wearing" not in w.ingestor._alias_map
    assert not any("(inverse)" in v for v in w.ingestor._alias_map.values())
    w.close()


def test_recipe_finds_exactly_prefix_rows(world):
    # §5 (r1.1 output shape): ADOPTION's recipe, verbatim, yields per inverted
    # row {assertion_id, frame, entity, attribute, value, receipt_id}.
    p = world.porcelain
    bad1, rec1 = _seed_prefix_row(world, "person:ann", "held_by", "obj:ring", "holds->held_by")
    bad2, rec2 = _seed_prefix_row(world, "person:bo", "worn_by", "obj:hat", "wearing->worn_by",
                                  frame="knows:person:bo")
    # decoys: a correctly-directed hand-written row, and a post-fix swapped row
    world.ingest_structured([
        {"entity": "obj:cup", "attribute": "held_by", "value": "person:ann", "valid_from": 2.0},
        {"entity": "person:cy", "attribute": "holds", "value": "obj:pen", "valid_from": 2.0},
    ])
    host_frames = ["canon", "knows:person:bo"]
    receipt_of = {f["entity"]: f["provenance"]["assertion_id"]
                  for f in p.facts("canon", attribute="canonicalized_from", include_meta=True)
                  if f["value"] in ("holds->held_by", "wearing->worn_by")}
    inverted = []
    for frame in host_frames:
        for f in p.facts(frame, attribute="held_by") + p.facts(frame, attribute="worn_by"):
            aid = f["provenance"]["assertion_id"]
            if aid in receipt_of:
                inverted.append({"assertion_id": aid, "frame": frame,
                                 "entity": f["entity"], "attribute": f["attribute"],
                                 "value": f["value"], "receipt_id": receipt_of[aid]})
    key = lambda d: d["assertion_id"]
    assert sorted(inverted, key=key) == sorted([
        {"assertion_id": bad1.id, "frame": "canon", "entity": "person:ann",
         "attribute": "held_by", "value": "obj:ring", "receipt_id": rec1.id},
        {"assertion_id": bad2.id, "frame": "knows:person:bo", "entity": "person:bo",
         "attribute": "worn_by", "value": "obj:hat", "receipt_id": rec2.id},
    ], key=key)


def test_inverse_swap_inside_atomic_unit(world):
    # atomic=True: a swapped item commits inside the unit.
    world.porcelain.ingest_structured([
        {"entity": "person:ralph", "attribute": "holds", "value": "obj:key", "valid_from": 1.0},
        {"entity": "person:ralph", "attribute": "wearing", "value": "obj:coat", "valid_from": 1.0},
    ], atomic=True, classify="rules")
    assert world.locate("obj:key") == ["person:ralph"]
    assert world.locate("obj:coat") == ["person:ralph"]
