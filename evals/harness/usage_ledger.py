"""Token and cost receipts for graded runs (R27): every model call the shims
complete is counted here, so a build's receipt says what it spent.

Harness machinery, not engine code. Thread-safe: parallel pass-0 calls the
shims from worker threads. With ``PB_EVAL_USAGE_LOG`` set, each call is also
appended to that file as one JSON line.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

logger = logging.getLogger(__name__)

_FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
_lock = threading.Lock()
_totals: dict[str, Any] = {}


def reset() -> None:
    """Start a new receipt (a runner calls this before each build)."""
    with _lock:
        _totals.clear()
        _totals.update({"calls": 0, "calls_without_usage": 0, "cost_usd": 0.0,
                        "cost_known": True, **{f: 0 for f in _FIELDS}})


reset()

# BUILD-PROFILE-V1: which stage, unit and attempt a call served. A contextvar,
# so a worker thread sees the label only through a copied context.
_NO_LABEL: dict[str, Any] = {"stage": None, "unit": None, "attempt": None}
_label: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "usage_label", default=_NO_LABEL)


@contextmanager
def label(*, stage: str | None = None, unit: str | None = None,
          attempt: int | None = None) -> Iterator[None]:
    """Label every ``record`` made inside this block. A field left ``None``
    keeps the enclosing label's value, so a unit's label can gain its attempt
    number without restating the stage and unit."""
    current = _label.get()
    token = _label.set({"stage": current["stage"] if stage is None else stage,
                        "unit": current["unit"] if unit is None else unit,
                        "attempt": current["attempt"] if attempt is None else attempt})
    try:
        yield
    finally:
        _label.reset(token)


def current_label() -> dict[str, Any]:
    """The label in force here (``stage`` is None outside any label)."""
    return dict(_label.get())


def record(provider: str, model: str, usage: Mapping[str, Any] | None,
           cost_usd: float | None = None, *, started: float | None = None,
           latency_s: float | None = None, outcome: str | None = None,
           prompt_chars: int | None = None, response_chars: int | None = None,
           num_turns: int | None = None, cli_duration_ms: float | None = None,
           api_duration_ms: float | None = None, effort: str | None = None) -> None:
    """Count one completed call. ``usage`` holds any of ``_FIELDS``; None
    means the provider reported nothing, which is counted, not guessed.

    The keyword fields are the call's profile (BUILD-PROFILE-V1): ``started``
    (epoch seconds), ``latency_s``, ``outcome`` (``ok``, ``timeout``,
    ``error``, ``multi_turn`` or ``parse_failure``; BARE-CALL-V1), the prompt
    and response sizes, and the claude CLI's own ``num_turns`` and durations. Each is ``None`` when the caller did not
    measure it. ``effort`` (STAGE-MODELS-V1) is the ``--effort`` the call ran at;
    ``None`` is the CLI's default. The current ``label`` is written beside them. None of them
    touches ``snapshot()``."""
    lab = _label.get()
    entry = {"t": time.time(), "started": started, "latency_s": latency_s,
             "provider": provider, "model": model,
             "stage": lab["stage"], "unit": lab["unit"], "attempt": lab["attempt"],
             "outcome": outcome,
             **{f: int((usage or {}).get(f) or 0) for f in _FIELDS},
             "cost_usd": cost_usd, "usage_reported": usage is not None,
             "prompt_chars": prompt_chars, "response_chars": response_chars,
             "num_turns": num_turns, "cli_duration_ms": cli_duration_ms,
             "api_duration_ms": api_duration_ms, "effort": effort}
    with _lock:
        _totals["calls"] += 1
        if usage is None:
            _totals["calls_without_usage"] += 1
        for f in _FIELDS:
            _totals[f] += entry[f]
        if cost_usd is None:
            _totals["cost_known"] = False
        else:
            _totals["cost_usd"] += float(cost_usd)
        path = os.environ.get("PB_EVAL_USAGE_LOG")
        if path:
            try:
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\n")
            except OSError as exc:
                logger.warning("usage log not written: %s", exc)


def snapshot() -> dict[str, Any]:
    """The receipt so far. ``cost_usd`` is a lower bound when ``cost_known``
    is False (a provider, such as the Codex subscription, reports no price)."""
    with _lock:
        return dict(_totals)
