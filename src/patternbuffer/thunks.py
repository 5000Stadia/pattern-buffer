"""Thunks and the resolver: the lazy world (whitepaper §8, P3).

An unresolved aspect is a first-class row (value_type='unresolved') whose
value carries its policy and any accreted constraints. Forcing evaluates
exactly once; the memo is the fold (generated rows supersede the thunk's
key). Thunks move without resolving — containment supersession touches
the holder, never the thunk row.

The resolver is the only component that may append `generated` (§12).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import CONSTITUTIVE, DISPOSITIONAL, Classifier
from patternbuffer.indexes import Indexes
from patternbuffer.model import CANON, Assertion
from patternbuffer.roles import WriterRole

logger = logging.getLogger(__name__)

INVENT_UNDER_CANON = "invent_under_canon"
OBSERVE_OR_UNKNOWN = "observe_or_unknown"
DENY = "deny"
POLICIES = frozenset({INVENT_UNDER_CANON, OBSERVE_OR_UNKNOWN, DENY})

UNKNOWN = object()  # the honest answer in observe_or_unknown worlds

_RESOLVE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "value": {},
                    "detail": {"type": "string"},
                },
                "required": ["value"],
            },
        }
    },
    "required": ["items"],
}


class ResolutionDenied(PermissionError):
    """The thunk's policy refuses resolution (deny/reserve)."""


@dataclass(frozen=True, slots=True)
class ThunkView:
    entity: str
    aspect: str
    policy: str
    constraints: tuple[str, ...]
    assertion_id: str


class Resolver:
    def __init__(
        self,
        buffer: PatternBuffer,
        classifier: Classifier,
        indexes: Indexes,
        role: WriterRole,
        model: Callable[[str, dict], Any],
        world_policy: str = INVENT_UNDER_CANON,
    ) -> None:
        if world_policy not in POLICIES:
            raise ValueError(f"unknown policy {world_policy!r}")
        self._buffer = buffer
        self._classifier = classifier
        self._indexes = indexes
        self._role = role
        self._model = model
        self._world_policy = world_policy

    # ----------------------------------------------------------- the table

    def thunk_table(self, frame: str = CANON) -> list[ThunkView]:
        """The frontier: open (un-superseded, unresolved) aspects."""
        out = []
        for row in self._buffer.visible(frame=frame):
            if row.value_type != "unresolved":
                continue
            result = self._indexes.fold_key(row.entity, row.attribute, frame)
            if result.winner is None or result.winner.id != row.id:
                continue  # superseded: resolved or overwritten
            if self._resolved_marker(row) is not None:
                continue
            spec = row.value if isinstance(row.value, dict) else {}
            out.append(
                ThunkView(
                    entity=row.entity,
                    aspect=row.attribute,
                    policy=spec.get("policy", self._world_policy),
                    constraints=tuple(spec.get("constraints", ())),
                    assertion_id=row.id,
                )
            )
        return out

    def _resolved_marker(self, thunk_row: Assertion) -> Assertion | None:
        markers = self._buffer.visible(entity=thunk_row.id, attribute="resolved_by")
        return markers[0] if markers else None

    # ------------------------------------------------------------- forcing

    def resolve(
        self,
        entity: str,
        aspect: str,
        frame: str = CANON,
        access: object | None = None,
    ) -> list[Assertion] | object:
        """Force a thunk per policy. Memoized: a second force serves the
        cache. `access` is the observer-position seam (spec §9.2) —
        accepted, not yet exercised in the spike."""
        fold = self._indexes.fold_key(entity, aspect, frame)
        if fold.winner is None:
            return UNKNOWN if self._world_policy == OBSERVE_OR_UNKNOWN else []
        row = fold.winner
        if row.value_type != "unresolved":
            return [row]  # already concrete (incl. previously memoized)

        marker = self._resolved_marker(row)
        if marker is not None:
            ids = marker.value if isinstance(marker.value, list) else [marker.value]
            return [self._buffer.get(i) for i in ids]

        spec = row.value if isinstance(row.value, dict) else {}
        policy = spec.get("policy", self._world_policy)
        if policy == DENY:
            raise ResolutionDenied(f"{entity}·{aspect} is sealed (policy=deny)")
        if policy == OBSERVE_OR_UNKNOWN:
            return UNKNOWN  # never invents; only observation resolves
        return self._invent(row, spec, frame)

    def _invent(self, thunk_row: Assertion, spec: dict, frame: str) -> list[Assertion]:
        constraints = self._inherited_constraints(thunk_row.entity, frame)
        constraints += [str(c) for c in spec.get("constraints", ())]
        prompt = (
            f"Resolve an unestablished aspect of a fictional world: the "
            f"{thunk_row.attribute} of {thunk_row.entity}.\n"
            "Invent content CONSISTENT WITH every constraint below; introduce "
            "nothing that contradicts them. Plain, concrete items only.\n\n"
            "Constraints (canon, in force):\n- " + "\n- ".join(constraints or ["(none)"])
        )
        out = self._model(prompt, _RESOLVE_SCHEMA)
        appended: list[Assertion] = []
        for item in out["items"]:
            appended.append(
                self._buffer.append(
                    entity=thunk_row.entity,
                    attribute=thunk_row.attribute,
                    value=item["value"],
                    value_type="literal",
                    valid_from=thunk_row.valid_from,
                    frame=frame,
                    status="generated",
                    role=self._role,
                )
            )
        marker = self._buffer.append(
            entity=thunk_row.id,
            attribute="resolved_by",
            value=[a.id for a in appended],
            status="generated",
            role=self._role,
        )
        # New assertions feed back through classification: the system is
        # closed under its own operations (whitepaper §13).
        for a in appended:
            self._classifier.classify(a)
        self._classifier.classify(marker)
        logger.info(
            "resolved %s·%s -> %d generated row(s)",
            thunk_row.entity, thunk_row.attribute, len(appended),
        )
        return appended

    def _inherited_constraints(self, entity: str, frame: str) -> list[str]:
        """Constraint inheritance: CONSTITUTIVE + DISPOSITIONAL rows of the
        entity and every containment ancestor (whitepaper §8)."""
        constraints: list[str] = []
        scope = [entity, *self._indexes.locate(entity, frame=frame)]
        for holder in scope:
            for attr, result in self._indexes.current_state(holder, frame=frame).items():
                row = result.winner
                if row is None or row.value_type == "unresolved":
                    continue
                if self._classifier.durability(row.id) in {CONSTITUTIVE, DISPOSITIONAL}:
                    constraints.append(f"{holder} · {attr} · {json.dumps(row.value)}")
        return constraints
