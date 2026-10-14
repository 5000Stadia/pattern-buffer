"""PLAY-BIND-V1: ``bind``, the deterministic matcher for a turn's mentions.
No model is called: the stub only backs classification."""

from __future__ import annotations

import pytest

from patternbuffer import World, ingest, model
from patternbuffer import bind as bind_module
from patternbuffer.names import tokens_match
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path / "w.world", world_id="w:bind",
              model=StubModel(fallback=rule_classifier_fallback()))
    yield w
    w.close()


def _seed(w: World) -> None:
    """At valid time 1: a cellar holding the player, who holds Tomas Reed's
    chains; a laundry hold; a straw pile in the cellar."""
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:cellar", "attribute": "kind", "value": "room"},
        {"entity": "place:laundry_hold", "attribute": "kind", "value": "hold"},
        {"entity": "place:laundry_hold", "attribute": "name", "value": "laundry hold"},
        {"entity": "person:player", "attribute": "kind", "value": "person"},
        {"entity": "person:player", "attribute": "in", "value": "place:cellar"},
        {"entity": "obj:tomas_reed_chains", "attribute": "kind", "value": "chains"},
        {"entity": "obj:tomas_reed_chains", "attribute": "name",
         "value": "Tomas Reed's chains"},
        {"entity": "obj:tomas_reed_chains", "attribute": "held_by", "value": "person:player"},
        {"entity": "obj:straw_pile", "attribute": "kind", "value": "pile"},
        {"entity": "obj:straw_pile", "attribute": "name", "value": "straw pile"},
        {"entity": "obj:straw_pile", "attribute": "in", "value": "place:cellar"},
    ], classify="rules")


def _future(w: World) -> None:
    """At valid time 10: a lantern that doesn't exist before then."""
    w.ingestor.cursor.advance(9.0)
    w.ingest_structured([
        {"entity": "obj:brass_lantern", "attribute": "kind", "value": "lantern"},
        {"entity": "obj:brass_lantern", "attribute": "name", "value": "brass lantern"},
        {"entity": "obj:brass_lantern", "attribute": "in", "value": "place:cellar"},
    ], classify="rules")


def _one(w, rows, **kw):
    kw.setdefault("as_of", 5.0)
    kw.setdefault("scope", ("place:cellar",))
    return w.bind(rows, **kw)


# 1 ---------------------------------------------------------- construct's runs

def test_1_run13_chain_binds_the_held_chains(world):
    _seed(world)
    r = _one(world, [{"entity": "obj:chain", "attribute": "condition", "value": "broken",
                      "name": "chain"}])
    side = r.rows[0].subject
    assert (side.outcome, side.id, side.signal) == ("bound", "obj:tomas_reed_chains", "name")
    assert r.rows[0].admitted and r.rows[0].row["entity"] == "obj:tomas_reed_chains"


def test_1_run12_hold_binds_across_obj_and_place(world):
    _seed(world)
    r = _one(world, [{"entity": "obj:hold", "attribute": "state", "value": "damp"}],
             include=("place:laundry_hold",))
    assert r.rows[0].subject.id == "place:laundry_hold"


def test_1_run11_straw_binds_by_fragment(world):
    _seed(world)
    r = _one(world, [{"entity": "obj:straw", "attribute": "state", "value": "wet"}])
    assert r.rows[0].subject.id == "obj:straw_pile"


# 2 ---------------------------------------------------------------- future-only

def test_2_a_future_entity_is_never_bound_or_minted_over(world):
    _seed(world)
    _future(world)
    exact = _one(world, [{"entity": "obj:brass_lantern", "attribute": "lit", "value": True}],
                 mint=("obj",))
    named = _one(world, [{"entity": "obj:light", "attribute": "lit", "value": True,
                          "name": "brass lantern"}], mint=("obj",))
    by_kind = _one(world, [{"entity": "obj:lantern", "attribute": "lit", "value": True}],
                   mint=("obj",))
    for r in (exact, named, by_kind):
        side = r.rows[0].subject
        assert side.outcome == "future_only" and side.candidates == ("obj:brass_lantern",)
        assert not r.rows[0].admitted and r.mints == {}


def test_2_a_learned_alias_is_not_evidence_of_existence(world):
    """pbr (code review): refer writes `learned_alias` timeless; it must not make
    a future entity exist at every time."""
    _seed(world)
    _future(world)
    world.ingest_structured([{"entity": "obj:brass_lantern", "attribute": "learned_alias",
                              "value": "the glim", "timeless": True, "status": "inferred"}],
                            classify="rules")
    assert any(r.attribute == "learned_alias"
               for r in world.buffer.visible(entity="obj:brass_lantern"))
    r = _one(world, [{"entity": "obj:brass_lantern", "attribute": "lit", "value": True}],
             include=("obj:brass_lantern",))
    assert r.rows[0].subject.outcome == "future_only"
    assert r.excluded == ("obj:brass_lantern",)


def test_2_future_search_is_global(world):
    _seed(world)
    _future(world)
    r = _one(world, [{"entity": "obj:brass_lantern", "attribute": "lit", "value": True}],
             scope=(), mint=("obj",))
    assert r.rows[0].subject.outcome == "future_only"


# 3 ------------------------------------------------------------------ collision

def test_3_a_mint_clears_every_id_and_repeats_once(world):
    _seed(world)
    world.ingest_structured([{"entity": "obj:rope", "attribute": "kind", "value": "rope",
                              "frame": "knows:person:player"}], classify="rules")
    r = _one(world, [{"entity": "obj:rope", "attribute": "state", "value": "frayed"},
                     {"entity": "person:player", "attribute": "holds", "value": "obj:rope",
                      "value_type": "entity"}], mint=("obj",))
    assert r.mints == {"obj:rope": "obj:rope_2"}
    assert r.rows[0].row["entity"] == "obj:rope_2" and r.rows[1].row["value"] == "obj:rope_2"


def test_3_a_taken_suffix_moves_on(world):
    _seed(world)
    world.ingest_structured([
        {"entity": "obj:rope", "attribute": "kind", "value": "rope", "frame": "knows:person:player"},
        {"entity": "obj:rope_2", "attribute": "kind", "value": "rope",
         "frame": "knows:person:player"}], classify="rules")
    r = _one(world, [{"entity": "obj:rope", "attribute": "state", "value": "frayed"}],
             mint=("obj",))
    assert r.mints == {"obj:rope": "obj:rope_3"}


# 4-5 ---------------------------------------------------- ambiguity, compatibility

def test_4_two_name_matches_are_ambiguous(world):
    _seed(world)
    world.ingest_structured([
        {"entity": "obj:straw_hat", "attribute": "name", "value": "straw hat"},
        {"entity": "obj:straw_hat", "attribute": "in", "value": "place:cellar"}],
        classify="rules")
    r = _one(world, [{"entity": "obj:straw", "attribute": "state", "value": "wet"}])
    side = r.rows[0].subject
    assert side.outcome == "ambiguous"
    assert side.candidates == ("obj:straw_hat", "obj:straw_pile")
    assert not r.rows[0].admitted and r.rows[0].row is None


def test_5_person_and_thing_never_cross(world):
    _seed(world)
    r = _one(world, [{"entity": "person:straw", "attribute": "mood", "value": "calm"},
                     {"entity": "obj:player", "attribute": "state", "value": "worn"}])
    assert r.rows[0].subject.outcome == "unknown"
    assert r.rows[1].subject.outcome == "unknown"


# 6-7 ------------------------------------------------- pass-through, whole rows

def test_6_other_namespaces_are_kept_and_malformed_ids_reported(world):
    _seed(world)
    r = _one(world, [{"entity": "event:fall", "attribute": "agent", "value": "person:player"},
                     {"entity": "person:/you", "attribute": "mood", "value": "calm"}])
    assert r.rows[0].subject.outcome == "kept" and r.rows[0].subject.id == "event:fall"
    assert (r.rows[0].value.outcome, r.rows[0].value.id) == ("bound", "person:player")
    assert r.rows[1].subject.outcome == "malformed" and not r.rows[1].admitted


def test_7_one_failed_side_rejects_the_whole_row(world):
    _seed(world)
    r = _one(world, [{"entity": "obj:chain", "attribute": "in", "value": "obj:nowhere",
                      "value_type": "entity"}])
    row = r.rows[0]
    assert row.subject.outcome == "bound" and row.value.outcome == "unknown"
    assert not row.admitted and row.row is None


def test_7a_one_decision_per_raw_id(world):
    _seed(world)
    r = _one(world, [
        {"entity": "obj:chain", "attribute": "condition", "value": "broken", "name": "chain"},
        {"entity": "person:player", "attribute": "drops", "value": "obj:chain",
         "value_type": "entity"},
        {"entity": "obj:bucket", "attribute": "state", "value": "full"},
        {"entity": "obj:bucket", "attribute": "in", "value": "place:cellar"},
    ], mint=("obj",))
    assert r.rows[0].subject.id == r.rows[1].value.id == "obj:tomas_reed_chains"
    assert r.rows[2].subject.id == r.rows[3].subject.id == "obj:bucket"
    assert r.mints == {"obj:bucket": "obj:bucket"}


def test_7a_surfaces_that_disagree_are_ambiguous_in_every_row(world):
    _seed(world)
    r = _one(world, [
        {"entity": "obj:thing", "attribute": "state", "value": "x", "name": "straw pile"},
        {"entity": "obj:thing", "attribute": "state", "value": "y", "name": "chains"},
    ])
    assert {row.subject.outcome for row in r.rows} == {"ambiguous"}
    assert r.rows[0].subject.candidates == ("obj:straw_pile", "obj:tomas_reed_chains")


def test_7b_value_typing_is_the_hosts(world):
    _seed(world)
    r = _one(world, [
        {"entity": "obj:straw", "attribute": "name", "value": "obj:chain",
         "value_type": "literal"},
        {"entity": "person:player", "attribute": "note", "value": "obj:chain",
         "value_type": "unresolved"},
    ])
    assert r.rows[0].value is None and r.rows[1].value is None


# 8 ---------------------------------------------------------------- candidates

def test_8_scope_expands_at_as_of_and_include_is_exact(world):
    _seed(world)
    _future(world)
    r = world.bind([{"entity": "obj:brass_lantern", "attribute": "lit", "value": True}],
                   as_of=12.0, scope=("place:cellar",))
    assert r.rows[0].subject.outcome == "bound"
    early = world.bind([{"entity": "obj:straw_pile", "attribute": "x", "value": 1}],
                       as_of=5.0, include=("person:player", "obj:brass_lantern"))
    assert early.rows[0].subject.outcome == "out_of_scope"   # include doesn't expand
    assert early.excluded == ("obj:brass_lantern",)


def test_8_widen_needs_a_name_row(world):
    _seed(world)
    r = world.bind([{"entity": "place:hold", "attribute": "x", "value": 1, "name": "laundry hold"},
                    {"entity": "place:cellar", "attribute": "x", "value": 1}],
                   as_of=5.0, widen=("place",))
    assert r.rows[0].subject.id == "place:laundry_hold"
    assert r.rows[1].subject.outcome == "out_of_scope"       # slug only: not widened


# 9 ------------------------------------------------------------- number matching

@pytest.mark.parametrize("a,b", [("chains", "chain"), ("keys", "key"), ("berries", "berry"),
                                 ("boxes", "box"), ("matches", "match"), ("buses", "bus"),
                                 ("gases", "gas"), ("heroes", "hero")])
def test_9_plural_pairs_match(a, b):
    assert tokens_match(a, b) and tokens_match(b, a)


@pytest.mark.parametrize("a,b", [("news", "new"), ("glasses", "glass"), ("arms", "arm"),
                                 ("analyses", "analysis"), ("statuses", "statu"),
                                 ("gas", "ga"), ("mice", "mouse")])
def test_9_non_pairs_never_match(a, b):
    assert not tokens_match(a, b)


def test_9a_value_sides_follow_ingests_predicate(world):
    _seed(world)
    assert ingest.infer_value_type is model.infer_value_type
    assert bind_module.infer_value_type is model.infer_value_type
    r = _one(world, [{"entity": "person:player", "attribute": "in", "value": "event:later"},
                     {"entity": "person:player", "attribute": "in", "value": "person:you"}])
    assert r.rows[0].value.outcome == "kept"
    assert r.rows[1].value is not None


def test_9b_an_exact_future_id_beats_a_current_name(world):
    _seed(world)
    world.ingestor.cursor.advance(9.0)
    world.ingest_structured([{"entity": "obj:straw_pile_2", "attribute": "kind",
                              "value": "pile"}], classify="rules")
    r = _one(world, [{"entity": "obj:straw_pile_2", "attribute": "x", "value": 1}])
    assert r.rows[0].subject.outcome == "future_only"


def test_9c_a_value_only_id_is_taken(world):
    _seed(world)
    world.ingest_structured([{"entity": "person:player", "attribute": "seeks",
                              "value": "obj:key", "value_type": "entity"}], classify="rules")
    assert "obj:key" in world.buffer.ids()
    r = _one(world, [{"entity": "obj:key", "attribute": "x", "value": 1}], mint=("obj",))
    assert r.mints == {"obj:key": "obj:key_2"}


def test_9d_a_closure_binds_its_canonical_id(world):
    _seed(world)
    world.porcelain.merge("obj:straw_pile", "obj:straw_heap", evidence="test: one heap")
    r = _one(world, [{"entity": "obj:straw_heap", "attribute": "x", "value": 1}])
    assert r.rows[0].subject.outcome == "bound"
    assert r.rows[0].subject.id == world.registry.resolve("obj:straw_heap")


# 10-11 -------------------------------------------------- read-only, MCP

def test_10_bind_writes_nothing_and_repeats(world):
    _seed(world)
    head = world.buffer.head()
    rows = [{"entity": "obj:chain", "attribute": "x", "value": 1},
            {"entity": "obj:new_thing", "attribute": "x", "value": 1}]
    first = _one(world, rows, mint=("obj",))
    assert _one(world, rows, mint=("obj",)) == first
    assert world.buffer.head() == head


def test_11_mcp_lists_bind_and_round_trips(world):
    from patternbuffer import mcp
    _seed(world)
    assert len(mcp.V1_TOOLS) == 46 and "bind" in mcp.V1_READS
    out = mcp.dispatch(world, "bind", {"rows": [{"entity": "obj:chain", "attribute": "x",
                                                 "value": 1}],
                                       "as_of": 5.0, "scope": ["place:cellar"]})
    assert "obj:tomas_reed_chains" in str(out)


def test_12_as_of_inf_is_the_head(world):
    """construct m01b969: a world with no play horizon binds at the head with
    as_of=math.inf. An entity whose rows start late binds, never future_only,
    and inf binds exactly as axis_heads()'s valid_head does."""
    import math
    _seed(world)
    _future(world)
    world.ingestor.cursor.advance(1e6)
    world.ingest_structured([{"entity": "obj:far_bell", "attribute": "name", "value": "far bell"},
                             {"entity": "obj:far_bell", "attribute": "in",
                              "value": "place:cellar"}], classify="rules")
    rows = [{"entity": "obj:far_bell", "attribute": "x", "value": 1},
            {"entity": "obj:lantern", "attribute": "x", "value": 1},
            {"entity": "obj:chain", "attribute": "x", "value": 1}]
    at_inf = world.porcelain.bind(rows, as_of=math.inf, scope=["place:cellar"])
    head = world.porcelain.axis_heads()["valid_head"]
    at_head = world.porcelain.bind(rows, as_of=head, scope=["place:cellar"])
    assert [r["subject"]["outcome"] for r in at_inf["rows"]] == ["bound"] * 3
    assert at_inf["rows"][0]["subject"]["id"] == "obj:far_bell"
    assert at_inf == at_head
