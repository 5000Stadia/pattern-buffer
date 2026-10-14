"""Extraction: one labelled model call per chunk, in a pool (BUILD-LIBRARY-V1 §4).

The model sees the chunk's numbered sentences and its candidates (ids, types,
names, gates), never a later entry, and writes INGEST-V2's line grammar on
candidate ids or build handles, each line citing its sentence. Code checks
everything it receives:

- a line citing no sentence, or one outside the chunk, is refused;
- an id that is neither a candidate nor a build handle is refused;
- a line naming a candidate (in any id position) from a sentence before that
  candidate's gate is ``gate_refused``;
- a source (``doc=`` or ``src=``) is an id position too (r1.7): checked against
  the whole registry, privately (the prompt shows only the chunk's
  candidates), a registry id is gated like any other, an unknown ``person:``
  source is refused, and any other source (``doc:letter_1``) is document
  provenance and stands;
- a pick whose choice is not one of its candidates is refused, with its lines;
- every build handle a line uses must be declared by exactly one escape or
  pick, or the whole chunk is refused (r1.9: so is a handle declared twice). A
  declared handle no accepted line uses is not a refusal: a parsed one is
  dropped with a ``DroppedHandle`` receipt and never allocated, a malformed one
  is an ordinary per-item refusal (§4a).
"""

from __future__ import annotations

import copy
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, Sequence

from patternbuffer.build.grammar import (
    complete_id,
    grammar_problem,
    handle_number,
    id_positions,
    is_handle,
    parse_line,
    replace_ids,
)
from patternbuffer.build.labels import labelled_context
from patternbuffer.build.plan import Chunk
from patternbuffer.build.registry import Registry
from patternbuffer.build.text import Book
from patternbuffer.vocab import Vocabulary

logger = logging.getLogger(__name__)

EXTRACT_HEAD = "Extract world-state facts (build library, chunk)"

EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "lines": {"type": "array", "items": {"type": "string"}},
        "escapes": {"type": "array", "items": {
            "type": "object",
            "properties": {"handle": {"type": "string"}, "type": {"type": "string"},
                           "name": {"type": "string"},
                           "species": {"type": ["string", "null"]},
                           "quote": {"type": "string"}},
            "required": ["handle", "type", "name", "quote"]}},
        "picks": {"type": "array", "items": {
            "type": "object",
            "properties": {"handle": {"type": "string"}, "surface": {"type": "string"},
                           "candidates": {"type": "array", "items": {"type": "string"}},
                           "choice": {"type": "string"},
                           "evidence_quote": {"type": "string"}},
            "required": ["handle", "surface", "candidates", "choice", "evidence_quote"]}},
    },
    "required": ["lines"],
}

_RULES = """\
Write the passage's facts about the world as GRAMMAR LINES, one per line. Each
line cites the numbered sentence of the passage it comes from:

  s<N>|entity|attribute|value|flags

- s<N>: the sentence the fact comes from, numbered as the passage shows it
  ([sN]). Every line cites one sentence of this passage.
- entity: a candidate id below, or a handle new:<k> you declare (NEW and
  AMBIGUOUS below). Ids are written by the build, never by you.
- A candidate may be named only from its gate sentence on ("from sN"): a line
  naming it that cites an earlier sentence is refused.
- value: @<id> for an entity (a candidate id or a handle); JSON ({...}, [...],
  "...") for structured or delimiter-bearing literals (approximate quantities
  as bounds: {"gte": 40000}); ?{"policy": "invent_under_canon"} for an
  explicitly unresolved aspect; a bare scalar otherwise.
- flags (comma-separated, optional): t timeless (ONLY identity and structure:
  names, fixed adjacency); f=knows:<id> knowledge-frame row; s=<status> one of
  stated|observed|inferred|assumed; doc=<doc:id> document-claimed; cb=<id>
  caused-by. Do not write vf= or vt=: the build stamps each passage's time.
- Do not write kind, being_type or species: the build writes every candidate's
  and handle's type. What a person is at a time (prisoner, captain, widow) is
  role.
- Attributes: 'in' for all containment and location.
- CANON VS KNOWLEDGE: facts about the world are canon rows (no f= flag). Rows
  with f=knows:X are ADDITIONAL copies marking that X knows a fact, never
  replacements. A scene where A tells B an established fact yields knows:B rows
  only.
- Status: stated for asserted fact; inferred for a character's deduction;
  assumed for a working theory. Document claims carry doc=.
- Never invent; atmosphere and sensory texture are not facts.

NEW: a person, animal, creature, place, thing, group or event the passage
introduces that is no candidate gets a handle new:<k> (k = 0, 1, ... within
this passage), declared once in "escapes" as {"handle", "type", "name",
"species", "quote"}: type is one of person, animal, creature, place, object,
group, event; species is a free word such as dog, only for an animal or
creature, else null; quote is the passage's exact words that introduce it.

AMBIGUOUS: when a name in the passage fits two or more candidates, write none
of its facts on a candidate. Give it a handle, declared once in "picks" as
{"handle", "surface", "candidates", "choice", "evidence_quote"}: surface is the
passage's words for it; candidates are every candidate id it could be; choice
is the one you judge it is; evidence_quote is the passage's exact words that
support the choice. Its facts go on the handle: the build keeps your choice as
evidence, never as identity.

Every handle a line uses is declared exactly once, and every handle declared is
used by a line."""


@dataclass(frozen=True)
class Escape:
    """A chunk's declaration of a build handle for an entity not among its
    candidates. ``type`` is as the model wrote it; commit coerces a role word
    to ``person`` with that ``role`` (§5 k4)."""

    handle: str
    type: str
    name: str
    species: str | None
    quote: str


@dataclass(frozen=True)
class Pick:
    """A chunk's declaration of a build handle for an ambiguous surface: the
    candidates it could be and the model's ``choice``, kept as evidence on a
    proposed ``same_as``, never as identity."""

    handle: str
    surface: str
    candidates: tuple[str, ...]
    choice: str
    evidence_quote: str


@dataclass(frozen=True)
class Refusal:
    """One thing a chunk wrote that code refused: ``where`` in the model's
    output (``lines[3]``, ``escapes[0]``, ``picks[1]``), a fixed ``reason`` and
    a ``detail``."""

    where: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class DroppedHandle:
    """A parsed escape or pick no accepted line used (§4a, r1.9): dropped, never
    allocated, reported so a host can decide what it means. ``kind`` is
    ``"escape"`` or ``"pick"``; ``name`` is the escape's name or the pick's
    surface; ``candidates`` is ``()`` for an escape and the registry ids a pick
    stood between; ``reason`` is ``"unused_handle"``."""

    chunk: int
    handle: str
    kind: str
    name: str
    candidates: tuple[str, ...]
    reason: str = "unused_handle"


@dataclass(frozen=True)
class Attempt:
    """One model call made for a chunk (§4a): the ``error`` that attempt's answer
    gave the chunk (None when it was accepted) and ``raw``, the model's returned
    JSON (None when the call raised). Diagnostic only: never written to a
    world."""

    error: str | None
    raw: Any


@dataclass(frozen=True)
class ChunkResult:
    """One chunk's extraction (§4). ``items`` are fact items on candidate ids or
    build handles, each carrying the ``sentence`` it cites, in the chunk's own
    numbering (``1`` is ``first_sentence``); ``escapes`` and ``picks`` declare
    the handles; ``gate_refused`` and ``refused`` record what code dropped;
    ``error`` is set when the whole chunk is refused (its output is malformed,
    a handle is used undeclared or declared twice, or the model call failed).
    ``dropped_handles`` receipts the declarations no accepted line used
    (r1.9), and ``attempts`` holds one ``Attempt`` per model call, in order;
    commit reads neither. ``chapter``, ``first_sentence`` and
    ``last_sentence`` place the chunk; extract sets them from the plan.

    ``commit`` re-validates every result as extract checks it (each item's
    citation, and the effective gate of every id it names at that sentence)
    and refuses the whole build, before any write, for a refused chunk or
    anything extract would not have accepted."""

    index: int
    items: tuple[dict[str, Any], ...]
    escapes: tuple[Escape, ...]
    picks: tuple[Pick, ...]
    chapter: int | None = None
    first_sentence: int | None = None
    last_sentence: int | None = None
    gate_refused: tuple[Refusal, ...] = ()
    refused: tuple[Refusal, ...] = ()
    error: str | None = None
    dropped_handles: tuple[DroppedHandle, ...] = ()
    attempts: tuple[Attempt, ...] = ()


def build_prompt(chunk: Chunk, book: Book, vocabulary: Vocabulary | None = None) -> str:
    """The chunk's prompt: the stable head, the rules, (given a ``vocabulary``)
    its section of attribute names, then the chunk's candidates and its
    numbered passage. Without a vocabulary the prompt is what it always was,
    byte for byte (RECIPE-VOCAB-V1 §5)."""
    rows = []
    for c in chunk.candidates:
        kind = f"{c.type}, {c.species}" if c.species else c.type
        rows.append(f"{c.id} | {kind} | {'; '.join(c.names)} | from s{c.gate}")
    passage = book.numbered(chunk.chapter, chunk.first_sentence, chunk.last_sentence)
    section = f"{vocabulary.prompt_section()}\n\n" if vocabulary is not None else ""
    return (f"{EXTRACT_HEAD}\n\n{_RULES}\n\n{section}"
            "CANDIDATES (id | type | names | gate):\n"
            + ("\n".join(rows) if rows else "(none)")
            + f"\n\nPASSAGE (chunk {chunk.index:02d}, chapter {chunk.chapter}):\n{passage}\n")


def extract(plan: Sequence[Chunk], registry: Registry,
            model: Callable[[str, dict], Any], *, workers: int = 4,
            retries: int = 1, vocabulary: Vocabulary | None = None) -> list[ChunkResult]:
    """Extract every chunk of ``plan`` with ``model``, ``workers`` at a time
    (§4). Each call is labelled ``stage="extract"``, ``unit="chunk:NN"`` and runs
    in its own copy of the caller's context, taken inside that label. Returns
    one ``ChunkResult`` per chunk, in plan order. A model call that raises
    refuses its chunk (``error``) and is not retried here.

    ``retries`` is 0 or 1 (an exact int, never a bool; anything else raises
    ``ValueError`` before any call). With 1, a chunk whose call returned an
    answer that refused the whole chunk (``error`` set) is asked once more, in
    the same label and worker, with the same prompt plus the refusal named; the
    second result replaces the first (§4a). Every call is kept in
    ``ChunkResult.attempts``.

    ``vocabulary`` (RECIPE-VOCAB-V1 §5) adds the vocabulary's attribute names
    to every prompt; ``None`` leaves the prompt unchanged."""
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError(f"workers must be a positive integer, got {workers!r}")
    if type(retries) is not int or retries not in (0, 1):
        raise ValueError(f"retries must be the int 0 or 1, got {retries!r}")
    if vocabulary is not None and not isinstance(vocabulary, Vocabulary):
        raise ValueError(f"vocabulary must be a Vocabulary or None, got {vocabulary!r}")
    chunks = list(plan)
    for chunk in chunks:
        if not (registry.book.has_sentence(chunk.chapter, chunk.first_sentence)
                and registry.book.has_sentence(chunk.chapter, chunk.last_sentence)):
            raise ValueError(f"chunk {chunk.index} is not a span of the registry's text")
        unknown = [c.id for c in chunk.candidates if not registry.knows(c.id)]
        if unknown:
            raise ValueError(f"chunk {chunk.index} names ids the registry never minted: {unknown}")
    if not chunks:
        return []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(labelled_context("extract", f"chunk:{c.index:02d}").run,
                               _extract_chunk, c, registry, model, retries, vocabulary)
                   for c in chunks]
        return [f.result() for f in futures]


def retry_prompt(prompt: str, error: str) -> str:
    """``prompt`` plus the corrective closing paragraph for a refused answer,
    set off by a blank line."""
    return (f"{prompt.rstrip()}\n\nYour previous answer for this chunk was refused: {error}. "
            "Answer again from the same text, following every rule above.")


def _extract_chunk(chunk: Chunk, registry: Registry,
                   model: Callable[[str, dict], Any], retries: int = 0,
                   vocabulary: Vocabulary | None = None) -> ChunkResult:
    prompt = build_prompt(chunk, registry.book, vocabulary)
    attempts: list[Attempt] = []
    result, returned = _attempt(chunk, registry, model, prompt, attempts)
    if retries and returned and result.error is not None:
        logger.warning("extract: chunk %d refused (%s); asking once more",
                       chunk.index, result.error)
        result, _ = _attempt(chunk, registry, model, retry_prompt(prompt, result.error),
                             attempts)
    return replace(result, attempts=tuple(attempts))


def _attempt(chunk: Chunk, registry: Registry, model: Callable[[str, dict], Any],
             prompt: str, attempts: list[Attempt]) -> tuple[ChunkResult, bool]:
    """One model call for ``chunk``: its ``ChunkResult`` and whether the call
    returned (a raise is ``False``). Appends the call's ``Attempt``."""
    try:
        out = model(prompt, copy.deepcopy(EXTRACT_SCHEMA))
    except Exception as exc:  # the chunk is refused; the injected callable owns transport retries
        logger.warning("extract: chunk %d: model call failed: %s", chunk.index, exc)
        error = f"model call failed: {type(exc).__name__}: {exc}"
        attempts.append(Attempt(error, None))
        return _empty(chunk, error), False
    result = read_output(chunk, out, registry)
    attempts.append(Attempt(result.error, out))
    return result, True


def _empty(chunk: Chunk, error: str) -> ChunkResult:
    return ChunkResult(index=chunk.index, items=(), escapes=(), picks=(), chapter=chunk.chapter,
                       first_sentence=chunk.first_sentence,
                       last_sentence=chunk.last_sentence, error=error)


def read_output(chunk: Chunk, out: Any, registry: Registry) -> ChunkResult:
    """Check one model output against its chunk and return the ``ChunkResult``
    (§4): every rule in this module's docstring, applied by code. ``registry``
    is the one the chunk was planned from; only its source check reads past the
    chunk's candidates (r1.7)."""
    if not isinstance(out, Mapping) or not isinstance(out.get("lines"), list):
        return _empty(chunk, "malformed output: expected an object with a 'lines' list")
    raw_escapes = out.get("escapes") if out.get("escapes") is not None else []
    raw_picks = out.get("picks") if out.get("picks") is not None else []
    if not isinstance(raw_escapes, list) or not isinstance(raw_picks, list):
        return _empty(chunk, "malformed output: 'escapes' and 'picks' must be lists")

    gates = {c.id: c.gate for c in chunk.candidates}
    known = set(gates)
    count = chunk.sentence_count
    refused: list[Refusal] = []
    gate_refused: list[Refusal] = []

    # 1. The grammar and the citation.
    parsed: list[tuple[str, int, dict[str, Any]]] = []
    for n, raw in enumerate(out["lines"]):
        where = f"lines[{n}]"
        if not isinstance(raw, str):
            refused.append(Refusal(where, "malformed_line", "a line must be a string"))
            continue
        try:
            got = parse_line(raw)
        except ValueError as exc:
            refused.append(Refusal(where, "malformed_line", f"{exc}: {raw!r}"))
            continue
        if got is None:
            continue
        sentence, item = got
        problem_text = grammar_problem(item)
        if problem_text is not None:
            refused.append(Refusal(where, "malformed_line", f"{problem_text}: {raw!r}"))
            continue
        if not 1 <= sentence <= count:
            refused.append(Refusal(where, "citation_outside_chunk",
                                   f"s{sentence} is not a sentence of this chunk "
                                   f"(s1-s{count}): {raw!r}"))
            continue
        parsed.append((where, sentence, item))

    # 2. Every id: a handle, or a candidate cited from its gate on.
    used: dict[str, list[int]] = {}
    lines: list[tuple[str, int, dict[str, Any]] | None] = []
    for k, (where, sentence, item) in enumerate(parsed):
        mapping: dict[str, str] = {}
        problem: Refusal | None = None
        gated: Refusal | None = None
        for position, ident in id_positions(item):
            if is_handle(ident):
                used.setdefault(ident, []).append(k)
                continue
            if position == "source":
                found = registry.source_problem(ident, chunk.chapter, chunk.absolute(sentence))
                if found is not None and found[0] == "gate_refused":
                    gated = gated or Refusal(where, found[0], found[1])
                elif found is not None:
                    problem = problem or Refusal(where, found[0], found[1])
                continue
            done = complete_id(ident, known)
            if done is None:
                problem = problem or Refusal(where, "unknown_id",
                                             f"{position} {ident!r} is not a candidate "
                                             "of this chunk")
                continue
            mapping[ident] = done
            if sentence < gates[done] and gated is None:
                gated = Refusal(where, "gate_refused",
                                f"{position} {done} is gated at s{gates[done]}; "
                                f"the line cites s{sentence}")
        if problem is not None:
            refused.append(problem)
            lines.append(None)
        elif gated is not None:
            gate_refused.append(gated)
            lines.append(None)
        else:
            lines.append((where, sentence, replace_ids(item, mapping)))

    # 3. The declarations, and the handle balance. A handle used but undeclared
    #    or declared twice refuses the chunk; one declared and unused (counted
    #    over the lines that survived) is dropped or refused item by item below.
    declared: dict[str, tuple[str, int]] = {}
    twice: set[str] = set()
    for kind, raws in (("escapes", raw_escapes), ("picks", raw_picks)):
        for n, raw in enumerate(raws):
            handle = raw.get("handle") if isinstance(raw, Mapping) else None
            if not is_handle(handle):
                refused.append(Refusal(f"{kind}[{n}]", "malformed_declaration",
                                       f"no handle new:<k>: {raw!r}"))
                continue
            if handle in declared:
                twice.add(handle)
            else:
                declared[handle] = (kind, n)
    undeclared = sorted(set(used) - set(declared), key=handle_number)
    if twice or undeclared:
        problems = []
        if undeclared:
            problems.append(f"used but not declared: {', '.join(undeclared)}")
        if twice:
            problems.append(f"declared twice: {', '.join(sorted(twice, key=handle_number))}")
        return replace(_empty(chunk, "handles: " + "; ".join(problems)),
                       refused=tuple(refused), gate_refused=tuple(gate_refused))

    parsed_decls: dict[str, Escape | Pick] = {}
    bad_handles: set[str] = set()
    for handle, (kind, n) in sorted(declared.items(), key=lambda kv: handle_number(kv[0])):
        raw = (raw_escapes if kind == "escapes" else raw_picks)[n]
        where = f"{kind}[{n}]"
        if kind == "escapes":
            escape, reason = _escape(handle, raw)
            if escape is None:
                refused.append(Refusal(where, "malformed_escape", reason))
                bad_handles.add(handle)
            else:
                parsed_decls[handle] = escape
        else:
            pick, code, reason = _pick(handle, raw, known)
            if pick is None:
                refused.append(Refusal(where, code, reason))
                bad_handles.add(handle)
            else:
                parsed_decls[handle] = pick

    # 4. Lines on a refused declaration's handle go with it.
    items: list[dict[str, Any]] = []
    for line in lines:
        if line is None:
            continue
        where, sentence, item = line
        bad = sorted({i for _, i in id_positions(item) if i in bad_handles})
        if bad:
            refused.append(Refusal(where, "refused_handle",
                                   f"{', '.join(bad)} was refused with its declaration"))
            continue
        items.append({**item, "sentence": sentence})

    # 5. A parsed declaration no kept item uses is dropped, with a receipt.
    kept = {i for item in items for _, i in id_positions(item) if is_handle(i)}
    escapes: list[Escape] = []
    picks: list[Pick] = []
    dropped: list[DroppedHandle] = []
    for handle, decl in parsed_decls.items():
        if isinstance(decl, Escape):
            if handle in kept:
                escapes.append(decl)
            else:
                dropped.append(DroppedHandle(chunk.index, handle, "escape", decl.name, ()))
        elif handle in kept:
            picks.append(decl)
        else:
            dropped.append(DroppedHandle(chunk.index, handle, "pick", decl.surface,
                                         decl.candidates))
    return ChunkResult(index=chunk.index, items=tuple(items), escapes=tuple(escapes),
                       picks=tuple(picks), chapter=chunk.chapter,
                       first_sentence=chunk.first_sentence, last_sentence=chunk.last_sentence,
                       gate_refused=tuple(gate_refused), refused=tuple(refused),
                       dropped_handles=tuple(dropped))


def _text(raw: Mapping[str, Any], field: str) -> str | None:
    value = raw.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _escape(handle: str, raw: Mapping[str, Any]) -> tuple[Escape | None, str]:
    name, type_ = _text(raw, "name"), _text(raw, "type")
    if name is None or type_ is None:
        return None, f"an escape needs a non-empty name and type: {dict(raw)!r}"
    quote = raw.get("quote")
    if quote is not None and not isinstance(quote, str):
        return None, f"quote must be a string: {dict(raw)!r}"
    return Escape(handle=handle, type=type_, name=name, species=_text(raw, "species"),
                  quote=quote or ""), ""


def _pick(handle: str, raw: Mapping[str, Any],
          known: set[str]) -> tuple[Pick | None, str, str]:
    surface = _text(raw, "surface")
    cands = raw.get("candidates")
    choice = raw.get("choice")
    evidence = raw.get("evidence_quote")
    if (surface is None or not isinstance(cands, list)
            or not all(isinstance(c, str) for c in cands) or not isinstance(choice, str)
            or (evidence is not None and not isinstance(evidence, str))):
        return None, "malformed_pick", f"a pick needs a surface, candidates, a choice: {dict(raw)!r}"
    completed: list[str] = []
    for cand in cands:
        done = complete_id(cand, known)
        if done is None:
            return None, "pick_candidate_unknown", f"{cand!r} is not a candidate of this chunk"
        if done not in completed:
            completed.append(done)
    if len(completed) < 2:
        return None, "pick_not_ambiguous", f"a pick needs two or more candidates, got {cands!r}"
    chosen = complete_id(choice, known)
    if chosen is None or chosen not in completed:
        return None, "pick_choice_not_candidate", f"choice {choice!r} is not one of {completed}"
    return Pick(handle=handle, surface=surface, candidates=tuple(completed), choice=chosen,
                evidence_quote=evidence or ""), "", ""
