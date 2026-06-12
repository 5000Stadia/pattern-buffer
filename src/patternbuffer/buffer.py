"""PatternBuffer: the append-only assertion log — the only truth (P1).

One SQLite file per world, and ``world_id`` stamped on every row as a
cross-wiring guard (the 1:1 invariant, spec §3.1/§4). Append-only is
enforced twice: the Python surface exposes no update/delete, and SQL
triggers raise on UPDATE/DELETE as belt-and-braces against future code.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from patternbuffer.model import CANON, STATUSES, VALUE_TYPES, Assertion
from patternbuffer.roles import WriterRole

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS world_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assertions (
  seq         INTEGER PRIMARY KEY,
  id          TEXT UNIQUE NOT NULL,
  world_id    TEXT NOT NULL,
  entity      TEXT NOT NULL,
  attribute   TEXT NOT NULL,
  value_type  TEXT NOT NULL,
  value       TEXT NOT NULL,
  valid_from  REAL,
  valid_to    REAL,
  frame       TEXT NOT NULL DEFAULT 'canon',
  status      TEXT NOT NULL,
  confidence  REAL,
  asserted_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_assertions_key
  ON assertions (entity, attribute, frame);
CREATE INDEX IF NOT EXISTS ix_assertions_attr_value
  ON assertions (attribute, value);
CREATE INDEX IF NOT EXISTS ix_assertions_frame
  ON assertions (frame, attribute);
CREATE TRIGGER IF NOT EXISTS assertions_append_only_update
  BEFORE UPDATE ON assertions
  BEGIN SELECT RAISE(ABORT, 'append-only: UPDATE forbidden'); END;
CREATE TRIGGER IF NOT EXISTS assertions_append_only_delete
  BEFORE DELETE ON assertions
  BEGIN SELECT RAISE(ABORT, 'append-only: DELETE forbidden'); END;
"""


class WorldMismatch(ValueError):
    """A buffer was opened or written with the wrong world_id (1:1 invariant)."""


class PatternBuffer:
    """The append-only store. Holds exactly one world's log, forever."""

    def __init__(self, path: str | Path, world_id: str) -> None:
        self.path = Path(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.executescript(_SCHEMA)
        existing = self._meta("world_id")
        if existing is None:
            self._conn.execute(
                "INSERT INTO world_meta (key, value) VALUES ('world_id', ?)", (world_id,)
            )
            self._conn.commit()
        elif existing != world_id:
            self._conn.close()
            raise WorldMismatch(
                f"buffer at {self.path} belongs to world {existing!r}, not {world_id!r}"
            )
        self.world_id = world_id
        self.rows_read = 0  # deserialization counter (read-path scaling guard, 037)

    def _meta(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM world_meta WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    # ---------------------------------------------------------------- write

    def append(
        self,
        *,
        entity: str,
        attribute: str,
        value: Any,
        role: WriterRole,
        status: str,
        value_type: str = "literal",
        valid_from: float | None = None,
        valid_to: float | None = None,
        frame: str = CANON,
        confidence: float | None = None,
    ) -> Assertion:
        """Append one assertion. The only write path that exists."""
        role.check(status)
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}")
        if value_type not in VALUE_TYPES:
            raise ValueError(f"unknown value_type {value_type!r}")
        seq = self.head() + 1
        row = Assertion(
            seq=seq,
            id=f"a:{seq}",
            world_id=self.world_id,
            entity=entity,
            attribute=attribute,
            value_type=value_type,
            value=value,
            valid_from=valid_from,
            valid_to=valid_to,
            frame=frame,
            status=status,
            confidence=confidence,
            asserted_at=seq,
        )
        self._insert(row)
        return row

    def _insert(self, row: Assertion) -> None:
        if row.world_id != self.world_id:
            raise WorldMismatch(
                f"assertion stamped for world {row.world_id!r} cannot enter "
                f"buffer of world {self.world_id!r}"
            )
        self._conn.execute(
            "INSERT INTO assertions (seq, id, world_id, entity, attribute, value_type,"
            " value, valid_from, valid_to, frame, status, confidence, asserted_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row.seq,
                row.id,
                row.world_id,
                row.entity,
                row.attribute,
                row.value_type,
                json.dumps(row.value, sort_keys=True),
                row.valid_from,
                row.valid_to,
                row.frame,
                row.status,
                row.confidence,
                row.asserted_at,
            ),
        )
        self._conn.commit()
        logger.debug("append %s: (%s · %s)", row.id, row.entity, row.attribute)

    # ----------------------------------------------------------------- read

    def head(self) -> int:
        """The current log head (last seq; 0 for an empty log)."""
        row = self._conn.execute("SELECT COALESCE(MAX(seq), 0) FROM assertions").fetchone()
        return int(row[0])

    def get(self, assertion_id: str) -> Assertion | None:
        rows = self._select("WHERE id = ?", (assertion_id,))
        return rows[0] if rows else None

    def all_rows(self) -> list[Assertion]:
        """The full log in append order (dump/rebuild substrate)."""
        return self._select("", ())

    def visible(
        self,
        *,
        entity: str | None = None,
        entity_in: list[str] | None = None,
        entity_prefix: str | None = None,
        attribute: str | None = None,
        attribute_in: list[str] | None = None,
        value: Any | None = None,
        frame: str | None = None,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> list[Assertion]:
        """Rows visible at ``(valid_as_of, asserted_as_of)`` — spec §4.2.

        Visibility is class-blind; which visible row a fold serves is
        durability-dependent and lives in the derived indexes, not here.
        Omitted bounds mean no bound (now / log head). Retraction
        meta-rows themselves are excluded from folds, and a row is
        invisible once a ``retracts`` row targeting it is itself visible
        on the asserted axis.
        """
        aao = self.head() if asserted_as_of is None else asserted_as_of
        clauses = ["a.asserted_at <= ?", "a.status != 'retracted'"]
        params: list[Any] = [aao]
        if entity is not None:
            clauses.append("a.entity = ?")
            params.append(entity)
        if entity_in is not None:
            clauses.append(f"a.entity IN ({','.join('?' * len(entity_in))})")
            params.extend(entity_in)
        if entity_prefix is not None:
            clauses.append("a.entity LIKE ?")
            params.append(entity_prefix + "%")
        if attribute is not None:
            clauses.append("a.attribute = ?")
            params.append(attribute)
        if attribute_in is not None:
            clauses.append(f"a.attribute IN ({','.join('?' * len(attribute_in))})")
            params.extend(attribute_in)
        if value is not None:
            clauses.append("a.value = ?")
            params.append(json.dumps(value, sort_keys=True))
        if frame is not None:
            clauses.append("a.frame = ?")
            params.append(frame)
        if valid_as_of is not None:
            clauses.append("(a.valid_from IS NULL OR a.valid_from <= ?)")
            params.append(valid_as_of)
            clauses.append("(a.valid_to IS NULL OR a.valid_to > ?)")
            params.append(valid_as_of)
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM assertions r"
            " WHERE r.entity = a.id AND r.attribute = 'retracts' AND r.asserted_at <= ?)"
        )
        params.append(aao)
        return self._select("WHERE " + " AND ".join(clauses), tuple(params))

    def _select(self, where: str, params: tuple) -> list[Assertion]:
        cur = self._conn.execute(
            "SELECT seq, id, world_id, entity, attribute, value_type, value,"
            " valid_from, valid_to, frame, status, confidence, asserted_at"
            f" FROM assertions a {where} ORDER BY seq",
            params,
        )
        out = [
            Assertion(
                seq=r[0],
                id=r[1],
                world_id=r[2],
                entity=r[3],
                attribute=r[4],
                value_type=r[5],
                value=json.loads(r[6]),
                valid_from=r[7],
                valid_to=r[8],
                frame=r[9],
                status=r[10],
                confidence=r[11],
                asserted_at=r[12],
            )
            for r in cur.fetchall()
        ]
        self.rows_read += len(out)
        return out

    # ------------------------------------------------------------- plumbing

    def raw_connection(self) -> sqlite3.Connection:
        """For tests asserting the triggers; never used by engine code."""
        return self._conn

    def close(self) -> None:
        self._conn.close()
