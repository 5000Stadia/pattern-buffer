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

from patternbuffer import World
from patternbuffer.dump import dump
from patternbuffer.ingest import SKIP_REASONS
from patternbuffer.testing import StubModel

FIXTURES = Path(__file__).parent / "fixtures"
CORPUS_LOG = FIXTURES / "gate_authority_corpus.jsonl"
CORPUS_SIDECAR = FIXTURES / "gate_authority_corpus_sidecar.jsonl"


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
