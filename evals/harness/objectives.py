"""BUILD-PROFILE-V1 §2: objectives, the units of work a build needs accepted,
written one line each to ``RUN_DIR/objectives.jsonl`` with one record per
attempt. Observation only: nothing here decides, retries or changes a result.

An objective is a pass-0 segment (glean rounds are its later attempts), a
pass-1 chunk (attempts 1 and 2), an escape repair, a classification batch, a
merge-gate batch or the audit. ``usage.jsonl`` stays calls only, so the
receipt never sees these lines.

Harness machinery, not engine code. Thread-safe: pass-1 chunks settle from
worker threads.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

try:
    import usage_ledger
except ImportError:                         # imported as evals.harness.objectives
    from evals.harness import usage_ledger

logger = logging.getLogger(__name__)

OBJECTIVES_FILE = "objectives.jsonl"
OUTCOMES = ("accepted", "rejected", "timeout", "error")


def outcome_for(exc: BaseException) -> str:
    """``timeout`` for an exception that names a timeout, else ``error``."""
    text = f"{type(exc).__name__} {exc}".lower()
    return "timeout" if "timeout" in text or "timed out" in text else "error"


class ObjectiveLog:
    """Append-only writer for one run's ``objectives.jsonl``."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def write(self, line: dict[str, Any]) -> None:
        with self._lock:
            try:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(line, sort_keys=True) + "\n")
            except OSError as exc:
                logger.warning("objective log not written: %s", exc)


class Attempt:
    """One attempt's verdict. Left alone it is ``accepted``; the caller marks a
    ``reject`` or a ``fail``; an exception leaving the block is a ``fail``."""

    def __init__(self, number: int) -> None:
        self.number, self.outcome, self.reason = number, "accepted", None
        self.started, self.seconds = time.time(), 0.0

    def reject(self, reason: str) -> None:
        self.outcome, self.reason = "rejected", reason

    def fail(self, exc: BaseException) -> None:
        self.outcome, self.reason = outcome_for(exc), str(exc)

    def record(self) -> dict[str, Any]:
        return {"attempt": self.number, "started": round(self.started, 3),
                "seconds": round(self.seconds, 3), "outcome": self.outcome,
                "reason": self.reason}


class Objective:
    """The attempts of one unit. ``log`` may be None: the labels still apply
    and nothing is written."""

    def __init__(self, log: ObjectiveLog | None, stage: str, unit: str) -> None:
        self.log, self.stage, self.unit = log, stage, unit
        self.attempts: list[Attempt] = []
        self._t0: float | None = None

    @contextmanager
    def attempt(self, number: int) -> Iterator[Attempt]:
        """Label and time one attempt (its model calls plus the caller's parse
        and check). The block may ``continue`` or ``return``; an exception
        escaping it is recorded as the attempt's failure and propagates."""
        at = Attempt(number)
        t = time.perf_counter()
        if self._t0 is None:
            self._t0 = t
        self.attempts.append(at)
        try:
            with usage_ledger.label(stage=self.stage, unit=self.unit, attempt=number):
                yield at
        except BaseException as exc:
            at.fail(exc)
            raise
        finally:
            at.seconds = time.perf_counter() - t

    def settle(self) -> None:
        if self.log is None or not self.attempts:
            return
        total = time.perf_counter() - (self._t0 or time.perf_counter())
        self.log.write({"stage": self.stage, "unit": self.unit,
                        "accepted": self.attempts[-1].outcome == "accepted",
                        "seconds": round(total, 3),
                        "attempts": [a.record() for a in self.attempts]})


@contextmanager
def track(log: ObjectiveLog | None, stage: str, unit: str) -> Iterator[Objective]:
    """One objective: its line is written when the block ends, normally or not."""
    obj = Objective(log, stage, unit)
    try:
        with usage_ledger.label(stage=stage, unit=unit):
            yield obj
    finally:
        obj.settle()


class ObjectiveModel:
    """A model callable whose every call is one objective with one attempt.

    ``kind`` names the unit: ``kind:NN`` numbered in call order within the
    stage, or just ``kind`` when ``numbered`` is False (the audit). The stage is
    ``stage`` when given, else the label in force at the call, else
    ``default_stage``. Attributes the engine reads off a model (``identity``,
    ``model_id``) pass through. A call that returns is ``accepted`` (whether the
    caller later uses the answer is not this wrapper's business); one that
    raises is a failed attempt and re-raises."""

    def __init__(self, model: Callable[[str, dict], Any], log: ObjectiveLog | None,
                 kind: str, *, stage: str | None = None, default_stage: str = "commit",
                 numbered: bool = True) -> None:
        self._model, self._log, self._kind = model, log, kind
        self._stage, self._default_stage, self._numbered = stage, default_stage, numbered
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__") or name in ("_model", "_log"):
            raise AttributeError(name)
        return getattr(self._model, name)

    def __call__(self, prompt: str, schema: dict) -> Any:
        stage = self._stage or usage_ledger.current_label()["stage"] or self._default_stage
        unit = self._kind
        if self._numbered:
            with self._lock:
                n = self._counts[stage] = self._counts.get(stage, 0) + 1
            unit = f"{self._kind}:{n:02d}"
        with track(self._log, stage, unit) as obj, obj.attempt(1):
            return self._model(prompt, schema)
