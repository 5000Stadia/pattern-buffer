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
from patternbuffer.model import (  # noqa: F401 — the policies are re-exported
    CANON,
    DENY,
    INVENT_UNDER_CANON,
    MECHANISM_STATUS,
    OBSERVE_OR_UNKNOWN,
    POLICIES,
    TASK_RESOLVE,
    Assertion,
    ResolveRequest,
    task_schema,
)
from patternbuffer.roles import WriterRole
from patternbuffer.semantics import AttributeSemantics

logger = logging.getLogger(__name__)

# INVENT_UNDER_CANON, OBSERVE_OR_UNKNOWN, DENY and POLICIES live in `model`
# (READ-SURFACE-V1 §7: the buffer validates the physics row against them).

UNKNOWN = object()  # the honest answer in observe_or_unknown worlds

_RESOLVE_SCHEMA = {
    "title": TASK_RESOLVE,
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
        semantics: AttributeSemantics | None = None,
        cursor: Callable[[], float | None] | None = None,
    ) -> None:
        if world_policy not in POLICIES:
            raise ValueError(f"unknown policy {world_policy!r}")
        self._buffer = buffer
        self._classifier = classifier
        self._indexes = indexes
        self._role = role
        self._model = model
        self._world_policy = world_policy
        # RESOLVE-UNMARKED-V1: the declarations that open an aspect to
        # invention, and the scene cursor an undated placeholder sits at. A
        # resolver wired with neither never plants (the pre-E1 behavior).
        self._semantics = semantics
        self._cursor = cursor

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
        """The thunk's memo marker — honored only with the resolver's own
        mark, status ``generated`` (GATE-AUTHORITY-V1 §1): a forged
        ``resolved_by`` row neither spends the thunk nor names its memo."""
        for marker in self._buffer.visible(entity=thunk_row.id, attribute="resolved_by"):
            if marker.status == MECHANISM_STATUS["resolved_by"]:
                return marker
        return None

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
        return self.resolve_planted(entity, aspect, frame, access)[0]

    def resolve_planted(
        self,
        entity: str,
        aspect: str,
        frame: str = CANON,
        access: object | None = None,
        *,
        joined: bool = False,
    ) -> tuple[list[Assertion] | object, bool]:
        """`resolve`, and whether this call planted the placeholder it forced
        (RESOLVE-UNMARKED-V1). ``joined`` (WORLD-SERVICE-V1 §7b) is the one
        internal flag that lets the plant-and-force run inside a unit its
        caller already opened (the `perceive_in` path); it is never a general
        rule that units nest, and a nested ``atomic_unit`` elsewhere is
        refused as ever."""
        thunk = self._find_thunk_row(entity, aspect, frame)

        # Memoized: a spent thunk serves its cache, forever, identically.
        if thunk is not None:
            marker = self._resolved_marker(thunk)
            if marker is not None:
                ids = marker.value if isinstance(marker.value, list) else [marker.value]
                return [self._buffer.get(i) for i in ids], False

        # Concrete state on the key answers without any thunk machinery.
        fold = self._indexes.fold_key(entity, aspect, frame)
        if fold.winner is not None and fold.winner.value_type != "unresolved":
            return [fold.winner], False

        if thunk is None:
            if self._may_plant(entity, aspect, frame):
                return self._plant_and_force(entity, aspect, frame, joined), True
            return (UNKNOWN if self._world_policy == OBSERVE_OR_UNKNOWN else []), False

        spec = thunk.value if isinstance(thunk.value, dict) else {}
        policy = spec.get("policy", self._world_policy)
        if policy == DENY:
            raise ResolutionDenied(f"{entity}·{aspect} is sealed (policy=deny)")
        if policy == OBSERVE_OR_UNKNOWN:
            return UNKNOWN, False  # never invents; only observation resolves
        return self._invent(thunk, spec, frame), False

    # ------------------------------------------- the unmarked (RESOLVE-UNMARKED-V1)

    def undeclared_reason(self, entity: str, aspect: str, frame: str = CANON) -> str | None:
        """Why `aspect` of `entity` is not open to invention, as prose for a
        module to read; None when the aspect is declared ``resolvable_for``
        the entity's folded kind."""
        kinds = self._semantics.resolvable_kinds(aspect) if self._semantics else frozenset()
        if not kinds:
            return f"{aspect!r} is not declared resolvable_for any kind in this world"
        winner = self._indexes.fold_key(entity, "kind", frame).winner
        kind = None if winner is None or winner.value_type == "unresolved" else winner.value
        if not isinstance(kind, str) or kind not in kinds:
            return (f"{aspect!r} is declared resolvable_for {sorted(kinds)}, "
                    f"not for the kind of {entity} ({kind!r})")
        return None

    def has_thunk(self, entity: str, aspect: str, frame: str = CANON) -> bool:
        """Whether a placeholder for (entity, aspect) stands in the frame."""
        return self._find_thunk_row(entity, aspect, frame) is not None

    def opted_in(self) -> bool:
        """Whether this is an inventing world that declares any aspect
        resolvable: the only world in which an undeclared aspect is reported."""
        return (self._semantics is not None and self._semantics.has_resolvable()
                and self._world_policy == INVENT_UNDER_CANON)

    def _may_plant(self, entity: str, aspect: str, frame: str) -> bool:
        """The unmarked case's guard (RESOLVE-UNMARKED-V1 §2): the world
        invents under canon, the aspect is declared for the entity's folded
        kind, and, for `contents`, the entity holds nothing. The placeholder
        and the concrete value were ruled out by the caller."""
        if self._world_policy != INVENT_UNDER_CANON:
            return False
        if self.undeclared_reason(entity, aspect, frame) is not None:
            return False
        return not (aspect == "contents" and self._indexes.contents(entity, frame=frame))

    def _plant_and_force(self, entity: str, aspect: str, frame: str,
                         joined: bool = False) -> list[Assertion]:
        """Plant the resolver's own `generated` placeholder and force it in ONE
        atomic unit (ATOMIC-ACTIVATION-V1): a failure anywhere, the model
        included, leaves neither the placeholder nor any row. The placeholder
        is timeless when the host pinned the aspect CONSTITUTIVE or
        DISPOSITIONAL, otherwise it sits at the scene cursor."""
        pin = self._semantics.durability_pin(aspect) if self._semantics else None
        valid_from = (None if pin in (CONSTITUTIVE, DISPOSITIONAL) or self._cursor is None
                      else self._cursor())
        subject = self._indexes.resolve_entity(entity)
        spec = {"policy": self._world_policy, "planted": "resolve"}

        def body() -> list[Assertion]:
            placeholder = self._buffer.append(
                entity=subject, attribute=aspect, value=spec, value_type="unresolved",
                valid_from=valid_from, frame=frame, status="generated", role=self._role,
            )
            self._classifier.classify(placeholder)  # guardrail: STATE
            return self._invent(placeholder, spec, frame)

        if joined and not self._buffer.unit_open:
            raise RuntimeError("a joined plant-and-force needs the caller's open unit")
        out = body() if joined else self._buffer.atomic_unit(body)
        logger.info("planted and resolved %s·%s", subject, aspect)
        return out

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
        inherited = self._inherited_facts(thunk_row.entity, frame)
        declared = [str(c) for c in spec.get("constraints", ())]
        constraints = [
            f"{holder} · {attr} · {json.dumps(value, default=json_default)}"
            for holder, attr, value in inherited
        ] + declared
        prompt = (
            f"Resolve an unestablished aspect of a fictional world: the "
            f"{thunk_row.attribute} of {thunk_row.entity}.\n"
            "Invent content CONSISTENT WITH every constraint below; introduce "
            "nothing that contradicts them. Plain, concrete items only.\n\n"
            "Constraints (canon, in force):\n- " + "\n- ".join(constraints or ["(none)"])
        )
        # RESOLVE-REQUEST-V1: the same call, its purpose also carried as data.
        kind = self._indexes.fold_key(thunk_row.entity, "kind", frame).winner
        request = ResolveRequest(
            world_id=self._buffer.world_id,
            entity=thunk_row.entity,
            aspect=thunk_row.attribute,
            kind=None if kind is None or kind.value_type == "unresolved" else kind.value,
            inherited=tuple(inherited),
            declared=tuple(declared),
            as_of=thunk_row.valid_from,
            frame=frame,
            policy=spec.get("policy", self._world_policy),
        )
        out = self._model(prompt, task_schema(_RESOLVE_SCHEMA, request))
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

    def _inherited_facts(self, entity: str, frame: str) -> list[tuple[str, str, Any]]:
        """Constraint inheritance: CONSTITUTIVE + DISPOSITIONAL rows of the
        entity and every containment ancestor (whitepaper §8), as
        ``(holder, attribute, value)`` in prompt order (RESOLVE-REQUEST-V1)."""
        constraints: list[tuple[str, str, Any]] = []
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
                    constraints.append((holder, attr, row.value))
        return constraints
