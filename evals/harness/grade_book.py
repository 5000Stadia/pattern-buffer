"""Grade a built world against a book's graded answer key (BOOK-RUN-V1 §3).

Deterministic, no model call. ``grade_book(world, registry, graded)`` reads the
world's canon ``name``/``alias`` rows and containment rows, never the prose, and
the ``graded.json`` that ``book_gold.py`` built from the key and two readers.

Everything is computed over closures (an entity's ``same_as`` family), so a
merge the build or the merge gate made is credited or charged where it lands.

CLI:
    PYTHONPATH=src python evals/harness/grade_book.py --run RUN_DIR \\
        --graded evals/books/<slug>/graded.json [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from patternbuffer.model import ATTR_PREFIX, CANON

try:
    from book_gold import book_normalize, fold_quotes
    from grade_leaks import grade_sections
    from grade_registry import grade
except ImportError:  # imported as evals.harness.grade_book
    from evals.harness.book_gold import book_normalize, fold_quotes
    from evals.harness.grade_leaks import grade_sections
    from evals.harness.grade_registry import grade

logger = logging.getLogger(__name__)

IDENTITY_KINDS = ("person", "place", "object")
_SECTION_ORDER = {"locations": 0, "holdings": 1}
_ID = re.compile(r"^(\w+)\[(\d+)\]$")


def _ratio(num: float, den: float) -> float | None:
    return None if not den else round(num / den, 4)


def _name_index(world: Any, ident: Any) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    """(normalized string -> closure roots, closure root -> its folded strings),
    from the canon ``name`` and ``alias`` rows."""
    index: dict[str, set[str]] = {}
    strings: dict[str, list[str]] = {}
    for row in world.buffer.visible(attribute_in=["name", "alias"], frame=CANON):
        if row.entity.startswith(ATTR_PREFIX) or not isinstance(row.value, str):
            continue
        root = ident.resolve(row.entity)
        index.setdefault(book_normalize(row.value), set()).add(root)
        folded = fold_quotes(row.value)
        if folded not in strings.setdefault(root, []):
            strings[root].append(folded)
    return index, strings


def _lcs(expected: Sequence[str], world: Sequence[frozenset[str]]) -> int:
    """Longest common subsequence where an expected key matches a world element
    that holds it (a fused closure holds several keys)."""
    prev = [0] * (len(world) + 1)
    for e in expected:
        cur = [0]
        for j, w in enumerate(world, 1):
            cur.append(prev[j - 1] + 1 if e in w else max(prev[j], cur[j - 1]))
        prev = cur
    return prev[-1]


def _collapse(items: Sequence[Any], key: Any = lambda x: x) -> list[Any]:
    """Drop consecutive repeats (by ``key``)."""
    out: list[Any] = []
    for x in items:
        if not out or key(out[-1]) != key(x):
            out.append(x)
    return out


def _move_order(move: Mapping[str, Any]) -> tuple[int, int, int]:
    """``(from_chapter, section, index)``; locations sort before holdings."""
    m = _ID.match(move["id"])
    section, index = (m.group(1), int(m.group(2))) if m else ("", 0)
    return (move["from_chapter"], _SECTION_ORDER.get(section, 2), index)


def grade_book(world: Any, registry: Any, graded: Mapping[str, Any], *,
               spans: Mapping[str, Any] | None = None,
               chunk_texts: Mapping[int, str] | None = None,
               pass0: Any | None = None) -> dict[str, Any]:
    """Score ``world`` against ``graded`` (the content of ``graded.json``).

    GRADE-LEAKS-V1: ``spans`` is the run's ``chunk_spans.json`` content,
    ``chunk_texts`` the text of each chunk by id and ``pass0`` the pass-0
    ``WorldRegistry``. They add the ``leaks``, ``beliefs`` and ``point_of_view``
    sections; without ``spans`` all three are ``"unmeasured"`` and nothing is
    inferred.

    ``registry`` is the world's identity registry (``world.registry``; ``None``
    means that), the one that resolves a row's entity to its closure. Returns a
    JSON-serializable scorecard: ``summary`` (one number per measure; ``None``
    when the book grades nothing of that kind), then the detail of each
    measure. See BOOK-RUN-V1 §3 for what each measures."""
    ident = registry if registry is not None else world.registry
    family = sorted(world.semantics.containment_family())
    index, strings = _name_index(world, ident)
    entities = graded["entities"]

    # ---- mapping: key entity -> closure roots
    ids: dict[str, list[str]] = {
        k: sorted(set().union(*(index.get(book_normalize(a), set()) for a in e["aliases"])))
        for k, e in entities.items()}
    keys_of: dict[str, list[str]] = {}
    for k, roots in ids.items():
        for r in roots:
            keys_of.setdefault(r, []).append(k)
    mapping = {
        "missing": sorted(k for k, r in ids.items() if not r),
        "split": {k: r for k, r in sorted(ids.items()) if len(r) > 1},
        "fused": {r: sorted(ks) for r, ks in sorted(keys_of.items()) if len(ks) > 1},
    }

    def label(k: str) -> str:
        aliases = entities[k]["aliases"]
        return f"{k} ({aliases[0]})" if aliases else k

    def members(key: str) -> list[str]:
        out: set[str] = set()
        for r in ids.get(key, []):
            out |= ident.closure(r)
        return sorted(out)

    # ---- 1. identity
    gold = {k: [fold_quotes(a) for a in e["aliases"]]
            for k, e in entities.items() if e["kind"] in IDENTITY_KINDS}
    pseudo = {"entities": {r: {"names": s, "aliases": []} for r, s in strings.items()}}
    g = grade(pseudo, gold)
    identity = {
        "gold_entities": g["gold_entities"], "mentions": g["mentions"],
        "b3_precision": g["b3_precision"], "b3_recall": g["b3_recall"], "b3_f1": g["b3_f1"],
        "split": g["fragmentation"], "fused": g["fusion"], "missing": g["uncovered"],
        "mapping": mapping,
    }

    # ---- 2. reveals
    reveal_items = []
    for r in graded["same_as"]:
        alias_roots = index.get(book_normalize(r["alias"]), set())
        joined = bool(alias_roots & set(ids.get(r["entity"], [])))
        reveal_items.append({**r, "joined": joined})
    reveals = {"score": _ratio(sum(i["joined"] for i in reveal_items), len(reveal_items)),
               "items": reveal_items}

    # ---- 3. look-alikes
    look_items, fusions = [], []
    for p in graded["not_same"]:
        common = sorted(set(ids.get(p["a"], [])) & set(ids.get(p["b"], [])))
        fused = bool(common)
        look_items.append({**p, "fused": fused, "closures": common})
        if fused:
            fusions.append(f"{label(p['a'])} / {label(p['b'])}")
    look_alikes = {"score": _ratio(sum(not i["fused"] for i in look_items), len(look_items)),
                   "fusions": fusions, "items": look_items}

    # ---- 4. where things are, as order
    def element(value: Any) -> tuple[frozenset[str], str]:
        root = ident.resolve(value)
        return frozenset(keys_of.get(root, ())), root

    def tag(el: tuple[frozenset[str], str]) -> str:
        return "+".join(sorted(el[0])) if el[0] else f"?{el[1]}"

    order_objects: dict[str, Any] = {}
    for key, moves in sorted(graded["moves"].items()):
        ordered = sorted(moves, key=_move_order)
        expected = _collapse([m["to"] for m in ordered])
        rows = world.buffer.visible(entity_in=members(key), attribute_in=family, frame=CANON) \
            if ids.get(key) else []
        rows.sort(key=lambda r: (r.valid_from is not None,
                                 r.valid_from if r.valid_from is not None else 0.0, r.seq))
        seq = _collapse([element(r.value) for r in rows if isinstance(r.value, str)],
                        key=lambda e: e[0] or e[1])
        lcs = _lcs(expected, [e[0] for e in seq])
        order_objects[key] = {
            "expected": expected, "world": [tag(e) for e in seq], "lcs": lcs,
            "score": _ratio(lcs, len(expected)),
            "last_to_chapter": ordered[-1]["to_chapter"], "last_to": ordered[-1]["to"],
            "ever_found": sorted({c for c in expected if any(c in e[0] for e in seq)}),
        }
    scored = [o["score"] for o in order_objects.values() if o["score"] is not None]
    order = {
        "mean": _ratio(sum(scored), len(scored)),
        "pooled": _ratio(sum(o["lcs"] for o in order_objects.values()),
                         sum(len(o["expected"]) for o in order_objects.values())),
        "objects": order_objects,
    }

    # final: the fold at the end of the book
    canon_rows = world.buffer.visible(frame=CANON)
    times = [r.valid_from for r in canon_rows if r.valid_from is not None]
    as_of = max(times) if times else None
    final_objects: dict[str, Any] = {}
    for key, o in order_objects.items():
        if o["last_to_chapter"] is not None:
            continue
        got: set[str] = set()
        for root in ids.get(key, []):
            winner = world.state(root, "in", valid_as_of=as_of).winner
            if winner is not None and isinstance(winner.value, str):
                got |= element(winner.value)[0]
        final_objects[key] = {"expected": o["last_to"], "got": sorted(got),
                              "ok": o["last_to"] in got}
    final = {"read": "as_of" if as_of is not None else "head", "as_of": as_of,
             "score": _ratio(sum(f["ok"] for f in final_objects.values()), len(final_objects)),
             "objects": final_objects}

    # ever: expected containers that appear anywhere in the world's sequence
    exp_total = sum(len(set(o["expected"])) for o in order_objects.values())
    found_total = sum(len(o["ever_found"]) for o in order_objects.values())
    ever = {"score": _ratio(found_total, exp_total),
            "objects": {k: {"expected": sorted(set(o["expected"])), "found": o["ever_found"]}
                        for k, o in order_objects.items()}}

    # ---- 5. containers
    container_items = []
    for c in graded["containers"]:
        roots = set(ids.get(c["container"], []))
        placed: dict[str, bool] = {}
        for content in c["contents"]:
            rows = world.buffer.visible(entity_in=members(content), attribute_in=["in", "within"],
                                        frame=CANON) if ids.get(content) else []
            placed[content] = any(isinstance(r.value, str) and ident.resolve(r.value) in roots
                                  for r in rows)
        container_items.append({"id": c["id"], "container": c["container"], "placed": placed,
                                "score": _ratio(sum(placed.values()), len(placed))})
    scores = [i["score"] for i in container_items if i["score"] is not None]
    containers = {"score": _ratio(sum(scores), len(scores)), "items": container_items}

    summary = {
        "identity_b3_f1": identity["b3_f1"] if gold else None,
        "reveals": reveals["score"], "look_alikes": look_alikes["score"],
        "order": order["mean"], "final": final["score"], "ever": ever["score"],
        "containers": containers["score"],
    }
    new = grade_sections(world, ident, graded, spans=spans, chunk_texts=chunk_texts, pass0=pass0)
    return {
        "key_sha256": graded.get("key_sha256"), "readers": graded.get("readers"),
        "summary": summary, "identity": identity, "reveals": reveals,
        "look_alikes": look_alikes, "order": order, "final": final, "ever": ever,
        "containers": containers,
        **new,
        "headline": _headline(look_alikes, new, summary),
        "field_counts": graded.get("field_counts", {}),
        "ungraded_counts": _ungraded(graded),
        "dropped": len(graded.get("dropped", [])),
        "dropped_fields": len(graded.get("dropped_fields", [])),
    }


def _ungraded(graded: Mapping[str, Any]) -> dict[str, int]:
    """Entries the grader does not score: the key's counts, less the entries a
    verified structured field now grades (GRADE-LEAKS-V1)."""
    counts = dict(graded.get("ungraded_counts", {}))
    if "field_counts" in graded:
        for key_section, graded_section in (("knowledge", "knowledge"), ("false_beliefs", "beliefs"),
                                            ("corrections", "corrections")):
            if key_section in counts:
                counts[key_section] = max(0, counts[key_section] - len(graded.get(graded_section, [])))
    return counts


def _headline(look_alikes: Mapping[str, Any], new: Mapping[str, Any],
              summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The judging order (docs/SPEED-PLAN-2026-10-13.md), most important first.
    Time and cost are filled by the CLI from the run's receipt."""
    leaks, beliefs = new["leaks"], new["beliefs"]
    return [
        {"rank": 1, "measure": "wrong merges across look-alike pairs",
         "value": len(look_alikes["fusions"]), "target": 0},
        {"rank": 2, "measure": "leaks",
         "value": leaks if isinstance(leaks, str) else leaks["total"], "target": 0,
         "unmeasured_parts": [] if isinstance(leaks, str) else leaks["unmeasured_parts"]},
        {"rank": 3, "measure": "false beliefs in canon",
         "value": beliefs if isinstance(beliefs, str) else beliefs["false_beliefs"]["false_in_canon"],
         "target": 0},
        {"rank": 4, "measure": "existing scores", "value": dict(summary)},
        {"rank": 5, "measure": "time and cost", "value": None},
    ]


def _count(x: Any) -> str:
    return x if isinstance(x, str) else ("n/a" if x is None else str(x))


def scorecard_md(card: Mapping[str, Any], title: str = "Book scorecard") -> str:
    """Render ``grade_book`` output as a Markdown scorecard."""
    fmt = lambda x: "n/a" if x is None else f"{x:.3f}"  # noqa: E731
    s, ident = card["summary"], card["identity"]
    lines = [f"# {title}", "", f"Readers: {', '.join(card.get('readers') or [])}; "
             f"{card['dropped']} entries dropped.", ""]
    if "headline" in card:
        lines += ["## Headline (judging order)", "", "| # | measure | value | target |", "|---|---|---|---|"]
        for h in card["headline"]:
            if h["rank"] == 4:
                value = "see the scores below"
            elif isinstance(h["value"], dict):
                v = h["value"]
                value = (f"{_count(v.get('seconds'))} s, ${_count(v.get('cost_usd'))}"
                         + ("" if v.get("cost_known") else " (price unknown for some calls)"))
            else:
                value = _count(h["value"])
            if h.get("unmeasured_parts"):
                value += f" (unmeasured: {', '.join(h['unmeasured_parts'])})"
            lines.append(f"| {h['rank']} | {h['measure']} | {value} | "
                         f"{_count(h['target']) if 'target' in h else ''} |")
        lines.append("")
    lines += ["| measure | score |", "|---|---|",
             f"| identity B3 F1 | {fmt(s['identity_b3_f1'])} |",
             f"| reveals joined | {fmt(s['reveals'])} |",
             f"| look-alikes kept apart | {fmt(s['look_alikes'])} |",
             f"| order (mean LCS) | {fmt(s['order'])} |",
             f"| final container | {fmt(s['final'])} |",
             f"| ever in container | {fmt(s['ever'])} |",
             f"| revealed contents placed | {fmt(s['containers'])} |", "",
             "## Identity", "",
             f"- B3 precision {fmt(ident['b3_precision'])}, recall {fmt(ident['b3_recall'])}, "
             f"over {ident['gold_entities']} entities and {ident['mentions']} mentions",
             f"- split: {', '.join(f'`{k}`' for k in sorted(ident['split'])) or 'none'}",
             f"- fused closures: "
             f"{', '.join(f'`{r}` = {ks}' for r, ks in sorted(ident['mapping']['fused'].items())) or 'none'}",
             f"- missing: {', '.join(f'`{k}`' for k in ident['mapping']['missing']) or 'none'}",
             "", "## Look-alikes merged", ""]
    lines += [f"- {f}" for f in card["look_alikes"]["fusions"]] or ["- none"]
    lines += ["", "## Reveals not joined", ""]
    lines += [f"- `{i['id']}`: {i['entity']} / {i['alias']!r}"
              for i in card["reveals"]["items"] if not i["joined"]] or ["- none"]
    lines += ["", "## Order by object", ""]
    for k, o in card["order"]["objects"].items():
        lines.append(f"- `{k}` {fmt(o['score'])}: expected {' > '.join(o['expected'])}; "
                     f"world {' > '.join(o['world']) or '(none)'}")
    lines += _leaks_md(card.get("leaks"))
    lines += _beliefs_md(card.get("beliefs"))
    lines += _pov_md(card.get("point_of_view"))
    lines += ["", "## Structured fields (entries / verified / dropped)", ""]
    counts = card.get("field_counts") or {}
    lines += [f"- {name}: {c['entries']} / {c['verified']} / {c['dropped']}"
              for name, c in sorted(counts.items())] or ["- none: the key carries no structured fields"]
    lines += ["", "## Not graded", ""]
    lines += [f"- {k}: {n} entries" for k, n in sorted(card["ungraded_counts"].items())]
    lines.append("")
    return "\n".join(lines)


def _leaks_md(leaks: Any) -> list[str]:
    if leaks is None:
        return []
    lines = ["", "## Leaks (target 0)", ""]
    if isinstance(leaks, str):
        return lines + [f"- {leaks}: this run has no chunk_spans.json; nothing is inferred"]
    a, ident = leaks["alias_leaks"], leaks["identity_leaks"]
    lines.append(f"- total {leaks['total']}" + (f"; unmeasured parts: {', '.join(leaks['unmeasured_parts'])}"
                                                 if leaks["unmeasured_parts"] else ""))
    lines.append(f"- alias leaks: {a['count'] if a['measured'] else 'unmeasured'}")
    lines += [f"  - seq {r['seq']} `{r['entity']}` {r['attribute']} {r['value']!r}: chapter "
              f"{r['chapter']}, first used in chapter {r['first_chapter']}" for r in a["rows"]]
    lines.append(f"- chunk leaks: {_count(ident['chunk_leak_rows'])}; registry leaks: "
                 f"{_count(ident['registry_leaks'])}; ambiguous rows (not charged): "
                 f"{_count(ident['ambiguous_rows'])}; unmapped rows (not charged): "
                 f"{_count(ident['unmapped_rows'])}")
    for e in ident["entries"]:
        lines.append(f"  - `{e['entity']}` / {e['pre_alias']!r} (reveal {e['reveal_chapter']}): "
                     f"{_count(e['chunk_leak_rows'])} chunk-leak rows, first leaking chapter "
                     f"{_count(e['first_leaking_chapter'])}, registry leak {_count(e['registry_leak'])}")
    if ident["unclassified_chunks"]:
        lines.append(f"- chunks with no text, never classified: {ident['unclassified_chunks']}")
    lines.append("- aliases left out of chunk classification: "
                 + (", ".join(f"`{x['entity']}` {x['alias']!r}" for x in ident["excluded_aliases"]) or "none"))
    return lines


def _beliefs_md(beliefs: Any) -> list[str]:
    if beliefs is None:
        return []
    lines = ["", "## Beliefs", ""]
    if isinstance(beliefs, str):
        return lines + [f"- {beliefs}: no chunk_spans.json, so no chapter has a log position"]
    fb, co = beliefs["false_beliefs"], beliefs["corrections"]
    lines += [f"- false beliefs: {fb['entries']} verified entries, {fb['measured']} measured, "
              f"{fb['unmatched']} unmatched; false in canon {fb['false_in_canon']} (target 0); "
              f"held by the believer {fb['held_by_believer']} ({_count(fb['held_by_believer_rate'])})"]
    lines += [f"  - false in canon: `{i['id']}` ({i['who']})" for i in fb["items"]
              if i.get("false_in_canon")]
    lines += [f"  - unmatched: `{i['id']}` ({', '.join(i['unmatched'])})" for i in fb["items"]
              if i["status"] == "unmatched"]
    lines += [f"- corrections: {co['entries']} verified entries; ends at the corrected value "
              f"{co['ends_correct']} of {co['ends_correct_entries']}; claim still held after the "
              f"correction {co['claim_after_correction']} (target 0); {co['unmatched']} with an unmatched part"]
    return lines


def _pov_md(pov: Any) -> list[str]:
    if pov is None:
        return []
    lines = ["", "## Point of view", ""]
    if isinstance(pov, str):
        return lines + [f"- {pov}: no chunk_spans.json, so no chapter has a log position"]
    ln, nv = pov["learns"], pov["never_learns"]
    lines += [f"- learns: {ln['entries']} entries, held by the end {ln['held']} ({_count(ln['held_rate'])}), "
              f"learned too early {ln['learned_too_early']}, unmatched {ln['unmatched']}",
              f"- never learns: {nv['entries']} entries, violations {nv['violations']} (target 0), "
              f"unmatched {nv['unmatched']}"]
    return lines


def write_scorecard(card: Mapping[str, Any], out_dir: str | Path, stem: str = "book_scorecard",
                    title: str = "Book scorecard") -> tuple[Path, Path]:
    """Write ``<stem>.md`` and ``<stem>.json`` into ``out_dir``; return both paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md, js = out / f"{stem}.md", out / f"{stem}.json"
    md.write_text(scorecard_md(card, title))
    js.write_text(json.dumps(card, indent=2, sort_keys=True) + "\n")
    return md, js


def _load_run_inputs(run: Path, graded_path: Path, book: Path | None,
                     world_id: str) -> tuple[Any, Any, Any]:
    """``(spans, chunk_texts, pass0)`` for a run: each ``None`` when the run or
    the book directory does not have it. Raises ``SystemExit`` when the book's
    chunk plan disagrees with the run's ``chunk_spans.json``."""
    spans_path = run / "chunk_spans.json"
    spans = json.loads(spans_path.read_text()) if spans_path.exists() else None
    texts = None
    if spans is not None:
        try:
            try:
                from run_book import load_book
            except ImportError:
                from evals.harness.run_book import load_book
            plan = load_book(book or graded_path.parent)
        except Exception as exc:  # no readable book beside the key: chunk leaks go unmeasured
            logger.warning("chunk texts unavailable (%s): chunk leaks are unmeasured", exc)
        else:
            texts = {i: text for i, (_, text) in enumerate(plan.chunks)}
            for c in spans["chunks"]:
                if c["chunk"] >= len(plan.chunks) or int(plan.chunks[c["chunk"]][0]) != c["chapter"]:
                    raise SystemExit(f"ABORT: chunk {c['chunk']} of {run.name}'s chunk_spans.json "
                                     f"does not match the book's chunk plan in {book or graded_path.parent}")
    pass0 = None
    if (run / "registry_pass0.json").exists():
        from registry import WorldRegistry
        pass0 = WorldRegistry.load(run / "registry_pass0.json", world_id)
    return spans, texts, pass0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, help="a run_book.py output directory")
    ap.add_argument("--graded", required=True, help="the book's graded.json")
    ap.add_argument("--book", default=None,
                    help="the book directory (chNN.md) for chunk texts; default: beside --graded")
    ap.add_argument("--out", default=None, help="where to write (default: the run directory)")
    ap.add_argument("--world-id", default=None, help="default: the run's meta.json")
    args = ap.parse_args(argv)
    from patternbuffer.mirror import open_read_only_copy

    run = Path(args.run)
    world_id = args.world_id or json.loads((run / "meta.json").read_text())["world_id"]
    spans, texts, pass0 = _load_run_inputs(run, Path(args.graded),
                                           Path(args.book) if args.book else None, world_id)
    # a sealed in-memory copy taken through `mode=ro`: the build artifact is
    # never opened for writing (bytes and mtime unchanged)
    world = open_read_only_copy(run / "fresh_ingest.world", world_id)
    try:
        card = grade_book(world, world.registry, json.loads(Path(args.graded).read_text()),
                          spans=spans, chunk_texts=texts, pass0=pass0)
    finally:
        world.close()
    receipt = run / "receipt.json"
    if receipt.exists():
        total = json.loads(receipt.read_text()).get("total", {})
        card["headline"][-1]["value"] = {"seconds": total.get("seconds"),
                                         "cost_usd": total.get("cost_usd"),
                                         "cost_known": total.get("cost_known")}
    md, js = write_scorecard(card, args.out or run, title=f"Book scorecard ({run.name})")
    print(f"{md}\n{js}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
