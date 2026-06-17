"""The porcelain: the frozen host surface (PORCELAIN-V1, porcelain-v0.1).

Typed, JSON-serializable verbs over shipped plumbing. Freeze semantics:
additive-only from the v0.1 tag — parameters gain defaults, verbs may be
added; nothing is renamed, removed, or re-typed.

No top-level import of this module from __init__ (lazy property there)
— porcelain imports World types only under TYPE_CHECKING to avoid
circularity.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from patternbuffer.model import ATTR_PREFIX, CANON, META_ATTRIBUTES
from patternbuffer.thunks import UNKNOWN, ResolutionDenied

if TYPE_CHECKING:  # pragma: no cover
    from patternbuffer import World

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-z][a-z0-9_]*:[a-z0-9_:]+$")


# ---------------------------------------------------------------- payloads


@dataclass
class Receipt:
    world_id: str
    seq_range: list[int] | None
    rows: list[dict] = field(default_factory=list)
    frames: list[str] = field(default_factory=list)
    canonicalization_receipts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Fact:
    entity: str
    attribute: str
    value: Any
    valid: list
    provenance: dict
    divergent: bool = False
    b_value: Any = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Answer:
    answered: bool
    facts: list[dict] = field(default_factory=list)
    prose: str | None = None
    unknown_reason: str | None = None
    asks: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


_ASK_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "refer_targets": {"type": "array", "items": {"type": "string"}},
        "keys": {"type": "array", "items": {
            "type": "object",
            "properties": {"target_index": {"type": "integer"},
                           "attribute": {"type": "string"}},
            "required": ["target_index", "attribute"]}},
        "wants_location": {"type": "boolean"},
        "wants_events": {"type": "boolean"},
        "as_of": {"type": ["number", "null"]},
    },
    "required": ["refer_targets", "keys"],
}


class Porcelain:
    """The five+1 verbs. Construct via ``World.porcelain``."""

    def __init__(self, world: "World") -> None:
        self._w = world

    # ------------------------------------------------------------- helpers

    def _receipt(self, rows) -> Receipt:
        rows = [r for r in rows if r is not None]
        return Receipt(
            world_id=self._w.world_id,
            seq_range=[min(r.seq for r in rows), max(r.seq for r in rows)] if rows else None,
            rows=[{"assertion_id": r.id, "entity": r.entity,
                   "attribute": r.attribute, "frame": r.frame} for r in rows],
            frames=sorted({r.frame for r in rows}),
            canonicalization_receipts=[
                r.value for r in rows if r.attribute == "canonicalized_from"],
        )

    def _fact(self, row, divergent=False, b_value=None) -> Fact:
        chain = [m.value for m in self._w.buffer.visible(entity=row.id, attribute="source")]
        return Fact(
            entity=row.entity, attribute=row.attribute, value=row.value,
            valid=[row.valid_from, row.valid_to],
            provenance={"status": row.status, "source_chain": chain,
                        "assertion_id": row.id},
            divergent=divergent, b_value=b_value,
        )

    def _quantity_fact(
        self,
        row,
        quantity: int | float,
        *,
        entity: str | None = None,
        attribute: str | None = None,
        divergent: bool = False,
        b_value: Any = None,
    ) -> Fact:
        chain = [m.value for m in self._w.buffer.visible(entity=row.id, attribute="source")]
        return Fact(
            entity=entity or row.entity, attribute=attribute or row.attribute,
            value=quantity, valid=[row.valid_from, row.valid_to],
            provenance={"status": row.status, "source_chain": chain,
                        "assertion_id": row.id},
            divergent=divergent, b_value=b_value,
        )

    @staticmethod
    def _is_numeric(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    # -------------------------------------------------------------- writes

    def ingest(self, text: str, source: str | None = None, scene: str | None = None,
               at: float | None = None, frame: str | None = None) -> Receipt:
        if at is not None:
            self._w.ingestor.cursor.advance(at)
        context = f"\nSCENE HINT (context only, never a spatial anchor): {scene}" if scene else ""
        rows = self._w.ingest(text, context=context, frame=frame)
        if source is not None:
            fact_rows = [
                r for r in rows
                if not r.entity.startswith("a:")
                and not r.entity.startswith(ATTR_PREFIX)
                and r.attribute not in META_ATTRIBUTES
            ]
            rows += self._w.ingest_structured([
                {"entity": r.id, "attribute": "source", "value": source,
                 "status": r.status if r.status in ("stated", "observed") else "stated",
                 "timeless": True}
                for r in fact_rows
            ])
        return self._receipt(rows)

    def ingest_structured(self, items: list[dict], frame: str | None = None) -> Receipt:
        return self._receipt(self._w.ingest_structured(items, frame=frame))

    def resolve(self, entity: str, aspect: str, frame: str = CANON) -> dict:
        try:
            out = self._w.resolve(entity, aspect, frame)
        except ResolutionDenied as exc:
            return {"status": "denied", "facts": [],
                    "receipt": self._receipt([]).to_dict(), "reason": str(exc)}
        if out is UNKNOWN:
            return {"status": "unknown", "facts": [],
                    "receipt": self._receipt([]).to_dict()}
        rows = [r for r in out if r is not None]
        return {"status": "resolved",
                "facts": [self._fact(r).to_dict() for r in rows],
                "receipt": self._receipt(rows).to_dict()}

    def retract(self, assertion_id: str, reason: str) -> Receipt:
        return self._receipt([self._w.truth.retract(assertion_id, reason)])

    # --------------------------------------------------- reads (LLM-free)

    def snapshot(self, scope, frame: str = CANON, as_of: float | None = None,
                 lens: str = "current_state", budget: int | None = None,
                 since: float | None = None) -> dict:
        roots = [scope] if isinstance(scope, str) else list(scope)
        known = {
            self._w.registry.resolve(r.entity)
            for r in self._w.buffer.visible()
            if not r.entity.startswith("a:")
            and not r.entity.startswith(ATTR_PREFIX)
        }
        bad = [s for s in roots
               if not _ID_RE.fullmatch(s) or self._w.registry.resolve(s) not in known]
        if bad:
            return {"error": "snapshot scope must be KNOWN entity ids "
                             "(use ask for references)", "bad": bad}
        m = self._w.materialize(roots, as_of=as_of, frame=frame, lens=lens,
                                budget=budget, since=since)
        return {
            "world_id": self._w.world_id,
            "charter": self._w.charter(),
            "frame": m.frame, "lens": m.lens, "as_of": m.as_of,
            "facts": [self._fact(r).to_dict() for r in m.assertions],
            "quantities": [
                {"entity": e, "attribute": a, "value": v}
                for e, a, v in m.quantities
            ],
            "unresolved": [list(u) for u in m.unresolved],
            "conflicted": [list(c) for c in m.conflicted_keys],
            "defaults": [asdict(d) for d in m.defaults],
            "truncated": m.truncated,
        }

    def state(self, entity: str, attribute: str, frame: str = CANON,
              as_of: float | None = None) -> dict:
        fold = self._w.state(entity, attribute, frame, valid_as_of=as_of)
        if fold.winner is None:
            return {"status": "unknown"}
        # Accrue: the host-facing value is the derived total, not the last
        # delta row — keep `fact.value` consistent with ask()/snapshot().
        fact = (self._quantity_fact(fold.winner, fold.quantity)
                if fold.quantity is not None else self._fact(fold.winner))
        out = {"status": "conflicted" if fold.conflicted else "known",
               "fact": fact.to_dict()}
        if fold.quantity is not None:
            out["quantity"] = fold.quantity
        if fold.conflicted:
            out["conflicting"] = list(fold.conflicting)
        return out

    def where(self, attribute: str, op: str, value, frame: str = CANON,
              as_of: float | None = None) -> list[str]:
        comparators = {
            ">=": lambda a, b: a >= b,
            ">": lambda a, b: a > b,
            "<=": lambda a, b: a <= b,
            "<": lambda a, b: a < b,
            "==": lambda a, b: a == b,
        }
        if op not in comparators:
            raise ValueError(f"unknown comparison operator {op!r}")
        if not self._is_numeric(value):
            return []
        candidates = {
            self._w.registry.resolve(r.entity)
            for r in self._w.buffer.visible(
                attribute=attribute, frame=frame, valid_as_of=as_of
            )
            if not r.entity.startswith("a:")
            and not r.entity.startswith(ATTR_PREFIX)
        }
        out: list[str] = []
        for entity in sorted(candidates):
            fold = self._w.state(entity, attribute, frame, valid_as_of=as_of)
            if fold.quantity is not None:
                target = fold.quantity
            elif fold.winner is not None:
                target = fold.winner.value
            else:
                continue
            if self._is_numeric(target) and comparators[op](target, value):
                out.append(entity)
        return out

    def aggregate(
        self,
        container: str,
        member_attribute: str,
        op: str,
        frame: str = CANON,
        as_of: float | None = None,
        recursive: bool = False,
    ) -> dict:
        return self._w.aggregate(
            container, member_attribute, op,
            frame=frame, as_of=as_of, recursive=recursive,
        )

    def locate(self, entity: str, as_of: float | None = None) -> list[str]:
        return self._w.locate(entity, valid_as_of=as_of)

    def contents(self, container: str, as_of: float | None = None) -> list[str]:
        return self._w.contents(container, valid_as_of=as_of)

    def path(self, a: str, b: str) -> list[str] | None:
        return self._w.path(a, b)

    def salience(
        self, entity: str, frame: str = CANON, as_of: float | None = None
    ) -> float:
        return self._w.salience(entity, frame=frame, as_of=as_of)

    def neighborhood(
        self,
        entity: str,
        depth: int = 1,
        frame: str = CANON,
        as_of: float | None = None,
        edge_kinds: list[str] | None = None,
        max_fanout: int = 64,
        budget: int | None = None,
    ) -> dict:
        return self._w.neighborhood(
            entity,
            depth=depth,
            frame=frame,
            as_of=as_of,
            edge_kinds=edge_kinds,
            max_fanout=max_fanout,
            budget=budget,
        )

    def events(self, kind: str | None = None,
               participants: str | list[str] | None = None,
               since: float | None = None, until: float | None = None,
               frame: str = CANON) -> list[dict]:
        scope = sorted({
            self._w.registry.resolve(r.entity)
            for r in self._w.buffer.visible(frame=frame, entity_prefix="event:")})
        m = self._w.materialize(scope or ["event:none"], frame=frame,
                                lens="what_happened", since=since, as_of=until)
        by_event: dict[str, dict] = {}
        for r in m.assertions:
            ev = by_event.setdefault(r.entity, {"id": r.entity, "kind": None,
                                                "agents": [], "patients": [],
                                                "t": r.valid_from, "caused_by": []})
            if r.attribute == "kind":
                ev["kind"] = r.value
            elif r.attribute == "agent":
                ev["agents"].append(r.value)
            elif r.attribute == "patient":
                ev["patients"].append(r.value)
            elif r.attribute == "caused_by":
                ev["caused_by"].append(r.value)
            if r.valid_from is not None:
                ev["t"] = r.valid_from
        out = list(by_event.values())
        if kind is not None:
            out = [e for e in out if e["kind"] == kind]
        if participants:
            wanted = {participants} if isinstance(participants, str) else set(participants)
            wanted = {self._w.registry.resolve(p) for p in wanted}
            out = [e for e in out
                   if wanted <= {self._w.registry.resolve(x)
                                 for x in e["agents"] + e["patients"]}]
        return sorted(out, key=lambda e: (e["t"] if e["t"] is not None else float("-inf")))

    def frame_diff(self, a: str, b: str | list[str], scope,
                   as_of: float | None = None) -> list[dict]:
        """Semantic fact diff: keys folded in `a`, absent or divergent in
        `b`. Never compares assertion ids (frames are sparse copies)."""
        if isinstance(b, str):
            roots = [scope] if isinstance(scope, str) else list(scope)
            m_a = self._w.materialize(roots, frame=a, as_of=as_of)
            out: list[dict] = []
            for entity, attribute, quantity in m_a.quantities:
                fold_a = self._w.state(entity, attribute, frame=a, valid_as_of=as_of)
                if fold_a.winner is None:
                    continue
                fold_b = self._w.state(entity, attribute, frame=b, valid_as_of=as_of)
                if fold_b.quantity is None:
                    out.append(
                        self._quantity_fact(
                            fold_a.winner, quantity, entity=entity, attribute=attribute
                        ).to_dict()
                    )
                elif fold_b.quantity != quantity:
                    out.append(
                        self._quantity_fact(
                            fold_a.winner, quantity, entity=entity, attribute=attribute,
                            divergent=True, b_value=fold_b.quantity,
                        ).to_dict()
                    )
            for row in m_a.assertions:
                if row.status == "default" or row.value_type == "unresolved":
                    continue
                if self._w.semantics.is_accrue(row.attribute):
                    continue
                entity = self._w.registry.resolve(row.entity)
                fold_b = self._w.state(entity, row.attribute, frame=b, valid_as_of=as_of)

                def _norm(value, value_type):
                    if value_type == "entity" and isinstance(value, str):
                        return ("entity", self._w.registry.resolve(value))
                    return (value_type, value)

                if self._w.semantics.is_set_valued(row.attribute):
                    # Set membership, not a single-winner comparison: an A-frame
                    # member is a diff only when absent from B's whole set
                    # (multi-value fold; otherwise every member but B's winner
                    # reads as falsely divergent).
                    b_members = {
                        _norm(br.value, br.value_type)
                        for br in (fold_b._value_rows
                                   or ((fold_b.winner,) if fold_b.winner else ()))
                    }
                    if _norm(row.value, row.value_type) not in b_members:
                        out.append(self._fact(row).to_dict())  # present in A, absent from B
                    continue

                if fold_b.winner is None:
                    out.append(self._fact(row).to_dict())
                    continue
                va, vb = row.value, fold_b.winner.value
                if row.value_type == "entity" and fold_b.winner.value_type == "entity":
                    equivalent = self._w.registry.resolve(va) == self._w.registry.resolve(vb)
                else:
                    equivalent = va == vb
                if not equivalent:
                    out.append(self._fact(row, divergent=True, b_value=vb).to_dict())
            return out

        b_frames = list(b)
        roots = [scope] if isinstance(scope, str) else list(scope)
        m_a = self._w.materialize(roots, frame=a, as_of=as_of)
        out: list[dict] = []

        def _norm(value, value_type):
            if value_type == "entity" and isinstance(value, str):
                return ("entity", self._w.registry.resolve(value))
            return (value_type, value)

        def _equivalent(row, other) -> bool:
            if row.value_type == "entity" and other.value_type == "entity":
                return self._w.registry.resolve(row.value) == self._w.registry.resolve(other.value)
            return row.value == other.value

        def _recency(row) -> tuple[float, int]:
            return (row.valid_from if row.valid_from is not None else float("-inf"),
                    row.asserted_at)

        for entity, attribute, quantity in m_a.quantities:
            fold_a = self._w.state(entity, attribute, frame=a, valid_as_of=as_of)
            if fold_a.winner is None:
                continue
            covered = False
            held = False
            divergent: tuple[tuple[float, int], int | float] | None = None
            for b_frame in b_frames:
                fold_b = self._w.state(entity, attribute, frame=b_frame, valid_as_of=as_of)
                if fold_b.quantity == quantity:
                    covered = True
                    break
                if fold_b.quantity is not None and fold_b.winner is not None:
                    held = True
                    candidate = (_recency(fold_b.winner), fold_b.quantity)
                    if divergent is None or candidate[0] > divergent[0]:
                        divergent = candidate
            if covered:
                continue
            if not held:
                out.append(
                    self._quantity_fact(
                        fold_a.winner, quantity, entity=entity, attribute=attribute
                    ).to_dict()
                )
            else:
                out.append(
                    self._quantity_fact(
                        fold_a.winner, quantity, entity=entity, attribute=attribute,
                        divergent=True, b_value=divergent[1],
                    ).to_dict()
                )

        for row in m_a.assertions:
            if row.status == "default" or row.value_type == "unresolved":
                continue
            if self._w.semantics.is_accrue(row.attribute):
                continue
            entity = self._w.registry.resolve(row.entity)
            if self._w.semantics.is_set_valued(row.attribute):
                b_members = set()
                for b_frame in b_frames:
                    fold_b = self._w.state(entity, row.attribute, frame=b_frame,
                                           valid_as_of=as_of)
                    b_members.update(
                        _norm(br.value, br.value_type)
                        for br in (fold_b._value_rows
                                   or ((fold_b.winner,) if fold_b.winner else ()))
                    )
                if _norm(row.value, row.value_type) not in b_members:
                    out.append(self._fact(row).to_dict())
                continue

            held = False
            covered = False
            divergent: tuple[tuple[float, int], Any] | None = None
            for b_frame in b_frames:
                fold_b = self._w.state(entity, row.attribute, frame=b_frame,
                                       valid_as_of=as_of)
                if fold_b.winner is None:
                    continue
                held = True
                if _equivalent(row, fold_b.winner):
                    covered = True
                    break
                candidate = (_recency(fold_b.winner), fold_b.winner.value)
                if divergent is None or candidate[0] > divergent[0]:
                    divergent = candidate
            if covered:
                continue
            if not held:
                out.append(self._fact(row).to_dict())
            else:
                out.append(self._fact(row, divergent=True, b_value=divergent[1]).to_dict())
        return out

    # ------------------------------------------------------------- ask

    def ask(self, question: str, frame: str = CANON,
            as_of: float | None = None) -> Answer:
        if self._w.ingestor._model is None:
            return Answer(answered=False, unknown_reason="no model injected for ask")
        prompt = (
            "Parse this question about a tracked world into a query plan. "
            "refer_targets: the referring expressions for entities mentioned "
            "(verbatim noun phrases). keys: which attribute of which target "
            "is asked about (attribute 'in' for any where/location question). "
            "wants_location true for where-questions.\n"
            f"QUESTION: {question}"
        )
        plan = self._w.ingestor._model(prompt, _ASK_PLAN_SCHEMA)
        # HD 003: identity/existence is a CANON question; only the answer is
        # knowledge-scoped. Resolve references against canon with a scene
        # scope mirroring the observe path — the asker (from a knows:<id>
        # frame) plus the asker's current container chain — so co-located
        # objects become candidates and the 018 escalation can fire. The
        # answer keys below are still folded in the asked `frame`.
        ask_scope: str | list[str] | None = None
        if frame.startswith("knows:"):
            asker = frame[len("knows:"):]
            ask_scope = [asker, *self._w.locate(asker, valid_as_of=as_of)]
        resolved: list[str | None] = []
        asks: list[dict] = []
        for target in plan.get("refer_targets", []):
            r = self._w.refer(target, scope=ask_scope, frame=CANON, as_of=as_of)
            if r.status == "resolved":
                resolved.append(r.entity_id)
            else:
                resolved.append(None)
                asks.append({"reference": target, "candidates": list(r.candidates)})
        facts: list[dict] = []
        for key in plan.get("keys", []):
            idx = key.get("target_index", 0)
            if not (0 <= idx < len(resolved)) or resolved[idx] is None:
                continue
            fold = self._w.state(resolved[idx], key["attribute"], frame,
                                 valid_as_of=as_of)
            if fold.winner is not None:
                if fold.quantity is not None:
                    facts.append(
                        self._quantity_fact(fold.winner, fold.quantity).to_dict()
                    )
                else:
                    facts.append(self._fact(fold.winner).to_dict())
        effective_as_of = plan.get("as_of") if plan.get("as_of") is not None else as_of
        if plan.get("wants_location"):
            for eid in resolved:
                if eid:
                    fold = self._w.state(eid, "in", frame, valid_as_of=effective_as_of)
                    if fold.winner is not None:
                        f = self._fact(fold.winner).to_dict()
                        # Frame-scope the chain like the fold beside it — a
                        # canon-frame locate would leak containment into a
                        # knows: answer (HD 003, incidental).
                        f["chain"] = self._w.locate(
                            eid, frame=frame, valid_as_of=effective_as_of)
                        facts.append(f)
        if plan.get("wants_events"):
            participants = [e for e in resolved if e]
            for ev in self.events(participants=participants or None,
                                  until=effective_as_of, frame=frame):
                facts.append({"event": ev})
        answered = bool(facts)
        return Answer(
            answered=answered, facts=facts,
            unknown_reason=None if answered else
            ("unresolved references" if asks else "no folded facts on the asked keys"),
            asks=asks,
        )
