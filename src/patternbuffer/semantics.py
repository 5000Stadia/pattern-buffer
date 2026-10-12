"""Attribute semantics as data (ATTRIBUTE-SEMANTICS-V1).

Attribute-level *behavior* — arity (functional vs set-valued), relation
family (containment tree / lateral graph / none), fold policy (by class,
last write, accrue), structural-ness, and the host's durability pin
(READ-SURFACE-V1 §1) — lifted out of the engine's code constants into
per-world, rebuildable, *declared* semantics that every consumer reads
through this one service. Domain vocabulary carries its own fold behavior
without engine edits.

Declarations are ordinary assertions about an ``attr:<name>`` entity (the
canonicalization-as-receipts pattern generalized); the sidecar here is a
rebuildable view over them, never truth (P2). Unspecified attributes return
the built-in defaults, so a world with zero declarations behaves exactly as
the pre-RFC engine did.

Two invariants this module owns (whitepaper guardrail; spec §5):
- **Inviolable core.** The engine's constitutional predicates (the
  containment family, ``kind``/``connects_to``/``adjacent_to``/``caused_by``,
  the identity predicates) can never be redeclared. A host adds domain
  semantics; it never redefines a primitive.
- **Declared semantics never reject a fact.** They govern how a row *folds*,
  never whether it is *admitted* (the Kernos rejection-test). The only
  rejection is authority-on-vocabulary (a forbidden ``attr:*`` write), never
  schema-on-world-facts.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from patternbuffer.buffer import PatternBuffer
from patternbuffer.model import (
    ATTR_PREFIX,
    CONTAINMENT_FAMILY,
    INVIOLABLE_CORE,
    META_ATTRIBUTES,
    SEMANTICS_PREDICATES,
    SET_VALUED_ATTRIBUTES,
    STRUCTURAL_PREDICATES,
)

logger = logging.getLogger(__name__)

# Axis values (fixed enums).
FUNCTIONAL, SET_VALUED = "functional", "set_valued"
CONTAINMENT, LATERAL, NONE = "containment", "lateral", "none"
LAST_WRITE, ACCRUE = "last_write", "accrue"
# The fold of an attribute that declares no fold policy: by durability class,
# the fold every undeclared attribute always had (READ-SURFACE-V1 §2).
# Internal: never declarable.
BY_CLASS = "by_class"

ARITIES = frozenset({FUNCTIONAL, SET_VALUED})
RELATION_FAMILIES = frozenset({CONTAINMENT, LATERAL, NONE})
# The declarable fold policies (READ-SURFACE-V1 §2). `move` was recorded but
# never wired, and is removed: a `move` declaration skips at the gate and an
# old one in a log is ignored on read. The containment family's cross-source
# move rule (HD 002) is keyed on `relation_family`, as it always was.
FOLD_POLICIES = frozenset({LAST_WRITE, ACCRUE})
# The durability pin's classes (READ-SURFACE-V1 §1): the classifier's names,
# spelled here because the classifier imports this module. Never EVENT:
# occurrence stays structural (CLASSIFIER-EVENT-SAFETY-V1), and EVENT erases a
# row from every fold.
PINNABLE_DURABILITIES = frozenset({"CONSTITUTIVE", "DISPOSITIONAL", "STATE"})

# Each string axis's vocabulary, by reference (GATE-AUTHORITY-V1 §5).
_AXIS_VOCABULARIES = {
    "arity": ARITIES,
    "relation_family": RELATION_FAMILIES,
    "fold_policy": FOLD_POLICIES,
    "durability": PINNABLE_DURABILITIES,
}

# Attributes whose class a classifier guardrail fixes before a pin is read
# (READ-SURFACE-V1 §1): a pin on one could never take effect.
_GUARDRAILED = frozenset({"name", "alias"}) | META_ATTRIBUTES


# A kind named in a `resolvable_for` declaration: the id-safe name grammar (the
# id prefix's: lowercase letters, digits, underscore, led by a letter), so a
# kind is never free text and never fragments the way an aspect name would.
KIND_NAME_RE = re.compile(r"[a-z][a-z0-9_]*")


def valid_declaration(predicate: str, value: object) -> bool:
    """Whether a declared ``value`` is in ``predicate``'s axis vocabulary
    (GATE-AUTHORITY-V1 §5): ``arity`` ∈ ARITIES, ``relation_family`` ∈
    RELATION_FAMILIES, ``fold_policy`` ∈ FOLD_POLICIES, ``durability`` ∈
    PINNABLE_DURABILITIES (READ-SURFACE-V1 §1), ``structural`` a real bool,
    ``resolvable_for`` a kind name (RESOLVE-UNMARKED-V1). The gate validates
    every declaration it would write through this, and the read side ignores a
    declared value that fails it."""
    if predicate == "structural":
        return isinstance(value, bool)
    if predicate == "resolvable_for":
        return isinstance(value, str) and KIND_NAME_RE.fullmatch(value) is not None
    vocabulary = _AXIS_VOCABULARIES.get(predicate)
    return vocabulary is not None and isinstance(value, str) and value in vocabulary

# Built-in lateral graph attributes; everything set-valued that is not a graph
# edge is plain set data.
_LATERAL = frozenset({"connects_to", "adjacent_to"})

# Names with non-default built-in semantics. Family helpers below derive their
# seed sets through builtin_default() so behavioral constants are read in one
# place.
_BUILTIN_DEFAULT_ATTRIBUTES = frozenset(
    {
        "in",
        "within",
        "held_by",
        "worn_by",
        "carried_by",
        "name",
        "alias",
        "connects_to",
        "adjacent_to",
        "maybe_same_as",
        "same_as",
        "kind",
        "caused_by",
    }
)


@dataclass(frozen=True, slots=True)
class Semantics:
    """The orthogonal attribute-level axes. ``durability`` is the host's pin
    (READ-SURFACE-V1 §1): a declared class, or None when the rows are
    model-judged per row."""

    arity: str
    relation_family: str
    fold_policy: str
    structural: bool
    durability: str | None = None


def builtin_default(attribute: str) -> Semantics:
    """Today's behavior, as data — the default for any undeclared attribute.
    Its fold policy is the internal `by_class` (READ-SURFACE-V1 §2): the fold
    by durability class."""
    arity = SET_VALUED if attribute in SET_VALUED_ATTRIBUTES else FUNCTIONAL
    if attribute in CONTAINMENT_FAMILY:
        family = CONTAINMENT
    elif attribute in _LATERAL:
        family = LATERAL
    else:
        family = NONE
    return Semantics(arity, family, BY_CLASS, attribute in STRUCTURAL_PREDICATES)


class AttributeSemantics:
    """Per-world, rebuildable attribute-semantics view. Holds no truth (P2):
    the declarations live in the log as ``attr:*`` rows; this is their fold."""

    def __init__(self, buffer: PatternBuffer) -> None:
        self._buffer = buffer
        self._declared: dict[str, dict[str, object]] = {}
        # RESOLVE-UNMARKED-V1: `resolvable_for` is set-valued and apart from
        # the axes, so declaring it never makes an attribute "declared" (which
        # would silence its first-use hints and `attribute_default`).
        self._resolvable: dict[str, frozenset[str]] = {}
        # Memos over `_declared`, cleared with it on every rebuild: the resolved
        # per-attribute Semantics and the two family sets.
        self._resolved: dict[str, Semantics] = {}
        self._families: dict[str, frozenset[str]] = {}
        self._rebuilt_at = -1
        self.rebuild()

    def rebuild(self) -> None:
        """Scan visible ``attr:*`` declarations into the sidecar (parity with
        the canonicalization map and the durability sidecar)."""
        declared: dict[str, dict[str, object]] = {}
        resolvable: dict[str, set[str]] = {}
        for row in self._buffer.visible(entity_prefix=ATTR_PREFIX):
            if row.attribute not in SEMANTICS_PREDICATES:
                continue
            name = row.entity[len(ATTR_PREFIX):]
            if row.attribute == "resolvable_for":
                if (valid_declaration("resolvable_for", row.value)
                        and not self.is_unresolvable(name)):
                    resolvable.setdefault(name, set()).add(row.value)
                continue
            declared.setdefault(name, {})[row.attribute] = row.value
        self._declared = declared
        self._resolvable = {k: frozenset(v) for k, v in resolvable.items()}
        self._resolved = {}
        self._families = {}
        # Keyed on the buffer's log version, not its head: a rollback followed
        # by re-appends can return the head to a value this view was built at.
        self._rebuilt_at = self._buffer.log_version

    def _refresh(self) -> None:
        if self._buffer.log_version != self._rebuilt_at:
            self.rebuild()

    # ----------------------------------------------------------------- read

    def semantics(self, attribute: str) -> Semantics:
        """Declared semantics over the built-in default for one attribute."""
        self._refresh()
        resolved = self._resolved.get(attribute)
        if resolved is None:
            resolved = self._resolved[attribute] = self._overlay(attribute)
        return resolved

    def _overlay(self, attribute: str) -> Semantics:
        """The declared axes laid over the built-in default (unmemoized). A
        declared value outside its axis vocabulary is ignored and that axis
        keeps its built-in default (GATE-AUTHORITY-V1 §5) — only a real
        ``True`` is structural."""
        base = builtin_default(attribute)
        d = self._declared.get(attribute)
        if not d:
            return base

        def axis(predicate: str, default):
            value = d.get(predicate, default)
            return value if valid_declaration(predicate, value) else default

        return Semantics(
            arity=axis("arity", base.arity),
            relation_family=axis("relation_family", base.relation_family),
            fold_policy=axis("fold_policy", base.fold_policy),
            structural=axis("structural", base.structural),
            durability=axis("durability", base.durability),
        )

    def durability_pin(self, attribute: str) -> str | None:
        """The class the host pinned for `attribute` (READ-SURFACE-V1 §1), or
        None. The classifier reads it after its structural guardrails and
        before `structural` and the model; a pin on an attribute a guardrail
        decides first (`name`, `alias`, a META attribute) is never reached."""
        return self.semantics(attribute).durability

    def conflict(self, attribute: str,
                 declaration: dict[str, object]) -> tuple[str, str] | None:
        """The coherence check (READ-SURFACE-V1 §1): the first key of
        `declaration` that could never take effect, or that contradicts
        another declaration on `attribute` — one already in the log or
        another key of `declaration` itself — as ``(field, conflicts_with)``;
        None when the declaration is coherent. Every value is already in its
        axis vocabulary (`valid_declaration`). The gate skips an incoherent
        declaration `invalid_semantics_declaration`.

        - ``resolvable_for`` on an attribute that is never resolvable: the
          inviolable core, `name`, `alias` or a META attribute
          (RESOLVE-UNMARKED-V1; ``"core"``).
        - A pin on `name`, `alias` or a META attribute: a guardrail fixes
          their class before the pin is read (``"guardrail"``).
        - A pin other than CONSTITUTIVE beside ``structural: true``, in either
          order (``"structural=true"`` / ``"durability=<class>"``). Within one
          declaration the pin is the key refused.
        - ``fold_policy: last_write`` beside a set-valued arity or the
          containment family (§2), declared or built in, in either order
          (``"arity=set_valued"`` / ``"relation_family=containment"`` /
          ``"fold_policy=last_write"``). Within one declaration the fold
          policy is the key refused."""
        if "resolvable_for" in declaration and self.is_unresolvable(attribute):
            return "resolvable_for", "core"
        current = self.semantics(attribute)
        pin = declaration.get("durability")
        structural = declaration.get("structural", current.structural)
        if pin is not None:
            if attribute in _GUARDRAILED:
                return "durability", "guardrail"
            if pin != "CONSTITUTIVE" and structural is True:
                return "durability", "structural=true"
        elif (declaration.get("structural") is True
              and current.durability not in (None, "CONSTITUTIVE")):
            return "structural", f"durability={current.durability}"
        arity = declaration.get("arity", current.arity)
        family = declaration.get("relation_family", current.relation_family)
        if declaration.get("fold_policy") == LAST_WRITE:
            if arity == SET_VALUED:
                return "fold_policy", f"arity={SET_VALUED}"
            if family == CONTAINMENT:
                return "fold_policy", f"relation_family={CONTAINMENT}"
        elif current.fold_policy == LAST_WRITE:
            if declaration.get("arity") == SET_VALUED:
                return "arity", f"fold_policy={LAST_WRITE}"
            if declaration.get("relation_family") == CONTAINMENT:
                return "relation_family", f"fold_policy={LAST_WRITE}"
        return None

    def is_set_valued(self, attribute: str) -> bool:
        return self.semantics(attribute).arity == SET_VALUED

    def is_containment(self, attribute: str) -> bool:
        return self.semantics(attribute).relation_family == CONTAINMENT

    def is_lateral(self, attribute: str) -> bool:
        return self.semantics(attribute).relation_family == LATERAL

    def is_accrue(self, attribute: str) -> bool:
        return self.semantics(attribute).fold_policy == ACCRUE

    def is_last_write(self, attribute: str) -> bool:
        """Declared `fold_policy: last_write` on a functional attribute outside
        the containment family (READ-SURFACE-V1 §2): the fold serves the latest
        row of the top evidence rank, whatever its durability. If a log
        carries the pair anyway, set-valued and containment win."""
        s = self.semantics(attribute)
        return (s.fold_policy == LAST_WRITE and s.arity != SET_VALUED
                and s.relation_family != CONTAINMENT)

    def is_structural(self, attribute: str) -> bool:
        return self.semantics(attribute).structural

    def resolvable_kinds(self, aspect: str) -> frozenset[str]:
        """The kinds the resolver may invent `aspect` for (RESOLVE-UNMARKED-V1):
        the visible ``attr:<aspect> · resolvable_for · <kind>`` rows, empty
        when none. A value outside the kind grammar, or on an attribute that
        can never be resolvable, is ignored on read."""
        self._refresh()
        return self._resolvable.get(aspect, frozenset())

    def has_resolvable(self) -> bool:
        """Whether the world declares any aspect resolvable: the opt-in that
        RESOLVE-UNMARKED-V1 keys the ``undeclared`` answer on."""
        self._refresh()
        return bool(self._resolvable)

    @staticmethod
    def is_unresolvable(attribute: str) -> bool:
        """An attribute that can never be declared resolvable: the inviolable
        core and the guardrailed names (`name`, `alias`, META attributes).
        `contents` is none of these, and is declarable."""
        return attribute in INVIOLABLE_CORE or attribute in _GUARDRAILED

    def is_declared(self, attribute: str) -> bool:
        """Whether an explicit ``attr:*`` declaration exists (vs. defaulting)."""
        self._refresh()
        return attribute in self._declared

    def containment_family(self) -> set[str]:
        """All attributes that fold as the single containment key — the
        built-in family plus any declared ``relation_family=containment``."""
        return self._family(CONTAINMENT)

    def lateral_family(self) -> set[str]:
        """All attributes that form the lateral graph (``path``)."""
        return self._family(LATERAL)

    def _family(self, relation_family: str) -> set[str]:
        """The built-in members of one relation family plus every declared
        member — memoized per view; each caller gets its own copy."""
        self._refresh()
        members = self._families.get(relation_family)
        if members is None:
            out = {
                name for name in _BUILTIN_DEFAULT_ATTRIBUTES
                if builtin_default(name).relation_family == relation_family
            }
            for name in self._declared:
                if self.semantics(name).relation_family == relation_family:
                    out.add(name)
            members = self._families[relation_family] = frozenset(out)
        return set(members)

    # ------------------------------------------------------------- authority

    @staticmethod
    def is_core(attribute: str) -> bool:
        """A constitutional predicate that can never be redeclared (spec §5)."""
        return attribute in INVIOLABLE_CORE
