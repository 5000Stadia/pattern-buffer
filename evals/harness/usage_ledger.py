"""Token and cost receipts for graded runs (R27): every model call the shims
complete is counted here, so a build's receipt says what it spent.

Harness machinery, not engine code. Thread-safe: parallel pass-0 calls the
shims from worker threads. With ``PB_EVAL_USAGE_LOG`` set, each call is also
appended to that file as one JSON line.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Mapping

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


def record(provider: str, model: str, usage: Mapping[str, Any] | None,
           cost_usd: float | None = None) -> None:
    """Count one completed call. ``usage`` holds any of ``_FIELDS``; None
    means the provider reported nothing, which is counted, not guessed."""
    entry = {"t": time.time(), "provider": provider, "model": model,
             **{f: int((usage or {}).get(f) or 0) for f in _FIELDS},
             "cost_usd": cost_usd, "usage_reported": usage is not None}
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
