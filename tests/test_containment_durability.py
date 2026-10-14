"""CONTAINMENT-DURABILITY-V1: a movable's location is never made permanent by a
guess. One test group per numbered spec test (specs/CONTAINMENT-DURABILITY-V1.md),
with the r1.1-r1.4 sub-cases, and the build-library cases of r1.3/r1.4."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import pytest

from patternbuffer import World, build as b
from patternbuffer import classify as classify_module
from patternbuffer.build.commit import CommitRefused
from patternbuffer.build.grammar import grammar_problem, parse_line
from patternbuffer.classify import (
    CONSTITUTIVE,
    CONTAINMENT_CONSTITUTIVE_FLOOR,
    STATE,
)
from patternbuffer.dump import dump
from patternbuffer.ingest import SKIP_REASONS
from patternbuffer.model import (
    STRUCTURAL_PREDICATES,
    TASK_CLASSIFY,
    TASK_CLASSIFY_BATCH,
    TASK_EXTRACT,
)

FIXTURES = Path(__file__).parent / "fixtures"
CORPUS = FIXTURES / "containment_durability_corpus.json"
NEW_SENTENCE = ("An object's location is STATE unless the object is clearly built into "
                "the place (a door, a window, a fixed fitting); when unsure, STATE.")


class Stub:
    """The injected model: scripted classify verdicts by (entity, attribute)
    (default STATE 0.9), scripted extraction items, and a record of every call.
    ``classify_calls`` lists the (entity, attribute) of each judged containment
    row (the world's own seed rows are judged too, and are not this spec's)."""

    def __init__(self, verdicts=None, extraction=None):
        self.verdicts = dict(verdicts or {})
        self.extraction = list(extraction or [])
        self.classify_calls: list[tuple[str, str]] = []
        self.prompts: dict[str, list[str]] = {TASK_CLASSIFY: [], TASK_CLASSIFY_BATCH: []}

    def verdict(self, entity, attribute):
        if attribute in ("in", "within", "held_by", "worn_by", "carried_by"):
            self.classify_calls.append((entity, attribute))
        return self.verdicts.get((entity, attribute), (STATE, 0.9))

    def __call__(self, prompt, schema):
        task = schema.get("title")
        if task == TASK_EXTRACT:
            return {"items": list(self.extraction)}
        if task == TASK_CLASSIFY_BATCH:
            self.prompts[task].append(prompt)
            out = []
            for line in prompt.splitlines():
                m = re.match(r"\s*(\d+)\.\s+(\S+) · (\S+) ·", line)
                if m:
                    dur, conf = self.verdict(m.group(2), m.group(3))
                    out.append({"index": int(m.group(1)), "durability": dur,
                                "class_confidence": conf})
            return {"verdicts": out}
        if task == TASK_CLASSIFY:
            self.prompts[task].append(prompt)
            subject = attribute = ""
            for line in prompt.splitlines():
                if line.startswith("Subject: "):
                    subject = line.removeprefix("Subject: ")
                elif line.startswith("Attribute: "):
                    attribute = line.removeprefix("Attribute: ")
            dur, conf = self.verdict(subject, attribute)
            return {"durability": dur, "class_confidence": conf}
        raise AssertionError(f"unscripted model call: {task}")


@pytest.fixture
def make_world(tmp_path):
    opened: list[World] = []

    def make(stub=None, name: str = "w") -> tuple[World, Any]:
        stub = stub or Stub()
        w = World(tmp_path / f"{name}.world", world_id="w:cd", model=stub)
        opened.append(w)
        return w, stub

    yield make
    for w in opened:
        w.close()


def put(w, entity, attribute, value, **kw):
    item = {"entity": entity, "attribute": attribute, "value": value, **kw}
    if attribute in ("in", "within", "held_by", "worn_by", "carried_by"):
        item.setdefault("value_type", "entity")
    return item


def contain(entity, container, t=1.0, attribute="in"):
    return {"entity": entity, "attribute": attribute, "value": container,
            "value_type": "entity", "valid_from": t}


def fixture_item(entity, value=True, **kw):
    return {"entity": entity, "attribute": "fixture", "value": value,
            "value_type": "literal", "timeless": True, "frame": "canon", **kw}


def the_row(w, entity, attribute, value=None):
    found = [r for r in w.buffer.all_rows()
             if r.entity == entity and r.attribute == attribute
             and (value is None or r.value == value)]
    assert found, (entity, attribute, value)
    return found[-1]


def verdict(w, row):
    c = w.classifier.get(row.id)
    return (c.durability, c.class_confidence) if c else None


def skips(w):
    return [s.reason for s in w.ingestor.last_skipped]


# ====================================================== 1. beings move


def test_1_a_person_subject_is_state_095_by_guardrail_with_no_model_call(make_world):
    w, stub = make_world()
    rows = w.ingest_structured([contain("person:mara", "place:hall")])
    row = rows[0]
    assert verdict(w, row) == (STATE, 0.95)
    assert stub.classify_calls == []
    # re-derivation agrees: the sidecar is rebuildable and the guardrail is the source
    w.classifier.rebuild()
    assert verdict(w, row) == (STATE, 0.95)
    assert stub.classify_calls == []


def test_1_every_containment_attribute_on_a_person_is_state(make_world):
    w, stub = make_world()
    for attribute, container in (("within", "place:hall"), ("held_by", "person:ann")):
        row = w.ingest_structured([contain("person:mara", container, attribute=attribute)])[0]
        assert verdict(w, row)[0] == STATE
    assert stub.classify_calls == []


def test_1_r1_1_a_non_person_namespace_being_goes_to_the_model_and_the_floor(make_world):
    stub = Stub({("npc:smuggler", "in"): (CONSTITUTIVE, 0.7)})
    w, _ = make_world(stub)
    row = w.ingest_structured([contain("npc:smuggler", "place:hall")])[0]
    assert stub.classify_calls == [("npc:smuggler", "in")]
    assert verdict(w, row) == (STATE, 0.7)         # rule 3 demotes it, confidence kept


def test_1_a_place_subject_is_still_constitutive_without_a_model_call(make_world):
    w, stub = make_world()
    row = w.ingest_structured([contain("place:study", "place:house")])[0]
    assert verdict(w, row)[0] == CONSTITUTIVE
    assert stub.classify_calls == []


# ====================================================== 2. declared fixtures


def test_2_a_fixture_declared_before_makes_its_containment_constitutive_10(make_world):
    w, stub = make_world()
    w.ingest_structured([fixture_item("obj:door")])
    assert skips(w) == []
    row = w.ingest_structured([contain("obj:door", "place:cell")])[0]
    assert verdict(w, row) == (CONSTITUTIVE, 1.0)
    assert stub.classify_calls == []


def test_2_without_the_declaration_the_same_row_goes_to_the_model(make_world):
    stub = Stub({("obj:door", "in"): (STATE, 0.8)})
    w, _ = make_world(stub)
    row = w.ingest_structured([contain("obj:door", "place:cell")])[0]
    assert stub.classify_calls == [("obj:door", "in")]
    assert verdict(w, row) == (STATE, 0.8)


def test_2_the_fixture_row_itself_is_structural_constitutive_never_model_judged(make_world):
    w, stub = make_world()
    assert "fixture" in STRUCTURAL_PREDICATES
    row = w.ingest_structured([fixture_item("obj:door")])[0]
    assert verdict(w, row) == (CONSTITUTIVE, 1.0)
    assert stub.classify_calls == []


@pytest.mark.parametrize("path", ["first", "rebuild"])
def test_2_r1_1_a_later_declaration_never_reclassifies_an_earlier_row(make_world, path):
    stub = Stub({("obj:page", "in"): (STATE, 0.8)})
    w, _ = make_world(stub)
    row = w.ingest_structured([contain("obj:page", "obj:book")], classify="defer")[0]
    w.ingest_structured([fixture_item("obj:page")])          # written AFTER the row
    if path == "first":
        w.classifier.classify_all()
    else:
        w.classifier.classify_all()
        w.classifier.rebuild()
    assert ("obj:page", "in") in stub.classify_calls         # judged by the model
    assert verdict(w, row) == (STATE, 0.8)                   # not the fixture guardrail
    # while a row written after the declaration does get it
    later = w.ingest_structured([contain("obj:page", "place:hall", t=5.0)])[0]
    assert verdict(w, later) == (CONSTITUTIVE, 1.0)


def test_2_r1_1_true_then_false_before_the_row_the_latest_decides(make_world):
    stub = Stub({("obj:door", "in"): (STATE, 0.8)})
    w, _ = make_world(stub)
    w.ingest_structured([fixture_item("obj:door", True)])
    w.ingest_structured([fixture_item("obj:door", False)])
    row = w.ingest_structured([contain("obj:door", "place:cell")])[0]
    assert ("obj:door", "in") in stub.classify_calls
    assert verdict(w, row) == (STATE, 0.8)


def test_2_r1_1_false_then_true_the_latest_decides_fixture(make_world):
    w, stub = make_world()
    w.ingest_structured([fixture_item("obj:door", False)])
    w.ingest_structured([fixture_item("obj:door", True)])
    row = w.ingest_structured([contain("obj:door", "place:cell")])[0]
    assert verdict(w, row) == (CONSTITUTIVE, 1.0)
    assert stub.classify_calls == []


def test_2_r1_1_a_retracted_true_does_not_count(make_world):
    stub = Stub({("obj:door", "in"): (STATE, 0.8)})
    w, _ = make_world(stub)
    declared = w.ingest_structured([fixture_item("obj:door")])[0]
    w.truth.retract(declared.id, "mistaken")
    row = w.ingest_structured([contain("obj:door", "place:cell")])[0]
    assert ("obj:door", "in") in stub.classify_calls
    assert verdict(w, row) == (STATE, 0.8)


def test_2_r1_1_only_timeless_literal_boolean_canon_rows_count(make_world):
    stub = Stub({("obj:door", "in"): (STATE, 0.8)})
    w, _ = make_world(stub)
    w.ingest_structured([
        fixture_item("obj:door", True, timeless=False, valid_from=1.0),   # not timeless
        fixture_item("obj:door", "yes"),                                  # not a boolean
        fixture_item("obj:door", True, frame="knows:person:ann"),         # not canon
    ])
    row = w.ingest_structured([contain("obj:door", "place:cell", t=2.0)])[0]
    assert ("obj:door", "in") in stub.classify_calls
    assert verdict(w, row) == (STATE, 0.8)


def test_2_the_subject_is_the_id_as_written_no_identity_closure(make_world):
    stub = Stub({("obj:hatch", "in"): (STATE, 0.8)})
    w, _ = make_world(stub)
    w.ingest_structured([fixture_item("obj:door")])
    row = w.ingest_structured([contain("obj:hatch", "place:cell")], classify="defer")[0]
    out = w.porcelain.merge("obj:door", "obj:hatch", evidence="the same hatch")
    assert out.get("outcome") in ("merged", "ok", None) or out
    w.classifier.classify_all()
    assert ("obj:hatch", "in") in stub.classify_calls         # a twin's declaration is not its own
    assert verdict(w, row) == (STATE, 0.8)


def test_2_r1_2_extracted_structured_ingest_skips_fixture_with_a_typed_receipt(make_world):
    stub = Stub({("obj:page", "in"): (CONSTITUTIVE, 0.7)})
    w, _ = make_world(stub)
    head = w.buffer.head()
    w.ingest_structured([fixture_item("obj:page")], extracted=True)
    assert skips(w) == ["fixture_not_host"]
    assert "fixture_not_host" in SKIP_REASONS
    assert w.buffer.head() == head                            # nothing written
    assert w.buffer.visible(attribute="fixture") == []
    row = w.ingest_structured([contain("obj:page", "obj:book")])[0]
    assert ("obj:page", "in") in stub.classify_calls           # model and floor, not the fixture
    assert verdict(w, row) == (STATE, 0.7)


def test_2_r1_2_the_prose_ingest_path_is_skipped_too(make_world):
    stub = Stub(extraction=[fixture_item("obj:page")])
    w, _ = make_world(stub)
    head = w.buffer.head()
    w.ingest("The page was part of the book.")
    assert skips(w) == ["fixture_not_host"]
    assert w.buffer.head() == head
    assert w.buffer.visible(attribute="fixture") == []


def test_2_r1_2_the_same_item_from_a_host_is_written_and_the_guardrail_applies(make_world):
    w, stub = make_world()
    w.ingest_structured([fixture_item("obj:page")], extracted=False)
    assert skips(w) == []
    assert len(w.buffer.visible(attribute="fixture")) == 1
    row = w.ingest_structured([contain("obj:page", "obj:book")])[0]
    assert verdict(w, row) == (CONSTITUTIVE, 1.0)
    assert stub.classify_calls == []


def test_2_r1_2_an_extracted_call_skips_only_the_fixture_item(make_world):
    w, _ = make_world()
    rows = w.ingest_structured([fixture_item("obj:page"),
                                put(None, "obj:page", "colour", "red", valid_from=1.0)],
                               extracted=True)
    assert skips(w) == ["fixture_not_host"]
    assert [r.attribute for r in rows if r.entity == "obj:page"] == ["colour"]


def test_2_r1_2_a_build_library_line_with_attribute_fixture_is_refused_by_grammar_problem():
    sentence, item = parse_line("s1|obj:page|fixture|true|t")
    assert sentence == 1
    problem = grammar_problem(item)
    assert problem is not None and "fixture" in problem
    assert grammar_problem({**item, "attribute": "colour"}) is None


# ====================================================== 3. the floor


def _seed_book_and_door(w):
    return w.ingest_structured([
        contain("obj:execution_page", "obj:book"),
        contain("obj:barred_door", "place:cell"),
    ], classify="defer")


def test_3_a_low_confidence_constitutive_is_stored_state_with_the_confidence_kept(make_world):
    stub = Stub({("obj:execution_page", "in"): (CONSTITUTIVE, 0.7)})
    w, _ = make_world(stub)
    row = w.ingest_structured([contain("obj:execution_page", "obj:book")])[0]
    c = w.classifier.get(row.id)
    assert (c.durability, c.class_confidence, c.needs_review) == (STATE, 0.7, False)


def test_3_a_high_confidence_constitutive_stays(make_world):
    stub = Stub({("obj:barred_door", "in"): (CONSTITUTIVE, 0.95)})
    w, _ = make_world(stub)
    row = w.ingest_structured([contain("obj:barred_door", "place:cell")])[0]
    assert verdict(w, row) == (CONSTITUTIVE, 0.95)


def test_3_the_floor_is_a_module_constant_095_and_exactly_at_it_stays():
    assert CONTAINMENT_CONSTITUTIVE_FLOOR == 0.95


def test_3_r1_5_the_corpus_boundary_cases(make_world):
    """r1.5: 0.93 on `execution_page in ledger` is STATE; the barred door stays
    CONSTITUTIVE at 0.95 and is STATE at 0.90."""
    w, _ = make_world(Stub({("obj:execution_page", "in"): (CONSTITUTIVE, 0.93),
                            ("obj:barred_door", "in"): (CONSTITUTIVE, 0.95),
                            ("obj:iron_door", "in"): (CONSTITUTIVE, 0.9)}))
    page = w.ingest_structured([contain("obj:execution_page", "obj:ledger")])[0]
    door = w.ingest_structured([contain("obj:barred_door", "place:cell")])[0]
    low = w.ingest_structured([contain("obj:iron_door", "place:cell")])[0]
    assert verdict(w, page) == (STATE, 0.93)
    assert verdict(w, door) == (CONSTITUTIVE, 0.95)
    assert verdict(w, low) == (STATE, 0.9)


def test_3_exactly_at_the_floor_stays_constitutive_and_just_below_is_demoted(make_world):
    stub = Stub({("obj:a", "in"): (CONSTITUTIVE, 0.95), ("obj:b", "in"): (CONSTITUTIVE, 0.949)})
    w, _ = make_world(stub)
    a = w.ingest_structured([contain("obj:a", "obj:box")])[0]
    bb = w.ingest_structured([contain("obj:b", "obj:box")])[0]
    assert verdict(w, a) == (CONSTITUTIVE, 0.95)
    assert verdict(w, bb) == (STATE, 0.949)


def test_3_r1_1_the_batch_path_gives_the_same_stored_classes(make_world):
    verdicts = {("obj:execution_page", "in"): (CONSTITUTIVE, 0.7),
                ("obj:barred_door", "in"): (CONSTITUTIVE, 0.95),
                ("obj:ledger_page", "in"): (CONSTITUTIVE, 0.93)}
    single, _ = make_world(Stub(verdicts), "single")
    batch, _ = make_world(Stub(verdicts), "batch")
    items = [contain("obj:execution_page", "obj:book"), contain("obj:barred_door", "place:cell"),
             contain("obj:ledger_page", "obj:ledger")]
    s_rows = single.ingest_structured(items)
    b_rows = batch.ingest_structured(items, classify="defer")
    batch.classifier.classify_all(batch_size=10)
    assert [verdict(single, r) for r in s_rows] == [verdict(batch, r) for r in b_rows]
    assert [verdict(batch, r) for r in b_rows] == [(STATE, 0.7), (CONSTITUTIVE, 0.95), (STATE, 0.93)]
    # the batch ingest path (classify="batch") agrees too
    third, _ = make_world(Stub(verdicts), "third")
    t_rows = third.ingest_structured(items, classify="batch")
    assert [verdict(third, r) for r in t_rows] == [(STATE, 0.7), (CONSTITUTIVE, 0.95), (STATE, 0.93)]


def test_3_a_failed_model_call_never_makes_a_location_permanent(make_world):
    """The model's failure default for containment was CONSTITUTIVE 0.5; the one
    floor helper now stores it STATE, on the single-row and the batch path."""
    def broken(prompt, schema):
        raise RuntimeError("model down")

    single, _ = make_world(broken, "single")
    row = single.ingest_structured([contain("obj:cup", "obj:shelf")])[0]
    assert verdict(single, row) == (STATE, 0.5)
    batch, _ = make_world(broken, "batch")
    row = batch.ingest_structured([contain("obj:cup", "obj:shelf")], classify="batch")[0]
    assert verdict(batch, row) == (STATE, 0.5)


def test_3_r1_1_each_demotion_logs_one_info_record_naming_the_row(make_world, caplog):
    stub = Stub({("obj:execution_page", "in"): (CONSTITUTIVE, 0.7),
                 ("obj:barred_door", "in"): (CONSTITUTIVE, 0.95)})
    w, _ = make_world(stub)
    with caplog.at_level(logging.INFO, logger="patternbuffer.classify"):
        page = w.ingest_structured([contain("obj:execution_page", "obj:book")])[0]
        w.ingest_structured([contain("obj:barred_door", "place:cell")])
    records = [r for r in caplog.records
               if r.name == "patternbuffer.classify" and r.levelno == logging.INFO
               and "containment floor" in r.getMessage()]
    assert len(records) == 1
    assert page.id in records[0].getMessage() and "0.700" in records[0].getMessage()

    # and in the batch path
    caplog.clear()
    w2, _ = make_world(Stub({("obj:execution_page", "in"): (CONSTITUTIVE, 0.7)}), "w2")
    with caplog.at_level(logging.INFO, logger="patternbuffer.classify"):
        row = w2.ingest_structured([contain("obj:execution_page", "obj:book")],
                                   classify="batch")[0]
    records = [r for r in caplog.records if "containment floor" in r.getMessage()]
    assert len(records) == 1 and row.id in records[0].getMessage()


def test_3_no_schema_change_the_classification_record_keeps_its_shape(make_world):
    w, _ = make_world()
    cols = [r[1] for r in w.buffer.raw_connection().execute(
        "PRAGMA table_info(sidecar_classification)")]
    assert cols == ["assertion_id", "durability", "class_confidence", "needs_review"]
    assert [f for f in classify_module.Classification.__dataclass_fields__] == [
        "assertion_id", "durability", "class_confidence", "needs_review"]


def test_3_the_floor_touches_only_containment_rows(make_world):
    stub = Stub({("obj:wall", "material"): (CONSTITUTIVE, 0.6)})
    w, _ = make_world(stub)
    row = w.ingest_structured([put(None, "obj:wall", "material", "stone", valid_from=1.0)])[0]
    assert verdict(w, row) == (CONSTITUTIVE, 0.6)             # not a containment row


# ====================================================== 4. the flicker, end to end


def _flicker(w):
    w.ingest_structured([contain("obj:execution_page", "obj:book", t=1.0)])
    w.ingest_structured([contain("obj:execution_page", "person:player", t=2.0,
                                 attribute="held_by")])
    w.ingest_structured([contain("obj:execution_page", "place:hall", t=3.0)])
    return w.locate("obj:execution_page")


def test_4_a_page_taken_and_dropped_reads_where_it_was_dropped(make_world):
    stub = Stub({("obj:execution_page", "in"): (CONSTITUTIVE, 0.7)})
    w, _ = make_world(stub)
    assert _flicker(w)[0] == "place:hall"


def test_4_without_the_demotion_the_page_flickers_back_to_the_book(make_world, monkeypatch):
    """The old rule, simulated: no floor. The page's first `in` is CONSTITUTIVE and
    outranks every later move."""
    monkeypatch.setattr(classify_module, "CONTAINMENT_CONSTITUTIVE_FLOOR", 0.0)
    stub = Stub({("obj:execution_page", "in"): (CONSTITUTIVE, 0.7)})
    w, _ = make_world(stub)
    assert _flicker(w)[0] == "obj:book"


# ====================================================== 5. the prompt text


def test_5_both_prompts_carry_the_new_sentence_and_not_the_old_one(make_world):
    stub = Stub({("obj:cup", "in"): (STATE, 0.9)})
    w, _ = make_world(stub)
    w.ingest_structured([contain("obj:cup", "obj:shelf")])                       # per-row
    w.ingest_structured([contain("obj:cup", "obj:table", t=2.0)], classify="batch")  # batch
    per_row = stub.prompts[TASK_CLASSIFY]
    batch = stub.prompts[TASK_CLASSIFY_BATCH]
    assert per_row and batch
    for prompt in per_row + batch:
        assert NEW_SENTENCE in prompt
        assert "ambiguous fixture containment" not in prompt.lower()
        assert "fixture containment -> constitutive" not in prompt.lower()


# ====================================================== 6. construct's corpus


def _corpus():
    return json.loads(CORPUS.read_text())


FLOOR = CONTAINMENT_CONSTITUTIVE_FLOOR
NAMED = {("obj:execution_page", "obj:book"), ("obj:split_seal", "obj:execution_page"),
         ("obj:wedge", "obj:fall_board")}



def _replay_audit(make_world):
    """Feed the audit's `in` rows (each stored CONSTITUTIVE by run 10) through a
    fake model that returns the archived verdict: CONSTITUTIVE at the archived
    confidence, in log order. Returns (rows, the stored classes)."""
    rows = _corpus()["audit_failures"]
    queue: dict[tuple[str, str], list[float]] = {}
    for r in rows:
        queue.setdefault((r["entity"], r["value"]), []).append(r["confidence"])

    def model(prompt, schema):
        subject = value = ""
        for line in prompt.splitlines():
            if line.startswith("Subject: "):
                subject = line.removeprefix("Subject: ")
            elif line.startswith("Value: "):
                value = json.loads(line.removeprefix("Value: "))
        return {"durability": CONSTITUTIVE,
                "class_confidence": queue[(subject, value)].pop(0)}

    w, _ = make_world(model, "audit")
    stored = []
    for n, r in enumerate(rows):
        got = w.ingest_structured([contain(r["entity"], r["value"], t=float(n + 1))])
        assert got and w.ingestor.last_skipped == [], r
        stored.append(verdict(w, got[0]))
    return rows, stored


def test_6_no_named_portable_object_ends_constitutive(make_world):
    """r1.5: every named portable object is STATE, including the verdicts that
    reached 0.9: `execution_page in book` (0.90, 0.92 in the probe), `execution_page
    in ledger` (0.93) and `wet_line` (0.90)."""
    rows, stored = _replay_audit(make_world)
    demoted = []
    for r, (dur, conf) in zip(rows, stored):
        assert conf == r["confidence"]                       # the confidence is always kept
        if r["entity"].startswith("place:"):
            assert dur == CONSTITUTIVE                        # a place's containment: unchanged
        elif r["confidence"] < FLOOR:
            assert dur == STATE, r
            demoted.append((r["entity"], r["value"], r["confidence"]))
        else:
            assert dur == CONSTITUTIVE, r
    for r, (dur, conf) in zip(rows, stored):
        if (r["entity"], r["value"]) in NAMED:
            assert dur == STATE, r
    survivors = {(r["entity"], r["value"]) for r, (dur, _) in zip(rows, stored)
                 if dur == CONSTITUTIVE and not r["entity"].startswith("place:")}
    assert not survivors & NAMED
    # the three the 0.9 floor left frozen are now STATE
    for key, confidence in ((("obj:execution_page", "obj:book"), 0.9),
                            (("obj:execution_page", "obj:ledger"), 0.93),
                            (("obj:wet_line", "obj:ledger"), 0.9)):
        assert any((r["entity"], r["value"], r["confidence"]) == (*key, confidence)
                   and dur == STATE for r, (dur, _) in zip(rows, stored)), key
    # the recorded evidence for the 0.95 default: 24 of the 30 object-subject rows
    assert len(demoted) == 24
    assert max(c for _, _, c in demoted) == 0.93
    print("demoted at 0.95:", sorted(demoted, key=lambda t: (t[2], t[0])))


def test_6_the_cell_window_and_the_barred_door_at_095_stay_constitutive(make_world):
    rows, stored = _replay_audit(make_world)
    window = [(dur, conf) for r, (dur, conf) in zip(rows, stored)
              if (r["entity"], r["value"]) == ("obj:slit_window", "place:cell_12")]
    assert window == [(CONSTITUTIVE, 0.96)]
    # the door's archived verdicts were 0.95, 0.90 and 0.84: only the first stays
    door = [(dur, conf) for r, (dur, conf) in zip(rows, stored)
            if (r["entity"], r["value"]) == ("obj:iron_barred_door", "place:cell_12")]
    assert door == [(CONSTITUTIVE, 0.95), (STATE, 0.9), (STATE, 0.84)]


@pytest.mark.parametrize("effort", ["low", "none"])
def test_6_the_batch_probe_replayed_through_classify_batch(make_world, effort):
    """The 12 archived batches (`in` rows only), each answered with the archived
    verdicts of one effort level, through the batch path."""
    batches = [bt for bt in _corpus()["batches"] if effort in bt]
    answers = {}
    for bt in batches:
        sig = tuple((r["entity"], r["value"]) for r in bt["rows"])
        answers[sig] = [v or {"durability": STATE, "class_confidence": 0.5}
                        for v in bt[effort]]

    def model(prompt, schema):
        facts = [m for m in (re.match(r"\d+\. (\S+) · in · \"(\S+)\"", ln)
                             for ln in prompt.splitlines()) if m]
        sig = tuple((m.group(1), m.group(2)) for m in facts)
        return {"verdicts": [{"index": i, **v} for i, v in enumerate(answers[sig])]}

    w, _ = make_world(model, effort)
    demoted = 0
    for t, bt in enumerate(batches, start=1):
        rows = w.ingest_structured([contain(r["entity"], r["value"], t=float(t * 100 + n))
                                    for n, r in enumerate(bt["rows"])], classify="batch")
        assert len(rows) == len(bt["rows"])
        for row, ans in zip(rows, bt[effort]):
            dur, conf = verdict(w, row)
            assert conf == ans["class_confidence"]
            if row.entity.startswith("place:"):
                continue
            if ans["durability"] == CONSTITUTIVE and conf < FLOOR:
                assert dur == STATE
                demoted += 1
            else:
                assert dur == ans["durability"]
    assert demoted > 0


# ====================================================== build library (r1.3, r1.4)

BOOK = {1: "The barred door stood in the cell. The page lay in the book.\n"}


def E(key, type_, names, anchor, **kw):
    return b.Entry(key=key, type=type_, names=names, anchor_quote=anchor, **kw)


def cast(*, door_fixture=True, reverse=False, door_type="object"):
    entries = [
        E("door", door_type, ["barred door"], "The barred door stood in the cell.",
          fixture=door_fixture),
        E("cell", "place", ["cell"], "The barred door stood in the cell."),
        E("page", "object", ["page"], "The page lay in the book."),
        E("book", "object", ["book"], "The page lay in the book."),
    ]
    return b.Manifest(entries=list(reversed(entries)) if reverse else entries)


class LineModel:
    """The extraction model: fixed lines for every chunk."""

    def __init__(self, lines, escapes=()):
        self.lines, self.escapes = list(lines), list(escapes)

    def __call__(self, prompt, schema):
        assert prompt.startswith(b.EXTRACT_HEAD)
        return {"lines": list(self.lines), "escapes": list(self.escapes), "picks": []}


LINES = ["s1|obj:barred_door|in|@place:cell", "s2|obj:page|in|@obj:book"]


def build_world(make_world, manifest, lines=LINES, *, name="w", world=None, stub=None,
                ingest_kwargs=None, escapes=()):
    reg = b.Registry.from_manifest(manifest, BOOK)
    results = b.extract(b.plan(BOOK, reg), reg, LineModel(lines, escapes))
    w, stub = (world, stub) if world is not None else make_world(stub, name)
    receipt = b.commit(w, reg, results, ingest_kwargs=ingest_kwargs)
    return reg, w, stub, receipt


def test_b_a_manifest_fixture_writes_a_host_row_before_any_chunk_fact(make_world):
    stub = Stub({("obj:page", "in"): (CONSTITUTIVE, 0.7)})
    reg, w, stub, receipt = build_world(make_world, cast(), stub=stub)
    assert receipt.skipped == ()
    declared = [r for r in w.buffer.all_rows() if r.attribute == "fixture"]
    assert [(r.entity, r.value, r.value_type, r.frame, r.valid_from, r.status)
            for r in declared] == [("obj:barred_door", True, "literal", "canon", None, "stated")]
    chunk_facts = [r for r in w.buffer.all_rows() if r.attribute == "in"]
    assert declared[0].seq < min(r.seq for r in chunk_facts)
    shapes = [r for r in w.buffer.all_rows()
              if r.entity == "obj:barred_door" and r.attribute == "kind"]
    assert shapes[0].seq < declared[0].seq                    # after the entry's shape rows
    # its containment row: the fixture guardrail, no model call
    door_in = the_row(w, "obj:barred_door", "in")
    assert verdict(w, door_in) == (CONSTITUTIVE, 1.0)
    assert ("obj:barred_door", "in") not in stub.classify_calls
    # the unannounced page goes to the model and the floor
    assert ("obj:page", "in") in stub.classify_calls
    assert verdict(w, the_row(w, "obj:page", "in")) == (STATE, 0.7)


def test_b_the_fixture_row_is_written_with_host_authority_whatever_ingest_kwargs_say(make_world):
    reg, w, stub, receipt = build_world(make_world, cast(), ingest_kwargs={"extracted": True})
    assert "fixture_not_host" not in [s["reason"] for s in receipt.skipped]
    assert [r.entity for r in w.buffer.all_rows() if r.attribute == "fixture"] == [
        "obj:barred_door"]


def test_b_no_fixture_entry_writes_no_fixture_row(make_world):
    reg, w, stub, receipt = build_world(make_world, cast(door_fixture=False))
    assert [r for r in w.buffer.all_rows() if r.attribute == "fixture"] == []


def test_b_a_place_may_be_a_fixture(make_world):
    m = b.Manifest(entries=[
        E("cell", "place", ["cell"], "The barred door stood in the cell.", fixture=True),
        E("door", "object", ["barred door"], "The barred door stood in the cell.")])
    reg, w, stub, receipt = build_world(make_world, m, lines=["s1|obj:barred_door|in|@place:cell"])
    assert [r.entity for r in w.buffer.all_rows() if r.attribute == "fixture"] == ["place:cell"]


def test_b_r1_3_fixture_on_a_being_is_refused_by_validate():
    m = b.Manifest(entries=[E("mara", "person", ["Mara"], "Mara ran.", fixture=True)])
    with pytest.raises(b.ManifestError) as err:
        m.validate({1: "Mara ran.\n"})
    assert [p["code"] for p in err.value.problems] == ["fixture_on_being"]
    for being in ("animal", "creature"):
        problems = b.Manifest(entries=[E("x", being, ["Mara"], "Mara ran.", fixture=True)]
                              ).problems({1: "Mara ran.\n"})
        assert [p["code"] for p in problems] == ["fixture_on_being"]
    # fixture=False on a being is just the default
    assert b.Manifest(entries=[E("mara", "person", ["Mara"], "Mara ran.", fixture=False)]
                      ).problems({1: "Mara ran.\n"}) == []


def test_b_a_group_or_event_cannot_be_a_fixture():
    for kind in ("group", "event"):
        problems = b.Manifest(entries=[E("x", kind, ["Mara"], "Mara ran.", fixture=True)]
                              ).problems({1: "Mara ran.\n"})
        assert [p["code"] for p in problems] == ["fixture_not_allowed"], kind


@pytest.mark.parametrize("bad", ["yes", "true", 1, 0, None, 1.0, [True]])
def test_b_r1_4_fixture_must_be_a_real_bool(bad):
    problems = b.Manifest(entries=[E("door", "object", ["Mara"], "Mara ran.", fixture=bad)]
                          ).problems({1: "Mara ran.\n"})
    assert [(p["where"], p["code"]) for p in problems] == [("entries[0].fixture",
                                                           "fixture_not_bool")]
    with pytest.raises(b.ManifestError):
        b.Registry.from_manifest(b.Manifest(entries=[
            E("door", "object", ["Mara"], "Mara ran.", fixture=bad)]), {1: "Mara ran.\n"})


def test_b_r1_4_fixture_problems_list_with_the_others_in_one_error():
    m = b.Manifest(entries=[
        E("a", "object", ["Mara"], "Mara ran.", fixture="yes"),
        E("b", "person", ["Mara"], "Not in the text.", fixture=True)])
    with pytest.raises(b.ManifestError) as err:
        m.validate({1: "Mara ran.\n"})
    assert {p["code"] for p in err.value.problems} == {
        "fixture_not_bool", "fixture_on_being", "quote_not_found"}


def test_b_r1_4_a_fixture_manifest_survives_json_and_commits_the_same_world(make_world):
    manifest = cast()
    data = json.loads(json.dumps(manifest.to_dict()))
    assert [e["fixture"] for e in data["entries"]] == [True, False, False, False]
    back = b.Manifest.from_dict(data)
    assert back == manifest
    _, first, _, _ = build_world(make_world, manifest, name="first")
    _, second, _, _ = build_world(make_world, back, name="second")
    assert dump(first.buffer) == dump(second.buffer)


def test_b_r1_4_a_manifest_written_before_this_change_still_loads(make_world):
    data = cast().to_dict()
    for e in data["entries"]:
        del e["fixture"]
    old = b.Manifest.from_dict(data)
    assert [e.fixture for e in old.entries] == [False] * 4
    assert old == cast(door_fixture=False)


def test_b_r1_4_entries_report_fixture_and_the_row_follows_the_id_not_the_position(make_world):
    reg = b.Registry.from_manifest(cast(), BOOK)
    assert {e["id"]: e["fixture"] for e in reg.entries()} == {
        "obj:barred_door": True, "place:cell": False, "obj:page": False, "obj:book": False}
    assert reg.identity("obj:barred_door").fixture is True
    assert reg.identity("obj:page").fixture is False
    # reordering the manifest's entries still declares the right id
    _, w, _, _ = build_world(make_world, cast(reverse=True), name="reversed")
    assert [r.entity for r in w.buffer.all_rows() if r.attribute == "fixture"] == [
        "obj:barred_door"]
    # two same-slug objects: the second gets `_2`; the flag follows the second one
    m = b.Manifest(entries=[
        E("a", "object", ["lamp"], "The lamp hung high."),
        E("c", "object", ["lamp"], "A second lamp hung low.", fixture=True)])
    text = {1: "The lamp hung high. A second lamp hung low.\n"}
    reg2 = b.Registry.from_manifest(m, text)
    assert {e["id"]: e["fixture"] for e in reg2.entries()} == {
        "obj:lamp": False, "obj:lamp_2": True}


def test_b_r1_3_a_model_line_with_attribute_fixture_never_leaves_extract(make_world):
    reg = b.Registry.from_manifest(cast(), BOOK)
    results = b.extract(b.plan(BOOK, reg), reg,
                        LineModel(["s2|obj:page|fixture|true|t"]))
    assert all(not r.items for r in results)
    assert [x.reason for r in results for x in r.refused] == ["malformed_line"]
    assert "fixture" in results[0].refused[0].detail


def test_b_r1_3_a_world_alias_cannot_carry_a_model_guess_past_commit(make_world):
    stub = Stub({("obj:page", "in"): (CONSTITUTIVE, 0.7)})
    w, _ = make_world(stub, "aliased")
    w.ingestor.add_attribute_alias("fixed", "fixture")
    assert w.canonical_attribute("fixed") == "fixture"
    reg = b.Registry.from_manifest(cast(door_fixture=False), BOOK)
    results = b.extract(b.plan(BOOK, reg), reg,
                        LineModel(["s2|obj:page|fixed|true|t", "s2|obj:page|in|@obj:book"]))
    assert any(r.items for r in results)                       # extract itself accepts the alias
    before = dump(w.buffer)
    with pytest.raises(CommitRefused, match="fixture"):
        b.commit(w, reg, results)
    assert dump(w.buffer) == before                            # the world is unchanged
    # a later containment row goes to the model and the floor, not the guardrail
    row = w.ingest_structured([contain("obj:page", "obj:book")])[0]
    assert ("obj:page", "in") in stub.classify_calls
    assert verdict(w, row) == (STATE, 0.7)


def test_b_r1_3_the_alias_check_also_covers_facts_on_escape_handles(make_world):
    w, _ = make_world(Stub(), "escape")
    w.ingestor.add_attribute_alias("fixed", "fixture")
    reg = b.Registry.from_manifest(cast(door_fixture=False), BOOK)
    escapes = [{"handle": "new:1", "name": "the shelf", "type": "object",
                "quote": "The page lay in the book."}]
    results = b.extract(b.plan(BOOK, reg), reg,
                        LineModel(["s2|new:1|fixed|true|t"], escapes))
    assert any(r.items for r in results)
    before = dump(w.buffer)
    with pytest.raises(CommitRefused, match="fixture"):
        b.commit(w, reg, results)
    assert dump(w.buffer) == before


def test_b_without_an_alias_a_world_that_never_heard_of_fixed_commits_the_literal(make_world):
    """The check is about canonicalization, not the word: `fixed` with no alias is
    an ordinary attribute."""
    w, _ = make_world(Stub(), "plain")
    reg, w, _, receipt = build_world(
        make_world, cast(door_fixture=False),
        lines=["s2|obj:page|fixed|true|t", "s2|obj:page|in|@obj:book"], world=w, stub=Stub())
    assert [r.value for r in w.buffer.all_rows() if r.attribute == "fixed"] == [True]
    assert [r for r in w.buffer.all_rows() if r.attribute == "fixture"] == []


def test_b_grammar_problem_keeps_its_literal_refusal_first():
    sentence, item = parse_line("s1|obj:page|fixture|false|t")
    assert "fixture" in grammar_problem(item)
