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
from patternbuffer.codec import json_default
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
        thunk = self._find_thunk_row(entity, aspect, frame)

        # Memoized: a spent thunk serves its cache, forever, identically.
        if thunk is not None:
            marker = self._resolved_marker(thunk)
            if marker is not None:
                ids = marker.value if isinstance(marker.value, list) else [marker.value]
                return [self._buffer.get(i) for i in ids]

        # Concrete state on the key answers without any thunk machinery.
        fold = self._indexes.fold_key(entity, aspect, frame)
        if fold.winner is not None and fold.winner.value_type != "unresolved":
            return [fold.winner]

        if thunk is None:
            return UNKNOWN if self._world_policy == OBSERVE_OR_UNKNOWN else []

        spec = thunk.value if isinstance(thunk.value, dict) else {}
        policy = spec.get("policy", self._world_policy)
        if policy == DENY:
            raise ResolutionDenied(f"{entity}·{aspect} is sealed (policy=deny)")
        if policy == OBSERVE_OR_UNKNOWN:
            return UNKNOWN  # never invents; only observation resolves
        return self._invent(thunk, spec, frame)

    def _find_thunk_row(self, entity: str, aspect: str, frame: str) -> Assertion | None:
        canonical = self._indexes.resolve_entity(entity)
        rows = [
            r
            for r in self._buffer.visible(attribute=aspect, frame=frame)
            if r.value_type == "unresolved"
            and self._indexes.resolve_entity(r.entity) == canonical
        ]
        return rows[-1] if rows else None

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
        if thunk_row.attribute == "contents":
            # Contents are never literal rows on one key (P2: emptiness and
            # contents derive from the tree). Invention mints entities with
            # containment edges; the contents query serves them forever.
            for item in out["items"]:
                eid = f"obj:gen_{self._buffer.head() + 1}"
                kind_row = self._buffer.append(
                    entity=eid, attribute="kind", value=str(item.get("kind", "object")),
                    frame=frame, status="generated", role=self._role,
                )
                name_row = self._buffer.append(
                    entity=eid, attribute="name", value=str(item["value"]),
                    frame=frame, status="generated", role=self._role,
                )
                edge = self._buffer.append(
                    entity=eid, attribute="in", value=thunk_row.entity,
                    value_type="entity", valid_from=thunk_row.valid_from,
                    frame=frame, status="generated", role=self._role,
                )
                self._classifier.classify(kind_row)   # guardrail: CONSTITUTIVE
                self._classifier.classify(name_row)   # guardrail: CONSTITUTIVE
                # The resolver holds the world context here: invented
                # contents are movables. Judgment injected, log untouched.
                self._classifier.set(edge.id, "STATE")
                appended.append(edge)
        else:
            for item in out["items"]:
                row = self._buffer.append(
                    entity=thunk_row.entity,
                    attribute=thunk_row.attribute,
                    value=item["value"],
                    value_type="literal",
                    valid_from=thunk_row.valid_from,
                    frame=frame,
                    status="generated",
                    role=self._role,
                )
                self._classifier.classify(row)
                appended.append(row)
        marker = self._buffer.append(
            entity=thunk_row.id,
            attribute="resolved_by",
            value=[a.id for a in appended],
            status="generated",
            role=self._role,
        )
        self._classifier.classify(marker)  # closed under its own operations
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
                if result.quantity is not None:
                    continue  # an accrue running total is not a scene-invention
                              # constraint, and its winner is a delta row, never
                              # the value (never inherit a delta as a constraint)
                if self._classifier.durability(row.id) in {CONSTITUTIVE, DISPOSITIONAL}:
                    constraints.append(
                        f"{holder} · {attr} · {json.dumps(row.value, default=json_default)}"
                    )
        return constraints
