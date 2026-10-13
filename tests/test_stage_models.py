"""STAGE-MODELS-V1: a model and an effort per build stage, and grading a partial
book. Every test is the spec's Tests section (the number in each name) or a
detail it fixes. No model is called: ``subprocess.run`` is patched for the shim,
and the grader reads hand-built worlds."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
HARNESS = ROOT / "evals" / "harness"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).parent))

import book_gold as bg  # noqa: E402
import grade_book as gb  # noqa: E402
import merge_gate as mg  # noqa: E402
import model_shim  # noqa: E402
import profile_build as pb  # noqa: E402
import run_book as rb  # noqa: E402
import usage_ledger  # noqa: E402
from patternbuffer.testing import rule_classifier_fallback  # noqa: E402

import test_bare_call as tbc  # noqa: E402
import test_book_run as tb  # noqa: E402
import test_grade_leaks as tl  # noqa: E402

_real_sleep = time.sleep
R27_DIR = ROOT / "evals" / "books" / "the-weather-that-would-not-leave"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.delenv("PB_SHIM_LEGACY", raising=False)
    monkeypatch.delenv(model_shim.STAGE_MODELS_ENV, raising=False)
    monkeypatch.delenv(rb.USAGE_ENV, raising=False)
    monkeypatch.setenv("PB_EVAL_USAGE_LOG", str(tmp_path / "u.jsonl"))
    monkeypatch.setattr(model_shim.time, "sleep", lambda s: None)
    monkeypatch.setattr(model_shim, "_map_cache", None)
    usage_ledger.reset()
    yield
    usage_ledger.reset()


def write_map(tmp_path: Path, content, name="stages.json") -> Path:
    path = tmp_path / name
    path.write_text(content if isinstance(content, str) else json.dumps(content))
    return path


def use_map(monkeypatch, tmp_path, content, name="stages.json") -> Path:
    path = write_map(tmp_path, content, name)
    monkeypatch.setenv(model_shim.STAGE_MODELS_ENV, str(path))
    return path


def argv_model_effort(argv: list[str]) -> tuple[str, str | None]:
    model = argv[argv.index("--model") + 1]
    return model, (argv[argv.index("--effort") + 1] if "--effort" in argv else None)


MAP = {
    "default": {"model": "m-default", "effort": None},
    "pass0": {"model": "m-p0", "effort": "low"},
    "pass1": {"model": "m-p1", "effort": None},
    "escape_repair": {"model": "m-esc", "effort": "max"},
    "commit": {"model": "m-commit", "effort": "medium"},
    "audit": {"model": "m-audit", "effort": "high"},
}
EXPECTED = {k: (v["model"], v["effort"]) for k, v in MAP.items()}


# 1 ------------------------------------------------------------- no map, no change


@pytest.mark.parametrize("stage", [None, "default", "pass0", "pass1", "escape_repair", "commit",
                                   "audit", "not-a-stage"])
def test_1_without_a_map_the_argv_is_exactly_bare_call_v1_under_every_label(monkeypatch, stage):
    fake = tbc._patch(monkeypatch, tbc.Fake([tbc._env_line()]))
    with usage_ledger.label(stage=stage, unit="u"):
        assert model_shim.claude_model("p", {}) == {"ok": True}
    (c,) = fake.calls
    assert c["argv"] == tbc.BARE[:3] + [model_shim.MODEL] + tbc.BARE[4:]
    assert "--effort" not in c["argv"]
    assert c["argv"] == model_shim.bare_argv(model_shim.MODEL)
    assert tbc._lines  # (helper imported)


def test_1_an_empty_variable_is_no_map(monkeypatch):
    monkeypatch.setenv(model_shim.STAGE_MODELS_ENV, "")
    fake = tbc._patch(monkeypatch, tbc.Fake([tbc._env_line()]))
    model_shim.claude_model("p", {})
    assert fake.calls[0]["argv"] == model_shim.bare_argv(model_shim.MODEL)
    assert model_shim.stage_map_receipt() is None


def test_1_bare_argv_appends_effort_only_when_set():
    assert model_shim.bare_argv("M") == tbc.BARE
    assert model_shim.bare_argv("M", None) == tbc.BARE
    assert model_shim.bare_argv("M", "low") == tbc.BARE + ["--effort", "low"]
    assert model_shim.bare_argv("M", "xhigh")[:-2] == tbc.BARE


# 2 -------------------------------------------------------------------- routing


def test_2_a_call_inside_a_stage_label_uses_that_stages_model_and_effort(monkeypatch, tmp_path):
    use_map(monkeypatch, tmp_path, MAP)
    fake = tbc._patch(monkeypatch, tbc.Fake([tbc._env_line()]))
    for stage in ("pass0", "pass1", "escape_repair", "commit", "audit"):
        with usage_ledger.label(stage=stage, unit="u", attempt=1):
            model_shim.claude_model("p", {})
    got = [argv_model_effort(c["argv"]) for c in fake.calls]
    assert got == [EXPECTED[s] for s in ("pass0", "pass1", "escape_repair", "commit", "audit")]
    # the argv ends with --effort <effort> exactly when an effort is set
    for c, (_, effort) in zip(fake.calls, got):
        assert (c["argv"][-2:] == ["--effort", effort]) if effort else ("--effort" not in c["argv"])
    assert fake.calls[0]["argv"] == model_shim.bare_argv("m-p0", "low")
    assert fake.calls[1]["argv"] == model_shim.bare_argv("m-p1")


def test_2_unlisted_stages_and_unlabelled_calls_use_default(monkeypatch, tmp_path):
    use_map(monkeypatch, tmp_path, {"default": {"model": "m-d", "effort": "medium"},
                                    "pass1": {"model": "m-p1", "effort": None}})
    fake = tbc._patch(monkeypatch, tbc.Fake([tbc._env_line()]))
    model_shim.claude_model("p", {})                       # unlabelled
    with usage_ledger.label(stage="audit"):                # unlisted
        model_shim.claude_model("p", {})
    with usage_ledger.label(stage="pass1"):
        model_shim.claude_model("p", {})
    assert [argv_model_effort(c["argv"]) for c in fake.calls] == [
        ("m-d", "medium"), ("m-d", "medium"), ("m-p1", None)]


def test_2_a_missing_default_is_todays_call_and_empty_map_changes_nothing(monkeypatch, tmp_path):
    use_map(monkeypatch, tmp_path, {"audit": {"model": "m-a", "effort": "low"}})
    fake = tbc._patch(monkeypatch, tbc.Fake([tbc._env_line()]))
    model_shim.claude_model("p", {})
    with usage_ledger.label(stage="pass0"):
        model_shim.claude_model("p", {})
    with usage_ledger.label(stage="audit"):
        model_shim.claude_model("p", {})
    assert [argv_model_effort(c["argv"]) for c in fake.calls] == [
        (model_shim.MODEL, None), (model_shim.MODEL, None), ("m-a", "low")]
    # an empty map is valid and changes nothing, under any label
    use_map(monkeypatch, tmp_path, {}, "empty.json")
    fake2 = tbc._patch(monkeypatch, tbc.Fake([tbc._env_line()]))
    for stage in (None, "pass0", "commit"):
        with usage_ledger.label(stage=stage):
            model_shim.claude_model("p", {})
    assert all(c["argv"] == model_shim.bare_argv(model_shim.MODEL) for c in fake2.calls)


def test_2_every_attempt_of_a_call_keeps_its_stage_model_and_effort(monkeypatch, tmp_path):
    use_map(monkeypatch, tmp_path, MAP)
    fake = tbc._patch(monkeypatch, tbc.Fake([tbc._env_line("nope"), tbc._env_line("no"),
                                             tbc._env_line()]))
    with usage_ledger.label(stage="pass0"):
        assert model_shim.claude_model("p", {}) == {"ok": True}
    assert len(fake.calls) == 3
    assert {tuple(c["argv"]) for c in fake.calls} == {tuple(model_shim.bare_argv("m-p0", "low"))}


# 2a ------------------------------------------------------- routing across workers


class SubprocessFake:
    """A patched ``subprocess.run`` that plays the whole toy build: it reads the prompt
    and schema out of stdin, answers as a model would, and records each call's argv, the
    stage the call belongs to and the thread it ran on."""

    def __init__(self, bad_first: tuple[int, ...] = (2,), sleep: float = 0.03) -> None:
        self.bad_first, self.sleep = bad_first, sleep
        self.calls: list[dict] = []
        self.attempts: dict[int, int] = {}
        self._lock = threading.Lock()

    def __call__(self, argv, **kw):
        full = kw["input"]
        prompt = full.split("\n\nRespond with ONLY")[0]
        schema, _ = json.JSONDecoder().raw_decode(full.split("this JSON Schema:\n")[1])
        served = None
        if "PASSAGE (chunk" in prompt:
            kind, stage = "pass1", "pass1"
            served = int(prompt.split("PASSAGE (chunk ")[1].split(")")[0])
        elif "WORLD REGISTRY" in prompt:
            kind, stage = "pass0", "pass0"
        elif "ops" in schema.get("properties", {}):
            kind, stage = "audit", "audit"
        elif schema.get("title") == mg.TASK_MERGE_GATE:
            kind, stage = "gate", "commit"
        else:
            kind, stage = "classify", "commit"
        with self._lock:
            n = self.attempts[served] = self.attempts.get(served, 0) + 1 if kind == "pass1" else 0
            self.calls.append({"argv": list(argv), "kind": kind, "stage": stage,
                               "thread": threading.get_ident(), "attempt": n})
        _real_sleep(self.sleep)
        if kind == "pass1":
            bad = served in self.bad_first and n == 1
            out = {"lines": ["not|a"] if bad else tb.PASS1_LINES[served]}
        elif kind == "pass0":
            out = {"lines": tb.PASS0_LINES}
        elif kind == "audit":
            out = {"ops": []}
        elif kind == "gate":
            out = {"verdicts": [{"pair_id": p["pair_id"], "verdict": "unsure"}
                                for p in mg.batch_request(schema)["pairs"]]}
        else:
            out = rule_classifier_fallback()(prompt, schema)
        env = {"type": "result", "is_error": False, "result": json.dumps(out), "num_turns": 1,
               "total_cost_usd": 0.01, "usage": {"input_tokens": 100, "output_tokens": 10}}
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(env), stderr="")


@pytest.fixture
def toy_build(monkeypatch, tmp_path):
    """The toy book built through the real shim and the real pipeline, with a stage map, on
    the parallel pass-0 and pass-1 pools (4 workers), one pass-1 retry and the commit's
    classification wrapped by ``ObjectiveModel``."""
    path = use_map(monkeypatch, tmp_path, MAP)
    fake = SubprocessFake()
    monkeypatch.setattr(model_shim.subprocess, "run", fake)
    book = tb.write_book(tmp_path / "book")
    out = tmp_path / "out"
    meta = rb.run_book(book, out, model_shim.claude_model, pass0="parallel", merge_gate=True)
    return {"fake": fake, "out": out, "meta": meta, "map_path": path,
            "usage": [json.loads(x) for x in (out / "usage.jsonl").read_text().splitlines()]}


def test_2a_every_recorded_call_carries_its_own_stages_model_and_effort(toy_build):
    fake = toy_build["fake"]
    stages = {c["stage"] for c in fake.calls}
    assert {"pass0", "pass1", "commit", "audit"} <= stages
    for c in fake.calls:
        assert argv_model_effort(c["argv"]) == EXPECTED[c["stage"]], c["kind"]
    # the pass-1 retry (chunk 2's first parse is bad) ran on pass1's model too
    assert [c["attempt"] for c in fake.calls if c["kind"] == "pass1"].count(2) == 1
    # and the pools really ran on several threads
    for stage in ("pass0", "pass1"):
        assert len({c["thread"] for c in fake.calls if c["stage"] == stage}) >= 2, stage
    # the receipt agrees with the argv: each usage line's label picks the same entry
    usage = toy_build["usage"]
    assert len(usage) == len(fake.calls)
    for line in usage:
        assert (line["model"], line["effort"]) == EXPECTED[line["stage"]], line["unit"]
    assert any(line["unit"].startswith("classify:") and line["stage"] == "commit" for line in usage)


# 3 ------------------------------------------------------------ refusals at load


BAD_MAPS = {
    "unknown stage": ({"pass2": {"model": "m", "effort": None}}, "unknown stage 'pass2'"),
    "bad effort": ({"pass0": {"model": "m", "effort": "turbo"}}, "effort 'turbo'"),
    "empty model": ({"pass0": {"model": "", "effort": None}}, "model is empty"),
    "blank model": ({"pass0": {"model": "  ", "effort": None}}, "model is empty"),
    "non-object map": (["pass0"], "must be a JSON object"),
    "string map": ('"x"', "must be a JSON object"),
    "invalid json": ("{not json", "not valid JSON"),
    "model not a string": ({"pass0": {"model": 5, "effort": None}}, "model must be a string"),
    "effort not a string": ({"pass0": {"model": "m", "effort": 3}}, "effort must be a string or null"),
    "entry not an object": ({"pass0": "m"}, "must be an object"),
    "unknown field": ({"pass0": {"model": "m", "efort": "low"}}, "unknown field"),
    "missing model": ({"pass0": {"effort": "low"}}, "model must be a string"),
    "flag-like model": ({"pass0": {"model": "--max-turns", "effort": None}}, "not a model name"),
}


@pytest.mark.parametrize("name", sorted(BAD_MAPS))
def test_3_a_refused_map_stops_the_run_before_any_call(monkeypatch, tmp_path, name):
    content, reason = BAD_MAPS[name]
    use_map(monkeypatch, tmp_path, content)
    fake = tbc._patch(monkeypatch, tbc.Fake([tbc._env_line()]))
    with pytest.raises(model_shim.StageMapError, match=reason):
        model_shim.claude_model("p", {})
    assert fake.calls == []
    # the runner refuses too: before any directory, call or ledger line
    book = tb.write_book(tmp_path / "book")
    out = tmp_path / "out"
    with pytest.raises(rb.BookRunAborted, match="stage map refused"):
        rb.run_book(book, out, lambda p, s: pytest.fail("a model call was made"))
    assert not out.exists()
    assert fake.calls == []
    with pytest.raises(SystemExit, match="ABORT: stage map refused"):
        rb.main(["--book", str(book), "--out", str(out)], model=lambda p, s: pytest.fail("called"))


def test_3_an_unreadable_file_is_refused_naming_the_path(monkeypatch, tmp_path):
    monkeypatch.setenv(model_shim.STAGE_MODELS_ENV, str(tmp_path / "missing.json"))
    fake = tbc._patch(monkeypatch, tbc.Fake([tbc._env_line()]))
    with pytest.raises(model_shim.StageMapError, match="unreadable"):
        model_shim.claude_model("p", {})
    assert fake.calls == []


def test_3_every_valid_effort_is_accepted():
    for effort in (None, "low", "medium", "high", "xhigh", "max"):
        m = model_shim.parse_stage_map(json.dumps({"pass0": {"model": "m", "effort": effort}}).encode())
        assert m.entries["pass0"] == ("m", effort)
    # effort left out is null
    assert model_shim.parse_stage_map(b'{"audit": {"model": "m"}}').entries["audit"] == ("m", None)


# 4 -------------------------------------------------------------------- receipts


def test_4_call_lines_carry_effort_and_meta_holds_the_map_and_its_sha(toy_build):
    raw = toy_build["map_path"].read_bytes()
    on_disk = json.loads((toy_build["out"] / "meta.json").read_text())
    assert on_disk["stage_models"] == {"applied": True, "sha256": hashlib.sha256(raw).hexdigest(),
                                       "map": MAP}
    assert toy_build["meta"]["stage_models"] == on_disk["stage_models"]
    assert all("effort" in line for line in toy_build["usage"])
    assert {line["effort"] for line in toy_build["usage"]} == {None, "low", "medium", "high"}


def test_4_a_timeout_line_records_the_effort_too(monkeypatch, tmp_path):
    use_map(monkeypatch, tmp_path, MAP)

    def boom(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 1)
    monkeypatch.setattr(model_shim.subprocess, "run", boom)
    with usage_ledger.label(stage="audit"), pytest.raises(model_shim.ModelShimError):
        model_shim.claude_model("p", {})
    lines = [json.loads(x) for x in (tmp_path / "u.jsonl").read_text().splitlines()]
    assert [(l["outcome"], l["model"], l["effort"]) for l in lines] == [("timeout", "m-audit", "high")] * 3


def test_4_without_a_map_meta_has_no_stage_models_and_effort_is_null(tmp_path, monkeypatch):
    fake = SubprocessFake(bad_first=())
    monkeypatch.setattr(model_shim.subprocess, "run", fake)
    out = tmp_path / "out"
    meta = rb.run_book(tb.write_book(tmp_path / "book"), out, model_shim.claude_model)
    assert "stage_models" not in meta and "stage_models" not in json.loads((out / "meta.json").read_text())
    usage = [json.loads(x) for x in (out / "usage.jsonl").read_text().splitlines()]
    assert usage and {l["effort"] for l in usage} == {None}
    assert {argv_model_effort(c["argv"]) for c in fake.calls} == {(model_shim.MODEL, None)}


def _call(stage, model, effort, out_tok=100, latency=2.0, **kw):
    return {"t": 1.0, "started": 1.0, "latency_s": latency, "provider": "claude", "model": model,
            "stage": stage, "unit": "u", "attempt": 1, "outcome": "ok", "input_tokens": 10,
            "output_tokens": out_tok, "cache_read_tokens": 0, "cache_write_tokens": 0,
            "cost_usd": 0.01, "usage_reported": True, "prompt_chars": 1, "response_chars": 1,
            "num_turns": 1, "cli_duration_ms": 1.0, "api_duration_ms": 1.0, "effort": effort, **kw}


def test_4_the_profile_groups_a_stage_by_model_and_effort_when_it_mixes_them(tmp_path):
    lines = [_call("pass1", "m-a", None), _call("pass1", "m-a", None), _call("pass1", "m-b", "low"),
             _call("pass0", "m-a", "low"), _call("pass0", "m-a", "low"),
             _call("commit", "m-a", None)]
    old = _call("commit", "m-a", None)
    del old["effort"]                     # a line from before STAGE-MODELS-V1: the CLI default
    lines.append(old)
    (tmp_path / "usage.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    profile = pb.build_profile(tmp_path)
    rows = profile["by_model_effort"]
    # only pass1 mixed; commit's old line and new line are the same (model, null)
    assert [(r["stage"], r["model"], r["effort"], r["calls"]) for r in rows] == [
        ("pass1", "m-a", None, 2), ("pass1", "m-b", "low", 1)]
    assert rows[0]["output_tokens"] == 200 and rows[1]["latency_sum_s"] == 2.0
    md = pb.render_md(profile)
    assert "Stages that mixed models or efforts" in md and "| pass1 | m-b | low | 1 |" in md
    assert "| pass0 | m-a" not in md.split("Stages that mixed")[1].split("## Turns")[0]
    # a single (model, effort) per stage adds no section
    (tmp_path / "usage.jsonl").write_text("\n".join(json.dumps(l) for l in lines[3:5]) + "\n")
    quiet = pb.build_profile(tmp_path)
    assert quiet["by_model_effort"] == []
    assert "mixed models" not in pb.render_md(quiet)


# 5 -------------------------------------------------------------------- legacy


def test_5_legacy_ignores_the_map_even_a_refused_one(monkeypatch, tmp_path):
    monkeypatch.setenv("PB_SHIM_LEGACY", "1")
    for content in (MAP, {"pass2": 1}):
        use_map(monkeypatch, tmp_path, content)
        fake = tbc._patch(monkeypatch, tbc.Fake([tbc._env_line()]))
        with usage_ledger.label(stage="pass0"):
            assert model_shim.claude_model("p", {}) == {"ok": True}
        (c,) = fake.calls
        assert c["argv"] == ["claude", "-p", "--model", model_shim.MODEL, "--max-turns", "8",
                             "--output-format", "json"]
        assert "cwd" not in c["kw"] and "env" not in c["kw"]
    lines = [json.loads(x) for x in (tmp_path / "u.jsonl").read_text().splitlines()]
    assert {(l["model"], l["effort"]) for l in lines} == {(model_shim.MODEL, None)}
    receipt = model_shim.stage_map_receipt()
    assert receipt["applied"] is False and "map" not in receipt


# 6 ------------------------------------------------------- grading a partial book


def key_doc() -> dict:
    """A hand-built key over chapters 1-4: one entry of every kind on each side of a
    window at chapter 2."""
    def ent(kind, aliases, first, afc=None):
        e = {"kind": kind, "aliases": aliases, "first_chapter": first}
        if afc:
            e["alias_first_chapter"] = afc
        return e

    def fact(entity, attribute, value):
        return {"entity": entity, "attribute": attribute,
                "value": {"entity": value[1:]} if value.startswith("@") else {"literal": value}}

    return {
        "title": "Window", "chapters": [{"n": n, "file": f"ch{n:02d}.md", "words": 10} for n in (1, 2, 3, 4)],
        "entities": {
            "mara": ent("person", ["Mara", "the hooded visitor"], 1, {"Mara": 1, "the hooded visitor": 2}),
            "oruva": ent("person", ["Oruva", "the third ear"], 1, {"Oruva": 1, "the third ear": 3}),
            "vael": ent("person", ["Vael"], 3),
            "lamp": ent("object", ["brass lamp"], 1), "coin": ent("object", ["coin"], 1),
            "ring": ent("object", ["ring"], 1), "box": ent("object", ["box"], 1),
            "chest": ent("object", ["chest"], 1),
            "twin_a": ent("object", ["silver key"], 1), "twin_b": ent("object", ["iron key"], 1),
            "cellar": ent("place", ["cellar"], 1), "dock": ent("place", ["dock"], 1),
            "attic": ent("place", ["attic"], 1),
        },
        "same_as": [["mara", "the hooded visitor", 2], ["oruva", "the third ear", 3]],
        "not_same": [["oruva", "vael", "different"], ["twin_a", "twin_b", "two keys"]],
        "locations": [
            {"entity": "lamp", "in": "cellar", "from_chapter": 1, "to_chapter": None},
            {"entity": "coin", "in": "dock", "from_chapter": 1, "to_chapter": 4},
            {"entity": "ring", "in": "attic", "from_chapter": 1, "to_chapter": 2},
            {"entity": "twin_a", "in": "dock", "from_chapter": 1, "to_chapter": None},
            {"entity": "twin_b", "in": "cellar", "from_chapter": 1, "to_chapter": None},
            {"entity": "vael", "in": "attic", "from_chapter": 3, "to_chapter": None}],
        "holdings": [{"entity": "coin", "held_by": "oruva", "from_chapter": 3, "to_chapter": None}],
        "containers": [{"container": "box", "contents": ["ring"], "revealed_chapter": 2},
                       {"container": "chest", "contents": ["coin"], "revealed_chapter": 3}],
        "knowledge": [
            {"who": "oruva", "learns": "x", "chapter": 3, "as_fact": fact("mara", "status", "alive")},
            {"who": "oruva", "learns": "y", "chapter": 2, "as_fact": fact("coin", "color", "tin")}],
        "false_beliefs": [
            {"who": "oruva", "believes": "z", "from_chapter": 1, "corrected_chapter": 3,
             "as_fact": fact("mara", "status", "dead")},
            {"who": "vael", "believes": "w", "from_chapter": 3, "corrected_chapter": None,
             "as_fact": fact("lamp", "in", "@attic")}],
        "corrections": [
            {"claim": "c0", "stated_chapter": 1, "corrected_chapter": 3,
             "as_fact": fact("mara", "status", "dead"), "corrected_as_fact": fact("mara", "status", "alive")},
            {"claim": "c1", "stated_chapter": 1, "corrected_chapter": 2,
             "as_fact": fact("coin", "color", "gold"), "corrected_as_fact": fact("coin", "color", "tin")}],
    }


def verdicts_for(key: dict, key_bytes: bytes, reader: str) -> dict:
    ok = {"verdict": "ok", "note": ""}
    doc = {"key_sha256": bg.sha256_bytes(key_bytes), "reader": reader,
           "entities": {k: {**ok, "bad_aliases": []} for k in key["entities"]}}
    for section in bg.GRADED_SECTIONS + bg.UNGRADED_SECTIONS:
        doc[section] = [{"i": i, **ok} for i in range(len(key.get(section, [])))]
    fields: dict = {"alias_first_chapter": {
        k: {a: "ok" for a in e["alias_first_chapter"]}
        for k, e in key["entities"].items() if e.get("alias_first_chapter")}}
    for section, names in bg.FACT_FIELDS.items():
        fields[section] = {str(i): {n: "ok" for n in names if entry.get(n) is not None}
                           for i, entry in enumerate(key[section])}
    doc["fields"] = fields
    return doc


@pytest.fixture(scope="module")
def key_bytes() -> bytes:
    return json.dumps(key_doc(), indent=1).encode()


def gold(key_bytes: bytes, n: int | None = None) -> dict:
    key = json.loads(key_bytes)
    docs = [verdicts_for(key, key_bytes, "A"), verdicts_for(key, key_bytes, "B")]
    return bg.build_gold(key_bytes, docs, through_chapter=n)


def test_6_through_chapter_keeps_exactly_the_entries_the_rules_select(key_bytes):
    full, g2 = gold(key_bytes), gold(key_bytes, 2)
    assert g2["through_chapter"] == 2 and "through_chapter" not in full
    # entities: first_chapter <= 2; aliases by alias_first_chapter
    assert sorted(g2["entities"]) == sorted(set(full["entities"]) - {"vael"})
    assert g2["entities"]["mara"]["aliases"] == ["Mara", "the hooded visitor"]
    assert g2["entities"]["oruva"]["aliases"] == ["Oruva"]            # "the third ear" is chapter 3
    assert g2["alias_first_chapter"]["oruva"] == {"Oruva": 1}
    # same_as: revealed by 2; not_same: both entities by 2
    assert [r["entity"] for r in g2["same_as"]] == ["mara"]
    assert [(r["a"], r["b"]) for r in g2["not_same"]] == [("twin_a", "twin_b")]
    # locations and holdings are half-open ranges, never clipped
    moves = {k: [(m["id"], m["to"], m["from_chapter"], m["to_chapter"]) for m in v]
             for k, v in g2["moves"].items()}
    assert moves == {"lamp": [("locations[0]", "cellar", 1, None)],
                     "coin": [("locations[1]", "dock", 1, None)],           # 1..4 stays open at 2
                     "ring": [("locations[2]", "attic", 1, 2)],             # 1..2 is closed
                     "twin_a": [("locations[3]", "dock", 1, None)],
                     "twin_b": [("locations[4]", "cellar", 1, None)]}       # no vael, no holding
    # containers revealed by 2; knowledge chapter <= 2
    assert [c["container"] for c in g2["containers"]] == ["box"]
    assert [k["id"] for k in g2["knowledge"]] == ["knowledge[1]"]
    # false beliefs from <= 2, held through 2; corrections only once corrected
    assert [(b["id"], b["corrected_chapter"]) for b in g2["beliefs"]] == [("false_beliefs[0]", None)]
    assert [c["id"] for c in g2["corrections"]] == ["corrections[1]"]
    # counts follow the window
    assert g2["ungraded_counts"] == {"knowledge": 1, "false_beliefs": 1, "corrections": 1}
    assert g2["dropped"] == [] and g2["field_counts"]["corrections"] == {
        "entries": 2, "verified": 2, "dropped": 0}


def test_6_the_window_moves_with_n(key_bytes):
    g1, g3, g4 = gold(key_bytes, 1), gold(key_bytes, 3), gold(key_bytes, 4)
    assert g1["entities"]["mara"]["aliases"] == ["Mara"] and g1["same_as"] == []
    assert g1["moves"]["ring"][0]["to_chapter"] is None                    # 1..2 is still open at 1
    assert g1["containers"] == [] and g1["knowledge"] == []
    assert sorted(g3["entities"]) == sorted(gold(key_bytes)["entities"])   # vael arrives in 3
    assert [r["entity"] for r in g3["same_as"]] == ["mara", "oruva"]
    assert [(b["id"], b["corrected_chapter"]) for b in g3["beliefs"]] == [
        ("false_beliefs[0]", 3), ("false_beliefs[1]", None)]
    assert [c["id"] for c in g3["corrections"]] == ["corrections[0]", "corrections[1]"]
    assert g3["pending_corrections"] == 0
    assert [m["to_chapter"] for m in g3["moves"]["coin"]] == [None, None]  # 1..4 open at 3
    assert [m["to_chapter"] for m in g4["moves"]["coin"]] == [4, None]     # closed at 4


def test_6_a_correction_stated_in_1_and_made_in_3_is_pending_at_2(key_bytes):
    g2, g3 = gold(key_bytes, 2), gold(key_bytes, 3)
    assert g2["pending_corrections"] == 1 and g3["pending_corrections"] == 0
    assert "corrections[0]" not in {c["id"] for c in g2["corrections"]}
    assert "corrections[0]" in {c["id"] for c in g3["corrections"]}


def test_6_a_correction_stated_after_n_is_neither_pending_nor_graded():
    key = key_doc()
    key["corrections"][0]["stated_chapter"] = 3
    kb = json.dumps(key).encode()
    g2 = gold(kb, 2)
    assert g2["pending_corrections"] == 0 and [c["id"] for c in g2["corrections"]] == ["corrections[1]"]


def test_6_book_gold_refuses_a_window_it_cannot_cut(key_bytes):
    for n in (0, -1, 5, True, "2"):
        with pytest.raises(bg.VerdictError, match="not in 1..4"):
            gold(key_bytes, n)
    key = key_doc()
    del key["entities"]["lamp"]["first_chapter"]
    kb = json.dumps(key).encode()
    with pytest.raises(bg.VerdictError, match="cannot window the key"):
        gold(kb, 2)


def test_6_book_gold_without_the_flag_is_byte_identical():
    key_bytes_ = (R27_DIR / "key.json").read_bytes()
    docs = [json.loads((R27_DIR / f"verdicts_{r}.json").read_text()) for r in ("A", "B")]
    assert bg.gold_json(bg.build_gold(key_bytes_, docs)) == (R27_DIR / "graded.json").read_text()
    assert bg.gold_json(bg.build_gold(key_bytes_, docs, through_chapter=None)) == \
        (R27_DIR / "graded.json").read_text()
    # a window over every chapter selects everything the full gold has
    n = len(json.loads(key_bytes_)["chapters"])
    whole = bg.build_gold(key_bytes_, docs, through_chapter=n)
    full = json.loads((R27_DIR / "graded.json").read_text())
    assert whole.pop("through_chapter") == n and whole.pop("pending_corrections") == 0
    assert set(whole) == set(full)
    for section in full:
        assert whole[section] == full[section], section


# ---- a short build: the world holds exactly chapters 1..N


def seed_cards() -> dict:
    c = tl.card
    return {"person:mara": c("person", ["Mara"]), "person:oruva": c("person", ["Oruva"]),
            "person:vael": c("person", ["Vael"]), "obj:lamp": c("object", ["brass lamp"]),
            "obj:coin": c("object", ["coin"]), "obj:ring": c("object", ["ring"]),
            "obj:box": c("object", ["box"]), "obj:chest": c("object", ["chest"]),
            "obj:twin_a": c("object", ["silver key"]), "obj:twin_b": c("object", ["iron key"]),
            "place:cellar": c("place", ["cellar"]), "place:dock": c("place", ["dock"]),
            "place:attic": c("place", ["attic"])}


def build_world(tmp_path, name, *, chapters=2):
    """A build of exactly chapters 1..``chapters`` (2 or 3)."""
    at, lit, nm = tl.at, tl.lit, tl.name
    b = tl.Built(tmp_path, seed_cards(), name=name)
    b.chunk(1, "one", [
        at("obj:lamp", "in", "place:cellar", 1.0), at("obj:coin", "in", "place:dock", 1.0),
        at("obj:ring", "in", "place:attic", 1.0), at("obj:twin_a", "in", "place:dock", 1.0),
        at("obj:twin_b", "in", "place:cellar", 1.0), lit("obj:coin", "color", "gold", valid_from=1.0),
        lit("person:mara", "status", "dead", valid_from=1.0, valid_to=3.0, frame="knows:person:oruva")])
    b.chunk(2, "two", [
        nm("person:mara", "the hooded visitor", "alias"), at("obj:ring", "within", "obj:box", 2.0),
        lit("obj:coin", "color", "tin", valid_from=2.0),
        lit("obj:coin", "color", "tin", valid_from=2.0, frame="knows:person:oruva")])
    if chapters >= 3:
        b.chunk(3, "three", [lit("person:mara", "status", "alive", valid_from=3.0),
                             at("person:vael", "in", "place:attic", 3.0),
                             at("obj:coin", "within", "obj:chest", 3.0)])
    return b


def grade(b, graded, n=None):
    b.world.classifier.classify_all(batch_size=40)
    return gb.grade_book(b.world, b.world.registry, graded, spans=b.spans, chunk_texts=b.texts,
                         through_chapter=n)


@pytest.fixture(scope="module")
def short(tmp_path_factory, key_bytes):
    """A 2-chapter build and a 3-chapter build of the same book, with their windowed golds."""
    base = tmp_path_factory.mktemp("short")
    out = {"b2": build_world(base, "b2"), "b3": build_world(base, "b3", chapters=3),
           "g1": gold(key_bytes, 1), "g2": gold(key_bytes, 2), "g3": gold(key_bytes, 3),
           "full": gold(key_bytes)}
    yield out
    out["b2"].close()
    out["b3"].close()


def test_6_a_2_chapter_build_graded_through_2_equals_the_existing_grader_on_the_same_gold(short):
    """The flag only checks and labels: the grading is the existing grader's, unchanged."""
    b, g2 = short["b2"], short["g2"]
    flagged = grade(b, g2, 2)
    unstamped = {k: v for k, v in g2.items() if k != "through_chapter"}
    existing = grade(b, unstamped)
    added = {"through_chapter", "pending_corrections"}
    assert added <= set(flagged) and not added & set(existing)
    assert {k: v for k, v in flagged.items() if k not in added} == existing
    assert flagged["through_chapter"] == 2 and flagged["pending_corrections"] == 1
    for key in ("summary", "identity", "reveals", "look_alikes", "order", "final", "leaks", "beliefs",
                "point_of_view"):
        assert flagged[key] == existing[key]


def test_6_grading_never_calls_the_private_fold_from_the_harness(short, monkeypatch):
    """The harness reaches no private engine method. (The engine's own ``fold_key`` runs its
    fold through ``_fold_over_closure``, so the check is on who calls it.)"""
    from patternbuffer.indexes.fold import FoldMixin
    real, outsiders = FoldMixin._fold_over_closure, []

    def spy(self, *a, **k):
        caller = sys._getframe(1).f_code.co_filename
        if "/src/patternbuffer/" not in caller.replace("\\", "/"):
            outsiders.append(caller)
        return real(self, *a, **k)
    monkeypatch.setattr(FoldMixin, "_fold_over_closure", spy)
    calls = []
    real_fold_key = FoldMixin.fold_key

    def counting_fold_key(self, *a, **k):
        calls.append(1)
        return real_fold_key(self, *a, **k)
    monkeypatch.setattr(FoldMixin, "fold_key", counting_fold_key)
    grade(short["b2"], short["g2"], 2)
    assert calls and outsiders == []     # folds ran, all through the engine's own entry points
    for path in HARNESS.glob("*.py"):
        assert "_fold_over_closure" not in path.read_text(), path.name
        assert "Horizon" not in path.read_text(), path.name


def test_6_a_belief_corrected_in_chapter_3_is_held_through_chapter_2(short):
    card = grade(short["b2"], short["g2"], 2)
    item = card["beliefs"]["false_beliefs"]["items"][0]
    assert item["id"] == "false_beliefs[0]" and item["corrected_chapter"] is None
    assert item["status"] == "measured" and item["held_by_believer"] == 1 and item["false_in_canon"] == 0
    assert card["beliefs"]["false_beliefs"]["entries"] == 1       # vael's belief starts in chapter 3


def test_6_pending_corrections_are_outside_items_and_denominators(short):
    c2 = grade(short["b2"], short["g2"], 2)
    co = c2["beliefs"]["corrections"]
    assert [i["id"] for i in co["items"]] == ["corrections[1]"]
    assert co["entries"] == 1 and co["ends_correct_entries"] == 1 and co["ends_correct"] == 1
    assert c2["pending_corrections"] == 1
    # at N = 3 (a 3-chapter build) the correction's checks are made
    c3 = grade(short["b3"], short["g3"], 3)
    co3 = c3["beliefs"]["corrections"]
    assert [i["id"] for i in co3["items"]] == ["corrections[0]", "corrections[1]"]
    assert co3["entries"] == 2 and co3["ends_correct_entries"] == 2 and c3["pending_corrections"] == 0
    assert co3["items"][0]["ends_correct"] == 1 and co3["items"][0]["unmatched"] == []
    assert [i["corrected_chapter"] for i in c3["beliefs"]["false_beliefs"]["items"]] == [3, None]


def test_6_open_ranges_count_for_final_and_a_range_closed_by_n_does_not(short):
    card = grade(short["b2"], short["g2"], 2)
    # lamp 1..null and coin 1..4 are both open at 2; ring 1..2 is closed
    assert sorted(card["final"]["objects"]) == ["coin", "lamp", "twin_a", "twin_b"]
    assert all(o["ok"] for o in card["final"]["objects"].values()) and card["final"]["score"] == 1.0
    assert "ring" in card["order"]["objects"] and "ring" not in card["final"]["objects"]


def test_6_the_report_states_the_window_on_its_first_line(short):
    card = grade(short["b2"], short["g2"], 2)
    md = gb.scorecard_md(card, "Book scorecard (run)")
    assert md.splitlines()[0] == "# Book scorecard (run) [through_chapter: 2]"
    assert "1 correction(s) pending" in md
    assert gb.scorecard_md(grade(short["b2"], short["full"]), "Book scorecard (run)").splitlines()[0] \
        == "# Book scorecard (run)"


def test_6_the_refusals(short):
    b, g1, g2, g3, full = short["b2"], short["g1"], short["g2"], short["g3"], short["full"]
    with pytest.raises(gb.WindowRefused, match="not windowed"):                # flag, no stamp
        grade(b, full, 2)
    with pytest.raises(gb.WindowRefused, match="is windowed"):                 # stamp, no flag
        grade(b, g2)
    with pytest.raises(gb.WindowRefused, match="not 3"):                       # another N
        grade(b, g2, 3)
    with pytest.raises(gb.WindowRefused, match="outside the book's chapters"):  # N = 0
        grade(b, {**g2, "through_chapter": 0}, 0)
    with pytest.raises(gb.WindowRefused, match="not the last chapter the run built \\(2\\)"):
        grade(b, g1, 1)                                                        # N below the build
    with pytest.raises(gb.WindowRefused, match="not the last chapter the run built \\(2\\)"):
        grade(b, g3, 3)                                                        # N above the build
    with pytest.raises(gb.WindowRefused, match="chunk_spans"):                 # no spans
        gb.grade_book(b.world, b.world.registry, g2, spans=None, through_chapter=2)
    with pytest.raises(gb.WindowRefused, match="not a chapter number"):
        gb.check_window(g2, True, b.spans)
    with pytest.raises(gb.WindowRefused, match="outside the book's chapters"):  # past the book
        gb.check_window({**g2, "through_chapter": 6}, 6, b.spans, chapters=4)
    with pytest.raises(gb.WindowRefused, match="not the run's chapter count"):  # meta says 4
        gb.check_window(g2, 2, b.spans, chapters=4)
    gb.check_window(g2, 2, b.spans, chapters=2)                                 # and a good one passes


def test_6_without_the_flag_the_output_is_byte_identical_to_the_current_grader(tmp_path):
    cards = tl.legacy_cards(tmp_path, gb.grade_book)
    assert {k: tl.legacy_digest(c) for k, c in cards.items()} == tl.LEGACY_DIGESTS
    for card in cards.values():
        assert not {"through_chapter", "asserted_as_of", "pending_corrections"} & set(card)
    (tmp_path / "again").mkdir()
    explicit = tl.legacy_cards(tmp_path / "again",
                               lambda w, reg, g: gb.grade_book(w, reg, g, through_chapter=None))
    assert json.dumps(explicit, sort_keys=True) == json.dumps(cards, sort_keys=True)


# ---- the command line, on a real (scripted) build of the three-chapter toy book


TOY_KEY = {
    "title": "Toy", "chapters": [{"n": n, "file": f"ch{n:02d}.md", "words": 10} for n in (1, 2, 3)],
    "entities": {
        "mara": {"kind": "person", "aliases": ["Mara"], "first_chapter": 1},
        "orin": {"kind": "person", "aliases": ["Orin", "the ferryman"], "first_chapter": 1},
        "lamp": {"kind": "object", "aliases": ["brass lamp"], "first_chapter": 1},
        "cellar": {"kind": "place", "aliases": ["cellar"], "first_chapter": 1},
        "dock": {"kind": "place", "aliases": ["dock"], "first_chapter": 1}},
    "same_as": [], "not_same": [],
    "locations": [{"entity": "lamp", "in": "cellar", "from_chapter": 1, "to_chapter": 2},
                  {"entity": "lamp", "in": "cellar", "from_chapter": 3, "to_chapter": None}],
    "holdings": [{"entity": "lamp", "held_by": "orin", "from_chapter": 2, "to_chapter": 3}],
    "containers": [], "knowledge": [], "false_beliefs": [], "corrections": [],
}


@pytest.fixture(scope="module")
def toy_run(tmp_path_factory):
    usage_ledger.reset()
    base = tmp_path_factory.mktemp("toyrun")
    book, out = tb.write_book(base / "book"), base / "out"
    rb.run_book(book, out, tb.scripted_model())
    kb = json.dumps(TOY_KEY).encode()
    docs = [verdicts_for(TOY_KEY, kb, r) for r in ("A", "B")]
    paths = {}
    for name, n in (("full", None), ("w2", 2), ("w3", 3)):
        paths[name] = base / f"graded_{name}.json"
        paths[name].write_text(bg.gold_json(bg.build_gold(kb, docs, through_chapter=n)))
    yield {"book": book, "out": out, "graded": paths, "base": base}
    usage_ledger.reset()


def run_cli(toy_run, which, *extra, out="grades"):
    return gb.main(["--run", str(toy_run["out"]), "--graded", str(toy_run["graded"][which]),
                    "--book", str(toy_run["book"]), "--out", str(toy_run["base"] / out), *extra])


def test_6_the_command_line_grades_a_window_equal_to_the_build(toy_run):
    assert run_cli(toy_run, "w3", "--through-chapter", "3", out="g3") == 0
    card = json.loads((toy_run["base"] / "g3" / "book_scorecard.json").read_text())
    md = (toy_run["base"] / "g3" / "book_scorecard.md").read_text()
    assert md.splitlines()[0].endswith("[through_chapter: 3]")
    assert card["through_chapter"] == 3 and card["final"]["objects"]["lamp"]["ok"] is True
    assert "asserted_as_of" not in card and "asserted_as_of" not in card["final"]
    # the full-book grade of the same run has no window
    assert run_cli(toy_run, "full", out="gfull") == 0
    full = json.loads((toy_run["base"] / "gfull" / "book_scorecard.json").read_text())
    assert "through_chapter" not in full
    assert (toy_run["base"] / "gfull" / "book_scorecard.md").read_text().startswith("# Book scorecard (out)")


def test_6_the_command_line_refuses_before_grading(toy_run):
    for which, extra, reason in (("w3", (), "is windowed"),
                                 ("full", ("--through-chapter", "3"), "not windowed"),
                                 ("w3", ("--through-chapter", "2"), "not 2"),
                                 ("w2", ("--through-chapter", "2"), "not the last chapter the run built"),
                                 ("w2", ("--through-chapter", "0"), "not 0")):
        with pytest.raises(SystemExit, match=f"ABORT: .*{reason}"):
            run_cli(toy_run, which, *extra, out="refused")
    # a stamp and a flag that agree on a chapter past the book's three
    beyond = toy_run["base"] / "graded_beyond.json"
    beyond.write_text(json.dumps({**json.loads(toy_run["graded"]["w3"].read_text()), "through_chapter": 4}))
    with pytest.raises(SystemExit, match="outside the book's chapters 1..3"):
        gb.main(["--run", str(toy_run["out"]), "--graded", str(beyond), "--book", str(toy_run["book"]),
                 "--out", str(toy_run["base"] / "refused"), "--through-chapter", "4"])
    assert not (toy_run["base"] / "refused").exists()


def test_6_book_gold_command_line_writes_a_stamped_window(tmp_path, key_bytes):
    key = tmp_path / "key.json"
    key.write_bytes(key_bytes)
    ka = json.loads(key_bytes)
    for r in ("A", "B"):
        (tmp_path / f"v{r}.json").write_text(json.dumps(verdicts_for(ka, key_bytes, r)))
    out = tmp_path / "graded2.json"
    assert bg.main(["--key", str(key), "--verdicts", str(tmp_path / "vA.json"), str(tmp_path / "vB.json"),
                    "--out", str(out), "--through-chapter", "2"]) == 0
    written = json.loads(out.read_text())
    assert written["through_chapter"] == 2 and written["pending_corrections"] == 1
    assert out.read_text() == bg.gold_json(gold(key_bytes, 2))
