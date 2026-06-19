"""CLASSIFIER-EVENT-SAFETY-V1: the model may not assign the erasing class.

EVENT excludes a row from every fold, so a model flip STATE->EVENT silently
erases established truth from reads (Construct 059/060). The model is restricted
to the standing spectrum {CONSTITUTIVE, DISPOSITIONAL, STATE}; EVENT stays
deterministic-only (event:/caused_by/META guardrails). Covers BOTH the per-row
and the batch (anchor-scale) model paths.
"""

from patternbuffer import World
from patternbuffer.classify import (
    EVENT, STATE, _MODEL_SCHEMA, _STANDING_DURABILITIES, DURABILITIES,
)


def _event_returning_model(durability="EVENT"):
    """A model that classifies EVERYTHING as EVENT (the worst case) and
    extracts nothing."""
    def shim(prompt, schema):
        if "verdicts" in schema.get("properties", {}):           # batch classify
            # count the listed facts; return EVENT for each
            n = prompt.count("\n") + 5
            return {"verdicts": [{"index": i, "durability": durability,
                                  "class_confidence": 0.9} for i in range(n)]}
        if "durability" in schema.get("properties", {}):          # per-row classify
            return {"durability": durability, "class_confidence": 0.9}
        return {"items": []}                                      # extraction
    return shim


def _world(tmp_path, inline=True):
    w = World(tmp_path / "evs.world", world_id="w:evs",
              model=_event_returning_model())
    w.ingestor.classify_inline = inline
    return w


def test_schemas_exclude_event():
    # both model schemas offer only the standing spectrum
    assert "EVENT" not in _MODEL_SCHEMA["properties"]["durability"]["enum"]
    assert EVENT not in _STANDING_DURABILITIES
    assert EVENT in DURABILITIES   # still a valid fold class, just not model-assignable


def test_per_row_event_verdict_becomes_state_and_folds(tmp_path):
    # the rung="refusal" repro, inline path: model says EVENT, engine keeps STATE
    w = _world(tmp_path, inline=True)
    w.ingest_structured([
        {"entity": "clock:refusal", "attribute": "rung", "value": "refusal", "valid_from": 1.0},
    ])
    row = next(r for r in w.buffer.all_rows() if r.attribute == "rung")
    assert w.classifier.durability(row.id) == STATE          # not EVENT
    assert w.state("clock:refusal", "rung").winner is not None   # folds
    assert any(r.attribute == "rung" for r in w.materialize(["clock:refusal"]).assertions)


def test_batch_event_verdict_becomes_state_and_folds(tmp_path):
    # the ACTUAL anchor-scale path (Cx 062): classify deferred, then batch.
    w = _world(tmp_path, inline=False)
    w.ingest_structured([
        {"entity": "clock:refusal", "attribute": "rung", "value": "refusal", "valid_from": 1.0},
        {"entity": "clock:refusal", "attribute": "rearm", "value": "once", "valid_from": 1.0},
    ])
    w.classifier.classify_all(batch_size=40)
    for attr in ("rung", "rearm"):
        row = next(r for r in w.buffer.all_rows() if r.attribute == attr)
        assert w.classifier.durability(row.id) == STATE, attr
        assert w.state("clock:refusal", attr).winner is not None, attr
    served = {r.attribute for r in w.materialize(["clock:refusal"]).assertions}
    assert {"rung", "rearm"} <= served


def test_event_entity_still_event(tmp_path):
    # structural EVENT path is untouched: an event: entity row stays EVENT
    w = _world(tmp_path, inline=True)
    w.ingest_structured([
        {"entity": "event:handoff", "attribute": "did", "value": "passed the dollar", "valid_from": 5.0},
    ])
    row = next(r for r in w.buffer.all_rows() if r.entity == "event:handoff" and r.attribute == "did")
    assert w.classifier.durability(row.id) == EVENT


def test_caused_by_still_event(tmp_path):
    # a caused_by row is guardrail-classified EVENT regardless of the model
    from dataclasses import replace
    w = _world(tmp_path, inline=True)
    w.ingest_structured([
        {"entity": "obj:x", "attribute": "state", "value": "broken", "valid_from": 5.0},
    ])
    eff = next(r for r in w.buffer.all_rows() if r.attribute == "state")
    caused = replace(eff, attribute="caused_by", value_type="entity", value="event:e")
    assert w.classifier._guardrails(caused) == (EVENT, 1.0)


def test_structural_declared_attr_skips_model(tmp_path):
    # a host-declared structural attr (via attribute_default) never reaches the
    # model -> CONSTITUTIVE, even though the model would say EVENT
    from patternbuffer.classify import CONSTITUTIVE

    def default(attribute):
        return {"structural": True} if attribute == "beat_phase" else None

    w = World(tmp_path / "evs2.world", world_id="w:evs2",
              model=_event_returning_model(), attribute_default=default)
    w.ingest_structured([
        {"entity": "clock:refusal", "attribute": "beat_phase", "value": "armed", "valid_from": 1.0},
    ])
    row = next(r for r in w.buffer.all_rows()
               if r.attribute == "beat_phase" and r.value == "armed")
    assert w.classifier.durability(row.id) == CONSTITUTIVE
