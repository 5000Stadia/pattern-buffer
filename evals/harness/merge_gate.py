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
  non-person nor event against non-event, not already held apart by ``distinct_between`` and not already one
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

import logging
import re
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any, Callable, Mapping, Sequence

# The question, the envelope, validation, components and election are the
# engine's one shared implementation (MERGE-GATE-VERB-V1); re-exported here so
# the harness's callers keep their imports.
from patternbuffer.merge_gate import (  # noqa: F401
    CONTEXT_SENTENCES, DEFAULT_BATCH_SIZE, TASK_MERGE_GATE, VERDICTS, _Components,
    _PROMPT, _SCHEMA, _is_class, _is_person, _jsonable, _longest_name, _side_payload,
    ask_batches, batch_request, check_batch_size, compute_components,
    elect_representative, gate_prompt, gate_schema, make_batches, model_identity,
    pair_id, read_sides, validate_batch)

try:
    from alias_index import stoplist_class
    from grade_registry import normalize
except ImportError:  # imported as evals.harness.merge_gate
    from evals.harness.alias_index import stoplist_class
    from evals.harness.grade_registry import normalize

logger = logging.getLogger(__name__)

#: Articles, possessive pronouns, ``of``, ``old``, ``new`` and the like. A
#: candidate token is never one of these.
STOP_WORDS = frozenset(
    "the a an of and her his their its my our your s old new to in on at for with from by".split())

# ----------------------------------------------------------------- reading


def _tokens(text: str) -> set[str]:
    """Identifying content words of one name or alias (spec: lowercased,
    possessive ``'s`` removed, >= 3 characters, not a stop word, not on the
    alias index's stoplist)."""
    s = text.lower().replace("’", "'").replace("'s", " ")
    return {w for w in re.findall(r"[a-z0-9]+", s)
            if len(w) >= 3 and w not in STOP_WORDS and not stoplist_class(w)}


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
        if sides[a].get("event", False) != sides[b].get("event", False):
            continue  # never event against non-event (r2.2)
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


def build_batches(w: Any, pairs: Sequence[tuple[str, str]],
                  sides: Mapping[str, Mapping[str, Any]],
                  segments: Sequence[str] | None = None,
                  batch_size: int = DEFAULT_BATCH_SIZE) -> list[dict[str, Any]]:
    """The requests, one per batch: ``{"batch": n, "pairs": [...]}`` (batch
    numbers are one-based). Each pair is ``{"pair_id", "a", "b"}`` with side
    payloads ``{id, kind, names, aliases, context}``."""
    check_batch_size(batch_size)
    context = _context(sides, {i for p in pairs for i in p}, segments)
    return make_batches(pairs, sides, context, batch_size)


# ------------------------------------------------------------------- apply


def apply_verdicts(w: Any, pair_results: Sequence[Mapping[str, Any]],
                   sides: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Apply the ``same`` verdicts together (spec: Applying the verdicts).

    ``pair_results`` holds, in ``pair_id`` order, ``{pair_id, a, b, verdict,
    keep, reason}``. Returns one record per component of two or more members, in
    order of its first pair: ``{members, same_pairs, different_pairs, votes,
    status: applied|conflicting_component, representative, served, merges}``.
    The components themselves are the engine's (``compute_components``); this
    writes only ``porcelain.merge`` rows, and never retracts."""
    by_id = {p["pair_id"]: p for p in pair_results}
    records = compute_components(pair_results, sides)
    for record in records:
        if record["status"] == "conflicting_component":
            record.update(served=None, merges=[])
            continue
        record.update(status="applied", merges=[])
        rep = record["representative"]
        same = [by_id[pid] for pid in record["same_pairs"]]
        for member in (m for m in record["members"] if m != rep):
            reasons = [p["reason"] or p["pair_id"] for p in same if member in (p["a"], p["b"])]
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
    return records


# ---------------------------------------------------------------- the gate


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
    results, stray, errors = ask_batches(model, batches, reraise=("QuotaExhausted",))
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
