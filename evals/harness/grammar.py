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


@dataclass(frozen=True)
class _SplitLine:
    entity: str
    attribute: str
    value_text: str
    flags_text: str


def parse(
    lines: list[str],
    registry: "WorldRegistry-like",
    cursor: float,
) -> tuple[list[dict[str, Any]], list[Orphan], list[Reject]]:
    """Parse INGEST-V2 grammar lines into structured ingest items."""
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
            split = _split_line(stripped)
            _validate_fields(split.entity, split.attribute)
            value, value_type = _parse_value(split.value_text)
            flags = _parse_flags(split.flags_text)
        except ValueError as exc:
            rejects.append(Reject(line_no=line_no, line=line, reason=str(exc)))
            continue

        item: dict[str, Any] = {
            "entity": split.entity,
            "attribute": split.attribute,
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


def _split_line(line: str) -> _SplitLine:
    parts = line.split("|", 2)
    if len(parts) < 3:
        raise ValueError("expected entity|attribute|value")

    entity, attribute, rest = parts
    if rest.startswith(("?", "{", "[", '"')):
        value_text, flags_text = _split_structured_value(rest)
    else:
        value_text, sep, flags_text = rest.partition("|")
        if not sep:
            flags_text = ""

    return _SplitLine(
        entity=entity,
        attribute=attribute,
        value_text=value_text,
        flags_text=flags_text,
    )


def _split_structured_value(text: str) -> tuple[str, str]:
    json_start = 1 if text.startswith("?{") else 0
    if text.startswith("?") and json_start == 0:
        value_text, sep, flags_text = text.partition("|")
        return value_text, flags_text if sep else ""

    try:
        _, end = json.JSONDecoder().raw_decode(text[json_start:])
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON value") from exc

    end += json_start
    if end == len(text):
        return text, ""
    if text[end] != "|":
        raise ValueError("unexpected trailing data after JSON value")
    return text[:end], text[end + 1 :]


def _validate_fields(entity: str, attribute: str) -> None:
    if FIELD_RE.fullmatch(entity) is None:
        raise ValueError("invalid entity field")
    if FIELD_RE.fullmatch(attribute) is None:
        raise ValueError("invalid attribute field")


def _parse_value(text: str) -> tuple[Any, str | None]:
    if text.startswith(("?", "{", "[", '"')):
        if text.startswith("?{"):
            try:
                return json.loads(text[1:]), "unresolved"
            except json.JSONDecodeError as exc:
                raise ValueError("invalid unresolved policy JSON") from exc
        if text.startswith("?"):
            return _coerce_bare_scalar(text), None
        try:
            return json.loads(text), None
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON value") from exc

    if text.startswith("@"):
        return text[1:], "entity"

    return _coerce_bare_scalar(text), None


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


def _find_orphan(
    item: dict[str, Any],
    known_entities: set[str],
    line_no: int,
    line: str,
) -> Orphan | None:
    checks = [
        ("subject", item["entity"]),
    ]
    if item.get("value_type") == "entity":
        checks.append(("value", item["value"]))
    if "caused_by" in item:
        checks.append(("caused_by", item["caused_by"]))
    frame = item.get("frame")
    if isinstance(frame, str) and frame.startswith("knows:"):
        checks.append(("frame", frame.removeprefix("knows:")))

    for position, entity_id in checks:
        if entity_id not in known_entities:
            return Orphan(
                line_no=line_no,
                line=line,
                entity_id=entity_id,
                position=position,
            )
    return None


__all__ = ["Orphan", "Reject", "parse", "reject_rate"]
