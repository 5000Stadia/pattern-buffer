"""MERGE-GATE-VERB-V1 (R48): the measured merge gate as a report-only engine verb.

Each numbered test of the spec's Tests section is here (1 is ``test_merge_gate.py``
passing unchanged; 12 is construct's). Real worlds, scripted model doubles; no
real model is ever called."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "evals" / "harness"))

from patternbuffer import World
from patternbuffer import merge_gate as eg
from patternbuffer.dump import dump
from patternbuffer.model import TaskSchema
from patternbuffer.service import VIEWER_EXCLUDED
from patternbuffer.testing import rule_classifier_fallback

import merge_gate as harness
from pipeline import seed_world
from registry import EntityCard, TimelineSpec, WorldRegistry

WID = "w:verb"

LA, LB, LC = "obj:ledger_a", "obj:ledger_b", "obj:ledger_c"


def card(kind, names, aliases=()):
    return EntityCard(kind=kind, names=list(names), aliases=list(aliases))


FIXTURE = {
    LA: card("object", ["The Brass Ledger"]),
    LB: card("object", ["Brass Ledger of the Vault"]),
    LC: card("object", ["Ledger"]),
    "obj:ledger_d": card("object", ["Ledger Prime"]),
    "person:ilsa": card("person", ["Ilsa Renn"], ["renn"]),
    "obj:desk": card("object", ["Ilsa Renn's desk"]),
    "place:vault_a": card("room", ["Records Vault"]),
    "place:vault_b": card("room", ["the vault"]),
    "event:theft": card("event", ["the memory core theft"]),
    "obj:core": card("object", ["the memory core"]),
    "obj:nameless": card("object", []),
    "person:nameless": card("person", []),
}


def make_world(tmp_path, model, entities=None, name="w") -> World:
    reg = WorldRegistry(world_id=WID, entities=dict(FIXTURE if entities is None else entities),
                        attributes={"in": "in"}, timeline=TimelineSpec(origin="Day 0"))
    w = World(tmp_path / f"{name}.world", world_id=WID, model=model)
    w.ingestor.classify_inline = False
    seed_world(w, reg)
    return w


def scripted(answers=None, *, calls=None, raise_on=(), identity=None):
    """A model double: ``(a, b) -> (verdict, keep?, reason?)``, else ``unsure``;
    ``raise_on`` lists the batch numbers whose call raises."""
    answers = answers or {}

    def model(prompt, schema):
        assert isinstance(schema, TaskSchema) and schema["title"] == "merge_gate"
        req = eg.batch_request(schema)
        if calls is not None:
            calls.append((prompt, schema, req))
        if req["batch"] in raise_on:
            raise RuntimeError("model down")
        out = []
        for p in req["pairs"]:
            ans = answers.get((p["a"]["id"], p["b"]["id"]), ("unsure",))
            e = {"pair_id": p["pair_id"], "verdict": ans[0], "reason": ans[2] if len(ans) > 2 else "r"}
            if len(ans) > 1 and ans[1]:
                e["keep"] = ans[1]
            out.append(e)
        return {"verdicts": out}
    if identity:
        model.identity = identity
    return model


def never(prompt, schema):  # pragma: no cover - reaching it fails the test
    raise AssertionError("the model must not be called")


def covers(report) -> bool:
    got = sorted(i for e in [*report["pairs"], *report["not_asked"]] for i in e["requested_as"])
    return got == list(range(len(report["requested"])))


@pytest.fixture
def world(tmp_path):
    w = make_world(tmp_path, scripted())
    yield w
    w.close()


def ask(w, model, pairs, **kw):
    w.ingestor._model = model
    return w.porcelain.merge_gate(pairs, **kw)


# ------------------------------------------------------------ 2. report-only


def test_2_report_only_writes_nothing(world):
    before = (dump(world.buffer), len(list(world.buffer.all_rows())))
    pairs = [[LA, LB], [LA, LC], ["place:vault_a", "place:vault_b"]]
    every_same = {(a, b): ("same", "a") for a, b in
                  [(LA, LB), (LA, LC), ("place:vault_a", "place:vault_b")]}
    r = ask(world, scripted(every_same), pairs)
    assert r["status"] == "asked" and r["counts"]["verdicts"] == {"same": 3}
    assert r["components"] and r["components"][0]["status"] == "would_merge"
    assert (dump(world.buffer), len(list(world.buffer.all_rows()))) == before
    assert world.registry.resolve(LB) == LB                        # nothing merged


# --------------------------------------------------------------- 3. not asked


def test_3_each_status_is_reported_and_never_reaches_the_model(tmp_path):
    w = make_world(tmp_path, never)
    w.porcelain.merge(LA, LB, "same ledger")                       # already_one
    w.porcelain.reject("place:vault_a", "place:vault_b")           # held_apart
    pairs = [
        [LA, LB],                                                  # already_one
        ["place:vault_a", "place:vault_b"],                        # held_apart
        ["person:ilsa", "obj:desk"],                               # class_mismatch (person)
        ["event:theft", "obj:core"],                               # class_mismatch (event)
        ["obj:core", "event:theft"],                               # ... the other way round
        [LC, "obj:nameless"],                                      # no_names
    ]
    r = ask(w, never, pairs)
    assert r["status"] == "nothing_to_ask" and r["pairs"] == [] and r["components"] == []
    by = {(e["a"], e["b"]): e["status"] for e in r["not_asked"]}
    assert by[(LA, LA)] == "already_one"
    assert by[("place:vault_a", "place:vault_b")] == "held_apart"
    assert by[("obj:desk", "person:ilsa")] == "class_mismatch"
    assert by[("event:theft", "obj:core")] == "class_mismatch"
    assert by[(LC, "obj:nameless")] == "no_names"
    assert r["counts"]["not_asked"] == {"already_one": 1, "class_mismatch": 2,
                                        "held_apart": 1, "no_names": 1}
    assert r["counts"]["asked"] == 0 and r["counts"]["batches"] == 0 and covers(r)
    w.close()


def test_3_overlaps_take_the_first_status_in_order(tmp_path):
    w = make_world(tmp_path, never)
    w.porcelain.reject("person:ilsa", "obj:desk")                  # held apart AND person v object
    r = ask(w, never, [["person:ilsa", "obj:desk"], ["person:nameless", "obj:nameless"]])
    by = {(e["a"], e["b"]): e["status"] for e in r["not_asked"]}
    assert by[("obj:desk", "person:ilsa")] == "held_apart"
    assert by[("obj:nameless", "person:nameless")] == "class_mismatch"   # not no_names
    w.close()


@pytest.mark.parametrize("with_model", [True, False])
def test_3_all_filtered_is_nothing_to_ask_with_or_without_a_model(world, with_model):
    r = ask(world, never if with_model else None, [["obj:desk", "obj:desk"]])
    assert r["status"] == "nothing_to_ask" and r["counts"]["batches"] == 0
    assert r["counts"]["asked"] == 0 and r["pairs"] == [] and r["components"] == []
    assert len(r["call_id"]) == 32 and r["cached"] is False
    assert r["requested"] == [["obj:desk", "obj:desk"]] and covers(r)
    assert r["not_asked"] == [{"a": "obj:desk", "b": "obj:desk", "status": "already_one",
                               "requested_as": [0]}]


# ----------------------------------------------------------- 4. canonicalization


def test_4_spellings_of_one_pair_are_asked_once(tmp_path):
    w = make_world(tmp_path, scripted())
    w.porcelain.merge(LA, LB, "same ledger", representative=LA)    # LB is a member of LA's closure
    calls = []
    r = ask(w, scripted(calls=calls), [[LC, LA], [LA, LC], [LC, LB]])
    assert [p["pair_id"] for p in r["pairs"]] == ["p0001"] and len(r["pairs"]) == 1
    p = r["pairs"][0]
    assert (p["a"], p["b"]) == (LA, LC) and p["a"] < p["b"]
    assert p["requested_as"] == [0, 1, 2] and covers(r)
    assert len(calls) == 1 and len(calls[0][2]["pairs"]) == 1
    w.close()


def test_4_asked_pairs_are_sorted_and_numbered(world):
    r = ask(world, scripted(), [[LC, "obj:ledger_d"], [LB, LA], [LC, LA]])
    assert [(p["pair_id"], p["a"], p["b"]) for p in r["pairs"]] == [
        ("p0001", LA, LB), ("p0002", LA, LC), ("p0003", LC, "obj:ledger_d")]


# ------------------------------------------------------------------ 5. context


def test_5_context_lands_on_the_representative_capped_and_trimmed(tmp_path):
    w = make_world(tmp_path, scripted())
    w.porcelain.merge(LA, LB, "same ledger", representative=LA)
    calls = []
    long = "x" * 450
    context = {LB: ["  b says this  ", "dup", "", "   "],       # a member key
               LA: ["dup", "a says " + long, "third is dropped"],
               LC: ["c one"]}
    r = ask(w, scripted(calls=calls), [[LA, LC]], context=context)
    req = calls[0][2]
    a_side, c_side = req["pairs"][0]["a"], req["pairs"][0]["b"]
    # key order is sorted id: LA's sentences first, then LB's; de-duplicated; capped at 2
    assert a_side["context"] == ["dup", "a says " + "x" * (400 - len("a says "))]
    assert len(a_side["context"][1]) == 400 and c_side["context"] == ["c one"]
    assert r["status"] == "asked"
    # a member key alone reaches its representative, trimmed
    calls.clear()
    ask(w, scripted(calls=calls), [[LA, LC]], context={LB: ["  b says this  "]})
    assert calls[0][2]["pairs"][0]["a"]["context"] == ["b says this"]
    assert calls[0][2]["pairs"][0]["b"]["context"] == []
    # no context: every side is []
    calls.clear()
    ask(w, scripted(calls=calls), [[LA, LC]])
    side_ctx = [s["context"] for s in (calls[0][2]["pairs"][0]["a"], calls[0][2]["pairs"][0]["b"])]
    assert side_ctx == [[], []]
    w.close()


# -------------------------------------------------------- 6. same envelope


def test_6_the_request_equals_the_harness_envelope(world):
    calls = []
    context = {LA: ["a sentence"], LC: ["c sentence", "another"]}
    ask(world, scripted(calls=calls), [[LC, LA], [LA, LB]], context=context)
    sides = eg.read_sides(world)
    pairs = [(LA, LB), (LA, LC)]
    expected = harness.make_batches(pairs, sides, {**{i: [] for i in (LA, LB, LC)},
                                                   LA: ["a sentence"],
                                                   LC: ["c sentence", "another"]})
    assert calls[0][2] == expected[0]
    # and the harness's own builder, over its own context input, gives the same shape
    built = harness.build_batches(world, pairs, sides, None)
    assert [p["pair_id"] for p in built[0]["pairs"]] == [p["pair_id"] for p in calls[0][2]["pairs"]]
    assert calls[0][1]["title"] == "merge_gate"
    assert calls[0][0] == eg.gate_prompt(calls[0][2])


def test_6_the_harness_re_exports_the_engine_pieces():
    for name in ("validate_batch", "read_sides", "elect_representative", "batch_request",
                 "gate_prompt", "gate_schema", "pair_id", "VERDICTS", "CONTEXT_SENTENCES"):
        assert getattr(harness, name) is getattr(eg, name)


def test_read_sides_with_ids_reads_only_those_closures(world):
    world.porcelain.merge(LA, LB, "same ledger", representative=LA)
    only = eg.read_sides(world, [LB])
    assert set(only) == {LA}
    everything = eg.read_sides(world)
    assert only[LA] == everything[LA] and len(everything) > 1


# --------------------------------------------------------------- 7. components


def test_7_two_same_pairs_make_one_would_merge_component(tmp_path):
    entities = {"obj:t_a": card("object", ["Ledger"]),
                "obj:t_b": card("object", ["Brass Ledger"]),
                "obj:t_c": card("object", ["The Old Brass Ledger of the Vault"])}
    w = make_world(tmp_path, scripted(), entities)
    answers = {("obj:t_a", "obj:t_b"): ("same", "a"), ("obj:t_b", "obj:t_c"): ("same", "a")}
    r = ask(w, scripted(answers), [["obj:t_a", "obj:t_b"], ["obj:t_b", "obj:t_c"]])
    (comp,) = r["components"]
    assert comp["status"] == "would_merge" and comp["votes"] == {"obj:t_a": 1, "obj:t_b": 1}
    assert comp["representative"] == "obj:t_c"       # the longest name, a third member
    assert comp["members"] == ["obj:t_a", "obj:t_b", "obj:t_c"]
    assert comp["same_pairs"] == ["p0001", "p0002"] and comp["different_pairs"] == []
    assert r["counts"]["components"] == 1 and r["counts"]["conflicting_components"] == 0
    assert r["pairs"][0]["keep_id"] == "obj:t_a" and r["pairs"][1]["keep_id"] == "obj:t_b"
    w.close()


def test_7_one_different_inside_makes_a_conflicting_component(world):
    answers = {(LA, LB): ("different",), (LA, LC): ("same", "a"), (LB, LC): ("same", "a")}
    r = ask(world, scripted(answers), [[LA, LB], [LA, LC], [LB, LC]])
    (comp,) = r["components"]
    assert comp["status"] == "conflicting_component" and comp["representative"] is None
    assert comp["different_pairs"] == ["p0001"] and comp["same_pairs"] == ["p0002", "p0003"]
    assert r["counts"]["conflicting_components"] == 1


# ----------------------------------------------------------------- 8. failures


def test_8_a_model_that_raises_leaves_its_batch_unparseable(world):
    answers = {(LA, LB): ("same", "a")}
    pairs = [[LA, LB], [LA, LC], [LB, LC]]
    r = ask(world, scripted(answers, raise_on=(1,)), pairs, batch_size=2)
    assert r["counts"]["batches"] == 2 and r["status"] == "asked"
    by = {p["pair_id"]: p for p in r["pairs"]}
    assert by["p0001"]["status"] == by["p0002"]["status"] == "batch_unparseable"
    assert by["p0001"]["verdict"] == "unsure" and by["p0003"]["status"] == "answered"
    assert [e["batch"] for e in r["batch_errors"]] == [1]
    assert "RuntimeError" in r["batch_errors"][0]["error"]
    assert r["counts"]["statuses"] == {"answered": 1, "batch_unparseable": 2}


def test_8_no_model_gives_a_full_report(world):
    world.porcelain.merge(LA, LB, "same ledger")
    r = ask(world, None, [[LA, LC], [LA, LB]])
    assert r["status"] == "no_model" and r["pairs"] == [] and r["components"] == []
    assert r["model"] is None and r["cached"] is False and len(r["call_id"]) == 32
    by = {(e["a"], e["b"]): e["status"] for e in r["not_asked"]}
    assert by == {(LA, LC): "no_model", (LA, LA): "already_one"}
    assert r["counts"]["asked"] == 0 and r["counts"]["batches"] == 0
    assert r["counts"]["not_asked"] == {"already_one": 1, "no_model": 1}
    assert covers(r)


# ---------------------------------------------------- 9. call identity, coverage


def test_9_two_calls_are_two_askings_and_requested_as_covers(world):
    calls = []
    model = scripted(calls=calls, identity="double-1")
    world.porcelain.merge(LA, LB, "same ledger")
    pairs = [[LA, LC], [LC, LA], [LA, LB], ["obj:desk", "person:ilsa"], [LA, "obj:ledger_d"]]
    r1 = ask(world, model, pairs)
    n = len(calls)
    r2 = ask(world, model, pairs)
    assert r1["call_id"] != r2["call_id"] and len(r1["call_id"]) == len(r2["call_id"]) == 32
    assert r1["cached"] is r2["cached"] is False
    assert len(calls) == 2 * n and n >= 1                      # asked anew
    assert r1["model"] == "double-1" and r1["requested"] == pairs
    assert covers(r1) and covers(r2)
    assert next(p for p in r1["pairs"] if (p["a"], p["b"]) == (LA, LC))["requested_as"] == [0, 1]


# ------------------------------------------------------------------ 10. bad input


@pytest.mark.parametrize("pairs,kw", [
    ([], {}),
    ([[LA, LB]] * 501, {}),
    ([[LA, 5]], {}),
    ([[LA, ""]], {}),
    ([[LA]], {}),
    ([[LA, LB, LC]], {}),
    ("ab", {}),
    ([[LA, LB]], {"batch_size": 0}),
    ([[LA, LB]], {"batch_size": True}),
    ([[LA, LB]], {"batch_size": 2.5}),
    ([[LA, LB]], {"context": ["not a mapping"]}),
    ([[LA, LB]], {"context": {LA: "a bare string"}}),
    ([[LA, LB]], {"context": {LA: [3]}}),
    (([LA, LB],), {}),                                    # the outer container is a list
    ([[LA, LB]], {"context": {LA: ("a tuple of sentences",)}}),
])
def test_10_bad_input_raises_before_any_model_call(world, pairs, kw):
    with pytest.raises(ValueError):
        ask(world, never, pairs, **kw)


def test_10_exactly_500_pairs_is_accepted(world):
    r = ask(world, scripted(), [[LA, LB]] * 500)
    assert r["status"] == "asked" and len(r["requested"]) == 500 and covers(r)


# --------------------------------------------------------------- 11. viewer walk


def test_11_the_verb_is_viewer_excluded():
    assert VIEWER_EXCLUDED["merge_gate"] == "reaches the model"


# --------------------------------------------------------- the module boundary


def test_the_core_does_not_import_the_module_and_the_engine_module_not_the_harness():
    code = ("import sys, patternbuffer.porcelain, patternbuffer.service; "
            "from patternbuffer import World; "
            "assert 'patternbuffer.merge_gate' not in sys.modules; "
            "import patternbuffer.merge_gate; "
            "assert not any(m.split('.')[0] in ('evals', 'merge_gate', 'pipeline') "
            "for m in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=ROOT, env={"PYTHONPATH": str(ROOT / "src"), "PATH": ""})
    assert out.returncode == 0, out.stderr
