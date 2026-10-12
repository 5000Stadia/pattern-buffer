"""The event-records section of `Indexes`: EVENTS-ONE-READER-V1's one reader
for event records, the pick and payload built on it, and the event-edge reads
(`event_participation`, `caused_by_of`).
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from patternbuffer.indexes._core import FoldResult
from patternbuffer.model import (
    CANON,
    EVENT_PREFIX,
    META_ATTRIBUTES,
    Assertion,
    FrameSel,
    is_event_row,
)

# The movement-payload keys of a `kind=moved` event (MOVED-EVENT-V1 §E1), named
# once (EVENTS-ONE-READER-V1 §3): a move's closing coordinate is the `valid_to`
# its payload rows carry, and `in_transit`'s anchor reads them.
MOVEMENT_KEYS = ("kind", "agent", "origin", "destination", "manner")
# A record's single-valued keys (EVENTS-ONE-READER-V1 §4 Rule B): the event
# algebra (whitepaper §12, `event(kind, agents, patients, t, effects)`) and
# MOVED-EVENT-V1 give each one value, so top-rank rows disagreeing at the
# winner's stamp are a contradiction. Every other attribute is description,
# which an occurrence may hold several values of, and is never conflicted.
_EVENT_SINGLE_VALUED = frozenset({"kind", "origin", "destination", "manner"})


class EventsMixin:
    """The event-records section of `Indexes`."""

    # ------------------------------------- event records (EVENTS-ONE-READER-V1)
    # An event is an entity (whitepaper §3.1) whose rows are its RECORD: what
    # kind of occurrence it was, who and what took part, when. A record is
    # read, never folded — nothing supersedes an occurrence, and an occurrence
    # is not a value of any other entity's key (§5). One reader returns
    # records, and every event read uses it.

    def event_records(
        self,
        frame: FrameSel = CANON,
        *,
        ids: Iterable[str] | None = None,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> dict[str, tuple[Assertion, ...]]:
        """The event records visible in `frame` (EVENTS-ONE-READER-V1 §1):
        resolved event id -> its record, events in the listing order
        (`_event_order`) and each record's rows in `recency_key` order.

        - **Identity.** An event is a resolved id: the event rows
          (`is_event_row`) visible in `frame` are grouped by the canonical id
          of their stored subject. A row on any other subject never makes an
          event — not a `caused_by` that names one, not an identity edge, not
          a thing contained in one. An event merged into a closure whose
          canonical id is not an `event:` id is keyed by that id, as
          `entities()` reports it.
        - **The record** is the event's rows minus the engine's machinery
          (`META_ATTRIBUTES`: identity edges, provenance, semantics), which
          rides beside a record as it does beside every entity.
        - **Never the sidecar**: no classification lookup, so a record reads
          the same before a sweep as after it.
        - **The asserted axis** is `visible(asserted_as_of=)`, retractions
          included, as for every read.
        - **The valid axis**, one rule for every event read: an event has
          occurred by `T` when `T` is None, when it has no stamped row (a
          timeless event, such as a merge), or when its earliest stamped
          `valid_from` is <= `T`; its record as of `T` is its timeless rows
          plus its rows stamped <= `T`. `valid_to` never hides an event row:
          a closed or zero-duration event stays history (MOVED-EVENT-V1 §D.6).
        - **`ids`** limits the read to the named events, each through its
          identity closure (the per-event callers: `event_attribute`, the
          `situation` lens, `event_participation`, `caused_by_of`)."""
        if ids is None:
            rows = self._buffer.visible(frame=frame, entity_prefix=EVENT_PREFIX,
                                        asserted_as_of=asserted_as_of)
        else:
            members: set[str] = set()
            for eid in ids:
                members |= self._closure_of(self._resolve(eid))
            # Only a stored `event:` subject carries event rows: a closure
            # without one has no record, and is read without a query.
            stored = sorted(m for m in members if m.startswith(EVENT_PREFIX))
            if not stored:
                return {}
            rows = self._buffer.visible(entity_in=stored, frame=frame,
                                        asserted_as_of=asserted_as_of)
        grouped: dict[str, list[Assertion]] = {}
        for row in rows:
            if not is_event_row(row) or row.attribute in META_ATTRIBUTES:
                continue
            grouped.setdefault(self._resolve(row.entity), []).append(row)
        records: dict[str, tuple[Assertion, ...]] = {}
        for event_id, record in grouped.items():
            record.sort(key=self.recency_key)
            if valid_as_of is not None:
                stamped = [r.valid_from for r in record if r.valid_from is not None]
                if stamped and min(stamped) > valid_as_of:
                    continue  # has not occurred by T
                record = [r for r in record
                          if r.valid_from is None or r.valid_from <= valid_as_of]
            records[event_id] = tuple(record)
        return dict(sorted(records.items(), key=lambda item: self._event_order(item[1])))

    @staticmethod
    def event_time(record: Sequence[Assertion]) -> float | None:
        """An event's `t`: the greatest `valid_from` in its record, or None
        when every row is timeless."""
        stamps = [r.valid_from for r in record if r.valid_from is not None]
        return max(stamps) if stamps else None

    _event_time = event_time  # the name before R21; kept as an alias

    @classmethod
    def _event_order(cls, record: Sequence[Assertion]) -> tuple:
        """The one order wherever events are listed (EVENTS-ONE-READER-V1 §1):
        by `t` (None first), then by the event's earliest row in
        `recency_key` order — today's `events()` order, reproduced."""
        t = cls.event_time(record)
        return (t if t is not None else float("-inf"),
                min(cls.recency_key(r) for r in record))

    @classmethod
    def event_pick(cls, rows: Sequence[Assertion]) -> Assertion | None:
        """The pick, the one rule for every single value read from a record
        (EVENTS-ONE-READER-V1 §1): among an attribute's rows, those at the top
        evidence rank (`_top_evidence`), then the one with the greatest
        `recency_key`. Rank first, as batch A applies it to every fold: a
        later `assumed` kind never displaces a `stated` one (P5)."""
        if not rows:
            return None
        return max(cls._top_evidence(list(rows)), key=cls.recency_key)

    _event_pick = event_pick  # the name before R21; kept as an alias

    @classmethod
    def event_payload(cls, event_id: str, record: Sequence[Assertion]) -> dict[str, Any]:
        """One event's dict, built from its record (a pure function;
        EVENTS-ONE-READER-V1 §1): MOVED-EVENT-V1 §E1's twelve keys, in their
        order.

        `kind`, `origin`, `destination`, `manner`: the pick, and
        `origin_bound`/`destination_bound` are the pick's `value_type ==
        "entity"` (the stored discriminator, never grammar). `agents`,
        `patients`, `caused_by`: every row's stored value, in `recency_key`
        order. `t`: the greatest `valid_from` in the record, or None. `valid_to`:
        the `valid_to` of the latest movement-payload row (`MOVEMENT_KEYS`)
        that carries one — None for an open event; a completed zero-duration
        move carries `valid_from == valid_to`."""
        ordered = sorted(record, key=cls.recency_key)

        def pick(attribute: str) -> Assertion | None:
            return cls.event_pick([r for r in ordered if r.attribute == attribute])

        def values(attribute: str) -> list[Any]:
            return [r.value for r in ordered if r.attribute == attribute]

        kind, origin = pick("kind"), pick("origin")
        destination, manner = pick("destination"), pick("manner")
        closing = [r for r in ordered
                   if r.attribute in MOVEMENT_KEYS and r.valid_to is not None]
        return {
            "id": event_id,
            "kind": kind.value if kind is not None else None,
            "agents": values("agent"),
            "patients": values("patient"),
            "t": cls.event_time(ordered),
            "caused_by": values("caused_by"),
            "origin": origin.value if origin is not None else None,
            "destination": destination.value if destination is not None else None,
            "manner": manner.value if manner is not None else None,
            "valid_to": closing[-1].valid_to if closing else None,
            "origin_bound": origin.value_type == "entity" if origin is not None else None,
            "destination_bound": (destination.value_type == "entity"
                                  if destination is not None else None),
        }

    def event_attribute(
        self,
        entity: str,
        attribute: str,
        frame: FrameSel = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
        *,
        correlated: bool = False,
    ) -> FoldResult:
        """A point read of an event's record (EVENTS-ONE-READER-V1 §4 Rule B):
        one attribute from the record of `entity`'s closure, as of the read
        (`event_records`' two axes). With `correlated=True` it reads the
        records of the `aka` union, as `state_union` and
        `current_state(correlated=)` do.

        No row, or a machinery attribute (`META_ATTRIBUTES`): nothing served.
        `winner` is the pick. `kind`, `origin`, `destination` and `manner` are
        single-valued: when the top-rank rows at the winner's stamp disagree
        (`_value_key`) the result is conflicted, `conflicting` holding their
        ids in log order — the fold's own same-stamp contradiction test. Every
        other attribute is description and never conflicted. A set-valued one
        (`name`, `alias`, `connects_to`, a declared set) keeps READ-SURFACE-V1
        §4's rule for a set-valued key: its members, each value once, in member
        order, whenever there are members. Any other description attribute
        with two or more rows holds them all in `_value_rows`, in
        `recency_key` order — §4's rule extended to a record's description.
        `state()` serves `_value_rows` as `values`. The point reads (`state`,
        `state_union`, `ask`'s keys, identity's kind lookup) call this only when
        the fold serves nothing; `fold_key` itself stays standing-only."""
        if attribute in META_ATTRIBUTES:
            return FoldResult(winner=None)
        entity = self._resolve(entity)
        ids = (self._correlation_of(entity, valid_as_of=valid_as_of,
                                    asserted_as_of=asserted_as_of, frame=frame)
               if correlated else {entity})
        rows = sorted(
            (r for record in self.event_records(
                frame, ids=sorted(ids), valid_as_of=valid_as_of,
                asserted_as_of=asserted_as_of).values()
             for r in record if r.attribute == attribute),
            key=self.recency_key)
        winner = self.event_pick(rows)
        if winner is None:
            return FoldResult(winner=None)
        if attribute in _EVENT_SINGLE_VALUED:
            tied = sorted((r for r in self._top_evidence(rows)
                           if r.valid_from == winner.valid_from),
                          key=lambda r: r.asserted_at)
            if len({self._value_key(r) for r in tied}) > 1:
                return FoldResult(winner=winner, conflicted=True,
                                  conflicting=tuple(r.id for r in tied))
            return FoldResult(winner=winner)
        if self._semantics.is_set_valued(attribute):
            members = self._fold_set_valued(rows)
            return FoldResult(winner=winner, values=members.values,
                              _value_rows=members._value_rows)
        if len(rows) > 1:
            return FoldResult(winner=winner, values=tuple(r.value for r in rows),
                              _value_rows=tuple(rows))
        return FoldResult(winner=winner)

    def event_participation(
        self,
        entity: str,
        frame: str = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> list[str]:
        """Events whose record, as of the read, has an `agent` or `patient`
        row resolving into this entity's closure (EVENTS-ONE-READER-V1 §6).

        Candidates come from the indexed participant/value lookup, kept only
        when the row is an event row; their records then decide, under the
        reader's valid-axis rule — so a closed or zero-duration event stays
        reachable once it has occurred, and a non-event subject with an
        `agent` row is no event.
        """
        entity = self._resolve(entity)
        candidates: set[str] = set()
        for eid in sorted(self._closure_of(entity)):
            for row in self._buffer.visible(
                attribute_in=["agent", "patient"],
                value=eid,
                frame=frame,
                asserted_as_of=asserted_as_of,
            ):
                if is_event_row(row):
                    candidates.add(self._resolve(row.entity))
        if not candidates:
            return []
        records = self.event_records(frame, ids=sorted(candidates),
                                     valid_as_of=valid_as_of, asserted_as_of=asserted_as_of)
        return sorted(
            event_id for event_id, record in records.items()
            if any(r.attribute in ("agent", "patient") and isinstance(r.value, str)
                   and self._resolve(r.value) == entity for r in record))

    def caused_by_of(
        self,
        event_ids: list[str] | set[str] | tuple[str, ...],
        frame: str = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> list[str]:
        """The resolved `caused_by` values of these events' records, as of the
        read (EVENTS-ONE-READER-V1 §6). Each event is read through its
        identity closure, so a cause on a merged event's stored id is reached
        (post-impl review)."""
        ids = sorted({self._resolve(e) for e in event_ids})
        if not ids:
            return []
        out: set[str] = set()
        for record in self.event_records(frame, ids=ids, valid_as_of=valid_as_of,
                                         asserted_as_of=asserted_as_of).values():
            for row in record:
                if (row.attribute == "caused_by" and row.value_type == "entity"
                        and isinstance(row.value, str)):
                    out.add(self._resolve(row.value))
        return sorted(out)
