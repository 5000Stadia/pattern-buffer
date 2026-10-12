"""Indexes core: the wiring (providers injected by World), the shared
helpers every section leans on (source class, recency order, evidence rank,
value identity, confidence building blocks), and the key-row access. The
sections are mixins over this core; `Indexes` (the package `__init__`) is
the one class they make up. Holds no durable state of its own (P2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import Classifier
from patternbuffer.decay import DecayPolicy
from patternbuffer.model import CANON, MECHANISM_STATUS, Assertion
from patternbuffer.semantics import AttributeSemantics

_FAMILY_KEY = "__containment__"
# Evidence rank (the assumption quarantine, generalized): provisional classes
# never hold incumbency against authoritative ones — an authored/observed fact
# arriving over a character's inference or a working assumption is
# confirmation or correction, never a conflict to ask about. Peers ({stated,
# observed}) keep the full corroborate-vs-flag machinery. (Found by
# chapter-test run 3: a narrator's wrong `inferred` theory outheld later
# `stated` canon.) Governs every durability class (FOLD-CORRECTNESS-V1 §4).
_EVIDENCE_RANK = {"stated": 3, "observed": 3, "generated": 2, "inferred": 1, "assumed": 0}


@dataclass(frozen=True, slots=True)
class FoldResult:
    """What the fold serves for one key."""

    winner: Assertion | None
    conflicted: bool = False
    conflicting: tuple[str, ...] = ()  # assertion ids party to the conflict
    corroborated_by: tuple[str, ...] = ()
    values: tuple = ()
    _value_rows: tuple[Assertion, ...] = field(default=(), repr=False, compare=False)
    quantity: int | float | Decimal | None = None
    _ledger_rows: tuple[Assertion, ...] = field(default=(), repr=False, compare=False)


class IndexesCore:
    """Wiring, caches and shared helpers for the sections of `Indexes`."""

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
        # AKA-CORRELATION-V1: the non-collapsing correlation set (aka-component),
        # injected by World from the registry. Default => just the entity, so
        # state_union with no aka edges is identical to fold_key.
        self._correlation_of = (
            lambda eid, valid_as_of=None, asserted_as_of=None, frame=CANON: {eid}
        )
        self._salience = lambda eid, frame=CANON, as_of=None: 0.0
        # TRACKING-MODE-V1: time physics. `_tracking` selects on
        # policy == "observe_or_unknown" ONLY (never stance — the no-bias
        # invariant); `_clock` is the World's injected wall clock; `_decay`
        # reads declared half-lives fresh at each read (rebuildable).
        self._tracking = False
        self._clock: Callable[[], float] = lambda: 0.0
        self._decay = DecayPolicy(buffer, self._semantics)

    def set_time_physics(self, tracking: bool, clock: Callable[[], float]) -> None:
        """World wiring (TRACKING-MODE-V1): tracking = the operational selector
        (`policy == "observe_or_unknown"`); clock = the injected wall clock."""
        self._tracking = tracking
        self._clock = clock

    def set_identity_resolver(self, fn: Callable[[str], str]) -> None:
        self._resolve = fn

    def set_closure_provider(self, fn: Callable[[str], set]) -> None:
        """Identity-closure lookup for indexed (read-path) retrieval —
        installed by World wiring alongside the resolver (037)."""
        self._closure_of = fn

    def set_correlation_provider(self, fn: Callable[..., set]) -> None:
        """`aka`-correlation-set lookup (AKA-CORRELATION-V1) — installed by World
        wiring from the registry's correlation_set. Read only by state_union."""
        self._correlation_of = fn

    def closure_of(self, entity: str) -> set:
        """The identity closure of `entity`: every id merged with it, itself
        included (the lookup World installs with `set_closure_provider`)."""
        return self._closure_of(entity)

    def set_salience_provider(
        self, fn: Callable[[str, str, float | None], float]
    ) -> None:
        self._salience = fn

    def resolve_entity(self, entity: str) -> str:
        """The identity closure's canonical representative for `entity`."""
        return self._resolve(entity)

    def fold_attribute(self, attribute: str) -> str:
        """World-bound fold-key attribute, including declared semantics."""
        return _FAMILY_KEY if self._semantics.is_containment(attribute) else attribute

    # -------------------------------------------------------------- helpers

    def source_class(self, row: Assertion, asserted_as_of: int | None) -> str:
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
        # SOURCE-IDENTITY-V1: a source class is a SOURCE, not a category. The
        # class carries the document's identity exactly as it carries the
        # speaker's — "a speaker is a document that talks" cuts both ways, and
        # only the talking one had kept its name. Collapsing every `doc:` to a
        # bare "document" made two distinct documents one supersession class,
        # so a cross-document disagreement silently last-write-wins instead of
        # raising §7.2's flag (the whitepaper's own supply-house example), and
        # N independently agreeing documents scored zero corroboration.
        #
        # Collected over the WHOLE meta set, never first-match: a row carrying
        # several sources must classify the same way regardless of the order
        # `visible()` returns them. `doc:` outranks `person:` because §7.1's
        # chain is two-hop — the document is the outer evidentiary artifact and
        # a person named beside it is the attributed voice within it.
        #
        # r2 (pbr): two further pins, both load-bearing.
        #
        # 1. IDs are canonicalized through the identity closure. Raw source
        #    strings are not source *identities*: write `doc:manual` and
        #    `doc:manual_alias`, merge them afterwards, and un-canonicalized
        #    classes stay distinct — one logical document then self-corroborates
        #    (corroboration=1 for a single source) and can false-flag on
        #    disagreement. Current-head closure, consistent with the engine's
        #    known historical-identity limitation.
        # 2. The class is the COMPOSITE of every source of the winning kind,
        #    not one selected member. Selecting `min()` made evidentiary
        #    identity depend on label spelling: two rows sharing one common
        #    document silently superseded when that shared id sorted first and
        #    conflicted when it sorted last — identical provenance topology,
        #    opposite outcome, decided alphabetically. A set of attesters is
        #    its own identity; sorting only canonicalizes the rendering.
        docs: set[str] = set()
        speakers: set[str] = set()
        for m in metas:
            if not isinstance(m.value, str):
                continue
            if m.value.startswith("doc:"):
                docs.add(self._resolve(m.value))
            elif m.value.startswith("person:"):
                speakers.add(self._resolve(m.value))
        if docs:
            return "document:" + "|".join(sorted(docs))
        if speakers:
            # Speaker-source class (027 Decision 2): a speaker is a
            # document that talks — same speaker supersedes self,
            # speakers disagreeing cross-source flag + ask (§7.2).
            return "speaker:" + "|".join(sorted(speakers))
        # stated and observed without a document chain are ONE supersession
        # class: both are rank-3 authoritative, and ordinary narrative
        # movement must supersede across them (run-4 finding: the §7.1
        # boundary is document-vs-direct, not stated-vs-observed).
        # NOTE: this pooling is the undeclared-origin case — deliberately
        # unchanged here and recorded as a founder crossroads in
        # SOURCE-IDENTITY-V1 §6, not an oversight.
        return "direct"

    _source_class = source_class  # the name before R21; kept as an alias

    @staticmethod
    def recency_key(row: Assertion) -> tuple[float, int]:
        """The one recency order every fold and pick uses (FOLD-CORRECTNESS-V1
        §1): valid time, then log order; a timeless row sorts before every
        timed one. `0.0` IS a time — the scene cursor starts there — so the
        old `valid_from or -inf` spelling read the commonest stamp as "no
        time" and let a flashback at −10 outrank the present."""
        return (
            row.valid_from if row.valid_from is not None else float("-inf"),
            row.asserted_at,
        )

    _recency_key = recency_key  # the name before R21; kept as an alias

    @staticmethod
    def _top_evidence(rows: list[Assertion]) -> list[Assertion]:
        """The rows at the best evidence rank present (`_EVIDENCE_RANK`), in
        their given order — the first filter of every durability class's fold
        (FOLD-CORRECTNESS-V1 §4)."""
        top = max(_EVIDENCE_RANK.get(r.status, 0) for r in rows)
        return [r for r in rows if _EVIDENCE_RANK.get(r.status, 0) == top]

    def _value_key(self, row: Assertion) -> tuple[str, object]:
        """The one value identity every tie test compares (FOLD-CORRECTNESS-V1
        §2) — the CONSTITUTIVE comparator (Cx 065), lifted: an entity value
        is its resolved identity, so two rows naming one later-merged thing
        are one value; anything else compares by its exact repr."""
        if row.value_type == "entity" and isinstance(row.value, str):
            return ("entity", self._resolve(row.value))
        return ("literal", repr(row.value))

    def _values_agree(self, old: Assertion, new: Assertion) -> bool:
        """Does `new` agree with `old` — the cross-source corroboration test.
        Two entity-valued rows agree iff they name one identity
        (FOLD-CORRECTNESS-V1 §2: once merged, `obj:purse` and `obj:pouch` are
        one value, not a disagreement); otherwise it stays directional on the
        literal values (`_refines`)."""
        if (old.value_type == "entity" and new.value_type == "entity"
                and isinstance(old.value, str) and isinstance(new.value, str)):
            return self._resolve(old.value) == self._resolve(new.value)
        return self._refines(old.value, new.value)

    @staticmethod
    def _refines(old: object, new: object) -> bool:
        """Equal, or `new` refines an explicitly approximate `old`
        ({'gte': x} / {'lte': x} / {'approx': x}) — spec §7. When `new` is
        an exact Decimal, bounds coerce via Decimal(str(...)) for the
        comparison only — a read-time judgment, never a stored sum."""
        if old == new:
            return True
        if isinstance(old, dict) and isinstance(new, (int, float, Decimal)):
            if "gte" in old and new >= old["gte"]:
                return True
            if "lte" in old and new <= old["lte"]:
                return True
            if "approx" in old:
                approx = old["approx"]
                if isinstance(new, Decimal) and isinstance(approx, (int, float)):
                    approx = Decimal(str(approx))
                    return abs(new - approx) <= Decimal("0.1") * abs(approx)
                if isinstance(new, (int, float)) and isinstance(approx, Decimal):
                    new = Decimal(str(new))
                    return abs(new - approx) <= Decimal("0.1") * abs(approx)
                if abs(new - approx) <= 0.1 * abs(approx):
                    return True
        return False

    @staticmethod
    def _is_numeric(value: object) -> bool:
        return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)

    def is_event_effect(self, row: Assertion, asserted_as_of: int | None) -> bool:
        """True iff the row carries a caused_by edge to an EVENT (spec §9.1)."""
        return bool(
            self._buffer.visible(
                entity=row.id, attribute="caused_by", asserted_as_of=asserted_as_of
            )
        )

    _is_event_effect = is_event_effect  # the name before R21; kept as an alias

    @staticmethod
    def _empty_confidence() -> dict:
        return {
            "score": None,
            "status": None,
            "last_observed_at": None,
            "corroboration": 0,
            "conflicted": False,
            # TRACKING-MODE-V1: one payload shape everywhere — the three
            # additive fields are present (null) on empty/set-valued/accrue.
            "recency": None,
            "recency_status": None,
            "last_confirmed_at_wallclock": None,
        }

    def _time_trust(
        self,
        winner: Assertion,
        entity: str,
        attribute: str,
        frames: list[str],
        as_of: float | None,
        asserted_as_of: int | None,
        now: float | None,
    ) -> tuple[float | None, str, float | None]:
        """(recency, recency_status, last_confirmed_at_wallclock) —
        TRACKING-MODE-V1's frozen branches.

        Non-tracking (invent_under_canon / deny): ("permanent", 1.0, None) —
        the page is true; story-time recency is salience's business (liveness),
        never trust's. Tracking: recency = 2**(−age/half_life) with
        age = max(0, now − stamp); "unconfigured"/"unconfirmed" return
        recency=None (excluded + renormalized upstream — fail-closed: neither
        fake permanence nor fake staleness)."""
        if not self._tracking:
            return 1.0, "permanent", None
        # The finite-clock contract (Cx 604 #1), validated FIRST — before any
        # branch can short-circuit: wall time must be a finite real number. A
        # NaN stamp would make max(0, now−NaN) select 0.0 — a broken clock
        # fabricating PERFECT freshness. A non-finite explicit/injected `now`
        # fails loudly on every tracking read; non-finite STORED stamps never
        # qualify as confirmations (enforced in _confirmation_stamp).
        ref_now = float(now) if now is not None else float(self._clock())
        if not math.isfinite(ref_now):
            raise ValueError(
                f"wall-clock 'now' must be finite, got {ref_now!r} "
                "(a broken clock must fail, not fabricate freshness)")
        half_life = self._decay.resolve(winner.attribute)
        if half_life is None:
            return None, "unconfigured", None
        stamp = self._confirmation_stamp(
            winner, entity, attribute, frames, as_of, asserted_as_of
        )
        if stamp is None:
            return None, "unconfirmed", None
        age = max(0.0, ref_now - float(stamp))
        return 2.0 ** (-(age / float(half_life))), "configured", float(stamp)

    def _confirmation_stamp(
        self,
        winner: Assertion,
        entity: str,
        attribute: str,
        frames: list[str],
        as_of: float | None,
        asserted_as_of: int | None,
    ) -> float | None:
        """The latest visible A1 wall stamp among rows that CONFIRM the served
        value: `stated`/`observed` provenance only, strict value-equivalence to
        the winner, frame- and asserted_as_of-respecting (TRACKING-MODE-V1 §B4).
        An assumed/inferred/conflicting/different-value row never refreshes it.
        Fail-closed: a tracking row missing its mandatory stamp contributes no
        confirmation. A stamp counts only with the gate's own mark, status
        `observed` (GATE-AUTHORITY-V1 §1, r2): a `learned_at_wallclock` row
        written under any other status confirms nothing."""
        stamped = MECHANISM_STATUS["learned_at_wallclock"]
        best: float | None = None
        for f in frames:
            for row in self._visible_key_rows(
                entity, attribute, frame=f,
                valid_as_of=as_of, asserted_as_of=asserted_as_of,
            ):
                if row.status not in ("stated", "observed"):
                    continue
                if not self._confidence_values_equivalent(row, winner):
                    continue
                for meta in self._buffer.visible(
                    entity=row.id, attribute="learned_at_wallclock",
                    asserted_as_of=asserted_as_of,
                ):
                    if meta.status != stamped:
                        continue
                    v = meta.value
                    # FINITE only (Cx 604 #1): a NaN/inf stamp must fall to
                    # the honest `unconfirmed` branch, never qualify as a
                    # confirmation (fail-closed).
                    if (isinstance(v, (int, float)) and not isinstance(v, bool)
                            and math.isfinite(v)):
                        if best is None or float(v) > best:
                            best = float(v)
        return best

    def _confidence_values_equivalent(self, left: Assertion, right: Assertion) -> bool:
        # Corroboration is "same value" (post-impl review): STRICT equivalence,
        # not the loose approximate-bounds agreement — a {gte:40} bound must not
        # count as corroborating a precise 42.
        if left.value_type != right.value_type:
            return False
        if left.value_type == "entity" and isinstance(left.value, str) \
                and isinstance(right.value, str):
            return self._resolve(left.value) == self._resolve(right.value)
        return left.value == right.value

    def _visible_key_rows(
        self,
        entity: str,
        attribute: str,
        frame: str,
        valid_as_of: float | None,
        asserted_as_of: int | None,
    ) -> list[Assertion]:
        fa = attribute if attribute == _FAMILY_KEY else self.fold_attribute(attribute)
        attrs = sorted(self._semantics.containment_family()) if fa == _FAMILY_KEY else [attribute]
        return self._buffer.visible(
            entity_in=sorted(self._closure_of(entity)),
            attribute_in=attrs,
            frame=frame,
            valid_as_of=valid_as_of,
            asserted_as_of=asserted_as_of,
        )

    def key_rows(
        self,
        entity: str,
        fold_key: str,
        frame: str = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> list[Assertion]:
        """The visible rows of one fold key (an attribute, or the containment
        family key) over `entity`'s identity closure — an indexed fetch, never
        a whole-log scan."""
        return self._visible_key_rows(entity, fold_key, frame, valid_as_of, asserted_as_of)
