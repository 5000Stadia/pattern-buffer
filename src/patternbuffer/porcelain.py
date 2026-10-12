"""The porcelain: the frozen host surface (PORCELAIN-V1, porcelain-v0.1).

Typed, JSON-serializable verbs over shipped plumbing. Freeze semantics:
additive-only from the v0.1 tag — parameters gain defaults, verbs may be
added; nothing is renamed, removed, or re-typed.

No top-level import of this module from __init__ (lazy property there)
— porcelain imports World types only under TYPE_CHECKING to avoid
circularity.
"""

from __future__ import annotations

import logging
import math
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from patternbuffer.codec import decode_value, encode_out
from patternbuffer.model import (
    ATTR_PREFIX,
    CANON,
    FRAME_CONTINUES_AS,
    FRAME_SCOPES,
    ID_RE,
    KNOWS_PREFIX,
    META_ATTRIBUTES,
    TASK_ASK_PLAN,
    FrameSel,
    task_schema,
)
from patternbuffer.thunks import UNKNOWN, ResolutionDenied

if TYPE_CHECKING:  # pragma: no cover
    from patternbuffer import World

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- payloads


@dataclass
class Receipt:
    world_id: str
    seq_range: list[int] | None
    rows: list[dict] = field(default_factory=list)
    frames: list[str] = field(default_factory=list)
    canonicalization_receipts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # INGEST-HARDENING-V1 Part B: what the gate refused and receipted — the host
    # audits exactly what was dropped (no silent cap). `reason` is a code from
    # ingest.SKIP_REASONS or a legacy per-edge prose reason (GATE-AUTHORITY-V1
    # §0); a record may carry `detail` (FOLD-CORRECTNESS-V1 §6: the bad time
    # value; GATE-AUTHORITY-V1: the bad field, the merge veto, the source).
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
    # READ-SURFACE-V1 §4: the row's value type ("entity", "literal",
    # "unresolved", "delta"); a derived accrue total is "literal". Appended
    # after b_value, so the existing keys keep their order.
    value_type: str = "literal"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Answer:
    answered: bool
    facts: list[dict] = field(default_factory=list)
    prose: str | None = None
    unknown_reason: str | None = None
    asks: list[dict] = field(default_factory=list)
    # READ-SURFACE-V1 §4: the asked keys that hold an unresolved placeholder
    # (never served as a fact) and the keys served conflicted, each
    # `[entity, attribute]` as in snapshot's `unresolved`/`conflicted`.
    unresolved: list[list[str]] = field(default_factory=list)
    conflicted: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


_ASK_PLAN_SCHEMA = {
    "title": TASK_ASK_PLAN,
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


def _finite_time(value: Any) -> bool:
    """A valid valid-time coordinate: a finite real number, never a bool
    (FOLD-CORRECTNESS-V1 §6's predicate; READ-SURFACE-V1 §6 reads the ask
    plan's `as_of` through it)."""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


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

    @contextmanager
    def _posed(self, at: float | None):
        """Apply a write call's `at=` to the scene cursor (GATE-AUTHORITY-V1
        §6). The cursor and the log head are snapshotted before `at` applies;
        if the call raises with the head unmoved and the buffer not poisoned,
        the cursor is restored — a rejected call leaves the pose where it was
        (this subsumes ATOMIC-ACTIVATION-V1 §B4 pin (a): an AtomicAbort rolls
        the head back). After a partial non-atomic write the cursor stays at
        `at`: the rows already written were stamped there."""
        cursor, buffer = self._w.ingestor.cursor, self._w.buffer
        prior_position, prior_head = cursor.position, buffer.head()
        if at is not None:
            cursor.advance(at)
        try:
            yield
        except BaseException:
            try:
                unmoved = not buffer.poisoned and buffer.head() == prior_head
            except Exception:       # never mask the call's own error
                unmoved = False
            if unmoved:
                cursor.position = prior_position
            raise

    def _source_chain(self, row, asserted_as_of: int | None = None) -> list:
        """The row's `source` chain as of the read's log position: a `source`
        row asserted after it is not in the chain (READ-SURFACE-V1 §8)."""
        return [m.value for m in self._w.buffer.visible(
            entity=row.id, attribute="source", asserted_as_of=asserted_as_of)]

    def _fact(self, row, divergent=False, b_value=None,
              asserted_as_of: int | None = None) -> Fact:
        chain = self._source_chain(row, asserted_as_of)
        return Fact(
            entity=row.entity, attribute=row.attribute, value=row.value,
            valid=[row.valid_from, row.valid_to],
            provenance={"status": row.status, "source_chain": chain,
                        "assertion_id": row.id, "frame": row.frame},
            divergent=divergent, b_value=b_value, value_type=row.value_type,
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
        asserted_as_of: int | None = None,
    ) -> Fact:
        chain = self._source_chain(row, asserted_as_of)
        return Fact(
            entity=entity or row.entity, attribute=attribute or row.attribute,
            value=quantity, valid=[row.valid_from, row.valid_to],
            provenance={"status": row.status, "source_chain": chain,
                        "assertion_id": row.id, "frame": row.frame},
            divergent=divergent, b_value=b_value,
            value_type="literal",    # a derived total (READ-SURFACE-V1 §4)
        )

    def _key_payload(self, fold, value: Any = None,
                     asserted_as_of: int | None = None) -> dict:
        """The one payload `state` and `state_union` build from a fold
        (READ-SURFACE-V1 §4). `status` is decided in order: nothing served ->
        `unknown`; the fold flags -> `conflicted`; the served row is an
        unresolved placeholder -> `unresolved` (the doctrine's
        established-deferred state, whitepaper A6: `fact` is the placeholder,
        its value the thunk spec, never a known value); else `known`. Keys
        follow in order: `status`, `fact`, `quantity`, `conflicting`, then
        `conflicting_facts` (one Fact per conflicting id, in that order) and
        `values` (a set-valued key's current members, in member order;
        `fact` stays the most recent). Given a `value`, `matches` comes last:
        `who_knows`'s test of this frame's fold (§5; False on `unknown`)."""
        winner = fold.winner
        if winner is None:
            return {"status": "unknown"} if value is None else {
                "status": "unknown", "matches": False}
        # Accrue: the host-facing value is the derived total, not the last
        # delta row — keep `fact.value` consistent with ask()/snapshot().
        aao = asserted_as_of
        fact = (self._quantity_fact(winner, fold.quantity, asserted_as_of=aao)
                if fold.quantity is not None else self._fact(winner, asserted_as_of=aao))
        if fold.conflicted:
            status = "conflicted"
        elif winner.value_type == "unresolved":
            status = "unresolved"
        else:
            status = "known"
        out = {"status": status, "fact": fact.to_dict()}
        if fold.quantity is not None:
            out["quantity"] = fold.quantity
        if fold.conflicted:
            out["conflicting"] = list(fold.conflicting)
            out["conflicting_facts"] = [
                self._fact(self._w.buffer.get(i), asserted_as_of=aao).to_dict()
                for i in fold.conflicting]
        if fold._value_rows and status != "unresolved":
            out["values"] = [self._fact(r, asserted_as_of=aao).to_dict()
                             for r in fold._value_rows]
        if value is not None:
            # decoded first, so the `$decimal` tag works over JSON and MCP
            out["matches"] = self._w.indexes.fold_matches(fold, decode_value(value))
        return encode_out(out)

    def _point_read(self, entity: str, attribute: str, frame: str,
                    as_of: float | None, asserted_as_of: int | None,
                    *, correlated: bool = False):
        """One key's point read (EVENTS-ONE-READER-V1 §4 Rule B): the fold
        first (`state_union`'s when `correlated`), and the event record when
        the fold serves nothing. An event's own rows never fold (Rule A), so
        its attributes come from its record, under the same frame and both
        as-ofs as `events()`; for any other entity the record is empty and
        the answer is the fold's. Shared by `state`, `state_union` and `ask`'s
        key reads."""
        fold = (self._w.state_union if correlated else self._w.state)(
            entity, attribute, frame, valid_as_of=as_of, asserted_as_of=asserted_as_of)
        if fold.winner is None:
            fold = self._w.indexes.event_attribute(
                entity, attribute, frame, as_of, asserted_as_of, correlated=correlated)
        return fold

    @staticmethod
    def _is_numeric(value: object) -> bool:
        return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)

    def _attr(self, name: Any) -> Any:
        """An attribute argument as the gate names it (READ-SURFACE-V1 §3):
        every porcelain argument that names an attribute passes through here
        first. A non-string argument passes through unchanged."""
        return self._w.canonical_attribute(name) if isinstance(name, str) else name

    def _scoped_frames(self, frame: str, frame_scope: str,
                       asserted_as_of: int | None) -> FrameSel:
        """The stored frames a read of `frame` covers under `frame_scope`
        (FRAME-CONTINUITY-V1 §2), resolved once per call as of the read's log
        position. `exact` returns the plain frame string untouched, so its
        code path is today's. A wider scope applies to `knows:` frames only
        (`ValueError` otherwise) and returns the frame itself first, then the
        others sorted; a scope that adds nothing returns the plain string.

        - `continued`: the frames the host declared continue into this one
          (canon `frame_continues_as` rows, retraction honoured), transitively.
          Edges are exact observer names: no identity closure is applied, so
          a merge never widens a frame (FRAME-SCOPED-IDENTITY-V1 P1).
        - `merged`: the frames of every member of the observer's canon
          `same_as` closure. Never `aka`."""
        if frame_scope not in FRAME_SCOPES:
            raise ValueError(
                f"frame_scope must be one of {FRAME_SCOPES}, got {frame_scope!r}")
        if frame_scope == "exact":
            return frame
        if not (isinstance(frame, str) and frame.startswith(KNOWS_PREFIX)
                and len(frame) > len(KNOWS_PREFIX)):
            raise ValueError(
                f"frame_scope={frame_scope!r} widens a knows:<observer> frame only "
                f"(got {frame!r}); canon, plot:* and every other frame read exactly")
        observer = frame[len(KNOWS_PREFIX):]
        if frame_scope == "merged":
            members = self._w.registry.closure(observer, asserted_as_of)
        else:
            sources: dict[str, list[str]] = {}
            for row in self._w.buffer.visible(
                    attribute=FRAME_CONTINUES_AS, frame=CANON,
                    asserted_as_of=asserted_as_of):
                if row.value_type == "entity" and isinstance(row.value, str):
                    sources.setdefault(row.value, []).append(row.entity)
            members = {observer}
            frontier = [observer]
            while frontier:
                for source in sources.get(frontier.pop(), ()):
                    if source not in members:
                        members.add(source)
                        frontier.append(source)
        others = sorted(KNOWS_PREFIX + m for m in members if m != observer)
        return (frame, *others) if others else frame

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
        `open_conflicts` (the frame's conflicted folds as of `as_of`, computed
        on read — FRAME-SCOPED-IDENTITY-V1 §5), and a `summary` with the
        headline live-fragmentation count. Read-only; run after seal. The host joins
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
        ingestor = self._w.ingestor
        with self._posed(at):
            context = f"\nSCENE HINT (context only, never a spatial anchor): {scene}" if scene else ""
            rows = self._w.ingest(text, context=context, frame=frame, classify=classify,
                                  extract=extract, cursor_authoritative=cursor_authoritative,
                                  pov=pov)
            # GATE-AUTHORITY-V1 §6: the Receipt lists the call's skips — the
            # extraction call's, then the `source=` stamping call's, each
            # captured right after its own gate call (the second call
            # replaces `last_skipped`).
            skipped = [s.to_dict() for s in ingestor.last_skipped]
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
                skipped += [s.to_dict() for s in ingestor.last_skipped]
        receipt = self._receipt(rows)
        receipt.skipped = skipped
        return receipt

    def ingest_structured(self, items: list[dict], frame: str | None = None,
                          classify: str = "inline",
                          cursor_authoritative: bool = False,
                          at: float | None = None,
                          extracted: bool = False,
                          atomic: bool = False) -> Receipt:
        """Commit already-structured items through the ingest gate (the only
        path for stated/observed truth): canonicalization, identity, the
        malformed-id gate and per-edge skips apply, and every dropped item is
        listed in the Receipt's `skipped`. `atomic=True` makes the whole call
        all-or-none; `extracted=True` is the prose-mode recipe after `extract()`."""
        # `extracted` (MOVED-EVENT-V1 §B.3): prose-authored mode. The engine runs
        # the moved-event coordinate pass, authoring movement timestamps from the
        # scene cursor. Default False leaves structured callers byte-identical.
        # `atomic` (ATOMIC-ACTIVATION-V1 §A): all-or-none visibility, default off.
        # `at` places the scene cursor before the commit (AXIS-HEAD-V1 Win 2)
        # — the per-chunk pose for parallel-extract/serial-commit paths,
        # mirroring ingest(at=). The porcelain owns the pose; the gate reads it.
        # A rejected call leaves the pose where it was (GATE-AUTHORITY-V1 §6,
        # which subsumes ATOMIC §B4 pin (a)).
        # frame= is a DEFAULT for unframed items (letter 028) — per-item frames
        # win, which mixed batches (knows:B rows beside canon) require. Make the
        # non-obvious case LOUD, never silent (HD 121: a staging frame silently
        # lost to item-level stamps bypassed a quarantine gate for weeks).
        kept_own = (sum(1 for i in items
                        if isinstance(i, dict) and i.get("frame") not in (None, frame))
                    if frame is not None else 0)
        with self._posed(at):
            rows = self._w.ingest_structured(
                items, frame=frame, classify=classify,
                cursor_authoritative=cursor_authoritative, extracted=extracted,
                atomic=atomic)
        receipt = self._receipt(rows)
        if kept_own:
            receipt.warnings.append(
                f"frame={frame!r} filled only unframed items; {kept_own} item(s) "
                "kept their own frame key (frame= is a default, not an override "
                "— strip item frames to re-target wholesale)")
        receipt.skipped = [s.to_dict() for s in self._w.ingestor.last_skipped]
        return receipt

    def resolve(self, entity: str, aspect: str, frame: str = CANON,
                at: float | None = None) -> dict:
        """Force an aspect (whitepaper §8). A planted placeholder is forced as
        ever; a declared (``resolvable_for``) aspect nobody planted is planted
        and forced in one unit, and the result says `"planted": true`
        (RESOLVE-UNMARKED-V1). `at` poses the scene cursor exactly as
        ``ingest_structured(at=)`` does, on every path: it is where a planted
        placeholder sits, and a call that raises with the head unmoved
        restores it. In a world that declares any aspect resolvable, an aspect
        nobody may invent answers `{"status": "undeclared", …, "reason"}`."""
        aspect = self._attr(aspect)
        resolver = self._w.resolver
        with self._posed(at):
            try:
                out, planted = resolver.resolve_planted(entity, aspect, frame)
            except ResolutionDenied as exc:
                return {"status": "denied", "facts": [],
                        "receipt": self._receipt([]).to_dict(), "reason": str(exc)}
        if out is UNKNOWN:
            return {"status": "unknown", "facts": [],
                    "receipt": self._receipt([]).to_dict()}
        rows = [r for r in out if r is not None]
        if not rows and not planted and resolver.opted_in():
            reason = resolver.undeclared_reason(entity, aspect, frame)
            if reason is not None and not resolver.has_thunk(entity, aspect, frame):
                return {"status": "undeclared", "facts": [],
                        "receipt": self._receipt([]).to_dict(), "reason": reason}
        result = {"status": "resolved",
                  "facts": [self._fact(r).to_dict() for r in rows],
                  "receipt": self._receipt(rows).to_dict()}
        if planted:
            result["planted"] = True
        return encode_out(result)

    def retract(self, assertion_id: str, reason: str) -> Receipt:
        """Withdraw one assertion by id with a reason: an appended retraction
        meta-assertion (the row stays in the log, out of every fold)."""
        return self._receipt([self._w.truth.retract(assertion_id, reason)])

    def commit_set(self, ops: list[dict], *, classify: str = "rules",
                   frame: str = CANON,
                   cursor_authoritative: bool = False) -> Receipt:
        """The typed activation door (ATOMIC-ACTIVATION-V1 §C): an ordered list
        of ``{op:"assert", item}`` / ``{op:"retract", assertion_id, reason}`` ops
        applied as ONE all-or-none unit of work. On any gate skip / raised
        condition the whole set rolls back and ``AtomicAbort`` (cause
        ``gate_skip``/``exception``) is raised — nothing becomes visible. Success
        returns the ordinary ``Receipt`` (non-idempotent; retry via a
        postcondition probe, §B5)."""
        rows = self._w.commit_set(ops, classify=classify, frame=frame,
                                  cursor_authoritative=cursor_authoritative)
        receipt = self._receipt(rows)
        receipt.skipped = [s.to_dict() for s in self._w.ingestor.last_skipped]
        return receipt

    # --------------------------------------------------- reads (LLM-free)

    def canonical_attribute(self, name: str) -> str:
        """The gate's name for an attribute (READ-SURFACE-V1 §3): its own
        normalization (strip, lowercase, spaces to `_`) and its forward alias
        map, exactly as applied on write — "Located In" -> "in", "type" ->
        "kind". Every porcelain argument that names an attribute passes
        through it, so an alias spelling reads the key the gate stored.
        Inverse spellings (`holds`, `wearing`) are not renamed."""
        return self._attr(name)

    def _is_known(self, entity: str, frame: str = CANON,
                  asserted_as_of: int | None = None) -> bool:
        """Whether `entity` exists from `frame`'s perspective: some visible row
        about a member of its identity closure lives in `frame` or in canon —
        an indexed check over the requested id only, never a whole-log scan
        per call.

        Existence follows perspective (FRAME-SCOPED-IDENTITY-V1 §6). Canon is
        the existence authority (HD 003: identity/existence is a canon
        question; only the answer is knowledge-scoped), and a frame may add
        entities canon lacks — a belief, a plot arc. An id that lives only in
        another frame is unknown here, exactly like an id nobody wrote.

        One `visible(entity_in=)` call, filtered to the two frames here (r2):
        adding `frame=` to the query lets SQLite pick the frame index over the
        entity index (measured on a 100k-row log: 8.8 ms per id against
        0.35). As of a log position (READ-SURFACE-V1 §8), an id first asserted
        after it is unknown, like an id nobody wrote."""
        members = sorted(self._w.registry.closure(entity))
        frames = {CANON, frame}
        return any(
            r.frame in frames
            and not r.entity.startswith("a:") and not r.entity.startswith(ATTR_PREFIX)
            for r in self._w.buffer.visible(entity_in=members,
                                            asserted_as_of=asserted_as_of)
        )

    def snapshot(self, scope, frame: str = CANON, as_of: float | None = None,
                 lens: str = "current_state", budget: int | None = None,
                 since: float | None = None, correlated: bool = False,
                 features: bool = False, asserted_as_of: int | None = None) -> dict:
        """Materialize known entity ids (and what they contain) from one frame:
        folded facts, accrue quantities, unresolved aspects, conflicted keys and
        render-time defaults, under a lens (current_state, establishing_set,
        what_happened, character_sheet, situation) as of a valid time, shaped to
        an optional budget. Unknown or malformed ids return {"error", "bad"};
        an id is known when some row about it lives in `frame` or in canon, so
        an id that only another frame carries is unknown here
        (FRAME-SCOPED-IDENTITY-V1 §6). `asserted_as_of` reads the log as it
        stood at that position (READ-SURFACE-V1 §8)."""
        # correlated/features (AWARENESS-READS-V1.1, opt-in): fold each entity over
        # its aka correlation union (the whole reveal scene) and/or inline each
        # place's part_of-feature children. Default off = unchanged.
        roots = [scope] if isinstance(scope, str) else list(scope)
        # Known in the snapshot's frame or in canon (FRAME-SCOPED-IDENTITY-V1 §6).
        bad = [s for s in roots
               if not ID_RE.fullmatch(s)
               or not self._is_known(s, frame, asserted_as_of)]
        if bad:
            return {"error": "snapshot scope must be KNOWN entity ids "
                             "(use ask for references)", "bad": bad}
        m = self._w.materialize(roots, as_of=as_of, frame=frame, lens=lens,
                                budget=budget, since=since,
                                correlated=correlated, features=features,
                                asserted_as_of=asserted_as_of)
        # encode_out at the return: the porcelain's plain-JSON contract —
        # exact-decimal values leave as the tag dict, never a raw Decimal.
        return encode_out({
            "world_id": self._w.world_id,
            "charter": self._w.charter(asserted_as_of=asserted_as_of),
            "frame": m.frame, "lens": m.lens, "as_of": m.as_of,
            "facts": [self._fact(r, asserted_as_of=asserted_as_of).to_dict()
                      for r in m.assertions],
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
              as_of: float | None = None, value: Any = None,
              asserted_as_of: int | None = None,
              frame_scope: str = "exact") -> dict:
        """The folded value of one (entity, attribute) key in a frame as of a valid
        time: {"status": "unknown"} when nothing is recorded, else "known",
        "conflicted" or "unresolved" (the served row is an unresolved
        placeholder) with the served fact; plus the conflicting assertion ids
        and their facts, a set-valued key's current members (`values`), or
        the derived quantity for an accrue attribute. A host treats a status
        it does not recognize as not known. Given a `value` (any JSON; a
        `$decimal` tag decodes), the payload gains `matches`: whether this
        frame's fold holds it, `who_knows`'s test (READ-SURFACE-V1 §5).
        `asserted_as_of` reads the log as it stood at that position (§8).

        An event's own attributes are read from its record
        (EVENTS-ONE-READER-V1 §4): `kind` and the movement keys answer exactly
        what `events()` reports (conflicted when two top-rank rows disagree at
        one stamp); a description key with several rows lists them in
        `values`; an event that has not occurred by `as_of` is unknown.

        `frame_scope` (FRAME-CONTINUITY-V1 §2) is `exact` (default: the rows
        stored under `frame`), `continued` (plus the frames the host declared
        continue into it, `continue_frame`) or `merged` (plus the frames of the
        observer's `same_as` closure); the latter two take a `knows:` frame
        only. The fold runs over the union as one row set and every served
        fact says its stored frame in `provenance.frame`."""
        return self._key_payload(
            self._point_read(entity, self._attr(attribute),
                             self._scoped_frames(frame, frame_scope, asserted_as_of),
                             as_of, asserted_as_of),
            value, asserted_as_of)

    def where(self, attribute: str, op: str, value, frame: str = CANON,
              as_of: float | None = None,
              asserted_as_of: int | None = None) -> list[str]:
        """Entity ids whose folded `attribute` satisfies `op value` (one of
        ">=", ">", "<=", "<", "==") in a frame as of a valid time."""
        comparators = {
            ">=": lambda a, b: a >= b,
            ">": lambda a, b: a > b,
            "<=": lambda a, b: a <= b,
            "<": lambda a, b: a < b,
            "==": lambda a, b: a == b,
        }
        if op not in comparators:
            raise ValueError(f"unknown comparison operator {op!r}")
        attribute = self._attr(attribute)
        value = decode_value(value)   # tag-form symmetry: {"$decimal": ...} ok
        if not self._is_numeric(value):
            return []
        candidates = {
            self._w.registry.resolve(r.entity)
            for r in self._w.buffer.visible(
                attribute=attribute, frame=frame, valid_as_of=as_of,
                asserted_as_of=asserted_as_of,
            )
            if not r.entity.startswith("a:")
            and not r.entity.startswith(ATTR_PREFIX)
        }
        out: list[str] = []
        for entity in sorted(candidates):
            fold = self._w.state(entity, attribute, frame, valid_as_of=as_of,
                                 asserted_as_of=asserted_as_of)
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
        asserted_as_of: int | None = None,
    ) -> dict:
        """A bounded rollup (sum, count, min, max, avg) of `member_attribute`
        over a container's members, optionally recursive; derived, never stored."""
        return encode_out(self._w.aggregate(
            container, self._attr(member_attribute), op,
            frame=frame, as_of=as_of, recursive=recursive,
            asserted_as_of=asserted_as_of,
        ))

    def entities(self, frame: str, prefix: str | None = None,
                 as_of: float | None = None,
                 asserted_as_of: int | None = None) -> list[str]:
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
        for r in self._w.buffer.visible(frame=frame, valid_as_of=as_of,
                                        asserted_as_of=asserted_as_of):
            if r.entity.startswith("a:") or r.entity.startswith(ATTR_PREFIX):
                continue
            eid = self._w.registry.resolve(r.entity)
            if prefix is None or eid.startswith(prefix):
                out.add(eid)
        return sorted(out)

    def facts(self, frame: str, entity: str | None = None,
              attribute: str | None = None, prefix: str | None = None,
              as_of: float | None = None, include_meta: bool = False,
              asserted_as_of: int | None = None,
              frame_scope: str = "exact") -> list[dict]:
        """The frame-scan read (BOUNDED-READS-V1): the visible rows OF one
        frame as Fact payloads — RAW log reads for audited scans (receipt
        trails, knowledge digests, marker rows), NOT folds (folded truth is
        `state`/`snapshot`). `frame` is required (the bound). `entity` targets
        one id (identity-closure for world entities; exact for `a:<n>` receipt
        chains — always served); frame/prefix-wide listings exclude meta rows
        unless `include_meta=True`. `frame_scope` is `exact` unless the caller
        widens it (see `state`); every fact says its stored frame in
        `provenance.frame`, so a scan can act on the rows of one frame."""
        if not frame:
            raise ValueError("facts() requires a frame — every read fixes perspective")
        if attribute is not None:
            attribute = self._attr(attribute)
        aao = asserted_as_of
        frame = self._scoped_frames(frame, frame_scope, aao)
        if entity is not None and not entity.startswith("a:"):
            clos = sorted(self._w.registry.closure(entity))
            rows = self._w.buffer.visible(entity_in=clos, frame=frame,
                                          attribute=attribute, valid_as_of=as_of,
                                          asserted_as_of=aao)
        elif entity is not None:
            rows = self._w.buffer.visible(entity=entity, frame=frame,
                                          attribute=attribute, valid_as_of=as_of,
                                          asserted_as_of=aao)
        else:
            rows = [
                r for r in self._w.buffer.visible(frame=frame, attribute=attribute,
                                                  valid_as_of=as_of, asserted_as_of=aao)
                if include_meta or (not r.entity.startswith("a:")
                                    and not r.entity.startswith(ATTR_PREFIX))
            ]
        if prefix is not None:
            rows = [r for r in rows
                    if self._w.registry.resolve(r.entity).startswith(prefix)]
        return encode_out([self._fact(r, asserted_as_of=aao).to_dict() for r in rows])

    def locate(self, entity: str, as_of: float | None = None, frame: str = CANON,
               asserted_as_of: int | None = None) -> list[str]:
        """The containment chain above an entity in a frame, nearest container
        first, as of a valid time (containment is single-parent)."""
        return self._w.locate(entity, frame=frame, valid_as_of=as_of,
                              asserted_as_of=asserted_as_of)

    def contents(self, container: str, as_of: float | None = None,
                 frame: str = CANON, asserted_as_of: int | None = None) -> list[str]:
        """The entities directly contained in a container in a frame as of a
        valid time."""
        return self._w.contents(container, frame=frame, valid_as_of=as_of,
                                asserted_as_of=asserted_as_of)

    def composition(self, entity: str, frame: str = CANON,
                    as_of: float | None = None,
                    asserted_as_of: int | None = None) -> list[str]:
        """The `part_of` chain up — the entity's place in the structure
        (PLACE-FEATURE-ABSTRACTION-V1). The compositional sibling of `locate`."""
        return self._w.composition(entity, frame=frame, valid_as_of=as_of,
                                   asserted_as_of=asserted_as_of)

    def features(self, place: str, frame: str = CANON,
                 as_of: float | None = None,
                 asserted_as_of: int | None = None) -> list[str]:
        """The `part_of`-children of a place — its structural sub-features
        (a burrow under a hillside). The compositional sibling of `contents`."""
        return self._w.features(place, frame=frame, valid_as_of=as_of,
                                asserted_as_of=asserted_as_of)

    def path(self, a: str, b: str, as_of: float | None = None, frame: str = CANON,
             asserted_as_of: int | None = None) -> list[str] | None:
        """A shortest route over the lateral graph (connects_to/adjacent_to) in
        a frame as of a valid time, or None: containment is not connectivity."""
        # as_of routes as the graph stood at that time: a severed edge
        # (valid_to passed) drops; history is preserved (PATH-TEMPORAL-V1).
        return self._w.path(a, b, frame=frame, valid_as_of=as_of,
                            asserted_as_of=asserted_as_of)

    def route(self, a: str, b: str, frame: str = CANON, as_of: float | None = None,
              asserted_as_of: int | None = None) -> dict:
        """Passability-aware route (RFC-003): {route, status, segments}. Status
        per segment is clear|blocked|obscured (removed is temporal/diagnostic);
        blocked carries obstructing-fact evidence, obscured a computed
        unknown_basis. The engine derives status from portal facts under the
        host's declared traversal policy; the host supplies the words."""
        return encode_out(self._w.route(a, b, frame=frame, valid_as_of=as_of,
                                        asserted_as_of=asserted_as_of))

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
        (rejected | noop_already_distinct | conflict_already_merged |
        conflict_already_correlated — the pair are facets of one canon
        correlation group; `blocking_edges` names its `aka` rows, and nothing
        is written: FRAME-SCOPED-IDENTITY-V1 §3(d))."""
        return self._w.registry.reject(a, b)

    # ------------------------------------ FRAME-CONTINUITY-V1 (the host's event)

    def continue_frame(self, source: str, into: str, evidence: str) -> Receipt:
        """Declare that what `source` knew is part of what `into` knows
        (FRAME-CONTINUITY-V1 §3): `continue_frame("person:daniel", "person:dan",
        "the same man; host decision")`. Both are observer ids, kept exactly as
        given (a frame's name is never resolved through identity). Writes one
        timeless canon row, `source · frame_continues_as · into` (`stated`),
        and its `evidence`, and returns a Receipt; a read of `knows:<into>`
        with `frame_scope="continued"` then also reads `knows:<source>`. One
        way: `source` gains nothing. Retract the row to end it. Declaring an
        edge that already stands writes nothing (a warning in the Receipt)."""
        for label, observer in (("source", source), ("into", into)):
            if not (isinstance(observer, str) and ID_RE.fullmatch(observer)):
                raise ValueError(f"continue_frame {label} must be an observer id, "
                                 f"got {observer!r}")
        if source == into:
            raise ValueError("continue_frame source and into are the same observer")
        if not (isinstance(evidence, str) and evidence.strip()):
            raise ValueError("continue_frame needs a non-empty evidence string")
        for row in self._w.buffer.visible(attribute=FRAME_CONTINUES_AS, frame=CANON,
                                          entity=source):
            if row.value == into:
                receipt = self._receipt([])
                receipt.warnings.append(
                    f"already declared by {row.id}; nothing written")
                return receipt
        ingestor = self._w.ingestor
        with self._posed(None):
            rows = self._w.ingest_structured([{
                "entity": source, "attribute": FRAME_CONTINUES_AS, "value": into,
                "value_type": "entity", "status": "stated", "frame": CANON,
                "timeless": True}], classify="rules")
            skipped = [sk.to_dict() for sk in ingestor.last_skipped]
            edge = next((r for r in rows if r.attribute == FRAME_CONTINUES_AS), None)
            if edge is not None:          # else the gate refused it: `skipped` says why
                rows += self._w.ingest_structured([{
                    "entity": edge.id, "attribute": "evidence", "value": evidence,
                    "status": "stated", "frame": CANON, "timeless": True}],
                    classify="rules")
                skipped += [sk.to_dict() for sk in ingestor.last_skipped]
        receipt = self._receipt(rows)
        receipt.skipped = skipped
        return receipt

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

    def identity_conflicts(self) -> list[dict]:
        """Read-only: merged canon closures that hold a pair the guarded merge
        would veto (a containment-family or `distinct_from` row with both
        endpoints inside) — what a raw or legacy `same_as` merged past the
        vetoes (FRAME-SCOPED-IDENTITY-V1 §4). Each entry is `{canonical_id,
        members, containment_edges, distinct_edges, same_as: [{assertion_id,
        edge, merge_event_id}]}`; you decide which `same_as` to retract. Canon
        only (identity is canon's). Zero writes."""
        return encode_out(self._w.identity_conflicts())

    def retype(self, entity: str, to_kind: str, evidence: str,
               absorb: str | None = None) -> dict:
        """Typing correction, distinct from merge. absorb=None: correct one
        mistyped entity's kind (wrong kind rows retracted, correct kind
        appended + classified). absorb=<target>: the entity is a spurious
        duplicate at the wrong kind — verified against the slip signature,
        artifact edges retracted, then merged through the guarded path.
        Never a veto bypass: a non-slip invocation returns
        `vetoed_not_a_slip`; `distinct_from` stays absolute. With absorb=, a
        `to_kind` that contradicts the target's kind returns
        `vetoed_kind_mismatch` and writes nothing (FRAME-SCOPED-IDENTITY-V1
        §8). Kind rows are canon's: a `knows:` belief about the kind survives
        (§2)."""
        return self._w.registry.retype(entity, to_kind, evidence, absorb=absorb)

    # ------------------------------------ AKA-CORRELATION-V1 (opt-in identity)

    def correlate(self, a: str, b: str, evidence: str, at: float | None = None) -> dict:
        """Correlate two entities as facets of one identity (non-collapsing
        `aka`), without merging them — the reveal/dual-persona/amalgamation call.
        `at` is the reveal's valid_from. Returns a Receipt
        (correlated | noop_already_correlated | vetoed_distinct). The hard
        `distinct_from` veto is absolute, and acts on whole correlation groups:
        a `distinct_from` between a's group and b's vetoes too
        (FRAME-SCOPED-IDENTITY-V1 §3(a)). A correlated pair is never
        auto-merged (`reconcile`, promotion); `merge`/`confirm` still can."""
        return self._w.registry.correlate(a, b, evidence, valid_from=at)

    def correlations(self, entity: str, as_of: float | None = None,
                     frame: str = CANON,
                     asserted_as_of: int | None = None) -> list[str]:
        """The facets correlated with `entity` as-of (the `aka` set minus its own
        same_as closure), first-seen ordered. Before a reveal's valid_from this
        is empty — the mystery is intact. Zero writes."""
        return self._w.registry.correlations(entity, valid_as_of=as_of,
                                             asserted_as_of=asserted_as_of,
                                             frame=frame)

    def state_union(self, entity: str, attribute: str, frame: str = CANON,
                    as_of: float | None = None, value: Any = None,
                    asserted_as_of: int | None = None,
                    frame_scope: str = "exact") -> dict:
        """The explicit correlated read: fold `attribute` over `entity` ∪ its
        correlated facets, as-of. Same shape as `state`. NOT a default read —
        `state`/`snapshot`/`ask` never union. As-of-before a reveal returns the
        uncorrelated view (no leak). An event's own attributes are read from
        the records of the union (EVENTS-ONE-READER-V1 §4). `frame_scope` is
        `state`'s (FRAME-CONTINUITY-V1 §2): under a wider scope the `aka` edges
        are read from the same union of stored frames."""
        return self._key_payload(
            self._point_read(entity, self._attr(attribute),
                             self._scoped_frames(frame, frame_scope, asserted_as_of),
                             as_of, asserted_as_of, correlated=True),
            value, asserted_as_of)

    def correlation_conflicts(self, as_of: float | None = None,
                              frame: str = CANON,
                              asserted_as_of: int | None = None) -> list[dict]:
        """Every `distinct_from` whose endpoints lie in one correlation group (a
        raw-authored contradiction) for host adjudication. The guarded
        `correlate()` prevents these at the source; this surfaces any that
        slipped in via raw ingest. Both edges are the frame's own: `aka` rows
        filtered by `as_of`, `distinct_from` valid-time-blind. Direct entries
        (one `aka` row joins the pair) come first; group entries carry
        `aka_edge: None` and the `aka_path` that joins them
        (FRAME-SCOPED-IDENTITY-V1 §3(b))."""
        return self._w.registry.correlation_conflicts(
            valid_as_of=as_of, asserted_as_of=asserted_as_of, frame=frame)

    def salience(
        self, entity: str, frame: str = CANON, as_of: float | None = None
    ) -> float:
        """The projection-time salience of an entity in a frame (recency,
        reinforcement, reference frequency, delta from baseline); a ranking,
        never a stored truth."""
        return self._w.salience(entity, frame=frame, as_of=as_of)

    def confidence(
        self,
        entity: str,
        attribute: str,
        frame: str | list[str] = CANON,
        as_of: float | None = None,
        now: float | None = None,
        asserted_as_of: int | None = None,
    ) -> dict:
        """Derived trust in one functional key: the served value plus provenance
        rank, corroboration, conflict and recency (wall-clock decay in tracking
        worlds). `frame` may be a list (an observer's effective knowledge)."""
        # frame may be a list: trust over an observer's effective knowledge
        # (knows:O ∪ public), mirroring multi-frame frame_diff.
        # now (TRACKING-MODE-V1): the WALL-time staleness reference in tracking
        # worlds (defaults to the injected clock; unused in fiction). The
        # payload carries recency/recency_status/last_confirmed_at_wallclock.
        return self._w.confidence(entity, self._attr(attribute), frame=frame,
                                  as_of=as_of, asserted_as_of=asserted_as_of,
                                  now=now)

    def neighborhood(
        self,
        entity: str,
        depth: int = 1,
        frame: str = CANON,
        as_of: float | None = None,
        edge_kinds: list[str] | None = None,
        max_fanout: int = 64,
        budget: int | None = None,
        asserted_as_of: int | None = None,
    ) -> dict:
        """The salience-ranked local subgraph around an entity across
        containment, lateral, relation and event edges, to a depth and budget.
        Salience, and so the ranking, is read at the head."""
        return encode_out(self._w.neighborhood(
            entity,
            depth=depth,
            frame=frame,
            as_of=as_of,
            edge_kinds=edge_kinds,
            max_fanout=max_fanout,
            budget=budget,
            asserted_as_of=asserted_as_of,
        ))

    def events(self, kind: str | None = None,
               participants: str | list[str] | None = None,
               since: float | None = None, until: float | None = None,
               frame: str = CANON, asserted_as_of: int | None = None) -> list[dict]:
        """Reified events (`event:` entities) in a frame, optionally filtered by
        kind, participant and a valid-time window; each carries its payload and
        the movement keys (origin/destination/manner) when it is a move.

        Each event is its record, read whole (EVENTS-ONE-READER-V1 §2): every
        event entity in the frame, classified or not, and nothing else, one
        entry per resolved id. `until` lists an event once it has occurred
        (its first stamped row is <= `until`, or it has none) with its record
        as of `until`; `since` keeps an event whose `t` (its latest stamp) is
        >= `since`. `participants` is all-of over the resolved agents and
        patients. Ordered by `t` (None first), then by the event's earliest
        row."""
        # §2: no `materialize` — the reader groups the frame's event rows by
        # resolved id without the sidecar, so a sweep changes nothing here, a
        # row on another subject never lists an event, and a merged event is
        # one entry. § E1's twelve keys come from `Indexes.event_payload`.
        indexes = self._w.indexes
        out = [indexes.event_payload(event_id, record)
               for event_id, record in indexes.event_records(
                   frame, valid_as_of=until, asserted_as_of=asserted_as_of).items()]
        if since is not None:
            out = [e for e in out if e["t"] is not None and e["t"] >= since]
        if kind is not None:
            out = [e for e in out if e["kind"] == kind]
        if participants:
            wanted = {participants} if isinstance(participants, str) else set(participants)
            wanted = {self._w.registry.resolve(p) for p in wanted}
            out = [e for e in out
                   if wanted <= {self._w.registry.resolve(x)
                                 for x in e["agents"] + e["patients"]}]
        return encode_out(out)

    def in_transit(self, agent: str | None = None, as_of: float | None = None,
                   frame: str = CANON, asserted_as_of: int | None = None) -> list[dict]:
        """Open moved events whose agent has not yet arrived (MOVED-EVENT-V1 § E2).
        Each result is `{agent, origin, destination, manner,
        last_known_containment}`; `last_known_containment` is the resolved
        containment value (place id) or `None`. Identical signature to
        `World.in_transit`; the porcelain result is `encode_out`-encoded.

        It reads `events()`'s records and parse (EVENTS-ONE-READER-V1 §3), so
        the two agree on a move's endpoints; `asserted_as_of` reads the log as
        it stood at that position."""
        return encode_out(self._w.in_transit(agent=agent, as_of=as_of, frame=frame,
                                             asserted_as_of=asserted_as_of))

    def who_knows(self, entity: str, attribute: str, value: Any = None,
                  as_of: float | None = None,
                  asserted_as_of: int | None = None) -> list[str]:
        """The `knows:*` frames that KNOW `(entity, attribute)` — the computed
        inverse of `frame_diff` (WHO-KNOWS-INVERSE-V1). A frame qualifies iff its
        fold serves a concrete value and, when `value` is given, the folded value
        matches it: identity-aware, any member of a set, an accrue key's total
        (READ-SURFACE-V1 §5). A `$decimal` tag decodes first. No stored
        `known_by`; superseded/retracted beliefs drop."""
        return self._w.who_knows(entity, self._attr(attribute), decode_value(value),
                                 valid_as_of=as_of, asserted_as_of=asserted_as_of)

    def frame_diff(self, a: str, b: str | list[str], scope,
                   as_of: float | None = None,
                   asserted_as_of: int | None = None) -> list[dict]:
        """Semantic fact diff: keys folded in `a`, absent or divergent in
        `b`. Never compares assertion ids (frames are sparse copies)."""
        # One frame is the one-element case of the effective-knowledge union
        # (WORLD-RETRIEVAL-V2 #25): a single shared path, never two copies.
        b_frames = [b] if isinstance(b, str) else list(b)
        roots = [scope] if isinstance(scope, str) else list(scope)
        aao = asserted_as_of
        m_a = self._w.materialize(roots, frame=a, as_of=as_of, asserted_as_of=aao)
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
            fold_a = self._w.state(entity, attribute, frame=a, valid_as_of=as_of,
                                   asserted_as_of=aao)
            if fold_a.winner is None:
                continue
            covered = False
            held = False
            divergent: tuple[tuple[float, int], int | float | Decimal] | None = None
            for b_frame in b_frames:
                fold_b = self._w.state(entity, attribute, frame=b_frame,
                                       valid_as_of=as_of, asserted_as_of=aao)
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
                        fold_a.winner, quantity, entity=entity, attribute=attribute,
                        asserted_as_of=aao,
                    ).to_dict()
                )
            else:
                out.append(
                    self._quantity_fact(
                        fold_a.winner, quantity, entity=entity, attribute=attribute,
                        divergent=True, b_value=divergent[1], asserted_as_of=aao,
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
                                           valid_as_of=as_of, asserted_as_of=aao)
                    b_members.update(
                        _norm(br.value, br.value_type)
                        for br in (fold_b._value_rows
                                   or ((fold_b.winner,) if fold_b.winner else ()))
                    )
                if _norm(row.value, row.value_type) not in b_members:
                    out.append(self._fact(row, asserted_as_of=aao).to_dict())
                continue

            held = False
            covered = False
            divergent: tuple[tuple[float, int], Any] | None = None
            for b_frame in b_frames:
                fold_b = self._w.state(entity, row.attribute, frame=b_frame,
                                       valid_as_of=as_of, asserted_as_of=aao)
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
                out.append(self._fact(row, asserted_as_of=aao).to_dict())
            else:
                out.append(self._fact(row, divergent=True, b_value=divergent[1],
                                      asserted_as_of=aao).to_dict())
        return encode_out(out)

    # ------------------------------------------------------- reference

    def refer(self, description: str, scope: str | list[str] | None = None,
              frame: str = CANON, as_of: float | None = None,
              constraints: list[list[str]] | None = None,
              asserted_as_of: int | None = None,
              learn: bool = True, model: bool = True) -> dict:
        """Resolve a referring expression (whitepaper §9) to one entity, a
        candidate set, or underdetermined: `{"status": "resolved" |
        "candidates" | "underdetermined", "entity_id", "candidates",
        "receipt"}` (READ-SURFACE-V1 §9). Tier 1 is deterministic: an authored
        name or alias in `frame`, constraint inversion (`constraints` are
        `[relation, anchor]` pairs: `contains`, `owned_by`, `held_by`), the one
        entity of the named kind in `scope`, a word refer learned earlier.
        `model=False` is tier 1 only: where tier 2 would judge, the result is
        `candidates` with signal `no_model`, and nothing is learned. `learn`
        (REFER-LEARNING-V1): a vocabulary miss that tier 2 maps onto one entity
        in scope is remembered as a word; a pick never is. `asserted_as_of`
        reads the log as it stood at that position and never learns."""
        pairs: list[tuple[str, str]] | None = None
        if constraints is not None:
            pairs = []
            for constraint in constraints:
                if not (isinstance(constraint, (list, tuple)) and len(constraint) == 2
                        and all(isinstance(part, str) for part in constraint)):
                    raise ValueError(
                        "a refer constraint is a [relation, anchor] pair of "
                        f"strings, got {constraint!r}")
                pairs.append((constraint[0], constraint[1]))
        resolution = self._w.refer(
            description, scope=scope, frame=frame, constraints=pairs, as_of=as_of,
            asserted_as_of=asserted_as_of, learn=learn, model=model)
        return encode_out(asdict(resolution))

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
        plan = self._w.ingestor._model(prompt, task_schema(_ASK_PLAN_SCHEMA))
        # READ-SURFACE-V1 §6 rule A: one effective time `t`, governing every
        # step below (the asker's scope, both refer passes, every key fold,
        # the location fold and its chain, events). The caller's `as_of` is a
        # ceiling the model's parse can lower but never raise: a valid plan
        # `as_of` (a finite real number) is taken when the caller gave none,
        # else the earlier of the two; an invalid one is ignored.
        t = as_of
        if _finite_time(plan.get("as_of")):
            t = plan["as_of"] if as_of is None else min(as_of, plan["as_of"])
        # HD 003: identity/existence is a CANON question; only the answer is
        # knowledge-scoped. Wherever the asked frame cannot bind a reference
        # by itself (rule B below), resolve it against canon with a scene
        # scope mirroring the observe path — the asker (from a knows:<id>
        # frame) plus the asker's current container chain — so co-located
        # objects become candidates and the 018 escalation can fire. The
        # answer keys below are still folded in the asked `frame`.
        # ask never learns (REFER-LEARNING-V1 §8): only a knows: ask has a
        # scope and so can reach the escalation, and the word it would learn
        # is the asker's — written in canon it would leak it. It still reads
        # the words direct refer calls learned.
        ask_scope: str | list[str] | None = None
        if frame.startswith("knows:"):
            asker = frame[len("knows:"):]
            ask_scope = [asker, *self._w.locate(asker, valid_as_of=t)]
        resolved: list[str | None] = []
        asks: list[dict] = []
        for target in plan.get("refer_targets", []):
            r = None
            if frame != CANON:
                # READ-SURFACE-V1 §6 rule B: the asker's own words first — the
                # asked frame's tier 1 alone (its names, aliases, learned
                # words, a kind unique in its view of the scene), kept only if
                # it resolves: zero model calls, zero writes. Canon stays the
                # binding authority wherever the frame cannot bind the
                # reference by itself (HD 003).
                own = self._w.refer(target, scope=ask_scope, frame=frame, as_of=t,
                                    learn=False, model=False)
                if own.status == "resolved":
                    r = own
            if r is None:
                r = self._w.refer(target, scope=ask_scope, frame=CANON, as_of=t,
                                  learn=False)
            if r.status == "resolved":
                resolved.append(r.entity_id)
            else:
                resolved.append(None)
                asks.append({"reference": target, "candidates": list(r.candidates)})
        facts: list[dict] = []
        unresolved: list[list[str]] = []
        conflicted: list[list[str]] = []

        def note(names: list[list[str]], entity: str, attribute: str) -> None:
            # snapshot's naming: the containment family is `in`.
            key = [entity, "in" if self._w.semantics.is_containment(attribute)
                   else attribute]
            if key not in names:
                names.append(key)

        for key in plan.get("keys", []):
            idx = key.get("target_index", 0)
            if not (0 <= idx < len(resolved)) or resolved[idx] is None:
                continue
            attribute = self._attr(key["attribute"])
            # EVENTS-ONE-READER-V1 §4 Rule B: an event target's key is read
            # from its record, as state() reads it.
            fold = self._point_read(resolved[idx], attribute, frame, t, None)
            if fold.winner is None:
                continue
            # READ-SURFACE-V1 §4: a placeholder is named, never served as a
            # fact; a set-valued key serves every current member; a
            # conflicted key serves its winner, as before, and is named.
            if fold.quantity is not None:
                facts.append(self._quantity_fact(fold.winner, fold.quantity).to_dict())
            elif fold.winner.value_type == "unresolved":
                note(unresolved, resolved[idx], attribute)
            elif fold._value_rows:
                facts.extend(self._fact(r).to_dict() for r in fold._value_rows)
            else:
                facts.append(self._fact(fold.winner).to_dict())
            if fold.conflicted:
                note(conflicted, resolved[idx], attribute)
        if plan.get("wants_location"):
            for eid in resolved:
                if eid:
                    fold = self._w.state(eid, "in", frame, valid_as_of=t)
                    if fold.winner is None:
                        continue
                    # The location fold is the `in` key, under §4's rules.
                    if fold.winner.value_type == "unresolved":
                        note(unresolved, eid, "in")
                    else:
                        f = self._fact(fold.winner).to_dict()
                        # Frame-scope the chain like the fold beside it — a
                        # canon-frame locate would leak containment into a
                        # knows: answer (HD 003, incidental).
                        f["chain"] = self._w.locate(eid, frame=frame, valid_as_of=t)
                        facts.append(f)
                    if fold.conflicted:
                        note(conflicted, eid, "in")
        if plan.get("wants_events"):
            participants = [e for e in resolved if e]
            for ev in self.events(participants=participants or None,
                                  until=t, frame=frame):
                facts.append({"event": ev})
        answered = bool(facts)
        return Answer(
            answered=answered, facts=encode_out(facts),
            unknown_reason=None if answered else
            ("unresolved references" if asks else "no folded facts on the asked keys"),
            asks=asks, unresolved=unresolved, conflicted=conflicted,
        )
