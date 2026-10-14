"""The build library's deterministic text layer (BUILD-LIBRARY-V1 §1-§3).

Everything here is literal and model-free: quote folding, the whole-token
tokenizer, sentence and paragraph splitting, quote location and name keys.

- **Sentences.** A chapter's text splits after ``.``, ``!``, ``?`` or ``…``,
  optionally followed by closing quotes or brackets, then whitespace. A
  paragraph break (a blank line) also ends a sentence, so a chunk cut at a
  paragraph break always falls between two sentences and a heading without a
  full stop is a sentence of its own. Sentences are numbered from 1 within each
  chapter.
- **Tokens.** :func:`tokens` is GRADE-LEAKS-V1's chunk-classification tokenizer
  (``evals/harness/grade_leaks.tokens``), copied here because the engine package
  never imports the eval harness; a test pins the two as equal.
- **Quotes.** A quote is matched after quote folding and whitespace collapse,
  case-sensitively, and its sentence is the one holding its first character.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Mapping, Sequence

_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})
_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)*")
# A sentence ends at terminal punctuation, optionally followed by closing
# quotes or brackets; the split needs whitespace right after (checked by hand).
_SENTENCE_END = re.compile(r"[.!?…][\"'”’»)\]}]*")

ARTICLES = frozenset({"the", "a", "an"})
# The fixed list of leading titles a name key drops (BUILD-LIBRARY-V1 §2:
# "leading titles from a fixed list"; BookNLP's honorific rule). Matched on
# whole tokens, so "Mr." and "Mr" are one title.
TITLES = frozenset(
    "mr mrs ms miss mx dr doctor prof professor sir dame lady lord madam madame mme mlle "
    "monsieur master mistress rev reverend father fr mother brother sister capt captain "
    "lt lieutenant sgt sergeant cpl corporal col colonel maj major gen general adm admiral "
    "cmdr commander officer inspector detective det constable judge king queen prince "
    "princess duke duchess count countess baron baroness earl emperor empress aunt uncle"
    .split())


def fold_quotes(text: str) -> str:
    """Curly single quotes to ``'`` and curly double quotes to ``"``; nothing
    else changes (``evals/harness/book_gold.fold_quotes``)."""
    return text.translate(_QUOTES)


def tokens(text: str) -> list[str]:
    """GRADE-LEAKS-V1's whole-token tokenizer: quote folding and lowercase,
    no article stripping, so ``o'brien`` is one token and ``copper-hand`` two."""
    return _TOKEN.findall(fold_quotes(text).lower())


def contains_run(haystack: Sequence[str], needle: Sequence[str]) -> bool:
    """Whether ``needle`` occurs as a contiguous run in ``haystack``."""
    n = len(needle)
    if n == 0 or n > len(haystack):
        return False
    needle = list(needle)
    return any(list(haystack[i:i + n]) == needle for i in range(len(haystack) - n + 1))


def collapse(text: str) -> str:
    """Quote folding and whitespace collapse, outer whitespace dropped: the
    form quotes are matched in."""
    return " ".join(fold_quotes(text).split())


def join_key(name: str) -> str:
    """A name's normalized form for joining (BUILD-LIBRARY-V1 §5 step 4, §6):
    the book matcher's key (``evals/harness/book_gold.book_normalize``) —
    quote folding, lowercase, whitespace collapse and one leading article
    dropped, so "a barmaid" and "the barmaid" join. Titles are kept, so "Mr.
    Vell" and "Mrs. Vell" never join."""
    key = " ".join(fold_quotes(name).lower().split())
    for article in ("the ", "a ", "an "):
        if key.startswith(article):
            return key[len(article):].strip()
    return key


def name_key(name: str) -> tuple[str, ...]:
    """A name's matching key for ``resolve`` (BUILD-LIBRARY-V1 §2): its whole
    tokens (lowercase, quote folding), with leading titles from :data:`TITLES`
    dropped while more than one token remains."""
    toks = tokens(name)
    while len(toks) > 1 and toks[0] in TITLES:
        toks = toks[1:]
    return tuple(toks)


def is_description(name: str) -> bool:
    """Whether an escape's name is a description rather than a proper name
    (BUILD-LIBRARY-V1 §5 k5): it starts with an article, or it is made only of
    lowercase words."""
    words = name.split()
    if not words:
        return True
    if fold_quotes(words[0]).lower().strip("\"'") in ARTICLES:
        return True
    return not any(ch.isupper() for ch in name)


def slug(name: str) -> str:
    """The id slug of a name: ASCII-folded, lowercase, every run of other
    characters one ``_``, ``unnamed`` when nothing is left."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    out = re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")
    return out or "unnamed"


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` of each paragraph: a run of non-blank lines, from its
    first non-whitespace character to just after its last one."""
    spans: list[tuple[int, int]] = []
    start: int | None = None
    end = 0
    pos = 0
    for line in text.splitlines(keepends=True):
        if line.strip():
            if start is None:
                start = pos + (len(line) - len(line.lstrip()))
            end = pos + len(line.rstrip())
        elif start is not None:
            spans.append((start, end))
            start = None
        pos += len(line)
    if start is not None:
        spans.append((start, end))
    return spans


def _sentence_spans(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """The sentences of one paragraph ``text[start:end]``."""
    out: list[tuple[int, int]] = []
    pos = start
    for match in _SENTENCE_END.finditer(text, start, end):
        stop = match.end()
        if stop >= end or not text[stop].isspace():
            continue
        out.append((pos, stop))
        pos = stop
        while pos < end and text[pos].isspace():
            pos += 1
    if pos < end:
        out.append((pos, end))
    return out


@dataclass(frozen=True)
class Sentence:
    """One sentence of a chapter: its character span and its tokens."""

    start: int
    end: int
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class Paragraph:
    """One paragraph of a chapter: its first and last sentence numbers and its
    word count."""

    first: int
    last: int
    words: int


class Book:
    """A story's chapters, split into numbered sentences and paragraphs.

    ``text_by_chapter`` maps a chapter number to its text. The digest is the
    sha256 of the chapters in order, so a plan can check it was given the text
    its registry was built from."""

    def __init__(self, text_by_chapter: Mapping[int, str]) -> None:
        if not isinstance(text_by_chapter, Mapping):
            raise TypeError("text_by_chapter must map chapter numbers to text")
        chapters: dict[int, str] = {}
        for number, text in text_by_chapter.items():
            if isinstance(number, bool) or not isinstance(number, int):
                raise TypeError(f"chapter number {number!r} is not an int")
            if not isinstance(text, str):
                raise TypeError(f"chapter {number} text is not a string")
            chapters[number] = text
        self._text = {n: chapters[n] for n in sorted(chapters)}
        self.chapters: tuple[int, ...] = tuple(self._text)
        self._sentences: dict[int, tuple[Sentence, ...]] = {}
        self._paragraphs: dict[int, tuple[Paragraph, ...]] = {}
        for number, text in self._text.items():
            sentences: list[Sentence] = []
            paragraphs: list[Paragraph] = []
            for p_start, p_end in _paragraph_spans(text):
                spans = _sentence_spans(text, p_start, p_end)
                first = len(sentences) + 1
                sentences.extend(Sentence(a, b, tuple(tokens(text[a:b]))) for a, b in spans)
                paragraphs.append(Paragraph(first, len(sentences),
                                            len(text[p_start:p_end].split())))
            self._sentences[number] = tuple(sentences)
            self._paragraphs[number] = tuple(paragraphs)
        self._norm: dict[int, tuple[str, list[int]]] = {}
        blob = json.dumps([[n, t] for n, t in self._text.items()], ensure_ascii=False)
        self.digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------ access

    def text(self, chapter: int) -> str:
        return self._text[chapter]

    def sentences(self, chapter: int) -> tuple[Sentence, ...]:
        return self._sentences[chapter]

    def paragraphs(self, chapter: int) -> tuple[Paragraph, ...]:
        return self._paragraphs[chapter]

    def has_sentence(self, chapter: int, sentence: int) -> bool:
        return chapter in self._sentences and 1 <= sentence <= len(self._sentences[chapter])

    def span_text(self, chapter: int, first: int, last: int) -> str:
        """The chapter's exact text from sentence ``first`` through ``last``."""
        sentences = self._sentences[chapter]
        return self._text[chapter][sentences[first - 1].start:sentences[last - 1].end]

    def numbered(self, chapter: int, first: int, last: int) -> str:
        """``span_text`` with each sentence opened by its number within the span,
        ``[s1]`` for sentence ``first``: the passage a model cites from."""
        text = self._text[chapter]
        sentences = self._sentences[chapter][first - 1:last]
        out: list[str] = []
        prev = sentences[0].start
        for n, sentence in enumerate(sentences, start=1):
            out.append(text[prev:sentence.start])
            out.append(f"[s{n}] {text[sentence.start:sentence.end]}")
            prev = sentence.end
        return "".join(out)

    # ------------------------------------------------------------ lookups

    def _normalized(self, chapter: int) -> tuple[str, list[int]]:
        """The chapter folded and whitespace-collapsed, with each character's
        offset in the original text."""
        if chapter not in self._norm:
            folded = fold_quotes(self._text[chapter])
            chars: list[str] = []
            index: list[int] = []
            i, n = 0, len(folded)
            while i < n:
                if folded[i].isspace():
                    chars.append(" ")
                    index.append(i)
                    while i < n and folded[i].isspace():
                        i += 1
                else:
                    chars.append(folded[i])
                    index.append(i)
                    i += 1
            self._norm[chapter] = ("".join(chars), index)
        return self._norm[chapter]

    def sentence_at(self, chapter: int, offset: int) -> int:
        """The number of the sentence holding character ``offset``."""
        starts = [s.start for s in self._sentences[chapter]]
        return bisect.bisect_right(starts, offset)

    def locate(self, quote: str) -> list[tuple[int, int]]:
        """Every occurrence of ``quote`` (overlapping ones included) as
        ``(chapter, sentence)``, after quote folding and whitespace collapse."""
        needle = collapse(quote)
        if not needle:
            return []
        hits: list[tuple[int, int]] = []
        for chapter in self.chapters:
            norm, index = self._normalized(chapter)
            at = norm.find(needle)
            while at != -1:
                hits.append((chapter, self.sentence_at(chapter, index[at])))
                at = norm.find(needle, at + 1)
        return hits

    def first_occurrence(self, name: str) -> tuple[int, int] | None:
        """The first ``(chapter, sentence)`` whose tokens hold the name's tokens
        as a whole-token run (GRADE-LEAKS-V1's tokenizer), or None."""
        needle = tokens(name)
        if not needle:
            return None
        for chapter in self.chapters:
            for number, sentence in enumerate(self._sentences[chapter], start=1):
                if contains_run(sentence.tokens, needle):
                    return chapter, number
        return None

    def unique_sentence_text(self, chapter: int, sentence: int) -> str | None:
        """The sentence's own text when, as a quote, it occurs exactly once in
        the book (else None)."""
        s = self._sentences[chapter][sentence - 1]
        text = self._text[chapter][s.start:s.end]
        return text if len(self.locate(text)) == 1 else None
