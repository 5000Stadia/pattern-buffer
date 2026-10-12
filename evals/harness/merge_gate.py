"""MERGE-GATE-V1 (R25 part A): a yes/no check on lexical merge candidates.

After identity is finalized (promote, then ``reconcile``), this pass finds pairs
of distinct closures that share an identifying word or an exact string, asks the
injected model one batched question ("same, different, or unsure?"), and applies
the ``same`` answers as host merges. Harness only: it reads the world through
the engine's own reads and writes only through ``porcelain.merge``.

The shape (specs/MERGE-GATE-V1.md r2.1):

- **Candidates** (``candidate_pairs``): no model. Two closure representatives
  qualify when they share a content token (lowercased, possessive removed, at
  least three characters, not a stop word, not on the alias index's stoplist) or
  an exact normalized name or alias string; they are not person against
  non-person, not already held apart by ``distinct_between`` and not already one
  closure. Sorted by ``(a, b)`` and numbered ``p0001`` onwards over the whole
  list.
- **The call** (``build_batches``, ``gate_schema``, ``gate_prompt``): the engine's
  model signature ``model(prompt, schema) -> dict``; the schema's title is
  ``merge_gate`` and its ``request`` carries ``{"batch": n, "pairs": [...]}``
  (``model.task_request`` reads it).
- **Validation** (``validate_batch``): every requested pair ends with exactly one
  verdict and one status; a bad answer is ``unsure``, never a guess. No retries.
- **Apply** (``apply_verdicts``): ask every batch first, write after. The ``same``
  pairs are joined into components; a component holding any ``different`` pair is
  skipped; otherwise one representative is elected (``keep`` is a vote) and every
  other member is merged into it, in sorted id order, naming that representative
  so nothing is re-pointed.

``run_gate`` is the one entry point ``pipeline.finalize_identity`` calls. The
report it returns is written as ``run_dir/merge_gate.json``. The gate never
retracts, never writes ``distinct_from``, and never calls anything but the
model and the porcelain.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any, Callable, Mapping, Sequence

from patternbuffer.model import CANON, task_request, task_schema

try:
    from alias_index import stoplist_class
    from grade_registry import normalize
except ImportError:  # imported as evals.harness.merge_gate
    from evals.harness.alias_index import stoplist_class
    from evals.harness.grade_registry import normalize

logger = logging.getLogger(__name__)

TASK_MERGE_GATE = "merge_gate"
DEFAULT_BATCH_SIZE = 25
VERDICTS = ("same", "different", "unsure")
CONTEXT_SENTENCES = 2

#: Articles, possessive pronouns, ``of``, ``old``, ``new`` and the like. A
#: candidate token is never one of these.
STOP_WORDS = frozenset(
    "the a an of and her his their its my our your s old new to in on at for with from by".split())

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


def _tokens(text: str) -> set[str]:
    """Identifying content words of one name or alias (spec: lowercased,
    possessive ``'s`` removed, >= 3 characters, not a stop word, not on the
    alias index's stoplist)."""
    s = text.lower().replace("’", "'").replace("'s", " ")
    return {w for w in re.findall(r"[a-z0-9]+", s)
            if len(w) >= 3 and w not in STOP_WORDS and not stoplist_class(w)}


def _is_person(w: Any, members: Sequence[str]) -> bool:
    """A closure is a person when any member's id is in the ``person:`` namespace
    or any member's folded canon ``kind`` is ``person``."""
    for m in members:
        if m.partition(":")[0] == "person":
            return True
        winner = getattr(w.state(m, "kind"), "winner", None)
        if winner is not None and str(winner.value).strip().lower() == "person":
            return True
    return False


def read_sides(w: Any) -> dict[str, dict[str, Any]]:
    """Every closure that carries a canon ``name`` or ``alias`` row, keyed by its
    served representative: ``{id, kind, members, names, aliases, person}``.

    Names and aliases are the world's own rows over the whole closure (generated
    rows excluded: invention is never evidence), sorted and de-duplicated."""
    rows = w.buffer.visible(attribute_in=["name", "alias"], frame=CANON)
    by_rep: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"name": set(), "alias": set()})
    for r in rows:
        if r.status == "generated" or not isinstance(r.value, str) or not r.value.strip():
            continue
        by_rep[w.registry.resolve(r.entity)][r.attribute].add(r.value)
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
        }
    return sides


def candidate_pairs(w: Any, sides: Mapping[str, Mapping[str, Any]] | None = None
                    ) -> list[tuple[str, str]]:
    """The deterministic candidate pairs ``(a, b)``, ``a < b``, sorted (spec:
    Candidates). Zero model calls, zero writes."""
    sides = read_sides(w) if sides is None else sides
    by_token: dict[str, set[str]] = defaultdict(set)
    by_string: dict[str, set[str]] = defaultdict(set)
    for rep, s in sides.items():
        for text in list(s["names"]) + list(s["aliases"]):
            for t in _tokens(text):
                by_token[t].add(rep)
            key = normalize(text.replace("’", "'"))
            if key:
                by_string[key].add(rep)
    found: set[tuple[str, str]] = set()
    for group in (*by_token.values(), *by_string.values()):
        found.update(combinations(sorted(group), 2))
    out = []
    for a, b in sorted(found):
        if sides[a]["person"] != sides[b]["person"]:
            continue  # never person against non-person
        if w.porcelain.distinct_between(a, b):
            continue  # already held apart, by anyone (R42)
        out.append((a, b))  # distinct representatives are never one closure
    return out


# ----------------------------------------------------------------- context


def _context(sides: Mapping[str, Mapping[str, Any]], ids: set[str],
             segments: Sequence[str] | None) -> dict[str, list[str]]:
    """Up to two source sentences per id, from the alias index's mention hits
    over ``segments`` (``[]`` for every id without a source)."""
    out: dict[str, list[str]] = {i: [] for i in ids}
    if not segments or not ids:
        return out
    try:
        import alias_index as ai
    except ImportError:
        from evals.harness import alias_index as ai
    lex = ai.Lexicon({"world_id": "", "entities": {
        rep: {"names": s["names"], "aliases": s["aliases"]} for rep, s in sides.items()}})
    common = frozenset(x for seg in segments for x in ai._LOWER_WORD.findall(seg.replace("’", "'")))
    seen: dict[str, set[tuple[int, int, int]]] = defaultdict(set)
    for si, seg in enumerate(segments):
        text = seg.replace("’", "'")
        spans = ai._sentence_spans(text)
        for m in lex.mentions(text, common):
            wanted = [i for i in m.ids if i in ids and len(out[i]) < CONTEXT_SENTENCES]
            if not wanted:
                continue
            sentence = next(((s, e) for s, e in spans if s <= m.start < e), None)
            if sentence is None:
                continue
            for i in wanted:
                key = (si, *sentence)
                if key not in seen[i]:
                    seen[i].add(key)
                    out[i].append(ai._excerpt(text, *sentence))
    return out


def _side_payload(s: Mapping[str, Any], context: Sequence[str]) -> dict[str, Any]:
    return {"id": s["id"], "kind": s["kind"], "names": list(s["names"]),
            "aliases": list(s["aliases"]), "context": list(context)}


def pair_id(n: int) -> str:
    """``p0001``, ``p0002``, ... (one-based, over the whole sorted candidate list)."""
    return f"p{n:04d}"


def build_batches(w: Any, pairs: Sequence[tuple[str, str]],
                  sides: Mapping[str, Mapping[str, Any]],
                  segments: Sequence[str] | None = None,
                  batch_size: int = DEFAULT_BATCH_SIZE) -> list[dict[str, Any]]:
    """The requests, one per batch: ``{"batch": n, "pairs": [...]}`` (batch
    numbers are one-based). Each pair is ``{"pair_id", "a", "b"}`` with side
    payloads ``{id, kind, names, aliases, context}``."""
    if not (isinstance(batch_size, int) and not isinstance(batch_size, bool) and batch_size >= 1):
        raise ValueError(f"batch_size must be a positive integer, got {batch_size!r}")
    context = _context(sides, {i for p in pairs for i in p}, segments)
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


# ------------------------------------------------------------------- apply


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


def apply_verdicts(w: Any, pair_results: Sequence[Mapping[str, Any]],
                   sides: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Apply the ``same`` verdicts together (spec: Applying the verdicts).

    ``pair_results`` holds, in ``pair_id`` order, ``{pair_id, a, b, verdict,
    keep, reason}``. Returns one record per component of two or more members, in
    order of its first pair: ``{members, same_pairs, different_pairs, votes,
    status: applied|conflicting_component, representative, served, merges}``.
    Writes only ``porcelain.merge`` rows, and never retracts."""
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
            record.update(status="conflicting_component", representative=None, served=None,
                          merges=[])
            records.append(record)
            continue
        rep = elect_representative(members, votes, sides)
        record.update(status="applied", representative=rep, merges=[])
        for member in (m for m in members if m != rep):
            reasons = [p["reason"] or p["pair_id"] for p in c["same"] if member in (p["a"], p["b"])]
            evidence = "merge gate: " + "; ".join(reasons)
            entry: dict[str, Any] = {"member": member}
            try:
                receipt = w.porcelain.merge(rep, member, evidence, representative=rep)
            except ValueError as exc:  # refused before any write
                entry.update(outcome=f"error: {exc}")
            else:
                entry.update(outcome=receipt.get("outcome"),
                             canonical_id=receipt.get("canonical_id"))
                if receipt.get("outcome") != "merged":
                    entry.update(reason=receipt.get("reason"),
                                 blocking_edges=list(receipt.get("blocking_edges") or []))
            record["merges"].append(entry)
        record["served"] = w.registry.resolve(rep)
        record["partial"] = any(m["outcome"] != "merged" for m in record["merges"])
        records.append(record)
    return records


# ---------------------------------------------------------------- the gate


def model_identity(model: Any) -> str | None:
    """The injected model's identity string, if it exposes one (``identity`` or
    ``model_id``), else None."""
    for attr in ("identity", "model_id"):
        v = getattr(model, attr, None)
        if isinstance(v, str) and v:
            return v
    return None


def plan(w: Any, segments: Sequence[str] | None = None,
         batch_size: int = DEFAULT_BATCH_SIZE) -> dict[str, Any]:
    """Candidates and batches for the world as it stands, no model call and no
    write: ``{"sides", "pairs", "batches"}``. The dry run and ``run_gate`` share it."""
    sides = read_sides(w)
    pairs = candidate_pairs(w, sides)
    return {"sides": sides, "pairs": pairs,
            "batches": build_batches(w, pairs, sides, segments, batch_size)}


def run_gate(w: Any, model: Callable[[str, dict], Any], *,
             segments: Sequence[str] | None = None,
             batch_size: int = DEFAULT_BATCH_SIZE,
             source: str | None = None) -> dict[str, Any]:
    """Ask every batch, then apply the ``same`` verdicts; return the report
    (``run_dir/merge_gate.json``). ``model`` is the engine's model signature;
    ``segments`` are the run's source segments (``None``: every ``context`` is
    ``[]``). Nothing is written while asking. A model that raises (other than a
    quota stop, which propagates) leaves its batch ``batch_unparseable``. No
    retries."""
    planned = plan(w, segments, batch_size)
    sides, pairs, batches = planned["sides"], planned["pairs"], planned["batches"]
    ids = {p["pair_id"]: p for b in batches for p in b["pairs"]}
    batch_of = {p["pair_id"]: b["batch"] for b in batches for p in b["pairs"]}
    results: dict[str, dict[str, Any]] = {}
    stray: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for request in batches:
        try:
            answer = model(gate_prompt(request), gate_schema(request))
        except Exception as exc:  # noqa: BLE001 - any failure is an unusable answer
            if type(exc).__name__ == "QuotaExhausted":
                raise
            logger.warning("merge gate: batch %d raised %s: %s",
                           request["batch"], type(exc).__name__, exc)
            errors.append({"batch": request["batch"], "error": f"{type(exc).__name__}: {exc}"})
            answer = None
        got, extra = validate_batch(request, answer)
        results.update(got)
        stray += [{"batch": request["batch"], "entry": _jsonable(e)} for e in extra]
    pair_results = []
    for pid in sorted(ids):
        p, r = ids[pid], results[pid]
        a, b = p["a"]["id"], p["b"]["id"]
        pair_results.append({
            "pair_id": pid, "batch": batch_of[pid], "a": a, "b": b,
            "a_names": p["a"]["names"], "b_names": p["b"]["names"],
            "verdict": r["verdict"], "keep": r["keep"],
            "keep_id": {"a": a, "b": b}.get(r["keep"]),
            "reason": r["reason"], "status": r["status"]})
    components = apply_verdicts(w, pair_results, sides)
    merges = [m for c in components for m in c["merges"]]
    report = {
        "gate": TASK_MERGE_GATE,
        "model": model_identity(model),
        "batch_size": batch_size,
        "source": source if segments else "none",
        "counts": {
            "candidates": len(pairs),
            "batches": len(batches),
            "verdicts": dict(sorted(Counter(p["verdict"] for p in pair_results).items())),
            "statuses": dict(sorted(Counter(p["status"] for p in pair_results).items())),
            "stray": len(stray),
            "components": len(components),
            "conflicting_components": sum(c["status"] == "conflicting_component"
                                          for c in components),
            "merges": dict(sorted(Counter(str(m["outcome"]) for m in merges).items())),
        },
        "pairs": pair_results,
        "stray": stray,
        "batch_errors": errors,
        "components": components,
    }
    logger.info("merge gate: %s", report["counts"])
    return report


def _jsonable(x: Any) -> Any:
    try:
        json.dumps(x)
        return x
    except (TypeError, ValueError):
        return repr(x)
