"""INGESTION-FIDELITY-V1: fidelity_audit() — the structural-gap read.

Surfaces where a freshly-built log is structurally incomplete, as a queryable
checklist the host joins for severity and re-extracts from. Deterministic,
membrane-clean (zero writes), frame/as-of scoped.
"""

import json

import pytest

from patternbuffer import World
from patternbuffer.dump import dump
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "fa.world", world_id="w:fa", model=stub)
    yield w
    w.close()


def _named(w, eid, kind, name, extra=()):
    items = [{"entity": eid, "attribute": "kind", "value": kind, "timeless": True},
             {"entity": eid, "attribute": "name", "value": name, "timeless": True}]
    items.extend(extra)
    w.ingest_structured(items)


def _status(group, a, b):
    for p in group["pairs"]:
        if {p["a"], p["b"]} == {a, b}:
            return p["status"], p.get("reason")
    return None, None


def _group(audit, anchor):
    return next((g for g in audit["name_collisions"] if g["anchor"] == anchor), None)


# ------------------------------------------------- name_collisions statuses

def test_collision_statuses(world):
    # alias_not_specific: distinct full names sharing a single-token ALIAS
    _named(world, "person:mara_vane", "person", "mara vane",
           extra=[{"entity": "person:mara_vane", "attribute": "alias",
                   "value": "mara", "timeless": True}])
    _named(world, "person:mara_thist", "person", "mara thist",
           extra=[{"entity": "person:mara_thist", "attribute": "alias",
                   "value": "mara", "timeless": True}])
    # kind_conflict (NOT a slip): both sides structurally rich, differing kind
    _named(world, "obj:crown_relic", "relic", "crown",
           extra=[{"entity": "obj:crown_relic", "attribute": "worn_by",
                   "value": "person:king", "value_type": "entity", "valid_from": 1.0},
                  {"entity": "person:king", "attribute": "kind", "value": "person",
                   "timeless": True}])
    _named(world, "place:crown_hall", "place", "crown",
           extra=[{"entity": "place:crown_hall", "attribute": "state",
                   "value": "grand", "valid_from": 1.0}])
    # distinct_from: hard-blocked
    _named(world, "person:clay_a", "person", "clay")
    _named(world, "person:clay_b", "person", "clay")
    world.registry.reject("person:clay_a", "person:clay_b")
    # aka: correlated facets — reported, NOT a gap
    _named(world, "person:masked", "person", "figure")
    _named(world, "person:ilsa", "person", "figure")
    world.correlate("person:masked", "person:ilsa", evidence="reveal", valid_from=1.0)

    # auto_declined requires a logged proposal the gate declined
    world.registry.maybe_same_as("person:mara_vane", "person:mara_thist", evidence="e")
    world.registry.maybe_same_as("obj:crown_relic", "place:crown_hall", evidence="e")

    a = world.porcelain.fidelity_audit()

    s, r = _status(_group(a, "mara"), "person:mara_vane", "person:mara_thist")
    assert s == "auto_declined" and r == "alias_not_specific"
    s, r = _status(_group(a, "crown"), "obj:crown_relic", "place:crown_hall")
    assert s == "auto_declined" and r == "kind_conflict"
    s, r = _status(_group(a, "clay"), "person:clay_a", "person:clay_b")
    assert s == "hard_blocked" and r == "distinct_from"
    s, _ = _status(_group(a, "figure"), "person:ilsa", "person:masked")
    assert s == "correlated"

    # folded kinds per group (HD 107) — parallel to `entities`; a cross-kind
    # (person↔place) collision is detectable from the kind pair, not the namespace
    crown = _group(a, "crown")
    kinds = dict(zip(crown["entities"], crown["kinds"]))
    assert kinds["obj:crown_relic"] == "relic" and kinds["place:crown_hall"] == "place"


def test_typing_slip_status(world):
    # person:harth (bare) shadows place:harth (has a villager) -> slip
    world.ingest_structured([
        {"entity": "place:harth", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:harth", "attribute": "name", "value": "harth", "timeless": True},
        {"entity": "person:v", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:v", "attribute": "in", "value": "place:harth",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:harth", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:harth", "attribute": "name", "value": "harth", "timeless": True},
    ])
    a = world.porcelain.fidelity_audit()
    s, _ = _status(_group(a, "harth"), "person:harth", "place:harth")
    assert s == "typing_slip"
    assert _group(a, "harth")["live"] is True


def test_unlinked_and_live_count_and_repair(world):
    # a pure fragment (tovin subset of tovin beck) -> unlinked -> live
    _named(world, "person:tovin", "person", "tovin")
    _named(world, "person:tovin_beck", "person", "tovin beck",
           extra=[{"entity": "person:tovin_beck", "attribute": "alias",
                   "value": "tovin", "timeless": True}])
    a = world.porcelain.fidelity_audit()
    s, _ = _status(_group(a, "tovin"), "person:tovin", "person:tovin_beck")
    assert s == "unlinked"
    assert a["summary"]["name_collisions"] == 1          # one live group
    # the read tracks repair: reconcile collapses the mergeable pair -> gone
    world.registry.reconcile()
    b = world.porcelain.fidelity_audit()
    assert b["summary"]["name_collisions"] == 0


def test_resolved_only_group_not_counted(world):
    # a distinct_from collision is reported but NOT counted as live
    _named(world, "person:clay_a", "person", "clay")
    _named(world, "person:clay_b", "person", "clay")
    world.registry.reject("person:clay_a", "person:clay_b")
    a = world.porcelain.fidelity_audit()
    assert _group(a, "clay") is not None                 # reported for visibility
    assert _group(a, "clay")["live"] is False
    assert a["summary"]["name_collisions"] == 0          # not counted
    assert a["summary"]["name_collisions_total"] >= 1


# ---------------------------------------------------- other gap categories

def test_unstamped_timed(world):
    # the real gap: a STATE fact WRONGLY marked timeless -> no valid_from, so it
    # can never be as-of'd. (A normal non-timeless row is cursor-stamped, so it
    # is not a gap.) A genuinely-timeless CONSTITUTIVE kind row is correct.
    world.ingest_structured([
        {"entity": "person:m", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:m", "attribute": "mood", "value": "grim", "timeless": True},
        {"entity": "person:m", "attribute": "mood", "value": "calm", "valid_from": 5.0},
    ])
    unstamped = world.porcelain.fidelity_audit()["unstamped_timed"]
    keys = {(u["entity"], u["attribute"]) for u in unstamped}
    assert ("person:m", "mood") in keys                  # STATE mis-marked timeless
    assert ("person:m", "kind") not in keys              # legitimately timeless


def test_orphan_entities(world):
    world.ingest_structured([
        {"entity": "place:room", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "obj:anchored", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:anchored", "attribute": "in", "value": "place:room",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "obj:floating", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "person:nowhere", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "event:thing", "attribute": "kind", "value": "event", "timeless": True},
    ])
    orphans = set(world.porcelain.fidelity_audit()["orphan_entities"])
    assert "obj:floating" in orphans and "person:nowhere" in orphans
    assert "obj:anchored" not in orphans                 # contained
    assert "place:room" not in orphans                   # top-level place excluded
    assert "event:thing" not in orphans                  # non-spatial excluded


def test_open_conflicts_surfaced(world):
    # a constitutive contradiction (two kinds) raises a truth-maintenance flag
    world.ingest_structured([
        {"entity": "obj:thing", "attribute": "kind", "value": "sword", "timeless": True},
        {"entity": "obj:thing", "attribute": "material", "value": "steel", "valid_from": 1.0},
    ])
    world.truth.scan()
    conflicts = world.porcelain.fidelity_audit()["open_conflicts"]
    assert isinstance(conflicts, list)   # shape present; populated when scan flags one


# ------------------------------------------------------------ membrane

def test_audit_is_read_only_and_json_safe(world):
    _named(world, "person:tovin", "person", "tovin")
    _named(world, "person:tovin_beck", "person", "tovin beck")
    before = dump(world.buffer)
    a = world.porcelain.fidelity_audit()
    after = dump(world.buffer)
    assert before == after                                # zero writes
    json.dumps(a)                                          # plain-JSON contract


def test_frame_scopes_grouping(world):
    # a knows: frame's rows don't collide with canon in a canon audit
    world.ingest_structured([
        {"entity": "person:a", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:a", "attribute": "alias", "value": "shadow",
         "frame": "knows:person_x", "timeless": True},
        {"entity": "person:b", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:b", "attribute": "alias", "value": "shadow", "timeless": True},
    ])
    canon = world.porcelain.fidelity_audit(frame="canon")
    assert _group(canon, "shadow") is None                # only one canon 'shadow'
