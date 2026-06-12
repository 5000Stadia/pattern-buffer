"""Parser for the INGEST-V2 line grammar.

The harness grammar is intentionally pure: it depends only on a registry
object exposing an ``entities`` mapping whose keys are known entity ids.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

FIELD_RE = re.compile(r"[a-z][a-z0-9_:]*")
STATUSES = {"stated", "observed", "inferred", "assumed"}


@dataclass(frozen=True)
class Orphan:
    """A syntactically valid line quarantined by registry validation."""

    line_no: int
    line: str
    entity_id: str
    position: str


@dataclass(frozen=True)
class Reject:
    """A malformed line rejected by the parser."""

    line_no: int
    line: str
    reason: str


def parse(
    lines: list[str],
    registry: Any,
    cursor: float,
) -> tuple[list[dict[str, Any]], list[Orphan], list[Reject]]:
    """Parse INGEST-V2 grammar lines into structured ingest items.

    ``registry`` is duck-typed: anything exposing an ``entities`` mapping
    whose keys are the known entity ids.
    """
    known_entities = set(registry.entities.keys())
    items: list[dict[str, Any]] = []
    orphans: list[Orphan] = []
    rejects: list[Reject] = []

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        try:
            parts = stripped.split("|", 2)
            if len(parts) < 3:
                raise ValueError("expected entity|attribute|value")
            entity, attribute, rest = parts
            _validate_fields(entity, attribute)
            value, value_type, flags_text = _parse_value_and_flags(rest)
            flags = _parse_flags(flags_text)
        except ValueError as exc:
            rejects.append(Reject(line_no=line_no, line=line, reason=str(exc)))
            continue

        item: dict[str, Any] = {
            "entity": entity,
            "attribute": attribute,
            "value": value,
        }
        if value_type is not None:
            item["value_type"] = value_type
        item.update(flags)
        if "valid_from" not in item and not item.get("timeless", False):
            item["valid_from"] = cursor

        orphan = _find_orphan(item, known_entities, line_no, line)
        if orphan is not None:
            orphans.append(orphan)
            continue

        items.append(item)

    return items, orphans, rejects


def reject_rate(
    items: list[dict[str, Any]],
    orphans: list[Orphan],
    rejects: list[Reject],
) -> float:
    """Return malformed-line rate, with orphans counted only in the denominator."""
    total = len(items) + len(orphans) + len(rejects)
    if total == 0:
        return 0.0
    return len(rejects) / total


def _validate_fields(entity: str, attribute: str) -> None:
    if FIELD_RE.fullmatch(entity) is None:
        raise ValueError("invalid entity field")
    if FIELD_RE.fullmatch(attribute) is None:
        raise ValueError("invalid attribute field")


def _parse_value_and_flags(rest: str) -> tuple[Any, str | None, str]:
    """Decode the value (exactly once) and return its trailing flags text.

    JSON values are boundary-detected with raw_decode, so delimiter
    characters inside them never split the line.
    """
    if rest.startswith("?"):
        if not rest.startswith("?{"):
            raise ValueError("unresolved value must be ?{...}")
        value, end = _raw_decode(rest, 1)
        return value, "unresolved", _flags_after(rest, end)
    if rest.startswith(("{", "[", '"')):
        value, end = _raw_decode(rest, 0)
        return value, None, _flags_after(rest, end)
    value_text, _, flags_text = rest.partition("|")
    if value_text.startswith("@"):
        return value_text[1:], "entity", flags_text
    return _coerce_bare_scalar(value_text), None, flags_text


def _raw_decode(text: str, start: int) -> tuple[Any, int]:
    try:
        value, end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON value") from exc
    return value, end + start


def _flags_after(text: str, end: int) -> str:
    if end == len(text):
        return ""
    if text[end] != "|":
        raise ValueError("unexpected trailing data after JSON value")
    return text[end + 1 :]


def _coerce_bare_scalar(text: str) -> int | float | bool | str:
    try:
        return int(text)
    except ValueError:
        pass

    try:
        return float(text)
    except ValueError:
        pass

    if text == "true":
        return True
    if text == "false":
        return False
    return text


def _parse_flags(text: str) -> dict[str, Any]:
    if not text:
        return {}

    flags: dict[str, Any] = {}
    for raw_flag in text.split(","):
        flag = raw_flag.strip()
        if flag == "t":
            flags["timeless"] = True
        elif flag.startswith("vf="):
            flags["valid_from"] = _parse_float_flag("vf", flag[3:])
        elif flag.startswith("vt="):
            flags["valid_to"] = _parse_float_flag("vt", flag[3:])
        elif flag.startswith("f="):
            flags["frame"] = flag[2:]
        elif flag.startswith("s="):
            status = flag[2:]
            if status not in STATUSES:
                raise ValueError(f"invalid status {status!r}")
            flags["status"] = status
        elif flag.startswith("doc="):
            flags["source_doc"] = flag[4:]
        elif flag.startswith("cb="):
            flags["caused_by"] = flag[3:]
        else:
            raise ValueError(f"unknown flag {flag!r}")
    return flags


def _parse_float_flag(name: str, text: str) -> float:
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"invalid {name} flag") from exc


def _complete_id(entity_id: str, known_entities: set[str]) -> str | None:
    """Deterministic namespace completion: an id the model emitted without
    its namespace ('narrator') completes to the registry id iff exactly one
    known id has that suffix ('person:narrator'). Ambiguity stays an orphan
    — completion never guesses."""
    if entity_id in known_entities:
        return entity_id
    if ":" not in entity_id:
        matches = [k for k in known_entities if k.split(":", 1)[1] == entity_id]
        if len(matches) == 1:
            return matches[0]
    return None


def _find_orphan(
    item: dict[str, Any],
    known_entities: set[str],
    line_no: int,
    line: str,
) -> Orphan | None:
    """Validate (and where unambiguous, namespace-complete) all four id
    positions. Mutates `item` in place when completion applies."""
    completed = _complete_id(item["entity"], known_entities)
    if completed is None:
        return Orphan(line_no=line_no, line=line, entity_id=item["entity"],
                      position="subject")
    item["entity"] = completed

    if item.get("value_type") == "entity":
        completed = _complete_id(item["value"], known_entities)
        if completed is None:
            return Orphan(line_no=line_no, line=line, entity_id=item["value"],
                          position="value")
        item["value"] = completed

    if "caused_by" in item:
        completed = _complete_id(item["caused_by"], known_entities)
        if completed is None:
            return Orphan(line_no=line_no, line=line, entity_id=item["caused_by"],
                          position="caused_by")
        item["caused_by"] = completed

    frame = item.get("frame")
    if isinstance(frame, str) and frame.startswith("knows:"):
        inner = frame.removeprefix("knows:")
        completed = _complete_id(inner, known_entities)
        if completed is None:
            return Orphan(line_no=line_no, line=line, entity_id=inner,
                          position="frame")
        item["frame"] = f"knows:{completed}"
    return None


__all__ = ["Orphan", "Reject", "parse", "reject_rate"]
