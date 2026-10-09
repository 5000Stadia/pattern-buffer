"""GATE-AUTHORITY-V1: the gate decides by authority, and every refusal is a receipt.

One test per oracle, by section (specs/GATE-AUTHORITY-V1.md), plus the two
suite-level checks the spec's Tests section names:
- every skip reason the suite records is a ``SKIP_REASONS`` code or one of the
  three legacy prose forms (enforced around every test by the autouse fixture
  in ``conftest.py``; ``test_s0_skip_vocabulary`` pins the vocabulary itself);
- a fixed corpus of well-formed items dumps byte-identically to the committed
  fixture, recorded on the engine as it was before this spec.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from patternbuffer import AtomicAbort, World
from patternbuffer.buffer import PatternBuffer
from patternbuffer.dump import build, dump
from patternbuffer.ingest import SKIP_REASONS
from patternbuffer.roles import RoleViolation, _make_engine_roles
from patternbuffer.testing import StubModel, StubModelExhausted, rule_classifier_fallback

FIXTURES = Path(__file__).parent / "fixtures"
CORPUS_LOG = FIXTURES / "gate_authority_corpus.jsonl"
CORPUS_SIDECAR = FIXTURES / "gate_authority_corpus_sidecar.jsonl"


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path / "ga.world", world_id="w:ga",
              model=StubModel(fallback=rule_classifier_fallback()))
    yield w
    w.close()


def _reasons(receipt) -> list[str]:
    return [s["reason"] for s in receipt.skipped]


def _dump_row(seq: int, entity: str, attribute: str, value, *, status="stated",
              value_type="literal", valid_from=None, world_id="w:forged") -> dict:
    """One row of a hand-written JSONL log for dump.build."""
    return {"seq": seq, "id": f"a:{seq}", "world_id": world_id, "entity": entity,
            "attribute": attribute, "value_type": value_type, "value": value,
            "valid_from": valid_from, "valid_to": None, "frame": "canon",
            "status": status, "confidence": None, "asserted_at": seq}


def _jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(r) + "\n" for r in rows)


# ------------------------------------------------------------- the corpus
#
# Well-formed items only: every one passes the gate before and after this spec,
# so the log must not move by a byte. It exercises each side row the gate
# writes, both frame doorways, generated authority, cursor demotion, the
# moved-event pass, declarations, a thunk's resolution, the identity verbs that
# share the guarded merge, commit_set, and p.ingest(source=). Ids that later
# calls reference are taken from earlier receipts, never hard-coded.

_EXTRACTION = {"items": [
    {"entity": "person:cal", "attribute": "kind", "value": "person", "timeless": True},
    {"entity": "person:cal", "attribute": "in", "value": "place:hall",
     "value_type": "entity"},
]}
_INVENTION = {"items": [{"value": "a brass ring", "kind": "ring"}]}


def _row_id(receipt, entity: str, attribute: str) -> str:
    return next(r["assertion_id"] for r in receipt.rows
                if r["entity"] == entity and r["attribute"] == attribute)


def _sidecar_lines(world: World) -> list[str]:
    rows = world.buffer.raw_connection().execute(
        "SELECT assertion_id, durability, class_confidence, needs_review"
        " FROM sidecar_classification").fetchall()
    rows.sort(key=lambda r: int(r[0].split(":")[1]))
    return [json.dumps({"world_id": world.world_id, "assertion_id": r[0],
                        "durability": r[1], "class_confidence": r[2],
                        "needs_review": bool(r[3])}, sort_keys=True)
            for r in rows]


def build_corpus(directory: Path) -> tuple[str, str]:
    """Build the corpus in a fiction world and a tracking world; return the
    two logs' JSONL dump and their rules-mode durability sidecars."""
    fiction = World(directory / "corpus.world", world_id="w:gate_corpus",
                    model=StubModel(responses=[_EXTRACTION, _INVENTION]),
                    clock=lambda: 1000.0)
    p = fiction.porcelain
    base = p.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:cellar", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:cellar", "attribute": "in", "value": "place:hall",
         "timeless": True},
        {"entity": "place:hall", "attribute": "connects_to", "value": "place:yard",
         "timeless": True},
        {"entity": "place:yard", "attribute": "kind", "value": "yard", "timeless": True,
         "aliases": ["the yard", "The Courtyard"]},
        {"entity": "person:ann", "attribute": "kind", "value": "person",
         "timeless": True, "aliases": ["ann", "the keeper"]},
        {"entity": "person:ann", "attribute": "in", "value": "place:hall"},
        {"entity": "person:ann", "attribute": "mood", "value": "calm",
         "confidence": 0.8},
        {"entity": "person:bob", "attribute": "located_in", "value": "place:cellar",
         "valid_from": 1.5},
        {"entity": "person:bob", "attribute": "kind", "value": "person",
         "timeless": True, "status": "observed", "frame": "canon"},
        {"entity": "person:catherine", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "obj:key", "attribute": "kind", "value": "key", "timeless": True},
        {"entity": "obj:key", "attribute": "held_by", "value": "person:ann",
         "valid_from": 1.0},
        {"entity": "obj:box", "attribute": "kind", "value": "box", "timeless": True},
        {"entity": "obj:box", "attribute": "part_of", "value": "place:cellar",
         "timeless": True},
        {"entity": "obj:purse", "attribute": "balance",
         "value": {"$decimal": "12.50"}, "valid_from": 1.0},
        {"entity": "person:ann", "attribute": "job", "value": "clerk",
         "valid_from": 1.0, "valid_to": 3.0},
        {"entity": "person:ann", "attribute": "title", "value": "Keeper",
         "source_doc": "doc:ledger", "status": "stated"},
        {"entity": "event:fire", "attribute": "kind", "value": "fire", "valid_from": 2.0},
        {"entity": "place:hall", "attribute": "state", "value": "burnt",
         "valid_from": 2.0, "caused_by": "event:fire"},
        {"entity": "person:ann", "attribute": "mood", "value": "angry",
         "valid_from": 2.5, "correction": True, "status": "inferred"},
        {"entity": "person:bobby", "attribute": "name", "value": "Bobby",
         "timeless": True, "same_as": "person:bob", "status": "assumed"},
        {"entity": "person:ann", "attribute": "gold", "value": 5,
         "value_type": "delta", "valid_from": 1.0, "fold_policy": "accrue"},
        {"entity": "person:ann", "attribute": "gold", "value": -2,
         "value_type": "delta", "valid_from": 2.0},
        {"entity": "person:ann", "attribute": "allies", "value": "person:bob",
         "arity": "set_valued"},
        {"entity": "person:ann", "attribute": "allies", "value": "person:cat"},
        {"entity": "attr:rank", "attribute": "arity", "value": "functional",
         "timeless": True},
        {"entity": "attr:sigil", "attribute": "structural", "value": True,
         "timeless": True},
        {"entity": "obj:chest", "attribute": "contents",
         "value": {"policy": "invent_under_canon"}, "value_type": "unresolved"},
        {"entity": "obj:chest", "attribute": "in", "value": "place:cellar",
         "timeless": True},
        {"entity": "person:ann", "attribute": "note",
         "value": "repaired: the rival arrives"},
        {"entity": "person:ann", "attribute": "nickname", "value": None},
        # Optional fields given as null that every engine reads as absent.
        {"entity": "person:ann", "attribute": "age", "value": 30, "valid_from": 1.0,
         "value_type": None, "timeless": None, "valid_to": None,
         "confidence": None, "source_doc": None, "caused_by": None,
         "same_as": None, "correction": None},
    ], classify="rules", at=1.0)
    # The call-level frame fills unframed items; an item's own frame wins.
    p.ingest_structured([
        {"entity": "person:ann", "attribute": "mood", "value": "calm"},
        {"entity": "person:ann", "attribute": "secret", "value": "the key",
         "frame": "canon"},
    ], frame="knows:person:bob", classify="rules", at=3.0)
    # Host-authored generated rows into a host-owned frame (letter 029).
    p.ingest_structured([
        {"entity": "arc:main", "attribute": "beat", "value": "rising",
         "status": "generated", "caused_by": "event:fire", "correction": True},
    ], frame="plot:arc1", classify="rules", at=4.0)
    # Cursor-authoritative: the item's year is demoted to source_valid_from.
    p.ingest_structured([
        {"entity": "person:ann", "attribute": "born", "value": "in the north",
         "valid_from": 612},
    ], classify="rules", cursor_authoritative=True, at=5.0)
    # Prose mode: the engine stamps the movement from the cursor.
    p.ingest_structured([
        {"entity": "event:walk1", "attribute": "kind", "value": "moved",
         "complete": True},
        {"entity": "event:walk1", "attribute": "agent", "value": "person:ann",
         "value_type": "entity"},
        {"entity": "event:walk1", "attribute": "origin", "value": "place:hall",
         "value_type": "entity"},
        {"entity": "event:walk1", "attribute": "destination", "value": "place:yard",
         "value_type": "entity"},
        {"entity": "person:ann", "attribute": "in", "value": "place:yard",
         "value_type": "entity"},
    ], classify="rules", extracted=True, at=6.0)
    # Host metadata on assertion ids stays item-writable (non-goals).
    p.ingest_structured([
        {"entity": _row_id(base, "person:ann", "mood"), "attribute": "last_confirmed",
         "value": 12.0, "timeless": True},
        {"entity": _row_id(base, "place:hall", "kind"), "attribute": "world_defining",
         "value": True, "timeless": True},
    ], classify="rules")
    p.ingest_structured([
        {"entity": "obj:lamp", "attribute": "kind", "value": "lamp", "timeless": True},
        {"entity": "obj:lamp", "attribute": "in", "value": "place:yard",
         "value_type": "entity", "valid_from": 6.5},
    ], classify="rules", atomic=True)
    p.commit_set([
        {"op": "assert", "item": {"entity": "person:ann", "attribute": "mood",
                                  "value": "wary", "valid_from": 7.0}},
        {"op": "retract", "assertion_id": _row_id(base, "person:ann", "job"),
         "reason": "mis-heard"},
    ], classify="rules")
    p.ingest("Cal walks into the hall.", source="doc:diary", at=8.0,
             classify="rules")
    # The identity verbs that share the guarded merge, and the resolver.
    p.reject("person:ann", "person:bob")
    p.confirm("person:bobby", "person:bob")
    p.merge("person:cat", "person:catherine", evidence="host: the same woman")
    fiction.resolve("obj:chest", "contents")

    tracking = World(directory / "tracking.world", world_id="w:gate_corpus_tracking",
                     model=StubModel(), policy="observe_or_unknown",
                     clock=lambda: 2000.0)
    tracking.porcelain.ingest_structured([
        {"entity": "place:office", "attribute": "kind", "value": "office",
         "timeless": True},
        {"entity": "person:dee", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:dee", "attribute": "in", "value": "place:office"},
        {"entity": "person:dee", "attribute": "mood", "value": "busy",
         "status": "observed"},
        {"entity": "person:dee", "attribute": "phone", "value": "555-0100"},
        {"entity": "person:d", "attribute": "name", "value": "Dee", "timeless": True,
         "same_as": "person:dee"},
        {"entity": "attr:mood", "attribute": "decay_halflife_seconds", "value": 3600,
         "timeless": True},
    ], classify="rules", at=1.0)

    worlds = (fiction, tracking)
    for w in worlds:
        w.classifier.classify_rows(w.buffer.all_rows(), model=False)
    log = "".join(dump(w.buffer) for w in worlds)
    sidecar = "".join(line + "\n" for w in worlds for line in _sidecar_lines(w))
    for w in worlds:
        w.close()
    return log, sidecar


# ------------------------------------------------- §0 order and vocabulary

def test_s0_skip_vocabulary(skip_reason_is_code):
    """§0: SKIP_REASONS is exactly the table's codes; the suite-wide check
    accepts those and the three legacy prose forms, and nothing else."""
    assert SKIP_REASONS == frozenset({
        "malformed_id", "invalid_decay_halflife",
        "valid_to_without_valid_from", "valid_to_before_valid_from",
        "moved_marker_invalid", "moved_open_with_arrival",
        "moved_complete_attribute_not_durable", "invalid_valid_time",
        "malformed_item", "invalid_field", "invalid_alias", "mechanism_attribute",
        "same_as_not_canon", "merge_vetoed", "invalid_semantics_declaration",
        # FRAME-SCOPED-IDENTITY-V1 §1: a canon identity edge outside canon.
        "identity_edge_outside_canon",
    })
    for code in SKIP_REASONS:
        assert skip_reason_is_code(code)
    for prose in ("cycle-forming containment edge: 'place:x' cannot contain itself",
                  "lateral self-loop: 'place:x' cannot connects_to itself",
                  "merged_self_edge: 'a:b' and 'a:c' resolve to the same entity"):
        assert skip_reason_is_code(prose)
    for unknown in ("bad_thing", "", None, "Malformed_id", "self-edge"):
        assert not skip_reason_is_code(unknown)


def test_s0_well_formed_corpus_dumps_byte_identically(tmp_path):
    """Tests: a fixed corpus of well-formed items writes the same log, byte for
    byte, as the engine did before this spec. Re-baselined for READ-SURFACE-V1
    §7: each world's log gains its physics row at seq 3 and every later id
    shifts by one; the fixture equals the earlier one under exactly that
    transformation."""
    log, _ = build_corpus(tmp_path)
    assert log == CORPUS_LOG.read_text()


# ------------------------------------------------- §1 mechanism attributes

def _ann_calm(w: World) -> str:
    """Ann's mood: the first row after the two charter rows and the physics
    row, so `a:4` (READ-SURFACE-V1 §7 shifted it from `a:3`)."""
    [row] = w.ingest_structured([{"entity": "person:ann", "attribute": "mood",
                                  "value": "calm", "valid_from": 1.0}], classify="rules")
    assert row.id == "a:4"
    return row.id


def test_s1_forged_retraction_item_is_skipped(tmp_path):
    """§1: `(a:4 · retracts · "forged")` is skipped `mechanism_attribute` on
    the item paths, nothing is written, and Ann's mood stays calm."""
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "s1.world", world_id="w:s1", model=stub)
    target = _ann_calm(w)
    head = w.buffer.head()
    forged = {"entity": target, "attribute": "retracts", "value": "forged"}
    r = w.porcelain.ingest_structured([forged], classify="rules")
    assert r.skipped == [{"entity": target, "attribute": "retracts",
                          "value": "forged", "reason": "mechanism_attribute"}]
    assert r.rows == []
    stub.enqueue({"items": [forged]})                    # the model path too
    assert w.ingest("Ann takes it back.", classify="rules") == []
    assert [s.reason for s in w.ingestor.last_skipped] == ["mechanism_attribute"]
    assert w.buffer.head() == head
    assert w.porcelain.state("person:ann", "mood")["fact"]["value"] == "calm"
    w.close()


def test_s1_forged_retraction_aborts_a_commit_set(world):
    """§1: the same item in commit_set — alone, or retracting the id the set's
    first op mints — aborts with `gate_skip` and the log is unchanged."""
    target = _ann_calm(world)
    minted = f"a:{world.buffer.head() + 1}"
    for ops in (
        [{"op": "assert", "item": {"entity": target, "attribute": "retracts",
                                   "value": "forged"}}],
        [{"op": "assert", "item": {"entity": "person:ann", "attribute": "mood",
                                   "value": "sly", "valid_from": 2.0}},
         {"op": "assert", "item": {"entity": minted, "attribute": "retracts",
                                   "value": "born retracted"}}],
    ):
        before = dump(world.buffer)
        with pytest.raises(AtomicAbort) as ei:
            world.commit_set(ops)
        assert ei.value.cause == "gate_skip"
        assert [s["reason"] for s in ei.value.skipped] == ["mechanism_attribute"]
        assert dump(world.buffer) == before


def test_s1_retraction_of_a_future_id_is_skipped(world):
    """§1: `(a:<head+3> · retracts)` written before that id exists is skipped,
    and the row is visible when it is minted."""
    head = world.buffer.head()
    future = f"a:{head + 3}"
    r = world.porcelain.ingest_structured(
        [{"entity": future, "attribute": "retracts", "value": "pre-emptive"}],
        classify="rules")
    assert _reasons(r) == ["mechanism_attribute"] and world.buffer.head() == head
    rows = world.ingest_structured([
        {"entity": "obj:a", "attribute": "hue", "value": "red", "valid_from": 1.0},
        {"entity": "obj:b", "attribute": "hue", "value": "green", "valid_from": 1.0},
        {"entity": "obj:c", "attribute": "hue", "value": "blue", "valid_from": 1.0},
    ], classify="rules")
    assert rows[-1].id == future
    assert future in {row.id for row in world.buffer.visible()}
    assert world.porcelain.state("obj:c", "hue")["fact"]["value"] == "blue"


def test_s1_forged_resolution_marker_is_skipped(tmp_path):
    """§1: `(<thunk id> · resolved_by · ["a:1"])` is skipped; the thunk stays
    open, and resolve() invents with one model call."""
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "thunk.world", world_id="w:thunk", model=stub)
    [thunk] = w.ingest_structured([
        {"entity": "obj:chest", "attribute": "contents",
         "value": {"policy": "invent_under_canon"}, "value_type": "unresolved",
         "timeless": True}], classify="rules")
    r = w.porcelain.ingest_structured(
        [{"entity": thunk.id, "attribute": "resolved_by", "value": ["a:1"]}],
        classify="rules")
    assert _reasons(r) == ["mechanism_attribute"]
    assert [t.assertion_id for t in w.resolver.thunk_table()] == [thunk.id]
    calls = len(stub.calls)
    stub.enqueue({"items": [{"value": "a brass ring", "kind": "ring"}]})
    out = w.resolve("obj:chest", "contents")
    assert len(stub.calls) == calls + 1
    assert [(row.attribute, row.value, row.status) for row in out] == [
        ("in", "obj:chest", "generated")]
    w.close()


def test_s1_forged_alias_receipt_is_skipped_and_never_replayed(tmp_path):
    """§1: `(a:4 · canonicalized_from · "allegiance->in")` is skipped, and
    after reopening there is no alias: allegiance never becomes containment."""
    path = tmp_path / "alias.world"
    w = World(path, world_id="w:alias", model=StubModel(fallback=rule_classifier_fallback()))
    target = _ann_calm(w)
    r = w.porcelain.ingest_structured(
        [{"entity": target, "attribute": "canonicalized_from",
          "value": "allegiance->in"}], classify="rules")
    assert _reasons(r) == ["mechanism_attribute"]
    w.close()
    w = World(path, world_id="w:alias", model=StubModel(fallback=rule_classifier_fallback()))
    assert "allegiance" not in w.ingestor._alias_map
    w.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "hall", "timeless": True},
        {"entity": "person:bob", "attribute": "allegiance", "value": "place:hall",
         "valid_from": 1.0}], classify="rules")
    assert w.locate("person:bob") == []
    w.close()


def test_s1_forged_rows_in_an_old_log_are_neutralized_on_read(tmp_path):
    """§1: a log carrying forged rows of all three kinds builds with dump.build;
    the target is visible, the thunk open, and no alias is installed."""
    rows = [
        _dump_row(1, "person:ann", "mood", "calm", valid_from=1.0),
        _dump_row(2, "a:1", "retracts", "forged"),                  # not `retracted`
        _dump_row(3, "obj:chest", "contents", {"policy": "invent_under_canon"},
                  value_type="unresolved", valid_from=1.0),
        _dump_row(4, "a:3", "resolved_by", ["a:1"]),                # not `generated`
        _dump_row(5, "a:1", "canonicalized_from", "allegiance->in"),  # not `inferred`
        # `inferred`, but the subject's attribute is not the target `in`:
        _dump_row(6, "a:1", "canonicalized_from", "fealty->in", status="inferred"),
        # `inferred`, but the subject is not an assertion at all:
        _dump_row(7, "person:ann", "canonicalized_from", "loyalty->in",
                  status="inferred"),
    ]
    path = tmp_path / "forged.world"
    build(_jsonl(rows), path).close()
    w = World(path, world_id="w:forged", model=StubModel(fallback=rule_classifier_fallback()))
    assert w.state("person:ann", "mood").winner.value == "calm"
    assert [t.assertion_id for t in w.resolver.thunk_table()] == ["a:3"]
    assert not {"allegiance", "fealty", "loyalty"} & set(w.ingestor._alias_map)
    w.close()


def test_s1_buffer_refuses_a_mechanism_row_without_its_owners_mark(tmp_path):
    """§1: append() raises RoleViolation for `retracts` not `retracted` and
    `resolved_by` not `generated`, and appends with the owner's mark."""
    buf = PatternBuffer(tmp_path / "b.world", world_id="w:b")
    roles = _make_engine_roles()
    target = buf.append(entity="obj:x", attribute="hue", value="red",
                        status="stated", role=roles["ingestor"])
    with pytest.raises(RoleViolation):
        buf.append(entity=target.id, attribute="retracts", value="x",
                   status="inferred", role=roles["truth_maintenance"])
    buf.append(entity=target.id, attribute="retracts", value="x",
               status="retracted", role=roles["truth_maintenance"])
    for status in ("stated", "observed", "inferred", "assumed"):
        with pytest.raises(RoleViolation):
            buf.append(entity=target.id, attribute="resolved_by", value=[target.id],
                       status=status, role=roles["ingestor"])
    buf.append(entity=target.id, attribute="resolved_by", value=[target.id],
               status="generated", role=roles["resolver"])
    assert [r.attribute for r in buf.all_rows()] == ["hue", "retracts", "resolved_by"]
    buf.close()


def test_s1_domain_retracts_row_is_skipped(world):
    """§1: a domain row `(person:ann · retracts · "her statement")` is skipped."""
    head = world.buffer.head()
    r = world.porcelain.ingest_structured(
        [{"entity": "person:ann", "attribute": "retracts", "value": "her statement",
          "valid_from": 1.0}], classify="rules")
    assert _reasons(r) == ["mechanism_attribute"]
    assert r.rows == [] and world.buffer.head() == head


# --------------------------------------- §3 authority before the first write

def test_s3_generated_side_fields_raise_before_any_write(world):
    """§3: `generated` into plot:arc1 with `source_doc`, or with
    `aliases: ["the shadow"]`, raises RoleViolation with the head unchanged."""
    for carried in ({"source_doc": "doc:ledger"}, {"aliases": ["the shadow"]}):
        head = world.buffer.head()
        with pytest.raises(RoleViolation, match="letter 029"):
            world.ingest_structured([
                {"entity": "arc:main", "attribute": "beat", "value": "rising",
                 "status": "generated", "frame": "plot:arc1", "valid_from": 1.0,
                 **carried}], classify="rules")
        assert world.buffer.head() == head


@pytest.mark.parametrize("status", ["retracted", "default", "bogus"])
def test_s3_status_outside_the_grant_raises_before_any_declaration(world, status):
    """§3: a status outside the grant on a first-use attribute with an `arity`
    hint raises RoleViolation, leaving no `attr:*` declaration behind."""
    head = world.buffer.head()
    with pytest.raises(RoleViolation, match="may not append status"):
        world.ingest_structured([
            {"entity": "person:ann", "attribute": "allies", "value": "person:bob",
             "arity": "set_valued", "status": status, "valid_from": 1.0}],
            classify="rules")
    assert world.buffer.head() == head
    assert not world.semantics.is_declared("allies")


def test_s3_generated_rows_and_their_side_rows_are_unchanged(world):
    """§3: plain `generated` into plot:, and `generated` with `caused_by` or
    `correction`, write exactly the rows they wrote before."""
    rows = world.ingest_structured([
        {"entity": "arc:main", "attribute": "beat", "value": "rising",
         "status": "generated", "frame": "plot:arc1", "valid_from": 1.0},
        {"entity": "arc:main", "attribute": "turn", "value": "fall",
         "status": "generated", "frame": "plot:arc1", "valid_from": 2.0,
         "caused_by": "event:storm"},
        {"entity": "arc:main", "attribute": "twist", "value": "betrayal",
         "status": "generated", "frame": "plot:arc1", "valid_from": 3.0,
         "correction": True},
    ], classify="rules")
    turn, twist = rows[1].id, rows[3].id
    assert [(r.entity, r.attribute, r.value, r.status, r.frame) for r in rows] == [
        ("arc:main", "beat", "rising", "generated", "plot:arc1"),
        ("arc:main", "turn", "fall", "generated", "plot:arc1"),
        (turn, "caused_by", "event:storm", "inferred", "plot:arc1"),
        ("arc:main", "twist", "betrayal", "generated", "plot:arc1"),
        (twist, "correction_proposal", True, "inferred", "canon"),
    ]


def test_s3_a_violation_mid_call_keeps_the_per_row_contract(world):
    """§3: a non-atomic [ok, violating, ok] call keeps the first item, writes
    nothing of the violating item, and raises."""
    head = world.buffer.head()
    with pytest.raises(RoleViolation):
        world.ingest_structured([
            {"entity": "obj:a", "attribute": "hue", "value": "red", "valid_from": 1.0},
            {"entity": "obj:b", "attribute": "hue", "value": "grey",
             "status": "generated", "frame": "plot:x", "source_doc": "doc:x"},
            {"entity": "obj:c", "attribute": "hue", "value": "blue", "valid_from": 1.0},
        ], classify="rules")
    assert [(r.entity, r.attribute) for r in world.buffer.all_rows()[head:]] == [
        ("obj:a", "hue")]


# ------------------------------------------------- §4 one _normalize_item

_BEFORE = {"entity": "obj:before", "attribute": "hue", "value": "red", "valid_from": 1.0}
_AFTER = {"entity": "obj:after", "attribute": "hue", "value": "blue", "valid_from": 1.0}


def _around(world: World, bad, **kw):
    """Ingest [good, bad, good] through the porcelain and check that the rest
    of the call still ingests (every §4 oracle asserts it)."""
    r = world.porcelain.ingest_structured([_BEFORE, bad, _AFTER], classify="rules", **kw)
    assert {"obj:before", "obj:after"} <= {row["entity"] for row in r.rows}
    return r


def _aliases_of(world: World, entity: str) -> list:
    return [row.value for row in world.buffer.visible(entity=entity, attribute="alias")]


def test_s4_string_aliases_are_one_alias(world):
    """§4: `aliases: "the vault"` writes one alias row, `"the vault"`."""
    r = _around(world, {"entity": "obj:vault", "attribute": "kind", "value": "vault",
                        "timeless": True, "aliases": "the vault"})
    assert r.skipped == []
    assert _aliases_of(world, "obj:vault") == ["the vault"]
    assert world.registry.by_alias("the vault") == {"obj:vault"}


def test_s4_null_aliases_are_no_aliases(world):
    """§4: `aliases: None` writes no alias rows and no skip."""
    r = _around(world, {"entity": "obj:vault", "attribute": "kind", "value": "vault",
                        "timeless": True, "aliases": None})
    assert r.skipped == [] and _aliases_of(world, "obj:vault") == []
    assert "obj:vault" in {row["entity"] for row in r.rows}


def test_s4_invalid_alias_members_are_receipted(world):
    """§4: `aliases: ["", "  ", 5, "ok"]` writes one alias row and three
    `invalid_alias` records; `aliases: 5` gives one, and the main row lands."""
    r = _around(world, {"entity": "obj:vault", "attribute": "kind", "value": "vault",
                        "timeless": True, "aliases": ["", "  ", 5, "ok"]})
    assert _aliases_of(world, "obj:vault") == ["ok"]
    assert r.skipped == [
        {"entity": "obj:vault", "attribute": "alias", "value": bad,
         "reason": "invalid_alias"} for bad in ("", "  ", 5)]
    r = _around(world, {"entity": "obj:safe", "attribute": "kind", "value": "safe",
                        "timeless": True, "aliases": 5})
    assert r.skipped == [{"entity": "obj:safe", "attribute": "alias", "value": 5,
                          "reason": "invalid_alias"}]
    assert "obj:safe" in {row["entity"] for row in r.rows}
    assert _aliases_of(world, "obj:safe") == []


def test_s4_null_frame_takes_the_default_frame(world):
    """§4: `frame: None` lands in canon, or in the call's `frame=`; generated
    lands in the call's plot frame, and with no call frame it is canon, which
    raises letter 029."""
    item = {"entity": "obj:x", "attribute": "hue", "value": "red", "valid_from": 1.0,
            "frame": None}
    r = _around(world, item)
    assert [row["frame"] for row in r.rows if row["entity"] == "obj:x"] == ["canon"]
    r = _around(world, {**item, "entity": "obj:y"}, frame="knows:person:ann")
    assert [row["frame"] for row in r.rows if row["entity"] == "obj:y"] == [
        "knows:person:ann"]
    generated = {"entity": "arc:a", "attribute": "beat", "value": "rise",
                 "status": "generated", "frame": None, "valid_from": 1.0}
    r = _around(world, generated, frame="plot:x")
    assert [(row["frame"]) for row in r.rows if row["entity"] == "arc:a"] == ["plot:x"]
    head = world.buffer.head()
    with pytest.raises(ValueError, match="letter 029"):
        world.ingest_structured([generated], classify="rules")
    assert world.buffer.head() == head


@pytest.mark.parametrize("frame", [5, ""])
def test_s4_malformed_frame_is_malformed_item(world, frame):
    """§4: `frame: 5` or `""` gives `malformed_item`, never canon."""
    r = _around(world, {"entity": "obj:x", "attribute": "hue", "value": "red",
                        "frame": frame})
    assert r.skipped == [{"entity": "obj:x", "attribute": "hue", "value": "red",
                          "reason": "malformed_item",
                          "detail": {"field": "frame", "value": frame}}]
    assert world.buffer.visible(entity="obj:x") == []


def test_s4_missing_required_field_is_malformed_item(world):
    """§4: a missing `entity`, `attribute` or `value` (or a null entity or
    attribute) gives `malformed_item` with the missing fields."""
    full = {"entity": "obj:x", "attribute": "hue", "value": "red"}
    for missing in ("entity", "attribute", "value"):
        r = _around(world, {k: v for k, v in full.items() if k != missing})
        assert _reasons(r) == ["malformed_item"]
        assert r.skipped[0]["detail"] == {"missing": [missing]}
        assert r.skipped[0][missing] is None
    for null in ("entity", "attribute"):
        r = _around(world, {**full, null: None})
        assert r.skipped[0]["detail"] == {"missing": [null]}
    r = _around(world, {"value": "red"})
    assert r.skipped[0]["detail"] == {"missing": ["entity", "attribute"]}
    assert world.buffer.visible(entity="obj:x") == []


def test_s4_non_string_entity_and_blank_attribute(world):
    """§4: `entity: 5` gives `malformed_id`; `attribute: 7` or `"  "` gives
    `malformed_item`."""
    r = _around(world, {"entity": 5, "attribute": "hue", "value": "red"})
    assert r.skipped == [{"entity": 5, "attribute": "hue", "value": "red",
                          "reason": "malformed_id"}]
    for attribute in (7, "  "):
        r = _around(world, {"entity": "obj:x", "attribute": attribute, "value": "red"})
        assert r.skipped == [{"entity": "obj:x", "attribute": attribute, "value": "red",
                              "reason": "malformed_item",
                              "detail": {"field": "attribute", "value": attribute}}]
    assert world.buffer.visible(entity="obj:x") == []


def test_s4_bare_string_item_is_malformed_item(world):
    """§4: a bare string item gives `malformed_item`, in ordinary and in
    `extracted=True` mode (where the moved-event pass passes it through)."""
    record = {"entity": None, "attribute": None, "value": "obj:x hue red",
              "reason": "malformed_item"}
    r = _around(world, "obj:x hue red")
    assert r.skipped == [record]
    world.ingestor.cursor.advance(4.0)
    r = _around(world, "obj:x hue red", extracted=True)
    assert r.skipped == [record]
    moved = [
        {"entity": "event:m1", "attribute": "kind", "value": "moved", "complete": True},
        {"entity": "event:m1", "attribute": "agent", "value": "person:ann",
         "value_type": "entity"},
        {"entity": "event:m1", "attribute": "destination", "value": "place:yard",
         "value_type": "entity"},
        "obj:x hue red",
        {"entity": "person:ann", "attribute": "in", "value": "place:yard",
         "value_type": "entity"},
    ]
    r = world.porcelain.ingest_structured(moved, classify="rules", extracted=True)
    assert r.skipped == [record]
    assert world.locate("person:ann") == ["place:yard"]


def test_s4_entity_typed_non_string_value_is_malformed_id(world):
    """§4: `in: 5` with `value_type: "entity"` gives `malformed_id`."""
    r = _around(world, {"entity": "person:ann", "attribute": "in", "value": 5,
                        "value_type": "entity"})
    assert r.skipped == [{"entity": "person:ann", "attribute": "in", "value": 5,
                          "reason": "malformed_id"}]
    assert world.locate("person:ann") == []


def test_s4_unknown_value_type_is_invalid_field(world):
    """§4: `value_type: "thing"` gives `invalid_field`, and no first-use
    declaration is left behind."""
    r = _around(world, {"entity": "person:ann", "attribute": "allies",
                        "value": "person:bob", "value_type": "thing",
                        "arity": "set_valued"})
    assert r.skipped == [{"entity": "person:ann", "attribute": "allies",
                          "value": "person:bob", "reason": "invalid_field",
                          "detail": {"field": "value_type", "value": "thing"}}]
    assert not world.semantics.is_declared("allies")


@pytest.mark.parametrize("field,bad", [
    ("timeless", "false"), ("correction", "false"), ("confidence", "high")])
def test_s4_mistyped_flags_and_confidence_are_invalid_field(world, field, bad):
    """§4: `timeless: "false"`, `correction: "false"` and `confidence: "high"`
    each give `invalid_field`."""
    r = _around(world, {"entity": "obj:x", "attribute": "hue", "value": "red",
                        "valid_from": 1.0, field: bad})
    assert r.skipped == [{"entity": "obj:x", "attribute": "hue", "value": "red",
                          "reason": "invalid_field",
                          "detail": {"field": field, "value": bad}}]
    assert world.buffer.visible(entity="obj:x") == []


def test_s4_null_status_reads_as_stated(world):
    """§4: `status: None` reads as `stated`."""
    r = _around(world, {"entity": "obj:x", "attribute": "hue", "value": "red",
                        "valid_from": 1.0, "status": None})
    assert r.skipped == []
    [row] = world.buffer.visible(entity="obj:x")
    assert row.status == "stated"


def test_s4_atomic_null_aliases_commit_and_invalid_alias_aborts(world):
    """§4: under `atomic=True`, `aliases: None` commits, and `aliases: [5]`
    aborts the set with `gate_skip`."""
    item = {"entity": "obj:vault", "attribute": "kind", "value": "vault",
            "timeless": True}
    r = world.porcelain.ingest_structured([{**item, "aliases": None}, _AFTER],
                                          classify="rules", atomic=True)
    assert r.skipped == [] and len(r.rows) == 2
    head = world.buffer.head()
    with pytest.raises(AtomicAbort) as ei:
        world.porcelain.ingest_structured(
            [{**item, "entity": "obj:safe", "aliases": [5]}, _BEFORE],
            classify="rules", atomic=True)
    assert ei.value.cause == "gate_skip"
    assert ei.value.skipped == [{"entity": "obj:safe", "attribute": "alias",
                                 "value": 5, "reason": "invalid_alias"}]
    assert world.buffer.head() == head


# ------------------------------------- §5 semantics declarations validated

def _declaration_skip(entity, attribute, value, field, bad, source) -> dict:
    return {"entity": entity, "attribute": attribute, "value": value,
            "reason": "invalid_semantics_declaration",
            "detail": {"field": field, "value": bad, "source": source}}


def test_s5_invalid_hint_skips_the_item_and_leaves_the_attribute_open(world):
    """§5: hint `arity: "many"` skips the item with nothing written; a later
    `arity: "set_valued"` declares it, and two allies coexist."""
    head = world.buffer.head()
    r = world.porcelain.ingest_structured([
        {"entity": "person:ann", "attribute": "allies", "value": "person:bob",
         "valid_from": 1.0, "arity": "many"}], classify="rules")
    assert r.skipped == [_declaration_skip("person:ann", "allies", "person:bob",
                                           "arity", "many", "item")]
    assert world.buffer.head() == head
    world.ingest_structured([
        {"entity": "person:ann", "attribute": "allies", "value": "person:bob",
         "valid_from": 1.0, "arity": "set_valued"},
        {"entity": "person:ann", "attribute": "allies", "value": "person:cat",
         "valid_from": 1.0}], classify="rules")
    fold = world.state("person:ann", "allies")
    assert set(fold.values) == {"person:bob", "person:cat"} and not fold.conflicted


@pytest.mark.parametrize("field,bad", [
    ("relation_family", "container"), ("fold_policy", "acrue")])
def test_s5_invalid_family_and_fold_policy_hints_skip(world, field, bad):
    """§5: `relation_family: "container"` and `fold_policy: "acrue"` skip
    their item instead of being silently ignored."""
    head = world.buffer.head()
    r = world.porcelain.ingest_structured([
        {"entity": "person:ann", "attribute": "coins", "value": 5,
         "value_type": "delta", "valid_from": 1.0, field: bad}], classify="rules")
    assert r.skipped == [_declaration_skip("person:ann", "coins", 5, field, bad, "item")]
    assert world.buffer.head() == head
    assert not world.semantics.is_declared("coins")


def test_s5_invalid_attribute_default_skips_every_item_on_it(tmp_path):
    """§5: an `attribute_default` returning `{"arity": "multi"}` skips each
    item on that attribute (source `attribute_default`) and declares nothing;
    the callback is asked again until it is fixed."""
    asked: list[str] = []

    def default(attribute: str):
        asked.append(attribute)
        return {"arity": "multi"} if attribute == "allies" else None

    w = World(tmp_path / "ad.world", world_id="w:ad", attribute_default=default,
              model=StubModel(fallback=rule_classifier_fallback()))
    for ally in ("person:bob", "person:cat"):
        r = w.porcelain.ingest_structured([
            {"entity": "person:ann", "attribute": "allies", "value": ally,
             "valid_from": 1.0}], classify="rules")
        assert r.skipped == [_declaration_skip("person:ann", "allies", ally, "arity",
                                               "multi", "attribute_default")]
    assert asked.count("allies") == 2
    assert not w.semantics.is_declared("allies")
    assert w.buffer.visible(entity="person:ann") == []
    w.close()


def test_s5_manual_structural_declaration_must_be_a_real_bool(world):
    """§5: a manual `attr:mood2 · structural · "false"` row skips; with `True`
    it is written and `mood2` is structural."""
    r = world.porcelain.ingest_structured([
        {"entity": "attr:mood2", "attribute": "structural", "value": "false",
         "timeless": True}], classify="rules")
    assert r.skipped == [_declaration_skip("attr:mood2", "structural", "false",
                                           "structural", "false", "attr_row")]
    assert not world.semantics.is_declared("mood2")
    assert not world.semantics.is_structural("mood2")
    r = world.porcelain.ingest_structured([
        {"entity": "attr:mood2", "attribute": "structural", "value": True,
         "timeless": True}], classify="rules")
    assert r.skipped == [] and world.semantics.is_structural("mood2")


def test_s5_vocabulary_authority_still_raises_first(world):
    """§5: a manual declaration on `in`, or after data exists, raises
    ValueError even when its value is also invalid."""
    with pytest.raises(ValueError, match="inviolable core"):
        world.ingest_structured([{"entity": "attr:in", "attribute": "arity",
                                  "value": "many", "timeless": True}], classify="rules")
    world.ingest_structured([{"entity": "obj:x", "attribute": "hue", "value": "red",
                              "valid_from": 1.0}], classify="rules")
    with pytest.raises(ValueError, match="after folded data"):
        world.ingest_structured([{"entity": "attr:hue", "attribute": "arity",
                                  "value": "many", "timeless": True}], classify="rules")


def test_s5_read_side_ignores_invalid_declared_values(tmp_path):
    """§5: a log carrying `structural: "false"` and `arity: "many"`, built from
    JSONL, reads `is_structural` false and `arity == "functional"`."""
    rows = [
        _dump_row(1, "attr:mood2", "structural", "false", status="inferred"),
        _dump_row(2, "attr:mood2", "arity", "many", status="inferred"),
        _dump_row(3, "person:ann", "mood2", "calm", valid_from=1.0),
    ]
    path = tmp_path / "decl.world"
    build(_jsonl(rows), path).close()
    w = World(path, world_id="w:forged", model=StubModel(fallback=rule_classifier_fallback()))
    assert w.semantics.is_structural("mood2") is False
    assert w.semantics.semantics("mood2").arity == "functional"
    w.close()


# ---------------------------- §7 id-shaped values on entity-valued predicates

def test_s7_id_shaped_typo_never_relocates_its_subject(world):
    """§7: Ann is in place:cellar; `in: "Place:Cellar"` is skipped
    `malformed_id` and Ann stays in the cellar."""
    world.ingest_structured([
        {"entity": "place:cellar", "attribute": "kind", "value": "cellar",
         "timeless": True},
        {"entity": "person:ann", "attribute": "in", "value": "place:cellar",
         "valid_from": 1.0}], classify="rules")
    r = world.porcelain.ingest_structured([
        {"entity": "person:ann", "attribute": "in", "value": "Place:Cellar",
         "valid_from": 2.0}], classify="rules")
    assert r.skipped == [{"entity": "person:ann", "attribute": "in",
                          "value": "Place:Cellar", "reason": "malformed_id"}]
    assert world.locate("person:ann") == ["place:cellar"]
    assert world.contents("place:cellar") == ["person:ann"]


@pytest.mark.parametrize("entity,attribute,value", [
    ("person:ann", "in", "place:/cellar"),
    ("person:ann", "in", "place:the cellar"),
    ("place:hall", "connects_to", "Place:Hall"),
    ("place:alcove", "part_of", "Place:House"),
    ("obj:key", "held_by", "person:Bob"),
    ("event:smoke", "caused_by", "Event:Fire"),
    ("person:ann", "distinct_from", "Person:B"),
    ("obj:coin", "stowed_in", "Obj:Chest"),     # a declared containment member
])
def test_s7_id_shaped_values_are_malformed_ids(world, entity, attribute, value):
    """§7: an id-shaped value failing the grammar on an entity-valued
    predicate (the families via semantics, part_of, caused_by, the identity
    predicates) is skipped `malformed_id`."""
    world.ingest_structured([
        {"entity": "attr:stowed_in", "attribute": "relation_family",
         "value": "containment", "timeless": True}], classify="rules")
    head = world.buffer.head()
    r = world.porcelain.ingest_structured([
        {"entity": entity, "attribute": attribute, "value": value,
         "valid_from": 1.0}], classify="rules")
    assert r.skipped == [{"entity": entity, "attribute": attribute, "value": value,
                          "reason": "malformed_id"}]
    assert world.buffer.head() == head


@pytest.mark.parametrize("attribute,value,extra", [
    ("in", "repaired: the rival arrives", {}),
    ("in", "12:30", {}),
    ("mood", "Note:see", {}),
    ("in", "Place:Cellar", {"value_type": "literal"}),
])
def test_s7_admitted_as_before(world, attribute, value, extra):
    """§7: not id-shaped, not an entity-valued predicate, or an explicit
    literal — admitted as a literal, as before."""
    r = world.porcelain.ingest_structured([
        {"entity": "person:ann", "attribute": attribute, "value": value,
         "valid_from": 1.0, **extra}], classify="rules")
    assert r.skipped == []
    [row] = world.buffer.visible(entity="person:ann", attribute=attribute)
    assert (row.value, row.value_type) == (value, "literal")


# --------------------------------------- §2 a raw same_as is a guarded merge
#
# test_source_identity O14 and test_moved_event oracle 11 write passing raw
# same_as rows; they stay green unchanged.

_PEOPLE = [{"entity": f"person:{name}", "attribute": "kind", "value": "person",
            "timeless": True} for name in ("x", "y", "z")]


def _raw_same_as(world: World, a: str, b, **item):
    return world.porcelain.ingest_structured(
        [{"entity": a, "attribute": "same_as", "value": b, **item}], classify="rules")


def test_s2_containment_veto_holds_for_a_raw_same_as(world):
    """§2: with the key in the box, `(key · same_as · box)` is skipped
    `merge_vetoed` naming the blocking edge; the key stays in the box."""
    world.ingest_structured([
        {"entity": "obj:box", "attribute": "kind", "value": "box", "timeless": True},
        {"entity": "obj:key", "attribute": "in", "value": "obj:box", "valid_from": 1.0},
    ], classify="rules")
    head = world.buffer.head()
    r = _raw_same_as(world, "obj:key", "obj:box")
    assert r.skipped == [{"entity": "obj:key", "attribute": "same_as",
                          "value": "obj:box", "reason": "merge_vetoed",
                          "detail": {"veto": "containment",
                                     "blocking_edges": ["obj:key·in·obj:box"]}}]
    assert world.buffer.head() == head
    assert world.registry.closure("obj:key") == {"obj:key"}
    assert world.locate("obj:key") == ["obj:box"]


def test_s2_distinct_from_veto_holds_for_a_raw_same_as(world):
    """§2: after `reject(a, b)`, `(a · same_as · b)` is skipped `merge_vetoed`
    with veto `distinct_from`; the pair stays distinct."""
    world.ingest_structured(_PEOPLE, classify="rules")
    assert world.porcelain.reject("person:x", "person:y")["outcome"] == "rejected"
    r = _raw_same_as(world, "person:x", "person:y")
    assert r.skipped == [{"entity": "person:x", "attribute": "same_as",
                          "value": "person:y", "reason": "merge_vetoed",
                          "detail": {"veto": "distinct_from",
                                     "blocking_edges": ["person:x·distinct_from·person:y"]}}]
    assert world.porcelain.reject("person:x", "person:y")["outcome"] == "noop_already_distinct"


def test_s2_a_passing_raw_same_as_writes_the_merge_verbs_rows(tmp_path):
    """§2: `(x · same_as · y)` with no veto writes the four rows
    `p.merge(x, y, evidence="same_as item")` would, classified EVENT with the
    call; the main-row side rows attach to the same_as edge."""
    def seeded(name: str) -> World:
        w = World(tmp_path / f"{name}.world", world_id="w:same",
                  model=StubModel(fallback=rule_classifier_fallback()))
        w.ingest_structured(_PEOPLE, classify="rules")
        return w

    gate, verb = seeded("gate"), seeded("verb")
    r = _raw_same_as(gate, "person:x", "person:y", status="stated", valid_from=4.0)
    verb.porcelain.merge("person:x", "person:y", evidence="same_as item")
    assert dump(gate.buffer) == dump(verb.buffer)
    assert r.skipped == []
    # READ-SURFACE-V1 §7: a fresh world's physics row shifts these ids by one.
    assert [(row["entity"], row["attribute"]) for row in r.rows] == [
        ("event:merge_7", "kind"), ("person:x", "same_as"),
        ("a:8", "caused_by"), ("event:merge_7", "evidence")]
    assert {gate.classifier.durability(row["assertion_id"]) for row in r.rows} == {"EVENT"}
    assert gate.registry.resolve("person:x") == gate.registry.resolve("person:y")
    edge = r.rows[1]["assertion_id"]
    r = _raw_same_as(gate, "person:z", "person:x", source_doc="doc:ledger",
                     caused_by="event:reveal", correction=True)
    edge = r.rows[1]["assertion_id"]
    assert [(row["entity"], row["attribute"]) for row in r.rows[4:]] == [
        (edge, "source"), (edge, "caused_by"), (edge, "correction_proposal")]
    gate.close()
    verb.close()


def test_s2_same_as_outside_canon_is_refused(world):
    """§2: `(person:x · same_as · person:z)` in `knows:person:x` is skipped
    `same_as_not_canon` and nothing is written."""
    world.ingest_structured(_PEOPLE, classify="rules")
    head = world.buffer.head()
    r = _raw_same_as(world, "person:x", "person:z", frame="knows:person:x")
    assert r.skipped == [{"entity": "person:x", "attribute": "same_as",
                          "value": "person:z", "reason": "same_as_not_canon",
                          "detail": {"field": "frame", "value": "knows:person:x"}}]
    assert world.buffer.head() == head
    assert world.registry.closure("person:x") == {"person:x"}


@pytest.mark.parametrize("value,extra", [
    ("Person:Y", {}), ("the same guy", {}), ("person:y", {"value_type": "literal"})])
def test_s2_a_raw_same_as_value_must_be_an_id(world, value, extra):
    """§2: `"Person:Y"`, `"the same guy"`, or `"person:y"` with an explicit
    `value_type: "literal"` are skipped `malformed_id`."""
    world.ingest_structured(_PEOPLE, classify="rules")
    head = world.buffer.head()
    r = _raw_same_as(world, "person:x", value, **extra)
    assert r.skipped == [{"entity": "person:x", "attribute": "same_as",
                          "value": value, "reason": "malformed_id"}]
    assert world.buffer.head() == head


def test_s2_an_already_merged_pair_writes_nothing(world):
    """§2: a raw same_as for a pair already merged, or `x same_as x`, writes
    no row and no skip; the item's subject-level rows still land."""
    world.ingest_structured(_PEOPLE, classify="rules")
    world.porcelain.merge("person:x", "person:y", evidence="host")
    for a, b in (("person:x", "person:y"), ("person:y", "person:x"),
                 ("person:z", "person:z")):
        head = world.buffer.head()
        r = _raw_same_as(world, a, b, source_doc="doc:ledger")
        assert r.skipped == [] and r.rows == []
        assert world.buffer.head() == head
    r = _raw_same_as(world, "person:x", "person:y", aliases=["the twin"])
    assert r.skipped == [] and r.rows == []
    assert world.registry.by_alias("the twin") == {world.registry.resolve("person:x")}


def test_s2_commit_set_carries_the_merge_or_aborts(world):
    """§2: in commit_set a vetoed raw same_as aborts with `gate_skip`; a
    passing one commits its merge rows with the set."""
    world.ingest_structured(_PEOPLE + [
        {"entity": "obj:box", "attribute": "kind", "value": "box", "timeless": True},
        {"entity": "obj:key", "attribute": "in", "value": "obj:box", "valid_from": 1.0},
    ], classify="rules")
    head = world.buffer.head()
    with pytest.raises(AtomicAbort) as ei:
        world.commit_set([
            {"op": "assert", "item": {"entity": "person:x", "attribute": "mood",
                                      "value": "calm", "valid_from": 2.0}},
            {"op": "assert", "item": {"entity": "obj:key", "attribute": "same_as",
                                      "value": "obj:box"}},
        ])
    assert ei.value.cause == "gate_skip"
    assert [s["reason"] for s in ei.value.skipped] == ["merge_vetoed"]
    assert world.buffer.head() == head
    rows = world.commit_set([
        {"op": "assert", "item": {"entity": "person:x", "attribute": "mood",
                                  "value": "calm", "valid_from": 2.0}},
        {"op": "assert", "item": {"entity": "person:x", "attribute": "same_as",
                                  "value": "person:y"}},
    ])
    assert [r.attribute for r in rows] == ["mood", "kind", "same_as", "caused_by",
                                           "evidence"]
    assert world.registry.resolve("person:y") == world.registry.resolve("person:x")


# ------------------------ §6 p.ingest() receipts and the cursor on rejection

_GENERATED_INTO_CANON = {"entity": "obj:x", "attribute": "hue", "value": "grey",
                         "status": "generated", "frame": "canon"}


def test_s6_p_ingest_receipts_its_skips(tmp_path):
    """§6: an extraction yielding `person:/you` and a self-edge lists both in
    `skipped` (malformed_id, then the cycle reason); the same with `source=`."""
    extraction = {"items": [
        {"entity": "person:/you", "attribute": "mood", "value": "tired"},
        {"entity": "place:hall", "attribute": "in", "value": "place:hall",
         "timeless": True},
        {"entity": "person:ann", "attribute": "mood", "value": "calm"},
    ]}
    w = World(tmp_path / "pi.world", world_id="w:pi",
              model=StubModel(responses=[extraction, extraction]))
    for source in (None, "doc:diary"):
        r = w.porcelain.ingest("Ann rests in the hall.", source=source,
                               classify="rules")
        assert [s["reason"] for s in r.skipped][:1] == ["malformed_id"]
        assert r.skipped[0]["entity"] == "person:/you"
        assert r.skipped[1]["reason"].startswith("cycle-forming containment edge: ")
        assert len(r.skipped) == 2
    assert [row["attribute"] for row in r.rows] == ["mood", "source"]
    w.close()


def test_s6_a_rejected_call_leaves_the_cursor_where_it_was(tmp_path):
    """§6: from a cursor at 5, `classify="bogus"` with at=99, a generated-into-
    canon raise with at=77, a failing model with at=42, and atomic with
    `classify="inline"` at=60 each leave the cursor at 5."""
    stub = StubModel()                      # an unscripted model call fails
    w = World(tmp_path / "pose.world", world_id="w:pose", model=stub)
    p = w.porcelain
    w.ingestor.cursor.advance(5.0)

    def bogus_after_extraction():
        stub.enqueue({"items": [_BEFORE]})
        p.ingest("text", classify="bogus", at=99)

    for call, error in (
        (lambda: p.ingest_structured([_BEFORE], classify="bogus", at=99), ValueError),
        (bogus_after_extraction, ValueError),
        (lambda: p.ingest_structured([_GENERATED_INTO_CANON], classify="rules", at=77),
         ValueError),
        (lambda: p.ingest("text", classify="rules", at=42), StubModelExhausted),
        (lambda: p.ingest_structured([_BEFORE], classify="inline", atomic=True, at=60),
         ValueError),
    ):
        head = w.buffer.head()
        with pytest.raises(error):
            call()
        assert w.buffer.head() == head
        assert w.ingestor.cursor.position == 5.0
    w.close()


def test_s6_a_partial_write_keeps_the_cursor_at_at(world):
    """§6: `[ok item, generated-into-canon]` with at=70 leaves the cursor at
    70, where the first row was stamped."""
    world.ingestor.cursor.advance(5.0)
    head = world.buffer.head()
    with pytest.raises(ValueError, match="letter 029"):
        world.porcelain.ingest_structured(
            [{"entity": "obj:a", "attribute": "hue", "value": "red"},
             _GENERATED_INTO_CANON], classify="rules", at=70)
    assert world.ingestor.cursor.position == 70
    [row] = world.buffer.all_rows()[head:]
    assert (row.entity, row.valid_from) == ("obj:a", 70)


def test_s6_atomic_abort_restores_the_cursor(world):
    """§6: an AtomicAbort restores the cursor, unchanged."""
    world.ingestor.cursor.advance(5.0)
    head = world.buffer.head()
    with pytest.raises(AtomicAbort) as ei:
        world.porcelain.ingest_structured(
            [_BEFORE, {"entity": "person:/you", "attribute": "mood", "value": "x"}],
            classify="rules", atomic=True, at=60)
    assert ei.value.cause == "gate_skip"
    assert world.buffer.head() == head
    assert world.ingestor.cursor.position == 5.0


# --------------------------------------- §8 bookkeeping never reaches the model

def _tracked_world(tmp_path, stub: StubModel) -> World:
    return World(tmp_path / "tracked.world", world_id="w:tracked", model=stub,
                 policy="observe_or_unknown", clock=lambda: 1000.0)


_TRACKED_WRITES = [{"entity": f"obj:o{i}", "attribute": "condition", "value": "ok",
                    "valid_from": float(i)} for i in range(5)]


def _verdict(world: World, assertion_id: str) -> tuple[str, float]:
    c = world.classifier.get(assertion_id)
    return c.durability, c.class_confidence


def test_s8_a_tracking_sweep_judges_only_the_facts(tmp_path):
    """§8: five tracked writes with classify="defer", then classify_all():
    five per-row model calls (not ten), and every learned_at_wallclock row is
    STATE 0.5."""
    stub = StubModel(fallback=rule_classifier_fallback())
    w = _tracked_world(tmp_path, stub)
    w.ingest_structured(_TRACKED_WRITES, classify="defer")
    calls = len(stub.calls)
    assert w.classifier.classify_all() == 10
    assert len(stub.calls) - calls == 5
    stamps = [r for r in w.buffer.all_rows() if r.attribute == "learned_at_wallclock"]
    assert len(stamps) == 5
    assert {_verdict(w, r.id) for r in stamps} == {("STATE", 0.5)}
    w.close()


def test_s8_seal_build_batch_prompt_lists_no_assertion_rows(tmp_path):
    """§8: `seal_build(model=True)` sends no `a:N` line to the batch prompt."""
    stub = StubModel(fallback=rule_classifier_fallback())
    w = _tracked_world(tmp_path, stub)
    w.porcelain.begin_build(at=1.0)
    w.porcelain.ingest_structured(_TRACKED_WRITES)
    w.porcelain.seal_build(model=True)
    prompts = [prompt for prompt, schema in stub.calls
               if schema.get("title") == "patternbuffer_classify_batch"]
    assert prompts
    assert not any(re.search(r"^\d+\. a:\d+ ", prompt, re.M) for prompt in prompts)
    w.close()


def test_s8_a_proposals_evidence_row_makes_no_model_call(world):
    """§8: the item-level same_as proposal's evidence row (subject `a:N`) is
    classified with no model call."""
    world.ingest_structured([{"entity": "person:bobby", "attribute": "name",
                              "value": "Bobby", "timeless": True,
                              "same_as": "person:bob"}], classify="defer")
    evidence = next(r for r in world.buffer.all_rows() if r.attribute == "evidence")
    calls = len(world.classifier._model.calls)
    world.classifier.classify(evidence)
    assert len(world.classifier._model.calls) == calls
    assert _verdict(world, evidence.id) == ("STATE", 0.5)


def test_s8_host_metadata_on_an_assertion_is_kept_without_a_model_call(world):
    """§8: `(a:4 · last_confirmed · 12.0)` makes no model call and
    `state("a:4", "last_confirmed")` still serves it; a META attribute on an
    assertion stays EVENT, and a host id shaped like the namespace
    (`a:artifact`) is still judged by the model."""
    target = _ann_calm(world)
    stub = world.classifier._model
    calls = len(stub.calls)
    rows = world.ingest_structured([
        {"entity": target, "attribute": "last_confirmed", "value": 12.0,
         "timeless": True},
        {"entity": target, "attribute": "source", "value": "doc:log", "timeless": True},
    ])
    assert len(stub.calls) == calls
    assert [_verdict(world, r.id) for r in rows] == [("STATE", 0.5), ("EVENT", 1.0)]
    assert world.porcelain.state(target, "last_confirmed")["fact"]["value"] == 12.0
    world.ingest_structured([{"entity": "a:artifact", "attribute": "glow",
                              "value": "faint", "valid_from": 1.0}])
    assert len(stub.calls) == calls + 1


def test_s8_rules_mode_sidecar_is_byte_identical(tmp_path):
    """§8: a rules-mode world's durability sidecar is byte-identical to the
    one recorded before this spec (re-baselined for READ-SURFACE-V1 §7: the
    physics row's CONSTITUTIVE verdict at a:3, every later id shifted by one)."""
    _, sidecar = build_corpus(tmp_path)
    assert sidecar == CORPUS_SIDECAR.read_text()


# ------------------------------------------------ r2: review resolutions
#
# One test per r2 oracle (specs/GATE-AUTHORITY-V1.md, "r2: review
# resolutions"): pbr's RED on §1's alias-map order, its ruling on numeric
# strings, and the internal pre-review's findings F3-F6.

def test_r2_alias_map_order_is_builtins_then_marked_receipts_then_inverse_pops(tmp_path):
    """§1 (r2, pbr RED): the rebuild runs built-ins, then the replayed receipts
    that carry the gate's mark, then pops the inverse keys. A host override
    outranks its built-in after reopen; a receipt without the mark displaces
    no built-in; an old forward receipt for an inverse relation is popped."""
    path = tmp_path / "order.world"
    w = World(path, world_id="w:order", model=StubModel(fallback=rule_classifier_fallback()))
    w.ingestor.add_attribute_alias("type", "genre")
    w.ingest_structured([{"entity": "doc:book", "attribute": "type", "value": "novel",
                          "valid_from": 1.0}], classify="rules")
    role = w.ingestor._role
    # Rows no item can write any more, appended below the gate to stand for an
    # old log: two receipts without the gate's mark, one old forward receipt.
    sigil = w.buffer.append(entity="obj:cup", attribute="allegiance", value="crown",
                            valid_from=1.0, status="stated", role=role)
    w.buffer.append(entity=sigil.id, attribute="canonicalized_from",
                    value="is_a->allegiance", status="stated", role=role)
    w.buffer.append(entity=sigil.id, attribute="canonicalized_from",
                    value="inside->fealty", status="inferred", role=role)
    held = w.buffer.append(entity="person:ann", attribute="held_by", value="obj:ring",
                           value_type="entity", valid_from=1.0, status="stated", role=role)
    w.buffer.append(entity=held.id, attribute="canonicalized_from",
                    value="holds->held_by", status="inferred", role=role)
    w.close()
    w = World(path, world_id="w:order", model=StubModel(fallback=rule_classifier_fallback()))
    aliases = w.ingestor._alias_map
    assert aliases["type"] == "genre"                       # receipts after built-ins
    assert aliases["is_a"] == "kind" and aliases["inside"] == "in"   # unmarked: ignored
    assert "holds" not in aliases and "wearing" not in aliases       # popped last
    w.close()


@pytest.mark.parametrize("given,stored", [
    ("0.9", 0.9), (" 0.25 ", 0.25), ("1", 1.0), (2 ** 70, float(2 ** 70))])
def test_r2_numeric_string_confidence_is_coerced(world, given, stored):
    """§4 (r2, pbr ruling a): an unambiguous numeric-string `confidence` is
    coerced before validation, exactly like a time coordinate, and so is an
    int past SQLite's 64-bit range."""
    r = _around(world, {"entity": "obj:x", "attribute": "hue", "value": "red",
                        "valid_from": 1.0, "confidence": given})
    assert r.skipped == []
    [row] = world.buffer.visible(entity="obj:x")
    assert row.confidence == stored and isinstance(row.confidence, float)


@pytest.mark.parametrize("bad", ["high", "nan", "inf", "-inf", "", True, [0.5]])
def test_r2_confidence_that_is_not_a_finite_number_is_invalid_field(world, bad):
    """§4 (r2, pbr ruling a): text, a non-finite numeric string, a bool or any
    other non-number is `invalid_field`, with the value as authored in
    `detail`."""
    r = _around(world, {"entity": "obj:x", "attribute": "hue", "value": "red",
                        "valid_from": 1.0, "confidence": bad})
    assert r.skipped == [{"entity": "obj:x", "attribute": "hue", "value": "red",
                          "reason": "invalid_field",
                          "detail": {"field": "confidence", "value": bad}}]
    assert world.buffer.visible(entity="obj:x") == []


def test_r2_times_and_confidence_follow_one_number_rule(world):
    """§4 (r2, pbr ruling a): one gate helper reads every number an item
    carries. For each value in a battery, the time path and the confidence
    path admit or refuse it together, store the same number, and receipt the
    value as authored."""
    battery = ["1660", " 7 ", "1e3", "-2.5", 3, 2.5, 2 ** 70, "spring", "inf", "nan",
               "", True, False, [1], {"$decimal": "1.5"}]
    for i, given in enumerate(battery):
        timed, rated = f"obj:t{i}", f"obj:c{i}"
        r = world.porcelain.ingest_structured([
            {"entity": timed, "attribute": "hue", "value": "red", "valid_from": given},
            {"entity": rated, "attribute": "hue", "value": "red", "valid_from": 1.0,
             "confidence": given},
        ], classify="rules")
        skips = {s["entity"]: s for s in r.skipped}
        assert (timed in skips) == (rated in skips), given
        if timed in skips:
            assert skips[timed]["reason"] == "invalid_valid_time"
            assert skips[rated]["reason"] == "invalid_field"
            assert skips[rated]["detail"] == {"field": "confidence",
                                              "value": skips[timed]["detail"]}
            assert skips[timed]["detail"] == ([1] if given == [1] else given)
        else:
            [t] = world.buffer.visible(entity=timed)
            [c] = world.buffer.visible(entity=rated)
            assert t.valid_from == c.confidence and type(t.valid_from) is type(c.confidence)


def test_r2_bool_flags_read_the_ints_0_and_1(world):
    """§4 (r2, pre-review F3): `timeless: 1` is timeless and `timeless: 0` is
    stamped by the cursor; `correction: 1` writes the proposal and
    `correction: 0` does not — as the base engine read them. Any other
    non-bool (2, 1.0, "1") is still `invalid_field`."""
    world.ingestor.cursor.advance(5.0)
    rows = world.ingest_structured([
        {"entity": "obj:a", "attribute": "hue", "value": "red", "timeless": 1},
        {"entity": "obj:b", "attribute": "hue", "value": "red", "timeless": 0},
        {"entity": "obj:c", "attribute": "hue", "value": "red", "valid_from": 1.0,
         "correction": 1},
        {"entity": "obj:d", "attribute": "hue", "value": "red", "valid_from": 1.0,
         "correction": 0},
    ], classify="rules")
    assert world.ingestor.last_skipped == []
    hue = {row.entity: row for row in rows if row.attribute == "hue"}
    assert {e: row.valid_from for e, row in hue.items()} == {
        "obj:a": None, "obj:b": 5.0, "obj:c": 1.0, "obj:d": 1.0}
    assert [row.entity for row in rows if row.attribute == "correction_proposal"] == [
        hue["obj:c"].id]
    for flag in ("timeless", "correction"):
        for bad in (2, 1.0, "1"):
            r = _around(world, {"entity": "obj:x", "attribute": "hue", "value": "red",
                                "valid_from": 1.0, flag: bad})
            assert r.skipped == [{"entity": "obj:x", "attribute": "hue", "value": "red",
                                  "reason": "invalid_field",
                                  "detail": {"field": flag, "value": bad}}]
    assert world.buffer.visible(entity="obj:x") == []


def test_r2_aliases_given_as_a_tuple_or_set_are_a_list(world):
    """§4 (r2, pre-review F3): `aliases` given as a tuple is its members in
    order; a set is its members in sorted order, so the log never depends on
    hash order. A generated item carrying a non-empty set still raises (§3)."""
    r = _around(world, {"entity": "obj:vault", "attribute": "kind", "value": "vault",
                        "timeless": True, "aliases": ("the vault", "the strongroom")})
    assert r.skipped == []
    assert _aliases_of(world, "obj:vault") == ["the vault", "the strongroom"]
    r = _around(world, {"entity": "obj:box", "attribute": "kind", "value": "box",
                        "timeless": True,
                        "aliases": {"the crate", "a box", "the old chest"}})
    assert r.skipped == []
    assert _aliases_of(world, "obj:box") == ["a box", "the crate", "the old chest"]
    head = world.buffer.head()
    with pytest.raises(RoleViolation, match="aliases"):
        world.ingest_structured([
            {"entity": "arc:main", "attribute": "beat", "value": "rising",
             "status": "generated", "frame": "plot:arc1", "valid_from": 1.0,
             "aliases": {"the shadow"}}], classify="rules")
    assert world.buffer.head() == head


def test_r2_the_status_grant_is_checked_before_the_frame(world):
    """§3 (r2, pre-review F4): authority first — `{status: "bogus", frame: ""}`
    raises RoleViolation, as on the base engine, before the frame's shape is
    judged. With a granted status the same frame is `malformed_item`, and so
    is a malformed frame on a generated item (letter 029 has no frame to
    judge)."""
    head = world.buffer.head()
    item = {"entity": "obj:x", "attribute": "hue", "value": "red", "valid_from": 1.0}
    for frame in ("", 5):
        with pytest.raises(RoleViolation, match="bogus"):
            world.ingest_structured([{**item, "status": "bogus", "frame": frame}],
                                    classify="rules")
    assert world.buffer.head() == head
    for status, frame in (("stated", ""), ("generated", ""), ("generated", 5)):
        r = _around(world, {**item, "status": status, "frame": frame})
        assert r.skipped == [{**{k: item[k] for k in ("entity", "attribute", "value")},
                              "reason": "malformed_item",
                              "detail": {"field": "frame", "value": frame}}]
    assert world.buffer.visible(entity="obj:x") == []


@pytest.mark.parametrize("attribute,value", [
    ("learned_at_wallclock", 9e9), ("source_valid_from", 612),
    ("correction_proposal", True)])
def test_r2_the_gates_own_side_rows_are_refused_as_items(tmp_path, attribute, value):
    """§1 (r2, pre-review F5): the tracking stamp, the cursor-authoritative
    demotion and the correction proposal are written only by the gate as side
    rows; no host path writes them, and the extractor copies engine rows from
    its context. An item carrying one is skipped `mechanism_attribute` on
    every path — `ingest_structured`, the model path, `commit_set` — and
    nothing is written."""
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "side.world", world_id="w:side", model=stub)
    target = _ann_calm(w)
    head = w.buffer.head()
    item = {"entity": target, "attribute": attribute, "value": value, "timeless": True}
    r = w.porcelain.ingest_structured([item], classify="rules")
    assert r.skipped == [{"entity": target, "attribute": attribute, "value": value,
                          "reason": "mechanism_attribute"}]
    stub.enqueue({"items": [item]})
    assert w.ingest("Ann's row, copied from the context.", classify="rules") == []
    assert [s.reason for s in w.ingestor.last_skipped] == ["mechanism_attribute"]
    with pytest.raises(AtomicAbort) as ei:
        w.commit_set([{"op": "assert", "item": item}])
    assert ei.value.cause == "gate_skip"
    assert w.buffer.head() == head
    w.close()


class _Clock:
    """An injected wall clock the test advances by hand."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


_DAY = 86400.0


def test_r2_a_copied_tracking_stamp_never_refreshes_confidence(tmp_path):
    """§1 (r2, pre-review F5): `learned_at_wallclock` is the stamp confidence()
    recency reads. An item copying one is skipped, so a stale fact stays
    stale; the buffer refuses a stamp without the gate's mark (`observed`);
    and a stamp already in a log under any other status confirms nothing."""
    clock = _Clock(0.0)
    w = World(tmp_path / "stamp.world", world_id="w:stamp",
              model=StubModel(fallback=rule_classifier_fallback()),
              policy="observe_or_unknown", clock=clock)
    rows = w.ingest_structured([
        {"entity": "attr:__world__", "attribute": "decay_halflife_seconds",
         "value": _DAY, "timeless": True},
        {"entity": "obj:box", "attribute": "state", "value": "sealed",
         "valid_from": 1.0, "status": "observed"},
    ], classify="rules")
    [state] = [row for row in rows if row.attribute == "state"]
    stale = w.confidence("obj:box", "state", now=2 * _DAY)
    assert stale["last_confirmed_at_wallclock"] == 0.0
    assert abs(stale["recency"] - 0.25) < 1e-9
    clock.t = 2 * _DAY
    r = w.porcelain.ingest_structured([
        {"entity": state.id, "attribute": "learned_at_wallclock", "value": 2 * _DAY,
         "timeless": True, "status": "observed"}], classify="rules")
    assert _reasons(r) == ["mechanism_attribute"]
    assert w.confidence("obj:box", "state", now=2 * _DAY) == stale
    with pytest.raises(RoleViolation):
        w.buffer.append(entity=state.id, attribute="learned_at_wallclock",
                        value=2 * _DAY, status="stated", role=w.ingestor._role)
    w.close()
    log = [
        _dump_row(1, "attr:__world__", "decay_halflife_seconds", _DAY),
        _dump_row(2, "obj:box", "state", "sealed", status="observed", valid_from=1.0),
        _dump_row(3, "a:2", "learned_at_wallclock", 0.0, status="observed"),
        _dump_row(4, "a:2", "learned_at_wallclock", 2 * _DAY),   # not `observed`
    ]
    path = tmp_path / "forged_stamp.world"
    build(_jsonl(log), path).close()
    w = World(path, world_id="w:forged", model=StubModel(fallback=rule_classifier_fallback()),
              policy="observe_or_unknown", clock=_Clock(2 * _DAY))
    c = w.confidence("obj:box", "state", now=2 * _DAY)
    assert c["last_confirmed_at_wallclock"] == 0.0
    assert abs(c["recency"] - 0.25) < 1e-9
    w.close()


def test_r2_an_item_declaring_a_family_is_judged_in_that_family(tmp_path):
    """§7 (r2, pre-review F6): steps 8 and 9 judge a new attribute's relation
    family as the item's own first-use declaration will leave it. An item
    declaring `relation_family: containment` (or lateral) with an id-shaped
    typo is `malformed_id`, and with a self-edge the per-edge skip, with
    nothing written — no declaration either. The same holds when the host's
    `attribute_default` supplies the family, and the callback still declares
    the attribute for the next good item."""
    def default(attribute: str):
        return {"relation_family": "containment"} if attribute == "lodged_in" else None

    w = World(tmp_path / "fam.world", world_id="w:fam", attribute_default=default,
              model=StubModel(fallback=rule_classifier_fallback()))
    head = w.buffer.head()
    r = w.porcelain.ingest_structured([
        {"entity": "obj:key", "attribute": "stowed_in", "value": "Place:Cellar",
         "relation_family": "containment"},
        {"entity": "obj:key", "attribute": "tucked_in", "value": "obj:key",
         "relation_family": "containment"},
        {"entity": "place:hall", "attribute": "links_to", "value": "Place:Yard",
         "relation_family": "lateral"},
        {"entity": "place:hall", "attribute": "opens_on", "value": "place:hall",
         "relation_family": "lateral"},
        {"entity": "obj:key", "attribute": "lodged_in", "value": "Place:Cellar"},
        {"entity": "obj:key", "attribute": "lodged_in", "value": "obj:key"},
    ], classify="rules")
    reasons = _reasons(r)
    assert reasons[0] == "malformed_id" and reasons[2] == "malformed_id"
    assert reasons[4] == "malformed_id"
    assert reasons[1].startswith("cycle-forming containment edge: ")
    assert reasons[3].startswith("lateral self-loop: ")
    assert reasons[5].startswith("cycle-forming containment edge: ")
    assert r.rows == [] and w.buffer.head() == head
    for attribute in ("stowed_in", "tucked_in", "links_to", "opens_on", "lodged_in"):
        assert not w.semantics.is_declared(attribute)
    w.ingest_structured([
        {"entity": "place:cellar", "attribute": "kind", "value": "cellar",
         "timeless": True},
        {"entity": "obj:key", "attribute": "lodged_in", "value": "place:cellar",
         "valid_from": 1.0}], classify="rules")
    assert w.semantics.is_containment("lodged_in")
    assert w.locate("obj:key") == ["place:cellar"]
    w.close()


@pytest.mark.parametrize("absent", ["", False])
def test_r2_an_empty_or_false_value_type_is_inferred(world, absent):
    """§4 (r2, pre-review F6): `value_type` given as `""` or `False` is absent
    and the type is inferred, as the base engine read it — an id value is an
    entity (so `in` locates), text a literal, and an id-shaped typo is still
    caught by §7. `value_type: 0` is still `invalid_field`."""
    r = _around(world, {"entity": "person:ann", "attribute": "in",
                        "value": "place:hall", "valid_from": 1.0, "value_type": absent})
    assert r.skipped == [] and world.locate("person:ann") == ["place:hall"]
    r = _around(world, {"entity": "person:ann", "attribute": "mood", "value": "calm",
                        "valid_from": 1.0, "value_type": absent})
    [mood] = world.buffer.visible(entity="person:ann", attribute="mood")
    assert r.skipped == [] and mood.value_type == "literal"
    r = _around(world, {"entity": "person:ann", "attribute": "in",
                        "value": "Place:Hall", "valid_from": 2.0, "value_type": absent})
    assert _reasons(r) == ["malformed_id"]
    r = _around(world, {"entity": "person:ann", "attribute": "hue", "value": "red",
                        "valid_from": 1.0, "value_type": 0})
    assert r.skipped[0]["detail"] == {"field": "value_type", "value": 0}
    assert world.locate("person:ann") == ["place:hall"]
