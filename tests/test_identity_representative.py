"""IDENTITY-REPRESENTATIVE-V1: a host merge can name the id the closure is served under.

One group of tests per Check (specs/IDENTITY-REPRESENTATIVE-V1.md):
1. construct's case; 2. latest wins; 2a. retype; 2b. receipt; 3. retraction and
as-of pins; 4. mechanism; 5. validation; 5a. the re-point event; 6/7 are the
corpus run and the full suite (run outside this file).
"""

from __future__ import annotations

import pytest

from patternbuffer import World
from patternbuffer.mcp import build_registry
from patternbuffer.model import Assertion
from patternbuffer.roles import RoleViolation
from patternbuffer.testing import StubModel, rule_classifier_fallback

ELIAS = "person:elias"
VENN = "person:elias_venn"
THIRD = "person:e_venn"


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path / "rep.world", world_id="w:rep",
              model=StubModel(fallback=rule_classifier_fallback()))
    yield w
    w.close()


def _seen(w, *ids: str) -> None:
    """Make each id appear in the log, in order (first-seen is log order)."""
    w.ingest_structured([
        {"entity": e, "attribute": "kind", "value": "person", "timeless": True}
        for e in ids
    ])


def _R(w, e: str, **kw) -> str:
    return w.registry.resolve(e, **kw)


def _rows(w, entity: str) -> list[tuple[str, object, str]]:
    return [(r.attribute, r.value, r.status)
            for r in w.buffer.visible(entity=entity)]


def _rep_row(w, event: str) -> Assertion:
    (row,) = w.buffer.visible(entity=event, attribute="representative")
    return row


def _edge_id(w, a: str, b: str) -> str:
    return next(r.id for r in w.buffer.visible(attribute="same_as")
                if {r.entity, r.value} == {a, b})


# ================================================================ 1 construct's case


def test_1_designated_merge_serves_the_arc_id(world):
    _seen(world, VENN, ELIAS)  # the fragment was seen first
    receipt = world.porcelain.merge(ELIAS, VENN, "same man", representative=ELIAS)
    assert receipt["outcome"] == "merged"
    assert _R(world, ELIAS) == _R(world, VENN) == ELIAS
    assert world.registry.closure(VENN) == {ELIAS, VENN}


def test_1_undesignated_merge_is_first_seen_as_today(world):
    _seen(world, VENN, ELIAS)
    world.porcelain.merge(ELIAS, VENN, "same man")
    assert _R(world, ELIAS) == _R(world, VENN) == VENN


def test_1_the_designation_is_one_inferred_timeless_row_on_the_merge_event(world):
    _seen(world, VENN, ELIAS)
    receipt = world.porcelain.merge(ELIAS, VENN, "same man", representative=ELIAS)
    event = receipt["merge_event_id"]
    row = _rep_row(world, event)
    assert (row.value, row.status, row.frame) == (ELIAS, "inferred", "canon")
    assert row.valid_from is None and row.valid_to is None
    # written last, in the same call as the merge's other rows
    seqs = [r.seq for r in world.buffer.visible(entity=event)]
    assert row.seq == max(seqs) == world.buffer.head()
    assert [r.attribute for r in world.buffer.visible(entity=event)] == [
        "kind", "evidence", "decided_by", "representative"]


def test_1_a_belief_frame_does_not_follow_the_merge(world):
    """P1: the knowledge written under the arc id stays under the arc id."""
    _seen(world, VENN, ELIAS)
    world.ingest_structured([{"entity": "obj:ledger", "attribute": "kind",
                              "value": "book", "timeless": True,
                              "frame": f"knows:{ELIAS}"}])
    world.porcelain.merge(ELIAS, VENN, "same man", representative=ELIAS)
    assert world.buffer.visible(frame=f"knows:{ELIAS}")
    assert _R(world, ELIAS) == ELIAS


# ================================================================ 2 latest wins


def test_2_a_newer_designation_repoints_and_a_later_fold_keeps_it(world):
    _seen(world, VENN, ELIAS, THIRD)
    world.porcelain.merge(ELIAS, VENN, "one", representative=ELIAS)
    assert _R(world, VENN) == ELIAS
    # a third id folded in with no designation: the standing one holds
    receipt = world.porcelain.merge(THIRD, VENN, "two")
    assert receipt["outcome"] == "merged"
    assert _R(world, THIRD) == _R(world, VENN) == ELIAS
    assert receipt["canonical_id"] == ELIAS
    # a newer host designation replaces it
    world.porcelain.merge(THIRD, ELIAS, "three")  # already merged: undesignated no-op
    assert _R(world, ELIAS) == ELIAS
    receipt = world.porcelain.merge(VENN, ELIAS, "four", representative=THIRD)
    assert receipt["outcome"] == "noop_already_merged" and receipt["repointed"] is True
    assert _R(world, ELIAS) == _R(world, VENN) == THIRD


def test_2_a_designation_on_a_later_merge_wins_over_an_earlier_one(world):
    _seen(world, VENN, ELIAS, THIRD)
    world.porcelain.merge(ELIAS, VENN, "one", representative=ELIAS)
    world.porcelain.merge(THIRD, ELIAS, "two", representative=THIRD)
    assert {_R(world, e) for e in (ELIAS, VENN, THIRD)} == {THIRD}


def test_2_two_closures_keep_their_own_designations_when_joined(world):
    """A designation naming a member of the joined closure still elects."""
    _seen(world, "person:a1", "person:a2", "person:b1", "person:b2")
    world.porcelain.merge("person:a1", "person:a2", "x", representative="person:a2")
    world.porcelain.merge("person:b1", "person:b2", "x", representative="person:b2")
    assert _R(world, "person:a1") == "person:a2"
    assert _R(world, "person:b1") == "person:b2"
    world.porcelain.merge("person:a1", "person:b1", "join")
    # the latest honoured designation of the joined closure
    assert {_R(world, e) for e in ("person:a1", "person:a2", "person:b1",
                                   "person:b2")} == {"person:b2"}


# ================================================================ 2a retype


def _harth_slip(world: World) -> None:
    """person:harth is seen FIRST; place:harth is the real place."""
    world.ingest_structured([
        {"entity": "person:harth", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:harth", "attribute": "name", "value": "Harth", "timeless": True},
        {"entity": "place:harth", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:harth", "attribute": "name", "value": "Harth", "timeless": True},
        {"entity": "obj:well", "attribute": "in", "value": "place:harth"},
    ])


def test_2a_retype_absorb_keeps_the_target_as_representative(world):
    _harth_slip(world)
    receipt = world.porcelain.retype("person:harth", "place", "slip",
                                     absorb="place:harth")
    assert receipt["outcome"] == "merged"
    assert _R(world, "person:harth") == _R(world, "place:harth") == "place:harth"
    assert receipt["canonical_id"] == "place:harth"


def test_2a_without_the_designation_the_slip_id_would_have_won(world):
    """The control: the first-seen rule serves the wrong-kind id."""
    _harth_slip(world)
    world.registry.guarded_merge("person:harth", "place:harth", "x")
    assert _R(world, "place:harth") == "person:harth"


def test_2a_retype_on_an_already_merged_pair_repoints_to_the_target(world):
    _harth_slip(world)
    world.registry.guarded_merge("person:harth", "place:harth", "earlier absorb")
    assert _R(world, "place:harth") == "person:harth"
    receipt = world.porcelain.retype("person:harth", "place", "slip",
                                     absorb="place:harth")
    assert receipt["outcome"] == "noop_already_merged"
    assert receipt["repointed"] is True and receipt["retracted"] == []
    assert receipt["canonical_id"] == "place:harth"
    assert _R(world, "person:harth") == "place:harth"


def test_2a_retype_without_absorb_writes_no_designation(world):
    _seen(world, VENN)
    world.porcelain.retype(VENN, "thing", "kind fix")
    assert world.buffer.visible(attribute="representative") == []


# ================================================================ 2b receipt


def test_2b_merge_receipt_canonical_id_is_the_elected_representative(world):
    _seen(world, VENN, ELIAS)
    receipt = world.porcelain.merge(ELIAS, VENN, "x", representative=ELIAS)
    assert receipt["canonical_id"] == ELIAS == _R(world, VENN)
    # undesignated: the first-seen member, and still resolve(a)
    _seen(world, "person:q1", "person:q2")
    receipt = world.porcelain.merge("person:q2", "person:q1", "x")
    assert receipt["canonical_id"] == "person:q1" == _R(world, "person:q2")


def test_2b_confirm_receipt_canonical_id_is_the_elected_representative(world):
    _seen(world, VENN, ELIAS)
    world.registry.maybe_same_as(ELIAS, VENN, "shared anchor")
    receipt = world.porcelain.confirm(ELIAS, VENN, representative=ELIAS)
    assert receipt["outcome"] == "merged"
    assert receipt["canonical_id"] == ELIAS == _R(world, VENN)
    event = receipt["merge_event_id"]
    assert _rep_row(world, event).value == ELIAS
    assert dict(((a, v) for a, v, _ in _rows(world, event)))["decided_by"] == "host"


def test_2b_retype_receipt_canonical_id_is_the_elected_representative(world):
    _harth_slip(world)
    receipt = world.porcelain.retype("person:harth", "place", "slip",
                                     absorb="place:harth")
    assert receipt["canonical_id"] == "place:harth"


def test_2b_a_vetoed_merge_still_reads_the_pre_merge_id(world):
    _seen(world, VENN, ELIAS)
    world.registry.reject(ELIAS, VENN)
    receipt = world.porcelain.merge(ELIAS, VENN, "x", representative=ELIAS)
    assert receipt["outcome"] == "vetoed"
    assert receipt["canonical_id"] == _R(world, ELIAS) == ELIAS


# ================================================================ 3 retraction and pins


def test_3_retracting_the_designation_row_reverts_to_the_prior_then_first_seen(world):
    _seen(world, VENN, ELIAS, THIRD)
    r1 = world.porcelain.merge(ELIAS, VENN, "one", representative=ELIAS)
    after_one = world.buffer.head()
    r2 = world.porcelain.merge(THIRD, ELIAS, "two", representative=THIRD)
    after_two = world.buffer.head()
    assert _R(world, VENN) == THIRD

    world.porcelain.retract(_rep_row(world, r2["merge_event_id"]).id, "no")
    after_retract_two = world.buffer.head()
    assert _R(world, VENN) == ELIAS            # the prior designation stands

    world.porcelain.retract(_rep_row(world, r1["merge_event_id"]).id, "no")
    assert _R(world, VENN) == VENN             # first-seen again

    # asserted_as_of pins see each stage
    assert _R(world, VENN, asserted_as_of=after_one) == ELIAS
    assert _R(world, THIRD, asserted_as_of=after_one) == THIRD   # not merged yet
    assert _R(world, VENN, asserted_as_of=after_two) == THIRD
    assert _R(world, VENN, asserted_as_of=after_retract_two) == ELIAS
    assert _R(world, VENN, asserted_as_of=world.buffer.head()) == VENN


def test_3_retracting_the_edge_cancels_the_designation_and_splits(world):
    _seen(world, VENN, ELIAS)
    world.porcelain.merge(ELIAS, VENN, "x", representative=ELIAS)
    merged = world.buffer.head()
    world.porcelain.retract(_edge_id(world, ELIAS, VENN), "wrong")
    assert _R(world, ELIAS) == ELIAS and _R(world, VENN) == VENN
    assert _R(world, VENN, asserted_as_of=merged) == ELIAS


def test_3_a_designation_that_loses_its_edge_does_not_elect_in_a_remerged_closure(world):
    """The first merge's edge is retracted; a new undesignated merge of the same
    pair is first-seen, because the old designation's edge is gone."""
    _seen(world, VENN, ELIAS)
    world.porcelain.merge(ELIAS, VENN, "x", representative=ELIAS)
    world.porcelain.retract(_edge_id(world, ELIAS, VENN), "wrong")
    world.porcelain.merge(ELIAS, VENN, "again")
    assert _R(world, ELIAS) == _R(world, VENN) == VENN


def test_3_retracting_the_event_kind_row_withdraws_it(world):
    _seen(world, VENN, ELIAS)
    receipt = world.porcelain.merge(ELIAS, VENN, "x", representative=ELIAS)
    (kind,) = world.buffer.visible(entity=receipt["merge_event_id"], attribute="kind")
    world.porcelain.retract(kind.id, "event void")
    assert _R(world, VENN) == VENN                # closure stands (edge live), election first-seen


def test_3_retracting_the_decided_by_row_withdraws_it(world):
    _seen(world, VENN, ELIAS)
    receipt = world.porcelain.merge(ELIAS, VENN, "x", representative=ELIAS)
    (row,) = world.buffer.visible(entity=receipt["merge_event_id"],
                                  attribute="decided_by")
    world.porcelain.retract(row.id, "no")
    assert _R(world, VENN) == VENN


def test_3_the_cached_view_follows_the_log(world):
    """Resolve, designate, resolve: the head view is invalidated on append."""
    _seen(world, VENN, ELIAS)
    world.porcelain.merge(ELIAS, VENN, "x")
    assert _R(world, ELIAS) == VENN
    world.porcelain.merge(ELIAS, VENN, "again", representative=ELIAS)
    assert _R(world, ELIAS) == ELIAS


# ================================================================ 4 mechanism


def test_4_a_representative_item_is_refused_at_the_gate(world):
    _seen(world, VENN, ELIAS)
    result = world.porcelain.ingest_structured([
        {"entity": "event:merge_99", "attribute": "representative",
         "value": ELIAS, "timeless": True}])
    assert [s["reason"] for s in result.skipped] == ["mechanism_attribute"]
    assert world.buffer.visible(attribute="representative") == []


def test_4_the_buffer_refuses_the_wrong_status(world):
    with pytest.raises(RoleViolation):
        world.buffer.append(entity="event:merge_1", attribute="representative",
                            value=ELIAS, status="stated",
                            role=world.registry._ingestor)


def _forge(world, entity: str, attribute: str, value, status: str) -> None:
    """Write a row the way `dump.build` replays an old log: past `append`'s mark
    check, straight into the insert."""
    seq = world.buffer.head() + 1
    world.buffer._insert(Assertion(
        seq=seq, id=f"a:{seq}", world_id=world.buffer.world_id, entity=entity,
        attribute=attribute, value_type="literal", value=value,
        valid_from=None, valid_to=None, frame="canon", status=status,
        confidence=None, asserted_at=seq))


def test_4_a_forged_row_with_the_wrong_status_elects_nothing(world):
    _seen(world, VENN, ELIAS)
    receipt = world.porcelain.merge(ELIAS, VENN, "x")
    _forge(world, receipt["merge_event_id"], "representative", ELIAS, "stated")
    assert _R(world, VENN) == VENN


def test_4_a_row_on_a_non_host_merge_event_elects_nothing(world):
    _seen(world, VENN, ELIAS)
    event = world.registry.merge(ELIAS, VENN, "reconcile: shared anchor")  # engine
    world.buffer.append(entity=event, attribute="representative", value=ELIAS,
                        status="inferred", role=world.registry._ingestor)
    assert _R(world, VENN) == VENN
    with pytest.raises(ValueError):
        world.registry.merge(ELIAS, VENN, "x", decided_by="engine",
                             representative=ELIAS)


def test_4_a_row_on_a_non_merge_event_elects_nothing(world):
    _seen(world, VENN, ELIAS)
    world.porcelain.merge(ELIAS, VENN, "x")
    world.buffer.append(entity="event:merge_999", attribute="representative",
                        value=ELIAS, status="inferred", role=world.registry._ingestor)
    world.buffer.append(entity="event:merge_999", attribute="decided_by",
                        value="host", status="inferred", role=world.registry._ingestor)
    assert _R(world, VENN) == VENN        # no `kind · identity_merge`


def test_4_a_row_naming_a_nonmember_elects_nothing(world):
    _seen(world, VENN, ELIAS)
    receipt = world.porcelain.merge(ELIAS, VENN, "x")
    world.buffer.append(entity=receipt["merge_event_id"], attribute="representative",
                        value="person:stranger", status="inferred",
                        role=world.registry._ingestor)
    assert _R(world, VENN) == VENN


def test_4_a_host_event_with_a_forged_decided_by_status_elects_nothing(world):
    _seen(world, VENN, ELIAS)
    receipt = world.registry.guarded_merge(ELIAS, VENN, "x")
    # strip the real mark: retract the row and forge one with the wrong status
    event = receipt["merge_event_id"]
    (real,) = world.buffer.visible(entity=event, attribute="decided_by")
    world.porcelain.retract(real.id, "replace")
    _forge(world, event, "decided_by", "host", "stated")
    world.buffer.append(entity=event, attribute="representative", value=ELIAS,
                        status="inferred", role=world.registry._ingestor)
    assert _R(world, VENN) == VENN


def test_4_a_stray_caused_by_cannot_withdraw_a_repoint(world):
    """Only a `caused_by` on a `same_as` row marks an event edge-producing."""
    _seen(world, VENN, ELIAS)
    world.porcelain.merge(ELIAS, VENN, "x")
    receipt = world.porcelain.merge(ELIAS, VENN, "p", representative=ELIAS)
    world.ingest_structured([{"entity": "obj:thing", "attribute": "caused_by",
                              "value": receipt["merge_event_id"],
                              "value_type": "entity", "timeless": True}])
    assert _R(world, VENN) == ELIAS


# ================================================================ 5 validation


def test_5_a_nonmember_raises_before_any_write(world):
    _seen(world, VENN, ELIAS, THIRD)
    head = world.buffer.head()
    with pytest.raises(ValueError):
        world.porcelain.merge(ELIAS, VENN, "x", representative=THIRD)
    with pytest.raises(ValueError):
        world.registry.guarded_merge(ELIAS, VENN, "x", representative="person:nobody")
    with pytest.raises(ValueError):
        world.registry.merge(ELIAS, VENN, "x", decided_by="host",
                             representative=THIRD)
    world.registry.maybe_same_as(ELIAS, VENN, "anchor")
    head = world.buffer.head()
    with pytest.raises(ValueError):
        world.porcelain.confirm(ELIAS, VENN, representative=THIRD)
    assert world.buffer.head() == head
    assert _R(world, ELIAS) == ELIAS


def test_5_a_member_of_either_closure_is_valid(world):
    _seen(world, VENN, ELIAS, THIRD, "person:f")
    world.porcelain.merge(ELIAS, VENN, "x")
    world.porcelain.merge(THIRD, "person:f", "x")
    # THIRD is a member of b's closure only
    world.porcelain.merge(VENN, "person:f", "join", representative=THIRD)
    assert _R(world, ELIAS) == THIRD


def test_5_a_nonmember_raises_on_an_already_merged_pair_too(world):
    _seen(world, VENN, ELIAS, THIRD)
    world.porcelain.merge(ELIAS, VENN, "x")
    head = world.buffer.head()
    with pytest.raises(ValueError):
        world.porcelain.merge(ELIAS, VENN, "x", representative=THIRD)
    assert world.buffer.head() == head


# ================================================================ 5a re-point


def _event_rows(w, event: str) -> list[tuple[str, object, str, object, object]]:
    return [(r.attribute, r.value, r.status, r.valid_from, r.frame)
            for r in w.buffer.visible(entity=event)]


def test_5a_merge_repoints_with_exactly_four_rows(world):
    _seen(world, VENN, ELIAS)
    world.porcelain.merge(ELIAS, VENN, "x")
    head = world.buffer.head()
    receipt = world.porcelain.merge(ELIAS, VENN, "arc names the survivor",
                                    representative=ELIAS)
    assert receipt["outcome"] == "noop_already_merged"
    assert receipt["repointed"] is True
    assert receipt["canonical_id"] == ELIAS
    assert world.buffer.head() == head + 4
    new = [r for r in world.buffer.visible() if r.seq > head]
    assert [(r.attribute, r.value, r.status, r.frame) for r in new] == [
        ("kind", "identity_merge", "inferred", "canon"),
        ("evidence", "arc names the survivor", "inferred", "canon"),
        ("decided_by", "host", "inferred", "canon"),
        ("representative", ELIAS, "inferred", "canon"),
    ]
    assert {r.entity for r in new} == {f"event:merge_{head + 1}"}
    assert all(r.valid_from is None and r.valid_to is None for r in new)
    assert not any(r.attribute in ("same_as", "caused_by") for r in new)
    assert receipt["merge_event_id"] == f"event:merge_{head + 1}"


def test_5a_confirm_repoints_with_exactly_four_rows(world):
    _seen(world, VENN, ELIAS)
    world.porcelain.merge(ELIAS, VENN, "x")
    head = world.buffer.head()
    receipt = world.porcelain.confirm(ELIAS, VENN, representative=ELIAS)
    assert receipt["outcome"] == "noop_already_merged" and receipt["repointed"] is True
    assert receipt["canonical_id"] == ELIAS == _R(world, VENN)
    new = [r for r in world.buffer.visible() if r.seq > head]
    assert [(r.attribute, r.value) for r in new] == [
        ("kind", "identity_merge"), ("evidence", "re-point: confirm"),
        ("decided_by", "host"), ("representative", ELIAS)]


def test_5a_retype_repoint_rows(world):
    _harth_slip(world)
    world.registry.guarded_merge("person:harth", "place:harth", "earlier")
    head = world.buffer.head()
    world.porcelain.retype("person:harth", "place", "slip", absorb="place:harth")
    new = [r for r in world.buffer.visible() if r.seq > head]
    assert [r.attribute for r in new] == ["kind", "evidence", "decided_by",
                                          "representative"]
    assert new[-1].value == "place:harth"


def test_5a_undesignated_noop_writes_nothing_and_the_receipt_is_unchanged(world):
    _seen(world, VENN, ELIAS)
    world.porcelain.merge(ELIAS, VENN, "x")
    head = world.buffer.head()
    merge = world.porcelain.merge(ELIAS, VENN, "again")
    confirm = world.porcelain.confirm(ELIAS, VENN)
    assert world.buffer.head() == head
    expect = {"outcome": "noop_already_merged", "canonical_id": VENN,
              "merge_event_id": None, "reason": None, "blocking_edges": []}
    assert merge == expect and confirm == expect
    assert "repointed" not in merge and "repointed" not in confirm
    assert list(merge) == list(expect)


def test_5a_retracting_the_repoint_withdraws_it(world):
    _seen(world, VENN, ELIAS)
    world.porcelain.merge(ELIAS, VENN, "x")
    for target in ("kind", "representative"):
        receipt = world.porcelain.merge(ELIAS, VENN, "p", representative=ELIAS)
        assert _R(world, VENN) == ELIAS
        (row,) = world.buffer.visible(entity=receipt["merge_event_id"],
                                      attribute=target)
        world.porcelain.retract(row.id, "withdraw")
        assert _R(world, VENN) == VENN, target


def test_5a_a_repoint_is_an_asserted_as_of_stage(world):
    _seen(world, VENN, ELIAS)
    world.porcelain.merge(ELIAS, VENN, "x")
    before = world.buffer.head()
    world.porcelain.merge(ELIAS, VENN, "p", representative=ELIAS)
    assert _R(world, VENN, asserted_as_of=before) == VENN
    assert _R(world, VENN, asserted_as_of=world.buffer.head()) == ELIAS
    assert _R(world, VENN) == ELIAS


def test_5a_a_vetoed_or_no_proposal_outcome_writes_nothing(world):
    _seen(world, VENN, ELIAS)
    # no_proposal: confirm on an unrelated pair
    head = world.buffer.head()
    for rep in (None, ELIAS):
        receipt = world.porcelain.confirm(ELIAS, VENN, representative=rep)
        assert receipt["outcome"] == "no_proposal"
        assert "repointed" not in receipt
    assert world.buffer.head() == head
    # vetoed: distinct_from
    world.registry.reject(ELIAS, VENN)
    head = world.buffer.head()
    for rep in (None, ELIAS):
        receipt = world.porcelain.merge(ELIAS, VENN, "x", representative=rep)
        assert receipt["outcome"] == "vetoed" and "repointed" not in receipt
    assert world.buffer.head() == head


def test_5a_a_retype_refusal_writes_nothing(world):
    _seen(world, VENN, ELIAS)
    head = world.buffer.head()
    receipt = world.porcelain.retype(VENN, "person", "no slip here", absorb=ELIAS)
    assert receipt["outcome"] == "vetoed_not_a_slip"
    assert world.buffer.head() == head


def test_5a_a_repoint_keeps_the_closure_and_adds_no_edge(world):
    _seen(world, VENN, ELIAS)
    world.porcelain.merge(ELIAS, VENN, "x")
    edges = [r.id for r in world.buffer.visible(attribute="same_as")]
    world.porcelain.merge(ELIAS, VENN, "p", representative=ELIAS)
    assert [r.id for r in world.buffer.visible(attribute="same_as")] == edges
    assert world.registry.closure(VENN) == {ELIAS, VENN}


# ================================================================ 5 byte-identity, small


def test_a_world_with_no_designation_elects_first_seen(world):
    _seen(world, "person:z", "person:a", "person:m")
    world.registry.merge("person:a", "person:z", "reconcile: x")
    world.porcelain.merge("person:m", "person:a", "x")
    assert {_R(world, e) for e in ("person:z", "person:a", "person:m")} == {"person:z"}
    assert world.buffer.visible(attribute="representative") == []


# ================================================================ MCP surface


def test_the_mcp_schemas_carry_the_new_parameter():
    reg = build_registry()
    for tool in ("merge", "confirm"):
        props = reg[tool]["inputSchema"]["properties"]
        assert "representative" in props, tool
        assert "representative" not in reg[tool]["inputSchema"].get("required", [])
