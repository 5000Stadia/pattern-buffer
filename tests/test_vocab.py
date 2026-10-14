"""RECIPE-VOCAB-V1 (r1.3): `patternbuffer.vocab`, the recipe vocabulary, and its
extraction prompt. Tests 1-5 of the spec's Tests section; lane 1 (the goldens) is
`tests/test_recipe_goldens.py`. No model is called: a model here is either a
stub scripted with nothing (any call raises) or the engine's rule fallback.
"""

from __future__ import annotations

import pytest

from patternbuffer import World, build as b
from patternbuffer.build.extract import EXTRACT_HEAD, _RULES, build_prompt
from patternbuffer.testing import StubModel, rule_classifier_fallback
from patternbuffer.vocab import (
    FINDING_KINDS, RECIPE, Term, Vocabulary, apply_aliases, attribute_default, check,
)

T0 = {"valid_from": 0}


def _world(tmp_path, name="v", *, vocabulary=RECIPE, aliases=True, model=None,
           fallback=None):
    """A world a host would open: attribute_default wired, aliases applied."""
    model = model or StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / f"{name}.world", world_id=f"w:{name}", model=model,
              attribute_default=(attribute_default(vocabulary, fallback)
                                 if vocabulary else None))
    if vocabulary and aliases:
        apply_aliases(w, vocabulary)
    return w


@pytest.fixture
def world(tmp_path):
    w = _world(tmp_path)
    yield w
    w.close()


@pytest.fixture
def bare(tmp_path):
    """A world opened without the vocabulary: rows land before declarations."""
    w = _world(tmp_path, "bare", vocabulary=None)
    yield w
    w.close()


def put(w, *items):
    receipt = w.porcelain.ingest_structured([{**T0, **i} for i in items])
    assert not receipt.skipped, receipt.skipped
    return receipt


def kinds(findings):
    return sorted(f.kind for f in findings)


def rows(w, entity, attribute):
    return [r for r in w.buffer.all_rows() if r.entity == entity and r.attribute == attribute]


# ----------------------------------------------- 1. Term and Vocabulary


def test_1_term_refusals_name_the_term():
    with pytest.raises(ValueError, match="'t'.*unknown value_type 'number'"):
        Term("t", "number")
    with pytest.raises(ValueError, match="'t'.*closed term needs its values"):
        Term("t", "literal", open_values=False)
    with pytest.raises(ValueError, match="'t'.*entity-valued term has no values"):
        Term("t", "entity", values=("a",))
    with pytest.raises(ValueError, match="'t'.*listed twice"):
        Term("t", "literal", values=("a", "a"))
    with pytest.raises(ValueError, match="'t'.*is not a valid declaration"):
        Term("t", "literal", semantics={"durability": "EVENT"})
    with pytest.raises(ValueError, match="'t'.*not a declarable semantics key"):
        Term("t", "literal", semantics={"mood": "x"})
    with pytest.raises(ValueError, match="'Not A Name'"):
        Term("Not A Name", "literal")
    with pytest.raises(ValueError, match="'t'.*alias 'Odd'"):
        Term("t", "literal", aliases=("Odd",))
    with pytest.raises(ValueError, match="'t'.*its own alias"):
        Term("t", "literal", aliases=("t",))


def test_1_vocabulary_refusals_name_the_pair():
    a = Term("a", "literal", aliases=("x",))
    with pytest.raises(ValueError, match="attribute 'a' is declared twice"):
        Vocabulary("v", (a, Term("a", "entity")))
    with pytest.raises(ValueError, match="alias 'x' is claimed by 'a' and 'b'"):
        Vocabulary("v", (a, Term("b", "literal", aliases=("x",))))
    with pytest.raises(ValueError, match="alias 'a' of 'b' is itself a term"):
        Vocabulary("v", (a, Term("b", "literal", aliases=("a",))))
    assert Vocabulary("v", (a,)).term("a") is a


def test_1_the_recipe_is_the_r1_3_table():
    by = {t.attribute: t for t in RECIPE.terms}
    assert list(by) == ["controls", "link_type", "control_mode", "state", "locked", "lit",
                        "outdoors", "exits", "disposition", "code"]
    assert RECIPE.alias_map() == {
        "operates": "controls", "powers": "controls", "control_type": "link_type",
        "switch_mode": "control_mode", "light_level": "lit", "lighting": "lit",
        "illumination": "lit", "is_outdoors": "outdoors", "temperament": "disposition",
        "demeanor": "disposition", "demeanour": "disposition", "passcode": "code",
        "combination": "code"}
    # the exclusions: hosts' own words, a thing's name, other meanings, entity-valued in the wild
    for taken in ("status", "mode", "light", "works", "opens", "outside", "exit", "way_out", "pin"):
        assert taken not in RECIPE.alias_map() and taken not in by
    assert by["controls"].semantics == {"arity": "set_valued", "durability": "CONSTITUTIVE"}
    assert by["controls"].value_type == "entity"
    assert by["locked"].semantics == {"durability": "STATE"}
    assert by["locked"].values == (True, False) and not by["locked"].open_values
    assert by["outdoors"].values == (True, False)
    assert by["control_mode"].values == ("latching", "momentary")
    assert by["state"].open_values and "locked" not in by["state"].values
    assert by["state"].semantics == {}
    assert by["exits"].values == ("none",) and not by["exits"].open_values
    assert by["disposition"].semantics == {"durability": "DISPOSITIONAL"}
    assert by["lit"].values == ("dark", "dim", "lit", "day", "night")
    assert by["link_type"].values == ("switch", "lever", "plate", "button", "keypad", "dial")


# --------------------------------------------------- 2. attribute_default


def test_2_controls_declares_before_its_row_and_classifies_with_no_model_call(tmp_path):
    silent = StubModel()                     # any model call raises
    w = _world(tmp_path, model=silent)
    try:
        put(w, {"entity": "obj:switch", "attribute": "controls", "value": "obj:light"})
        arity = rows(w, "attr:controls", "arity")[0]
        pin = rows(w, "attr:controls", "durability")[0]
        data = rows(w, "obj:switch", "controls")[0]
        assert arity.value == "set_valued" and pin.value == "CONSTITUTIVE"
        assert arity.seq < pin.seq < data.seq
        verdict = w.classifier.get(data.id)
        assert (verdict.durability, verdict.class_confidence) == ("CONSTITUTIVE", 1.0)
        assert silent.calls == []
        assert w.semantics.is_set_valued("controls")
    finally:
        w.close()


def test_2_disposition_pins_dispositional(world):
    put(world, {"entity": "person:dog", "attribute": "disposition", "value": "friendly"})
    assert rows(world, "attr:disposition", "durability")[0].value == "DISPOSITIONAL"
    verdict = world.classifier.get(rows(world, "person:dog", "disposition")[0].id)
    assert (verdict.durability, verdict.class_confidence) == ("DISPOSITIONAL", 1.0)


def test_2_a_term_with_no_semantics_declares_nothing(world):
    put(world, {"entity": "obj:light", "attribute": "state", "value": "off"})
    assert rows(world, "attr:state", "durability") == []
    assert [r for r in world.buffer.all_rows() if r.entity == "attr:state"] == []


def test_2_a_non_term_falls_through_to_the_hosts_fallback(tmp_path):
    asked = []

    def host(attribute):
        asked.append(attribute)
        return {"durability": "STATE"} if attribute == "arc_status" else None

    default = attribute_default(RECIPE, host)
    assert default("controls") == {"arity": "set_valued", "durability": "CONSTITUTIVE"}
    assert asked == []                                   # a term never asks the host
    assert default("arc_status") == {"durability": "STATE"}
    assert default("rung") is None
    assert asked == ["arc_status", "rung"]
    assert attribute_default(RECIPE)("rung") is None     # and no fallback is fine
    default("controls")["arity"] = "functional"           # a caller's dict is its own
    assert default("controls")["arity"] == "set_valued"

    w = _world(tmp_path, "fallback", fallback=host)
    try:
        put(w, {"entity": "arc:main", "attribute": "arc_status", "value": "open"})
        assert rows(w, "attr:arc_status", "durability")[0].value == "STATE"
    finally:
        w.close()


# ------------------------------------------------------ 3. apply_aliases


def test_3_an_alias_canonicalizes_with_the_gates_receipt(world):
    assert world.canonical_attribute("Temperament") == "disposition"
    receipt = put(world, {"entity": "person:dog", "attribute": "temperament", "value": "friendly"})
    assert world.porcelain.state("person:dog", "disposition")["fact"]["value"] == "friendly"
    assert rows(world, "person:dog", "temperament") == []
    assert receipt.canonicalization_receipts == ["temperament->disposition"]
    assert world.porcelain.state("person:dog", "temperament")["status"] == "known"


def test_3_an_inverse_key_as_an_alias_raises_naming_the_pair(tmp_path):
    v = Vocabulary("odd", (Term("carrier", "entity", aliases=("holds",)),))
    w = _world(tmp_path, vocabulary=None)
    try:
        with pytest.raises(ValueError, match="alias 'holds' -> 'carrier'.*inverse relation"):
            apply_aliases(w, v)
        assert w.canonical_attribute("holds") == "holds"
    finally:
        w.close()


def test_3_an_alias_that_already_maps_elsewhere_raises(tmp_path):
    v = Vocabulary("odd", (Term("place_of", "entity", aliases=("location",)),))
    w = _world(tmp_path, vocabulary=None)
    try:
        with pytest.raises(ValueError, match="alias 'location' -> 'place_of'.*already maps 'location' to 'in'"):
            apply_aliases(w, v)
    finally:
        w.close()


def test_3_applying_twice_and_after_a_reopen_is_idempotent(tmp_path):
    w = _world(tmp_path, "reopen")
    put(w, {"entity": "person:dog", "attribute": "temperament", "value": "friendly"})
    apply_aliases(w, RECIPE)
    assert w.canonical_attribute("passcode") == "code"
    w.close()
    again = World(tmp_path / "reopen.world", world_id="w:reopen",
                  model=StubModel(fallback=rule_classifier_fallback()),
                  attribute_default=attribute_default(RECIPE))
    try:
        # only the alias the gate applied is rebuilt from its receipt
        assert again.canonical_attribute("temperament") == "disposition"
        assert again.canonical_attribute("passcode") == "passcode"
        apply_aliases(again, RECIPE)
        apply_aliases(again, RECIPE)
        assert again.canonical_attribute("passcode") == "code"
        assert again.canonical_attribute("temperament") == "disposition"
    finally:
        again.close()


# ----------------------------------------------------------------- 4. check


def test_4_a_clean_world_has_no_findings(world):
    put(world,
        {"entity": "obj:switch", "attribute": "controls", "value": "obj:light"},
        {"entity": "obj:switch", "attribute": "link_type", "value": "switch"},
        {"entity": "obj:switch", "attribute": "control_mode", "value": "latching"},
        {"entity": "obj:light", "attribute": "state", "value": "off"},
        {"entity": "obj:light", "attribute": "state", "value": "off-ish-custom"},  # open term
        {"entity": "place:room", "attribute": "lit", "value": "dark"},
        {"entity": "place:room", "attribute": "exits", "value": "none"},
        {"entity": "place:outside", "attribute": "outdoors", "value": True, "timeless": True},
        {"entity": "person:dog", "attribute": "disposition", "value": "ferocious"},  # open
        {"entity": "obj:keypad", "attribute": "code", "value": "4071"},
        {"entity": "obj:door", "attribute": "locked", "value": True},
        {"entity": "obj:door", "attribute": "state", "value": "shut"})
    assert check(world, RECIPE) == []


def test_4_off_vocabulary_wrong_type_and_alias_findings(bare):
    put(bare,
        {"entity": "obj:switch", "attribute": "link_type", "value": "toggle"},
        {"entity": "place:outside", "attribute": "outdoors", "value": "true"},
        {"entity": "obj:switch", "attribute": "controls", "value": "the light", "value_type": "literal"},
        {"entity": "obj:switch", "attribute": "control_mode", "value": "obj:other", "value_type": "entity"},
        {"entity": "person:dog", "attribute": "temperament", "value": "friendly"})
    found = check(bare, RECIPE)
    by_kind = {k: [f for f in found if f.kind == k] for k in set(kinds(found))}
    assert [(f.entity, f.attribute, f.value) for f in by_kind["off_vocabulary_value"]] == [
        ("obj:switch", "link_type", "toggle"), ("place:outside", "outdoors", "true")]
    assert sorted((f.entity, f.attribute) for f in by_kind["wrong_value_type"]) == [
        ("obj:switch", "control_mode"), ("obj:switch", "controls")]
    assert [(f.entity, f.attribute, f.value) for f in by_kind["alias_in_log"]] == [
        ("person:dog", "temperament", "friendly")]
    assert "disposition" in by_kind["alias_in_log"][0].detail
    # a boolean term is closed to the booleans, not to their spellings
    assert not any(f.attribute == "link_type" for f in by_kind["wrong_value_type"])


def test_4_undeclared_semantics_when_rows_came_first(bare):
    put(bare, {"entity": "obj:switch", "attribute": "controls", "value": "obj:light"},
        {"entity": "person:dog", "attribute": "disposition", "value": "friendly"},
        {"entity": "obj:light", "attribute": "state", "value": "off"})
    found = [f for f in check(bare, RECIPE) if f.kind == "undeclared_semantics"]
    assert [f.attribute for f in found] == ["controls", "disposition"]
    assert "CONSTITUTIVE" in found[0].detail and found[0].entity is None


def test_4_declaring_after_the_rows_does_not_take_and_is_named(tmp_path):
    w = _world(tmp_path, "late", vocabulary=None)
    try:
        put(w, {"entity": "person:dog", "attribute": "disposition", "value": "friendly"})
        assert kinds(check(w, RECIPE)) == ["undeclared_semantics"]
        with pytest.raises(ValueError):          # the engine's declare-before-data rule
            w.porcelain.ingest_structured([{
                "entity": "attr:disposition", "attribute": "durability",
                "value": "DISPOSITIONAL", "timeless": True}])
        assert len(check(w, RECIPE)) == 1
    finally:
        w.close()


def test_4_exits_none_with_an_edge_is_served_as_written_and_reported(world):
    put(world, {"entity": "place:room", "attribute": "exits", "value": "none"},
        {"entity": "obj:door", "attribute": "connects_to", "value": "place:room"})
    assert world.porcelain.state("place:room", "exits")["fact"]["value"] == "none"
    found = check(world, RECIPE)
    assert [(f.kind, f.entity) for f in found] == [("exits_none_with_edge", "place:room")]
    # an edge elsewhere does not count, and an ended edge does not either
    quiet = [f for f in check(world, RECIPE) if f.entity != "place:room"]
    assert quiet == []


def test_4_an_ended_edge_is_not_a_way_out(world):
    put(world, {"entity": "place:room", "attribute": "exits", "value": "none"},
        {"entity": "place:room", "attribute": "connects_to", "value": "place:hall",
         "valid_from": 0, "valid_to": 5})
    assert check(world, RECIPE) == []


def _door(world, *items):
    put(world, {"entity": "obj:door", "attribute": "kind", "value": "door", "timeless": True},
        *items)
    return check(world, RECIPE)


def test_4_state_locked_alone_is_the_legacy_spelling(world):
    found = _door(world, {"entity": "obj:door", "attribute": "state", "value": "locked"})
    assert [(f.kind, f.entity, f.value) for f in found] == [("state_locked_legacy", "obj:door", "locked")]


def test_4_locked_with_no_state_is_missing(world):
    found = _door(world, {"entity": "obj:door", "attribute": "locked", "value": True})
    assert [(f.kind, f.entity) for f in found] == [("locked_state_missing", "obj:door")]


def test_4_locked_with_a_conflicted_state_is_missing(world):
    found = _door(world, {"entity": "obj:door", "attribute": "locked", "value": True},
                  {"entity": "obj:door", "attribute": "state", "value": "shut"},
                  {"entity": "obj:door", "attribute": "state", "value": "open"})
    assert world.porcelain.state("obj:door", "state")["status"] == "conflicted"
    assert [f.kind for f in found] == ["locked_state_missing"]


def test_4_locked_with_another_state_is_not_shut(world):
    found = _door(world, {"entity": "obj:door", "attribute": "locked", "value": True},
                  {"entity": "obj:door", "attribute": "state", "value": "ajar"})
    assert [(f.kind, f.value) for f in found] == [("locked_not_shut", "ajar")]


def test_4_locked_but_open(world):
    found = _door(world, {"entity": "obj:door", "attribute": "locked", "value": True},
                  {"entity": "obj:door", "attribute": "state", "value": "open"})
    assert [(f.kind, f.value) for f in found] == [("locked_but_open", "open")]


def test_4_the_folded_pair_is_judged_at_the_head(world):
    """Locked, shut, then unlocked and opened later: the head is clean; a stale
    `state · open` under a still-locked door is not."""
    found = _door(world,
                  {"entity": "obj:door", "attribute": "locked", "value": True, "valid_from": 0},
                  {"entity": "obj:door", "attribute": "state", "value": "shut", "valid_from": 0},
                  {"entity": "obj:door", "attribute": "locked", "value": False, "valid_from": 2},
                  {"entity": "obj:door", "attribute": "state", "value": "open", "valid_from": 2})
    assert found == []
    found = _door(world, {"entity": "obj:door", "attribute": "locked", "value": True, "valid_from": 3})
    assert [f.kind for f in found] == ["locked_but_open"]


def test_4_shut_and_locked_is_clean_and_blocks_the_route(world):
    put(world,
        {"entity": "traversal:door", "attribute": "blocks_when_state", "value": "shut",
         "timeless": True},
        {"entity": "obj:door", "attribute": "kind", "value": "door", "timeless": True},
        {"entity": "obj:door", "attribute": "locked", "value": True},
        {"entity": "obj:door", "attribute": "state", "value": "shut"},
        {"entity": "place:a", "attribute": "connects_to", "value": "obj:door", "timeless": True},
        {"entity": "obj:door", "attribute": "connects_to", "value": "place:b", "timeless": True})
    assert check(world, RECIPE) == []
    route = world.route("place:a", "place:b")
    assert route["status"] == "blocked"
    assert route["route"] == ["place:a", "obj:door", "place:b"]


def test_4_the_checks_that_name_attributes_need_those_terms(world):
    small = Vocabulary("small", (Term("code", "literal"),))
    put(world, {"entity": "obj:door", "attribute": "locked", "value": True},
        {"entity": "obj:door", "attribute": "state", "value": "locked"})
    assert check(world, small) == []


def test_4_check_reads_the_frame_it_is_given(world):
    put(world, {"entity": "obj:keypad", "attribute": "code", "value": "4071",
                "frame": "knows:person:dog"},
        {"entity": "obj:switch", "attribute": "link_type", "value": "toggle",
         "frame": "knows:person:dog"})
    assert check(world, RECIPE) == []
    assert kinds(check(world, RECIPE, frame="knows:person:dog")) == ["off_vocabulary_value"]


def test_4_check_writes_nothing_and_calls_no_model(tmp_path):
    silent = StubModel(fallback=rule_classifier_fallback())
    w = _world(tmp_path, "ro", vocabulary=None, model=silent)
    try:
        put(w, {"entity": "obj:door", "attribute": "locked", "value": True},
            {"entity": "person:dog", "attribute": "temperament", "value": "x"},
            {"entity": "place:room", "attribute": "exits", "value": "none"},
            {"entity": "obj:switch", "attribute": "link_type", "value": "toggle"})
        head, calls = w.buffer.head(), len(silent.calls)
        found = check(w, RECIPE)
        assert len(found) >= 4
        assert w.buffer.head() == head and len(silent.calls) == calls
        assert set(kinds(found)) <= set(FINDING_KINDS)
    finally:
        w.close()


def test_4_every_named_finding_kind_is_reachable(tmp_path):
    """The nine kinds of the spec, each produced by some hand-built world above."""
    w = _world(tmp_path, "all", vocabulary=None)
    try:
        put(w,
            {"entity": "obj:s", "attribute": "link_type", "value": "toggle"},        # off_vocabulary
            {"entity": "obj:s", "attribute": "controls", "value": "lit", "value_type": "literal"},  # wrong type
            {"entity": "person:dog", "attribute": "temperament", "value": "friendly"},   # alias in log
            {"entity": "place:room", "attribute": "exits", "value": "none"},
            {"entity": "place:room", "attribute": "connects_to", "value": "place:hall"},
            {"entity": "obj:d1", "attribute": "locked", "value": True},                  # missing
            {"entity": "obj:d2", "attribute": "locked", "value": True},
            {"entity": "obj:d2", "attribute": "state", "value": "open"},                 # but open
            {"entity": "obj:d3", "attribute": "locked", "value": True},
            {"entity": "obj:d3", "attribute": "state", "value": "ajar"},                 # not shut
            {"entity": "obj:d4", "attribute": "state", "value": "locked"})               # legacy
        assert set(kinds(check(w, RECIPE))) == set(FINDING_KINDS)    # undeclared_semantics too
    finally:
        w.close()


# ------------------------------------------------- 5. the extract prompt


def _registry():
    text = {1: "Mara rowed to the mill. The mill stood quiet."}
    manifest = b.Manifest([b.Entry("mara", "person", ["Mara"], "Mara rowed to the mill."),
                           b.Entry("mill", "place", ["the mill"], "The mill stood quiet.")])
    reg = b.Registry.from_manifest(manifest, text)
    return reg, b.plan(text, reg)


def _prompt_as_it_was(chunk, book):
    """`build_prompt` as it read before RECIPE-VOCAB-V1 (BUILD-LIBRARY-V1 r1.9.1)."""
    rows = []
    for c in chunk.candidates:
        kind = f"{c.type}, {c.species}" if c.species else c.type
        rows.append(f"{c.id} | {kind} | {'; '.join(c.names)} | from s{c.gate}")
    passage = book.numbered(chunk.chapter, chunk.first_sentence, chunk.last_sentence)
    return (f"{EXTRACT_HEAD}\n\n{_RULES}\n\n"
            "CANDIDATES (id | type | names | gate):\n"
            + ("\n".join(rows) if rows else "(none)")
            + f"\n\nPASSAGE (chunk {chunk.index:02d}, chapter {chunk.chapter}):\n{passage}\n")


def test_5_without_a_vocabulary_the_prompt_is_byte_identical():
    reg, chunks = _registry()
    for chunk in chunks:
        assert build_prompt(chunk, reg.book) == _prompt_as_it_was(chunk, reg.book)
        assert build_prompt(chunk, reg.book, None) == _prompt_as_it_was(chunk, reg.book)


def test_5_extract_without_a_vocabulary_sends_the_old_prompt():
    reg, chunks = _registry()
    seen = []

    def model(prompt, schema):
        seen.append(prompt)
        return {"lines": []}

    b.extract(chunks, reg, model, workers=1)
    b.extract(chunks, reg, model, workers=1, vocabulary=None)
    assert seen == [_prompt_as_it_was(chunks[0], reg.book)] * 2


def test_5_with_the_recipe_the_section_follows_the_rules_and_lists_every_term_once():
    reg, chunks = _registry()
    seen = []

    def model(prompt, schema):
        seen.append(prompt)
        return {"lines": []}

    b.extract(chunks, reg, model, workers=1, vocabulary=RECIPE)
    prompt = seen[0]
    assert prompt.index(_RULES) < prompt.index("Use these attribute names where they fit:") \
        < prompt.index("CANDIDATES (id | type | names | gate):")
    lines = prompt.splitlines()
    for term in RECIPE.terms:
        listed = [line for line in lines if line.startswith(f"{term.attribute}: ")]
        assert len(listed) == 1, term.attribute
        assert term.gloss in listed[0]
        assert ("(values: " in listed[0]) == (term.value_type == "literal" and not term.open_values)
    assert "locked: whether a lock is engaged; a JSON boolean, separate from `state` (values: true, false)" in lines
    assert "exits: an observed \"no way out\" (values: none)" in lines
    # the rest of the prompt is the old one
    assert prompt.replace(RECIPE.prompt_section() + "\n\n", "") == _prompt_as_it_was(chunks[0], reg.book)


def test_5_extract_refuses_something_that_is_not_a_vocabulary():
    reg, chunks = _registry()
    with pytest.raises(ValueError, match="vocabulary must be a Vocabulary"):
        b.extract(chunks, reg, lambda p, s: {"lines": []}, vocabulary="recipe")
