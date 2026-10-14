"""A declared vocabulary: names, value shapes and semantics as data (RECIPE-VOCAB-V1).

Three projects write facts about the same small worlds, and nothing named the
attributes they share. A **vocabulary** is a list of **terms**; each term is
one canonical attribute with its value type, its recommended or closed values,
its ``attr:`` declaration (the RFC-001 axes and READ-SURFACE-V1's durability
pin), the variant names that fold into it and a one-line gloss.

This module sits outside the engine core, as ``service`` and ``build`` do. It
reaches the engine only through seams the engine already has:

- :func:`attribute_default` returns the callable ``World(attribute_default=...)``
  takes, so a term's semantics land before its first data row;
- :func:`apply_aliases` installs the term aliases through
  ``Ingestor.add_attribute_alias``;
- :func:`check` is a read-only lint over the porcelain's reads.

Declared semantics never reject a fact (RFC-001): a value outside a term's
``values`` is still written, and :func:`check` reports it.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from patternbuffer.semantics import valid_declaration

logger = logging.getLogger(__name__)

__all__ = [
    "ENTITY", "LITERAL", "FINDING_KINDS", "Finding", "RECIPE", "Term", "Vocabulary",
    "apply_aliases", "attribute_default", "check",
]

ENTITY, LITERAL = "entity", "literal"
_VALUE_TYPES = (ENTITY, LITERAL)

# The `attr:` declaration keys a host's attribute_default may carry.
_DECLARABLE = ("arity", "relation_family", "fold_policy", "structural", "durability",
               "resolvable_for")

# The gate's normal form of an attribute name: an alias installed in any other
# shape would never match what the gate looks up.
_NAME = re.compile(r"[a-z][a-z0-9_]*")

FINDING_KINDS = (
    "off_vocabulary_value", "wrong_value_type", "alias_in_log", "undeclared_semantics",
    "exits_none_with_edge", "locked_but_open", "locked_not_shut", "locked_state_missing",
    "state_locked_legacy",
)


@dataclass(frozen=True)
class Term:
    """One canonical attribute of a vocabulary.

    ``values`` are the canonical literal values (empty for an entity-valued
    term, or an open literal one with no list); ``open_values`` is ``False``
    when ``values`` is the whole set and ``True`` when it is a recommended
    list. ``semantics`` is the ``attr:`` declaration as a dict (possibly
    empty). ``aliases`` are the variant names that canonicalize to
    ``attribute``. ``gloss`` is one line, used verbatim in a prompt.
    """

    attribute: str
    value_type: str
    values: tuple[Any, ...] = ()
    open_values: bool = True
    semantics: Mapping[str, Any] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    gloss: str = ""

    def __post_init__(self) -> None:
        name = self.attribute
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise ValueError(f"term {name!r}: an attribute is a lowercase name "
                             "(letters, digits, underscore, led by a letter)")
        if self.value_type not in _VALUE_TYPES:
            raise ValueError(f"term {name!r}: unknown value_type {self.value_type!r} "
                             f"(one of {list(_VALUE_TYPES)})")
        object.__setattr__(self, "values", tuple(self.values))
        object.__setattr__(self, "aliases", tuple(self.aliases))
        object.__setattr__(self, "semantics", dict(self.semantics))
        if self.open_values is not True and self.open_values is not False:
            raise ValueError(f"term {name!r}: open_values must be a bool")
        if self.value_type == ENTITY and self.values:
            raise ValueError(f"term {name!r}: an entity-valued term has no values")
        if self.value_type == LITERAL and not self.open_values and not self.values:
            raise ValueError(f"term {name!r}: a closed term needs its values")
        if len({_key(v) for v in self.values}) != len(self.values):
            raise ValueError(f"term {name!r}: a value is listed twice")
        for alias in self.aliases:
            if not isinstance(alias, str) or not _NAME.fullmatch(alias):
                raise ValueError(f"term {name!r}: alias {alias!r} is not a lowercase name")
            if alias == name:
                raise ValueError(f"term {name!r}: it is its own alias")
        if len(set(self.aliases)) != len(self.aliases):
            raise ValueError(f"term {name!r}: an alias is listed twice")
        for predicate, declared in self.semantics.items():
            if predicate not in _DECLARABLE:
                raise ValueError(f"term {name!r}: {predicate!r} is not a declarable "
                                 f"semantics key (one of {list(_DECLARABLE)})")
            if predicate == "resolvable_for" and isinstance(declared, (list, tuple, set, frozenset)):
                ok = bool(declared) and all(valid_declaration(predicate, k) for k in declared)
            else:
                ok = valid_declaration(predicate, declared)
            if not ok:
                raise ValueError(f"term {name!r}: {predicate}={declared!r} is not a valid declaration")
        if not isinstance(self.gloss, str) or "\n" in self.gloss:
            raise ValueError(f"term {name!r}: the gloss is one line")


@dataclass(frozen=True)
class Vocabulary:
    """A named list of terms. Construction refuses a duplicate attribute, an
    alias claimed by two terms, and an alias that is another term's attribute."""

    name: str
    terms: tuple[Term, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "terms", tuple(self.terms))
        seen: dict[str, str] = {}
        for term in self.terms:
            if not isinstance(term, Term):
                raise ValueError(f"vocabulary {self.name!r}: {term!r} is not a Term")
            if term.attribute in seen:
                raise ValueError(f"vocabulary {self.name!r}: attribute {term.attribute!r} "
                                 "is declared twice")
            seen[term.attribute] = term.attribute
        claimed: dict[str, str] = {}
        for term in self.terms:
            for alias in term.aliases:
                if alias in seen:
                    raise ValueError(f"vocabulary {self.name!r}: alias {alias!r} of "
                                     f"{term.attribute!r} is itself a term")
                if alias in claimed:
                    raise ValueError(f"vocabulary {self.name!r}: alias {alias!r} is claimed by "
                                     f"{claimed[alias]!r} and {term.attribute!r}")
                claimed[alias] = term.attribute

    def term(self, attribute: str) -> Term | None:
        """The term whose canonical attribute is ``attribute``, or None."""
        for term in self.terms:
            if term.attribute == attribute:
                return term
        return None

    def alias_map(self) -> dict[str, str]:
        """Every alias, to the canonical attribute it folds into."""
        return {alias: term.attribute for term in self.terms for alias in term.aliases}

    def prompt_section(self) -> str:
        """The vocabulary section of an extraction prompt: one line per term,
        ``<attribute>: <gloss>``, with its values when the term is closed."""
        lines = ["Use these attribute names where they fit:"]
        for term in self.terms:
            line = f"{term.attribute}: {term.gloss}"
            if term.value_type == LITERAL and not term.open_values:
                line += f" (values: {', '.join(_say(v) for v in term.values)})"
            lines.append(line)
        return "\n".join(lines)


def _key(value: Any) -> tuple[type, Any]:
    """A literal as compared: by type and value, so ``True`` is not ``1``."""
    return (type(value), value)


def _say(value: Any) -> str:
    """A literal as a prompt or message shows it (a boolean as JSON's)."""
    return json.dumps(value) if isinstance(value, bool) else str(value)


# ---------------------------------------------------------------- the recipe

RECIPE = Vocabulary("recipe", (
    Term("controls", ENTITY,
         semantics={"arity": "set_valued", "durability": "CONSTITUTIVE"},
         aliases=("operates", "powers"),
         gloss="what a switch, lever, plate, button or keypad works: `<switch> controls <light>`"),
    Term("link_type", LITERAL,
         values=("switch", "lever", "plate", "button", "keypad", "dial"), open_values=False,
         semantics={"durability": "CONSTITUTIVE"}, aliases=("control_type",),
         gloss="what kind of control the source is"),
    Term("control_mode", LITERAL, values=("latching", "momentary"), open_values=False,
         semantics={"durability": "CONSTITUTIVE"}, aliases=("switch_mode",),
         gloss="latching stays as set; momentary acts only while held"),
    Term("state", LITERAL, values=("on", "off", "open", "shut"), open_values=True,
         gloss="a thing's one main setting now: a door's or lid's open or shut, a light's or switch's on or off; never locked"),
    Term("locked", LITERAL, values=(True, False), open_values=False,
         semantics={"durability": "STATE"},
         gloss="true while a lock is engaged; a locked door is also state shut"),
    Term("lit", LITERAL, values=("dark", "dim", "lit", "day", "night"), open_values=False,
         aliases=("light_level", "lighting", "illumination"),
         gloss="how much light a place has now"),
    Term("outdoors", LITERAL, values=(True, False), open_values=False,
         semantics={"durability": "CONSTITUTIVE"}, aliases=("is_outdoors",),
         gloss="a place open to the sky; written timeless"),
    Term("exits", LITERAL, values=("none",), open_values=False,
         gloss='an observed "no way out": only ever the word none; ways out are connects_to'),
    Term("disposition", LITERAL,
         values=("friendly", "wary", "hostile", "timid", "playful", "indifferent"),
         open_values=True, semantics={"durability": "DISPOSITIONAL"},
         aliases=("temperament", "demeanor", "demeanour"),
         gloss="a being's temperament"),
    Term("code", LITERAL, open_values=True, aliases=("passcode", "combination"),
         gloss="what a keypad or lock opens to"),
    Term("colour", LITERAL,
         values=("black", "white", "grey", "brown", "red", "blue", "green", "yellow"),
         open_values=True, aliases=("color",),
         gloss="a thing's main colour, one plain word"),
))


# --------------------------------------------------------- the two seams


def attribute_default(
    vocabulary: Vocabulary,
    fallback: Callable[[str], dict | None] | None = None,
) -> Callable[[str], dict | None]:
    """The callable for ``World(..., attribute_default=...)``: a term's
    ``semantics`` (a fresh dict, possibly empty), and for any other attribute
    ``fallback(attribute)`` or None. The engine asks once per attribute, at its
    first row, so a declaration always precedes its data."""

    def default(attribute: str) -> dict | None:
        term = vocabulary.term(attribute)
        if term is not None:
            return {k: (list(v) if isinstance(v, (list, tuple, set, frozenset)) else v)
                    for k, v in term.semantics.items()}
        return fallback(attribute) if fallback is not None else None

    return default


def apply_aliases(world: Any, vocabulary: Vocabulary) -> None:
    """Install every term alias on ``world``'s gate
    (``Ingestor.add_attribute_alias``). The alias map is in memory, so a host
    calls this each time it opens a world; applying twice is harmless.

    Raises ``ValueError`` naming the pair when an alias is an inverse relation
    (``holds``, ``wearing``: the engine refuses it) or already maps to another
    attribute. Nothing is installed for a pair that raises; pairs before it
    stay installed (the map is in memory and the call is repeatable)."""
    ingestor = world.ingestor
    for alias, canonical in vocabulary.alias_map().items():
        current = ingestor.canonical_attribute(alias)
        if current not in (alias, canonical):
            raise ValueError(f"alias {alias!r} -> {canonical!r}: the gate already maps "
                             f"{alias!r} to {current!r}")
        try:
            ingestor.add_attribute_alias(alias, canonical)
        except ValueError as exc:
            raise ValueError(f"alias {alias!r} -> {canonical!r}: {exc}") from exc


# ------------------------------------------------------------------- check


@dataclass(frozen=True)
class Finding:
    """One thing :func:`check` found. ``kind`` is one of :data:`FINDING_KINDS`;
    ``detail`` says why in a sentence."""

    kind: str
    entity: str | None
    attribute: str | None
    value: Any
    detail: str


def check(world: Any, vocabulary: Vocabulary, *, frame: str = "canon") -> list[Finding]:
    """Lint ``world``'s ``frame`` against ``vocabulary``: read-only (no write,
    no model call), through the porcelain's reads. Returns the findings sorted
    by kind, entity and attribute; an empty list is a clean world.

    Every row of the frame is read (all of valid time, not only the head), so
    an old off-vocabulary row is found as well as a current one. The checks
    that name an attribute, ``exits``, ``locked`` and ``state``, run only when
    the vocabulary has that term."""
    p = world.porcelain
    rows = p.facts(frame, bookkeeping=False)
    aliases = vocabulary.alias_map()
    out: list[Finding] = []
    seen_attrs: set[str] = set()

    def add(kind: str, row_or_entity: Any, attribute: str | None, value: Any, detail: str) -> None:
        entity = row_or_entity["entity"] if isinstance(row_or_entity, dict) else row_or_entity
        out.append(Finding(kind, entity, attribute, value, detail))

    for row in rows:
        attr = row["attribute"]
        canonical = aliases.get(attr, attr)
        term = vocabulary.term(canonical)
        if term is None:
            continue
        seen_attrs.add(canonical)
        value, vtype = row["value"], row["value_type"]
        if attr != canonical:
            add("alias_in_log", row, attr, value,
                f"stored under the alias {attr!r}; {canonical!r} is the term "
                "(written before apply_aliases ran)")
        if term.value_type == LITERAL and vtype == ENTITY:
            add("wrong_value_type", row, attr, value,
                f"{canonical!r} is literal-valued; this row's value is an entity")
        elif term.value_type == ENTITY and vtype == LITERAL:
            add("wrong_value_type", row, attr, value,
                f"{canonical!r} is entity-valued; this row's value is a literal")
        elif (term.value_type == LITERAL and vtype == LITERAL and not term.open_values
              and _key(value) not in {_key(v) for v in term.values}):
            add("off_vocabulary_value", row, attr, value,
                f"{canonical!r} is closed to {[v for v in term.values]!r}")
        if canonical == "state" and vocabulary.term("locked") is not None and value == "locked":
            add("state_locked_legacy", row, attr, value,
                "a lock is `locked · true` with `state · shut`, not `state · locked`")

    # A term whose semantics the world does not carry, because rows came first.
    for term in vocabulary.terms:
        if term.semantics and term.attribute in seen_attrs:
            missing = _uncarried(world, term)
            if missing:
                add("undeclared_semantics", None, term.attribute, None,
                    f"the world does not carry {missing} for {term.attribute!r} "
                    "(rows were written before the declaration)")

    if vocabulary.term("exits") is not None:
        out.extend(_exits_with_edges(p, rows, frame))
    if vocabulary.term("locked") is not None and vocabulary.term("state") is not None:
        out.extend(_locked_pairs(p, rows, frame))

    out.sort(key=lambda f: (f.kind, f.entity or "", f.attribute or "", str(f.value)))
    return out


def _uncarried(world: Any, term: Term) -> dict[str, Any]:
    """The declared keys of ``term`` that ``world`` does not carry for it: the
    visible ``attr:<term>`` declaration rows themselves, read key by key (the
    last visible row of a predicate wins, as the semantics view folds them), not
    the effective semantics. A term key equal to the engine's built-in default
    is still missing until a row declares it (pbr, code review)."""
    declared_rows: dict[str, Any] = {}
    resolvable: set[str] = set()
    for row in world.buffer.visible(entity=f"attr:{term.attribute}"):
        if row.attribute == "resolvable_for":
            if valid_declaration("resolvable_for", row.value):
                resolvable.add(row.value)
        elif row.attribute in _DECLARABLE:
            declared_rows[row.attribute] = row.value
    missing: dict[str, Any] = {}
    for predicate, declared in term.semantics.items():
        if predicate == "resolvable_for":
            kinds = [declared] if isinstance(declared, str) else list(declared)
            if not set(kinds) <= resolvable:
                missing[predicate] = declared
        elif predicate not in declared_rows or declared_rows[predicate] != declared:
            missing[predicate] = declared
    return missing


def _exits_with_edges(p: Any, rows: Iterable[dict], frame: str) -> list[Finding]:
    """A place served `exits · none` that also has a current `connects_to` edge
    (either end), served as written."""
    edge_ends: set[str] = set()
    for row in rows:
        if (row["attribute"] == "connects_to" and row["value_type"] == ENTITY
                and row["valid"][1] is None):
            edge_ends.update((row["entity"], row["value"]))
    found = []
    for entity in sorted({r["entity"] for r in rows if r["attribute"] == "exits"}):
        served = p.state(entity, "exits", frame)
        if (served["status"] == "known" and served["fact"]["value"] == "none"
                and entity in edge_ends):
            found.append(Finding(
                "exits_none_with_edge", entity, "exits", "none",
                "the place says it has no way out and also has a connects_to edge"))
    return found


def _locked_pairs(p: Any, rows: Iterable[dict], frame: str) -> list[Finding]:
    """The folded `locked`/`state` pair at the head: a served `locked · true`
    needs a served `state · shut`."""
    found = []
    for entity in sorted({r["entity"] for r in rows if r["attribute"] == "locked"}):
        locked = p.state(entity, "locked", frame)
        if not (locked["status"] == "known" and locked["fact"]["value"] is True):
            continue
        state = p.state(entity, "state", frame)
        if state["status"] != "known":
            found.append(Finding(
                "locked_state_missing", entity, "state", None,
                f"locked · true but state is {state['status']}: a locked door also reads `state · shut`"))
            continue
        current = state["fact"]["value"]
        if current == "shut":
            continue
        kind = "locked_but_open" if current == "open" else "locked_not_shut"
        found.append(Finding(
            kind, entity, "state", current,
            f"locked · true but state is {current!r}: a locked door also reads `state · shut`"))
    return found
