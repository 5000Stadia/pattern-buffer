"""Test doubles for the engine's single outside dependency.

The engine takes one injected callable ``(prompt, schema) -> json`` at
World construction (whitepaper §17.1). ``StubModel`` is that callable
for tests: it replays canned responses and records every call, so tests
can assert both what the engine asked and that deterministic paths made
no model call at all.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class StubModelExhausted(AssertionError):
    """Raised when the engine makes a model call the test did not script."""


class StubModel:
    """A scripted ``(prompt, schema) -> json`` callable.

    Responses are returned in FIFO order. Every call is recorded in
    ``calls`` as ``(prompt, schema)`` tuples. An unscripted call raises
    ``StubModelExhausted`` — the no-LLM-on-deterministic-paths invariant
    (P7) is asserted by scripting zero responses.
    """

    def __init__(self, responses: list[Any] | None = None) -> None:
        self._responses: list[Any] = list(responses or [])
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def enqueue(self, response: Any) -> None:
        """Script one more response."""
        self._responses.append(response)

    def __call__(self, prompt: str, schema: dict[str, Any]) -> Any:
        self.calls.append((prompt, schema))
        if not self._responses:
            raise StubModelExhausted(
                f"unscripted model call (call #{len(self.calls)}): "
                f"{prompt[:120]!r}"
            )
        response = self._responses.pop(0)
        logger.debug("StubModel call #%d -> %r", len(self.calls), response)
        return response
