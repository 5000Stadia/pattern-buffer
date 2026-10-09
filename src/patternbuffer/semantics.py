"""Attribute semantics as data (ATTRIBUTE-SEMANTICS-V1).

Attribute-level *behavior* — arity (functional vs set-valued), relation
family (containment tree / lateral graph / none), fold policy (last-write
vs move-supersession), structural-ness, and the host's durability pin
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
LAST_WRITE, MOVE, ACCRUE = "last_write", "move", "accrue"

ARITIES = frozenset({FUNCTIONAL, SET_VALUED})
RELATION_FAMILIES = frozenset({CONTAINMENT, LATERAL, NONE})
FOLD_POLICIES = frozenset({LAST_WRITE, MOVE, ACCRUE})
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


def valid_declaration(predicate: str, value: object) -> bool:
    """Whether a declared ``value`` is in ``predicate``'s axis vocabulary
    (GATE-AUTHORITY-V1 §5): ``arity`` ∈ ARITIES, ``relation_family`` ∈
    RELATION_FAMILIES, ``fold_policy`` ∈ FOLD_POLICIES, ``durability`` ∈
    PINNABLE_DURABILITIES (READ-SURFACE-V1 §1), ``structural`` a real bool.
    The gate validates every declaration it would write through this, and the
    read side ignores a declared value that fails it."""
    if predicate == "structural":
        return isinstance(value, bool)
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
    """Today's behavior, as data — the default for any undeclared attribute."""
    arity = SET_VALUED if attribute in SET_VALUED_ATTRIBUTES else FUNCTIONAL
    if attribute in CONTAINMENT_FAMILY:
        family, policy = CONTAINMENT, MOVE
    elif attribute in _LATERAL:
        family, policy = LATERAL, LAST_WRITE
    else:
        family, policy = NONE, LAST_WRITE
    return Semantics(arity, family, policy, attribute in STRUCTURAL_PREDICATES)


class AttributeSemantics:
    """Per-world, rebuildable attribute-semantics view. Holds no truth (P2):
    the declarations live in the log as ``attr:*`` rows; this is their fold."""

    def __init__(self, buffer: PatternBuffer) -> None:
        self._buffer = buffer
        self._declared: dict[str, dict[str, object]] = {}
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
        for row in self._buffer.visible(entity_prefix=ATTR_PREFIX):
            if row.attribute in SEMANTICS_PREDICATES:
                name = row.entity[len(ATTR_PREFIX):]
                declared.setdefault(name, {})[row.attribute] = row.value
        self._declared = declared
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

        - A pin on `name`, `alias` or a META attribute: a guardrail fixes
          their class before the pin is read (``"guardrail"``).
        - A pin other than CONSTITUTIVE beside ``structural: true``, in either
          order (``"structural=true"`` / ``"durability=<class>"``). Within one
          declaration the pin is the key refused."""
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
        return None

    def is_set_valued(self, attribute: str) -> bool:
        return self.semantics(attribute).arity == SET_VALUED

    def is_containment(self, attribute: str) -> bool:
        return self.semantics(attribute).relation_family == CONTAINMENT

    def is_lateral(self, attribute: str) -> bool:
        return self.semantics(attribute).relation_family == LATERAL

    def is_accrue(self, attribute: str) -> bool:
        return self.semantics(attribute).fold_policy == ACCRUE

    def is_structural(self, attribute: str) -> bool:
        return self.semantics(attribute).structural

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
