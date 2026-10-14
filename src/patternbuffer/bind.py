"""``bind``: one deterministic matcher for a turn's mentions (PLAY-BIND-V1).

A read. Given the rows a turn's extraction produced, it decides once per raw id
whether that id names an entity that exists at the turn's valid time, mints a
collision-checked id where the host allows, or reports why not, and returns one
result per row. It makes no model call and writes nothing; every permission
(voice, frames, stub gates, place creation, refusing a future name) stays with
the host, around it (§5).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from patternbuffer.model import CANON, ID_RE, infer_value_type
from patternbuffer.names import ARTICLES, contains_matching_run, keys_match, name_key, tokens

logger = logging.getLogger(__name__)

BINDABLE = ("person", "place", "obj")
ADMITTING = frozenset({"bound", "minted", "kept"})
_NAME_ATTRS = ["name", "alias", "learned_alias"]


@dataclass(frozen=True)
class Side:
    """One side of a row: the raw id, its outcome (``bound``, ``minted``,
    ``kept``, ``ambiguous``, ``out_of_scope``, ``future_only``, ``unknown`` or
    ``malformed``), the id it resolved to, the candidates it named, and the
    signal that decided it (``id``, ``name``, ``kind``)."""
    raw: Any
    outcome: str
    id: str | None = None
    candidates: tuple[str, ...] = ()
    signal: str | None = None


@dataclass(frozen=True)
class RowResult:
    """One input row: admitted when every side is bound, minted or kept, and
    then ``row`` is a copy with the ids rewritten. Admitted means bound, not
    permission to ingest (§4)."""
    index: int
    admitted: bool
    row: dict | None
    subject: Side
    value: Side | None = None


@dataclass(frozen=True)
class BindResult:
    """Every row's result in input order, each raw id's minted id, and the
    ``scope``/``include`` ids left out because they don't exist at ``as_of``."""
    rows: tuple[RowResult, ...]
    mints: Mapping[str, str] = field(default_factory=dict)
    excluded: tuple[str, ...] = ()


def namespace(entity_id: str) -> str:
    return entity_id.split(":", 1)[0]


def compatible(raw_ns: str, candidate_ns: str) -> bool:
    """A person binds a person; a place or obj binds a place or obj (§2.4)."""
    if raw_ns == "person" or candidate_ns == "person":
        return raw_ns == candidate_ns
    return raw_ns in ("place", "obj") and candidate_ns in ("place", "obj")


def slug_words(entity_id: str) -> str:
    return entity_id.split(":", 1)[1].replace("_", " ").replace(":", " ")


def surface_matches(surfaces: Iterable[tuple[str, ...]],
                    names: Iterable[tuple[str, ...]]) -> bool:
    """A surface key equals a name key, or is a whole-token run inside one, up
    to number (§2.4, §3). A key of articles alone matches only exactly."""
    names = list(names)
    for key in surfaces:
        if not key:
            continue
        fragment_ok = not all(tok in ARTICLES for tok in key)
        for nk in names:
            if keys_match(nk, key) or (fragment_ok and contains_matching_run(nk, key)):
                return True
    return False


class Bind:
    """The ``bind`` read over one world's buffer, indexes and identity
    registry (the same three ``Refer`` holds)."""

    def __init__(self, buffer, indexes, registry) -> None:
        self._buffer = buffer
        self._indexes = indexes
        self._registry = registry

    # ------------------------------------------------------------ existence

    def _first_valid(self, canon: str, frame: str, cache: dict) -> float | None:
        """The earliest valid time any closure member has a visible row in
        ``frame`` (timeless counts as -inf); None when it has none at the head
        (§2a)."""
        if canon not in cache:
            members = sorted(self._registry.closure(canon))
            rows = self._buffer.visible(entity_in=members, frame=frame)
            cache[canon] = (min(-math.inf if r.valid_from is None else r.valid_from
                                for r in rows) if rows else None)
        return cache[canon]

    def _names(self, canon: str, frame: str, valid_as_of: float | None,
               cache: dict) -> list[tuple[str, ...]]:
        """A candidate's name keys: its closure's name, alias and learned-alias
        rows in ``frame`` (at ``valid_as_of`` when given), plus each member's
        slug read as words (§2a)."""
        k = (canon, valid_as_of)
        if k not in cache:
            members = sorted(self._registry.closure(canon))
            rows = self._buffer.visible(entity_in=members, attribute_in=_NAME_ATTRS,
                                        frame=frame, valid_as_of=valid_as_of)
            keys = {name_key(r.value) for r in rows if isinstance(r.value, str)}
            keys |= {name_key(slug_words(m)) for m in members}
            cache[k] = [key for key in keys if key]
        return cache[k]

    def _kind(self, canon: str, frame: str, valid_as_of: float | None) -> tuple[str, ...]:
        result = self._indexes.fold_key(canon, "kind", frame, valid_as_of, None)
        value = result.winner.value if result.winner else None
        return tuple(tokens(value.replace("_", " "))) if isinstance(value, str) else ()

    # ------------------------------------------------------------ candidates

    def _candidates(self, scope, include, widen, as_of, frame, first) -> tuple[set, list]:
        cands: set[str] = set()
        excluded: list[str] = []

        def exists(e: str) -> bool:
            fv = self._first_valid(e, frame, first)
            return fv is not None and fv <= as_of

        frontier: list[str] = []
        for root in scope:
            canon = self._registry.resolve(root)
            if exists(canon):
                frontier.append(canon)
            else:
                excluded.append(root)
        seen: set[str] = set()
        while frontier:                                # refer's scope expansion
            e = frontier.pop(0)
            if e in seen:
                continue
            seen.add(e)
            cands.add(e)
            frontier.extend(self._indexes.contents(e, frame, as_of, None))
        for raw in include:                            # an exact roster (r1.1)
            canon = self._registry.resolve(raw)
            if exists(canon):
                cands.add(canon)
            else:
                excluded.append(raw)
        for ns in widen:                               # named = a name or alias row
            for row in self._buffer.visible(attribute_in=["name", "alias"], frame=frame,
                                            valid_as_of=as_of, entity_prefix=f"{ns}:"):
                canon = self._registry.resolve(row.entity)
                if exists(canon):
                    cands.add(canon)
        cands = {c for c in cands if ID_RE.fullmatch(c) and namespace(c) in BINDABLE}
        return cands, sorted(set(excluded))

    def _future(self, raw_ns: str, as_of: float, frame: str, first: dict) -> list[str]:
        """Compatible entities with a name, alias or kind row at the head in
        ``frame`` that don't exist at ``as_of`` (§2.6, global)."""
        out: set[str] = set()
        for row in self._buffer.visible(attribute_in=["name", "alias", "kind"], frame=frame):
            if not ID_RE.fullmatch(row.entity) or namespace(row.entity) not in BINDABLE:
                continue
            canon = self._registry.resolve(row.entity)
            if not compatible(raw_ns, namespace(canon)):
                continue
            fv = self._first_valid(canon, frame, first)
            if fv is not None and fv > as_of:
                out.add(canon)
        return sorted(out)

    # ------------------------------------------------------------ one raw id

    def _match(self, raw, surfaces, pool, frame, valid_as_of, names_cache) -> Side | None:
        """Steps 4-5 over ``pool``: name, then unique kind. None on no match."""
        raw_ns = namespace(raw)
        compat = sorted(c for c in pool if compatible(raw_ns, namespace(c)))
        hits = [c for c in compat
                if surface_matches(surfaces, self._names(c, frame, valid_as_of, names_cache))]
        if len(hits) == 1:
            return Side(raw, "bound", hits[0], signal="name")
        if hits:
            return Side(raw, "ambiguous", candidates=tuple(hits), signal="name")
        slug = tuple(tokens(slug_words(raw)))
        kinds = [c for c in compat if slug and keys_match(self._kind(c, frame, valid_as_of), slug)]
        if len(kinds) == 1:
            return Side(raw, "bound", kinds[0], signal="kind")
        if kinds:
            return Side(raw, "ambiguous", candidates=tuple(kinds), signal="kind")
        return None

    def _decide(self, raw, surfaces, cands, as_of, frame, mint, state) -> Side:
        if not isinstance(raw, str) or not ID_RE.fullmatch(raw):
            return Side(raw, "malformed")                                   # 1
        ns = namespace(raw)
        if ns not in BINDABLE:
            return Side(raw, "kept", raw)                                   # 2
        first, names_cache = state["first"], state["names"]
        canon = self._registry.resolve(raw)                                 # 3
        fv = self._first_valid(canon, frame, first)
        if fv is not None and fv <= as_of:
            if canon in cands:
                return Side(raw, "bound", canon, signal="id")
            return Side(raw, "out_of_scope", canon, signal="id")
        if fv is not None:
            return Side(raw, "future_only", candidates=(canon,), signal="id")
        side = self._match(raw, surfaces, cands, frame, as_of, names_cache)  # 4-5
        if side is not None:
            return side
        if state.get("future") is None:
            state["future"] = {}
        if ns not in state["future"]:
            state["future"][ns] = self._future(ns, as_of, frame, first)
        future = self._match(raw, surfaces, state["future"][ns], frame, None,
                             names_cache)                                   # 6
        if future is not None:
            ids = (future.id,) if future.id else future.candidates
            return Side(raw, "future_only", candidates=ids, signal=future.signal)
        if ns in mint:                                                      # 7
            return Side(raw, "minted", self._allocate(raw, state))
        return Side(raw, "unknown")                                         # 8

    def _allocate(self, raw: str, state: dict) -> str:
        """``raw``, or ``raw_2``, ``raw_3``... clear of every id the log has
        ever named and this call's earlier mints (§2.7)."""
        if raw in state["mints"]:
            return state["mints"][raw]
        if state.get("taken") is None:
            state["taken"] = self._buffer.ids()
        taken = state["taken"]
        new, n = raw, 1
        while new in taken:
            n += 1
            new = f"{raw}_{n}"
        taken.add(new)
        state["mints"][raw] = new
        return new

    # ------------------------------------------------------------ the read

    def __call__(self, rows: Sequence[Mapping[str, Any]], *, as_of: float,
                 scope: Sequence[str] = (), include: Sequence[str] = (),
                 widen: Sequence[str] = (), mint: Sequence[str] = (),
                 frame: str = CANON) -> BindResult:
        if isinstance(as_of, bool) or not isinstance(as_of, (int, float)):
            raise ValueError(f"bind: as_of must be a number, got {as_of!r}")
        for name, given in (("widen", widen), ("mint", mint)):
            bad = [ns for ns in given if ns not in BINDABLE]
            if bad:
                raise ValueError(f"bind: {name} takes {', '.join(BINDABLE)} only, got {bad}")
        for name, given in (("scope", scope), ("include", include)):
            if isinstance(given, str):
                raise ValueError(f"bind: {name} is a list of ids, got the string {given!r}")
        if not all(isinstance(r, Mapping) for r in rows):
            raise ValueError("bind: every row is a mapping")
        state: dict = {"first": {}, "names": {}, "mints": {}}
        cands, excluded = self._candidates(scope, include, widen, as_of, frame, state["first"])

        # One decision per raw id per call (r1.1): surfaces are gathered from
        # every row where the raw id is the subject.
        surfaces: dict[Any, set[tuple[str, ...]]] = {}
        sides: list[tuple[Any, Any]] = []
        for row in rows:
            subject = row.get("entity")
            value = row.get("value")
            has_value = (infer_value_type(value, row.get("value_type")) == "entity"
                         and isinstance(value, str))
            sides.append((subject, value if has_value else None))
            for raw in (subject, value if has_value else None):
                if isinstance(raw, str) and raw not in surfaces:
                    surfaces[raw] = ({name_key(slug_words(raw))}
                                     if ID_RE.fullmatch(raw) else set())
            if isinstance(subject, str):
                texts = [row.get("name")]
                for key in ("names", "aliases"):
                    extra = row.get(key)
                    if isinstance(extra, (list, tuple)):
                        texts.extend(extra)
                surfaces[subject] |= {name_key(t) for t in texts if isinstance(t, str)}
        decided: dict[Any, Side] = {}
        for raw, keys in surfaces.items():
            decided[raw] = self._decide(raw, [k for k in keys if k], cands, as_of,
                                        frame, mint, state)

        results: list[RowResult] = []
        for index, (row, (subject, value)) in enumerate(zip(rows, sides)):
            s_side = decided.get(subject) if isinstance(subject, str) else Side(subject,
                                                                               "malformed")
            v_side = decided[value] if value is not None else None
            admitted = s_side.outcome in ADMITTING and (
                v_side is None or v_side.outcome in ADMITTING)
            out = None
            if admitted:
                out = dict(row)
                out["entity"] = s_side.id
                if v_side is not None:
                    out["value"] = v_side.id
            results.append(RowResult(index, admitted, out, s_side, v_side))
        logger.debug("bind: %d rows, %d admitted, %d minted", len(results),
                     sum(r.admitted for r in results), len(state["mints"]))
        return BindResult(tuple(results), dict(state["mints"]), tuple(excluded))
