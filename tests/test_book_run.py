"""BOOK-RUN-V1 (R27 prep): build any book, grade it against its answer key.
Every test here is the spec's Tests section or a detail it fixes. No model is
called anywhere: the runner takes a scripted double, and the grader reads hand-
built worlds."""

from __future__ import annotations

import builtins
import copy
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
HARNESS = ROOT / "evals" / "harness"
sys.path.insert(0, str(HARNESS))

from patternbuffer import World
from patternbuffer.testing import rule_classifier_fallback

import book_gold as bg
import grade_book as gb
import merge_gate as mg
import run_book as rb
import usage_ledger
from pipeline import seed_world
from registry import EntityCard, TimelineSpec, WorldRegistry

WID = "w:booktest"


# ------------------------------------------------------------- a toy book

TOY_CHAPTERS = {
    1: "# Chapter 1: The Lamp\n\nMara kept the brass lamp in the cellar of the old mill.\n\n"
       "* * *\n\nOrin the ferryman watched the mill from the dock.\n",
    2: "# Chapter 2: The Crossing\n\nMara carried the brass lamp to the dock and gave it to Orin.\n",
    3: "# Chapter 3: The Return\n\nOrin returned the lamp to Mara, who locked it in the cellar again.\n",
}
PASS0_LINES = [
    "E|person:mara|person|Mara||", "E|person:orin|person|Orin|the ferryman|",
    "E|obj:lamp|object|brass lamp||", "E|place:cellar|room|cellar||",
    "E|place:dock|place|dock||", "O|Day 0 = the first morning",
]
PASS1_LINES = {
    0: ["obj:lamp|in|@place:cellar|vf=1,s=stated"],
    1: ["person:orin|in|@place:dock|vf=1,s=stated"],
    2: ["obj:lamp|held_by|@person:orin|vf=2,s=stated"],
    3: ["obj:lamp|in|@place:cellar|vf=3,s=stated"],
}


def write_book(root: Path, chapters: dict[int, str] | None = None, with_key: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for n, text in (chapters or TOY_CHAPTERS).items():
        (root / f"ch{n:02d}.md").write_text(text)
    if with_key:
        (root / "key.json").write_text(json.dumps({"same_as": [], "not_same": []}))
        (root / "graded.json").write_text("{}")
    return root


def scripted_model(calls: list | None = None, unpriced: tuple[str, ...] = ()):
    """A scripted model for the whole build. Each call is counted in the usage
    ledger as a real shim would; the kinds in ``unpriced`` report no price."""

    def model(prompt, schema):
        if "PASSAGE (chunk" in prompt:
            kind = "pass1"
        elif "WORLD REGISTRY" in prompt:
            kind = "pass0"
        elif "ops" in schema.get("properties", {}):
            kind = "audit"
        else:
            kind = schema.get("title", "other")
        if calls is not None:
            calls.append(kind)
        usage_ledger.record("test", "scripted", {"input_tokens": 100, "output_tokens": 10},
                            cost_usd=None if kind in unpriced else 0.01)
        if kind == "pass1":
            chunk_id = int(prompt.split("PASSAGE (chunk ")[1].split(")")[0])
            return {"lines": PASS1_LINES[chunk_id]}
        if kind == "pass0":
            return {"lines": PASS0_LINES}
        if kind == "audit":
            return {"ops": []}
        if kind == mg.TASK_MERGE_GATE:
            return {"verdicts": [{"pair_id": p["pair_id"], "verdict": "unsure"}
                                 for p in mg.batch_request(schema)["pairs"]]}
        return rule_classifier_fallback()(prompt, schema)

    return model


@pytest.fixture(autouse=True)
def _clean_usage(monkeypatch):
    monkeypatch.delenv(rb.USAGE_ENV, raising=False)
    usage_ledger.reset()
    yield
    usage_ledger.reset()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """One scripted build of the toy book (pass-0 calls report no price)."""
    base = tmp_path_factory.mktemp("built")
    book, out = write_book(base / "toybook"), base / "out"
    calls: list[str] = []
    meta = rb.run_book(book, out, scripted_model(calls, unpriced=("pass0",)))
    return {"book": book, "out": out, "meta": meta, "calls": calls}


# ------------------------------------------------- 1. the runner without a model


def _twelve_chapter_book(root: Path) -> Path:
    chapters = {}
    for n in range(1, 13):
        body = f"# Chapter {n}: Title {n}\n\nParagraph one of chapter {n}.\n\n"
        body += "* * *\n\nParagraph two.\n" if n % 2 == 0 else "Paragraph two.\n"
        chapters[n] = body
    return write_book(root, chapters)


def test_dry_run_counts_segments_and_chunks_and_imports_no_model(tmp_path):
    book = _twelve_chapter_book(tmp_path / "twelve")
    code = (f"import sys; sys.path.insert(0, {str(HARNESS)!r}); import run_book; "
            f"rc = run_book.main(['--book', {str(book)!r}, '--dry-run']); "
            "bad = [m for m in ('model_shim', 'codex_shim') if m in sys.modules]; "
            "sys.stderr.write('IMPORTED ' + ','.join(bad) if bad else ''); sys.exit(rc or len(bad))")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["segments"] == 12
    assert report["chunks"] == 6 * 1 + 6 * 2   # odd chapters one chunk, even ones split on * * *
    assert report["est_wall_s_sequential"] > 0 and report["est_input_tokens"] > 0
    assert "IMPORTED" not in proc.stderr


def test_a_scripted_model_builds_the_toy_book_and_writes_every_stage(built):
    out, meta = built["out"], built["meta"]
    receipt = json.loads((out / "receipt.json").read_text())
    assert set(receipt["stages"]) == set(rb.STAGES)
    for stage in receipt["stages"].values():
        assert {"seconds", "calls", "calls_without_usage", "input_tokens", "output_tokens",
                "cache_read_tokens", "cache_write_tokens", "cost_usd", "cost_known"} <= set(stage)
    assert set(receipt["total"]) >= {"seconds", "calls", "cost_usd", "cost_known"}
    assert meta["chapters"] == 3 and meta["chunks"] == 4
    assert (out / "fresh_ingest.world").exists() and (out / "ingest_dump.jsonl").exists()
    timings = json.loads((out / "timings.json").read_text())
    assert {f"{s}_s" for s in rb.STAGES} <= set(timings)
    # one pass-0 segment per chapter, pass-1 one call per chunk, the cursor is the chapter
    assert built["calls"].count("pass0") == 3 and built["calls"].count("pass1") == 4


def test_receipt_stages_are_deltas_and_sum_to_the_total(built):
    receipt = json.loads((built["out"] / "receipt.json").read_text())
    stages, total = receipt["stages"], receipt["total"]
    assert stages["pass0"]["calls"] == 3 and stages["pass1"]["calls"] == 4
    assert stages["audit"]["calls"] == 1
    assert stages["commit"]["calls"] >= 1                      # classification
    assert sum(s["calls"] for s in stages.values()) == total["calls"]
    assert sum(s["input_tokens"] for s in stages.values()) == total["input_tokens"] == 100 * total["calls"]
    assert sum(s["cost_usd"] for s in stages.values()) == pytest.approx(total["cost_usd"])
    # the price flag is per stage: only pass-0 left a call unpriced
    assert stages["pass0"]["cost_known"] is False
    assert all(stages[s]["cost_known"] for s in ("pass1", "escape_repair", "commit", "audit"))
    assert total["cost_known"] is False
    assert stages["escape_repair"]["calls"] == 0


def test_the_usage_log_holds_only_this_run(tmp_path):
    book = write_book(tmp_path / "toybook")
    out = tmp_path / "out"
    out.mkdir()
    (out / "usage.jsonl").write_text('{"stale": true}\n')
    rb.run_book(book, out, scripted_model())
    assert (out / "usage.jsonl.1").read_text() == '{"stale": true}\n'
    lines = (out / "usage.jsonl").read_text().splitlines()
    receipt = json.loads((out / "receipt.json").read_text())
    assert len(lines) == receipt["total"]["calls"] and all("stale" not in ln for ln in lines)
    rb.run_book(book, out, scripted_model())            # a second rerun takes the next free n
    assert (out / "usage.jsonl.2").exists() and (out / "usage.jsonl.1").exists()
    assert os.environ.get(rb.USAGE_ENV) is None         # the runner restores the environment


def test_parallel_pass0_and_the_merge_gate_run(tmp_path):
    book = write_book(tmp_path / "toybook")
    out = tmp_path / "out"
    meta = rb.run_book(book, out, scripted_model(), pass0="parallel", merge_gate=True)
    assert meta["pass0_mode"] == "parallel" and meta["merge_gate"] is True
    assert (out / "merge_gate.json").exists()
    assert json.loads((out / "receipt.json").read_text())["total"]["calls"] > 0


def test_a_failed_stage_keeps_what_it_spent(tmp_path):
    book = write_book(tmp_path / "toybook")
    out = tmp_path / "out"
    good = scripted_model()

    def breaks_in_pass1(prompt, schema):
        if "PASSAGE (chunk" in prompt:
            usage_ledger.record("test", "scripted", {"input_tokens": 7}, cost_usd=0.5)
            raise RuntimeError("boom")
        return good(prompt, schema)

    with pytest.raises(rb.BookRunAborted):
        rb.run_book(book, out, breaks_in_pass1)
    receipt = json.loads((out / "receipt.json").read_text())
    assert receipt["stages"]["pass0"]["calls"] == 3
    assert receipt["stages"]["pass1"]["calls"] >= 4 and receipt["stages"]["pass1"]["cost_usd"] >= 2.0
    assert "commit" not in receipt["stages"]


# -------------------------------------------------- chunks and the book directory


def test_chunks_split_on_scene_breaks_else_group_paragraphs():
    scenes = rb.split_chunks("# Chapter 1: A\n\nOne.\n\n* * *\n\nTwo.\n\n---\n\nThree.\n")
    assert [c.splitlines()[-1] for c in scenes] == ["One.", "Two.", "Three."]
    para = " ".join(["word"] * 500)
    chapter = "# Chapter 1: A\n\n" + "\n\n".join([para] * 5)
    chunks = rb.split_chunks(chapter)
    sizes = [len(c.split()) for c in chunks]
    assert sizes == [1004, 1000, 500]          # about 1,200 words, never over it
    assert rb.split_chunks("# Chapter 1: A\n\nShort.") == ["# Chapter 1: A\n\nShort."]


def test_chunk_cursor_is_the_chapter_number(tmp_path):
    plan = rb.load_book(write_book(tmp_path / "toybook"))
    assert [c for c, _ in plan.chunks] == [1.0, 1.0, 2.0, 3.0]
    assert plan.segments[1] == TOY_CHAPTERS[2]


def test_book_with_gaps_or_bad_headings_is_refused(tmp_path):
    with pytest.raises(rb.BookRefused):
        rb.load_book(write_book(tmp_path / "gap", {1: TOY_CHAPTERS[1], 3: TOY_CHAPTERS[3]}))
    with pytest.raises(rb.BookRefused):
        rb.load_book(write_book(tmp_path / "head", {1: "No heading here.\n"}))
    with pytest.raises(rb.BookRefused):
        rb.load_book(write_book(tmp_path / "wrong", {1: "# Chapter 2: Wrong\n\nText.\n"}))


# ----------------------------------------------------------- 2. the key guard


@pytest.mark.parametrize("leak", ['the "same_as" list', 'the "not_same" pairs', "the Answer Key says"])
def test_a_chapter_with_a_key_marker_is_refused_before_any_call(tmp_path, leak):
    chapters = dict(TOY_CHAPTERS)
    chapters[2] += f"\n{leak}\n"
    book = write_book(tmp_path / "leaky", chapters)
    calls: list[str] = []
    with pytest.raises(SystemExit) as exc:
        rb.main(["--book", str(book), "--out", str(tmp_path / "out")], model=scripted_model(calls))
    assert "ch02.md" in str(exc.value) and calls == []
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").glob("*.world"))


# ------------------------------------------------------------- 5. isolation


def test_the_build_never_opens_the_key_or_the_graded_set(tmp_path, monkeypatch):
    book = write_book(tmp_path / "toybook")
    opened: list[str] = []
    real_open, real_io_open, real_path_open = builtins.open, io.open, Path.open

    def spy(real):
        def wrapper(file, *a, **k):
            opened.append(str(file))
            return real(file, *a, **k)
        return wrapper

    def path_spy(self, *a, **k):
        opened.append(str(self))
        return real_path_open(self, *a, **k)

    monkeypatch.setattr(builtins, "open", spy(real_open))
    monkeypatch.setattr(io, "open", spy(real_io_open))
    monkeypatch.setattr(Path, "open", path_spy)
    rb.main(["--book", str(book), "--out", str(tmp_path / "out")], model=scripted_model())
    monkeypatch.undo()
    assert any(p.endswith("ch01.md") for p in opened)           # the spy sees reads
    assert not [p for p in opened if p.endswith(("key.json", "graded.json"))]


# --------------------------------------------------- 3. the grader, hand-built worlds


def card(kind, names, aliases=()):
    return EntityCard(kind=kind, names=list(names), aliases=list(aliases))


def base_cards() -> dict[str, EntityCard]:
    return {
        "person:mara": card("person", ["Mara Venn"], ["mara", "the keeper"]),
        "person:orin": card("person", ["Orin"], ["the ferryman", "the veiled woman"]),
        "obj:lamp": card("object", ["Brass Lamp"], ["the lamp"]),
        "place:cellar": card("room", ["Cellar"], ["the cellar"]),
        "place:dock": card("place", ["Dock"], ["the dock"]),
        "place:attic": card("room", ["Attic"], ["the attic"]),
        "obj:box": card("object", ["Oak Box"], ["the oak box"]),
        "obj:coin": card("object", ["Copper Coin"], ["the copper coin"]),
        "obj:key_a": card("object", ["Silver Key"], ["the silver key"]),
        "obj:key_b": card("object", ["Iron Key"], ["the iron key"]),
    }


def at(entity, attribute, value, t):
    return {"entity": entity, "attribute": attribute, "value": value,
            "value_type": "entity", "valid_from": t}


def lamp_rows(t0=10.0, t1=20.0, t2=30.0, middle=("held_by", "person:orin")):
    return [at("obj:lamp", "in", "place:cellar", t0),
            at("obj:lamp", middle[0], middle[1], t1),
            at("obj:lamp", "in", "place:cellar", t2),
            at("obj:coin", "in", "obj:box", t0)]


def make_world(tmp_path, cards, rows, name="w") -> World:
    reg = WorldRegistry(world_id=WID, entities=cards, attributes={},
                        timeline=TimelineSpec(origin="Day 0"))
    w = World(tmp_path / f"{name}.world", world_id=WID,
              model=lambda p, s: rule_classifier_fallback()(p, s))
    w.ingestor.classify_inline = False
    seed_world(w, reg)
    for row in rows:
        w.ingest_structured([row])
    w.classifier.classify_all(batch_size=40)
    return w


GRADED = {
    "key_sha256": "x", "readers": ["A", "B"],
    "entities": {
        "mara": {"kind": "person", "aliases": ["Mara Venn", "Mara", "the keeper"]},
        "orin": {"kind": "person", "aliases": ["Orin", "the ferryman"]},
        "lamp": {"kind": "object", "aliases": ["brass lamp", "the lamp"]},
        "cellar": {"kind": "place", "aliases": ["the cellar", "Cellar"]},
        "dock": {"kind": "place", "aliases": ["the dock"]},
        "attic": {"kind": "place", "aliases": ["the attic"]},
        "box": {"kind": "object", "aliases": ["the oak box"]},
        "coin": {"kind": "object", "aliases": ["the copper coin"]},
        "key_a": {"kind": "object", "aliases": ["the silver key"]},
        "key_b": {"kind": "object", "aliases": ["the iron key"]},
    },
    "same_as": [{"id": "same_as[0]", "entity": "orin", "alias": "the veiled woman", "chapter": 8}],
    "not_same": [{"id": "not_same[0]", "a": "key_a", "b": "key_b"}],
    "moves": {"lamp": [
        {"id": "locations[0]", "to": "cellar", "from_chapter": 1, "to_chapter": 4},
        {"id": "holdings[0]", "to": "orin", "from_chapter": 5, "to_chapter": 6},
        {"id": "locations[1]", "to": "cellar", "from_chapter": 7, "to_chapter": None}]},
    "containers": [{"id": "containers[0]", "container": "box", "contents": ["coin"]}],
    "dropped": [], "ungraded_counts": {"knowledge": 2, "false_beliefs": 1, "corrections": 0},
}


def grade_world(tmp_path, cards=None, rows=None, graded=None, name="w"):
    w = make_world(tmp_path, cards or base_cards(), lamp_rows() if rows is None else rows, name)
    try:
        return gb.grade_book(w, w.registry, graded or GRADED)
    finally:
        w.close()


def test_a_perfect_world_scores_one_everywhere(tmp_path):
    card_ = grade_world(tmp_path)
    assert card_["summary"] == {k: 1.0 for k in card_["summary"]}
    ident = card_["identity"]
    assert ident["split"] == {} and ident["fused"] == {} and ident["missing"] == []
    assert card_["look_alikes"]["fusions"] == []
    assert card_["order"]["objects"]["lamp"]["world"] == ["cellar", "orin", "cellar"]
    assert card_["final"]["objects"]["lamp"]["ok"] and card_["final"]["read"] == "as_of"
    assert card_["ungraded_counts"] == {"knowledge": 2, "false_beliefs": 1, "corrections": 0}


def test_a_split_person_shows_the_split_and_lowers_recall(tmp_path):
    cards = base_cards()
    cards["person:mara"] = card("person", ["Mara Venn"], ["mara"])
    cards["person:keeper"] = card("person", ["The Keeper"])        # the same woman, a second id
    split = grade_world(tmp_path, cards)
    assert set(split["identity"]["split"]) == {"mara"}
    assert sorted(split["identity"]["split"]["mara"]) == ["person:keeper", "person:mara"]
    assert split["identity"]["b3_recall"] < 1.0
    assert split["identity"]["b3_precision"] == 1.0
    assert split["identity"]["mapping"]["split"] == {"mara": ["person:keeper", "person:mara"]}


def test_a_missing_entity_is_listed(tmp_path):
    cards = base_cards()
    del cards["obj:coin"]
    result = grade_world(tmp_path, cards, rows=[])
    assert "coin" in result["identity"]["missing"]
    assert result["containers"]["score"] == 0.0


def test_a_merged_not_same_pair_shows_the_fusion_by_name(tmp_path):
    cards = base_cards()
    cards["obj:key_a"] = card("object", ["Silver Key"], ["the silver key", "the iron key"])
    del cards["obj:key_b"]
    result = grade_world(tmp_path, cards)
    assert result["look_alikes"]["score"] == 0.0
    assert result["look_alikes"]["fusions"] == ["key_a (the silver key) / key_b (the iron key)"]
    assert result["identity"]["fused"]          # one closure answering to two key entities


def test_an_unjoined_reveal_scores_zero(tmp_path):
    cards = base_cards()
    cards["person:orin"] = card("person", ["Orin"], ["the ferryman"])
    cards["person:veiled"] = card("person", ["The Veiled Woman"])
    result = grade_world(tmp_path, cards)
    assert result["reveals"]["score"] == 0.0 and not result["reveals"]["items"][0]["joined"]


def test_a_to_b_to_a_scores_one_and_a_to_c_to_a_scores_two_thirds(tmp_path):
    assert grade_world(tmp_path, name="aba")["order"]["objects"]["lamp"]["score"] == 1.0
    other = copy.deepcopy(GRADED)
    other["moves"]["lamp"][1]["to"] = "attic"                     # A -> C -> A expected
    result = grade_world(tmp_path, graded=other, name="aca")
    assert result["order"]["objects"]["lamp"]["score"] == pytest.approx(2 / 3, abs=1e-4)
    assert result["order"]["mean"] == pytest.approx(2 / 3, abs=1e-4)
    assert result["ever"]["score"] == pytest.approx(0.5)          # cellar found, attic not


def test_a_world_value_that_names_no_key_entity_is_kept_and_listed(tmp_path):
    cards = base_cards()
    cards["place:shed"] = card("room", ["Shed"])                 # not a key entity
    rows = lamp_rows(middle=("in", "place:shed"))
    result = grade_world(tmp_path, cards, rows)
    obj = result["order"]["objects"]["lamp"]
    assert obj["world"] == ["cellar", "?place:shed", "cellar"]
    assert obj["score"] == pytest.approx(2 / 3, abs=1e-4)


def test_day_numbers_that_differ_from_chapter_numbers_do_not_change_the_order_score(tmp_path):
    chapters_as_days = grade_world(tmp_path, rows=lamp_rows(1.0, 5.0, 7.0), name="ch")
    far_days = grade_world(tmp_path, rows=lamp_rows(-400.0, 0.5, 9000.0), name="far")
    for result in (chapters_as_days, far_days):
        assert result["order"]["objects"]["lamp"]["score"] == 1.0
        assert result["order"]["objects"]["lamp"]["world"] == ["cellar", "orin", "cellar"]


def test_order_follows_valid_time_not_the_order_asserted(tmp_path):
    rows = lamp_rows()
    result = grade_world(tmp_path, rows=[rows[2], rows[0], rows[1], rows[3]], name="shuffled")
    assert result["order"]["objects"]["lamp"]["world"] == ["cellar", "orin", "cellar"]


def test_final_reads_the_fold_at_the_end_and_catches_a_wrong_last_place(tmp_path):
    rows = lamp_rows()[:2] + [at("obj:lamp", "held_by", "person:mara", 30.0), lamp_rows()[3]]
    result = grade_world(tmp_path, rows=rows)
    assert result["final"]["score"] == 0.0
    assert result["final"]["objects"]["lamp"]["got"] == ["mara"]
    assert result["order"]["objects"]["lamp"]["score"] == pytest.approx(2 / 3, abs=1e-4)


def test_an_object_whose_last_entry_ends_before_the_book_is_not_scored_for_final(tmp_path):
    ended = copy.deepcopy(GRADED)
    ended["moves"]["lamp"][2]["to_chapter"] = 9
    result = grade_world(tmp_path, graded=ended)
    assert result["final"]["objects"] == {} and result["final"]["score"] is None
    assert result["summary"]["order"] == 1.0


def test_with_no_timed_row_final_is_the_head_read(tmp_path):
    cards = base_cards()
    rows = [{"entity": "obj:lamp", "attribute": "in", "value": "place:cellar",
             "value_type": "entity", "timeless": True}]
    w = make_world(tmp_path, cards, rows)
    try:
        assert not [r for r in w.buffer.visible() if r.valid_from is not None]
        result = gb.grade_book(w, None, GRADED)       # registry=None: the world's own
    finally:
        w.close()
    assert result["final"]["read"] == "head" and result["final"]["as_of"] is None
    assert result["final"]["objects"]["lamp"]["ok"] is True


def test_revealed_contents_must_be_placed_in_the_container(tmp_path):
    rows = [r for r in lamp_rows() if r["entity"] != "obj:coin"]
    rows.append(at("obj:coin", "in", "place:dock", 10.0))
    result = grade_world(tmp_path, rows=rows)
    assert result["containers"]["score"] == 0.0
    assert result["containers"]["items"][0]["placed"] == {"coin": False}


def test_curly_quotes_match_straight_ones_on_both_sides(tmp_path):
    assert bg.book_normalize("Or’s spoon") == bg.book_normalize("Or's spoon") == "or's spoon"
    assert bg.book_normalize("The woman with the copper hand") == "woman with the copper hand"
    assert bg.book_normalize("“the Lamp”") == '"the lamp"'
    cards = {"obj:spoon": card("object", ["Or's Spoon"])}
    graded = {**GRADED, "entities": {"spoon": {"kind": "object", "aliases": ["Or’s spoon"]}},
              "same_as": [], "not_same": [], "moves": {}, "containers": []}
    result = grade_world(tmp_path, cards, rows=[], graded=graded)
    assert result["identity"]["b3_f1"] == 1.0 and result["identity"]["missing"] == []
    assert result["summary"]["reveals"] is None and result["summary"]["order"] is None


def test_a_fused_closure_is_credited_for_the_order_of_each_key_it_holds(tmp_path):
    """The gate merged the attic into the cellar: the lamp's world sequence reads
    that one closure, which holds both key entities, so A -> C -> A still lands."""
    cards = base_cards()
    cards["place:cellar"] = card("room", ["Cellar"], ["the cellar", "the attic"])
    del cards["place:attic"]
    other = copy.deepcopy(GRADED)
    other["moves"]["lamp"][1]["to"] = "attic"
    result = grade_world(tmp_path, cards, graded=other)
    assert result["identity"]["fused"]                          # charged on identity
    assert result["order"]["objects"]["lamp"]["lcs"] >= 2


def test_the_scorecard_writes_json_and_markdown(tmp_path):
    result = grade_world(tmp_path)
    md, js = gb.write_scorecard(result, tmp_path / "out")
    assert json.loads(js.read_text())["summary"]["order"] == 1.0
    text = md.read_text()
    assert "identity B3 F1" in text and "Not graded in V1" in text and "knowledge: 2" in text


def test_the_grader_grades_a_built_world_from_the_command_line(built, tmp_path):
    graded = {
        "key_sha256": "x", "readers": ["A", "B"],
        "entities": {"mara": {"kind": "person", "aliases": ["Mara"]},
                     "lamp": {"kind": "object", "aliases": ["brass lamp"]},
                     "cellar": {"kind": "place", "aliases": ["cellar"]},
                     "orin": {"kind": "person", "aliases": ["Orin", "the ferryman"]}},
        "same_as": [], "not_same": [], "containers": [], "dropped": [], "ungraded_counts": {},
        "moves": {"lamp": [
            {"id": "locations[0]", "to": "cellar", "from_chapter": 1, "to_chapter": 2},
            {"id": "holdings[0]", "to": "orin", "from_chapter": 2, "to_chapter": 3},
            {"id": "locations[1]", "to": "cellar", "from_chapter": 3, "to_chapter": None}]},
    }
    path = tmp_path / "graded.json"
    path.write_text(json.dumps(graded))
    out = tmp_path / "grades"
    world_file = built["out"] / "fresh_ingest.world"
    before = (world_file.read_bytes(), world_file.stat().st_mtime_ns)
    siblings = sorted(p.name for p in world_file.parent.iterdir())
    world_file.chmod(0o444)                       # a write handle would fail on it
    try:
        assert gb.main(["--run", str(built["out"]), "--graded", str(path), "--out", str(out)]) == 0
    finally:
        world_file.chmod(0o644)
    # the grader read a sealed copy: the artifact is untouched, and no journal appeared
    assert (world_file.read_bytes(), world_file.stat().st_mtime_ns) == before
    assert sorted(p.name for p in world_file.parent.iterdir()) == siblings
    card_ = json.loads((out / "book_scorecard.json").read_text())
    assert card_["summary"]["identity_b3_f1"] == 1.0
    assert card_["summary"]["order"] == 1.0 and card_["summary"]["final"] == 1.0
    assert (out / "book_scorecard.md").exists()


# ------------------------------------------------------------- 4. book_gold


def toy_key() -> dict:
    return {
        "title": "Toy",
        "chapters": [{"n": 1, "file": "ch01.md", "words": 10}],
        "entities": {
            "mara": {"kind": "person", "aliases": ["Mara", "the keeper", "M."], "first_chapter": 1},
            "orin": {"kind": "person", "aliases": ["Orin"], "first_chapter": 1},
            "lamp": {"kind": "object", "aliases": ["brass lamp"], "first_chapter": 1},
            "cellar": {"kind": "place", "aliases": ["the cellar"], "first_chapter": 1},
            "ghost": {"kind": "person", "aliases": ["the ghost"], "first_chapter": 2},
        },
        "same_as": [["orin", "the veiled woman", 8], ["ghost", "the cold", 3]],
        "not_same": [["mara", "orin", "different people"]],
        "locations": [
            {"entity": "lamp", "in": "cellar", "from_chapter": 1, "to_chapter": 3, "evidence": "e"},
            {"entity": "lamp", "in": "cellar", "from_chapter": 5, "to_chapter": None, "evidence": "e"}],
        "holdings": [{"entity": "lamp", "held_by": "orin", "from_chapter": 3, "to_chapter": 5,
                      "evidence": "e"}],
        "containers": [{"container": "cellar", "contents": ["lamp", "ghost"], "revealed_chapter": 3,
                        "evidence": "e"}],
        "knowledge": [{"who": "mara"}], "false_beliefs": [], "corrections": [{"x": 1}, {"y": 2}],
        "do_not_grade": [],
    }


def verdict_file(key_bytes: bytes, reader: str, key: dict | None = None, **overrides) -> dict:
    key = key or json.loads(key_bytes)
    ok = {"verdict": "ok", "note": ""}
    doc = {
        "key_sha256": bg.sha256_bytes(key_bytes), "reader": reader,
        "entities": {k: {**ok, "bad_aliases": []} for k in key["entities"]},
        "same_as": [{"i": i, **ok} for i in range(len(key["same_as"]))],
        "not_same": [{"i": i, **ok} for i in range(len(key["not_same"]))],
        "locations": [{"i": i, **ok} for i in range(len(key["locations"]))],
        "holdings": [{"i": i, **ok} for i in range(len(key["holdings"]))],
        "containers": [{"i": i, **ok} for i in range(len(key["containers"]))],
        "knowledge": [{"i": 0, **ok}], "false_beliefs": [],
        "corrections": [{"i": 0, **ok}, {"i": 1, **ok}],
        "missing": [], "text_contradictions": [],
    }
    doc.update(overrides)
    return doc


def test_book_gold_drops_what_a_reader_marked_wrong_and_lists_it():
    key = toy_key()
    kb = json.dumps(key).encode()
    a = verdict_file(kb, "A")
    b = verdict_file(kb, "B")
    b["locations"][1] = {"i": 1, "verdict": "wrong", "note": "the lamp is upstairs by then"}
    b["not_same"][0] = {"i": 0, "verdict": "unclear", "note": "cannot settle"}
    a["same_as"][1] = {"i": 1, "verdict": "wrong", "note": "A: no such reveal"}
    gold = bg.build_gold(kb, [b, a])                  # argument order must not matter
    assert gold["readers"] == ["A", "B"] and gold["key_sha256"] == bg.sha256_bytes(kb)
    assert [m["id"] for m in gold["moves"]["lamp"]] == ["locations[0]", "holdings[0]"]
    assert gold["not_same"] == [] and [s["id"] for s in gold["same_as"]] == ["same_as[0]"]
    dropped = {d["id"]: d for d in gold["dropped"]}
    assert dropped["locations[1]"]["verdicts"] == {"A": "ok", "B": "wrong"}
    assert dropped["locations[1]"]["notes"]["B"] == "the lamp is upstairs by then"
    assert dropped["not_same[0]"]["verdicts"] == {"A": "ok", "B": "unclear"}
    assert dropped["same_as[1]"]["notes"] == {"A": "A: no such reveal", "B": ""}
    assert [d["id"] for d in gold["dropped"]] == sorted(dropped)
    assert gold["ungraded_counts"] == {"knowledge": 1, "false_beliefs": 0, "corrections": 2}
    assert gold["containers"] == [{"id": "containers[0]", "container": "cellar",
                                   "contents": ["lamp", "ghost"]}]


def test_book_gold_drops_a_bad_alias_from_its_entity():
    key = toy_key()
    kb = json.dumps(key).encode()
    a = verdict_file(kb, "A")
    b = verdict_file(kb, "B")
    a["entities"]["mara"]["bad_aliases"] = ["M."]
    b["entities"]["mara"]["bad_aliases"] = ["The Keeper", "not an alias"]
    gold = bg.build_gold(kb, [a, b])
    assert gold["entities"]["mara"]["aliases"] == ["Mara"]
    assert gold["dropped_aliases"] == [{"entity": "mara", "alias": "M.", "by": ["A"]},
                                       {"entity": "mara", "alias": "the keeper", "by": ["B"]}]


def test_an_entity_one_reader_rejects_takes_its_items_with_it():
    key = toy_key()
    kb = json.dumps(key).encode()
    a = verdict_file(kb, "A")
    b = verdict_file(kb, "B")
    b["entities"]["ghost"] = {"verdict": "wrong", "note": "never appears", "bad_aliases": []}
    gold = bg.build_gold(kb, [a, b])
    assert "ghost" not in gold["entities"]
    dropped = {d["id"]: d for d in gold["dropped"]}
    assert dropped["entities.ghost"]["verdicts"] == {"A": "ok", "B": "wrong"}
    assert dropped["same_as[1]"]["verdicts"] == {"entity": "dropped"}
    assert gold["containers"][0]["contents"] == ["lamp"]
    assert gold["dropped_contents"] == [{"id": "containers[0]", "entity": "ghost"}]
    # an item that refers to a dropped entity is dropped too
    b["entities"]["cellar"] = {"verdict": "unclear", "note": "", "bad_aliases": []}
    gold = bg.build_gold(kb, [a, b])
    assert {d["id"] for d in gold["dropped"]} >= {"locations[0]", "locations[1]", "containers[0]"}
    assert [m["id"] for m in gold["moves"]["lamp"]] == ["holdings[0]"]    # the one not touching it


def test_a_readers_fields_only_rejudgement_stands_in_for_the_entity_verdict():
    # r2.2: an entity is graded on kind and aliases; a first_chapter objection
    # re-judged on those fields alone does not drop it
    key = toy_key()
    kb = json.dumps(key).encode()
    a = verdict_file(kb, "A")
    b = verdict_file(kb, "B")
    b["entities"]["ghost"] = {"verdict": "wrong", "note": "first_chapter is 1", "bad_aliases": []}
    b["entities_fields"] = {"ghost": {"verdict": "ok", "note": "kind and aliases check out",
                                      "bad_aliases": ["the ghost"]}}
    gold = bg.build_gold(kb, [a, b])
    assert "ghost" in gold["entities"] and gold["entities"]["ghost"]["aliases"] == []
    assert gold["dropped_aliases"] == [{"entity": "ghost", "alias": "the ghost", "by": ["B"]}]
    assert "entities.ghost" not in {d["id"] for d in gold["dropped"]}
    assert [s["id"] for s in gold["same_as"]] == ["same_as[0]", "same_as[1]"]
    # a fields-only verdict can also drop: it is the whole judgement for that entity
    b["entities"]["ghost"] = {"verdict": "ok", "note": "", "bad_aliases": []}
    b["entities_fields"] = {"ghost": {"verdict": "unclear", "note": "", "bad_aliases": []}}
    assert "ghost" not in bg.build_gold(kb, [a, b])["entities"]


def test_entities_fields_for_an_unknown_entity_or_without_a_verdict_is_refused():
    key = toy_key()
    kb = json.dumps(key).encode()
    a = verdict_file(kb, "A")
    for bad in ({"nobody": {"verdict": "ok"}}, {"ghost": {"note": "x"}}):
        b = verdict_file(kb, "B", entities_fields=bad)
        with pytest.raises(bg.VerdictError):
            bg.build_gold(kb, [a, b])


def test_book_gold_is_deterministic(tmp_path):
    key = toy_key()
    kb = json.dumps(key).encode()
    a, b = verdict_file(kb, "A"), verdict_file(kb, "B")
    b["entities"]["mara"]["bad_aliases"] = ["M."]
    b["holdings"][0] = {"i": 0, "verdict": "wrong", "note": "n"}
    first = bg.gold_json(bg.build_gold(kb, [a, b]))
    assert bg.gold_json(bg.build_gold(kb, [b, copy.deepcopy(a)])) == first
    # the CLI writes the same bytes
    (tmp_path / "key.json").write_bytes(kb)
    for name, doc in (("a.json", a), ("b.json", b)):
        (tmp_path / name).write_text(json.dumps(doc))
    assert bg.main(["--key", str(tmp_path / "key.json"), "--verdicts", str(tmp_path / "b.json"),
                    str(tmp_path / "a.json"), "--out", str(tmp_path / "graded.json"),
                    "--dropped-md", str(tmp_path / "dropped.md")]) == 0
    assert (tmp_path / "graded.json").read_text() == first
    assert "holdings[0]" in (tmp_path / "dropped.md").read_text()


def test_book_gold_output_feeds_the_grader(tmp_path):
    key = toy_key()
    kb = json.dumps(key).encode()
    gold = bg.build_gold(kb, [verdict_file(kb, "A"), verdict_file(kb, "B")])
    cards = {"person:mara": card("person", ["Mara"], ["the keeper", "m."]),
             "person:orin": card("person", ["Orin"], ["the veiled woman"]),
             "person:ghost": card("person", ["the ghost"], ["the cold"]),
             "obj:lamp": card("object", ["Brass Lamp"]), "place:cellar": card("room", ["The Cellar"])}
    rows = [at("obj:lamp", "in", "place:cellar", 1.0), at("obj:lamp", "held_by", "person:orin", 3.0),
            at("obj:lamp", "in", "place:cellar", 5.0), at("person:ghost", "in", "place:cellar", 2.0)]
    result = grade_world(tmp_path, cards, rows, graded=gold)
    assert result["summary"]["order"] == 1.0 and result["summary"]["final"] == 1.0
    assert result["summary"]["containers"] == 1.0


def test_a_verdict_file_for_another_key_is_refused():
    key = toy_key()
    kb = json.dumps(key).encode()
    good = verdict_file(kb, "A")
    stale = verdict_file(kb + b" ", "B")                      # the hash of a different key
    with pytest.raises(bg.VerdictError, match="key_sha256"):
        bg.build_gold(kb, [good, stale])


def test_a_verdict_file_that_misses_or_repeats_an_item_is_refused():
    key = toy_key()
    kb = json.dumps(key).encode()
    a = verdict_file(kb, "A")
    missing = verdict_file(kb, "B")
    missing["locations"] = missing["locations"][:1]
    with pytest.raises(bg.VerdictError, match="locations"):
        bg.build_gold(kb, [a, missing])
    twice = verdict_file(kb, "B")
    twice["holdings"] = twice["holdings"] * 2
    with pytest.raises(bg.VerdictError, match="holdings"):
        bg.build_gold(kb, [a, twice])
    no_entity = verdict_file(kb, "B")
    del no_entity["entities"]["lamp"]
    with pytest.raises(bg.VerdictError, match="entities"):
        bg.build_gold(kb, [a, no_entity])
    bad = verdict_file(kb, "B")
    bad["same_as"][0]["verdict"] = "maybe"
    with pytest.raises(bg.VerdictError, match="verdict"):
        bg.build_gold(kb, [a, bad])
    with pytest.raises(bg.VerdictError, match="share the label"):
        bg.build_gold(kb, [a, verdict_file(kb, "A")])


def test_a_key_that_names_an_unknown_entity_is_refused():
    key = toy_key()
    key["locations"][0]["in"] = "nowhere"
    kb = json.dumps(key).encode()
    with pytest.raises(bg.VerdictError, match="locations\\[0\\]"):
        bg.build_gold(kb, [verdict_file(kb, "A", toy_key()), verdict_file(kb, "B", toy_key())])
