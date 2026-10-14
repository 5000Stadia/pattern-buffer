"""The registry: ids minted by code, gated by sentence (BUILD-LIBRARY-V1 §2).

``Registry.from_manifest(manifest, text_by_chapter)`` validates the manifest,
mints one id per entry and per persona from one allocator, and computes each
one's **effective gate**: the earlier of its anchor (an entry's
``anchor_quote``, a persona's ``intro_quote``) and the first sentence naming
it as a whole-token run. ``resolve`` and the chunk check both read that gate,
so they never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from patternbuffer.build.manifest import (
    BEING_NAMESPACES,
    BEINGS,
    NAMESPACE,
    TYPES,
    Manifest,
    normalize_type,
)
from patternbuffer.build.text import ARTICLES, Book, contains_run, name_key, slug

HINTS = ("being",) + TYPES


@dataclass(frozen=True)
class Resolved:
    """``resolve``'s answer for exactly one compatible candidate."""

    id: str


@dataclass(frozen=True)
class Ambiguous:
    """``resolve``'s answer for two or more compatible candidates, in registry
    order."""

    candidates: tuple[str, ...]


@dataclass(frozen=True)
class Unknown:
    """``resolve``'s answer when no candidate matches."""


@dataclass(frozen=True)
class Identity:
    """One minted identity: a manifest entry or one of its personas.

    For a persona, ``key`` is its entry's key, ``names`` holds the persona name
    only, ``anchor`` is its intro sentence, and ``entry_id``, ``reveal`` and
    ``reveal_quote`` are set."""

    id: str
    key: str
    type: str
    species: str | None
    names: tuple[str, ...]
    role: str | None
    anchor: tuple[int, int]
    gate: tuple[int, int]
    entry_id: str | None = None
    reveal: tuple[int, int] | None = None
    reveal_quote: str | None = None

    @property
    def is_persona(self) -> bool:
        return self.entry_id is not None


class Allocator:
    """The one id allocator (§2, r1.2): every minted id, whether entry,
    persona, mention or escape, is drawn here, so no two are ever equal."""

    def __init__(self, taken: tuple[str, ...] = ()) -> None:
        self._taken: set[str] = set(taken)
        self.order: list[str] = list(taken)

    def _take(self, minted: str) -> str:
        self._taken.add(minted)
        self.order.append(minted)
        return minted

    def mint(self, base: str) -> str:
        """``base`` if free, else ``base_2``, ``base_3``, … (the first free)."""
        if base not in self._taken:
            return self._take(base)
        n = 2
        while f"{base}_{n}" in self._taken:
            n += 1
        return self._take(f"{base}_{n}")

    def mint_numbered(self, base: str) -> str:
        """``base_1``, ``base_2``, … (the first free): a mention id."""
        n = 1
        while f"{base}_{n}" in self._taken:
            n += 1
        return self._take(f"{base}_{n}")

    def copy(self) -> "Allocator":
        return Allocator(tuple(self.order))


def compatible(hint: str | None, type_: str) -> bool:
    """Type-hint compatibility (§2): ``being`` matches any being type; every
    other hint matches its own type only (the Rex rule: ``animal`` never
    reaches a ``person``)."""
    if hint is None:
        return True
    if hint == "being":
        return type_ in BEINGS
    return type_ == hint


def shape_rows(id: str, type: str, species: str | None = None) -> list[dict[str, Any]]:
    """The shape writer (§5 step 0): an id's shape rows, timeless and canon.

    - a being (``person``, ``animal``, ``creature``): ``kind = person``, then
      ``being_type = <type>``, then ``species`` when given;
    - ``being`` (a mention whose candidates are beings of several types):
      ``kind = person`` only, so R49's role move still applies;
    - anything else: ``kind = <type>``.

    No other path in the library writes ``kind`` on a minted id."""

    def row(attribute: str, value: str) -> dict[str, Any]:
        return {"entity": id, "attribute": attribute, "value": value,
                "value_type": "literal", "timeless": True, "frame": "canon"}

    if type == "being":
        return [row("kind", "person")]
    if type in BEINGS:
        rows = [row("kind", "person"), row("being_type", type)]
        if species:
            rows.append(row("species", species))
        return rows
    if type not in TYPES:
        raise ValueError(f"shape_rows: {type!r} is not a type")
    return [row("kind", type)]


class Registry:
    """The registry built from a validated manifest. Construct it with
    :meth:`from_manifest`."""

    def __init__(self, book: Book, manifest: Manifest, identities: tuple[Identity, ...],
                 namesakes: tuple[tuple[str, str, str], ...], allocator: Allocator) -> None:
        self.book = book
        self.manifest = manifest
        self._identities = identities
        self._by_id = {i.id: i for i in identities}
        self.namesakes = namesakes
        self._allocator = allocator

    @classmethod
    def from_manifest(cls, manifest: Manifest, text_by_chapter: Mapping[int, str]) -> "Registry":
        """Validate ``manifest`` against the text (raising ``ManifestError``),
        then mint the ids: every entry first, in manifest order, then each
        entry's personas, in manifest order. An entry's id is its type's
        namespace and its first name, slugged (``person:rex``); a later one with
        the same slug gets ``_2``, ``_3``, …; a persona's id is its entry's
        namespace and the persona name, slugged."""
        book = Book(text_by_chapter)
        manifest.validate(book)
        allocator = Allocator()
        entry_ids: list[str] = []
        for entry in manifest.entries:
            entry_type = normalize_type(entry.type)
            entry_ids.append(allocator.mint(f"{NAMESPACE[entry_type]}:{slug(entry.names[0])}"))
        persona_ids: list[list[str]] = []
        for entry in manifest.entries:
            entry_type = normalize_type(entry.type)
            persona_ids.append([allocator.mint(f"{NAMESPACE[entry_type]}:{slug(p.name)}")
                                for p in entry.personas])

        identities: list[Identity] = []
        for entry, eid in zip(manifest.entries, entry_ids):
            anchor = book.locate(entry.anchor_quote)[0]
            identities.append(Identity(
                id=eid, key=entry.key, type=normalize_type(entry.type),
                species=entry.species.strip() if entry.species else None,
                names=tuple(entry.names), role=entry.role, anchor=anchor,
                gate=_effective_gate(book, anchor, entry.names)))
        for entry, eid, pids in zip(manifest.entries, entry_ids, persona_ids):
            for persona, pid in zip(entry.personas, pids):
                intro = book.locate(persona.intro_quote)[0]
                identities.append(Identity(
                    id=pid, key=entry.key, type=normalize_type(entry.type),
                    species=entry.species.strip() if entry.species else None,
                    names=(persona.name,), role=None, anchor=intro,
                    gate=_effective_gate(book, intro, (persona.name,)),
                    entry_id=eid, reveal=book.locate(persona.reveal_quote)[0],
                    reveal_quote=persona.reveal_quote))
        by_key = dict(zip((e.key for e in manifest.entries), entry_ids))
        namesakes = tuple((by_key[a], by_key[b], quote) for a, b, quote in manifest.namesakes)
        return cls(book, manifest, tuple(identities), namesakes, allocator)

    # ------------------------------------------------------------ reads

    @property
    def identities(self) -> tuple[Identity, ...]:
        """Every entry, then every persona, in allocation order."""
        return self._identities

    def identity(self, id: str) -> Identity:
        return self._by_id[id]

    def allocator(self) -> Allocator:
        """A copy of the one allocator, with every entry and persona id taken:
        what commit mints mentions and escapes from (§2, r1.2). The registry's
        own allocator is never advanced, so one registry commits the same ids
        every time."""
        return self._allocator.copy()

    def knows(self, id: str) -> bool:
        return id in self._by_id

    def entries(self) -> list[dict[str, Any]]:
        """The entries in manifest order, for a host's cast author (§2 c3):
        ``{id, key, type, species, names, role, anchor, gate, personas}`` with
        each persona as ``{name, id, reveal, gate}``; positions are
        ``(chapter, sentence)``."""
        out: list[dict[str, Any]] = []
        for ident in self._identities:
            if ident.is_persona:
                continue
            out.append({
                "id": ident.id, "key": ident.key, "type": ident.type,
                "species": ident.species, "names": list(ident.names), "role": ident.role,
                "anchor": ident.anchor, "gate": ident.gate,
                "personas": [{"name": p.names[0], "id": p.id, "reveal": p.reveal,
                              "gate": p.gate}
                             for p in self._identities if p.entry_id == ident.id],
            })
        return out

    def resolve(self, surface: str, chapter: int, sentence: int,
                hint: str | None = None) -> Resolved | Ambiguous | Unknown:
        """What ``surface`` names at ``(chapter, sentence)`` (§2).

        The candidates are the entries and personas whose effective gate is at
        or before ``(chapter, sentence)`` and whose type ``hint`` allows. A
        candidate matches when one of its names has the surface's name key
        (lowercase, quote folding, leading titles dropped), or holds the
        surface's tokens as a whole-token run (a fragment: "Breck" in "Tomas
        Breck"); a surface of articles alone matches exactly or not at all. A
        persona's name always resolves to the persona id; the link to its entry
        is the ``aka`` written at its reveal, never this read."""
        if hint is not None and hint not in HINTS:
            raise ValueError(f"unknown type hint {hint!r} (hints: {', '.join(HINTS)})")
        key = name_key(surface) if isinstance(surface, str) else ()
        if not key:
            return Unknown()
        fragment_ok = not all(tok in ARTICLES for tok in key)
        at = (chapter, sentence)
        matches: list[str] = []
        for ident in self._identities:
            if ident.gate > at or not compatible(hint, ident.type):
                continue
            for name in ident.names:
                nk = name_key(name)
                if nk == key or (fragment_ok and contains_run(nk, key)):
                    matches.append(ident.id)
                    break
        if not matches:
            return Unknown()
        if len(matches) == 1:
            return Resolved(matches[0])
        return Ambiguous(tuple(matches))

    def source_problem(self, source: str, chapter: int,
                       sentence: int) -> tuple[str, str] | None:
        """Whether a fact's source (``doc=`` or ``src=``) may stand at
        ``(chapter, sentence)`` (r1.7). None for an entry or persona id gated
        by then, and for document provenance: any source outside a being
        namespace, such as ``doc:letter_1``. Otherwise ``(reason, detail)``:
        ``gate_refused`` for a registry id gated later, ``unknown_id`` for a
        ``person:`` source naming no entry or persona (the engine reads a
        ``person:`` source as a speaker's identity, so it is never taken for a
        document). A build handle is the caller's to check."""
        if self.knows(source):
            gate = self.identity(source).gate
            if gate > (chapter, sentence):
                return ("gate_refused", f"source {source} is gated at chapter {gate[0]} "
                                        f"sentence {gate[1]}")
            return None
        namespace, colon, _ = source.partition(":")
        if colon and namespace in BEING_NAMESPACES:
            return "unknown_id", f"source {source!r} names no entity of this registry"
        return None

    def candidates_at(self, chapter: int, sentence: int) -> list[Identity]:
        """Every entry and persona gated at or before ``(chapter, sentence)``,
        in registry order."""
        at = (chapter, sentence)
        return [i for i in self._identities if i.gate <= at]

    def reveals(self) -> list[tuple[int, int]]:
        """Every persona's reveal sentence, sorted."""
        return sorted({i.reveal for i in self._identities if i.reveal is not None})


def _effective_gate(book: Book, anchor: tuple[int, int],
                    names: tuple[str, ...] | list[str]) -> tuple[int, int]:
    """The earlier of ``anchor`` and the first sentence naming any of ``names``
    as a whole-token run (§3, r1.4)."""
    found = [book.first_occurrence(n) for n in names]
    return min([anchor] + [g for g in found if g is not None])
