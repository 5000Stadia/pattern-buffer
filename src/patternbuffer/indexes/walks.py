"""The walks section of `Indexes`: containment (`locate`, `contents`),
composition (`composition`, `features`), the aggregate over a container, and
the one-hop lateral / incoming reads. Each rides the fold; none stores
anything.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from patternbuffer.codec import check_no_mix, exact_div, exact_sum
from patternbuffer.model import ATTR_PREFIX, CANON

# One logger for the whole package, named as before the split.
logger = logging.getLogger("patternbuffer.indexes")


class WalksMixin:
    """The walks section of `Indexes`."""

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
        for target in sorted(self._closure_of(container)):
            for row in self._buffer.visible(
                attribute_in=sorted(self._semantics.containment_family()), value=target,
                frame=frame, valid_as_of=valid_as_of, asserted_as_of=asserted_as_of,
            ):
                if not row.entity.startswith("a:") and not row.entity.startswith(ATTR_PREFIX):
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

    # ------------------------------- PLACE-FEATURE-ABSTRACTION-V1 (composition)
    # The compositional axis (`part_of`), mirroring locate/contents but for
    # structural part-of-the-whole, NOT movable location. Conflict HALTS the
    # walk — a co-existing-parent fold is never silently resolved to a winner
    # (Cx 064 #1); the conflict surfaces through state()/truth-maintenance.

    def composition(
        self,
        entity: str,
        frame: str = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> list[str]:
        """The `part_of` chain upward, nearest whole first — the entity's
        place-in-the-structure. Mirror of `locate` over the compositional axis;
        single-parent, cycle-guarded. A conflicted `part_of` fold stops the walk
        (never picks among parents)."""
        chain: list[str] = []
        seen = {self._resolve(entity)}
        current = self._resolve(entity)
        while True:
            result = self.fold_key(current, "part_of", frame, valid_as_of, asserted_as_of)
            if (result.winner is None or result.conflicted
                    or result.winner.value_type != "entity"):
                return chain
            parent = self._resolve(result.winner.value)
            if parent in seen:
                logger.warning("composition cycle at %s", parent)
                return chain
            chain.append(parent)
            seen.add(parent)
            current = parent

    def features(
        self,
        place: str,
        frame: str = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> list[str]:
        """The `part_of`-children of `place` — its structural sub-features. A
        child is included iff its folded, non-conflicted current `part_of`
        winner resolves to `place` (Cx 064: not "any visible row with
        value=place" — so valid-time/identity/retraction/conflict all align).
        Ordered first-seen/log order, lexical tie-break."""
        place = self._resolve(place)
        first_seen: dict[str, int] = {}
        for target in sorted(self._closure_of(place)):
            for row in self._buffer.visible(
                attribute="part_of", value=target,
                frame=frame, valid_as_of=valid_as_of, asserted_as_of=asserted_as_of,
            ):
                if row.entity.startswith("a:") or row.entity.startswith(ATTR_PREFIX):
                    continue
                eid = self._resolve(row.entity)
                if eid not in first_seen or row.seq < first_seen[eid]:
                    first_seen[eid] = row.seq
        members: list[str] = []
        for eid in first_seen:
            result = self.fold_key(eid, "part_of", frame, valid_as_of, asserted_as_of)
            if (result.winner is not None and not result.conflicted
                    and result.winner.value_type == "entity"
                    and self._resolve(result.winner.value) == place):
                members.append(eid)
        return sorted(members, key=lambda e: (first_seen[e], e))

    def aggregate(
        self,
        container: str,
        member_attribute: str,
        op: str,
        frame: str = CANON,
        as_of: float | None = None,
        recursive: bool = False,
        asserted_as_of: int | None = None,
    ) -> dict[str, Any]:
        """Bounded numeric rollup over a container's folded member values."""
        if op not in {"sum", "count", "min", "max", "avg"}:
            raise ValueError(f"unknown aggregate operator {op!r}")

        subject = self._resolve(container)

        def members() -> list[str]:
            direct = self.contents(subject, frame, as_of, asserted_as_of)
            if not recursive:
                return direct
            out: list[str] = []
            seen = {subject}
            queue = list(direct)
            while queue:
                member = self._resolve(queue.pop(0))
                if member in seen:
                    continue
                seen.add(member)
                out.append(member)
                queue.extend(self.contents(member, frame, as_of, asserted_as_of))
            return out

        contributing: list[str] = []
        values: list[int | float | Decimal] = []
        if not self._semantics.is_set_valued(member_attribute):
            for member in members():
                folded = self.fold_key(
                    member, member_attribute, frame, as_of, asserted_as_of
                )
                if self._semantics.is_accrue(member_attribute):
                    value = folded.quantity
                elif folded.winner is not None:
                    value = folded.winner.value
                else:
                    value = None
                if self._is_numeric(value):
                    contributing.append(member)
                    values.append(value)

        # Mix validation runs on the contributing set BEFORE any op —
        # a Decimal/float mix is the same authoring smell for min/max/count
        # as for sum/avg (EXACT-DECIMAL-QUANTITIES-V1 §4).
        check_no_mix(values, ids=contributing)
        count = len(values)
        if op == "count":
            value = count
        elif op == "sum":
            value = exact_sum(values, ids=contributing) if values else 0
        elif op == "min":
            value = min(values) if values else None
        elif op == "max":
            value = max(values) if values else None
        else:
            value = (
                exact_div(exact_sum(values, ids=contributing), count)
                if count else None
            )
        return {
            "op": op,
            "value": value,
            "count": count,
            "members": contributing,
            "container": subject,
        }

    def lateral_neighbors(
        self,
        entity: str,
        frame: str = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> list[str]:
        """One indexed hop over the lateral family from an identity closure."""
        entity = self._resolve(entity)
        attrs = sorted(self._semantics.lateral_family())
        out: set[str] = set()
        for eid in sorted(self._closure_of(entity)):
            for row in self._buffer.visible(
                entity=eid,
                attribute_in=attrs,
                value_type="entity",
                frame=frame,
                valid_as_of=valid_as_of,
                asserted_as_of=asserted_as_of,
            ):
                if isinstance(row.value, str):
                    out.add(self._resolve(row.value))
            for row in self._buffer.visible(
                attribute_in=attrs,
                value=eid,
                value_type="entity",
                frame=frame,
                valid_as_of=valid_as_of,
                asserted_as_of=asserted_as_of,
            ):
                if not row.entity.startswith("a:") and not row.entity.startswith(ATTR_PREFIX):
                    out.add(self._resolve(row.entity))
        out.discard(entity)
        return sorted(out)

    def incoming_refs(
        self,
        entity: str,
        frame: str = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> list[str]:
        """Entities with entity-valued rows pointing at the full closure."""
        entity = self._resolve(entity)
        out: set[str] = set()
        for eid in sorted(self._closure_of(entity)):
            for row in self._buffer.visible(
                value=eid,
                value_type="entity",
                frame=frame,
                valid_as_of=valid_as_of,
                asserted_as_of=asserted_as_of,
            ):
                if row.entity.startswith("a:") or row.entity.startswith(ATTR_PREFIX):
                    continue
                out.add(self._resolve(row.entity))
        return sorted(out)
