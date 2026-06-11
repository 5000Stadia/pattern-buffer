"""JSONL dump + deterministic builder (spec §10, the letter-005 seam).

The dump is the canonical, diffable artifact; the SQLite file is
disposable. ``build`` replays a dump through a builder-privileged append
that preserves ``seq``/``id``/``asserted_at`` byte-for-byte — and it is
not a second write authority: every constraint below aborts the build.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from patternbuffer.buffer import PatternBuffer
from patternbuffer.model import STATUSES, VALUE_TYPES, Assertion
from patternbuffer.roles import _make_builder_role

logger = logging.getLogger(__name__)

_FIELDS = (
    "seq",
    "id",
    "world_id",
    "entity",
    "attribute",
    "value_type",
    "value",
    "valid_from",
    "valid_to",
    "frame",
    "status",
    "confidence",
    "asserted_at",
)


class DumpError(ValueError):
    """A dump failed the builder's validation; nothing was built."""


def dump(buffer: PatternBuffer) -> str:
    """The full log as JSONL, one assertion per line, in append order."""
    lines = []
    for row in buffer.all_rows():
        lines.append(
            json.dumps({f: getattr(row, f) for f in _FIELDS}, sort_keys=True)
        )
    return "\n".join(lines) + ("\n" if lines else "")


def build(jsonl: str, path: str | Path) -> PatternBuffer:
    """Materialize a buffer from a dump. Refuses anything but a clean replay.

    Constraints (spec §10): target absent or empty; exactly one
    ``world_id`` across all rows; ``seq`` contiguous from 1;
    ``id == "a:<seq>"`` and ``asserted_at == seq``; statuses and value
    types in vocabulary. No judgment runs — the dump already carries the
    log as it was; sidecars are rebuilt by their own ``rebuild()``.
    """
    path = Path(path)
    if path.exists() and path.stat().st_size > 0:
        raise DumpError(f"build target {path} already exists; restore is not a write path")

    rows = []
    for n, line in enumerate(jsonl.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DumpError(f"line {n}: not valid JSON: {exc}") from exc
        missing = set(_FIELDS) - raw.keys()
        if missing:
            raise DumpError(f"line {n}: missing fields {sorted(missing)}")
        rows.append(Assertion(**{f: raw[f] for f in _FIELDS}))

    world_ids = {r.world_id for r in rows}
    if len(world_ids) > 1:
        raise DumpError(f"dump spans worlds {sorted(world_ids)}; a buffer holds exactly one")
    if not rows:
        raise DumpError("empty dump; nothing to build")
    builder = _make_builder_role()
    for i, row in enumerate(rows, start=1):
        if row.seq != i:
            raise DumpError(f"seq not contiguous from 1: expected {i}, got {row.seq}")
        if row.id != f"a:{i}":
            raise DumpError(f"row {i}: id {row.id!r} != 'a:{i}'")
        if row.asserted_at != i:
            raise DumpError(f"row {i}: asserted_at {row.asserted_at} != seq {i}")
        if row.status not in STATUSES or row.status == "default":
            raise DumpError(f"row {i}: status {row.status!r} cannot appear in a log")
        if row.value_type not in VALUE_TYPES:
            raise DumpError(f"row {i}: unknown value_type {row.value_type!r}")
        builder.check(row.status)

    buffer = PatternBuffer(path, world_id=rows[0].world_id)
    try:
        for row in rows:
            buffer._insert(row)
    except Exception:
        buffer.close()
        path.unlink(missing_ok=True)
        raise
    logger.info("built %s: %d assertions, world %s", path, len(rows), rows[0].world_id)
    return buffer
