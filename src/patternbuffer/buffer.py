"""PatternBuffer: the append-only assertion log — the only truth (P1).

One SQLite file per world, and ``world_id`` stamped on every row as a
cross-wiring guard (the 1:1 invariant, spec §3.1/§4). Append-only is
enforced twice: the Python surface exposes no update/delete, and SQL
triggers raise on UPDATE/DELETE as belt-and-braces against future code.

The buffer is its file's only writer (one writer per world — ATOMIC-
ACTIVATION-V1 non-goals; the buffer owns the sole connection). So the log
head is tracked in memory, and ``log_version`` tells the derived in-memory
caches (identity closure, durability, attribute semantics) when this
connection's view of the file may have changed. A second connection
appending to the same file is outside that model: this buffer would not see
its rows until reopened.
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
    MECHANISM_STATUS,
    POLICIES,
    RESOLUTION_POLICY,
    SEMANTICS_PREDICATES,
    STATUSES,
    VALUE_TYPES,
    WORLD_PHYSICS_SUBJECT,
    Assertion,
    FrameSel,
)
from patternbuffer.roles import RoleViolation, WriterRole

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


def _prefix_upper_bound(prefix: str) -> str:
    """The least string greater than every string starting with ``prefix``."""
    return prefix[:-1] + chr(ord(prefix[-1]) + 1)

class WorldMismatch(ValueError):
    """A buffer was opened or written with the wrong world_id (1:1 invariant)."""


class WorldPhysicsMismatch(ValueError):
    """A world was opened with an explicit resolution policy that disagrees
    with the physics row it stores (READ-SURFACE-V1 §7). The log was written
    under its physics; a world that needs other physics is a new world."""


class SecondWriter(RuntimeError):
    """Another connection committed to this world's file while this buffer
    held it open (the one-live-World-per-file rule, ADOPTION). This buffer's
    head and derived caches cannot see that write, so every later operation
    on it raises instead of serving stale reads or minting a clashing row id;
    reopen the world, and route all writers and readers through one World."""


class ReadOnlyWorld(RuntimeError):
    """A write to the log was attempted on a sealed World — a `World.snapshot()`
    copy (WORLD-SERVICE-V1 §7a). The log (append, the gate, retraction, every
    atomic unit) is read-only there; the derived sidecars stay writable."""


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


def _live_cursor(proxy: Any) -> Any:
    """Re-check the owning buffer, then return the native cursor — for module
    code only.

    This is a module function for the same reason ``_slot`` is: it must not be
    an attribute of the borrowed proxy. An earlier revision made it a method
    and allowlisted it, which handed callers
    ``facade.execute(...)._live().connection`` — the exact raw connection, and
    therefore ``set_authorizer(None)`` and unmediated transaction control. The
    poison check has to be reachable from every proxy operation and reachable
    from nowhere else.
    """
    _slot(_slot(proxy, "_facade"), "_buffer")._live_conn()
    return _slot(proxy, "_cursor")


_CURSOR_ALLOWED = frozenset({
    "execute", "executemany", "fetchone", "fetchall", "fetchmany",
    "connection", "lastrowid", "rowcount", "description",
})


class _CursorProxy:
    """A cursor whose ``.connection`` is the facade and whose execute/executemany
    return the proxy — never the native cursor (ATOMIC-ACTIVATION-V1 §B1).
    Attribute reads are allowlisted (`__getattribute__`), so the native cursor
    (`_cursor`, any mangled spelling) is unreachable by ordinary access (a
    misuse guard, not a security boundary); internals are reached only through
    ``object.__getattribute__``. Iteration stays on the proxy
    (``__iter__`` returns self, ``__next__`` delegates), so no chain —
    ``facade.execute(...).connection``, ``iter(...).connection`` — recovers raw."""

    __slots__ = ("_cursor", "_facade")

    __getattribute__ = _guarded_getattribute(_CURSOR_ALLOWED)

    def __init__(self, cursor: sqlite3.Cursor, facade: "_ConnectionFacade") -> None:
        object.__setattr__(self, "_cursor", cursor)
        object.__setattr__(self, "_facade", facade)

    def execute(self, *a: Any, **k: Any) -> "_CursorProxy":
        _live_cursor(self).execute(*a, **k)
        return self

    def executemany(self, *a: Any, **k: Any) -> "_CursorProxy":
        _live_cursor(self).executemany(*a, **k)
        return self

    def fetchone(self) -> Any:
        return _live_cursor(self).fetchone()

    def fetchall(self) -> list:
        return _live_cursor(self).fetchall()

    def fetchmany(self, size: int | None = None) -> list:
        cur = _live_cursor(self)
        return cur.fetchmany(size) if size is not None else cur.fetchmany()

    def __iter__(self) -> "_CursorProxy":
        return self                       # NOT iter(native) — that leaks .connection

    def __next__(self) -> Any:
        return _live_cursor(self).__next__()

    @property
    def connection(self) -> "_ConnectionFacade":
        return _slot(self, "_facade")

    @property
    def lastrowid(self) -> int | None:
        return _live_cursor(self).lastrowid

    @property
    def rowcount(self) -> int:
        return _live_cursor(self).rowcount

    @property
    def description(self) -> Any:
        return _live_cursor(self).description

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
      raw-returning path are unreachable by ordinary or mangled spellings, so a
      borrowed holder cannot recover the native connection by accident (pbr r2
      A1). This guards against misuse, not a hostile holder: Python offers no
      true capability boundary (``object.__getattribute__`` reaches internals,
      and sidecars hold the buffer itself). The enforcement that holds is the
      SQLite authorizer installed for an atomic unit, which refuses any
      non-terminal commit whatever handle issues it;
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

    def __init__(self, path: str | Path, world_id: str, *,
                 connection: sqlite3.Connection | None = None) -> None:
        self.path = Path(path)
        # The poison gate is armed BEFORE the connection exists: `_live_conn()`
        # is now the single database entry point (§B6 fail-closed), and it is
        # consulted by `_meta()` during construction itself.
        self._poisoned = False
        # The log head as this connection sees it (None = unknown, re-read on
        # demand), and the counter derived caches key on. Both are derived and
        # disposable: a reopen starts from None/0.
        self._head: int | None = None
        self._log_version = 0
        # `connection` (WORLD-SERVICE-V1 §7a): a snapshot hands in the in-memory
        # copy it made; the buffer then owns that connection exactly as it owns
        # a file's. Absent, the file at `path` is opened as ever.
        self._sealed = False
        self._conn = connection if connection is not None else sqlite3.connect(self.path)
        self._conn.executescript(_SCHEMA)
        # SQLite's data_version moves only when ANOTHER connection commits to
        # the file; `_live_conn()` compares it on every operation (the
        # second-writer guard). Disarmed (None) until construction is done.
        self._data_version: int | None = None
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
        self._data_version = self._read_data_version()

    def _read_data_version(self) -> int:
        return self._conn.execute("PRAGMA data_version").fetchone()[0]

    def _meta(self, key: str) -> str | None:
        row = self._live_conn().execute(
            "SELECT value FROM world_meta WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    # ---------------------------------------------------------------- seal

    def seal_log(self) -> None:
        """Seal the log (WORLD-SERVICE-V1 §7a): from here every append, the
        gate, retraction and every atomic unit raise ``ReadOnlyWorld``. One-way
        for this buffer; the derived sidecar tables stay writable (they are the
        holder's own disposable layer, not the log)."""
        self._sealed = True

    @property
    def sealed(self) -> bool:
        """Whether the log is sealed (a ``World.snapshot()`` copy)."""
        return self._sealed

    def require_writable(self) -> None:
        """Raise ``ReadOnlyWorld`` when the log is sealed."""
        if self._sealed:
            raise ReadOnlyWorld(
                "this World is a read-only snapshot: its log accepts no write")

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
        self.require_writable()
        role.check(status)
        # GATE-AUTHORITY-V1 §1: a mechanism row is written only with its
        # owner's mark. Checked here, not in `_insert`, so `dump.build` still
        # replays any old log as it was (readers neutralize forged rows).
        required = MECHANISM_STATUS.get(attribute)
        if required is not None and status != required:
            raise RoleViolation(
                f"a {attribute!r} row is written only by its owning component, "
                f"with status {required!r} (got {status!r})"
            )
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
        self.require_writable()
        if row.world_id != self.world_id:
            raise WorldMismatch(
                f"assertion stamped for world {row.world_id!r} cannot enter "
                f"buffer of world {self.world_id!r}"
            )
        self.check_declaration_authority(row.entity, row.attribute)
        self._validate_physics_insert(row)
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
        # The row is visible on this connection from here on, committed or
        # not (a deferred unit commit, or a failed commit left pending).
        if self._head is not None and row.seq > self._head:
            self._head = row.seq
        self._log_version += 1
        self._commit_or_defer()
        logger.debug("append %s: (%s · %s)", row.id, row.entity, row.attribute)

    def check_declaration_authority(self, entity: str, attribute: str) -> None:
        """The vocabulary-authority refusal for an ``attr:<name> · <axis>``
        declaration row: never on an inviolable core attribute, and never once
        folded data exists for the attribute. Raises ValueError; a no-op for
        any other row. The one check shared by every append, ``dump.build``
        replay (through ``_insert``) and the ingest gate, which runs it before
        validating a declared value (GATE-AUTHORITY-V1 §5)."""
        if not entity.startswith(ATTR_PREFIX) or attribute not in SEMANTICS_PREDICATES:
            return
        target = entity[len(ATTR_PREFIX):]
        if target in INVIOLABLE_CORE:
            raise ValueError(
                f"cannot declare semantics for inviolable core attribute {target!r}"
            )
        if attribute == "resolvable_for":
            # RESOLVE-UNMARKED-V1: opening an aspect to invention changes no
            # fold, so existing data on the aspect does not lock it.
            return
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

    def physics_row_id(self) -> str | None:
        """The id of the world's physics row (READ-SURFACE-V1 §7), or None
        for a world created before it — an indexed lookup on the row's key."""
        row = self._live_conn().execute(
            "SELECT id FROM assertions WHERE entity = ? AND attribute = ?"
            " ORDER BY seq LIMIT 1",
            (WORLD_PHYSICS_SUBJECT, RESOLUTION_POLICY),
        ).fetchone()
        return row[0] if row else None

    def _validate_physics_insert(self, row: Assertion) -> None:
        """The physics row is immutable (READ-SURFACE-V1 §7), checked in the
        insert validator `append` and `dump.build` share, so a tampered dump
        fails to build: at most one physics row per log, only in canon, only
        in the shape World writes (stated, literal, timeless, no confidence),
        only with a value in POLICIES — and no `retracts` row may target it (a
        hidden physics row would leave the world unable to record its own).
        Raises ValueError; a no-op for any other row."""
        if row.entity == WORLD_PHYSICS_SUBJECT and row.attribute == RESOLUTION_POLICY:
            if row.frame != CANON:
                raise ValueError(
                    f"the world's physics row lives in canon only (got frame {row.frame!r})")
            # The whole shape World writes, not just its frame and value (pbr,
            # on the build): a row replayed with another status — `retracted`
            # hides it from every read while physics_row_id() still finds it —
            # or with a time or a confidence is not the world's physics.
            if (row.status != "stated" or row.value_type != "literal"
                    or row.valid_from is not None or row.valid_to is not None
                    or row.confidence is not None):
                raise ValueError(
                    "the world's physics row is stated, literal and timeless, "
                    f"with no confidence (got status={row.status!r}, "
                    f"value_type={row.value_type!r}, valid_from={row.valid_from!r}, "
                    f"valid_to={row.valid_to!r}, confidence={row.confidence!r})")
            if not isinstance(row.value, str) or row.value not in POLICIES:
                raise ValueError(
                    f"the world's physics row must name a policy in "
                    f"{sorted(POLICIES)} (got {row.value!r})")
            existing = self.physics_row_id()
            if existing is not None:
                raise ValueError(
                    f"this world already records its physics ({existing}); the "
                    "physics row is written once and is immutable")
        elif row.attribute == "retracts" and row.entity == self.physics_row_id():
            raise ValueError(
                f"the world's physics row {row.entity} is immutable and cannot "
                "be retracted")

    # ----------------------------------------------------------------- read

    def head(self) -> int:
        """The current log head (last seq; 0 for an empty log).

        Read from SQLite once, then tracked: ``_insert`` advances it and a
        rollback, close or poison forgets it (single writer — module doc)."""
        conn = self._live_conn()          # a poisoned buffer still refuses
        if self._head is None:
            row = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM assertions").fetchone()
            self._head = int(row[0])
        return self._head

    @property
    def log_version(self) -> int:
        """A counter that moves on every append, and whenever pending writes
        may have been discarded or the connection became unusable (rollback,
        close, poison). Derived in-memory caches rebuild when it differs from
        the value they were built at. Never stored; meaningful only within
        this instance."""
        return self._log_version

    def _forget_view(self) -> None:
        """Rows (or sidecar writes) may have vanished or become unreadable:
        re-read the head on demand and move ``log_version`` so every derived
        cache re-derives (or raises, on a closed/poisoned connection)."""
        self._head = None
        self._log_version += 1

    def get(self, assertion_id: str) -> Assertion | None:
        rows = self._select("WHERE id = ?", (assertion_id,))
        return rows[0] if rows else None

    def all_rows(self) -> list[Assertion]:
        """The full log in append order (dump/rebuild substrate)."""
        return self._select("", ())

    def rows_after(self, seq: int) -> list[Assertion]:
        """Every row with ``seq`` above the given one, in append order (the
        rows a call appended, when ``seq`` is the head before it)."""
        return self._select("WHERE a.seq > ?", (seq,))

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
        frame: FrameSel | None = None,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> list[Assertion]:
        """Rows visible at ``(valid_as_of, asserted_as_of)`` — spec §4.2.

        Visibility is class-blind; which visible row a fold serves is
        durability-dependent and lives in the derived indexes, not here.
        Omitted bounds mean no bound (now / log head). Retraction
        meta-rows themselves are excluded from folds, and a row is
        invisible once a ``retracts`` row targeting it is itself visible
        on the asserted axis — honored only with truth maintenance's mark,
        status ``retracted`` (GATE-AUTHORITY-V1 §1): a ``retracts`` row
        forged under any other status hides nothing.

        ``frame`` is one stored frame name (``=``) or a tuple of them (``IN``,
        FRAME-CONTINUITY-V1 §2: the stored frames a wider ``frame_scope``
        resolved to; an empty tuple selects nothing).
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
            # A half-open range, not LIKE: indexable, and `_`/`%` in a prefix
            # match literally (ids are lowercase by the gate's grammar).
            clauses.append("a.entity >= ? AND a.entity < ?")
            params.extend([entity_prefix, _prefix_upper_bound(entity_prefix)])
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
        if isinstance(frame, str):
            clauses.append("a.frame = ?")
            params.append(frame)
        elif frame is not None:
            clauses.append(f"a.frame IN ({','.join('?' * len(frame))})")
            params.extend(frame)
        if valid_as_of is not None:
            clauses.append("(a.valid_from IS NULL OR a.valid_from <= ?)")
            params.append(valid_as_of)
            clauses.append("(a.valid_to IS NULL OR a.valid_to > ?)")
            params.append(valid_as_of)
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM assertions r"
            " WHERE r.entity = a.id AND r.attribute = 'retracts'"
            " AND r.status = ? AND r.asserted_at <= ?)"
        )
        params.extend([MECHANISM_STATUS["retracts"], aao])
        return self._select("WHERE " + " AND ".join(clauses), tuple(params))

    def retracted_targets(
        self,
        *,
        attribute: str,
        frame: str = CANON,
        asserted_as_of: int | None = None,
    ) -> list[Assertion]:
        """Rows of ``attribute`` in ``frame`` that a ``retracts`` row hides at
        ``asserted_as_of`` (log head when omitted) — the rows ``visible()``
        omits, in append order (IDENTITY-ROOT-CAUSES-V1 §2). The retraction
        counts only with truth maintenance's mark, status ``retracted``
        (GATE-AUTHORITY-V1 §1), exactly as ``visible()`` honors it. Read-only;
        the one reader of a decided-against identity edge."""
        aao = self.head() if asserted_as_of is None else asserted_as_of
        return self._select(
            "WHERE a.asserted_at <= ? AND a.status != 'retracted'"
            " AND a.attribute = ? AND a.frame = ?"
            " AND EXISTS (SELECT 1 FROM assertions r"
            " WHERE r.entity = a.id AND r.attribute = 'retracts'"
            " AND r.status = ? AND r.asserted_at <= ?)",
            (aao, attribute, frame, MECHANISM_STATUS["retracts"], aao),
        )

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
        self._forget_view()               # later reads hit the closed handle, as before
        self._conn.close()

    # ------------------------------------------------- unit-of-work (§B1)

    def _live_conn(self) -> sqlite3.Connection:
        if self._poisoned:
            raise PoisonedConnection(
                "connection poisoned after an unconfirmable rollback")
        if self._data_version is not None and self._read_data_version() != self._data_version:
            raise SecondWriter(
                f"another connection wrote to {self.path} while this World held it "
                "open; this handle cannot see that write. One live World per "
                "file: reopen, and route every writer and reader through it")
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
        try:
            self._live_conn().rollback()
        finally:
            self._forget_view()

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
        # The second-writer guard's read of `PRAGMA data_version` (no
        # argument: read-only), so the guard stays live inside a unit.
        if action == sqlite3.SQLITE_PRAGMA and arg1 == "data_version" and arg2 is None:
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
        self._forget_view()
        for op in (lambda: self._conn.set_authorizer(None), self._conn.close):
            try:
                op()
            except Exception:
                pass

    @property
    def unit_open(self) -> bool:
        """Whether an atomic unit is open on this buffer."""
        return self._unit_open

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
        self.require_writable()
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
                finally:
                    # the unit's rows and sidecar writes are gone: the head
                    # returns to its pre-unit value and every cache re-derives
                    self._forget_view()
            raise
        finally:
            self._unit_open = False
            self._unit_precall_head = None
            if restore and not self._poisoned:
                self._conn.set_authorizer(prior_authorizer)
