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
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from patternbuffer.codec import decode_value, encode_out
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
    # INGEST-HARDENING-V1 Part B: edges skipped at the gate (cycle / self-edge /
    # lateral self-loop) — the host audits exactly what was dropped (no silent cap).
    skipped: list[dict] = field(default_factory=list)

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
        # BUILD-SESSION-V1 state. The session is a host-workflow concept and
        # lives here (the engine's toggle/classifier don't know it exists).
        # World.porcelain is THE handle — a second manual Porcelain(world) is
        # unsupported (sessions would not see each other).
        self._build_head: int | None = None
        self._build_prev_inline: bool | None = None

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
        quantity: int | float | Decimal,
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
        return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)

    # ------------------------------------------------- BUILD-SESSION-V1

    def begin_build(self, at: float | None = None) -> dict:
        """Enter build mode: every subsequent ingest DEFERS durability
        classification (regardless of per-call `classify=` — the session
        wins); `seal_build` runs one pass at the end. `at` places the scene
        cursor. Raises on double-enter (not a nesting feature)."""
        if self._build_head is not None:
            raise RuntimeError("a build session is already open; seal or abort it")
        ing = self._w.ingestor
        self._build_prev_inline = ing.classify_inline
        ing.classify_inline = False
        self._build_head = self._w.buffer.head()
        if at is not None:
            ing.cursor.advance(at)
        return {"outcome": "build_open", "since_seq": self._build_head,
                "cursor": ing.cursor.position}

    def seal_build(self, model: bool = False, scope: str = "session") -> dict:
        """Finalize the session: one classification pass over its rows
        (already-classified rows — e.g. a per-call `classify="rules"` inside
        the session — are skipped, never re-judged), restore the toggle,
        close the session. `scope="all"` sweeps the whole log instead (the
        classify_all-style pass, for pre-session deferred rows). `model=True`
        sends ambiguous rows to the batch LM call; default is rules-only."""
        if self._build_head is None:
            raise RuntimeError("no build session open")
        if scope not in ("session", "all"):
            raise ValueError(f"unknown seal scope {scope!r}")
        begin = self._build_head
        head = self._w.buffer.head()
        rows = self._w.buffer.all_rows()
        if scope == "session":
            rows = [r for r in rows if r.seq > begin]
        classified = self._w.classifier.classify_rows(rows, model=model)
        self._w.ingestor.classify_inline = self._build_prev_inline
        self._build_head = None
        self._build_prev_inline = None
        return {"outcome": "sealed", "classified": classified,
                "seq_range": [begin + 1, head], "scope": scope}

    def abort_build(self) -> dict:
        """Close an open session WITHOUT classifying (restore the toggle,
        clear the state). Idempotent — `no_session` when none is open. The
        `build()` sugar's exception path and World.close() route through
        this: a half-built world is the host's to inspect; classifying
        wreckage helps nobody."""
        if self._build_head is None:
            return {"outcome": "no_session"}
        self._w.ingestor.classify_inline = self._build_prev_inline
        since = self._build_head
        self._build_head = None
        self._build_prev_inline = None
        return {"outcome": "aborted", "since_seq": since}

    @contextmanager
    def build(self, at: float | None = None, model: bool = False,
              scope: str = "session"):
        """Python sugar over begin_build/seal_build: seals on clean exit,
        aborts (toggle restored, nothing classified) on exception."""
        self.begin_build(at=at)
        try:
            yield self
        except BaseException:
            self.abort_build()
            raise
        else:
            self.seal_build(model=model, scope=scope)

    def fidelity_audit(self, frame: str = CANON, as_of: float | None = None) -> dict:
        """Structural ingestion-fidelity gaps as a queryable checklist
        (INGESTION-FIDELITY-V1): `name_collisions` (distinct ids sharing an
        anchor, each pair annotated with WHY it isn't merged — the coreference-
        fragmentation metric), `unstamped_timed` (classified STATE/EVENT rows off
        the time spine), `orphan_entities` (unanchored obj:/person:),
        `open_conflicts`, and a `summary` with the headline live-fragmentation
        count. Read-only; run after seal + `truth.scan()`. The host joins
        arc/cast severity and drives targeted re-extraction of the flagged
        spans; the engine surfaces, never repairs (membrane)."""
        return encode_out(self._w.fidelity_audit(frame=frame, as_of=as_of))

    def axis_heads(self) -> dict:
        """The two-axis high-water mark of the log (AXIS-HEAD-V1):
        `asserted_head` (the seq head) and `valid_head` (MAX valid_from over
        ALL rows, all frames; None when no timed rows exist). A coordinate
        scalar, never content — no entity/attribute/value/frame crosses. The
        entry-epoch read: a pre-play coordinate must sit above every seeded
        row wherever it landed (a frame-scoped max under-raises)."""
        return {"asserted_head": self._w.buffer.head(),
                "valid_head": self._w.buffer.max_valid_from()}

    # -------------------------------------------------------------- writes

    def extract(self, text: str, scene: str | None = None,
                extract: str = "full", pov: str | None = None) -> list[dict]:
        """Read-only extraction (INGEST-LATENCY-V2): returns the raw item dicts,
        NO write. Run these concurrently in your runtime (your cap), then
        ingest_structured() the results serially. `pov` (SHAPE-FIX-V1 4c): the
        viewpoint entity id — deixis pronouns (I/you) bind to it instead of
        minting phantom persons."""
        context = f"\nSCENE HINT (context only, never a spatial anchor): {scene}" if scene else ""
        return self._w.extract(text, context=context, extract=extract, pov=pov)

    def ingest(self, text: str, source: str | None = None, scene: str | None = None,
               at: float | None = None, frame: str | None = None,
               classify: str = "inline", extract: str = "full",
               cursor_authoritative: bool = False, pov: str | None = None) -> Receipt:
        # classify (HD 079): "batch" collapses ~100 serial per-turn durability
        # calls into one; "rules" (HD 083) does it with zero LM calls; "defer"
        # skips. extract (HD 082): "lean" trims the prompt. cursor_authoritative
        # (HD 084): the cursor governs valid_from (bible source-ingest).
        if at is not None:
            self._w.ingestor.cursor.advance(at)
        context = f"\nSCENE HINT (context only, never a spatial anchor): {scene}" if scene else ""
        rows = self._w.ingest(text, context=context, frame=frame, classify=classify,
                              extract=extract, cursor_authoritative=cursor_authoritative,
                              pov=pov)
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
            ], classify=classify)
        return self._receipt(rows)

    def ingest_structured(self, items: list[dict], frame: str | None = None,
                          classify: str = "inline",
                          cursor_authoritative: bool = False,
                          at: float | None = None) -> Receipt:
        # `at` places the scene cursor before the commit (AXIS-HEAD-V1 Win 2)
        # — the per-chunk pose for parallel-extract/serial-commit paths,
        # mirroring ingest(at=). The porcelain owns the pose; the gate reads it.
        if at is not None:
            self._w.ingestor.cursor.advance(at)
        # frame= is a DEFAULT for unframed items (letter 028) — per-item frames
        # win, which mixed batches (knows:B rows beside canon) require. Make the
        # non-obvious case LOUD, never silent (HD 121: a staging frame silently
        # lost to item-level stamps bypassed a quarantine gate for weeks).
        kept_own = (sum(1 for i in items
                        if isinstance(i, dict) and i.get("frame") not in (None, frame))
                    if frame is not None else 0)
        rows = self._w.ingest_structured(items, frame=frame, classify=classify,
                                         cursor_authoritative=cursor_authoritative)
        receipt = self._receipt(rows)
        if kept_own:
            receipt.warnings.append(
                f"frame={frame!r} filled only unframed items; {kept_own} item(s) "
                "kept their own frame key (frame= is a default, not an override "
                "— strip item frames to re-target wholesale)")
        receipt.skipped = [
            {"entity": s.entity, "attribute": s.attribute,
             "value": encode_out(s.value), "reason": s.reason}
            for s in self._w.ingestor.last_skipped
        ]
        return receipt

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
        return encode_out({"status": "resolved",
                           "facts": [self._fact(r).to_dict() for r in rows],
                           "receipt": self._receipt(rows).to_dict()})

    def retract(self, assertion_id: str, reason: str) -> Receipt:
        return self._receipt([self._w.truth.retract(assertion_id, reason)])

    # --------------------------------------------------- reads (LLM-free)

    def snapshot(self, scope, frame: str = CANON, as_of: float | None = None,
                 lens: str = "current_state", budget: int | None = None,
                 since: float | None = None, correlated: bool = False,
                 features: bool = False) -> dict:
        # correlated/features (AWARENESS-READS-V1.1, opt-in): fold each entity over
        # its aka correlation union (the whole reveal scene) and/or inline each
        # place's part_of-feature children. Default off = unchanged.
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
                                budget=budget, since=since,
                                correlated=correlated, features=features)
        # encode_out at the return: the porcelain's plain-JSON contract —
        # exact-decimal values leave as the tag dict, never a raw Decimal.
        return encode_out({
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
        })

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
        return encode_out(out)

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
        value = decode_value(value)   # tag-form symmetry: {"$decimal": ...} ok
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
        return encode_out(self._w.aggregate(
            container, member_attribute, op,
            frame=frame, as_of=as_of, recursive=recursive,
        ))

    def entities(self, frame: str, prefix: str | None = None,
                 as_of: float | None = None) -> list[str]:
        """The roster read (BOUNDED-READS-V1): entity ids carried by ONE
        frame's rows, identity-resolved, deduped, sorted. `frame` is required —
        every read fixes perspective (a prefix-only enumeration would leak
        cross-frame entity existence). `prefix` narrows by id namespace
        ('place:'); `as_of` is the valid-time gate. Zero writes, no fold."""
        if not frame:
            # visible(frame=None) omits the frame predicate — that would be an
            # unbounded cross-frame scan, exactly what this verb must not be.
            raise ValueError("entities() requires a frame — every read fixes perspective")
        out: set[str] = set()
        for r in self._w.buffer.visible(frame=frame, valid_as_of=as_of):
            if r.entity.startswith("a:") or r.entity.startswith(ATTR_PREFIX):
                continue
            eid = self._w.registry.resolve(r.entity)
            if prefix is None or eid.startswith(prefix):
                out.add(eid)
        return sorted(out)

    def facts(self, frame: str, entity: str | None = None,
              attribute: str | None = None, prefix: str | None = None,
              as_of: float | None = None, include_meta: bool = False) -> list[dict]:
        """The frame-scan read (BOUNDED-READS-V1): the visible rows OF one
        frame as Fact payloads — RAW log reads for audited scans (receipt
        trails, knowledge digests, marker rows), NOT folds (folded truth is
        `state`/`snapshot`). `frame` is required (the bound). `entity` targets
        one id (identity-closure for world entities; exact for `a:<n>` receipt
        chains — always served); frame/prefix-wide listings exclude meta rows
        unless `include_meta=True`."""
        if not frame:
            raise ValueError("facts() requires a frame — every read fixes perspective")
        if entity is not None and not entity.startswith("a:"):
            clos = sorted(self._w.registry.closure(entity))
            rows = self._w.buffer.visible(entity_in=clos, frame=frame,
                                          attribute=attribute, valid_as_of=as_of)
        elif entity is not None:
            rows = self._w.buffer.visible(entity=entity, frame=frame,
                                          attribute=attribute, valid_as_of=as_of)
        else:
            rows = [
                r for r in self._w.buffer.visible(frame=frame, attribute=attribute,
                                                  valid_as_of=as_of)
                if include_meta or (not r.entity.startswith("a:")
                                    and not r.entity.startswith(ATTR_PREFIX))
            ]
        if prefix is not None:
            rows = [r for r in rows
                    if self._w.registry.resolve(r.entity).startswith(prefix)]
        return encode_out([self._fact(r).to_dict() for r in rows])

    def locate(self, entity: str, as_of: float | None = None) -> list[str]:
        return self._w.locate(entity, valid_as_of=as_of)

    def contents(self, container: str, as_of: float | None = None) -> list[str]:
        return self._w.contents(container, valid_as_of=as_of)

    def composition(self, entity: str, frame: str = CANON,
                    as_of: float | None = None) -> list[str]:
        """The `part_of` chain up — the entity's place in the structure
        (PLACE-FEATURE-ABSTRACTION-V1). The compositional sibling of `locate`."""
        return self._w.composition(entity, frame=frame, valid_as_of=as_of)

    def features(self, place: str, frame: str = CANON,
                 as_of: float | None = None) -> list[str]:
        """The `part_of`-children of a place — its structural sub-features
        (a burrow under a hillside). The compositional sibling of `contents`."""
        return self._w.features(place, frame=frame, valid_as_of=as_of)

    def path(self, a: str, b: str, as_of: float | None = None) -> list[str] | None:
        # as_of routes as the graph stood at that time: a severed edge
        # (valid_to passed) drops; history is preserved (PATH-TEMPORAL-V1).
        return self._w.path(a, b, valid_as_of=as_of)

    def route(self, a: str, b: str, frame: str = CANON, as_of: float | None = None) -> dict:
        """Passability-aware route (RFC-003): {route, status, segments}. Status
        per segment is clear|blocked|obscured (removed is temporal/diagnostic);
        blocked carries obstructing-fact evidence, obscured a computed
        unknown_basis. The engine derives status from portal facts under the
        host's declared traversal policy; the host supplies the words."""
        return encode_out(self._w.route(a, b, frame=frame, valid_as_of=as_of))

    # ----------------------------------- host reconciliation (MERGE-RECONCILE-VERB-V1)

    def reconcile(self) -> dict:
        """Run the global coreference finalize pass and return the count
        merged plus the residual proposals to adjudicate. Host-invoked; never
        auto-run by ingest. Zero model calls."""
        merges = self._w.registry.reconcile()
        return {"merges": merges, "proposals": self._w.registry.enumerate_proposals()}

    def proposals(self) -> list[dict]:
        """Visible un-promoted maybe_same_as as adjudicable proposals, each
        with a recomputed `auto_decline_reason` (the kind-pair on conflict)."""
        return self._w.registry.enumerate_proposals()

    def confirm(self, a: str, b: str) -> dict:
        """Promote an existing proposal through the guarded path. Returns a
        Receipt; `no_proposal` if none relates them."""
        return self._w.registry.confirm(a, b)

    def merge(self, a: str, b: str, evidence: str) -> dict:
        """Assert a merge (no proposal required) through the guarded path.
        Host-authoritative past the soft heuristic, but the hard vetoes
        (containment, distinct_from) are absolute (a `vetoed` Receipt names the
        blocking edge)."""
        return self._w.registry.guarded_merge(a, b, evidence)

    def reject(self, a: str, b: str) -> dict:
        """Assert these are definitively different (`distinct_from`) — the
        sticky separation that keeps two same-named entities (two Clays) apart
        on every future reconcile. Returns a Receipt
        (rejected | noop_already_distinct | conflict_already_merged)."""
        return self._w.registry.reject(a, b)

    # -------------------------------------------- SHAPE-FIX-V1 (identity shape)

    def adjudicate_deferred(self) -> dict:
        """Merge the structurally-DECISIVE subset of open proposals — pure
        name-fragments with no independent identity signal (anchor subsumption:
        `tovin` ⊆ `tovin beck`), no relating edges, no kind conflict, no `aka`.
        Returns {merged: [receipts], residue: [proposals-with-auto_decline]} —
        the residue is yours to adjudicate with confirm/merge/reject. Opt-in;
        `reconcile()` is unchanged. Zero model calls; idempotent."""
        return self._w.registry.adjudicate_deferred()

    def typing_conflicts(self) -> list[dict]:
        """Read-only: same-anchor cross-kind pairs carrying the typing-slip
        signature (an outgoing-bare spurious twin beside a structurally real
        entity — person:harth beside place:harth). Proposals cannot surface
        these; adjudicate each with `retype(...)` or leave it. Zero writes."""
        return self._w.registry.typing_conflicts()

    def retype(self, entity: str, to_kind: str, evidence: str,
               absorb: str | None = None) -> dict:
        """Typing correction, distinct from merge. absorb=None: correct one
        mistyped entity's kind (wrong kind rows retracted, correct kind
        appended + classified). absorb=<target>: the entity is a spurious
        duplicate at the wrong kind — verified against the slip signature,
        artifact edges retracted, then merged through the guarded path.
        Never a veto bypass: a non-slip invocation returns
        `vetoed_not_a_slip`; `distinct_from` stays absolute."""
        return self._w.registry.retype(entity, to_kind, evidence, absorb=absorb)

    # ------------------------------------ AKA-CORRELATION-V1 (opt-in identity)

    def correlate(self, a: str, b: str, evidence: str, at: float | None = None) -> dict:
        """Correlate two entities as facets of one identity (non-collapsing
        `aka`), without merging them — the reveal/dual-persona/amalgamation call.
        `at` is the reveal's valid_from. Returns a Receipt
        (correlated | noop_already_correlated | vetoed_distinct). The hard
        `distinct_from` veto is absolute."""
        return self._w.registry.correlate(a, b, evidence, valid_from=at)

    def correlations(self, entity: str, as_of: float | None = None,
                     frame: str = CANON) -> list[str]:
        """The facets correlated with `entity` as-of (the `aka` set minus its own
        same_as closure), first-seen ordered. Before a reveal's valid_from this
        is empty — the mystery is intact. Zero writes."""
        return self._w.registry.correlations(entity, valid_as_of=as_of, frame=frame)

    def state_union(self, entity: str, attribute: str, frame: str = CANON,
                    as_of: float | None = None) -> dict:
        """The explicit correlated read: fold `attribute` over `entity` ∪ its
        correlated facets, as-of. Same shape as `state`. NOT a default read —
        `state`/`snapshot`/`ask` never union. As-of-before a reveal returns the
        uncorrelated view (no leak)."""
        fold = self._w.state_union(entity, attribute, frame, valid_as_of=as_of)
        if fold.winner is None:
            return {"status": "unknown"}
        fact = (self._quantity_fact(fold.winner, fold.quantity)
                if fold.quantity is not None else self._fact(fold.winner))
        out = {"status": "conflicted" if fold.conflicted else "known",
               "fact": fact.to_dict()}
        if fold.quantity is not None:
            out["quantity"] = fold.quantity
        if fold.conflicted:
            out["conflicting"] = list(fold.conflicting)
        return encode_out(out)

    def correlation_conflicts(self, as_of: float | None = None,
                              frame: str = CANON) -> list[dict]:
        """Pairs carrying both an `aka` and a `distinct_from` (a raw-authored
        contradiction) for host adjudication. The guarded `correlate()` prevents
        these at the source; this surfaces any that slipped in via raw ingest.
        `aka` rows are filtered by `as_of`/`frame`; `distinct_from` is global."""
        return self._w.registry.correlation_conflicts(valid_as_of=as_of, frame=frame)

    def salience(
        self, entity: str, frame: str = CANON, as_of: float | None = None
    ) -> float:
        return self._w.salience(entity, frame=frame, as_of=as_of)

    def confidence(
        self,
        entity: str,
        attribute: str,
        frame: str | list[str] = CANON,
        as_of: float | None = None,
    ) -> dict:
        # frame may be a list: trust over an observer's effective knowledge
        # (knows:O ∪ public), mirroring multi-frame frame_diff.
        return self._w.confidence(entity, attribute, frame=frame, as_of=as_of)

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
        return encode_out(self._w.neighborhood(
            entity,
            depth=depth,
            frame=frame,
            as_of=as_of,
            edge_kinds=edge_kinds,
            max_fanout=max_fanout,
            budget=budget,
        ))

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
        return encode_out(
            sorted(out, key=lambda e: (e["t"] if e["t"] is not None else float("-inf")))
        )

    def who_knows(self, entity: str, attribute: str, value: Any = None,
                  as_of: float | None = None) -> list[str]:
        """The `knows:*` frames that KNOW `(entity, attribute)` — the computed
        inverse of `frame_diff` (WHO-KNOWS-INVERSE-V1). A frame qualifies iff its
        folded winner is present and (when `value` given) value-matches,
        identity-aware. No stored `known_by`; superseded/retracted beliefs drop."""
        return self._w.who_knows(entity, attribute, value, valid_as_of=as_of)

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
            return encode_out(out)

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
            divergent: tuple[tuple[float, int], int | float | Decimal] | None = None
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
        return encode_out(out)

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
            answered=answered, facts=encode_out(facts),
            unknown_reason=None if answered else
            ("unresolved references" if asks else "no folded facts on the asked keys"),
            asks=asks,
        )
