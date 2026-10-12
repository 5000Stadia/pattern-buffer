"""IDENTITY-ROOT-CAUSES-V1: automatic merges the evidence can't support.

One group of tests per rule (specs/IDENTITY-ROOT-CAUSES-V1.md):
- §1 name-like anchors (the corpus sentences are reproduced as fixtures);
- §2 a retracted merge stays retracted;
- §3 every merge records who decided it;
- §4 no automatic merge of a closure that owns a `knows:` frame.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from patternbuffer import World
from patternbuffer.identity import _anchor_words, _name_like
from patternbuffer.roles import RoleViolation
from patternbuffer.testing import StubModel, rule_classifier_fallback

NOT_NAME_LIKE = "reconcile: shared anchor not name-like (adjudicate)"
FRAME_OWNER = "reconcile: frame owner, host confirmation required"
GENERIC = "reconcile: shared anchor, gate declined (adjudicate)"


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path / "irc.world", world_id="w:irc",
              model=StubModel(fallback=rule_classifier_fallback()))
    yield w
    w.close()


def _thing(w, eid: str, *, name: str | None = None, alias: str | None = None,
           kind: str = "person", frame: str | None = None) -> None:
    items = [{"entity": eid, "attribute": "kind", "value": kind, "timeless": True}]
    if name:
        items.append({"entity": eid, "attribute": "name", "value": name, "timeless": True})
    if alias:
        items.append({"entity": eid, "attribute": "alias", "value": alias, "timeless": True})
    w.ingest_structured(items)


def _proposals(w) -> dict[frozenset[str], str | None]:
    return {frozenset((p["a"], p["b"])): p["evidence"]
            for p in w.registry.enumerate_proposals()}


def _R(w, e: str) -> str:
    return w.registry.resolve(e)


def _decided(w, receipt_or_event) -> str:
    event = (receipt_or_event["merge_event_id"]
             if isinstance(receipt_or_event, dict) else receipt_or_event)
    return w.registry.merge_decided_by(event)


def _edge_id(w, a: str, b: str) -> str:
    """The `same_as` assertion that joined a and b (named first by the registry)."""
    return w.registry._same_as_path_ids(a, b)[0]


# ============================================================ §1 name-like

def test_anchor_words_are_raw():
    assert _anchor_words("The Cafe de la Digue") == ["the", "cafe", "de", "la", "digue"]
    assert _anchor_words("received corin in the guild hall") == [
        "received", "corin", "in", "the", "union", "hall"]
    assert _anchor_words("Kit's  key--ring_x") == ["kit's", "key", "ring", "x"]
    assert _anchor_words("") == []


def test_name_like_predicate():
    assert _name_like("ilsa renn")
    assert _name_like("the old keeper of lights")             # exactly five words
    assert not _name_like("the old keeper of the lights")     # six
    for phrase in ("my apprentice", "his apprentice", "her prayer book",
                   "our house", "your coat", "their dog", "its handle"):
        assert not _name_like(phrase), phrase
    assert _name_like("mythic apprentice")                    # first token, not prefix
    assert _name_like("hero's apprentice")


SENTENCE = "singing into a wind that had tried and failed to quiet them"


def test_six_people_sharing_a_sentence_are_proposals_not_a_fusion(world):
    """The ida group: six people fused on a clause one extraction chunk used
    as an alias. Seven words; no merge, a proposal per pair, alias still reads."""
    people = [f"person:{n}" for n in ("ida", "lena", "mae", "nell", "opal", "rue")]
    for p in people:
        _thing(world, p, alias=SENTENCE)
    assert world.registry.reconcile() == 0
    assert len({_R(world, p) for p in people}) == 6
    props = _proposals(world)
    assert len(props) == 15
    assert set(props.values()) == {NOT_NAME_LIKE}
    # not identity evidence, still a good alias
    assert world.registry.by_alias(SENTENCE) == set(people)
    assert {p["auto_decline"]["code"] for p in world.registry.enumerate_proposals()} \
        == {"not_name_like"}


def test_a_clause_as_a_name_is_declined_too(world):
    """Names are held to the rule as aliases are: 'received corin in the union
    hall' (six words) fused anselm_varo with corin."""
    clause = "received corin in the guild hall"
    _thing(world, "person:anselm_varo", name=clause)
    _thing(world, "person:corin", name=clause)
    assert world.registry.reconcile() == 0
    assert _proposals(world) == {
        frozenset(("person:anselm_varo", "person:corin")): NOT_NAME_LIKE}


def test_a_title_sentence_fuses_nothing(world):
    title = "the true tale of the crown"
    _thing(world, "obj:book", name=title, kind="object")
    _thing(world, "obj:band", name=title, kind="object")
    assert world.registry.reconcile() == 0


def test_speaker_relative_anchors_do_not_fuse_the_protagonist(world):
    """'my apprentice' names a different person for every speaker."""
    for eid in ("person:tamsin", "person:ash_apprentice", "person:dorn_vale"):
        _thing(world, eid)
    world.ingest_structured([
        {"entity": "person:tamsin", "attribute": "alias", "value": "my apprentice",
         "timeless": True},
        {"entity": "person:ash_apprentice", "attribute": "alias", "value": "my apprentice",
         "timeless": True},
        {"entity": "person:dorn_vale", "attribute": "alias", "value": "his apprentice",
         "timeless": True},
        {"entity": "person:ash_apprentice", "attribute": "alias", "value": "his apprentice",
         "timeless": True},
    ])
    assert world.registry.reconcile() == 0
    props = _proposals(world)
    assert props[frozenset(("person:tamsin", "person:ash_apprentice"))] == NOT_NAME_LIKE
    assert props[frozenset(("person:dorn_vale", "person:ash_apprentice"))] == NOT_NAME_LIKE
    assert len({_R(world, e) for e in ("person:tamsin", "person:ash_apprentice",
                                       "person:dorn_vale")}) == 3


def test_a_real_name_and_a_five_word_alias_still_merge(world):
    _thing(world, "person:a", name="ilsa renn")
    _thing(world, "person:b", name="ilsa renn")
    _thing(world, "person:c", alias="the old keeper of lights")
    _thing(world, "person:d", alias="the old keeper of lights")
    assert world.registry.reconcile() == 2
    assert _R(world, "person:a") == _R(world, "person:b")
    assert _R(world, "person:c") == _R(world, "person:d")


def test_a_six_word_alias_is_declined(world):
    _thing(world, "person:c", alias="the old keeper of the lights")
    _thing(world, "person:d", alias="the old keeper of the lights")
    assert world.registry.reconcile() == 0
    assert list(_proposals(world).values()) == [NOT_NAME_LIKE]


def test_a_name_like_anchor_beside_a_sentence_still_decides(world):
    """The sentence is dropped from the evidence; the real shared name stands."""
    for eid in ("person:a", "person:b"):
        _thing(world, eid, name="ilsa renn", alias=SENTENCE)
    assert world.registry.reconcile() == 1


def test_promotion_declines_a_sentence_like_proposal(world):
    _thing(world, "person:a", alias=SENTENCE)
    _thing(world, "person:b", alias=SENTENCE)
    world.registry.maybe_same_as("person:a", "person:b", evidence="seed")
    assert world.registry.promote_identity_proposals() == 0
    assert _R(world, "person:a") != _R(world, "person:b")


def test_the_decline_is_not_a_live_fragmentation(world):
    """name_collisions reports the pair as an auto-declined proposal once logged."""
    _thing(world, "person:a", alias=SENTENCE)
    _thing(world, "person:b", alias=SENTENCE)
    world.registry.reconcile()
    (entry,) = world.registry.name_collisions()
    assert entry["pairs"][0]["status"] == "auto_declined"
    assert entry["pairs"][0]["reason"] == "not_name_like"


def test_subsumption_ignores_anchors_that_are_not_name_like(world):
    """`tovin` ⊆ `tovin beck` merges; 'my friend tovin' ⊆ 'my friend tovin beck'
    is two possessive phrases, not a fragment of one name."""
    _thing(world, "person:t1", name="tovin")
    _thing(world, "person:t2", name="tovin beck")
    world.registry.maybe_same_as("person:t1", "person:t2", evidence="seed")
    _thing(world, "person:f1", alias="my friend tovin")
    _thing(world, "person:f2", alias="my friend tovin beck")
    world.registry.maybe_same_as("person:f1", "person:f2", evidence="seed")
    out = world.registry.adjudicate_deferred()
    assert len(out["merged"]) == 1
    assert _R(world, "person:t1") == _R(world, "person:t2")
    assert _R(world, "person:f1") != _R(world, "person:f2")


def test_a_host_can_still_confirm_a_declined_pair(world):
    _thing(world, "person:a", alias=SENTENCE)
    _thing(world, "person:b", alias=SENTENCE)
    world.registry.reconcile()
    receipt = world.registry.confirm("person:a", "person:b")
    assert receipt["outcome"] == "merged"


# ============================================================ §2 retracted

def _host_merge_and_retract(w, a: str, b: str) -> str:
    receipt = w.registry.guarded_merge(a, b, "host judged")
    assert receipt["outcome"] == "merged"
    edge = _edge_id(w, a, b)
    w.porcelain.retract(edge, "no: two different people")
    assert _R(w, a) != _R(w, b)
    return edge


def test_a_retracted_merge_is_not_remade_by_reconcile(world):
    """Today reconcile silently re-makes the host's correction."""
    _thing(world, "person:a", name="ilsa renn")
    _thing(world, "person:b", name="ilsa renn")
    _host_merge_and_retract(world, "person:a", "person:b")
    head = world.buffer.head()
    assert world.registry.reconcile() == 0
    assert _R(world, "person:a") != _R(world, "person:b")
    assert _proposals(world) == {}                  # nor re-proposed
    assert world.buffer.head() == head              # reconcile wrote nothing


def test_a_retracted_merge_is_not_promoted_or_adjudicated(world):
    _thing(world, "person:t1", name="tovin")
    _thing(world, "person:t2", name="tovin beck")
    _host_merge_and_retract(world, "person:t1", "person:t2")
    world.registry.maybe_same_as("person:t1", "person:t2", evidence="seed")
    assert world.registry.promote_identity_proposals() == 0
    assert world.registry.adjudicate_deferred()["merged"] == []
    assert _R(world, "person:t1") != _R(world, "person:t2")


def test_settled_apart_reaches_the_whole_closures(world):
    _thing(world, "person:x", name="ilsa renn")
    _thing(world, "person:y", name="ilsa renn")
    _host_merge_and_retract(world, "person:x", "person:y")
    _thing(world, "person:x2", name="x two")
    _thing(world, "person:y2", name="y two")
    world.registry.guarded_merge("person:x2", "person:x", "host")
    world.registry.guarded_merge("person:y2", "person:y", "host")
    for e in ("person:x2", "person:y2"):
        world.ingest_structured([
            {"entity": e, "attribute": "name", "value": "shared name", "timeless": True}])
    assert world.registry.reconcile() == 0
    assert _R(world, "person:x2") != _R(world, "person:y2")


def test_the_host_verbs_still_decide_a_settled_pair(world):
    _thing(world, "person:a", name="ilsa renn")
    _thing(world, "person:b", name="ilsa renn")
    _host_merge_and_retract(world, "person:a", "person:b")
    again = world.registry.guarded_merge("person:a", "person:b", "re-judged")
    assert again["outcome"] == "merged"
    assert _R(world, "person:a") == _R(world, "person:b")


def test_confirm_still_merges_a_settled_pair(world):
    _thing(world, "person:a", name="ilsa renn")
    _thing(world, "person:b", name="ilsa renn")
    _host_merge_and_retract(world, "person:a", "person:b")
    world.registry.maybe_same_as("person:a", "person:b", evidence="host re-proposed")
    assert world.registry.confirm("person:a", "person:b")["outcome"] == "merged"


def test_reject_still_writes_distinct_from(world):
    _thing(world, "person:a", name="ilsa renn")
    _thing(world, "person:b", name="ilsa renn")
    _host_merge_and_retract(world, "person:a", "person:b")
    assert world.registry.reject("person:a", "person:b")["outcome"] == "rejected"


def test_retracting_only_the_merge_event_settles_nothing(world):
    """Only a marked retraction of the `same_as` edge changes the closure."""
    _thing(world, "person:a", name="ilsa renn")
    _thing(world, "person:b", name="ilsa renn")
    receipt = world.registry.guarded_merge("person:a", "person:b", "host")
    event = receipt["merge_event_id"]
    kind_row = world.buffer.visible(entity=event, attribute="kind")[0]
    world.porcelain.retract(kind_row.id, "wrong event")
    assert _R(world, "person:a") == _R(world, "person:b")        # edge stands
    assert world.buffer.retracted_targets(attribute="same_as") == []
    assert not world.registry._settled_apart("person:a", "person:b")


def test_retracted_targets_honor_the_asserted_pin(world):
    _thing(world, "person:a", name="ilsa renn")
    _thing(world, "person:b", name="ilsa renn")
    world.registry.guarded_merge("person:a", "person:b", "host")
    edge = _edge_id(world, "person:a", "person:b")
    before = world.buffer.head()
    world.porcelain.retract(edge, "undo")
    after = world.buffer.head()
    assert world.buffer.retracted_targets(attribute="same_as", asserted_as_of=before) == []
    got = world.buffer.retracted_targets(attribute="same_as", asserted_as_of=after)
    assert [r.id for r in got] == [edge]
    assert [r.id for r in world.buffer.retracted_targets(attribute="same_as")] == [edge]
    assert world.buffer.retracted_targets(attribute="maybe_same_as") == []


def test_a_forged_retraction_settles_nothing(world):
    """A `retracts` row without truth maintenance's mark hides nothing and so
    records no decision; the buffer refuses to write one."""
    _thing(world, "person:a", name="ilsa renn")
    _thing(world, "person:b", name="ilsa renn")
    world.registry.guarded_merge("person:a", "person:b", "host")
    edge = _edge_id(world, "person:a", "person:b")
    with pytest.raises(RoleViolation):
        world.buffer.append(entity=edge, attribute="retracts", value="x",
                            role=world.registry._ingestor, status="inferred")
    assert world.buffer.retracted_targets(attribute="same_as") == []


def test_the_retracted_view_follows_the_log(world):
    """Cached per log version: a later retraction is seen, no stale answer."""
    _thing(world, "person:a", name="ilsa renn")
    _thing(world, "person:b", name="ilsa renn")
    world.registry.guarded_merge("person:a", "person:b", "host")
    assert not world.registry._settled_apart("person:a", "person:b")
    world.porcelain.retract(_edge_id(world, "person:a", "person:b"), "undo")
    assert world.registry._settled_apart("person:a", "person:b")


# ============================================================ §3 decided_by

def test_every_path_writes_its_value(world):
    # engine: reconcile
    _thing(world, "person:r1", name="ilsa renn")
    _thing(world, "person:r2", name="ilsa renn")
    world.registry.reconcile()
    ev = world.buffer.visible(attribute="kind", value="identity_merge")
    assert len(ev) == 1
    assert _decided(world, ev[0].entity) == "engine"

    # engine: promotion
    _thing(world, "person:p1", name="sela voss")
    _thing(world, "person:p2", name="sela voss")
    world.registry.maybe_same_as("person:p1", "person:p2", evidence="seed")
    n_before = len(world.buffer.visible(attribute="kind", value="identity_merge"))
    assert world.registry.promote_identity_proposals() == 1
    ev = world.buffer.visible(attribute="kind", value="identity_merge")
    assert len(ev) == n_before + 1 and _decided(world, ev[-1].entity) == "engine"

    # engine: adjudicate_deferred
    _thing(world, "person:t1", name="tovin")
    _thing(world, "person:t2", name="tovin beck")
    world.registry.maybe_same_as("person:t1", "person:t2", evidence="seed")
    (receipt,) = world.registry.adjudicate_deferred()["merged"]
    assert _decided(world, receipt) == "engine"

    # host: the porcelain merge verb
    _thing(world, "person:h1")
    _thing(world, "person:h2")
    assert _decided(world, world.porcelain.merge("person:h1", "person:h2", "judged")) == "host"

    # host: confirm
    _thing(world, "person:c1")
    _thing(world, "person:c2")
    world.registry.maybe_same_as("person:c1", "person:c2", evidence="seed")
    assert _decided(world, world.porcelain.confirm("person:c1", "person:c2")) == "host"


def test_retype_absorb_is_host(world):
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
    assert _decided(world, r) == "host"


def _merge_event_rows(w, event: str) -> dict[str, list]:
    out: dict[str, list] = {}
    for row in w.buffer.visible(entity=event):
        out.setdefault(row.attribute, []).append(row)
    return out


def test_a_raw_same_as_item_is_a_statement(world):
    _thing(world, "person:a")
    _thing(world, "person:b")
    world.ingest_structured([
        {"entity": "person:a", "attribute": "same_as", "value": "person:b",
         "value_type": "entity"}])
    (event,) = world.buffer.visible(attribute="kind", value="identity_merge")
    rows = _merge_event_rows(world, event.entity)
    assert _decided(world, event.entity) == "statement"
    assert "extracted" not in rows
    assert rows["decided_by"][0].status == "inferred"
    assert rows["decided_by"][0].valid_from is None


def test_an_extracted_statement_also_carries_the_extracted_bit(world):
    _thing(world, "person:a")
    _thing(world, "person:b")
    world.ingest_structured(
        [{"entity": "person:a", "attribute": "same_as", "value": "person:b",
          "value_type": "entity"}], extracted=True)
    (event,) = world.buffer.visible(attribute="kind", value="identity_merge")
    rows = _merge_event_rows(world, event.entity)
    assert _decided(world, event.entity) == "statement"      # one value ...
    assert [r.value for r in rows["extracted"]] == [True]    # ... plus the origin bit
    assert rows["extracted"][0].status == "inferred"


def test_a_commit_set_statement_is_not_extracted(world):
    _thing(world, "person:a")
    _thing(world, "person:b")
    world.porcelain.commit_set([{"op": "assert", "item": {
        "entity": "person:a", "attribute": "same_as", "value": "person:b",
        "value_type": "entity"}}])
    (event,) = world.buffer.visible(attribute="kind", value="identity_merge")
    assert "extracted" not in _merge_event_rows(world, event.entity)


def test_decided_by_is_refused_as_an_item(world):
    _thing(world, "person:a")
    _thing(world, "person:b")
    world.registry.guarded_merge("person:a", "person:b", "host")
    (event,) = world.buffer.visible(attribute="kind", value="identity_merge")
    r = world.porcelain.ingest_structured(
        [{"entity": event.entity, "attribute": "decided_by", "value": "host"}],
        classify="rules")
    assert [s["reason"] for s in r.skipped] == ["mechanism_attribute"]
    assert len(_merge_event_rows(world, event.entity)["decided_by"]) == 1


def test_decided_by_needs_the_registrys_mark(world):
    _thing(world, "person:a")
    with pytest.raises(RoleViolation):
        world.buffer.append(entity="event:merge_x", attribute="decided_by",
                            value="host", role=world.registry._ingestor,
                            status="stated")


def test_merge_rejects_an_unknown_decided_by(world):
    _thing(world, "person:a")
    _thing(world, "person:b")
    with pytest.raises(ValueError):
        world.registry.merge("person:a", "person:b", "x", decided_by="whoever")


def test_the_value_is_never_inferred_from_the_evidence(world):
    """A host `merge` whose text happens to start 'reconcile:' is still host;
    the legacy derivation applies only to rows without `decided_by`."""
    _thing(world, "person:a")
    _thing(world, "person:b")
    r = world.porcelain.merge("person:a", "person:b", "reconcile: looks like the engine")
    assert _decided(world, r) == "host"


def _legacy_merge(w, n: int, evidence: str, kind_status: str = "inferred") -> str:
    """A merge event as written before `decided_by` existed: no such row."""
    event = f"event:merge_legacy{n}"
    role = w.registry._ingestor
    w.buffer.append(entity=event, attribute="kind", value="identity_merge",
                    status=kind_status, role=role)
    w.buffer.append(entity=event, attribute="evidence", value=evidence,
                    status=kind_status, role=role)
    return event


@pytest.mark.parametrize("evidence, expected", [
    ("reconcile: gated shared-anchor coreference", "engine"),
    ("promoted from a:12: gated coreference", "engine"),
    ("adjudicate_deferred: fragment subsumption", "engine"),
    ("confirmed proposal: reconcile: shared anchor", "host"),   # not 'reconcile:'
    ("retype absorb: typing slip", "host"),
    ("fidelity-repair: same speaker", "unknown"),
])
def test_legacy_merges_derive_from_the_evidence_prefix(world, evidence, expected):
    event = _legacy_merge(world, 1, evidence)
    assert world.registry.merge_decided_by(event) == expected


def test_a_forged_decided_by_decides_nothing(world):
    """On an event without the registry's mark, a `decided_by` row is ignored."""
    event = _legacy_merge(world, 2, "fidelity-repair: x", kind_status="stated")
    world.buffer.append(entity=event, attribute="decided_by", value="host",
                        status="inferred", role=world.registry._ingestor)
    assert world.registry.merge_decided_by(event) == "unknown"


def test_identity_conflicts_report_who_decided(world):
    """A merged closure holding a vetoed pair lists each merge's decided_by."""
    world.ingest_structured([{"entity": "obj:ring", "attribute": "in", "value": "obj:box",
                              "value_type": "entity"}])
    world.porcelain.reject("obj:box", "obj:ring")
    # a raw, legacy same_as past the vetoes: no merge event, no decided_by
    world.buffer.append(entity="obj:ring", attribute="same_as", value="obj:box",
                        value_type="entity", status="inferred",
                        role=world.registry._ingestor)
    (entry,) = world.porcelain.identity_conflicts()
    assert "decided_by" not in entry["same_as"][0]
    # a legacy merge event joining two other members of a closure
    _thing(world, "obj:lid", kind="object")
    legacy = _legacy_merge(world, 3, "reconcile: gated shared-anchor coreference")
    edge = world.buffer.append(entity="obj:ring", attribute="same_as", value="obj:lid",
                               value_type="entity", status="inferred",
                               role=world.registry._ingestor)
    world.buffer.append(entity=edge.id, attribute="caused_by", value=legacy,
                        value_type="entity", status="inferred",
                        role=world.registry._ingestor)
    (entry,) = world.porcelain.identity_conflicts()
    by_edge = {s["assertion_id"]: s for s in entry["same_as"]}
    assert by_edge[edge.id]["decided_by"] == "engine"


# ============================================================ §4 frame owners

def _owner(w, eid: str, **kw) -> None:
    """An entity that owns a `knows:` frame: it has a row in `knows:<eid>`."""
    _thing(w, eid, **kw)
    w.ingest_structured(
        [{"entity": "place:hall", "attribute": "kind", "value": "place", "timeless": True}],
        frame=f"knows:{eid}")


def test_a_frame_owner_pair_is_a_proposal(world):
    _owner(world, "person:a", name="soren vale")
    _thing(world, "person:b", name="soren vale")
    assert world.registry.reconcile() == 0
    assert _R(world, "person:a") != _R(world, "person:b")
    assert _proposals(world) == {frozenset(("person:a", "person:b")): FRAME_OWNER}
    (p,) = world.registry.enumerate_proposals()
    assert p["auto_decline"]["code"] == "frame_owner"
    assert p["auto_decline_reason"] == "frame_owner"


def test_the_other_side_owning_a_frame_counts_too(world):
    _thing(world, "person:a", name="soren vale")
    _owner(world, "person:b", name="soren vale")
    assert world.registry.reconcile() == 0
    assert list(_proposals(world).values()) == [FRAME_OWNER]


def test_ownership_reaches_the_whole_closure(world):
    _owner(world, "person:a", name="soren vale")
    _thing(world, "person:a2", name="a two")
    world.registry.guarded_merge("person:a2", "person:a", "host")
    _thing(world, "person:b", name="soren vale")
    assert world.registry.reconcile() == 0
    assert _R(world, "person:b") != _R(world, "person:a2")


def test_a_pair_declined_for_another_reason_keeps_the_generic_text(world):
    """The frame-owner text is for a pair that would otherwise have merged."""
    _owner(world, "person:a", alias="red")          # a single-token alias: declined anyway
    _thing(world, "person:b", alias="red")
    world.registry.reconcile()
    assert list(_proposals(world).values()) == [GENERIC]


def test_confirm_merges_a_frame_owner_pair(world):
    _owner(world, "person:a", name="soren vale")
    _thing(world, "person:b", name="soren vale")
    world.registry.reconcile()
    receipt = world.registry.confirm("person:a", "person:b")
    assert receipt["outcome"] == "merged"
    assert _decided(world, receipt) == "host"


def test_promotion_and_adjudication_leave_frame_owners_alone(world):
    _owner(world, "person:a", name="soren vale")
    _thing(world, "person:b", name="soren vale")
    world.registry.maybe_same_as("person:a", "person:b", evidence="seed")
    _owner(world, "person:t1", name="tovin")
    _thing(world, "person:t2", name="tovin beck")
    world.registry.maybe_same_as("person:t1", "person:t2", evidence="seed")
    assert world.registry.promote_identity_proposals() == 0
    assert world.registry.adjudicate_deferred()["merged"] == []


def test_host_merge_of_a_frame_owner_is_unchanged(world):
    _owner(world, "person:a")
    _owner(world, "person:b")
    assert world.porcelain.merge("person:a", "person:b", "judged")["outcome"] == "merged"


def test_a_non_owner_merge_is_unchanged(world):
    _thing(world, "person:a", name="soren vale")
    _thing(world, "person:b", name="soren vale")
    assert world.registry.reconcile() == 1


# ----------------------------------------- the book pipeline's host step

@pytest.fixture
def pipeline_module(monkeypatch):
    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parent.parent / "evals" / "harness"))
    import pipeline
    return pipeline


def test_confirm_frame_owners_decides_what_the_engine_left(world, pipeline_module):
    _owner(world, "person:a", name="soren vale")
    _thing(world, "person:b", name="soren vale")
    _owner(world, "person:t1", alias="red")           # declined for another reason
    _thing(world, "person:t2", alias="red")
    world.registry.reconcile()
    assert pipeline_module.Pipeline.confirm_frame_owners(world) == 1
    assert _R(world, "person:a") == _R(world, "person:b")
    assert _R(world, "person:t1") != _R(world, "person:t2")     # not its business
    (event,) = world.buffer.visible(attribute="kind", value="identity_merge")
    assert _decided(world, event.entity) == "host"
    assert pipeline_module.Pipeline.confirm_frame_owners(world) == 0   # idempotent
