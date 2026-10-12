"""Helpers for VIEW-EXPORT-V1's property over host world files (not a test module).

A host world is read only through copies: the file is opened with `mode=ro`
and backed up into memory (SQLite's backup API), never opened for writing. A
"client at position p" is emulated by truncating the in-memory copy's log at
seq p and exporting it, which is the document a client would have been handed
when the log head stood at p.
"""

from __future__ import annotations

import sqlite3
import urllib.parse
from pathlib import Path

from patternbuffer import World, mirror


def copy_read_only(path: Path) -> sqlite3.Connection:
    """An in-memory copy of the file, backed up from a `mode=ro` connection."""
    uri = "file:" + urllib.parse.quote(str(path.resolve())) + "?mode=ro"
    source = sqlite3.connect(uri, uri=True)
    try:
        copy = sqlite3.connect(":memory:", check_same_thread=False)
        source.backup(copy)
    finally:
        source.close()
    return copy


def world_id_of(conn: sqlite3.Connection) -> str:
    return conn.execute("SELECT value FROM world_meta WHERE key='world_id'").fetchone()[0] \
        if _has_key_column(conn) else conn.execute("SELECT * FROM world_meta").fetchone()[-1]


def _has_key_column(conn: sqlite3.Connection) -> bool:
    return [r[1] for r in conn.execute("PRAGMA table_info(world_meta)")] == ["key", "value"]


def busiest_knows_frame(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT frame, COUNT(*) c FROM assertions WHERE frame LIKE 'knows:%' "
        "GROUP BY frame ORDER BY c DESC, frame LIMIT 1").fetchone()
    return row[0] if row else None


def head_of(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COALESCE(MAX(seq),0) FROM assertions").fetchone()[0]


def positions(head: int, n: int = 20) -> list[int]:
    """`n` distinct log positions spread over (0, head)."""
    return sorted({max(1, head * i // (n + 1)) for i in range(1, n + 1)})


def truncated(conn: sqlite3.Connection, seq: int, wid: str) -> World:
    """A sealed World over a copy of `conn` with its log cut after `seq`."""
    clone = sqlite3.connect(":memory:", check_same_thread=False)
    conn.backup(clone)
    for trigger in ("assertions_append_only_delete", "assertions_append_only_update"):
        clone.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    clone.execute("DELETE FROM assertions WHERE seq > ?", (seq,))
    clone.commit()
    world = World(Path("truncated.world"), wid, _connection=clone)
    world.buffer.seal_log()
    return world


def full_world(conn: sqlite3.Connection, wid: str) -> World:
    clone = sqlite3.connect(":memory:", check_same_thread=False)
    conn.backup(clone)
    world = World(Path("full.world"), wid, _connection=clone)
    world.buffer.seal_log()
    return world


def check_world(path: Path, key: bytes, n: int = 20) -> dict:
    """The defining property over one host world file, at `n` positions, with
    and without the present layer. Returns counts and any mismatch."""
    conn = copy_read_only(path)
    wid = world_id_of(conn)
    frame = busiest_knows_frame(conn)
    out = {"world": path.name, "frame": frame, "head": head_of(conn),
           "checks": 0, "resets": 0, "diffs": 0, "mismatches": []}
    if frame is None:
        out["skipped"] = "no knows: frame"
        return out
    full = full_world(conn, wid)
    try:
        for seq in positions(out["head"], n):
            old_world = truncated(conn, seq, wid)
            try:
                for k in (None, key):
                    old_doc = mirror.export(old_world, frame, key=k)
                    answer = mirror.feed(full, frame, old_doc["cursor"], key=k)
                    got = mirror.canonical_json(mirror.apply(old_doc, answer))
                    want = mirror.canonical_json(mirror.export(full, frame, key=k))
                    out["checks"] += 1
                    is_reset = any(op["op"] == "clear" for op in answer["ops"])
                    out["resets" if is_reset else "diffs"] += 1
                    if got != want:
                        out["mismatches"].append({"seq": seq, "keyed": k is not None})
            finally:
                old_world.close()
    finally:
        full.close()
        conn.close()
    return out
