"""BUILD-PROFILE-V1: per-call labels, latency and objectives for book builds,
and the profile report. Every test here is the spec's Tests section (the number
in each docstring) or a detail it fixes. No model is called: the fakes sleep for
tens of milliseconds and record their own calls in the usage ledger as a shim
does."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
HARNESS = ROOT / "evals" / "harness"
sys.path.insert(0, str(HARNESS))

import codex_shim  # noqa: E402
import model_shim  # noqa: E402
import profile_build as pb  # noqa: E402
import run_book as rb  # noqa: E402
import usage_ledger  # noqa: E402
import merge_gate as mg  # noqa: E402
from patternbuffer.testing import rule_classifier_fallback  # noqa: E402
from test_book_run import PASS0_LINES, PASS1_LINES, write_book  # noqa: E402

_real_sleep = time.sleep
R26_SEQ = ROOT / "evals" / "results" / "2026-10-10-r26-build-timings" / "seq"


@pytest.fixture(autouse=True)
def _clean_usage(monkeypatch):
    monkeypatch.delenv(rb.USAGE_ENV, raising=False)
    usage_ledger.reset()
    yield
    usage_ledger.reset()


# ------------------------------------------------------------- the fake model


class FakeModel:
    """A scripted model for the toy book that sleeps, records its own call in the
    usage ledger with a measured latency (as a shim does), and notes the label in
    force when it ran. ``bad_first`` chunks parse badly on attempt 1; ``bad_always``
    chunks on every attempt."""

    def __init__(self, sleep: float = 0.03, bad_first: tuple[int, ...] = (),
                 bad_always: tuple[int, ...] = (), priced: bool = True) -> None:
        self.sleep, self.bad_first, self.bad_always, self.priced = sleep, bad_first, bad_always, priced
        self.seen: list[tuple[str, int | None, dict]] = []   # (kind, served id, label)
        self.attempts: dict[int, int] = {}
        self._lock = threading.Lock()

    def __call__(self, prompt, schema):
        started, t0 = time.time(), time.perf_counter()
        served: int | None = None
        if "PASSAGE (chunk" in prompt:
            kind = "pass1"
            served = int(prompt.split("PASSAGE (chunk ")[1].split(")")[0])
        elif "WORLD REGISTRY" in prompt:
            kind = "pass0"
            served = int(prompt.split("# Chapter ")[1].split(":")[0]) - 1
        elif "ops" in schema.get("properties", {}):
            kind = "audit"
        else:
            kind = schema.get("title", "other")
        with self._lock:
            self.seen.append((kind, served, usage_ledger.current_label()))
            n = self.attempts[served] = (self.attempts.get(served, 0) + 1) if kind == "pass1" else 0
        _real_sleep(self.sleep)
        if kind == "pass1":
            bad = served in self.bad_always or (served in self.bad_first and n == 1)
            out = {"lines": ["not|a"] if bad else PASS1_LINES[served]}
        elif kind == "pass0":
            out = {"lines": PASS0_LINES}
        elif kind == "audit":
            out = {"ops": []}
        elif kind == mg.TASK_MERGE_GATE:
            out = {"verdicts": [{"pair_id": p["pair_id"], "verdict": "unsure"}
                                for p in mg.batch_request(schema)["pairs"]]}
        else:
            out = rule_classifier_fallback()(prompt, schema)
        usage_ledger.record("test", "fake", {"input_tokens": 100, "output_tokens": 10},
                            cost_usd=0.01 if self.priced else None, started=started,
                            latency_s=time.perf_counter() - t0, outcome="ok",
                            prompt_chars=len(prompt), response_chars=len(json.dumps(out)))
        return out


def _build(tmp_path, model, name="out", **kw):
    book = write_book(tmp_path / f"book_{name}")
    out = tmp_path / name
    return out, rb.run_book(book, out, model, **kw)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines()]


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    """One profiled build of the toy book: pass-1 on 4 workers, the first parse of
    chunk 2 rejected."""
    usage_ledger.reset()
    base = tmp_path_factory.mktemp("profiled")
    model = FakeModel(sleep=0.04, bad_first=(2,))
    out, meta = _build(base, model)
    return {"out": out, "meta": meta, "model": model,
            "calls": _jsonl(out / "usage.jsonl"), "objs": _jsonl(out / "objectives.jsonl")}


# ------------------------------------------------------------------ 1. labels


def test_1_every_call_line_has_its_stage_unit_and_attempt(run):
    calls = run["calls"]
    assert calls and all(c["stage"] for c in calls)
    by_stage: dict[str, list[dict]] = {}
    for c in calls:
        by_stage.setdefault(c["stage"], []).append(c)
    assert {c["unit"] for c in by_stage["pass0"]} == {"segment:00", "segment:01", "segment:02"}
    assert all(c["attempt"] == 1 for c in by_stage["pass0"])
    pass1 = by_stage["pass1"]
    assert sorted((c["unit"], c["attempt"]) for c in pass1) == [
        ("chunk:00", 1), ("chunk:01", 1), ("chunk:02", 1), ("chunk:02", 2), ("chunk:03", 1)]
    assert [c["unit"] for c in by_stage["audit"]] == ["audit"]
    assert by_stage["commit"] and all(c["unit"].startswith("classify:") for c in by_stage["commit"])
    # the label in force inside the fake (a worker thread for pass-1) is the line's label
    for (kind, served, lab) in run["model"].seen:
        if kind == "pass1":
            assert lab["stage"] == "pass1" and lab["unit"] == f"chunk:{served:02d}"
        if kind == "pass0":
            assert lab["stage"] == "pass0" and lab["unit"] == f"segment:{served:02d}"


def test_1_a_call_outside_any_label_has_a_null_stage_and_is_counted(tmp_path, monkeypatch):
    log = tmp_path / "usage.jsonl"
    monkeypatch.setenv(rb.USAGE_ENV, str(log))
    usage_ledger.record("test", "m", {"output_tokens": 3}, 0.1)
    with usage_ledger.label(stage="s", unit="u", attempt=2):
        usage_ledger.record("test", "m", None)
    line, labelled = _jsonl(log)
    assert (line["stage"], line["unit"], line["attempt"]) == (None, None, None)
    assert (labelled["stage"], labelled["unit"], labelled["attempt"]) == ("s", "u", 2)
    assert usage_ledger.snapshot()["calls"] == 2
    # a label gains its attempt without restating the stage and unit
    with usage_ledger.label(stage="s", unit="u"), usage_ledger.label(attempt=3):
        assert usage_ledger.current_label() == {"stage": "s", "unit": "u", "attempt": 3}
    assert usage_ledger.current_label()["stage"] is None


def test_1a_concurrent_units_keep_their_own_labels(tmp_path):
    model = FakeModel(sleep=0.12)
    out, _ = _build(tmp_path, model, pass0="parallel")
    calls = _jsonl(out / "usage.jsonl")
    for (kind, served, lab) in model.seen:
        if kind == "pass0":
            assert (lab["stage"], lab["unit"]) == ("pass0", f"segment:{served:02d}")
        if kind == "pass1":
            assert (lab["stage"], lab["unit"]) == ("pass1", f"chunk:{served:02d}")
    # the calls really overlapped, in both pools
    for stage in ("pass0", "pass1"):
        cs = [c for c in calls if c["stage"] == stage]
        assert pb._max_concurrent(cs) >= 2, stage
        assert len({c["unit"] for c in cs}) == len(cs)          # one unit per call, none crossed


# ------------------------------------------------------------------ 2. timing


def _envelope(result='{"ok": true}', **extra):
    env = {"type": "result", "is_error": False, "result": result, "total_cost_usd": 0.01,
           "usage": {"input_tokens": 10, "output_tokens": 5}}
    env.update(extra)
    return json.dumps(env)


def _sleeping_run(stdouts, sleep=0.06, returncode=0, timeout=False):
    def run(argv, **kwargs):
        _real_sleep(sleep)
        if timeout:
            raise subprocess.TimeoutExpired(argv, 1)
        return subprocess.CompletedProcess(argv, returncode, stdout=stdouts[0], stderr="")
    return run


def test_2_latency_is_the_measured_call_and_outcome_ok(tmp_path, monkeypatch):
    log = tmp_path / "u.jsonl"
    monkeypatch.setenv(rb.USAGE_ENV, str(log))
    monkeypatch.setattr(model_shim.subprocess, "run", _sleeping_run([_envelope()], 0.06))
    assert model_shim.claude_model("hello", {}) == {"ok": True}
    (line,) = _jsonl(log)
    assert line["outcome"] == "ok" and abs(line["latency_s"] - 0.06) < 0.05
    assert line["started"] > 0 and line["prompt_chars"] > len("hello")
    assert line["response_chars"] == len('{"ok": true}')


def test_2_a_timeout_and_an_error_are_recorded_and_counted(tmp_path, monkeypatch):
    log = tmp_path / "u.jsonl"
    monkeypatch.setenv(rb.USAGE_ENV, str(log))
    monkeypatch.setattr(model_shim.time, "sleep", lambda s: None)         # the retry backoff
    monkeypatch.setattr(model_shim.subprocess, "run", _sleeping_run([""], 0.05, timeout=True))
    with pytest.raises(model_shim.ModelShimError):
        model_shim.claude_model("p", {})
    lines = _jsonl(log)
    assert len(lines) == 3 and all(x["outcome"] == "timeout" for x in lines)
    assert all(abs(x["latency_s"] - 0.05) < 0.05 for x in lines)
    assert all(x["num_turns"] is None and x["api_duration_ms"] is None for x in lines)
    assert usage_ledger.snapshot()["calls"] == 3
    usage_ledger.reset()
    log.write_text("")
    monkeypatch.setattr(model_shim.subprocess, "run", _sleeping_run([_envelope()], 0.05, returncode=1))
    with pytest.raises(model_shim.ModelShimError):
        model_shim.claude_model("p", {})
    lines = _jsonl(log)
    assert len(lines) == 3 and all(x["outcome"] == "error" for x in lines)
    assert usage_ledger.snapshot()["calls"] == 3


def test_2_the_cli_envelope_turns_and_durations_reach_the_line(tmp_path, monkeypatch):
    log = tmp_path / "u.jsonl"
    monkeypatch.setenv(rb.USAGE_ENV, str(log))
    env = _envelope(num_turns=1, duration_ms=5400, duration_api_ms=4100)
    monkeypatch.setattr(model_shim.subprocess, "run", _sleeping_run([env], 0.01))
    model_shim.claude_model("p", {})
    monkeypatch.setattr(model_shim.subprocess, "run", _sleeping_run([_envelope()], 0.01))
    model_shim.claude_model("p", {})                         # an envelope without them
    monkeypatch.setattr(model_shim.subprocess, "run", _sleeping_run(['{"ok": 1}'], 0.01))
    model_shim.claude_model("p", {})                         # plain output, no envelope
    a, b, c = _jsonl(log)
    assert (a["num_turns"], a["cli_duration_ms"], a["api_duration_ms"]) == (1, 5400, 4100)
    for x in (b, c):
        assert (x["num_turns"], x["cli_duration_ms"], x["api_duration_ms"]) == (None, None, None)


class _Stream:
    def __init__(self, lines): self._lines = lines
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __iter__(self): return iter(self._lines)


def test_2_the_codex_shim_measures_a_call_and_a_failed_call(tmp_path, monkeypatch):
    log = tmp_path / "u.jsonl"
    monkeypatch.setenv(rb.USAGE_ENV, str(log))
    monkeypatch.setattr(codex_shim, "_credentials", lambda: ("tok", "acct"))
    final = {"type": "response.completed", "response": {
        "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"a": 1}'}]}],
        "usage": {"input_tokens": 20, "output_tokens": 8}}}

    def ok(req, timeout=None):
        _real_sleep(0.05)
        return _Stream([b"data: " + json.dumps(final).encode() + b"\n", b"\n"])
    monkeypatch.setattr(codex_shim.urllib.request, "urlopen", ok)
    assert codex_shim._call_once("prompt", {}) == {"a": 1}

    def down(req, timeout=None):
        _real_sleep(0.05)
        raise urllib.error.URLError("no route")
    monkeypatch.setattr(codex_shim.urllib.request, "urlopen", down)
    with pytest.raises(codex_shim.CodexShimError):
        codex_shim._call_once("prompt", {})
    good, bad = _jsonl(log)
    assert good["outcome"] == "ok" and abs(good["latency_s"] - 0.05) < 0.05
    assert good["output_tokens"] == 8 and good["response_chars"] == len('{"a": 1}')
    assert bad["outcome"] == "error" and abs(bad["latency_s"] - 0.05) < 0.05
    assert usage_ledger.snapshot()["calls"] == 2


# --------------------------------------------------------------- 3. objectives


def test_3_a_rejected_first_parse_has_two_attempt_records(run):
    (obj,) = [o for o in run["objs"] if o["stage"] == "pass1" and o["unit"] == "chunk:02"]
    assert obj["accepted"] is True
    assert [a["attempt"] for a in obj["attempts"]] == [1, 2]
    assert [a["outcome"] for a in obj["attempts"]] == ["rejected", "accepted"]
    assert "reject rate over threshold" in obj["attempts"][0]["reason"]
    assert obj["attempts"][1]["reason"] is None
    assert obj["seconds"] >= sum(a["seconds"] for a in obj["attempts"]) - 0.01
    assert all(a["started"] > 0 and a["seconds"] >= 0.03 for a in obj["attempts"])
    others = [o for o in run["objs"] if o["stage"] == "pass1" and o["unit"] != "chunk:02"]
    assert others and all(len(o["attempts"]) == 1 and o["accepted"] for o in others)


def test_3_a_chunk_that_fails_twice_is_not_accepted_and_the_run_aborts(tmp_path):
    book = write_book(tmp_path / "book")
    out = tmp_path / "out"
    with pytest.raises(rb.BookRunAborted):
        rb.run_book(book, out, FakeModel(sleep=0.01, bad_always=(1,)))
    (obj,) = [o for o in _jsonl(out / "objectives.jsonl") if o["unit"] == "chunk:01"]
    assert obj["accepted"] is False and len(obj["attempts"]) == 2
    assert [a["outcome"] for a in obj["attempts"]] == ["rejected", "rejected"]
    assert all("reject rate" in a["reason"] for a in obj["attempts"])


def test_3_a_failing_call_is_an_error_attempt(tmp_path):
    book = write_book(tmp_path / "book")
    out = tmp_path / "out"
    good = FakeModel(sleep=0.0)

    def flaky(prompt, schema):
        if "PASSAGE (chunk 0)" in prompt:
            raise TimeoutError("call timed out")
        return good(prompt, schema)

    with pytest.raises(rb.BookRunAborted):
        rb.run_book(book, out, flaky)
    (obj,) = [o for o in _jsonl(out / "objectives.jsonl") if o["unit"] == "chunk:00"]
    assert obj["accepted"] is False
    assert [a["outcome"] for a in obj["attempts"]] == ["timeout", "timeout"]
    assert obj["attempts"][0]["reason"] == "call timed out"


def test_3_the_objective_count_is_the_units_the_run_planned(run):
    objs, calls = run["objs"], run["calls"]
    classify = [c for c in calls if c["stage"] == "commit"]
    assert len(objs) == 3 + 4 + len(classify) + 1                 # segments, chunks, batches, audit
    assert len({(o["stage"], o["unit"]) for o in objs}) == len(objs)
    assert {(o["stage"], o["unit"]) for o in objs} == {(c["stage"], c["unit"]) for c in calls}
    assert {o["stage"] for o in objs} == {"pass0", "pass1", "commit", "audit"}
    assert [o["unit"] for o in objs if o["stage"] == "commit"] == sorted(
        o["unit"] for o in objs if o["stage"] == "commit")


def test_3_usage_jsonl_holds_no_objective_line(run):
    for c in run["calls"]:
        assert "provider" in c and "attempts" not in c and "accepted" not in c
    assert all("attempts" in o for o in run["objs"])


def test_3_the_merge_gate_batches_are_objectives(tmp_path):
    model = FakeModel(sleep=0.0)
    out, _ = _build(tmp_path, model, merge_gate=True, pass0="parallel")
    gate = (out / "merge_gate.json").exists()
    objs = _jsonl(out / "objectives.jsonl")
    calls = _jsonl(out / "usage.jsonl")
    assert gate
    assert {(o["stage"], o["unit"]) for o in objs} == {(c["stage"], c["unit"]) for c in calls}
    assert all(c["stage"] for c in calls)


def test_3a_profiling_does_not_change_the_receipt(tmp_path):
    outs = {}
    for name, profile in (("on", True), ("off", False)):
        out, _ = _build(tmp_path, FakeModel(sleep=0.01), name=name, profile=profile)
        outs[name] = json.loads((out / "receipt.json").read_text())
    assert (tmp_path / "on" / "objectives.jsonl").exists()
    assert not (tmp_path / "off" / "objectives.jsonl").exists()
    on, off = outs["on"], outs["off"]
    assert set(on) == set(off) == {"stages", "total"}
    assert on["stages"].keys() == off["stages"].keys() == set(rb.STAGES)
    for stage in on["stages"]:
        a, b = dict(on["stages"][stage]), dict(off["stages"][stage])
        a.pop("seconds"), b.pop("seconds")                           # wall time varies run to run
        assert a == b, stage
        assert on["stages"][stage]["cost_known"] is True
    a, b = dict(on["total"]), dict(off["total"])
    a.pop("seconds"), b.pop("seconds")
    assert a == b and a["cost_known"] is True


# ------------------------------------------------------------------ 4. report


def _call(stage, unit, lat, out_tok, in_tok=100, started=0.0, **extra):
    return {"t": started + lat, "started": started, "latency_s": lat, "provider": "t", "model": "m",
            "stage": stage, "unit": unit, "attempt": 1, "outcome": "ok", "input_tokens": in_tok,
            "output_tokens": out_tok, "cache_read_tokens": 0, "cache_write_tokens": 0,
            "cost_usd": 0.01, "usage_reported": True, "prompt_chars": 10, "response_chars": 10,
            "num_turns": None, "cli_duration_ms": None, "api_duration_ms": None, **extra}


def _obj(stage, unit, attempts, started=1000.0, accepted=True):
    """attempts: [(seconds, outcome, reason)]"""
    recs, t = [], started
    for i, (sec, outcome, reason) in enumerate(attempts, 1):
        recs.append({"attempt": i, "started": t, "seconds": sec, "outcome": outcome, "reason": reason})
        t += sec
    return {"stage": stage, "unit": unit, "accepted": accepted,
            "seconds": sum(a[0] for a in attempts), "attempts": recs}


def _write(d: Path, name: str, rows) -> None:
    d.mkdir(parents=True, exist_ok=True)
    if name.endswith(".jsonl"):
        (d / name).write_text("".join(json.dumps(r) + "\n" for r in rows))
    else:
        (d / name).write_text(json.dumps(rows))


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    """A hand-built run: nine pass-1 chunks (one retried and accepted, one never
    accepted), two classification batches, ten pass-1 calls with latency 1..10 s
    and output tokens proportional to latency."""
    d = tmp_path_factory.mktemp("synthetic")
    objs = [
        _obj("pass1", "chunk:00", [(6, "accepted", None)], 1000.0),
        _obj("pass1", "chunk:01", [(6, "accepted", None)], 1001.0),
        _obj("pass1", "chunk:02", [(6, "accepted", None)], 1002.0),
        _obj("pass1", "chunk:03", [(3, "rejected", "reject rate over threshold (4 rejects)"),
                                   (3, "accepted", None)], 1003.0),
        *[_obj("pass1", f"chunk:{i:02d}", [(3, "accepted", None)], 1000.0 + i) for i in range(4, 8)],
        _obj("pass1", "chunk:08", [(1.5, "rejected", "reject rate over threshold (9 rejects)"),
                                   (1.5, "error", "boom")], 1008.0, accepted=False),
        _obj("commit", "classify:01", [(4, "accepted", None)], 1100.0),
        _obj("commit", "classify:02", [(3, "accepted", None)], 1104.0),
        _obj("pass0", "segment:00", [(5, "accepted", None), (2, "accepted", None)], 990.0),
    ]
    in_toks = [50, 10, 40, 20, 30, 70, 5, 90, 15, 60]
    calls = [_call("pass1", f"chunk:{i:02d}", float(i + 1), 100 * (i + 1), in_toks[i],
                   started=1000.0 + i, num_turns=1 + i % 3, cli_duration_ms=(i + 1) * 1000.0,
                   api_duration_ms=(i + 1) * 800.0) for i in range(10)]
    calls += [_call("pass0", "segment:00", 4.0, 400), _call("pass0", "segment:00", 2.0, 200)]
    _write(d, "usage.jsonl", calls)
    _write(d, "objectives.jsonl", objs)
    _write(d, "timings.json", {"pass0_s": 10.0, "pass1_s": 30.0, "escape_repair_s": 0.0,
                               "commit_s": 8.0, "audit_s": 2.0, "total_s": 50.0})
    _write(d, "meta.json", {"pass0_mode": "parallel"})
    return d


def test_4_stage_shares_utilization_and_percentiles(synthetic):
    p = pb.build_profile(synthetic)
    rows = {r["stage"]: r for r in p["stages"]}
    assert sum(r["share"] for r in rows.values()) == pytest.approx(1.0, abs=0.01)
    p1 = rows["pass1"]
    assert 0 < p1["utilization"] <= 1
    assert p1["utilization"] == pytest.approx(55 / (30 * 4), abs=1e-3)       # latency sum / (wall x workers)
    assert (p1["latency_p50_s"], p1["latency_p90_s"], p1["latency_max_s"]) == (5.0, 9.0, 10.0)
    assert p1["calls"] == 10 and p1["objectives"] == 9
    assert p1["out_tok_per_s_median"] == pytest.approx(100.0) and p1["out_tok_per_s_p10"] == pytest.approx(100.0)
    assert p1["input_tokens"] == 390 and p1["output_tokens"] == 5500
    for r in rows.values():
        assert r["utilization"] == pb.UNMEASURED or 0 < r["utilization"] <= 1


def test_4_cli_turns_and_api_share_are_shown_per_stage(synthetic):
    p = pb.build_profile(synthetic)
    p1 = {r["stage"]: r for r in p["stages"]}["pass1"]
    assert (p1["turns_per_call_median"], p1["turns_per_call_max"]) == (2.0, 3.0)
    assert p1["api_time_share_of_latency"] == pytest.approx(0.8)
    assert p1["harness_overhead_s"] == pytest.approx(11.0)
    p0 = {r["stage"]: r for r in p["stages"]}["pass0"]
    assert p0["turns_per_call_median"] == pb.UNMEASURED and p0["api_time_share_of_latency"] == pb.UNMEASURED
    md = pb.render_md(p)
    assert "turns/call median" in md and "80.0%" in md


def test_4_the_floor_is_the_longest_objective_and_the_replays_match_a_hand_schedule(synthetic):
    c = {x["stage"]: x for x in pb.build_profile(synthetic)["ceilings"]}["pass1"]
    assert (c["floor_s"], c["floor_unit"]) == (6.0, "chunk:00")
    by_w = {w["workers"]: w for w in c["what_if"]}
    assert set(by_w) == {1, 4, 8} and by_w[4]["current"] is True
    # durations in submission order [6,6,6,6,3,3,3,3,3]: 4 workers -> 12, 8 workers -> 6, 1 -> 39
    assert (by_w[4]["all_attempts_s"], by_w[8]["all_attempts_s"], by_w[1]["all_attempts_s"]) == (12.0, 6.0, 39.0)
    assert pb.list_schedule([6, 6, 6, 6, 3, 3, 3, 3, 3], 4)[0] == 12.0
    assert pb.list_schedule([6, 6, 6, 6, 3, 3, 3, 3, 3], None)[0] == 6.0
    assert "Lower bound" in c["note"]


def test_4_no_retries_uses_first_attempt_durations_and_lists_the_never_accepted(synthetic):
    c = {x["stage"]: x for x in pb.build_profile(synthetic)["ceilings"]}["pass1"]
    by_w = {w["workers"]: w for w in c["what_if"]}
    # chunk:03 counts 3 s (its rejected first attempt); chunk:08 never accepted, so it is left out:
    # [6,6,6,3,3,3,3,3] -> 4 workers 9, 8 workers 6, 1 worker 33
    assert (by_w[4]["no_retries_s"], by_w[8]["no_retries_s"], by_w[1]["no_retries_s"]) == (9.0, 6.0, 33.0)
    assert c["would_still_fail"] == 1
    assert c["never_accepted"] == [{"unit": "chunk:08", "first_attempt_s": 1.5}]
    assert "chunk:08" in pb.render_md(pb.build_profile(synthetic)) and "would still fail: 1" in pb.render_md(
        pb.build_profile(synthetic))


def test_4_turns_table_counts_attempts_and_retry_seconds(synthetic):
    t = {x["stage"]: x for x in pb.build_profile(synthetic)["turns"]}
    p1 = t["pass1"]
    assert p1["attempts_histogram"] == {"1": 7, "2": 2} and p1["accepted"] == 8
    assert [u["unit"] for u in p1["retried"]] == ["chunk:03", "chunk:08"]
    assert p1["retry_seconds"] == 4.5                                   # 3 (chunk:03) + 1.5 (chunk:08)
    assert "reject rate over threshold (4 rejects)" in p1["retried"][0]["reasons"]
    assert t["pass0"]["retried"] == [] and t["pass0"]["attempts_histogram"] == {"2": 1}   # a glean round is not a retry


def test_4_the_overlapped_pipeline_matches_a_hand_schedule(synthetic):
    ov = pb.build_profile(synthetic)["overlapped_pipeline"]
    # chunks finish at [6,6,6,6,9,9,9,9,12] on 4 workers; batch 1 (4 s) is ready at chunk 5 (t=9) and
    # ends 13; batch 2 (3 s) is ready at chunk 9 (t=12), starts 13, ends 16. Phase 16 s.
    # Total = pass0 10 + 16 + escape 0 + other commit (8 - 7) 1 + audit 2 = 29.
    assert ov["batch_ready_s"] == [9.0, 12.0]
    assert (ov["last_chunk_done_s"], ov["classification_done_s"], ov["pass1_phase_s"]) == (12.0, 16.0, 16.0)
    assert ov["commit_other_s"] == 1.0 and ov["total_s"] == 29.0
    assert ov["measured_total_s"] == 50.0 and ov["saved_s"] == 21.0
    assert "Dependency model" in ov["model"]
    md = pb.render_md(pb.build_profile(synthetic))
    assert "Dependency model" in md and md.count("Lower bound") >= 2


def test_4_every_what_if_carries_the_lower_bound_note(synthetic):
    p = pb.build_profile(synthetic)
    assert all(pb.LOWER_BOUND_NOTE == c["note"] for c in p["ceilings"])
    assert pb.LOWER_BOUND_NOTE in pb.render_md(p)
    rows = {r["scenario"]: r["total_s"] for r in p["build_what_ifs"]}
    assert rows["measured"] == 50.0
    assert rows["pass1 on 8 worker(s)"] == 26.0                          # 50 - 30 + 6
    assert rows["overlapped pipeline (hypothetical)"] == 29.0


def test_4_a_three_call_run_marks_the_fit_unmeasured(tmp_path):
    _write(tmp_path, "usage.jsonl", [_call("pass1", f"chunk:0{i}", i + 1.0, 100 * (i + 1), 10 * i + 5)
                                     for i in range(3)])
    p = pb.build_profile(tmp_path)
    f = p["output_bound_fit"]["all"]["latency_vs_output_tokens"]
    assert "unmeasured" in f and "fewer than 5" in f["unmeasured"] and "r2" not in f
    md = pb.render_md(p)
    assert "unmeasured (fewer than 5 calls (3))" in md


def test_4_zero_variance_is_unmeasured_not_a_number(tmp_path):
    _write(tmp_path, "usage.jsonl", [_call("pass1", f"chunk:{i:02d}", 1.0 + i, 100, 50 + i)
                                     for i in range(6)])
    f = pb.build_profile(tmp_path)["output_bound_fit"]["all"]
    assert f["latency_vs_output_tokens"]["unmeasured"] == "zero variance in the token count"
    assert "r2" in f["latency_vs_input_tokens"]
    _write(tmp_path, "usage.jsonl", [_call("pass1", f"chunk:{i:02d}", 2.0, 100 + i, 50 + i)
                                     for i in range(6)])
    f = pb.build_profile(tmp_path)["output_bound_fit"]["all"]
    assert f["latency_vs_output_tokens"]["unmeasured"] == "zero variance in latency"


def test_4_the_latency_fit_finds_a_call_bound_by_its_output(synthetic):
    fits = pb.build_profile(synthetic)["output_bound_fit"]
    f = fits["pass1"]["latency_vs_output_tokens"]
    assert f["r2"] == pytest.approx(1.0, abs=1e-3) and f["seconds_per_1k_tokens"] == pytest.approx(10.0)
    assert fits["pass1"]["latency_vs_input_tokens"]["r2"] < 0.5
    assert "unmeasured" in fits["pass0"]["latency_vs_output_tokens"]


def test_4_the_report_on_a_real_fake_run(run):
    """The profile of the module's fake build: shares sum to 1, rows exist for every
    stage, and a sleep-proportional latency shows up in the calls."""
    p = pb.build_profile(run["out"])
    assert {r["stage"] for r in p["stages"]} >= set(rb.STAGES)
    shares = [r["share"] for r in p["stages"] if isinstance(r["share"], float)]
    assert sum(shares) == pytest.approx(1.0, abs=0.01)
    pass1 = {r["stage"]: r for r in p["stages"]}["pass1"]
    assert pass1["latency_p50_s"] >= 0.04 and pass1["calls"] == 5
    assert p["turns"] and p["overlapped_pipeline"] is not None
    assert [a["result"] for a in p["ablation"]] == ["not measured"] * len(p["ablation"])
    pb.render_md(p)


def test_4_main_writes_profile_json_and_md_and_an_ablation_file_fills_the_column(synthetic, tmp_path):
    d = tmp_path / "copy"
    shutil.copytree(synthetic, d)
    _write(d, "ablation.json", {"audit": "accuracy 0.91 against 0.93 with the audit cut"})
    assert pb.main([str(d)]) == 0
    prof = json.loads((d / "profile.json").read_text())
    md = (d / "profile.md").read_text()
    assert prof["run_dir"] == "copy" and md.startswith("# Build profile: copy")
    assert "| audit | accuracy 0.91 against 0.93 with the audit cut |" in md
    assert "| pass1 | not measured |" in md
    first = (d / "profile.json").read_text()
    pb.main([str(d)])
    assert (d / "profile.json").read_text() == first                      # deterministic


# ------------------------------------------------------------------ 5. old runs


def test_5_an_old_run_gets_stage_totals_and_unmeasured_per_call_fields(tmp_path):
    d = tmp_path / "seq"
    shutil.copytree(R26_SEQ, d)
    assert not (d / "usage.jsonl").exists()
    assert pb.main([str(d)]) == 0
    prof = json.loads((d / "profile.json").read_text())
    rows = {r["stage"]: r for r in prof["stages"]}
    assert rows["pass0"]["wall_s"] == 883.6 and rows["pass1"]["wall_s"] == 563.8
    assert rows["commit"]["wall_s"] == 261.1 and rows["audit"]["wall_s"] == 200.9
    assert sum(r["share"] for r in rows.values()) == pytest.approx(1.0, abs=0.01)
    for key in ("calls", "latency_p50_s", "utilization", "input_tokens", "cost_usd", "objectives"):
        assert rows["pass0"][key] == pb.UNMEASURED, key
    assert prof["output_bound_fit"] == pb.UNMEASURED and prof["ceilings"] == []
    md = (d / "profile.md").read_text()
    assert "unmeasured" in md and "883.6" in md and "no usage.jsonl" in md


def test_5_a_directory_with_nothing_to_read_does_not_fail(tmp_path):
    assert pb.main([str(tmp_path)]) == 0
    assert "unmeasured" in (tmp_path / "profile.md").read_text()


# ------------------------------------------------------------------ 6. ledger


def test_6_new_fields_leave_the_snapshot_and_receipt_unchanged():
    keys = {"calls", "calls_without_usage", "cost_usd", "cost_known", "input_tokens",
            "output_tokens", "cache_read_tokens", "cache_write_tokens"}
    assert set(usage_ledger.snapshot()) == keys
    usage_ledger.record("p", "m", {"input_tokens": 5, "output_tokens": 2}, 0.5)
    plain = usage_ledger.snapshot()
    usage_ledger.reset()
    with usage_ledger.label(stage="s", unit="u", attempt=1):
        usage_ledger.record("p", "m", {"input_tokens": 5, "output_tokens": 2}, 0.5, started=1.0,
                            latency_s=2.0, outcome="ok", prompt_chars=9, response_chars=3,
                            num_turns=2, cli_duration_ms=10.0, api_duration_ms=8.0)
    assert usage_ledger.snapshot() == plain and set(plain) == keys


def test_6_a_line_holds_every_field_of_the_spec(tmp_path, monkeypatch):
    log = tmp_path / "u.jsonl"
    monkeypatch.setenv(rb.USAGE_ENV, str(log))
    usage_ledger.record("p", "m", {"input_tokens": 1}, 0.1)
    (line,) = _jsonl(log)
    assert set(line) == {"t", "started", "latency_s", "provider", "model", "stage", "unit", "attempt",
                         "outcome", "input_tokens", "output_tokens", "cache_read_tokens",
                         "cache_write_tokens", "cost_usd", "usage_reported", "prompt_chars",
                         "response_chars", "num_turns", "cli_duration_ms", "api_duration_ms"}
