"""EXACT-DECIMAL-QUANTITIES-V1: exact money without a float membrane.

A quantity that must fold exactly is a Decimal in memory and the reserved
tag dict {"$decimal": "12.50"} on every JSON boundary. Invariants: exact
accrue folds; authored scale preserved through dump/build; Decimal+float
mixing raises; the collision guard never coerces host dicts; every default
(non-decimal) path is byte-unchanged; porcelain payloads stay plain-JSON.
"""

import json
from decimal import Decimal, getcontext, localcontext

import pytest

from patternbuffer import World
from patternbuffer.codec import DEC_TAG, decode_value, encode_out, encode_value
from patternbuffer.dump import build, dump
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "dec.world", world_id="w:dec", model=stub)
    yield w
    w.close()


def _declare_accrue(w, attribute="balance"):
    w.ingest_structured([
        {"entity": f"attr:{attribute}", "attribute": "fold_policy",
         "value": "accrue", "timeless": True},
    ])


# ------------------------------------------------------------- exactness

def test_accrue_folds_decimal_exactly(world):
    _declare_accrue(world)
    world.ingest_structured([
        {"entity": "acct:a", "attribute": "kind", "value": "account", "timeless": True},
        {"entity": "acct:a", "attribute": "balance", "value": Decimal("0.10"),
         "valid_from": 1.0},
        {"entity": "acct:a", "attribute": "balance", "value": Decimal("0.20"),
         "value_type": "delta", "valid_from": 2.0},
    ])
    fold = world.state("acct:a", "balance")
    assert fold.quantity == Decimal("0.30")          # float path gives 0.30000000000000004
    assert isinstance(fold.quantity, Decimal)


def test_long_delta_chain_is_exact(world):
    _declare_accrue(world)
    items = [{"entity": "acct:b", "attribute": "kind", "value": "account",
              "timeless": True},
             {"entity": "acct:b", "attribute": "balance", "value": Decimal("0.00"),
              "valid_from": 0.0}]
    items += [
        {"entity": "acct:b", "attribute": "balance", "value": Decimal("0.01"),
         "value_type": "delta", "valid_from": float(i)}
        for i in range(1, 1001)
    ]
    world.ingest_structured(items, classify="rules")
    assert world.state("acct:b", "balance").quantity == Decimal("10.00")


# ------------------------------------------------------------- round-trip

def test_dump_build_preserves_decimal_and_scale(world, tmp_path):
    world.ingest_structured([
        {"entity": "acct:c", "attribute": "kind", "value": "account", "timeless": True},
        {"entity": "acct:c", "attribute": "balance", "value": Decimal("12.50"),
         "valid_from": 1.0},
    ])
    jsonl = dump(world.buffer)
    assert f'"{DEC_TAG}": "12.50"' in jsonl.replace('": "', '": "') or DEC_TAG in jsonl
    rebuilt = build(jsonl, tmp_path / "rebuilt.world")
    try:
        row = [r for r in rebuilt.all_rows() if r.attribute == "balance"][0]
        assert isinstance(row.value, Decimal)
        assert str(row.value) == "12.50"              # trailing zero preserved
        assert dump(rebuilt) == jsonl                 # byte-identical round-trip
    finally:
        rebuilt.close()


def test_ingest_symmetry_tag_form_equals_decimal(world):
    world.ingest_structured([
        {"entity": "acct:d", "attribute": "kind", "value": "account", "timeless": True},
        {"entity": "acct:d", "attribute": "balance", "value": {DEC_TAG: "12.50"},
         "valid_from": 1.0},
        {"entity": "acct:e", "attribute": "kind", "value": "account", "timeless": True},
        {"entity": "acct:e", "attribute": "balance", "value": Decimal("12.50"),
         "valid_from": 1.0},
    ])
    rows = {r.entity: r for r in world.buffer.visible(attribute="balance")}
    assert rows["acct:d"].value == rows["acct:e"].value == Decimal("12.50")
    assert isinstance(rows["acct:d"].value, Decimal)


# ------------------------------------------------------------- mixing rule

def test_decimal_plus_float_raises(world):
    _declare_accrue(world)
    world.ingest_structured([
        {"entity": "acct:f", "attribute": "kind", "value": "account", "timeless": True},
        {"entity": "acct:f", "attribute": "balance", "value": Decimal("1.00"),
         "valid_from": 1.0},
        {"entity": "acct:f", "attribute": "balance", "value": 0.5,
         "value_type": "delta", "valid_from": 2.0},
    ])
    with pytest.raises(ValueError, match="mixed"):
        world.state("acct:f", "balance")


def test_decimal_plus_int_folds_exactly(world):
    _declare_accrue(world)
    world.ingest_structured([
        {"entity": "acct:g", "attribute": "kind", "value": "account", "timeless": True},
        {"entity": "acct:g", "attribute": "balance", "value": Decimal("1.25"),
         "valid_from": 1.0},
        {"entity": "acct:g", "attribute": "balance", "value": 2,
         "value_type": "delta", "valid_from": 2.0},
    ])
    assert world.state("acct:g", "balance").quantity == Decimal("3.25")


# ------------------------------------------------------------- collision guard

def test_collision_guard_passes_host_dicts_through(world):
    for bad in ({DEC_TAG: "x", "note": 1}, {DEC_TAG: "NaN"},
                {DEC_TAG: "Infinity"}, {DEC_TAG: "hi"}):
        assert decode_value(bad) == bad               # never coerced
    world.ingest_structured([
        {"entity": "obj:o", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:o", "attribute": "note", "value": {DEC_TAG: "not-a-number"},
         "valid_from": 1.0},
    ])
    row = world.buffer.visible(attribute="note")[0]
    assert row.value == {DEC_TAG: "not-a-number"}     # stored + read back as the dict


# ------------------------------------------------------------- determinism

def test_avg_uses_fixed_context_not_ambient(world):
    _declare_accrue(world)
    world.ingest_structured([
        {"entity": "box:h", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "coin:1", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "coin:2", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "coin:1", "attribute": "in", "value": "box:h", "valid_from": 1.0},
        {"entity": "coin:2", "attribute": "in", "value": "box:h", "valid_from": 1.0},
        {"entity": "coin:1", "attribute": "balance", "value": Decimal("1.00"),
         "valid_from": 1.0},
        {"entity": "coin:2", "attribute": "balance", "value": Decimal("2.00"),
         "valid_from": 1.0},
    ])
    baseline = world.aggregate("box:h", "balance", "avg")["value"]
    with localcontext() as ctx:               # ambient-context mutation must not leak in
        ctx.prec = 2
        mutated = world.aggregate("box:h", "balance", "avg")["value"]
    assert baseline == mutated == Decimal("1.50")
    assert world.aggregate("box:h", "balance", "sum")["value"] == Decimal("3.00")


# ------------------------------------------------------------- default lock

def test_no_decimal_world_is_byte_unchanged(world):
    _declare_accrue(world)
    world.ingest_structured([
        {"entity": "acct:i", "attribute": "kind", "value": "account", "timeless": True},
        {"entity": "acct:i", "attribute": "balance", "value": 10.5, "valid_from": 1.0},
        {"entity": "acct:i", "attribute": "balance", "value": 2.5,
         "value_type": "delta", "valid_from": 2.0},
    ])
    fold = world.state("acct:i", "balance")
    assert fold.quantity == 13.0 and isinstance(fold.quantity, float)
    jsonl = dump(world.buffer)
    assert DEC_TAG not in jsonl                        # no tag leaks into a float world


# ------------------------------------------------------------- contract

def test_porcelain_payloads_stay_plain_json(world):
    _declare_accrue(world)
    world.ingest_structured([
        {"entity": "acct:j", "attribute": "kind", "value": "account", "timeless": True},
        {"entity": "acct:j", "attribute": "balance", "value": Decimal("5.25"),
         "valid_from": 1.0},
    ])
    p = world.porcelain
    snap = p.snapshot(["acct:j"])
    state = p.state("acct:j", "balance")
    hood = p.neighborhood("acct:j")
    for payload in (snap, state, hood):
        json.dumps(payload)                            # plain json must serialize it
    assert state["quantity"] == {DEC_TAG: "5.25"}      # the tag dict, not raw Decimal
    q = [x for x in snap["quantities"] if x["attribute"] == "balance"]
    assert q and q[0]["value"] == {DEC_TAG: "5.25"}


def test_where_accepts_decimal_and_tag_form(world):
    _declare_accrue(world)
    world.ingest_structured([
        {"entity": "acct:k", "attribute": "kind", "value": "account", "timeless": True},
        {"entity": "acct:k", "attribute": "balance", "value": Decimal("7.00"),
         "valid_from": 1.0},
    ])
    assert world.porcelain.where("balance", ">=", Decimal("6.50")) == ["acct:k"]
    assert world.porcelain.where("balance", ">=", {DEC_TAG: "6.50"}) == ["acct:k"]


def test_float_fold_grouping_is_byte_identical(world):
    # Cx final: float addition is non-associative — the fold must keep the
    # pre-change grouping `baseline + sum(deltas)` verbatim, not re-group.
    _declare_accrue(world)
    world.ingest_structured([
        {"entity": "acct:m", "attribute": "kind", "value": "account", "timeless": True},
        {"entity": "acct:m", "attribute": "balance", "value": 0.1, "valid_from": 1.0},
        {"entity": "acct:m", "attribute": "balance", "value": 0.2,
         "value_type": "delta", "valid_from": 2.0},
        {"entity": "acct:m", "attribute": "balance", "value": 0.3,
         "value_type": "delta", "valid_from": 3.0},
    ])
    assert world.state("acct:m", "balance").quantity == 0.1 + (0.2 + 0.3)


def test_build_rejects_bare_tag_line(world, tmp_path):
    # a JSONL line that decodes to a Decimal (not a row object) must abort as
    # a DumpError through validation, never an AttributeError
    from patternbuffer.dump import DumpError
    with pytest.raises(DumpError, match="not an assertion row"):
        build('{"$decimal": "1"}\n', tmp_path / "bad.world")


def test_neighborhood_payload_carries_tag(world):
    _declare_accrue(world)
    world.ingest_structured([
        {"entity": "acct:n", "attribute": "kind", "value": "account", "timeless": True},
        {"entity": "acct:n", "attribute": "balance", "value": Decimal("9.99"),
         "valid_from": 1.0},
    ])
    hood = world.neighborhood("acct:n")     # core payload read: tag, not raw Decimal
    q = [x for x in hood["subject"]["quantities"] if x["attribute"] == "balance"]
    assert q and q[0]["value"] == {DEC_TAG: "9.99"}
    json.dumps(hood)


def test_encode_out_recurses_and_is_idempotent():
    payload = {"a": [Decimal("1.10"), {"b": Decimal("2.20")}], "c": "s"}
    once = encode_out(payload)
    assert once == {"a": [{DEC_TAG: "1.10"}, {"b": {DEC_TAG: "2.20"}}], "c": "s"}
    assert encode_out(once) == once
    assert encode_value(Decimal("3")) == {DEC_TAG: "3"}
