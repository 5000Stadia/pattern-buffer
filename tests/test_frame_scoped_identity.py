"""FRAME-SCOPED-IDENTITY-V1: identity is canon's, description is perspectival,
an observer follows its identity.

One test per oracle, by section (specs/FRAME-SCOPED-IDENTITY-V1.md), plus the
two property tests the spec's Tests section names.

Alice's frame is `knows:person:alice`; Marn's is `knows:person:marn`.
"""

from __future__ import annotations

import pytest

from patternbuffer import AtomicAbort, World
from patternbuffer.refer import RESOLVED
from patternbuffer.testing import StubModel, rule_classifier_fallback

ALICE = "knows:person:alice"
MARN = "knows:person:marn"


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "fsi.world", world_id="w:fsi", model=stub)
    w._stub = stub  # test handle
    yield w
    w.close()


def _hooded(frame: str = ALICE, **extra) -> dict:
    """The masked figure Alice privately calls "the traitor"."""
    return {"entity": "person:hooded", "attribute": "kind", "value": "person",
            "timeless": True, "frame": frame, "aliases": ["the traitor"], **extra}


# --------------------------------------------- §1 identity writes carry the frame


def test_1a_alias_lands_in_the_items_frame(world):
    """1a: an `aliases` member on a non-canon item is written in that item's
    frame (today: canon)."""
    world.ingest_structured([_hooded()])
    rows = world.buffer.visible(entity="person:hooded", attribute="alias")
    assert [(r.value, r.frame) for r in rows] == [("the traitor", ALICE)]


def test_1b_same_as_key_outside_canon_is_receipted(world):
    """1b: the side-channel `same_as` on a non-canon item is skipped
    `identity_edge_outside_canon`; no `maybe_same_as`, no canon proposal; the
    main row is admitted as usual."""
    p = world.porcelain
    receipt = p.ingest_structured([_hooded(same_as="person:bob")])
    assert receipt.skipped == [{"entity": "person:hooded", "attribute": "same_as",
                                "value": "person:bob",
                                "reason": "identity_edge_outside_canon"}]
    assert world.buffer.visible(attribute="maybe_same_as") == []
    assert p.proposals() == []
    kind = world.buffer.visible(entity="person:hooded", attribute="kind")
    assert [r.frame for r in kind] == [ALICE]


def test_1c_raw_same_as_outside_canon_never_merges_canon(world):
    """1c: a raw `same_as` in Alice's frame is skipped — through GATE-AUTHORITY-V1
    §2's own refusal, reused (`same_as_not_canon`) — and canon never serves the
    stranger's facts under Bob's id."""
    world.ingest_structured([
        {"entity": "person:bob", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:stranger", "attribute": "occupation", "value": "spy",
         "valid_from": 1.0},
    ])
    head = world.buffer.head()
    receipt = world.porcelain.ingest_structured([
        {"entity": "person:stranger", "attribute": "same_as", "value": "person:bob",
         "frame": ALICE},
    ])
    assert [s["reason"] for s in receipt.skipped] == ["same_as_not_canon"]
    assert world.buffer.head() == head
    assert world.registry.closure("person:stranger") == {"person:stranger"}
    assert world.porcelain.state("person:bob", "occupation")["status"] == "unknown"


@pytest.mark.parametrize("frame", [ALICE, "plot:twist"])
@pytest.mark.parametrize("attribute", ["maybe_same_as", "distinct_from"])
def test_1d_raw_identity_edges_outside_canon_skip(world, attribute, frame):
    """1d: raw `maybe_same_as` / `distinct_from` rows in `knows:` and `plot:`
    are skipped `identity_edge_outside_canon`, with nothing appended."""
    head = world.buffer.head()
    receipt = world.porcelain.ingest_structured([
        {"entity": "person:a", "attribute": attribute, "value": "person:b",
         "frame": frame},
    ])
    assert receipt.skipped == [{"entity": "person:a", "attribute": attribute,
                                "value": "person:b",
                                "reason": "identity_edge_outside_canon"}]
    assert world.buffer.head() == head


def test_1e_raw_aka_stays_in_its_frame(world):
    """1e: `aka` is perspectival — a raw `aka` in Alice's frame is admitted in
    Alice's frame (unchanged)."""
    rows = world.ingest_structured([
        {"entity": "person:masked", "attribute": "aka", "value": "person:bob",
         "frame": ALICE},
    ])
    assert [(r.attribute, r.frame) for r in rows] == [("aka", ALICE)]
    assert world.ingestor.last_skipped == []


def test_1f_atomic_set_aborts_on_the_skip(world):
    """1f: under atomic=True the new skip aborts the set (`gate_skip`, carrying
    the receipt) and nothing is visible."""
    head = world.buffer.head()
    with pytest.raises(AtomicAbort) as caught:
        world.ingest_structured([_hooded(same_as="person:bob")],
                                atomic=True, classify="rules")
    assert caught.value.cause == "gate_skip"
    assert caught.value.skipped == [{"entity": "person:hooded", "attribute": "same_as",
                                     "value": "person:bob",
                                     "reason": "identity_edge_outside_canon"}]
    assert world.buffer.head() == head
    assert world.buffer.visible(entity="person:hooded") == []


def test_1g_refer_accrues_in_the_calls_frame(world):
    """1g: a tier-2 hit from `refer(frame=Alice)` writes its alias row in
    Alice's frame (today: canon). Alice's hall holds Bob and Carl; "the
    traitor" is a vocabulary miss tier 2 maps onto Bob."""
    world.ingest_structured([
        {"entity": "person:bob", "attribute": "in", "value": "place:hall"},
        {"entity": "person:carl", "attribute": "in", "value": "place:hall"},
    ], frame=ALICE)
    world._stub.enqueue({"entity_id": "person:bob", "confidence": 0.9,
                         "signals": ["synonym"]})
    r = world.refer("the traitor", scope="place:hall", frame=ALICE)
    assert r.status == RESOLVED and r.entity_id == "person:bob"
    rows = world.buffer.visible(attribute="alias", value="the traitor")
    assert [(row.entity, row.frame) for row in rows] == [("person:bob", ALICE)]
