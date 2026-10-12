"""CLOSURE-READ-V1: a host's read of identity closures (construct's ask, R42).

One test (or group) per check of specs/CLOSURE-READ-V1.md (Tests 1-6, 3a).
"""

from __future__ import annotations

import pytest

from patternbuffer import World
from patternbuffer.mcp import V1_READS, build_registry, dispatch
from patternbuffer.roles import _make_engine_roles
from patternbuffer.service import VIEWER_EXCLUDED, Refused, WorldService
from patternbuffer.testing import StubModel, rule_classifier_fallback

A, B, C, D = "person:ann", "person:ann_reed", "person:a_reed", "person:bea"
F = "knows:person:bea"
INGESTOR = _make_engine_roles()["ingestor"]


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path / "closure.world", world_id="w:closure",
              model=StubModel(fallback=rule_classifier_fallback()))
    w.ingest_structured([
        {"entity": e, "attribute": "kind", "value": "person", "timeless": True}
        for e in (A, B, C, D)
    ])
    yield w
    w.close()


def _legacy_row(w, entity: str, attribute: str, value: str, frame: str):
    """A row already in a log, appended past the gate with the ingestor role (a
    non-canon identity edge today's gate refuses, `identity_edge_outside_canon`)."""
    return w.buffer.append(entity=entity, attribute=attribute, value=value,
                           value_type="entity", status="stated", role=INGESTOR,
                           frame=frame)


def _same_as_id(w, a: str, b: str) -> str:
    return next(r.id for r in w.buffer.visible(attribute="same_as")
                if {r.entity, r.value} == {a, b})


def _distinct_ids(w, frame: str = "canon") -> list[str]:
    return [r.id for r in w.buffer.visible(attribute="distinct_from", frame=frame)]


def _walk_like_construct(w) -> dict[str, set[str]]:
    """Construct's copy of the walk: canon same_as rows from `facts`, joined."""
    edges: dict[str, set[str]] = {}
    for fact in w.porcelain.facts("canon", attribute="same_as"):
        a, b = fact["entity"], fact["value"]
        edges.setdefault(a, set()).add(b)
        edges.setdefault(b, set()).add(a)
    out: dict[str, set[str]] = {}
    for start in edges:
        seen, todo = {start}, [start]
        while todo:
            for nxt in edges.get(todo.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        out[start] = seen
    return out


def _history(w) -> None:
    """Merges, a retracted same_as, and a re-pointed representative."""
    w.porcelain.merge(A, B, "the same woman")
    w.porcelain.merge(B, C, "her initials")
    w.porcelain.retract(_same_as_id(w, B, C), "a different Reed")
    w.porcelain.merge(A, B, "the same woman", representative=B)


# ------------------------------------------------------------------ 1. closure


def test_1_closure_matches_the_registry_at_head_and_at_every_position(world):
    p = world.porcelain
    assert p.closure(A) == [A]                          # no same_as: itself
    _history(world)
    head = world.buffer.head()
    for e in (A, B, C, D):
        assert p.closure(e) == sorted(world.registry.closure(e))
    assert p.closure(A) == sorted([A, B]) and p.closure(C) == [C]
    for pos in range(1, head + 1):
        for e in (A, B, C, D):
            assert p.closure(e, asserted_as_of=pos) == sorted(world.registry.closure(e, pos))
    seen_three = [pos for pos in range(1, head + 1)
                  if p.closure(A, asserted_as_of=pos) == sorted([A, B, C])]
    assert seen_three                                   # the as-of walk saw C joined, then split


def test_1_closure_refuses_a_malformed_id(world):
    with pytest.raises(ValueError):
        world.porcelain.closure("not an id")


# ----------------------------------------------- 2. parity with construct's walk


def test_2_construct_s_walk_gives_the_same_members(world):
    _history(world)
    walked = _walk_like_construct(world)
    for e in (A, B, C, D):
        assert world.porcelain.closure(e) == sorted(walked.get(e, {e}))


# ---------------------------------------------------------- 3. distinct_between


def test_3_the_rows_holding_two_closures_apart_in_both_directions(world):
    p = world.porcelain
    assert p.distinct_between(A, D) == []
    p.merge(A, B, "the same woman")
    p.reject(B, D)                                      # a row on a member of A's closure
    p.reject(D, C)                                      # the reverse direction, to C
    # reject writes canonical endpoints: the B-D row lands on A's closure
    ab_d = [i for i in _distinct_ids(world)
            if {world.buffer.get(i).entity, world.buffer.get(i).value} <= {A, B, D}]
    assert len(ab_d) == 1
    assert p.distinct_between(A, D) == ab_d and p.distinct_between(D, A) == ab_d
    assert p.distinct_between(B, D) == ab_d                 # any member names the closure
    assert p.distinct_between(C, D) == p.distinct_between(D, C) != []
    assert p.distinct_between(A, C) == []


def test_3_a_retracted_row_drops_out_and_as_of_spans_its_life(world):
    p = world.porcelain
    before = world.buffer.head()
    p.reject(A, D)
    (row_id,) = _distinct_ids(world)
    asserted = world.buffer.head()
    p.retract(row_id, "they are the same after all")
    retracted = world.buffer.head()
    assert p.distinct_between(A, D) == []
    assert p.distinct_between(A, D, asserted_as_of=before) == []
    assert p.distinct_between(A, D, asserted_as_of=asserted) == [row_id]
    assert p.distinct_between(A, D, asserted_as_of=retracted) == []
    assert p.distinct_between(A, D, asserted_as_of=retracted + 5) == []


def test_3_a_row_inside_one_shared_closure_is_still_reported(world):
    p = world.porcelain
    p.reject(A, B)
    _legacy_row(world, A, "same_as", B, "canon")            # merged past the veto
    assert p.closure(A) == sorted([A, B])
    assert p.distinct_between(A, B) == _distinct_ids(world)
    assert world.porcelain.identity_conflicts()             # what that read flags


# ------------------------------------------------- 3a. the frame stays the caller's


def test_3a_a_frame_reads_only_its_own_rows_and_the_public_verb_only_canon(world):
    _legacy_row(world, A, "distinct_from", D, F)
    world.porcelain.reject(A, D)                        # the canon decoy
    (in_f,) = _distinct_ids(world, F)
    (in_canon,) = _distinct_ids(world)
    reg = world.registry
    assert reg.distinct_rows(A, D, frame=F) == [in_f]
    assert reg.distinct_block(A, D, frame=F) == [f"{A}·distinct_from·{D}"]
    assert reg.distinct_rows(A, D) == [in_canon]
    assert world.porcelain.distinct_between(A, D) == [in_canon]
    with pytest.raises(TypeError):
        world.porcelain.distinct_between(A, D, frame=F)


def test_3a_correlation_conflicts_still_reads_its_frame(world):
    _legacy_row(world, A, "distinct_from", D, F)
    _legacy_row(world, A, "aka", D, F)
    world.porcelain.reject(B, C)                        # a canon decoy, nowhere near F
    found = world.registry.correlation_conflicts(frame=F)
    assert len(found) == 1
    assert {found[0]["a"], found[0]["b"]} == {A, D}
    assert found[0]["distinct_edges"] == [f"{A}·distinct_from·{D}"]
    assert world.registry.correlation_conflicts() == []


def test_3_distinct_block_descriptors_are_unchanged(world):
    world.porcelain.reject(A, D)
    assert world.registry.distinct_block(A, D) == [f"{A}·distinct_from·{D}"]
    assert world.registry.distinct_block(D, A) == [f"{A}·distinct_from·{D}"]


# --------------------------------------------------------------------- 5. MCP


def test_5_mcp_serves_both_reads(world):
    _history(world)
    assert {"closure", "distinct_between"} <= set(V1_READS)
    assert len(build_registry()) == 45
    assert dispatch(world, "closure", {"entity": A})["result"] == sorted([A, B])
    assert dispatch(world, "distinct_between", {"a": A, "b": D})["result"] == []


# --------------------------------------------------------------- 6. viewers


def test_6_a_viewer_is_refused_both(world):
    svc = WorldService()
    svc.attach(world, F)
    try:
        sess = svc.session("renderer")
        for verb, args in (("closure", {"entity": A}),
                           ("distinct_between", {"a": A, "b": D})):
            assert VIEWER_EXCLUDED[verb] == "a canon identity diagnostic"
            with pytest.raises(Refused, match="canon identity diagnostic"):
                sess.call(verb, **args)
    finally:
        svc.detach()
