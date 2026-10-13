"""The injected model callable for graded runs: a two-line-spirit shim
around the local `claude` CLI. (prompt, schema) -> parsed JSON.

This is harness machinery, not engine code — the engine knows only the
callable contract (whitepaper §17.1).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time

try:
    import usage_ledger
except ImportError:                         # imported as evals.harness.model_shim
    from evals.harness import usage_ledger

logger = logging.getLogger(__name__)

MODEL = os.environ.get("PB_EVAL_MODEL", "claude-sonnet-4-6")
TIMEOUT = int(os.environ.get("PB_EVAL_TIMEOUT", "300"))


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


def claude_model(prompt: str, schema: dict) -> dict:
    """One model call. Retries once on JSON-parse failure."""
    full = (
        f"{prompt}\n\n"
        "Respond with ONLY a JSON object (no prose, no code fences) matching "
        f"this JSON Schema:\n{json.dumps(schema)}"
    )
    last_err: Exception | None = None
    for attempt in (1, 2, 3):
        if attempt > 1:
            time.sleep(15 * (attempt - 1))  # transient rate pressure backs off
        try:
            proc = subprocess.run(
                ["claude", "-p", "--model", MODEL, "--max-turns", "8",
                 "--output-format", "json"],
                input=full,
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            usage_ledger.record("claude", MODEL, None, None)   # spent, amount unknown
            last_err = exc
            logger.warning("model shim timeout (attempt %d)", attempt)
            continue
        # every completed invocation leaves a receipt, whatever its exit code
        text, usage, cost = _cli_result(proc.stdout)
        usage_ledger.record("claude", MODEL, usage, cost)
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
