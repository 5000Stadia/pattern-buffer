"""Truth maintenance: conflict detection (derived) and retraction (log).

A fired flag is a sidecar row pointing at the assertions in tension —
both rows coexist in the log untouched (whitepaper §5.1/§7.2). The flag
stands until an explicit retraction/supersession resolves it; resolution
is never required for the flag to exist, and a silent merge is the
failure the chapter test's feature 8 exists to catch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import Classifier
from patternbuffer.indexes import Indexes, fold_attribute
from patternbuffer.model import SET_VALUED_ATTRIBUTES, Assertion
from patternbuffer.roles import WriterRole

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sidecar_conflicts (
  key_entity    TEXT NOT NULL,
  key_attribute TEXT NOT NULL,
  key_frame     TEXT NOT NULL,
  kind          TEXT NOT NULL,
  assertion_ids TEXT NOT NULL,
  PRIMARY KEY (key_entity, key_attribute, key_frame, kind)
);
"""


@dataclass(frozen=True, slots=True)
class Conflict:
    entity: str
    attribute: str
    frame: str
    kind: str  # 'constitutive_contradiction' | 'cross_source'
    assertion_ids: tuple[str, ...]


class TruthMaintenance:
    def __init__(
        self, buffer: PatternBuffer, classifier: Classifier, indexes: Indexes, role: WriterRole
    ) -> None:
        self._buffer = buffer
        self._classifier = classifier
        self._indexes = indexes
        self._role = role
        buffer.raw_connection().executescript(_SCHEMA)

    def scan(self) -> list[Conflict]:
        """Re-derive the conflict table from the log. Rebuildable: the
        table is dropped and refilled on every scan."""
        keys: set[tuple[str, str, str]] = set()
        for row in self._buffer.visible():
            if row.entity.startswith("a:") or row.attribute in SET_VALUED_ATTRIBUTES:
                continue
            keys.add(
                (
                    self._indexes._resolve(row.entity),
                    "in" if fold_attribute(row.attribute) == fold_attribute("in") else row.attribute,
                    row.frame,
                )
            )
        conflicts: list[Conflict] = []
        for entity, attribute, frame in sorted(keys):
            result = self._indexes.fold_key(entity, attribute, frame)
            if result.conflicted:
                kind = (
                    "constitutive_contradiction"
                    if result.winner is not None
                    and self._classifier.durability(result.winner.id) == "CONSTITUTIVE"
                    else "cross_source"
                )
                conflicts.append(
                    Conflict(entity, attribute, frame, kind, result.conflicting)
                )
        conn = self._buffer.raw_connection()
        conn.execute("DELETE FROM sidecar_conflicts")
        for c in conflicts:
            conn.execute(
                "INSERT OR REPLACE INTO sidecar_conflicts VALUES (?, ?, ?, ?, ?)",
                (c.entity, c.attribute, c.frame, c.kind, ",".join(c.assertion_ids)),
            )
        conn.commit()
        if conflicts:
            logger.info("truth maintenance: %d open conflict(s)", len(conflicts))
        return conflicts

    def open_conflicts(self) -> list[Conflict]:
        rows = self._buffer.raw_connection().execute(
            "SELECT key_entity, key_attribute, key_frame, kind, assertion_ids"
            " FROM sidecar_conflicts ORDER BY key_entity"
        ).fetchall()
        return [Conflict(r[0], r[1], r[2], r[3], tuple(r[4].split(","))) for r in rows]

    def retract(self, target: Assertion | str, reason: str) -> Assertion:
        """Append a retraction meta-assertion. The target survives in the
        log; folds exclude it from the retraction's asserted_at onward."""
        target_id = target if isinstance(target, str) else target.id
        return self._buffer.append(
            entity=target_id,
            attribute="retracts",
            value=reason,
            status="retracted",
            role=self._role,
        )
