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
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from patternbuffer.model import CANON, META_ATTRIBUTES
from patternbuffer.thunks import UNKNOWN, ResolutionDenied

if TYPE_CHECKING:  # pragma: no cover
    from patternbuffer import World

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- payloads


@dataclass
class Receipt:
    world_id: str
    seq_range: list[int]
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
            seq_range=[min(r.seq for r in rows), max(r.seq for r in rows)] if rows else [0, 0],
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

    # -------------------------------------------------------------- writes

    def ingest(self, text: str, source: str | None = None, scene: str | None = None,
               at: float | None = None, frame: str | None = None) -> Receipt:
        if at is not None:
            self._w.ingestor.cursor.advance(at)
        context = f"\nSCENE HINT (context only, never a spatial anchor): {scene}" if scene else ""
        rows = self._w.ingest(text, context=context, frame=frame)
        if source is not None:
            fact_rows = [r for r in rows if not r.entity.startswith("a:")
                         and r.attribute not in META_ATTRIBUTES]
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
            return {"status": "denied", "facts": [], "reason": str(exc)}
        if out is UNKNOWN:
            return {"status": "unknown", "facts": []}
        return {"status": "resolved",
                "facts": [self._fact(r).to_dict() for r in out if r is not None]}

    def retract(self, assertion_id: str, reason: str) -> Receipt:
        return self._receipt([self._w.truth.retract(assertion_id, reason)])

    # --------------------------------------------------- reads (LLM-free)

    def snapshot(self, scope, frame: str = CANON, as_of: float | None = None,
                 lens: str = "current_state", budget: int | None = None,
                 since: float | None = None) -> dict:
        roots = [scope] if isinstance(scope, str) else list(scope)
        bad = [s for s in roots if ":" not in s]
        if bad:
            return {"error": "snapshot scope must be entity ids (use ask for references)",
                    "bad": bad}
        m = self._w.materialize(roots, as_of=as_of, frame=frame, lens=lens,
                                budget=budget, since=since)
        return {
            "world_id": self._w.world_id,
            "charter": self._w.charter(),
            "frame": m.frame, "lens": m.lens, "as_of": m.as_of,
            "facts": [self._fact(r).to_dict() for r in m.assertions],
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
        out = {"status": "conflicted" if fold.conflicted else "known",
               "fact": self._fact(fold.winner).to_dict()}
        if fold.conflicted:
            out["conflicting"] = list(fold.conflicting)
        return out

    def locate(self, entity: str, as_of: float | None = None) -> list[str]:
        return self._w.locate(entity, valid_as_of=as_of)

    def contents(self, container: str, as_of: float | None = None) -> list[str]:
        return self._w.contents(container, valid_as_of=as_of)

    def path(self, a: str, b: str) -> list[str] | None:
        return self._w.path(a, b)

    def events(self, kind: str | None = None,
               participants: str | list[str] | None = None,
               since: float | None = None, until: float | None = None,
               frame: str = CANON) -> list[dict]:
        scope = sorted({
            self._w.registry.resolve(r.entity)
            for r in self._w.buffer.visible(frame=frame)
            if r.entity.startswith("event:")})
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

    def frame_diff(self, a: str, b: str, scope, as_of: float | None = None) -> list[dict]:
        """Semantic fact diff: keys folded in `a`, absent or divergent in
        `b`. Never compares assertion ids (frames are sparse copies)."""
        roots = [scope] if isinstance(scope, str) else list(scope)
        m_a = self._w.materialize(roots, frame=a, as_of=as_of)
        out: list[dict] = []
        for row in m_a.assertions:
            if row.status == "default" or row.value_type == "unresolved":
                continue
            entity = self._w.registry.resolve(row.entity)
            fold_b = self._w.state(entity, row.attribute, frame=b, valid_as_of=as_of)
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
        resolved: list[str | None] = []
        asks: list[dict] = []
        for target in plan.get("refer_targets", []):
            r = self._w.refer(target, frame=frame, as_of=as_of)
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
                facts.append(self._fact(fold.winner).to_dict())
        if plan.get("wants_location"):
            for eid in resolved:
                if eid:
                    fold = self._w.state(eid, "in", frame, valid_as_of=as_of)
                    if fold.winner is not None:
                        f = self._fact(fold.winner).to_dict()
                        f["chain"] = self._w.locate(eid, valid_as_of=as_of)
                        facts.append(f)
        answered = bool(facts)
        return Answer(
            answered=answered, facts=facts,
            unknown_reason=None if answered else
            ("unresolved references" if asks else "no folded facts on the asked keys"),
            asks=asks,
        )
