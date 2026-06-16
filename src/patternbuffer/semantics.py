"""Attribute semantics as data (ATTRIBUTE-SEMANTICS-V1).

Attribute-level *behavior* — arity (functional vs set-valued), relation
family (containment tree / lateral graph / none), fold policy (last-write
vs move-supersession), and structural-ness — lifted out of the engine's
code constants into per-world, rebuildable, *declared* semantics that every
consumer reads through this one service. Domain vocabulary carries its own
fold behavior without engine edits.

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
    CONTAINMENT_FAMILY,
    SET_VALUED_ATTRIBUTES,
    STRUCTURAL_PREDICATES,
)

logger = logging.getLogger(__name__)

# Axis values (fixed enums).
FUNCTIONAL, SET_VALUED = "functional", "set_valued"
CONTAINMENT, LATERAL, NONE = "containment", "lateral", "none"
LAST_WRITE, MOVE = "last_write", "move"

ARITIES = frozenset({FUNCTIONAL, SET_VALUED})
RELATION_FAMILIES = frozenset({CONTAINMENT, LATERAL, NONE})
FOLD_POLICIES = frozenset({LAST_WRITE, MOVE})

# The metadata predicates, asserted on ``attr:<name>`` entities.
ATTR_PREFIX = "attr:"
SEMANTICS_PREDICATES = frozenset({"arity", "relation_family", "fold_policy", "structural"})

# Built-in lateral graph attributes (the rest of CONTAINMENT_FAMILY is the
# tree; everything in SET_VALUED that isn't a graph edge is plain set data).
_LATERAL = frozenset({"connects_to", "adjacent_to"})

# The constitutional core a host may never redeclare (spec §5). Structural
# predicates already cover the containment family + kind/connects_to/
# adjacent_to/caused_by; identity predicates are added explicitly.
INVIOLABLE_CORE = STRUCTURAL_PREDICATES | {"same_as", "maybe_same_as"}


@dataclass(frozen=True, slots=True)
class Semantics:
    """The four orthogonal attribute-level axes."""

    arity: str
    relation_family: str
    fold_policy: str
    structural: bool


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

    # ----------------------------------------------------------------- read

    def semantics(self, attribute: str) -> Semantics:
        """Declared semantics over the built-in default for one attribute."""
        base = builtin_default(attribute)
        d = self._declared.get(attribute)
        if not d:
            return base
        return Semantics(
            arity=str(d.get("arity", base.arity)),
            relation_family=str(d.get("relation_family", base.relation_family)),
            fold_policy=str(d.get("fold_policy", base.fold_policy)),
            structural=bool(d.get("structural", base.structural)),
        )

    def is_set_valued(self, attribute: str) -> bool:
        return self.semantics(attribute).arity == SET_VALUED

    def is_containment(self, attribute: str) -> bool:
        return self.semantics(attribute).relation_family == CONTAINMENT

    def is_lateral(self, attribute: str) -> bool:
        return self.semantics(attribute).relation_family == LATERAL

    def is_structural(self, attribute: str) -> bool:
        return self.semantics(attribute).structural

    def is_declared(self, attribute: str) -> bool:
        """Whether an explicit ``attr:*`` declaration exists (vs. defaulting)."""
        return attribute in self._declared

    def containment_family(self) -> set[str]:
        """All attributes that fold as the single containment key — the
        built-in family plus any declared ``relation_family=containment``."""
        out = set(CONTAINMENT_FAMILY)
        for name in self._declared:
            if self.semantics(name).relation_family == CONTAINMENT:
                out.add(name)
        return out

    def lateral_family(self) -> set[str]:
        """All attributes that form the lateral graph (``path``)."""
        out = set(_LATERAL)
        for name in self._declared:
            if self.semantics(name).relation_family == LATERAL:
                out.add(name)
        return out

    # ------------------------------------------------------------- authority

    @staticmethod
    def is_core(attribute: str) -> bool:
        """A constitutional predicate that can never be redeclared (spec §5)."""
        return attribute in INVIOLABLE_CORE
