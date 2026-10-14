"""Category passes: a manifest for prose with no author (BUILD-LIBRARY-V1 §6).

One model call per category (beings, places, things, groups), all at once,
each over the whole text and labelled ``stage="registry"``,
``unit="pass:<category>"``. Each lists ``(type, name, aliases, first quote)``.
Merging is code:

- entries merge on (type, normalized name), and only when no pass listed two
  entries under that key (a pass that lists two Johns says they are two);
- a pass never joins two names into one being: an alias is kept only when it
  shares a word (other than an article or a title) with the entry's name, so a
  different name or a description listed as an alias is dropped; hidden
  identities are a later interpretation pass, written as personas and reveals;
- each entry's anchor is its pass's first quote, or, when that quote does not
  occur exactly once in the text, the first sentence that names the entry and
  occurs once.

The result is a ``Manifest``, which goes through ``validate()`` like an
author's.
"""

from __future__ import annotations

import copy
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from patternbuffer.build.labels import labelled_context
from patternbuffer.build.manifest import (
    SPECIES_TYPES,
    TYPES,
    Entry,
    Manifest,
    is_role_word,
    normalize_type,
)
from patternbuffer.build.text import (
    ARTICLES,
    TITLES,
    Book,
    contains_run,
    join_key,
    slug,
    tokens,
)

logger = logging.getLogger(__name__)

CATEGORY_HEAD = "Name the beings, places and things (build library, {category} pass)"

# Each category's types; the first is what an entry outside the closed set is
# filed as (a being outside it is a person with that role word, k4's rule).
CATEGORY_TYPES: dict[str, tuple[str, ...]] = {
    "beings": ("person", "animal", "creature"),
    "places": ("place",),
    "things": ("object",),
    "groups": ("group",),
    "events": ("event",),
}
DEFAULT = ("beings", "places", "things", "groups")

_ASK = {
    "beings": ("every being the story names or introduces: people, animals and creatures",
               "being"),
    "places": ("every place the story names: rooms, buildings, streets, towns, regions",
               "place"),
    "things": ("every key thing the story names: objects, tools, documents, vehicles",
               "thing"),
    "groups": ("every group the story names: factions, crews, families, organizations",
               "group"),
    "events": ("every named event in the story", "event"),
}

CATEGORY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"entries": {"type": "array", "items": {
        "type": "object",
        "properties": {"type": {"type": "string"}, "name": {"type": "string"},
                       "aliases": {"type": "array", "items": {"type": "string"}},
                       "species": {"type": ["string", "null"]},
                       "quote": {"type": "string"}},
        "required": ["type", "name", "quote"]}}},
    "required": ["entries"],
}


def category_prompt(category: str, book: Book) -> str:
    """One category pass's prompt: its stable head, the rules, the whole text."""
    what, unit = _ASK[category]
    types = ", ".join(CATEGORY_TYPES[category])
    story = "\n\n".join(book.text(n) for n in book.chapters)
    return (
        f"{CATEGORY_HEAD.format(category=category)}\n\n"
        f"Read the whole story below and list {what}. One entry per {unit}, as\n"
        '{"type", "name", "aliases", "species", "quote"}:\n'
        f"- type: one of {types}.\n"
        f"- name: the fullest name the story gives the {unit}; an unnamed {unit} goes by\n"
        "  the words the story uses for it.\n"
        "- aliases: only other forms of that same name (a first name alone, a surname,\n"
        f"  a title with the name). Never a different name and never a description: a\n"
        f"  {unit} the story calls by two names is two entries. You never decide that two\n"
        f"  names are one {unit}.\n"
        "- species: for an animal or a creature, a free word such as dog or wraith;\n"
        "  otherwise null.\n"
        "- quote: the exact sentence where the story first names it.\n"
        f"- Two different {unit}s with the same name are two entries.\n\n"
        f"STORY:\n{story}\n")


def category_passes(text_by_chapter: Mapping[int, str], model: Callable[[str, dict], Any], *,
                    categories: Sequence[str] = DEFAULT) -> Manifest:
    """Run the category passes concurrently and merge them by code (§6).
    Raises ``ValueError`` for an unknown category or a pass whose output is not
    an object with an ``entries`` list; a model error propagates."""
    categories = tuple(categories)
    unknown = [c for c in categories if c not in CATEGORY_TYPES]
    if unknown or not categories or len(set(categories)) != len(categories):
        raise ValueError(f"categories must be distinct names from {sorted(CATEGORY_TYPES)}, "
                         f"got {list(categories)}")
    book = Book(text_by_chapter)
    with ThreadPoolExecutor(max_workers=len(categories)) as pool:
        futures = [pool.submit(labelled_context("registry", f"pass:{c}").run,
                               _one_pass, c, category_prompt(c, book), model)
                   for c in categories]
        outputs = [f.result() for f in futures]
    return _merge(book, categories, outputs)


def _one_pass(category: str, prompt: str, model: Callable[[str, dict], Any]) -> list[Any]:
    out = model(prompt, copy.deepcopy(CATEGORY_SCHEMA))
    if not isinstance(out, Mapping) or not isinstance(out.get("entries"), list):
        raise ValueError(f"category pass {category!r}: expected an object with an "
                         "'entries' list")
    return list(out["entries"])


@dataclass
class _Found:
    order: tuple[int, int]
    type: str
    name: str
    aliases: list[str]
    species: str | None
    role: str | None
    quote: str


@dataclass
class _Merged:
    type: str
    names: list[str]
    species: str | None
    role: str | None
    quotes: list[str] = field(default_factory=list)
    order: tuple[int, int] = (0, 0)


def _category_type(category: str, declared: Any) -> tuple[str, str | None]:
    normalized = normalize_type(declared)
    if normalized in TYPES:
        return normalized, None
    if category == "beings":
        return "person", declared.strip() if is_role_word(declared) else None
    return CATEGORY_TYPES[category][0], None


def _content_words(text: str) -> set[str]:
    return set(tokens(text)) - ARTICLES - TITLES


def _same_name(alias: str, name: str) -> bool:
    """Whether an alias is another form of the name: it shares a word with it
    that is not an article or a title."""
    return bool(_content_words(alias) & _content_words(name))


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _found(category: str, index: tuple[int, int], raw: Any) -> _Found | None:
    if not isinstance(raw, Mapping) or _text(raw.get("name")) is None:
        logger.warning("category pass %s: entry %d has no name; skipped", category, index[1])
        return None
    name = _text(raw.get("name"))
    type_, role = _category_type(category, raw.get("type"))
    species = _text(raw.get("species")) if type_ in SPECIES_TYPES else None
    aliases: list[str] = []
    for alias in raw.get("aliases") or []:
        alias = _text(alias)
        if alias is None or join_key(alias) == join_key(name):
            continue
        if _same_name(alias, name):
            aliases.append(alias)
        else:
            logger.info("category pass %s: alias %r of %r names someone else; dropped",
                        category, alias, name)
    return _Found(order=index, type=type_, name=name, aliases=aliases, species=species,
                  role=role, quote=raw.get("quote") if isinstance(raw.get("quote"), str) else "")


def _merge(book: Book, categories: Sequence[str], outputs: Sequence[list[Any]]) -> Manifest:
    groups: dict[tuple[str, str], list[_Found]] = {}
    for p, (category, entries) in enumerate(zip(categories, outputs)):
        for e, raw in enumerate(entries):
            found = _found(category, (p, e), raw)
            if found is not None:
                groups.setdefault((found.type, join_key(found.name)), []).append(found)

    merged: list[_Merged] = []
    for members in groups.values():
        passes = [m.order[0] for m in members]
        if len(set(passes)) < len(passes):
            # A pass listed two entries under one key: they are two.
            parts = [[m] for m in members]
        else:
            parts = [members]
        for part in parts:
            names: list[str] = []
            for m in part:
                for n in [m.name, *m.aliases]:
                    if join_key(n) not in {join_key(x) for x in names}:
                        names.append(n)
            merged.append(_Merged(
                type=part[0].type, names=names,
                species=next((m.species for m in part if m.species), None),
                role=next((m.role for m in part if m.role), None),
                quotes=[m.quote for m in part], order=part[0].order))

    placed: list[tuple[tuple[Any, ...], _Merged, str]] = []
    for m in merged:
        quote, at = _anchor(book, m)
        placed.append(((0, at, m.order) if at is not None else (1, (0, 0), m.order), m, quote))
    placed.sort(key=lambda t: t[0])

    entries: list[Entry] = []
    keys: set[str] = set()
    for _, m, quote in placed:
        base = f"{m.type}:{slug(m.names[0])}"
        key, n = base, 2
        while key in keys:
            key, n = f"{base}_{n}", n + 1
        keys.add(key)
        entries.append(Entry(key=key, type=m.type, names=m.names, anchor_quote=quote,
                             role=m.role, species=m.species))
    return Manifest(entries=entries)


def _anchor(book: Book, m: _Merged) -> tuple[str, tuple[int, int] | None]:
    """The entry's anchor quote and its position: the earliest of its passes'
    quotes that occurs exactly once, else the first sentence naming it that
    occurs exactly once, else its first quote as given (validate reports it)."""
    located = []
    for quote in m.quotes:
        hits = book.locate(quote) if quote.strip() else []
        if len(hits) == 1:
            located.append((hits[0], quote))
    if located:
        at, quote = min(located)
        return quote, at
    needles = [tokens(n) for n in m.names]
    for chapter in book.chapters:
        for number, sentence in enumerate(book.sentences(chapter), start=1):
            if any(contains_run(sentence.tokens, needle) for needle in needles):
                text = book.unique_sentence_text(chapter, number)
                if text is not None:
                    return text, (chapter, number)
    return (m.quotes[0] if m.quotes else ""), None
