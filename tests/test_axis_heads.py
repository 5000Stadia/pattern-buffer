"""AXIS-HEAD-V1: axis_heads() + ingest_structured(at=) — the last residues.

The two-axis high-water mark is a coordinate scalar over ALL rows, all
frames (the entry-epoch read); the per-chunk cursor pose mirrors ingest(at=).
"""

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "ah.world", world_id="w:ah", model=stub)
    yield w
    w.close()


def test_axis_heads_timeless_only(world):
    world.ingest_structured([
        {"entity": "obj:rock", "attribute": "kind", "value": "object",
         "timeless": True},
    ])
    heads = world.porcelain.axis_heads()
    assert heads["asserted_head"] >= 1
    assert heads["valid_head"] is None          # no timed rows yet


def test_axis_heads_cross_frame_max(world):
    # the HD regression: a seeded knows: row carries the highest coordinate —
    # a canon-only max would under-raise the entry epoch
    world.ingest_structured([
        {"entity": "person:nell", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:nell", "attribute": "mood", "value": "grim",
         "valid_from": 10.0},
        {"entity": "person:nell", "attribute": "suspects", "value": "the mate",
         "frame": "knows:person_maud", "valid_from": 99.0},
    ])
    heads = world.porcelain.axis_heads()
    assert heads["valid_head"] == 99.0          # the knows: row anchors the head
    world.ingest_structured([
        {"entity": "person:nell", "attribute": "mood", "value": "calm",
         "valid_from": 120.0},
    ])
    assert world.porcelain.axis_heads()["valid_head"] == 120.0   # monotone


def test_ingest_structured_at_poses_cursor(world):
    world.porcelain.ingest_structured([
        {"entity": "obj:coin", "attribute": "kind", "value": "object",
         "timeless": True},
        {"entity": "obj:coin", "attribute": "state", "value": "dropped"},
    ], at=7.0)
    row = world.buffer.visible(attribute="state")[0]
    assert row.valid_from == 7.0                # un-timed row stamped from the pose
    # default (no at=) leaves the cursor where it was
    world.porcelain.ingest_structured([
        {"entity": "obj:coin", "attribute": "state", "value": "picked_up"},
    ])
    later = [r for r in world.buffer.visible(attribute="state")
             if r.value == "picked_up"][0]
    assert later.valid_from == 7.0
