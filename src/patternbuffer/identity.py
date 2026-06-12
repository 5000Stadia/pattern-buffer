"""The identity registry (whitepaper §11): anchors, aliases,
SAME_AS / MAYBE_SAME_AS, merges as logged events.

The registry is derived: edges are ordinary assertions; the closure is
computed (union-find over visible same_as edges). A merge appends — late
binding leaves every earlier row intact and reachable through the merged
identity. A bad merge is repaired forward by retracting the edge.
"""

from __future__ import annotations

import logging

from patternbuffer.buffer import PatternBuffer
from patternbuffer.model import CANON
from patternbuffer.roles import WriterRole

logger = logging.getLogger(__name__)


class IdentityRegistry:
    def __init__(self, buffer: PatternBuffer, ingestor: WriterRole) -> None:
        self._buffer = buffer
        self._ingestor = ingestor

    # --------------------------------------------------------------- write

    def add_alias(self, entity: str, alias: str, status: str = "stated") -> None:
        self._buffer.append(
            entity=entity, attribute="alias", value=alias.strip().lower(),
            status=status, role=self._ingestor,
        )

    def merge(self, a: str, b: str, evidence: str) -> str:
        """Identity merge, logged as an event (auditable, reversible by
        retraction). Returns the merge event's entity id."""
        event_id = f"event:merge_{self._buffer.head() + 1}"
        self._buffer.append(
            entity=event_id, attribute="kind", value="identity_merge",
            status="inferred", role=self._ingestor,
        )
        edge = self._buffer.append(
            entity=a, attribute="same_as", value=b, value_type="entity",
            status="inferred", role=self._ingestor,
        )
        self._buffer.append(
            entity=edge.id, attribute="caused_by", value=event_id, value_type="entity",
            status="inferred", role=self._ingestor,
        )
        self._buffer.append(
            entity=event_id, attribute="evidence", value=evidence,
            status="inferred", role=self._ingestor,
        )
        logger.info("merge %s == %s (%s)", a, b, evidence)
        return event_id

    def maybe_same_as(self, a: str, b: str, evidence: str) -> None:
        """Ambiguity is represented, not forced: the edge survives until
        a force collapses it (split/underdetermined anchors, §11)."""
        edge = self._buffer.append(
            entity=a, attribute="maybe_same_as", value=b, value_type="entity",
            status="assumed", role=self._ingestor,
        )
        self._buffer.append(
            entity=edge.id, attribute="evidence", value=evidence,
            status="assumed", role=self._ingestor,
        )

    # ---------------------------------------------------------------- read

    def resolve(self, entity: str, asserted_as_of: int | None = None) -> str:
        """Canonical representative: the first-seen member of the entity's
        same_as closure (stable across instances — first-seen is log order)."""
        closure = self.closure(entity, asserted_as_of)
        if len(closure) == 1:
            return entity
        first_seen: dict[str, int] = {}
        for row in self._buffer.visible(asserted_as_of=asserted_as_of):
            if row.entity in closure and row.entity not in first_seen:
                first_seen[row.entity] = row.seq
            if (
                row.value_type == "entity"
                and isinstance(row.value, str)
                and row.value in closure
                and row.value not in first_seen
            ):
                first_seen[row.value] = row.seq
        return min(closure, key=lambda e: (first_seen.get(e, 1 << 62), e))

    def closure(self, entity: str, asserted_as_of: int | None = None) -> set[str]:
        edges: dict[str, set[str]] = {}
        for row in self._buffer.visible(attribute="same_as", asserted_as_of=asserted_as_of):
            if row.value_type == "entity":
                edges.setdefault(row.entity, set()).add(row.value)
                edges.setdefault(row.value, set()).add(row.entity)
        out = {entity}
        frontier = [entity]
        while frontier:
            for nxt in edges.get(frontier.pop(), ()):
                if nxt not in out:
                    out.add(nxt)
                    frontier.append(nxt)
        return out

    def candidates(self, entity: str) -> set[str]:
        """Open maybe_same_as edges touching this entity's closure."""
        closure = self.closure(entity)
        out = set()
        for row in self._buffer.visible(attribute="maybe_same_as"):
            if row.entity in closure:
                out.add(row.value)
            elif row.value in closure:
                out.add(row.entity)
        return out

    def name_anchors(self, entity: str) -> set[str]:
        """NAME-class anchors only (names + aliases, lowercased) — the
        high-weight identity signal. Role/title tokens deliberately
        excluded (036: a shared title register must never carry a merge)."""
        closure = self.closure(entity)
        out: set[str] = set()
        for row in self._buffer.visible():
            if row.entity in closure and row.attribute in ("name", "alias") \
                    and isinstance(row.value, str):
                out.add(row.value.strip().lower())
        return out

    def promote_identity_proposals(self) -> int:
        """Whole-world promotion pass (036): a maybe_same_as proposal
        whose two sides share a NAME-class anchor promotes to a logged
        merge event; title-only candidates stay proposals (for tier-2 or
        explicit confirmation). Returns merges performed."""
        promoted = 0
        for row in list(self._buffer.visible(attribute="maybe_same_as")):
            a, b = row.entity, row.value
            if not isinstance(b, str):
                continue
            if self.resolve(a) == self.resolve(b):
                continue  # already merged
            shared = self.name_anchors(a) & self.name_anchors(b)
            if shared:
                ev = self._buffer.visible(entity=row.id, attribute="evidence")
                self.merge(a, b, evidence=(
                    f"promoted from {row.id}: shared name anchor(s) "
                    f"{sorted(shared)[:3]}"
                    + (f"; proposal evidence: {ev[0].value}" if ev else "")))
                promoted += 1
        if promoted:
            logger.info("identity promotion: %d merge(s)", promoted)
        return promoted

    def by_alias(self, alias: str, asserted_as_of: int | None = None) -> set[str]:
        needle = alias.strip().lower()
        hits = set()
        for row in self._buffer.visible(attribute="alias", asserted_as_of=asserted_as_of):
            if row.value == needle:
                hits.add(self.resolve(row.entity, asserted_as_of))
        # Names assert identity too: check 'name' rows.
        for row in self._buffer.visible(attribute="name", asserted_as_of=asserted_as_of):
            if isinstance(row.value, str) and row.value.strip().lower() == needle:
                hits.add(self.resolve(row.entity, asserted_as_of))
        return hits
