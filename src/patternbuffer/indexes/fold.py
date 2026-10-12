"""The fold section of `Indexes`: the current-value rule for every key —
`fold_key`, `state_union`, `confidence`, `current_state` and the per-durability
folds beneath them (whitepaper §13; FOLD-CORRECTNESS-V1).
"""

from __future__ import annotations

import math
from decimal import Decimal

from patternbuffer.classify import CONSTITUTIVE, DISPOSITIONAL, EVENT, STATE
from patternbuffer.codec import check_no_mix, exact_sum
from patternbuffer.indexes._core import FoldResult, _FAMILY_KEY
from patternbuffer.model import (
    ATTR_PREFIX,
    CANON,
    MECHANISM_STATUS,
    META_ATTRIBUTES,
    Assertion,
    is_event_row,
)

_FAMILY_NAME = "in"  # the family's only name outside the engine (FOLD-CORRECTNESS-V1 §7)
CONFIDENCE_PARAMS = {
    # CONFIDENCE-V1: fixed, tunable read-layer weights. These scores are
    # derived on demand and are never stored in the assertion log or sidecar.
    "weights": {
        "provenance": 0.45,
        "recency": 0.30,
        "corroboration": 0.25,
    },
    "provenance": {
        "stated": 1.0,
        "observed": 1.0,
        "inferred": 0.6,
        "assumed": 0.3,
        "generated": 0.4,
        "default": 0.0,
    },
    "recency_scale": 10.0,
    "corroboration_scale": 4.0,
}


class FoldMixin:
    """The fold section of `Indexes`."""

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
        return self._fold_over_closure(
            closure, attribute, fa, frame, valid_as_of, asserted_as_of
        )

    def _fold_over_closure(
        self,
        closure: list[str],
        attribute: str,
        fa: str,
        frame: str,
        valid_as_of: float | None,
        asserted_as_of: int | None,
    ) -> FoldResult:
        """Fold one attribute over a fixed set of subject ids (the entity's
        `same_as` closure for `fold_key`; the union of correlated facets'
        closures for `state_union`). Identical fold semantics either way — so a
        correlated-union read returns exactly what the normal fold would have
        served had the rows been authored on one closure (AKA-CORRELATION-V1 §3,
        the retrieval-invariance invariant)."""
        attrs = sorted(self._semantics.containment_family()) if fa == _FAMILY_KEY else [attribute]
        candidates: list[Assertion] = []
        for row in self._buffer.visible(
            entity_in=closure, attribute_in=attrs,
            frame=frame, valid_as_of=valid_as_of, asserted_as_of=asserted_as_of,
        ):
            # Events never fold (EVENTS-ONE-READER-V1 §4 Rule A): an event row
            # is dropped by its structure, classified or not — an unclassified
            # row reads STATE, so a test of the class alone let it fold until a
            # sweep — and so is every other row the classifier made EVENT.
            if is_event_row(row) or self._classifier.durability(row.id) == EVENT:
                continue
            candidates.append(row)
        if not candidates:
            return FoldResult(winner=None)

        # Accrue reads raw numeric literal/delta rows (it filters to numbers
        # internally and ignores unresolved/thunk machinery), so it branches
        # before the thunk filter. Deltas are STATE by guardrail, never EVENT,
        # and never event rows, so the gather-loop drop above leaves the ledger
        # intact — an accrue ledger on an event still folds.
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
        # on a key, its unresolved placeholder no longer competes either. A
        # marker spends the thunk only with the resolver's own mark, status
        # `generated` (GATE-AUTHORITY-V1 §1).
        spent = MECHANISM_STATUS["resolved_by"]
        candidates = [
            r
            for r in candidates
            if r.value_type != "unresolved"
            or not any(
                m.status == spent
                for m in self._buffer.visible(
                    entity=r.id, attribute="resolved_by",
                    asserted_as_of=asserted_as_of,
                )
            )
        ]
        if any(r.value_type != "unresolved" for r in candidates):
            candidates = [r for r in candidates if r.value_type != "unresolved"]
        if not candidates:
            return FoldResult(winner=None)

        if self._semantics.is_set_valued(attribute):
            return self._fold_set_valued(candidates)
        if self._semantics.is_last_write(attribute):
            return self._fold_last_write(candidates)

        constitutive: list[Assertion] = []
        standing: list[Assertion] = []   # STATE ∪ DISPOSITIONAL, in log order
        for row in candidates:
            durability = self._classifier.durability(row.id)
            if durability == CONSTITUTIVE:
                constitutive.append(row)
            elif durability in (STATE, DISPOSITIONAL):
                standing.append(row)

        # CONSTITUTIVE outranks: structure is never superseded by recency.
        if constitutive:
            # FOLD-CORRECTNESS-V1 §4: evidence rank first, as in every class —
            # a later stated `kind` overrides an earlier inferred one (the
            # earliest row used to serve whatever its evidence). Within the top
            # rank, structure still outranks recency: the earliest serves.
            rows = self._top_evidence(constitutive)
            # Identity-aware value identity (Cx 065): entity-valued CONSTITUTIVE
            # rows that point to a later-MERGED whole are NOT a conflict — resolve
            # before comparing, so a `part_of` (or place containment) edge to
            # h1/h1_alias collapses once they are same_as. Literals compare raw.
            values = {self._value_key(r) for r in rows}
            earliest = min(rows, key=lambda r: r.asserted_at)
            if len(values) > 1:
                return FoldResult(
                    winner=earliest,
                    conflicted=True,
                    conflicting=tuple(r.id for r in rows),
                )
            return FoldResult(winner=earliest)

        if standing:
            # FOLD-CORRECTNESS-V1 §4: STATE and DISPOSITIONAL fold together
            # through one rank, source-class and recency machinery. The old
            # DISPOSITIONAL branch skipped rank and §7.2 (a later inferred habit
            # replaced a stated one; two sources disagreeing never flagged), and
            # any STATE row on the key hid every DISPOSITIONAL one whatever the
            # times. A timeless habit still yields to a timed STATE row of its
            # class (None sorts first); a timed one now competes on recency.
            return self._fold_state(
                standing, asserted_as_of, is_containment=(fa == _FAMILY_KEY)
            )
        return FoldResult(winner=None)

    def state_union(
        self,
        entity: str,
        attribute: str,
        frame: str = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> FoldResult:
        """The explicit, opt-in correlated read (AKA-CORRELATION-V1 §3): fold one
        attribute over the union of subject rows across the entity's `aka`
        correlation set (each facet expanded through its own `same_as` closure),
        as-of. With no visible `aka` edge the correlation set is just the entity,
        so this is byte-for-byte `fold_key`. NEVER consulted by any default read;
        nothing stored. The reveal is valid-time-gated: as-of-before the reveal,
        the correlation set is the lone entity → the pre-reveal (uncorrelated)
        view, never leaking the post-reveal identity."""
        cset = self._correlation_of(
            entity, valid_as_of=valid_as_of, asserted_as_of=asserted_as_of, frame=frame
        )
        union: set[str] = set()
        for facet in cset:
            union |= self._closure_of(facet)
        fa = self.fold_attribute(attribute)
        return self._fold_over_closure(
            sorted(union), attribute, fa, frame, valid_as_of, asserted_as_of
        )

    def confidence(
        self,
        entity: str,
        attribute: str,
        frame: str | list[str] = CANON,
        as_of: float | None = None,
        asserted_as_of: int | None = None,
        now: float | None = None,
    ) -> dict:
        """Derived trust score for one functional folded key.

        CONFIDENCE-V1 is compute-only: it reads the visible closure and the
        functional fold, writes nothing, and returns ``None`` fields for
        absent, set-valued, or accrue keys.

        ``frame`` may be a list of frames (CONFIDENCE-MULTIFRAME-V1): trust
        over an observer's *effective* knowledge = the read-union of those
        frames (``knows:O ∪ public``), mirroring multi-frame ``frame_diff``.
        A deduped single-frame list reduces to the str path byte-for-byte.

        Identity closure is computed at current head (consistent with
        ``fold_key``/``current_state`` engine-wide), so under ``asserted_as_of``
        a later merge can change a historical confidence read — a known,
        shared limitation, not a confidence-specific one.
        """
        if not isinstance(frame, str):
            return self._confidence_multiframe(
                entity, attribute, list(frame), as_of, asserted_as_of, now
            )
        entity = self._resolve(entity)
        if self._semantics.is_set_valued(attribute) or self._semantics.is_accrue(attribute):
            return self._empty_confidence()

        fold = self.fold_key(
            entity,
            attribute,
            frame=frame,
            valid_as_of=as_of,
            asserted_as_of=asserted_as_of,
        )
        winner = fold.winner
        if winner is None:
            return self._empty_confidence()

        params = CONFIDENCE_PARAMS
        provenance = params["provenance"].get(winner.status, 0.0)
        if winner.confidence is not None:
            # Clamp the source-confidence field to [0,1] before flooring — the
            # gate accepts any float, and a garbage negative must not zero a
            # stated fact (post-impl review).
            provenance = min(provenance, max(0.0, min(1.0, winner.confidence)))

        # TRACKING-MODE-V1: the recency component. Non-tracking = permanent
        # (the fiction anti-decay amendment — story-time decay removed from
        # trust; liveness is salience's axis). Tracking = wall-clock age under
        # the declared DecayPolicy, with the fail-closed null branches.
        recency, recency_status, confirmed_at = self._time_trust(
            winner, entity, attribute, [frame], as_of, asserted_as_of, now
        )

        source_classes = {self.source_class(winner, asserted_as_of)}
        for assertion_id in fold.corroborated_by:
            row = self._buffer.get(assertion_id)
            if row is not None:
                source_classes.add(self.source_class(row, asserted_as_of))
        for row in self._visible_key_rows(
            entity,
            attribute,
            frame=frame,
            valid_as_of=as_of,
            asserted_as_of=asserted_as_of,
        ):
            if self._confidence_values_equivalent(row, winner):
                source_classes.add(self.source_class(row, asserted_as_of))

        corroboration = max(0, len(source_classes) - 1)
        corroboration_score = (
            math.log1p(corroboration) / math.log1p(params["corroboration_scale"])
        )

        weights = params["weights"]
        if recency is None:
            # unconfigured/unconfirmed: the recency term is EXCLUDED and its
            # weight renormalized over the remaining components (fail-closed).
            denom = weights["provenance"] + weights["corroboration"]
            score = (
                weights["provenance"] * provenance
                + weights["corroboration"] * corroboration_score
            ) / denom
        else:
            score = (
                weights["provenance"] * provenance
                + weights["recency"] * recency
                + weights["corroboration"] * corroboration_score
            )
        if fold.conflicted:
            score *= 0.5
        score = min(1.0, max(0.0, score))
        return {
            "score": score,
            "status": winner.status,
            "last_observed_at": winner.valid_from,
            "corroboration": corroboration,
            "conflicted": fold.conflicted,
            "recency": recency,
            "recency_status": recency_status,
            "last_confirmed_at_wallclock": confirmed_at,
        }

    def _confidence_multiframe(
        self,
        entity: str,
        attribute: str,
        frames: list[str],
        as_of: float | None,
        asserted_as_of: int | None,
        now: float | None = None,
    ) -> dict:
        """Confidence over the read-union of `frames` (CONFIDENCE-MULTIFRAME-V1).

        The effective winner is the most-recent across the per-frame folds;
        conflict is any per-frame conflict OR a cross-frame value
        disagreement; corroboration unions each fold's V1 source classes with
        the strict cross-frame scan. Derived, writes nothing (the membrane)."""
        # Dedup preserving order; a single distinct frame delegates to the str
        # path so the reduction invariant is byte-identical (Codex r1).
        ordered: list[str] = []
        seen: set[str] = set()
        for f in frames:
            if f not in seen:
                seen.add(f)
                ordered.append(f)
        if not ordered:
            # An empty frame list names no knowledge — empty, never a canon
            # read (Codex post-impl finding 1).
            return self._empty_confidence()
        if len(ordered) == 1:
            # Reduction: a single distinct frame is byte-identical to the str
            # path (and inherits its full V1 corroboration recovery).
            return self.confidence(entity, attribute, ordered[0], as_of,
                                   asserted_as_of, now)

        entity = self._resolve(entity)
        if self._semantics.is_set_valued(attribute) or self._semantics.is_accrue(attribute):
            return self._empty_confidence()

        folds: list[tuple[str, FoldResult]] = []
        for f in ordered:
            fold = self.fold_key(
                entity, attribute, frame=f, valid_as_of=as_of, asserted_as_of=asserted_as_of
            )
            if fold.winner is not None:
                folds.append((f, fold))
        if not folds:
            return self._empty_confidence()

        winner = max(folds, key=lambda ff: self.recency_key(ff[1].winner))[1].winner

        # Conflict: any per-frame conflict, or two frames' winners disagree
        # (strict, entity-resolved — the effective belief is contested).
        conflicted = any(fold.conflicted for _, fold in folds)
        if not conflicted:
            for i in range(len(folds)):
                if conflicted:
                    break
                for j in range(i + 1, len(folds)):
                    if not self._confidence_values_equivalent(
                        folds[i][1].winner, folds[j][1].winner
                    ):
                        conflicted = True
                        break

        params = CONFIDENCE_PARAMS
        provenance = params["provenance"].get(winner.status, 0.0)
        if winner.confidence is not None:
            provenance = min(provenance, max(0.0, min(1.0, winner.confidence)))

        # TRACKING-MODE-V1: same frozen branches as the single-frame path —
        # one payload shape, the stamp taken per the EFFECTIVE winner over the
        # frame union.
        recency, recency_status, confirmed_at = self._time_trust(
            winner, entity, attribute, ordered, as_of, asserted_as_of, now
        )

        # Corroboration: distinct source classes attesting the EFFECTIVE served
        # value (Codex post-impl finding 2). Counting sources that back a
        # *different* per-frame value would inflate trust in a contested value;
        # those are conflict, not corroboration. This is the strict cross-frame
        # scan against the effective winner (recovers every agreeing frame's
        # incumbents — V1's recovery) unioned with the V1 loose-refinement
        # `corroborated_by` of only the folds that serve the effective value.
        # A per-call memo collapses source_class's repeated visible() reads.
        sc_memo: dict[str, str] = {}

        def source_class(row: Assertion) -> str:
            cached = sc_memo.get(row.id)
            if cached is None:
                cached = self.source_class(row, asserted_as_of)
                sc_memo[row.id] = cached
            return cached

        source_classes: set[str] = set()
        for f in ordered:
            for row in self._visible_key_rows(
                entity, attribute, frame=f, valid_as_of=as_of, asserted_as_of=asserted_as_of
            ):
                if self._confidence_values_equivalent(row, winner):
                    source_classes.add(source_class(row))
        for _, fold in folds:
            if not self._confidence_values_equivalent(fold.winner, winner):
                continue  # this frame serves a different value — not corroboration
            source_classes.add(source_class(fold.winner))
            for assertion_id in fold.corroborated_by:
                row = self._buffer.get(assertion_id)
                if row is not None:
                    source_classes.add(source_class(row))
        corroboration = max(0, len(source_classes) - 1)
        corroboration_score = (
            math.log1p(corroboration) / math.log1p(params["corroboration_scale"])
        )

        weights = params["weights"]
        if recency is None:
            denom = weights["provenance"] + weights["corroboration"]
            score = (
                weights["provenance"] * provenance
                + weights["corroboration"] * corroboration_score
            ) / denom
        else:
            score = (
                weights["provenance"] * provenance
                + weights["recency"] * recency
                + weights["corroboration"] * corroboration_score
            )
        if conflicted:
            score *= 0.5
        score = min(1.0, max(0.0, score))
        return {
            "score": score,
            "status": winner.status,
            "last_observed_at": winner.valid_from,
            "corroboration": corroboration,
            "conflicted": conflicted,
            "recency": recency,
            "recency_status": recency_status,
            "last_confirmed_at_wallclock": confirmed_at,
        }

    def _fold_accrue(self, rows: list[Assertion]) -> FoldResult:
        """Accrue quantities: latest absolute numeric baseline plus later
        signed numeric deltas. The ledger is provenance-only; the derived
        quantity is surfaced separately from stored facts."""
        recency = self.recency_key
        literals = [
            r for r in rows
            if r.value_type == "literal" and self._is_numeric(r.value)
        ]
        deltas = [
            r for r in rows
            if r.value_type == "delta" and self._is_numeric(r.value)
        ]
        baseline = max(literals, key=recency) if literals else None
        baseline_value: int | float | Decimal = baseline.value if baseline is not None else 0
        baseline_key = recency(baseline) if baseline is not None else None
        contributing = [
            r for r in deltas if baseline_key is None or recency(r) > baseline_key
        ]
        contributing.sort(key=recency)
        if baseline is None and not contributing:
            return FoldResult(winner=None)
        # Any-Decimal ledger folds exactly under MONEY_CTX; a Decimal/float
        # mix raises with the offending rows (EXACT-DECIMAL-QUANTITIES-V1).
        # The non-Decimal path keeps the pre-change expression VERBATIM —
        # float addition is non-associative, so re-grouping the same values
        # would break byte-identity for existing float worlds.
        ledger_ids = ([baseline.id] if baseline is not None else []) + [
            r.id for r in contributing
        ]
        ledger_values = [baseline_value] + [r.value for r in contributing]
        check_no_mix(ledger_values, ids=ledger_ids)
        if any(isinstance(v, Decimal) for v in ledger_values):
            total = exact_sum(ledger_values, ids=ledger_ids)
        else:
            total = baseline_value + sum(r.value for r in contributing)
        winner = contributing[-1] if contributing else baseline
        ledger_rows = ((baseline,) if baseline is not None else ()) + tuple(contributing)
        return FoldResult(
            winner=winner,
            quantity=total,
            _ledger_rows=ledger_rows,
        )

    def _fold_last_write(self, rows: list[Assertion]) -> FoldResult:
        """A declared `fold_policy: last_write` key (READ-SURFACE-V1 §2): the
        row with the greatest recency key (`recency_key`) among the rows of
        the top evidence rank, whatever their durability. Never conflicted,
        and source classes take no part (no §7.2 flag): last_write is about
        time, not trust. Rank stays, so a later `inferred` or `assumed` row
        never displaces a `stated` one (P5's assumption quarantine). The
        pre-fold filters (EVENT, delta, spent and superseded thunks) have
        already run."""
        return FoldResult(winner=max(self._top_evidence(rows), key=self.recency_key))

    def _fold_set_valued(self, rows: list[Assertion]) -> FoldResult:
        """Set-valued keys accumulate current members instead of conflicting.

        Duplicate assertions for the same member supersede within that
        member's own (entity, attribute, value-identity) key. The served
        winner remains the most-recent current member for compatibility.
        """
        recency = self.recency_key

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
        """STATE ∪ DISPOSITIONAL (FOLD-CORRECTNESS-V1 §4): the top evidence
        rank only; recency wins within a source class; across classes,
        agreement corroborates (serve the more precise value), disagreement
        flags and keeps serving the prior in-class winner (spec §7).

        ``is_containment`` (HD 002 finding 2): for the containment/movement
        family, relocation is inherently time-sequential — a later move
        supersedes an earlier placement across source classes, instead of
        raising the §7.2 cross-source flag. A genuine same-valid-time
        cross-source disagreement still flags. A class's same-time tie is a
        contradiction only while it is the latest word: a later move from
        any class supersedes it (FOLD-CORRECTNESS-V1 §3)."""
        rows = self._top_evidence(rows)

        by_source: dict[str, list[Assertion]] = {}
        for r in rows:
            by_source.setdefault(self.source_class(r, asserted_as_of), []).append(r)

        if is_containment:
            # Movement is time-sequential: the latest-valid move supersedes
            # earlier placements across source classes (HD 002 finding 2).
            # FOLD-CORRECTNESS-V1 §3: every class contributes the rows at its
            # OWN latest valid_from (one row, or a tied set) and only rows at
            # the overall latest one are current. A class's same-time tie used
            # to return before the other classes were heard, so one gossip
            # line placing p in two rooms at t=1 outvoted every later narrated
            # move. Only a disagreement AMONG the current rows contradicts —
            # serve earliest-asserted, flag them all. With one class this is
            # exactly the in-class tie rule below.
            contributed: list[Assertion] = []
            for rs in by_source.values():
                latest = max(rs, key=self.recency_key)
                contributed += [r for r in rs if r.valid_from == latest.valid_from]
            top = max(contributed, key=self.recency_key)
            current = sorted(
                (r for r in contributed if r.valid_from == top.valid_from),
                key=lambda r: r.asserted_at,
            )
            # At one instant a STATE row is "right now" and a habit stamped
            # with it is "tends to" — not a contradiction (whitepaper §5/§14):
            # STATE outranks, and only STATE rows can contradict each other
            # (pre-review finding 2).
            state_now = [r for r in current
                         if self._classifier.durability(r.id) == STATE]
            if state_now:
                current = state_now
                if len({self._value_key(r) for r in current}) > 1:
                    return FoldResult(
                        winner=current[0],
                        conflicted=True,
                        conflicting=tuple(r.id for r in current),
                    )
            return FoldResult(winner=current[-1])

        winners: dict[str, Assertion] = {}
        for sc, rs in by_source.items():
            top = max(rs, key=self.recency_key)
            # Supersession requires world-time progression: rows tied at the
            # winner's valid_from with a DIFFERENT value are a simultaneous
            # contradiction, not an update — flag, serve earliest-asserted
            # (run-4 finding: log order alone must never pick a truth). Values
            # compare by identity (FOLD-CORRECTNESS-V1 §2), never raw text.
            # Outside the containment family this still ends the fold: across
            # classes such a key flags under §7.2 anyway (§3's non-goal).
            tied = [r for r in rs if r.valid_from == top.valid_from]
            # A STATE row outranks a habit stamped with it, and habits tied at
            # one instant coexist (an NPC's drives) — only STATE rows tied
            # with different values contradict (pre-review finding 2).
            state_tied = [r for r in tied
                          if self._classifier.durability(r.id) == STATE]
            if state_tied:
                tied = state_tied
                top = max(tied, key=self.recency_key)
            if state_tied and len({self._value_key(r) for r in tied}) > 1:
                earliest = min(tied, key=lambda r: r.asserted_at)
                return FoldResult(
                    winner=earliest,
                    conflicted=True,
                    conflicting=tuple(r.id for r in tied),
                )
            winners[sc] = top
        if len(winners) == 1:
            return FoldResult(winner=next(iter(winners.values())))

        # Multiple source classes on one key: order in-class winners by
        # arrival; the earliest-arrived class is the incumbent.
        ordered = sorted(winners.values(), key=lambda r: r.asserted_at)
        incumbent, rest = ordered[0], ordered[1:]
        serving = incumbent
        corroborations: list[str] = []
        for challenger in rest:
            if self._values_agree(serving, challenger):
                corroborations.append(challenger.id)
                serving = challenger  # the refinement is the more precise value
        # SOURCE-IDENTITY-V1 r2 (pbr): the parties are recomputed against the
        # FINAL serving value, never anchored to the incumbent. `serving`
        # advances on refinement, so an incumbent that agreed with everything
        # could still be reported as a conflicting party while the rows that
        # actually disagree went unnamed: with a={gte:10}, b=12, c=13 the fold
        # served b and reported conflicting={a,c} — a pair that AGREES — while
        # the real incompatibility was b↔c. TruthMaintenance.scan() persisted
        # the same wrong pair, so the durable cross_source sidecar (and any
        # host ask built on it) named the wrong evidence. Document splitting
        # makes this ordinary three-document shape newly reachable.
        # Compatibility is SYMMETRIC, unlike `_values_agree(old, new)`, which
        # asks the directional question "does `new` refine `old`?" — so
        # `_values_agree({gte:10}, 12)` holds while `_values_agree(12, {gte:10})`
        # does not. Asking it one way round here would report an approximate
        # row that the served exact value satisfies as a conflicting party.
        def compatible(a: Assertion, b: Assertion) -> bool:
            return self._values_agree(a, b) or self._values_agree(b, a)

        # `corroborated_by` keeps its existing meaning EXACTLY — the challengers
        # that agreed as the fold advanced (test_fold.py::TestCrossSource::
        # test_agreeing_value_corroborates pins it). pbr's finding was about
        # `conflicting` naming the wrong parties; widening it to redefine
        # corroboration too would be an unasked contract change, so only the
        # conflict parties are recomputed here.
        disagreeing = [
            w.id for w in ordered
            if w.id != serving.id and not compatible(serving, w)
        ]
        if disagreeing:
            return FoldResult(
                winner=serving,
                conflicted=True,
                # The serving row is itself a party to the disagreement.
                conflicting=tuple([serving.id, *disagreeing]),
                corroborated_by=tuple(corroborations),
            )
        return FoldResult(winner=serving, corroborated_by=tuple(corroborations))

    def current_state(
        self,
        entity: str,
        frame: str = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
        correlated: bool = False,
    ) -> dict[str, FoldResult]:
        """All folded keys for one entity (attribute -> result). The
        containment family is ONE key, named `in` (FOLD-CORRECTNESS-V1 §7).

        ``correlated=True`` (AWARENESS-READS-V1.1): discover keys over the
        entity's `aka` correlation union and fold each via `state_union` instead
        of the bare closure — the projection-level form of `state_union`. Opt-in;
        the META filter is preserved either way so `aka`/identity never leak."""
        entity = self._resolve(entity)
        if correlated:
            keyset: set[str] = set()
            for member in self._correlation_of(
                entity, valid_as_of=valid_as_of,
                asserted_as_of=asserted_as_of, frame=frame,
            ):
                keyset |= self._closure_of(member)
            closure = sorted(keyset)
        else:
            closure = sorted(self._closure_of(entity))
        attrs: set[str] = set()
        for row in self._buffer.visible(
            entity_in=closure,
            frame=frame, valid_as_of=valid_as_of, asserted_as_of=asserted_as_of,
        ):
            if row.entity.startswith("a:") or row.entity.startswith(ATTR_PREFIX):
                continue
            if row.attribute in META_ATTRIBUTES:
                continue  # identity/meta edges (same_as, distinct_from, …) are
                          # machinery, not materialized facts (membrane)
            attrs.add(row.attribute)
        out: dict[str, FoldResult] = {}
        for attr in attrs:
            result = (self.state_union(entity, attr, frame, valid_as_of, asserted_as_of)
                      if correlated
                      else self.fold_key(entity, attr, frame, valid_as_of, asserted_as_of))
            if result.winner is not None:
                # FOLD-CORRECTNESS-V1 §7: `__containment__` is an internal fold
                # key; at the read boundary the family is named `in` (its
                # public subject, as decay's `attr:in` already reads it).
                fa = self.fold_attribute(attr)
                out[_FAMILY_NAME if fa == _FAMILY_KEY else fa] = result
        return out
