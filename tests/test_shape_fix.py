"""SHAPE-FIX-V1: deferred-coreference adjudication, retype, phantom suppression.

Bucket 1: adjudicate_deferred() merges only the structurally-decisive
fragment-subsumption subset; the semantic trap stays a proposal. Bucket 2:
retype is a typing correction distinct from merge (artifact edges retracted,
child containment preserved, never a veto bypass). Bucket 4: malformed ids
skip with a typed receipt; the extractor suppresses narrative-voice phantoms
and binds deixis to pov.
"""

import pytest

from patternbuffer import World
from patternbuffer.ingest import _EXTRACT_RULES_FULL, _EXTRACT_RULES_LEAN
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "sf.world", world_id="w:sf", model=stub)
    yield w
    w.close()


def _person(w, eid, name=None, aliases=(), extra=()):
    items = [{"entity": eid, "attribute": "kind", "value": "person", "timeless": True}]
    if name:
        items.append({"entity": eid, "attribute": "name", "value": name, "timeless": True})
    for a in aliases:
        items.append({"entity": eid, "attribute": "alias", "value": a, "timeless": True})
    items.extend(extra)
    w.ingest_structured(items)


# ------------------------------------------------- Win 1: adjudicate_deferred

def test_fragment_trio_merges(world):
    # the founder's pencil case: three mints of one pencil — subsumed fragments
    for eid, name in (("obj:pencil", "pencil"), ("obj:pencil_1", "pencil"),
                      ("obj:plain_pencil", "plain pencil")):
        world.ingest_structured([
            {"entity": eid, "attribute": "kind", "value": "object", "timeless": True},
            {"entity": eid, "attribute": "name", "value": name, "timeless": True},
        ])
    world.registry.maybe_same_as("obj:pencil", "obj:pencil_1", evidence="t")
    world.registry.maybe_same_as("obj:pencil", "obj:plain_pencil", evidence="t")
    out = world.porcelain.adjudicate_deferred()
    assert len(out["merged"]) == 2
    assert world.registry.resolve("obj:pencil_1") == world.registry.resolve("obj:pencil")
    assert world.registry.resolve("obj:plain_pencil") == world.registry.resolve("obj:pencil")


def test_trap_pair_stays_residue_each_side_distinctive(world):
    # mara(relic, alias "the crown") ~ mara_thist: each side holds distinctive
    # non-shared tokens -> two individuated things sharing a token -> residue
    _person(world, "person:mara", name="mara", aliases=("the crown",))
    _person(world, "person:mara_thist", name="mara thist")
    world.registry.maybe_same_as("person:mara", "person:mara_thist", evidence="t")
    out = world.porcelain.adjudicate_deferred()
    assert out["merged"] == []
    assert world.registry.resolve("person:mara") != world.registry.resolve("person:mara_thist")
    assert any({p["a"], p["b"]} == {"person:mara", "person:mara_thist"}
               for p in out["residue"])


def test_subsumed_fragment_merges_but_relating_edge_blocks(world):
    _person(world, "person:tovin", name="tovin")
    _person(world, "person:tovin_beck", name="tovin beck")
    _person(world, "person:lysa", name="lysa",
            extra=[{"entity": "person:lysa", "attribute": "ally_of",
                    "value": "person:lysa_fen", "value_type": "entity",
                    "valid_from": 1.0}])
    _person(world, "person:lysa_fen", name="lysa fen")
    world.registry.maybe_same_as("person:tovin", "person:tovin_beck", evidence="t")
    world.registry.maybe_same_as("person:lysa", "person:lysa_fen", evidence="t")
    out = world.porcelain.adjudicate_deferred()
    assert len(out["merged"]) == 1        # tovin merges; lysa pair edge-blocked
    assert world.registry.resolve("person:tovin") == world.registry.resolve("person:tovin_beck")
    assert world.registry.resolve("person:lysa") != world.registry.resolve("person:lysa_fen")


def test_aka_correlated_pair_never_merges(world):
    # correlation is non-collapsing by design: an aka pair is two facets
    _person(world, "person:masked", name="masked")
    _person(world, "person:masked_figure", name="masked figure")
    world.correlate("person:masked", "person:masked_figure", evidence="reveal",
                    valid_from=1.0)
    world.registry.maybe_same_as("person:masked", "person:masked_figure", evidence="t")
    out = world.porcelain.adjudicate_deferred()
    assert out["merged"] == []
    assert world.registry.resolve("person:masked") != world.registry.resolve("person:masked_figure")


def test_adjudicate_idempotent_and_reconcile_unchanged(world):
    _person(world, "person:tovin", name="tovin")
    _person(world, "person:tovin_beck", name="tovin beck")
    world.registry.maybe_same_as("person:tovin", "person:tovin_beck", evidence="t")
    first = world.porcelain.adjudicate_deferred()
    second = world.porcelain.adjudicate_deferred()
    assert len(first["merged"]) == 1 and second["merged"] == []
    assert world.registry.reconcile() == 0     # nothing left for the default pass


# ------------------------------------- Win 4: durable-contradiction veto

def test_contradictory_roles_block_auto_merge(world):
    # HD 089: pavel_orra (retrieval lead) fused into tom_apprentice despite
    # contradictory standing role rows — the veto keeps them a proposal
    _person(world, "person:pavel", name="pavel",
            extra=[{"entity": "person:pavel", "attribute": "role",
                    "value": "retrieval lead", "valid_from": 1.0}])
    _person(world, "person:pavel_orra", name="pavel orra",
            extra=[{"entity": "person:pavel_orra", "attribute": "role",
                    "value": "defense apprentice", "valid_from": 1.0}])
    world.classifier.set(
        world.buffer.visible(attribute="role")[0].id, "DISPOSITIONAL")
    world.classifier.set(
        world.buffer.visible(attribute="role")[1].id, "DISPOSITIONAL")
    assert world.registry.durable_contradictions(
        "person:pavel", "person:pavel_orra")
    world.registry.maybe_same_as("person:pavel", "person:pavel_orra", evidence="t")
    out = world.porcelain.adjudicate_deferred()
    assert out["merged"] == []
    assert world.registry.resolve("person:pavel") != world.registry.resolve("person:pavel_orra")
    assert world.registry.reconcile() == 0     # _mergeable declines too
    assert world.registry.resolve("person:pavel") != world.registry.resolve("person:pavel_orra")
    # the (C) bundle names the contradiction for the host
    props = world.porcelain.proposals()
    pair = [p for p in props
            if {p["a"], p["b"]} == {"person:pavel", "person:pavel_orra"}]
    assert pair and pair[0]["auto_decline"]["code"] == "durable_contradiction"
    assert "role" in pair[0]["auto_decline"]["durable_contradictions"][0]


def test_same_role_fragments_still_merge(world):
    # the veto only fires on CONTRADICTION — agreeing standing facts don't block
    _person(world, "person:cass", name="cass",
            extra=[{"entity": "person:cass", "attribute": "role",
                    "value": "clerk", "valid_from": 1.0}])
    _person(world, "person:cass_reed", name="cass reed",
            extra=[{"entity": "person:cass_reed", "attribute": "role",
                    "value": "clerk", "valid_from": 1.0}])
    for row in world.buffer.visible(attribute="role"):
        world.classifier.set(row.id, "DISPOSITIONAL")
    world.registry.maybe_same_as("person:cass", "person:cass_reed", evidence="t")
    out = world.porcelain.adjudicate_deferred()
    assert len(out["merged"]) == 1
    assert world.registry.resolve("person:cass") == world.registry.resolve("person:cass_reed")


def test_transient_state_difference_does_not_block(world):
    # STATE rows (mood) differing never read as a durable contradiction
    _person(world, "person:finn", name="finn",
            extra=[{"entity": "person:finn", "attribute": "mood",
                    "value": "grim", "valid_from": 1.0}])
    _person(world, "person:finn_ash", name="finn ash",
            extra=[{"entity": "person:finn_ash", "attribute": "mood",
                    "value": "calm", "valid_from": 1.0}])
    for row in world.buffer.visible(attribute="mood"):
        world.classifier.set(row.id, "STATE")
    assert world.registry.durable_contradictions(
        "person:finn", "person:finn_ash") == []
    world.registry.maybe_same_as("person:finn", "person:finn_ash", evidence="t")
    out = world.porcelain.adjudicate_deferred()
    assert len(out["merged"]) == 1


# ---------------------------------------------------------- Win 2: retype

def test_retype_case_a_corrects_kind(world):
    world.ingest_structured([
        {"entity": "obj:cinder_crown", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "obj:cinder_crown", "attribute": "name", "value": "cinder crown",
         "timeless": True},
    ])
    r = world.porcelain.retype("obj:cinder_crown", "relic", evidence="typing slip")
    assert r["outcome"] == "retyped" and r["retracted"]
    fold = world.state("obj:cinder_crown", "kind")
    assert fold.winner.value == "relic" and not fold.conflicted


def test_retype_case_b_absorbs_spurious_twin(world):
    # place:harth has villagers (incoming children); person:harth is bare
    world.ingest_structured([
        {"entity": "place:harth", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:harth", "attribute": "name", "value": "harth", "timeless": True},
        {"entity": "person:villager", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:villager", "attribute": "in", "value": "place:harth",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:harth", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:harth", "attribute": "name", "value": "harth", "timeless": True},
    ])
    r = world.porcelain.retype("person:harth", "place", evidence="typing slip",
                               absorb="place:harth")
    assert r["outcome"] == "merged"
    assert world.registry.resolve("person:harth") == world.registry.resolve("place:harth")
    # child containment preserved: the villager is still in harth
    assert world.registry.resolve("place:harth") in {
        world.registry.resolve(c) for c in world.locate("person:villager")}


def test_retype_case_b_retracts_artifact_edge(world):
    # obj:street holds the protagonist (nonsense chain); place:street is real;
    # an inter-closure containment edge (obj:street in place:street) is the
    # artifact that must be retracted, not inherited as a self-edge
    world.ingest_structured([
        {"entity": "place:street", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:street", "attribute": "name", "value": "street", "timeless": True},
        {"entity": "place:street", "attribute": "connects_to", "value": "place:yard",
         "value_type": "entity", "timeless": True},
        {"entity": "place:yard", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "obj:street", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:street", "attribute": "name", "value": "street", "timeless": True},
        {"entity": "obj:street", "attribute": "in", "value": "place:street",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:protagonist", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:protagonist", "attribute": "in", "value": "obj:street",
         "value_type": "entity", "valid_from": 1.0},
    ])
    r = world.porcelain.retype("obj:street", "place", evidence="typing slip",
                               absorb="place:street")
    assert r["outcome"] == "merged" and r["retracted"]
    assert world.registry.resolve("obj:street") == world.registry.resolve("place:street")
    # the protagonist's location now resolves through the merged street
    assert world.registry.resolve("place:street") in {
        world.registry.resolve(c) for c in world.locate("person:protagonist")}


def test_retype_not_a_slip_is_vetoed(world):
    # chest-in-room sharing an alias: both sides real -> retype refuses (no
    # containment-veto bypass)
    world.ingest_structured([
        {"entity": "place:room", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:room", "attribute": "alias", "value": "storage", "timeless": True},
        {"entity": "obj:chest", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:chest", "attribute": "alias", "value": "storage", "timeless": True},
        {"entity": "obj:chest", "attribute": "state", "value": "locked", "valid_from": 1.0},
        {"entity": "obj:chest", "attribute": "in", "value": "place:room",
         "value_type": "entity", "valid_from": 1.0},
    ])
    r = world.porcelain.retype("obj:chest", "place", evidence="nope",
                               absorb="place:room")
    assert r["outcome"] == "vetoed_not_a_slip"
    assert world.registry.resolve("obj:chest") != world.registry.resolve("place:room")


def test_retype_distinct_from_stays_absolute(world):
    world.ingest_structured([
        {"entity": "place:harth2", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:harth2", "attribute": "name", "value": "harth2", "timeless": True},
        {"entity": "person:h2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:h2", "attribute": "name", "value": "harth2", "timeless": True},
    ])
    world.porcelain.reject("person:h2", "place:harth2")
    r = world.porcelain.retype("person:h2", "place", evidence="slip",
                               absorb="place:harth2")
    assert r["outcome"] == "vetoed" and r["reason"] == "distinct_from"


def test_typing_conflicts_surfaces_slip_and_clean_world_empty(world):
    assert world.porcelain.typing_conflicts() == []
    world.ingest_structured([
        {"entity": "place:harth", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:harth", "attribute": "name", "value": "harth", "timeless": True},
        {"entity": "person:v1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:v1", "attribute": "in", "value": "place:harth",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:harth", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:harth", "attribute": "name", "value": "harth", "timeless": True},
    ])
    tc = world.porcelain.typing_conflicts()
    assert len(tc) == 1
    assert tc[0]["spurious"] == "person:harth" and tc[0]["target"] == "place:harth"
    assert tc[0]["shared_anchor"] == "harth"


# ------------------------------------------- Win 3: phantom suppression (4a-c)

def test_malformed_id_skips_with_receipt(world):
    receipt = world.porcelain.ingest_structured([
        {"entity": "person:/you", "attribute": "mood", "value": "tense",
         "valid_from": 1.0},
        {"entity": "person:real", "attribute": "kind", "value": "person",
         "timeless": True},
    ])
    assert [s["reason"] for s in receipt.skipped] == ["malformed_id"]
    assert receipt.skipped[0]["entity"] == "person:/you"
    entities = {r.entity for r in world.buffer.visible()}
    assert "person:/you" not in entities and "person:real" in entities


def test_malformed_entity_value_skips(world):
    receipt = world.porcelain.ingest_structured([
        {"entity": "person:real", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:real", "attribute": "in", "value": "place:/coffee_house",
         "value_type": "entity", "valid_from": 1.0},
    ])
    assert [s["reason"] for s in receipt.skipped] == ["malformed_id"]
    assert not world.locate("person:real")


def test_malformed_caused_by_and_same_as_skip(world):
    # side-channel entity edges pass the same gate as the main row
    receipt = world.porcelain.ingest_structured([
        {"entity": "event:fall", "attribute": "kind", "value": "event",
         "timeless": True, "caused_by": "event:/push"},
        {"entity": "person:real2", "attribute": "kind", "value": "person",
         "timeless": True, "same_as": "person:/me"},
    ])
    reasons = {(s["attribute"], s["reason"]) for s in receipt.skipped}
    assert ("caused_by", "malformed_id") in reasons
    assert ("same_as", "malformed_id") in reasons
    # the main rows themselves ingested; the phantoms did not
    entities = {r.entity for r in world.buffer.visible()}
    assert "event:fall" in entities and "person:real2" in entities
    assert not [r for r in world.buffer.visible(attribute="caused_by")]
    assert not [r for r in world.buffer.visible(attribute="maybe_same_as")]


def test_typing_conflicts_carries_asymmetry(world):
    world.ingest_structured([
        {"entity": "place:vale", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:vale", "attribute": "name", "value": "vale", "timeless": True},
        {"entity": "person:p1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p1", "attribute": "in", "value": "place:vale",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:vale", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:vale", "attribute": "name", "value": "vale", "timeless": True},
    ])
    tc = world.porcelain.typing_conflicts()
    assert len(tc) == 1
    asym = tc[0]["asymmetry"]
    assert asym["spurious_own_facts"] == 0
    assert asym["target_children"] >= 1


def test_authority_violation_raises_even_on_malformed_row(world):
    # ordering: the authority gate runs BEFORE the malformed-id skip
    with pytest.raises(ValueError, match="generated"):
        world.ingest_structured([
            {"entity": "person:/ghost", "attribute": "mood", "value": "x",
             "status": "generated", "frame": "canon", "valid_from": 1.0},
        ])


def test_extractor_prompts_carry_suppression_and_pov(world):
    for rules in (_EXTRACT_RULES_FULL, _EXTRACT_RULES_LEAN):
        assert "narrative voice is not an entity" in rules
        assert "never mint a person from a bare pronoun" in rules.lower()
    with pytest.raises(ValueError, match="pov"):
        world.extract("text", pov="person:/bad")


def test_pov_threads_into_prompt(world, tmp_path):
    seen = {}

    def spy(prompt, schema):
        seen["prompt"] = prompt
        return {"items": []}

    w = World(tmp_path / "pov.world", world_id="w:pov", model=spy)
    try:
        w.porcelain.extract("I run my hand along the counter.", pov="person:hero")
        assert "person:hero" in seen["prompt"]
        # HD 126 / Cx 570: pin the deictic INSTRUCTION LINE itself (word-bounded,
        # rules section only — an unbounded whole-prompt substring search passes
        # even when forms are deleted, because the base rules and the passage
        # fixture contain look-alike words).
        import re
        rules_section = seen["prompt"].split("\n\nPASSAGE:\n")[0]
        line = next(l for l in rules_section.splitlines()
                    if l.startswith("- Viewpoint deixis:"))
        for form in ("I", "me", "my", "mine", "myself", "we", "us", "our",
                     "ours", "you", "your", "yours"):
            assert re.search(rf"\b{form}\b", line), f"deictic form {form!r} missing"
        # the complete no-sideways clause, on that same line
        assert ("singular possessee (my hand, your coat) is NEVER attributed "
                "to any other present character") in line
        # the plural scoping (Cx 570 #1): includes the POV, never exclusive
        # ownership, never guessed members, never wholesale rebinding
        assert "INCLUDE person:hero" in line
        assert "never guess the other members" in line
        assert "never rebind the plural wholesale" in line
    finally:
        w.close()
