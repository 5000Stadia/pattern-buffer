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
from patternbuffer.model import ATTR_PREFIX, CANON, Assertion
from patternbuffer.semantics import AttributeSemantics, CONTAINMENT, builtin_default

logger = logging.getLogger(__name__)

_FAMILY_KEY = "__containment__"


def fold_attribute(attribute: str) -> str:
    """Built-in fold-key compatibility helper.

    World-bound reads use Indexes.fold_attribute(), which includes declared
    semantics. This free function remains for callers that only need the
    built-in defaults.
    """
    return _FAMILY_KEY if builtin_default(attribute).relation_family == CONTAINMENT else attribute


@dataclass(frozen=True, slots=True)
class FoldResult:
    """What the fold serves for one key."""

    winner: Assertion | None
    conflicted: bool = False
    conflicting: tuple[str, ...] = ()  # assertion ids party to the conflict
    corroborated_by: tuple[str, ...] = ()
    values: tuple = ()
    _value_rows: tuple[Assertion, ...] = field(default=(), repr=False, compare=False)
    quantity: int | float | None = None
    _ledger_rows: tuple[Assertion, ...] = field(default=(), repr=False, compare=False)


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
        semantics: AttributeSemantics | None = None,
    ) -> None:
        self._buffer = buffer
        self._classifier = classifier
        self._semantics = semantics or AttributeSemantics(buffer)
        # Identity closure hook: maps any entity id to its canonical
        # representative. Installed by World wiring once the registry exists.
        self._resolve = identity_resolve or (lambda eid: eid)
        self._closure_of = lambda eid: {eid}

    def set_identity_resolver(self, fn: Callable[[str], str]) -> None:
        self._resolve = fn

    def set_closure_provider(self, fn: Callable[[str], set]) -> None:
        """Identity-closure lookup for indexed (read-path) retrieval —
        installed by World wiring alongside the resolver (037)."""
        self._closure_of = fn

    def resolve_entity(self, entity: str) -> str:
        """The identity closure's canonical representative for `entity`."""
        return self._resolve(entity)

    def fold_attribute(self, attribute: str) -> str:
        """World-bound fold-key attribute, including declared semantics."""
        return _FAMILY_KEY if self._semantics.is_containment(attribute) else attribute

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
                return "document"
            if isinstance(m.value, str) and m.value.startswith("person:"):
                # Speaker-source class (027 Decision 2): a speaker is a
                # document that talks — same speaker supersedes self,
                # speakers disagreeing cross-source flag + ask (§7.2).
                return f"speaker:{m.value}"
        # stated and observed without a document chain are ONE supersession
        # class: both are rank-3 authoritative, and ordinary narrative
        # movement must supersede across them (run-4 finding: the §7.1
        # boundary is document-vs-direct, not stated-vs-observed).
        return "direct"

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

    @staticmethod
    def _is_numeric(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

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
        fa = self.fold_attribute(attribute)
        closure = sorted(self._closure_of(entity))
        attrs = sorted(self._semantics.containment_family()) if fa == _FAMILY_KEY else [attribute]
        candidates: list[Assertion] = []
        for row in self._buffer.visible(
            entity_in=closure, attribute_in=attrs,
            frame=frame, valid_as_of=valid_as_of, asserted_as_of=asserted_as_of,
        ):
            if self._classifier.durability(row.id) == EVENT:
                continue  # events never fold
            candidates.append(row)
        if not candidates:
            return FoldResult(winner=None)

        # Accrue reads raw numeric literal/delta rows (it filters to numbers
        # internally and ignores unresolved/thunk machinery), so it branches
        # before the thunk filter. Deltas are STATE by guardrail, never EVENT,
        # so the gather-loop EVENT drop above leaves the ledger intact.
        if self._semantics.is_accrue(attribute):
            return self._fold_accrue(candidates)

        # A `delta` on a NON-accrue attribute is not an absolute value — drop
        # it before the thunk filter so it can neither suppress an unresolved
        # placeholder nor compete in _fold_state.
        candidates = [r for r in candidates if r.value_type != "delta"]
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

        if self._semantics.is_set_valued(attribute):
            return self._fold_set_valued(candidates)

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
            return self._fold_state(
                by_class[STATE], asserted_as_of, is_containment=(fa == _FAMILY_KEY)
            )

        if by_class[DISPOSITIONAL]:
            rows = by_class[DISPOSITIONAL]
            winner = max(rows, key=lambda r: (r.valid_from or float("-inf"), r.asserted_at))
            return FoldResult(winner=winner)
        return FoldResult(winner=None)

    def _fold_accrue(self, rows: list[Assertion]) -> FoldResult:
        """Accrue quantities: latest absolute numeric baseline plus later
        signed numeric deltas. The ledger is provenance-only; the derived
        quantity is surfaced separately from stored facts."""
        def recency(row: Assertion) -> tuple[float, int]:
            return (
                row.valid_from if row.valid_from is not None else float("-inf"),
                row.asserted_at,
            )

        literals = [
            r for r in rows
            if r.value_type == "literal" and self._is_numeric(r.value)
        ]
        deltas = [
            r for r in rows
            if r.value_type == "delta" and self._is_numeric(r.value)
        ]
        baseline = max(literals, key=recency) if literals else None
        baseline_value: int | float = baseline.value if baseline is not None else 0
        baseline_key = recency(baseline) if baseline is not None else None
        contributing = [
            r for r in deltas if baseline_key is None or recency(r) > baseline_key
        ]
        contributing.sort(key=recency)
        if baseline is None and not contributing:
            return FoldResult(winner=None)
        total = baseline_value + sum(r.value for r in contributing)
        winner = contributing[-1] if contributing else baseline
        ledger_rows = ((baseline,) if baseline is not None else ()) + tuple(contributing)
        return FoldResult(
            winner=winner,
            quantity=total,
            _ledger_rows=ledger_rows,
        )

    def _fold_set_valued(self, rows: list[Assertion]) -> FoldResult:
        """Set-valued keys accumulate current members instead of conflicting.

        Duplicate assertions for the same member supersede within that
        member's own (entity, attribute, value-identity) key. The served
        winner remains the most-recent current member for compatibility.
        """
        def recency(row: Assertion) -> tuple[float, int]:
            return (row.valid_from if row.valid_from is not None else float("-inf"), row.asserted_at)

        def value_identity(row: Assertion) -> tuple[str, object]:
            if row.value_type == "entity" and isinstance(row.value, str):
                return row.value_type, self._resolve(row.value)
            return row.value_type, repr(row.value)

        current: dict[tuple[str, str, tuple[str, object]], Assertion] = {}
        for row in rows:
            key = (self._resolve(row.entity), row.attribute, value_identity(row))
            prior = current.get(key)
            if prior is None or recency(row) > recency(prior):
                current[key] = row
        value_rows = tuple(sorted(current.values(), key=lambda r: (r.asserted_at, r.id)))
        winner = max(value_rows, key=recency) if value_rows else None
        return FoldResult(
            winner=winner,
            values=tuple(r.value for r in value_rows),
            _value_rows=value_rows,
        )

    def _fold_state(
        self, rows: list[Assertion], asserted_as_of: int | None,
        is_containment: bool = False,
    ) -> FoldResult:
        """STATE: recency wins within a source class; across classes,
        agreement corroborates (serve the more precise value), disagreement
        flags and keeps serving the prior in-class winner (spec §7).

        ``is_containment`` (HD 002 finding 2): for the containment/movement
        family, relocation is inherently time-sequential — a later move
        supersedes an earlier placement across source classes, instead of
        raising the §7.2 cross-source flag. A genuine same-valid-time
        cross-source disagreement still flags."""
        # Evidence rank (the assumption quarantine, generalized): provisional
        # classes never hold incumbency against authoritative ones — an
        # authored/observed fact arriving over a character's inference or a
        # working assumption is confirmation or correction, never a conflict
        # to ask about. Peers ({stated, observed}) keep the full
        # corroborate-vs-flag machinery below. (Found by chapter-test run 3:
        # a narrator's wrong `inferred` theory outheld later `stated` canon.)
        rank = {"stated": 3, "observed": 3, "generated": 2, "inferred": 1, "assumed": 0}
        top = max(rank.get(r.status, 0) for r in rows)
        rows = [r for r in rows if rank.get(r.status, 0) == top]

        by_source: dict[str, list[Assertion]] = {}
        for r in rows:
            by_source.setdefault(self._source_class(r, asserted_as_of), []).append(r)
        winners: dict[str, Assertion] = {}
        for sc, rs in by_source.items():
            top = max(rs, key=lambda r: (r.valid_from or float("-inf"), r.asserted_at))
            # Supersession requires world-time progression: rows tied at the
            # winner's valid_from with a DIFFERENT value are a simultaneous
            # contradiction, not an update — flag, serve earliest-asserted
            # (run-4 finding: log order alone must never pick a truth).
            tied = [r for r in rs if r.valid_from == top.valid_from]
            if len({repr(r.value) for r in tied}) > 1:
                earliest = min(tied, key=lambda r: r.asserted_at)
                return FoldResult(
                    winner=earliest,
                    conflicted=True,
                    conflicting=tuple(r.id for r in tied),
                )
            winners[sc] = top
        if len(winners) == 1:
            return FoldResult(winner=next(iter(winners.values())))

        if is_containment:
            # Movement is time-sequential: the latest-valid move supersedes
            # earlier placements across source classes (HD 002 finding 2).
            # Only a same-latest-valid_from disagreement is a true
            # contradiction — serve earliest-asserted, flag those rows.
            top_vf = max(
                (w.valid_from if w.valid_from is not None else float("-inf"))
                for w in winners.values()
            )
            current = [
                w for w in winners.values()
                if (w.valid_from if w.valid_from is not None else float("-inf")) == top_vf
            ]
            if len({repr(w.value) for w in current}) > 1:
                earliest = min(current, key=lambda r: r.asserted_at)
                return FoldResult(
                    winner=earliest,
                    conflicted=True,
                    conflicting=tuple(sorted(r.id for r in current)),
                )
            return FoldResult(winner=max(current, key=lambda r: r.asserted_at))

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
        closure = sorted(self._closure_of(entity))
        attrs: set[str] = set()
        for row in self._buffer.visible(
            entity_in=closure,
            frame=frame, valid_as_of=valid_as_of, asserted_as_of=asserted_as_of,
        ):
            if not row.entity.startswith("a:") and not row.entity.startswith(ATTR_PREFIX):
                attrs.add(row.attribute)
        out: dict[str, FoldResult] = {}
        for attr in attrs:
            result = self.fold_key(entity, attr, frame, valid_as_of, asserted_as_of)
            if result.winner is not None:
                out[self.fold_attribute(attr)] = result
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
            if (
                row.attribute in self._semantics.lateral_family()
                and row.value_type == "entity"
                and not row.entity.startswith("a:")
                and not row.entity.startswith(ATTR_PREFIX)
            ):
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
