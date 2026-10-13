"""Two readers, one gold (BOOK-RUN-V1 §4): build a book's ``graded.json``.

The writer's answer key is checked against the text by two independent
readers. Only the entries both readers marked ``ok`` are graded; everything
else is dropped and listed with each reader's note, so nothing is silently
lost. Deterministic, no model call.

CLI:
    python evals/harness/book_gold.py --key evals/books/<slug>/key.json \\
        --verdicts readerA.json readerB.json --out evals/books/<slug>/graded.json \\
        [--dropped-md dropped.md] [--through-chapter N]

``--through-chapter N`` (STAGE-MODELS-V1) writes a **windowed** ``graded.json`` for a build
of chapters 1..N, stamped ``"through_chapter": N``: only what a reader of those chapters
could know. The window is cut here, where the full key is (``window_gold``).

GRADE-LEAKS-V1 §2: a key may also carry ``alias_first_chapter`` on its entities
and ``as_fact`` / ``corrected_as_fact`` fact forms on ``false_beliefs``,
``corrections`` and ``knowledge``. Each reader's verdict file may then carry a
``fields`` object with a per-field verdict (``"ok"`` or ``"wrong: <why>"``);
only a field both readers marked ``ok`` lands in the new ``graded.json``
sections (``alias_first_chapter``, ``beliefs``, ``corrections``, ``knowledge``),
and every other field is listed in ``dropped_fields``. A key without those
fields builds exactly the ``graded.json`` it always did.

A verdict file is refused when its ``key_sha256`` is not the hash of the key's
bytes, when it misses an item or gives one twice, or when the two readers share
a label. The key itself is refused when an id-valued field names no entity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
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

# GRADE-LEAKS-V1 §2: the key sections that carry structured fact forms, and
# which fields of each are verified one by one.
FACT_FIELDS = {"false_beliefs": ("as_fact",), "corrections": ("as_fact", "corrected_as_fact"),
               "knowledge": ("as_fact",)}
FIELD_SECTIONS = ("alias_first_chapter",) + tuple(FACT_FIELDS)
# graded.json section for each key section
GRADED_FIELD_SECTION = {"alias_first_chapter": "alias_first_chapter", "false_beliefs": "beliefs",
                        "corrections": "corrections", "knowledge": "knowledge"}

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


def fact_problem(fact: Any, ids: Sequence[str] | set[str]) -> str | None:
    """Why ``fact`` is not a fact form (GRADE-LEAKS-V1 §2), or ``None`` when it
    is: ``{"entity": <key>, "attribute": <plain str>, "value": {"entity": <key>}
    | {"literal": <JSON scalar>}}``, every key named an entity of the same key."""
    if not isinstance(fact, Mapping) or set(fact) != {"entity", "attribute", "value"}:
        return "not an {entity, attribute, value} object"
    if fact["entity"] not in ids:
        return f"entity {fact['entity']!r} is not an entity of the key"
    if not isinstance(fact["attribute"], str) or not fact["attribute"].strip():
        return "attribute is not a plain string"
    value = fact["value"]
    if not isinstance(value, Mapping) or len(value) != 1:
        return "value is not {entity: key} or {literal: scalar}"
    if "entity" in value:
        return None if value["entity"] in ids else f"value entity {value['entity']!r} is not an entity of the key"
    if "literal" in value:
        lit = value["literal"]
        return None if lit is None or isinstance(lit, (str, int, float, bool)) else "literal is not a JSON scalar"
    return "value is not {entity: key} or {literal: scalar}"


def _check_fields(key: Mapping[str, Any]) -> list[str]:
    """Problems with the GRADE-LEAKS-V1 fields of ``key`` (empty when none or all fine)."""
    ids = set(key.get("entities", {}))
    bad: list[str] = []
    for kid, ent in key.get("entities", {}).items():
        afc = ent.get("alias_first_chapter")
        if afc is None:
            continue
        if not isinstance(afc, Mapping):
            bad.append(f"entities.{kid}.alias_first_chapter: not an object")
            continue
        for alias, chapter in afc.items():
            if alias not in ent.get("aliases", []):
                bad.append(f"entities.{kid}.alias_first_chapter: {alias!r} is not one of its aliases")
            if not isinstance(chapter, int) or isinstance(chapter, bool):
                bad.append(f"entities.{kid}.alias_first_chapter[{alias!r}]: chapter is not an int")
    for section, names in FACT_FIELDS.items():
        for i, entry in enumerate(_section(key, section)):
            for name in names:
                if name not in entry:
                    continue
                fact = entry[name]
                if fact is None:
                    continue
                problem = fact_problem(fact, ids)
                if problem:
                    bad.append(f"{section}[{i}].{name}: {problem}")
            if section == "knowledge" and entry.get("as_fact") is not None \
                    and entry.get("who") not in ids:
                bad.append(f"knowledge[{i}].who: {entry.get('who')!r} is not an entity of the key")
            if section == "false_beliefs" and entry.get("as_fact") is not None:
                if entry.get("who") not in ids:
                    bad.append(f"false_beliefs[{i}].who: {entry.get('who')!r} is not an entity of the key")
    return bad


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
    malformed = _check_fields(key)
    if malformed:
        raise VerdictError("key has malformed structured fields: " + "; ".join(malformed))


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
    fields = verdicts.get("entities_fields")
    if fields is None:
        fields = {}
    elif not isinstance(fields, Mapping):
        raise VerdictError(f"{where}: entities_fields must be an object of entity verdicts")
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
    if verdicts.get("fields") is not None:
        _check_field_verdicts(verdicts["fields"], key, where)


def field_verdict_ok(v: Any) -> bool:
    """Whether ``v`` is a valid per-field verdict (GRADE-LEAKS-V1 r2.4): exactly ``"ok"``, or
    ``"wrong: "`` followed by a non-empty reason. Nothing else is accepted."""
    return isinstance(v, str) and (v == "ok" or (v.startswith("wrong: ") and bool(v[len("wrong: "):].strip())))


def _check_field_verdicts(fields: Any, key: Mapping[str, Any], where: str) -> None:
    """Refuse a malformed per-field verdict object (GRADE-LEAKS-V1 §2): it must
    name only fields the key has, each with a string verdict."""
    if not isinstance(fields, Mapping):
        raise VerdictError(f"{where}: fields must be an object")
    unknown = sorted(set(fields) - set(FIELD_SECTIONS))
    if unknown:
        raise VerdictError(f"{where}: fields names unknown sections {unknown}")
    entities = key.get("entities", {})
    for kid, by_alias in (fields.get("alias_first_chapter") or {}).items():
        afc = (entities.get(kid) or {}).get("alias_first_chapter")
        if not isinstance(by_alias, Mapping) or not isinstance(afc, Mapping):
            raise VerdictError(f"{where}: fields.alias_first_chapter.{kid} names no such field in the key")
        for alias, v in by_alias.items():
            if alias not in afc:
                raise VerdictError(f"{where}: fields.alias_first_chapter.{kid}[{alias!r}] names an "
                                   "alias the key does not map")
            if not field_verdict_ok(v):
                raise VerdictError(f"{where}: fields.alias_first_chapter.{kid}[{alias!r}] is {v!r}, "
                                   "not 'ok' or 'wrong: <reason>'")
    for section, names in FACT_FIELDS.items():
        entries = _section(key, section)
        for idx, by_name in (fields.get(section) or {}).items():
            ok_idx = isinstance(idx, str) and idx.isdigit() and int(idx) < len(entries)
            if not ok_idx or not isinstance(by_name, Mapping):
                raise VerdictError(f"{where}: fields.{section}[{idx!r}] names no such entry")
            for name, v in by_name.items():
                if name not in names or name not in entries[int(idx)]:
                    raise VerdictError(f"{where}: fields.{section}[{idx}].{name} names a field "
                                       "the entry does not have")
                if not field_verdict_ok(v):
                    raise VerdictError(f"{where}: fields.{section}[{idx}].{name} is {v!r}, "
                                       "not 'ok' or 'wrong: <reason>'")


def _by_index(verdicts: Mapping[str, Any], section: str) -> dict[int, Mapping[str, Any]]:
    return {item["i"]: item for item in _section(verdicts, section)}


def _has_fields(key: Mapping[str, Any]) -> bool:
    """Whether ``key`` carries any GRADE-LEAKS-V1 field (else it builds as it always did)."""
    if any("alias_first_chapter" in e for e in key.get("entities", {}).values()):
        return True
    return any(name in entry for section, names in FACT_FIELDS.items()
               for entry in _section(key, section) for name in names)


def _field_verdict(doc: Mapping[str, Any], section: str, where: Sequence[Any]) -> tuple[str, str]:
    """One reader's verdict on one field as ``(ok | wrong | missing, why)``."""
    node: Any = (doc.get("fields") or {}).get(section) or {}
    for step in where:
        node = node.get(step) if isinstance(node, Mapping) else None
    if node is None:
        return "missing", "no verdict"
    if node == "ok":
        return "ok", ""
    return "wrong", node[len("wrong: "):].strip()


def _field_gold(key: Mapping[str, Any], docs: Sequence[Mapping[str, Any]], readers: Sequence[str],
                entity_ok: Mapping[str, bool], dropped_alias_set: set[tuple[str, str]],
                entry_verdict: Any) -> dict[str, Any]:
    """The GRADE-LEAKS-V1 sections of ``graded.json``: the fields both readers
    marked ``ok`` (and whose entry and entities stand), ``dropped_fields`` for
    every other, and ``field_counts``. Empty for a key without those fields."""
    if not _has_fields(key):
        return {}
    dropped: list[dict[str, Any]] = []
    counts = {s: {"entries": 0, "verified": 0, "dropped": 0} for s in GRADED_FIELD_SECTION.values()}

    def judge(section: str, field_id: str, where: Sequence[Any], blocked: tuple[str, dict, dict] | None) -> bool:
        """Count one field and say whether it is graded; record why not."""
        c = counts[GRADED_FIELD_SECTION[section]]
        c["entries"] += 1
        if blocked is None:
            vs, ns = {}, {}
            for r, d in zip(readers, docs):
                vs[r], ns[r] = _field_verdict(d, section, where)
            if all(v == "ok" for v in vs.values()):
                c["verified"] += 1
                return True
            reason = "a reader did not mark the field ok"
        else:
            reason, vs, ns = blocked
        c["dropped"] += 1
        dropped.append({"id": field_id, "reason": reason, "verdicts": vs, "notes": ns})
        return False

    alias_first: dict[str, dict[str, int]] = {}
    for kid, ent in key.get("entities", {}).items():
        for alias, chapter in sorted((ent.get("alias_first_chapter") or {}).items()):
            if not entity_ok[kid]:
                blocked: tuple[str, dict, dict] | None = ("entity dropped", {"entity": "dropped"}, {})
            elif (kid, alias) in dropped_alias_set:
                blocked = ("alias dropped (bad_aliases)", {"alias": "dropped"}, {})
            else:
                blocked = None
            if judge("alias_first_chapter", f"entities.{kid}.alias_first_chapter[{alias}]",
                     (kid, alias), blocked):
                alias_first.setdefault(kid, {})[alias] = chapter

    graded: dict[str, list[dict[str, Any]]] = {"beliefs": [], "corrections": [], "knowledge": []}
    for section, names in FACT_FIELDS.items():
        for i, entry in enumerate(_section(key, section)):
            item_id = f"{section}[{i}]"
            entry_vs, entry_ns = {}, {}
            for r, d in zip(readers, docs):
                entry_vs[r], entry_ns[r] = entry_verdict(d, section, i)
            entry_ok = all(v == "ok" for v in entry_vs.values())
            verified: dict[str, Any] = {}
            for name in names:
                if name not in entry:
                    continue
                fact = entry[name]
                field_id = f"{item_id}.{name}"
                if fact is None:
                    if name == "corrected_as_fact":     # the correction only negates the claim
                        continue
                    counts[GRADED_FIELD_SECTION[section]]["entries"] += 1
                    counts[GRADED_FIELD_SECTION[section]]["dropped"] += 1
                    dropped.append({"id": field_id, "reason": "as_fact is null: not one fact",
                                    "verdicts": {}, "notes": {}})
                    continue
                refs = [fact["entity"]] + ([fact["value"]["entity"]] if "entity" in fact["value"] else []) \
                    + ([entry["who"]] if section != "corrections" else [])
                if not entry_ok:
                    blocked = ("the entry-level verdict is not ok for both readers", entry_vs, entry_ns)
                elif any(not entity_ok[x] for x in refs):
                    blocked = ("entity dropped", {"entity": "dropped"}, {})
                else:
                    blocked = None
                if judge(section, field_id, (str(i), name), blocked):
                    verified[name] = fact
            if not verified:
                continue
            if section == "false_beliefs":
                graded["beliefs"].append({
                    "id": item_id, "who": entry["who"], "fact": verified["as_fact"],
                    "from_chapter": entry.get("from_chapter"),
                    "corrected_chapter": entry.get("corrected_chapter")})
            elif section == "corrections":
                graded["corrections"].append({
                    "id": item_id, "stated_chapter": entry.get("stated_chapter"),
                    "corrected_chapter": entry.get("corrected_chapter"),
                    "as_fact": verified.get("as_fact"),
                    "corrected_as_fact": verified.get("corrected_as_fact")})
            else:
                graded["knowledge"].append({
                    "id": item_id, "who": entry["who"], "fact": verified["as_fact"],
                    "mode": "never_learns" if "never_learns" in entry else "learns",
                    "chapter": entry.get("chapter")})
    return {"alias_first_chapter": alias_first, **graded,
            "dropped_fields": sorted(dropped, key=lambda e: e["id"]), "field_counts": counts}


def build_gold(key_bytes: bytes, verdict_docs: Sequence[Mapping[str, Any]],
               through_chapter: int | None = None) -> dict[str, Any]:
    """The ``graded.json`` content from the key's bytes and two readers' verdict
    documents. Raises ``VerdictError`` on any refusal (see the module doc).
    ``through_chapter`` windows it (see ``window_gold``)."""
    key = json.loads(key_bytes)
    if through_chapter is not None:
        n_chapters = len(key.get("chapters", []) or [])
        if isinstance(through_chapter, bool) or not isinstance(through_chapter, int) \
                or not 1 <= through_chapter <= n_chapters:
            raise VerdictError(f"--through-chapter {through_chapter!r} is not in 1..{n_chapters} "
                               "(the key's chapter count)")
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

    field_gold = _field_gold(key, docs, readers, entity_ok,
                             {(a["entity"], a["alias"]) for a in dropped_aliases}, verdict_of)
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
    gold.update(field_gold)
    if through_chapter is not None:
        gold = window_gold(gold, key, through_chapter)
    return gold


# ------------------------------------------------------ the window (STAGE-MODELS-V1)

_ID_INDEX = re.compile(r"^(\w+)\[(\d+)\]")


def _chapter(value: Any, where: str, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise VerdictError(f"cannot window the key: {where} is {value!r}, not a chapter number")
    return value


def window_gold(gold: Mapping[str, Any], key: Mapping[str, Any], n: int) -> dict[str, Any]:
    """The part of ``gold`` a reader of chapters 1..``n`` could know, stamped
    ``"through_chapter": n``. The rules, from the full ``key``:

    - entities with ``first_chapter <= n`` (an entity without one refuses the window);
      aliases only where ``alias_first_chapter <= n`` when the key gives one;
    - ``same_as`` revealed by ``n``; ``not_same`` pairs whose entities both exist by ``n``;
    - locations and holdings are half-open ``[from_chapter, to_chapter)``: in when
      ``from_chapter <= n``; a ``to_chapter`` of null or beyond ``n`` stays open
      (``to_chapter: null``), otherwise as written; nothing is clipped;
    - containers revealed by ``n``; knowledge with ``chapter <= n``;
    - false beliefs with ``from_chapter <= n``, held through ``n`` (``corrected_chapter`` null)
      when their correction comes after it;
    - corrections only when ``corrected_chapter <= n``. One stated by ``n`` and not yet
      corrected is *pending*: outside every item and denominator, counted in
      ``pending_corrections``.

    Dropped lists and the counts follow the window. Raises ``VerdictError`` when the key
    lacks a chapter the rules need."""
    entities_k = key.get("entities", {})
    first = {k: _chapter(e.get("first_chapter"), f"entities.{k}.first_chapter")
             for k, e in entities_k.items()}
    present = {k for k, c in first.items() if c <= n}

    def entry_in_window(item_id: str) -> bool:
        """Whether a dropped-list id (``entities.X``, ``entities.X.alias_first_chapter[a]``,
        ``same_as[3]``, ``corrections[1].as_fact``...) names something inside the window."""
        if item_id.startswith("entities."):
            kid = item_id.split(".")[1]
            if kid not in present:
                return False
            m = re.match(r"^entities\.[^.]+\.alias_first_chapter\[(.*)\]$", item_id, re.S)
            if m:
                chapter = (entities_k[kid].get("alias_first_chapter") or {}).get(m.group(1))
                return chapter is None or chapter <= n
            return True
        m = _ID_INDEX.match(item_id)
        if not m:
            return True
        section, i = m.group(1), int(m.group(2))
        row = _section(key, section)[i]
        if section == "same_as":
            return _chapter(row[2], f"same_as[{i}]") <= n
        if section == "not_same":
            return row[0] in present and row[1] in present
        if section in ("locations", "holdings"):
            return _chapter(row["from_chapter"], f"{section}[{i}].from_chapter") <= n
        if section == "containers":
            return _chapter(row["revealed_chapter"], f"containers[{i}].revealed_chapter") <= n
        if section == "knowledge":
            return _chapter(row.get("chapter"), f"knowledge[{i}].chapter") <= n
        if section == "false_beliefs":
            return _chapter(row["from_chapter"], f"false_beliefs[{i}].from_chapter") <= n
        if section == "corrections":
            c = _chapter(row["corrected_chapter"], f"corrections[{i}].corrected_chapter", nullable=True)
            return c is not None and c <= n
        return True

    out: dict[str, Any] = dict(gold)
    # entities, with their aliases
    ents: dict[str, Any] = {}
    for kid, ent in gold["entities"].items():
        if kid not in present:
            continue
        afc = entities_k[kid].get("alias_first_chapter") or {}
        ents[kid] = {**ent, "aliases": [a for a in ent["aliases"]
                                        if a not in afc or _chapter(afc[a], f"{kid} alias {a!r}") <= n]}
    out["entities"] = ents
    if "alias_first_chapter" in gold:
        out["alias_first_chapter"] = {
            kid: {a: c for a, c in by.items() if c <= n and a in ents[kid]["aliases"]}
            for kid, by in gold["alias_first_chapter"].items() if kid in ents
            and any(c <= n and a in ents[kid]["aliases"] for a, c in by.items())}
    out["same_as"] = [r for r in gold["same_as"] if _chapter(r["chapter"], r["id"]) <= n]
    out["not_same"] = [r for r in gold["not_same"] if r["a"] in present and r["b"] in present]
    moves: dict[str, list[dict[str, Any]]] = {}
    for kid, rows in gold["moves"].items():
        for r in rows:
            if _chapter(r["from_chapter"], r["id"]) > n:
                continue
            to = _chapter(r["to_chapter"], r["id"], nullable=True)
            moves.setdefault(kid, []).append({**r, "to_chapter": to if to is not None and to <= n else None})
    out["moves"] = moves
    out["containers"] = [r for r in gold["containers"] if entry_in_window(r["id"])]
    if "knowledge" in gold:
        out["knowledge"] = [r for r in gold["knowledge"] if _chapter(r["chapter"], r["id"]) <= n]
    if "beliefs" in gold:
        beliefs = []
        for r in gold["beliefs"]:
            if _chapter(r["from_chapter"], r["id"]) > n:
                continue
            c = _chapter(r["corrected_chapter"], r["id"], nullable=True)
            beliefs.append({**r, "corrected_chapter": c if c is not None and c <= n else None})
        out["beliefs"] = beliefs
    out["pending_corrections"] = 0
    if "corrections" in gold:
        graded_c, pending = [], 0
        for r in gold["corrections"]:
            c = _chapter(r["corrected_chapter"], r["id"], nullable=True)
            if c is not None and c <= n:
                graded_c.append(r)
            elif r.get("stated_chapter") is None or _chapter(r["stated_chapter"], r["id"]) <= n:
                pending += 1
        out["corrections"] = graded_c
        out["pending_corrections"] = pending
    for name in ("dropped", "dropped_fields"):
        if name in gold:
            out[name] = [d for d in gold[name] if entry_in_window(d["id"])]
    out["dropped_aliases"] = [d for d in gold["dropped_aliases"] if d["entity"] in present]
    out["dropped_contents"] = [d for d in gold["dropped_contents"] if entry_in_window(d["id"])]
    # counts follow the window
    out["ungraded_counts"] = {
        s: sum(1 for i in range(len(_section(key, s))) if entry_in_window(f"{s}[{i}]"))
        for s in UNGRADED_SECTIONS}
    if "field_counts" in gold:
        verified = {
            "alias_first_chapter": sum(len(v) for v in out.get("alias_first_chapter", {}).values()),
            "beliefs": len(out.get("beliefs", [])),
            "corrections": sum((r.get("as_fact") is not None) + (r.get("corrected_as_fact") is not None)
                               for r in out.get("corrections", [])),
            "knowledge": len(out.get("knowledge", []))}
        by_key_section = {"false_beliefs": "beliefs", "corrections": "corrections",
                          "knowledge": "knowledge"}
        dropped_by = dict.fromkeys(verified, 0)
        for d in out["dropped_fields"]:
            m = _ID_INDEX.match(d["id"])
            dropped_by[by_key_section.get(m.group(1) if m else "", "alias_first_chapter")] += 1
        out["field_counts"] = {name: {"entries": verified[name] + dropped_by[name],
                                      "verified": verified[name], "dropped": dropped_by[name]}
                               for name in verified}
    out["through_chapter"] = n
    return out


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
    if "dropped_fields" in gold:
        lines += ["", "## Fields (GRADE-LEAKS-V1)", ""]
        for d in gold["dropped_fields"]:
            vs = ", ".join(f"{r}: {v}" for r, v in d["verdicts"].items())
            notes = "; ".join(f"{r}: {n}" for r, n in d["notes"].items() if n)
            lines.append(f"- `{d['id']}` ({d['reason']}" + (f"; {vs}" if vs else "") + ")"
                         + (f" - {notes}" if notes else ""))
        if not gold["dropped_fields"]:
            lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--key", required=True, help="the frozen key.json")
    ap.add_argument("--verdicts", nargs=2, required=True, metavar="FILE",
                    help="the two readers' final verdict files")
    ap.add_argument("--out", required=True, help="graded.json to write")
    ap.add_argument("--dropped-md", default=None, help="also write the dropped list as Markdown")
    ap.add_argument("--through-chapter", type=int, default=None, metavar="N",
                    help="write a graded.json windowed to chapters 1..N and stamped with N")
    args = ap.parse_args(argv)
    docs = [json.loads(Path(p).read_text()) for p in args.verdicts]
    gold = build_gold(Path(args.key).read_bytes(), docs, through_chapter=args.through_chapter)
    Path(args.out).write_text(gold_json(gold))
    if args.dropped_md:
        Path(args.dropped_md).write_text(dropped_markdown(gold))
    logger.info("graded.json: %d entities, %d dropped", len(gold["entities"]), len(gold["dropped"]))
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
