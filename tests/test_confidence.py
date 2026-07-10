"""CONFIDENCE-V1: derived temporal trust read."""

import json

import pytest

from patternbuffer import World
from patternbuffer.indexes import CONFIDENCE_PARAMS
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "confidence.world", world_id="w:confidence", model=stub)
    yield w
    w.close()


def _null_confidence():
    return {
        "score": None,
        "status": None,
        "last_observed_at": None,
        "corroboration": 0,
        "conflicted": False,
        # TRACKING-MODE-V1: one payload shape everywhere — the additive
        # fields are present (null) on empty/set-valued/accrue results.
        "recency": None,
        "recency_status": None,
        "last_confirmed_at_wallclock": None,
    }


def test_stated_recent_multi_source_corroborated_scores_high(world):
    world.ingest_structured([
        {"entity": "obj:beacon", "attribute": "condition", "value": "lit",
         "valid_from": 10.0},
        {"entity": "obj:beacon", "attribute": "condition", "value": "lit",
         "valid_from": 10.0, "source_doc": "person:dale"},
        {"entity": "obj:beacon", "attribute": "condition", "value": "lit",
         "valid_from": 10.0, "source_doc": "person:meg"},
    ])

    out = world.confidence("obj:beacon", "condition", as_of=10.0)

    assert out["status"] == "stated"
    assert out["last_observed_at"] == 10.0
    assert out["corroboration"] == 2
    assert out["conflicted"] is False
    assert out["score"] > 0.85


def test_assumed_old_single_source_scores_below_stated(world):
    # TRACKING-MODE-V1 amendment (founder ruling): fiction recency is
    # PERMANENT — story-time age no longer erodes trust (the page is true).
    # An `assumed` fact still scores strictly below a `stated` equivalent via
    # PROVENANCE; age contributes nothing in either direction.
    world.ingest_structured([
        {"entity": "obj:relic", "attribute": "condition", "value": "dusty",
         "valid_from": 1.0, "status": "assumed"},
        {"entity": "obj:altar", "attribute": "condition", "value": "dusty",
         "valid_from": 1.0},                        # stated, same age
    ])

    old_read = world.confidence("obj:relic", "condition", as_of=101.0)
    fresh_read = world.confidence("obj:relic", "condition", as_of=1.0)
    stated = world.confidence("obj:altar", "condition", as_of=101.0)

    assert old_read["status"] == "assumed"
    assert old_read["last_observed_at"] == 1.0
    assert old_read["corroboration"] == 0
    assert old_read["recency"] == 1.0 and old_read["recency_status"] == "permanent"
    assert old_read["score"] == fresh_read["score"]     # age changes nothing
    assert old_read["score"] < stated["score"]          # provenance still ranks


def test_conflicted_key_is_flagged_and_score_is_halved(world):
    world.ingest_structured([
        {"entity": "obj:gem", "attribute": "color", "value": "red",
         "valid_from": 5.0},
        {"entity": "obj:gem", "attribute": "color", "value": "blue",
         "valid_from": 5.0},
    ])

    out = world.confidence("obj:gem", "color", as_of=5.0)

    weights = CONFIDENCE_PARAMS["weights"]
    unconflicted = weights["provenance"] * 1.0 + weights["recency"] * 1.0
    assert out["conflicted"] is True
    assert out["score"] == pytest.approx(unconflicted * 0.5)


def test_timeless_winner_has_full_recency_and_no_last_observed_at(world):
    world.ingest_structured([
        {"entity": "obj:coin", "attribute": "kind", "value": "coin",
         "timeless": True},
    ])

    out = world.confidence("obj:coin", "kind", as_of=999.0)

    weights = CONFIDENCE_PARAMS["weights"]
    assert out["last_observed_at"] is None
    assert out["score"] == pytest.approx(
        weights["provenance"] * 1.0 + weights["recency"] * 1.0
    )


def test_confidence_does_not_change_state_snapshot_or_log(world):
    world.ingest_structured([
        {"entity": "obj:beacon", "attribute": "kind", "value": "beacon",
         "timeless": True},
        {"entity": "obj:beacon", "attribute": "condition", "value": "lit",
         "valid_from": 10.0},
    ])
    before_state = world.porcelain.state("obj:beacon", "condition")
    before_snapshot = world.porcelain.snapshot("obj:beacon")
    before_head = world.buffer.head()
    before_len = len(world.buffer.all_rows())

    out = world.porcelain.confidence("obj:beacon", "condition", as_of=10.0)

    assert world.porcelain.state("obj:beacon", "condition") == before_state
    assert world.porcelain.snapshot("obj:beacon") == before_snapshot
    assert world.buffer.head() == before_head
    assert len(world.buffer.all_rows()) == before_len
    json.dumps(out)


def test_confidence_reads_fresh_log_state_without_rebuild(world):
    world.ingest_structured([
        {"entity": "obj:beacon", "attribute": "condition", "value": "lit",
         "valid_from": 10.0},
    ])
    before = world.confidence("obj:beacon", "condition", as_of=10.0)

    world.ingest_structured([
        {"entity": "obj:beacon", "attribute": "condition", "value": "lit",
         "valid_from": 10.0, "source_doc": "person:dale"},
    ])
    after = world.confidence("obj:beacon", "condition", as_of=10.0)

    assert before["corroboration"] == 0
    assert after["corroboration"] == 1
    assert after["score"] > before["score"]


def test_functional_only_set_valued_accrue_and_absent_return_none(world):
    world.ingest_structured([
        {"entity": "obj:meter", "attribute": "name", "value": "master meter",
         "timeless": True},
        {"entity": "person:you", "attribute": "gold", "value": 100,
         "fold_policy": "accrue", "valid_from": 1.0},
        {"entity": "person:you", "attribute": "gold", "value": -10,
         "value_type": "delta", "valid_from": 2.0},
    ])

    assert world.confidence("obj:meter", "name") == _null_confidence()
    assert world.confidence("person:you", "gold") == _null_confidence()
    assert world.confidence("obj:meter", "missing") == _null_confidence()


def test_corroboration_is_strict_not_approximate(world):
    # Post-impl review: a {gte} bound must NOT corroborate a precise value
    # (corroboration is "same value", strict — not approximate agreement).
    world.ingest_structured([
        {"entity": "place:vault", "attribute": "liters", "value": 42,
         "value_type": "literal", "valid_from": 1.0},
        {"entity": "place:vault", "attribute": "liters", "value": {"gte": 40},
         "value_type": "literal", "valid_from": 1.0, "source_doc": "doc:ledger"},
    ])
    out = world.confidence("place:vault", "liters", as_of=1.0)
    assert out["corroboration"] == 0  # the bound is not a same-value corroborator


def test_negative_source_confidence_does_not_zero_a_stated_fact(world):
    # Post-impl review: a garbage out-of-range confidence field must be clamped
    # to [0,1] before flooring provenance, not zero a stated fact.
    world.ingest_structured([
        {"entity": "obj:meter", "attribute": "reading", "value": 7,
         "value_type": "literal", "valid_from": 1.0, "confidence": -1.0},
    ])
    out = world.confidence("obj:meter", "reading", as_of=1.0)
    assert out["score"] is not None and out["score"] > 0.0
