"""PERSON-ROLES-V1 (R49): a person is a person for life; what they are at a time
is a role.

One test (or group) per numbered test of specs/PERSON-ROLES-V1.md (1, 1a, 2-10;
10 is the full suite and is run, not written here). Invented names only; no
host world and no player text."""

from __future__ import annotations

import logging

import pytest

from patternbuffer import World, mirror, service
from patternbuffer import merge_gate as eg
from patternbuffer.dump import dump
from patternbuffer.ingest import (_BUILTIN_ALIASES, _EXTRACT_RULES_FULL,
                                  _EXTRACT_RULES_LEAN)
from patternbuffer.model import (META_ATTRIBUTES, SET_VALUED_ATTRIBUTES,
                                 TaskSchema)
from patternbuffer.semantics import builtin_default
from patternbuffer.testing import StubModel, rule_classifier_fallback

RULE = (
    "- a person's 'kind' is always 'person'. What they are at a time "
    "(prisoner, captain, widow, hero) is 'role', with valid_from when it "
    "begins and valid_to when the text ends it; a person can hold several "
    "roles at once.\n"
)


def item(entity, attribute, value, **kw):
    out = {"entity": entity, "attribute": attribute, "value": value,
           "status": "stated"}
    out.update(kw)
    return out


def make_world(tmp_path, name="w", model=None):
    return World(tmp_path / f"{name}.world", world_id=f"w:{name}",
                 model=model or StubModel(fallback=rule_classifier_fallback()))


@pytest.fixture
def world(tmp_path):
    w = make_world(tmp_path)
    yield w
    w.close()


def rows_of(w, entity=None, attribute=None, frame=None):
    return [r for r in w.buffer.all_rows()
            if (entity is None or r.entity == entity)
            and (attribute is None or r.attribute == attribute)
            and (frame is None or r.frame == frame)]


def receipts_on(w, row_id):
    return sorted((r.attribute, r.value, r.status)
                  for r in w.buffer.all_rows() if r.entity == row_id)


# ------------------------------------------------------------ 0. the built-in


def test_role_is_a_set_valued_builtin():
    assert "role" in SET_VALUED_ATTRIBUTES
    assert builtin_default("role").arity == "set_valued"
    assert not builtin_default("role").structural
    assert {"reclassified_from", "derived_by"} <= META_ATTRIBUTES


# --------------------------------------------------------------- 1. the gate


def test_1_a_persons_non_person_kind_becomes_a_dated_role(world):
    world.ingest_structured([
        item("person:tomas", "kind", "Condemned Man", valid_from=1, valid_to=5),
    ])
    assert rows_of(world, "person:tomas", "kind") == rows_of(
        world, "person:tomas", "kind", "canon")
    roles = rows_of(world, "person:tomas", "role")
    assert len(roles) == 1
    role = roles[0]
    assert (role.value, role.status, role.valid_from, role.valid_to,
            role.frame) == ("Condemned Man", "stated", 1.0, 5.0, "canon")
    # the gate's own contextual receipt, and never a canonicalized_from
    assert receipts_on(world, role.id) == [("reclassified_from", "kind", "inferred")]
    assert not rows_of(world, attribute="canonicalized_from")
    # one timeless inferred kind = person, with its derivation receipt
    kinds = rows_of(world, "person:tomas", "kind")
    assert len(kinds) == 1
    kind = kinds[0]
    assert (kind.value, kind.status, kind.valid_from, kind.valid_to,
            kind.frame) == ("person", "inferred", None, None, "canon")
    assert receipts_on(world, kind.id) == [("derived_by", "person_subject", "inferred")]
    assert world.state("person:tomas", "kind").winner.value == "person"


def test_1_a_second_role_adds_no_second_kind_row(world):
    world.ingest_structured([
        item("person:tomas", "kind", "condemned man", valid_from=1, valid_to=5),
        item("person:tomas", "kind", "hero", valid_from=7),
    ])
    assert sorted(r.value for r in rows_of(world, "person:tomas", "role")) == [
        "condemned man", "hero"]
    assert len(rows_of(world, "person:tomas", "kind")) == 1
    assert len(rows_of(world, attribute="derived_by")) == 1


def test_1_the_items_status_is_kept_and_the_role_row_is_classified(world):
    world.ingest_structured([
        item("person:tomas", "kind", "traitor", status="assumed", valid_from=3),
        item("person:tomas", "kind", "spy", status="inferred", valid_from=4),
    ])
    roles = {r.value: r for r in rows_of(world, "person:tomas", "role")}
    assert roles["traitor"].status == "assumed" and roles["spy"].status == "inferred"
    assert all(world.classifier.get(r.id) is not None for r in roles.values())
    kind = rows_of(world, "person:tomas", "kind")[0]
    assert kind.status == "inferred"
    assert world.classifier.get(kind.id) is not None


def test_1_the_item_that_is_kind_person_is_stored_as_given(world):
    world.ingest_structured([item("person:tomas", "kind", " Person ")])
    assert [(r.attribute, r.value) for r in rows_of(world, "person:tomas")] == [
        ("kind", " Person ")]
    assert not rows_of(world, attribute="reclassified_from")
    assert not rows_of(world, attribute="derived_by")


def test_1_a_stated_kind_person_is_not_duplicated(world):
    world.ingest_structured([item("person:tomas", "kind", "person"),
                             item("person:tomas", "kind", "hero", valid_from=7)])
    kinds = rows_of(world, "person:tomas", "kind")
    assert [(r.value, r.status) for r in kinds] == [("person", "stated")]
    assert not rows_of(world, attribute="derived_by")


def test_1_the_identity_closure_decides_the_person(world):
    world.ingest_structured([
        item("obj:figure", "name", "the figure"),
        item("person:wren", "name", "Wren"),
    ])
    world.registry.merge("obj:figure", "person:wren", "same man")
    world.ingest_structured([item("obj:figure", "kind", "courier", valid_from=2)])
    head = world.registry.resolve("obj:figure")
    assert [r.value for r in rows_of(world, head, "role")] == ["courier"]
    assert not [r for r in rows_of(world, attribute="kind") if r.value == "courier"]


# ------------------------------------------------- 1a. the alias map is untouched


def test_1a_the_alias_map_is_untouched_and_survives_reopen(tmp_path):
    path = tmp_path / "a.world"
    w = World(path, world_id="w:a", model=StubModel(fallback=rule_classifier_fallback()))
    before = dict(w.ingestor._alias_map)
    assert before == dict(_BUILTIN_ALIASES)
    w.ingest_structured([
        item("person:x", "kind", "prisoner", valid_from=1),
        item("person:y", "type", "warden", valid_from=1),
        item("obj:lamp", "kind", "brass lamp"),
    ])
    x_role = rows_of(w, "person:x", "role")[0]
    y_role = rows_of(w, "person:y", "role")[0]
    # the `kind` item carries only the reclassification; the `type` item both
    assert receipts_on(w, x_role.id) == [("reclassified_from", "kind", "inferred")]
    assert receipts_on(w, y_role.id) == [
        ("canonicalized_from", "type->kind", "inferred"),
        ("reclassified_from", "kind", "inferred")]
    # a non-person kind is stored as kind, with no receipt
    lamp = rows_of(w, "obj:lamp", "kind")
    assert len(lamp) == 1 and lamp[0].value == "brass lamp"
    assert receipts_on(w, lamp[0].id) == []
    assert not rows_of(w, "obj:lamp", "role")
    assert w.ingestor.canonical_attribute("kind") == "kind"
    assert w.ingestor.canonical_attribute("type") == "kind"
    assert dict(w.ingestor._alias_map) == before
    w.close()

    reopened = World(path, world_id="w:a", model=StubModel(fallback=rule_classifier_fallback()))
    try:
        assert dict(reopened.ingestor._alias_map) == dict(_BUILTIN_ALIASES)
        assert "role" not in reopened.ingestor._alias_map.values()
        assert reopened.ingestor.canonical_attribute("kind") == "kind"
        assert reopened.ingestor.canonical_attribute("type") == "kind"
        assert reopened.ingestor.canonical_attribute("role") == "role"
    finally:
        reopened.close()


def test_1a_the_receipts_are_never_read_by_the_alias_machinery(tmp_path):
    """A forged `reclassified_from` / `derived_by` row installs no alias."""
    w = make_world(tmp_path, "forge")
    w.ingest_structured([item("person:x", "kind", "prisoner", valid_from=1)])
    role = rows_of(w, "person:x", "role")[0]
    w.buffer.append(entity=role.id, attribute="reclassified_from", value="tag->role",
                    status="inferred", role=w.ingestor._role)
    w.ingestor._rebuild_alias_map()
    assert w.ingestor._alias_map == dict(_BUILTIN_ALIASES)
    w.close()


def test_the_receipts_are_hidden_and_barred(world):
    world.ingest_structured([item("person:tomas", "kind", "hero", valid_from=7)])
    shown = world.porcelain.facts("canon", entity="person:tomas")
    assert {f["attribute"] for f in shown} == {"role", "kind"}
    every = world.porcelain.facts("canon", entity="person:tomas", include_meta=True)
    assert {f["attribute"] for f in every} == {"role", "kind"}
    role_id = rows_of(world, "person:tomas", "role")[0].id
    receipts = world.porcelain.facts("canon", entity=role_id)
    assert [f["attribute"] for f in receipts] == ["reclassified_from"]
    assert world.porcelain.facts("canon", entity=role_id, bookkeeping=False) == []
    for name in ("reclassified_from", "derived_by"):
        assert name in service._RECORD_BARRED_ATTRIBUTES
        assert name in mirror._PEOPLE_BARRED
        # bookkeeping by guardrail: EVENT without a model call
        receipt = rows_of(world, attribute=name)[0]
        world.classifier.classify(receipt)
        assert world.classifier.durability(receipt.id) == "EVENT"


# ----------------------------------------------------------------- 2. eras


def test_2_eras_read_from_state_as_of(world):
    world.ingest_structured([
        item("person:tomas", "kind", "prisoner", valid_from=1, valid_to=5),
        item("person:tomas", "kind", "hero", valid_from=7),
        item("person:tomas", "kind", "father", valid_from=2, valid_to=4),
    ])
    p = world.porcelain

    def held(at):
        r = p.state("person:tomas", "role", as_of=at)
        return r["status"], sorted(v["value"] for v in r.get("values", []))

    assert held(1) == ("known", ["prisoner"])
    assert held(3) == ("known", ["father", "prisoner"])        # overlapping roles
    assert held(4.5) == ("known", ["prisoner"])
    assert held(6) == ("unknown", [])                          # no role in force
    assert p.state("person:tomas", "role", as_of=6) == {"status": "unknown"}
    assert held(8) == ("known", ["hero"])
    # the whole life, every interval: facts
    life = {f["value"]: f["valid"] for f in
            p.facts("canon", entity="person:tomas", attribute="role")}
    assert life == {"prisoner": [1.0, 5.0], "hero": [7.0, None],
                    "father": [2.0, 4.0]}


# --------------------------------------------------- 3. non-persons unchanged


def test_3_non_persons_keep_their_kind_exactly(world):
    world.ingest_structured([
        item("obj:lamp", "kind", "brass lamp"),
        item("place:inn", "kind", "tavern"),
        item("event:x", "kind", "moved"),
    ])
    for entity, value in (("obj:lamp", "brass lamp"), ("place:inn", "tavern"),
                          ("event:x", "moved")):
        kinds = rows_of(world, entity, "kind")
        assert [(r.value, r.status) for r in kinds] == [(value, "stated")]
        assert receipts_on(world, kinds[0].id) == []
        assert not rows_of(world, entity, "role")
    assert not rows_of(world, attribute="reclassified_from")
    assert not rows_of(world, attribute="derived_by")


# ------------------------------------------------------------ 4. person by kind


def test_4_a_subject_whose_kind_already_folds_to_person_gets_a_role(world):
    world.ingest_structured([item("npc:smuggler", "kind", "person")])
    world.ingest_structured([item("npc:smuggler", "kind", "smuggler", valid_from=2)])
    assert [r.value for r in rows_of(world, "npc:smuggler", "role")] == ["smuggler"]
    assert [r.value for r in rows_of(world, "npc:smuggler", "kind")] == ["person"]
    assert not rows_of(world, attribute="derived_by")      # canon already had one


def test_4_inside_one_batch_the_order_of_items_decides(world):
    # kind = person first: the next kind in the same batch is a role
    world.ingest_structured([item("npc:fence", "kind", "person"),
                             item("npc:fence", "kind", "smuggler", valid_from=2)])
    assert [r.value for r in rows_of(world, "npc:fence", "role")] == ["smuggler"]
    # smuggler first: judged before kind = person arrives, so stored as given
    world.ingest_structured([item("npc:broker", "kind", "smuggler", valid_from=2),
                             item("npc:broker", "kind", "person")])
    assert not rows_of(world, "npc:broker", "role")
    assert sorted(r.value for r in rows_of(world, "npc:broker", "kind")) == [
        "person", "smuggler"]


def test_4_a_contested_kind_is_not_a_basis(world):
    world.ingest_structured([item("npc:ash", "kind", "smuggler", valid_from=1),
                             item("npc:ash", "kind", "person", valid_from=1)])
    assert world.state("npc:ash", "kind").conflicted
    world.ingest_structured([item("npc:ash", "kind", "pilot", valid_from=3)])
    assert not rows_of(world, "npc:ash", "role")


# --------------------------------------------------------------- 5. frames


def test_5_a_frame_gets_its_own_kind_person_and_canon_is_untouched(world):
    frame = "knows:person:mara"
    world.ingest_structured([item("person:tomas", "kind", "traitor", valid_from=4,
                                  frame=frame)])
    role = rows_of(world, "person:tomas", "role")[0]
    assert (role.frame, role.value) == (frame, "traitor")
    kind = rows_of(world, "person:tomas", "kind")
    assert [(r.frame, r.value, r.status) for r in kind] == [(frame, "person", "inferred")]
    assert not [r for r in rows_of(world, "person:tomas") if r.frame == "canon"]
    # once per subject and frame
    world.ingest_structured([item("person:tomas", "kind", "judge", valid_from=6,
                                  frame=frame)])
    assert len(rows_of(world, "person:tomas", "kind")) == 1
    # a canon item adds canon's own
    world.ingest_structured([item("person:tomas", "kind", "hero", valid_from=7)])
    assert sorted((r.frame, r.value) for r in rows_of(world, "person:tomas", "kind")) == [
        ("canon", "person"), (frame, "person")]


# ------------------------------------------------------------- 6. identity


def _model_double(answers=None):
    answers = answers or {}

    def model(prompt, schema):
        assert isinstance(schema, TaskSchema) and schema["title"] == "merge_gate"
        out = []
        for p in eg.batch_request(schema)["pairs"]:
            verdict = answers.get((p["a"]["id"], p["b"]["id"]), "unsure")
            out.append({"pair_id": p["pair_id"], "verdict": verdict, "reason": "r"})
        return {"verdicts": out}
    return model


A, B = "person:tomas_breck", "person:breck"


def _old_way(w):
    """The run-8 shape written directly, as the engine wrote it before R49."""
    rows = [
        (A, "name", "Tomas Breck"), (A, "alias", "Breck"),
        (A, "kind", "condemned man"),
        (B, "alias", "Breck"), (B, "name", "Mr. Breck"),
        (B, "kind", "person"),
    ]
    for entity, attribute, value in rows:
        row = w.buffer.append(entity=entity, attribute=attribute, value=value,
                              status="stated", role=w.ingestor._role)
        w.classifier.classify(row)


def _new_way(w):
    w.ingest_structured([
        item(A, "name", "Tomas Breck", timeless=True),
        item(A, "alias", "Breck", timeless=True),
        item(A, "kind", "condemned man", valid_from=1),
        item(B, "alias", "Breck", timeless=True),
        item(B, "name", "Mr. Breck", timeless=True),
        item(B, "kind", "person", timeless=True),
    ])


def test_6_a_run8_pair_was_a_kind_conflict_and_is_not_now(tmp_path):
    old = make_world(tmp_path, "old")
    _old_way(old)
    assert old.registry.decline_reason(A, B).startswith("kind_conflict")
    old.close()

    new = make_world(tmp_path, "new")
    _new_way(new)
    reason = new.registry.decline_reason(A, B)
    assert reason is None or not reason.startswith("kind_conflict")
    assert reason == "alias_not_specific"
    assert new.registry._kind_state(A, B) == "present_equal"
    new.close()


def test_6_merge_gate_lists_the_pair_as_askable(tmp_path):
    w = make_world(tmp_path, "gate")
    _new_way(w)
    w.ingestor._model = _model_double({(B, A): "unsure", (A, B): "unsure"})
    report = w.porcelain.merge_gate([[A, B]])
    assert report["status"] == "asked"
    assert report["not_asked"] == []
    assert len(report["pairs"]) == 1
    assert A in str(report["pairs"][0]) and B in str(report["pairs"][0])
    w.close()


def test_6_a_non_person_namespace_with_kind_person_is_still_askable(tmp_path):
    w = make_world(tmp_path, "ns")
    w.ingest_structured([
        item(A, "name", "Tomas Breck", timeless=True),
        item(A, "kind", "condemned man", valid_from=1),
        item("npc:breck", "name", "Breck", timeless=True),
        item("npc:breck", "kind", "person", timeless=True),
    ])
    w.ingestor._model = _model_double()
    report = w.porcelain.merge_gate([[A, "npc:breck"]])
    assert [e["status"] for e in report["not_asked"]] == []
    assert len(report["pairs"]) == 1
    w.close()


# -------------------------------------------------------------- 7. prompts


def test_7_both_prompts_carry_the_identical_rule():
    assert RULE in _EXTRACT_RULES_FULL
    assert RULE in _EXTRACT_RULES_LEAN
    assert _EXTRACT_RULES_FULL.count(RULE) == _EXTRACT_RULES_LEAN.count(RULE) == 1
    assert "'kind' for what a thing is" in _EXTRACT_RULES_FULL
    assert "'kind' for what a thing is" in _EXTRACT_RULES_LEAN


# ------------------------------------------------------- 8. existing worlds


def test_8_a_world_built_before_the_change_reads_byte_identically(tmp_path):
    path = tmp_path / "old.world"
    w = World(path, world_id="w:old", model=StubModel(fallback=rule_classifier_fallback()))
    # the gate path bypassed: the rows are exactly what the old code wrote
    for entity, attribute, value, vf in (
            ("person:tomas", "kind", "condemned man", 1.0),
            ("person:tomas", "kind", "hero", 7.0),
            ("person:tomas", "kind", "person", None),
            ("obj:lamp", "kind", "brass lamp", None)):
        row = w.buffer.append(entity=entity, attribute=attribute, value=value,
                              valid_from=vf, status="stated", role=w.ingestor._role)
        w.classifier.classify(row)

    def reads(world):
        p = world.porcelain
        return (dump(world.buffer),
                [p.state("person:tomas", "kind", as_of=t) for t in (0, 2, 8)],
                p.facts("canon", entity="person:tomas"),
                p.state("person:tomas", "role"),
                world.registry.decline_reason("person:tomas", "obj:lamp"))
    before = reads(w)
    w.close()
    again = World(path, world_id="w:old", model=StubModel(fallback=rule_classifier_fallback()))
    try:
        assert reads(again) == before
        assert not rows_of(again, attribute="role")
        assert not rows_of(again, attribute="reclassified_from")
        assert len(rows_of(again, "person:tomas", "kind")) == 3     # kept as written
    finally:
        again.close()


# --------------------------------------------- 9. the entity-valued kind


def test_9_an_entity_valued_kind_on_a_person_is_left_alone_and_logged(world, caplog):
    with caplog.at_level(logging.WARNING, logger="patternbuffer.ingest"):
        world.ingest_structured([
            item("person:tomas", "kind", "obj:convict_type", value_type="entity")])
    kinds = rows_of(world, "person:tomas", "kind")
    assert [(r.value, r.value_type) for r in kinds] == [("obj:convict_type", "entity")]
    assert not rows_of(world, "person:tomas", "role")
    assert not rows_of(world, attribute="reclassified_from")
    assert not rows_of(world, attribute="derived_by")
    warned = [r for r in caplog.records if r.levelno == logging.WARNING
              and "PERSON-ROLES-V1" in r.getMessage()]
    assert len(warned) == 1 and "person:tomas" in warned[0].getMessage()


def test_9_the_entity_valued_kind_on_a_non_person_is_silent(world, caplog):
    with caplog.at_level(logging.WARNING, logger="patternbuffer.ingest"):
        world.ingest_structured([
            item("obj:lamp", "kind", "obj:lamp_type", value_type="entity")])
    assert not [r for r in caplog.records if "PERSON-ROLES-V1" in r.getMessage()]
