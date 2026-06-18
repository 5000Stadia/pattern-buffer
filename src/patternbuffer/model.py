"""The assertion row shape and the engine's fixed vocabularies.

The model is triples-on-triples: assertions are addressable entities,
so everything *about* an assertion is itself an assertion. Hot fields
are denormalized into columns (whitepaper §3.2); nothing is ever
special-cased.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Provenance vocabulary (whitepaper §7). `default` appears only in
# materialization payloads; it is included here because the renderer-
# facing payload reuses the vocabulary, but no role may append it.
STATUSES = frozenset(
    {"stated", "observed", "inferred", "assumed", "generated", "default", "retracted"}
)

# The containment family folds as ONE logical key (spec §7, letter 002
# Q1): a new family edge supersedes the prior one as a single operation.
CONTAINMENT_FAMILY = frozenset({"in", "within", "held_by", "worn_by", "carried_by"})

# Fixed structural predicates (spec §4.3). Domain vocabulary emerges
# freely through the canonicalization gate; these never do.
STRUCTURAL_PREDICATES = (
    frozenset({"kind", "connects_to", "adjacent_to", "caused_by"}) | CONTAINMENT_FAMILY
)

# Attribute-semantics declarations are assertions about attr:<name> entities.
# These low-level names live here so the buffer guard can enforce authority
# without importing the semantics service.
ATTR_PREFIX = "attr:"
SEMANTICS_PREDICATES = frozenset(
    {"arity", "relation_family", "fold_policy", "structural"}
)
INVIOLABLE_CORE = STRUCTURAL_PREDICATES | {"same_as", "maybe_same_as", "distinct_from"}

# The engine's own meta-attributes (subjects of these rows are assertion
# ids or carry engine semantics).
META_ATTRIBUTES = frozenset(
    {
        "superseded_by",
        "retracts",
        "source",
        "same_as",
        "maybe_same_as",
        "distinct_from",
        "canonicalized_from",
        "resolved_by",
        "justified_by",
        "world_defining",
        "correction_proposal",
    }
) | SEMANTICS_PREDICATES

# Set-valued attributes: multiple coexisting values are data, never a
# contradiction — a conflict requires a functional key (run-4 finding:
# 62 of 77 flags were names/aliases/edges misread as disputes).
SET_VALUED_ATTRIBUTES = frozenset({"name", "alias", "connects_to", "adjacent_to",
                                   "maybe_same_as", "same_as", "distinct_from"})

VALUE_TYPES = frozenset({"entity", "literal", "unresolved", "delta"})

CANON = "canon"


@dataclass(frozen=True, slots=True)
class Assertion:
    """One fact. Append-only; never edited (whitepaper §3.2).

    ``valid_from``/``valid_to`` are world time (None = timeless, legal
    only for CONSTITUTIVE/DISPOSITIONAL rows — enforced at the gate, not
    here). ``asserted_at`` is transaction time: the log sequence number,
    permanently (spec §4.2).
    """

    seq: int
    id: str
    world_id: str
    entity: str
    attribute: str
    value_type: str
    value: Any
    valid_from: float | None
    valid_to: float | None
    frame: str
    status: str
    confidence: float | None
    asserted_at: int
