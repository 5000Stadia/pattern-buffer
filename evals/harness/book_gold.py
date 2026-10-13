"""Two readers, one gold (BOOK-RUN-V1 §4): build a book's ``graded.json``.

The writer's answer key is checked against the text by two independent
readers. Only the entries both readers marked ``ok`` are graded; everything
else is dropped and listed with each reader's note, so nothing is silently
lost. Deterministic, no model call.

CLI:
    python evals/harness/book_gold.py --key evals/books/<slug>/key.json \\
        --verdicts readerA.json readerB.json --out evals/books/<slug>/graded.json \\
        [--dropped-md dropped.md]

A verdict file is refused when its ``key_sha256`` is not the hash of the key's
bytes, when it misses an item or gives one twice, or when the two readers share
a label. The key itself is refused when an id-valued field names no entity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from grade_registry import normalize
except ImportError:  # imported as evals.harness.book_gold
    from evals.harness.grade_registry import normalize

logger = logging.getLogger(__name__)

VERDICTS = ("ok", "wrong", "unclear")
# Sections the grader scores, and sections it only counts (natural-language
# statements that need a judge model; BOOK-RUN-V1 §3.6).
GRADED_SECTIONS = ("same_as", "not_same", "locations", "holdings", "containers")
UNGRADED_SECTIONS = ("knowledge", "false_beliefs", "corrections")

_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def fold_quotes(s: str) -> str:
    """Map curly single quotes to ``'`` and curly double quotes to ``"``;
    nothing else changes."""
    return s.translate(_QUOTES)


def book_normalize(s: str) -> str:
    """The book matcher's string key (BOOK-RUN-V1 §1.1): ``fold_quotes`` and
    then ``grade_registry.normalize`` (lowercase, collapsed whitespace, one
    leading article dropped)."""
    return normalize(fold_quotes(s))


class VerdictError(ValueError):
    """A key or verdict file the gold builder refuses."""


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def _section(key: Mapping[str, Any], name: str) -> list[Any]:
    return list(key.get(name, []) or [])


def check_key(key: Mapping[str, Any]) -> None:
    """Refuse a key whose id-valued fields name no entity (BOOK-RUN-V1 §1.1)."""
    ids = set(key.get("entities", {}))
    bad: list[str] = []

    def need(where: str, *names: str) -> None:
        for n in names:
            if n not in ids:
                bad.append(f"{where}: {n!r}")

    for i, row in enumerate(_section(key, "same_as")):
        need(f"same_as[{i}]", row[0])
    for i, row in enumerate(_section(key, "not_same")):
        need(f"not_same[{i}]", row[0], row[1])
    for section, target in (("locations", "in"), ("holdings", "held_by")):
        for i, row in enumerate(_section(key, section)):
            need(f"{section}[{i}]", row["entity"], row[target])
    for i, row in enumerate(_section(key, "containers")):
        need(f"containers[{i}]", row["container"], *row["contents"])
    if bad:
        raise VerdictError("key names unknown entity ids: " + "; ".join(bad))


def check_verdicts(verdicts: Mapping[str, Any], key: Mapping[str, Any], key_sha: str,
                   where: str) -> None:
    """Refuse a verdict file with the wrong key hash, a missing or repeated
    item, or a verdict outside ``ok|wrong|unclear``."""
    if verdicts.get("key_sha256") != key_sha:
        raise VerdictError(f"{where}: key_sha256 is not the hash of the key beside it")
    if not isinstance(verdicts.get("reader"), str) or not verdicts["reader"]:
        raise VerdictError(f"{where}: no reader label")
    entities = verdicts.get("entities", {})
    missing = sorted(set(key.get("entities", {})) - set(entities))
    extra = sorted(set(entities) - set(key.get("entities", {})))
    if missing or extra:
        raise VerdictError(f"{where}: entities missing {missing} / unknown {extra}")
    for k, v in entities.items():
        if v.get("verdict") not in VERDICTS:
            raise VerdictError(f"{where}: entities.{k} has verdict {v.get('verdict')!r}")
    # r2.2: the reader's own re-judgement of an entity on its graded fields only
    fields = verdicts.get("entities_fields", {}) or {}
    unknown = sorted(set(fields) - set(key.get("entities", {})))
    if unknown:
        raise VerdictError(f"{where}: entities_fields names unknown entities {unknown}")
    for k, v in fields.items():
        if not isinstance(v, Mapping) or v.get("verdict") not in VERDICTS:
            raise VerdictError(f"{where}: entities_fields.{k} has no valid verdict")
    for section in GRADED_SECTIONS + UNGRADED_SECTIONS:
        want = len(_section(key, section))
        got = [item.get("i") for item in _section(verdicts, section)]
        if not all(isinstance(i, int) for i in got) or sorted(got) != list(range(want)):
            raise VerdictError(f"{where}: {section} must hold exactly one verdict for "
                               f"each of {want} items (got indices {got})")
        for item in verdicts.get(section, []) or []:
            if item.get("verdict") not in VERDICTS:
                raise VerdictError(f"{where}: {section}[{item['i']}] has verdict "
                                   f"{item.get('verdict')!r}")


def _by_index(verdicts: Mapping[str, Any], section: str) -> dict[int, Mapping[str, Any]]:
    return {item["i"]: item for item in _section(verdicts, section)}


def build_gold(key_bytes: bytes, verdict_docs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The ``graded.json`` content from the key's bytes and two readers' verdict
    documents. Raises ``VerdictError`` on any refusal (see the module doc)."""
    key = json.loads(key_bytes)
    key_sha = sha256_bytes(key_bytes)
    check_key(key)
    if len(verdict_docs) != 2:
        raise VerdictError(f"exactly two readers are required, got {len(verdict_docs)}")
    docs = sorted(verdict_docs, key=lambda d: str(d.get("reader")))
    for d in docs:
        check_verdicts(d, key, key_sha, f"reader {d.get('reader')!r}")
    readers = [d["reader"] for d in docs]
    if readers[0] == readers[1]:
        raise VerdictError(f"the two readers share the label {readers[0]!r}")

    def entity_verdict(d: Mapping[str, Any], kid: str) -> Mapping[str, Any]:
        """r2.2: an entity is judged on kind and aliases only (first_chapter is
        never graded); the reader's ``entities_fields`` entry, when present,
        is that judgement and stands in for the whole-entry verdict."""
        return (d.get("entities_fields") or {}).get(kid) or d["entities"][kid]

    def verdict_of(d: Mapping[str, Any], section: str, i: int) -> tuple[str, str]:
        item = _by_index(d, section)[i]
        return item["verdict"], item.get("note", "") or ""

    dropped: list[dict[str, Any]] = []

    # entities: both readers ok
    entity_ok: dict[str, bool] = {}
    for kid in key.get("entities", {}):
        vs = {r: entity_verdict(d, kid)["verdict"] for r, d in zip(readers, docs)}
        ns = {r: entity_verdict(d, kid).get("note", "") or "" for r, d in zip(readers, docs)}
        entity_ok[kid] = all(v == "ok" for v in vs.values())
        if not entity_ok[kid]:
            dropped.append({"id": f"entities.{kid}", "verdicts": vs, "notes": ns})

    entities: dict[str, Any] = {}
    dropped_aliases: list[dict[str, Any]] = []
    for kid, ent in key.get("entities", {}).items():
        if not entity_ok[kid]:
            continue
        flagged: dict[str, list[str]] = {}
        for r, d in zip(readers, docs):
            for bad in entity_verdict(d, kid).get("bad_aliases", []) or []:
                flagged.setdefault(book_normalize(bad), []).append(r)
        keep = []
        for alias in ent.get("aliases", []):
            by = flagged.get(book_normalize(alias))
            if by:
                dropped_aliases.append({"entity": kid, "alias": alias, "by": sorted(set(by))})
            else:
                keep.append(alias)
        entities[kid] = {"kind": ent.get("kind"), "aliases": keep}

    def judge(section: str, i: int, refs: Sequence[str]) -> bool:
        """Whether item ``section[i]`` is graded; otherwise record why not."""
        item_id = f"{section}[{i}]"
        vs, ns = {}, {}
        for r, d in zip(readers, docs):
            vs[r], ns[r] = verdict_of(d, section, i)
        if not all(v == "ok" for v in vs.values()):
            dropped.append({"id": item_id, "verdicts": vs, "notes": ns})
            return False
        if any(not entity_ok[x] for x in refs):
            dropped.append({"id": item_id, "verdicts": {"entity": "dropped"}, "notes": {}})
            return False
        return True

    same_as = []
    for i, (ent, alias, chapter) in enumerate(_section(key, "same_as")):
        if judge("same_as", i, [ent]):
            same_as.append({"id": f"same_as[{i}]", "entity": ent, "alias": alias,
                            "chapter": chapter})
    not_same = []
    for i, row in enumerate(_section(key, "not_same")):
        if judge("not_same", i, [row[0], row[1]]):
            not_same.append({"id": f"not_same[{i}]", "a": row[0], "b": row[1]})

    moves: dict[str, list[dict[str, Any]]] = {}
    for section, target in (("locations", "in"), ("holdings", "held_by")):
        for i, row in enumerate(_section(key, section)):
            if judge(section, i, [row["entity"], row[target]]):
                moves.setdefault(row["entity"], []).append({
                    "id": f"{section}[{i}]", "to": row[target],
                    "from_chapter": row["from_chapter"], "to_chapter": row.get("to_chapter")})

    containers = []
    dropped_contents: list[dict[str, str]] = []
    for i, row in enumerate(_section(key, "containers")):
        if not judge("containers", i, [row["container"]]):
            continue
        contents = [c for c in row["contents"] if entity_ok[c]]
        dropped_contents += [{"id": f"containers[{i}]", "entity": c}
                             for c in row["contents"] if not entity_ok[c]]
        if not contents:
            dropped.append({"id": f"containers[{i}]", "verdicts": {"entity": "dropped"},
                            "notes": {}})
            continue
        containers.append({"id": f"containers[{i}]", "container": row["container"],
                           "contents": contents})

    gold: dict[str, Any] = {
        "key_sha256": key_sha,
        "readers": readers,
        "entities": entities,
        "same_as": same_as,
        "not_same": not_same,
        "moves": moves,
        "containers": containers,
        "dropped": sorted(dropped, key=lambda e: e["id"]),
        "dropped_aliases": sorted(dropped_aliases, key=lambda e: (e["entity"], e["alias"])),
        "dropped_contents": sorted(dropped_contents, key=lambda e: (e["id"], e["entity"])),
        "ungraded_counts": {s: len(_section(key, s)) for s in UNGRADED_SECTIONS},
    }
    return gold


def gold_json(gold: Mapping[str, Any]) -> str:
    """The canonical text of ``graded.json``: sorted keys, so the same inputs
    give the same bytes."""
    return json.dumps(gold, indent=2, sort_keys=True) + "\n"


def dropped_markdown(gold: Mapping[str, Any]) -> str:
    """Everything dropped, with each reader's note, as Markdown for the book's
    README (BOOK-RUN-V1 §4)."""
    lines = ["# Dropped from the graded set", "",
             f"Readers: {', '.join(gold['readers'])}. Key `{gold['key_sha256']}`.", ""]
    lines += ["## Entries", ""]
    for d in gold["dropped"]:
        vs = ", ".join(f"{r}: {v}" for r, v in d["verdicts"].items())
        notes = "; ".join(f"{r}: {n}" for r, n in d["notes"].items() if n)
        lines.append(f"- `{d['id']}` ({vs})" + (f" - {notes}" if notes else ""))
    if not gold["dropped"]:
        lines.append("- none")
    lines += ["", "## Aliases", ""]
    lines += [f"- `{a['entity']}`: {a['alias']!r} (flagged by {', '.join(a['by'])})"
              for a in gold["dropped_aliases"]] or ["- none"]
    lines += ["", "## Container contents", ""]
    lines += [f"- `{c['id']}`: `{c['entity']}`" for c in gold["dropped_contents"]] or ["- none"]
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--key", required=True, help="the frozen key.json")
    ap.add_argument("--verdicts", nargs=2, required=True, metavar="FILE",
                    help="the two readers' final verdict files")
    ap.add_argument("--out", required=True, help="graded.json to write")
    ap.add_argument("--dropped-md", default=None, help="also write the dropped list as Markdown")
    args = ap.parse_args(argv)
    docs = [json.loads(Path(p).read_text()) for p in args.verdicts]
    gold = build_gold(Path(args.key).read_bytes(), docs)
    Path(args.out).write_text(gold_json(gold))
    if args.dropped_md:
        Path(args.dropped_md).write_text(dropped_markdown(gold))
    logger.info("graded.json: %d entities, %d dropped", len(gold["entities"]), len(gold["dropped"]))
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
