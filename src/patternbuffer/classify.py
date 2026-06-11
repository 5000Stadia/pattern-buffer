"""The durability classifier and its rebuildable sidecar (whitepaper §5).

Durability is an index, not truth (P1): the class is a judgment about a
fact, keyed by assertion id, living in a sidecar table that can be
dropped and re-derived from the untouched log at any time. Deterministic
guardrails run first and short-circuit; the injected model judges only
what they leave ambiguous, under asymmetric-cost defaults.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from patternbuffer.buffer import PatternBuffer
from patternbuffer.model import CONTAINMENT_FAMILY, META_ATTRIBUTES, Assertion

logger = logging.getLogger(__name__)

CONSTITUTIVE = "CONSTITUTIVE"
DISPOSITIONAL = "DISPOSITIONAL"
STATE = "STATE"
EVENT = "EVENT"
DURABILITIES = frozenset({CONSTITUTIVE, DISPOSITIONAL, STATE, EVENT})

# Review threshold: low-confidence CONSTITUTIVE verdicts silently corrupt
# every future materialization (whitepaper §5.1), so they are flagged.
_REVIEW_FLOOR = 0.6

_SIDECAR_SCHEMA = """
CREATE TABLE IF NOT EXISTS sidecar_classification (
  assertion_id     TEXT PRIMARY KEY,
  durability       TEXT NOT NULL,
  class_confidence REAL NOT NULL,
  needs_review     INTEGER NOT NULL DEFAULT 0
);
"""

_MODEL_SCHEMA = {
    "type": "object",
    "properties": {
        "durability": {"enum": sorted(DURABILITIES)},
        "class_confidence": {"type": "number"},
    },
    "required": ["durability", "class_confidence"],
}


@dataclass(frozen=True, slots=True)
class Classification:
    assertion_id: str
    durability: str
    class_confidence: float
    needs_review: bool


class Classifier:
    """classify(assertion, world_context) -> {durability, class_confidence}.

    Writes the sidecar only — never the log (role matrix §12).
    """

    def __init__(self, buffer: PatternBuffer, model: Callable[[str, dict], Any]) -> None:
        self._buffer = buffer
        self._model = model
        buffer.raw_connection().executescript(_SIDECAR_SCHEMA)

    # ------------------------------------------------------------ judgment

    def _guardrails(self, row: Assertion) -> tuple[str, float] | None:
        """Deterministic short-circuits. Return None to defer to the model."""
        if row.entity.startswith("event:") or row.attribute == "caused_by":
            return EVENT, 1.0
        if row.attribute in {"kind", "connects_to", "adjacent_to"}:
            return CONSTITUTIVE, 1.0
        if row.attribute in {"name", "alias"}:
            return CONSTITUTIVE, 0.95  # identity anchors
        if row.attribute in META_ATTRIBUTES:
            # Meta-assertions ride with their subject; they never fold as
            # world facts. Classified EVENT-like for lens purposes: immutable.
            return EVENT, 1.0
        if row.value_type == "unresolved":
            return STATE, 1.0  # a thunk occupies its key like mutable state
        if row.attribute in CONTAINMENT_FAMILY:
            if row.attribute in {"held_by", "worn_by", "carried_by"}:
                return STATE, 0.95  # things held by agents are movable
            return None  # in/within: fixture vs movable is a judgment
        return None

    def classify(self, row: Assertion) -> Classification:
        verdict = self._guardrails(row)
        if verdict is not None:
            durability, confidence = verdict
        else:
            durability, confidence = self._ask_model(row)
        needs_review = durability == CONSTITUTIVE and confidence < _REVIEW_FLOOR
        c = Classification(row.id, durability, confidence, needs_review)
        self._store(c)
        return c

    def _ask_model(self, row: Assertion) -> tuple[str, float]:
        prompt = (
            "Classify the lifetime of this fact about a world.\n"
            f"Subject: {row.entity}\nAttribute: {row.attribute}\n"
            f"Value: {json.dumps(row.value)}\n\n"
            "CONSTITUTIVE: what the thing IS (identity, structure, fixtures, era). "
            "True at every moment unless the world is re-authored.\n"
            "DISPOSITIONAL: what it TENDS to be (habits, roles, recurring behavior). "
            "Generally true but defeasible.\n"
            "STATE: what it is RIGHT NOW (positions of movables, moods, conditions). "
            "One event could flip it.\n"
            "EVENT: what HAPPENED (an occurrence at a time).\n\n"
            "The mutability test resolves most ambiguity: could one event flip this "
            "without re-authoring the world? -> STATE. Asymmetric defaults: an "
            "ambiguous property is STATE; ambiguous fixture containment is "
            "CONSTITUTIVE."
        )
        try:
            out = self._model(prompt, _MODEL_SCHEMA)
            durability = out["durability"]
            confidence = float(out["class_confidence"])
            if durability not in DURABILITIES:
                raise ValueError(durability)
        except Exception:
            logger.exception("classifier model call failed for %s; defaulting", row.id)
            # Asymmetric default: ambiguous property -> STATE, except
            # in/within containment, which defaults CONSTITUTIVE.
            if row.attribute in {"in", "within"}:
                return CONSTITUTIVE, 0.5
            return STATE, 0.5
        return durability, confidence

    # ------------------------------------------------------------- sidecar

    def _store(self, c: Classification) -> None:
        self._buffer.raw_connection().execute(
            "INSERT OR REPLACE INTO sidecar_classification"
            " (assertion_id, durability, class_confidence, needs_review)"
            " VALUES (?, ?, ?, ?)",
            (c.assertion_id, c.durability, c.class_confidence, int(c.needs_review)),
        )
        self._buffer.raw_connection().commit()

    def set(self, assertion_id: str, durability: str, confidence: float = 1.0) -> None:
        """Judgment injection for components that hold the world context
        (e.g. the resolver knows invented contents are movables). Sidecar
        only — the log is untouched, and rebuild() re-derives."""
        if durability not in DURABILITIES:
            raise ValueError(durability)
        self._store(Classification(assertion_id, durability, confidence, False))

    def get(self, assertion_id: str) -> Classification | None:
        r = self._buffer.raw_connection().execute(
            "SELECT assertion_id, durability, class_confidence, needs_review"
            " FROM sidecar_classification WHERE assertion_id = ?",
            (assertion_id,),
        ).fetchone()
        return Classification(r[0], r[1], r[2], bool(r[3])) if r else None

    def durability(self, assertion_id: str) -> str:
        """The fold's view. Unclassified rows read as STATE (conservative:
        a transient mistaken for structure decays; structure mistaken for
        transient gets flagged on contradiction) — classify_all() should
        leave none."""
        c = self.get(assertion_id)
        return c.durability if c else STATE

    def classify_all(self) -> int:
        """Classify every row not yet in the sidecar. Returns count."""
        done = 0
        for row in self._buffer.all_rows():
            if self.get(row.id) is None:
                self.classify(row)
                done += 1
        return done

    def rebuild(self) -> int:
        """Drop the sidecar and re-derive it from the untouched log."""
        conn = self._buffer.raw_connection()
        conn.execute("DELETE FROM sidecar_classification")
        conn.commit()
        return self.classify_all()
