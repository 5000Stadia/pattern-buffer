"""Derived indexes: the durability-aware fold, the containment tree, the
lateral graph (whitepaper §13/§17; spec §7). Deterministic, no LLM,
rebuildable — these are views over the buffer, never truth.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import (
    CONSTITUTIVE,
    DISPOSITIONAL,
    EVENT,
    STATE,
    Classifier,
)
from patternbuffer.model import CANON, CONTAINMENT_FAMILY, Assertion

logger = logging.getLogger(__name__)

_FAMILY_KEY = "__containment__"


def fold_attribute(attribute: str) -> str:
    """The fold-key attribute: the containment family folds as one key."""
    return _FAMILY_KEY if attribute in CONTAINMENT_FAMILY else attribute


@dataclass(frozen=True, slots=True)
class FoldResult:
    """What the fold serves for one key."""

    winner: Assertion | None
    conflicted: bool = False
    conflicting: tuple[str, ...] = ()  # assertion ids party to the conflict
    corroborated_by: tuple[str, ...] = ()


@dataclass
class _KeyRows:
    rows: list[Assertion] = field(default_factory=list)


class Indexes:
    """Fold + walks. Holds no durable state of its own (P2)."""

    def __init__(
        self,
        buffer: PatternBuffer,
        classifier: Classifier,
        identity_resolve: Callable[[str], str] | None = None,
    ) -> None:
        self._buffer = buffer
        self._classifier = classifier
        # Identity closure hook: maps any entity id to its canonical
        # representative. Installed by World wiring once the registry exists.
        self._resolve = identity_resolve or (lambda eid: eid)

    def set_identity_resolver(self, fn: Callable[[str], str]) -> None:
        self._resolve = fn

    def resolve_entity(self, entity: str) -> str:
        """The identity closure's canonical representative for `entity`."""
        return self._resolve(entity)

    # -------------------------------------------------------------- helpers

    def _source_class(self, row: Assertion, asserted_as_of: int | None) -> str:
        """Provenance status, refined by the document-vs-direct distinction
        (whitepaper §7.1, spec §7). The refinement applies to `stated` as
        well as `observed`: in fiction mode an in-fiction document's claims
        (the story observed the letter; the letter claims the facts) must
        sit in a different trust chain from narration-direct facts."""
        if row.status not in {"observed", "stated"}:
            return row.status
        metas = self._buffer.visible(
            entity=row.id, attribute="source", asserted_as_of=asserted_as_of
        )
        for m in metas:
            if isinstance(m.value, str) and m.value.startswith("doc:"):
                return f"{row.status}:document"
        return f"{row.status}:direct"

    @staticmethod
    def _values_agree(old: object, new: object) -> bool:
        """Equal, or `new` refines an explicitly approximate `old`
        ({'gte': x} / {'lte': x} / {'approx': x}) — spec §7."""
        if old == new:
            return True
        if isinstance(old, dict) and isinstance(new, (int, float)):
            if "gte" in old and new >= old["gte"]:
                return True
            if "lte" in old and new <= old["lte"]:
                return True
            if "approx" in old and abs(new - old["approx"]) <= 0.1 * abs(old["approx"]):
                return True
        return False

    def _is_event_effect(self, row: Assertion, asserted_as_of: int | None) -> bool:
        """True iff the row carries a caused_by edge to an EVENT (spec §9.1)."""
        return bool(
            self._buffer.visible(
                entity=row.id, attribute="caused_by", asserted_as_of=asserted_as_of
            )
        )

    # ----------------------------------------------------------------- fold

    def fold_key(
        self,
        entity: str,
        attribute: str,
        frame: str = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> FoldResult:
        """Serve one (entity, attribute, frame) key per the per-class rules."""
        entity = self._resolve(entity)
        fa = fold_attribute(attribute)
        candidates: list[Assertion] = []
        for row in self._buffer.visible(
            frame=frame, valid_as_of=valid_as_of, asserted_as_of=asserted_as_of
        ):
            if self._resolve(row.entity) != entity:
                continue
            if fold_attribute(row.attribute) != fa:
                continue
            if self._classifier.durability(row.id) == EVENT:
                continue  # events never fold
            candidates.append(row)
        if not candidates:
            return FoldResult(winner=None)

        # Resolution IS the supersession (whitepaper §8 — forcing memoizes
        # into the log; the fold serves the memo): a spent thunk (one with a
        # resolved_by marker) never competes, and once concrete rows exist
        # on a key, its unresolved placeholder no longer competes either.
        candidates = [
            r
            for r in candidates
            if r.value_type != "unresolved"
            or not self._buffer.visible(
                entity=r.id, attribute="resolved_by", asserted_as_of=asserted_as_of
            )
        ]
        if any(r.value_type != "unresolved" for r in candidates):
            candidates = [r for r in candidates if r.value_type != "unresolved"]
        if not candidates:
            return FoldResult(winner=None)

        by_class = {STATE: [], DISPOSITIONAL: [], CONSTITUTIVE: []}
        for row in candidates:
            by_class.setdefault(self._classifier.durability(row.id), []).append(row)

        # CONSTITUTIVE outranks: structure is never superseded by recency.
        if by_class[CONSTITUTIVE]:
            rows = by_class[CONSTITUTIVE]
            values = {repr(r.value) for r in rows}
            earliest = min(rows, key=lambda r: r.asserted_at)
            if len(values) > 1:
                return FoldResult(
                    winner=earliest,
                    conflicted=True,
                    conflicting=tuple(r.id for r in rows),
                )
            return FoldResult(winner=earliest)

        if by_class[STATE]:
            return self._fold_state(by_class[STATE], asserted_as_of)

        if by_class[DISPOSITIONAL]:
            rows = by_class[DISPOSITIONAL]
            winner = max(rows, key=lambda r: (r.valid_from or float("-inf"), r.asserted_at))
            return FoldResult(winner=winner)
        return FoldResult(winner=None)

    def _fold_state(
        self, rows: list[Assertion], asserted_as_of: int | None
    ) -> FoldResult:
        """STATE: recency wins within a source class; across classes,
        agreement corroborates (serve the more precise value), disagreement
        flags and keeps serving the prior in-class winner (spec §7)."""
        by_source: dict[str, list[Assertion]] = {}
        for r in rows:
            by_source.setdefault(self._source_class(r, asserted_as_of), []).append(r)
        winners = {
            sc: max(rs, key=lambda r: (r.valid_from or float("-inf"), r.asserted_at))
            for sc, rs in by_source.items()
        }
        if len(winners) == 1:
            return FoldResult(winner=next(iter(winners.values())))

        # Multiple source classes on one key: order in-class winners by
        # arrival; the earliest-arrived class is the incumbent.
        ordered = sorted(winners.values(), key=lambda r: r.asserted_at)
        incumbent, rest = ordered[0], ordered[1:]
        serving = incumbent
        corroborations: list[str] = []
        conflicts: list[str] = []
        for challenger in rest:
            if self._values_agree(serving.value, challenger.value):
                corroborations.append(challenger.id)
                serving = challenger  # the refinement is the more precise value
            else:
                conflicts.append(challenger.id)
        if conflicts:
            return FoldResult(
                winner=serving if not corroborations else serving,
                conflicted=True,
                conflicting=tuple([incumbent.id, *conflicts]),
                corroborated_by=tuple(corroborations),
            )
        return FoldResult(winner=serving, corroborated_by=tuple(corroborations))

    def current_state(
        self,
        entity: str,
        frame: str = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> dict[str, FoldResult]:
        """All folded keys for one entity (attribute -> result)."""
        entity = self._resolve(entity)
        attrs: set[str] = set()
        for row in self._buffer.visible(
            frame=frame, valid_as_of=valid_as_of, asserted_as_of=asserted_as_of
        ):
            if self._resolve(row.entity) == entity and not row.entity.startswith("a:"):
                attrs.add(row.attribute)
        out: dict[str, FoldResult] = {}
        for attr in attrs:
            result = self.fold_key(entity, attr, frame, valid_as_of, asserted_as_of)
            if result.winner is not None:
                out[fold_attribute(attr) if attr in CONTAINMENT_FAMILY else attr] = result
        return out

    # ---------------------------------------------------------------- walks

    def locate(
        self,
        entity: str,
        frame: str = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> list[str]:
        """Walk the containment family up to a root. Returns the chain,
        nearest container first. Single-parent: the family fold yields at
        most one edge per entity."""
        chain: list[str] = []
        seen = {self._resolve(entity)}
        current = self._resolve(entity)
        while True:
            result = self.fold_key(current, "in", frame, valid_as_of, asserted_as_of)
            if result.winner is None or result.winner.value_type != "entity":
                return chain
            parent = self._resolve(result.winner.value)
            if parent in seen:
                logger.warning("containment cycle at %s", parent)
                return chain
            chain.append(parent)
            seen.add(parent)
            current = parent

    def contents(
        self,
        container: str,
        frame: str = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> list[str]:
        """Entities whose folded containment edge lands on `container`.
        Emptiness is this query returning [] — stored nowhere (P2)."""
        container = self._resolve(container)
        members: set[str] = set()
        candidates: set[str] = set()
        for row in self._buffer.visible(
            frame=frame, valid_as_of=valid_as_of, asserted_as_of=asserted_as_of
        ):
            if row.attribute in CONTAINMENT_FAMILY and not row.entity.startswith("a:"):
                candidates.add(self._resolve(row.entity))
        for eid in candidates:
            result = self.fold_key(eid, "in", frame, valid_as_of, asserted_as_of)
            if (
                result.winner is not None
                and result.winner.value_type == "entity"
                and self._resolve(result.winner.value) == container
            ):
                members.add(eid)
        return sorted(members)

    def path(
        self,
        a: str,
        b: str,
        frame: str = CANON,
        asserted_as_of: int | None = None,
    ) -> list[str] | None:
        """BFS over the lateral graph (connects_to/adjacent_to, undirected).
        None = no path: vertical proximity is not connectivity."""
        a, b = self._resolve(a), self._resolve(b)
        edges: dict[str, set[str]] = {}
        for row in self._buffer.visible(asserted_as_of=asserted_as_of, frame=frame):
            if row.attribute in {"connects_to", "adjacent_to"} and row.value_type == "entity":
                x, y = self._resolve(row.entity), self._resolve(row.value)
                edges.setdefault(x, set()).add(y)
                edges.setdefault(y, set()).add(x)
        if a == b:
            return [a]
        frontier = [[a]]
        visited = {a}
        while frontier:
            path_so_far = frontier.pop(0)
            for nxt in sorted(edges.get(path_so_far[-1], ())):
                if nxt in visited:
                    continue
                if nxt == b:
                    return path_so_far + [nxt]
                visited.add(nxt)
                frontier.append(path_so_far + [nxt])
        return None
