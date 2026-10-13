"""Leaks, false beliefs and points of view (GRADE-LEAKS-V1 §3).

Three deterministic, model-free sections that ``grade_book`` adds to its
scorecard, read from a world copy that is never written:

- ``leaks``: what was written before the text could know it. Alias leaks (a
  ``name``/``alias`` row from a chunk earlier than the alias's first chapter),
  identity leaks (a row written on a raw id bound to an entity inside a
  pre-reveal chunk) and registry leaks (pass-0 joined the pre-reveal alias to
  a later alias before any chunk ran). Identity is read **raw**: a row's
  ``entity`` exactly as written, never resolved through the final closure.
- ``beliefs``: a false belief never becomes canon; a correction ends at the
  corrected value.
- ``point_of_view``: who learns what, when.

Positions are the log's ``seq``. A chunk's rows are found from
``chunk_spans.json`` (``Pipeline.commit``, GRADE-LEAKS-V1 §1). Without spans,
nothing is inferred: the sections say ``"unmeasured"``.

``beliefs`` and ``point_of_view`` run on the narrative-exposure clock (r2.4):
"by chapter k" is a read as the log stood after chapter k's last chunk
(``asserted_as_of = hi(k)``), valid time unpinned. Story time is the model's
and is never inferred; the recorded cursor is not read by any check.

STAGE-MODELS-V1: grading a partial book (``through_chapter=N``) reads the world
through a ``Horizon``: every read is bounded at ``asserted_as_of = hi(N)``, and
identity (roots and closures) is read as of that same position, so nothing written
after chapter N's last chunk (a gate merge, an audit row) reaches a verdict. With
no horizon every call is the one it always was.
"""

from __future__ import annotations

import bisect
import logging
import re
from typing import Any, Iterable, Mapping, Sequence

from patternbuffer.model import (ATTR_PREFIX, CANON, EVENT_PREFIX, KNOWS_PREFIX, META_ATTRIBUTES,
                                 is_event_row)

try:
    from book_gold import book_normalize, fold_quotes
except ImportError:  # imported as evals.harness.grade_leaks
    from evals.harness.book_gold import book_normalize, fold_quotes

logger = logging.getLogger(__name__)

UNMEASURED = "unmeasured"

_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)*")
# Normative and complete (GRADE-LEAKS-V1 §3 step 3): an alias that is exactly
# one of these tokens takes no part in chunk classification.
STOPLIST = frozenset(
    "a about after all an and any as at be before but by can for from he her here him his i if "
    "in is it its me my no nor not now of on one or our she so than that the them then there "
    "they this to up us was we were what when who will with yet you your".split())
SHORT_TOKEN = 3     # an alias of exactly one token of this many characters or fewer is left out


def tokens(text: str) -> list[str]:
    """The chunk-classification tokenizer: quote folding and lowercase, no
    article stripping (``tokens("The One") == ["the", "one"]``), so
    ``o'brien`` is one token and ``copper-hand`` two."""
    return _TOKEN.findall(fold_quotes(text).lower())


def is_common_word_alias(alias: str) -> bool:
    """Whether ``alias`` is left out of chunk classification: no tokens, or
    exactly one token that is three characters or fewer or is on the stoplist."""
    toks = tokens(alias)
    return not toks or (len(toks) == 1 and (len(toks[0]) <= SHORT_TOKEN or toks[0] in STOPLIST))


def contains_run(haystack: Sequence[str], needle: Sequence[str]) -> bool:
    """Whether ``needle`` occurs as a contiguous run in ``haystack``."""
    n = len(needle)
    return n > 0 and any(list(haystack[i:i + n]) == list(needle)
                         for i in range(len(haystack) - n + 1))


# ------------------------------------------------------------------ spans


class Spans:
    """``chunk_spans.json`` read for lookups: a row's source chunk, a chapter's time.

    ``through`` (STAGE-MODELS-V1) ends the chapter clock at that chapter: ``chapters``,
    ``marks`` and ``hi`` know nothing later, while ``chunk_of`` still places every row."""

    def __init__(self, doc: Mapping[str, Any], through: int | None = None) -> None:
        self.chunks: list[dict[str, Any]] = list(doc["chunks"])
        spans = sorted(((c["seq"][0], c["seq"][1], c["chunk"], c["chapter"])
                        for c in self.chunks if c.get("seq")), key=lambda t: t[0])
        self._los = [s[0] for s in spans]
        self._spans = spans
        self.chapter_of_chunk: dict[int, int] = {c["chunk"]: c["chapter"] for c in self.chunks}
        self.chapters: list[int] = sorted(c for c in set(self.chapter_of_chunk.values())
                                          if through is None or c <= through)
        #: chapter 0 is the seed: the log head before the first chunk
        self.head0: int = (spans[0][0] - 1) if spans else 0
        self._hi: dict[int, int] = {0: self.head0}
        best = self.head0
        for chapter in self.chapters:
            best = max([best] + [s[1] for s in spans if s[3] == chapter])
            self._hi[chapter] = best      # a chapter with no rows keeps the previous hi

    def hi(self, chapter: int) -> int:
        """``hi(k)``: the greatest ``seq`` in the spans of chapter ``k``'s chunks (the
        previous chapter's ``hi`` when it appended nothing; chapter 0, or any chapter
        before the first, is the log head before the first chunk)."""
        known = [c for c in self._hi if c <= chapter]
        return self._hi[max(known)]

    def marks(self, lo: int | None = None, hi: int | None = None, *, lo_inclusive: bool = True,
              hi_inclusive: bool = True, seed: bool = False) -> list[int]:
        """Log positions ``hi(c)`` for the chapters ``c`` within the bounds (an open end is
        ``None``), plus the seed position when ``seed``."""
        out = [self._hi[0]] if seed else []
        for chapter in self.chapters:
            if lo is not None and (chapter < lo or (chapter == lo and not lo_inclusive)):
                continue
            if hi is not None and (chapter > hi or (chapter == hi and not hi_inclusive)):
                continue
            out.append(self._hi[chapter])
        return out

    def chunk_of(self, seq: int) -> int | None:
        """The chunk whose inclusive span holds ``seq``; ``None`` for a seed,
        gate or audit row outside every span."""
        i = bisect.bisect_right(self._los, seq) - 1
        if i >= 0 and self._spans[i][0] <= seq <= self._spans[i][1]:
            return self._spans[i][2]
        return None

    def chapter_of(self, seq: int) -> int | None:
        chunk = self.chunk_of(seq)
        return None if chunk is None else self.chapter_of_chunk[chunk]


# ------------------------------------------------------------------ horizon


class Horizon:
    """How a grader reads a world. With ``bound=None`` (the full book) every method is the
    call the grader always made. With ``bound`` (``hi(N)`` of a partial book) rows are read
    ``asserted_as_of`` that position (or earlier, where a caller asks for an earlier mark),
    roots and closures come from ``ident`` as of ``bound``, and a fold runs over the
    ``bound`` closure's members, never the end-of-run closure ``World.state`` would use."""

    def __init__(self, world: Any, ident: Any, bound: int | None = None) -> None:
        self.world, self.ident, self.bound = world, ident, bound

    def resolve(self, entity: str) -> str:
        return self.ident.resolve(entity) if self.bound is None else self.ident.resolve(entity, self.bound)

    def closure(self, entity: str) -> set[str]:
        return self.ident.closure(entity) if self.bound is None else self.ident.closure(entity, self.bound)

    def visible(self, **kw: Any) -> list[Any]:
        """``buffer.visible``, bounded at the horizon unless the caller gave an earlier bound."""
        if self.bound is not None:
            kw["asserted_as_of"] = min(kw["asserted_as_of"], self.bound) \
                if kw.get("asserted_as_of") is not None else self.bound
        return self.world.buffer.visible(**kw)

    def state(self, root: str, attribute: str, frame: Any = CANON, *, valid_as_of: float | None = None,
              asserted_as_of: int | None = None) -> Any:
        """The fold of ``attribute`` on ``root``'s closure. ``asserted_as_of=None`` is the end
        of what the grader may see: the head, or the horizon."""
        if self.bound is None:
            return self.world.state(root, attribute, frame, valid_as_of=valid_as_of,
                                    asserted_as_of=asserted_as_of)
        at = self.bound if asserted_as_of is None else min(asserted_as_of, self.bound)
        idx = self.world.indexes
        return idx._fold_over_closure(sorted(self.closure(root)), attribute,
                                      idx.fold_attribute(attribute), frame, valid_as_of, at)

    def event_values(self, root: str, attribute: str, frame: Any,
                     asserted_as_of: int | None) -> tuple[Any, tuple[Any, ...]]:
        """An event's own ``attribute`` (the read a fold serving nothing falls back to):
        ``(winner row or None, every value)``. Bounded, it reads the event rows of the
        ``bound`` closure; unbounded it is ``World.indexes.event_attribute``."""
        if self.bound is None:
            fold = self.world.indexes.event_attribute(root, attribute, frame, None, asserted_as_of)
            return fold.winner, tuple(fold.values)
        if attribute in META_ATTRIBUTES:
            return None, ()
        at = self.bound if asserted_as_of is None else min(asserted_as_of, self.bound)
        stored = sorted(m for m in self.closure(root) if m.startswith(EVENT_PREFIX))
        if not stored:
            return None, ()
        rows = [r for r in self.world.buffer.visible(entity_in=stored, attribute=attribute,
                                                     frame=frame, asserted_as_of=at)
                if is_event_row(r)]
        winner = self.world.indexes.event_pick(rows)
        return winner, tuple(r.value for r in rows)


# -------------------------------------------------------------- raw reading


def _is_entity_row(row: Any) -> bool:
    return not row.entity.startswith("a:") and not row.entity.startswith(ATTR_PREFIX)


class RawIds:
    """The raw mapping (§3 steps 1-2): each raw id R to the key entity E it
    names, read from R's own canon ``name`` and ``alias`` rows."""

    def __init__(self, world: Any, graded: Mapping[str, Any], bound: int | None = None) -> None:
        self.alias_entities: dict[str, set[str]] = {}
        for key, ent in graded["entities"].items():
            for alias in ent["aliases"]:
                self.alias_entities.setdefault(book_normalize(alias), set()).add(key)
        #: raw id -> [(seq, normalized value)] of its canon name/alias rows, in log order
        self.names: dict[str, list[tuple[int, str]]] = {}
        extra = {} if bound is None else {"asserted_as_of": bound}
        for row in world.buffer.visible(attribute_in=["name", "alias"], frame=CANON, **extra):
            if _is_entity_row(row) and isinstance(row.value, str):
                self.names.setdefault(row.entity, []).append((row.seq, book_normalize(row.value)))
        self._map: dict[str, tuple[str, str | None]] = {}

    def status(self, raw: str) -> tuple[str, str | None]:
        """``("mapped", E)``, ``("ambiguous", None)`` or ``("unmapped", None)``.

        ``map(R) = E`` when every name of R that matches any graded alias
        matches one of E's, and at least one does. If no single entity fits but
        some name matched, R is ambiguous; if none matched, unmapped."""
        if raw not in self._map:
            matched = [self.alias_entities[n] for _, n in self.names.get(raw, ())
                       if n in self.alias_entities]
            if not matched:
                self._map[raw] = ("unmapped", None)
            else:
                common = set.intersection(*matched)
                self._map[raw] = ("mapped", next(iter(common))) if len(common) == 1 \
                    else ("ambiguous", None)
        return self._map[raw]

    def raw_ids_of(self, key: str) -> list[str]:
        """Raw ids that map to key entity ``key``."""
        return sorted(r for r in self.names if self.status(r) == ("mapped", key))

    def bound_at(self, raw: str, aliases: Iterable[str]) -> int | None:
        """``b(R, E)``: the lowest ``seq`` of a name/alias row on ``raw`` matching one of
        ``aliases`` (normalized); ``None`` when never bound."""
        want = {book_normalize(a) for a in aliases}
        hits = [seq for seq, n in self.names.get(raw, ()) if n in want]
        return min(hits) if hits else None


# ------------------------------------------------------------------- leaks


def _row_view(row: Any, spans: Spans) -> dict[str, Any]:
    chunk = spans.chunk_of(row.seq)
    return {"seq": row.seq, "entity": row.entity, "attribute": row.attribute,
            "value": row.value if isinstance(row.value, (str, int, float, bool, type(None))) else str(row.value),
            "frame": row.frame, "chunk": chunk, "chapter": spans.chapter_of_chunk.get(chunk)}


def grade_leaks(world: Any, graded: Mapping[str, Any], spans: Spans | None,
                chunk_texts: Mapping[int, str] | None, pass0: Any | None,
                raw: RawIds | None = None, bound: int | None = None) -> dict[str, Any] | str:
    """The ``leaks`` section (§3). ``pass0`` is the pass-0 ``WorldRegistry`` (or ``None``),
    ``chunk_texts`` the text of each chunk by id (or ``None``)."""
    if spans is None:
        return UNMEASURED
    raw = raw or RawIds(world, graded, bound)
    rows = [r for r in world.buffer.visible(**({} if bound is None else {"asserted_as_of": bound}))
            if _is_entity_row(r)]
    entities = graded["entities"]
    afc: Mapping[str, Mapping[str, int]] = graded.get("alias_first_chapter") or {}

    # ---- alias leaks
    first_of: dict[str, int] = {}
    for key, by_alias in afc.items():
        for alias, chapter in by_alias.items():
            n = book_normalize(alias)
            first_of[n] = min(chapter, first_of.get(n, chapter))
    alias_rows = []
    for r in rows:
        if r.attribute in ("name", "alias") and r.frame == CANON and isinstance(r.value, str):
            first = first_of.get(book_normalize(r.value))
            chapter = spans.chapter_of(r.seq)
            if first is not None and chapter is not None and chapter < first:
                alias_rows.append({**_row_view(r, spans), "first_chapter": first})
    alias_leaks: dict[str, Any] = {
        "measured": bool(afc), "count": len(alias_rows), "rows": alias_rows}
    if not afc:
        alias_leaks["reason"] = "the graded key carries no alias_first_chapter"

    # ---- identity leaks, per same_as entry
    chunk_toks: dict[int, list[str]] | None = None
    unclassified: list[int] = []
    if chunk_texts is not None:
        chunk_toks = {}
        for chunk in spans.chapter_of_chunk:
            if chunk in chunk_texts:
                chunk_toks[chunk] = tokens(chunk_texts[chunk])
            else:
                unclassified.append(chunk)
    rows_by_chunk: dict[int, list[Any]] = {}
    for r in rows:
        chunk = spans.chunk_of(r.seq)
        if chunk is not None:
            rows_by_chunk.setdefault(chunk, []).append(r)

    excluded: list[dict[str, str]] = []
    seen_excluded: set[tuple[str, str]] = set()
    entries: list[dict[str, Any]] = []
    all_leak_seqs: set[int] = set()
    all_ambiguous: set[int] = set()
    all_unmapped: set[int] = set()
    registry_total = 0
    for same in graded.get("same_as", []):
        key, pre, reveal = same["entity"], same["alias"], same["chapter"]
        pre_norm = book_normalize(pre)
        others = [a for a in entities.get(key, {}).get("aliases", []) if book_normalize(a) != pre_norm]
        for alias in [pre] + others:
            if is_common_word_alias(alias) and (key, alias) not in seen_excluded:
                seen_excluded.add((key, alias))
                excluded.append({"entity": key, "alias": alias,
                                 "reason": "common-word alias: not used to classify chunks"})
        entry: dict[str, Any] = {"id": same.get("id"), "entity": key, "pre_alias": pre,
                                 "reveal_chapter": reveal}
        # pre-reveal chunks
        pre_chunks: list[int] = []
        if chunk_toks is not None and not is_common_word_alias(pre):
            pre_toks = tokens(pre)
            other_toks = [tokens(a) for a in others if not is_common_word_alias(a)]
            for chunk, toks in sorted(chunk_toks.items()):
                if (spans.chapter_of_chunk[chunk] < reveal and contains_run(toks, pre_toks)
                        and not any(contains_run(toks, o) for o in other_toks)):
                    pre_chunks.append(chunk)
        entry["pre_reveal_chunks"] = pre_chunks
        if chunk_toks is None:
            entry.update(chunk_leaks=UNMEASURED, rows=[], chunk_leak_rows=None,
                         first_leaking_chapter=None, ambiguous_rows=None, unmapped_rows=None)
        else:
            leaks, ambiguous, unmapped = [], set(), set()
            for chunk in pre_chunks:
                for r in rows_by_chunk.get(chunk, ()):
                    kind, mapped = raw.status(r.entity)
                    if kind == "ambiguous":
                        ambiguous.add(r.seq)
                    elif kind == "unmapped":
                        unmapped.add(r.seq)
                    elif mapped == key:
                        b = raw.bound_at(r.entity, others)
                        if b is not None and b <= r.seq:
                            leaks.append(_row_view(r, spans))
            leaks.sort(key=lambda v: v["seq"])
            entry.update(rows=leaks, chunk_leak_rows=len(leaks),
                         first_leaking_chapter=min((v["chapter"] for v in leaks), default=None),
                         ambiguous_rows=len(ambiguous), unmapped_rows=len(unmapped))
            all_leak_seqs |= {v["seq"] for v in leaks}
            all_ambiguous |= ambiguous
            all_unmapped |= unmapped
        # registry leak: pass-0 joined the pre-reveal alias to a later alias
        if pass0 is None:
            entry.update(registry_leak=UNMEASURED, registry_leak_ids=[])
        elif not afc:
            entry.update(registry_leak=UNMEASURED, registry_leak_ids=[],
                         registry_reason="the graded key carries no alias_first_chapter")
        else:
            later = [a for a in others if afc.get(key, {}).get(a, -1) >= reveal]
            ids = []
            for eid, card in sorted(pass0.entities.items()):
                strings = {book_normalize(s) for s in list(card.names) + list(card.aliases)}
                if pre_norm in strings and any(book_normalize(a) in strings for a in later):
                    ids.append(eid)
            entry.update(registry_leak=bool(ids), registry_leak_ids=ids)
            registry_total += bool(ids)
        entries.append(entry)

    identity_leaks = {
        "entries": entries,
        "chunk_leak_rows": len(all_leak_seqs) if chunk_toks is not None else None,
        "registry_leaks": registry_total if pass0 is not None and afc else None,
        "ambiguous_rows": len(all_ambiguous) if chunk_toks is not None else None,
        "unmapped_rows": len(all_unmapped) if chunk_toks is not None else None,
        "unclassified_chunks": sorted(unclassified),
        "excluded_aliases": excluded,
    }
    parts = [alias_leaks["count"] if alias_leaks["measured"] else None,
             identity_leaks["chunk_leak_rows"], identity_leaks["registry_leaks"]]
    return {
        "alias_leaks": alias_leaks, "identity_leaks": identity_leaks,
        "total": sum(p for p in parts if p is not None),
        "unmeasured_parts": [n for n, p in zip(("alias_leaks", "chunk_leaks", "registry_leaks"), parts)
                             if p is None],
        "target": 0,
    }


# ------------------------------------------------------------ fact reading


def _lit(value: Any) -> Any:
    """A literal for comparison: strings fold quotes, lowercase and collapse
    whitespace; every other scalar compares as itself."""
    return " ".join(fold_quotes(value).lower().split()) if isinstance(value, str) else value


class Reader:
    """Reads a fact form from a world: where its keys map, whether a frame holds it at a time.

    ``horizon`` (STAGE-MODELS-V1) bounds every read and every identity lookup at a partial
    book's last position; without one the reader is as it always was."""

    def __init__(self, world: Any, ident: Any, raw: RawIds, spans: Spans,
                 horizon: Horizon | None = None) -> None:
        self.world, self.ident, self.raw, self.spans = world, ident, raw, spans
        self.h = horizon or Horizon(world, ident)
        self._rows: dict[tuple[tuple[str, ...], str], bool] = {}

    def roots(self, key: str) -> list[str]:
        """Closure representatives of the raw ids that map to key entity ``key``."""
        return sorted({self.h.resolve(r) for r in self.raw.raw_ids_of(key)})

    def resolve(self, fact: Mapping[str, Any]) -> dict[str, Any]:
        """A fact form with its keys mapped to built ids; ``problems`` lists
        what failed to map (``entity``, ``value``, ``attribute``)."""
        problems: list[str] = []
        roots = self.roots(fact["entity"])
        if not roots:
            problems.append("entity")
        value = fact["value"]
        value_roots: set[str] | None = None
        literal: Any = None
        if "entity" in value:
            value_roots = set(self.roots(value["entity"]))
            if not value_roots:
                problems.append("value")
        else:
            literal = _lit(value["literal"])
        attribute = self.world.canonical_attribute(fact["attribute"])
        if roots and not self._attribute_seen(roots, attribute):
            problems.append("attribute")
        return {"roots": roots, "attribute": attribute, "value_roots": value_roots,
                "literal": literal, "problems": problems, "form": fact}

    def _attribute_seen(self, roots: Sequence[str], attribute: str) -> bool:
        members: set[str] = set()
        for r in roots:
            members |= self.h.closure(r)
        return bool(self.h.visible(entity_in=sorted(members), attribute=attribute))

    def _matches(self, resolved: Mapping[str, Any], value: Any) -> bool:
        if resolved["value_roots"] is not None:
            return isinstance(value, str) and self.h.resolve(value) in resolved["value_roots"]
        return _lit(value) == resolved["literal"]

    def merged_frame(self, observer: str) -> Any:
        """The ``knows:`` frame of ``observer`` read with ``frame_scope="merged"``: the frame
        itself, then the frames of every other member of its closure at the end of the run
        (at the horizon, for a partial book)."""
        frame = KNOWS_PREFIX + observer
        others = sorted(KNOWS_PREFIX + m for m in self.h.closure(observer) if m != observer)
        return (frame, *others) if others else frame

    def holds(self, resolved: Mapping[str, Any], asserted_as_of: int | None, *,
              observer: Sequence[str] | None = None) -> bool:
        """Whether the fact is served as the log stood at ``asserted_as_of`` (``None``: the end),
        valid time unpinned: the canon fold, or, with ``observer`` (closure representatives
        of a believer), each merged ``knows:`` frame. A set-valued key holds it when any member does."""
        for root in resolved["roots"]:
            for who in (observer if observer is not None else [None]):
                frame = CANON if who is None else self.merged_frame(who)
                fold = self.h.state(root, resolved["attribute"], frame, asserted_as_of=asserted_as_of)
                winner, values = fold.winner, tuple(fold.values)
                if winner is None:     # an event's own attributes come from its record
                    winner, values = self.h.event_values(root, resolved["attribute"], frame,
                                                         asserted_as_of)
                if winner is None or winner.value_type == "unresolved":
                    continue
                if any(self._matches(resolved, v) for v in [winner.value, *values]):
                    return True
        return False

    def holds_ever(self, resolved: Mapping[str, Any], marks: Iterable[int], *,
                   observer: Sequence[str] | None = None) -> bool:
        return any(self.holds(resolved, m, observer=observer) for m in marks)


def _unmatched(*resolved: Mapping[str, Any] | None) -> list[str]:
    return sorted({p for r in resolved if r for p in r["problems"]})


def grade_beliefs(world: Any, graded: Mapping[str, Any], reader: Reader | None) -> dict[str, Any] | str:
    """The ``beliefs`` section (§3): false beliefs never canon, held by the believer;
    corrections end at the corrected value and never return to the claim."""
    if reader is None:
        return UNMEASURED
    spans = reader.spans
    belief_items = []
    for entry in graded.get("beliefs", []):
        res = reader.resolve(entry["fact"])
        who = reader.roots(entry["who"])
        problems = _unmatched(res) + (["who"] if not who else [])
        item: dict[str, Any] = {"id": entry["id"], "who": entry["who"],
                                "from_chapter": entry["from_chapter"],
                                "corrected_chapter": entry["corrected_chapter"]}
        if problems:
            item.update(status="unmatched", unmatched=sorted(set(problems)),
                        false_in_canon=None, held_by_believer=None)
        else:
            canon_times = spans.marks(entry["from_chapter"])
            held_times = spans.marks(entry["from_chapter"], entry["corrected_chapter"],
                                     hi_inclusive=entry["corrected_chapter"] is None)
            item.update(status="measured", unmatched=[],
                        false_in_canon=int(reader.holds_ever(res, canon_times)),
                        held_by_believer=int(reader.holds_ever(res, held_times, observer=who)))
        belief_items.append(item)
    measured = [i for i in belief_items if i["status"] == "measured"]
    correction_items = []
    for entry in graded.get("corrections", []):
        claim = reader.resolve(entry["as_fact"]) if entry.get("as_fact") else None
        fixed = reader.resolve(entry["corrected_as_fact"]) if entry.get("corrected_as_fact") else None
        item = {"id": entry["id"], "stated_chapter": entry["stated_chapter"],
                "corrected_chapter": entry["corrected_chapter"],
                "ends_correct": None, "claim_after_correction": None, "unmatched": []}
        if fixed is not None:
            if fixed["problems"]:
                item["unmatched"] += [f"corrected:{p}" for p in fixed["problems"]]
            else:
                item["ends_correct"] = int(reader.holds(fixed, None))
        if claim is not None:
            if claim["problems"]:
                item["unmatched"] += [f"claim:{p}" for p in claim["problems"]]
            else:
                item["claim_after_correction"] = int(reader.holds_ever(
                    claim, spans.marks(entry["corrected_chapter"], lo_inclusive=False)))
        correction_items.append(item)
    ends = [i for i in correction_items if i["ends_correct"] is not None]
    after = [i for i in correction_items if i["claim_after_correction"] is not None]
    return {
        "false_beliefs": {
            "entries": len(belief_items), "measured": len(measured),
            "unmatched": len(belief_items) - len(measured),
            "false_in_canon": sum(i["false_in_canon"] for i in measured), "target": 0,
            "held_by_believer": sum(i["held_by_believer"] for i in measured),
            "held_by_believer_rate": _rate(sum(i["held_by_believer"] for i in measured),
                                           len(belief_items)),
            "items": belief_items},
        "corrections": {
            "entries": len(correction_items),
            "ends_correct": sum(i["ends_correct"] for i in ends),
            "ends_correct_entries": sum(1 for e in graded.get("corrections", [])
                                        if e.get("corrected_as_fact")),
            "ends_correct_rate": _rate(sum(i["ends_correct"] for i in ends),
                                       sum(1 for e in graded.get("corrections", [])
                                           if e.get("corrected_as_fact"))),
            "claim_after_correction": sum(i["claim_after_correction"] for i in after), "target": 0,
            "unmatched": sum(1 for i in correction_items if i["unmatched"]),
            "items": correction_items},
    }


def _rate(num: int, den: int) -> float | None:
    return None if not den else round(num / den, 4)


def grade_point_of_view(world: Any, graded: Mapping[str, Any],
                        reader: Reader | None) -> dict[str, Any] | str:
    """The ``point_of_view`` section (§3): ``learns`` entries held by the end and not before
    their chapter; ``never_learns`` entries never held."""
    if reader is None:
        return UNMEASURED
    spans = reader.spans
    learns, never = [], []
    for entry in graded.get("knowledge", []):
        res = reader.resolve(entry["fact"])
        who = reader.roots(entry["who"])
        problems = sorted(set(_unmatched(res) + (["who"] if not who else [])))
        item: dict[str, Any] = {"id": entry["id"], "who": entry["who"], "chapter": entry.get("chapter")}
        if problems:
            item.update(status="unmatched", unmatched=problems)
        elif entry["mode"] == "never_learns":
            item.update(status="measured", unmatched=[],
                        violation=int(reader.holds_ever(res, spans.marks(seed=True), observer=who)))
        else:
            chapter = entry.get("chapter")
            early = None if chapter is None else int(reader.holds_ever(
                res, spans.marks(hi=chapter, hi_inclusive=False, seed=True), observer=who))
            item.update(status="measured", unmatched=[], too_early=early,
                        held_by_end=int(reader.holds(res, None, observer=who)))
        (never if entry["mode"] == "never_learns" else learns).append(item)
    held = sum(i["held_by_end"] for i in learns if i["status"] == "measured")
    return {
        "learns": {"entries": len(learns), "held": held, "held_rate": _rate(held, len(learns)),
                   "learned_too_early": sum(i.get("too_early") or 0 for i in learns
                                            if i["status"] == "measured"),
                   "unmatched": sum(1 for i in learns if i["status"] == "unmatched"),
                   "items": learns},
        "never_learns": {"entries": len(never), "violations": sum(i.get("violation", 0) for i in never),
                         "target": 0,
                         "unmatched": sum(1 for i in never if i["status"] == "unmatched"),
                         "items": never},
    }


def grade_sections(world: Any, ident: Any, graded: Mapping[str, Any], *, spans: Mapping[str, Any] | None,
                   chunk_texts: Mapping[int, str] | None = None, pass0: Any | None = None,
                   through_chapter: int | None = None) -> dict[str, Any]:
    """``{"leaks", "beliefs", "point_of_view"}`` for ``grade_book``. Without ``spans`` all
    three are ``"unmeasured"``. ``through_chapter`` (STAGE-MODELS-V1) grades a partial book:
    the chapter clock ends at that chapter and every read is bounded at its ``hi``."""
    if spans is None:
        return {"leaks": UNMEASURED, "beliefs": UNMEASURED, "point_of_view": UNMEASURED}
    span_index = Spans(spans, through=through_chapter)
    bound = None if through_chapter is None else span_index.hi(through_chapter)
    raw = RawIds(world, graded, bound)
    reader = Reader(world, ident, raw, span_index, Horizon(world, ident, bound))
    return {
        "leaks": grade_leaks(world, graded, span_index, chunk_texts, pass0, raw, bound),
        "beliefs": grade_beliefs(world, graded, reader),
        "point_of_view": grade_point_of_view(world, graded, reader),
    }
