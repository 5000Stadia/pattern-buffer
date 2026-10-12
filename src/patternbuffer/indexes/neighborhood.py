"""The neighborhood section of `Indexes`: the awareness read — what is
around an entity, by edge family, depth-capped and salience-ordered.
"""

from __future__ import annotations

from typing import Any

from patternbuffer.classify import CONSTITUTIVE
from patternbuffer.codec import encode_out, encode_value
from patternbuffer.model import CANON, Assertion

_NEIGHBORHOOD_EDGES = frozenset({"containment", "lateral", "relations", "events"})
_NEIGHBORHOOD_DEPTH_CAP = 3


class NeighborhoodMixin:
    """The neighborhood section of `Indexes`."""

    # --------------------------------------------------------- neighborhood

    def _fact_payload(self, row: Assertion) -> dict[str, Any]:
        durability = self._classifier.durability(row.id)
        out = {
            "entity": self._resolve(row.entity),
            "attribute": row.attribute,
            "value": encode_out(row.value),   # recursive: nested Decimal leaves too
            "value_type": row.value_type,
            "valid": [row.valid_from, row.valid_to],
            "provenance": {
                "status": row.status,
                "assertion_id": row.id,
                "durability": durability,
            },
        }
        if row.value_type == "unresolved":
            out["status"] = "unresolved"
            if isinstance(row.value, dict):
                out["policy"] = row.value.get("policy")
        return out

    def _state_payload(
        self,
        entity: str,
        frame: str,
        valid_as_of: float | None,
        asserted_as_of: int | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        facts: list[dict[str, Any]] = []
        quantities: list[dict[str, Any]] = []
        for attr, result in sorted(
            self.current_state(entity, frame, valid_as_of, asserted_as_of).items()
        ):
            if result.quantity is not None and result.winner is not None:
                quantities.append(
                    {
                        "entity": self._resolve(entity),
                        "attribute": attr,
                        "value": encode_value(result.quantity),
                        "provenance": {
                            "status": result.winner.status,
                            "assertion_id": result.winner.id,
                            "durability": self._classifier.durability(result.winner.id),
                        },
                    }
                )
                continue
            for row in result._value_rows or (
                (result.winner,) if result.winner is not None else ()
            ):
                facts.append(self._fact_payload(row))
        return facts, quantities

    def _entity_relation_neighbors(
        self,
        entity: str,
        frame: str,
        valid_as_of: float | None,
        asserted_as_of: int | None,
    ) -> list[str]:
        out: set[str] = set()
        skip = self._semantics.containment_family() | self._semantics.lateral_family()
        for attr, result in self.current_state(
            entity, frame, valid_as_of, asserted_as_of
        ).items():
            # The family's key is `in` (FOLD-CORRECTNESS-V1 §7), so it is caught
            # here; the old `__containment__` key slipped past this skip and
            # served the containment parent as a "relations" neighbor.
            if attr in skip:
                continue
            for row in result._value_rows or (
                (result.winner,) if result.winner is not None else ()
            ):
                if row.value_type == "entity" and isinstance(row.value, str):
                    out.add(self._resolve(row.value))
        out.discard(self._resolve(entity))
        return sorted(out)

    def _containment_edge_protected(
        self,
        child: str,
        parent: str,
        frame: str,
        valid_as_of: float | None,
        asserted_as_of: int | None,
    ) -> bool:
        result = self.fold_key(child, "in", frame, valid_as_of, asserted_as_of)
        return (
            result.winner is not None
            and result.winner.value_type == "entity"
            and self._resolve(result.winner.value) == self._resolve(parent)
            and self._classifier.durability(result.winner.id) == CONSTITUTIVE
        )

    def neighborhood(
        self,
        entity: str,
        depth: int = 1,
        frame: str = CANON,
        as_of: float | None = None,
        edge_kinds: list[str] | set[str] | tuple[str, ...] | None = None,
        max_fanout: int = 64,
        budget: int | None = None,
        asserted_as_of: int | None = None,
    ) -> dict[str, Any]:
        """Bounded structural neighborhood around one identity-closed entity."""
        subject = self._resolve(entity)
        allowed = set(_NEIGHBORHOOD_EDGES if edge_kinds is None else edge_kinds)
        unknown = allowed - _NEIGHBORHOOD_EDGES
        if unknown:
            raise ValueError(f"unknown neighborhood edge kind(s): {sorted(unknown)}")
        depth = max(0, min(int(depth), _NEIGHBORHOOD_DEPTH_CAP))
        max_fanout = max(0, int(max_fanout))
        subject_facts, subject_quantities = self._state_payload(
            subject, frame, as_of, asserted_as_of
        )
        out: dict[str, Any] = {
            "subject": {
                "entity": subject,
                "facts": subject_facts,
                "quantities": subject_quantities,
                "location": self.locate(subject, frame, as_of, asserted_as_of),
                "contents": self.contents(subject, frame, as_of, asserted_as_of),
            },
            "neighbors": [],
            "truncated": 0,
        }

        def score(eid: str) -> float:
            return float(self._salience(eid, frame, as_of))

        neighbors: dict[str, dict[str, Any]] = {}
        queue: list[tuple[str, int]] = [(subject, 0)]
        seen = {subject}
        expanded: set[str] = set()
        while queue:
            current, hop = queue.pop(0)
            if current in expanded or hop >= depth:
                continue
            expanded.add(current)
            candidates: dict[str, dict[str, Any]] = {}

            def add_candidate(eid: str, via: str, protected: bool = False) -> None:
                resolved = self._resolve(eid)
                if resolved == subject:
                    return
                existing = candidates.get(resolved)
                if existing is None:
                    candidates[resolved] = {
                        "entity": resolved,
                        "via": via,
                        "protected": protected,
                    }
                else:
                    existing["protected"] = existing["protected"] or protected

            if "containment" in allowed:
                chain = self.locate(current, frame, as_of, asserted_as_of)
                if chain:
                    parent = chain[0]
                    add_candidate(
                        parent,
                        "containment",
                        self._containment_edge_protected(
                            current, parent, frame, as_of, asserted_as_of
                        ),
                    )
                for child in self.contents(current, frame, as_of, asserted_as_of):
                    add_candidate(
                        child,
                        "containment",
                        self._containment_edge_protected(
                            child, current, frame, as_of, asserted_as_of
                        ),
                    )
            if "lateral" in allowed:
                for neighbor in self.lateral_neighbors(current, frame, as_of, asserted_as_of):
                    add_candidate(neighbor, "lateral")
            if "relations" in allowed:
                for neighbor in self._entity_relation_neighbors(
                    current, frame, as_of, asserted_as_of
                ):
                    add_candidate(neighbor, "relations")
            if "events" in allowed:
                events = self.event_participation(current, frame, as_of, asserted_as_of)
                for event_id in events:
                    add_candidate(event_id, "events")
                causal_sources = set(events)
                if current.startswith("event:"):
                    causal_sources.add(current)
                for cause in self.caused_by_of(
                    causal_sources, frame, as_of, asserted_as_of
                ):
                    add_candidate(cause, "events")

            ranked = sorted(
                candidates.values(),
                key=lambda c: (score(c["entity"]), c["entity"]),
                reverse=True,
            )
            if len(ranked) > max_fanout:
                out["truncated"] += len(ranked) - max_fanout
                ranked = ranked[:max_fanout]
            for candidate in ranked:
                eid = candidate["entity"]
                if eid not in neighbors:
                    facts, quantities = self._state_payload(eid, frame, as_of, asserted_as_of)
                    neighbors[eid] = {
                        "entity": eid,
                        "via": candidate["via"],
                        "hop": hop + 1,
                        "salience": score(eid),
                        "facts": facts,
                        "quantities": quantities,
                        "_protected": bool(candidate["protected"]),
                    }
                elif candidate["protected"]:
                    neighbors[eid]["_protected"] = True
                if eid not in seen:
                    seen.add(eid)
                    queue.append((eid, hop + 1))

        shaped = sorted(
            neighbors.values(),
            key=lambda n: (n["salience"], -n["hop"], n["entity"]),
            reverse=True,
        )
        if budget is not None and len(shaped) > budget:
            protected = [n for n in shaped if n["_protected"]]
            rest = [n for n in shaped if not n["_protected"]]
            keep = max(0, int(budget) - len(protected))
            out["truncated"] += max(0, len(rest) - keep)
            shaped = sorted(
                protected + rest[:keep],
                key=lambda n: (n["salience"], -n["hop"], n["entity"]),
                reverse=True,
            )
        for neighbor in shaped:
            neighbor.pop("_protected", None)
        out["neighbors"] = shaped
        return out
