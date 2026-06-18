"""AKA-CORRELATION-V1: the non-collapsing third identity relation.

`aka` correlates two entities as facets of one identity WITHOUT collapsing them.
It stays out of the `same_as` closure and every default read; the correlated
view is reachable only through the explicit, valid-time-gated `state_union` /
`correlations` reads. The seven §5 membrane leak tests are the acceptance gate.
"""

import json

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "aka.world", world_id="w:aka", model=stub)
    yield w
    w.close()


def _facts(w):
    # masked figure and the real person — two richly-attributed entities.
    w.ingest_structured([
        {"entity": "person:masked", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:masked", "attribute": "mood", "value": "grim", "valid_from": 1.0},
        {"entity": "person:ilsa", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:ilsa", "attribute": "occupation", "value": "clerk", "valid_from": 1.0},
    ])


def _reveal(w, at=10.0):
    # the reveal: masked IS ilsa, as of t=10 (correlate, not merge)
    return w.correlate("person:masked", "person:ilsa", evidence="the reveal", valid_from=at)


# ----------------------------------------------------------- §5 gate tests

def test_pre_reveal_isolation(world):
    _facts(world); _reveal(world, at=10.0)
    # before the reveal: each side sees only its own facts, union or not
    assert world.porcelain.state("person:masked", "occupation", as_of=5.0)["status"] == "unknown"
    assert world.porcelain.state_union("person:masked", "occupation", as_of=5.0)["status"] == "unknown"
    # ilsa's own occupation is visible to ilsa
    assert world.porcelain.state("person:ilsa", "occupation", as_of=5.0)["fact"]["value"] == "clerk"


def test_no_default_union_post_reveal(world):
    _facts(world); _reveal(world, at=10.0)
    # AFTER the reveal, the DEFAULT read still does not union the other facet
    assert world.porcelain.state("person:masked", "occupation", as_of=15.0)["status"] == "unknown"
    assert world.porcelain.state("person:ilsa", "mood", as_of=15.0)["status"] == "unknown"


def test_explicit_union_only(world):
    _facts(world); _reveal(world, at=10.0)
    # only the explicit union read, as-of-after, returns the combined view
    u = world.porcelain.state_union("person:masked", "occupation", as_of=15.0)
    assert u["status"] == "known" and u["fact"]["value"] == "clerk"
    # and symmetrically from ilsa's side for masked's mood
    assert world.porcelain.state_union("person:ilsa", "mood", as_of=15.0)["fact"]["value"] == "grim"


def test_as_of_before_never_leaks(world):
    _facts(world); _reveal(world, at=10.0)
    # the edge exists (asserted now) but its valid_from is 10 — an as-of BEFORE
    # the reveal must return the uncorrelated view
    assert world.porcelain.state_union("person:masked", "occupation", as_of=5.0)["status"] == "unknown"
    # at/after the reveal it correlates
    assert world.porcelain.state_union("person:masked", "occupation", as_of=10.0)["status"] == "known"


def test_resolve_and_closure_ignore_aka(world):
    _facts(world); _reveal(world, at=10.0)
    reg = world.registry
    assert reg.resolve("person:masked") != reg.resolve("person:ilsa")
    assert "person:ilsa" not in reg.closure("person:masked")
    # the auto-merger never fuses an aka pair
    assert reg._mergeable("person:masked", "person:ilsa") is False


def test_distinct_from_veto(world):
    _facts(world)
    world.registry.reject("person:masked", "person:ilsa")   # distinct_from
    head = world.buffer.head()
    rec = world.correlate("person:masked", "person:ilsa", evidence="contradiction", valid_from=10.0)
    assert rec["outcome"] == "vetoed_distinct"
    assert rec["blocking_edges"]                              # names the distinct edge
    assert world.buffer.head() == head                       # nothing appended


def test_reads_write_nothing(world):
    _facts(world); _reveal(world, at=10.0)
    head = world.buffer.head()
    json.dumps(world.porcelain.correlations("person:masked", as_of=15.0))
    json.dumps(world.porcelain.state_union("person:masked", "occupation", as_of=15.0))
    assert world.buffer.head() == head


def test_aka_absent_from_projection(world):
    # the membrane: aka (like same_as) never appears in the PROJECTION
    # (snapshot/materialize) — it is meta-hidden. The inspection surface is
    # correlations(), not the served facts.
    _facts(world); _reveal(world, at=10.0)
    snap = world.porcelain.snapshot(["person:masked"], as_of=15.0)
    assert not any(f["attribute"] == "aka" for f in snap["facts"])
    m = world.materialize(["person:masked"], as_of=15.0)
    assert not any(r.attribute == "aka" for r in m.assertions)
    # the only inspection surface is correlations()
    assert "person:ilsa" in world.porcelain.correlations("person:masked", as_of=15.0)
    # consistency: an explicit single-key state() fold of aka behaves EXACTLY
    # like same_as. Both return the raw identity edge through an explicit fold
    # (the projection-absence above is the membrane; explicit state() is a
    # targeted query, same as same_as) — aka introduces no new read behavior.
    world.ingest_structured([
        {"entity": "person:c", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:d", "attribute": "kind", "value": "person", "timeless": True},
    ])
    world.registry.merge("person:c", "person:d", evidence="x")
    assert (world.porcelain.state("person:masked", "aka", as_of=15.0)["status"]
            == world.porcelain.state("person:c", "same_as", as_of=15.0)["status"])


# --------------------------------------------------------- behavior tests

def test_correlations_empty_before_reveal(world):
    _facts(world); _reveal(world, at=10.0)
    assert world.porcelain.correlations("person:masked", as_of=5.0) == []
    assert world.porcelain.correlations("person:masked", as_of=15.0) == ["person:ilsa"]


def test_transitive_correlation_set(world):
    # A aka B, B aka C  =>  union read from A sees C's facts (equivalence-like)
    world.ingest_structured([
        {"entity": "person:a", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:b", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:c", "attribute": "trait", "value": "brave", "valid_from": 1.0},
    ])
    world.correlate("person:a", "person:b", evidence="reveal1", valid_from=2.0)
    world.correlate("person:b", "person:c", evidence="reveal2", valid_from=2.0)
    assert world.porcelain.state_union("person:a", "trait", as_of=5.0)["fact"]["value"] == "brave"
    assert set(world.porcelain.correlations("person:a", as_of=5.0)) == {"person:b", "person:c"}


def test_divergent_facet_uses_existing_conflict_semantics(world):
    # same-valid-time divergent STATE across facets => conflicted (the fold's
    # ordinary behavior), NOT a special blanket rule.
    world.ingest_structured([
        {"entity": "person:p1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p1", "attribute": "stance", "value": "hostile", "valid_from": 5.0},
        {"entity": "person:p2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p2", "attribute": "stance", "value": "friendly", "valid_from": 5.0},
    ])
    world.correlate("person:p1", "person:p2", evidence="reveal", valid_from=1.0)
    u = world.porcelain.state_union("person:p1", "stance", as_of=10.0)
    assert u["status"] == "conflicted"


def test_time_sequential_state_recency_supersedes_not_conflict(world):
    # different STATE values at different valid-times across facets => recency
    # supersession, NOT permanent conflict (Cx 056 #4).
    world.ingest_structured([
        {"entity": "person:p1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p1", "attribute": "mood", "value": "grim", "valid_from": 2.0},
        {"entity": "person:p2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p2", "attribute": "mood", "value": "calm", "valid_from": 8.0},
    ])
    world.correlate("person:p1", "person:p2", evidence="reveal", valid_from=1.0)
    u = world.porcelain.state_union("person:p1", "mood", as_of=10.0)
    assert u["status"] == "known" and u["fact"]["value"] == "calm"


def test_noop_already_correlated(world):
    _facts(world)
    assert world.correlate("person:masked", "person:ilsa", evidence="r1")["outcome"] == "correlated"
    assert world.correlate("person:masked", "person:ilsa", evidence="r2")["outcome"] == "noop_already_correlated"


def test_correlation_conflicts_surfaces_raw_contradiction(world):
    # a raw aka authored directly over a distinct_from is appended (append-only)
    # but surfaced for adjudication
    _facts(world)
    world.registry.reject("person:masked", "person:ilsa")
    world.ingest_structured([
        {"entity": "person:masked", "attribute": "aka", "value": "person:ilsa",
         "value_type": "entity", "valid_from": 10.0},
    ])
    conflicts = world.correlation_conflicts()
    assert len(conflicts) == 1
    assert conflicts[0]["distinct_edges"]


def test_union_invariant_across_same_as_members(world):
    # Cx 057 #1: an aka edge attached to one same_as member must be found when
    # querying ANY member of that closure (retrieval-invariance).
    world.ingest_structured([
        {"entity": "person:a", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:a2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:b", "attribute": "trait", "value": "brave", "valid_from": 1.0},
    ])
    world.registry.merge("person:a", "person:a2", evidence="same person")
    world.correlate("person:a", "person:b", evidence="reveal", valid_from=2.0)
    assert world.porcelain.state_union("person:a", "trait", as_of=3.0)["fact"]["value"] == "brave"
    # querying the OTHER closure member must see the same correlated facet
    assert world.porcelain.state_union("person:a2", "trait", as_of=3.0)["fact"]["value"] == "brave"


def test_correlate_noop_on_transitive_component(world):
    # Cx 057 #2: A-aka-B, B-aka-C => correlate(A,C) is already correlated
    world.ingest_structured([
        {"entity": "person:a", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:b", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:c", "attribute": "kind", "value": "person", "timeless": True},
    ])
    assert world.correlate("person:a", "person:b", evidence="r1")["outcome"] == "correlated"
    assert world.correlate("person:b", "person:c", evidence="r2")["outcome"] == "correlated"
    head = world.buffer.head()
    assert world.correlate("person:a", "person:c", evidence="r3")["outcome"] == "noop_already_correlated"
    assert world.buffer.head() == head    # no redundant edge appended


def test_correlation_conflicts_as_of_aware(world):
    # Cx 057 #3: an aka with valid_from=10 over a distinct_from shows no conflict
    # as-of-before the reveal; passing as_of must not raise.
    _facts(world)
    world.registry.reject("person:masked", "person:ilsa")
    world.ingest_structured([
        {"entity": "person:masked", "attribute": "aka", "value": "person:ilsa",
         "value_type": "entity", "valid_from": 10.0},
    ])
    assert world.porcelain.correlation_conflicts(as_of=5.0) == []      # before reveal
    assert len(world.porcelain.correlation_conflicts(as_of=15.0)) == 1  # after reveal


def test_default_snapshot_unchanged_by_aka(world):
    # the membrane: a snapshot of masked after the reveal is identical with or
    # without the aka edge present (default reads never union)
    _facts(world)
    before = world.porcelain.snapshot(["person:masked"], as_of=15.0)
    _reveal(world, at=10.0)
    after = world.porcelain.snapshot(["person:masked"], as_of=15.0)
    assert [f["value"] for f in before["facts"]] == [f["value"] for f in after["facts"]]
