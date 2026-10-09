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
    assert f"(inverse) {inverse}->{forward}" in _receipts(world)
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
    assert "(inverse) holds->held_by" in _receipts(w)
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
    assert not any("(inverse)" in k or "(inverse)" in v
                   for k, v in w.ingestor._alias_map.items())
    w.close()


def _run_adoption_recipe(p, host_frames):
    """Execute ADOPTION.md's recipe block VERBATIM (the doc cannot drift from
    the test) and return its namespace."""
    import re
    from pathlib import Path
    doc = (Path(__file__).resolve().parent.parent / "docs" / "ADOPTION.md").read_text()
    m = re.search(r"<!-- recipe:inverted-rows[^>]*-->\s*```python\n(.*?)```", doc, re.S)
    assert m, "recipe block missing from docs/ADOPTION.md"
    code = "\n".join(l[2:] if l.startswith("  ") else l for l in m.group(1).split("\n"))
    ns = {"p": p, "host_frames": host_frames}
    exec(code, ns)
    return ns


def _seed_prefix_world(w):
    """Pre-fix state: receipted rows, a receipt-less copy in canon of a
    knows:-frame receipted row, a text-valued row, a duplicated pair, and decoys."""
    rows = {}
    rows["ann"] = _seed_prefix_row(w, "person:ann", "held_by", "obj:ring", "holds->held_by")
    rows["bo"] = _seed_prefix_row(w, "person:bo", "worn_by", "obj:hat", "wearing->worn_by",
                                  frame="knows:person:bo")
    role = w.ingestor._role
    # receipt-less copy of bo's triple, in ANOTHER frame (a re-ingested promotion)
    rows["bo_copy"] = (w.buffer.append(entity="person:bo", attribute="worn_by", value="obj:hat",
                                       value_type="entity", valid_from=1.0, frame="canon",
                                       status="stated", role=role), None)
    # two copies of one triple in ONE frame, one receipt-less, interval kept
    rows["dee1"] = _seed_prefix_row(w, "person:dee", "held_by", "obj:map", "holds->held_by")
    rows["dee2"] = (w.buffer.append(entity="person:dee", attribute="held_by", value="obj:map",
                                    value_type="entity", valid_from=1.0, valid_to=9.0,
                                    frame="canon", status="stated", role=role), None)
    # text-valued inverted row
    w_row = w.buffer.append(entity="person:ed", attribute="held_by", value="a lantern",
                            value_type="literal", valid_from=2.0, frame="canon",
                            status="stated", role=role)
    rec = w.buffer.append(entity=w_row.id, attribute="canonicalized_from",
                          value="holds->held_by", status="inferred", role=role)
    rows["ed"] = (w_row, rec)
    # decoys: a correctly-directed hand-written row, and a post-fix swapped row
    w.ingest_structured([
        {"entity": "obj:cup", "attribute": "held_by", "value": "person:ann", "valid_from": 2.0},
        {"entity": "person:cy", "attribute": "holds", "value": "obj:pen", "valid_from": 2.0},
    ])
    return rows


def test_recipe_finds_prefix_rows_and_receiptless_copies(world):
    # §5 (r1.2): per inverted row {assertion_id, frame, entity, attribute, value,
    # value_type, valid, receipt_id}; receipt-less copies of a receipted triple
    # are reported with receipt_id None; decoys and post-fix rows are not.
    rows = _seed_prefix_world(world)
    ns = _run_adoption_recipe(world.porcelain, ["canon", "knows:person:bo"])
    got = {d["assertion_id"]: d for d in ns["inverted"]}
    expected = {rows[k][0].id: (rows[k][1].id if rows[k][1] is not None else None)
                for k in ("ann", "bo", "bo_copy", "dee1", "dee2", "ed")}
    assert {a: d["receipt_id"] for a, d in got.items()} == expected
    d = got[rows["bo"][0].id]
    assert d == {"assertion_id": rows["bo"][0].id, "frame": "knows:person:bo",
                 "entity": "person:bo", "attribute": "worn_by", "value": "obj:hat",
                 "value_type": "entity", "valid": [1.0, None],
                 "receipt_id": rows["bo"][1].id}
    assert got[rows["ed"][0].id]["value_type"] == "literal"
    assert got[rows["dee2"][0].id]["valid"] == [1.0, 9.0]


def test_unrepaired_inverse_refuses_correct_write_and_aborts_atomic(world):
    # ADOPTION: until repair, the CORRECT write on the pair is skipped as a
    # cycle, and an atomic set containing it aborts.
    from patternbuffer.tmaint import AtomicAbort
    _seed_prefix_row(world, "person:ann", "held_by", "obj:ring", "holds->held_by")
    fix = {"entity": "obj:ring", "attribute": "held_by", "value": "person:ann", "valid_from": 3.0}
    r = world.porcelain.ingest_structured([fix])
    assert [s["reason"] for s in r.skipped] and "cycle" in r.skipped[0]["reason"]
    with pytest.raises(AtomicAbort) as ei:
        world.porcelain.ingest_structured([fix], atomic=True, classify="rules")
    assert ei.value.cause == "gate_skip"


def test_grouped_repair_via_commit_set(world):
    # §5: group by (frame, triple); retract all copies, assert once. A per-row
    # repair would refuse the second copy as a cycle. Text rows become a
    # literal holds (never a swap); the original interval is kept.
    rows = _seed_prefix_world(world)
    p = world.porcelain
    ns = _run_adoption_recipe(p, ["canon", "knows:person:bo"])
    assert len(ns["groups"]) == 5          # ann, bo(knows), bo(canon copy), dee(x2 -> one), ed
    for g in ns["groups"].values():
        p.commit_set(ns["repair_ops"](g))
    assert _run_adoption_recipe(p, ["canon", "knows:person:bo"])["inverted"] == []
    assert world.locate("obj:ring") == ["person:ann"]
    assert world.locate("obj:map") == ["person:dee"]
    ed = [r for r in world.buffer.visible() if r.entity == "person:ed" and r.attribute == "holds"]
    assert [(r.value, r.value_type, r.valid_from) for r in ed] == [("a lantern", "literal", 2.0)]
    assert not any(r.attribute == "held_by" and r.entity == "person:ed"
                   for r in world.buffer.visible())
    mapx = [r for r in world.buffer.visible()
            if r.entity == "obj:map" and r.attribute == "held_by"]
    assert [(r.value, r.valid_from, r.valid_to) for r in mapx] == [("person:dee", 1.0, None)]   # earliest-starting copy; ties: first


def test_swapped_skip_record_carries_authored_form(world):
    # §2/nit 6: a skip on a swapped item names the authored form; `detail` is
    # absent from unswapped skips (byte-identical wire form).
    _seed_prefix_row(world, "person:ralph", "held_by", "obj:bag", "holds->held_by")
    r = world.porcelain.ingest_structured([
        {"entity": "person:ralph", "attribute": "holds", "value": "obj:bag", "valid_from": 2.0},
        {"entity": "obj:bag", "attribute": "in", "value": "obj:bag", "valid_from": 2.0},
    ])
    assert r.skipped[0]["detail"] == "authored: person:ralph holds obj:bag"
    assert r.skipped[0]["entity"] == "obj:bag" and r.skipped[0]["attribute"] == "held_by"
    assert "detail" not in r.skipped[1]


def test_add_attribute_alias_rejects_inverse_keys(world):
    for key in ("holds", "wearing", " Holds "):
        with pytest.raises(ValueError):
            world.ingestor.add_attribute_alias(key, "held_by")


def test_host_override_of_builtin_alias_survives_reopen(tmp_path):
    # nit 7: built-ins -> receipts -> pop inverse keys, so a host override
    # (type->genre) outranks the built-in (type->kind) after reopen.
    path = tmp_path / "ov.world"
    w = _reopen(path, "w:ov")
    w.ingestor.add_attribute_alias("type", "genre")
    w.ingest_structured([{"entity": "doc:book", "attribute": "type", "value": "novel",
                          "valid_from": 1.0}])
    assert any(r.attribute == "genre" for r in w.buffer.all_rows())
    w.close()
    w = _reopen(path, "w:ov")
    assert w.ingestor._alias_map["type"] == "genre"
    assert w.ingestor._alias_map["is_a"] == "kind"           # other built-ins intact
    assert "holds" not in w.ingestor._alias_map
    w.close()


def test_inverse_receipt_is_not_a_forward_alias_for_an_older_engine(tmp_path):
    # nit 8: the pre-swap engine (4404cc0) replays every `src->dst` receipt via
    # split("->", 1). A post-fix receipt must yield a source that never occurs.
    path = tmp_path / "old_engine.world"
    w = _reopen(path, "w:oe")
    w.ingest_structured([
        {"entity": "person:ralph", "attribute": "holds", "value": "obj:key", "valid_from": 1.0},
        {"entity": "person:ralph", "attribute": "wearing", "value": "obj:coat", "valid_from": 1.0},
    ])

    def base_rebuild(buffer):          # verbatim logic of 4404cc0 _rebuild_alias_map
        from patternbuffer.ingest import _BUILTIN_ALIASES
        m = dict(_BUILTIN_ALIASES)
        for row in buffer.visible(attribute="canonicalized_from"):
            if isinstance(row.value, str) and "->" in row.value:
                src, dst = row.value.split("->", 1)
                m[src.strip()] = dst.strip()
        return m

    old = base_rebuild(w.buffer)
    assert w.ingestor._alias_map == {k: v for k, v in old.items()
                                     if not k.startswith("(inverse)")}
    for attr in ("holds", "wearing", "held_by", "worn_by"):
        assert attr not in old                       # nothing an attribute can match
    assert all(k.startswith("(inverse)") for k in set(old) - set(w.ingestor._alias_map))
    w.close()


def test_extractor_prompts_read_consistently():
    from patternbuffer.ingest import _EXTRACT_RULES_FULL, _EXTRACT_RULES_LEAN
    for rules in (_EXTRACT_RULES_FULL, _EXTRACT_RULES_LEAN):
        assert "held_by <person>" in rules and "worn_by <person>" in rules
        assert "physically held or carried" in rules
        assert "possession" not in rules
        assert "GATE-INVERSE-ALIAS" not in rules
        assert "all containment" not in rules


def test_inverse_swap_inside_atomic_unit(world):
    # atomic=True: a swapped item commits inside the unit.
    world.porcelain.ingest_structured([
        {"entity": "person:ralph", "attribute": "holds", "value": "obj:key", "valid_from": 1.0},
        {"entity": "person:ralph", "attribute": "wearing", "value": "obj:coat", "valid_from": 1.0},
    ], atomic=True, classify="rules")
    assert world.locate("obj:key") == ["person:ralph"]
    assert world.locate("obj:coat") == ["person:ralph"]
