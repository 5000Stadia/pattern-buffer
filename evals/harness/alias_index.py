"""Deterministic alias index over a pass-0 registry and its source text (R24, ALIAS-INDEX-V1 Part A).

Reads a world registry and the story segments (never bible text) and reports,
with no model call and no engine change:

1. the alias index: normalized names and aliases mapped to ids, and per
   segment which ids the text hits and by what string (``exact``,
   ``title_surname``, ``prefix``);
2. ambiguous strings: one normalized string carried by two or more ids
   ("the vault" on three cards);
3. the stoplist: kinship, address, generic-role and pronoun strings that are
   never treated as identifying (kept in this module, ``stoplist_class``);
4. escape candidates: capitalized strings in the text that match no name or
   alias, ranked by frequency, before pass-1 runs;
5. distinctness evidence: pairs of ids that cannot be one entity, each with
   the evidence string and a strength (``strong`` or ``weak``);
6. merge candidates: a card that lists, as an alias, the full proper name of
   another card of the same kind, unless strong evidence says the two differ.

Ids are repaired as ``registry._norm_id`` repairs them (``person:/x`` becomes
``person:x``); the mapping is reported as ``id_repairs``. ``build_report`` is
Part A and writes nothing. ``apply_distinctness`` is Part B (ALIAS-INDEX-V1): the
host's ``distinct_from`` for strong non-person pairs, called by
``Pipeline.commit`` through the porcelain; it never merges.

CLI (the story is segmented exactly as ``run_pass0_baseline.story_segments``):

    PYTHONPATH=src python evals/harness/alias_index.py REGISTRY.json \\
        --story evals/last_honest_meter/story.md --out DIR
"""

from __future__ import annotations

import argparse
import bisect
import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from grade_registry import normalize
    from registry import _norm_id
except ImportError:  # imported as evals.harness.alias_index
    from evals.harness.grade_registry import normalize
    from evals.harness.registry import _norm_id

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ stoplist

#: Strings that never identify an individual. A registry string whose
#: normalized form (after one leading possessive) is in a class is kept out of
#: the index, the ambiguous list, hits, coordination and co-presence; it is
#: reported separately under ``stoplisted``.
STOPLIST: dict[str, frozenset[str]] = {
    "kinship": frozenset(
        "mother father mom mum mama dad papa mommy daddy brother sister son "
        "daughter uncle aunt cousin cousins wife husband grandmother grandfather "
        "grandma grandpa parent parents sibling nephew niece family".split()),
    "address": frozenset(
        "sir madam ma'am miss mister lord lady boss friend stranger mate pal "
        "master mistress".split()),
    "role": frozenset(
        ["boy", "girl", "man", "woman", "kid", "child", "children", "clerk", "clerks",
         "guard", "guards", "soldier", "visitor", "client", "customer", "worker",
         "official", "officer", "old man", "old woman", "young man", "young woman",
         "little girl", "little boy"]),
    "pronoun": frozenset(
        "he she him her they them it i we you one".split()),
}
_POSSESSIVES = ("my ", "your ", "his ", "her ", "our ", "their ")

#: Titles for the ``title_surname`` match ("Warden Cray" hits the card named "...Cray").
TITLES = ("mr", "mrs", "ms", "miss", "dr", "doctor", "captain", "warden", "marshal",
          "commander", "chief", "councillor", "councilor", "elder", "sergeant",
          "lieutenant", "professor", "inspector", "magistrate", "overseer")

#: Words that start sentences or link names; never part of an escape candidate's head.
_FUNCTION_WORDS = frozenset(
    "the a an he she it they we i you his her their my our your this that these those "
    "there here then but and or so if when as in on at of for with by to from what who "
    "how why where no not yes now still after before once all some any each every "
    "i'm i'll i'd i've it's he's she's we're they're you're that's there's don't "
    "didn't wasn't isn't can't won't".split())
_CONNECTORS = frozenset("of the de la von van".split())
_COORD_GAP = re.compile(r"^(?:\s*,\s*(?:and\s+)?|\s+and\s+|\s*&\s*)$", re.I)
_SENT_END = re.compile(r"[.!?…]+[\"'”’)\]]*(?:\s+|$)|\n\s*\n")
_CAP_TOKEN = r"[A-Z][A-Za-z]*(?:['\-][A-Za-z]+)*"
_CAP_RUN = re.compile(rf"{_CAP_TOKEN}(?:[ \t]+(?:(?:of|the|de|la|von|van)[ \t]+)?{_CAP_TOKEN})*")
_CAP_WORD = re.compile(_CAP_TOKEN)
_LOWER_WORD = re.compile(r"[a-z][a-z'\-]*")


def stoplist_class(text: str) -> str | None:
    """The stoplist class ('kinship', 'address', 'role', 'pronoun') of ``text``, or None.

    Compares the normalized string, after dropping one leading possessive
    ("my mother" is as generic as "mother")."""
    s = normalize(text.replace("’", "'"))
    for pos in _POSSESSIVES:
        if s.startswith(pos):
            s = s[len(pos):].strip()
            break
    for cls, words in STOPLIST.items():
        if s in words:
            return cls
    return None


# ------------------------------------------------------------------- helpers


def _ns(eid: str) -> str:
    """The id's namespace ('person' in 'person:ilsa_renn'), the kind used for 'same kind'."""
    return eid.partition(":")[0]


def _tokens(name: str) -> list[str]:
    """Lowercase alphanumeric tokens of a name, possessive 's dropped."""
    s = normalize(name.replace("’", "'"))
    return re.findall(r"[a-z0-9]+", re.sub(r"'s\b", "", s))


def is_proper_name(name: str) -> bool:
    """True when every word of the name, after a leading article, is capitalized.

    Lowercase connectors inside ("Order of the Meter") are allowed. "Seed
    Vault" and "SEED VAULT" are proper; "the vault", "the clerk" and "Seed
    Vault hatch" are not. Stoplisted strings are never proper."""
    toks = name.replace("’", "'").split()
    if toks and toks[0].lower() in ("the", "a", "an"):
        toks = toks[1:]
    if not toks or stoplist_class(name):
        return False
    last = len(toks) - 1
    core = [t for i, t in enumerate(toks) if not (0 < i < last and t in _CONNECTORS)]
    return all(t[:1].isupper() for t in core)


def _load_registry(registry: Any) -> tuple[str, dict[str, tuple[list[str], list[str]]], dict[str, str]]:
    """(world_id, id -> (names, aliases), id_repairs) from a path, dict or WorldRegistry."""
    if isinstance(registry, (str, Path)):
        registry = json.loads(Path(registry).read_text())
    if isinstance(registry, Mapping):
        world_id, entities = registry.get("world_id", ""), registry["entities"]
    else:
        world_id, entities = registry.world_id, registry.entities
    cards: dict[str, tuple[list[str], list[str]]] = {}
    repairs: dict[str, str] = {}
    for raw, card in entities.items():
        eid = _norm_id(raw)
        if eid != raw:
            repairs[eid] = raw
        if isinstance(card, Mapping):
            names, aliases = list(card.get("names", [])), list(card.get("aliases", []))
        else:
            names, aliases = list(card.names), list(card.aliases)
        cards[eid] = (names, aliases)
    return world_id, cards, repairs


# ------------------------------------------------------------------- lexicon


@dataclass(frozen=True)
class Mention:
    """One place the text names registry ids: char span, matched surface text,
    index key, match kind and the ids hit (more than one means ambiguous)."""
    start: int
    end: int
    text: str
    key: str
    match: str  # exact | title_surname | prefix
    ids: tuple[str, ...]


class Lexicon:
    """The alias index of one registry: what each normalized string maps to.

    ``strings`` holds the identifying strings (stoplisted ones are in
    ``stoplisted``); ``proper`` the proper-name set per id."""

    def __init__(self, registry: Any) -> None:
        self.world_id, self.cards, self.id_repairs = _load_registry(registry)
        self.strings: dict[str, set[str]] = defaultdict(set)
        self.spellings: dict[str, set[str]] = defaultdict(set)
        self.stoplisted: dict[str, dict[str, Any]] = {}
        self.proper: dict[str, list[str]] = {}
        for eid, (names, aliases) in self.cards.items():
            self.proper[eid] = [n for n in names if is_proper_name(n)]
            for s in names + aliases:
                key = normalize(s.replace("’", "'"))
                if not key:
                    continue
                cls = stoplist_class(s)
                if cls:
                    entry = self.stoplisted.setdefault(key, {"class": cls, "ids": set()})
                    entry["ids"].add(eid)
                    continue
                self.strings[key].add(eid)
                self.spellings[key].add(s)
        # surname (last token of a multi-token proper person name) -> ids
        self.surnames: dict[str, set[str]] = defaultdict(set)
        # first token of a multi-token proper name -> ids
        self.prefixes: dict[str, set[str]] = defaultdict(set)
        for eid, names in self.proper.items():
            for n in names:
                toks = _tokens(n)
                if toks and toks[0] in ("the", "a", "an"):
                    toks = toks[1:]
                if len(toks) < 2:
                    continue
                if _ns(eid) == "person":
                    self.surnames[toks[-1]].add(eid)
                if len(toks[0]) >= 3 and toks[0] not in _FUNCTION_WORDS and toks[0] not in self.strings:
                    self.prefixes[toks[0]].add(eid)
        keys = sorted(self.strings, key=lambda k: (-len(k), k))
        self._exact = re.compile(
            r"(?<!\w)(?:" + "|".join(r"\s+".join(re.escape(w) for w in k.split()) for k in keys) + r")(?!\w)",
            re.I) if keys else None
        self._title = re.compile(
            rf"(?<!\w)(?:{'|'.join(TITLES)})\.?[ \t]+({_CAP_TOKEN})", re.I)

    def mentions(self, text: str, common: frozenset[str] = frozenset()) -> list[Mention]:
        """All mentions in ``text``, sorted by position, non-overlapping.

        ``exact``: a registry string, whole-word, case-insensitive, longest
        string first. ``title_surname``: a title plus a capitalized word that is
        the last word of a multi-word person name ("Warden Cray"); it replaces
        the exact hits inside it. ``prefix``: a capitalized word that is the
        first word of a multi-word proper name and is not itself a registry
        string ("Ilsa" for "Ilsa Renn"); skipped at a sentence start when
        ``common`` (lowercase words seen in the text) shows it is an ordinary
        word."""
        text = text.replace("’", "'")
        found: list[Mention] = []
        if self._exact:
            for m in self._exact.finditer(text):
                key = normalize(m.group(0))
                found.append(Mention(m.start(), m.end(), m.group(0), key, "exact",
                                     tuple(sorted(self.strings[key]))))
        for m in self._title.finditer(text):
            ids = self.surnames.get(m.group(1).lower())
            if not ids:
                continue
            found = [f for f in found if not (f.start >= m.start() and f.end <= m.end())]
            found.append(Mention(m.start(), m.end(), m.group(0), m.group(1).lower(),
                                 "title_surname", tuple(sorted(ids))))
        taken = sorted((f.start, f.end) for f in found)
        for m in _CAP_WORD.finditer(text):
            ids = self.prefixes.get(m.group(0).lower())
            if not ids or _overlaps(taken, m.start(), m.end()):
                continue
            if _sentence_initial(text, m.start()) and m.group(0).lower() in common:
                continue
            found.append(Mention(m.start(), m.end(), m.group(0), m.group(0).lower(),
                                 "prefix", tuple(sorted(ids))))
        return sorted(found, key=lambda f: (f.start, f.end))


def _overlaps(spans: Sequence[tuple[int, int]], start: int, end: int) -> bool:
    return any(s < end and start < e for s, e in spans)


def _sentence_initial(text: str, pos: int) -> bool:
    """True when only quotes, dashes or markup separate ``pos`` from a sentence
    boundary; an opening curly quote ("said, “Nothing") also starts a sentence."""
    i = pos - 1
    while i >= 0 and text[i] in " \t\"”‘'—-*_([":
        i -= 1
    return i < 0 or text[i] in ".!?…\n“"


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Sentence spans by terminal punctuation or blank line ("Dr." splits; accepted)."""
    spans, start = [], 0
    for m in _SENT_END.finditer(text):
        if text[start:m.end()].strip():
            spans.append((start, m.end()))
        start = m.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for m in re.finditer(r"\n\s*\n", text):
        if text[start:m.start()].strip():
            spans.append((start, m.start()))
        start = m.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


def _excerpt(text: str, start: int, end: int, limit: int = 220) -> str:
    s = " ".join(text[start:end].split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


# ------------------------------------------------------------- the report


def _segment_hits(lex: Lexicon, segments: Sequence[str], common: frozenset[str]):
    """Per segment mentions and the item-1 hit table."""
    per_seg: list[list[Mention]] = []
    table: list[dict[str, Any]] = []
    for i, seg in enumerate(segments):
        ms = lex.mentions(seg, common)
        per_seg.append(ms)
        counts: dict[str, Counter] = defaultdict(Counter)
        for m in ms:
            for eid in m.ids:
                counts[eid][(m.key, m.match, len(m.ids) > 1)] += 1
        if counts:
            table.append({"segment": i, "ids": {
                eid: [{"string": k, "match": mt, "count": n, "ambiguous": amb}
                      for (k, mt, amb), n in sorted(c.items())]
                for eid, c in sorted(counts.items())}})
    return per_seg, table


def _ambiguous(lex: Lexicon, per_seg: list[list[Mention]]) -> list[dict[str, Any]]:
    mention_counts = Counter(m.key for ms in per_seg for m in ms if m.match == "exact")
    out = []
    for key, ids in sorted(lex.strings.items()):
        if len(ids) < 2:
            continue
        out.append({"string": key, "spellings": sorted(lex.spellings[key]), "ids": sorted(ids),
                    "same_kind": len({_ns(i) for i in ids}) == 1,
                    "text_mentions": mention_counts.get(key, 0)})
    out.sort(key=lambda e: (-len(e["ids"]), -e["text_mentions"], e["string"]))
    return out


def _escapes(lex: Lexicon, segments: Sequence[str], per_seg: list[list[Mention]],
             common: frozenset[str]) -> list[dict[str, Any]]:
    """Capitalized runs that match no registry string, ranked by frequency.

    A run is a sequence of capitalized words (lowercase "of/the/de" allowed
    inside). At a sentence start, leading function words and ordinary words
    (seen lowercase in the text, and in no registry string) are stripped
    ("Because Marn" becomes "Marn"); a lone
    sentence-initial word that also occurs lowercase in the text is an
    ordinary word and dropped. Headings (# lines), stoplisted strings and
    runs that equal a hit span are skipped. ``overlaps`` lists ids with a
    string sharing words with the run, so a partial name ("Ilsa") is visible
    as such."""
    key_tokens = {k: set(k.split()) for k in lex.strings}
    reg_words = {t for ts in key_tokens.values() for t in ts}
    found: dict[str, dict[str, Any]] = {}
    for si, seg in enumerate(segments):
        seg = seg.replace("’", "'")
        spans = [(m.start, m.end) for m in per_seg[si]]
        offset = 0
        for line in seg.split("\n"):
            if not line.lstrip().startswith("#"):
                for m in _CAP_RUN.finditer(line):
                    start, end, run = m.start(), m.end(), m.group(0)
                    if _sentence_initial(line, start):
                        words = run.split()
                        while words and (words[0].lower() in _FUNCTION_WORDS or (
                                words[0].lower() in common and words[0].lower() not in reg_words)):
                            run = run[len(words[0]):].lstrip()
                            start = end - len(run)
                            words = run.split()
                        if len(words) == 1 and run.lower() in common:
                            continue
                    run = re.sub(r"'s$", "", run)
                    if not run or len(run) < 2 or run.lower() in _FUNCTION_WORDS:
                        continue
                    key = normalize(run)
                    if key in lex.strings or key in lex.stoplisted or stoplist_class(run):
                        continue
                    if (offset + start, offset + start + len(run)) in set(spans):
                        continue
                    e = found.setdefault(key, {"string": key, "surface": Counter(), "count": 0,
                                               "segments": set(), "example": ""})
                    e["surface"][run] += 1
                    e["count"] += 1
                    e["segments"].add(si)
                    if not e["example"]:
                        e["example"] = _excerpt(line, max(0, start - 80), end + 80)
            offset += len(line) + 1
    out = []
    for key, e in found.items():
        toks = set(key.split())
        over = sorted({i for k, ts in key_tokens.items() if ts <= toks or toks <= ts
                       for i in lex.strings[k]})
        out.append({"string": key, "surface": e["surface"].most_common(1)[0][0],
                    "count": e["count"], "segments": sorted(e["segments"]),
                    "overlaps": over[:8], "example": e["example"]})
    out.sort(key=lambda e: (-e["count"], e["string"]))
    return out


def _risk_pairs(lex: Lexicon) -> dict[tuple[str, str], list[str]]:
    """Same-kind pairs worth testing for distinctness, with why: they share an
    identifying string, or one lists the other's proper name as an alias."""
    why: dict[tuple[str, str], list[str]] = defaultdict(list)
    for key, ids in lex.strings.items():
        for a, b in combinations(sorted(ids), 2):
            if _ns(a) == _ns(b):
                why[(a, b)].append(f"shared string {key!r}")
    for cand in _merge_pairs(lex):
        pair = tuple(sorted((cand["holder"], cand["named"])))
        why[pair].append(f"{cand['holder']} lists {cand['string']!r}, the proper name of {cand['named']}")
    return why


def _merge_pairs(lex: Lexicon) -> list[dict[str, str]]:
    """Item 6 before exclusion: holder A has an alias equal to a full proper
    name of same-kind card B that A does not name itself. A person's full
    name needs two words ("Ilsa Renn", not "Ilsa")."""
    out = []
    for a, (names, aliases) in sorted(lex.cards.items()):
        own = {normalize(n.replace("’", "'")) for n in names}
        for b in sorted(lex.cards):
            if a == b or _ns(a) != _ns(b):
                continue
            for pn in lex.proper[b]:
                key = normalize(pn.replace("’", "'"))
                if _ns(b) == "person" and len(_tokens(pn)) < 2:
                    continue
                if key in own:
                    continue
                if any(normalize(al.replace("’", "'")) == key for al in aliases):
                    out.append({"holder": a, "named": b, "string": key, "named_proper": pn})
    return out


def _name_distinct(lex: Lexicon, a: str, b: str) -> str | None:
    """Evidence string when both cards have proper names and no proper name of
    one has its words inside a proper name of the other, else None."""
    pa, pb = lex.proper[a], lex.proper[b]
    if not pa or not pb:
        return None
    for x in pa:
        for y in pb:
            tx, ty = set(_tokens(x)) - _CONNECTORS - {"the"}, set(_tokens(y)) - _CONNECTORS - {"the"}
            if tx <= ty or ty <= tx:
                return None
    return f"different proper names: {pa[0]!r} vs {pb[0]!r}"


def _coordinated(seg: str, ms: list[Mention]) -> list[list[Mention]]:
    """Runs of mentions joined by "and", "&", "," or ", and" (with at least one
    "and"/"&"): the names in "Sela and Marn" or "Sela, Marn, and Tovan"."""
    out: list[list[Mention]] = []
    chain: list[Mention] = []
    has_and = False
    for m in ms:
        gap = seg[chain[-1].end:m.start] if chain else None
        if chain and _COORD_GAP.match(gap):
            chain.append(m)
            has_and |= bool(re.search(r"and|&", gap, re.I))
            continue
        if has_and:
            out.append(chain)
        chain, has_and = [m], False
    if has_and:
        out.append(chain)
    return out


def _distinctness(lex: Lexicon, segments: Sequence[str], per_seg: list[list[Mention]],
                  risk: dict[tuple[str, str], list[str]]) -> list[dict[str, Any]]:
    """Item 5. Strong evidence: different proper names of the same kind (checked
    for risk pairs only, else every pair of unrelated people would be listed),
    and coordination ("Sela and Marn" in one sentence, any same-kind pair).
    Weak evidence: co-presence in one paragraph (risk pairs only; segments are
    chapters, so a segment is too coarse a scene). Only unambiguous mentions
    count for coordination and co-presence."""
    ev: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for pair in sorted(risk):
        e = _name_distinct(lex, *pair)
        if e:
            ev[pair].append({"type": "distinct_proper_names", "strength": "strong",
                             "evidence": e, "count": 1, "segments": []})

    coord: dict[tuple[str, str], dict[str, Any]] = {}
    copres: dict[tuple[str, str], dict[str, Any]] = {}
    for si, (seg, ms) in enumerate(zip(segments, per_seg)):
        seg = seg.replace("’", "'")
        uniq = [m for m in ms if len(m.ids) == 1]
        starts = [s for s, _ in _sentence_spans(seg)]
        spans = _sentence_spans(seg)
        by_sent: dict[int, list[Mention]] = defaultdict(list)
        for m in uniq:
            by_sent[bisect.bisect_right(starts, m.start) - 1].append(m)
        for sidx, sms in by_sent.items():
            sent = _excerpt(seg, *spans[sidx])
            for chain in _coordinated(seg, sorted(sms, key=lambda m: m.start)):
                for x, y in combinations(chain, 2):
                    a, b = x.ids[0], y.ids[0]
                    if a != b and _ns(a) == _ns(b):
                        slot = coord.setdefault(tuple(sorted((a, b))), {
                            "type": "coordination", "strength": "strong",
                            "evidence": sent, "count": 0, "segments": []})
                        slot["count"] += 1
                        if si not in slot["segments"]:
                            slot["segments"].append(si)
        paras = _paragraph_spans(seg)
        pstarts = [s for s, _ in paras]
        by_para: dict[int, set[str]] = defaultdict(set)
        for m in uniq:
            by_para[bisect.bisect_right(pstarts, m.start) - 1].add(m.ids[0])
        for pidx, ids in by_para.items():
            for a, b in combinations(sorted(ids), 2):
                if (a, b) in risk:
                    slot = copres.setdefault((a, b), {
                        "type": "co_presence", "strength": "weak",
                        "evidence": "named in one paragraph: " + _excerpt(seg, *paras[pidx]),
                        "count": 0, "segments": []})
                    slot["count"] += 1
                    if si not in slot["segments"]:
                        slot["segments"].append(si)
    for pair, e in coord.items():
        ev[pair].append(e)
    for pair, e in copres.items():
        ev[pair].append(e)

    out = []
    for pair in sorted(ev):
        items = ev[pair]
        out.append({"ids": list(pair),
                    "strength": "strong" if any(i["strength"] == "strong" for i in items) else "weak",
                    "why_checked": risk.get(pair, []), "evidence": items})
    out.sort(key=lambda p: (p["strength"] != "strong", p["ids"]))
    return out


def build_report(registry: Any, segments: Sequence[str]) -> dict[str, Any]:
    """Build the full alias-index report for ``registry`` over ``segments``.

    ``registry`` is a path to registry.json, a loaded dict, or a
    WorldRegistry; ``segments`` are source-text chunks (never bible text).
    Returns a JSON-serializable dict with the six items and a ``counts``
    summary. Deterministic; no model call."""
    lex = Lexicon(registry)
    common = frozenset(w for seg in segments for w in _LOWER_WORD.findall(seg.replace("’", "'")))
    per_seg, hit_table = _segment_hits(lex, segments, common)
    ambiguous = _ambiguous(lex, per_seg)
    escapes = _escapes(lex, segments, per_seg, common)
    risk = _risk_pairs(lex)
    distinct = _distinctness(lex, segments, per_seg, risk)
    strong = {tuple(p["ids"]) for p in distinct if p["strength"] == "strong"}
    weak_types = {tuple(p["ids"]): [e["type"] for e in p["evidence"]] for p in distinct}
    merges, excluded = [], []
    for c in _merge_pairs(lex):
        pair = tuple(sorted((c["holder"], c["named"])))
        if pair in strong:
            reasons = [e["evidence"] for p in distinct if tuple(p["ids"]) == pair
                       for e in p["evidence"] if e["strength"] == "strong"]
            excluded.append({**c, "excluded_by": reasons})
        else:
            merges.append({**c, "weak_evidence_against": weak_types.get(pair, [])})
    report = {
        "world_id": lex.world_id,
        "segments": len(segments),
        "entities": len(lex.cards),
        "id_repairs": lex.id_repairs,
        "index": {k: sorted(v) for k, v in sorted(lex.strings.items())},
        "stoplisted": {k: {"class": v["class"], "ids": sorted(v["ids"])}
                       for k, v in sorted(lex.stoplisted.items())},
        "segment_hits": hit_table,
        "ambiguous_strings": ambiguous,
        "escape_candidates": escapes,
        "distinctness_evidence": distinct,
        "merge_candidates": merges,
        "merge_excluded": excluded,
    }
    report["counts"] = {
        "index_strings": len(lex.strings),
        "segments_with_hits": len(hit_table),
        "ambiguous_strings": len(ambiguous),
        "stoplisted_strings": len(lex.stoplisted),
        "escape_candidates": len(escapes),
        "distinct_pairs": len(distinct),
        "distinct_pairs_strong": sum(1 for p in distinct if p["strength"] == "strong"),
        "merge_candidates": len(merges),
        "merge_excluded": len(excluded),
    }
    logger.info("alias index: %s", report["counts"])
    return report


def slice_ids(registry: Any, text: str) -> set[str]:
    """Ids the pass-1 registry slice should keep for ``text``: every id the text
    hits, plus every id sharing an identifying string with a hit id, so
    ambiguous siblings ("the vault" cards) reach the extractor together. Used by
    ``Pipeline`` behind its ``alias_slice`` flag (off by default)."""
    lex = Lexicon(registry)
    common = frozenset(_LOWER_WORD.findall(text.replace("’", "'")))
    hit = {i for m in lex.mentions(text, common) for i in m.ids}
    keep = set(hit)
    for ids in lex.strings.values():
        if ids & hit:
            keep |= ids
    return keep


# ------------------------------------------------- Part B: writing distinctness


def _is_person(w: Any, registry: Any, eid: str) -> str | None:
    """Why ``eid`` counts as a person (ALIAS-INDEX-V1 Part B, r3), or None.

    Any one of three makes it a person: its id is in the ``person:`` namespace,
    its seeded card's ``kind`` is ``person``, or the canon ``kind`` folded in
    the world after seeding is ``person``. Kinds compare case-insensitively
    and trimmed; a wider net only ever keeps a pair report-only."""
    if _norm_id(eid).startswith("person:"):
        return "person_namespace"
    card = registry.entities.get(eid)
    if card is not None and str(card.kind).strip().lower() == "person":
        return "person_card_kind"
    fold = w.state(eid, "kind")
    winner = getattr(fold, "winner", None)
    if winner is not None and str(winner.value).strip().lower() == "person":
        return "person_folded_kind"
    return None


def apply_distinctness(w: Any, registry: Any, report: Mapping[str, Any]) -> dict[str, Any]:
    """Write the host's ``distinct_from`` for ``report``'s strong distinctness
    pairs (ALIAS-INDEX-V1 Part B). The world ``w`` holds the seeded registry
    and nothing else; the call goes through ``w.porcelain.reject``.

    A pair is written only when both ids are seeded (keys of
    ``registry.entities``) and neither is a person (see ``_is_person``). Every
    other strong pair is returned under ``report_only`` with its reason. A
    ``conflict_*`` receipt wrote nothing and is listed as written-with-that-
    outcome; nothing is ever retracted. Returns ``{"written", "report_only"}``,
    in report order (deterministic)."""
    written: list[dict[str, Any]] = []
    report_only: list[dict[str, Any]] = []
    for p in report["distinctness_evidence"]:
        if p["strength"] != "strong":
            continue
        a, b = p["ids"]
        strong = [{"type": e["type"], "evidence": e["evidence"]}
                  for e in p["evidence"] if e["strength"] == "strong"]
        entry = {"ids": [a, b], "evidence": strong[0]["evidence"] if strong else "",
                 "evidence_all": strong}
        missing = [i for i in (a, b) if i not in registry.entities]
        if missing:
            report_only.append({**entry, "reason": "not_seeded", "detail": missing})
            continue
        why = {i: r for i in (a, b) if (r := _is_person(w, registry, i))}
        if why:
            report_only.append({**entry, "reason": "person", "detail": why})
            continue
        try:
            outcome = w.porcelain.reject(a, b).get("outcome")
        except ValueError as exc:  # the gate refused the pair; nothing was written
            written.append({**entry, "outcome": f"error: {exc}"})
            logger.warning("alias distinctness: reject(%s, %s) refused: %s", a, b, exc)
            continue
        written.append({**entry, "outcome": outcome})
    logger.info("alias distinctness: %d written, %d report-only", len(written), len(report_only))
    return {"written": written, "report_only": report_only}


# --------------------------------------------------------------- rendering


def report_md(r: Mapping[str, Any], title: str = "Alias index") -> str:
    """Render a ``build_report`` dict as a short Markdown summary."""
    c = r["counts"]
    lines = [f"# {title}", "",
             f"{r['entities']} ids, {r['segments']} segments, {c['index_strings']} identifying strings "
             f"({c['stoplisted_strings']} stoplisted).", "",
             "| item | count |", "|---|---|",
             f"| 2 ambiguous strings | {c['ambiguous_strings']} |",
             f"| 4 escape candidates | {c['escape_candidates']} |",
             f"| 5 distinctness pairs (strong) | {c['distinct_pairs']} ({c['distinct_pairs_strong']}) |",
             f"| 6 merge candidates (excluded) | {c['merge_candidates']} ({c['merge_excluded']}) |", "",
             "## Ambiguous strings (one string, 2+ ids)", ""]
    for a in r["ambiguous_strings"][:30]:
        lines.append(f"- `{a['string']}` ({a['text_mentions']} mentions"
                     f"{'' if a['same_kind'] else ', mixed kinds'}): "
                     + ", ".join(f"`{i}`" for i in a["ids"]))
    if not r["ambiguous_strings"]:
        lines.append("- none")
    lines += ["", "## Distinctness evidence", ""]
    for p in r["distinctness_evidence"]:
        a, b = p["ids"]
        lines.append(f"- `{a}` / `{b}` ({p['strength']})")
        for e in p["evidence"]:
            lines.append(f"  - {e['type']} ({e['strength']}, x{e['count']}): {e['evidence']}")
    if not r["distinctness_evidence"]:
        lines.append("- none")
    lines += ["", "## Merge candidates", ""]
    for m in r["merge_candidates"]:
        weak = f"; weak evidence against: {', '.join(m['weak_evidence_against'])}" \
            if m["weak_evidence_against"] else ""
        lines.append(f"- `{m['holder']}` lists `{m['string']}`, the name of `{m['named']}`{weak}")
    for m in r["merge_excluded"]:
        lines.append(f"- EXCLUDED `{m['holder']}` lists `{m['string']}` ({m['named']}): "
                     + "; ".join(m["excluded_by"]))
    if not r["merge_candidates"] and not r["merge_excluded"]:
        lines.append("- none")
    lines += ["", "## Escape candidates (top 25 by frequency)", ""]
    for e in r["escape_candidates"][:25]:
        ov = f" (overlaps {', '.join(f'`{i}`' for i in e['overlaps'][:3])})" if e["overlaps"] else ""
        lines.append(f"- `{e['surface']}` x{e['count']} in segments {e['segments']}{ov}")
    if not r["escape_candidates"]:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def write_report(report: Mapping[str, Any], out_dir: str | Path,
                 title: str = "Alias index") -> tuple[Path, Path]:
    """Write ``alias_index.json`` and ``alias_index.md`` into ``out_dir``; return both paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    js, md = out / "alias_index.json", out / "alias_index.md"
    js.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    md.write_text(report_md(report, title))
    return js, md


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("registry", help="path to registry.json (read only)")
    ap.add_argument("--story", help="story.md (default: the chapter-test story)")
    ap.add_argument("--out", required=True, help="directory for alias_index.json/.md")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import run_pass0_baseline  # the segmentation lives there; needs PYTHONPATH=src

    if args.story:
        run_pass0_baseline.STORY = Path(args.story)
    segments = run_pass0_baseline.story_segments()
    report = build_report(args.registry, segments)
    js, md = write_report(report, args.out, title=f"Alias index ({Path(args.out).name})")
    print(f"{js}\n{md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
