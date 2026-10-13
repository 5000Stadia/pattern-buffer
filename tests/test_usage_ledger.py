"""Token and cost receipts (R27 prep): the shims count every completed call
in ``usage_ledger``; no model is called here."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent.parent / "evals" / "harness"
sys.path.insert(0, str(HARNESS))

import codex_shim  # noqa: E402
import model_shim  # noqa: E402
import usage_ledger  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_ledger(monkeypatch):
    monkeypatch.delenv("PB_EVAL_USAGE_LOG", raising=False)
    usage_ledger.reset()
    yield
    usage_ledger.reset()


def _envelope(result: str, cost: float = 0.012) -> str:
    return "\n".join([
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "result", "is_error": False, "result": result,
                    "total_cost_usd": cost,
                    "usage": {"input_tokens": 120, "output_tokens": 40,
                              "cache_read_input_tokens": 900,
                              "cache_creation_input_tokens": 300}}),
    ])


def _fake_run(stdouts):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=stdouts.pop(0), stderr="")
    return run, calls


def test_claude_call_asks_for_the_json_envelope_and_counts_it(monkeypatch):
    run, calls = _fake_run([_envelope('{"ok": true}')])
    monkeypatch.setattr(model_shim.subprocess, "run", run)
    assert model_shim.claude_model("p", {"type": "object"}) == {"ok": True}
    assert calls[0][-2:] == ["--output-format", "json"]
    snap = usage_ledger.snapshot()
    assert snap["calls"] == 1 and snap["calls_without_usage"] == 0
    assert (snap["input_tokens"], snap["output_tokens"]) == (120, 40)
    assert (snap["cache_read_tokens"], snap["cache_write_tokens"]) == (900, 300)
    assert snap["cost_usd"] == pytest.approx(0.012) and snap["cost_known"] is True


def test_a_reply_that_fails_to_parse_still_counts_its_spend(monkeypatch):
    run, _ = _fake_run([_envelope("not json at all"), _envelope('{"ok": 1}')])
    monkeypatch.setattr(model_shim.subprocess, "run", run)
    monkeypatch.setattr(model_shim.time, "sleep", lambda s: None)
    assert model_shim.claude_model("p", {}) == {"ok": 1}
    snap = usage_ledger.snapshot()
    assert snap["calls"] == 2 and snap["input_tokens"] == 240
    assert snap["cost_usd"] == pytest.approx(0.024)


def test_plain_output_without_an_envelope_is_text_with_unknown_usage(monkeypatch):
    run, _ = _fake_run(['{"ok": true}'])
    monkeypatch.setattr(model_shim.subprocess, "run", run)
    assert model_shim.claude_model("p", {}) == {"ok": True}
    snap = usage_ledger.snapshot()
    assert snap["calls"] == 1 and snap["calls_without_usage"] == 1
    assert snap["cost_known"] is False and snap["input_tokens"] == 0


def test_quota_text_inside_the_envelope_still_raises(monkeypatch):
    out = json.dumps({"type": "result", "is_error": True,
                      "result": "You've hit your session limit", "total_cost_usd": 0})

    def run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, stdout=out, stderr="")
    monkeypatch.setattr(model_shim.subprocess, "run", run)
    with pytest.raises(model_shim.QuotaExhausted):
        model_shim.claude_model("p", {})


def test_codex_usage_block_maps_to_ledger_fields():
    final = {"usage": {"input_tokens": 50, "output_tokens": 7,
                       "input_tokens_details": {"cached_tokens": 30}}}
    assert codex_shim._usage_from_final(final) == {
        "input_tokens": 50, "output_tokens": 7, "cache_read_tokens": 30}
    assert codex_shim._usage_from_final(None) is None
    assert codex_shim._usage_from_final({"output": []}) is None


def test_codex_calls_leave_the_cost_unknown():
    usage_ledger.record("codex", "m", {"input_tokens": 5, "output_tokens": 1})
    snap = usage_ledger.snapshot()
    assert snap["cost_known"] is False and snap["cost_usd"] == 0.0
    assert snap["input_tokens"] == 5


def test_log_file_gets_one_line_per_call(monkeypatch, tmp_path):
    log = tmp_path / "usage.jsonl"
    monkeypatch.setenv("PB_EVAL_USAGE_LOG", str(log))
    usage_ledger.record("claude", "m", {"input_tokens": 3}, 0.001)
    usage_ledger.record("codex", "m", None)
    lines = [json.loads(x) for x in log.read_text().splitlines()]
    assert [x["provider"] for x in lines] == ["claude", "codex"]
    assert lines[0]["input_tokens"] == 3 and lines[1]["usage_reported"] is False


def test_parallel_records_are_all_counted():
    def worker():
        for _ in range(200):
            usage_ledger.record("claude", "m", {"input_tokens": 1, "output_tokens": 2}, 0.5)
    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    snap = usage_ledger.snapshot()
    assert snap["calls"] == 1600 and snap["input_tokens"] == 1600
    assert snap["output_tokens"] == 3200 and snap["cost_usd"] == pytest.approx(800.0)
