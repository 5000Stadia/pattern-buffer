"""Codex-auth HTTP shim: (prompt, schema) -> json over the ChatGPT
consumer backend (letter 020, Path A).

Pattern copied from the Kernos reference implementation
(kernos/providers/codex_provider.py) — copied, never imported: the
engine-neutrality rule is about coupling, not prior art. Every body
field below is load-bearing per that file's wire-shape invariants;
this shim stays far under the ~40KB payload cliff by construction
(compact line-grammar prompts).

Operational rules (letters 020/021): credentials are read fresh from
~/.codex/auth.json each call; a 401 fails fast and loud ("run codex
login"), never retry-spins; every call is wall-clock bounded.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MODEL = os.environ.get("PB_CODEX_MODEL", "gpt-5.5")
TIMEOUT = int(os.environ.get("PB_EVAL_TIMEOUT", "600"))
_AUTH_PATH = Path(os.environ.get("CODEX_AUTH_PATH", str(Path.home() / ".codex" / "auth.json")))
_URL = os.environ.get("PB_CODEX_BASE_URL", "https://chatgpt.com/backend-api") + "/codex/responses"
_RUN_CACHE_KEY = f"pattern-buffer-{uuid.uuid4().hex[:12]}"

_INSTRUCTIONS = (
    "You are a precise extraction component inside a data pipeline. Follow "
    "the task in the user message exactly; output ONLY what its schema "
    "demands — no preamble, no commentary."
)


class CodexShimError(RuntimeError):
    pass


class CodexAuthError(CodexShimError):
    """401 from the backend: the founder needs to run `codex login`."""


def _strict_object_schema(schema: Any) -> Any:
    """Every type:object level must carry additionalProperties:false
    (backend requirement, 2026-05-22 tightening). Returns a new dict."""
    if isinstance(schema, list):
        return [_strict_object_schema(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    out = dict(schema)
    if out.get("type") == "object":
        out["additionalProperties"] = False
        if isinstance(out.get("properties"), dict):
            out["properties"] = {k: _strict_object_schema(v) for k, v in out["properties"].items()}
        # The backend also requires every property to be listed in `required`.
        if isinstance(out.get("properties"), dict):
            out.setdefault("required", sorted(out["properties"].keys()))
    if out.get("type") == "array" and "items" in out:
        out["items"] = _strict_object_schema(out["items"])
    for key in ("oneOf", "anyOf", "allOf"):
        if isinstance(out.get(key), list):
            out[key] = [_strict_object_schema(b) for b in out[key]]
    for key in ("$defs", "definitions"):
        if isinstance(out.get(key), dict):
            out[key] = {k: _strict_object_schema(v) for k, v in out[key].items()}
    return out


def _credentials() -> tuple[str, str]:
    """Read the LIVE auth file fresh (derived copies go stale — Kernos ops)."""
    try:
        raw = json.loads(_AUTH_PATH.read_text())
        tokens = raw["tokens"]
        return tokens["access_token"], tokens["account_id"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise CodexAuthError(
            f"cannot read codex credentials at {_AUTH_PATH}: {exc}; "
            "the founder needs to run `codex login`"
        ) from exc


def codex_model(prompt: str, schema: dict) -> dict:
    """One schema-constrained model call. Bounded; one transient retry."""
    last_err: Exception | None = None
    for attempt in (1, 2):
        if attempt > 1:
            time.sleep(10)
        try:
            return _call_once(prompt, schema)
        except CodexAuthError:
            raise  # fail fast and loud, never retry-spin (letter 020)
        except CodexShimError as exc:
            last_err = exc
            logger.warning("codex shim attempt %d failed: %s", attempt, exc)
    raise CodexShimError(f"codex call failed after retry: {last_err}")


def _call_once(prompt: str, schema: dict) -> dict:
    access_token, account_id = _credentials()
    body = {
        "model": MODEL,
        "instructions": _INSTRUCTIONS,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        "store": False,           # REQUIRED: persistence overhead tips large payloads
        "stream": True,           # REQUIRED: endpoint is SSE-only
        "include": ["reasoning.encrypted_content"],  # REQUIRED for gpt-5.x
        "prompt_cache_key": _RUN_CACHE_KEY,
        "text": {"format": {"type": "json_schema", "name": "output",
                            "schema": _strict_object_schema(schema), "strict": True}},
    }
    if MODEL.startswith("gpt-5"):
        body["reasoning"] = {
            "effort": os.getenv("OPENAI_CODEX_REASONING_EFFORT", "medium"),
            "summary": "auto",
        }
    request_id = uuid.uuid4().hex
    req = urllib.request.Request(
        _URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {access_token}",
            "chatgpt-account-id": account_id,
            "originator": "pi",
            "User-Agent": "pattern-buffer-harness/0.1",
            "Content-Type": "application/json",
            "accept": "text/event-stream",
            "session_id": request_id,
            "x-client-request-id": request_id,
        },
        method="POST",
    )
    deadline = time.monotonic() + TIMEOUT
    try:
        resp = urllib.request.urlopen(req, timeout=min(TIMEOUT, 120))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise CodexAuthError("401 from backend — founder needs `codex login`") from exc
        raise CodexShimError(f"HTTP {exc.code}: {exc.read()[:300]!r}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CodexShimError(f"connection failed: {exc}") from exc

    final, deltas = None, []
    with resp:
        for raw_line in resp:
            if time.monotonic() > deadline:
                raise CodexShimError(f"SSE read exceeded {TIMEOUT}s bound")
            line = raw_line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            etype = event.get("type", "")
            if etype == "response.output_text.delta":
                deltas.append(event.get("delta", ""))
            elif etype in ("response.completed", "response.done"):
                final = event.get("response", event)
                break
            elif etype in ("response.failed", "error") or "server_error" in etype:
                raise CodexShimError(f"backend error event: {json.dumps(event)[:300]}")

    text = ""
    if final:
        for item in final.get("output", []):
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        text += part.get("text", "")
            elif item.get("type") == "output_text":
                text += item.get("text", "")
    if not text:
        text = "".join(deltas)
    if not text:
        raise CodexShimError("stream ended with no output text")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise CodexShimError(f"non-JSON output: {text[:200]!r}") from exc
