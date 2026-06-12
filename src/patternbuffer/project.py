"""The projector: materialize() (whitepaper §13; spec §9.1).

The projector writes nothing durable. Out-of-frame rows are absent from
the payload — filtering happens at source, in the row selection, never
as a marking pass. The CONSTITUTIVE spine is budget-exempt. Closed-world
render commitments are payload-only `default` marks that can never
harden into canon.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import CONSTITUTIVE, DISPOSITIONAL, EVENT, STATE, Classifier
from patternbuffer.indexes import Indexes
from patternbuffer.model import CANON, Assertion

logger = logging.getLogger(__name__)

LENSES = frozenset({"establishing_set", "current_state", "what_happened", "character_sheet"})

# Kind defaults: render-coherence fills, never fact claims (whitepaper
# §3.1). Deliberately tiny in the spike.
KIND_DEFAULTS: dict[str, dict[str, object]] = {
    "room": {"lighting": "unremarkable", "walls": "plain"},
    "person": {"build": "average"},
}


@dataclass(frozen=True, slots=True)
class DefaultFill:
    entity: str
    attribute: str
    value: object
    status: str = "default"  # payload-only; no role can append this


@dataclass
class Materialization:
    scope: tuple[str, ...]
    frame: str
    as_of: float | None
    asserted_as_of: int | None
    lens: str
    assertions: list[Assertion] = field(default_factory=list)
    defaults: list[DefaultFill] = field(default_factory=list)
    conflicted_keys: list[tuple[str, str]] = field(default_factory=list)
    unresolved: list[tuple[str, str]] = field(default_factory=list)  # the visible frontier
    truncated: int = 0  # rows dropped to budget (never CONSTITUTIVE)


class Projector:
    def __init__(self, buffer: PatternBuffer, classifier: Classifier, indexes: Indexes) -> None:
        self._buffer = buffer
        self._classifier = classifier
        self._indexes = indexes

    # ------------------------------------------------------------ scoping

    def _scope_entities(self, scope: str | list[str], frame: str,
                        valid_as_of: float | None, asserted_as_of: int | None) -> list[str]:
        """A scope is an entity list, or a container whose subtree it is."""
        roots = [scope] if isinstance(scope, str) else list(scope)
        out: list[str] = []
        seen: set[str] = set()
        frontier = [self._indexes.resolve_entity(r) for r in roots]
        while frontier:
            e = frontier.pop(0)
            if e in seen:
                continue
            seen.add(e)
            out.append(e)
            frontier.extend(
                self._indexes.contents(e, frame, valid_as_of, asserted_as_of)
            )
        return out

    def _establishing_scope(self, scope: str | list[str], frame: str,
                            valid_as_of: float | None, asserted_as_of: int | None) -> list[str]:
        """Subtree membership by establishing containment edges."""
        from patternbuffer.model import CONTAINMENT_FAMILY

        roots = {self._indexes.resolve_entity(r)
                 for r in ([scope] if isinstance(scope, str) else scope)}
        by_entity: dict[str, list[Assertion]] = {}
        for row in self._buffer.visible(
            frame=frame, valid_as_of=valid_as_of, asserted_as_of=asserted_as_of
        ):
            if row.attribute in CONTAINMENT_FAMILY and not row.entity.startswith("a:"):
                by_entity.setdefault(self._indexes.resolve_entity(row.entity), []).append(row)
        parent: dict[str, str] = {}
        for entity, rows in by_entity.items():
            qualifying = [
                r for r in rows
                if r.value_type == "entity"
                and (
                    self._classifier.durability(r.id) != STATE
                    or not self._indexes._is_event_effect(r, asserted_as_of)
                )
            ]
            if qualifying:
                first = min(qualifying, key=lambda r: (r.valid_from or float("-inf"), r.asserted_at))
                parent[entity] = self._indexes.resolve_entity(first.value)
        out, ordering = set(roots), list(roots)
        changed = True
        while changed:
            changed = False
            for entity, p in parent.items():
                if p in out and entity not in out:
                    out.add(entity)
                    ordering.append(entity)
                    changed = True
        return ordering

    # -------------------------------------------------------------- lenses

    def materialize(
        self,
        scope: str | list[str],
        as_of: float | None = None,
        frame: str = CANON,
        lens: str = "current_state",
        budget: int | None = None,
        asserted_as_of: int | None = None,
        since: float | None = None,
    ) -> Materialization:
        """`since` (letter 029): lower bound for the what_happened lens —
        with `as_of` it gives occurred(window=[since, as_of]) matching."""
        if lens not in LENSES:
            raise ValueError(f"unknown lens {lens!r}")
        if lens == "establishing_set":
            # The world at rest: the scope walk itself uses establishing
            # containment, or entities the plot moved away vanish from the
            # very lens meant to show where they started.
            entities = self._establishing_scope(scope, frame, as_of, asserted_as_of)
        else:
            entities = self._scope_entities(scope, frame, as_of, asserted_as_of)
        m = Materialization(
            scope=tuple(entities), frame=frame, as_of=as_of,
            asserted_as_of=asserted_as_of, lens=lens,
        )
        if lens == "what_happened":
            self._lens_events(m, entities, since)
        elif lens == "character_sheet":
            self._lens_sheet(m, entities)
        else:
            self._lens_state(m, entities, establishing=(lens == "establishing_set"))
        self._fill_defaults(m)
        self._shape_to_budget(m, budget)
        return m

    def _lens_state(self, m: Materialization, entities: list[str], establishing: bool) -> None:
        for entity in entities:
            folded = self._indexes.current_state(
                entity, m.frame, m.as_of, m.asserted_as_of
            )
            for attr, result in sorted(folded.items()):
                row = result.winner
                if row is None:
                    continue
                if result.conflicted:
                    m.conflicted_keys.append((entity, attr))
                if row.value_type == "unresolved":
                    m.unresolved.append((entity, attr))
                    continue  # the frontier is named, never painted (§10)
                durability = self._classifier.durability(row.id)
                if establishing and durability == STATE:
                    row = self._establishing_state(entity, attr, m) or None
                    if row is None:
                        continue
                m.assertions.append(row)

    def _establishing_state(
        self, entity: str, attr: str, m: Materialization
    ) -> Assertion | None:
        """First STATE by (valid_from, asserted_at) with no caused_by edge
        to an EVENT — the world at rest (spec §9.1); honors world_defining."""
        from patternbuffer.indexes import fold_attribute

        rows = [
            r
            for r in self._buffer.visible(
                frame=m.frame,
                valid_as_of=m.as_of, asserted_as_of=m.asserted_as_of,
            )
            if self._indexes.resolve_entity(r.entity) == entity
            and fold_attribute(r.attribute) == attr  # attr is already fold-keyed
            and r.value_type != "unresolved"
            and self._classifier.durability(r.id) == STATE
        ]
        qualifying = []
        for r in rows:
            pinned = bool(self._buffer.visible(entity=r.id, attribute="world_defining"))
            if pinned:
                return r
            if not self._indexes._is_event_effect(r, m.asserted_as_of):
                qualifying.append(r)
        if not qualifying:
            return None
        return min(qualifying, key=lambda r: (r.valid_from or float("-inf"), r.asserted_at))

    def _lens_events(self, m: Materialization, entities: list[str],
                     since: float | None = None) -> None:
        in_scope = set(entities)
        events = []
        for row in self._buffer.visible(
            frame=m.frame, valid_as_of=None, asserted_as_of=m.asserted_as_of
        ):
            if self._classifier.durability(row.id) != EVENT:
                continue
            if row.entity.startswith("a:"):
                continue  # meta rows ride with their subjects
            subject = self._indexes.resolve_entity(row.entity)
            object_ = (
                self._indexes.resolve_entity(row.value)
                if row.value_type == "entity" and isinstance(row.value, str)
                else None
            )
            if subject in in_scope or object_ in in_scope or not in_scope:
                if m.as_of is not None and row.valid_from is not None and row.valid_from > m.as_of:
                    continue
                if since is not None and (row.valid_from is None or row.valid_from < since):
                    continue
                events.append(row)
        events.sort(key=lambda r: (r.valid_from if r.valid_from is not None else float("-inf"), r.seq))
        m.assertions.extend(events)

    def _lens_sheet(self, m: Materialization, entities: list[str]) -> None:
        """One entity's accumulated card, frame-respecting."""
        for entity in entities[:1]:
            folded = self._indexes.current_state(entity, m.frame, m.as_of, m.asserted_as_of)
            for attr, result in sorted(folded.items()):
                if result.winner is None:
                    continue
                if result.winner.value_type == "unresolved":
                    m.unresolved.append((entity, attr))
                    continue
                if result.conflicted:
                    m.conflicted_keys.append((entity, attr))
                m.assertions.append(result.winner)

    # --------------------------------------------------- defaults + budget

    def _fill_defaults(self, m: Materialization) -> None:
        """Closed-world render commitments, marked `default` in the payload
        only (open-world store / closed-world projection, §13)."""
        if m.lens == "what_happened":
            return
        present: dict[str, set[str]] = {}
        kinds: dict[str, str] = {}
        for row in m.assertions:
            e = self._indexes.resolve_entity(row.entity)
            present.setdefault(e, set()).add(row.attribute)
            if row.attribute == "kind" and isinstance(row.value, str):
                kinds[e] = row.value
        for entity, kind in kinds.items():
            for attr, value in KIND_DEFAULTS.get(kind, {}).items():
                if attr not in present.get(entity, set()):
                    m.defaults.append(DefaultFill(entity, attr, value))

    def _shape_to_budget(self, m: Materialization, budget: int | None) -> None:
        """The budget invariant: the CONSTITUTIVE spine is exempt; compress
        the rest by salience (recency + reference frequency), never drop
        identity and structure (§13)."""
        if budget is None or len(m.assertions) <= budget:
            return
        spine = [
            r for r in m.assertions if self._classifier.durability(r.id) == CONSTITUTIVE
        ]
        rest = [r for r in m.assertions if r not in spine]
        refs: dict[str, int] = {}
        for row in self._buffer.all_rows():
            if row.value_type == "entity" and isinstance(row.value, str):
                refs[row.value] = refs.get(row.value, 0) + 1
        rest.sort(  # salience: projection-time ranking, never stored (P1)
            key=lambda r: (refs.get(r.entity, 0), r.asserted_at), reverse=True
        )
        keep = max(0, budget - len(spine))
        m.truncated = len(rest) - keep
        m.assertions = spine + rest[:keep]
