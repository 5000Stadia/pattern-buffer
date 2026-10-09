"""Suite-wide checks shared by every test module.

GATE-AUTHORITY-V1 §0: every skip the gate records carries a fixed reason code
from ``ingest.SKIP_REASONS``, or one of the three legacy prose forms the spec
keeps byte-identical (tests and hosts match substrings of them). The check
runs around every test in the suite, so a new skip path that invents a reason
fails the test that first reaches it.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest

from patternbuffer.ingest import SKIP_REASONS, Ingestor

# The per-edge structural reasons stay prose (GATE-AUTHORITY-V1 §0).
LEGACY_SKIP_PREFIXES = (
    "cycle-forming containment edge: ",
    "lateral self-loop: ",
    "merged_self_edge: ",
)


def is_skip_code(reason: Any) -> bool:
    """Whether a recorded skip reason is in the gate's vocabulary."""
    return isinstance(reason, str) and (
        reason in SKIP_REASONS or reason.startswith(LEGACY_SKIP_PREFIXES))


@pytest.fixture
def skip_reason_is_code() -> Callable[[Any], bool]:
    """The vocabulary predicate the suite-wide check applies."""
    return is_skip_code


@pytest.fixture(autouse=True)
def _skip_reasons_are_codes(monkeypatch: pytest.MonkeyPatch):
    """Record every skip reason a test makes the gate write; fail the test
    if any is outside the vocabulary (GATE-AUTHORITY-V1 §0)."""
    recorded: list[Any] = []
    original = Ingestor._record_skip

    def recording(self, entity, attribute, value, reason, detail=None):
        recorded.append(reason)
        return original(self, entity, attribute, value, reason, detail)

    monkeypatch.setattr(Ingestor, "_record_skip", recording)
    yield
    unknown = [r for r in recorded if not is_skip_code(r)]
    assert not unknown, f"skip reason(s) outside SKIP_REASONS: {unknown!r}"
