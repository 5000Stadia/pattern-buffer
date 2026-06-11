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

logger = logging.getLogger(__name__)

MODEL = os.environ.get("PB_EVAL_MODEL", "claude-sonnet-4-6")
TIMEOUT = int(os.environ.get("PB_EVAL_TIMEOUT", "300"))


class ModelShimError(RuntimeError):
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


def claude_model(prompt: str, schema: dict) -> dict:
    """One model call. Retries once on JSON-parse failure."""
    full = (
        f"{prompt}\n\n"
        "Respond with ONLY a JSON object (no prose, no code fences) matching "
        f"this JSON Schema:\n{json.dumps(schema)}"
    )
    last_err: Exception | None = None
    for attempt in (1, 2, 3):
        try:
            proc = subprocess.run(
                ["claude", "-p", "--model", MODEL, "--max-turns", "1"],
                input=full,
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            last_err = exc
            logger.warning("model shim timeout (attempt %d)", attempt)
            continue
        if proc.returncode != 0:
            last_err = ModelShimError(f"claude exited {proc.returncode}: {proc.stderr[:300]}")
            logger.warning("model shim attempt %d failed: %s", attempt, last_err)
            continue
        try:
            return _extract_json(proc.stdout)
        except (ModelShimError, json.JSONDecodeError) as exc:
            last_err = exc
            logger.warning("model shim parse failure (attempt %d): %s", attempt, exc)
            full += "\n\nYour previous reply was not valid JSON. JSON object ONLY."
    raise ModelShimError(f"model call failed after retries: {last_err}")
