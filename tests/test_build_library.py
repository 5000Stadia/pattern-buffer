"""BUILD-LIBRARY-V1: ``patternbuffer.build``, registry-first world building.

Every test is the spec's Tests section (numbers in the test names) or a detail
it fixes. No model is called: every model here is a fake that returns
deterministic line-grammar output, and classification goes to the engine's rule
fallback.
"""

from __future__ import annotations

import ast
import contextvars
import copy
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).parent.parent
HARNESS = ROOT / "evals" / "harness"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).parent))

from patternbuffer import World, build as b
from patternbuffer.build import text as btext
from patternbuffer.build.extract import build_prompt
from patternbuffer.build.grammar import grammar_problem, parse_line
from patternbuffer.model import ID_RE
from patternbuffer.testing import rule_classifier_fallback

import book_gold
import grade_book as gb
import grade_leaks as gl
import grammar as harness_grammar
import run_book as rb
import test_book_run as tb
import usage_ledger

WID = "w:buildlib"
CLASSIFY = rule_classifier_fallback()


# ------------------------------------------------------------------ helpers


@pytest.fixture
def worlds(tmp_path):
    """Worlds opened by a test, closed at its end."""
    opened: list[World] = []

    def make(name: str = "w") -> World:
        w = World(tmp_path / f"{name}.world", world_id=WID, model=CLASSIFY)
        opened.append(w)
        return w

    yield make
    for w in opened:
        w.close()


@pytest.fixture(autouse=True)
def _clean_usage(monkeypatch):
    monkeypatch.delenv(rb.USAGE_ENV, raising=False)
    usage_ledger.reset()
    yield
    usage_ledger.reset()


class FakeModel:
    """Extraction outputs by chunk index (fixed dicts), category-pass outputs by
    category, and the rule fallback for classification. Records every prompt."""

    def __init__(self, chunks: dict[int, dict] | None = None,
                 categories: dict[str, list] | None = None) -> None:
        self.chunks = chunks or {}
        self.categories = categories or {}
        self.prompts: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, prompt: str, schema: dict) -> Any:
        with self._lock:
            self.prompts.append(prompt)
        usage_ledger.record("test", "fake", {"input_tokens": 1, "output_tokens": 1}, cost_usd=0.0)
        if prompt.startswith(b.EXTRACT_HEAD):
            index = int(re.search(r"PASSAGE \(chunk (\d+)", prompt).group(1))
            return copy.deepcopy(self.chunks.get(index, {"lines": []}))
        m = re.match(r"Name the beings, places and things \(build library, (\w+) pass\)", prompt)
        if m:
            return {"entries": copy.deepcopy(self.categories.get(m.group(1), []))}
        return CLASSIFY(prompt, schema)


def built(worlds, text, manifest, outputs, *, max_words=1500, name="w", time_of=None,
          ingest_kwargs=None, world=None):
    """Registry, plan, fake extraction and commit of one small story."""
    registry = b.Registry.from_manifest(manifest, text)
    chunks = b.plan(text, registry, max_words=max_words)
    model = FakeModel(outputs)
    results = b.extract(chunks, registry, model)
    w = world if world is not None else worlds(name)
    receipt = b.commit(w, registry, results, time_of=time_of,
                       ingest_kwargs={"classify": "rules"} if ingest_kwargs is None
                       else ingest_kwargs)
    return SimpleNamespace(registry=registry, chunks=chunks, results=results, world=w,
                           receipt=receipt, model=model)


def rows(world, entity=None, attribute=None):
    return [r for r in world.buffer.all_rows()
            if (entity is None or r.entity == entity)
            and (attribute is None or r.attribute == attribute)]


def values(world, entity, attribute):
    return [r.value for r in rows(world, entity, attribute)]


def entity_rows(world, entity):
    """The rows whose subject is ``entity``, in log order (no assertion subjects)."""
    return [r for r in world.buffer.all_rows() if r.entity == entity]


def E(key, type_, names, anchor, **kw):
    return b.Entry(key=key, type=type_, names=names, anchor_quote=anchor, **kw)


# ------------------------------------------------------------------ stories

REX_TEXT = {1: "A man called Rex walked into the yard. His dog, also called Rex, trotted after "
               "him.\n\nRex the dog barked at the gate. The man laughed.\n"}
REX = b.Manifest(entries=[
    E("rex_man", "person", ["Rex"], "A man called Rex walked into the yard."),
    E("rex_dog", "animal", ["Rex"], "His dog, also called Rex, trotted after him.",
      species="dog"),
])

HOLMES_TEXT = {1: "Sherlock Holmes lit his pipe. Mycroft Holmes read the paper. Mr. Holmes rose "
                  "and took his hat. Watson waited.\n"}
HOLMES = b.Manifest(entries=[
    E("sherlock", "person", ["Sherlock Holmes"], "Sherlock Holmes lit his pipe."),
    E("mycroft", "person", ["Mycroft Holmes"], "Mycroft Holmes read the paper."),
    E("watson", "person", ["Watson"], "Watson waited."),
])
SHERLOCK, MYCROFT, WATSON = "person:sherlock_holmes", "person:mycroft_holmes", "person:watson"

# The kitchen sink: a pick, an escape, a persona with a mid-chapter reveal, a
# place, and a being whose chunk writes a role word as its kind.
KS_TEXT = {
    1: "Sherlock Holmes lit his pipe. Mycroft Holmes read the paper. Mr. Holmes rose and "
       "took his hat.\n\nThe hooded stranger knocked at the door. A barmaid let the hooded "
       "stranger in.\n",
    2: "Orin waited at the dock. Orin was a condemned man now.\n\nThe hooded stranger was "
       "Lord Vane. Vane bowed.\n",
}
KS = b.Manifest(entries=[
    E("sherlock", "person", ["Sherlock Holmes"], "Sherlock Holmes lit his pipe."),
    E("mycroft", "person", ["Mycroft Holmes"], "Mycroft Holmes read the paper."),
    E("orin", "person", ["Orin"], "Orin waited at the dock."),
    E("vane", "person", ["Lord Vane", "Vane"], "Vane bowed.",
      personas=[b.Persona("the hooded stranger", "The hooded stranger knocked at the door.",
                          "The hooded stranger was Lord Vane.")]),
    E("dock", "place", ["the dock"], "Orin waited at the dock."),
])
KS_OUT = {
    0: {"lines": ["s4|new:0|took|hat",
                  "s5|person:the_hooded_stranger|knocked_at|door",
                  "s6|new:1|admits|@person:the_hooded_stranger"],
        "picks": [{"handle": "new:0", "surface": "Mr. Holmes", "candidates": [SHERLOCK, MYCROFT],
                   "choice": SHERLOCK, "evidence_quote": "Mr. Holmes rose and took his hat."}],
        "escapes": [{"handle": "new:1", "type": "person", "name": "a barmaid", "species": None,
                     "quote": "A barmaid let the hooded stranger in."}]},
    1: {"lines": ["s1|person:orin|in|@place:the_dock", "s2|person:orin|kind|condemned man"]},
    2: {"lines": ["s2|person:lord_vane|bows|true"]},
}


@pytest.fixture
def ks(worlds):
    return built(worlds, KS_TEXT, KS, KS_OUT, name="ks")


# ------------------------------------------------------------ 1. Rex


def test_1_rex_a_man_and_a_dog_stay_two_from_the_first_commit(worlds):
    out = built(worlds, REX_TEXT, REX, {0: {"lines": ["s3|person:rex_2|mood|excited",
                                                      "s4|person:rex|mood|amused"]}})
    w, reg = out.world, out.registry
    assert [e["id"] for e in reg.entries()] == ["person:rex", "person:rex_2"]
    assert values(w, "person:rex", "kind") == ["person"]
    assert values(w, "person:rex", "being_type") == ["person"]
    assert values(w, "person:rex", "species") == []
    assert values(w, "person:rex_2", "kind") == ["person"]
    assert values(w, "person:rex_2", "being_type") == ["animal"]
    assert values(w, "person:rex_2", "species") == ["dog"]
    # no role row for either, and R49's reclassification never fired
    assert rows(w, "person:rex", "role") == rows(w, "person:rex_2", "role") == []
    assert rows(w, attribute="reclassified_from") == []
    # "Rex the dog" with an animal hint is the dog; the Rex rule in code
    assert reg.resolve("Rex", 1, 3, hint="animal") == b.Resolved("person:rex_2")
    assert reg.resolve("Rex", 1, 3, hint="person") == b.Resolved("person:rex")
    assert reg.resolve("Rex", 1, 3, hint="being") == b.Ambiguous(("person:rex", "person:rex_2"))
    assert reg.resolve("Rex", 1, 3) == b.Ambiguous(("person:rex", "person:rex_2"))
    assert reg.resolve("Rex", 1, 3, hint="place") == b.Unknown()
    # the dog's facts are the dog's; no merge or proposal ever joins them
    assert w.state("person:rex_2", "mood").winner.value == "excited"
    assert w.state("person:rex", "mood").winner.value == "amused"
    for attribute in ("same_as", "maybe_same_as", "aka"):
        assert rows(w, attribute=attribute) == []
    assert w.porcelain.closure("person:rex") == ["person:rex"]
    assert w.porcelain.proposals() == []


def test_1_a_hint_outside_the_set_is_an_error():
    reg = b.Registry.from_manifest(REX, REX_TEXT)
    with pytest.raises(ValueError, match="unknown type hint"):
        reg.resolve("Rex", 1, 1, hint="dog")


# ------------------------------------------------------------ 2. namesakes

NAMESAKE_TEXT = {1: "Two men named John lived on the quay. John the baker opened his shop. "
                    "John the boatwright mended a hull.\n"}


def test_2_namesakes_stay_two_ids_with_a_distinct_from(worlds):
    manifest = b.Manifest(
        entries=[E("john_a", "person", ["John"], "John the baker opened his shop."),
                 E("john_b", "person", ["John"], "John the boatwright mended a hull.")],
        namesakes=[("john_a", "john_b", "Two men named John lived on the quay.")])
    out = built(worlds, NAMESAKE_TEXT, manifest, {})
    w = out.world
    assert [e["id"] for e in out.registry.entries()] == ["person:john", "person:john_2"]
    assert w.porcelain.distinct_between("person:john", "person:john_2")
    assert [(r.entity, r.value) for r in rows(w, attribute="distinct_from")] == [
        ("person:john", "person:john_2")]
    assert out.receipt.rejections == 1
    assert w.porcelain.closure("person:john") == ["person:john"]


# ------------------------------------------------------------ 3. quote anchors

ANCHOR_TEXT = {1: "The lamp was lit. The lamp was lit.\n\nMara “kept” the lamp.\n"
                  "She waited\nby the door.\n",
               2: "Orin rowed home.\n"}


def test_3_a_quote_found_once_resolves_after_folding_and_collapse():
    manifest = b.Manifest(entries=[
        E("mara", "person", ["Mara"], 'Mara "kept" the lamp.'),
        E("door", "place", ["the door"], "She waited by the door."),
        E("orin", "person", ["Orin"], "Orin rowed home."),
    ])
    reg = b.Registry.from_manifest(manifest, ANCHOR_TEXT)
    anchors = {e["key"]: e["anchor"] for e in reg.entries()}
    assert anchors == {"mara": (1, 3), "door": (1, 4), "orin": (2, 1)}


def test_3_quotes_found_0_or_2_times_are_refused_and_every_problem_is_listed_at_once():
    manifest = b.Manifest(entries=[
        E("a", "person", ["Ann"], "Nobody said this."),
        E("b", "object", ["the lamp"], "The lamp was lit."),
        E("c", "condemned man", ["Cal"], "Orin rowed home."),
    ])
    with pytest.raises(b.ManifestError) as exc:
        manifest.validate(ANCHOR_TEXT)
    problems = exc.value.problems
    assert [(p["where"], p["code"]) for p in problems] == [
        ("entries[0].anchor_quote", "quote_not_found"),
        ("entries[1].anchor_quote", "quote_not_unique"),
        ("entries[2].type", "role_as_type"),
    ]
    assert all(set(p) == {"where", "code", "detail"} and p["detail"] for p in problems)
    with pytest.raises(b.ManifestError):
        b.Registry.from_manifest(manifest, ANCHOR_TEXT)


CODES_TEXT = {1: "The masked rider crossed the ford. The masked rider laughed at the guards. "
                 "Ada sang. Ada sang. Bo ran.\n",
              2: "Lord Vane returned to the hall. Ida hid. Ida was the shade.\n"}


def test_3_validate_reports_every_listed_code():
    manifest = b.Manifest(
        entries=[
            E("t1", "obj:thing", ["Bo"], "Bo ran."),                          # unknown_type
            E("t2", "condemned man", ["Bo"], "Bo ran."),                      # role_as_type
            E("t2", "person", ["Bo"], "Bo ran."),                             # duplicate_key
            E("t4", "person", ["Ann"], "Nobody said this."),                  # quote_not_found
            E("t5", "person", ["Ada"], "Ada sang."),                          # quote_not_unique
            E("vane", "person", ["Lord Vane"], "Lord Vane returned to the hall.",
              personas=[b.Persona("the masked rider", "The masked rider crossed the ford.",
                                  "The masked rider laughed at the guards.")]),  # before entry
            E("ida", "person", ["Ida"], "Ida hid.",
              personas=[b.Persona("the shade", "Ida was the shade.", "Ida hid."),  # before intro
                        b.Persona("Bo", "Bo ran.", "Ida was the shade.")]),       # name is alias
            E("t8", "person", ["Bo"], "Bo ran.", species="human"),         # species_not_allowed
            E("t9", "person", [], "Bo ran."),                               # missing_field
            # CONTAINMENT-DURABILITY-V1: the three fixture codes.
            E("f1", "object", ["Bo"], "Bo ran.", fixture="yes"),            # fixture_not_bool
            E("f2", "person", ["Bo"], "Bo ran.", fixture=True),             # fixture_on_being
            E("f3", "group", ["Bo"], "Bo ran.", fixture=True),              # fixture_not_allowed
        ],
        namesakes=[("t4", "nobody", "Bo ran.")])                            # namesake_unknown_key
    problems = manifest.problems(CODES_TEXT)
    assert {p["code"] for p in problems} == set(b.CODES)
    by_code = {p["code"]: p["where"] for p in problems}
    assert by_code["persona_reveal_before_entry"] == "entries[5].personas[0].reveal_quote"
    assert by_code["persona_reveal_before_intro"] == "entries[6].personas[0].reveal_quote"
    assert by_code["persona_name_is_alias"] == "entries[6].personas[1].name"
    assert by_code["namesake_unknown_key"] == "namesakes[0]"
    assert by_code["duplicate_key"] == "entries[2].key"


# ------------------------------------------------------------ 4. the time gate

DUKE_TEXT = {1: "The village slept. Orin kept watch.\n", 2: "A rider came at dusk.\n",
             3: "Duke Orsino entered the hall.\n"}


def test_4_the_dukes_entry_anchored_in_chapter_3_is_never_a_chapter_2_candidate():
    manifest = b.Manifest(entries=[
        E("orin", "person", ["Orin"], "Orin kept watch."),
        E("duke", "person", ["Duke Orsino"], "Duke Orsino entered the hall."),
    ])
    reg = b.Registry.from_manifest(manifest, DUKE_TEXT)
    chunks = b.plan(DUKE_TEXT, reg)
    by_chapter = {c.chapter: [x.id for x in c.candidates] for c in chunks}
    assert "person:duke_orsino" not in by_chapter[1] + by_chapter[2]
    assert "person:duke_orsino" in by_chapter[3]
    assert reg.resolve("Orsino", 2, 1) == b.Unknown()
    assert reg.resolve("Orsino", 3, 1) == b.Resolved("person:duke_orsino")


STRANGER_TEXT = {
    1: "The hooded stranger took the key. The rain did not stop. A stranger in a hood waited "
       "by the well. The bells rang.\n",
    2: "Lord Vane smiled. The hooded stranger was Lord Vane all along. Vane left.\n",
}
STRANGER = b.Manifest(entries=[
    E("vane", "person", ["Lord Vane", "Vane"], "Lord Vane smiled.",
      personas=[b.Persona("the hooded stranger", "A stranger in a hood waited by the well.",
                          "The hooded stranger was Lord Vane all along.")]),
])
STRANGER_ID = "person:the_hooded_stranger"


def test_4_a_name_before_its_chosen_intro_gates_the_persona_at_the_name(worlds):
    out = built(worlds, STRANGER_TEXT, STRANGER,
                {0: {"lines": ["s1|person:the_hooded_stranger|carries|key"]}})
    reg = out.registry
    persona = reg.entries()[0]["personas"][0]
    assert persona["id"] == STRANGER_ID
    assert persona["gate"] == (1, 1)                  # the name's first occurrence
    assert reg.identity(STRANGER_ID).anchor == (1, 3)  # the chosen intro_quote
    assert reg.resolve("the hooded stranger", 1, 1) == b.Resolved(STRANGER_ID)
    chunk0 = out.chunks[0]
    assert {c.id: c.gate for c in chunk0.candidates}[STRANGER_ID] == 1
    assert out.results[0].gate_refused == () and len(out.results[0].items) == 1
    assert out.world.state(STRANGER_ID, "carries").winner.value == "key"


ORIN_TEXT = {1: "The ferry left at dawn. The river was high. Orin cast off the rope. Orin sang.\n"}
ORIN = b.Manifest(entries=[
    E("orin", "person", ["Orin"], "Orin sang."),
    E("river", "place", ["the river"], "The river was high."),
])


def test_4_a_line_before_its_candidates_gate_is_gate_refused_and_resolve_agrees(worlds):
    out = built(worlds, ORIN_TEXT, ORIN, {0: {"lines": [
        "s1|person:orin|mood|tired", "s3|person:orin|holds|rope", "s2|place:the_river|level|high",
        "s1|place:the_river|in|@person:orin"]}})
    reg, result = out.registry, out.results[0]
    assert reg.entries()[0]["gate"] == (1, 3) and reg.entries()[0]["anchor"] == (1, 4)
    assert [r.reason for r in result.gate_refused] == ["gate_refused", "gate_refused"]
    assert [r.where for r in result.gate_refused] == ["lines[0]", "lines[3]"]
    assert [(i["attribute"], i["sentence"]) for i in result.items] == [("holds", 3), ("level", 2)]
    assert reg.resolve("Orin", 1, 1) == b.Unknown()
    assert reg.resolve("Orin", 1, 3) == b.Resolved("person:orin")
    assert values(out.world, "person:orin", "holds") == ["rope"]
    assert values(out.world, "person:orin", "mood") == []


def test_4_a_line_citing_outside_its_chunk_or_citing_nothing_is_refused():
    reg = b.Registry.from_manifest(ORIN, ORIN_TEXT)
    chunk = b.plan(ORIN_TEXT, reg)[0]
    result = b.read_output(chunk, {"lines": ["s9|person:orin|mood|x", "s0|person:orin|mood|x",
                                             "person:orin|mood|x", "[s4]|person:orin|sings|true"]},
                           reg)
    assert [(r.where, r.reason) for r in result.refused] == [
        ("lines[0]", "citation_outside_chunk"), ("lines[1]", "citation_outside_chunk"),
        ("lines[2]", "malformed_line")]
    assert "missing sentence citation" in result.refused[2].detail
    assert [i["sentence"] for i in result.items] == [4]
    assert result.error is None


def test_4_a_reveal_mid_chunk_splits_before_the_reveal_sentence():
    reg = b.Registry.from_manifest(STRANGER, STRANGER_TEXT)
    chunks = b.plan(STRANGER_TEXT, reg)
    spans = [(c.chapter, c.first_sentence, c.last_sentence) for c in chunks]
    assert spans == [(1, 1, 4), (2, 1, 1), (2, 2, 3)]
    assert chunks[1].text == "Lord Vane smiled."
    assert chunks[2].text.startswith("The hooded stranger was Lord Vane all along.")


MID_TEXT = {1: "Rain fell on the docks. Orin waited. The grey lady stepped off the barge. She "
               "asked for Orin.\n",
            2: "The grey lady was Queen Ysolde. Ysolde wept.\n"}
MID = b.Manifest(entries=[
    E("orin", "person", ["Orin"], "Orin waited."),
    E("ysolde", "person", ["Queen Ysolde", "Ysolde"], "Ysolde wept.",
      personas=[b.Persona("the grey lady", "The grey lady stepped off the barge.",
                          "The grey lady was Queen Ysolde.")]),
])


def test_4_a_persona_introduced_mid_chunk_is_a_candidate_gated_from_its_intro(worlds):
    out = built(worlds, MID_TEXT, MID, {0: {"lines": ["s2|person:the_grey_lady|mood|calm",
                                                      "s3|person:the_grey_lady|came_by|barge"]}})
    gates = {c.id: c.gate for c in out.chunks[0].candidates}
    assert gates["person:the_grey_lady"] == 3
    assert "person:queen_ysolde" not in gates
    assert [r.reason for r in out.results[0].gate_refused] == ["gate_refused"]
    assert values(out.world, "person:the_grey_lady", "came_by") == ["barge"]
    assert values(out.world, "person:the_grey_lady", "mood") == []


# ------------------------------------------------------------ 5. personas

P_TEXT = {
    1: "The mill stood empty.\n\nOrin fished alone.\n",
    2: "The hooded stranger came to the mill. The hooded stranger lit a lamp.\n",
    3: "Duke Orsino rode in. The hooded stranger pulled back the hood: it was Duke Orsino."
       "\n\nOrsino laughed.\n",
}
P = b.Manifest(entries=[
    E("duke", "person", ["Duke Orsino", "Orsino"], "Orsino laughed.",
      personas=[b.Persona("the hooded stranger", "The hooded stranger came to the mill.",
                          "The hooded stranger pulled back the hood: it was Duke Orsino.")]),
    E("orin", "person", ["Orin"], "Orin fished alone."),
    E("mill", "place", ["the mill"], "The mill stood empty."),
])
P_OUT = {1: {"lines": ["s1|person:the_hooded_stranger|in|@place:the_mill",
                       "s2|person:the_hooded_stranger|lit|lamp"]},
         3: {"lines": ["s2|person:duke_orsino|mood|amused"]}}
DUKE = "person:duke_orsino"


@pytest.fixture
def personas(worlds):
    return built(worlds, P_TEXT, P, P_OUT, name="personas")


def test_5_a_persona_is_no_candidate_before_its_intro_and_resolves_to_itself_after(personas):
    reg, chunks = personas.registry, personas.chunks
    assert [(c.chapter, c.first_sentence, c.last_sentence) for c in chunks] == [
        (1, 1, 2), (2, 1, 2), (3, 1, 1), (3, 2, 3)]
    assert STRANGER_ID not in [c.id for c in chunks[0].candidates]
    assert reg.resolve("the hooded stranger", 1, 2) == b.Unknown()
    assert reg.resolve("the hooded stranger", 2, 2) == b.Resolved(STRANGER_ID)
    assert reg.resolve("the hooded stranger", 3, 3) == b.Resolved(STRANGER_ID)   # after the reveal too
    assert reg.resolve("Orsino", 3, 3) == b.Resolved(DUKE)


@pytest.mark.parametrize("intro, reveal", [
    ("The hooded stranger pulled back the hood", "it was Duke Orsino."),      # one sentence
    ("Orsino laughed.", "The hooded stranger pulled back the hood: it was Duke Orsino."),
])
def test_5_a_reveal_at_or_before_its_intro_is_refused(intro, reveal):
    manifest = b.Manifest(entries=[
        E("duke", "person", ["Duke Orsino"], "Orsino laughed.",
          personas=[b.Persona("the hooded stranger", intro, reveal)])])
    with pytest.raises(b.ManifestError) as exc:
        manifest.validate(P_TEXT)
    assert [p["code"] for p in exc.value.problems] == ["persona_reveal_before_intro"]


def test_5_commit_writes_one_aka_at_the_reveal_chunks_time(personas):
    w, receipt = personas.world, personas.receipt
    akas = rows(w, attribute="aka")
    assert [(r.entity, r.value, r.valid_from, r.frame) for r in akas] == [
        (STRANGER_ID, DUKE, 4, "canon")]                   # chunk 3 opens with the reveal
    assert receipt.correlations == 1 and receipt.pending_reveals == ()
    evidence = rows(w, akas[0].id, "evidence")
    assert [r.value for r in evidence] == [P.entries[0].personas[0].reveal_quote]


def test_5_the_personas_facts_stay_on_it_and_default_reads_of_the_duke_never_show_them(personas):
    w, p = personas.world, personas.world.porcelain
    assert values(w, STRANGER_ID, "lit") == ["lamp"]
    assert values(w, STRANGER_ID, "in") == ["place:the_mill"]
    for attribute in ("lit", "in"):
        assert p.state(DUKE, attribute)["status"] == "unknown"
        assert p.state(DUKE, attribute, as_of=10)["status"] == "unknown"
    assert not [f for f in p.facts("canon", entity=DUKE) if f["attribute"] in ("lit", "in")]
    # the dated aka still joins them on purpose, from the reveal on
    assert p.state_union(DUKE, "lit", as_of=10)["status"] == "known"
    assert p.state_union(DUKE, "lit", as_of=3)["status"] == "unknown"


def test_5_a_reveal_outside_the_committed_chunks_writes_no_aka(worlds):
    reg = b.Registry.from_manifest(P, P_TEXT)
    chunks = b.plan(P_TEXT, reg)
    results = b.extract(chunks[:2], reg, FakeModel(P_OUT))
    w = worlds()
    receipt = b.commit(w, reg, results, ingest_kwargs={"classify": "rules"})
    assert receipt.pending_reveals == (STRANGER_ID,) and receipt.correlations == 0
    assert rows(w, attribute="aka") == []


# ------------------------------------------------------------ 6. picks


def holmes_pick(choice=SHERLOCK, candidates=(SHERLOCK, MYCROFT)):
    return {0: {"lines": ["s4|new:0|took|hat"],
                "picks": [{"handle": "new:0", "surface": "Mr. Holmes",
                           "candidates": list(candidates), "choice": choice,
                           "evidence_quote": "Mr. Holmes rose and took his hat."}]}}


def test_6_an_ambiguous_pick_puts_its_facts_on_a_typed_mention_with_a_proposal(worlds):
    out = built(worlds, HOLMES_TEXT, HOLMES, holmes_pick())
    w, reg, receipt = out.world, out.registry, out.receipt
    assert reg.resolve("Mr. Holmes", 1, 4) == b.Ambiguous((SHERLOCK, MYCROFT))
    mention = receipt.handle_ids[(0, "new:0")]
    assert mention == "mention:mr_holmes_1" and ID_RE.fullmatch(mention)
    first = [(r.attribute, r.value) for r in entity_rows(w, mention)]
    assert first[:2] == [("kind", "person"), ("being_type", "person")]   # its type first
    assert ("took", "hat") in first
    assert values(w, SHERLOCK, "took") == []
    edges = rows(w, mention, "maybe_same_as")
    assert [(r.value, r.frame) for r in edges] == [(SHERLOCK, "canon")]
    assert values(w, edges[0].id, "evidence") == ["Mr. Holmes rose and took his hat."]
    proposals = w.porcelain.proposals()
    assert [(p["a"], p["b"], p["evidence"]) for p in proposals] == [
        (mention, SHERLOCK, "Mr. Holmes rose and took his hat.")]
    # nothing is merged
    assert rows(w, attribute="same_as") == []
    assert w.porcelain.closure(mention) == [mention]
    assert w.porcelain.closure(SHERLOCK) == [SHERLOCK]
    assert (receipt.mentions, receipt.proposals) == (1, 1)


def test_6_a_pick_outside_its_candidates_is_refused_with_its_lines(worlds):
    out = built(worlds, HOLMES_TEXT, HOLMES, holmes_pick(choice=WATSON))
    result = out.results[0]
    assert result.error is None and result.picks == () and result.items == ()
    assert [(r.where, r.reason) for r in result.refused] == [
        ("picks[0]", "pick_choice_not_candidate"), ("lines[0]", "refused_handle")]
    assert out.receipt.mentions == 0
    assert not [r for r in out.world.buffer.all_rows() if r.entity.startswith("mention:")]


def test_6_a_pick_needs_two_known_candidates():
    reg = b.Registry.from_manifest(HOLMES, HOLMES_TEXT)
    chunk = b.plan(HOLMES_TEXT, reg)[0]
    one = b.read_output(chunk, holmes_pick(candidates=(SHERLOCK,))[0], reg)
    assert [r.reason for r in one.refused][:1] == ["pick_not_ambiguous"]
    stranger = b.read_output(chunk, holmes_pick(candidates=(SHERLOCK, "person:moriarty"))[0],
                             reg)
    assert [r.reason for r in stranger.refused][:1] == ["pick_candidate_unknown"]


# ------------------------------------------------------------ 6a. handles


def test_6a_an_undeclared_or_unused_handle_refuses_the_chunk(worlds):
    reg = b.Registry.from_manifest(ORIN, ORIN_TEXT)
    chunk = b.plan(ORIN_TEXT, reg)[0]
    undeclared = b.read_output(chunk, {"lines": ["s3|new:0|mood|x"]}, reg)
    assert undeclared.error == "handles: used but not declared: new:0"
    unused = b.read_output(chunk, {"lines": ["s3|person:orin|mood|x"], "escapes": [
        {"handle": "new:1", "type": "person", "name": "a ferryman", "quote": "The ferry"}]}, reg)
    assert unused.error == "handles: declared but not used: new:1"
    twice = b.read_output(chunk, {"lines": ["s3|new:0|mood|x"], "escapes": [
        {"handle": "new:0", "type": "person", "name": "a", "quote": ""},
        {"handle": "new:0", "type": "person", "name": "b", "quote": ""}]}, reg)
    assert twice.error == "handles: declared twice: new:0"
    with pytest.raises(b.CommitRefused, match="refused at extraction"):
        b.commit(worlds(), reg, [undeclared])


def test_6a_every_committed_row_names_real_ids_never_handles(ks):
    for r in ks.world.buffer.all_rows():
        assert not r.entity.startswith("new:")
        if r.value_type == "entity":
            assert not str(r.value).startswith("new:")
        assert not r.frame.startswith("knows:new:")


BRECK_TEXT = {1: "Tomas Breck mended nets. Anna Breck sold fish. Breck shouted from the boat.\n"}
BRECK = b.Manifest(entries=[E("tomas", "person", ["Tomas Breck"], "Tomas Breck mended nets."),
                            E("anna", "person", ["Anna Breck"], "Anna Breck sold fish.")])


def test_6a_an_escape_colliding_with_two_entries_keeps_its_own_id_and_two_proposals(worlds):
    out = built(worlds, BRECK_TEXT, BRECK, {0: {
        "lines": ["s3|new:0|shouted|true"],
        "escapes": [{"handle": "new:0", "type": "person", "name": "Breck", "species": None,
                     "quote": "Breck shouted from the boat."}]}})
    w = out.world
    assert out.receipt.handle_ids[(0, "new:0")] == "person:breck"
    assert sorted(r.value for r in rows(w, "person:breck", "maybe_same_as")) == [
        "person:anna_breck", "person:tomas_breck"]
    assert values(w, "person:breck", "shouted") == [True]
    assert values(w, "person:tomas_breck", "shouted") == values(w, "person:anna_breck", "shouted") == []
    assert out.receipt.proposals == 2


# ------------------------- commit re-validates every result (pbr code review P1)


def world_reads(w) -> dict[str, Any]:
    """Every read a refused commit must leave unchanged."""
    from patternbuffer.dump import dump

    p = w.porcelain
    return {"dump": dump(w.buffer), "heads": p.axis_heads(),
            "facts": p.facts("canon", include_meta=True), "entities": p.entities("canon"),
            "proposals": p.proposals(),
            "states": [p.state(e, a) for e in ("person:rex", "person:rex_2", "person:orin")
                       for a in ("kind", "mood", "carries")]}


def hand_made(items, *, picks=(), escapes=(), index=0, chapter=1, first=1, last=4):
    return b.ChunkResult(index=index, items=tuple(items), escapes=tuple(escapes),
                         picks=tuple(picks), chapter=chapter, first_sentence=first,
                         last_sentence=last)


def test_p1_an_item_citing_no_sentence_is_refused_and_the_world_is_unchanged(worlds):
    """pbr's case: a hand-made ChunkResult whose item cites no sentence."""
    w = worlds()
    built(worlds, REX_TEXT, REX, {0: {"lines": ["s4|person:rex|mood|amused"]}}, world=w)
    reg = b.Registry.from_manifest(REX, REX_TEXT)
    before = world_reads(w)
    bad = b.ChunkResult(index=0, items=({"entity": "person:rex_2", "attribute": "mood",
                                         "value": "excited"},), escapes=(), picks=(),
                        chapter=1, first_sentence=1, last_sentence=4)
    with pytest.raises(b.CommitRefused, match="cites no sentence"):
        b.commit(w, reg, [bad], ingest_kwargs={"classify": "rules"})
    assert world_reads(w) == before


@pytest.mark.parametrize("sentence, match", [
    (5, "outside its chunk"), (0, "outside its chunk"), (-1, "outside its chunk"),
    (True, "cites no sentence"), ("2", "cites no sentence"), (2.0, "cites no sentence")])
def test_p1_an_item_citing_outside_its_chunk_is_refused(worlds, sentence, match):
    w = worlds()
    reg = b.Registry.from_manifest(REX, REX_TEXT)
    before = world_reads(w)
    bad = hand_made([{"entity": "person:rex_2", "attribute": "mood", "value": "excited",
                      "sentence": sentence}])
    with pytest.raises(b.CommitRefused, match=match):
        b.commit(w, reg, [bad])
    assert world_reads(w) == before


GATED_ITEMS = {        # each names Orin (gated at s3 of ORIN_TEXT) in one id position
    "subject": {"entity": "person:orin", "attribute": "mood", "value": "tired"},
    "value": {"entity": "place:the_river", "attribute": "carries", "value": "person:orin",
              "value_type": "entity"},
    "inferred value": {"entity": "place:the_river", "attribute": "carries",
                       "value": "person:orin"},
    "caused_by": {"entity": "place:the_river", "attribute": "level", "value": "high",
                  "caused_by": "person:orin"},
    "knows observer": {"entity": "place:the_river", "attribute": "level", "value": "high",
                       "frame": "knows:person:orin"},
}


@pytest.mark.parametrize("position", sorted(GATED_ITEMS))
def test_p1_an_item_citing_before_a_named_ids_gate_is_refused(worlds, position):
    w = worlds()
    reg = b.Registry.from_manifest(ORIN, ORIN_TEXT)
    before = world_reads(w)
    early = hand_made([{**GATED_ITEMS[position], "sentence": 2}])
    with pytest.raises(b.CommitRefused, match="person:orin is gated at chapter 1 sentence 3"):
        b.commit(w, reg, [early])
    assert world_reads(w) == before
    # at the gate the same item is accepted and written
    receipt = b.commit(w, reg, [hand_made([{**GATED_ITEMS[position], "sentence": 3}])],
                       ingest_kwargs={"classify": "rules"})
    assert receipt.chunk_spans[0]["seq"] is not None


def test_p1_malformed_items_and_unknown_ids_are_refused(worlds):
    w = worlds()
    reg = b.Registry.from_manifest(ORIN, ORIN_TEXT)
    before = world_reads(w)
    for items, match in (
            (["person:orin|mood|x"], "is not a fact item"),
            ([{"attribute": "mood", "value": "x", "sentence": 3}], "is not a fact item"),
            ([{"entity": "person:ghost", "attribute": "mood", "value": "x", "sentence": 3}],
             "never minted"),
            ([{"entity": "person:orin", "attribute": "mood", "value": "person:ghost",
               "sentence": 3}], "never minted"),
            ([{"entity": "new:0", "attribute": "mood", "value": "x", "sentence": 3}],
             "undeclared handles")):
        with pytest.raises(b.CommitRefused, match=match):
            b.commit(w, reg, [hand_made(items)])
    assert world_reads(w) == before


def test_p1_a_pick_must_choose_among_candidates_of_its_chunk(worlds):
    w = worlds()
    reg = b.Registry.from_manifest(b.Manifest(entries=[
        E("orin", "person", ["Orin"], "Orin kept watch."),
        E("duke", "person", ["Duke Orsino"], "Duke Orsino entered the hall.")]), DUKE_TEXT)
    before = world_reads(w)
    pick = b.Pick(handle="new:0", surface="the watchman",
                  candidates=("person:orin", "person:duke_orsino"), choice="person:orin",
                  evidence_quote="Orin kept watch.")
    early = hand_made([{"entity": "new:0", "attribute": "mood", "value": "x", "sentence": 2}],
                      picks=[pick], first=1, last=2)
    with pytest.raises(b.CommitRefused, match="candidates of its chunk"):
        b.commit(w, reg, [early])
    assert world_reads(w) == before


def test_p1_extract_reads_an_id_shaped_bare_value_as_the_gate_does(worlds):
    """The gate infers an id-shaped bare value to be an entity, so extract checks
    it as one and commit rewrites a bare build handle like an @ one."""
    reg = b.Registry.from_manifest(ORIN, ORIN_TEXT)
    chunk = b.plan(ORIN_TEXT, reg)[0]
    early = b.read_output(chunk, {"lines": ["s2|place:the_river|carries|person:orin",
                                            "s3|place:the_river|carries|person:ghost"]}, reg)
    assert [r.reason for r in early.gate_refused] == ["gate_refused"]
    assert [r.reason for r in early.refused] == ["unknown_id"]
    out = built(worlds, ORIN_TEXT, ORIN, {0: {
        "lines": ["s2|place:the_river|carries|new:0"],
        "escapes": [esc("new:0", "a ferry", "The ferry left at dawn.", type_="object")]}})
    assert values(out.world, "place:the_river", "carries") == ["obj:a_ferry"]
    assert not [r for r in out.world.buffer.all_rows()
                if isinstance(r.value, str) and r.value.startswith("new:")]


# ----------------- commit accepts exactly extract's language (pbr re-review, r1.7)


@pytest.mark.parametrize("decl", [
    b.Escape("new:0", "object", "forged lantern", None, "a lantern"),
    b.Pick("new:0", "Rex", ("person:rex", "person:rex_2"), "person:rex",
           "Rex the dog barked at the gate."),
], ids=["escape", "pick"])
def test_r17_a_declared_handle_no_item_uses_is_refused_and_the_world_is_unchanged(worlds,
                                                                                    decl):
    """pbr's P1a: a hand-made result declaring a build handle no item uses."""
    w = worlds()
    reg = b.Registry.from_manifest(REX, REX_TEXT)
    before = world_reads(w)
    forged = hand_made([], escapes=[decl] if isinstance(decl, b.Escape) else [],
                       picks=[decl] if isinstance(decl, b.Pick) else [])
    with pytest.raises(b.CommitRefused, match="declares build handles no item uses"):
        b.commit(w, reg, [forged])
    assert world_reads(w) == before
    assert not rows(w, "obj:forged_lantern") and not rows(w, "mention:rex_1")


# Rex the man is named at s1; Rèx the dog first at s2 ("Rèx" slugs like "Rex",
# so the dog is person:rex_2, but its tokens differ, so its gate is s2).
REX2_TEXT = {1: "Rex walked into the yard. His dog Rèx trotted after him. Rex laughed. "
                "Rèx barked.\n"}
REX2 = b.Manifest(entries=[
    E("man", "person", ["Rex"], "Rex walked into the yard."),
    E("dog", "animal", ["Rèx"], "His dog Rèx trotted after him.", species="dog"),
])


def test_r17_an_early_same_as_side_key_is_refused_with_nothing_written(worlds):
    """pbr's P1b: a cited-s1 item on person:rex carrying same_as person:rex_2,
    which is gated at s2, would have written a canon maybe_same_as."""
    reg = b.Registry.from_manifest(REX2, REX2_TEXT)
    assert [(i.id, i.gate) for i in reg.identities] == [("person:rex", (1, 1)),
                                                       ("person:rex_2", (1, 2))]
    w = worlds()
    before = world_reads(w)
    early = hand_made([{"entity": "person:rex", "attribute": "mood", "value": "calm",
                        "sentence": 1, "same_as": "person:rex_2"}])
    with pytest.raises(b.CommitRefused, match="keys the grammar never writes: same_as"):
        b.commit(w, reg, [early])
    assert world_reads(w) == before
    assert rows(w, attribute="maybe_same_as") == []


@pytest.mark.parametrize("extra", [
    {"aliases": ["the ferryman"]}, {"confidence": 0.9}, {"arity": "set_valued"},
    {"complete": True}, {"fold_policy": "accrue"}, {"valid_form": 3.0},
    {"status": "generated"}, {"status": "retracted"}, {"value_type": "delta"},
    {"value_type": "literal"}, {"timeless": False}, {"correction": 1},
    {"valid_from": "3"}, {"frame": 7}, {"value": {1, 2}}, {"attribute": "Mood"},
], ids=lambda extra: "-".join(f"{k}={v}" for k, v in extra.items()))
def test_r17_an_item_the_grammar_could_not_write_is_refused_with_nothing_written(worlds,
                                                                                extra):
    w = worlds()
    reg = b.Registry.from_manifest(ORIN, ORIN_TEXT)
    before = world_reads(w)
    item = {"entity": "person:orin", "attribute": "mood", "value": "x", "sentence": 3, **extra}
    with pytest.raises(b.CommitRefused, match="is not a fact item the grammar writes"):
        b.commit(w, reg, [hand_made([item])])
    assert world_reads(w) == before


SOURCES = ["s2|place:the_river|level|high|src=person:orin",       # Orin is gated at s3
           "s3|place:the_river|level|high|src=person:orin",       # at the gate
           "s2|place:the_river|level|high|doc=doc:letter_1",      # document provenance
           "s3|place:the_river|level|high|src=person:ghost",      # no such person
           "s3|place:the_river|level|high|src=person:Mara Senn",  # person-shaped, not an id
           "s3|place:the_river|level|high|src=the ferry log"]     # free-text provenance


def test_r17_extract_gates_a_source_like_every_id_position():
    reg = b.Registry.from_manifest(ORIN, ORIN_TEXT)
    chunk = b.plan(ORIN_TEXT, reg)[0]
    result = b.read_output(chunk, {"lines": SOURCES}, reg)
    assert [(r.where, r.reason) for r in result.gate_refused] == [("lines[0]", "gate_refused")]
    assert [(r.where, r.reason) for r in result.refused] == [
        ("lines[3]", "unknown_id"), ("lines[4]", "unknown_id")]
    assert [i["source_doc"] for i in result.items] == [
        "person:orin", "doc:letter_1", "the ferry log"]


def test_r17_extract_checks_sources_against_the_whole_registry_privately():
    manifest = b.Manifest(entries=[E("orin", "person", ["Orin"], "Orin kept watch."),
                                   E("duke", "person", ["Duke Orsino"],
                                     "Duke Orsino entered the hall.")])
    reg = b.Registry.from_manifest(manifest, DUKE_TEXT)
    chunk = b.plan(DUKE_TEXT, reg)[0]
    assert "duke" not in build_prompt(chunk, reg.book).lower()    # no later identity shown
    result = b.read_output(chunk, {"lines": [
        "s2|person:orin|warned_of|rider|src=person:duke_orsino"]}, reg)
    assert [r.reason for r in result.gate_refused] == ["gate_refused"]
    assert "chapter 3 sentence 1" in result.gate_refused[0].detail


@pytest.mark.parametrize("source, cited, refused", [
    ("person:orin", 2, "person:orin is gated at chapter 1 sentence 3"),
    ("person:orin", 3, None),
    ("doc:letter_1", 2, None),
    ("person:ghost", 3, "names no entity of this registry"),
    ("person:Mara Senn", 3, "names no entity of this registry"),
])
def test_r17_commit_gates_a_source_like_every_id_position(worlds, source, cited, refused):
    w = worlds()
    reg = b.Registry.from_manifest(ORIN, ORIN_TEXT)
    before = world_reads(w)
    item = {"entity": "place:the_river", "attribute": "level", "value": "high",
            "sentence": cited, "source_doc": source}
    if refused is not None:
        with pytest.raises(b.CommitRefused, match=refused):
            b.commit(w, reg, [hand_made([item])])
        assert world_reads(w) == before
        return
    b.commit(w, reg, [hand_made([item])], ingest_kwargs={"classify": "rules"})
    assert values(w, rows(w, "place:the_river", "level")[0].id, "source") == [source]


def test_r17_a_build_handle_as_a_source_is_rewritten_to_its_id(worlds):
    out = built(worlds, ORIN_TEXT, ORIN, {0: {
        "lines": ["s3|place:the_river|level|high|src=new:0"],
        "escapes": [esc("new:0", "a boatman", "Orin cast off the rope.")]}})
    row = rows(out.world, "place:the_river", "level")[0]
    assert values(out.world, row.id, "source") == ["person:a_boatman"]


# ------------------------------------------------------------ 6b. one allocator

SLUG_TEXT = {
    1: "The Stranger rode north. The-stranger walked south. Lord Vane slept. Queen Ysolde sang.\n",
    2: "The Stranger was Lord Vane. The-stranger was Queen Ysolde.\n",
}


def test_6b_personas_slugging_alike_mint_distinct_ids():
    manifest = b.Manifest(entries=[
        E("vane", "person", ["Lord Vane"], "Lord Vane slept.",
          personas=[b.Persona("The Stranger", "The Stranger rode north.",
                              "The Stranger was Lord Vane.")]),
        E("ysolde", "person", ["Queen Ysolde"], "Queen Ysolde sang.",
          personas=[b.Persona("the-stranger", "The-stranger walked south.",
                              "The-stranger was Queen Ysolde.")]),
    ])
    reg = b.Registry.from_manifest(manifest, SLUG_TEXT)
    ids = [(e["id"], [p["id"] for p in e["personas"]]) for e in reg.entries()]
    assert ids == [("person:lord_vane", ["person:the_stranger"]),
                   ("person:queen_ysolde", ["person:the_stranger_2"])]


ODELL_TEXT = {1: "O'Dell kept the inn. A man called O Dell drank there. Pell watched them.\n",
              2: "O Dell was Pell in disguise. Pell paid.\n"}


def test_6b_a_persona_slugging_like_an_entry_mints_a_distinct_id():
    manifest = b.Manifest(entries=[
        E("odell", "person", ["O'Dell"], "O'Dell kept the inn."),
        E("pell", "person", ["Pell"], "Pell paid.",
          personas=[b.Persona("O Dell", "A man called O Dell drank there.",
                              "O Dell was Pell in disguise.")]),
    ])
    reg = b.Registry.from_manifest(manifest, ODELL_TEXT)
    assert [i.id for i in reg.identities] == ["person:o_dell", "person:pell", "person:o_dell_2"]


def test_6b_mentions_and_escapes_draw_from_the_same_allocator(worlds):
    text = {1: "Rex barked. Rex Hale whistled. Rex Hale waved.\n"}
    manifest = b.Manifest(entries=[E("dog", "animal", ["Rex"], "Rex barked.", species="dog"),
                                   E("man", "person", ["Rex Hale"], "Rex Hale whistled.")])
    out = built(worlds, text, manifest, {0: {
        "lines": ["s1|new:0|barks|true", "s3|new:1|waves|true"],
        "escapes": [{"handle": "new:0", "type": "animal", "name": "Rex", "species": "dog",
                     "quote": "Rex barked."},
                    {"handle": "new:1", "type": "person", "name": "Rex Hale",
                     "quote": "Rex Hale waved."}]}})
    minted = out.receipt.minted
    assert len(set(minted)) == len(minted)
    assert out.receipt.handle_ids == {(0, "new:0"): "person:rex_2",
                                      (0, "new:1"): "person:rex_hale_2"}


# ------------------------------------------------------------ 7. escapes

E_TEXT = {
    1: "The guard watched the gate. Mira Vell crossed the bridge.\n\nThe barmaid poured ale "
       "for Orin.\n\nThe barmaid laughed at Orin.\n",
    2: "Orin slept.\n",
    3: "The guard yawned at dawn. Mira Vell bought bread. A condemned man prayed.\n",
}
E_MANIFEST = b.Manifest(entries=[E("orin", "person", ["Orin"], "Orin slept.")])


def esc(handle, name, quote, type_="person", species=None):
    return {"handle": handle, "type": type_, "name": name, "species": species, "quote": quote}


E_OUT = {
    0: {"lines": ["s1|new:0|watches|gate", "s2|new:1|crossed|bridge"],
        "escapes": [esc("new:0", "the guard", "The guard watched the gate."),
                    esc("new:1", "Mira Vell", "Mira Vell crossed the bridge.")]},
    1: {"lines": ["s1|new:0|serves|@person:orin"],
        "escapes": [esc("new:0", "the barmaid", "The barmaid poured ale for Orin.")]},
    2: {"lines": ["s1|new:0|mood|merry", "s1|new:1|laughs_at|@new:0"],
        "escapes": [esc("new:0", "the barmaid", "The barmaid laughed at Orin."),
                    esc("new:1", "Orin", "The barmaid laughed at Orin.")]},
    4: {"lines": ["s1|new:0|yawned|true", "s2|new:1|bought|bread", "s3|new:2|prays|true"],
        "escapes": [esc("new:0", "the guard", "The guard yawned at dawn."),
                    esc("new:1", "Mira Vell", "Mira Vell bought bread."),
                    esc("new:2", "a condemned man", "A condemned man prayed.",
                        type_="condemned man")]},
}


@pytest.fixture
def escapes(worlds):
    return built(worlds, E_TEXT, E_MANIFEST, E_OUT, max_words=10, name="escapes")


def test_7_the_plan_cuts_paragraphs_under_max_words(escapes):
    assert [(c.chapter, c.first_sentence, c.last_sentence) for c in escapes.chunks] == [
        (1, 1, 2), (1, 3, 3), (1, 4, 4), (2, 1, 1), (3, 1, 3)]


def test_7_two_chunks_of_one_chapter_escaping_the_barmaid_converge(escapes):
    ids = escapes.receipt.handle_ids
    assert ids[(1, "new:0")] == ids[(2, "new:0")] == "person:the_barmaid"
    assert values(escapes.world, "person:the_barmaid", "serves") == ["person:orin"]
    assert values(escapes.world, "person:the_barmaid", "mood") == ["merry"]


def test_7_a_description_in_two_chapters_stays_two_ids_with_a_proposal(escapes):
    ids, w = escapes.receipt.handle_ids, escapes.world
    assert (ids[(0, "new:0")], ids[(4, "new:0")]) == ("person:the_guard", "person:the_guard_2")
    edges = rows(w, "person:the_guard_2", "maybe_same_as")
    assert [r.value for r in edges] == ["person:the_guard"]
    assert values(w, edges[0].id, "evidence") == ["The guard yawned at dawn."]
    assert w.porcelain.closure("person:the_guard_2") == ["person:the_guard_2"]


def test_7_a_proper_name_in_two_chapters_converges(escapes):
    ids = escapes.receipt.handle_ids
    assert ids[(0, "new:1")] == ids[(4, "new:1")] == "person:mira_vell"
    assert values(escapes.world, "person:mira_vell", "name") == ["Mira Vell"]


def test_7_an_escape_colliding_with_the_manifest_is_a_proposal_not_a_join(escapes):
    w, ids = escapes.world, escapes.receipt.handle_ids
    assert ids[(2, "new:1")] == "person:orin_2"
    assert [r.value for r in rows(w, "person:orin_2", "maybe_same_as")] == ["person:orin"]
    assert values(w, "person:orin_2", "laughs_at") == ["person:the_barmaid"]
    assert values(w, "person:orin", "laughs_at") == []
    assert w.porcelain.closure("person:orin") == ["person:orin"]


def test_7_an_escape_typed_with_a_role_word_is_a_person_with_that_role(escapes):
    w = escapes.world
    escape = escapes.receipt.handle_ids[(4, "new:2")]
    assert escape == "person:a_condemned_man"
    assert [(r.attribute, r.value) for r in entity_rows(w, escape)][:4] == [
        ("kind", "person"), ("being_type", "person"), ("name", "a condemned man"),
        ("role", "condemned man")]
    assert b.coerce_type("Condemned Man") == ("person", "Condemned Man")
    assert b.coerce_type(" Animal ") == ("animal", None)


# ------------------------------------------------------------ 7a. mixed-type picks

RX_TEXT = {1: "Rex Hale fed his dog Rex. The Rex sailed at noon. Rex barked. Rex waved from "
              "the Rex.\n"}
RX = b.Manifest(entries=[
    E("man", "person", ["Rex"], "Rex Hale fed his dog Rex."),
    E("dog", "animal", ["Rex"], "Rex barked.", species="dog"),
    E("ship", "object", ["The Rex"], "The Rex sailed at noon."),
])


def test_7a_a_pick_among_beings_of_two_types_is_kind_person_and_among_mixed_is_untyped(worlds):
    out = built(worlds, RX_TEXT, RX, {0: {
        "lines": ["s3|new:0|barks|true", "s4|new:1|seen_from|true"],
        "picks": [{"handle": "new:0", "surface": "Rex", "candidates": ["person:rex", "person:rex_2"],
                   "choice": "person:rex_2", "evidence_quote": "Rex barked."},
                  {"handle": "new:1", "surface": "the Rex",
                   "candidates": ["person:rex", "obj:the_rex"], "choice": "obj:the_rex",
                   "evidence_quote": "Rex waved from the Rex."}]}})
    w, ids = out.world, out.receipt.handle_ids
    beings, mixed = ids[(0, "new:0")], ids[(0, "new:1")]
    assert (beings, mixed) == ("mention:rex_1", "mention:the_rex_1")
    assert [(r.attribute, r.value) for r in entity_rows(w, beings)][:2] == [
        ("kind", "person"), ("barks", True)]
    assert values(w, beings, "being_type") == []
    assert values(w, mixed, "kind") == [] and values(w, mixed, "being_type") == []
    edge = rows(w, mixed, "maybe_same_as")[0]
    assert edge.value == "obj:the_rex"
    assert values(w, edge.id, "candidates") == [["person:rex", "obj:the_rex"]]
    assert values(w, rows(w, beings, "maybe_same_as")[0].id, "candidates") == []


# ------------------------------------------------------------ 7b. context in workers

HOST_VAR: contextvars.ContextVar[str | None] = contextvars.ContextVar("host_timing_log",
                                                                      default=None)


def test_7b_a_host_context_variable_and_the_label_reach_every_worker_call():
    reg = b.Registry.from_manifest(P, P_TEXT)
    chunks = b.plan(P_TEXT, reg)
    seen: list[tuple[Any, Any, str]] = []
    lock = threading.Lock()

    def model(prompt, schema):
        with lock:
            seen.append((HOST_VAR.get(), b.current_label(), threading.current_thread().name))
        return {"lines": []}

    token = HOST_VAR.set("timing-log-7b")
    try:
        results = b.extract(chunks, reg, model, workers=3)
    finally:
        HOST_VAR.reset(token)
    assert len(seen) == len(chunks) == len(results)
    assert {value for value, _, _ in seen} == {"timing-log-7b"}
    assert sorted(label["unit"] for _, label, _ in seen) == [
        f"chunk:{c.index:02d}" for c in chunks]
    assert {label["stage"] for _, label, _ in seen} == {"extract"}
    assert all(name != threading.main_thread().name for _, _, name in seen)
    assert b.current_label() is None


# ------------------------------------------------------------ 7c. the persona link


def test_7c_the_only_row_linking_a_persona_and_its_entry_is_the_aka(personas):
    w = personas.world
    linking = [r for r in w.buffer.all_rows()
               if {r.entity, r.value} == {STRANGER_ID, DUKE}]
    assert [(r.attribute, r.entity, r.value) for r in linking] == [("aka", STRANGER_ID, DUKE)]
    names = values(w, DUKE, "name") + values(w, DUKE, "alias")
    assert book_gold.book_normalize("the hooded stranger") not in {
        book_gold.book_normalize(n) for n in names}
    assert values(w, STRANGER_ID, "name") == ["the hooded stranger"]
    for attribute in ("in", "lit"):
        assert w.porcelain.state(DUKE, attribute, as_of=3)["status"] == "unknown"


# ------------------------------------------------------------ 8. shape first


def test_8_every_minted_ids_first_rows_are_its_shape_rows(ks):
    w, reg, receipt = ks.world, ks.registry, ks.receipt
    mention = receipt.handle_ids[(0, "new:0")]
    barmaid = receipt.handle_ids[(0, "new:1")]
    expected = {ident.id: b.shape_rows(ident.id, ident.type, ident.species)
                for ident in reg.identities}
    expected[mention] = b.shape_rows(mention, "person")
    expected[barmaid] = b.shape_rows(barmaid, "person")
    assert set(expected) == set(receipt.minted)
    for minted, shape in expected.items():
        first = [(r.attribute, r.value, r.valid_from, r.frame)
                 for r in entity_rows(w, minted)[:len(shape)]]
        assert first == [(s["attribute"], s["value"], None, "canon") for s in shape], minted
        assert values(w, minted, "kind") == [shape[0]["value"]]  # no other kind row


def test_8_beings_carry_kind_person_and_r49_never_moves_a_shape_row(ks):
    w = ks.world
    for minted in ks.receipt.minted:
        ident_type = values(w, minted, "being_type")
        if minted.startswith("person:"):
            assert values(w, minted, "kind") == ["person"] and len(ident_type) == 1
    shape_ids = {r.id for m in ks.receipt.minted for r in entity_rows(w, m)
                 if r.attribute in ("kind", "being_type", "species")}
    for receipt in rows(w, attribute="reclassified_from"):
        moved = w.buffer.get(receipt.entity)
        assert moved.id not in shape_ids and moved.valid_from is not None


def test_8_a_beings_role_word_kind_becomes_a_role_never_a_kind_conflict(ks):
    w = ks.world
    assert values(w, "person:orin", "role") == ["condemned man"]
    assert len(rows(w, attribute="reclassified_from")) == 1
    fold = w.state("person:orin", "kind")
    assert fold.winner.value == "person" and not fold.conflicted


# ------------------------------------------------------------ 9. no leaks

LEAK_TEXT = {
    1: "# Chapter 1: The Visitor\n\nThe hooded visitor stood at the door of the mill.\n\n"
       "Orin watched the hooded visitor from the dock.\n",
    2: "# Chapter 2: The Lamp\n\nThe hooded visitor took the brass lamp.\n\n"
       "Orin followed the hooded visitor to the cellar.\n",
    3: "# Chapter 3: The Reveal\n\nOrin walked to the mill. The hooded visitor lowered her "
       "hood and Orin saw that she was Mara Senn. Mara set the lamp down.\n",
}
LEAK_PLACES = [E("orin", "person", ["Orin"], "Orin watched the hooded visitor from the dock."),
               E("mill", "place", ["the mill"], "Orin walked to the mill."),
               E("lamp", "object", ["the brass lamp"], "The hooded visitor took the brass lamp.")]
LEAK = b.Manifest(entries=[
    E("mara", "person", ["Mara Senn", "Mara"], "Mara set the lamp down.",
      personas=[b.Persona("the hooded visitor",
                          "The hooded visitor stood at the door of the mill.",
                          "The hooded visitor lowered her hood and Orin saw that she was "
                          "Mara Senn.")]),
    *LEAK_PLACES,
])
VISITOR = "person:the_hooded_visitor"
LEAK_OUT = {
    0: {"lines": [f"s2|{VISITOR}|in|@place:the_mill", f"s3|person:orin|watches|@{VISITOR}",
                  # a model that names Mara before the text does: refused, not a leak
                  "s2|person:mara_senn|in|@place:the_mill"]},
    1: {"lines": [f"s2|obj:the_brass_lamp|held_by|@{VISITOR}",
                  f"s3|person:orin|follows|@{VISITOR}"]},
    2: {"lines": ["s2|person:orin|in|@place:the_mill"]},
    3: {"lines": ["s2|obj:the_brass_lamp|in|@place:the_mill",
                  "s1|person:mara_senn|in|@place:the_mill"]},
}
LEAK_GRADED = {
    "key_sha256": "x", "readers": ["A", "B"],
    "entities": {"mara": {"kind": "person", "aliases": ["Mara Senn", "Mara", "the hooded visitor"]},
                 "orin": {"kind": "person", "aliases": ["Orin"]},
                 "mill": {"kind": "place", "aliases": ["the mill"]},
                 "lamp": {"kind": "object", "aliases": ["the brass lamp", "the lamp"]}},
    "same_as": [{"id": "same_as[0]", "entity": "mara", "alias": "the hooded visitor", "chapter": 3}],
    "not_same": [], "moves": {}, "containers": [], "dropped": [], "ungraded_counts": {},
    "alias_first_chapter": {"mara": {"Mara Senn": 3, "Mara": 3, "the hooded visitor": 1},
                            "orin": {"Orin": 1}},
}


def leak_grade(out):
    spans = gl.Spans({"chunks": list(out.receipt.chunk_spans)})
    texts = {c.index: c.text for c in out.chunks}
    pass0 = rb.library_registry_view(out.registry, WID)
    return gl.grade_leaks(out.world, LEAK_GRADED, spans, texts, pass0)


def test_9_a_fake_build_with_one_reveal_has_zero_chunk_and_registry_leaks(worlds):
    out = built(worlds, LEAK_TEXT, LEAK, LEAK_OUT, time_of=lambda i: float(i + 1))
    assert [r.reason for r in out.results[0].refused] == ["unknown_id"]   # Mara, too early
    grade = leak_grade(out)
    entry = grade["identity_leaks"]["entries"][0]
    assert entry["pre_reveal_chunks"] == [0, 1]           # the check ran on real chunks
    assert entry["chunk_leak_rows"] == 0 and entry["rows"] == []
    assert grade["identity_leaks"]["chunk_leak_rows"] == 0
    assert grade["identity_leaks"]["registry_leaks"] == 0
    assert grade["alias_leaks"]["count"] == 0
    assert grade["total"] == 0 and grade["unmeasured_parts"] == []
    # the persona's pre-reveal rows exist, on the persona id
    assert values(out.world, VISITOR, "in") == ["place:the_mill"]


def test_9_the_grader_does_see_the_leak_a_merged_name_would_make(worlds):
    """The control: the same story with the visitor written as Mara's alias
    (what a persona exists to prevent) leaks through the registry and the chunks."""
    naive = b.Manifest(entries=[
        E("mara", "person", ["Mara Senn", "Mara", "the hooded visitor"], "Mara set the lamp down."),
        *LEAK_PLACES])
    mara = "person:mara_senn"
    outputs = {0: {"lines": [f"s2|{mara}|in|@place:the_mill"]},
               1: {"lines": [f"s2|{mara}|takes|@obj:the_brass_lamp"]}}
    grade = leak_grade(built(worlds, LEAK_TEXT, naive, outputs, name="naive"))
    assert grade["identity_leaks"]["registry_leaks"] == 1
    assert grade["identity_leaks"]["chunk_leak_rows"] == 2


# ------------------------------------------------- 10. time_of and ingest_kwargs


def test_10_time_of_and_ingest_kwargs_pass_through(worlds, monkeypatch):
    w = worlds("passthrough")
    calls: list[dict] = []
    real = w.porcelain.ingest_structured

    def spy(items, **kwargs):
        calls.append(kwargs)
        return real(items, **kwargs)

    monkeypatch.setattr(w.porcelain, "ingest_structured", spy)
    out = built(worlds, KS_TEXT, KS, KS_OUT, world=w, time_of=lambda i: 100.0 + 10 * i,
                ingest_kwargs={"classify": "rules", "cursor_authoritative": True})
    assert len(calls) > 10
    assert all(c["classify"] == "rules" and c["cursor_authoritative"] is True for c in calls)
    assert out.receipt.time_of == {0: 100.0, 1: 110.0, 2: 120.0}
    by_seq = {r.seq: r for r in w.buffer.all_rows()}
    for span in out.receipt.chunk_spans:
        lo, hi = span["seq"]
        stamped = {by_seq[s].valid_from for s in range(lo, hi + 1)
                   if by_seq[s].valid_from is not None and not by_seq[s].entity.startswith("a:")}
        assert stamped == {span["cursor"]}
    assert [r.valid_from for r in rows(w, attribute="aka")] == [120.0]


@pytest.mark.parametrize("kwargs", [{"at": 3.0}, {"items": []}, {"model": True}])
def test_10_ingest_kwargs_refuse_what_commit_owns(worlds, kwargs):
    reg = b.Registry.from_manifest(REX, REX_TEXT)
    with pytest.raises(ValueError, match="ingest_kwargs"):
        b.commit(worlds(), reg, [], ingest_kwargs=kwargs)


def test_10_time_of_must_be_finite(worlds):
    reg = b.Registry.from_manifest(REX, REX_TEXT)
    results = b.extract(b.plan(REX_TEXT, reg), reg, FakeModel())
    w = worlds()
    with pytest.raises(ValueError, match="finite"):
        b.commit(w, reg, results, time_of=lambda i: float("nan"))
    assert w.buffer.head() == 3                      # world:self and its physics only


# ------------------------------------------------------------ 11. prompt heads


def test_11_the_prompt_heads_are_pinned_and_every_call_starts_with_its_head():
    assert b.EXTRACT_HEAD == "Extract world-state facts (build library, chunk)"
    assert b.CATEGORY_HEAD == "Name the beings, places and things (build library, {category} pass)"
    reg = b.Registry.from_manifest(P, P_TEXT)
    model = FakeModel(P_OUT)
    b.extract(b.plan(P_TEXT, reg), reg, model)
    assert len(model.prompts) == 4 and all(p.startswith(b.EXTRACT_HEAD) for p in model.prompts)
    cats = FakeModel(categories={})
    b.category_passes(P_TEXT, cats)
    heads = sorted(p.splitlines()[0] for p in cats.prompts)
    assert heads == sorted(b.CATEGORY_HEAD.format(category=c) for c in b.DEFAULT)


# ------------------------------------------------------------ 12. category passes

CAT_TEXT = {
    1: "Mara Senn rowed to the mill. The hooded visitor waited on the bank. Rex the dog barked "
       "at the visitor.\n",
    2: "John the baker sold bread. John the boatwright bought some. The brass lamp hung in the "
       "mill.\n",
}
CAT_OUT = {
    "beings": [
        {"type": "person", "name": "Mara Senn", "aliases": ["Mara", "the hooded visitor"],
         "quote": "Mara Senn rowed to the mill."},
        {"type": "person", "name": "the hooded visitor", "aliases": [],
         "quote": "The hooded visitor waited on the bank."},
        {"type": "animal", "name": "Rex", "aliases": [], "species": "dog",
         "quote": "Rex the dog barked at the visitor."},
        {"type": "person", "name": "John", "aliases": [], "quote": "John the baker sold bread."},
        {"type": "person", "name": "John", "aliases": [],
         "quote": "John the boatwright bought some."},
        {"type": "baker", "name": "the baker", "aliases": [], "quote": "a paraphrase, not a quote"},
    ],
    "places": [{"type": "place", "name": "the mill", "aliases": ["mill"],
                "quote": "Mara Senn rowed to the mill."}],
    "things": [{"type": "object", "name": "the brass lamp", "aliases": ["the lamp"],
                "quote": "The brass lamp hung in the mill."}],
    "groups": [],
}


class BarrierModel(FakeModel):
    """Each category call waits until all four are in flight: they must overlap."""

    def __init__(self, categories):
        super().__init__(categories=categories)
        self.barrier = threading.Barrier(len(b.DEFAULT), timeout=10)
        self.windows: list[tuple[float, float]] = []
        self.labels: list[Any] = []

    def __call__(self, prompt, schema):
        start = time.monotonic()
        self.labels.append(b.current_label())
        self.barrier.wait()
        out = super().__call__(prompt, schema)
        self.windows.append((start, time.monotonic()))
        return out


def test_12_category_passes_run_concurrently_and_are_labelled():
    model = BarrierModel(CAT_OUT)
    b.category_passes(CAT_TEXT, model)
    assert len(model.windows) == 4
    latest_start = max(s for s, _ in model.windows)
    assert all(end >= latest_start for _, end in model.windows)        # all four overlap
    assert sorted(label["unit"] for label in model.labels) == sorted(
        f"pass:{c}" for c in b.DEFAULT)
    assert {label["stage"] for label in model.labels} == {"registry"}


def test_12_the_merge_never_joins_names_a_pass_listed_separately_and_validates():
    manifest = b.category_passes(CAT_TEXT, FakeModel(categories=CAT_OUT))
    names = [(e.type, list(e.names)) for e in manifest.entries]
    assert ("person", ["Mara Senn", "Mara"]) in names            # the visitor is not her alias
    assert ("person", ["the hooded visitor"]) in names
    assert names.count(("person", ["John"])) == 2
    assert ("animal", ["Rex"]) in names
    assert ("place", ["the mill"]) in names
    assert ("object", ["the brass lamp", "the lamp"]) in names
    baker = next(e for e in manifest.entries if e.names[0] == "the baker")
    assert (baker.type, baker.role) == ("person", "baker")       # k4's rule for a being
    assert baker.anchor_quote == "John the baker sold bread."    # the first sentence naming it
    rex = next(e for e in manifest.entries if e.names[0] == "Rex")
    assert rex.species == "dog"
    manifest.validate(CAT_TEXT)
    reg = b.Registry.from_manifest(manifest, CAT_TEXT)
    johns = [e for e in reg.entries() if e["names"] == ["John"]]
    assert [e["id"] for e in johns] == ["person:john", "person:john_2"]
    assert [e["anchor"] for e in johns] == [(2, 1), (2, 2)]


def test_12_an_unknown_category_or_a_malformed_pass_is_an_error():
    with pytest.raises(ValueError, match="categories"):
        b.category_passes(CAT_TEXT, FakeModel(), categories=("beings", "weather"))
    with pytest.raises(ValueError, match="entries"):
        b.category_passes(CAT_TEXT, lambda p, s: {"lines": []}, categories=("beings",))


# ------------------------------------------------------------ 13. determinism


def test_13_plan_and_minted_ids_are_byte_identical_across_runs(worlds):
    first = built(worlds, KS_TEXT, KS, KS_OUT, name="one")
    second = built(worlds, KS_TEXT, KS, KS_OUT, name="two")
    as_json = lambda chunks: json.dumps([c.to_dict() for c in chunks], sort_keys=True)
    assert as_json(first.chunks) == as_json(second.chunks)
    assert first.receipt.minted == second.receipt.minted
    assert json.dumps(first.receipt.to_dict(), sort_keys=True) == json.dumps(
        second.receipt.to_dict(), sort_keys=True)
    from patternbuffer.dump import dump
    assert dump(first.world.buffer) == dump(second.world.buffer)
    # the registry is not advanced by a commit
    assert first.registry.allocator().order == [i.id for i in first.registry.identities]


def test_13_plan_and_minted_ids_are_byte_identical_across_processes():
    script = (
        "import json, sys, tempfile\n"
        f"sys.path[:0] = [{str(Path(__file__).parent)!r}, {str(HARNESS)!r}]\n"
        "import test_build_library as t\n"
        "from patternbuffer import World\n"
        "reg = t.b.Registry.from_manifest(t.KS, t.KS_TEXT)\n"
        "chunks = t.b.plan(t.KS_TEXT, reg)\n"
        "results = t.b.extract(chunks, reg, t.FakeModel(t.KS_OUT))\n"
        "w = World(tempfile.mkdtemp() + '/x.world', world_id=t.WID, model=t.CLASSIFY)\n"
        "receipt = t.b.commit(w, reg, results, ingest_kwargs={'classify': 'rules'})\n"
        "print(json.dumps({'plan': [c.to_dict() for c in chunks],\n"
        "                  'minted': list(receipt.minted)}, sort_keys=True))\n"
        "w.close()\n")
    outputs = []
    for seed in ("1", "2"):
        done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                              cwd=ROOT, timeout=120,
                              env={"PYTHONPATH": str(ROOT / "src"), "PYTHONHASHSEED": seed,
                                   "PATH": ""})
        assert done.returncode == 0, done.stderr
        outputs.append(done.stdout)
    assert outputs[0] == outputs[1] and json.loads(outputs[0])["minted"]


# ------------------------------------------------------------ 14. the book runner

TOY_CATEGORIES = {
    "beings": [
        {"type": "person", "name": "Mara", "aliases": [],
         "quote": "Mara kept the brass lamp in the cellar of the old mill."},
        {"type": "person", "name": "Orin", "aliases": ["the ferryman"],
         "quote": "Orin the ferryman watched the mill from the dock."}],
    "places": [
        {"type": "place", "name": "the cellar", "aliases": [],
         "quote": "Mara kept the brass lamp in the cellar of the old mill."},
        {"type": "place", "name": "the old mill", "aliases": ["the mill"],
         "quote": "Mara kept the brass lamp in the cellar of the old mill."},
        {"type": "place", "name": "the dock", "aliases": [],
         "quote": "Orin the ferryman watched the mill from the dock."}],
    "things": [{"type": "object", "name": "the brass lamp", "aliases": ["the lamp"],
                "quote": "Mara kept the brass lamp in the cellar of the old mill."}],
    "groups": [],
}
TOY_EXTRACT = {
    0: {"lines": ["s2|obj:the_brass_lamp|in|@place:the_cellar",
                  "s4|person:orin|in|@place:the_dock"]},
    1: {"lines": ["s2|obj:the_brass_lamp|held_by|@person:orin"]},
    2: {"lines": ["s2|obj:the_brass_lamp|in|@place:the_cellar"]},
}
TOY_GRADED = {
    "key_sha256": "x", "readers": ["A", "B"],
    "entities": {"mara": {"kind": "person", "aliases": ["Mara"]},
                 "orin": {"kind": "person", "aliases": ["Orin", "the ferryman"]},
                 "lamp": {"kind": "object", "aliases": ["the brass lamp", "the lamp"]},
                 "cellar": {"kind": "place", "aliases": ["the cellar"]},
                 "dock": {"kind": "place", "aliases": ["the dock"]},
                 "mill": {"kind": "place", "aliases": ["the old mill", "the mill"]}},
    "same_as": [], "not_same": [],
    "moves": {"lamp": [
        {"id": "locations[0]", "to": "cellar", "from_chapter": 1, "to_chapter": 1},
        {"id": "holdings[0]", "to": "orin", "from_chapter": 2, "to_chapter": 2},
        {"id": "locations[1]", "to": "cellar", "from_chapter": 3, "to_chapter": None}]},
    "containers": [], "dropped": [], "ungraded_counts": {},
}


def library_model():
    return FakeModel(chunks=TOY_EXTRACT, categories=TOY_CATEGORIES)


def test_14_pipeline_library_builds_the_toy_book_and_grades_it(tmp_path, monkeypatch):
    book, out = tb.write_book(tmp_path / "toybook"), tmp_path / "out"
    code = rb.main(["--book", str(book), "--out", str(out), "--pipeline", "library"],
                   model=library_model())
    assert code == 0
    meta = json.loads((out / "meta.json").read_text())
    assert meta["pipeline"] == "BUILD-LIBRARY-V1 (patternbuffer.build)"
    assert (meta["chapters"], meta["chunks"], meta["manifest_entries"]) == (3, 3, 6)
    receipt = json.loads((out / "receipt.json").read_text())
    assert set(receipt["stages"]) == set(rb.LIBRARY_STAGES)
    assert receipt["stages"]["registry"]["calls"] == 4
    assert receipt["stages"]["extract"]["calls"] == 3
    for name in ("manifest.json", "plan.json", "build_receipt.json", "registry_pass0.json",
                 "chunk_spans.json", "fresh_ingest.world", "ingest_dump.jsonl"):
        assert (out / name).exists(), name
    usage = [json.loads(line) for line in (out / "usage.jsonl").read_text().splitlines()]
    assert {(u["stage"], u["unit"]) for u in usage if u["stage"] == "extract"} == {
        ("extract", f"chunk:{i:02d}") for i in range(3)}
    assert {u["unit"] for u in usage if u["stage"] == "registry"} == {
        f"pass:{c}" for c in b.DEFAULT}
    spans = json.loads((out / "chunk_spans.json").read_text())["chunks"]
    assert [(c["chunk"], c["chapter"], c["cursor"]) for c in spans] == [
        (0, 1, 1.0), (1, 2, 2.0), (2, 3, 3.0)]

    graded = tmp_path / "graded.json"
    graded.write_text(json.dumps(TOY_GRADED))
    assert gb.main(["--run", str(out), "--graded", str(graded), "--book", str(book)]) == 0
    card = json.loads((out / "book_scorecard.json").read_text())
    assert card["summary"]["order"] == 1.0 and card["summary"]["final"] == 1.0
    assert card["identity"]["split"] == {} and card["identity"]["fused"] == {}
    assert isinstance(card["leaks"], dict) and card["leaks"]["total"] == 0
    assert card["leaks"]["identity_leaks"]["unclassified_chunks"] == []


def test_14_the_library_pipeline_refuses_ingest_v2_options(tmp_path):
    book = tb.write_book(tmp_path / "toybook")
    for kwargs in ({"merge_gate": True}, {"glean": True}, {"pass0": "parallel"}):
        with pytest.raises(rb.BookRefused, match="INGEST-V2 options"):
            rb.run_book(book, tmp_path / "out", library_model(), pipeline="library", **kwargs)
    with pytest.raises(rb.BookRefused, match="unknown pipeline"):
        rb.run_book(book, tmp_path / "out", library_model(), pipeline="ingest-v3")


def test_14_ingest_v2_stays_the_default_and_never_touches_the_library(tmp_path, monkeypatch):
    book = tb.write_book(tmp_path / "toybook")
    monkeypatch.setitem(sys.modules, "patternbuffer.build", None)    # importing it would fail
    implicit = rb.run_book(book, tmp_path / "implicit", tb.scripted_model())
    explicit = rb.run_book(book, tmp_path / "explicit", tb.scripted_model(), pipeline="ingest-v2")
    assert implicit["pipeline"] == explicit["pipeline"] == "INGEST-V2 (registry-first)"
    for name in ("ingest_dump.jsonl", "chunk_spans.json", "registry.json"):
        assert (tmp_path / "implicit" / name).read_bytes() == (
            tmp_path / "explicit" / name).read_bytes()
    assert not (tmp_path / "implicit" / rb.LIBRARY_MANIFEST_FILE).exists()
    assert rb.parse_args(["--book", "x", "--out", "y"]).pipeline == "ingest-v2"


def test_14_the_stage_map_routes_library_calls_by_their_labels(tmp_path, monkeypatch):
    """STAGE-MODELS-V1 routing reaches the library: the harness copies the
    build label into the usage ledger, whose stage the shim routes by."""
    import model_shim

    stage_map = tmp_path / "stages.json"
    stage_map.write_text(json.dumps({"extract": {"model": "m-extract", "effort": "low"},
                                     "registry": {"model": "m-registry", "effort": None}}))
    monkeypatch.setenv(model_shim.STAGE_MODELS_ENV, str(stage_map))
    monkeypatch.delenv("PB_SHIM_LEGACY", raising=False)
    routed: list[tuple[str, Any]] = []
    lock = threading.Lock()

    def router(prompt, schema):
        with lock:
            routed.append((prompt.splitlines()[0], model_shim.route()))
        return {"lines": []} if prompt.startswith(b.EXTRACT_HEAD) else {"entries": []}

    model = rb.ledger_labelled(router)
    reg = b.Registry.from_manifest(P, P_TEXT)
    b.extract(b.plan(P_TEXT, reg), reg, model)
    b.category_passes(P_TEXT, model)
    assert {r for head, r in routed if head == b.EXTRACT_HEAD} == {("m-extract", "low")}
    assert {r for head, r in routed if head != b.EXTRACT_HEAD} == {("m-registry", None)}
    assert model_shim.parse_stage_map(stage_map.read_bytes()).route("extract") == (
        "m-extract", "low")


# ------------------------------------------------------- the module boundary


def test_the_core_never_imports_the_library_and_the_library_never_the_harness():
    code = ("import sys, patternbuffer, patternbuffer.porcelain, patternbuffer.service, "
            "patternbuffer.mirror, patternbuffer.merge_gate; "
            "from patternbuffer import World; "
            "assert 'patternbuffer.build' not in sys.modules, 'core imported the library'; "
            "import patternbuffer.build; "
            "assert not any(m.split('.')[0] in ('evals', 'grammar', 'registry', 'pipeline', "
            "'usage_ledger', 'grade_leaks', 'book_gold') for m in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=ROOT, env={"PYTHONPATH": str(ROOT / "src"), "PATH": ""})
    assert out.returncode == 0, out.stderr


def test_nothing_in_the_engine_outside_build_mentions_the_library():
    src = ROOT / "src" / "patternbuffer"
    hits = [p for p in src.rglob("*.py") if "build" not in p.relative_to(src).parts
            and re.search(r"patternbuffer\.build|from \. import build|from \.build", p.read_text())]
    assert hits == []


def test_the_library_writes_only_through_the_porcelain():
    """Every attribute the library reads off a world is ``porcelain``, and it
    imports no engine writer (buffer, ingestor, identity, classifier, truth)."""
    used: set[str] = set()
    for path in (ROOT / "src" / "patternbuffer" / "build").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id == "world"):
                used.add(node.attr)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", None) or ""
                names = [a.name for a in node.names]
                for name in [module, *names]:
                    assert not re.match(r"patternbuffer\.(buffer|ingest|identity|classify|tmaint"
                                        r"|indexes)", name), (path.name, name)
    assert used == {"porcelain"}


# ------------------------------------------------------- copies kept in step


def test_the_tokenizer_is_grade_leaks_tokenizer():
    samples = ["The One", "O'Brien’s copper-hand", "“Mara,” said Orin.", "Ångström 42x",
               "the hooded  visitor", ""]
    for s in samples:
        assert btext.tokens(s) == gl.tokens(s)
    assert btext.fold_quotes("‘a’ “b”") == book_gold.fold_quotes("‘a’ “b”")
    for s in ["The Barmaid", "a  ferryman", "Mr. Vell", "an Owl"]:
        assert btext.join_key(s) == book_gold.book_normalize(s)


class _Known:
    entities = {i: None for i in ("obj:core", "person:ada", "event:start", "place:lab")}


@pytest.mark.parametrize("line", [
    "obj:core|charge|5|vf=4.5,vt=9",
    'obj:core|label|"a|b"|t',
    "obj:core|visible|true|f=knows:person:ada,s=observed,doc=doc:alpha,cb=event:start",
    "person:ada|in|@place:lab",
    'obj:core|spec|{"gte": 40000}',
    'obj:core|contents|?{"policy": "invent_under_canon"}',
    "obj:core|fixed|true|corr,src=person:ada",
])
def test_the_library_grammar_is_ingest_v2s_with_a_citation(line):
    items, orphans, rejects = harness_grammar.parse([line], _Known(), cursor=7.0)
    assert orphans == rejects == []
    expected = dict(items[0])
    if expected.get("valid_from") == 7.0 and "vf=" not in line:
        del expected["valid_from"]                   # the harness stamps its cursor; commit poses
    assert parse_line("s3|" + line) == (3, expected)
    assert grammar_problem(expected) is None        # commit accepts what the grammar writes
    with pytest.raises(ValueError, match="missing sentence citation"):
        parse_line(line)


# ------------------------------------------------------- entries() and plan()


def test_entries_report_ids_types_anchors_gates_and_personas():
    reg = b.Registry.from_manifest(P, P_TEXT)
    assert reg.entries() == [
        {"id": DUKE, "key": "duke", "type": "person", "species": None,
         "names": ["Duke Orsino", "Orsino"], "role": None, "fixture": False, "anchor": (3, 3), "gate": (3, 1),
         "personas": [{"name": "the hooded stranger", "id": STRANGER_ID, "reveal": (3, 2),
                       "gate": (2, 1)}]},
        {"id": "person:orin", "key": "orin", "type": "person", "species": None,
         "names": ["Orin"], "role": None, "fixture": False, "anchor": (1, 2), "gate": (1, 2), "personas": []},
        {"id": "place:the_mill", "key": "mill", "type": "place", "species": None,
         "names": ["the mill"], "role": None, "fixture": False, "anchor": (1, 1), "gate": (1, 1), "personas": []},
    ]


def test_a_manifest_round_trips_through_plain_json():
    for manifest in (P, KS, REX):
        assert b.Manifest.from_dict(json.loads(json.dumps(manifest.to_dict()))) == manifest
    broken = b.Manifest.from_dict({"entries": [{"key": "x", "names": "Mara"}]})
    codes = [p["code"] for p in broken.problems({1: "Mara rowed."})]
    assert codes == ["unknown_type", "missing_field", "quote_not_found"]


def test_plan_refuses_other_text_and_extract_numbers_the_passage():
    reg = b.Registry.from_manifest(P, P_TEXT)
    with pytest.raises(ValueError, match="not the text the registry"):
        b.plan({**P_TEXT, 1: "Changed."}, reg)
    chunk = b.plan(P_TEXT, reg)[3]
    prompt = build_prompt(chunk, reg.book)
    assert "[s1] The hooded stranger pulled back the hood: it was Duke Orsino." in prompt
    assert "[s2] Orsino laughed." in prompt
    assert f"{DUKE} | person | Duke Orsino; Orsino | from s1" in prompt


def test_a_model_error_refuses_its_chunk_and_commit_refuses_the_build(worlds):
    reg = b.Registry.from_manifest(REX, REX_TEXT)

    def broken(prompt, schema):
        raise RuntimeError("boom")

    results = b.extract(b.plan(REX_TEXT, reg), reg, broken)
    assert results[0].error == "model call failed: RuntimeError: boom"
    w = worlds()
    with pytest.raises(b.CommitRefused):
        b.commit(w, reg, results)
    assert w.buffer.head() == 3
