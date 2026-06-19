"""Test doubles for the engine's single outside dependency.

The engine takes one injected callable ``(prompt, schema) -> json`` at
World construction (whitepaper §17.1). ``StubModel`` is that callable
for tests: it replays canned responses and records every call, so tests
can assert both what the engine asked and that deterministic paths made
no model call at all.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

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

    def __init__(
        self,
        responses: list[Any] | None = None,
        fallback: "Callable[[str, dict[str, Any]], Any] | None" = None,
    ) -> None:
        self._responses: list[Any] = list(responses or [])
        self._fallback = fallback
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def enqueue(self, response: Any) -> None:
        """Script one more response."""
        self._responses.append(response)

    def __call__(self, prompt: str, schema: dict[str, Any]) -> Any:
        self.calls.append((prompt, schema))
        if self._responses:
            response = self._responses.pop(0)
            logger.debug("StubModel call #%d -> %r", len(self.calls), response)
            return response
        if self._fallback is not None:
            return self._fallback(prompt, schema)
        raise StubModelExhausted(
            f"unscripted model call (call #{len(self.calls)}): "
            f"{prompt[:120]!r}"
        )


def rule_classifier_fallback(movable_prefixes: tuple[str, ...] = ("obj:",)):
    """A deterministic classify-fallback for tests: places and furniture
    are structure; everything else movable is STATE. Raises on non-classify
    prompts so unscripted extraction/resolution still fails loudly."""

    def _durability(subject: str) -> str:
        if subject.startswith("place:") or subject.split(":")[-1] in {"desk", "drawer"}:
            return "CONSTITUTIVE"
        return "STATE"

    def fallback(prompt: str, schema: dict[str, Any]) -> Any:
        if not prompt.startswith("Classify the lifetime"):
            raise StubModelExhausted(f"unscripted non-classify call: {prompt[:80]!r}")
        # Batch path (INGEST-HARDENING-V1): the schema asks for `verdicts` and the
        # prompt lists facts as "N. entity · attribute · value".
        if "verdicts" in schema.get("properties", {}):
            verdicts = []
            for line in prompt.splitlines():
                m = re.match(r"\s*(\d+)\.\s+(\S+)\s+·", line)
                if m:
                    verdicts.append({
                        "index": int(m.group(1)),
                        "durability": _durability(m.group(2)),
                        "class_confidence": 0.9,
                    })
            return {"verdicts": verdicts}
        # Per-row path.
        subject = ""
        for line in prompt.splitlines():
            if line.startswith("Subject: "):
                subject = line.removeprefix("Subject: ")
        return {"durability": _durability(subject), "class_confidence": 0.9}

    return fallback
