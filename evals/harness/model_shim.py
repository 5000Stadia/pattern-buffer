"""The injected model callable for graded runs: a two-line-spirit shim
around the local `claude` CLI. (prompt, schema) -> parsed JSON.

This is harness machinery, not engine code — the engine knows only the
callable contract (whitepaper §17.1).

BARE-CALL-V1: every *attempt* is one bare call — one turn, no tools, the
default system prompt replaced by ``BARE_SYSTEM_PROMPT``, no settings or MCP
servers, no session file — run from a fresh empty temporary directory (so no
``CLAUDE.md``, project memory or repo file is in reach) with a trimmed child
environment (``_CHILD_ENV_KEYS``). ``bare_argv(model)`` is the command line.
An envelope reporting ``num_turns > 1`` is recorded (outcome ``multi_turn``),
logged at WARNING and rejected through the retry path; its JSON is never
returned. ``PB_SHIM_LEGACY=1`` (temporary, for one comparison run) restores
the old ``--max-turns 8`` command line with no cwd or env override, and
with it the old acceptance of multi-turn answers.
``python -m evals.harness.model_shim --smoke`` makes one paid bare call and
prints the envelope's figures.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time

try:
    import usage_ledger
except ImportError:                         # imported as evals.harness.model_shim
    from evals.harness import usage_ledger

logger = logging.getLogger(__name__)

MODEL = os.environ.get("PB_EVAL_MODEL", "claude-sonnet-4-6")
TIMEOUT = int(os.environ.get("PB_EVAL_TIMEOUT", "300"))


BARE_SYSTEM_PROMPT = (
    "You answer with one JSON object that matches the schema in the user "
    "message. No prose, no code fences, no tools."
)

# The only caller variables a bare call's child process receives: what the CLI
# and its authentication need (HOME locates the OAuth credentials). No PB_* and
# no CLAUDE_* variable passes.
_CHILD_ENV_KEYS = ("HOME", "PATH", "USER", "LANG", "LC_ALL", "TMPDIR",
                   "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")


class ModelShimError(RuntimeError):
    pass


class QuotaExhausted(ModelShimError):
    pass


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    if start == -1:
        raise ModelShimError(f"no JSON object in model output: {text[:200]!r}")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ModelShimError("unbalanced JSON in model output")


def _cli_result(stdout: str) -> tuple[str, dict | None, float | None]:
    """Split ``claude -p --output-format json`` output into (reply text,
    usage, cost). The envelope is the last JSON line of type ``result``;
    output without one is taken as plain reply text with no usage."""
    for line in reversed(stdout.strip().splitlines()):
        try:
            env = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(env, dict) and env.get("type") == "result":
            u = env.get("usage")
            usage = None if not isinstance(u, dict) else {
                "input_tokens": u.get("input_tokens"),
                "output_tokens": u.get("output_tokens"),
                "cache_read_tokens": u.get("cache_read_input_tokens"),
                "cache_write_tokens": u.get("cache_creation_input_tokens"),
            }
            cost = env.get("total_cost_usd")
            return (str(env.get("result") or ""), usage,
                    float(cost) if isinstance(cost, (int, float)) else None)
    return stdout, None, None


def _cli_extras(stdout: str) -> dict:
    """The envelope's own run figures (BUILD-PROFILE-V1): ``num_turns``,
    ``cli_duration_ms`` (``duration_ms``) and ``api_duration_ms``. A field the
    envelope lacks, or output with no envelope, gives ``None``."""
    for line in reversed(stdout.strip().splitlines()):
        try:
            env = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(env, dict) and env.get("type") == "result":
            def num(key: str):
                v = env.get(key)
                return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
            return {"num_turns": num("num_turns"), "cli_duration_ms": num("duration_ms"),
                    "api_duration_ms": num("duration_api_ms")}
    return {"num_turns": None, "cli_duration_ms": None, "api_duration_ms": None}


def bare_argv(model: str) -> list[str]:
    """The bare call's command line (BARE-CALL-V1): one turn, no tools, no
    settings or MCP servers, no session file, a fixed minimal system prompt."""
    return ["claude", "-p", "--model", model, "--output-format", "json",
            "--max-turns", "1", "--tools", "", "--strict-mcp-config",
            "--setting-sources", "", "--no-session-persistence",
            "--system-prompt", BARE_SYSTEM_PROMPT]


def _legacy() -> bool:
    return os.environ.get("PB_SHIM_LEGACY") == "1"


def _child_env() -> dict[str, str]:
    return {k: os.environ[k] for k in _CHILD_ENV_KEYS if k in os.environ}


def _invoke(full: str) -> subprocess.CompletedProcess:
    """One CLI invocation with ``full`` on stdin. Bare by default: a fresh empty
    temporary directory as cwd (removed afterwards on every path) and a trimmed
    environment. ``PB_SHIM_LEGACY=1`` runs the old command line as before."""
    if _legacy():
        return subprocess.run(
            ["claude", "-p", "--model", MODEL, "--max-turns", "8",
             "--output-format", "json"],
            input=full, capture_output=True, text=True, timeout=TIMEOUT)
    with tempfile.TemporaryDirectory(prefix="pb-bare-") as empty:
        return subprocess.run(
            bare_argv(MODEL), input=full, capture_output=True, text=True,
            timeout=TIMEOUT, cwd=empty, env=_child_env())


def claude_model(prompt: str, schema: dict) -> dict:
    """One model call: up to three attempts, each one bare call. Retries on a
    failed exit, a timeout, a multi-turn answer, or a JSON-parse failure."""
    full = (
        f"{prompt}\n\n"
        "Respond with ONLY a JSON object (no prose, no code fences) matching "
        f"this JSON Schema:\n{json.dumps(schema)}"
    )
    last_err: Exception | None = None
    for attempt in (1, 2, 3):
        if attempt > 1:
            time.sleep(15 * (attempt - 1))  # transient rate pressure backs off
        started, t0 = time.time(), time.perf_counter()
        try:
            proc = _invoke(full)
        except subprocess.TimeoutExpired as exc:
            usage_ledger.record("claude", MODEL, None, None, started=started,
                                latency_s=time.perf_counter() - t0, outcome="timeout",
                                prompt_chars=len(full), response_chars=0)  # spent, amount unknown
            last_err = exc
            logger.warning("model shim timeout (attempt %d)", attempt)
            continue
        # every completed invocation leaves a receipt, whatever its exit code
        latency = time.perf_counter() - t0
        text, usage, cost = _cli_result(proc.stdout)
        extras = _cli_extras(proc.stdout)
        turns = extras["num_turns"]
        multi_turn = (not _legacy() and proc.returncode == 0
                      and turns is not None and turns > 1)
        usage_ledger.record("claude", MODEL, usage, cost, started=started, latency_s=latency,
                            outcome=("multi_turn" if multi_turn
                                     else "ok" if proc.returncode == 0 else "error"),
                            prompt_chars=len(full), response_chars=len(text), **extras)
        if multi_turn:
            last_err = ModelShimError(f"claude reported num_turns={turns}; one turn expected")
            logger.warning("model shim multi-turn answer rejected (attempt %d): "
                           "num_turns=%s", attempt, turns)
            # the parse-failure path's counterpart: the retry says what was wrong
            full += ("\n\nYour previous reply took more than one turn. Answer in this "
                     "one reply with the JSON object ONLY.")
            continue
        if proc.returncode != 0:
            stdout_lower = proc.stdout.lower()
            if "hit your" in stdout_lower and "limit" in stdout_lower:
                raise QuotaExhausted(
                    f"claude quota exhausted: stderr={proc.stderr[:200]!r} "
                    f"stdout={proc.stdout[:200]!r}"
                )
            last_err = ModelShimError(
                f"claude exited {proc.returncode}: stderr={proc.stderr[:200]!r} "
                f"stdout={proc.stdout[:200]!r}"
            )
            logger.warning("model shim attempt %d failed: %s", attempt, last_err)
            continue
        try:
            return _extract_json(text)
        except (ModelShimError, json.JSONDecodeError) as exc:
            last_err = exc
            logger.warning("model shim parse failure (attempt %d): %s", attempt, exc)
            full += "\n\nYour previous reply was not valid JSON. JSON object ONLY."
    raise ModelShimError(f"model call failed after retries: {last_err}")


def get_model():
    """Provider switch (letter 020): PB_EVAL_PROVIDER=codex routes pipeline
    calls through the subscription-auth HTTP shim; default stays the CLI."""
    if os.environ.get("PB_EVAL_PROVIDER", "claude") == "codex":
        from codex_shim import MODEL as codex_model_name, codex_model
        return codex_model, f"codex:{codex_model_name}"
    return claude_model, MODEL


def _smoke() -> int:
    """One paid bare call (a few hundred tokens): prints the envelope's figures
    so a human can see the one-turn, no-tool shape hold. Run by hand only."""
    schema = {"type": "object", "properties": {"answer": {"type": "string"}},
              "required": ["answer"]}
    full = ("Reply with the word pong as the value of the field answer.\n"
            "Respond with ONLY a JSON object (no prose, no code fences) matching "
            f"this JSON Schema:\n{json.dumps(schema)}")
    proc = _invoke(full)
    text, usage, _cost = _cli_result(proc.stdout)
    extras = _cli_extras(proc.stdout)
    denials = None
    for line in reversed(proc.stdout.strip().splitlines()):
        try:
            env = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(env, dict) and env.get("type") == "result":
            denials = env.get("permission_denials")
            break
    print(f"exit={proc.returncode} reply={text.strip()[:80]!r}")
    print(f"num_turns={extras['num_turns']} duration_api_ms={extras['api_duration_ms']} "
          f"duration_ms={extras['cli_duration_ms']}")
    u = usage or {}
    print(f"input_tokens={u.get('input_tokens')} output_tokens={u.get('output_tokens')}")
    print(f"tool_use_reported={'n/a' if denials is None else bool(denials)} "
          "(a tool-less single turn has num_turns=1)")
    return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
    if "--smoke" in sys.argv[1:]:
        sys.exit(_smoke())
    print("usage: python -m evals.harness.model_shim --smoke", file=sys.stderr)
    sys.exit(2)
