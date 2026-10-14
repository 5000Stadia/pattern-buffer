"""The manifest: a story's entries, anchored by quote (BUILD-LIBRARY-V1 §1).

A **manifest** is a host's or author's list of a story's entries, one identity
each, with a type, names, an anchor quote and any personas (hidden facets with
an introduction and a reveal). ``Manifest.validate(text_by_chapter)`` checks it
against the prose and raises one ``ManifestError`` listing every problem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from patternbuffer.build.text import Book, name_key

TYPES = ("person", "animal", "creature", "place", "object", "group", "event")
BEINGS = frozenset({"person", "animal", "creature"})
SPECIES_TYPES = frozenset({"animal", "creature"})
NAMESPACE = {"person": "person", "animal": "person", "creature": "person",
             "place": "place", "object": "obj", "group": "group", "event": "event"}

# The codes a ManifestError item carries. The first nine are the spec's list
# (§1); ``species_not_allowed`` (a species on a type other than animal or
# creature) and ``missing_field`` (a required field absent, empty or of the
# wrong shape) cover the two refusals §1 states without naming a code.
CODES = ("unknown_type", "role_as_type", "duplicate_key", "quote_not_found",
         "quote_not_unique", "persona_name_is_alias", "persona_reveal_before_entry",
         "persona_reveal_before_intro", "namesake_unknown_key", "species_not_allowed",
         "missing_field")

# A type outside the closed set that is a plain word or phrase is read as a
# role word (§1: "A role word ('condemned man') is refused as a type").
_WORDS = re.compile(r"[^\W\d_]+(?:[ '\-][^\W\d_]+)*")


def normalize_type(value: Any) -> Any:
    """A type as compared: stripped and lowercased when it is a string."""
    return value.strip().lower() if isinstance(value, str) else value


def is_role_word(value: Any) -> bool:
    """Whether a type outside the closed set reads as a role word: a non-empty
    string of words (letters, with single spaces, hyphens or apostrophes)."""
    return isinstance(value, str) and bool(_WORDS.fullmatch(value.strip()))


class ManifestError(ValueError):
    """Every problem ``Manifest.validate`` found, as structured items
    ``{"where", "code", "detail"}`` in ``problems`` (BUILD-LIBRARY-V1 §1 c5)."""

    def __init__(self, problems: Sequence[Mapping[str, str]]) -> None:
        self.problems = [dict(p) for p in problems]
        lines = [f"{p['where']}: {p['code']} ({p['detail']})" for p in self.problems]
        super().__init__(f"{len(self.problems)} manifest problem(s): " + "; ".join(lines))


@dataclass(frozen=True)
class Persona:
    """A hidden facet of an entry: its name, the quote where it first appears
    (gating its candidacy) and the quote where the reader learns who it is
    (splitting the chunk and dating the ``correlate``)."""

    name: str
    intro_quote: str
    reveal_quote: str


@dataclass(frozen=True)
class Entry:
    """One identity. ``type`` is from the closed set (:data:`TYPES`); ``names``
    lead with the name the id is minted from; ``anchor_quote`` is an exact
    sentence (or a phrase found once) where it appears; ``species`` is allowed
    for an animal or creature only."""

    key: str
    type: str
    names: Sequence[str]
    anchor_quote: str
    personas: Sequence[Persona] = ()
    role: str | None = None
    species: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.names, (list, tuple)):
            object.__setattr__(self, "names", tuple(self.names))
        if isinstance(self.personas, (list, tuple)):
            object.__setattr__(self, "personas", tuple(self.personas))


@dataclass(frozen=True)
class Manifest:
    """The cast, places and things of a story. ``namesakes`` lists
    ``(key_a, key_b, anchor_quote)`` for pairs a reader could confuse; each is
    kept apart by ``distinct_from`` at commit."""

    entries: Sequence[Entry]
    namesakes: Sequence[tuple[str, str, str]] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if isinstance(self.entries, (list, tuple)):
            object.__setattr__(self, "entries", tuple(self.entries))
        if isinstance(self.namesakes, (list, tuple)):
            object.__setattr__(self, "namesakes", tuple(
                tuple(n) if isinstance(n, (list, tuple)) else n for n in self.namesakes))

    # ------------------------------------------------------- validation

    def validate(self, text_by_chapter: Mapping[int, str]) -> None:
        """Check the manifest against the prose; raise one ``ManifestError``
        listing every problem, or return None."""
        problems = self.problems(text_by_chapter)
        if problems:
            raise ManifestError(problems)

    def problems(self, text_by_chapter: Mapping[int, str] | Book) -> list[dict[str, str]]:
        """Every problem, in manifest order, as ``{"where", "code", "detail"}``."""
        book = text_by_chapter if isinstance(text_by_chapter, Book) else Book(text_by_chapter)
        out: list[dict[str, str]] = []

        def add(where: str, code: str, detail: str) -> None:
            out.append({"where": where, "code": code, "detail": detail})

        def place(where: str, quote: Any) -> tuple[int, int] | None:
            """Locate a quote that must occur exactly once; report it otherwise."""
            if not isinstance(quote, str) or not quote.strip():
                add(where, "quote_not_found", "the quote is empty or not a string")
                return None
            hits = book.locate(quote)
            if not hits:
                add(where, "quote_not_found", f"{quote!r} occurs nowhere in the text")
                return None
            if len(hits) > 1:
                at = ", ".join(f"chapter {c} sentence {s}" for c, s in hits[:5])
                add(where, "quote_not_unique", f"{quote!r} occurs {len(hits)} times ({at})")
                return None
            return hits[0]

        entries = list(self.entries)
        all_name_keys: dict[tuple[str, ...], str] = {}
        for entry in entries:
            names = getattr(entry, "names", ())
            for name in names if isinstance(names, tuple) else ():
                if isinstance(name, str) and name_key(name):
                    all_name_keys.setdefault(name_key(name), str(getattr(entry, "key", "")))

        keys_seen: set[str] = set()
        for i, entry in enumerate(entries):
            where = f"entries[{i}]"
            if not isinstance(entry, Entry):
                add(where, "missing_field", "not an Entry")
                continue
            if not isinstance(entry.key, str) or not entry.key.strip():
                add(f"{where}.key", "missing_field", "an entry needs a non-empty key")
            elif entry.key in keys_seen:
                add(f"{where}.key", "duplicate_key", f"key {entry.key!r} is used twice")
            else:
                keys_seen.add(entry.key)
            etype = normalize_type(entry.type)
            if etype not in TYPES:
                if is_role_word(entry.type):
                    add(f"{where}.type", "role_as_type",
                        f"{entry.type!r} is not a type; a role word goes in role, with "
                        f"type person (types: {', '.join(TYPES)})")
                else:
                    add(f"{where}.type", "unknown_type",
                        f"{entry.type!r} is not one of {', '.join(TYPES)}")
            if entry.species is not None:
                if not isinstance(entry.species, str) or not entry.species.strip():
                    add(f"{where}.species", "missing_field", "species must be a non-empty word")
                elif etype not in SPECIES_TYPES:
                    add(f"{where}.species", "species_not_allowed",
                        f"species {entry.species!r} is allowed only for animal and creature")
            names = entry.names if isinstance(entry.names, tuple) else ()
            if not names or not all(isinstance(n, str) and n.strip() for n in names):
                add(f"{where}.names", "missing_field",
                    "an entry needs at least one name, and every name non-empty")
            if entry.role is not None and (not isinstance(entry.role, str)
                                           or not entry.role.strip()):
                add(f"{where}.role", "missing_field", "role must be a non-empty string")
            anchor = place(f"{where}.anchor_quote", entry.anchor_quote)
            gate = _gate(book, anchor, [n for n in names if isinstance(n, str)])

            personas = entry.personas if isinstance(entry.personas, tuple) else ()
            for j, persona in enumerate(personas):
                pwhere = f"{where}.personas[{j}]"
                if not isinstance(persona, Persona):
                    add(pwhere, "missing_field", "not a Persona")
                    continue
                if not isinstance(persona.name, str) or not persona.name.strip():
                    add(f"{pwhere}.name", "missing_field", "a persona needs a non-empty name")
                else:
                    owner = all_name_keys.get(name_key(persona.name))
                    if owner is not None:
                        add(f"{pwhere}.name", "persona_name_is_alias",
                            f"persona name {persona.name!r} is also a name of entry {owner!r}")
                intro = place(f"{pwhere}.intro_quote", persona.intro_quote)
                reveal = place(f"{pwhere}.reveal_quote", persona.reveal_quote)
                if reveal is not None and intro is not None and reveal <= intro:
                    add(f"{pwhere}.reveal_quote", "persona_reveal_before_intro",
                        f"the reveal ({_at(reveal)}) is not after the intro ({_at(intro)})")
                if reveal is not None and gate is not None and reveal < gate:
                    add(f"{pwhere}.reveal_quote", "persona_reveal_before_entry",
                        f"the reveal ({_at(reveal)}) is before the entry's first "
                        f"appearance ({_at(gate)})")

        keys = {e.key for e in entries if isinstance(e, Entry) and isinstance(e.key, str)}
        for k, namesake in enumerate(self.namesakes):
            where = f"namesakes[{k}]"
            if not (isinstance(namesake, tuple) and len(namesake) == 3):
                add(where, "missing_field", "a namesake is (key_a, key_b, anchor_quote)")
                continue
            key_a, key_b, quote = namesake
            for key in (key_a, key_b):
                if key not in keys:
                    add(where, "namesake_unknown_key", f"no entry has key {key!r}")
            place(f"{where}.anchor_quote", quote)
        return out

    # ---------------------------------------------------- serialization

    def to_dict(self) -> dict[str, Any]:
        """The manifest as plain JSON data."""
        return {
            "entries": [{
                "key": e.key, "type": e.type,
                "names": list(e.names) if isinstance(e.names, tuple) else e.names,
                "anchor_quote": e.anchor_quote, "role": e.role, "species": e.species,
                "personas": [{"name": p.name, "intro_quote": p.intro_quote,
                              "reveal_quote": p.reveal_quote} for p in e.personas],
            } for e in self.entries],
            "namesakes": [list(n) for n in self.namesakes],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Manifest":
        """A manifest from :meth:`to_dict`'s shape (or an author's JSON). Absent
        fields become empty, so ``validate`` reports them rather than this
        raising."""
        entries = []
        for raw in data.get("entries") or []:
            raw = raw if isinstance(raw, Mapping) else {}
            personas = [Persona(name=p.get("name", ""), intro_quote=p.get("intro_quote", ""),
                                reveal_quote=p.get("reveal_quote", ""))
                        for p in (raw.get("personas") or []) if isinstance(p, Mapping)]
            names = raw.get("names")
            entries.append(Entry(key=raw.get("key", ""), type=raw.get("type", ""),
                                 names=list(names) if isinstance(names, (list, tuple)) else names,
                                 anchor_quote=raw.get("anchor_quote", ""),
                                 personas=personas, role=raw.get("role"),
                                 species=raw.get("species")))
        namesakes = [tuple(n) for n in (data.get("namesakes") or [])]
        return cls(entries=entries, namesakes=namesakes)


def _at(where: tuple[int, int]) -> str:
    return f"chapter {where[0]} sentence {where[1]}"


def _gate(book: Book, anchor: tuple[int, int] | None,
          names: Sequence[str]) -> tuple[int, int] | None:
    """An effective gate (§3): the earlier of the anchor's sentence and the first
    sentence naming any of ``names`` as a whole-token run."""
    found = [book.first_occurrence(n) for n in names]
    candidates = [g for g in [anchor, *found] if g is not None]
    return min(candidates) if candidates else None
