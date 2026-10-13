"""MERGE-GATE-VERB-V1: the measured merge gate, as one shared implementation.

Two callers use this module: the eval harness (``evals/harness/merge_gate.py``,
MERGE-GATE-V1: lexical candidates, then host merges) and the report-only engine
verb ``Porcelain.merge_gate`` (:func:`report`), which a host calls with the
pairs it chose. The question (the prompt and the ``merge_gate`` schema), the
envelope (``{"batch", "pairs"}`` with sides ``{id, kind, names, aliases,
context}``), the validation of an answer, the components of ``same`` verdicts and
the election of a representative live here once.

The engine core never imports this module: only the porcelain verb does, lazily.
Nothing here writes to a world: the verb returns verdicts, and a host merges
through ``porcelain.merge`` itself.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from patternbuffer.model import CANON, task_request, task_schema

logger = logging.getLogger(__name__)

TASK_MERGE_GATE = "merge_gate"
DEFAULT_BATCH_SIZE = 25
MAX_PAIRS = 500
VERDICTS = ("same", "different", "unsure")
CONTEXT_SENTENCES = 2
CONTEXT_SENTENCE_CHARS = 400

_PROMPT = """\
You are checking whether pairs of entity cards from one story's world registry
name the SAME thing. Each pair has side "a" and side "b": a kind, the names and
aliases the registry holds for it, and up to two sentences of the story that
mention it. Decide each pair on that evidence alone.

For every pair give one verdict:
- "same": both cards are certainly one and the same thing (one person, one
  place, one object). For "same" also give "keep": "a" or "b", the side whose
  name is the most complete.
- "different": they are certainly two different things.
- "unsure": anything else. When in doubt, "unsure": a wrong "same" cannot be
  undone cheaply, a missed one can be revisited.

A shared word is not evidence by itself ("the vault" may be two vaults). Answer
with ONE entry per pair_id, using exactly the pair_ids given:

{{"verdicts": [{{"pair_id": "p0001", "verdict": "same", "keep": "a", "reason": "one short sentence"}}, ...]}}

BATCH {batch}: {count} pair(s)
{pairs}
"""

_SCHEMA: dict[str, Any] = {
    "title": TASK_MERGE_GATE,
    "type": "object",
    "properties": {"verdicts": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "pair_id": {"type": "string"},
            "verdict": {"type": "string", "enum": list(VERDICTS)},
            "keep": {"type": "string", "enum": ["a", "b"]},
            "reason": {"type": "string"},
        },
        "required": ["pair_id", "verdict"],
    }}},
    "required": ["verdicts"],
}


# ----------------------------------------------------------------- reading


def _is_class(w: Any, members: Sequence[str], cls: str) -> bool:
    """A closure is of class ``cls`` (``person``, ``event``) when any member's id
    is in the ``cls:`` namespace or any member's folded canon ``kind`` is ``cls``."""
    for m in members:
        if m.partition(":")[0] == cls:
            return True
        winner = getattr(w.state(m, "kind"), "winner", None)
        if winner is not None and str(winner.value).strip().lower() == cls:
            return True
    return False


def _is_person(w: Any, members: Sequence[str]) -> bool:
    return _is_class(w, members, "person")


def read_sides(w: Any, ids: Sequence[str] | None = None) -> dict[str, dict[str, Any]]:
    """Every closure that carries a canon ``name`` or ``alias`` row, keyed by its
    served representative: ``{id, kind, members, names, aliases, person, event}``.

    Names and aliases are the world's own rows over the whole closure (generated
    rows excluded: invention is never evidence), sorted and de-duplicated. With
    ``ids``, only the closures those ids belong to are read."""
    wanted = None if ids is None else {w.registry.resolve(i) for i in ids}
    rows = w.buffer.visible(attribute_in=["name", "alias"], frame=CANON)
    by_rep: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"name": set(), "alias": set()})
    for r in rows:
        if r.status == "generated" or not isinstance(r.value, str) or not r.value.strip():
            continue
        rep = w.registry.resolve(r.entity)
        if wanted is not None and rep not in wanted:
            continue
        by_rep[rep][r.attribute].add(r.value)
    sides: dict[str, dict[str, Any]] = {}
    for rep, strings in sorted(by_rep.items()):
        members = sorted(w.registry.closure(rep))
        winner = getattr(w.state(rep, "kind"), "winner", None)
        sides[rep] = {
            "id": rep,
            "kind": str(winner.value) if winner is not None else rep.partition(":")[0],
            "members": members,
            "names": sorted(strings["name"]),
            "aliases": sorted(strings["alias"] - strings["name"]),
            "person": _is_person(w, members),
            "event": _is_class(w, members, "event"),
        }
    return sides


# ---------------------------------------------------------------- the call


def _side_payload(s: Mapping[str, Any], context: Sequence[str]) -> dict[str, Any]:
    return {"id": s["id"], "kind": s["kind"], "names": list(s["names"]),
            "aliases": list(s["aliases"]), "context": list(context)}


def pair_id(n: int) -> str:
    """``p0001``, ``p0002``, ... (one-based, over the whole sorted pair list)."""
    return f"p{n:04d}"


def check_batch_size(batch_size: Any) -> None:
    """Raise ``ValueError`` unless ``batch_size`` is a positive int (not a bool)."""
    if not (isinstance(batch_size, int) and not isinstance(batch_size, bool) and batch_size >= 1):
        raise ValueError(f"batch_size must be a positive integer, got {batch_size!r}")


def make_batches(pairs: Sequence[tuple[str, str]],
                 sides: Mapping[str, Mapping[str, Any]],
                 context: Mapping[str, Sequence[str]],
                 batch_size: int = DEFAULT_BATCH_SIZE) -> list[dict[str, Any]]:
    """The requests, one per batch: ``{"batch": n, "pairs": [...]}`` (batch
    numbers are one-based). Each pair is ``{"pair_id", "a", "b"}`` with side
    payloads ``{id, kind, names, aliases, context}``; ``context`` maps an id to
    its sentences."""
    check_batch_size(batch_size)
    payloads = [{"pair_id": pair_id(n), "a": _side_payload(sides[a], context[a]),
                 "b": _side_payload(sides[b], context[b])}
                for n, (a, b) in enumerate(pairs, 1)]
    return [{"batch": k + 1, "pairs": payloads[i:i + batch_size]}
            for k, i in enumerate(range(0, len(payloads), batch_size))]


def gate_prompt(request: Mapping[str, Any]) -> str:
    """The fixed prompt text plus the batch rendered for reading."""
    return _PROMPT.format(batch=request["batch"], count=len(request["pairs"]),
                          pairs=json.dumps(request["pairs"], indent=1, ensure_ascii=False))


def gate_schema(request: Mapping[str, Any]) -> dict[str, Any]:
    """The ``merge_gate`` task schema, carrying ``request`` as data."""
    return task_schema(_SCHEMA, request=request)


def batch_request(schema: Any) -> Mapping[str, Any] | None:
    """The ``{"batch", "pairs"}`` request a ``merge_gate`` call carries, or None."""
    req = task_request(schema)
    return req if isinstance(req, Mapping) and "pairs" in req else None


def model_identity(model: Any) -> str | None:
    """The injected model's identity string, if it exposes one (``identity`` or
    ``model_id``), else None."""
    for attr in ("identity", "model_id"):
        v = getattr(model, attr, None)
        if isinstance(v, str) and v:
            return v
    return None


def _jsonable(x: Any) -> Any:
    try:
        json.dumps(x)
        return x
    except (TypeError, ValueError):
        return repr(x)


# -------------------------------------------------------------- validation


def validate_batch(request: Mapping[str, Any], answer: Any
                   ) -> tuple[dict[str, dict[str, Any]], list[Any]]:
    """Validate one batch's answer (spec: Validation).

    Returns ``(results, stray)``: ``results`` maps every requested ``pair_id`` to
    ``{"verdict", "keep", "reason", "status"}`` (exactly one final verdict and
    one status each), ``stray`` lists the ignored entries (not an object, or a
    ``pair_id`` outside this batch), which change no pair."""
    ids = [p["pair_id"] for p in request["pairs"]]
    verdicts = answer.get("verdicts") if isinstance(answer, Mapping) else None
    if not isinstance(verdicts, list):
        return ({i: {"verdict": "unsure", "keep": None, "reason": "",
                     "status": "batch_unparseable"} for i in ids}, [])
    entries: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    stray: list[Any] = []
    known = set(ids)
    for entry in verdicts:
        pid = entry.get("pair_id") if isinstance(entry, Mapping) else None
        if isinstance(pid, str) and pid in known:
            entries[pid].append(entry)
        else:
            stray.append(entry)
    results: dict[str, dict[str, Any]] = {}
    for pid in ids:
        got = entries.get(pid, [])
        verdict, keep, reason, status = "unsure", None, "", "answered"
        if not got:
            status = "missing"
        elif len(got) > 1:
            status = "duplicate"
        else:
            e = got[0]
            v = e.get("verdict")
            if not (isinstance(v, str) and v in VERDICTS):
                status = "bad_verdict"
            elif v == "same" and e.get("keep") not in ("a", "b"):
                status = "bad_keep"
            else:
                verdict = v
                keep = e["keep"] if v == "same" else None
                reason = e["reason"] if isinstance(e.get("reason"), str) else ""
        results[pid] = {"verdict": verdict, "keep": keep, "reason": reason, "status": status}
    return results, stray


def ask_batches(model: Callable[[str, dict], Any], batches: Sequence[Mapping[str, Any]],
                *, reraise: Sequence[str] = ()
                ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Ask every batch, then validate each answer: ``(results, stray, errors)``.

    ``results`` maps every ``pair_id`` to its validated verdict. A model that
    raises leaves its batch ``batch_unparseable`` and is recorded in ``errors``;
    the other batches still run. No retries. An exception whose class name is in
    ``reraise`` propagates instead (the harness's quota stop; the engine names
    none)."""
    results: dict[str, dict[str, Any]] = {}
    stray: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for request in batches:
        try:
            answer = model(gate_prompt(request), gate_schema(request))
        except Exception as exc:  # noqa: BLE001 - any failure is an unusable answer
            if type(exc).__name__ in reraise:
                raise
            logger.warning("merge gate: batch %d raised %s: %s",
                           request["batch"], type(exc).__name__, exc)
            errors.append({"batch": request["batch"], "error": f"{type(exc).__name__}: {exc}"})
            answer = None
        got, extra = validate_batch(request, answer)
        results.update(got)
        stray += [{"batch": request["batch"], "entry": _jsonable(e)} for e in extra]
    return results, stray, errors


# -------------------------------------------------------------- components


class _Components:
    """Union-find over closure representatives; deterministic (smallest id roots)."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _longest_name(side: Mapping[str, Any]) -> int:
    strings = side["names"] or side["aliases"]
    return max((len(s) for s in strings), default=0)


def elect_representative(members: Sequence[str], votes: Mapping[str, int],
                         sides: Mapping[str, Mapping[str, Any]]) -> str:
    """The component's representative (spec: One representative per component):
    the id named by the most ``keep`` votes; on a tie, the member whose longest
    name is longest; on a further tie, the smallest id.

    A tie is on the vote count, and the name-length rule then ranks **every**
    member of the component, not only the tied ones: that is how the elected id
    can be a third member (pass mark 7, r2.1)."""
    top = max((votes.get(m, 0) for m in members), default=0)
    leaders = [m for m in members if votes.get(m, 0) == top]
    if len(leaders) == 1:
        return leaders[0]
    return min(members, key=lambda m: (-_longest_name(sides[m]), m))


def compute_components(pair_results: Sequence[Mapping[str, Any]],
                       sides: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The components of the ``same`` verdicts, computed and never applied.

    ``pair_results`` holds, in ``pair_id`` order, ``{pair_id, a, b, verdict,
    keep, reason}``. Returns one record per component of two or more members, in
    order of its first pair: ``{members, same_pairs, different_pairs, votes,
    status: would_merge|conflicting_component, representative}``;
    ``representative`` is None for a conflicting component (one holding any
    ``different`` pair). A caller that writes (the harness) turns each
    ``would_merge`` into merges; the verb reports it as it is."""
    uf = _Components()
    for p in pair_results:
        if p["verdict"] == "same":
            uf.union(p["a"], p["b"])
    comps: dict[str, dict[str, Any]] = {}
    for p in pair_results:
        if p["verdict"] != "same":
            continue
        c = comps.setdefault(uf.find(p["a"]), {"same": [], "members": set()})
        c["same"].append(p)
        c["members"].update((p["a"], p["b"]))
    different: dict[str, list[str]] = defaultdict(list)
    for p in pair_results:
        if p["verdict"] == "different" and uf.find(p["a"]) == uf.find(p["b"]) \
                and uf.find(p["a"]) in comps:
            different[uf.find(p["a"])].append(p["pair_id"])
    records: list[dict[str, Any]] = []
    for root, c in comps.items():
        members = sorted(c["members"])
        votes = Counter(p["a"] if p["keep"] == "a" else p["b"] for p in c["same"])
        record: dict[str, Any] = {
            "members": members,
            "same_pairs": [p["pair_id"] for p in c["same"]],
            "different_pairs": different.get(root, []),
            "votes": {m: votes[m] for m in members if votes[m]},
        }
        if record["different_pairs"]:
            record.update(status="conflicting_component", representative=None)
        else:
            record.update(status="would_merge",
                          representative=elect_representative(members, votes, sides))
        records.append(record)
    return records


# ---------------------------------------------------------------- the verb


def _check_pairs(pairs: Any) -> list[tuple[str, str]]:
    if isinstance(pairs, (str, bytes)) or not isinstance(pairs, (list, tuple)) or not pairs:
        raise ValueError("pairs must be a non-empty list of [id, id] pairs")
    if len(pairs) > MAX_PAIRS:
        raise ValueError(f"at most {MAX_PAIRS} pairs per call, got {len(pairs)}")
    out: list[tuple[str, str]] = []
    for pair in pairs:
        if not (isinstance(pair, (list, tuple)) and len(pair) == 2
                and all(isinstance(i, str) and i for i in pair)):
            raise ValueError(f"a pair is two non-empty id strings, got {pair!r}")
        out.append((pair[0], pair[1]))
    return out


def _check_context(context: Any) -> dict[str, list[str]]:
    if context is None:
        return {}
    if not isinstance(context, Mapping):
        raise ValueError("context is a mapping of id to a list of sentences")
    out: dict[str, list[str]] = {}
    for key, sentences in context.items():
        if not (isinstance(key, str) and key):
            raise ValueError(f"a context key is a non-empty id string, got {key!r}")
        if isinstance(sentences, (str, bytes)) or not isinstance(sentences, (list, tuple)) \
                or not all(isinstance(s, str) for s in sentences):
            raise ValueError(f"context for {key!r} is a list of strings")
        out[key] = list(sentences)
    return out


def _representative_context(w: Any, context: Mapping[str, Sequence[str]], reps: set[str]
                            ) -> dict[str, list[str]]:
    """Sentences per representative: key order (sorted id), then list order,
    trimmed and cut, de-duplicated, capped at ``CONTEXT_SENTENCES``."""
    out: dict[str, list[str]] = {rep: [] for rep in reps}
    for key in sorted(context):
        rep = w.registry.resolve(key)
        if rep not in out:
            continue
        for sentence in context[key]:
            text = sentence.strip()[:CONTEXT_SENTENCE_CHARS]
            if text and text not in out[rep] and len(out[rep]) < CONTEXT_SENTENCES:
                out[rep].append(text)
    return out


def report(w: Any, model: Callable[[str, dict], Any] | None, pairs: Any, *,
           context: Mapping[str, Sequence[str]] | None = None,
           batch_size: int = DEFAULT_BATCH_SIZE) -> dict[str, Any]:
    """Ask ``model`` whether the host's pairs name the same thing; report only.

    The implementation of ``Porcelain.merge_gate`` (MERGE-GATE-VERB-V1). Writes
    nothing and keeps nothing between calls. ``model`` is the world's injected
    callable, or None: with none, nothing is asked and the report says so."""
    requested = _check_pairs(pairs)
    check_batch_size(batch_size)
    ctx = _check_context(context)
    # resolve each pair to its closures' representatives and collapse duplicates
    collapsed: dict[tuple[str, str], list[int]] = {}
    for index, (x, y) in enumerate(requested):
        rx, ry = w.registry.resolve(x), w.registry.resolve(y)
        collapsed.setdefault((min(rx, ry), max(rx, ry)), []).append(index)
    reps = {i for key in collapsed for i in key}
    flags: dict[str, tuple[bool, bool]] = {}
    for rep in reps:
        members = sorted(w.registry.closure(rep))
        flags[rep] = (_is_person(w, members), _is_class(w, members, "event"))
    sides = read_sides(w, sorted(reps))
    not_asked: list[dict[str, Any]] = []
    askable: list[tuple[str, str]] = []
    for (a, b), indexes in sorted(collapsed.items()):
        if a == b:
            status = "already_one"
        elif w.porcelain.distinct_between(a, b):
            status = "held_apart"
        elif flags[a][0] != flags[b][0] or flags[a][1] != flags[b][1]:
            status = "class_mismatch"
        elif a not in sides or b not in sides:
            status = "no_names"
        else:
            askable.append((a, b))
            continue
        not_asked.append({"a": a, "b": b, "status": status, "requested_as": indexes})
    if not askable:
        status_top = "nothing_to_ask"
    elif model is None:
        status_top = "no_model"
        for a, b in askable:
            not_asked.append({"a": a, "b": b, "status": "no_model",
                              "requested_as": collapsed[(a, b)]})
        askable = []
    else:
        status_top = "asked"
    not_asked.sort(key=lambda e: (e["a"], e["b"]))
    batches = make_batches(askable, sides, _representative_context(w, ctx, reps), batch_size)
    results, stray, errors = (ask_batches(model, batches) if batches and model is not None
                              else ({}, [], []))
    batch_of = {p["pair_id"]: b["batch"] for b in batches for p in b["pairs"]}
    pair_results: list[dict[str, Any]] = []
    for n, (a, b) in enumerate(askable, 1):
        pid = pair_id(n)
        r = results[pid]
        pair_results.append({
            "pair_id": pid, "a": a, "b": b,
            "a_names": sides[a]["names"], "b_names": sides[b]["names"],
            "verdict": r["verdict"], "keep": r["keep"],
            "keep_id": {"a": a, "b": b}.get(r["keep"]),
            "reason": r["reason"], "status": r["status"],
            "batch": batch_of[pid], "requested_as": collapsed[(a, b)]})
    components = compute_components(pair_results, sides)
    out = {
        "gate": TASK_MERGE_GATE,
        "status": status_top,
        "call_id": uuid.uuid4().hex,
        "cached": False,
        "model": model_identity(model) if model is not None else None,
        "batch_size": batch_size,
        "requested": [[x, y] for x, y in requested],
        "counts": {
            "requested": len(requested),
            "asked": len(pair_results),
            "not_asked": dict(sorted(Counter(e["status"] for e in not_asked).items())),
            "batches": len(batches),
            "verdicts": dict(sorted(Counter(p["verdict"] for p in pair_results).items())),
            "statuses": dict(sorted(Counter(p["status"] for p in pair_results).items())),
            "stray": len(stray),
            "components": len(components),
            "conflicting_components": sum(c["status"] == "conflicting_component"
                                          for c in components),
        },
        "pairs": pair_results,
        "not_asked": not_asked,
        "stray": stray,
        "batch_errors": errors,
        "components": components,
    }
    logger.info("merge gate verb: %s %s", status_top, out["counts"])
    return out
