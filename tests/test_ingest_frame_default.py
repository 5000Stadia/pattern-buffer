"""HD 121 / Cx 545: frame= is a default-fill, made LOUD — and extract() stays raw.

The precedence (per-item frames win) is intended and load-bearing for mixed
batches; the Receipt warning makes the non-obvious case visible; extract()
returns the model's items verbatim (raw-output contract, INGEST-LATENCY-V2) —
wholesale re-targeting is host policy over a copy.
"""

import copy

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


def test_extract_is_raw_canon_stamp_preserved_and_payload_unmutated(tmp_path):
    # Cx 545 blocker 1: extract() must return the model's items VERBATIM —
    # an explicit frame="canon" stamp survives, and the provider payload is
    # never mutated in place.
    payload = {"items": [
        {"entity": "person:m", "attribute": "mood", "value": "grim",
         "frame": "canon", "valid_from": 1.0},
        {"entity": "person:m", "attribute": "suspects", "value": "the mate",
         "frame": "knows:person_b", "valid_from": 1.0},
    ]}
    pristine = copy.deepcopy(payload)

    def scripted(prompt, schema):
        if "PASSAGE:" in prompt:
            return payload
        return {"durability": "STATE", "class_confidence": 0.9}

    w = World(tmp_path / "raw.world", world_id="w:raw", model=scripted)
    try:
        items = w.porcelain.extract("She seemed grim; she told B her suspicion.")
        assert items[0]["frame"] == "canon"            # raw stamp preserved
        assert items[1]["frame"] == "knows:person_b"
        assert payload == pristine                     # no in-place mutation
    finally:
        w.close()


def test_staging_requires_host_policy_and_warning_fires(tmp_path):
    # the HD-121 pattern, honestly: extracted items MAY carry their own frame
    # (schema-optional; live providers commonly stamp canon) and must not be
    # assumed unframed — so a wholesale quarantine applies HOST policy to a
    # COPY, and pushing the raw batch at a staging frame warns.
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "stage.world", world_id="w:stage", model=stub)
    try:
        raw = [
            {"entity": "person:a", "attribute": "mood", "value": "grim",
             "frame": "canon", "valid_from": 1.0},
            {"entity": "person:a", "attribute": "kind", "value": "person",
             "timeless": True},                       # unframed
        ]
        # naive push: canon item keeps canon (the bypass), and the Receipt SAYS SO
        r1 = w.porcelain.ingest_structured(copy.deepcopy(raw),
                                           frame="proposed:main")
        assert any("1 item(s) kept their own frame" in wng for wng in r1.warnings)
        # host policy (strip on a copy): everything stages
        stripped = [{k: v for k, v in i.items() if k != "frame"}
                    for i in copy.deepcopy(raw)]
        w2 = World(tmp_path / "stage2.world", world_id="w:stage", model=stub)
        try:
            r2 = w2.porcelain.ingest_structured(stripped, frame="proposed:main")
            assert not r2.warnings
            assert all(row.frame == "proposed:main"
                       for row in w2.buffer.visible()
                       if row.entity == "person:a")
        finally:
            w2.close()
    finally:
        w.close()


def test_warning_branches_exact(tmp_path):
    # Cx 545 coverage ask: no warning when all items are absent-frame; no
    # warning when own frames EQUAL frame=; exact count when mixed.
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "warn.world", world_id="w:warn", model=stub)
    try:
        r_absent = w.porcelain.ingest_structured([
            {"entity": "person:a", "attribute": "kind", "value": "person",
             "timeless": True}], frame="proposed:main")
        assert not r_absent.warnings                        # all filled: quiet

        r_equal = w.porcelain.ingest_structured([
            {"entity": "person:a", "attribute": "mood", "value": "calm",
             "frame": "proposed:main", "valid_from": 1.0}],
            frame="proposed:main")
        assert not r_equal.warnings                         # same target: quiet

        r_mixed = w.porcelain.ingest_structured([
            {"entity": "person:a", "attribute": "mood", "value": "grim",
             "frame": "canon", "valid_from": 2.0},
            {"entity": "person:a", "attribute": "secret", "value": "x",
             "frame": "knows:person_z", "valid_from": 2.0},
            {"entity": "person:a", "attribute": "note", "value": "y",
             "valid_from": 2.0}], frame="proposed:main")
        assert any("2 item(s) kept their own frame" in wng
                   for wng in r_mixed.warnings)             # exact count

        r_noarg = w.porcelain.ingest_structured([
            {"entity": "person:b", "attribute": "kind", "value": "person",
             "timeless": True, "frame": "knows:person_z"}])
        assert not r_noarg.warnings                         # no frame=: quiet
    finally:
        w.close()


def test_mixed_batch_knows_frames_survive_default(tmp_path):
    # the load-bearing case the precedence protects: a telling scene's knows:B
    # rows must survive a default frame (why argument-wins would be WRONG)
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "mix.world", world_id="w:mix", model=stub)
    try:
        w.porcelain.ingest_structured([
            {"entity": "person:a", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:a", "attribute": "secret", "value": "x",
             "frame": "knows:person_z", "valid_from": 1.0},
        ], frame="plot:main")
        sec = w.buffer.visible(attribute="secret")[0]
        assert sec.frame == "knows:person_z"                # knowledge intact
        kind = [r for r in w.buffer.visible(attribute="kind")
                if r.entity == "person:a"][0]
        assert kind.frame == "plot:main"                    # default applied
    finally:
        w.close()
