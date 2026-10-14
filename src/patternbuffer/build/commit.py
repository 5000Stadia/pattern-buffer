"""Commit: one serial writer, through the porcelain only (BUILD-LIBRARY-V1 §5).

The writes, in order:

0. **Shape rows first** for every minted id (:func:`shape_rows`).
1. **The manifest**: each entry's shape rows, name and alias rows, and role,
   then its host `fixture = true` row when the entry declares one
   (CONTAINMENT-DURABILITY-V1; written with ``extracted=False``, timed like
   the entry's other identity rows); then each
   persona's shape rows and name (on the persona id only, k7). With
   ``identity_time="gate"`` (the default, r1.8) these rows carry the story time
   of their entry's (or persona's) effective gate chunk, and an escape's or
   mention's rows the time of its declaring chunk; ``"timeless"`` writes them
   timeless, as r1.7 did.
2. **Allocation, before any fact**: each chunk's handles, in (chunk index,
   handle number) order. A pick gets a provisional ``mention:<slug>_<n>`` with
   its shape (2a); an escape joins an earlier escape id or is minted like an
   entry (4), with a role word as its type coerced to ``person`` plus that
   ``role`` (k4). Every handle is then rewritten to its id.
3. **Chunk facts**, in chunk order, each chunk at ``time_of(i)``.
4. (The escape rules of step 2.)
5. **Proposals, never merges**: a canon ``maybe_same_as`` with its evidence,
   for each pick, each colliding escape and each cross-chapter description.
6. **Hidden personas**: ``correlate(persona, entry, evidence=<reveal quote>,
   at=time_of(reveal chunk))``, the only write linking a persona to its entry.
7. **Namesakes**: ``reject`` for each listed pair.

Every write is a porcelain call (``ingest_structured``, ``correlate``,
``reject``), so the ingestor does every write. Before the first one, every
result is re-validated as ``extract`` checks it (r1.7: exactly extract's
language — the grammar's keys, a citation inside the chunk, every id it names,
sources included, gated at or before that sentence, and balanced build
handles), so a hand-made ``ChunkResult`` can write nothing ``extract`` would
have refused.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from patternbuffer.build.extract import ChunkResult, Pick
from patternbuffer.build.grammar import (
    grammar_problem,
    handle_number,
    id_positions,
    is_handle,
    replace_ids,
)
from patternbuffer.build.manifest import BEINGS, NAMESPACE, SPECIES_TYPES, TYPES, normalize_type
from patternbuffer.build.registry import (
    Ambiguous,
    Registry,
    Resolved,
    shape_rows,
)
from patternbuffer.build.text import is_description, join_key, slug

# What ``ingest_kwargs`` may carry: every ``ingest_structured`` keyword but
# ``items`` and ``at`` (commit poses each chunk itself).
INGEST_KEYS = frozenset({"frame", "classify", "cursor_authoritative", "extracted", "atomic"})


IDENTITY_TIMES = ("gate", "timeless")


class CommitRefused(ValueError):
    """``commit`` refused its input before writing anything. ``code`` names the
    refusal when it has a stable one (r1.8: ``no_chunk_for_identity_time``,
    ``no_chunk_at_or_after_identity_gate``); the message starts with it."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BuildReceipt:
    """What one commit wrote (§5).

    - ``skipped``: every write receipt's skips, gathered in write order;
    - ``minted``: every id this build minted (entries, personas, mentions,
      escapes), in allocation order; ``handle_ids`` maps ``(chunk index,
      handle)`` to the id it was given;
    - the mention, escape, proposal, correlation and rejection counts;
    - ``time_of``: each chunk's story time;
    - ``chunk_spans``: per chunk, its chapter, its time as ``cursor`` and the
      inclusive ``seq`` span its facts appended (``None`` when none), the shape
      GRADE-LEAKS-V1 §1 reads;
    - ``pending_reveals``: persona ids whose reveal chunk was not among the
      results, so no ``correlate`` was written;
    - ``identity_receipts``: the ``correlate`` and ``reject`` receipts."""

    skipped: tuple[dict[str, Any], ...]
    minted: tuple[str, ...]
    handle_ids: Mapping[tuple[int, str], str]
    mentions: int
    escapes: int
    proposals: int
    correlations: int
    rejections: int
    time_of: Mapping[int, float]
    chunk_spans: tuple[dict[str, Any], ...] = ()
    pending_reveals: tuple[str, ...] = ()
    identity_receipts: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """The receipt as plain JSON data (handle keys as ``"NN/new:k"``)."""
        return {
            "skipped": list(self.skipped), "minted": list(self.minted),
            "handle_ids": {f"{i:02d}/{h}": v for (i, h), v in sorted(self.handle_ids.items())},
            "mentions": self.mentions, "escapes": self.escapes, "proposals": self.proposals,
            "correlations": self.correlations, "rejections": self.rejections,
            "time_of": {str(i): t for i, t in sorted(self.time_of.items())},
            "chunk_spans": list(self.chunk_spans),
            "pending_reveals": list(self.pending_reveals),
            "identity_receipts": list(self.identity_receipts),
        }


def coerce_type(declared: str) -> tuple[str, str | None]:
    """An escape's type at the library edge (§5 k4): a type from the closed set
    stands; anything else is a role word, minted as ``person`` with that
    ``role`` (R49's rule), never refused."""
    normalized = normalize_type(declared)
    if normalized in TYPES:
        return normalized, None
    return "person", declared.strip()


@dataclass
class _Proposal:
    source: str
    target: str
    evidence: str
    candidates: tuple[str, ...] | None = None


class _Writer:
    """Every ``ingest_structured`` call of one commit, with ``ingest_kwargs``
    passed through unchanged and the skips gathered."""

    def __init__(self, world: Any, kwargs: Mapping[str, Any]) -> None:
        self.porcelain = world.porcelain
        self.kwargs = dict(kwargs)
        self.skipped: list[dict[str, Any]] = []

    def put(self, items: list[dict[str, Any]], at: float | None = None,
            **override: Any) -> Any:
        receipt = self.porcelain.ingest_structured(
            items, at=at, **{**self.kwargs, **override})
        self.skipped.extend(receipt.skipped)
        return receipt

    def head(self) -> int:
        return self.porcelain.axis_heads()["asserted_head"]


def _literal(entity: str, attribute: str, value: Any, *, status: str | None = None) -> dict[str, Any]:
    row = {"entity": entity, "attribute": attribute, "value": value,
           "value_type": "literal", "timeless": True, "frame": "canon"}
    if status is not None:
        row["status"] = status
    return row


def _identity_rows(id: str, type_: str, species: str | None, names: Sequence[str],
                   role: str | None) -> list[dict[str, Any]]:
    """A minted id's rows: shape first, then its name, aliases and role."""
    rows = shape_rows(id, type_, species if type_ in SPECIES_TYPES else None)
    seen: list[str] = []
    for name in names:
        if name in seen:
            continue
        rows.append(_literal(id, "name" if not seen else "alias", name))
        seen.append(name)
    if role:
        rows.append(_literal(id, "role", role))
    return rows


def _ingest_kwargs(ingest_kwargs: Mapping[str, Any] | None) -> dict[str, Any]:
    if ingest_kwargs is None:
        return {}
    if not isinstance(ingest_kwargs, Mapping):
        raise TypeError("ingest_kwargs must be a mapping of ingest_structured keywords")
    extra = sorted(set(ingest_kwargs) - INGEST_KEYS)
    if extra:
        raise ValueError(f"ingest_kwargs may carry only {sorted(INGEST_KEYS)}; got {extra} "
                         "(commit poses each chunk at time_of(i) itself)")
    return dict(ingest_kwargs)


def _check_item(registry: Registry, r: ChunkResult, n: int, item: Any,
                canonical_attribute: Callable[[str], str] | None = None) -> set[str]:
    """One item re-validated as ``extract`` checks it (§3, §4, r1.7): an item
    the grammar could write (its keys within ``GRAMMAR_KEYS`` plus
    ``sentence``, each holding what the grammar puts there), citing a sentence
    of its chunk (the chunk's own numbering), with every registry id it names
    (subject, entity value, ``caused_by``, a ``knows:`` observer, a source)
    gated at or before that sentence, and no ``person:`` source that names no
    entry or persona. Returns the build handles it uses; raises
    ``CommitRefused`` for anything else."""
    where = f"chunk {r.index} items[{n}]"
    if not isinstance(item, Mapping):
        raise CommitRefused(f"{where} is not a fact item")
    problem = grammar_problem({k: v for k, v in item.items() if k != "sentence"})
    if problem is not None:
        raise CommitRefused(f"{where} is not a fact item the grammar writes: {problem}")
    if canonical_attribute is not None and canonical_attribute(item["attribute"]) == "fixture":
        raise CommitRefused(
            f"{where}: attribute {item['attribute']!r} is the host's `fixture` declaration "
            "in this world; a model's item never writes it")
    cited = item.get("sentence")
    if isinstance(cited, bool) or not isinstance(cited, int):
        raise CommitRefused(f"{where} cites no sentence")
    count = r.last_sentence - r.first_sentence + 1
    if not 1 <= cited <= count:
        raise CommitRefused(f"{where} cites s{cited}, outside its chunk (s1-s{count})")
    at = (r.chapter, r.first_sentence + cited - 1)
    handles: set[str] = set()
    for position, ident in id_positions(item):
        if is_handle(ident):
            handles.add(ident)
            continue
        if position == "source":
            found = registry.source_problem(ident, *at)
            if found is not None:
                raise CommitRefused(f"{where}: {found[1]}; the item cites chapter {at[0]} "
                                    f"sentence {at[1]}")
            continue
        if not registry.knows(ident):
            raise CommitRefused(f"{where} names {ident!r}, which this registry never minted")
        gate = registry.identity(ident).gate
        if gate > at:
            raise CommitRefused(
                f"{where}: {position} {ident} is gated at chapter {gate[0]} sentence {gate[1]}; "
                f"the item cites chapter {at[0]} sentence {at[1]}")
    return handles


def _checked(registry: Registry, results: Sequence[ChunkResult],
             canonical_attribute: Callable[[str], str] | None = None) -> list[ChunkResult]:
    """The results in chunk order, refused (``CommitRefused``) before any write
    when they could not have come from ``extract`` over this registry's plan
    (r1.7: commit accepts exactly extract's language): every item is one the
    grammar could write, citing a sentence of its chunk, with the effective gate
    of every id it names at or before that sentence; every build handle used is
    declared and every declared one used; a pick's candidates are candidates of
    its chunk. A hand-made ``ChunkResult`` passes only what ``extract`` would
    have accepted.

    ``canonical_attribute`` is the target world's attribute canonicalizer, the
    one the gate applies on write: an item whose attribute canonicalizes to
    ``fixture`` is refused (CONTAINMENT-DURABILITY-V1 r1.3), so a world alias
    such as ``fixed -> fixture`` cannot carry a model's guess past the check."""
    results = list(results)
    for r in results:
        if not isinstance(r, ChunkResult):
            raise TypeError(f"commit takes ChunkResults, got {type(r).__name__}")
    indices = [r.index for r in results]
    if len(set(indices)) != len(indices):
        raise CommitRefused(f"chunk indices repeat: {sorted(indices)}")
    errors = sorted(r.index for r in results if r.error)
    if errors:
        raise CommitRefused(f"chunks {errors} were refused at extraction; nothing committed")
    ordered = sorted(results, key=lambda r: r.index)
    previous: tuple[int, int] | None = None
    book = registry.book
    for r in ordered:
        if r.chapter is None or r.first_sentence is None or r.last_sentence is None:
            raise CommitRefused(f"chunk {r.index} carries no chapter and sentences")
        if not (book.has_sentence(r.chapter, r.first_sentence)
                and book.has_sentence(r.chapter, r.last_sentence)
                and r.first_sentence <= r.last_sentence):
            raise CommitRefused(f"chunk {r.index} is not a span of the registry's text")
        if previous is not None and (r.chapter, r.first_sentence) <= previous:
            raise CommitRefused(f"chunk {r.index} overlaps or precedes the chunk before it")
        previous = (r.chapter, r.last_sentence)
        declared = [e.handle for e in r.escapes] + [p.handle for p in r.picks]
        if len(set(declared)) != len(declared) or not all(is_handle(h) for h in declared):
            raise CommitRefused(f"chunk {r.index} declares a handle twice or a malformed one")
        used: set[str] = set()
        for n, item in enumerate(r.items):
            used |= _check_item(registry, r, n, item, canonical_attribute)
        if used - set(declared):
            raise CommitRefused(f"chunk {r.index} uses undeclared handles "
                                f"{sorted(used - set(declared), key=handle_number)}")
        if set(declared) - used:
            raise CommitRefused(f"chunk {r.index} declares build handles no item uses: "
                                f"{sorted(set(declared) - used, key=handle_number)}")
        last = (r.chapter, r.last_sentence)
        for pick in r.picks:
            if not (isinstance(pick.surface, str) and pick.surface.strip()
                    and isinstance(pick.evidence_quote, str)
                    and len(set(pick.candidates)) >= 2 and pick.choice in pick.candidates
                    and all(registry.knows(c) and registry.identity(c).gate <= last
                            for c in pick.candidates)):
                raise CommitRefused(f"chunk {r.index} pick {pick.handle} is not a choice "
                                    "among two or more candidates of its chunk")
        for escape in r.escapes:
            if not (isinstance(escape.name, str) and escape.name.strip()
                    and isinstance(escape.type, str) and escape.type.strip()
                    and isinstance(escape.quote, str)
                    and (escape.species is None or isinstance(escape.species, str))):
                raise CommitRefused(f"chunk {r.index} escape {escape.handle} has no name, "
                                    "type or quote")
    return ordered


def _times(ordered: list[ChunkResult],
           time_of: Callable[[int], float] | None) -> dict[int, float]:
    clock = time_of if time_of is not None else (lambda i: i + 1)
    times: dict[int, float] = {}
    for r in ordered:
        t = clock(r.index)
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t):
            raise ValueError(f"time_of({r.index}) must be a finite number, got {t!r}")
        times[r.index] = t
    return times


def _mention_shape(registry: Registry,
                   candidates: Sequence[str]) -> tuple[str | None, str | None, bool]:
    """A pick's mention shape (§5 2a, k3): ``(type, species, carries)``. One
    type among the candidates gives that type (species only when all agree);
    beings of several types give ``being`` (``kind = person`` alone); anything
    else gives no shape rows, and the proposal carries the candidates."""
    idents = [registry.identity(c) for c in candidates]
    types = {i.type for i in idents}
    if len(types) == 1:
        species = {i.species for i in idents}
        return next(iter(types)), (next(iter(species)) if len(species) == 1 else None), False
    if types <= BEINGS:
        return "being", None, False
    return None, None, True


def _resolved_ids(answer: Any) -> list[str]:
    if isinstance(answer, Resolved):
        return [answer.id]
    if isinstance(answer, Ambiguous):
        return list(answer.candidates)
    return []


def _gate_chunk(ordered: Sequence[ChunkResult], gate: tuple[int, int]) -> int | None:
    """The index of the committed chunk holding ``gate`` (chapter, sentence);
    failing that the first committed chunk after it; None when no committed
    chunk lies at or after it (r1.8). ``ordered`` is in text order."""
    for r in ordered:
        if r.chapter == gate[0] and r.first_sentence <= gate[1] <= r.last_sentence:
            return r.index
    for r in ordered:
        if (r.chapter, r.first_sentence) > gate:
            return r.index
    return None


def _identity_chunks(registry: Registry,
                     ordered: Sequence[ChunkResult]) -> dict[str, int]:
    """Gate mode: each entry's and persona's identity-time chunk index, or a
    refusal naming every one with no committed chunk at or after its gate."""
    if not ordered:
        raise CommitRefused(
            "no_chunk_for_identity_time: identity_time='gate' takes each identity's time from a "
            "committed chunk, and there is none (use identity_time='timeless' knowingly)",
            code="no_chunk_for_identity_time")
    chunks: dict[str, int] = {}
    stranded: list[str] = []
    for ident in registry.identities:
        index = _gate_chunk(ordered, ident.gate)
        if index is None:
            stranded.append(ident.id)
        else:
            chunks[ident.id] = index
    if stranded:
        raise CommitRefused(
            "no_chunk_at_or_after_identity_gate: no committed chunk lies at or after the gate of "
            f"{stranded}; leave them out of the manifest or use identity_time='timeless'",
            code="no_chunk_at_or_after_identity_gate")
    return chunks


def commit(world: Any, registry: Registry, results: Sequence[ChunkResult], *,
           time_of: Callable[[int], float] | None = None,
           ingest_kwargs: Mapping[str, Any] | None = None,
           identity_time: str = "gate") -> BuildReceipt:
    """Write a build into ``world`` (§5), serially, through its porcelain.

    ``time_of(chunk_index)`` gives each chunk's story time (default ``i + 1``).
    ``ingest_kwargs`` (``frame``, ``classify``, ``cursor_authoritative``,
    ``extracted``, ``atomic``) pass through to every ``ingest_structured``
    call unchanged. ``identity_time`` (r1.8) is ``"gate"`` (the default: each
    entry's and persona's identity rows are valid from the story time of the
    committed chunk holding its effective gate, or the first committed chunk
    after it; an escape's or mention's from its declaring chunk) or
    ``"timeless"`` (r1.7's rows, byte for byte). Gate mode refuses
    (``CommitRefused``, nothing written) when no chunk is committed
    (``no_chunk_for_identity_time``) or an identity is gated after every
    committed chunk (``no_chunk_at_or_after_identity_gate``). Refuses (``CommitRefused``, nothing written) results that
    carry a refused chunk or could not have come from ``extract`` over this
    registry. The registry is not changed: mentions and escapes are drawn from
    a copy of its allocator, after every entry and persona id."""
    if identity_time not in IDENTITY_TIMES:
        raise CommitRefused(f"identity_time must be one of {list(IDENTITY_TIMES)}, "
                            f"got {identity_time!r}", code="invalid_identity_time")
    kwargs = _ingest_kwargs(ingest_kwargs)
    ordered = _checked(registry, results, getattr(world, "canonical_attribute", None))
    times = _times(ordered, time_of)
    gated = identity_time == "gate"
    identity_chunk = _identity_chunks(registry, ordered) if gated else {}
    writer = _Writer(world, kwargs)
    allocator = registry.allocator()

    def put_identity(rows: list[dict[str, Any]], chunk: int | None,
                     **override: Any) -> None:
        """Identity rows: timeless (r1.7) or, in gate mode, valid from the
        chunk's story time (the pose stamps ``valid_from``; nothing carries
        ``timeless``)."""
        if not gated:
            writer.put(rows, **override)
            return
        writer.put([{k: v for k, v in row.items() if k != "timeless"} for row in rows],
                   at=times[chunk], **override)

    # 0 + 1. The manifest: shape rows first, then names, aliases and role.
    for ident in registry.identities:
        if not ident.is_persona:
            chunk = identity_chunk.get(ident.id)
            put_identity(_identity_rows(ident.id, ident.type, ident.species, ident.names,
                                        ident.role), chunk)
            if ident.fixture:
                # CONTAINMENT-DURABILITY-V1 r1.3: the host's declaration, by the
                # minted id, with host authority whatever `ingest_kwargs` say
                # (a model's item never reaches this row). Gate-timed like every
                # identity row (r1.8.3): that spec's r1.6 counts a dated,
                # open-ended declaration from its valid time.
                put_identity([_literal(ident.id, "fixture", True)], chunk, extracted=False)
    for ident in registry.identities:
        if ident.is_persona:
            put_identity(_identity_rows(ident.id, ident.type, ident.species, ident.names, None),
                         identity_chunk.get(ident.id))

    # 2 (with the rules of 4). Allocation, before any fact.
    handle_ids: dict[tuple[int, str], str] = {}
    proposals: list[_Proposal] = []
    proposed: set[tuple[str, str]] = set()
    proper: dict[tuple[str, str], str] = {}
    described: dict[tuple[int, str, str], str] = {}
    latest_description: dict[tuple[str, str], tuple[int, str]] = {}
    mentions = escapes = 0

    def propose(source: str, target: str, evidence: str,
                candidates: tuple[str, ...] | None = None) -> None:
        if source != target and (source, target) not in proposed:
            proposed.add((source, target))
            proposals.append(_Proposal(source, target, evidence, candidates))

    for r in ordered:
        declared: dict[str, Any] = {e.handle: e for e in r.escapes}
        declared.update({p.handle: p for p in r.picks})
        for handle in sorted(declared, key=handle_number):
            decl = declared[handle]
            if isinstance(decl, Pick):
                mention = allocator.mint_numbered(f"mention:{slug(decl.surface)}")
                shape, species, carries = _mention_shape(registry, decl.candidates)
                if shape is not None:
                    put_identity(shape_rows(mention, shape, species), r.index)
                propose(mention, decl.choice, decl.evidence_quote,
                        tuple(decl.candidates) if carries else None)
                mentions += 1
                handle_ids[(r.index, handle)] = mention
                continue
            type_, role = coerce_type(decl.type)
            key = join_key(decl.name)
            escape_id: str | None
            if is_description(decl.name):
                slot = (r.chapter, type_, key)
                escape_id = described.get(slot)
                if escape_id is None:
                    escape_id = allocator.mint(f"{NAMESPACE[type_]}:{slug(decl.name)}")
                    put_identity(_identity_rows(escape_id, type_, decl.species, [decl.name], role),
                                 r.index)
                    escapes += 1
                    described[slot] = escape_id
                    earlier = latest_description.get((type_, key))
                    if earlier is not None and earlier[0] < r.chapter:
                        propose(escape_id, earlier[1], decl.quote)
                    latest_description[(type_, key)] = (r.chapter, escape_id)
            else:
                escape_id = proper.get((type_, key))
                if escape_id is None:
                    escape_id = allocator.mint(f"{NAMESPACE[type_]}:{slug(decl.name)}")
                    put_identity(_identity_rows(escape_id, type_, decl.species, [decl.name], role),
                                 r.index)
                    escapes += 1
                    proper[(type_, key)] = escape_id
            # A collision with the manifest: the escape keeps its own id, and
            # each colliding entry or persona gets a proposal.
            answer = registry.resolve(decl.name, r.chapter, r.last_sentence, hint=type_)
            for colliding in _resolved_ids(answer):
                propose(escape_id, colliding, decl.quote)
            handle_ids[(r.index, handle)] = escape_id

    # 3. Chunk facts, handles rewritten, each chunk at its time.
    spans: list[dict[str, Any]] = []
    for r in ordered:
        mapping = {h: i for (index, h), i in handle_ids.items() if index == r.index}
        items = [replace_ids({k: v for k, v in item.items() if k != "sentence"}, mapping)
                 for item in r.items]
        before = writer.head()
        if items:
            writer.put(items, at=times[r.index])
        after = writer.head()
        spans.append({"chunk": r.index, "chapter": r.chapter, "cursor": times[r.index],
                      "seq": [before + 1, after] if after > before else None})

    # 5. Proposals: a canon maybe_same_as and its evidence; nothing merges.
    written = 0
    for prop in proposals:
        receipt = writer.put([{"entity": prop.source, "attribute": "maybe_same_as",
                               "value": prop.target, "value_type": "entity",
                               "timeless": True, "status": "assumed", "frame": "canon"}])
        edge = next((row["assertion_id"] for row in receipt.rows
                     if row["attribute"] == "maybe_same_as"), None)
        if edge is None:
            continue                         # the gate refused it; `skipped` says why
        written += 1
        meta = [_literal(edge, "evidence", prop.evidence or "(no quote given)",
                         status="assumed")]
        if prop.candidates is not None:
            meta.append(_literal(edge, "candidates", list(prop.candidates), status="assumed"))
        writer.put(meta)

    # 6. Hidden personas: the dated aka, the only persona-entry link.
    chunk_of: dict[tuple[int, int], int] = {}
    for r in ordered:
        for sentence in range(r.first_sentence, r.last_sentence + 1):
            chunk_of[(r.chapter, sentence)] = r.index
    identity_receipts: list[dict[str, Any]] = []
    pending: list[str] = []
    correlations = 0
    for ident in registry.identities:
        if not ident.is_persona:
            continue
        index = chunk_of.get(ident.reveal)
        if index is None:
            pending.append(ident.id)
            continue
        out = writer.porcelain.correlate(ident.id, ident.entry_id,
                                         evidence=ident.reveal_quote, at=times[index])
        identity_receipts.append({"verb": "correlate", "a": ident.id, "b": ident.entry_id, **out})
        correlations += out.get("outcome") == "correlated"

    # 7. Namesakes: distinct_from keeps the auto-gate off them.
    rejections = 0
    for a, b, _quote in registry.namesakes:
        out = writer.porcelain.reject(a, b)
        identity_receipts.append({"verb": "reject", "a": a, "b": b, **out})
        rejections += out.get("outcome") == "rejected"

    return BuildReceipt(
        skipped=tuple(writer.skipped), minted=tuple(allocator.order),
        handle_ids=dict(handle_ids), mentions=mentions, escapes=escapes,
        proposals=written, correlations=correlations, rejections=rejections,
        time_of=dict(times), chunk_spans=tuple(spans), pending_reveals=tuple(pending),
        identity_receipts=tuple(identity_receipts))
