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
from pathlib import Path

import pytest

from patternbuffer import AtomicAbort, World
from patternbuffer.buffer import PatternBuffer
from patternbuffer.dump import build, dump
from patternbuffer.ingest import SKIP_REASONS
from patternbuffer.roles import RoleViolation, _make_engine_roles
from patternbuffer.testing import StubModel, rule_classifier_fallback

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
    byte, as the engine did before this spec."""
    log, _ = build_corpus(tmp_path)
    assert log == CORPUS_LOG.read_text()


# ------------------------------------------------- §1 mechanism attributes

def _ann_calm(w: World) -> str:
    """Ann's mood: the first row after the two charter rows, so `a:3`."""
    [row] = w.ingest_structured([{"entity": "person:ann", "attribute": "mood",
                                  "value": "calm", "valid_from": 1.0}], classify="rules")
    assert row.id == "a:3"
    return row.id


def test_s1_forged_retraction_item_is_skipped(tmp_path):
    """§1: `(a:3 · retracts · "forged")` is skipped `mechanism_attribute` on
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
    """§1: `(a:3 · canonicalized_from · "allegiance->in")` is skipped, and
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
