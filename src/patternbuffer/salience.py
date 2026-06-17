"""Projection-time salience: a rebuildable ranking sidecar.

Salience is derived from the assertion log and classifier sidecar. It is
cached for retrieval speed, but never authored into the log.
"""

from __future__ import annotations

import json
import math

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import STATE, Classifier
from patternbuffer.indexes import Indexes
from patternbuffer.model import ATTR_PREFIX, CANON, Assertion

SALIENCE_PARAMS = {
    "weights": {
        "recency": 0.40,
        "reference_frequency": 0.25,
        "reinforcement": 0.20,
        "delta_from_baseline": 0.15,
    },
    "ref_scale": 8.0,
    "reinf_scale": 8.0,
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sidecar_salience (
  entity             TEXT NOT NULL,
  frame              TEXT NOT NULL,
  as_of_key          TEXT NOT NULL,
  score              REAL NOT NULL,
  head               INTEGER NOT NULL,
  classifier_version INTEGER NOT NULL,
  PRIMARY KEY (entity, frame, as_of_key)
);
"""


class SalienceIndex:
    """Derived, disposable salience scores over the current log."""

    def __init__(
        self,
        buffer: PatternBuffer,
        classifier: Classifier,
        indexes: Indexes,
    ) -> None:
        self._buffer = buffer
        self._classifier = classifier
        self._indexes = indexes
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._buffer.raw_connection().executescript(_SCHEMA)
        self._buffer.raw_connection().commit()

    @staticmethod
    def _as_of_key(as_of: float | None) -> str:
        return json.dumps(as_of, sort_keys=True)

    def rebuild(self) -> None:
        """Drop cached scores; they will be recomputed on demand."""
        self._ensure_schema()
        self._buffer.raw_connection().execute("DELETE FROM sidecar_salience")
        self._buffer.raw_connection().commit()

    def salience(
        self,
        entity: str,
        frame: str = CANON,
        as_of: float | None = None,
    ) -> float:
        entity = self._indexes.resolve_entity(entity)
        head = self._buffer.head()
        version = self._classifier.version
        as_of_key = self._as_of_key(as_of)
        self._ensure_schema()
        row = self._buffer.raw_connection().execute(
            "SELECT score, head, classifier_version FROM sidecar_salience"
            " WHERE entity = ? AND frame = ? AND as_of_key = ?",
            (entity, frame, as_of_key),
        ).fetchone()
        if row is not None and int(row[1]) == head and int(row[2]) == version:
            return float(row[0])
        score = self._compute(entity, frame, as_of)
        self._buffer.raw_connection().execute(
            "INSERT OR REPLACE INTO sidecar_salience"
            " (entity, frame, as_of_key, score, head, classifier_version)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (entity, frame, as_of_key, score, head, version),
        )
        self._buffer.raw_connection().commit()
        return score

    def _visible_entity_rows(
        self, entity: str, frame: str, as_of: float | None
    ) -> list[Assertion]:
        closure = sorted(self._indexes._closure_of(entity))
        if not closure:
            return []
        return [
            row
            for row in self._buffer.visible(
                entity_in=closure, frame=frame, valid_as_of=as_of
            )
            if not row.entity.startswith(ATTR_PREFIX)
        ]

    def _compute(self, entity: str, frame: str, as_of: float | None) -> float:
        rows = self._visible_entity_rows(entity, frame, as_of)
        head = self._buffer.head()
        max_asserted = max((r.asserted_at for r in rows), default=0)
        recency = (max_asserted / head) if head else 0.0

        incoming = self._indexes.incoming_refs(entity, frame, as_of)
        ref_scale = SALIENCE_PARAMS["ref_scale"]
        reference_frequency = min(1.0, math.log1p(len(incoming)) / math.log1p(ref_scale))

        valid_times = {r.valid_from for r in rows}
        reinf_scale = SALIENCE_PARAMS["reinf_scale"]
        reinforcement = min(1.0, math.log1p(len(valid_times)) / math.log1p(reinf_scale))

        delta = self._delta_from_baseline(entity, rows, frame, as_of)

        weights = SALIENCE_PARAMS["weights"]
        return (
            weights["recency"] * recency
            + weights["reference_frequency"] * reference_frequency
            + weights["reinforcement"] * reinforcement
            + weights["delta_from_baseline"] * delta
        )

    def _delta_from_baseline(
        self,
        entity: str,
        rows: list[Assertion],
        frame: str,
        as_of: float | None,
    ) -> float:
        by_fold_attr: dict[str, list[Assertion]] = {}
        for row in rows:
            if (
                row.entity.startswith("a:")
                or row.value_type == "unresolved"
                or self._classifier.durability(row.id) != STATE
            ):
                continue
            by_fold_attr.setdefault(self._indexes.fold_attribute(row.attribute), []).append(row)
        if not by_fold_attr:
            return 0.0
        current = self._indexes.current_state(entity, frame, as_of)

        def recency_key(row: Assertion) -> tuple[float, int]:
            return (
                row.valid_from if row.valid_from is not None else float("-inf"),
                row.asserted_at,
            )

        for attr, attr_rows in by_fold_attr.items():
            result = current.get(attr)
            if result is None or result.winner is None:
                continue
            if self._classifier.durability(result.winner.id) != STATE:
                continue
            baseline = min(attr_rows, key=recency_key)
            if result.winner.id != baseline.id and recency_key(result.winner) > recency_key(baseline):
                return 1.0
        return 0.0
