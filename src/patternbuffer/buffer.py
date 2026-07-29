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

from patternbuffer.codec import decode_hook, json_default
from patternbuffer.model import (
    ATTR_PREFIX,
    CANON,
    INVIOLABLE_CORE,
    SEMANTICS_PREDICATES,
    STATUSES,
    VALUE_TYPES,
    Assertion,
)
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
CREATE INDEX IF NOT EXISTS ix_assertions_value
  ON assertions (value);
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


class PoisonedConnection(RuntimeError):
    """Raised by every later operation after a rollback-unconfirmable abort
    poisons the connection (ATOMIC-ACTIVATION-V1 §B1) — uncertain transaction
    state can never be finalized; only a fresh reopen recovers."""


# The DML/read opcode classes Pattern Buffer legitimately borrows; everything
# else (SAVEPOINT, ATTACH/DETACH, mutating PRAGMA, VACUUM, DDL) is denied by
# default for borrowed execution, and SQLITE_TRANSACTION is provenance-gated.
_ALLOWED_ACTIONS = frozenset({
    sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_INSERT,
    sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE, sqlite3.SQLITE_FUNCTION,
})


def _guarded_getattribute(allowed: frozenset):
    """Build a ``__getattribute__`` that enforces a REAL read allowlist: only the
    named public members and Python's own dunders resolve; every other attribute
    read — private slot, name-mangled spelling, arbitrary sqlite surface — raises
    AttributeError. Name mangling is renaming, not access control (pbr r2 A1); a
    borrowed holder must not reach the native handle by any attribute spelling."""
    def __getattribute__(self, name: str) -> Any:
        if name in allowed or (name.startswith("__") and name.endswith("__")):
            return object.__getattribute__(self, name)
        raise AttributeError(name)
    return __getattribute__


def _slot(obj: Any, name: str) -> Any:
    """Read a private slot past the allowlisting ``__getattribute__`` — internal
    use only (a module function, so it is not an attribute of the borrowed
    object; a borrowed holder cannot invoke it as ``proxy.<anything>``)."""
    return object.__getattribute__(obj, name)


_CURSOR_ALLOWED = frozenset({
    "execute", "executemany", "fetchone", "fetchall", "fetchmany",
    "connection", "lastrowid", "rowcount", "description",
    "_live",   # the per-operation poison re-check (§B6)
})


class _CursorProxy:
    """A cursor whose ``.connection`` is the facade and whose execute/executemany
    return the proxy — never the native cursor (ATOMIC-ACTIVATION-V1 §B1).
    Attribute reads are allowlisted (`__getattribute__`), so the native cursor
    (`_cursor`, any mangled spelling) is unreachable; internals are reached only
    through ``object.__getattribute__``. Iteration stays on the proxy
    (``__iter__`` returns self, ``__next__`` delegates), so no chain —
    ``facade.execute(...).connection``, ``iter(...).connection`` — recovers raw."""

    __slots__ = ("_cursor", "_facade")

    __getattribute__ = _guarded_getattribute(_CURSOR_ALLOWED)

    def __init__(self, cursor: sqlite3.Cursor, facade: "_ConnectionFacade") -> None:
        object.__setattr__(self, "_cursor", cursor)
        object.__setattr__(self, "_facade", facade)

    def _live(self) -> sqlite3.Cursor:
        """Re-check the owning buffer on EVERY operation, then hand back the
        native cursor.

        A cursor obtained before an abort used to keep working afterwards: it
        delegated straight to its native cursor, so poisoning the buffer never
        reached it. That made the §B6 fail-closed guarantee conditional on the
        physical `close()` succeeding — and when both ROLLBACK and `close()`
        raise while the underlying connection stays live, an uncertain
        transaction remained readable and finalizable through a cached handle.
        Poison is a software gate, so it has to be consulted per operation
        rather than trusted to a one-shot teardown.
        """
        _slot(_slot(self, "_facade"), "_buffer")._live_conn()
        return _slot(self, "_cursor")

    def execute(self, *a: Any, **k: Any) -> "_CursorProxy":
        self._live().execute(*a, **k)
        return self

    def executemany(self, *a: Any, **k: Any) -> "_CursorProxy":
        self._live().executemany(*a, **k)
        return self

    def fetchone(self) -> Any:
        return self._live().fetchone()

    def fetchall(self) -> list:
        return self._live().fetchall()

    def fetchmany(self, size: int | None = None) -> list:
        cur = self._live()
        return cur.fetchmany(size) if size is not None else cur.fetchmany()

    def __iter__(self) -> "_CursorProxy":
        return self                       # NOT iter(native) — that leaks .connection

    def __next__(self) -> Any:
        return self._live().__next__()

    @property
    def connection(self) -> "_ConnectionFacade":
        return _slot(self, "_facade")

    @property
    def lastrowid(self) -> int | None:
        return self._live().lastrowid

    @property
    def rowcount(self) -> int:
        return _slot(self, "_cursor").rowcount

    @property
    def description(self) -> Any:
        return _slot(self, "_cursor").description

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"cannot set {name!r} on the cursor proxy")


_FACADE_ALLOWED = frozenset({
    "execute", "executemany", "cursor", "executescript", "commit", "rollback",
    "total_changes", "in_transaction", "close",
})


class _ConnectionFacade:
    """A deny-by-default capability over the buffer's sole SQLite connection
    (ATOMIC-ACTIVATION-V1 §B1). Sidecars hold THIS, never the raw handle:

    - attribute reads are allowlisted (`__getattribute__`): only the public
      methods/read-properties below resolve; the buffer ref (`_buffer`) and every
      raw-returning path are unreachable by ANY spelling — mangled or not — so a
      borrowed holder cannot recover the native connection and disable the
      authorizer (pbr r2 A1). Internals use ``object.__getattribute__``;
    - ``commit()``/``rollback()`` route through the buffer's unit-of-work — gated
      to the single terminal commit while a unit is open;
    - every cursor-producing call returns a ``_CursorProxy`` whose ``.connection``
      is the facade;
    - ``executescript``/DDL is rejected while a unit is open (it implicitly
      commits before running);
    - transaction-control SQL through ``execute`` is caught below the text by the
      unit authorizer the buffer installs on the raw connection.
    """

    __slots__ = ("_buffer",)

    __getattribute__ = _guarded_getattribute(_FACADE_ALLOWED)

    def __init__(self, buffer: "PatternBuffer") -> None:
        object.__setattr__(self, "_buffer", buffer)

    def execute(self, *a: Any, **k: Any) -> _CursorProxy:
        return _CursorProxy(_slot(self, "_buffer")._live_conn().execute(*a, **k), self)

    def executemany(self, *a: Any, **k: Any) -> _CursorProxy:
        return _CursorProxy(
            _slot(self, "_buffer")._live_conn().executemany(*a, **k), self)

    def cursor(self) -> _CursorProxy:
        return _CursorProxy(_slot(self, "_buffer")._live_conn().cursor(), self)

    def executescript(self, script: str) -> _CursorProxy:
        buf = _slot(self, "_buffer")
        if buf._unit_open:
            raise RuntimeError(
                "executescript/DDL is forbidden while an atomic unit is open "
                "(it implicitly commits before running)")
        return _CursorProxy(buf._live_conn().executescript(script), self)

    def commit(self) -> None:
        _slot(self, "_buffer")._gated_commit()

    def rollback(self) -> None:
        _slot(self, "_buffer")._gated_rollback()

    @property
    def total_changes(self) -> int:
        return _slot(self, "_buffer")._live_conn().total_changes

    @property
    def in_transaction(self) -> bool:
        return _slot(self, "_buffer")._live_conn().in_transaction

    def __enter__(self) -> "_ConnectionFacade":
        return self                       # never the raw connection (§B1)

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        # A4: outside a unit, mirror sqlite context semantics — commit on clean
        # exit, rollback on exception. Both route through the gated owner path, so
        # INSIDE an open unit they are inert (the terminal commit still governs).
        if exc_type is None:
            _slot(self, "_buffer")._gated_commit()
        else:
            _slot(self, "_buffer")._gated_rollback()
        return False

    def close(self) -> None:
        # owner-only: the facade never closes the shared connection (the buffer
        # owns its lifecycle) — a borrowed close() is always rejected.
        raise RuntimeError("close() is owner-only on the connection facade")

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ("autocommit", "isolation_level"):
            raise RuntimeError(f"{name} is owner-only on the connection facade")
        raise AttributeError(f"cannot set {name!r} on the connection facade")


class PatternBuffer:
    """The append-only store. Holds exactly one world's log, forever."""

    def __init__(self, path: str | Path, world_id: str) -> None:
        self.path = Path(path)
        # The poison gate is armed BEFORE the connection exists: `_live_conn()`
        # is now the single database entry point (§B6 fail-closed), and it is
        # consulted by `_meta()` during construction itself.
        self._poisoned = False
        self._conn = sqlite3.connect(self.path)
        self._conn.executescript(_SCHEMA)
        existing = self._meta("world_id")
        if existing is None:
            self._live_conn().execute(
                "INSERT INTO world_meta (key, value) VALUES ('world_id', ?)", (world_id,)
            )
            self._live_conn().commit()
        elif existing != world_id:
            self._conn.close()
            raise WorldMismatch(
                f"buffer at {self.path} belongs to world {existing!r}, not {world_id!r}"
            )
        self.world_id = world_id
        self.rows_read = 0  # deserialization counter (read-path scaling guard, 037)
        # Unit-of-work (ATOMIC-ACTIVATION-V1 §B1): the buffer owns the sole
        # connection and hands every holder a capability facade, never the raw
        # handle. While a unit is open, all commits defer to one terminal commit.
        self._facade = _ConnectionFacade(self)
        self._unit_open = False
        self._owner_phase = "none"       # {none, begin, commit, rollback}
        self._unit_committed = False     # last unit reached a terminal COMMIT
        self._unit_precall_head: int | None = None

    def _meta(self, key: str) -> str | None:
        row = self._live_conn().execute(
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
        self._validate_attr_semantics_insert(row)
        self._live_conn().execute(
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
                json.dumps(row.value, sort_keys=True, default=json_default),
                row.valid_from,
                row.valid_to,
                row.frame,
                row.status,
                row.confidence,
                row.asserted_at,
            ),
        )
        self._commit_or_defer()
        logger.debug("append %s: (%s · %s)", row.id, row.entity, row.attribute)

    def _validate_attr_semantics_insert(self, row: Assertion) -> None:
        """Shared attr:* authority guard for append() and dump.build replay."""
        if not row.entity.startswith(ATTR_PREFIX) or row.attribute not in SEMANTICS_PREDICATES:
            return
        target = row.entity[len(ATTR_PREFIX):]
        if target in INVIOLABLE_CORE:
            raise ValueError(
                f"cannot declare semantics for inviolable core attribute {target!r}"
            )
        prior = self._live_conn().execute(
            "SELECT id FROM assertions"
            " WHERE attribute = ? AND entity NOT LIKE ? AND entity NOT LIKE ?"
            " ORDER BY seq LIMIT 1",
            (target, ATTR_PREFIX + "%", "a:%"),
        ).fetchone()
        if prior is not None:
            raise ValueError(
                f"cannot declare semantics for attribute {target!r} after "
                f"folded data already exists ({prior[0]})"
            )

    # ----------------------------------------------------------------- read

    def head(self) -> int:
        """The current log head (last seq; 0 for an empty log)."""
        row = self._live_conn().execute(
            "SELECT COALESCE(MAX(seq), 0) FROM assertions").fetchone()
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
        value_type: str | None = None,
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
            # Encoded-byte equality: a Decimal query matches its stored row at
            # the authored scale ("12.50" != "12.5" — append-only fidelity).
            params.append(json.dumps(value, sort_keys=True, default=json_default))
        if value_type is not None:
            clauses.append("a.value_type = ?")
            params.append(value_type)
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

    def max_valid_from(self) -> float | None:
        """The valid-time high-water mark over ALL rows, all frames (None when
        no timed rows exist). Log coordinates are real after retraction —
        monotone by construction (AXIS-HEAD-V1)."""
        row = self._live_conn().execute(
            "SELECT MAX(valid_from) FROM assertions").fetchone()
        return row[0]

    def _select(self, where: str, params: tuple) -> list[Assertion]:
        cur = self._live_conn().execute(
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
                value=json.loads(r[6], object_hook=decode_hook),
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

    def raw_connection(self) -> "_ConnectionFacade":
        """The capability facade over the sole connection (ATOMIC-ACTIVATION-V1
        §B1) — the ONLY boundary any holder receives; the raw handle never
        escapes, so nothing can cache it and bypass the unit-of-work."""
        return self._facade

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------- unit-of-work (§B1)

    def _live_conn(self) -> sqlite3.Connection:
        if self._poisoned:
            raise PoisonedConnection(
                "connection poisoned after an unconfirmable rollback")
        return self._conn

    def _commit_or_defer(self) -> None:
        """The buffer's own per-row commit — deferred while a unit is open."""
        if self._unit_open:
            return
        self._live_conn().commit()

    def _gated_commit(self) -> None:
        """A borrowed ``facade.commit()`` — a no-op during a unit (deferred to
        the single terminal commit), a real commit outside one."""
        if self._unit_open:
            return
        self._live_conn().commit()

    def _gated_rollback(self) -> None:
        if self._unit_open:
            return                        # borrowed rollback is inert mid-unit
        self._live_conn().rollback()

    def _unit_authorizer(self, action: int, arg1: Any, arg2: Any,
                         dbname: Any, source: Any) -> int:
        """Compile-time capability check for borrowed execution during a unit.
        Transaction control is provenance-gated by ``_owner_phase``; the DML/read
        classes are allowed; everything else is denied by default."""
        if action == sqlite3.SQLITE_TRANSACTION:
            want = {"begin": "BEGIN", "commit": "COMMIT",
                    "rollback": "ROLLBACK"}.get(self._owner_phase)
            return (sqlite3.SQLITE_OK
                    if want is not None and arg1 == want else sqlite3.SQLITE_DENY)
        if action in _ALLOWED_ACTIONS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    def _run_phase(self, phase: str, sql: str) -> None:
        """Issue one owner transaction statement with the phase set to exactly
        it, resetting to ``none`` in a try/finally so a raised commit/rollback
        can never leave the capability authorizing (§B1.b)."""
        self._owner_phase = phase
        try:
            self._live_conn().execute(sql)
        finally:
            self._owner_phase = "none"

    def _poison(self) -> None:
        self._poisoned = True
        for op in (lambda: self._conn.set_authorizer(None), self._conn.close):
            try:
                op()
            except Exception:
                pass

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    @property
    def unit_committed(self) -> bool:
        """Whether the LAST ``atomic_unit`` reached a confirmed terminal COMMIT.
        A fault after this point is the ambiguous post-commit outcome (§B6/F7):
        the set is durable — the raw error propagates, never wrapped as
        ``AtomicAbort``, and in-memory views are NOT restored."""
        return self._unit_committed

    @property
    def unit_precall_head(self) -> int | None:
        """The committed head at unit entry — retract target eligibility uses
        it to exclude staged (in-set-minted) ids (§C1); ``None`` outside a unit."""
        return self._unit_precall_head

    def atomic_unit(self, body: "Any") -> Any:
        """Run ``body()`` inside ONE transaction (ATOMIC-ACTIVATION-V1 §B1):
        a single commit on success, a single rollback on any exception, and the
        authorizer installed/restored in an OUTER try/finally on every exit so
        later non-atomic work is unaffected. A rollback-unconfirmable failure
        **poisons** the connection and propagates the raw error unwrapped (§B6).
        Once COMMIT succeeds, any later fault is the ambiguous post-commit outcome
        (raw, never ``AtomicAbort``). Nested entry is rejected."""
        if self._unit_open:
            raise RuntimeError("nested atomic unit entry is rejected")
        self._live_conn()
        prior_authorizer = None    # sqlite3 exposes no getter; known None here
        self._unit_committed = False
        began = False
        restore = True
        try:
            # A3: EVERY stateful install is inside the guard — a setup fault
            # (head(), set_authorizer) still runs the finally cleanup, so
            # `_unit_open`/authorizer never linger to break the next INSERT.
            self._conn.set_authorizer(self._unit_authorizer)
            self._unit_open = True
            self._unit_precall_head = self.head()
            self._run_phase("begin", "BEGIN")
            began = True
            result = body()
            self._run_phase("commit", "COMMIT")
            self._unit_committed = True     # A2: terminal success is recorded
            return result
        except BaseException:
            # A2: never roll back a committed set — once COMMIT lands, a later
            # fault is post-commit-ambiguous and propagates raw.
            if began and not self._unit_committed:
                try:
                    self._run_phase("rollback", "ROLLBACK")
                except BaseException:
                    self._poison()          # unconfirmable → fail closed (§B6)
                    restore = False
                    raise
            raise
        finally:
            self._unit_open = False
            self._unit_precall_head = None
            if restore and not self._poisoned:
                self._conn.set_authorizer(prior_authorizer)
