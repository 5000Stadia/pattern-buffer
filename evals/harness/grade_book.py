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
    from grade_registry import grade
except ImportError:  # imported as evals.harness.grade_book
    from evals.harness.book_gold import book_normalize, fold_quotes
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


def grade_book(world: Any, registry: Any, graded: Mapping[str, Any]) -> dict[str, Any]:
    """Score ``world`` against ``graded`` (the content of ``graded.json``).

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
    return {
        "key_sha256": graded.get("key_sha256"), "readers": graded.get("readers"),
        "summary": summary, "identity": identity, "reveals": reveals,
        "look_alikes": look_alikes, "order": order, "final": final, "ever": ever,
        "containers": containers,
        "ungraded_counts": graded.get("ungraded_counts", {}),
        "dropped": len(graded.get("dropped", [])),
    }


def scorecard_md(card: Mapping[str, Any], title: str = "Book scorecard") -> str:
    """Render ``grade_book`` output as a Markdown scorecard."""
    fmt = lambda x: "n/a" if x is None else f"{x:.3f}"  # noqa: E731
    s, ident = card["summary"], card["identity"]
    lines = [f"# {title}", "", f"Readers: {', '.join(card.get('readers') or [])}; "
             f"{card['dropped']} entries dropped.", "",
             "| measure | score |", "|---|---|",
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
    lines += ["", "## Not graded in V1", ""]
    lines += [f"- {k}: {n} entries" for k, n in sorted(card["ungraded_counts"].items())]
    lines.append("")
    return "\n".join(lines)


def write_scorecard(card: Mapping[str, Any], out_dir: str | Path, stem: str = "book_scorecard",
                    title: str = "Book scorecard") -> tuple[Path, Path]:
    """Write ``<stem>.md`` and ``<stem>.json`` into ``out_dir``; return both paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md, js = out / f"{stem}.md", out / f"{stem}.json"
    md.write_text(scorecard_md(card, title))
    js.write_text(json.dumps(card, indent=2, sort_keys=True) + "\n")
    return md, js


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, help="a run_book.py output directory")
    ap.add_argument("--graded", required=True, help="the book's graded.json")
    ap.add_argument("--out", default=None, help="where to write (default: the run directory)")
    ap.add_argument("--world-id", default=None, help="default: the run's meta.json")
    args = ap.parse_args(argv)
    from patternbuffer.mirror import open_read_only_copy

    run = Path(args.run)
    world_id = args.world_id or json.loads((run / "meta.json").read_text())["world_id"]
    # a sealed in-memory copy taken through `mode=ro`: the build artifact is
    # never opened for writing (bytes and mtime unchanged)
    world = open_read_only_copy(run / "fresh_ingest.world", world_id)
    try:
        card = grade_book(world, world.registry, json.loads(Path(args.graded).read_text()))
    finally:
        world.close()
    md, js = write_scorecard(card, args.out or run, title=f"Book scorecard ({run.name})")
    print(f"{md}\n{js}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
