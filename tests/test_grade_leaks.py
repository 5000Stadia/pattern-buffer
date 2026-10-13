"""GRADE-LEAKS-V1: leak, false-belief and point-of-view grading, and the chunk
spans a commit records. Every test is the spec's Tests section (numbers in the
test names) or a detail it fixes. No model is called: worlds are hand-built, the
one build is a scripted toy book."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
HARNESS = ROOT / "evals" / "harness"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).parent))

from patternbuffer import World
from patternbuffer.testing import rule_classifier_fallback

import book_gold as bg
import grade_book as gb
import grade_leaks as gl
import run_book as rb
import usage_ledger
from pipeline import Pipeline, seed_world
from registry import EntityCard, TimelineSpec, WorldRegistry
import test_book_run as tb

WID = "w:leaktest"
BOOK_DIR = ROOT / "evals" / "books" / "the-weather-that-would-not-leave"


@pytest.fixture(autouse=True)
def _clean_usage(monkeypatch):
    monkeypatch.delenv(rb.USAGE_ENV, raising=False)
    usage_ledger.reset()
    yield
    usage_ledger.reset()


# ------------------------------------------------------------ hand-built worlds


def card(kind, names, aliases=()):
    return EntityCard(kind=kind, names=list(names), aliases=list(aliases))


def lit(entity, attribute, value, **kw):
    return {"entity": entity, "attribute": attribute, "value": value, "value_type": "literal", **kw}


def name(entity, value, attribute="name"):
    """A timeless name or alias row."""
    return lit(entity, attribute, value, timeless=True)


def at(entity, attribute, value, t, **kw):
    return {"entity": entity, "attribute": attribute, "value": value, "value_type": "entity",
            "valid_from": t, **kw}


class Built:
    """A hand-built world with chunk bookkeeping: seed rows from ``cards`` and
    ``seed_rows`` first, then ``chunk()`` appends one chunk's rows and records
    its span, as ``Pipeline.commit`` does."""

    def __init__(self, tmp_path, cards=None, name="w", seed_rows=()):
        reg = WorldRegistry(world_id=WID, entities=cards or {}, attributes={},
                            timeline=TimelineSpec(origin="Day 0"))
        self.world = World(tmp_path / f"{name}.world", world_id=WID,
                           model=lambda p, s: rule_classifier_fallback()(p, s))
        self.world.ingestor.classify_inline = False
        seed_world(self.world, reg)
        for row in seed_rows:
            self.world.ingest_structured([row])
        self.chunks: list[dict] = []
        self.texts: dict[int, str] = {}

    def chunk(self, chapter, text, rows=(), cursor=None):
        chunk_id = len(self.chunks)
        before = self.world.buffer.head()
        for row in rows:
            self.world.ingest_structured([row])
        after = self.world.buffer.head()
        self.chunks.append({"chunk": chunk_id, "chapter": chapter,
                            "cursor": float(chapter if cursor is None else cursor),
                            "seq": [before + 1, after] if after > before else None})
        self.texts[chunk_id] = text
        return chunk_id

    @property
    def spans(self):
        return {"chunks": copy.deepcopy(self.chunks)}

    def grade(self, graded, *, texts="auto", pass0=None, spans="auto"):
        self.world.classifier.classify_all(batch_size=40)
        return gb.grade_book(
            self.world, self.world.registry, graded,
            spans=self.spans if spans == "auto" else spans,
            chunk_texts=self.texts if texts == "auto" else texts, pass0=pass0)

    def close(self):
        self.world.close()


def graded_for(entities, same_as=(), **extra):
    """A minimal graded.json: ``entities`` maps a key to (kind, aliases)."""
    return {
        "key_sha256": "x", "readers": ["A", "B"],
        "entities": {k: {"kind": kind, "aliases": list(aliases)} for k, (kind, aliases) in entities.items()},
        "same_as": [{"id": f"same_as[{i}]", "entity": e, "alias": a, "chapter": c}
                    for i, (e, a, c) in enumerate(same_as)],
        "not_same": [], "moves": {}, "containers": [], "dropped": [],
        "ungraded_counts": {}, **extra}


MARA = ("person", ["Mara", "Mara Senn", "the hooded visitor"])
ORUVA = ("person", ["Oruva", "Or", "the third Listener"])
REVEAL = graded_for({"mara": MARA, "oruva": ORUVA}, [("mara", "the hooded visitor", 4)],
                    alias_first_chapter={"mara": {"Mara": 1, "Mara Senn": 1, "the hooded visitor": 2},
                                         "oruva": {"Oruva": 1, "Or": 1, "the third Listener": 3}})
VISITOR_TEXT = "The hooded visitor stood at the door."
MARA_TEXT = "Mara walked to the mill."
PLACES = {"place:door": card("place", ["Door"]), "place:mill": card("place", ["Mill"])}


def leak_rows(result):
    return [r for e in result["leaks"]["identity_leaks"]["entries"] for r in e["rows"]]


# ------------------------------------------------------- 1. chunk_spans


@pytest.fixture(scope="module")
def spans_build(tmp_path_factory):
    base = tmp_path_factory.mktemp("spans")
    book, out = tb.write_book(base / "toybook"), base / "out"
    meta = rb.run_book(book, out, tb.scripted_model())
    return {"book": book, "out": out, "meta": meta}


def test_1_chunk_spans_cover_every_chunk_row_in_order_with_chapter_and_cursor(spans_build):
    out = spans_build["out"]
    doc = json.loads((out / "chunk_spans.json").read_text())
    chunks = doc["chunks"]
    assert [c["chunk"] for c in chunks] == [0, 1, 2, 3]
    assert [c["chapter"] for c in chunks] == [1, 1, 2, 3]
    assert [c["cursor"] for c in chunks] == [1.0, 1.0, 2.0, 3.0]
    # each toy chunk ingests one item: spans are inclusive, contiguous and ordered
    assert all(c["seq"][0] == c["seq"][1] for c in chunks)
    seqs = [c["seq"][0] for c in chunks]
    assert seqs == list(range(seqs[0], seqs[0] + 4))
    # the pass-1 rows (the four toy lines) are exactly the span rows; seed rows fall outside
    world = World(out / "fresh_ingest.world", world_id=spans_build["meta"]["world_id"])
    try:
        inside = {c["seq"][0] for c in chunks}
        rows = {r.seq: r for r in world.buffer.all_rows()}
        assert [rows[c["seq"][0]].entity for c in chunks] == ["obj:lamp", "person:orin", "obj:lamp", "obj:lamp"]
        assert min(inside) > 1 and all(s < min(inside) for s, r in rows.items() if r.attribute == "name")
        spans = gl.Spans(doc)
        assert [spans.chunk_of(s) for s in sorted(inside)] == [0, 1, 2, 3]
        assert spans.chunk_of(1) is None and spans.chunk_of(max(rows) + 1) is None   # a later gate or audit row
    finally:
        world.close()


def test_1_an_empty_chunk_records_a_null_span(tmp_path):
    book = tb.write_book(tmp_path / "book")
    lines = {k: list(v) for k, v in tb.PASS1_LINES.items()}
    base = tb.scripted_model()

    def model(prompt, schema):
        if "PASSAGE (chunk 2)" in prompt:
            usage_ledger.record("test", "scripted", {"input_tokens": 1, "output_tokens": 1}, cost_usd=0.0)
            return {"lines": []}
        return base(prompt, schema)

    rb.run_book(book, tmp_path / "out", model)
    chunks = json.loads((tmp_path / "out" / "chunk_spans.json").read_text())["chunks"]
    assert chunks[2]["seq"] is None and chunks[1]["seq"] and chunks[3]["seq"]
    assert chunks[3]["seq"][0] == chunks[1]["seq"][1] + 1
    assert lines  # the toy lines were not mutated


def test_1_commit_with_a_chunk_plan_writes_the_same_log(spans_build, tmp_path):
    out = spans_build["out"]
    pipe = Pipeline(tb.scripted_model(), spans_build["meta"]["world_id"], out, max_workers=1)
    registry = WorldRegistry.load(out / "registry.json", spans_build["meta"]["world_id"])
    plain = pipe.commit(tmp_path / "plain.world", copy.deepcopy(registry))
    planned = pipe.commit(tmp_path / "planned.world", copy.deepcopy(registry),
                          chunk_plan=[(0, 1), (1, 1), (2, 2), (3, 3)])
    try:
        def view(w):
            return [(r.entity, r.attribute, r.value, r.frame, r.valid_from, r.status)
                    for r in w.buffer.all_rows()]
        assert view(plain) == view(planned)
    finally:
        plain.close()
        planned.close()
    # the pair form defaults the cursor to the chapter number
    pairs = json.loads((out / "chunk_spans.json").read_text())["chunks"]
    assert [(c["chunk"], c["chapter"], c["cursor"]) for c in pairs] == [(0, 1, 1.0), (1, 1, 1.0), (2, 2, 2.0), (3, 3, 3.0)]


def test_1_a_chunk_plan_that_misses_a_staged_chunk_is_refused_before_anything_is_written(spans_build, tmp_path):
    out = spans_build["out"]
    pipe = Pipeline(tb.scripted_model(), spans_build["meta"]["world_id"], out, max_workers=1)
    registry = WorldRegistry.load(out / "registry.json", spans_build["meta"]["world_id"])
    with pytest.raises(ValueError, match="chunk_plan"):
        pipe.commit(tmp_path / "x.world", registry, chunk_plan=[(0, 1), (1, 1)])
    assert not (tmp_path / "x.world").exists()


# ---------------------------------------------------- tokens and classification (3d)


def test_3d_tokenizer_and_common_word_aliases():
    assert gl.tokens("The One") == ["the", "one"]
    assert gl.tokens("O’Brien’s spoon") == ["o'brien's", "spoon"]
    assert gl.tokens("o'brien") == ["o'brien"]
    assert gl.tokens("copper-hand") == ["copper", "hand"]
    assert gl.is_common_word_alias("Or") and gl.is_common_word_alias("One")
    assert gl.is_common_word_alias("M.") and gl.is_common_word_alias("Mar")      # <= 3 characters
    assert not gl.is_common_word_alias("The One")                                # two tokens
    assert not gl.is_common_word_alias("Mara") and not gl.is_common_word_alias("Thorn")  # 5 chars, not stoplisted
    assert gl.is_common_word_alias("Before") and gl.is_common_word_alias("your")
    assert gl.contains_run(gl.tokens("saw the hooded visitor leave"), gl.tokens("the hooded visitor"))
    assert not gl.contains_run(gl.tokens("saw the hooded visitors leave"), gl.tokens("the hooded visitor"))


def classify(tmp_path, graded, texts, name="cls"):
    b = Built(tmp_path, name=name)
    for chapter, text in texts:
        b.chunk(chapter, text)
    try:
        return b.grade(graded)["leaks"]["identity_leaks"]
    finally:
        b.close()


def test_3d_or_never_classifies_a_chunk_and_is_listed_as_left_out(tmp_path):
    graded = graded_for({"oruva": ORUVA}, [("oruva", "the third Listener", 5)],
                        alias_first_chapter={"oruva": {"Oruva": 1, "Or": 1, "the third Listener": 2}})
    leaks = classify(tmp_path, graded, [
        (2, "The third Listener spoke, or maybe not."),        # prose "or": still pre-reveal
        (2, "The third Listener, Oruva, spoke."),              # another graded alias: not pre-reveal
        (2, "The third listeners spoke."),                     # not the phrase
        (5, "The third Listener spoke."),                      # at the reveal: not earlier
    ])
    assert leaks["entries"][0]["pre_reveal_chunks"] == [0]
    assert {"entity": "oruva", "alias": "Or", "reason": "common-word alias: not used to classify chunks"} \
        in leaks["excluded_aliases"]


def test_3d_hooded_visitor_matches_as_a_phrase_and_the_hooded_visitors_does_not(tmp_path):
    leaks = classify(tmp_path, REVEAL, [
        (2, "She saw the hooded visitor leave."), (2, "The hooded visitors arrived."),
        (2, "Hooded, the visitor waited."), (3, "The HOODED  VISITOR!")], name="phrase")
    assert leaks["entries"][0]["pre_reveal_chunks"] == [0, 3]


def test_3d_the_one_classifies_and_one_alone_does_not(tmp_path):
    graded = graded_for({"king": ("person", ["Aldric", "The One", "One", "the hooded visitor"])},
                        [("king", "the hooded visitor", 6)])
    leaks = classify(tmp_path, graded, [
        (2, "The hooded visitor met The One at dusk."),        # contains the alias "The One"
        (2, "The hooded visitor met one man at dusk."),        # "One" is a stoplisted single token
    ], name="theone")
    assert leaks["entries"][0]["pre_reveal_chunks"] == [1]
    assert {x["alias"] for x in leaks["excluded_aliases"]} == {"One"}


# ----------------------------------------------------------- 2. alias leak


def test_2_an_alias_row_from_an_earlier_chapter_than_its_first_chapter_is_a_leak(tmp_path):
    graded = graded_for({"duke": ("person", ["The Duke", "Aldous"])},
                        alias_first_chapter={"duke": {"The Duke": 3, "Aldous": 1}})
    early = Built(tmp_path, {"person:x": card("person", ["Someone"])}, name="early")
    early.chunk(1, "The duke is here.", [name("person:x", "the duke", "alias")])
    early.chunk(1, "Aldous too.", [name("person:x", "Aldous", "alias")])
    result = early.grade(graded)
    early.close()
    rows = result["leaks"]["alias_leaks"]["rows"]
    assert [(r["value"], r["chapter"], r["first_chapter"]) for r in rows] == [("the duke", 1, 3)]
    assert result["leaks"]["total"] == 1

    late = Built(tmp_path, {"person:x": card("person", ["Someone"])}, name="late")
    late.chunk(3, "The duke is here.", [name("person:x", "the duke", "alias")])
    clean = late.grade(graded)
    late.close()
    assert clean["leaks"]["alias_leaks"]["rows"] == [] and clean["leaks"]["total"] == 0


def test_2_a_seed_row_has_no_source_chunk_and_is_not_an_alias_leak(tmp_path):
    graded = graded_for({"duke": ("person", ["The Duke"])}, alias_first_chapter={"duke": {"The Duke": 3}})
    b = Built(tmp_path, {"person:duke": card("person", ["The Duke"])})
    b.chunk(1, "Nothing happens.", [at("person:duke", "in", "place:door", 1.0)])
    result = b.grade(graded)
    b.close()
    assert result["leaks"]["alias_leaks"]["rows"] == []


# ------------------------------------------------------ 3. identity leaks


def test_3_a_visitor_row_written_on_maras_id_in_a_pre_reveal_chunk_is_one_leak(tmp_path):
    b = Built(tmp_path, {**PLACES, "person:mara": card("person", ["Mara"])})
    b.chunk(1, MARA_TEXT, [at("person:mara", "in", "place:mill", 1.0)])
    b.chunk(2, VISITOR_TEXT, [at("person:mara", "in", "place:door", 2.0)])
    b.chunk(5, "Mara and the hooded visitor were one.", [name("person:mara", "the hooded visitor", "alias")])
    result = b.grade(REVEAL)
    b.close()
    entry = result["leaks"]["identity_leaks"]["entries"][0]
    assert entry["pre_reveal_chunks"] == [1]
    assert entry["chunk_leak_rows"] == 1 and entry["rows"][0]["attribute"] == "in"
    assert entry["first_leaking_chapter"] == 2 and result["leaks"]["total"] == 1
    assert result["headline"][1]["value"] == 1


def build_separate_visitor(tmp_path, merge: bool):
    b = Built(tmp_path, {**PLACES, "person:mara": card("person", ["Mara"]),
                         "person:visitor": card("person", ["The Hooded Visitor"])},
              name="merged" if merge else "apart")
    b.chunk(1, MARA_TEXT, [at("person:mara", "in", "place:mill", 1.0)])
    b.chunk(2, VISITOR_TEXT, [at("person:visitor", "in", "place:door", 2.0)])
    if merge:
        assert b.world.registry.merge("person:visitor", "person:mara", "the reveal", decided_by="host",
                                      representative="person:mara")
    return b


def test_3_a_separate_visitor_id_merged_later_is_no_leak_and_identity_is_unchanged(tmp_path):
    leaky = Built(tmp_path, {**PLACES, "person:mara": card("person", ["Mara"])}, name="leaky")
    leaky.chunk(1, MARA_TEXT, [at("person:mara", "in", "place:mill", 1.0)])
    leaky.chunk(2, VISITOR_TEXT, [at("person:mara", "in", "place:door", 2.0)])
    leaky.chunk(5, "Mara and the hooded visitor were one.", [name("person:mara", "the hooded visitor", "alias")])
    leak_card = leaky.grade(REVEAL)
    leaky.close()
    merged = build_separate_visitor(tmp_path, merge=True)
    merged_card = merged.grade(REVEAL)
    merged.close()
    assert leak_card["leaks"]["total"] == 1 and merged_card["leaks"]["total"] == 0
    assert leak_card["identity"] == merged_card["identity"] and leak_card["reveals"]["score"] == 1.0
    assert merged_card["reveals"]["score"] == 1.0
    apart = build_separate_visitor(tmp_path, merge=False)
    assert apart.grade(REVEAL)["leaks"]["total"] == 0
    apart.close()


def test_3c_unsafe_a_chapter_one_name_then_a_pre_reveal_row_on_the_same_id_is_a_leak(tmp_path):
    b = Built(tmp_path, PLACES)
    b.chunk(1, MARA_TEXT, [name("person:r", "mara")])
    b.chunk(3, VISITOR_TEXT, [at("person:r", "in", "place:door", 3.0),
                              name("person:r", "the hooded visitor", "alias")])
    result = b.grade(REVEAL)
    b.close()
    rows = leak_rows(result)
    # the visitor alias row on R counts too: a row on an id bound to Mara, written by a pre-reveal chunk
    assert sorted(r["attribute"] for r in rows) == ["alias", "in"]


def test_3c_unsafe_the_mara_name_may_come_from_a_seed_row(tmp_path):
    b = Built(tmp_path, {**PLACES, "person:r": card("person", ["Mara"])})
    b.chunk(3, VISITOR_TEXT, [at("person:r", "in", "place:door", 3.0)])
    result = b.grade(REVEAL)
    b.close()
    assert [r["attribute"] for r in leak_rows(result)] == ["in"]


def test_3c_safe_an_id_that_only_gains_mara_after_its_pre_reveal_rows_is_no_leak(tmp_path):
    b = Built(tmp_path, PLACES)
    b.chunk(3, VISITOR_TEXT, [name("person:v", "the hooded visitor"), at("person:v", "in", "place:door", 3.0)])
    b.chunk(9, "Mara it was.", [name("person:v", "mara", "alias")])
    result = b.grade(REVEAL)
    b.close()
    assert result["leaks"]["total"] == 0
    assert result["leaks"]["identity_leaks"]["entries"][0]["pre_reveal_chunks"] == [0]


def test_3c_safe_a_visitor_id_merged_into_maras_after_the_reveal_is_no_leak(tmp_path):
    b = Built(tmp_path, {**PLACES, "person:mara": card("person", ["Mara"])})
    b.chunk(3, VISITOR_TEXT, [name("person:v", "the hooded visitor"), at("person:v", "in", "place:door", 3.0)])
    assert b.world.registry.merge("person:v", "person:mara", "the reveal", decided_by="host",
                                  representative="person:mara")
    result = b.grade(REVEAL)
    b.close()
    assert result["leaks"]["total"] == 0


def test_3e_same_chunk_binding_both_the_name_row_and_the_following_row_are_leaks(tmp_path):
    b = Built(tmp_path, PLACES)
    b.chunk(1, MARA_TEXT, [name("person:mara", "Mara")])
    b.chunk(3, VISITOR_TEXT, [name("person:r", "Mara"), at("person:r", "in", "place:door", 3.0)])
    result = b.grade(REVEAL)
    b.close()
    rows = leak_rows(result)
    assert [(r["entity"], r["attribute"]) for r in rows] == [("person:r", "name"), ("person:r", "in")]
    assert rows[0]["seq"] < rows[1]["seq"]


def test_3e_a_row_before_the_binding_row_in_the_same_chunk_is_no_leak(tmp_path):
    b = Built(tmp_path, PLACES)
    b.chunk(3, VISITOR_TEXT, [at("person:r", "in", "place:door", 3.0), name("person:r", "Mara")])
    result = b.grade(REVEAL)
    b.close()
    assert [r["attribute"] for r in leak_rows(result)] == ["name"]


def test_3f_an_id_named_by_mara_and_by_another_entity_is_ambiguous_and_not_charged(tmp_path):
    b = Built(tmp_path, PLACES)
    b.chunk(1, MARA_TEXT, [name("person:r", "Mara"), name("person:r", "Oruva", "alias")])
    b.chunk(3, VISITOR_TEXT, [at("person:r", "in", "place:door", 3.0)])
    result = b.grade(REVEAL)
    b.close()
    ident = result["leaks"]["identity_leaks"]
    assert result["leaks"]["total"] == 0 and leak_rows(result) == []
    assert ident["entries"][0]["ambiguous_rows"] == 1 and ident["ambiguous_rows"] == 1


def test_3a_raw_mapping_ambiguous_unmapped_and_a_later_merge_changes_nothing(tmp_path):
    b = Built(tmp_path, {**PLACES, "person:mara": card("person", ["Mara"])})
    b.chunk(1, MARA_TEXT, [name("person:r", "Mara"), name("person:x", "Oruva"), name("person:x", "mara", "alias")])
    b.chunk(3, VISITOR_TEXT, [at("person:r", "in", "place:door", 3.0),       # a leak
                              at("person:x", "in", "place:door", 3.0),       # ambiguous
                              at("obj:nameless", "in", "place:door", 3.0)])  # unmapped
    before = b.grade(REVEAL)
    raw = gl.RawIds(b.world, REVEAL)
    assert raw.status("person:x") == ("ambiguous", None) and raw.status("obj:nameless") == ("unmapped", None)
    assert raw.status("person:r") == ("mapped", "mara")
    ident = before["leaks"]["identity_leaks"]
    assert ident["entries"][0]["chunk_leak_rows"] == 1
    assert ident["ambiguous_rows"] == 1 and ident["unmapped_rows"] >= 1
    assert b.world.registry.merge("person:r", "person:mara", "later", decided_by="host",
                                  representative="person:mara")
    after = b.grade(REVEAL)
    b.close()
    assert after["leaks"]["identity_leaks"]["entries"][0]["rows"] == before["leaks"]["identity_leaks"]["entries"][0]["rows"]
    assert after["leaks"]["total"] == before["leaks"]["total"] == 1


def test_3a_a_name_shared_by_two_entities_still_maps_when_another_name_settles_it(tmp_path):
    graded = graded_for({"a": ("person", ["Pat", "the visitor"]), "b": ("person", ["Sam", "the visitor"])},
                        [("a", "Pat", 5)])
    b = Built(tmp_path)
    b.chunk(1, "x", [name("person:r", "the visitor"), name("person:r", "Pat", "alias")])
    b.grade(graded)
    raw = gl.RawIds(b.world, graded)
    assert raw.status("person:r") == ("mapped", "a")
    b.close()


def test_3b_a_pass0_id_holding_both_the_visitor_and_a_later_alias_is_a_registry_leak(tmp_path):
    graded = copy.deepcopy(REVEAL)
    graded["alias_first_chapter"]["mara"]["Mara"] = 4          # first used at the reveal chapter
    joined = WorldRegistry(world_id=WID, entities={
        "person:a": card("person", ["The Hooded Visitor"], ["mara"])})
    apart = WorldRegistry(world_id=WID, entities={
        "person:v": card("person", ["The Hooded Visitor"]), "person:m": card("person", ["Mara"])})
    b = Built(tmp_path, name="reg")
    b.chunk(1, "Nothing.")
    flagged = b.grade(graded, pass0=joined)["leaks"]
    clean = b.grade(graded, pass0=apart)["leaks"]
    unknown = b.grade(graded, pass0=None)["leaks"]
    b.close()
    entry = flagged["identity_leaks"]["entries"][0]
    assert entry["registry_leak"] is True and entry["registry_leak_ids"] == ["person:a"]
    assert flagged["identity_leaks"]["registry_leaks"] == 1 and flagged["total"] == 1
    assert clean["identity_leaks"]["entries"][0]["registry_leak"] is False and clean["total"] == 0
    assert unknown["identity_leaks"]["entries"][0]["registry_leak"] == "unmeasured"
    # an alias the text already used before the reveal is not a later alias
    early = copy.deepcopy(graded)
    early["alias_first_chapter"]["mara"]["Mara"] = 1
    b2 = Built(tmp_path, name="reg2")
    b2.chunk(1, "Nothing.")
    assert b2.grade(early, pass0=joined)["leaks"]["total"] == 0
    b2.close()


def test_3_without_chunk_texts_chunk_leaks_are_unmeasured_not_zero(tmp_path):
    b = Built(tmp_path, {"person:mara": card("person", ["Mara"])})
    b.chunk(1, "x", [at("person:mara", "in", "place:mill", 1.0)])
    result = b.grade(REVEAL, texts=None)["leaks"]
    b.close()
    assert result["identity_leaks"]["chunk_leak_rows"] is None
    assert "chunk_leaks" in result["unmeasured_parts"]


# ------------------------------------------------------------ 4-6. beliefs


def fact(entity, attribute, value):
    return {"entity": entity, "attribute": attribute,
            "value": {"entity": value[1:]} if value.startswith("@") else {"literal": value}}


def belief_graded(**extra):
    return graded_for(
        {"mara": ("person", ["Mara"]), "oruva": ("person", ["Oruva"])},
        beliefs=[{"id": "false_beliefs[0]", "who": "oruva", "fact": fact("mara", "status", "dead"),
                  "from_chapter": 1, "corrected_chapter": 3}],
        corrections=[{"id": "corrections[0]", "stated_chapter": 1, "corrected_chapter": 3,
                      "as_fact": fact("mara", "status", "dead"),
                      "corrected_as_fact": fact("mara", "status", "alive")}],
        knowledge=[{"id": "knowledge[0]", "who": "oruva", "mode": "learns", "chapter": 3,
                    "fact": fact("mara", "status", "alive")}],
        **extra)


def chapters_world(tmp_path, name, rows_by_chapter, n=5):
    b = Built(tmp_path, {"person:mara": card("person", ["Mara"]), "person:oruva": card("person", ["Oruva"])},
              name=name)
    for chapter in range(1, n + 1):
        b.chunk(chapter, f"Chapter {chapter}.", rows_by_chapter.get(chapter, ()))
    return b


def test_4_canon_folding_to_the_belief_is_false_in_canon(tmp_path):
    b = chapters_world(tmp_path, "canon4", {2: [lit("person:mara", "status", "dead", valid_from=2.0)]})
    result = b.grade(belief_graded())
    b.close()
    item = result["beliefs"]["false_beliefs"]["items"][0]
    assert item["false_in_canon"] == 1 and result["beliefs"]["false_beliefs"]["false_in_canon"] == 1
    assert result["headline"][2]["value"] == 1


def test_4_a_belief_only_in_the_believers_frame_is_held_not_canon(tmp_path):
    held = lit("person:mara", "status", "dead", valid_from=1.0, valid_to=3.0, frame="knows:person:oruva")
    b = chapters_world(tmp_path, "frame4", {1: [held]})
    result = b.grade(belief_graded())
    b.close()
    fb = result["beliefs"]["false_beliefs"]
    assert fb["items"][0]["false_in_canon"] == 0 and fb["items"][0]["held_by_believer"] == 1
    assert fb["false_in_canon"] == 0 and fb["held_by_believer_rate"] == 1.0
    assert result["headline"][2]["value"] == 0


def test_4_the_believers_frame_is_read_through_the_merged_closure(tmp_path):
    held = lit("person:mara", "status", "dead", valid_from=1.0, valid_to=3.0, frame="knows:person:oruva2")
    b = Built(tmp_path, {"person:mara": card("person", ["Mara"]), "person:oruva": card("person", ["Oruva"]),
                         "person:oruva2": card("person", ["Oruva Senn"])}, name="merged4")
    graded = belief_graded()
    graded["entities"]["oruva"]["aliases"].append("Oruva Senn")
    for chapter in range(1, 6):
        b.chunk(chapter, "x", [held] if chapter == 1 else [])
    assert b.world.registry.merge("person:oruva2", "person:oruva", "same", decided_by="host",
                                  representative="person:oruva")
    result = b.grade(graded)
    b.close()
    assert result["beliefs"]["false_beliefs"]["items"][0]["held_by_believer"] == 1


def test_4_a_belief_held_only_after_it_was_corrected_is_not_held_by_the_believer(tmp_path):
    late = lit("person:mara", "status", "dead", valid_from=3.0, frame="knows:person:oruva")
    b = chapters_world(tmp_path, "late4", {3: [late]})
    result = b.grade(belief_graded())
    b.close()
    assert result["beliefs"]["false_beliefs"]["items"][0]["held_by_believer"] == 0


def test_5_a_correction_passes_when_canon_ends_at_the_corrected_value(tmp_path):
    rows = {1: [lit("person:mara", "status", "dead", valid_from=1.0, valid_to=3.0)],
            3: [lit("person:mara", "status", "alive", valid_from=3.0)]}
    b = chapters_world(tmp_path, "pass5", rows)
    result = b.grade(belief_graded())["beliefs"]["corrections"]
    b.close()
    assert result["ends_correct"] == 1 and result["claim_after_correction"] == 0
    assert result["items"][0]["ends_correct"] == 1 and result["items"][0]["claim_after_correction"] == 0


def test_5_canon_still_at_the_claim_after_the_correction_chapter_fails(tmp_path):
    b = chapters_world(tmp_path, "fail5", {1: [lit("person:mara", "status", "dead", valid_from=1.0)],
                                           3: [lit("person:mara", "status", "alive", valid_from=0.5)]})
    result = b.grade(belief_graded())["beliefs"]["corrections"]
    b.close()
    assert result["items"][0]["claim_after_correction"] == 1 and result["claim_after_correction"] == 1
    assert result["items"][0]["ends_correct"] == 0


def test_5_a_correction_that_only_negates_has_no_end_check(tmp_path):
    graded = belief_graded()
    graded["corrections"][0]["corrected_as_fact"] = None
    b = chapters_world(tmp_path, "neg5", {1: [lit("person:mara", "status", "dead", valid_from=1.0)]})
    result = b.grade(graded)["beliefs"]["corrections"]
    b.close()
    assert result["items"][0]["ends_correct"] is None and result["ends_correct_entries"] == 0
    assert result["claim_after_correction"] == 1


# ------------------------------------------------------- 6. point of view


def test_6_a_fact_in_the_learners_frame_from_their_chapter_on_is_held(tmp_path):
    row = lit("person:mara", "status", "alive", valid_from=3.0, frame="knows:person:oruva")
    b = chapters_world(tmp_path, "pov6", {3: [row]})
    result = b.grade(belief_graded())["point_of_view"]
    b.close()
    item = result["learns"]["items"][0]
    assert item["held_by_end"] == 1 and item["too_early"] == 0
    assert result["learns"]["held_rate"] == 1.0 and result["learns"]["learned_too_early"] == 0


def test_6_a_fact_present_before_the_learners_chapter_is_too_early(tmp_path):
    row = lit("person:mara", "status", "alive", valid_from=1.0, frame="knows:person:oruva")
    b = chapters_world(tmp_path, "early6", {1: [row]})
    result = b.grade(belief_graded())["point_of_view"]
    b.close()
    assert result["learns"]["items"][0]["too_early"] == 1
    assert result["learns"]["learned_too_early"] == 1 and result["learns"]["held"] == 1


def test_6_a_fact_never_learned_scores_zero_held(tmp_path):
    b = chapters_world(tmp_path, "none6", {})
    result = b.grade(belief_graded())["point_of_view"]["learns"]
    b.close()
    assert result["held"] == 0 and result["held_rate"] == 0.0


def test_6a_never_learns_one_violation_when_the_frame_holds_the_fact_at_any_time(tmp_path):
    graded = belief_graded()
    graded["knowledge"] = [{"id": "knowledge[1]", "who": "oruva", "mode": "never_learns", "chapter": None,
                            "fact": fact("mara", "status", "alive")}]
    row = lit("person:mara", "status", "alive", valid_from=4.0, valid_to=5.0, frame="knows:person:oruva")
    b = chapters_world(tmp_path, "nl6a", {4: [row]})
    bad = b.grade(graded)["point_of_view"]["never_learns"]
    b.close()
    assert bad["violations"] == 1 and bad["items"][0]["violation"] == 1
    ok = chapters_world(tmp_path, "nl6a_ok", {})
    clean = ok.grade(graded)["point_of_view"]["never_learns"]
    ok.close()
    assert clean["violations"] == 0 and clean["entries"] == 1


# -------------------------------------------------- matching: unmatched, never a pass


def test_an_unmapped_key_or_a_different_spelling_is_unmatched_never_a_pass(tmp_path):
    graded = belief_graded()
    graded["knowledge"].append({"id": "knowledge[1]", "who": "ghost", "mode": "learns", "chapter": 3,
                                "fact": fact("mara", "status", "alive")})
    graded["entities"]["ghost"] = {"kind": "person", "aliases": ["The Ghost"]}       # maps to no built id
    graded["beliefs"].append({"id": "false_beliefs[1]", "who": "oruva", "fact": fact("mara", "mood", "dead"),
                              "from_chapter": 1, "corrected_chapter": 3})            # attribute never written
    row = lit("person:mara", "status", "alive", valid_from=3.0, frame="knows:person:oruva")
    b = chapters_world(tmp_path, "unm", {3: [row]})
    result = b.grade(graded)
    b.close()
    learns = result["point_of_view"]["learns"]
    assert learns["entries"] == 2 and learns["held"] == 1 and learns["held_rate"] == 0.5 and learns["unmatched"] == 1
    assert learns["items"][1]["status"] == "unmatched" and learns["items"][1]["unmatched"] == ["who"]
    fb = result["beliefs"]["false_beliefs"]
    assert fb["items"][1]["status"] == "unmatched" and fb["items"][1]["unmatched"] == ["attribute"]
    assert fb["unmatched"] == 1 and fb["false_in_canon"] == 0


def test_the_key_attribute_is_matched_through_the_worlds_canonical_attribute(tmp_path):
    graded = graded_for({"mara": ("person", ["Mara"]), "mill": ("place", ["Mill"])},
                        beliefs=[{"id": "false_beliefs[0]", "who": "mara",
                                  "fact": fact("mara", "Located In", "@mill"),
                                  "from_chapter": 1, "corrected_chapter": None}])
    b = Built(tmp_path, {"person:mara": card("person", ["Mara"]), "place:mill": card("place", ["Mill"])})
    b.chunk(1, "x", [at("person:mara", "in", "place:mill", 1.0)])
    item = b.grade(graded)["beliefs"]["false_beliefs"]["items"][0]
    b.close()
    assert item["status"] == "measured" and item["false_in_canon"] == 1


# ------------------------------------------------ 7. unverified and null fields


def gold_key() -> dict:
    mara = {"kind": "person", "aliases": ["Mara", "Mara Senn", "the hooded visitor"], "first_chapter": 1,
            "alias_first_chapter": {"Mara": 1, "Mara Senn": 1, "the hooded visitor": 2}}
    return {
        "title": "Toy",
        "chapters": [{"n": 1, "file": "ch01.md", "words": 10}],
        "entities": {
            "mara": mara,
            "oruva": {"kind": "person", "aliases": ["Oruva", "Or", "the third Listener"], "first_chapter": 1,
                      "alias_first_chapter": {"Oruva": 1, "Or": 1, "the third Listener": 3}},
            "mill": {"kind": "place", "aliases": ["the mill"], "first_chapter": 1}},
        "same_as": [["mara", "the hooded visitor", 4], ["oruva", "the third Listener", 5]],
        "not_same": [], "locations": [],
        "holdings": [], "containers": [],
        "knowledge": [
            {"who": "oruva", "learns": "Mara is alive", "chapter": 3,
             "as_fact": fact("mara", "status", "alive")},
            {"who": "oruva", "never_learns": "Mara is in the mill", "as_fact": fact("mara", "in", "@mill")}],
        "false_beliefs": [
            {"who": "oruva", "believes": "Mara is dead", "from_chapter": 1, "corrected_chapter": 3,
             "as_fact": fact("mara", "status", "dead")},
            {"who": "oruva", "believes": "something vague", "from_chapter": 1, "corrected_chapter": 3,
             "as_fact": None}],
        "corrections": [
            {"claim": "Mara is dead", "stated_chapter": 1, "corrected_chapter": 3,
             "as_fact": fact("mara", "status", "dead"), "corrected_as_fact": fact("mara", "status", "alive")},
            {"claim": "It was a trick", "stated_chapter": 2, "corrected_chapter": 3,
             "as_fact": fact("mara", "status", "dead"), "corrected_as_fact": None}],
        "do_not_grade": []}


def reader(key_bytes, label, **fields):
    key = json.loads(key_bytes)
    ok = {"verdict": "ok", "note": ""}
    doc = {"key_sha256": bg.sha256_bytes(key_bytes), "reader": label,
           "entities": {k: {**ok, "bad_aliases": []} for k in key["entities"]},
           "missing": [], "text_contradictions": []}
    for section in ("same_as", "not_same", "locations", "holdings", "containers", "knowledge",
                    "false_beliefs", "corrections"):
        doc[section] = [{"i": i, **ok} for i in range(len(key[section]))]
    doc["fields"] = {
        "alias_first_chapter": {k: {a: "ok" for a in e["alias_first_chapter"]}
                                for k, e in key["entities"].items() if "alias_first_chapter" in e},
        "false_beliefs": {"0": {"as_fact": "ok"}},
        "corrections": {"0": {"as_fact": "ok", "corrected_as_fact": "ok"}, "1": {"as_fact": "ok"}},
        "knowledge": {"0": {"as_fact": "ok"}, "1": {"as_fact": "ok"}}}
    for path, value in fields.items():
        node = doc["fields"]
        *steps, last = path.split("/")
        for s in steps:
            node = node[s]
        node[last] = value
    return doc


def test_7_only_fields_both_readers_marked_ok_are_graded_the_rest_are_dropped_with_notes():
    kb = json.dumps(gold_key()).encode()
    a = reader(kb, "A", **{"false_beliefs/0/as_fact": "wrong: the text says she is missing"})
    b = reader(kb, "B", **{"alias_first_chapter/mara/the hooded visitor": "wrong: used in chapter 1"})
    gold = bg.build_gold(kb, [a, b])
    assert gold["beliefs"] == []                                  # reader A rejected it
    assert gold["alias_first_chapter"]["mara"] == {"Mara": 1, "Mara Senn": 1}
    assert gold["alias_first_chapter"]["oruva"] == {"Or": 1, "Oruva": 1, "the third Listener": 3}
    dropped = {d["id"]: d for d in gold["dropped_fields"]}
    assert dropped["false_beliefs[0].as_fact"]["verdicts"] == {"A": "wrong", "B": "ok"}
    assert dropped["false_beliefs[0].as_fact"]["notes"]["A"] == "the text says she is missing"
    assert dropped["entities.mara.alias_first_chapter[the hooded visitor]"]["notes"]["B"] == "used in chapter 1"
    assert [d["id"] for d in gold["dropped_fields"]] == sorted(dropped)


def test_7_a_null_as_fact_is_not_graded_and_is_listed_as_dropped():
    kb = json.dumps(gold_key()).encode()
    gold = bg.build_gold(kb, [reader(kb, "A"), reader(kb, "B")])
    dropped = {d["id"]: d for d in gold["dropped_fields"]}
    assert dropped["false_beliefs[1].as_fact"]["reason"].startswith("as_fact is null")
    assert [e["id"] for e in gold["beliefs"]] == ["false_beliefs[0]"]
    # a correction that only negates is a legitimate null: neither graded nor dropped
    assert "corrections[1].corrected_as_fact" not in dropped
    assert [(e["id"], e["corrected_as_fact"] is None) for e in gold["corrections"]] == [
        ("corrections[0]", False), ("corrections[1]", True)]
    assert gold["field_counts"]["beliefs"] == {"entries": 2, "verified": 1, "dropped": 1}
    assert gold["field_counts"]["corrections"] == {"entries": 3, "verified": 3, "dropped": 0}
    assert gold["field_counts"]["knowledge"] == {"entries": 2, "verified": 2, "dropped": 0}
    assert gold["field_counts"]["alias_first_chapter"] == {"entries": 6, "verified": 6, "dropped": 0}
    assert [(e["id"], e["mode"]) for e in gold["knowledge"]] == [("knowledge[0]", "learns"),
                                                                 ("knowledge[1]", "never_learns")]
    assert "false_beliefs[1].as_fact" in bg.dropped_markdown(gold)


def test_7_a_field_with_no_verdict_from_a_reader_is_dropped_not_graded():
    kb = json.dumps(gold_key()).encode()
    b = reader(kb, "B")
    del b["fields"]["knowledge"]["1"]
    gold = bg.build_gold(kb, [reader(kb, "A"), b])
    assert [e["id"] for e in gold["knowledge"]] == ["knowledge[0]"]
    dropped = {d["id"]: d for d in gold["dropped_fields"]}
    assert dropped["knowledge[1].as_fact"]["verdicts"] == {"A": "ok", "B": "missing"}


def test_7_the_entry_level_verdict_and_the_entities_still_gate_a_field():
    kb = json.dumps(gold_key()).encode()
    a, b = reader(kb, "A"), reader(kb, "B")
    b["knowledge"][0] = {"i": 0, "verdict": "wrong", "note": "she never learns it"}
    b["entities"]["mill"]["verdict"] = "unclear"
    gold = bg.build_gold(kb, [a, b])
    dropped = {d["id"]: d for d in gold["dropped_fields"]}
    assert dropped["knowledge[0].as_fact"]["reason"].startswith("the entry-level verdict")
    assert dropped["knowledge[1].as_fact"]["reason"] == "entity dropped"        # names the mill
    assert gold["knowledge"] == []


def test_7_malformed_fields_are_refused():
    def refused(mutate, match):
        key = gold_key()
        mutate(key)
        kb = json.dumps(key).encode()
        with pytest.raises(bg.VerdictError, match=match):
            bg.build_gold(kb, [reader(kb, "A"), reader(kb, "B")])

    refused(lambda k: k["false_beliefs"][0]["as_fact"].update(entity="nobody"), "not an entity")
    refused(lambda k: k["false_beliefs"][0]["as_fact"].update(value={"literal": ["x"]}), "scalar")
    refused(lambda k: k["false_beliefs"][0]["as_fact"].update(extra=1), "entity, attribute, value")
    refused(lambda k: k["entities"]["mara"]["alias_first_chapter"].update(Nobody=3), "not one of its aliases")
    refused(lambda k: k["entities"]["mara"]["alias_first_chapter"].update(Mara="one"), "not an int")
    kb = json.dumps(gold_key()).encode()
    bad = reader(kb, "B")
    bad["fields"]["knowledge"]["9"] = {"as_fact": "ok"}
    with pytest.raises(bg.VerdictError, match="no such entry"):
        bg.build_gold(kb, [reader(kb, "A"), bad])
    bad = reader(kb, "B")
    bad["fields"]["beliefs"] = {}
    with pytest.raises(bg.VerdictError, match="unknown sections"):
        bg.build_gold(kb, [reader(kb, "A"), bad])


def test_7_gold_is_deterministic_and_its_sections_feed_the_grader(tmp_path):
    kb = json.dumps(gold_key()).encode()
    docs = [reader(kb, "A"), reader(kb, "B")]
    gold = bg.build_gold(kb, docs)
    assert bg.gold_json(gold) == bg.gold_json(bg.build_gold(kb, list(reversed(docs))))
    row = lit("person:mara", "status", "alive", valid_from=3.0, frame="knows:person:oruva")
    b = chapters_world(tmp_path, "goldfeed", {3: [row]})
    cards = b.grade(json.loads(bg.gold_json(gold)))
    b.close()
    assert cards["field_counts"]["beliefs"]["verified"] == 1
    assert cards["dropped_fields"] == 1
    assert cards["ungraded_counts"] == {"corrections": 0, "false_beliefs": 1, "knowledge": 0}
    assert cards["point_of_view"]["learns"]["held"] == 1
    assert cards["point_of_view"]["never_learns"]["entries"] == 1


# ------------------------------------------------------------ 8. old runs


def test_8_a_run_without_spans_is_unmeasured_and_the_existing_sections_are_unchanged(spans_build, tmp_path):
    graded_path = tmp_path / "graded.json"
    graded_path.write_text(json.dumps(tb.GRADED))
    out_new = tmp_path / "with_spans"
    out_old = tmp_path / "old_run"
    for out in (out_new, out_old):
        out.mkdir()
        for f in spans_build["out"].iterdir():
            if f.is_file():
                (out / f.name).write_bytes(f.read_bytes())
    (out_old / "chunk_spans.json").unlink()
    assert gb.main(["--run", str(out_new), "--graded", str(graded_path), "--book", str(spans_build["book"])]) == 0
    assert gb.main(["--run", str(out_old), "--graded", str(graded_path)]) == 0
    new = json.loads((out_new / "book_scorecard.json").read_text())
    old = json.loads((out_old / "book_scorecard.json").read_text())
    assert old["leaks"] == old["beliefs"] == old["point_of_view"] == "unmeasured"
    assert isinstance(new["leaks"], dict) and new["leaks"]["total"] == 0
    for section in LEGACY:
        assert old[section] == new[section]
    text = (out_old / "book_scorecard.md").read_text()
    assert "unmeasured" in text and "nothing is inferred" in text
    # a time-and-cost line from the receipt rides in the headline
    assert new["headline"][4]["value"]["cost_usd"] is not None


def test_8_a_chunk_plan_that_disagrees_with_the_run_is_refused(spans_build, tmp_path):
    other = tb.write_book(tmp_path / "other", {1: tb.TOY_CHAPTERS[1], 2: tb.TOY_CHAPTERS[2]})
    graded_path = tmp_path / "graded.json"
    graded_path.write_text(json.dumps(tb.GRADED))
    with pytest.raises(SystemExit, match="chunk plan"):
        gb.main(["--run", str(spans_build["out"]), "--graded", str(graded_path), "--book", str(other),
                 "--out", str(tmp_path / "x")])


def test_8_no_stored_run_world_is_opened_for_writing(spans_build, tmp_path):
    world = spans_build["out"] / "fresh_ingest.world"
    before = (world.stat().st_mtime_ns, world.read_bytes())
    graded_path = tmp_path / "graded.json"
    graded_path.write_text(json.dumps(tb.GRADED))
    gb.main(["--run", str(spans_build["out"]), "--graded", str(graded_path), "--book", str(spans_build["book"]),
             "--out", str(tmp_path / "scores")])
    assert (world.stat().st_mtime_ns, world.read_bytes()) == before


# --------------------------------------------- 9. byte-stable legacy payloads

LEGACY = ("identity", "reveals", "look_alikes", "order", "final", "ever", "containers")


def legacy_digest(card_) -> str:
    payload = json.dumps({s: card_[s] for s in LEGACY}, indent=2, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def r27_world(tmp_path, graded):
    """A deterministic world synthesized from R27's graded.json: one card per entity,
    the moves as timed rows, the containers as placements."""
    prefix = {"person": "person", "place": "place", "object": "obj"}
    ids = {k: f"{prefix[e['kind']]}:{k}" for k, e in graded["entities"].items()}
    cards = {ids[k]: card(e["kind"], e["aliases"][:1], e["aliases"][1:])
             for k, e in graded["entities"].items() if e["aliases"]}
    rows = []
    for key, moves in sorted(graded["moves"].items()):
        for m in moves:
            attribute = "in" if m["id"].startswith("locations") else "held_by"
            rows.append(at(ids[key], attribute, ids[m["to"]], 10.0 * m["from_chapter"]))
    for c in graded["containers"]:
        rows += [at(ids[x], "in", ids[c["container"]], 5.0) for x in c["contents"]]
    reg = WorldRegistry(world_id=WID, entities=cards, attributes={}, timeline=TimelineSpec(origin="Day 0"))
    w = World(tmp_path / "r27.world", world_id=WID, model=lambda p, s: rule_classifier_fallback()(p, s))
    w.ingestor.classify_inline = False
    seed_world(w, reg)
    for row in rows:
        try:
            w.ingest_structured([row])
        except ValueError:
            pass
    w.classifier.classify_all(batch_size=40)
    return w


# sha256 of the legacy sections' canonical JSON, taken from the grader before GRADE-LEAKS-V1
LEGACY_DIGESTS = {
    "hand_built": "f61fe8c6280d5206a46b0c3fda27523263839ca864fa02be0880244bdc2f9c5d",
    "r27": "4f1e1898f2d9eeccd1b659149238b7046f6f218625bdcb3d9bfac859b77594d7",
}


def legacy_cards(tmp_path, grade_fn):
    """The two scorecards the legacy sections are pinned on."""
    out = {}
    w = tb.make_world(tmp_path, tb.base_cards(), tb.lamp_rows(), "hand")
    try:
        out["hand_built"] = grade_fn(w, w.registry, tb.GRADED)
    finally:
        w.close()
    graded = json.loads((BOOK_DIR / "graded.json").read_text())
    w = r27_world(tmp_path, graded)
    try:
        out["r27"] = grade_fn(w, w.registry, graded)
    finally:
        w.close()
    return out


def test_9_legacy_section_payloads_are_byte_identical_to_before(tmp_path):
    cards = legacy_cards(tmp_path, gb.grade_book)
    assert {k: legacy_digest(c) for k, c in cards.items()} == LEGACY_DIGESTS
    # nothing was added to the summary the old scorecard reported
    assert set(cards["r27"]["summary"]) == {"identity_b3_f1", "reveals", "look_alikes", "order", "final",
                                            "ever", "containers"}


def test_9_a_key_without_the_new_fields_builds_exactly_the_graded_json_it_always_did():
    key_bytes = (BOOK_DIR / "key.json").read_bytes()
    docs = [json.loads((BOOK_DIR / f"verdicts_{r}.json").read_text()) for r in ("A", "B")]
    gold = bg.build_gold(key_bytes, docs)
    assert bg.gold_json(gold) == (BOOK_DIR / "graded.json").read_text()
    assert not {"alias_first_chapter", "beliefs", "corrections", "knowledge", "field_counts",
                "dropped_fields"} & set(gold)


def test_9_the_old_graded_json_grades_with_empty_new_sections(spans_build, tmp_path):
    w = tb.make_world(tmp_path, tb.base_cards(), tb.lamp_rows(), "oldgold")
    try:
        result = gb.grade_book(w, w.registry, tb.GRADED, spans={"chunks": []})
    finally:
        w.close()
    assert result["beliefs"]["false_beliefs"]["entries"] == 0
    assert result["point_of_view"]["learns"]["entries"] == 0
    assert result["leaks"]["alias_leaks"]["measured"] is False
    assert result["ungraded_counts"] == tb.GRADED["ungraded_counts"] and result["field_counts"] == {}


# ------------------------------------------------------------- reporting


def test_the_report_states_counts_the_excluded_aliases_and_the_headline_order(tmp_path):
    kb = json.dumps(gold_key()).encode()
    gold = json.loads(bg.gold_json(bg.build_gold(kb, [reader(kb, "A"), reader(kb, "B")])))
    row = lit("person:mara", "status", "dead", valid_from=2.0)
    b = chapters_world(tmp_path, "report", {2: [row]})
    result = b.grade(gold)
    b.close()
    assert [h["rank"] for h in result["headline"]] == [1, 2, 3, 4, 5]
    assert [h["measure"] for h in result["headline"]][:3] == [
        "wrong merges across look-alike pairs", "leaks", "false beliefs in canon"]
    assert result["headline"][2]["value"] == 1
    md = gb.scorecard_md(result)
    for text in ("Headline (judging order)", "## Leaks (target 0)", "## Beliefs", "## Point of view",
                 "false in canon 1 (target 0)", "alias_first_chapter: 6 / 6 / 0", "beliefs: 2 / 1 / 1",
                 "`mara` 'the hooded visitor'"[:0], "aliases left out of chunk classification"):
        assert text in md
    assert "`oruva` 'Or'" in md
    assert result["dropped_fields"] == 1
