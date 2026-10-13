"""MERGE-GATE-V1 (R25 part A): lexical candidates, a batched yes/no gate, host
merges by component. The free pass mark (spec items 1-7) is each a test here: hand
fixtures with scripted gates, and the five stored registries with a gold-oracle
gate. No model is called anywhere."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "evals" / "harness"))

from patternbuffer import World
from patternbuffer.dump import dump
from patternbuffer.model import TaskSchema, task_request
from patternbuffer.testing import rule_classifier_fallback

import grade_registry as gr
import merge_gate as mg
import pipeline as pl
from grade_registry import grade, merge_gate_effect, gold_oracle_gate, seeded_registry
from pipeline import MERGE_GATE_FILE, Pipeline, finalize_identity, seed_world, write_source_segments
from registry import EntityCard, TimelineSpec, WorldRegistry

WID = "w:gate"
RESULTS = ROOT / "evals" / "results"


def stub(prompt, schema):
    return rule_classifier_fallback()(prompt, schema)


def card(kind, names, aliases=()):
    return EntityCard(kind=kind, names=list(names), aliases=list(aliases))


def registry(entities: dict[str, EntityCard]) -> WorldRegistry:
    return WorldRegistry(world_id=WID, entities=entities, attributes={"in": "in"},
                         timeline=TimelineSpec(origin="Day 0"))


def make_world(tmp_path, reg: WorldRegistry, name: str = "w") -> World:
    w = World(tmp_path / f"{name}.world", world_id=WID, model=stub)
    w.ingestor.classify_inline = False
    seed_world(w, reg)
    return w


def scripted(answers: dict[tuple[str, str], tuple], *, reverse: bool = False, calls: list | None = None):
    """A gate that answers by id pair: ``(a, b) -> (verdict, keep?, reason?)``; any
    pair not listed is ``unsure``. ``reverse`` presents the entries in reverse order."""
    def gate(prompt, schema):
        req = mg.batch_request(schema)
        assert schema["title"] == "merge_gate" and isinstance(schema, TaskSchema)
        if calls is not None:
            calls.append((prompt, schema, req))
        out = []
        for p in req["pairs"]:
            ans = answers.get((p["a"]["id"], p["b"]["id"]), ("unsure",))
            e = {"pair_id": p["pair_id"], "verdict": ans[0]}
            if len(ans) > 1 and ans[1]:
                e["keep"] = ans[1]
            e["reason"] = ans[2] if len(ans) > 2 else f"r:{p['a']['id']}:{p['b']['id']}"
            out.append(e)
        return {"verdicts": out[::-1] if reverse else out}
    return gate


def all_unsure(prompt, schema):
    return {"verdicts": [{"pair_id": p["pair_id"], "verdict": "unsure"}
                         for p in mg.batch_request(schema)["pairs"]]}


def gate_world(tmp_path, reg, gate, name="w", segments=None, batch_size=25, reconcile=False):
    w = make_world(tmp_path, reg, name)
    report = finalize_identity(w, reconcile=reconcile, gate=gate, segments=segments,
                               gate_batch_size=batch_size)
    return w, report


def pair(report, a, b):
    return next(p for p in report["pairs"] if (p["a"], p["b"]) == (a, b))


def rows(w, attribute):
    return [r for r in w.buffer.all_rows() if r.attribute == attribute]


# ----------------------------------------------------------- the fixtures

LEDGERS = {  # three cards of one ledger; every pair shares "ledger"
    "obj:ledger_a": card("object", ["The Brass Ledger"]),
    "obj:ledger_b": card("object", ["Brass Ledger of the Vault"]),
    "obj:ledger_c": card("object", ["Ledger"]),
}
LA, LB, LC = "obj:ledger_a", "obj:ledger_b", "obj:ledger_c"

TIE = {  # a, b, c; c has the longest name by far
    "obj:t_a": card("object", ["Ledger"]),
    "obj:t_b": card("object", ["Brass Ledger"]),
    "obj:t_c": card("object", ["The Old Brass Ledger of the Vault"]),
}


def desk_registry() -> WorldRegistry:
    return registry({
        "person:ilsa_renn": card("person", ["Ilsa Renn"], ["renn"]),
        "person:tin_ear_clerk": card("person", ["the tin ear"], ["the clerk"]),
        "person:vael_clerk": card("person", ["Vael"], ["the clerk"]),
        "obj:renn_desk": card("object", ["Ilsa Renn's desk"]),
        "obj:ilsa_desk": card("object", ["Ilsa's desk"]),
        "place:records_vault": card("room", ["Records Vault"], ["the vault"]),
    })


# ------------------------------------------------------------ candidates


def test_candidate_rules(tmp_path):
    reg = registry({
        "obj:renn_desk": card("object", ["Ilsa Renn's desk"]),   # possessive 's removed
        "obj:ilsa_desk": card("object", ["Ilsa's desk"]),        # shares ilsa, desk
        "person:ilsa_renn": card("person", ["Ilsa Renn"]),       # person against non-person: never
        "person:tin_ear_clerk": card("person", ["the tin ear"], ["the clerk"]),
        "person:vael_clerk": card("person", ["Vael"], ["the clerk"]),  # only "the clerk" is shared
        "person:old_guard": card("person", ["The Old Guard"]),   # old, the: stop words; guard: stoplist
        "person:new_guard": card("person", ["The New Guard"]),
        "obj:of_it": card("object", ["Box of Ash"]),             # of: a stop word; "box" too short? no, 3
        "obj:ash_box": card("object", ["Ash"]),                  # shares "ash"
        "obj:ab": card("object", ["Ab Cd"]),                     # tokens under 3 characters
        "obj:ab2": card("object", ["Cd Ef"]),
    })
    w = make_world(tmp_path, reg)
    got = mg.candidate_pairs(w)
    assert ("obj:ilsa_desk", "obj:renn_desk") in got
    assert not any("person:ilsa_renn" in p and ("obj:renn_desk" in p or "obj:ilsa_desk" in p)
                   for p in got)                                    # person x non-person
    assert ("person:tin_ear_clerk", "person:vael_clerk") in got      # exact shared "the clerk"
    assert ("person:new_guard", "person:old_guard") not in got       # only stop/stoplist words
    assert ("obj:ash_box", "obj:of_it") in got
    assert ("obj:ab", "obj:ab2") not in got
    assert got == sorted(got) and all(a < b for a, b in got)
    w.close()


def test_stoplisted_token_alone_is_not_a_candidate_but_an_exact_string_is(tmp_path):
    reg = registry({
        "person:a": card("person", ["Orsin"], ["the clerk"]),     # exact "the clerk" shared
        "person:b": card("person", ["Pell"], ["the clerk"]),
        "person:c": card("person", ["Quill"], ["senior clerk"]),  # "clerk" token only, stoplisted
        "person:d": card("person", ["Rask"], ["junior clerk"]),
        "person:e": card("person", ["Sorn"], ["a clerk"]),        # articles drop: one string "clerk"
        "person:f": card("person", ["Tave"], ["clerk"]),
    })
    w = make_world(tmp_path, reg)
    got = mg.candidate_pairs(w)
    assert ("person:a", "person:b") in got
    assert ("person:e", "person:f") in got      # "a clerk" and "clerk" are one normalized string
    assert ("person:c", "person:d") not in got  # a stoplisted token alone is not evidence
    assert ("person:a", "person:c") not in got
    w.close()


def test_pair_already_held_apart_or_already_one_closure_is_not_a_candidate(tmp_path):
    reg = registry({
        "place:records_vault": card("room", ["Records Vault"], ["the vault"]),
        "place:seed_vault": card("room", ["Seed Vault"], ["the vault"]),
        "place:cellar": card("room", ["Deep Cellar"]),
        "place:cellar2": card("room", ["Cellar"]),
    })
    w = make_world(tmp_path, reg)
    assert ("place:records_vault", "place:seed_vault") in mg.candidate_pairs(w)
    w.porcelain.reject("place:records_vault", "place:seed_vault")   # anyone's distinct_from (R42)
    assert w.porcelain.merge("place:cellar", "place:cellar2", "same", representative="place:cellar")[
        "outcome"] == "merged"
    assert mg.candidate_pairs(w) == []        # held apart, and one closure
    w.close()


def test_candidates_work_on_closures_not_ids(tmp_path):
    reg = registry({
        "obj:a": card("object", ["Brass Lamp"]),
        "obj:b": card("object", ["Lantern"], ["storm lamp"]),
        "obj:c": card("object", ["Storm Glass"]),
    })
    w = make_world(tmp_path, reg)
    assert w.porcelain.merge("obj:a", "obj:b", "same", representative="obj:a")["outcome"] == "merged"
    sides = mg.read_sides(w)
    assert set(sides) == {"obj:a", "obj:c"}
    assert sides["obj:a"]["names"] == ["Brass Lamp", "Lantern"]
    assert sides["obj:a"]["aliases"] == ["storm lamp"]
    assert mg.candidate_pairs(w) == [("obj:a", "obj:c")]     # via the merged-in alias "storm"
    w.close()


# -------------------------------------------------- the call (the envelope)


def test_envelope_batches_ids_sides_and_context(tmp_path):
    reg = registry({f"obj:k{i:02d}": card("object", [f"Brass Key {i}"]) for i in range(6)})
    reg.entities["obj:zz"] = card("object", ["Brass Key"], ["key"])
    segs = ["The brass key lay on the table. It was cold.\n\nNobody touched Brass Key 3 again."]
    calls: list = []
    w, report = gate_world(tmp_path, reg, scripted({}, calls=calls), segments=segs, batch_size=10)
    # 7 ids, all sharing "brass"/"key" -> 21 pairs -> 3 batches of 10, 10, 1
    assert report["counts"]["candidates"] == 21 and report["counts"]["batches"] == 3
    assert [len(c[2]["pairs"]) for c in calls] == [10, 10, 1]
    assert [c[2]["batch"] for c in calls] == [1, 2, 3]
    ids = [p["pair_id"] for c in calls for p in c[2]["pairs"]]
    assert ids == [f"p{n:04d}" for n in range(1, 22)]            # one numbering over all batches
    first = calls[0][2]["pairs"][0]
    assert set(first) == {"pair_id", "a", "b"} and set(first["a"]) == {
        "id", "kind", "names", "aliases", "context"}
    assert all(p["a"]["id"] < p["b"]["id"] for c in calls for p in c[2]["pairs"])
    for p in (q for c in calls for q in c[2]["pairs"]):
        for side in (p["a"], p["b"]):
            assert side["names"] == sorted(side["names"]) and side["kind"] == "object"
            assert len(side["context"]) <= 2
    # task_request reads the same request; the prompt carries the batch for reading
    assert task_request(calls[0][1]) is calls[0][2] and calls[0][1]["title"] == "merge_gate"
    assert "p0001" in calls[0][0] and "BATCH 1" in calls[0][0]
    # context: sentences of the source that mention one of the side's names
    zz = next(p["b"] if p["b"]["id"] == "obj:zz" else p["a"]
              for c in calls for p in c[2]["pairs"] if "obj:zz" in (p["a"]["id"], p["b"]["id"]))
    assert zz["context"] == ["The brass key lay on the table."]
    k3 = next(s for c in calls for p in c[2]["pairs"] for s in (p["a"], p["b"])
              if s["id"] == "obj:k03")
    assert k3["context"] == ["Nobody touched Brass Key 3 again."]
    w.close()


def test_context_is_empty_without_a_source(tmp_path):
    calls: list = []
    gate_world(tmp_path, registry(LEDGERS), scripted({}, calls=calls))
    assert all(s["context"] == [] for c in calls for p in c[2]["pairs"] for s in (p["a"], p["b"]))


def test_batch_size_is_validated(tmp_path):
    w = make_world(tmp_path, registry(LEDGERS))
    for bad in (0, -1, 2.5, "25", True):
        with pytest.raises(ValueError, match="batch_size"):
            mg.build_batches(w, [], {}, None, bad)
        with pytest.raises(ValueError, match="merge_gate_batch_size"):
            Pipeline(stub, WID, tmp_path / "v", merge_gate_batch_size=bad)
    w.close()


# ------------------------------------------- 4: malformed answers, per status


def malformed_run(tmp_path, make_answer):
    """Three ledger pairs plus one unrelated pair; ``make_answer(req)`` builds the
    answer. Every status must leave the pair ``unsure`` and merge nothing for it."""
    reg = registry({**LEDGERS, "place:hall_a": card("room", ["Grand Hall"]),
                    "place:hall_b": card("room", ["Hall"])})
    w, report = gate_world(tmp_path, reg, lambda prompt, schema: make_answer(
        mg.batch_request(schema)))
    return w, report


def _same(p, keep="a"):
    return {"pair_id": p["pair_id"], "verdict": "same", "keep": keep, "reason": "ok"}


@pytest.mark.parametrize("answer", [None, "text", [], 3, {}, {"verdicts": "x"}, {"verdicts": None}])
def test_status_batch_unparseable(tmp_path, answer):
    w, report = malformed_run(tmp_path, lambda req: answer)
    assert {p["status"] for p in report["pairs"]} == {"batch_unparseable"}
    assert {p["verdict"] for p in report["pairs"]} == {"unsure"}
    assert report["counts"]["merges"] == {} and rows(w, "same_as") == []
    w.close()


def test_a_model_that_raises_leaves_its_batch_unparseable_and_quota_propagates(tmp_path):
    def boom(prompt, schema):
        raise RuntimeError("cli down")
    w, report = gate_world(tmp_path, registry(LEDGERS), boom)
    assert {p["status"] for p in report["pairs"]} == {"batch_unparseable"}
    assert report["batch_errors"] == [{"batch": 1, "error": "RuntimeError: cli down"}]
    assert rows(w, "same_as") == []
    w.close()

    class QuotaExhausted(Exception):
        pass

    def quota(prompt, schema):
        raise QuotaExhausted("limit")
    with pytest.raises(QuotaExhausted):
        gate_world(tmp_path, registry(LEDGERS), quota, name="q")


def test_status_stray_changes_nothing_and_other_pairs_keep_their_verdicts(tmp_path):
    def answer(req):
        pairs = req["pairs"]
        return {"verdicts": [
            _same(pairs[0]),
            {"pair_id": "p9999", "verdict": "same", "keep": "a"},     # not in this batch
            "not an object", 7, None, {"verdict": "same"},            # no pair_id
            {"pair_id": ["p0002"], "verdict": "same", "keep": "a"},   # unhashable pair_id
        ]}
    w, report = malformed_run(tmp_path, answer)
    by_status = [p["status"] for p in report["pairs"]]
    assert by_status[0] == "answered" and report["pairs"][0]["verdict"] == "same"
    assert set(by_status[1:]) == {"missing"}                  # only unanswered pairs are missing
    assert len(report["stray"]) == 6 and report["counts"]["stray"] == 6
    assert {p["verdict"] for p in report["pairs"][1:]} == {"unsure"}
    assert [m["outcome"] for c in report["components"] for m in c["merges"]] == ["merged"]
    assert len(rows(w, "same_as")) == 1                        # the one answered pair, nothing else
    w.close()


def test_status_duplicate_discards_every_entry_for_it(tmp_path):
    def answer(req):
        p0, p1 = req["pairs"][0], req["pairs"][1]
        return {"verdicts": [_same(p0), _same(p0, "b"), _same(p1)]}
    w, report = malformed_run(tmp_path, answer)
    first, second = report["pairs"][0], report["pairs"][1]
    assert (first["status"], first["verdict"], first["keep"]) == ("duplicate", "unsure", None)
    assert (second["status"], second["verdict"]) == ("answered", "same")
    assert len(rows(w, "same_as")) == 1                         # only the other pair merged
    w.close()


def test_status_missing(tmp_path):
    w, report = malformed_run(tmp_path, lambda req: {"verdicts": []})
    assert {p["status"] for p in report["pairs"]} == {"missing"}
    assert report["counts"]["merges"] == {} and rows(w, "same_as") == []
    w.close()


@pytest.mark.parametrize("bad", ["Same", "yes", "", None, 1, ["same"], {"v": 1}])
def test_status_bad_verdict(tmp_path, bad):
    def answer(req):
        return {"verdicts": [{"pair_id": p["pair_id"], "verdict": bad, "keep": "a"}
                             for p in req["pairs"]]}
    w, report = malformed_run(tmp_path, answer)
    assert {p["status"] for p in report["pairs"]} == {"bad_verdict"}
    assert {p["verdict"] for p in report["pairs"]} == {"unsure"}
    assert rows(w, "same_as") == []
    w.close()


@pytest.mark.parametrize("keep", [None, "c", "A", "", 0, ["a"]])
def test_status_bad_keep(tmp_path, keep):
    def answer(req):
        out = []
        for p in req["pairs"]:
            e = {"pair_id": p["pair_id"], "verdict": "same"}
            if keep is not None:
                e["keep"] = keep
            out.append(e)
        return {"verdicts": out}
    w, report = malformed_run(tmp_path, answer)
    assert {p["status"] for p in report["pairs"]} == {"bad_keep"}
    assert {p["verdict"] for p in report["pairs"]} == {"unsure"}
    assert all(p["keep"] is None for p in report["pairs"])
    assert rows(w, "same_as") == []
    w.close()


def test_keep_with_another_verdict_is_ignored_and_a_bad_reason_is_empty(tmp_path):
    def answer(req):
        p0, p1 = req["pairs"][0], req["pairs"][1]
        return {"verdicts": [
            {"pair_id": p0["pair_id"], "verdict": "different", "keep": "zzz", "reason": 4},
            {"pair_id": p1["pair_id"], "verdict": "unsure", "keep": "a", "reason": "hm"}]}
    w, report = malformed_run(tmp_path, answer)
    first, second = report["pairs"][0], report["pairs"][1]
    assert (first["status"], first["verdict"], first["keep"], first["reason"]) == (
        "answered", "different", None, "")
    assert (second["status"], second["verdict"], second["keep"], second["reason"]) == (
        "answered", "unsure", None, "hm")
    w.close()


def test_validate_batch_unit():
    req = {"batch": 1, "pairs": [{"pair_id": "p0001"}, {"pair_id": "p0002"}]}
    res, stray = mg.validate_batch(req, {"verdicts": [
        {"pair_id": "p0001", "verdict": "same", "keep": "b", "reason": "x"}]})
    assert res["p0001"] == {"verdict": "same", "keep": "b", "reason": "x", "status": "answered"}
    assert res["p0002"]["status"] == "missing" and stray == []


# ------------------------------------------------ 4a: overlap, no repoints


def merge_events(w):
    """(same_as rows, representative rows): each merge writes one of each, and a
    re-point writes a `representative` row with no `same_as`."""
    return rows(w, "same_as"), rows(w, "representative")


def test_three_members_with_different_keeps_merge_under_the_elected_representative(tmp_path):
    answers = {(LA, LB): ("same", "a", "ab"), (LA, LC): ("same", "a", "ac"),
               (LB, LC): ("same", "a", "bc")}   # keep a on (b, c) is side "a" = ledger_b
    w, report = gate_world(tmp_path, registry(LEDGERS), scripted(answers))
    # votes: ledger_a 2 (ab, ac), ledger_b 1 (bc keeps side a = ledger_b): ledger_a wins the vote
    (comp,) = report["components"]
    assert comp["votes"] == {LA: 2, LB: 1} and comp["representative"] == LA
    assert [m["member"] for m in comp["merges"]] == [LB, LC]      # sorted id order
    assert all(m["outcome"] == "merged" for m in comp["merges"])
    assert w.registry.resolve(LB) == w.registry.resolve(LC) == LA == comp["served"]
    same_as, reps = merge_events(w)
    assert len(same_as) == len(reps) == 2                        # no re-point event
    ev = [r for r in rows(w, "kind") if r.value == "identity_merge"]
    assert len(ev) == 2
    assert [r.value for r in reps] == [LA, LA]
    w.close()


def test_the_same_verdicts_in_another_order_give_a_byte_identical_log(tmp_path):
    answers = {(LA, LB): ("same", "a"), (LA, LC): ("same", "a"), (LB, LC): ("same", "b")}
    w1, r1 = gate_world(tmp_path, registry(LEDGERS), scripted(answers), name="fwd")
    w2, r2 = gate_world(tmp_path, registry(LEDGERS), scripted(answers, reverse=True), name="rev")
    assert dump(w1.buffer) == dump(w2.buffer)
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
    w1.close(); w2.close()


def test_tie_on_votes_is_broken_by_the_longest_name_which_may_be_a_third_member(tmp_path):
    # ledger t_a keeps (t_a, t_b); t_b keeps (t_b, t_c)... one vote each; t_c has no vote
    answers = {("obj:t_a", "obj:t_b"): ("same", "a"),    # votes obj:t_a
               ("obj:t_b", "obj:t_c"): ("same", "a")}    # votes obj:t_b
    w, report = gate_world(tmp_path, registry(TIE), scripted(answers))
    (comp,) = report["components"]
    assert comp["votes"] == {"obj:t_a": 1, "obj:t_b": 1}
    assert comp["representative"] == "obj:t_c"            # the third member: the longest name
    assert [m["member"] for m in comp["merges"]] == ["obj:t_a", "obj:t_b"]
    for i in TIE:
        assert w.registry.resolve(i) == "obj:t_c"
    assert w.porcelain.closure("obj:t_a") == ["obj:t_a", "obj:t_b", "obj:t_c"]
    same_as, reps = merge_events(w)
    assert len(same_as) == len(reps) == 2
    w.close()


def test_vote_tie_and_equal_names_falls_to_the_smallest_id(tmp_path):
    reg = registry({"obj:x2": card("object", ["Ledger One"]), "obj:x1": card("object", ["Ledger Two"])})
    w, report = gate_world(tmp_path, reg, scripted({("obj:x1", "obj:x2"): ("same", "a")}))
    assert report["components"][0]["representative"] == "obj:x1"     # one vote
    w.close()
    # no votes can tie at zero for a same pair, so test the election directly
    sides = {"obj:x2": {"names": ["Ledger One"], "aliases": []},
             "obj:x1": {"names": ["Ledger Two"], "aliases": []}}
    assert mg.elect_representative(["obj:x1", "obj:x2"], {"obj:x1": 1, "obj:x2": 1}, sides) == "obj:x1"
    sides["obj:x2"]["names"] = ["Ledger One!"]
    assert mg.elect_representative(["obj:x1", "obj:x2"], {"obj:x1": 1, "obj:x2": 1}, sides) == "obj:x2"


def test_vault_chain_conflicting_component_writes_nothing(tmp_path):
    # a same c, b same c, while a is different from b
    answers = {(LA, LB): ("different",), (LA, LC): ("same", "a"), (LB, LC): ("same", "a")}
    w, report = gate_world(tmp_path, registry(LEDGERS), scripted(answers))
    (comp,) = report["components"]
    assert comp["status"] == "conflicting_component"
    assert comp["members"] == [LA, LB, LC] and comp["different_pairs"] == ["p0001"]
    assert comp["same_pairs"] == ["p0002", "p0003"] and comp["merges"] == []
    assert report["counts"]["conflicting_components"] == 1 and report["counts"]["merges"] == {}
    base, _ = gate_world(tmp_path, registry(LEDGERS), all_unsure, name="base")
    assert dump(w.buffer) == dump(base.buffer)
    w.close(); base.close()


def test_other_components_still_apply_beside_a_conflicting_one(tmp_path):
    reg = registry({**LEDGERS, "place:hall_a": card("room", ["Grand Hall"]),
                    "place:hall_b": card("room", ["Hall"])})
    answers = {(LA, LB): ("different",), (LA, LC): ("same", "a"), (LB, LC): ("same", "a"),
               ("place:hall_a", "place:hall_b"): ("same", "a")}
    w, report = gate_world(tmp_path, reg, scripted(answers))
    assert [c["status"] for c in report["components"]] == ["conflicting_component", "applied"]
    assert w.registry.resolve("place:hall_b") == "place:hall_a"
    assert w.registry.resolve(LB) == LB and w.registry.resolve(LC) == LC
    w.close()


def test_a_different_pair_outside_the_component_does_not_block_it(tmp_path):
    reg = registry({**LEDGERS, "obj:ledger_d": card("object", ["Ledger Four"])})
    answers = {(LA, LB): ("same", "a"), (LA, "obj:ledger_d"): ("different",)}
    w, report = gate_world(tmp_path, reg, scripted(answers))
    (comp,) = report["components"]
    assert comp["status"] == "applied" and comp["members"] == [LA, LB]
    w.close()


# --------------------------------------------- 6: persons, vetoes, partials


def test_person_against_non_person_is_never_a_candidate_even_through_the_gate(tmp_path):
    calls: list = []
    w, report = gate_world(tmp_path, desk_registry(), scripted({}, calls=calls))
    asked = {(p["a"]["id"], p["b"]["id"]) for c in calls for p in c[2]["pairs"]}
    assert asked == {("obj:ilsa_desk", "obj:renn_desk"),
                     ("person:tin_ear_clerk", "person:vael_clerk")}
    assert not any(i.startswith("person:") != j.startswith("person:") for i, j in asked)
    w.close()


def test_a_person_by_folded_kind_is_a_person(tmp_path):
    reg = registry({"obj:sela": card("person", ["Sela Voss"]),
                    "obj:vase": card("object", ["Sela's Vase"])})
    w = make_world(tmp_path, reg)
    assert mg.candidate_pairs(w) == []
    w.close()


def test_event_against_non_event_is_never_a_candidate(tmp_path):
    # the metered run's rep 2 merged event:memory_core_theft into the core (r2.2)
    reg = registry({"event:core_theft": card("event", ["the memory core theft"]),
                    "obj:core": card("object", ["the memory core"]),
                    "obj:core_case": card("object", ["the memory core case"]),
                    "event:theft_night": card("event", ["the night of the core theft"])})
    w = make_world(tmp_path, reg)
    got = mg.candidate_pairs(w)
    assert ("event:core_theft", "obj:core") not in got
    assert ("event:core_theft", "event:theft_night") in got     # event against event stays
    assert ("obj:core", "obj:core_case") in got
    w.close()


def test_an_event_by_folded_kind_is_an_event(tmp_path):
    reg = registry({"obj:the_fire": card("event", ["the warehouse fire"]),
                    "place:warehouse": card("room", ["the warehouse"])})
    w = make_world(tmp_path, reg)
    assert mg.candidate_pairs(w) == []
    w.close()


def test_the_r24_vault_pair_is_never_a_candidate(tmp_path):
    reg = registry({
        "place:records_vault": card("room", ["Records Vault"], ["the vault"]),
        "place:seed_vault": card("room", ["Seed Vault"], ["the vault"]),
        "place:vault": card("room", ["the vault"]),
    })
    w = make_world(tmp_path, reg)
    for a, b in (("place:records_vault", "place:seed_vault"),):
        w.porcelain.reject(a, b)                       # what ALIAS-INDEX-V1 Part B writes
    got = mg.candidate_pairs(w)
    assert ("place:records_vault", "place:seed_vault") not in got
    assert ("place:records_vault", "place:vault") in got
    w.close()


def test_a_same_verdict_the_engine_vetoes_writes_nothing_and_reports_the_reason(tmp_path):
    reg = registry({"place:cellar": card("room", ["Deep Cellar"]),
                    "place:cellar_vent": card("room", ["Cellar Vent"])})
    w = make_world(tmp_path, reg)
    w.ingest_structured([{"entity": "place:cellar_vent", "attribute": "in",
                          "value": "place:cellar", "value_type": "entity"}])
    before = dump(w.buffer)
    report = finalize_identity(w, reconcile=False, gate=scripted(
        {("place:cellar", "place:cellar_vent"): ("same", "a", "one place")}))
    (comp,) = report["components"]
    (merge,) = comp["merges"]
    assert merge["outcome"] == "vetoed" and merge["reason"] and merge["blocking_edges"]
    assert report["counts"]["merges"] == {"vetoed": 1}
    assert rows(w, "same_as") == []
    assert w.registry.resolve("place:cellar_vent") == "place:cellar_vent"
    assert dump(w.buffer) == before                     # nothing written, nothing retracted
    w.close()


def test_a_veto_partway_leaves_the_members_merged_so_far_and_says_so(tmp_path):
    reg = registry(LEDGERS)
    w = make_world(tmp_path, reg)
    # ledger_c sits inside ledger_b: merging c into the closure holding b is vetoed
    w.ingest_structured([{"entity": LC, "attribute": "in", "value": LB, "value_type": "entity"}])
    answers = {(LA, LB): ("same", "a"), (LA, LC): ("same", "a"), (LB, LC): ("unsure",)}
    report = finalize_identity(w, reconcile=False, gate=scripted(answers))
    (comp,) = report["components"]
    assert [(m["member"], m["outcome"]) for m in comp["merges"]] == [(LB, "merged"), (LC, "vetoed")]
    assert comp["partial"] is True and comp["representative"] == LA
    assert w.registry.resolve(LB) == LA and w.registry.resolve(LC) == LC
    assert len(rows(w, "same_as")) == 1 and rows(w, "retracts") == []
    w.close()


def test_different_and_unsure_write_nothing(tmp_path):
    answers = {(LA, LB): ("different",), (LA, LC): ("unsure",)}
    w, report = gate_world(tmp_path, registry(LEDGERS), scripted(answers))
    base, _ = gate_world(tmp_path, registry(LEDGERS), all_unsure, name="base")
    assert dump(w.buffer) == dump(base.buffer)
    assert rows(w, "distinct_from") == []                       # `different` is only reported
    assert report["counts"]["verdicts"] == {"different": 1, "unsure": 2}
    w.close(); base.close()


# ------------------------------------------------ 7: keep is a vote, honoured


def test_a_component_of_one_pair_honours_its_keep_exactly(tmp_path):
    reg = registry({"obj:m": card("object", ["Brass Ledger of the Vault"]),
                    "obj:n": card("object", ["Ledger"])})
    for keep, want in (("a", "obj:m"), ("b", "obj:n")):    # the shorter name can be kept
        w, report = gate_world(tmp_path, reg, scripted({("obj:m", "obj:n"): ("same", keep)}),
                               name=f"k{keep}")
        assert report["components"][0]["representative"] == want
        assert w.registry.resolve("obj:m") == w.registry.resolve("obj:n") == want
        w.close()


def test_votes_beat_name_length(tmp_path):
    answers = {(LA, LB): ("same", "a"), (LA, LC): ("same", "a"), (LB, LC): ("same", "a")}
    w, report = gate_world(tmp_path, registry(LEDGERS), scripted(answers))
    assert report["components"][0]["representative"] == LA        # 2 votes; ledger_b has the longest name
    assert w.registry.resolve(LC) == LA
    w.close()


def test_evidence_names_the_pairs_reasons(tmp_path):
    answers = {(LA, LB): ("same", "a", "brass ledger twice"), (LA, LC): ("same", "a", "")}
    w, report = gate_world(tmp_path, registry(LEDGERS), scripted(answers))
    ev = {r.entity: r.value for r in rows(w, "evidence") if r.entity.startswith("event:merge")}
    assert sorted(ev.values()) == ["merge gate: brass ledger twice", "merge gate: p0002"]
    assert all(r.value == "host" for r in rows(w, "decided_by") if r.entity.startswith("event:merge"))
    w.close()


# ------------------------------------ 3: off, and all-unsure, are R24's commit


def desk_pipeline(tmp_path, name, model, **kw):
    p = Pipeline(model, WID, tmp_path / name, max_workers=1, **kw)
    write_source_segments(p.run_dir, ["Ilsa Renn's desk stood by the window.\n\nIlsa's desk was empty."])
    return p


def commit_dump(tmp_path, name, model=stub, **kw):
    p = desk_pipeline(tmp_path, name, model, **kw)
    w = p.commit(tmp_path / f"{name}.world", desk_registry())
    d = dump(w.buffer)
    w.close()
    return p, hashlib.sha256(d.encode()).hexdigest(), d


def test_gate_off_and_an_all_unsure_gate_are_r24s_default_commit_byte_for_byte(tmp_path):
    def model(prompt, schema):
        if schema.get("title") == "merge_gate":
            return all_unsure(prompt, schema)
        return stub(prompt, schema)

    off, h_off, d_off = commit_dump(tmp_path, "off")
    assert not (off.run_dir / MERGE_GATE_FILE).exists()
    on, h_on, d_on = commit_dump(tmp_path, "on", model, merge_gate=True)
    assert h_on == h_off and d_on == d_off
    rep = json.loads((on.run_dir / MERGE_GATE_FILE).read_text())
    assert rep["counts"]["candidates"] == 2 and rep["counts"]["merges"] == {}
    assert rep["source"] == "file"
    # and R24's default commit is "today's": the explicit flag changes nothing either
    _, h_flag, _ = commit_dump(tmp_path, "flag", merge_gate=False)
    assert h_flag == h_off


def test_a_real_gate_changes_the_log_only_by_its_merges(tmp_path):
    def model(prompt, schema):
        if schema.get("title") == "merge_gate":
            return scripted({("obj:ilsa_desk", "obj:renn_desk"): ("same", "b", "the desk")})(
                prompt, schema)
        return stub(prompt, schema)
    _, h_off, d_off = commit_dump(tmp_path, "off")
    p, h_on, d_on = commit_dump(tmp_path, "on", model, merge_gate=True)
    assert h_on != h_off
    rep = json.loads((p.run_dir / MERGE_GATE_FILE).read_text())
    assert rep["counts"]["merges"] == {"merged": 1}
    w = World(tmp_path / "on.world", world_id=WID, model=stub)
    assert w.registry.resolve("obj:ilsa_desk") == "obj:renn_desk"       # keep b = the longer name
    w.close()


def test_the_gate_reads_the_source_even_with_part_b_off(tmp_path):
    calls: list = []

    def model(prompt, schema):
        if schema.get("title") == "merge_gate":
            return scripted({}, calls=calls)(prompt, schema)
        return stub(prompt, schema)
    p, _, _ = commit_dump(tmp_path, "nb", model, merge_gate=True, alias_distinct=False)
    ctx = [s["context"] for c in calls for q in c[2]["pairs"] for s in (q["a"], q["b"])]
    assert any(ctx)
    assert json.loads((p.run_dir / MERGE_GATE_FILE).read_text())["source"] == "file"


def test_no_source_means_empty_context(tmp_path):
    p = Pipeline(stub, WID, tmp_path / "ns", max_workers=1, merge_gate=True)
    calls: list = []
    p.model = scripted({}, calls=calls)
    w = p.commit(tmp_path / "ns.world", desk_registry())
    assert calls and all(s["context"] == [] for c in calls for q in c[2]["pairs"]
                         for s in (q["a"], q["b"]))
    assert json.loads((p.run_dir / MERGE_GATE_FILE).read_text())["source"] == "none"
    w.close()


# ------------------------------------------------------------ 5: determinism


def test_same_answers_give_a_byte_identical_log_and_report_from_a_fresh_pipeline(tmp_path):
    answers = {("obj:ilsa_desk", "obj:renn_desk"): ("same", "b", "the desk"),
               ("person:tin_ear_clerk", "person:vael_clerk"): ("different", None, "two clerks")}

    def model(prompt, schema):
        if schema.get("title") == "merge_gate":
            return scripted(answers)(prompt, schema)
        return stub(prompt, schema)

    p = desk_pipeline(tmp_path, "run", model, merge_gate=True)
    reg = desk_registry()
    w1 = p.commit(tmp_path / "one.world", reg)
    d1, rep1 = dump(w1.buffer), (p.run_dir / MERGE_GATE_FILE).read_bytes()
    assert json.loads(rep1)["counts"]["merges"] == {"merged": 1}
    w1.close()
    (p.run_dir / MERGE_GATE_FILE).unlink()

    fresh = Pipeline(model, WID, p.run_dir, max_workers=1, merge_gate=True)   # nothing in memory
    w2 = fresh.commit(tmp_path / "two.world", WorldRegistry.load(p.run_dir / "registry.json", WID))
    assert dump(w2.buffer) == d1
    assert (fresh.run_dir / MERGE_GATE_FILE).read_bytes() == rep1
    w2.close()


def test_report_lists_every_candidate_with_its_batch_verdict_keep_reason_and_outcome(tmp_path):
    answers = {(LA, LB): ("same", "b", "why"), (LA, LC): ("unsure",)}
    w, report = gate_world(tmp_path, registry(LEDGERS), scripted(answers), batch_size=2)
    assert report["gate"] == "merge_gate" and report["batch_size"] == 2 and report["model"] is None
    assert [(p["pair_id"], p["batch"]) for p in report["pairs"]] == [
        ("p0001", 1), ("p0002", 1), ("p0003", 2)]
    p1 = report["pairs"][0]
    assert (p1["verdict"], p1["keep"], p1["keep_id"], p1["reason"], p1["status"]) == (
        "same", "b", LB, "why", "answered")
    assert [m["outcome"] for m in report["components"][0]["merges"]] == ["merged"]
    json.dumps(report)                                           # serializable
    w.close()


def test_model_identity_is_recorded_when_the_model_exposes_one(tmp_path):
    gate = scripted({})
    gate.identity = "test-model-1"
    _, report = gate_world(tmp_path, registry(LEDGERS), gate)
    assert report["model"] == "test-model-1"


def test_no_candidates_means_no_calls(tmp_path):
    calls: list = []
    w, report = gate_world(tmp_path, registry({"obj:a": card("object", ["Alpha"]),
                                              "obj:b": card("object", ["Beta"])}),
                           scripted({}, calls=calls))
    assert calls == [] and report["counts"]["candidates"] == 0 and report["counts"]["batches"] == 0
    w.close()


def test_asking_writes_nothing(tmp_path):
    w = make_world(tmp_path, registry(LEDGERS))
    heads = []

    def spy(prompt, schema):
        heads.append(w.buffer.head())
        return all_unsure(prompt, schema)
    head0 = w.buffer.head()
    finalize_identity(w, reconcile=False, gate=spy, gate_batch_size=1)
    assert heads == [head0] * 3                                    # one head through every ask
    w.close()


# ------------------------------------- 1, 2: the five stored registries (free)

STORED = {
    "r23-run1": RESULTS / "2026-10-10-r23-pass0-baseline" / "run1",
    "r23-run2": RESULTS / "2026-10-10-r23-pass0-baseline" / "run2",
    "r26-seq": RESULTS / "2026-10-10-r26-build-timings" / "seq",
    "r26-par1b": RESULTS / "2026-10-10-r26-build-timings" / "par1b",
    "r26-par2b": RESULTS / "2026-10-10-r26-build-timings" / "par2b",
}
#: candidates after R24's finalization, with the pair ``distinct_from`` holds apart
#: left out. The spec's 84, 98, 92, 287, 285 counted that one pair (the vaults) in
#: four registries (r23 run1, run2, par1b, par2b). r2.2 bars event against
#: non-event; before it the counts were 83, 97, 92, 286, 284.
CANDIDATES = {"r23-run1": 65, "r23-run2": 77, "r26-seq": 73, "r26-par1b": 228, "r26-par2b": 208}
BATCHES = {"r23-run1": 3, "r23-run2": 4, "r26-seq": 3, "r26-par1b": 10, "r26-par2b": 9}
GOLD_DIFFERENT = {"r23-run1": 4, "r23-run2": 8, "r26-seq": 4, "r26-par1b": 15, "r26-par2b": 8}
SPLIT_PAIRS = {"r23-run1": 0, "r23-run2": 0, "r26-seq": 0, "r26-par1b": 4, "r26-par2b": 7}
ORACLE_F1_FLOOR = {"r26-par1b": 0.8483, "r26-par2b": 0.8339}


@pytest.fixture(scope="module")
def story_segments() -> list[str]:
    import run_pass0_baseline
    return run_pass0_baseline.story_segments()


@pytest.fixture(scope="module")
def oracle_effects(story_segments) -> dict[str, dict]:
    return {name: merge_gate_effect(d / "registry.json", story_segments, gold_oracle_gate())
            for name, d in STORED.items()}


@pytest.mark.parametrize("name", sorted(STORED))
def test_pass_mark_1_candidate_recall_and_counts(oracle_effects, name):
    e = oracle_effects[name]
    assert e["recall"]["found"] == e["recall"]["of"] == SPLIT_PAIRS[name]
    assert e["recall"]["missed"] == []
    assert (e["candidates"], e["batches"], e["calls"]) == (
        CANDIDATES[name], BATCHES[name], BATCHES[name])
    assert e["labels"].get("different", 0) == GOLD_DIFFERENT[name]
    assert e["labels"].get("same", 0) == SPLIT_PAIRS[name]
    report = e["gate_report"]
    assert ("place:records_vault", "place:seed_vault") not in {
        (p["a"], p["b"]) for p in report["pairs"]}


def test_pass_mark_1_totals():
    assert sum(SPLIT_PAIRS.values()) == 11 and sum(GOLD_DIFFERENT.values()) == 39
    assert sum(GOLD_DIFFERENT.values()) + 4 == 43     # plus the held-apart vault pair, four times


@pytest.mark.parametrize("name", sorted(STORED))
def test_pass_mark_2_oracle_ceiling(oracle_effects, name):
    e = oracle_effects[name]
    assert e["gated"]["fragmentation_count"] == 0
    assert e["gated"]["fusion_count"] == 0
    assert e["gated"]["b3_f1"] >= e["default"]["b3_f1"]
    assert e["split_pairs_joined"] == SPLIT_PAIRS[name]
    assert e["same_by_label"] == ({"same": SPLIT_PAIRS[name]} if SPLIT_PAIRS[name] else {})
    assert e["verdicts"].get("same", 0) == SPLIT_PAIRS[name]
    assert e["conflicting_components"] == 0
    if name in ORACLE_F1_FLOOR:
        assert e["gated"]["b3_f1"] >= ORACLE_F1_FLOOR[name]


def test_pass_mark_2_the_oracle_is_a_measurement_gate_not_a_real_one():
    assert gold_oracle_gate().identity == "gold-oracle"
    assert not hasattr(mg, "gold_oracle_gate")


def test_pass_mark_3_all_unsure_gate_leaves_every_stored_log_byte_identical(story_segments, monkeypatch):
    """Through the shared path: the dump the finalization leaves, per registry."""
    seen: list[str] = []
    real = pl.finalize_identity

    def spy(w, **kw):
        out = real(w, **kw)
        seen.append(dump(w.buffer))
        return out
    monkeypatch.setattr(pl, "finalize_identity", spy)
    for name, d in sorted(STORED.items()):
        seen.clear()
        seeded_registry(d / "registry.json", segments=story_segments)
        seeded_registry(d / "registry.json", segments=story_segments, gate=all_unsure)
        assert len(seen) == 2 and seen[0] == seen[1], name


def test_pass_mark_3_without_a_gate_seeded_registry_is_unchanged(story_segments):
    reg = STORED["r26-par1b"] / "registry.json"
    base = seeded_registry(reg, segments=story_segments)
    assert "gate_report" not in base
    gated = seeded_registry(reg, segments=story_segments, gate=all_unsure)
    assert gated.pop("gate_report")["counts"]["merges"] == {}
    assert gated == base


# ------------------------------------- the metered runner (never called here)


def test_dry_run_counts_the_metered_run_without_a_model(story_segments, monkeypatch, capsys):
    import run_merge_gate_metered as rm
    monkeypatch.setitem(sys.modules, "model_shim", None)   # importing the real model would fail
    out = rm.dry_run({"r26-par2b": rm.REGISTRIES["r26-par2b"]}, 2, 25, story_segments)
    c = out["per_registry"]["r26-par2b"]
    assert (c["candidates"], c["batches"], c["calls"]) == (208, 9, 9)
    assert out["total"]["calls"] == 18 and out["est_tokens_total"] > 0
    assert "DRY RUN (no model is called)" in capsys.readouterr().out


def test_metered_run_and_scoring_with_the_oracle_standing_in_for_the_model(tmp_path, story_segments):
    import run_merge_gate_metered as rm
    only = {"r26-par2b": rm.REGISTRIES["r26-par2b"]}
    scoring = rm.run(tmp_path / "out", gold_oracle_gate(), "gold-oracle", reps=2,
                     registries=only, segments=story_segments)
    assert scoring["complete"] is False                       # one registry is not the pass mark
    r1, r2 = scoring["per_rep"]
    for r in (r1, r2):
        assert r["precision_ok"] and r["f1_ok"] and r["recall_joined"] == r["recall_of"] == 7
        assert r["unlabelled_same"] == 0
    assert scoring["run_to_run_differing_pairs"] == [] and scoring["sample"] == []
    meta = json.loads((tmp_path / "out" / "meta.json").read_text())
    assert meta["calls"] == 18 and meta["model"] == "gold-oracle"      # 9 batches x 2 reps
    rep = json.loads((tmp_path / "out" / "rep1" / "r26-par2b.json").read_text())
    assert rep["gate_report"]["model"] == "gold-oracle"
    assert (tmp_path / "out" / "SCORING.md").exists()


def test_scoring_flags_a_wrong_same_and_run_to_run_disagreement():
    import run_merge_gate_metered as rm

    def effect(verdict_p1, label_p1="different"):
        pairs = [{"pair_id": "p0001", "a": "x:a", "b": "x:b", "a_names": ["A"], "b_names": ["B"],
                  "verdict": verdict_p1, "keep_id": "x:a", "reason": "r"}]
        return {"pair_labels": {"p0001": label_p1}, "gate_report": {"pairs": pairs},
                "split_pairs_joined": 0, "split_pairs": [], "statuses": {}, "verdicts": {},
                "default": {"b3_f1": 0.8}, "gated": {"b3_f1": 0.79}}
    s = rm.score([{"r": effect("same")}, {"r": effect("unsure")}])
    r1, r2 = s["per_rep"]
    assert not r1["precision_ok"] and r2["precision_ok"]
    assert not r1["f1_ok"] and s["pass"] is False
    assert s["run_to_run_differing_pairs"] == [
        {"registry": "r", "a": "x:a", "b": "x:b", "verdicts": ["same", "unsure"]}]
    s = rm.score([{"r": effect("same", "unknown")}, {"r": effect("same", "unknown")}])
    assert s["unlabelled_same_pairs"] == 1 and len(s["sample"]) == 1
