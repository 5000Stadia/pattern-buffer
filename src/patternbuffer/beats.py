"""Beats (BEATS-V1): the written shape of a beat condition, and the reference lint
that keeps the plot out of reachable frames.

This module sits outside the engine core, as ``vocab`` and ``service`` do. It
reaches the engine only through seams the engine already has, and it writes
nothing and calls no model. The engine stores no beat, evaluates no condition
and fires no effect; a host does, with its own evaluator.

- :data:`CONDITION_SCHEMA` names the one condition grammar, ``patternbuffer.condition/1``,
  the JSON object construct's ``arc/io.py`` writes. The published contract is the
  JSON Schema file ``schemas/patternbuffer.condition-1.json``.
- :func:`validate_condition` is a shape check of one condition object against that
  grammar. The engine takes no ``jsonschema`` dependency, so the rules are written
  out here; a test pins them to the schema file.
- :func:`author_references` is a read-only lint, never a gate: it finds a row in a
  frame a player can reach that names something only an **author frame** holds
  (BEATS-V1 §1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable

from patternbuffer.model import (ATTR_PREFIX, CANON, KNOWS_PREFIX, MECHANISM_ATTRIBUTES,
                                 META_ATTRIBUTES, is_author_frame)

logger = logging.getLogger(__name__)

__all__ = [
    "ATOMS", "CONDITION_SCHEMA", "FINDING_KINDS", "Finding", "OPERATORS",
    "author_references", "validate_condition",
]

#: The pinned grammar version. A change to either side's grammar is a ``/2``.
CONDITION_SCHEMA = "patternbuffer.condition/1"

FINDING_KINDS = ("author_frame_reference", "dangling_caused_by")

# ------------------------------------------------------------- the grammar
#
# Field kinds: "str", "int", "int?" (an integer or null), "number", "any" (any JSON
# value), "strs" (a list of strings), "cmp" (one of CMP_VALUES). Each atom is
# (required fields, defaulted fields): construct's serializer writes every field,
# its reader takes a defaulted one omitted.

CMP_VALUES = (">=", ">", "<=", "<", "==", "!=")

ATOMS: dict[str, tuple[dict[str, str], dict[str, str]]] = {
    "state_is": ({"entity": "str", "attribute": "str", "value": "any"}, {}),
    "located": ({"entity": "str", "place": "str"}, {}),
    "in_frame": ({"frame": "str", "entity": "str", "attribute": "str", "value": "any"}, {}),
    "occurred": ({"kind": "str"},
                 {"participants": "strs", "since": "int?", "until": "int?",
                  "min_count": "int"}),
    "beat_achieved": ({"beat_id": "str"}, {"plot_frame": "str"}),
    "clock_fired": ({"clock_id": "str"}, {"n": "int", "plot_frame": "str"}),
    "turns_elapsed": ({"at_least": "int"}, {}),
    "turns_quiet": ({"at_least": "int"}, {}),
    "quantity": ({"entity": "str", "attribute": "str", "cmp": "cmp", "value": "number"},
                 {"frame": "str"}),
}

#: The four operators: operator -> (scalar fields, whether it has ``operands`` or
#: a single ``operand``).
OPERATORS: dict[str, tuple[dict[str, str], str]] = {
    "not": ({}, "operand"),
    "all_of": ({}, "operands"),
    "any_of": ({}, "operands"),
    "at_least": ({"k": "int"}, "operands"),
}

_MAX_DEPTH = 200


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _is_int(value: Any) -> bool:
    """A JSON integer: a Python int (never a bool), or a float with no fraction
    (JSON Schema reads ``1.0`` as an integer)."""
    if isinstance(value, bool):
        return False
    return isinstance(value, int) or (isinstance(value, float) and value.is_integer())


def _check_kind(kind: str, value: Any) -> str | None:
    """None when ``value`` fits ``kind``, else what was expected."""
    if kind == "any":
        return None
    if kind == "str":
        return None if isinstance(value, str) else "a string"
    if kind == "int":
        return None if _is_int(value) else "an integer"
    if kind == "int?":
        return None if value is None or _is_int(value) else "an integer or null"
    if kind == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        return None if ok else "a number"
    if kind == "strs":
        ok = isinstance(value, list) and all(isinstance(v, str) for v in value)
        return None if ok else "an array of strings"
    if kind == "cmp":
        return None if value in CMP_VALUES and isinstance(value, str) else f"one of {list(CMP_VALUES)}"
    raise AssertionError(f"unknown field kind {kind!r}")


def _check_fields(obj: dict, path: str, op: str, required: dict[str, str],
                  optional: dict[str, str], out: list[str]) -> None:
    for name in required:
        if name not in obj:
            out.append(f"{path}: {op} is missing the required field {name!r}")
    for name, kind in {**required, **optional}.items():
        if name in obj:
            want = _check_kind(kind, obj[name])
            if want is not None:
                out.append(f"{path}.{name}: expected {want}, got {_type_name(obj[name])}"
                           + (f" {obj[name]!r}" if kind == "cmp" else ""))
    for name in obj:
        if name != "op" and name not in required and name not in optional:
            out.append(f"{path}: {op} has an unexpected field {name!r}")


def _check_expr(obj: Any, path: str, depth: int, out: list[str]) -> None:
    if depth > _MAX_DEPTH:
        out.append(f"{path}: nested deeper than {_MAX_DEPTH} levels")
        return
    if not isinstance(obj, dict):
        out.append(f"{path}: expected an object, got {_type_name(obj)}")
        return
    if "op" not in obj:
        out.append(f"{path}: missing the field 'op'")
        return
    op = obj["op"]
    if not isinstance(op, str) or (op not in ATOMS and op not in OPERATORS):
        out.append(f"{path}.op: unknown op {op!r} "
                   f"(one of {sorted(ATOMS) + sorted(OPERATORS)})")
        return
    if op in ATOMS:
        required, optional = ATOMS[op]
        _check_fields(obj, path, op, required, optional, out)
        return
    scalars, child = OPERATORS[op]
    required = {**scalars, child: "any"}
    _check_fields(obj, path, op, required, {}, out)
    if child == "operand":
        if child in obj:
            _check_expr(obj[child], f"{path}.operand", depth + 1, out)
    elif child in obj:
        operands = obj[child]
        if not isinstance(operands, list):
            out.append(f"{path}.operands: expected an array, got {_type_name(operands)}")
        else:
            for i, operand in enumerate(operands):
                _check_expr(operand, f"{path}.operands[{i}]", depth + 1, out)


def validate_condition(obj: Any) -> list[str]:
    """The problems with ``obj`` as a ``patternbuffer.condition/1`` object; an empty
    list is a valid condition. A shape check only: it evaluates nothing, reads no
    world and never raises on a malformed ``obj``.

    ``obj`` is the decoded object, not the JSON string a beat stores (a string is
    reported). One problem is named per fault, each led by its path from the root
    (``$``): an unknown ``op``, a missing required field, a wrong type, a ``cmp``
    outside the six comparators, an unexpected field. A field with a default may be
    omitted. The rules are those of ``schemas/patternbuffer.condition-1.json``."""
    problems: list[str] = []
    _check_expr(obj, "$", 0, problems)
    return problems


# ------------------------------------------------------- the reference lint


@dataclass(frozen=True)
class Finding:
    """One thing :func:`author_references` found in one row. ``kind`` is one of
    :data:`FINDING_KINDS`; ``row_id`` is the stored row's assertion id, ``entity``
    and ``attribute`` are as stored, ``target`` is the id the row names (its
    entity, its entity value, or its ``caused_by`` target) and ``detail`` says why
    in a sentence."""

    kind: str
    row_id: str
    entity: str
    attribute: str
    target: str
    detail: str


def author_references(world: Any, *, frames: Iterable[str] = (CANON,)) -> list[Finding]:
    """Lint ``frames`` of ``world`` for references that carry the plot into a frame
    a player can reach (BEATS-V1 §1). Read-only: no write, no model call. A lint,
    never a gate: it reports, and every row stays as written.

    ``frames`` lists stored frame names; ``"knows:*"`` stands for every ``knows:``
    frame that has a row. An author frame (``plot:*``) in ``frames`` is a
    ``ValueError`` (its rows are the plot), as is a bare string.

    Each row of the frames (all of valid time; bookkeeping attributes other than
    ``caused_by`` are left out) is checked for the ids it names: its entity, its
    value when entity-valued, and, on a ``caused_by`` row, its target. Ids are read
    through the identity closure. The findings, grouped by kind and in log order, are:

    - ``author_frame_reference``: a named id has rows in an author frame and none
      in canon;
    - ``dangling_caused_by``: a ``caused_by`` target has no canon row at all.

    A ``caused_by`` row rides in its effect's frame and its entity is the effect
    row's id, so it is reported as stored and ``detail`` names the effect. A target
    that is both plot-only and uncaused is reported under both kinds."""
    if isinstance(frames, str):
        raise TypeError("frames is a list of frame names, not a bare string")
    wanted = tuple(frames)
    if not wanted:
        raise ValueError("frames names no frame to lint")
    for name in wanted:
        if not isinstance(name, str) or not name:
            raise ValueError(f"a frame is a non-empty name, not {name!r}")
        if is_author_frame(name):
            raise ValueError(f"{name!r} is an author frame: it holds the plot, so there "
                             "is nothing in it to lint for plot references")

    registry = world.registry
    resolved: dict[str, str] = {}

    def ident(raw: str) -> str:
        if raw not in resolved:
            resolved[raw] = registry.resolve(raw)
        return resolved[raw]

    def is_subject(raw: str) -> bool:
        return not raw.startswith("a:") and not raw.startswith(ATTR_PREFIX)

    rows = world.buffer.visible()
    in_canon: set[str] = set()
    in_author: set[str] = set()
    for r in rows:
        if not is_subject(r.entity):
            continue
        if r.frame == CANON:
            in_canon.add(ident(r.entity))
        elif is_author_frame(r.frame):
            in_author.add(ident(r.entity))

    knows_all = "knows:*" in wanted
    exact = {f for f in wanted if f != "knows:*"}
    bookkeeping = (META_ATTRIBUTES | MECHANISM_ATTRIBUTES) - {"caused_by"}
    by_id = {r.id: r for r in rows}
    out: list[Finding] = []

    for r in rows:
        if not (r.frame in exact or (knows_all and r.frame.startswith(KNOWS_PREFIX))):
            continue
        if r.attribute in bookkeeping or r.entity.startswith(ATTR_PREFIX):
            continue
        caused = r.attribute == "caused_by"
        named: list[tuple[str, str]] = []              # (target, how it is named)
        if is_subject(r.entity):
            named.append((r.entity, "its entity"))
        if r.value_type == "entity" and isinstance(r.value, str):
            named.append((r.value, "its caused_by target" if caused else "its value"))
        effect = ""
        if caused:
            eff = by_id.get(r.entity)
            effect = (f" (the effect row {r.entity}: {eff.entity} {eff.attribute})"
                      if eff is not None else f" (the effect row {r.entity})")
        for target, how in named:
            tid = ident(target)
            if tid in in_author and tid not in in_canon:
                out.append(Finding(
                    "author_frame_reference", r.id, r.entity, r.attribute, target,
                    f"{how} {target!r} has rows in an author frame and none in canon"
                    f"{effect}"))
            if caused and how == "its caused_by target" and tid not in in_canon:
                out.append(Finding(
                    "dangling_caused_by", r.id, r.entity, r.attribute, target,
                    f"the caused_by target {target!r} has no canon row{effect}"))

    out.sort(key=lambda f: f.kind)                    # stable: log order within a kind
    return out
