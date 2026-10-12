"""The assertion row shape and the engine's fixed vocabularies.

The model is triples-on-triples: assertions are addressable entities,
so everything *about* an assertion is itself an assertion. Hot fields
are denormalized into columns (whitepaper §3.2); nothing is ever
special-cased.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from types import MappingProxyType
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

# The compositional axis (PLACE-FEATURE-ABSTRACTION-V1): structural part-of-the-
# whole, distinct from movable containment. A burrow is `part_of` a hillside;
# an actor in the burrow is NOT thereby located in the hillside. Read by
# composition()/features(), never by locate()/contents()/route().
COMPOSITION_FAMILY = frozenset({"part_of"})

# Fixed structural predicates (spec §4.3). Domain vocabulary emerges
# freely through the canonicalization gate; these never do.
STRUCTURAL_PREDICATES = (
    frozenset({"kind", "connects_to", "adjacent_to", "caused_by"})
    | CONTAINMENT_FAMILY | COMPOSITION_FAMILY
)

# Attribute-semantics declarations are assertions about attr:<name> entities.
# These low-level names live here so the buffer guard can enforce authority
# without importing the semantics service.
ATTR_PREFIX = "attr:"
# `durability` is the host's durability pin (READ-SURFACE-V1 §1): a declared
# class for its own attribute, read by the classifier before the model.
# `resolvable_for` (RESOLVE-UNMARKED-V1) is set-valued, one row per kind, and
# never folds: it declares which kinds of entity the resolver may invent that
# aspect for.
SEMANTICS_PREDICATES = frozenset(
    {"arity", "relation_family", "fold_policy", "structural", "durability",
     "resolvable_for"}
)
# FRAME-CONTINUITY-V1 §3: the host's declaration that one observer's knowledge
# is part of another's, written only by `continue_frame` (or a host's structured
# canon item) and never by prose extraction. A host cannot redeclare it.
FRAME_CONTINUES_AS = "frame_continues_as"
INVIOLABLE_CORE = (STRUCTURAL_PREDICATES
                   | {"same_as", "maybe_same_as", "distinct_from", "aka",
                      FRAME_CONTINUES_AS})

# FRAME-CONTINUITY-V1 §2: a frame selector is one stored frame name, or the
# tuple of stored frames a wider `frame_scope` resolved to (read as an `IN`).
FrameSel = str | tuple[str, ...]
FRAME_SCOPES = ("exact", "continued", "merged")
KNOWS_PREFIX = "knows:"

# The resolution policies — the world's one switch (whitepaper §8). Defined
# here so the buffer can validate the physics row without importing the
# resolver; `thunks` re-exports them.
INVENT_UNDER_CANON = "invent_under_canon"
OBSERVE_OR_UNKNOWN = "observe_or_unknown"
DENY = "deny"
POLICIES = frozenset({INVENT_UNDER_CANON, OBSERVE_OR_UNKNOWN, DENY})

# The world's physics row (READ-SURFACE-V1 §7): `attr:__world__ ·
# resolution_policy · <policy>`, canon, timeless, stated, CONSTITUTIVE, written
# once by World and immutable after. `attr:__world__` already carries the
# world's decay default (TRACKING-MODE-V1), so a world's physics live together,
# outside every world-fact read (`attr:` subjects are excluded everywhere).
WORLD_PHYSICS_SUBJECT = "attr:__world__"
RESOLUTION_POLICY = "resolution_policy"

# The canon identity edges (FRAME-SCOPED-IDENTITY-V1): the rows that make,
# propose or forbid a merge. Identity is canon's — which ids are one thing is
# one fact about the world, not a belief — so these are written and read in
# canon only. `aka` is not among them: a perspectival identity belief ("Alice
# thinks the masked man is Bob") stays an `aka` row in its own frame.
CANON_IDENTITY_EDGES = frozenset({"same_as", "maybe_same_as", "distinct_from",
                                  FRAME_CONTINUES_AS})

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
        "aka",
        FRAME_CONTINUES_AS,  # FRAME-CONTINUITY-V1 §3: identity-adjacent canon structure
        "canonicalized_from",
        "resolved_by",
        "justified_by",
        "world_defining",
        "correction_proposal",
        "source_valid_from",  # INGEST-LATENCY-V2: demoted cursor-authoritative coord
        # REFER-LEARNING-V1 §2: refer's memory of words — timeless bookkeeping
        # like same_as/aka, never identity: EVENT by the classifier guardrail,
        # so it never folds, stands as a fact, or counts as an unstamped row.
        "learned_alias",
        # Four of the five semantics predicates, listed by name (READ-SURFACE-V1
        # §1). The fifth, `durability`, is an ordinary domain word too (a
        # sword's durability), and a META attribute is erased from every fold.
        # A semantics predicate means something only on an `attr:` subject;
        # the classifier's own step keeps the pin row model-free.
        "arity",
        "relation_family",
        "fold_policy",
        "structural",
    }
)

# Mechanism attributes (GATE-AUTHORITY-V1 §1): rows the engine writes about
# OTHER rows. Each has exactly one owning engine component and is recognized by
# that owner's mark, never by its name alone — the gate never accepts one as an
# item, the buffer refuses the wrong status on append, and readers honor only
# the owner's mark. One read-only definition shared by the buffer, the readers
# and the gate.
# - `retracts` hides its target (truth maintenance, `retracted`).
# - `resolved_by` spends a thunk and names its memo (the resolver, `generated`).
# - `decided_by` records who decided an identity merge (IDENTITY-ROOT-CAUSES-V1
#   §3): the identity registry writes it on the `identity_merge` event, with
#   status `inferred`, and readers honor it only there.
# - `representative` names the id a host merge wants its closure served under
#   (IDENTITY-REPRESENTATIVE-V1 §1): the identity registry writes it on a
#   host-decided `identity_merge` event, with status `inferred`, and the
#   election honours it only there.
# - `learned_at_wallclock` is the tracking-mode confirmation stamp that
#   confidence() recency reads (the gate's A1 rider, `observed`; r2).
# - `canonicalized_from` is replayed into the attribute-alias map on open (the
#   gate's own receipt: `inferred`, on an assertion whose attribute is the
#   receipt's target — a structural mark, so it has no single status here).
# - `source_valid_from` (the cursor-authoritative demotion) and
#   `correction_proposal` (the `correction` field's proposal) are the gate's
#   own records of what it did to an item; no engine read consumes them, so
#   they carry no status mark here, but a copied row would misstate them and
#   a host promoting corrections acts on the latter (r2).
MECHANISM_STATUS = MappingProxyType({
    "retracts": "retracted",
    "resolved_by": "generated",
    "learned_at_wallclock": "observed",
    "decided_by": "inferred",
    "representative": "inferred",
})
MECHANISM_ATTRIBUTES = frozenset(MECHANISM_STATUS) | {
    "canonicalized_from", "source_valid_from", "correction_proposal"}

# Set-valued attributes: multiple coexisting values are data, never a
# contradiction — a conflict requires a functional key (run-4 finding:
# 62 of 77 flags were names/aliases/edges misread as disputes).
SET_VALUED_ATTRIBUTES = frozenset({"name", "alias", "connects_to", "adjacent_to",
                                   "maybe_same_as", "same_as", "distinct_from", "aka"})

VALUE_TYPES = frozenset({"entity", "literal", "unresolved", "delta"})

CANON = "canon"

# Reified occurrences (whitepaper §3.1, §12 `event(...)`): an `event:` id is an
# entity whose rows are its record (EVENTS-ONE-READER-V1).
EVENT_PREFIX = "event:"

# The id grammar (SHAPE-FIX-V1 4a): namespaced snake_case, no stray slashes.
# A malformed id (person:/you) is SKIPPED at the gate with a typed receipt,
# never normalized — guessing person:you would manufacture the phantom
# well-formed. One definition for the gate and the porcelain.
ID_RE = re.compile(r"^[a-z][a-z0-9_]*:[a-z0-9_:]+$")

# A value that LOOKS like an id (GATE-AUTHORITY-V1 §7): a letter-led word, a
# colon, and no whitespace right after it — `Place:Cellar`, `place:/cellar`,
# `place:the cellar`, `place:`; never `repaired: the rival arrives`, `12:30`
# or `a drawer at home`. Matched from the start of the value.
ID_SHAPED_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*:(?!\s)")

# An assertion id, as the buffer mints them (`a:<seq>`) — GATE-AUTHORITY-V1 §8.
# A host id merely shaped like the namespace (`a:artifact`) is not one.
ASSERTION_ID_RE = re.compile(r"^a:[0-9]+$")

# Model task keys. Every schema the engine hands the injected model callable
# carries one of these as its JSON-Schema `title`, so a host can route a call
# (to a cheaper tier, a stricter validator) by what the call is for. The
# titles are frozen; prompt wording is not a contract and may change.
TASK_EXTRACT = "patternbuffer_extract"
TASK_CLASSIFY = "patternbuffer_classify"
TASK_CLASSIFY_BATCH = "patternbuffer_classify_batch"
TASK_RESOLVE = "patternbuffer_resolve"
TASK_REFER = "patternbuffer_refer"
TASK_ASK_PLAN = "patternbuffer_ask_plan"
MODEL_TASKS = frozenset({TASK_EXTRACT, TASK_CLASSIFY, TASK_CLASSIFY_BATCH,
                         TASK_RESOLVE, TASK_REFER, TASK_ASK_PLAN})


@dataclass(frozen=True, slots=True)
class ResolveRequest:
    """What a `patternbuffer_resolve` call is for, as data (RESOLVE-REQUEST-V1).

    A generator that answers by code (a seeded sampler, a layout generator)
    reads this instead of parsing the prompt. ``inherited`` holds the standing
    facts of the entity and its containment ancestors, as
    ``(holder, attribute, value)``; ``declared`` holds the placeholder's own
    constraint strings. Together they are exactly the prompt's constraint
    lines, in the same order."""

    world_id: str
    entity: str
    aspect: str
    kind: Any
    inherited: tuple[tuple[str, str, Any], ...]
    declared: tuple[str, ...]
    as_of: float | None
    frame: str
    policy: str


class TaskSchema(dict):
    """A task schema that also carries its call's structured request
    (RESOLVE-REQUEST-V1). It is a dict with the same keys and values as the
    plain schema, so it serializes byte-identically and every adapter that
    forwards it to a model sends exactly what it sent before. Only a generator
    that asks for ``task_request(schema)`` sees the request."""

    request: Any = None


def task_schema(schema: dict[str, Any], request: Any = None) -> dict[str, Any]:
    """A private copy of a task schema for one model call: an adapter that
    edits the schema in place (strict-mode rewrites) cannot corrupt the
    engine's shared definition for every later call. With ``request``, the
    copy is a `TaskSchema` carrying it."""
    if request is None:
        return copy.deepcopy(schema)
    out = TaskSchema(copy.deepcopy(schema))
    out.request = request
    return out


def task_request(schema: Any) -> Any:
    """The structured request a model call carries, or None
    (RESOLVE-REQUEST-V1): a `ResolveRequest` on a `patternbuffer_resolve`
    call, None on every other call and on a schema an adapter rebuilt."""
    return getattr(schema, "request", None) if isinstance(schema, TaskSchema) else None


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


def is_event_row(row: Assertion) -> bool:
    """Whether `row` is an event row (EVENTS-ONE-READER-V1 §1): its stored
    subject is an `event:` id and its value type is not `delta`.

    Exactly the rows the classifier's guardrail makes EVENT because of their
    subject — a `delta` is decided first, and is STATE, so an accrue ledger
    entry on an event still folds. The one predicate the guardrail, the fold
    (which never folds an event row, classified or not) and the event reader
    (`Indexes.event_records`) share."""
    return row.entity.startswith(EVENT_PREFIX) and row.value_type != "delta"
