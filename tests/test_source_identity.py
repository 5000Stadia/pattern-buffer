"""SOURCE-IDENTITY-V1: a source class is a source, not a category.

`_source_class` collapsed every `doc:` source to the bare literal
`"document"`, discarding which document, while speakers kept identity.
That made two distinct documents ONE supersession class, so a
cross-document disagreement silently last-write-wins instead of raising
whitepaper §7.2's truth-maintenance flag — the whitepaper's own
supply-house example — and N independently agreeing documents scored
zero corroboration.

Oracles are numbered as in specs/SOURCE-IDENTITY-V1.md §4.
"""

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    w = World(
        tmp_path / "si.world",
        world_id="w:si",
        model=StubModel(fallback=rule_classifier_fallback()),
    )
    yield w
    w.close()


def _sourced(world, entity, attribute, rows, *, status="observed"):
    """Assert `rows` as (value, valid_from, source) and attach each source.

    `source=None` leaves the row undeclared-origin. Returns the ids of the
    payload rows in the order given.
    """
    written = world.ingest_structured([
        {"entity": entity, "attribute": attribute, "value": value,
         "valid_from": vf, "status": status}
        for value, vf, _ in rows
    ])
    ids = [r.id for r in written if getattr(r, "attribute", None) == attribute]
    metas = [
        {"entity": ids[i], "attribute": "source", "value": src,
         "valid_from": 1.0, "status": "stated"}
        for i, (_, _, src) in enumerate(rows) if src is not None
    ]
    if metas:
        world.ingest_structured(metas)
    return ids


# --------------------------------------------------------------- fold / §7.2

def test_o1_distinct_documents_disagreeing_flag(world):
    """O1 — §7.2's own worked example. Two distinct documents disagreeing are
    distinct source classes: flag + ask, and serve EARLIEST-asserted rather
    than silently last-write-wins."""
    ids = _sourced(world, "order:8841", "count", [
        ("20", 1.0, "doc:supply_house"),
        ("12", 2.0, "doc:invoice"),
    ])
    fold = world.state("order:8841", "count")
    assert fold.conflicted is True
    assert set(fold.conflicting) == set(ids)
    assert fold.winner.value == "20", "must not last-write-wins across documents"


def test_o2_same_document_correcting_itself_supersedes(world):
    """O2 — one document correcting itself stays one class: supersede, no flag."""
    _sourced(world, "order:8841", "count", [
        ("20", 1.0, "doc:invoice"),
        ("12", 2.0, "doc:invoice"),
    ])
    fold = world.state("order:8841", "count")
    assert fold.conflicted is False
    assert fold.winner.value == "12"


def test_o3_document_and_speaker_disagreeing_flag(world):
    """O3 — distinct classes before and after the change."""
    _sourced(world, "order:8841", "count", [
        ("20", 1.0, "doc:invoice"),
        ("12", 2.0, "person:ana"),
    ])
    assert world.state("order:8841", "count").conflicted is True


def test_o4_distinct_documents_agreeing_do_not_flag(world):
    """O4 — agreement across classes is corroboration, never conflict."""
    _sourced(world, "order:8841", "count", [
        ("20", 1.0, "doc:supply_house"),
        ("20", 2.0, "doc:invoice"),
    ])
    fold = world.state("order:8841", "count")
    assert fold.conflicted is False
    assert fold.winner.value == "20"


def test_o5_containment_across_documents_stays_time_sequential(world):
    """O5 — movement is time-sequential: the latest-valid move wins across
    source classes; only a same-valid_from disagreement flags."""
    _sourced(world, "person:edda", "in", [
        ("place:hall", 1.0, "doc:logbook"),
        ("place:yard", 2.0, "doc:roster"),
    ])
    fold = world.state("person:edda", "in")
    assert fold.conflicted is False
    assert fold.winner.value == "place:yard"


def test_o5b_containment_same_valid_time_across_documents_flags(world):
    """O5b — the genuine simultaneous contradiction still flags."""
    _sourced(world, "person:edda", "in", [
        ("place:hall", 1.0, "doc:logbook"),
        ("place:yard", 1.0, "doc:roster"),
    ])
    assert world.state("person:edda", "in").conflicted is True


# ------------------------------------------------------------- corroboration

def test_o6_two_distinct_documents_corroborate(world):
    """O6 — the reported defect: independent documents earned nothing."""
    _sourced(world, "sensor:tank", "level", [
        ("high", 1.0, "doc:manual"),
        ("high", 2.0, "doc:logbook"),
    ])
    assert world.confidence("sensor:tank", "level")["corroboration"] == 1


def test_o7_three_distinct_documents_corroborate(world):
    _sourced(world, "sensor:tank", "level", [
        ("high", 1.0, "doc:a"),
        ("high", 2.0, "doc:b"),
        ("high", 3.0, "doc:c"),
    ])
    assert world.confidence("sensor:tank", "level")["corroboration"] == 2


def test_o8_document_echo_does_not_corroborate(world):
    """O8 — one document quoted twice is still one source. Must stay 0."""
    _sourced(world, "sensor:tank", "level", [
        ("high", 1.0, "doc:manual"),
        ("high", 2.0, "doc:manual"),
    ])
    assert world.confidence("sensor:tank", "level")["corroboration"] == 0


def test_o9_speaker_controls_unchanged(world, tmp_path):
    """O9 — speakers already behaved correctly; they must not move."""
    _sourced(world, "sensor:tank", "level", [
        ("high", 1.0, "person:ana"),
        ("high", 2.0, "person:bo"),
    ])
    assert world.confidence("sensor:tank", "level")["corroboration"] == 1

    other = World(tmp_path / "si2.world", world_id="w:si2",
                  model=StubModel(fallback=rule_classifier_fallback()))
    try:
        _sourced(other, "sensor:tank", "level", [
            ("high", 1.0, "person:ana"),
            ("high", 2.0, "person:ana"),
        ])
        assert other.confidence("sensor:tank", "level")["corroboration"] == 0
    finally:
        other.close()


def test_o10_multiframe_union_counts_the_same_identities(world):
    """O10 — the frame-union corroboration path reads the same classes, and a
    deduped single-frame list still reduces to the str path byte-for-byte."""
    written = world.ingest_structured([
        {"entity": "obj:ring", "attribute": "bearer", "value": "frodo",
         "valid_from": 1.0, "status": "observed", "frame": "canon"},
        {"entity": "obj:ring", "attribute": "bearer", "value": "frodo",
         "valid_from": 2.0, "status": "observed", "frame": "knows:olwe"},
    ])
    ids = [r.id for r in written if getattr(r, "attribute", None) == "bearer"]
    world.ingest_structured([
        {"entity": ids[0], "attribute": "source", "value": "doc:a",
         "valid_from": 1.0, "status": "stated"},
        {"entity": ids[1], "attribute": "source", "value": "doc:b",
         "valid_from": 1.0, "status": "stated"},
    ])
    union = world.confidence("obj:ring", "bearer", frame=["canon", "knows:olwe"])
    assert union["corroboration"] == 1

    as_list = world.confidence("obj:ring", "bearer", frame=["canon"])
    as_str = world.confidence("obj:ring", "bearer", frame="canon")
    assert as_list == as_str


# --------------------------------------------------------------- determinism

@pytest.mark.parametrize("order", [("doc:d", "person:p"), ("person:p", "doc:d")])
def test_o11_document_outranks_speaker_either_order(tmp_path, order):
    """O11 — a row carrying both kinds classifies by the document, whichever
    order visible() returns the metas in."""
    w = World(tmp_path / f"o11_{order[0][:3]}.world", world_id="w:o11",
              model=StubModel(fallback=rule_classifier_fallback()))
    try:
        written = w.ingest_structured([
            {"entity": "order:1", "attribute": "count", "value": "20",
             "valid_from": 1.0, "status": "observed"},
        ])
        rid = [r.id for r in written if getattr(r, "attribute", None) == "count"][0]
        w.ingest_structured([
            {"entity": rid, "attribute": "source", "value": order[0],
             "valid_from": 1.0, "status": "stated"},
            {"entity": rid, "attribute": "source", "value": order[1],
             "valid_from": 1.0, "status": "stated"},
        ])
        row = w.indexes._buffer.get(rid)
        assert w.indexes._source_class(row, None) == "document:doc:d"
    finally:
        w.close()


@pytest.mark.parametrize("order", [("doc:b", "doc:a"), ("doc:a", "doc:b")])
def test_o12_multiple_documents_form_a_composite_class(tmp_path, order):
    """O12 (r2) — a multi-source row's class is the COMPOSITE of every source,
    not one member selected by spelling. r1.1 used min(), which made
    evidentiary identity depend on label sort order (pbr F2/F3)."""
    w = World(tmp_path / f"o12_{order[0][-1]}.world", world_id="w:o12",
              model=StubModel(fallback=rule_classifier_fallback()))
    try:
        written = w.ingest_structured([
            {"entity": "order:1", "attribute": "count", "value": "20",
             "valid_from": 1.0, "status": "observed"},
        ])
        rid = [r.id for r in written if getattr(r, "attribute", None) == "count"][0]
        w.ingest_structured([
            {"entity": rid, "attribute": "source", "value": order[0],
             "valid_from": 1.0, "status": "stated"},
            {"entity": rid, "attribute": "source", "value": order[1],
             "valid_from": 1.0, "status": "stated"},
        ])
        row = w.indexes._buffer.get(rid)
        assert w.indexes._source_class(row, None) == "document:doc:a|doc:b"
    finally:
        w.close()


@pytest.mark.parametrize("order", [("person:b", "person:a"), ("person:a", "person:b")])
def test_o12a_multiple_speakers_form_a_composite_class(tmp_path, order):
    """O12a (r2) — the same composite rule, both kinds."""
    w = World(tmp_path / f"o12a_{order[0][-1]}.world", world_id="w:o12a",
              model=StubModel(fallback=rule_classifier_fallback()))
    try:
        written = w.ingest_structured([
            {"entity": "order:1", "attribute": "count", "value": "20",
             "valid_from": 1.0, "status": "observed"},
        ])
        rid = [r.id for r in written if getattr(r, "attribute", None) == "count"][0]
        w.ingest_structured([
            {"entity": rid, "attribute": "source", "value": order[0],
             "valid_from": 1.0, "status": "stated"},
            {"entity": rid, "attribute": "source", "value": order[1],
             "valid_from": 1.0, "status": "stated"},
        ])
        row = w.indexes._buffer.get(rid)
        assert w.indexes._source_class(row, None) == "speaker:person:a|person:b"
    finally:
        w.close()


# ------------------------------------------------------ §6 boundary is pinned

def test_undeclared_origin_pool_is_unchanged(world):
    """§6 — N independent undeclared-origin rows still score 0. This is the
    documented boundary of this spec, NOT a fix: it is recorded as a founder
    crossroads. The test exists so the boundary cannot move silently."""
    _sourced(world, "sensor:tank", "level", [
        ("high", 1.0, None),
        ("high", 2.0, None),
        ("high", 3.0, None),
    ])
    assert world.confidence("sensor:tank", "level")["corroboration"] == 0


# ------------------------------------------------ r2: pbr's three RED findings

def test_o14_source_ids_canonicalize_through_identity_closure(world):
    """O14 (r2, pbr F1/F2) — raw source strings are not source IDENTITIES.
    Two aliases of one document, sourced BEFORE the merge, must stop
    corroborating once the closure joins them: a single logical source cannot
    self-corroborate."""
    _sourced(world, "o:1", "k", [
        ("v", 1.0, "doc:manual"),
        ("v", 2.0, "doc:manual_alias"),
    ])
    assert world.confidence("o:1", "k")["corroboration"] == 1, "distinct before merge"

    world.ingest_structured([
        {"entity": "doc:manual_alias", "attribute": "same_as", "value": "doc:manual",
         "valid_from": 1.0, "status": "stated"},
    ])
    assert world.confidence("o:1", "k")["corroboration"] == 0, (
        "after the merge both rows attest ONE logical document"
    )


@pytest.mark.parametrize("shared", ["doc:a", "doc:z"])
def test_o15_outcome_is_invariant_to_source_label_spelling(tmp_path, shared):
    """O15 (r2, pbr F2/F3) — identical provenance topology must give an
    identical outcome whether the shared source sorts first or last.

    Under r1.1's `min()`, renaming the shared id flipped two rows from silent
    same-class supersession to cross-class conflict — spelling decided which
    value was SERVED.
    """
    w = World(tmp_path / f"o15_{shared[-1]}.world", world_id="w:o15",
              model=StubModel(fallback=rule_classifier_fallback()))
    try:
        written = w.ingest_structured([
            {"entity": "o:1", "attribute": "k", "value": "old", "valid_from": 1.0,
             "status": "observed"},
            {"entity": "o:1", "attribute": "k", "value": "new", "valid_from": 2.0,
             "status": "observed"},
        ])
        ids = [r.id for r in written if getattr(r, "attribute", None) == "k"]
        w.ingest_structured([
            {"entity": ids[0], "attribute": "source", "value": "doc:a",
             "valid_from": 1.0, "status": "stated"},
            {"entity": ids[0], "attribute": "source", "value": "doc:z",
             "valid_from": 1.0, "status": "stated"},
            {"entity": ids[1], "attribute": "source", "value": shared,
             "valid_from": 1.0, "status": "stated"},
        ])
        fold = w.state("o:1", "k")
        # The invariant is that BOTH spellings agree — pinned to the composite
        # answer: {a,z} and {shared} are different attester sets, so cross-source.
        assert fold.conflicted is True
        assert fold.winner.value == "old"
    finally:
        w.close()


def test_o16_conflicting_names_the_actually_incompatible_rows(world):
    """O16 (r2, pbr F3/F1) — with a={gte:10}, b=12, c=13 the fold serves b and
    the real incompatibility is b vs c; a is satisfied by both exact values.
    r1.1 anchored the tuple to the incumbent and reported {a,c} — a pair that
    AGREES — and TruthMaintenance.scan() persisted the same wrong pair."""
    ids = _sourced(world, "o:1", "k", [
        ({"gte": 10}, 5.0, "doc:a"),
        (12,          5.0, "doc:b"),
        (13,          5.0, "doc:c"),
    ])
    a, b, c = ids
    fold = world.state("o:1", "k")
    assert fold.conflicted is True
    assert fold.winner.value == 12
    assert set(fold.conflicting) == {b, c}, "the incompatible pair, not the incumbent"
    assert a not in fold.conflicting, "{gte:10} agrees with both 12 and 13"
