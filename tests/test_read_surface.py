"""READ-SURFACE-V1 (batch E of the October self-audit): oracle tests from the spec.

Written from specs/READ-SURFACE-V1.md alone (plus the public porcelain / ADOPTION
surface) as an independent oracle suite: one test per stated oracle, by section,
plus the byte-identical pins and the three defaults recorded at the spec's top.
§10 (events() from one reader) is deferred by the spec and is not tested here.

Where the spec leaves a reading open, the test takes the best reading and says
so in a ``# AMBIGUOUS:`` comment for pbr / the implementer to settle.

Everything goes through public host surfaces: ``World(...)``, ``world.porcelain``
and the MCP module's registry/dispatch. A few §1/§7 oracles are stated in terms
of the classifier sidecar (``world.classifier``), the log (``world.buffer``) or
``dump``/``build``; those are read through the World's public attributes.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import pytest

import patternbuffer
from patternbuffer import AtomicAbort, World
from patternbuffer.dump import build, dump
from patternbuffer.model import TASK_ASK_PLAN, TASK_CLASSIFY, TASK_CLASSIFY_BATCH, TASK_REFER
from patternbuffer.testing import StubModel, rule_classifier_fallback

ASK_PLAN = "patternbuffer_ask_plan"
assert TASK_ASK_PLAN == ASK_PLAN

INVENT = "invent_under_canon"
OBSERVE = "observe_or_unknown"
ALICE = "knows:person:alice"

# The order of a Fact's keys today; READ-SURFACE-V1 §4 appends `value_type`.
FACT_KEYS_TODAY = ["entity", "attribute", "value", "valid", "provenance",
                   "divergent", "b_value"]


# ------------------------------------------------------------------ helpers


class ScriptedModel:
    """A StubModel whose fallback keys off the task schema's `title`:
    ask plans and tier-2 refer verdicts are scripted per task; classification
    goes to the deterministic rule classifier."""

    def __init__(self) -> None:
        self.plans: list[dict] = []
        self.refer_verdicts: list[dict] = []
        self._rule = rule_classifier_fallback()
        self.stub = StubModel(fallback=self._fallback)

    def _fallback(self, prompt: str, schema: dict[str, Any]) -> Any:
        title = schema.get("title")
        if title == ASK_PLAN:
            return self.plans.pop(0)
        if title == TASK_REFER:
            if not self.refer_verdicts:
                raise AssertionError("unscripted refer tier-2 call")
            return self.refer_verdicts.pop(0)
        return self._rule(prompt, schema)

    def __call__(self, prompt: str, schema: dict[str, Any]) -> Any:
        return self.stub(prompt, schema)

    @property
    def calls(self) -> list[tuple[str, dict[str, Any]]]:
        return self.stub.calls

    def titles(self, since: int = 0) -> list[str | None]:
        return [s.get("title") for _, s in self.stub.calls[since:]]

    def classify_calls(self, since: int = 0, mentioning: str | None = None) -> int:
        return sum(
            1 for p, s in self.stub.calls[since:]
            if s.get("title") in (TASK_CLASSIFY, TASK_CLASSIFY_BATCH)
            and (mentioning is None or mentioning in p)
        )


def _world(tmp_path: Path, name: str = "rs", **kw: Any) -> tuple[World, ScriptedModel]:
    model = kw.pop("model", None) or ScriptedModel()
    w = World(tmp_path / f"{name}.world", world_id=f"w:{name}", model=model, **kw)
    return w, model


@pytest.fixture
def wm(tmp_path):
    w, m = _world(tmp_path)
    yield w, m
    w.close()


def _row(w: World, entity: str, attribute: str, value: Any = None):
    rows = [r for r in w.buffer.all_rows()
            if r.entity == entity and r.attribute == attribute
            and (value is None or r.value == value)]
    assert rows, f"no row {entity} · {attribute} · {value!r}"
    return rows[-1]


def _verdict(w: World, row) -> tuple[str, float]:
    c = w.classifier.get(row.id)
    assert c is not None, f"{row.id} is unclassified"
    return c.durability, c.class_confidence


def _skip_reasons(receipt) -> list[str]:
    return [s["reason"] for s in receipt.skipped]


def _physics_rows(w: World) -> list:
    return [r for r in w.buffer.all_rows()
            if r.entity == "attr:__world__" and r.attribute == "resolution_policy"]


def _strip(obj: Any, keys: frozenset[str]) -> Any:
    if isinstance(obj, dict):
        return {k: _strip(v, keys) for k, v in obj.items() if k not in keys}
    if isinstance(obj, list):
        return [_strip(v, keys) for v in obj]
    return obj


def _norm(obj: Any) -> str:
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()
    return json.dumps(obj, sort_keys=True, default=str)


# ===================================================== the three defaults


def test_default_1_ask_binds_askers_own_words_first_and_learns_nothing(tmp_path):
    """READ-SURFACE-V1 default 1: `ask` tries the asker's own words first,
    deterministically, learning nothing."""
    w, m = _world(tmp_path, "d1")
    try:
        _seed_stash(w)
        head = w.buffer.head()
        m.plans.append({"refer_targets": ["the stash"],
                        "keys": [{"target_index": 0, "attribute": "state"}],
                        "wants_location": False, "wants_events": False})
        n = len(m.calls)
        a = w.porcelain.ask("is the stash locked?", frame=ALICE)
        assert [f["value"] for f in a.facts] == ["locked"]
        assert m.titles(n) == [ASK_PLAN]          # deterministic binding
        assert w.buffer.head() == head            # learns nothing
    finally:
        w.close()


def test_default_2_pre_spec_world_records_policy_on_first_explicit_open(tmp_path):
    """READ-SURFACE-V1 default 2: a world created before this change records its
    policy the first time it is opened with an explicit `policy=`."""
    path = _pre_spec_world(tmp_path)
    w = World(path, world_id="w:pre", policy=OBSERVE)
    try:
        rows = _physics_rows(w)
        assert [r.value for r in rows] == [OBSERVE]
    finally:
        w.close()


def test_default_3_fold_policy_move_is_removed(wm):
    """READ-SURFACE-V1 default 3: `fold_policy: move` is removed — a `move`
    declaration is skipped invalid_semantics_declaration."""
    w, _ = wm
    head = w.buffer.head()
    r = w.porcelain.ingest_structured([
        {"entity": "attr:stance_kind", "attribute": "fold_policy", "value": "move",
         "timeless": True},
    ])
    assert _skip_reasons(r) == ["invalid_semantics_declaration"]
    assert w.buffer.head() == head


# ===================================================== §1 the durability pin


def _pin(w: World, attribute: str, cls: Any, frame: str | None = None):
    return w.porcelain.ingest_structured([
        {"entity": f"attr:{attribute}", "attribute": "durability", "value": cls,
         "timeless": True},
    ])


def test_s1_o1a_manual_pin_makes_zero_model_calls(wm):
    """READ-SURFACE-V1 §1 O1a: a manual STATE pin, then a timeless data row
    classified inline: 0 model calls; data row STATE 1.0, the pin row EVENT."""
    w, m = wm
    n = len(m.calls)
    _pin(w, "arc_status", "STATE")
    w.porcelain.ingest_structured([
        {"entity": "arc:main", "attribute": "arc_status", "value": "open",
         "timeless": True},
    ])
    assert m.classify_calls(n) == 0
    assert _verdict(w, _row(w, "arc:main", "arc_status")) == ("STATE", 1.0)
    assert _verdict(w, _row(w, "attr:arc_status", "durability"))[0] == "EVENT"


def test_s1_o1b_attribute_default_pin_lands_before_first_row(tmp_path):
    """READ-SURFACE-V1 §1 O1b: attribute_default returns
    {"durability": "CONSTITUTIVE"} for `rung`; the declaration lands before the
    first `rung` row, which is CONSTITUTIVE with no model call."""
    w, m = _world(tmp_path, "o1b", attribute_default=lambda a: (
        {"durability": "CONSTITUTIVE"} if a == "rung" else None))
    try:
        n = len(m.calls)
        w.porcelain.ingest_structured([
            {"entity": "bell:tower", "attribute": "rung", "value": "thrice",
             "valid_from": 1.0},
        ])
        decl = _row(w, "attr:rung", "durability", "CONSTITUTIVE")
        data = _row(w, "bell:tower", "rung")
        assert decl.seq < data.seq
        assert _verdict(w, data)[0] == "CONSTITUTIVE"
        assert m.classify_calls(n, mentioning="rung") == 0
    finally:
        w.close()


def test_s1_o1c_pin_after_data_raises(wm):
    """READ-SURFACE-V1 §1 O1c: a `rung` row first, then the pin: ValueError,
    head unchanged (declare before data)."""
    w, _ = wm
    w.porcelain.ingest_structured([
        {"entity": "bell:tower", "attribute": "rung", "value": "once",
         "valid_from": 1.0},
    ])
    head = w.buffer.head()
    with pytest.raises(ValueError):
        _pin(w, "rung", "STATE")
    assert w.buffer.head() == head


@pytest.mark.parametrize("bad", ["EVENT", "state", 1])
def test_s1_o1d_invalid_pin_value_is_skipped(wm, bad):
    """READ-SURFACE-V1 §1 O1d: pin values "EVENT", "state" and 1 are each skipped
    invalid_semantics_declaration with nothing written."""
    w, _ = wm
    head = w.buffer.head()
    r = _pin(w, "arc_status", bad)
    assert _skip_reasons(r) == ["invalid_semantics_declaration"]
    assert w.buffer.head() == head


def test_s1_o1d_invalid_pin_from_attribute_default_skips_item_unchecked(tmp_path):
    """READ-SURFACE-V1 §1 O1d: an invalid pin from attribute_default skips the
    item, and the attribute is not marked checked (B §5) — the callback is
    consulted again on the next item."""
    seen: list[str] = []

    def default(attribute: str) -> dict | None:
        if attribute == "tone":
            seen.append(attribute)
            return {"durability": "EVENT"}
        return None

    w, _ = _world(tmp_path, "o1d", attribute_default=default)
    try:
        head = w.buffer.head()
        item = {"entity": "bell:tower", "attribute": "tone", "value": "low",
                "valid_from": 1.0}
        r1 = w.porcelain.ingest_structured([item])
        r2 = w.porcelain.ingest_structured([item])
        assert _skip_reasons(r1) == ["invalid_semantics_declaration"]
        assert _skip_reasons(r2) == ["invalid_semantics_declaration"]
        assert w.buffer.head() == head
        assert seen == ["tone", "tone"]
    finally:
        w.close()


def test_s1_o1e_pin_on_core_attribute_raises(wm):
    """READ-SURFACE-V1 §1 O1e: a pin on the inviolable core (`in`): ValueError."""
    w, _ = wm
    head = w.buffer.head()
    with pytest.raises(ValueError):
        _pin(w, "in", "STATE")
    assert w.buffer.head() == head


def test_s1_o1e_pin_on_guardrailed_attribute_is_skipped(wm):
    """READ-SURFACE-V1 §1 O1e: a pin on `alias` in a fresh world is skipped,
    conflicts_with "guardrail"."""
    w, _ = wm
    head = w.buffer.head()
    r = _pin(w, "alias", "STATE")
    assert _skip_reasons(r) == ["invalid_semantics_declaration"]
    assert r.skipped[0]["detail"]["conflicts_with"] == "guardrail"
    assert w.buffer.head() == head


def test_s1_o1e_pin_beside_structural_true_is_skipped(tmp_path):
    """READ-SURFACE-V1 §1 O1e: {"structural": true, "durability": "STATE"} from
    attribute_default: the item is skipped, conflicts_with "structural=true"."""
    w, _ = _world(tmp_path, "o1e", attribute_default=lambda a: (
        {"structural": True, "durability": "STATE"} if a == "gauge" else None))
    try:
        head = w.buffer.head()
        r = w.porcelain.ingest_structured([
            {"entity": "obj:meter", "attribute": "gauge", "value": "brass",
             "timeless": True},
        ])
        assert _skip_reasons(r) == ["invalid_semantics_declaration"]
        assert r.skipped[0]["detail"]["conflicts_with"] == "structural=true"
        assert w.buffer.head() == head
    finally:
        w.close()


def test_s1_o1f_event_subject_beats_pin(wm):
    """READ-SURFACE-V1 §1 O1f: `event:bell · arc_status · "rung"`, with
    arc_status pinned STATE, classifies EVENT (occurrence stays structural)."""
    w, _ = wm
    _pin(w, "arc_status", "STATE")
    w.porcelain.ingest_structured([
        {"entity": "event:bell", "attribute": "arc_status", "value": "rung",
         "valid_from": 2.0},
    ])
    assert _verdict(w, _row(w, "event:bell", "arc_status"))[0] == "EVENT"


def test_s1_o1g_pinned_attribute_is_never_promoted(wm):
    """READ-SURFACE-V1 §1 O1g: one pinned-STATE value at t=1, 2 and 3:
    promote_accruals() promotes 0 rows."""
    w, _ = wm
    _pin(w, "arc_status", "STATE")
    w.porcelain.ingest_structured([
        {"entity": "arc:main", "attribute": "arc_status", "value": "open",
         "valid_from": float(t)}
        for t in (1, 2, 3)
    ])
    assert w.classifier.promote_accruals() == 0


def test_s1_o1h_rebuild_reproduces_pinned_verdicts_without_model(wm):
    """READ-SURFACE-V1 §1 O1h: classifier.rebuild() gives identical verdicts
    with 0 model calls (for the pin and its data)."""
    w, m = wm
    _pin(w, "arc_status", "STATE")
    w.porcelain.ingest_structured([
        {"entity": "arc:main", "attribute": "arc_status", "value": "open",
         "timeless": True},
    ])
    rows = [_row(w, "attr:arc_status", "durability"), _row(w, "arc:main", "arc_status")]
    before = [_verdict(w, r) for r in rows]
    n = len(m.calls)
    w.classifier.rebuild()
    # AMBIGUOUS: "0 model calls" for a WHOLE-world rebuild cannot include the
    # charter rows (world:self · kind/stance), which no guardrail covers and
    # which World.__init__ sets by hand; this reads the oracle as "0 calls
    # about the pin and its data rows" and compares only their verdicts.
    assert m.classify_calls(n, mentioning="arc_status") == 0
    assert [_verdict(w, r) for r in rows] == before


def test_s1_o1i_domain_durability_attribute_is_plain_data(wm):
    """READ-SURFACE-V1 §1 O1i (byte-identical): `obj:sword · durability · 80`
    is a domain row: state(sword, "durability") is known 80, today and after."""
    w, _ = wm
    w.porcelain.ingest_structured([
        {"entity": "obj:sword", "attribute": "durability", "value": 80,
         "valid_from": 1.0},
    ])
    out = w.porcelain.state("obj:sword", "durability")
    assert out["status"] == "known" and out["fact"]["value"] == 80


# ===================================================== §2 last_write / move


def _declare(w: World, attribute: str, **decl: Any) -> None:
    for predicate, value in decl.items():
        r = w.porcelain.ingest_structured([
            {"entity": f"attr:{attribute}", "attribute": predicate, "value": value,
             "timeless": True},
        ])
        assert not r.skipped, r.skipped


def test_s2_o2a_last_write_same_stamp_serves_latest(wm):
    """READ-SURFACE-V1 §2 O2a: arc_phase declared last_write; "setup" then
    "climax" at one stamp (5.0): known "climax", no `conflicting`."""
    w, _ = wm
    _declare(w, "arc_phase", fold_policy="last_write")
    for v in ("setup", "climax"):
        w.porcelain.ingest_structured([
            {"entity": "arc:main", "attribute": "arc_phase", "value": v,
             "valid_from": 5.0},
        ])
    out = w.porcelain.state("arc:main", "arc_phase")
    assert out["status"] == "known"
    assert out["fact"]["value"] == "climax"
    assert "conflicting" not in out


def test_s2_o2b_last_write_timeless_serves_latest(wm):
    """READ-SURFACE-V1 §2 O2b: the same, timeless: known "b"."""
    w, _ = wm
    _declare(w, "arc_phase", fold_policy="last_write")
    for v in ("a", "b"):
        w.porcelain.ingest_structured([
            {"entity": "arc:main", "attribute": "arc_phase", "value": v,
             "timeless": True},
        ])
    out = w.porcelain.state("arc:main", "arc_phase")
    assert (out["status"], out["fact"]["value"]) == ("known", "b")


def test_s2_o2c_constitutive_pin_plus_last_write(wm):
    """READ-SURFACE-V1 §2 O2c: pinned CONSTITUTIVE plus last_write, timeless
    "one" then "two": known "two"."""
    w, _ = wm
    _declare(w, "arc_label", durability="CONSTITUTIVE", fold_policy="last_write")
    for v in ("one", "two"):
        w.porcelain.ingest_structured([
            {"entity": "arc:main", "attribute": "arc_label", "value": v,
             "timeless": True},
        ])
    out = w.porcelain.state("arc:main", "arc_label")
    assert (out["status"], out["fact"]["value"]) == ("known", "two")


def test_s2_o2d_last_write_cross_source_by_recency(wm):
    """READ-SURFACE-V1 §2 O2d: `posture` last_write; "sitting" at t=1 (doc:x),
    "standing" at t=2 (doc:y): known "standing", unconflicted; as_of=1.5 serves
    "sitting"."""
    w, _ = wm
    _declare(w, "posture", fold_policy="last_write")
    w.porcelain.ingest_structured([
        {"entity": "person:ann", "attribute": "posture", "value": "sitting",
         "valid_from": 1.0, "source_doc": "doc:x"},
        {"entity": "person:ann", "attribute": "posture", "value": "standing",
         "valid_from": 2.0, "source_doc": "doc:y"},
    ])
    out = w.porcelain.state("person:ann", "posture")
    assert (out["status"], out["fact"]["value"]) == ("known", "standing")
    assert "conflicting" not in out
    past = w.porcelain.state("person:ann", "posture", as_of=1.5)
    assert past["fact"]["value"] == "sitting"


def test_s2_o2e_last_write_keeps_evidence_rank(wm):
    """READ-SURFACE-V1 §2 O2e: stated "a" at t=1, then inferred "b" at t=2:
    "a" (a later inferred row never displaces a stated one)."""
    w, _ = wm
    _declare(w, "arc_phase", fold_policy="last_write")
    w.porcelain.ingest_structured([
        {"entity": "arc:main", "attribute": "arc_phase", "value": "a",
         "valid_from": 1.0, "status": "stated"},
        {"entity": "arc:main", "attribute": "arc_phase", "value": "b",
         "valid_from": 2.0, "status": "inferred"},
    ])
    out = w.porcelain.state("arc:main", "arc_phase")
    assert out["fact"]["value"] == "a"
    assert "conflicting" not in out


def test_s2_o2f_event_row_never_served_on_last_write(wm):
    """READ-SURFACE-V1 §2 O2f: an `event:`-subject row on a last_write attribute
    is never served."""
    w, _ = wm
    _declare(w, "arc_phase", fold_policy="last_write")
    w.porcelain.ingest_structured([
        {"entity": "event:bell", "attribute": "arc_phase", "value": "climax",
         "valid_from": 3.0},
    ])
    assert w.porcelain.state("event:bell", "arc_phase")["status"] == "unknown"


def test_s2_o2g_last_write_beside_set_valued_is_skipped(tmp_path):
    """READ-SURFACE-V1 §2 O2g: attribute_default returning {"arity":
    "set_valued", "fold_policy": "last_write"}: the item is skipped,
    conflicts_with "arity=set_valued"."""
    w, _ = _world(tmp_path, "o2g", attribute_default=lambda a: (
        {"arity": "set_valued", "fold_policy": "last_write"} if a == "allies" else None))
    try:
        head = w.buffer.head()
        r = w.porcelain.ingest_structured([
            {"entity": "person:bob", "attribute": "allies", "value": "person:x",
             "valid_from": 1.0},
        ])
        assert _skip_reasons(r) == ["invalid_semantics_declaration"]
        assert r.skipped[0]["detail"]["conflicts_with"] == "arity=set_valued"
        assert w.buffer.head() == head
    finally:
        w.close()


def test_s2_o2h_move_hint_is_skipped(wm):
    """READ-SURFACE-V1 §2 O2h: a `fold_policy: "move"` hint on an item is skipped
    invalid_semantics_declaration (B §5: the whole item, nothing written)."""
    w, _ = wm
    head = w.buffer.head()
    r = w.porcelain.ingest_structured([
        {"entity": "person:ann", "attribute": "posture", "value": "sitting",
         "valid_from": 1.0, "fold_policy": "move"},
    ])
    assert _skip_reasons(r) == ["invalid_semantics_declaration"]
    assert w.buffer.head() == head


def test_s2_o2i_undeclared_same_stamp_still_conflicts(wm):
    """READ-SURFACE-V1 §2 O2i (byte-identical): an undeclared attribute holding
    two values at one stamp is still conflicted."""
    w, _ = wm
    w.porcelain.ingest_structured([
        {"entity": "arc:main", "attribute": "arc_mood", "value": "grim",
         "valid_from": 5.0},
        {"entity": "arc:main", "attribute": "arc_mood", "value": "bright",
         "valid_from": 5.0},
    ])
    assert w.porcelain.state("arc:main", "arc_mood")["status"] == "conflicted"


# ===================================================== §3 canonical attributes


def _seed_ann(w: World) -> None:
    w.porcelain.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "person:ann", "attribute": "kind", "value": "person",
         "timeless": True, "aliases": ["ann"]},
        {"entity": "person:ann", "attribute": "in", "value": "place:hall",
         "valid_from": 1.0},
        {"entity": "obj:box", "attribute": "kind", "value": "box", "timeless": True},
    ])
    w.porcelain.ingest_structured([
        {"entity": "person:ann", "attribute": "in", "value": "place:hall",
         "valid_from": 1.0},
    ], frame="knows:person:bob")


def test_s3_canonical_attribute_verb(wm):
    """READ-SURFACE-V1 §3: canonical_attribute maps "Located In" → "in",
    "type" → "kind", "holds" → "holds", "Mood" → "mood", "in" → "in"."""
    w, _ = wm
    p = w.porcelain
    assert p.canonical_attribute("Located In") == "in"
    assert p.canonical_attribute("type") == "kind"
    assert p.canonical_attribute("holds") == "holds"
    assert p.canonical_attribute("Mood") == "mood"
    assert p.canonical_attribute("in") == "in"
    assert w.canonical_attribute("Located In") == "in"     # World delegates


def test_s3_state_reads_alias_spelling(wm):
    """READ-SURFACE-V1 §3: state(ann, "located_in") is known with the same
    payload as state(ann, "in"); the Fact echoes the stored name."""
    w, _ = wm
    _seed_ann(w)
    via_alias = w.porcelain.state("person:ann", "located_in")
    assert via_alias["status"] == "known"
    assert via_alias == w.porcelain.state("person:ann", "in")
    assert via_alias["fact"]["attribute"] == "in"
    assert w.porcelain.state("person:ann", "Located In") == via_alias


def test_s3_facts_attribute_filter_canonicalized(wm):
    """READ-SURFACE-V1 §3: facts("canon", attribute="located_in"): 0 rows → 1."""
    w, _ = wm
    _seed_ann(w)
    rows = w.porcelain.facts("canon", entity="person:ann", attribute="located_in")
    assert len(rows) == 1 and rows[0]["attribute"] == "in"


def test_s3_who_knows_alias_spelling(wm):
    """READ-SURFACE-V1 §3: who_knows(ann, "located_in") equals who_knows(ann, "in")."""
    w, _ = wm
    _seed_ann(w)
    expected = w.porcelain.who_knows("person:ann", "in")
    assert expected == ["knows:person:bob"]
    assert w.porcelain.who_knows("person:ann", "located_in") == expected


def test_s3_confidence_alias_spelling(wm):
    """READ-SURFACE-V1 §3: confidence(ann, "located_in")["value"]: None → "place:hall"."""
    w, _ = wm
    _seed_ann(w)
    assert w.porcelain.confidence("person:ann", "located_in")["value"] == "place:hall"


def test_s3_type_reads_kind(wm):
    """READ-SURFACE-V1 §3: state(box, "type") equals state(box, "kind")."""
    w, _ = wm
    _seed_ann(w)
    kind = w.porcelain.state("obj:box", "kind")
    assert kind["status"] == "known"
    assert w.porcelain.state("obj:box", "type") == kind


def test_s3_runtime_host_alias_reads_both_spellings(wm):
    """READ-SURFACE-V1 §3: after add_attribute_alias("allegiance", "loyal_to"),
    state, where and aggregate answer the same for either spelling."""
    w, _ = wm
    w.ingestor.add_attribute_alias("allegiance", "loyal_to")
    w.porcelain.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "person:cy", "attribute": "in", "value": "place:hall", "valid_from": 1.0},
        {"entity": "person:cy", "attribute": "allegiance", "value": 3, "valid_from": 1.0},
        {"entity": "person:di", "attribute": "in", "value": "place:hall", "valid_from": 1.0},
        {"entity": "person:di", "attribute": "loyal_to", "value": 4, "valid_from": 1.0},
    ])
    p = w.porcelain
    assert p.state("person:cy", "allegiance") == p.state("person:cy", "loyal_to")
    assert p.state("person:cy", "allegiance")["status"] == "known"
    assert p.where("allegiance", ">=", 0) == p.where("loyal_to", ">=", 0) \
        == ["person:cy", "person:di"]
    assert p.aggregate("place:hall", "allegiance", "sum") \
        == p.aggregate("place:hall", "loyal_to", "sum")
    assert p.aggregate("place:hall", "allegiance", "sum")["value"] == 7


def test_s3_ask_plan_key_canonicalized(wm):
    """READ-SURFACE-V1 §3: an `ask` plan key "located_in" serves the `in` fact."""
    w, m = wm
    _seed_ann(w)
    m.plans.append({"refer_targets": ["ann"],
                    "keys": [{"target_index": 0, "attribute": "located_in"}],
                    "wants_location": False, "wants_events": False})
    a = w.porcelain.ask("where is ann?")
    assert [(f["attribute"], f["value"]) for f in a.facts] == [("in", "place:hall")]


def test_s3_resolve_aspect_canonicalized(wm):
    """READ-SURFACE-V1 §3: resolve(e, "Contents") finds the `contents` thunk."""
    w, _ = wm
    w.porcelain.ingest_structured([
        {"entity": "obj:locker", "attribute": "kind", "value": "locker", "timeless": True},
        {"entity": "obj:locker", "attribute": "contents", "value": {"policy": "deny"},
         "value_type": "unresolved"},
    ])
    assert w.porcelain.resolve("obj:locker", "contents")["status"] == "denied"
    assert w.porcelain.resolve("obj:locker", "Contents")["status"] == "denied"


def test_s3_canonical_argument_is_byte_identical(wm):
    """READ-SURFACE-V1 §3 byte-identical: an argument that is already canonical
    maps to itself — the `in` read is unchanged."""
    w, _ = wm
    _seed_ann(w)
    out = w.porcelain.state("person:ann", "in")
    assert out["status"] == "known" and out["fact"]["value"] == "place:hall"
    assert w.porcelain.who_knows("person:ann", "in") == ["knows:person:bob"]


# ===================================================== §4 state() whole key


def _seed_tin(w: World) -> None:
    _declare(w, "contains", arity="set_valued")
    w.porcelain.ingest_structured([
        {"entity": "obj:tin", "attribute": "kind", "value": "tin", "timeless": True,
         "aliases": ["the tin"]},
    ] + [
        {"entity": "obj:tin", "attribute": "contains", "value": f"obj:cig_{i}",
         "value_type": "entity", "valid_from": float(i)}
        for i in (1, 2, 3)
    ])


def _seed_split_p(w: World) -> None:
    w.porcelain.ingest_structured([
        {"entity": "person:p", "attribute": "kind", "value": "person", "timeless": True,
         "aliases": ["p"]},
        {"entity": "person:p", "attribute": "in", "value": "place:a", "valid_from": 3.0},
        {"entity": "person:p", "attribute": "in", "value": "place:b", "valid_from": 3.0},
    ])


def _seed_placeholder(w: World) -> None:
    w.porcelain.ingest_structured([
        {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True,
         "aliases": ["the study"]},
        {"entity": "place:study", "attribute": "description",
         "value": {"policy": INVENT}, "value_type": "unresolved"},
    ])


def test_s4_o4a_set_valued_key_serves_values(wm):
    """READ-SURFACE-V1 §4 O4a: a set-valued `contains` with three cigarettes:
    `values` holds cig_1..cig_3 in member order; `fact` is still cig_3."""
    w, _ = wm
    _seed_tin(w)
    out = w.porcelain.state("obj:tin", "contains")
    assert out["status"] == "known"
    assert out["fact"]["value"] == "obj:cig_3"
    assert [f["value"] for f in out["values"]] == ["obj:cig_1", "obj:cig_2", "obj:cig_3"]
    json.dumps(out)


def test_s4_o4b_conflicting_facts(wm):
    """READ-SURFACE-V1 §4 O4b: p in place:a and place:b at one stamp:
    `conflicting_facts`, one Fact per id in `conflicting`'s order."""
    w, _ = wm
    _seed_split_p(w)
    out = w.porcelain.state("person:p", "in")
    assert out["status"] == "conflicted"
    cf = out["conflicting_facts"]
    assert [f["provenance"]["assertion_id"] for f in cf] == out["conflicting"]
    assert [f["value"] for f in cf] == ["place:a", "place:b"]
    assert list(out) == ["status", "fact", "conflicting", "conflicting_facts"]
    json.dumps(out)


def test_s4_o4c_placeholder_is_unresolved(wm):
    """READ-SURFACE-V1 §4 O4c: a `description` placeholder answers `unresolved`
    with fact.value_type == "unresolved" (today: `known`, the spec as value)."""
    w, _ = wm
    _seed_placeholder(w)
    out = w.porcelain.state("place:study", "description")
    assert out["status"] == "unresolved"
    assert out["fact"]["value_type"] == "unresolved"
    assert out["fact"]["value"] == {"policy": INVENT}
    json.dumps(out)


def test_s4_o4d_every_fact_carries_value_type(wm):
    """READ-SURFACE-V1 §4 O4d: every Fact from snapshot, facts, frame_diff and
    resolve carries value_type; an accrue total carries "literal"."""
    w, _ = wm
    _seed_ann(w)
    _declare(w, "gold", fold_policy="accrue")
    w.porcelain.ingest_structured([
        {"entity": "person:ann", "attribute": "gold", "value": 10, "valid_from": 1.0},
        {"entity": "person:ann", "attribute": "gold", "value": 5,
         "value_type": "delta", "valid_from": 2.0},
        {"entity": "obj:locker", "attribute": "contents", "value": {"policy": "deny"},
         "value_type": "unresolved"},
        {"entity": "obj:lamp", "attribute": "kind", "value": "lamp", "timeless": True},
    ])
    p = w.porcelain
    payloads = (
        p.snapshot("place:hall")["facts"]
        + p.facts("canon")
        + p.frame_diff("canon", "knows:person:bob", "place:hall")
    )
    assert payloads
    for f in payloads:
        assert "value_type" in f, f
        assert list(f)[: len(FACT_KEYS_TODAY) + 1] == FACT_KEYS_TODAY + ["value_type"]
    kind = p.facts("canon", entity="obj:lamp", attribute="kind")[0]
    assert kind["value_type"] == "literal"
    # AMBIGUOUS: a resolve() that serves facts needs a resolving thunk (a model
    # under invent, or a scripted generation); the denied path serves none.
    # The oracle is checked on resolve's `facts` list for whatever it serves.
    for f in p.resolve("obj:locker", "contents")["facts"]:
        assert "value_type" in f
    total = p.state("person:ann", "gold")
    assert total["fact"]["value"] == 15 and total["fact"]["value_type"] == "literal"


def test_s4_o4e_ask_placeholder_key_is_unresolved(wm):
    """READ-SURFACE-V1 §4 O4e: ask on a placeholder key: facts == [],
    unresolved == [["place:study", "description"]], answered False."""
    w, m = wm
    _seed_placeholder(w)
    m.plans.append({"refer_targets": ["the study"],
                    "keys": [{"target_index": 0, "attribute": "description"}],
                    "wants_location": False, "wants_events": False})
    a = w.porcelain.ask("what does the study look like?")
    assert a.facts == []
    assert a.unresolved == [["place:study", "description"]]
    assert a.answered is False
    json.dumps(a.to_dict())


def test_s4_o4e_ask_set_valued_key_serves_every_member(wm):
    """READ-SURFACE-V1 §4 O4e: ask with the tin key: 3 facts."""
    w, m = wm
    _seed_tin(w)
    m.plans.append({"refer_targets": ["the tin"],
                    "keys": [{"target_index": 0, "attribute": "contains"}],
                    "wants_location": False, "wants_events": False})
    a = w.porcelain.ask("what is in the tin?")
    assert sorted(f["value"] for f in a.facts) == ["obj:cig_1", "obj:cig_2", "obj:cig_3"]


def test_s4_o4e_ask_conflicted_key_named(wm):
    """READ-SURFACE-V1 §4 O4e: ask with p's `in` key: 1 fact (the winner) and
    conflicted == [["person:p", "in"]]."""
    w, m = wm
    _seed_split_p(w)
    m.plans.append({"refer_targets": ["p"],
                    "keys": [{"target_index": 0, "attribute": "in"}],
                    "wants_location": False, "wants_events": False})
    a = w.porcelain.ask("where is p?")
    assert len(a.facts) == 1
    assert a.conflicted == [["person:p", "in"]]
    assert a.answered is True
    json.dumps(a.to_dict())


def test_s4_o4f_state_union_same_shape(wm):
    """READ-SURFACE-V1 §4 O4f: state_union over an aka pair has the same shape
    (values / conflicting_facts / value_type)."""
    w, _ = wm
    _declare(w, "allies", arity="set_valued")
    w.porcelain.ingest_structured([
        {"entity": "person:mask", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:lord", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:mask", "attribute": "allies", "value": "person:x",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:lord", "attribute": "allies", "value": "person:y",
         "value_type": "entity", "valid_from": 2.0},
        {"entity": "person:mask", "attribute": "in", "value": "place:a", "valid_from": 3.0},
        {"entity": "person:lord", "attribute": "in", "value": "place:b", "valid_from": 3.0},
    ])
    w.porcelain.correlate("person:mask", "person:lord", evidence="unmasked", at=0.5)
    allies = w.porcelain.state_union("person:mask", "allies")
    assert sorted(f["value"] for f in allies["values"]) == ["person:x", "person:y"]
    assert "value_type" in allies["fact"]
    loc = w.porcelain.state_union("person:mask", "in")
    assert loc["status"] == "conflicted"
    assert [f["provenance"]["assertion_id"] for f in loc["conflicting_facts"]] \
        == loc["conflicting"]
    json.dumps(allies), json.dumps(loc)


def test_s4_known_functional_key_byte_identical_but_value_type(wm):
    """READ-SURFACE-V1 §4 byte-identical: a known, functional, unconflicted key
    keeps every key and value except the new `value_type` inside `fact`."""
    w, _ = wm
    _seed_ann(w)
    out = w.porcelain.state("person:ann", "in")
    assert list(out) == ["status", "fact"]
    fact = {k: v for k, v in out["fact"].items() if k != "value_type"}
    assert list(fact) == FACT_KEYS_TODAY
    assert fact["entity"] == "person:ann" and fact["value"] == "place:hall"
    assert fact["valid"] == [1.0, None]
    assert fact["divergent"] is False and fact["b_value"] is None
    assert set(fact["provenance"]) == {"status", "source_chain", "assertion_id"}


def test_s4_value_type_appended_after_b_value(wm):
    """READ-SURFACE-V1 §4: Fact.value_type is appended after b_value (existing
    keys keep their order); an entity-valued row reports "entity"."""
    w, _ = wm
    w.porcelain.ingest_structured([
        {"entity": "person:ann", "attribute": "in", "value": "place:hall",
         "value_type": "entity", "valid_from": 1.0},
    ])
    fact = w.porcelain.state("person:ann", "in")["fact"]
    assert list(fact) == FACT_KEYS_TODAY + ["value_type"]
    assert fact["value_type"] == "entity"


# ===================================================== §5 who_knows folded value


def _seed_who(w: World) -> None:
    _declare(w, "ally", arity="set_valued")
    _declare(w, "coins", fold_policy="accrue")
    w.porcelain.ingest_structured([
        {"entity": "person:bob", "attribute": "ally", "value": "person:x",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:bob", "attribute": "ally", "value": "person:y",
         "value_type": "entity", "valid_from": 2.0},
    ], frame=ALICE)
    w.porcelain.ingest_structured([
        {"entity": "person:bob", "attribute": "coins", "value": 10, "valid_from": 1.0},
        {"entity": "person:bob", "attribute": "coins", "value": 5,
         "value_type": "delta", "valid_from": 2.0},
    ], frame="knows:person:carol")
    w.ingest_structured([
        {"entity": "person:bob", "attribute": "debt", "value": Decimal("12.50"),
         "valid_from": 1.0},
    ], frame="knows:person:dana")


def test_s5_who_knows_set_member(wm):
    """READ-SURFACE-V1 §5: set member person:x, the older of two allies in
    knows:person:alice: [] → ["knows:person:alice"]."""
    w, _ = wm
    _seed_who(w)
    assert w.porcelain.who_knows("person:bob", "ally", "person:x") == [ALICE]


def test_s5_who_knows_accrue_total(wm):
    """READ-SURFACE-V1 §5: accrue total 15 (10 + delta 5) in knows:person:carol:
    who_knows(…, 15) lists carol and who_knows(…, 5) does not."""
    w, _ = wm
    _seed_who(w)
    assert w.porcelain.who_knows("person:bob", "coins", 15) == ["knows:person:carol"]
    assert w.porcelain.who_knows("person:bob", "coins", 5) == []


def test_s5_who_knows_decimal_tag(wm):
    """READ-SURFACE-V1 §5: {"$decimal": "12.50"} matches knows:person:dana; a
    Decimal("12.50") matches before and after."""
    w, _ = wm
    _seed_who(w)
    assert w.porcelain.who_knows("person:bob", "debt", {"$decimal": "12.50"}) \
        == ["knows:person:dana"]
    assert w.porcelain.who_knows("person:bob", "debt", Decimal("12.50")) \
        == ["knows:person:dana"]


def test_s5_who_knows_placeholder_frame_not_listed(wm):
    """READ-SURFACE-V1 §5: a frame holding only a placeholder for the key is no
    longer listed."""
    w, _ = wm
    w.porcelain.ingest_structured([
        {"entity": "place:study", "attribute": "description", "value": "dusty",
         "valid_from": 1.0},
    ], frame="knows:person:erin")
    w.porcelain.ingest_structured([
        {"entity": "place:study", "attribute": "description",
         "value": {"policy": INVENT}, "value_type": "unresolved"},
    ], frame="knows:person:finn")
    assert w.porcelain.who_knows("place:study", "description") == ["knows:person:erin"]


def test_s5_state_value_matches(wm):
    """READ-SURFACE-V1 §5: state(bob, "ally", frame=alice, value="person:x")
    ["matches"] is True; with person:z False; on an unknown key False."""
    w, _ = wm
    _seed_who(w)
    p = w.porcelain
    yes = p.state("person:bob", "ally", frame=ALICE, value="person:x")
    assert yes["matches"] is True
    assert p.state("person:bob", "ally", frame=ALICE, value="person:z")["matches"] is False
    unknown = p.state("person:bob", "hat", frame=ALICE, value="red")
    assert unknown["status"] == "unknown" and unknown["matches"] is False
    assert list(yes)[-1] == "matches"                     # new keys follow existing ones
    assert "matches" not in p.state("person:bob", "ally", frame=ALICE)
    tagged = p.state("person:bob", "debt", frame="knows:person:dana",
                     value={"$decimal": "12.50"})
    assert tagged["matches"] is True
    json.dumps(yes)


def test_s5_state_union_value_matches(wm):
    """READ-SURFACE-V1 §5: state_union(..., value=) gains `matches` too."""
    w, _ = wm
    _seed_who(w)
    out = w.porcelain.state_union("person:bob", "ally", frame=ALICE, value="person:y")
    assert out["matches"] is True


def test_s5_who_knows_mcp_decimal_tag(spy_world):
    """READ-SURFACE-V1 §5 / §11: over MCP, who_knows with a {"$decimal"} tag value
    gives ["knows:person:dana"]."""
    from patternbuffer.mcp import dispatch
    w, _ = spy_world
    w.ingest_structured([
        {"entity": "person:bob", "attribute": "debt", "value": Decimal("12.50"),
         "valid_from": 1.0},
    ], frame="knows:person:dana", classify="rules")
    out = dispatch(w, "who_knows", {"entity": "person:bob", "attribute": "debt",
                                    "value": {"$decimal": "12.50"}})
    assert out == {"result": ["knows:person:dana"]}


def test_s5_who_knows_functional_byte_identical(wm):
    """READ-SURFACE-V1 §5 byte-identical: a functional, non-accrue key with a
    non-tag value over frames serving a concrete value."""
    w, _ = wm
    w.porcelain.ingest_structured([
        {"entity": "obj:door", "attribute": "lock_state", "value": "shut",
         "valid_from": 1.0, "frame": ALICE},
        {"entity": "obj:door", "attribute": "lock_state", "value": "open",
         "valid_from": 1.0, "frame": "knows:person:bob"},
    ])
    p = w.porcelain
    assert p.who_knows("obj:door", "lock_state") == [ALICE, "knows:person:bob"]
    assert p.who_knows("obj:door", "lock_state", "shut") == [ALICE]


# ===================================================== §6 ask(): time and words


def _seed_badge(w: World) -> None:
    w.porcelain.ingest_structured([
        {"entity": "place:a", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:b", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "obj:badge", "attribute": "kind", "value": "badge", "timeless": True,
         "aliases": ["the badge"]},
        {"entity": "obj:badge", "attribute": "in", "value": "place:a",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "obj:badge", "attribute": "in", "value": "place:b",
         "value_type": "entity", "valid_from": 10.0},
        {"entity": "event:early", "attribute": "kind", "value": "polish",
         "valid_from": 2.0},
        {"entity": "event:early", "attribute": "patient", "value": "obj:badge",
         "value_type": "entity", "valid_from": 2.0},
        {"entity": "event:late", "attribute": "kind", "value": "drop",
         "valid_from": 40.0},
        {"entity": "event:late", "attribute": "patient", "value": "obj:badge",
         "value_type": "entity", "valid_from": 40.0},
    ])


def _plan(as_of: Any = None, keys: list | None = None, location: bool = True,
          events: bool = False) -> dict:
    plan = {"refer_targets": ["the badge"], "keys": keys or [],
            "wants_location": location, "wants_events": events}
    if as_of is not None:
        plan["as_of"] = as_of
    return plan


def _loc_values(a) -> list:
    return [f["value"] for f in a.facts if "chain" in f]


def test_s6_o6a_caller_as_of_caps_plan(wm):
    """READ-SURFACE-V1 §6 O6a: caller as_of=5, plan as_of=50: place:a (today place:b)."""
    w, m = wm
    _seed_badge(w)
    m.plans.append(_plan(as_of=50))
    a = w.porcelain.ask("where was the badge?", as_of=5)
    assert _loc_values(a) == ["place:a"]


def test_s6_o6b_one_effective_time_for_keys_and_location(wm):
    """READ-SURFACE-V1 §6 O6b: caller 20, plan 5, a key on `in`: the key and the
    location both fold at 5."""
    w, m = wm
    _seed_badge(w)
    m.plans.append(_plan(as_of=5, keys=[{"target_index": 0, "attribute": "in"}]))
    a = w.porcelain.ask("where was the badge?", as_of=20)
    key_facts = [f["value"] for f in a.facts if "chain" not in f and "event" not in f]
    assert key_facts == ["place:a"]
    assert _loc_values(a) == ["place:a"]


def test_s6_o6c_caller_none_plan_5(wm):
    """READ-SURFACE-V1 §6 O6c (byte-identical): caller None, plan 5: place:a."""
    w, m = wm
    _seed_badge(w)
    m.plans.append(_plan(as_of=5))
    a = w.porcelain.ask("where was the badge?")
    assert _loc_values(a) == ["place:a"]


def test_s6_o6d_invalid_plan_as_of_ignored(wm):
    """READ-SURFACE-V1 §6 O6d: plan as_of "yesterday", caller 5: both the location
    and wants_events use the caller's 5 (today: place:b and a TypeError)."""
    w, m = wm
    _seed_badge(w)
    m.plans.append(_plan(as_of="yesterday", events=True))
    a = w.porcelain.ask("where was the badge yesterday?", as_of=5)
    assert _loc_values(a) == ["place:a"]
    ts = [f["event"]["t"] for f in a.facts if "event" in f]
    assert ts == [2.0]


def test_s6_o6e_events_capped_at_caller_time(wm):
    """READ-SURFACE-V1 §6 O6e: wants_events with caller 5 and plan 50: the event
    at t=40 is not listed."""
    w, m = wm
    _seed_badge(w)
    m.plans.append(_plan(as_of=50, location=False, events=True))
    a = w.porcelain.ask("what happened to the badge?", as_of=5)
    ids = [f["event"]["id"] for f in a.facts if "event" in f]
    assert "event:late" not in ids
    assert ids == ["event:early"]


def _seed_stash(w: World) -> None:
    w.porcelain.ingest_structured([
        {"entity": "person:alice", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "obj:desk_drawer", "attribute": "kind", "value": "drawer",
         "timeless": True},
    ])
    w.porcelain.ingest_structured([
        {"entity": "obj:desk_drawer", "attribute": "state", "value": "locked",
         "valid_from": 1.0, "aliases": ["the stash"]},
    ], frame=ALICE)


def test_s6_o6f_askers_private_alias_binds_in_own_frame(wm):
    """READ-SURFACE-V1 §6 O6f: Alice's private alias "the stash" binds in her own
    ask: the fact "locked", 1 model call (the plan), head unchanged."""
    w, m = wm
    _seed_stash(w)
    head = w.buffer.head()
    m.plans.append({"refer_targets": ["the stash"],
                    "keys": [{"target_index": 0, "attribute": "state"}],
                    "wants_location": False, "wants_events": False})
    n = len(m.calls)
    a = w.porcelain.ask("is the stash locked?", frame=ALICE)
    assert [f["value"] for f in a.facts] == ["locked"]
    assert len(m.calls) - n == 1
    assert w.buffer.head() == head


def test_s6_o6f_canon_ask_does_not_bind_private_alias(wm):
    """READ-SURFACE-V1 §6 O6f (with batch C): a canon ask of the same question is
    underdetermined, with an entry in `asks`."""
    w, m = wm
    _seed_stash(w)
    m.plans.append({"refer_targets": ["the stash"],
                    "keys": [{"target_index": 0, "attribute": "state"}],
                    "wants_location": False, "wants_events": False})
    a = w.porcelain.ask("is the stash locked?")
    assert a.answered is False
    assert [x["reference"] for x in a.asks] == ["the stash"]


def test_s6_o6g_frame_alias_beats_canon_alias_only_in_that_frame(wm):
    """READ-SURFACE-V1 §6 O6g: canon alias "the stash" on obj:safe, Alice's on
    obj:desk_drawer: Alice's ask binds the drawer; a canon ask binds the safe."""
    w, m = wm
    _seed_stash(w)
    w.porcelain.ingest_structured([
        {"entity": "obj:safe", "attribute": "kind", "value": "safe", "timeless": True,
         "aliases": ["the stash"]},
        {"entity": "obj:safe", "attribute": "state", "value": "open", "valid_from": 1.0},
    ])
    w.porcelain.ingest_structured([
        {"entity": "obj:safe", "attribute": "state", "value": "shut", "valid_from": 1.0},
    ], frame=ALICE)
    plan = {"refer_targets": ["the stash"],
            "keys": [{"target_index": 0, "attribute": "state"}],
            "wants_location": False, "wants_events": False}
    m.plans.append(dict(plan))
    alice = w.porcelain.ask("is the stash locked?", frame=ALICE)
    assert [f["entity"] for f in alice.facts] == ["obj:desk_drawer"]
    m.plans.append(dict(plan))
    canon = w.porcelain.ask("is the stash locked?")
    assert [f["entity"] for f in canon.facts] == ["obj:safe"]


def test_s6_o6h_canon_scene_binding_unchanged(wm):
    """READ-SURFACE-V1 §6 O6h / byte-identical: a non-canon ask where the frame's
    own vocabulary resolves nothing binds exactly as today (HD 003 parity: a
    possessive kind word via the asker's scene)."""
    # The full TestAskReferParity class lives in tests/test_porcelain.py and must
    # pass unchanged; this is one representative case run here as well.
    w, m = wm
    w.porcelain.ingest_structured([
        {"entity": "place:room", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "person:marn", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:marn", "attribute": "in", "value": "place:room", "valid_from": 1.0},
        {"entity": "obj:table", "attribute": "kind", "value": "table", "timeless": True},
        {"entity": "obj:table", "attribute": "in", "value": "place:room", "valid_from": 1.0},
        {"entity": "obj:spoon", "attribute": "kind", "value": "spoon", "timeless": True},
        {"entity": "obj:spoon", "attribute": "in", "value": "obj:table", "valid_from": 1.0},
    ])
    w.porcelain.ingest_structured([
        {"entity": "obj:spoon", "attribute": "in", "value": "obj:table", "valid_from": 1.0},
    ], frame="knows:person:marn")
    m.plans.append({"refer_targets": ["my spoon"], "keys": [], "wants_location": True})
    a = w.porcelain.ask("Where is my spoon?", frame="knows:person:marn")
    assert a.answered and a.facts[0]["value"] == "obj:table"


# ===================================================== §7 world physics


def _tracking_world(path: Path, wid: str = "w:phys", **kw: Any) -> World:
    return World(path, world_id=wid, model=ScriptedModel(), clock=lambda: 1000.0, **kw)


def _learned_at_rows(receipt) -> list[dict]:
    return [r for r in receipt.rows if r["attribute"] == "learned_at_wallclock"]


def _pre_spec_world(tmp_path: Path) -> Path:
    """A world as built before READ-SURFACE-V1: only the charter rows, no
    physics row (built from a dump fixture)."""
    src = World(tmp_path / "src.world", world_id="w:pre")
    lines = [json.loads(line) for line in dump(src.buffer).splitlines() if line.strip()]
    src.close()
    charter = [r for r in lines if r["entity"] == "world:self"]
    assert [r["seq"] for r in charter] == list(range(1, len(charter) + 1))
    path = tmp_path / "pre.world"
    build("\n".join(json.dumps(r) for r in charter) + "\n", path).close()
    return path


def test_s7_o7a_tracking_world_reopened_without_policy_keeps_physics(tmp_path):
    """READ-SURFACE-V1 §7 O7a: a tracking world reopened without `policy=` runs
    as observe_or_unknown, and a new timed row is stamped learned-at."""
    path = tmp_path / "t.world"
    _tracking_world(path, policy=OBSERVE).close()
    w = _tracking_world(path)
    try:
        assert w.policy == OBSERVE
        r = w.porcelain.ingest_structured([
            {"entity": "obj:badge", "attribute": "in", "value": "place:desk",
             "valid_from": 10.0, "status": "observed"},
        ], classify="rules")
        assert len(_learned_at_rows(r)) == 1
    finally:
        w.close()


def test_s7_o7b_disagreeing_policy_raises_and_writes_nothing(tmp_path):
    """READ-SURFACE-V1 §7 O7b: the same world reopened with
    policy="invent_under_canon": WorldPhysicsMismatch (a ValueError). The file is
    unchanged and reopens normally afterwards."""
    WorldPhysicsMismatch = getattr(patternbuffer, "WorldPhysicsMismatch")
    assert issubclass(WorldPhysicsMismatch, ValueError)
    assert "WorldPhysicsMismatch" in patternbuffer.__all__
    path = tmp_path / "t.world"
    w = _tracking_world(path, policy=OBSERVE)
    before = dump(w.buffer)
    w.close()
    with pytest.raises(WorldPhysicsMismatch):
        _tracking_world(path, policy=INVENT)
    w = _tracking_world(path)
    try:
        assert dump(w.buffer) == before
        assert w.policy == OBSERVE
    finally:
        w.close()


def test_s7_o7c_fresh_world_physics_row_after_charter(tmp_path):
    """READ-SURFACE-V1 §7 O7c: a fresh world holds the physics row right after the
    charter (canon, timeless, stated, CONSTITUTIVE); construction with a raising
    model makes no model call; facts("canon", entity="attr:__world__") lists it."""
    calls: list[str] = []

    def raising(prompt: str, schema: dict) -> Any:
        calls.append(prompt)
        raise AssertionError("model called during construction")

    w = World(tmp_path / "f.world", world_id="w:f", model=raising, policy=OBSERVE,
              title="T", description="D")
    try:
        assert calls == []
        rows = w.buffer.all_rows()
        last_charter = max(r.seq for r in rows if r.entity == "world:self")
        phys = _physics_rows(w)
        assert len(phys) == 1
        row = phys[0]
        assert row.seq == last_charter + 1
        assert (row.value, row.frame, row.status) == (OBSERVE, "canon", "stated")
        assert row.valid_from is None and row.valid_to is None
        assert w.classifier.durability(row.id) == "CONSTITUTIVE"
        listed = w.porcelain.facts("canon", entity="attr:__world__")
        assert [(f["attribute"], f["value"]) for f in listed] \
            == [("resolution_policy", OBSERVE)]
    finally:
        w.close()


def test_s7_policy_none_default_on_fresh_world(tmp_path):
    """READ-SURFACE-V1 §7 contract: `policy` now defaults to None, resolving to
    invent_under_canon on a fresh world (which records it)."""
    w = World(tmp_path / "n.world", world_id="w:n", policy=None)
    try:
        assert w.policy == INVENT
        assert [r.value for r in _physics_rows(w)] == [INVENT]
    finally:
        w.close()


def test_s7_o7d_pre_spec_world(tmp_path):
    """READ-SURFACE-V1 §7 O7d: a pre-spec world (no physics row): opened without
    `policy=` head unchanged and invent_under_canon; opened with
    policy="observe_or_unknown" head +1; reopened without: observe_or_unknown."""
    path = _pre_spec_world(tmp_path)
    w = World(path, world_id="w:pre")
    head = w.buffer.head()
    assert w.policy == INVENT
    w.close()
    w = World(path, world_id="w:pre")
    assert w.buffer.head() == head
    w.close()
    w = World(path, world_id="w:pre", policy=OBSERVE)
    assert w.buffer.head() == head + 1
    w.close()
    w = World(path, world_id="w:pre")
    try:
        assert w.policy == OBSERVE
        assert w.buffer.head() == head + 1
    finally:
        w.close()


def test_s7_o7e_gate_refuses_physics_key(tmp_path):
    """READ-SURFACE-V1 §7 O7e: ingest_structured on attr:__world__ ·
    resolution_policy: ValueError, head unchanged; atomic=True: AtomicAbort
    (cause="exception")."""
    w, _ = _world(tmp_path, "o7e")
    try:
        item = {"entity": "attr:__world__", "attribute": "resolution_policy",
                "value": "deny"}
        head = w.buffer.head()
        with pytest.raises(ValueError):
            w.porcelain.ingest_structured([dict(item)])
        assert w.buffer.head() == head
        with pytest.raises(AtomicAbort) as exc:
            w.porcelain.ingest_structured([dict(item)], atomic=True, classify="rules")
        assert exc.value.cause == "exception"
        assert w.buffer.head() == head
        assert w.policy == INVENT
    finally:
        w.close()


def test_s7_o7f_physics_row_cannot_be_retracted(tmp_path):
    """READ-SURFACE-V1 §7 O7f: retract(<the physics row's id>, "x"): ValueError."""
    w, _ = _world(tmp_path, "o7f")
    try:
        phys = _physics_rows(w)
        assert len(phys) == 1, "no physics row on a fresh world"
        head = w.buffer.head()
        with pytest.raises(ValueError):
            w.porcelain.retract(phys[0].id, "x")
        with pytest.raises(ValueError):
            w.truth.retract(phys[0].id, "x")
        assert w.buffer.head() == head
    finally:
        w.close()


def test_s7_o7g_dump_build_keeps_physics_and_rejects_two_rows(tmp_path):
    """READ-SURFACE-V1 §7 O7g: dump → build → reopen keeps the physics. A dump
    with two physics rows fails to build, and its file is removed."""
    w = _tracking_world(tmp_path / "t.world", policy=OBSERVE)
    text = dump(w.buffer)
    w.close()
    build(text, tmp_path / "copy.world").close()
    w2 = _tracking_world(tmp_path / "copy.world")
    try:
        assert w2.policy == OBSERVE
    finally:
        w2.close()
    lines = [json.loads(line) for line in text.splitlines() if line.strip()]
    phys = next(r for r in lines if r["entity"] == "attr:__world__"
                and r["attribute"] == "resolution_policy")
    n = len(lines) + 1
    dup = {**phys, "seq": n, "id": f"a:{n}", "asserted_at": n}
    bad = text + json.dumps(dup) + "\n"
    target = tmp_path / "bad.world"
    with pytest.raises(ValueError):
        build(bad, target)
    assert not target.exists()


class _Captured(Exception):
    pass


def _run_main(monkeypatch, argv: list[str]) -> World:
    """Run the MCP launcher up to the point it would serve, capturing the World."""
    import patternbuffer.mcp as mcpmod
    pytest.importorskip("mcp")
    captured: list[World] = []

    def fake_build_server(world: World):
        captured.append(world)
        raise _Captured()

    monkeypatch.setattr(mcpmod, "build_server", fake_build_server)
    with pytest.raises(_Captured):
        mcpmod.main(argv)
    return captured[0]


def test_s7_o7h_mcp_policy_flag(tmp_path, monkeypatch):
    """READ-SURFACE-V1 §7 O7h: start with --policy observe_or_unknown on a fresh
    path, restart without the flag and ingest a timed row: it carries a learned-at
    stamp. Restarting with --policy invent_under_canon fails startup."""
    from patternbuffer.mcp import dispatch, main
    p = str(tmp_path / "m.world")
    w = _run_main(monkeypatch, ["--world", p, "--world-id", "w:m",
                                "--policy", OBSERVE])
    assert w.policy == OBSERVE
    w.close()
    w = _run_main(monkeypatch, ["--world", p, "--world-id", "w:m"])
    try:
        assert w.policy == OBSERVE
        out = dispatch(w, "ingest_structured", {"items": [
            {"entity": "obj:badge", "attribute": "in", "value": "place:desk",
             "valid_from": 10.0, "status": "observed"}]})
        assert [r for r in out["result"]["rows"]
                if r["attribute"] == "learned_at_wallclock"]
    finally:
        w.close()
    monkeypatch.undo()
    with pytest.raises(getattr(patternbuffer, "WorldPhysicsMismatch")):
        main(["--world", p, "--world-id", "w:m", "--policy", INVENT])


def test_s7_o7h_mcp_policy_env(tmp_path, monkeypatch):
    """READ-SURFACE-V1 §7: the launcher reads PATTERNBUFFER_POLICY as the
    --policy fallback."""
    monkeypatch.setenv("PATTERNBUFFER_POLICY", OBSERVE)
    w = _run_main(monkeypatch, ["--world", str(tmp_path / "e.world"),
                                "--world-id", "w:e"])
    try:
        assert w.policy == OBSERVE
    finally:
        w.close()


def test_s7_o7i_reopen_stance_ignored(tmp_path):
    """READ-SURFACE-V1 §7 O7i (byte-identical): reopening with stance="reality"
    is ignored, as today."""
    path = tmp_path / "s.world"
    World(path, world_id="w:s", stance="fiction").close()
    w = World(path, world_id="w:s", stance="reality")
    try:
        assert w.charter()["stance"] == "fiction"
    finally:
        w.close()


def test_s7_pre_spec_world_without_policy_byte_identical(tmp_path):
    """READ-SURFACE-V1 §7 byte-identical: every pre-spec world opened without
    `policy=` — nothing written, fiction physics."""
    path = _pre_spec_world(tmp_path)
    w = World(path, world_id="w:pre")
    try:
        before = dump(w.buffer)
        assert w.policy == INVENT
        assert _physics_rows(w) == []
    finally:
        w.close()
    w = World(path, world_id="w:pre")
    try:
        assert dump(w.buffer) == before
    finally:
        w.close()


# ===================================================== §8 frame= / asserted_as_of=


def _seed_key(w: World) -> None:
    w.porcelain.ingest_structured([
        {"entity": "obj:box", "attribute": "kind", "value": "box", "timeless": True},
        {"entity": "obj:key", "attribute": "in", "value": "obj:box",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "place:x", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:y", "attribute": "kind", "value": "place", "timeless": True},
    ])
    w.porcelain.ingest_structured([
        {"entity": "obj:key", "attribute": "in", "value": "obj:drawer",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "place:x", "attribute": "connects_to", "value": "place:y",
         "value_type": "entity", "timeless": True},
    ], frame=ALICE)


def test_s8_o8a_locate_frame(wm):
    """READ-SURFACE-V1 §8 O8a: locate(key, frame=alice)[0] == obj:drawer;
    locate(key)[0] == obj:box."""
    w, _ = wm
    _seed_key(w)
    assert w.porcelain.locate("obj:key", frame=ALICE)[0] == "obj:drawer"
    assert w.porcelain.locate("obj:key")[0] == "obj:box"


def test_s8_o8a_locate_positional_as_of_survives(wm):
    """READ-SURFACE-V1 §8 O8a (byte-identical): locate("obj:key", 5.0) still
    means as_of=5.0."""
    w, _ = wm
    _seed_key(w)
    assert w.porcelain.locate("obj:key", 5.0)[0] == "obj:box"
    assert w.porcelain.locate("obj:key", 0.5) == []


def test_s8_o8a_contents_frame(wm):
    """READ-SURFACE-V1 §8 O8a: contents with frame=."""
    w, _ = wm
    _seed_key(w)
    assert w.porcelain.contents("obj:drawer", frame=ALICE) == ["obj:key"]
    assert w.porcelain.contents("obj:drawer") == []
    assert w.porcelain.contents("obj:box") == ["obj:key"]
    assert w.porcelain.contents("obj:box", 5.0) == ["obj:key"]


def test_s8_o8a_path_frame(wm):
    """READ-SURFACE-V1 §8 O8a: path with frame= (a lateral edge only Alice holds)."""
    w, _ = wm
    _seed_key(w)
    assert w.porcelain.path("place:x", "place:y", frame=ALICE) == ["place:x", "place:y"]
    assert w.porcelain.path("place:x", "place:y") is None
    assert w.porcelain.path("place:x", "place:y", None) is None


def _seed_history(w: World) -> int:
    """Rows up to H; returns H."""
    p = w.porcelain
    p.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:yard", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:hall", "attribute": "connects_to", "value": "place:yard",
         "value_type": "entity", "timeless": True},
        {"entity": "obj:door", "attribute": "kind", "value": "door", "timeless": True},
        {"entity": "obj:door", "attribute": "part_of", "value": "place:hall",
         "value_type": "entity", "timeless": True},
        {"entity": "obj:box", "attribute": "kind", "value": "box", "timeless": True},
        {"entity": "obj:box", "attribute": "in", "value": "place:hall",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "obj:coin", "attribute": "kind", "value": "coin", "timeless": True},
        {"entity": "obj:coin", "attribute": "in", "value": "obj:box",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "obj:coin", "attribute": "weight", "value": 3, "valid_from": 1.0},
        {"entity": "person:ann", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:ann", "attribute": "in", "value": "place:hall",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:ann", "attribute": "mood", "value": "calm", "valid_from": 1.0},
        {"entity": "person:mask", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "event:drop", "attribute": "kind", "value": "drop", "valid_from": 2.0},
        {"entity": "event:drop", "attribute": "agent", "value": "person:ann",
         "value_type": "entity", "valid_from": 2.0},
    ], classify="rules")
    p.ingest_structured([
        {"entity": "obj:coin", "attribute": "in", "value": "obj:box",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:ann", "attribute": "mood", "value": "calm", "valid_from": 1.0},
    ], frame="knows:person:ann", classify="rules")
    p.correlate("person:ann", "person:mask", evidence="seen", at=0.5)
    return w.buffer.head()


def _add_later(w: World) -> None:
    """A later value, a later `source` row, a later retraction, a new entity."""
    p = w.porcelain
    mood = p.state("person:ann", "mood")["fact"]["provenance"]["assertion_id"]
    box_in = p.state("obj:box", "in")["fact"]["provenance"]["assertion_id"]
    p.ingest_structured([
        {"entity": "person:ann", "attribute": "mood", "value": "angry", "valid_from": 1.5},
        {"entity": "obj:coin", "attribute": "weight", "value": 5, "valid_from": 1.0},
        {"entity": mood, "attribute": "source", "value": "person:dale"},
        {"entity": "obj:gem", "attribute": "kind", "value": "gem", "timeless": True},
        {"entity": "obj:gem", "attribute": "in", "value": "obj:box",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "obj:gem", "attribute": "weight", "value": 2, "valid_from": 1.0},
        {"entity": "place:yard", "attribute": "connects_to", "value": "place:shed",
         "value_type": "entity", "timeless": True},
        {"entity": "obj:window", "attribute": "part_of", "value": "place:hall",
         "value_type": "entity", "timeless": True},
        {"entity": "event:break", "attribute": "kind", "value": "break", "valid_from": 2.5},
        {"entity": "event:break", "attribute": "agent", "value": "person:ann",
         "value_type": "entity", "valid_from": 2.5},
    ], classify="rules")
    p.ingest_structured([
        {"entity": "person:ann", "attribute": "mood", "value": "calm", "valid_from": 1.0},
    ], frame="knows:person:bob", classify="rules")
    p.ingest_structured([
        {"entity": "person:ann", "attribute": "mood", "value": "angry", "valid_from": 1.5},
    ], frame="knows:person:ann", classify="rules")
    p.retract(box_in, "moved")
    p.correlate("person:ann", "person:ghost", evidence="later", at=0.5)


# The twenty reads of §8, each called with a fixed argument set.
_S8_READS: dict[str, Callable[..., Any]] = {
    "snapshot": lambda p, **k: p.snapshot("place:hall", **k),
    "state": lambda p, **k: p.state("person:ann", "mood", **k),
    "state_union": lambda p, **k: p.state_union("person:ann", "mood", **k),
    "where": lambda p, **k: p.where("weight", ">=", 0, **k),
    "aggregate": lambda p, **k: p.aggregate("obj:box", "weight", "sum", **k),
    "entities": lambda p, **k: p.entities("canon", **k),
    "facts": lambda p, **k: p.facts("canon", **k),
    "locate": lambda p, **k: p.locate("obj:coin", **k),
    "contents": lambda p, **k: p.contents("obj:box", **k),
    "composition": lambda p, **k: p.composition("obj:door", **k),
    "features": lambda p, **k: p.features("place:hall", **k),
    "path": lambda p, **k: p.path("place:hall", "place:shed", **k),
    "route": lambda p, **k: p.route("place:hall", "place:shed", **k),
    "neighborhood": lambda p, **k: p.neighborhood("obj:box", **k),
    "correlations": lambda p, **k: p.correlations("person:ann", **k),
    "correlation_conflicts": lambda p, **k: p.correlation_conflicts(**k),
    "confidence": lambda p, **k: p.confidence("person:ann", "mood", **k),
    "events": lambda p, **k: p.events(**k),
    "who_knows": lambda p, **k: p.who_knows("person:ann", "mood", "calm", **k),
    "frame_diff": lambda p, **k: p.frame_diff("canon", "knows:person:ann",
                                              "place:hall", **k),
}


@pytest.mark.parametrize("verb", sorted(_S8_READS))
def test_s8_o8b_asserted_as_of_property(tmp_path, verb):
    """READ-SURFACE-V1 §8 O8b (the property test): seed rows up to H, then add a
    later value, a later `source` row, a later retraction and a new entity. Every
    one of the twenty reads at asserted_as_of=H answers as it did at H."""
    w, _ = _world(tmp_path, f"o8b_{verb}")
    try:
        h = _seed_history(w)
        call = _S8_READS[verb]
        at_h = call(w.porcelain)
        _add_later(w)
        assert w.buffer.head() > h
        replay = call(w.porcelain, asserted_as_of=h)
        # AMBIGUOUS: neighborhood's per-neighbour `salience` is computed at the
        # head (salience is outside §8; "budget shaping ... ranks by current
        # salience" is a stated known limit), so it is excluded from the
        # comparison here, and neighbours (ranked by that salience) are compared
        # as a set. Every other key must match.
        if verb == "neighborhood":
            replay, at_h = (
                {**_strip(x, frozenset({"salience"})),
                 "neighbors": sorted(_strip(x["neighbors"], frozenset({"salience"})),
                                     key=lambda n: (n["entity"], n["via"]))}
                for x in (replay, at_h)
            )
        assert _norm(replay) == _norm(at_h)
    finally:
        w.close()


def test_s8_o8c_snapshot_of_later_entity_errors(tmp_path):
    """READ-SURFACE-V1 §8 O8c: snapshot(<an id first asserted after H>,
    asserted_as_of=H) returns the error payload."""
    w, _ = _world(tmp_path, "o8c")
    try:
        h = _seed_history(w)
        _add_later(w)
        assert "error" not in w.porcelain.snapshot("obj:gem")
        out = w.porcelain.snapshot("obj:gem", asserted_as_of=h)
        assert "error" in out and out["bad"] == ["obj:gem"]
    finally:
        w.close()


def test_s8_signatures_append_new_params_last(wm):
    """READ-SURFACE-V1 §8: `frame=` follows `as_of` on locate/contents/path, and
    `asserted_as_of` is a keyword on all twenty reads (positional calls survive)."""
    import inspect
    p = wm[0].porcelain
    for verb in ("locate", "contents", "path"):
        params = list(inspect.signature(getattr(p, verb)).parameters)
        assert "frame" in params, verb
        assert params.index("frame") == params.index("as_of") + 1, verb
        assert params[-1] == "asserted_as_of", verb
    for verb in _S8_READS:
        sig = inspect.signature(getattr(p, verb))
        assert "asserted_as_of" in sig.parameters, verb
        assert sig.parameters["asserted_as_of"].default is None, verb


# ===================================================== §9 porcelain refer


def _seed_study(w: World) -> None:
    w.porcelain.ingest_structured([
        {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "obj:pipe", "attribute": "kind", "value": "pipe", "timeless": True,
         "aliases": ["the pipe"]},
        {"entity": "obj:pipe", "attribute": "in", "value": "place:study",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "obj:drawer_1", "attribute": "kind", "value": "drawer", "timeless": True},
        {"entity": "obj:drawer_1", "attribute": "in", "value": "place:study",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "obj:drawer_2", "attribute": "kind", "value": "drawer", "timeless": True},
        {"entity": "obj:drawer_2", "attribute": "in", "value": "place:study",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "obj:spoon", "attribute": "kind", "value": "spoon", "timeless": True},
        {"entity": "obj:spoon", "attribute": "in", "value": "obj:drawer_1",
         "value_type": "entity", "valid_from": 1.0},
    ])


def test_s9_o9a_refer_equals_encoded_world_refer(wm):
    """READ-SURFACE-V1 §9 O9a: p.refer("the pipe") equals the encoded
    asdict(world.refer("the pipe")): resolved, obj:pipe, tier 1 alias_exact."""
    w, _ = wm
    _seed_study(w)
    out = w.porcelain.refer("the pipe")
    expected = json.loads(json.dumps(asdict(w.refer("the pipe"))))
    assert out == expected
    assert out["status"] == "resolved" and out["entity_id"] == "obj:pipe"
    assert out["receipt"]["tier"] == 1 and out["receipt"]["signals"] == ["alias_exact"]
    assert set(out) == {"status", "entity_id", "candidates", "receipt"}
    json.dumps(out)


def test_s9_o9b_model_false_returns_candidates(wm):
    """READ-SURFACE-V1 §9 O9b: "the drawer" in a study holding two drawers,
    model=False: candidates naming both, signal no_model, 0 model calls, head
    unchanged."""
    w, m = wm
    _seed_study(w)
    head, n = w.buffer.head(), len(m.calls)
    out = w.porcelain.refer("the drawer", scope="place:study", model=False)
    assert out["status"] == "candidates"
    assert sorted(out["candidates"]) == ["obj:drawer_1", "obj:drawer_2"]
    assert out["receipt"] == {"tier": 2, "signals": ["no_model"]}
    assert len(m.calls) == n
    assert w.buffer.head() == head
    json.dumps(out)


def test_s9_o9c_learn_false_tier2_writes_nothing(wm):
    """READ-SURFACE-V1 §9 O9c: a vocabulary miss in scope with learn=False:
    resolved at tier 2, head unchanged."""
    w, m = wm
    _seed_study(w)
    m.refer_verdicts.append({"entity_id": "obj:pipe", "confidence": 0.95,
                             "signals": ["synonym"]})
    head = w.buffer.head()
    out = w.porcelain.refer("the briar", scope="place:study", learn=False)
    assert out["status"] == "resolved" and out["entity_id"] == "obj:pipe"
    assert out["receipt"]["tier"] == 2
    assert w.buffer.head() == head
    json.dumps(out)


def test_s9_o9d_constraint_inversion(wm):
    """READ-SURFACE-V1 §9 O9d: constraints=[["contains", "obj:spoon"]]: the
    spoon's container, signal constraint_inversion:contains(obj:spoon)."""
    w, _ = wm
    _seed_study(w)
    out = w.porcelain.refer("the drawer", scope="place:study",
                            constraints=[["contains", "obj:spoon"]], model=False)
    assert out["status"] == "resolved" and out["entity_id"] == "obj:drawer_1"
    assert out["receipt"]["signals"] == ["constraint_inversion:contains(obj:spoon)"]
    json.dumps(out)


def test_s9_o9e_frame_and_asserted_as_of_pass_through(wm):
    """READ-SURFACE-V1 §9 O9e: `frame` and `asserted_as_of` pass through to refer."""
    w, _ = wm
    w.porcelain.ingest_structured([
        {"entity": "place:den", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "obj:box_1", "attribute": "kind", "value": "box", "timeless": True},
        {"entity": "obj:box_1", "attribute": "in", "value": "place:den",
         "value_type": "entity", "valid_from": 1.0},
    ])
    w.porcelain.ingest_structured([
        {"entity": "obj:box_1", "attribute": "kind", "value": "box", "timeless": True},
        {"entity": "obj:box_1", "attribute": "in", "value": "place:den",
         "value_type": "entity", "valid_from": 1.0},
    ], frame=ALICE)
    h = w.buffer.head()
    w.porcelain.ingest_structured([
        {"entity": "obj:box_2", "attribute": "kind", "value": "box", "timeless": True},
        {"entity": "obj:box_2", "attribute": "in", "value": "place:den",
         "value_type": "entity", "valid_from": 1.0},
    ])
    p = w.porcelain
    now = p.refer("the box", scope="place:den", model=False)
    assert now["status"] == "candidates"
    at_h = p.refer("the box", scope="place:den", asserted_as_of=h, model=False)
    assert (at_h["status"], at_h["entity_id"]) == ("resolved", "obj:box_1")
    in_alice = p.refer("the box", scope="place:den", frame=ALICE, model=False)
    assert (in_alice["status"], in_alice["entity_id"]) == ("resolved", "obj:box_1")
    assert in_alice["receipt"]["signals"] == ["unique_kind_in_scope"]


def test_s9_o9f_underdetermined_round_trips(wm):
    """READ-SURFACE-V1 §9 O9f: every return round-trips through json.dumps
    (the underdetermined shape too)."""
    w, _ = wm
    out = w.porcelain.refer("the nothing", model=False)
    assert out["status"] == "underdetermined"
    assert json.loads(json.dumps(out)) == out


def test_s9_world_refer_byte_identical(wm):
    """READ-SURFACE-V1 §9 byte-identical: world.refer for a caller that doesn't
    pass `model` is unchanged."""
    w, _ = wm
    _seed_study(w)
    r = w.refer("the pipe")
    assert (r.status, r.entity_id, r.receipt) == (
        "resolved", "obj:pipe", {"tier": 1, "signals": ["alias_exact"]})


# ===================================================== §11 the MCP surface


class ModelSpy:
    """A raising spy: any model-path call is a test failure."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, prompt: str, schema: dict) -> Any:
        self.calls += 1
        raise AssertionError("model path reached by a V1 MCP tool")


@pytest.fixture
def spy_world(tmp_path):
    spy = ModelSpy()
    w = World(tmp_path / "mcp.world", world_id="w:mcp", model=spy)
    yield w, spy
    w.close()


def test_s11_registry_declares_refer_and_canonical_attribute():
    """READ-SURFACE-V1 §11: two new V1 reads; the registry holds exactly the
    declared tools (39 → 41 on today's base, 42 with C's identity_conflicts)."""
    from patternbuffer.mcp import V1_READS, V1_TOOLS, build_registry
    reg = build_registry()
    assert set(reg) == set(V1_TOOLS)
    assert {"refer", "canonical_attribute"} <= set(V1_READS)
    # AMBIGUOUS: the count depends on whether batch C's identity_conflicts has
    # landed; both stated counts are accepted.
    assert len(reg) == (42 if "identity_conflicts" in reg else 41)


def test_s11_completeness_still_classifies_every_verb():
    """READ-SURFACE-V1 §11: every public porcelain verb is a V1 tool, V1.1 or
    Python sugar (with refer and canonical_attribute classified V1)."""
    import inspect
    from patternbuffer.mcp import V1_TOOLS
    from patternbuffer.porcelain import Porcelain
    public = {n for n, _ in inspect.getmembers(Porcelain, inspect.isfunction)
              if not n.startswith("_")}
    assert {"refer", "canonical_attribute"} <= public
    unclassified = public - set(V1_TOOLS) - {"extract", "ingest", "ask", "resolve"} \
        - {"build"}
    assert not unclassified


def test_s11_forced_params_table():
    """READ-SURFACE-V1 §11: FORCED_PARAMS is the one table; OMITTED_PARAMS is
    frozenset(FORCED_PARAMS); every forced parameter is omitted from the schemas
    and every omitted one is forced."""
    import patternbuffer.mcp as mcpmod
    forced = getattr(mcpmod, "FORCED_PARAMS")
    assert forced == {("seal_build", "model"): False, ("refer", "model"): False,
                      ("refer", "learn"): False}
    assert mcpmod.OMITTED_PARAMS == frozenset(forced)
    reg = mcpmod.build_registry()
    for tool, param in forced:
        assert param not in reg[tool]["inputSchema"]["properties"], (tool, param)


def test_s11_refer_is_read_only_idempotent():
    """READ-SURFACE-V1 §11: refer's annotations are read-only and idempotent."""
    from patternbuffer.mcp import build_registry
    reg = build_registry()
    for name in ("refer", "canonical_attribute"):
        a = reg[name]["annotations"]
        assert a["readOnlyHint"] is True and a["idempotentHint"] is True, name


def test_s11_permissive_schema_allowlist():
    """READ-SURFACE-V1 §11: the permissive-schema allowlist names exactly
    who_knows.value, state.value and state_union.value."""
    from patternbuffer.mcp import build_registry
    reg = build_registry()
    empty = {(t, p) for t, spec in reg.items()
             for p, s in spec["inputSchema"]["properties"].items() if s == {}}
    assert empty == {("who_knows", "value"), ("state", "value"),
                     ("state_union", "value")}


def test_s11_zero_model_smoke_refer_and_canonical_attribute(spy_world):
    """READ-SURFACE-V1 §11: a raising-spy model; refer with an ambiguous kind
    word, and canonical_attribute: 0 calls, 0 writes."""
    from patternbuffer.mcp import dispatch
    w, spy = spy_world
    w.ingest_structured([
        {"entity": "place:room", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "obj:cup_1", "attribute": "kind", "value": "cup", "timeless": True},
        {"entity": "obj:cup_1", "attribute": "in", "value": "place:room",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "obj:cup_2", "attribute": "kind", "value": "cup", "timeless": True},
        {"entity": "obj:cup_2", "attribute": "in", "value": "place:room",
         "value_type": "entity", "valid_from": 1.0},
    ], classify="rules")
    head = w.buffer.head()
    out = dispatch(w, "refer", {"description": "the cup", "scope": "place:room"})
    assert out["result"]["status"] == "candidates"
    assert sorted(out["result"]["candidates"]) == ["obj:cup_1", "obj:cup_2"]
    assert dispatch(w, "canonical_attribute", {"name": "Located In"}) == {"result": "in"}
    assert spy.calls == 0
    assert w.buffer.head() == head


def test_s11_forced_params_refused_before_dispatch(spy_world):
    """READ-SURFACE-V1 §11: refer with "model": True, and with "learn": True,
    raise before dispatch naming the parameter; seal_build with model still
    raises."""
    from patternbuffer.mcp import dispatch
    w, spy = spy_world
    head = w.buffer.head()
    with pytest.raises(ValueError, match="model"):
        dispatch(w, "refer", {"description": "x", "model": True})
    with pytest.raises(ValueError, match="learn"):
        dispatch(w, "refer", {"description": "x", "learn": True})
    dispatch(w, "begin_build", {})
    with pytest.raises(ValueError, match="model"):
        dispatch(w, "seal_build", {"model": True})
    dispatch(w, "abort_build", {})
    assert spy.calls == 0 and w.buffer.head() == head


def test_s11_new_params_appear_in_schemas():
    """READ-SURFACE-V1 §11: new parameters (§4–§9) appear in the generated
    schemas from their annotations."""
    from patternbuffer.mcp import build_registry
    reg = build_registry()
    props = {t: spec["inputSchema"]["properties"] for t, spec in reg.items()}
    for t in ("locate", "contents", "path"):
        assert props[t]["frame"]["type"] == "string", t
    for t in ("snapshot", "state", "facts", "entities", "frame_diff", "confidence",
              "events", "who_knows"):
        assert "asserted_as_of" in props[t], t
    assert "value" in props["state"] and "value" in props["state_union"]
    assert set(props["refer"]) >= {"description", "scope", "frame", "as_of",
                                   "constraints", "asserted_as_of"}
