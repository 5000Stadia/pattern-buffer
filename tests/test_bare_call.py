"""BARE-CALL-V1: every build model call attempt is one bare call. No model is
called: ``subprocess.run`` is patched throughout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent.parent / "evals" / "harness"
sys.path.insert(0, str(HARNESS))

import model_shim  # noqa: E402
import usage_ledger  # noqa: E402

BARE = ["claude", "-p", "--model", "M", "--output-format", "json", "--max-turns", "1",
        "--tools", "", "--strict-mcp-config", "--setting-sources", "",
        "--no-session-persistence", "--system-prompt", model_shim.BARE_SYSTEM_PROMPT]


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.delenv("PB_SHIM_LEGACY", raising=False)
    monkeypatch.setenv("PB_EVAL_USAGE_LOG", str(tmp_path / "u.jsonl"))
    monkeypatch.setattr(model_shim.time, "sleep", lambda s: None)
    usage_ledger.reset()
    yield
    usage_ledger.reset()


def _env_line(result='{"ok": true}', **extra) -> str:
    env = {"type": "result", "is_error": False, "result": result,
           "usage": {"input_tokens": 3, "output_tokens": 2}}
    env.update(extra)
    return json.dumps(env)


def _lines(tmp_path) -> list[dict]:
    p = tmp_path / "u.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


class Fake:
    """A patched subprocess.run that records what each call was given."""

    def __init__(self, stdouts, returncode=0, raises=None):
        self.stdouts, self.returncode, self.raises = list(stdouts), returncode, raises
        self.calls: list[dict] = []

    def __call__(self, argv, **kw):
        cwd = kw.get("cwd")
        self.calls.append({"argv": argv, "kw": kw,
                           "cwd_existed": cwd is not None and os.path.isdir(cwd),
                           "cwd_listing": os.listdir(cwd) if cwd and os.path.isdir(cwd) else None})
        if self.raises:
            raise self.raises
        out = self.stdouts.pop(0) if len(self.stdouts) > 1 else self.stdouts[0]
        return subprocess.CompletedProcess(argv, self.returncode, stdout=out, stderr="boom")


def _patch(monkeypatch, fake):
    monkeypatch.setattr(model_shim.subprocess, "run", fake)
    return fake


# 1 ------------------------------------------------------------------ argv

def test_1_bare_argv_is_exactly_the_spec_command_line():
    assert model_shim.bare_argv("M") == BARE
    assert "8" not in model_shim.bare_argv("M")
    assert model_shim.BARE_SYSTEM_PROMPT.startswith("You answer with one JSON object")


def test_1_every_attempt_uses_bare_argv(monkeypatch):
    fake = _patch(monkeypatch, Fake([_env_line("nope"), _env_line("still no"), _env_line()]))
    assert model_shim.claude_model("p", {}) == {"ok": True}
    assert len(fake.calls) == 3
    assert all(c["argv"] == model_shim.bare_argv(model_shim.MODEL) for c in fake.calls)


# 2 ------------------------------------------------------- empty cwd per call

def test_2_cwd_is_a_fresh_empty_dir_removed_after_success(monkeypatch):
    fake = _patch(monkeypatch, Fake([_env_line()]))
    assert model_shim.claude_model("hello", {}) == {"ok": True}
    (c,) = fake.calls
    assert c["cwd_existed"] and c["cwd_listing"] == []
    assert not os.path.exists(c["kw"]["cwd"])
    assert c["kw"]["input"].startswith("hello")


def test_2_each_attempt_gets_its_own_dir_removed_after_failures(monkeypatch):
    fake = _patch(monkeypatch, Fake([""], returncode=1))
    with pytest.raises(model_shim.ModelShimError):
        model_shim.claude_model("p", {})
    assert len(fake.calls) == 3
    dirs = [c["kw"]["cwd"] for c in fake.calls]
    assert len(set(dirs)) == 3
    assert all(c["cwd_existed"] and c["cwd_listing"] == [] for c in fake.calls)
    assert not any(os.path.exists(d) for d in dirs)


def test_2_cwd_is_removed_after_a_timeout(monkeypatch):
    fake = _patch(monkeypatch, Fake([""], raises=subprocess.TimeoutExpired("claude", 1)))
    with pytest.raises(model_shim.ModelShimError):
        model_shim.claude_model("p", {})
    assert len(fake.calls) == 3
    assert not any(os.path.exists(c["kw"]["cwd"]) for c in fake.calls)


# 3 ------------------------------------------------------- the turn guarantee

def test_3_multi_turn_on_every_attempt_raises_and_returns_no_json(monkeypatch, tmp_path):
    fake = _patch(monkeypatch, Fake([_env_line('{"leak": 1}', num_turns=3)]))
    with pytest.raises(model_shim.ModelShimError, match="after retries"):
        model_shim.claude_model("p", {})
    assert len(fake.calls) == 3
    lines = _lines(tmp_path)
    assert [l["outcome"] for l in lines] == ["multi_turn"] * 3
    assert all(l["num_turns"] == 3 for l in lines)


def test_3_multi_turn_first_then_one_turn_returns_the_second(monkeypatch, tmp_path, caplog):
    _patch(monkeypatch, Fake([_env_line('{"leak": 1}', num_turns=2),
                              _env_line('{"good": 2}', num_turns=1)]))
    with caplog.at_level("WARNING", logger=model_shim.logger.name):
        assert model_shim.claude_model("p", {}) == {"good": 2}
    assert [l["outcome"] for l in _lines(tmp_path)] == ["multi_turn", "ok"]
    assert any("multi-turn" in r.message and r.levelname == "WARNING" for r in caplog.records)


def test_3_num_turns_one_is_ok_and_absent_is_accepted_as_null(monkeypatch, tmp_path):
    _patch(monkeypatch, Fake([_env_line(num_turns=1), _env_line()]))
    assert model_shim.claude_model("p", {}) == {"ok": True}
    assert model_shim.claude_model("p", {}) == {"ok": True}
    one, absent = _lines(tmp_path)
    assert one["outcome"] == "ok" and one["num_turns"] == 1
    assert absent["outcome"] == "ok" and absent["num_turns"] is None


# 3a ------------------------------------------------------------ environment

def test_3a_child_env_holds_only_the_allowlist(monkeypatch):
    for k in model_shim._CHILD_ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", "/home/x")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("CLAUDE_FOO", "1")
    monkeypatch.setenv("PB_SECRET", "1")
    fake = _patch(monkeypatch, Fake([_env_line()]))
    model_shim.claude_model("p", {})
    env = fake.calls[0]["kw"]["env"]
    assert env == {"HOME": "/home/x", "PATH": "/usr/bin", "ANTHROPIC_API_KEY": "k"}
    assert "PB_EVAL_USAGE_LOG" not in env and "CLAUDE_FOO" not in env and "HOME" in env
    assert set(env) <= set(model_shim._CHILD_ENV_KEYS)


# 4 ------------------------------------------------------------------ legacy

def test_4_legacy_gives_the_old_argv_and_no_cwd_or_env(monkeypatch):
    monkeypatch.setenv("PB_SHIM_LEGACY", "1")
    fake = _patch(monkeypatch, Fake([_env_line()]))
    assert model_shim.claude_model("p", {}) == {"ok": True}
    (c,) = fake.calls
    assert c["argv"] == ["claude", "-p", "--model", model_shim.MODEL, "--max-turns", "8",
                         "--output-format", "json"]
    assert "cwd" not in c["kw"] and "env" not in c["kw"]


# 5 ------------------------------------------------- retry / quota / timeout

def test_5_quota_is_still_detected_without_retry(monkeypatch):
    fake = _patch(monkeypatch, Fake(["You've hit your usage limit"], returncode=1))
    with pytest.raises(model_shim.QuotaExhausted):
        model_shim.claude_model("p", {})
    assert len(fake.calls) == 1


def test_5_parse_failure_retries_with_the_repair_prompt(monkeypatch):
    fake = _patch(monkeypatch, Fake([_env_line("not json"), _env_line()]))
    assert model_shim.claude_model("p", {}) == {"ok": True}
    assert "not valid JSON" in fake.calls[1]["kw"]["input"]
    assert fake.calls[1]["kw"]["timeout"] == model_shim.TIMEOUT


def test_5_timeout_records_a_receipt_per_attempt(monkeypatch, tmp_path):
    _patch(monkeypatch, Fake([""], raises=subprocess.TimeoutExpired("claude", 1)))
    with pytest.raises(model_shim.ModelShimError):
        model_shim.claude_model("p", {})
    assert [l["outcome"] for l in _lines(tmp_path)] == ["timeout"] * 3


def test_4_legacy_keeps_accepting_multi_turn_answers(monkeypatch, tmp_path):
    monkeypatch.setenv("PB_SHIM_LEGACY", "1")
    _patch(monkeypatch, Fake([_env_line(num_turns=5)]))
    assert model_shim.claude_model("p", {}) == {"ok": True}
    assert [l["outcome"] for l in _lines(tmp_path)] == ["ok"]
