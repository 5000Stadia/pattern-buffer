"""Name keys and token matching, shared by ``refer``-style reads and the build
library (PLAY-BIND-V1 §2-§3; BUILD-LIBRARY-V1 §2).

Model-free and literal. They were first written for the book builder's text
layer, which now re-exports them from here, so the engine core imports nothing
from the builder.
"""

from __future__ import annotations

import re
from typing import Sequence

_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})
_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)*")
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


def name_key(name: str) -> tuple[str, ...]:
    """A name's matching key for ``resolve`` (BUILD-LIBRARY-V1 §2): its whole
    tokens (lowercase, quote folding), with leading titles from :data:`TITLES`
    dropped while more than one token remains."""
    toks = tokens(name)
    while len(toks) > 1 and toks[0] in TITLES:
        toks = toks[1:]
    return tuple(toks)


# PLAY-BIND-V1 §3: pairs whose plural has its own sense, never matched.
PLURAL_EXCEPTIONS = frozenset({
    ("new", "news"), ("mean", "means"), ("arm", "arms"), ("good", "goods"),
    ("glass", "glasses"), ("paper", "papers"), ("work", "works"),
    ("custom", "customs"), ("quarter", "quarters"), ("manner", "manners"),
    ("spirit", "spirits"),
})
_VOWELS = frozenset("aeiou")


def is_plural_of(plural: str, single: str) -> bool:
    """Whether ``plural`` is ``single``'s plural by one of PLAY-BIND-V1 §3's
    pair rules, with ``single`` at least 3 letters and the pair not in
    :data:`PLURAL_EXCEPTIONS`. Nothing is stemmed: both words are given."""
    if len(single) < 3 or (single, plural) in PLURAL_EXCEPTIONS:
        return False
    if plural == single + "s":
        return True
    if plural == single + "es" and single.endswith(("ch", "sh", "s", "x", "z")):
        return True
    if (single.endswith("y") and single[-2] not in _VOWELS
            and plural == single[:-1] + "ies"):
        return True
    return (single.endswith("o") and single[-2] not in _VOWELS
            and plural == single + "es")


def tokens_match(a: str, b: str) -> bool:
    """Two tokens are equal or one is the other's plural (PLAY-BIND-V1 §3)."""
    return a == b or is_plural_of(a, b) or is_plural_of(b, a)


def keys_match(a: Sequence[str], b: Sequence[str]) -> bool:
    """Two name keys of equal length whose tokens match pairwise."""
    return len(a) == len(b) and all(tokens_match(x, y) for x, y in zip(a, b))


def contains_matching_run(haystack: Sequence[str], needle: Sequence[str]) -> bool:
    """``contains_run`` under :func:`tokens_match`: ``needle`` occurs as a
    contiguous run in ``haystack``, token by token up to number."""
    n = len(needle)
    if n == 0 or n > len(haystack):
        return False
    return any(keys_match(haystack[i:i + n], needle) for i in range(len(haystack) - n + 1))
