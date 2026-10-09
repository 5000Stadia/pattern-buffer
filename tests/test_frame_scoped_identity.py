"""FRAME-SCOPED-IDENTITY-V1: identity is canon's, description is perspectival,
an observer follows its identity.

One test per oracle, by section (specs/FRAME-SCOPED-IDENTITY-V1.md), plus the
two property tests the spec's Tests section names.

Alice's frame is `knows:person:alice`; Marn's is `knows:person:marn`.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from patternbuffer import AtomicAbort, World
from patternbuffer.refer import RESOLVED, UNDERDETERMINED
from patternbuffer.roles import _make_engine_roles
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


# --------------------------------------------- §2 identity reads are canon reads

INGESTOR = _make_engine_roles()["ingestor"]


def _legacy_row(world: World, entity: str, attribute: str, value, frame: str,
                value_type: str = "entity"):
    """A row already in a log, appended past the gate with the ingestor role
    (what today's gate let through, or a log written before this spec)."""
    return world.buffer.append(entity=entity, attribute=attribute, value=value,
                               value_type=value_type, status="stated",
                               role=INGESTOR, frame=frame)


def test_2a_legacy_same_as_outside_canon_is_inert(world):
    """2a: a legacy `same_as` in Alice's frame merges nothing: the closure is
    canon's, so canon never serves the stranger's "spy" under Bob's id."""
    world.ingest_structured([
        {"entity": "person:bob", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:stranger", "attribute": "occupation", "value": "spy",
         "valid_from": 1.0},
    ])
    _legacy_row(world, "person:stranger", "same_as", "person:bob", ALICE)
    assert world.registry.closure("person:stranger") == {"person:stranger"}
    assert world.porcelain.state("person:bob", "occupation")["status"] == "unknown"


def test_2b_a_private_name_never_drives_canon_reconcile(world):
    """2b: a name known only to Alice is no canon anchor: reconcile merges 0
    pairs and proposes none."""
    world.ingest_structured([
        {"entity": "person:bob", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:bob", "attribute": "name", "value": "Bob", "timeless": True},
        {"entity": "person:hooded", "attribute": "kind", "value": "person", "timeless": True},
    ])
    world.ingest_structured([
        {"entity": "person:hooded", "attribute": "name", "value": "Bob", "timeless": True},
    ], frame=ALICE)
    out = world.porcelain.reconcile()
    assert out["merges"] == 0 and out["proposals"] == []
    assert world.registry.closure("person:hooded") == {"person:hooded"}


def test_2c_a_private_alias_resolves_only_in_its_frame(world):
    """2c: `by_alias` and `refer` read names and aliases in the asked frame
    only, with no canon fallback."""
    world.ingest_structured([
        {"entity": "person:bob", "attribute": "kind", "value": "person", "timeless": True},
    ])
    world.ingest_structured([
        {"entity": "person:bob", "attribute": "alias", "value": "the traitor",
         "timeless": True},
    ], frame=ALICE)
    assert world.registry.by_alias("the traitor") == set()
    assert world.registry.by_alias("the traitor", frame=ALICE) == {"person:bob"}
    assert world.refer("the traitor").status == UNDERDETERMINED
    r = world.refer("the traitor", frame=ALICE)
    assert r.status == RESOLVED and r.entity_id == "person:bob"


def test_2d_canon_retype_retracts_only_canon_kind_rows(world):
    """2d: `retype` retracts canon kind rows only; Marn's "ghost" survives."""
    world.ingest_structured([
        {"entity": "obj:crown", "attribute": "kind", "value": "person", "timeless": True},
    ])
    marn_row = world.ingest_structured([
        {"entity": "obj:crown", "attribute": "kind", "value": "ghost", "timeless": True},
    ], frame=MARN)[0]
    canon_row = world.buffer.visible(entity="obj:crown", attribute="kind", frame="canon")[0]
    receipt = world.porcelain.retype("obj:crown", "relic", "a slip")
    assert receipt["outcome"] == "retyped"
    assert receipt["retracted"] == [canon_row.id]
    assert world.porcelain.state("obj:crown", "kind")["fact"]["value"] == "relic"
    marn = world.porcelain.state("obj:crown", "kind", frame=MARN)
    assert marn["fact"]["value"] == "ghost"
    assert world.buffer.visible(entity=marn_row.id, attribute="retracts") == []


def test_2e_a_slip_is_anchored_on_canon_names(world):
    """2e: canon `place:harth` (named "Harth") beside canon `person:harth`,
    whose "Harth" lives only in Marn's frame: no typing conflict."""
    world.ingest_structured([
        {"entity": "place:harth", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:harth", "attribute": "name", "value": "Harth", "timeless": True},
        {"entity": "obj:well", "attribute": "in", "value": "place:harth"},
        {"entity": "person:harth", "attribute": "kind", "value": "person", "timeless": True},
    ])
    world.ingest_structured([
        {"entity": "person:harth", "attribute": "name", "value": "Harth", "timeless": True},
    ], frame=MARN)
    assert world.porcelain.typing_conflicts() == []


def test_2f_a_belief_relation_never_blocks_a_canon_merge(world):
    """2f: two canon "Clay"s, with `clay1 · father_of · clay2` only in Alice's
    frame: canon's own rules decide, and they say mergeable."""
    world.ingest_structured([
        {"entity": "person:clay1", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:clay1", "attribute": "name", "value": "Clay", "timeless": True},
        {"entity": "person:clay2", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:clay2", "attribute": "name", "value": "Clay", "timeless": True},
    ])
    world.ingest_structured([
        {"entity": "person:clay1", "attribute": "father_of", "value": "person:clay2"},
    ], frame=ALICE)
    assert world.registry._mergeable("person:clay1", "person:clay2") is True


def test_2g_a_belief_containment_never_vetoes_a_canon_merge(world):
    """2g: `obj:a · in · obj:b` only in Alice's frame: the canon guarded merge
    goes through."""
    world.ingest_structured([
        {"entity": "obj:a", "attribute": "in", "value": "obj:b"},
    ], frame=ALICE)
    assert world.porcelain.merge("obj:a", "obj:b", "one box")["outcome"] == "merged"


def test_2h_durable_contradictions_read_canon(world):
    """2h: a contradiction carried only by a `knows:` attribute is none (its
    folds were already canon); the same contradiction in canon is reported."""
    world.ingest_structured([
        {"entity": "person:p", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:q", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:p", "attribute": "rank", "value": "king", "timeless": True},
    ])
    private = world.ingest_structured([
        {"entity": "person:q", "attribute": "rank", "value": "beggar", "timeless": True},
    ], frame=ALICE)[0]
    for row in world.buffer.visible(attribute="rank"):
        world.classifier.set(row.id, "CONSTITUTIVE", 1.0)
    assert private.frame == ALICE
    assert world.registry.durable_contradictions("person:p", "person:q") == []
    canon = world.ingest_structured([
        {"entity": "person:q", "attribute": "rank", "value": "beggar", "timeless": True},
    ])[0]
    world.classifier.set(canon.id, "CONSTITUTIVE", 1.0)
    assert world.registry.durable_contradictions("person:p", "person:q") == [
        "rank: 'king' vs 'beggar'"]


def test_2i_election_is_first_seen_among_canon_rows(world):
    """2i (the rule): a closure's representative is its first-seen member among
    canon rows — a non-canon row that mentions a member earlier elects
    nothing."""
    world.ingest_structured([
        {"entity": "person:daniel", "attribute": "mood", "value": "calm"},
    ], frame=ALICE)
    world.ingest_structured([
        {"entity": "person:dan", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:daniel", "attribute": "kind", "value": "person", "timeless": True},
    ])
    assert world.porcelain.merge("person:daniel", "person:dan", "one man")["outcome"] == "merged"
    assert world.registry.resolve("person:daniel") == "person:dan"


def _construct_worlds() -> list[Path]:
    root = os.environ.get("PB_CONSTRUCT_WORLDS")
    return sorted(Path(root).glob("*.world")) if root else []


@pytest.mark.skipif(not _construct_worlds(),
                    reason="opt-in corpus check: set PB_CONSTRUCT_WORLDS to a "
                           "directory of host world files (read through copies)")
def test_2i_construct_worlds_reelect_no_closure(tmp_path):
    """2i (the measurement): over a host corpus, electing among canon rows
    re-elects no closure that electing among all rows chose differently.
    Each world is read through a copy; the originals are never opened."""
    reelected: list[tuple[str, str, str]] = []
    for source in _construct_worlds():
        copy = tmp_path / source.name
        shutil.copyfile(source, copy)
        conn = sqlite3.connect(copy)
        world_id = conn.execute(
            "SELECT value FROM world_meta WHERE key = 'world_id'").fetchone()[0]
        conn.close()
        w = World(copy, world_id=world_id)
        try:
            reg = w.registry
            closures = {frozenset(reg.closure(e)) for e in reg._components()}
            merged = set().union(*closures) if closures else set()
            canon_seen = reg._first_seen_scan(merged, None)
            all_seen: dict[str, int] = {}
            for row in w.buffer.visible():
                for eid in (row.entity, row.value if row.value_type == "entity" else None):
                    if isinstance(eid, str) and eid in merged and eid not in all_seen:
                        all_seen[eid] = row.seq
            for closure in closures:
                old, new = reg._elect(closure, all_seen), reg._elect(closure, canon_seen)
                if old != new:
                    reelected.append((source.name, old, new))
        finally:
            w.close()
    assert reelected == []


# ------------------------------- §3 aka vetoes act on whole correlation groups


def _people(world: World, *names: str) -> None:
    world.ingest_structured([
        {"entity": f"person:{n}", "attribute": "kind", "value": "person", "timeless": True}
        for n in names
    ])


def _masked_and_ilsa(world: World) -> None:
    """The masked figure (alias "ilsa") and Ilsa (name "Ilsa"), correlated by
    a reveal at t=10."""
    world.ingest_structured([
        {"entity": "person:masked", "attribute": "kind", "value": "person",
         "timeless": True, "aliases": ["ilsa"]},
        {"entity": "person:ilsa", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:ilsa", "attribute": "name", "value": "Ilsa", "timeless": True},
    ])
    assert world.correlate("person:masked", "person:ilsa", evidence="the reveal",
                           valid_from=10.0)["outcome"] == "correlated"


def test_3a_correlate_is_vetoed_across_groups(world):
    """3a: canon a~b, then reject(a, c): correlate(b, c) would join two ids
    the world says are different — vetoed, naming the edge; nothing written."""
    _people(world, "a", "b", "c")
    assert world.correlate("person:a", "person:b", evidence="r1")["outcome"] == "correlated"
    assert world.porcelain.reject("person:a", "person:c")["outcome"] == "rejected"
    head = world.buffer.head()
    receipt = world.correlate("person:b", "person:c", evidence="r2")
    assert receipt["outcome"] == "vetoed_distinct"
    assert receipt["reason"] == "distinct_from"
    assert receipt["blocking_edges"] == ["person:a·distinct_from·person:c"]
    assert world.buffer.head() == head


def test_3b_a_group_conflict_surfaces_as_of(world):
    """3b: raw a~b (from 2) and b~c (from 5), over a reject(a, c) made before
    either: one group entry at t=6, none at t=3."""
    _people(world, "a", "b", "c")
    world.porcelain.reject("person:a", "person:c")
    world.ingest_structured([
        {"entity": "person:a", "attribute": "aka", "value": "person:b", "valid_from": 2.0},
        {"entity": "person:b", "attribute": "aka", "value": "person:c", "valid_from": 5.0},
    ])
    assert world.porcelain.correlation_conflicts(as_of=6.0) == [{
        "a": "person:a", "b": "person:c", "aka_edge": None,
        "aka_path": ["person:a·aka·person:b", "person:b·aka·person:c"],
        "distinct_edges": ["person:a·distinct_from·person:c"],
    }]
    assert world.porcelain.correlation_conflicts(as_of=3.0) == []


def test_3c_reconcile_never_collapses_a_reveal(world):
    """3c: the shared anchor "ilsa" no longer merges the two facets, so the
    masked figure's name does not leak to before the reveal."""
    _masked_and_ilsa(world)
    head = world.buffer.head()
    assert world.registry.reconcile() == 0
    assert world.buffer.head() == head                       # no proposal either
    assert world.state("person:masked", "name", valid_as_of=5.0).winner is None


def test_3d_a_proposal_between_facets_is_declined_correlated(world):
    """3d: a `maybe_same_as` between correlated facets lists with decline code
    `correlated`, and promotion merges nothing."""
    _masked_and_ilsa(world)
    world.registry.maybe_same_as("person:masked", "person:ilsa", evidence="extractor")
    listed = [(p["a"], p["b"], p["auto_decline"]["code"])
              for p in world.porcelain.proposals()]
    assert listed == [("person:masked", "person:ilsa", "correlated")]
    assert world.registry.promote_identity_proposals() == 0


def test_3e_reject_of_correlated_facets_is_a_conflict(world):
    """3e: after correlate(p, q), reject(p, q) names the `aka` row and writes
    nothing."""
    _people(world, "p", "q")
    correlated = world.correlate("person:p", "person:q", evidence="reveal")
    head = world.buffer.head()
    assert world.porcelain.reject("person:p", "person:q") == {
        "outcome": "conflict_already_correlated", "canonical_id": "person:p",
        "merge_event_id": None, "reason": "already_correlated",
        "blocking_edges": [correlated["aka_assertion_id"]],
    }
    assert world.buffer.head() == head


def test_3f_a_host_merge_stays_available(world):
    """3f: `aka` is a soft auto-merge block, never a hard veto."""
    _masked_and_ilsa(world)
    assert world.porcelain.merge("person:masked", "person:ilsa",
                                 "the host judged")["outcome"] == "merged"


# ------------------------- §4 identity_conflicts(): merged groups with a vetoed pair

ANCHOR = Path(__file__).resolve().parent.parent / "examples" / "anchor" / "anchor.world"


def _open_copy(source: Path, tmp_path: Path) -> World:
    """A World over a copy of `source` (its world_id read from the file)."""
    copy = tmp_path / source.name
    shutil.copyfile(source, copy)
    conn = sqlite3.connect(copy)
    world_id = conn.execute(
        "SELECT value FROM world_meta WHERE key = 'world_id'").fetchone()[0]
    conn.close()
    return World(copy, world_id=world_id)


def _ring_fused_with_its_box(world: World):
    """The probe world: the ring is in the box, the box is rejected as the
    ring, then a raw canon `same_as` (appended past the gate) fuses them."""
    world.ingest_structured([{"entity": "obj:ring", "attribute": "in", "value": "obj:box"}])
    world.porcelain.reject("obj:box", "obj:ring")
    return _legacy_row(world, "obj:ring", "same_as", "obj:box", "canon")


def test_4a_a_fused_vetoed_pair_is_listed(world):
    """4a: one entry, both edge lists populated, the raw `same_as` named with
    no merge event; the call writes nothing."""
    edge = _ring_fused_with_its_box(world)
    head = world.buffer.head()
    assert world.porcelain.identity_conflicts() == [{
        "canonical_id": "obj:box",
        "members": ["obj:box", "obj:ring"],
        "containment_edges": ["obj:ring·in·obj:box"],
        "distinct_edges": ["obj:box·distinct_from·obj:ring"],
        "same_as": [{"assertion_id": edge.id, "edge": "obj:ring·same_as·obj:box",
                     "merge_event_id": None}],
    }]
    assert world.buffer.head() == head


def test_4b_retracting_the_same_as_clears_it(world):
    """4b: retract that `same_as` and the closure, and the entry, are gone."""
    edge = _ring_fused_with_its_box(world)
    world.porcelain.retract(edge.id, "a ring is not its box")
    assert world.porcelain.identity_conflicts() == []


def test_4c_clean_worlds_list_nothing(world, tmp_path):
    """4c: a clean world (one guarded merge, no vetoed pair inside) and the
    anchor example world give []."""
    _people(world, "dan", "daniel")
    assert world.porcelain.merge("person:dan", "person:daniel", "one man")["outcome"] == "merged"
    assert world.porcelain.identity_conflicts() == []
    anchor = _open_copy(ANCHOR, tmp_path)
    try:
        assert anchor.porcelain.identity_conflicts() == []
    finally:
        anchor.close()


def test_4d_the_read_writes_nothing(world):
    """4d: the head, and every table's content, is unchanged by the call."""
    _ring_fused_with_its_box(world)
    conn = world.buffer.raw_connection()
    head, changes = world.buffer.head(), conn.total_changes
    world.porcelain.identity_conflicts()
    world.identity_conflicts(asserted_as_of=head)
    assert world.buffer.head() == head and conn.total_changes == changes


# ------------------------- §5 open_conflicts is computed on read, frame-scoped, as-of


def _marn_doubts_the_crown(world: World) -> list:
    """Two kind rows (CONSTITUTIVE by guardrail) in Marn's frame only."""
    return world.ingest_structured([
        {"entity": "obj:crown", "attribute": "kind", "value": "crown", "timeless": True},
        {"entity": "obj:crown", "attribute": "kind", "value": "forgery", "timeless": True},
    ], frame=MARN)


def test_5a_no_scan_needed(world):
    """5a: without any `truth.scan()`, a `knows:` frame's audit lists its
    conflict."""
    _marn_doubts_the_crown(world)
    conflicts = world.porcelain.fidelity_audit(frame=MARN)["open_conflicts"]
    assert [(c["entity"], c["attribute"], c["frame"]) for c in conflicts] == [
        ("obj:crown", "kind", MARN)]


def test_5b_a_frame_audit_lists_only_that_frame(world):
    """5b: after a scan, the canon audit does not list a conflict that exists
    only in `knows:person:marn`."""
    _marn_doubts_the_crown(world)
    world.truth.scan()
    assert world.porcelain.fidelity_audit(frame="canon")["open_conflicts"] == []


def test_5c_never_stale(world):
    """5c: retract one side and the entry is gone."""
    rows = _marn_doubts_the_crown(world)
    world.truth.scan()
    world.porcelain.retract(rows[1].id, "Marn learned better")
    assert world.porcelain.fidelity_audit(frame=MARN)["open_conflicts"] == []


def test_5d_honest_about_as_of(world):
    """5d: `kind book @1`, `kind forgery @10`: a conflict at 15, none at 5."""
    world.ingest_structured([
        {"entity": "obj:ledger", "attribute": "kind", "value": "book", "valid_from": 1.0},
        {"entity": "obj:ledger", "attribute": "kind", "value": "forgery", "valid_from": 10.0},
    ])
    world.truth.scan()
    assert world.porcelain.fidelity_audit(as_of=5.0)["open_conflicts"] == []
    late = world.porcelain.fidelity_audit(as_of=15.0)["open_conflicts"]
    assert [(c["entity"], c["attribute"]) for c in late] == [("obj:ledger", "kind")]


def test_5e_anchor_matches_its_stored_flags(tmp_path):
    """5e: on the anchor example world, `open_conflicts(frame="canon")` equals
    the 8 rows its retired `sidecar_conflicts` table stores, field for field —
    under the fold rules of this build's base.

    The stored flags predate FOLD-CORRECTNESS-V1 (batch A, in this base; the
    spec verified 5e at 212754f, before it). Its §4 puts evidence rank first
    in every durability class, so `a:457` — an `inferred` row beside four
    `stated` ones on place:anchor · discrepancy_origin_era — is out-ranked and
    no longer party to that conflict. Every other field is the stored one."""
    world = _open_copy(ANCHOR, tmp_path)
    try:
        stored = world.buffer.raw_connection().execute(
            "SELECT key_entity, key_attribute, key_frame, kind, assertion_ids"
            " FROM sidecar_conflicts ORDER BY key_entity").fetchall()
        assert len(stored) == 8
        outranked = {"a:457"}
        assert world.buffer.get("a:457").status == "inferred"
        expected = [(e, a, f, k, ",".join(i for i in ids.split(",") if i not in outranked))
                    for e, a, f, k, ids in stored]
        computed = [(c.entity, c.attribute, c.frame, c.kind, ",".join(c.assertion_ids))
                    for c in world.truth.open_conflicts(frame="canon")]
        assert computed == expected
    finally:
        world.close()


def test_5f_scan_and_audit_write_nothing(world):
    """5f: `scan()` and `fidelity_audit()` leave the head and every table
    (log and sidecars) unchanged."""
    _marn_doubts_the_crown(world)
    conn = world.buffer.raw_connection()
    head, changes = world.buffer.head(), conn.total_changes
    assert len(world.truth.scan()) == 1
    world.porcelain.fidelity_audit(frame=MARN)
    world.porcelain.fidelity_audit()
    assert world.buffer.head() == head and conn.total_changes == changes
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
    assert "sidecar_conflicts" not in tables                # retired: never created


_FRAMES = ("canon", "knows:person:x", "plot:p")
_KEYS = (("mood", ("calm", "grim")), ("kind", ("box", "urn")),
         ("in", ("place:a", "place:b")), ("held_by", ("person:x", "person:y")))


def test_5_property_open_conflicts_lists_exactly_the_conflicted_keys(tmp_path):
    """Property (Tests): over small generated worlds, `open_conflicts(F,
    as_of)` lists exactly the keys whose `state(...)` is `conflicted`."""
    import random

    # Few entities, three valid times and two documents make ties and
    # cross-source disagreements common: the 20 worlds hold ~25 conflicts.
    for seed in range(20):
        rng = random.Random(seed)
        w = World(tmp_path / f"p{seed}.world", world_id="w:prop",
                  model=StubModel(fallback=rule_classifier_fallback()))
        try:
            entities = ["obj:o1", "obj:o2", "person:p1"]
            items = []
            for _ in range(rng.randint(8, 20)):
                attribute, values = rng.choice(_KEYS)
                item = {"entity": rng.choice(entities), "attribute": attribute,
                        "value": rng.choice(values), "frame": rng.choice(_FRAMES),
                        "status": rng.choice(["stated", "stated", "observed", "inferred"]),
                        "valid_from": rng.choice([1.0, 2.0, 5.0])}
                if rng.random() < 0.5:
                    item["source_doc"] = rng.choice(["doc:a", "doc:b"])
                items.append(item)
            w.ingest_structured(items)
            if rng.random() < 0.5:
                w.porcelain.merge("obj:o1", "obj:o2", "one thing")
            keys = {(w.registry.resolve(e), "in" if a == "held_by" else a)
                    for e in entities for a, _ in _KEYS}
            for frame in _FRAMES:
                for as_of in (None, 1.5, 3.0):
                    listed = {(c.entity, c.attribute)
                              for c in w.truth.open_conflicts(frame, valid_as_of=as_of)}
                    conflicted = {k for k in keys
                                  if w.porcelain.state(k[0], k[1], frame=frame,
                                                       as_of=as_of)["status"] == "conflicted"}
                    assert listed == conflicted, (seed, frame, as_of)
        finally:
            w.close()
