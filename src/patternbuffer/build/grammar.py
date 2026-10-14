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
from typing import Any, Mapping

from patternbuffer.model import ID_RE

FIELD_RE = re.compile(r"[a-z][a-z0-9_:]*")
STATUSES = {"stated", "observed", "inferred", "assumed"}
CITATION_RE = re.compile(r"\[?s([0-9]+)\]?")
HANDLE_RE = re.compile(r"new:(0|[1-9][0-9]*)")


def is_handle(value: Any) -> bool:
    """Whether ``value`` is a build handle ``new:<k>``."""
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


def names_entity(item: Mapping[str, Any]) -> bool:
    """Whether the item's value is an entity reference as the ingest gate reads
    it: ``value_type`` ``entity``, or no ``value_type`` (``None``, ``""`` or
    ``False`` count as none) and a string value matching the id grammar, which
    the gate then infers to be an entity."""
    value, value_type = item.get("value"), item.get("value_type")
    return isinstance(value, str) and (
        value_type == "entity" or (not value_type and ID_RE.fullmatch(value) is not None))


def id_positions(item: Mapping[str, Any]) -> list[tuple[str, str]]:
    """The ids an item names, as ``(position, id)``: its subject, its entity
    value (explicit or inferred, :func:`names_entity`), its ``caused_by``, the
    observer of a ``knows:`` frame, and its ``source`` (``doc=`` or ``src=``,
    r1.7). A source may also be document provenance (``doc:letter_1``), which
    the caller tells apart (``Registry.source_problem``)."""
    out = [("subject", item["entity"])]
    if names_entity(item):
        out.append(("value", item["value"]))
    if isinstance(item.get("caused_by"), str):
        out.append(("caused_by", item["caused_by"]))
    frame = item.get("frame")
    if isinstance(frame, str) and frame.startswith("knows:"):
        out.append(("frame", frame.removeprefix("knows:")))
    if isinstance(item.get("source_doc"), str):
        out.append(("source", item["source_doc"]))
    return out


def replace_ids(item: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """A copy of ``item`` with every id in an id position mapped through
    ``mapping`` (ids it lacks stay as they are)."""
    out = dict(item)
    out["entity"] = mapping.get(out["entity"], out["entity"])
    if names_entity(out):
        out["value"] = mapping.get(out["value"], out["value"])
    for field in ("caused_by", "source_doc"):
        if isinstance(out.get(field), str):
            out[field] = mapping.get(out[field], out[field])
    frame = out.get("frame")
    if isinstance(frame, str) and frame.startswith("knows:"):
        inner = frame.removeprefix("knows:")
        out["frame"] = "knows:" + mapping.get(inner, inner)
    return out


# The keys an item from `parse_line` can carry (BUILD-LIBRARY-V1 r1.7): commit
# accepts no other, so a result can say nothing the grammar could not.
GRAMMAR_KEYS = frozenset({"entity", "attribute", "value", "value_type", "timeless",
                          "valid_from", "valid_to", "frame", "status", "source_doc",
                          "caused_by", "correction"})


def grammar_problem(item: Mapping[str, Any]) -> str | None:
    """Why ``item`` is not an item :func:`parse_line` could write, or None: its
    keys are within :data:`GRAMMAR_KEYS` and each holds what the grammar puts
    there (a field-shaped entity and attribute, JSON data as the value,
    ``value_type`` only ``entity`` or ``unresolved``, a status from
    :data:`STATUSES`, ``timeless`` and ``correction`` only ``true``)."""
    extra = sorted(str(k) for k in set(item) - GRAMMAR_KEYS)
    if extra:
        return f"keys the grammar never writes: {', '.join(extra)}"
    for field in ("entity", "attribute"):
        value = item.get(field)
        if not isinstance(value, str) or FIELD_RE.fullmatch(value) is None:
            return f"{field} {value!r} is not a field the grammar writes"
    if item["attribute"] == "fixture":
        # CONTAINMENT-DURABILITY-V1 r1.2: a fixture is a host's declaration (a
        # manifest entry's `fixture`), never a model's guess. World-independent
        # first line; commit's `_checked` closes the alias route after the
        # target world's canonicalization.
        return "attribute 'fixture' is a host declaration; a model never writes it"
    if "value" not in item:
        return "no value"
    if not _json_data(item["value"]):
        return "the value is not JSON data"
    if "value_type" in item:
        value_type = item["value_type"]
        if value_type == "entity":
            if not isinstance(item["value"], str):
                return "an entity value must be an id string"
        elif value_type == "unresolved":
            if not isinstance(item["value"], dict):
                return "an unresolved value must be an object"
        else:
            return f"value_type {value_type!r} is not one the grammar writes"
    for flag in ("timeless", "correction"):
        if flag in item and item[flag] is not True:
            return f"{flag} is {item[flag]!r}; the grammar writes only true"
    for flag in ("valid_from", "valid_to"):
        if flag in item and (isinstance(item[flag], bool)
                             or not isinstance(item[flag], (int, float))):
            return f"{flag} {item[flag]!r} is not a number"
    for flag in ("frame", "source_doc", "caused_by"):
        if flag in item and not isinstance(item[flag], str):
            return f"{flag} {item[flag]!r} is not a string"
    if "status" in item and item["status"] not in STATUSES:
        return f"status {item['status']!r} is not one the grammar writes"
    return None


def _json_data(value: Any) -> bool:
    """Whether ``value`` is JSON data as the grammar decodes it."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(_json_data(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _json_data(v) for k, v in value.items())
    return False


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
