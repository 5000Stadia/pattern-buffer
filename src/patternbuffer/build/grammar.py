"""The build library's line grammar: INGEST-V2's, with a sentence citation.

A fact line is INGEST-V2's ``entity|attribute|value|flags`` led by the
sentence it comes from, in the chunk's own numbering::

    s3|person:mara|in|@place:mill|s=stated

The citation is a required field (BUILD-LIBRARY-V1 §3): a line without one is
refused. The value and flag syntax is INGEST-V2's, unchanged
(``evals/harness/grammar.py``, which stays the default harness path); the
library's copy writes no ``valid_from``: commit poses each chunk at its story
time. Ids are checked by the caller against the chunk's candidates and handles.
"""

from __future__ import annotations

import json
import re
from typing import Any

FIELD_RE = re.compile(r"[a-z][a-z0-9_:]*")
STATUSES = {"stated", "observed", "inferred", "assumed"}
CITATION_RE = re.compile(r"\[?s([0-9]+)\]?")
HANDLE_RE = re.compile(r"new:(0|[1-9][0-9]*)")


def is_handle(value: Any) -> bool:
    """Whether ``value`` is a local handle ``new:<k>``."""
    return isinstance(value, str) and HANDLE_RE.fullmatch(value) is not None


def handle_number(handle: str) -> int:
    return int(handle.split(":", 1)[1])


def parse_line(raw: str) -> tuple[int, dict[str, Any]] | None:
    """One line as ``(cited sentence, item)``; None for a blank line or a
    ``#`` comment. Raises ``ValueError`` naming what is malformed."""
    stripped = raw.rstrip("\r\n").strip()
    if not stripped or stripped.startswith("#"):
        return None
    cite, sep, rest = stripped.partition("|")
    match = CITATION_RE.fullmatch(cite.strip())
    if not sep or match is None:
        raise ValueError("missing sentence citation (s<N>|entity|attribute|value)")
    parts = rest.split("|", 2)
    if len(parts) < 3:
        raise ValueError("expected s<N>|entity|attribute|value")
    entity, attribute, tail = parts
    _validate_fields(entity, attribute)
    value, value_type, flags_text = _parse_value_and_flags(tail)
    item: dict[str, Any] = {"entity": entity, "attribute": attribute, "value": value}
    if value_type is not None:
        item["value_type"] = value_type
    item.update(_parse_flags(flags_text))
    return int(match.group(1)), item


def complete_id(entity_id: str, known: set[str]) -> str | None:
    """INGEST-V2's namespace completion: an id written without its namespace
    completes to the known id with that suffix iff exactly one has it."""
    if entity_id in known:
        return entity_id
    if ":" not in entity_id:
        matches = [k for k in known if k.split(":", 1)[1] == entity_id]
        if len(matches) == 1:
            return matches[0]
    return None


def id_positions(item: dict[str, Any]) -> list[tuple[str, str]]:
    """The ids an item names, as ``(position, id)``: its subject, its entity
    value, its ``caused_by`` and the observer of a ``knows:`` frame."""
    out = [("subject", item["entity"])]
    if item.get("value_type") == "entity" and isinstance(item.get("value"), str):
        out.append(("value", item["value"]))
    if isinstance(item.get("caused_by"), str):
        out.append(("caused_by", item["caused_by"]))
    frame = item.get("frame")
    if isinstance(frame, str) and frame.startswith("knows:"):
        out.append(("frame", frame.removeprefix("knows:")))
    return out


def replace_ids(item: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """A copy of ``item`` with every id in an id position mapped through
    ``mapping`` (ids it lacks stay as they are)."""
    out = dict(item)
    out["entity"] = mapping.get(out["entity"], out["entity"])
    if out.get("value_type") == "entity" and isinstance(out.get("value"), str):
        out["value"] = mapping.get(out["value"], out["value"])
    if isinstance(out.get("caused_by"), str):
        out["caused_by"] = mapping.get(out["caused_by"], out["caused_by"])
    frame = out.get("frame")
    if isinstance(frame, str) and frame.startswith("knows:"):
        inner = frame.removeprefix("knows:")
        out["frame"] = "knows:" + mapping.get(inner, inner)
    return out


# ------------------------------------------- INGEST-V2's value and flag syntax


def _validate_fields(entity: str, attribute: str) -> None:
    if FIELD_RE.fullmatch(entity) is None:
        raise ValueError("invalid entity field")
    if FIELD_RE.fullmatch(attribute) is None:
        raise ValueError("invalid attribute field")


def _parse_value_and_flags(rest: str) -> tuple[Any, str | None, str]:
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
    return text[end + 1:]


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
        elif flag.startswith("src="):
            flags["source_doc"] = flag[4:]
        elif flag.startswith("cb="):
            flags["caused_by"] = flag[3:]
        elif flag == "corr":
            flags["correction"] = True
        else:
            raise ValueError(f"unknown flag {flag!r}")
    return flags


def _parse_float_flag(name: str, text: str) -> float:
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"invalid {name} flag") from exc
