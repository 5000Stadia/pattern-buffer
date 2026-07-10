"""INGESTION-FIDELITY-V2: the standing-property contract (Cx GREEN r3).

Two orthogonal contracts, never conflated: valid time (`timeless` = true
across the world's whole history) and durability (a standing class may
coexist with `valid_from`). Each oracle pins a row's exit from the
`unstamped_timed` bin by its CORRECT contract — stamping for mutable
time-relative facts (age), classification for standing ones — never
bin-shrink-by-relabeling.
"""

import re

import pytest

from patternbuffer import World
from patternbuffer.classify import CONSTITUTIVE, DISPOSITIONAL, STATE
from patternbuffer.ingest import _EXTRACT_RULES_FULL, _EXTRACT_RULES_LEAN
from patternbuffer.testing import StubModel, rule_classifier_fallback


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "v2.world", world_id="w:v2", model=stub)
    yield w
    w.close()


# ------------------------------------------------ §A: the extract TIME clause

def _bullet(rules: str, prefix: str) -> str:
    """The single line-local bullet carrying the TIME rule (SHAPE-FIX test
    discipline: an unbounded whole-prompt search passes even when the clause
    is gutted)."""
    return next(l for l in rules.splitlines() if l.startswith(prefix))


def test_extract_time_clause_full_variant():
    line = _bullet(_EXTRACT_RULES_FULL, "- TIME:")
    # The whole-history rule and the origin-facts bucket.
    assert "across the world's whole history" in line
    assert "facts of origin" in line
    assert re.search(r"\bkinship of origin\b", line)
    # The onset rule with its dated example, and the earliest-supported stamp.
    assert "became a soldier at the war" in line
    assert "earliest supported" in line
    # age is never timeless; acquired standing properties are stamped.
    assert "Time-relative quantities (age) are current state at the cursor, " \
           "never timeless" in line
    assert "Standing-but-acquired properties" in line
    assert "NOT timeless" in line


def test_extract_time_clause_lean_variant():
    line = _bullet(_EXTRACT_RULES_LEAN, "- timeless=true ONLY")
    assert "across the world's whole history" in line
    assert re.search(r"\bkinship of origin\b", line)
    assert "earliest supported" in line
    assert "never timeless" in line
    assert "NOT timeless" in line


# --------------------------------------- §B2: the classifier preference line

def test_classifier_prompt_carries_enduring_baseline_preference(tmp_path):
    seen = {}

    def spy(prompt, schema):
        seen["prompt"] = prompt
        return {"durability": "STATE", "class_confidence": 0.9}

    w = World(tmp_path / "cls.world", world_id="w:cls", model=spy)
    try:
        # `mood` passes no guardrail -> reaches the model.
        w.ingest_structured([
            {"entity": "person:m", "attribute": "mood", "value": "grim",
             "valid_from": 1.0},
        ])
        prompt = seen["prompt"]
        assert "enduring baseline" in prompt
        assert ("prefer CONSTITUTIVE (what they are) or DISPOSITIONAL "
                "(how they tend) over STATE") in prompt
        assert ("a temporary ability or condition, or a time-relative "
                "quantity (age), remains STATE") in prompt
        # The mutability test and asymmetric defaults survive unchanged.
        assert "could one event flip this" in prompt
        assert "ambiguous property is STATE" in prompt
    finally:
        w.close()


# ------------------------------- §B1: the kinship-of-origin declaration path

def _raise_on_classify(prompt, schema):
    raise AssertionError(f"model called for a declared attribute: {prompt[:60]!r}")


def test_declared_father_classifies_constitutive_without_model(tmp_path):
    # The canonical CHILD->PARENT form, fixture-exact (Cx r2 directionality):
    # subject HAS father. Declared structural -> deterministic guardrail.
    def default(attribute):
        return {"structural": True} if attribute in ("father", "mother") else None

    w = World(tmp_path / "kin.world", world_id="w:kin",
              model=_raise_on_classify, attribute_default=default)
    try:
        w.ingest_structured([
            {"entity": "person:mara_thist", "attribute": "father",
             "value": "person:mara_thist_father", "value_type": "entity",
             "timeless": True},
        ])
        row = next(r for r in w.buffer.all_rows() if r.attribute == "father")
        # No canonicalization touched the authored attribute (no father_of
        # mapping exists; the declaration sees exactly what was written).
        assert row.attribute == "father"
        assert row.entity == "person:mara_thist"          # direction preserved
        c = w.classifier.get(row.id)
        assert c.durability == CONSTITUTIVE and c.class_confidence == 1.0
    finally:
        w.close()


def test_undeclared_father_and_spouse_defer_to_model(tmp_path):
    calls = []

    def counting(prompt, schema):
        calls.append(prompt)
        return {"durability": "STATE", "class_confidence": 0.7}

    w = World(tmp_path / "kin2.world", world_id="w:kin2", model=counting)
    try:
        w.ingest_structured([
            {"entity": "person:a", "attribute": "father", "value": "person:b",
             "value_type": "entity", "timeless": True},
            {"entity": "person:a", "attribute": "spouse", "value": "person:c",
             "value_type": "entity", "valid_from": 1.0},
        ])
        assert len(calls) == 2      # both deferred: no engine kinship builtin
    finally:
        w.close()


# ------------------------- §C: audit-bin regression pins (existing contract)

def test_unstamped_dispositional_exits_bin(world):
    world.ingest_structured([
        {"entity": "person:m", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:m", "attribute": "occupation", "value": "hunter",
         "timeless": True},
    ])
    row = next(r for r in world.buffer.all_rows()
               if r.attribute == "occupation")
    world.classifier.set(row.id, STATE)
    in_bin = {(u["entity"], u["attribute"])
              for u in world.porcelain.fidelity_audit()["unstamped_timed"]}
    assert ("person:m", "occupation") in in_bin           # STATE stays in
    world.classifier.set(row.id, DISPOSITIONAL)
    out_bin = {(u["entity"], u["attribute"])
               for u in world.porcelain.fidelity_audit()["unstamped_timed"]}
    assert ("person:m", "occupation") not in out_bin      # standing class exits


def test_stamped_rows_never_enter_bin_regardless_of_class(world):
    world.ingest_structured([
        {"entity": "person:m", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:m", "attribute": "age", "value": 32,
         "valid_from": 3.0},
    ])
    row = next(r for r in world.buffer.all_rows() if r.attribute == "age")
    for durability in (STATE, DISPOSITIONAL, CONSTITUTIVE):
        world.classifier.set(row.id, durability)
        keys = {(u["entity"], u["attribute"])
                for u in world.porcelain.fidelity_audit()["unstamped_timed"]}
        assert ("person:m", "age") not in keys


# ------------------------------------- §D: the merged_self_edge receipt rider

def test_merge_induced_self_edge_receipts_merged_self_edge(world):
    world.ingest_structured([
        {"entity": "place:harth", "attribute": "kind", "value": "place",
         "timeless": True},
        {"entity": "place:harth_village", "attribute": "kind", "value": "place",
         "timeless": True},
    ])
    world.registry.merge("place:harth", "place:harth_village", evidence="t")
    world.ingest_structured([
        {"entity": "place:harth", "attribute": "in",
         "value": "place:harth_village", "value_type": "entity",
         "valid_from": 5.0},
    ])
    skips = world.ingestor.last_skipped
    assert len(skips) == 1
    reason = skips[0].reason
    # The distinct reason, with BOTH raw ids retained (actionable diagnosis):
    # raw ids differ before resolution, canonical ids match after.
    assert reason.startswith("merged_self_edge:")
    assert "place:harth" in reason and "place:harth_village" in reason
    # The row never entered (gate behavior identical).
    assert not [r for r in world.buffer.all_rows()
                if r.attribute == "in" and r.valid_from == 5.0]


def test_authored_self_edge_keeps_original_reason(world):
    world.ingest_structured([
        {"entity": "place:loop", "attribute": "kind", "value": "place",
         "timeless": True},
        {"entity": "place:loop", "attribute": "in", "value": "place:loop",
         "value_type": "entity", "valid_from": 5.0},
    ])
    skips = world.ingestor.last_skipped
    assert len(skips) == 1
    assert not skips[0].reason.startswith("merged_self_edge")
    assert "cannot contain" in skips[0].reason            # the original reason


# -------------- §D boundary: the rider is CONTAINMENT-ONLY (Cx code review)

def test_merged_lateral_loop_keeps_original_reason(world):
    # A merged pair whose rejected edge is LATERAL (connects_to) keeps the
    # original loop reason — merged_self_edge is defined for containment only
    # (§D / LEXICON); code and docs must not disagree.
    world.ingest_structured([
        {"entity": "place:a", "attribute": "kind", "value": "place",
         "timeless": True},
        {"entity": "place:b", "attribute": "kind", "value": "place",
         "timeless": True},
    ])
    world.registry.merge("place:a", "place:b", evidence="t")
    world.ingest_structured([
        {"entity": "place:a", "attribute": "connects_to", "value": "place:b",
         "value_type": "entity", "timeless": True},
    ])
    skips = world.ingestor.last_skipped
    assert len(skips) == 1
    assert not skips[0].reason.startswith("merged_self_edge")


# --------------------- Oracle 6: row-level fixture outcomes (per-row, unit form)

def test_row_level_outcomes_each_row_exits_by_its_own_contract(tmp_path):
    """Every a:64-class row exits the bin by its CORRECT contract — never one
    label for all. The model responder below is SCRIPTED to the contract's
    expected verdicts (the §B2 preference); it is sidecar-outcome wiring, not
    evidence the live model judges this way — that semantic evidence is the
    host-side fixture re-run."""
    def default(attribute):
        return {"structural": True} if attribute in ("father", "mother") else None

    VERDICTS = {
        "age": "STATE",                    # time-relative -> stays STATE
        "build": "CONSTITUTIVE",           # enduring physical trait
        "scar_on_left_palm": "CONSTITUTIVE",
        "occupation": "DISPOSITIONAL",     # continuing role
        "can_hunt": "DISPOSITIONAL",       # capability
    }

    def scripted(prompt, schema):
        if not prompt.startswith("Classify the lifetime"):
            raise AssertionError(f"unscripted call: {prompt[:60]!r}")
        attr = next(l.split(": ", 1)[1] for l in prompt.splitlines()
                    if l.startswith("Attribute: "))
        assert attr != "father", "declared kinship must never reach the model"
        return {"durability": VERDICTS[attr], "class_confidence": 0.9}

    w = World(tmp_path / "rows.world", world_id="w:rows", model=scripted,
              attribute_default=default)
    try:
        w.ingest_structured([
            # age: mutable time-relative -> STATE, stamped (exits by STAMP)
            {"entity": "person:mara_thist", "attribute": "age", "value": 32,
             "valid_from": 7.0},
            # father: declared kinship of origin -> CONSTITUTIVE timeless
            # (exits by CLASS; deterministic — the responder raises if asked)
            {"entity": "person:mara_thist", "attribute": "father",
             "value": "person:mara_thist_father", "value_type": "entity",
             "timeless": True},
            # build/scar: standing class, earliest-supported valid time
            # HONORED as authored (§A: acquired -> stamped, never timeless)
            {"entity": "person:mara_thist", "attribute": "build",
             "value": "wiry", "valid_from": 1.0},
            {"entity": "person:mara_thist", "attribute": "scar_on_left_palm",
             "value": True, "valid_from": 1.0},
            # occupation/can_*: authored wrongly-timeless (the defect shape —
            # an ordinary non-timeless row is cursor-stamped, so the fixture's
            # unstamped rows arrive exactly this way) and exit by CLASS — the
            # §C mechanic on the real row shape
            {"entity": "person:mara_thist", "attribute": "occupation",
             "value": "hunter", "timeless": True},
            {"entity": "person:mara_thist", "attribute": "can_hunt",
             "value": True, "timeless": True},
        ])
        rows = {r.attribute: r for r in w.buffer.all_rows()
                if r.entity == "person:mara_thist"}

        # age: STATE with the authored stamp, directly asserted
        assert w.classifier.durability(rows["age"].id) == STATE
        assert rows["age"].valid_from == 7.0
        # father: deterministic CONSTITUTIVE 1.0, timeless
        c = w.classifier.get(rows["father"].id)
        assert c.durability == CONSTITUTIVE and c.class_confidence == 1.0
        assert rows["father"].valid_from is None
        # build/scar: standing class; earliest-supported valid time honored
        for attr in ("build", "scar_on_left_palm"):
            assert w.classifier.durability(rows[attr].id) == CONSTITUTIVE
            assert rows[attr].valid_from == 1.0
        # occupation/can_*: standing class on genuinely-unstamped rows
        for attr in ("occupation", "can_hunt"):
            assert w.classifier.durability(rows[attr].id) == DISPOSITIONAL
            assert rows[attr].valid_from is None

        bin_keys = {(u["entity"], u["attribute"])
                    for u in w.porcelain.fidelity_audit()["unstamped_timed"]}
        assert ("person:mara_thist", "age") not in bin_keys         # by stamp
        assert ("person:mara_thist", "father") not in bin_keys      # by class
        assert ("person:mara_thist", "build") not in bin_keys       # stamped
        assert ("person:mara_thist", "scar_on_left_palm") not in bin_keys
        assert ("person:mara_thist", "occupation") not in bin_keys  # by class
        assert ("person:mara_thist", "can_hunt") not in bin_keys    # by class
    finally:
        w.close()
