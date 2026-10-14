"""The plan: chunks with sentence-scoped candidates (BUILD-LIBRARY-V1 §3).

Chapters are cut into chunks at paragraph breaks, under ``max_words`` (a
paragraph is never split, so one longer than ``max_words`` is a chunk alone).
A chunk that holds a persona's reveal sentence is split before it: the reveal
sentence opens the next chunk. Each chunk receives every entry and persona
whose effective gate is at or before its last sentence, each annotated with its
gate as a sentence number in the chunk's own numbering (``1`` for anything
gated before the chunk begins).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from patternbuffer.build.registry import Registry
from patternbuffer.build.text import Book

DEFAULT_MAX_WORDS = 1500


@dataclass(frozen=True)
class Candidate:
    """An entry or persona a chunk may name, and the chunk sentence it may be
    cited from (its effective gate in the chunk's numbering)."""

    id: str
    type: str
    names: tuple[str, ...]
    species: str | None
    gate: int

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "names": list(self.names),
                "species": self.species, "gate": self.gate}


@dataclass(frozen=True)
class Chunk:
    """One unit of extraction: chapter sentences ``first_sentence`` through
    ``last_sentence`` (numbered within the chapter), their exact ``text``, and
    the chunk's candidates. The chunk numbers its own sentences from 1."""

    index: int
    chapter: int
    first_sentence: int
    last_sentence: int
    text: str
    candidates: tuple[Candidate, ...]

    @property
    def sentence_count(self) -> int:
        return self.last_sentence - self.first_sentence + 1

    def local(self, sentence: int) -> int:
        """A chapter sentence number in the chunk's own numbering."""
        return sentence - self.first_sentence + 1

    def absolute(self, local: int) -> int:
        """A chunk sentence number as the chapter numbers it."""
        return self.first_sentence + local - 1

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "chapter": self.chapter,
                "first_sentence": self.first_sentence, "last_sentence": self.last_sentence,
                "text": self.text, "candidates": [c.to_dict() for c in self.candidates]}


def plan(text_by_chapter: Mapping[int, str], registry: Registry, *,
         max_words: int = DEFAULT_MAX_WORDS) -> list[Chunk]:
    """Cut the story into chunks (§3). The same text and manifest give the same
    plan, byte for byte. ``text_by_chapter`` must be the text the registry was
    built from (checked by digest)."""
    if isinstance(max_words, bool) or not isinstance(max_words, int) or max_words < 1:
        raise ValueError(f"max_words must be a positive integer, got {max_words!r}")
    book = Book(text_by_chapter)
    if book.digest != registry.book.digest:
        raise ValueError("plan: text_by_chapter is not the text the registry was built from")
    reveals = registry.reveals()
    chunks: list[Chunk] = []
    for chapter in book.chapters:
        groups: list[tuple[int, int]] = []
        first: int | None = None
        last = 0
        words = 0
        for para in book.paragraphs(chapter):
            if first is not None and words + para.words > max_words:
                groups.append((first, last))
                first, words = None, 0
            if first is None:
                first = para.first
            last = para.last
            words += para.words
        if first is not None:
            groups.append((first, last))
        for g_first, g_last in groups:
            cuts = [s for c, s in reveals if c == chapter and g_first < s <= g_last]
            starts = [g_first] + cuts
            ends = [s - 1 for s in cuts] + [g_last]
            for a, b in zip(starts, ends):
                chunks.append(_chunk(len(chunks), chapter, a, b, book, registry))
    return chunks


def _chunk(index: int, chapter: int, first: int, last: int, book: Book,
           registry: Registry) -> Chunk:
    candidates = []
    for ident in registry.candidates_at(chapter, last):
        gate_chapter, gate_sentence = ident.gate
        local = gate_sentence - first + 1 if gate_chapter == chapter else 1
        candidates.append(Candidate(id=ident.id, type=ident.type, names=ident.names,
                                    species=ident.species, gate=max(1, local)))
    return Chunk(index=index, chapter=chapter, first_sentence=first, last_sentence=last,
                 text=book.span_text(chapter, first, last), candidates=tuple(candidates))
