"""The ingest gate (whitepaper §10/§17): the ONLY path for stated truth.

Pipeline per item: canonicalize the attribute (receipts in the log, map
in a rebuildable sidecar) -> identity-resolve -> stamp valid_time from
the scene cursor -> role-checked append -> classify. The scene cursor is
the pose; anchoring never claims more precision than was observed. The
full check order is GATE-AUTHORITY-V1 §0's (see `_ingest_item`): authority
is settled before an item's first write, and every refusal that is not an
authority violation is a typed skip receipt (`SKIP_REASONS`).

A2 rider (whitepaper amendment log): in observe_or_unknown worlds the
gate stamps a wall-clock learned-at meta-assertion on every non-timeless
write — staleness decay computes from real time and silently breaks
without it.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Callable

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import Classifier
from patternbuffer.codec import decode_value, encode_out
from patternbuffer.identity import IdentityRegistry
from patternbuffer.model import (
    ATTR_PREFIX,
    CANON,
    COMPOSITION_FAMILY,
    ID_RE,
    ID_SHAPED_RE,
    MECHANISM_ATTRIBUTES,
    SEMANTICS_PREDICATES,
    TASK_EXTRACT,
    VALUE_TYPES,
    Assertion,
    task_schema,
)
from patternbuffer.roles import RoleViolation, WriterRole
from patternbuffer.semantics import AttributeSemantics, valid_declaration
from patternbuffer.tmaint import AtomicAbort

logger = logging.getLogger(__name__)


class _GateSkip(Exception):
    """Internal signal (ATOMIC-ACTIVATION-V1 §B2): a receipt-and-continue skip
    occurred inside an atomic set — carries the skip records so the envelope can
    raise ``AtomicAbort(cause="gate_skip")`` after rollback. Never escapes the
    ingestor."""

    def __init__(self, skipped: list) -> None:
        self.skipped = skipped
        super().__init__(f"{len(skipped)} gate skip(s) aborted the atomic set")

# The id grammar (SHAPE-FIX-V1 4a) is `model.ID_RE`, shared with the porcelain.

# GATE-INVERSE-ALIAS-V1 §2/§4: an inverse-swap receipt is "(inverse) holds->held_by".
# The marker comes FIRST so an engine that predates the swap (which replays every
# `src->dst` receipt as an alias, splitting on the first "->") reads the source as
# "(inverse) holds" — an attribute that never occurs — and installs nothing.
_INVERSE_RECEIPT_PREFIX = "(inverse)"

# Entity-valued predicates beyond the containment and lateral families
# (GATE-AUTHORITY-V1 §7): their engine readers only ever see entity values.
# `same_as` is not here — a raw same_as is a guarded merge (§2).
_ENTITY_VALUED = COMPOSITION_FAMILY | {"caused_by", "maybe_same_as", "distinct_from", "aka"}

# Built-in attribute aliases: the fold key must never fragment. Domain
# vocabulary emerges freely; these structural repairs are fixed.
_BUILTIN_ALIASES = {
    "inside": "in",
    "located_in": "in",
    "location": "in",
    "contained_in": "in",
    "connected_to": "connects_to",
    "adjacent": "adjacent_to",
    "feature_of": "part_of",      # compositional axis (PLACE-FEATURE-ABSTRACTION-V1)
    "component_of": "part_of",
    "type": "kind",
    "is_a": "kind",
}

# GATE-INVERSE-ALIAS-V1 §1: INVERSE relations — the forward form names the same
# fact with subject and object exchanged, so a rename alone would invert the
# containment edge. These are applied only by the entity-value swap in
# `_ingest_item` (§2); a text value keeps the attribute as authored (§3).
_BUILTIN_INVERSE_ALIASES = {
    "holds": "held_by",
    "wearing": "worn_by",
}

_EXTRACT_SCHEMA = {
    "title": TASK_EXTRACT,
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "attribute": {"type": "string"},
                    "value": {},
                    "value_type": {"enum": ["entity", "literal", "unresolved", "delta"]},
                    "frame": {"type": "string"},
                    "status": {"enum": ["stated", "observed", "inferred", "assumed"]},
                    "timeless": {"type": "boolean"},
                    "valid_from": {"type": ["number", "null"]},
                    # MOVED-EVENT-V1 §B.1: valid_to is consumed at the gate but
                    # was undeclared (permissive tolerance is not a contract).
                    "valid_to": {"type": ["number", "null"]},
                    # MOVED-EVENT-V1 §B.1/§A: the movement completion marker is
                    # a first-class item field on the kind=moved item only —
                    # boolean-only (a null marker fails the group closed, §B.4),
                    # never a durable `complete` attribute row.
                    "complete": {"type": "boolean"},
                    "confidence": {"type": ["number", "null"]},
                    "source_doc": {"type": ["string", "null"]},
                    "caused_by": {"type": ["string", "null"]},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "same_as": {"type": ["string", "null"]},
                    "correction": {"type": "boolean"},
                },
                "required": ["entity", "attribute", "value"],
            },
        }
    },
    "required": ["items"],
}

# The extraction rules block (HD 082). `full` is the complete contract; `lean`
# (opt-in via ingest(extract="lean")) keeps the LOAD-BEARING rules — id
# namespacing, the `in`/`connects_to`/`kind` canonicalization, value_type, the
# canon-vs-knows: frame discipline, aliases, timeless, never-invent — and drops
# the rarely-needed-per-turn ones (document-claims/source_doc, the
# overturned-belief status nuance, the habits/catchphrases enumeration) to trim
# input tokens for the hot per-turn render extraction. NOTE: a ~30s extraction is
# dominated by OUTPUT generation (item count), not this block — so lean is a
# marginal input-side lever; the structural cut is extracting fewer items
# (delta/scoped extraction). Quality must be eval-guarded before enabling.
_EXTRACT_RULES_FULL = (
    "Extract world-state assertions from this narrative passage.\n"
    "Return triples (entity, attribute, value). Rules:\n"
    "- entity ids namespaced: person:/place:/obj:/event:/doc: + snake_case.\n"
    "- attributes: use 'in' for where a thing or person is (a place or a "
    "container); 'connects_to' for passage; 'kind' for what a thing is; domain "
    "attributes freely otherwise.\n"
    "- an object physically held or carried is '<thing> held_by <person>', and "
    "a garment worn is '<garment> worn_by <person>' (not 'in', and never with "
    "the person as the subject).\n"
    "- value_type 'entity' when the value is another entity id.\n"
    "- MOVEMENT: when the text narrates a person actually leaving or arriving "
    "at a place (goes out, slips away, comes in, arrives, departs, walks/rides/"
    "drives from A to B), ALSO emit an event with a FRESH UNIQUE id of the form "
    "'event:<short-occurrence-slug>' — a new id for every distinct movement, "
    "never reused — with these attributes, all sharing the one id: kind=moved; "
    "agent=<person id>; origin=<place> and/or destination=<place> exactly as the "
    "text gives them (a bound place is its entity id; a named-but-unregistered "
    "place is that name as a plain string with value_type=literal; an unnamed "
    "end is simply absent); manner=<the verb's own mode: walk/run/crawl/ride/"
    "drive/fly/swim> when the verb says it. Use exactly the keys agent, origin, "
    "destination, manner — not actor, from, to, source, target, mode. Do NOT "
    "emit valid_from or valid_to for a movement — the engine stamps the "
    "timeline; a number invented from prose ('that evening') is forbidden. "
    "Instead put a single boolean field 'complete' on the kind=moved item: "
    "complete=true when the SAME passage narrates the finished arrival, "
    "complete=false when only the departure is narrated. A bound destination "
    "whose arrival is narrated (complete=true) also gets its ordinary 'in' row "
    "(no timestamp on it either). Only actual displacement by a person is "
    "movement: intent or facing ('turned toward the door', 'keeps to the "
    "threshold'), preparation ('takes up the pails'), moving atmosphere (air, "
    "rain, light), and repositioning within the same place are NOT moved "
    "events.\n"
    "- FRAMES: facts about the world are frame 'canon' — even facts revealed "
    "late or learned by a character mid-story; give them their TRUE historical "
    "valid_from. Use frame 'knows:<person_id>' ONLY for the additional fact "
    "that a character has learned something (a copy marking knowledge), never "
    "instead of the canon row. When character A tells character B an "
    "already-established fact, emit knows:B rows for it — no new canon rows.\n"
    "- status: 'stated' for asserted fact, 'inferred' for a character's "
    "deduction, 'assumed' for a working theory not yet confirmed. When the "
    "story later overturns an earlier belief or official verdict, close it "
    "with valid_to at the time it was overturned.\n"
    "- DOCUMENT CLAIMS (letters, ledgers, logs): emit the claimed fact with "
    "source_doc=<doc id>. Approximate quantities as bounds: 'over forty "
    "thousand' -> {\"gte\": 40000}. When a later source confirms or refines "
    "the SAME fact, use the SAME entity and attribute so the records converge.\n"
    "- ALIASES: attach every referring expression used for an entity as "
    "aliases (e.g. 'the clerk with the tin ear', 'the vault'). When a "
    "previously-seen entity gains a name, keep its id and add the name; if "
    "you minted a duplicate id for the same individual, emit same_as.\n"
    "- SPACE: emit connects_to edges for every passage/route the text "
    "describes (stairs, gates, corridors); never invent an edge the text "
    "does not support — vertical proximity is not connectivity.\n"
    "- TIME: timeless=true ONLY for what holds across the world's whole "
    "history: identity/structure (kind, names, fixed adjacency) and facts of "
    "origin (kinship of origin, innate traits presented as what the person "
    "has always been). Everything acquired or mutable gets valid_from — a "
    "dated onset when the text gives one ('became a soldier at the war'); "
    "otherwise the earliest supported point (the entity's introduction or "
    "the scene cursor). Time-relative quantities (age) are current state at "
    "the cursor, never timeless. Standing-but-acquired properties "
    "(occupation, scars, learned skills) are NOT timeless — stamp them at "
    "their earliest supported time.\n"
    "- Repeated habits, spoken catchphrases, confrontations, confessions, "
    "and scheduled/conditional future events are assertions too (use event: "
    "entities with caused_by where the text gives causality).\n"
    "- NEVER invent: extract only what the text supports. Atmosphere and "
    "sensory texture are not assertions.\n"
    "- The narrative voice is not an entity: never emit person: entities for "
    "the narrator, an unnamed speaker, or the audience. Never mint a person "
    "from a bare pronoun; if a pronoun's referent is unknown, skip that "
    "assertion.\n"
)
_EXTRACT_RULES_LEAN = (
    "Extract world-state assertions from this narrative passage.\n"
    "Return triples (entity, attribute, value). Rules:\n"
    "- entity ids namespaced: person:/place:/obj:/event: + snake_case.\n"
    "- attributes: 'in' for where a thing or person is (a place or a "
    "container); 'connects_to' for passage; 'kind' for what a thing is; domain "
    "attributes otherwise.\n"
    "- an object physically held or carried is '<thing> held_by <person>', and "
    "a garment worn is '<garment> worn_by <person>' (not 'in', and never with "
    "the person as the subject).\n"
    "- value_type 'entity' when the value is another entity id.\n"
    "- FRAMES: world facts are frame 'canon' (give their true historical "
    "valid_from even if revealed late); use 'knows:<person_id>' ONLY for the "
    "extra fact that a character learned something, never instead of canon.\n"
    "- aliases: attach referring expressions used for an entity.\n"
    "- ALWAYS extract location changes: X moves/leaves/arrives => a new 'in' "
    "row for X. Presence and departure are core state, never atmosphere "
    "(a departure that goes unrecorded makes presence lie).\n"
    "- MOVEMENT: when a person actually leaves or arrives at a place, ALSO emit "
    "an event with a FRESH UNIQUE id 'event:<slug>' (new per movement, never "
    "reused) sharing one id: kind=moved; agent=<person id>; origin=<place> "
    "and/or destination=<place> as the text gives them (bound place = its id; "
    "named-but-unregistered = the name as value_type=literal; unnamed end = "
    "absent); manner=<walk/run/crawl/ride/drive/fly/swim> when the verb says it. "
    "Use exactly agent, origin, destination, manner — not actor/from/to/source/"
    "target/mode. Do NOT emit valid_from or valid_to for a movement; instead put "
    "one boolean 'complete' on the kind=moved item (true when the same passage "
    "narrates the finished arrival, false when only departure). A bound "
    "destination with complete=true also gets its ordinary 'in' row (no "
    "timestamp). Only real person displacement is movement: intent/facing, "
    "preparation, moving atmosphere (air/rain/light), and same-place "
    "repositioning are NOT moved events.\n"
    "- timeless=true ONLY for what holds across the world's whole history: "
    "identity/structure (kind, names, fixed adjacency) and facts of origin "
    "(kinship of origin, innate traits). Everything acquired or mutable gets "
    "valid_from — the dated onset if given, else the earliest supported "
    "point (the entity's introduction or the scene cursor). Time-relative "
    "quantities (age) are current state at the cursor, never timeless; "
    "standing-but-acquired properties (occupation, scars, learned skills) "
    "are NOT timeless — stamp them at their earliest supported time.\n"
    "- NEVER invent: extract only what the text supports; atmosphere is not an "
    "assertion.\n"
    "- The narrative voice is not an entity: never emit person: entities for "
    "the narrator, an unnamed speaker, or the audience. Never mint a person "
    "from a bare pronoun; if a pronoun's referent is unknown, skip that "
    "assertion.\n"
)

_SEMANTICS_HINT_KEYS = ("arity", "relation_family", "fold_policy")
_SEMANTICS_DECL_KEYS = (*_SEMANTICS_HINT_KEYS, "structural")


# GATE-AUTHORITY-V1 §0: the fixed codes a skip receipt's `reason` is drawn
# from. The three per-edge structural reasons ("cycle-forming containment
# edge: …", "lateral self-loop: …", "merged_self_edge: …") stay prose and
# byte-identical outside it — tests and hosts match substrings of them.
SKIP_REASONS = frozenset({
    "malformed_id",                          # SHAPE-FIX-V1; widened by §2, §4, §7
    "invalid_decay_halflife",                # TRACKING-MODE-V1
    "valid_to_without_valid_from",           # MOVED-EVENT-V1 §B.2
    "valid_to_before_valid_from",            # MOVED-EVENT-V1 §B.2
    "moved_marker_invalid",                  # MOVED-EVENT-V1
    "moved_open_with_arrival",               # MOVED-EVENT-V1
    "moved_complete_attribute_not_durable",  # MOVED-EVENT-V1
    "invalid_valid_time",                    # FOLD-CORRECTNESS-V1 §6
    "malformed_item",                        # GATE-AUTHORITY-V1 §4
    "invalid_field",                         # GATE-AUTHORITY-V1 §4
    "invalid_alias",                         # GATE-AUTHORITY-V1 §4
    "mechanism_attribute",                   # GATE-AUTHORITY-V1 §1
    "same_as_not_canon",                     # GATE-AUTHORITY-V1 §2
    "merge_vetoed",                          # GATE-AUTHORITY-V1 §2
    "invalid_semantics_declaration",         # GATE-AUTHORITY-V1 §5
})


@dataclass(frozen=True)
class SkipRecord:
    """A refusal at the gate, receipted while the rest of the chunk ingests
    (INGEST-HARDENING-V1 Part B; GATE-AUTHORITY-V1 §0): an item, or one of
    its side rows, dropped with a `reason` from `SKIP_REASONS` (or a legacy
    per-edge prose reason). Fields the item lacks are None. No silent caps —
    the host reads these off the porcelain Receipt's `skipped`."""

    # The item's own fields; None where it lacks one, and whatever it sent
    # where a field is malformed (GATE-AUTHORITY-V1 §0/§4).
    entity: Any
    attribute: Any
    value: Any
    reason: str
    # Optional, set only when a skip needs more than the row to explain it:
    # the offending time coordinate of an `invalid_valid_time` skip
    # (FOLD-CORRECTNESS-V1 §6), or the AUTHORED form of a swapped inverse
    # item, e.g. "authored: person:ralph holds obj:bag" (GATE-INVERSE-ALIAS-V1).
    detail: Any = None

    def to_dict(self) -> dict[str, Any]:
        """The JSON-ready record a host reads (Receipt.skipped and
        AtomicAbort.skipped share it). `detail` appears only when set, so
        every record without one keeps its exact prior shape."""
        out = {"entity": self.entity, "attribute": self.attribute,
               "value": encode_out(self.value), "reason": self.reason}
        if self.detail is not None:
            out["detail"] = encode_out(self.detail)
        return out


def _time_value(t: Any) -> tuple[bool, float | int | None]:
    """Validate one stored time coordinate (FOLD-CORRECTNESS-V1 §6): None or a
    finite real number, never a bool. Text ("spring 1660") was admitted and
    then crashed every read of its key; NaN was stored as NULL, turning a
    timed fact silently timeless. Returns (ok, coordinate) — the coordinate is
    coerced where the value is unambiguous: a numeric string ("1660", which
    SQLite used to coerce silently) becomes a float, and an int past SQLite's
    64-bit range becomes a float instead of crashing the insert."""
    if t is None:
        return True, None
    if isinstance(t, str):
        try:
            t = float(t.strip())
        except ValueError:
            return False, t
    if isinstance(t, bool) or not isinstance(t, (int, float)):
        return False, t
    if isinstance(t, int) and not -(2 ** 63) <= t < 2 ** 63:
        try:
            t = float(t)
        except OverflowError:  # past float range: no coordinate
            return False, t
    return math.isfinite(t), t


# The fields an item must carry (GATE-AUTHORITY-V1 §4): `value` may be null,
# the other two may not. Every other field is optional, and null means absent.
_REQUIRED_FIELDS = ("entity", "attribute", "value")


def _finite_real(x: Any) -> bool:
    """A finite real number, never a bool (GATE-AUTHORITY-V1 §4: an item's
    `confidence`) — and within SQLite's 64-bit integer range, since a larger
    int cannot be stored."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return False
    if isinstance(x, int):
        return -(2 ** 63) <= x < 2 ** 63
    return math.isfinite(x)


def _aliases_given(raw: Any) -> bool:
    """Whether an item carries an `aliases` value (GATE-AUTHORITY-V1 §3): a
    non-empty string or a non-empty list, whatever its members."""
    if isinstance(raw, str):
        return raw != ""
    return isinstance(raw, (list, tuple)) and len(raw) > 0


@dataclass
class SceneCursor:
    """The ingest-time pose: where on the timeline the narrated action is."""

    position: float = 0.0

    def advance(self, to: float) -> None:
        self.position = to


class Ingestor:
    def __init__(
        self,
        buffer: PatternBuffer,
        classifier: Classifier,
        registry: IdentityRegistry,
        role: WriterRole,
        model: Callable[[str, dict], Any] | None = None,
        observe_mode: bool = False,
        clock: Callable[[], float] = time.time,
        classify_inline: bool = True,
        resolver_role: WriterRole | None = None,
        containment_ancestors: Callable[[str, str, float | None], set[str]] | None = None,
        semantics: AttributeSemantics | None = None,
        attribute_default: Callable[[str], dict | None] | None = None,
    ) -> None:
        self._buffer = buffer
        self._classifier = classifier
        self._registry = registry
        self._role = role
        self._semantics = semantics or AttributeSemantics(buffer)
        self._attribute_default = attribute_default
        self._attribute_default_checked: set[str] = set()
        # Letter 029: host-authored `generated` rows (arc repair into
        # plot:-style frames) enter through THIS gate but are appended
        # under RESOLVER authority — the API is ingest_structured, the
        # authority stays the matrix's. Guard enforced below.
        self._resolver_role = resolver_role
        # HD 002 finding 1: cycle-forming containment edges are rejected at
        # the gate (a write-time invariant, not a read-time symptom). The
        # ancestor walk is injected (a thin lambda over indexes.locate) so
        # the engine stays decoupled; when unwired, only the self-edge check
        # runs (it needs no derived state and is always enforced).
        self._containment_ancestors = containment_ancestors
        self._model = model
        self._observe_mode = observe_mode
        self._clock = clock
        self.classify_inline = classify_inline  # harness defers to batch
        self.cursor = SceneCursor()
        # INGEST-HARDENING-V1: per-call batched-classify collector + skip records.
        self._classify_collect: list[Assertion] | None = None
        self._skipped: list[SkipRecord] | None = None
        self.last_skipped: list[SkipRecord] = []
        # INGEST-LATENCY-V2 Win 3: cursor governs valid_from for this ingest call.
        self._cursor_authoritative: bool = False
        self._alias_map: dict[str, str] = {}
        self._rebuild_alias_map()

    # -------------------------------------------------- canonicalization

    def _rebuild_alias_map(self) -> None:
        """The map is a sidecar judgment, rebuildable from the receipts in
        the log (spec §3.7, letter 002 Q6).

        Order (GATE-INVERSE-ALIAS-V1 §4): built-ins, then the replayed receipts
        in log order (each records the FIRST hop that was applied, so a later
        host override such as ``type->genre`` outranks the built-in and
        survives reopen), then the inverse relations are popped — an inverse
        relation is never a plain alias, whatever an old receipt says.

        Within that order a receipt is honored only with the gate's own mark
        (GATE-AUTHORITY-V1 §1): status ``inferred``, on an existing assertion
        whose attribute is the receipt's target — exactly the shape
        `_ingest_item` writes. A forged ``canonicalized_from`` row installs
        nothing on reopen, and an ``(inverse)`` receipt is a record of a swap,
        never a map entry."""
        self._alias_map = dict(_BUILTIN_ALIASES)
        for row in self._buffer.visible(attribute="canonicalized_from"):
            if isinstance(row.value, str) and "->" in row.value:
                # an "(inverse)" receipt records a swap — it is not a map entry.
                if row.value.lstrip().startswith(_INVERSE_RECEIPT_PREFIX):
                    continue
                src, dst = row.value.split("->", 1)
                if row.status != "inferred":
                    continue
                subject = self._buffer.get(row.entity)
                if subject is None or subject.attribute != dst.strip():
                    continue
                self._alias_map[src.strip()] = dst.strip()
        for inverse_attr in _BUILTIN_INVERSE_ALIASES:
            self._alias_map.pop(inverse_attr, None)

    def add_attribute_alias(self, alias: str, canonical: str) -> None:
        """Install a host alias. An inverse relation (``holds``/``wearing``)
        cannot be aliased: renaming it without swapping would invert the edge
        (GATE-INVERSE-ALIAS-V1)."""
        key = alias.strip().lower().replace(" ", "_")
        if key in _BUILTIN_INVERSE_ALIASES:
            raise ValueError(
                f"{alias!r} is an inverse relation: the gate swaps its direction "
                f"(-> {_BUILTIN_INVERSE_ALIASES[key]!r}); it cannot be aliased")
        self._alias_map[alias.strip().lower()] = canonical

    def _canonicalize(self, attribute: str) -> tuple[str, str | None]:
        """Returns (canonical, receipt-or-None)."""
        attr = attribute.strip().lower().replace(" ", "_")
        if self._semantics.is_structural(attr) or attr not in self._alias_map:
            return attr, None
        canonical = self._alias_map[attr]
        return canonical, f"{attr}->{canonical}"

    def _inverse_of(self, attr: str) -> str | None:
        """The forward attribute for an inverse relation (GATE-INVERSE-ALIAS-V1
        §1), or None. ``attr`` is already normalized by `_canonicalize`."""
        if attr in _BUILTIN_INVERSE_ALIASES and not self._semantics.is_structural(attr):
            return _BUILTIN_INVERSE_ALIASES[attr]
        return None

    # ---------------------------------------------------- attr semantics

    @staticmethod
    def _semantics_payload(source: dict[str, Any], keys) -> dict[str, Any]:
        return {k: source[k] for k in keys if k in source and source[k] is not None}

    def _declaration_plan(
        self, attribute: str, item: dict[str, Any]
    ) -> tuple[dict[str, Any], str] | None:
        """The first-use attr:* declaration the gate would write before an
        item's data row, with its source (GATE-AUTHORITY-V1 §5): the item's
        own hints (`"item"`), else the host's `attribute_default` output,
        asked once per attribute (`"attribute_default"`). None when there is
        nothing to declare — hints on a core or already-declared attribute
        are ignored, as before. Writes nothing."""
        if self._semantics.is_core(attribute) or self._semantics.is_declared(attribute):
            return None
        declaration = self._semantics_payload(item, _SEMANTICS_HINT_KEYS)
        if declaration:
            return declaration, "item"
        if attribute in self._attribute_default_checked:
            return None
        self._attribute_default_checked.add(attribute)
        if self._attribute_default is None:
            return None
        default = self._attribute_default(attribute)
        if default:
            declaration = self._semantics_payload(default, _SEMANTICS_DECL_KEYS)
        return (declaration, "attribute_default") if declaration else None

    def _declare(self, attribute: str, declaration: dict[str, Any]) -> list[Assertion]:
        """Write a validated first-use declaration before the triggering data
        row."""
        out: list[Assertion] = []
        for predicate, value in declaration.items():
            row = self._buffer.append(
                entity=f"{ATTR_PREFIX}{attribute}",
                attribute=predicate,
                value=value,
                status="inferred",
                role=self._role,
            )
            out.append(row)
            if self.classify_inline:
                self._classifier.classify(row)
        self._semantics.rebuild()
        return out

    # ------------------------------------------ moved-event coordinate pass

    def _apply_moved_coordinate_pass(
        self, items: list[dict[str, Any]], call_frame: str | None = None
    ) -> list[dict[str, Any]]:
        """MOVED-EVENT-V1 §B.3-B.5: engine-authored movement timestamps
        (extracted mode). For each `kind=moved` event: validate its single
        boolean `complete` marker (fail closed on missing / non-boolean /
        duplicated / misplaced — drop the whole moved group AND its matched
        arrival `in`, one `moved_marker_invalid` receipt); strip any
        model-supplied `valid_from`/`valid_to`; stamp from the scene cursor. The
        event PAYLOAD rows (kind/agent/origin/destination/manner) get
        `valid_from`=cursor and `valid_to`=cursor when complete (the
        zero-duration event); the matched arrival `in` gets `valid_from`=cursor
        with `valid_to` ABSENT (the standing destination — never `[t,t)`, else
        `locate()` could never flip to it). An `attribute="complete"` row is
        stray and never durable."""
        items = list(items)  # stamp a copy: the caller's extract() output stays raw
        cursor = self.cursor.position

        def ev_id(it: Any) -> str | None:
            # A non-object item passes through untouched, so it reaches the
            # gate's `malformed_item` receipt (GATE-AUTHORITY-V1 §4).
            if not isinstance(it, dict):
                return None
            e = it.get("entity")
            return e if isinstance(e, str) and e.startswith("event:") else None

        def cattr(it: dict[str, Any]) -> str:
            raw = it.get("attribute")
            return self._canonicalize(raw)[0] if isinstance(raw, str) else ""

        def eff_frame(it: dict[str, Any]) -> str:
            """The frame this row will actually land in.

            The pass runs BEFORE `_ingest_body` fills `frame=` into unframed
            items, so reading `it["frame"]` raw compares a pre-default value
            against a post-default one. An event explicitly stamped
            `knows:b` and its unframed arrival — which the call default puts
            in `knows:b` too — looked like different frames, the arrival went
            unmatched, and the model's invented coordinates survived into the
            log instead of being replaced by the cursor. Explicit item frame
            wins, else the call-level default, else canon.
            """
            return it.get("frame") or call_frame or CANON

        moved_ids = {
            ev_id(it) for it in items
            if ev_id(it) and cattr(it) == "kind" and it.get("value") == "moved"
        }
        if not moved_ids:
            return items

        payload: dict[str, list[int]] = {eid: [] for eid in moved_ids}
        kind_idx: dict[str, int] = {}
        markers: dict[str, list[Any]] = {eid: [] for eid in moved_ids}
        agent: dict[str, Any] = {}
        dest: dict[str, Any] = {}
        dest_is_entity: dict[str, bool] = {}
        frame_of: dict[str, str] = {eid: CANON for eid in moved_ids}
        drop: set[int] = set()

        for idx, it in enumerate(items):
            eid = ev_id(it)
            if eid not in payload:
                continue
            attr = cattr(it)
            if attr == "complete":
                # A skip RECEIPT, not a silent drop (§B.4 calls it a malformed
                # movement row that is skipped). Silently dropping it meant
                # `last_skipped` carried no receipt on the ordinary path, and —
                # worse — under extracted+atomic+rules `_skip_aborting` saw no
                # skip at all, so a malformed gate row failed to abort the set
                # the atomic contract promises is all-or-none.
                self._record_skip(it.get("entity"), "complete", it.get("value"),
                                  "moved_complete_attribute_not_durable")
                drop.add(idx)          # stray row — never the marker, never durable
                continue
            payload[eid].append(idx)
            if "complete" in it:
                markers[eid].append(it["complete"])
            if attr == "kind" and it.get("value") == "moved":
                kind_idx[eid] = idx
                frame_of[eid] = eff_frame(it)
            elif attr == "agent":
                agent[eid] = it.get("value")
            elif attr == "destination":
                dest[eid] = it.get("value")
                vt = it.get("value_type") or (
                    "entity" if isinstance(it.get("value"), str)
                    and ID_RE.fullmatch(str(it.get("value"))) else "literal")
                dest_is_entity[eid] = vt == "entity"

        for eid in moved_ids:
            ki = kind_idx.get(eid)
            marker_ok = (
                len(markers[eid]) == 1
                and isinstance(markers[eid][0], bool)
                and ki is not None
                and "complete" in items[ki]
            )
            # EVERY exact arrival match is a candidate (M1): a duplicate arrival
            # row must not survive with model-authored coordinates. Match rule:
            # entity==agent ∧ canonical attr=="in" ∧ value==destination ∧ frame.
            arrival_idxs: list[int] = []
            if agent.get(eid) is not None and dest.get(eid) is not None \
                    and dest_is_entity.get(eid):
                for idx, it in enumerate(items):
                    if (isinstance(it, dict)
                            and it.get("entity") == agent[eid] and cattr(it) == "in"
                            and it.get("value") == dest[eid]
                            and eff_frame(it) == frame_of[eid]):
                        arrival_idxs.append(idx)
            if not marker_ok:
                for idx in payload[eid]:
                    drop.add(idx)
                for idx in arrival_idxs:          # drop ALL matches, not just one
                    drop.add(idx)
                self._record_skip(eid, "kind", "moved", "moved_marker_invalid")
                continue
            complete = markers[eid][0]
            # An OPEN move (complete=false) has NO arrival `in` (§B.3): an exact
            # arrival-shaped row is contradictory — drop+receipt every candidate
            # so the untrusted prose path can neither flip locate() nor retain an
            # invented coordinate (M2).
            if not complete and arrival_idxs:
                for idx in arrival_idxs:
                    drop.add(idx)
                self._record_skip(eid, "arrival", dest[eid], "moved_open_with_arrival")
            for idx in payload[eid]:
                it = dict(items[idx])
                it.pop("complete", None)
                it.pop("timeless", None)
                it["valid_from"] = cursor
                it["valid_to"] = cursor if complete else None
                items[idx] = it
            if complete:
                for idx in arrival_idxs:          # stamp ALL exact matches (M1)
                    it = dict(items[idx])
                    it.pop("timeless", None)
                    it["valid_from"] = cursor
                    it["valid_to"] = None
                    items[idx] = it

        if not drop:
            return items
        return [it for idx, it in enumerate(items) if idx not in drop]

    # -------------------------------------------------------- structured

    def ingest_structured(
        self, items: list[dict[str, Any]], frame: str | None = None,
        classify: str = "inline", cursor_authoritative: bool = False,
        extracted: bool = False, atomic: bool = False,
    ) -> list[Assertion]:
        """The no-model gate entry: pre-extracted items, full discipline.
        Synthetic test content only — never bible-derived (spec §6).

        ``frame`` (letter 028): default frame for items that carry none —
        the sanctioned doorway to named-frame authoring (knows:<id>
        session-zero seeding, plot: arcs). Frame is a TARGET only; every
        other gate discipline (provenance, canonicalization, cursor,
        roles) applies unchanged. Per-item frames still win.

        ``classify`` (INGEST-HARDENING-V1 Part A): durability classification mode.
        ``"inline"`` (default) classifies each row per-row as it lands (unchanged).
        ``"batch"`` defers during the call and runs ONE batch model call over the
        call's model-needing rows at the end — the first-class form of the
        manual ``classify_inline=False`` + ``classify_all`` recipe (~65% build-time
        cut). ``"defer"`` skips classification entirely (the host runs
        ``classify_all`` later over the whole build). ``batch``/``defer`` inherit
        the deferred-classification residual (the read-time ``locate()`` guard
        remains the transitive-cycle backstop, as in the harness build).

        ``atomic`` (ATOMIC-ACTIVATION-V1 §A): default ``False`` — existing per-row
        visibility byte-identical. Under ``atomic=True`` the whole set is one unit
        of work (all-or-none); classification must be model-free
        (``classify ∈ {rules, defer}``, else ``ValueError`` before any write), and
        any gate skip aborts the set with ``AtomicAbort`` (§B6)."""
        if classify not in ("inline", "batch", "defer", "rules"):
            raise ValueError(f"unknown classify mode {classify!r}")
        if atomic:
            if classify not in ("rules", "defer"):
                raise ValueError(
                    "atomic=True requires model-free classify ∈ {rules, defer} "
                    "— 'inline'/'batch' call the model inside the open "
                    "transaction (ATOMIC-ACTIVATION-V1 §A)")
            return self._run_atomic(lambda: self._skip_aborting(
                lambda: self._ingest_body(items, frame, classify,
                                          cursor_authoritative, extracted)))
        return self._ingest_body(items, frame, classify, cursor_authoritative,
                                 extracted)

    def _ingest_body(
        self, items: list[dict[str, Any]], frame: str | None,
        classify: str, cursor_authoritative: bool, extracted: bool,
    ) -> list[Assertion]:
        self._skipped = []
        # "rules" collects like "batch", then applies guardrails+STATE (no LM).
        collect: list[Assertion] | None = [] if classify in ("batch", "rules") else None
        prev_inline = self.classify_inline
        if classify in ("batch", "defer", "rules"):
            self.classify_inline = False
        prev_collect = self._classify_collect   # save/restore (re-entrancy-safe)
        self._classify_collect = collect
        prev_cursor_auth = self._cursor_authoritative
        self._cursor_authoritative = cursor_authoritative
        try:
            # MOVED-EVENT-V1 §B.3: in extracted (prose) mode the ENGINE authors
            # movement timestamps — the model is untrusted for timing. The
            # coordinate pass strips model coordinates from moved-event rows and
            # their matched arrival `in`, stamps from the scene cursor, and
            # fails a malformed marker group closed. Structured callers
            # (extracted=False) keep their own numeric coordinates untouched.
            if extracted:
                items = self._apply_moved_coordinate_pass(items, frame)
            appended: list[Assertion] = []
            for item in items:
                # `frame` fills unframed items inside the gate's normalization
                # (GATE-AUTHORITY-V1 §4).
                appended.extend(self._ingest_item(item, frame))
            if collect:
                self._classifier.classify_rows(collect, model=(classify == "batch"))
            return appended
        finally:
            # Always reflect THIS call's skips, even if an item raised mid-batch
            # (Cx final: no stale carryover from a prior call).
            self.classify_inline = prev_inline
            self._classify_collect = prev_collect
            self._cursor_authoritative = prev_cursor_auth
            self.last_skipped = list(self._skipped or [])
            self._skipped = None

    # ------------------------------------------------- atomic (§B / §C)

    def _skip_aborting(self, body):
        """Run an ingest/op body, then raise ``_GateSkip`` if it receipted any
        skip — so a receipt-and-continue skip aborts the whole atomic set (§B2).
        The skips are captured before the body's finally nulls ``_skipped``."""
        appended = body()
        if self.last_skipped:
            raise _GateSkip(list(self.last_skipped))
        return appended

    def _run_atomic(self, body):
        """Shared atomic envelope: snapshot in-memory views, run ``body`` in the
        buffer's unit-of-work, translate faults to ``AtomicAbort`` (§B4/§B6). A
        rollback-unconfirmable failure poisons the connection and propagates the
        raw error unwrapped — never wrapped as ``AtomicAbort`` (§B6)."""
        snap = self._snapshot_views()
        try:
            return self._buffer.atomic_unit(body)
        except _GateSkip as sig:
            self._restore_views(snap)
            # §B6: skipped is the non-atomic path's record shape, JSON-ready
            # (encoded value), so it rides the exception AND the MCP wire cleanly.
            raise AtomicAbort("gate_skip", [s.to_dict() for s in sig.skipped], None)
        except AtomicAbort:
            raise
        except BaseException as exc:
            # A2/§B6: a fault after a confirmed COMMIT (post-commit-ambiguous) or
            # an unconfirmable rollback (poisoned) is the RAW error — never
            # wrapped as AtomicAbort, and in-memory views are NOT restored (the
            # set is durable / its state is unknown).
            if self._buffer.poisoned or self._buffer.unit_committed:
                raise
            self._restore_views(snap)
            raise AtomicAbort(
                "exception", [],
                {"type": type(exc).__name__, "message": str(exc)}) from exc

    def _snapshot_views(self) -> dict[str, Any]:
        """In-memory mutable views SQLite rollback does NOT restore (§B4)."""
        return {
            "alias_map": dict(self._alias_map),
            "default_checked": set(self._attribute_default_checked),
            "classify_inline": self.classify_inline,
            "last_skipped": list(self.last_skipped),
        }

    def _restore_views(self, snap: dict[str, Any]) -> None:
        self._alias_map = snap["alias_map"]
        self._attribute_default_checked = snap["default_checked"]
        self.classify_inline = snap["classify_inline"]
        # this abort's skips ride out on AtomicAbort; the object's last_skipped
        # is restored to its prior value — the two never alias (§B4).
        self.last_skipped = snap["last_skipped"]
        # the semantics declaration view self-heals from the rolled-back log on
        # next access; force the refresh so a staged attr:* declaration is gone.
        self._semantics._rebuilt_at = -1

    def commit_set(
        self, ops: list[dict[str, Any]], truth, *, classify: str = "rules",
        frame: str = CANON, cursor_authoritative: bool = False,
    ) -> list[Assertion]:
        """The typed activation door (ATOMIC-ACTIVATION-V1 §C): an ordered list
        of ``{op:"assert", item}`` / ``{op:"retract", assertion_id, reason}`` ops
        applied as ONE unit of work. Each op dispatches through its EXISTING path
        (gate discipline / the truth-maintenance verb) — the unit-of-work changes
        only WHEN durability happens. Model-free classify only."""
        if classify not in ("rules", "defer"):
            raise ValueError(
                "commit_set requires model-free classify ∈ {rules, defer}")
        self._validate_ops(ops)
        return self._run_atomic(lambda: self._skip_aborting(
            lambda: self._apply_ops(ops, truth, frame, classify,
                                    cursor_authoritative)))

    @staticmethod
    def _validate_ops(ops: list[dict[str, Any]]) -> None:
        if not isinstance(ops, list):
            raise ValueError("commit_set ops must be a list")
        # §C1's vocabulary is EXACT, and the Python door enforces it rather
        # than trusting the MCP schema to be the only gate. It previously
        # checked the discriminant and a few required fields, so an assert op
        # could smuggle outer `role`/`status` keys (authority laundering is
        # precisely what §C1 forbids) and a retract could carry a non-string
        # `reason`, which was then stored as the retraction value. The
        # published MCP schema already excluded both (`additionalProperties:
        # false`, `reason: string`); Python was simply laxer than the contract
        # it advertised. This narrows Python to the contract — it never widens
        # it, so no valid call changes.
        allowed = {"assert": {"op", "item"}, "retract": {"op", "assertion_id", "reason"}}
        for op in ops:
            if not isinstance(op, dict) or op.get("op") not in ("assert", "retract"):
                raise ValueError(
                    f"commit_set op must be {{op: assert|retract, …}}, got {op!r}")
            extra = set(op) - allowed[op["op"]]
            if extra:
                raise ValueError(
                    f"a '{op['op']}' op accepts exactly {sorted(allowed[op['op']])}; "
                    f"unexpected {sorted(extra)} (authority and provenance are "
                    "held internally, never taken from the op)")
            if op["op"] == "assert":
                if not isinstance(op.get("item"), dict):
                    raise ValueError("an 'assert' op requires an 'item' dict")
            else:
                if not isinstance(op.get("assertion_id"), str):
                    raise ValueError("a 'retract' op requires 'assertion_id'")
                if not isinstance(op.get("reason"), str):
                    raise ValueError(
                        "a 'retract' op requires 'reason' to be a string, got "
                        f"{type(op.get('reason')).__name__}")

    def _apply_ops(self, ops, truth, frame, classify, cursor_authoritative):
        """The commit_set op loop — the assert path mirrors ``_ingest_body``'s
        gate + classify collection; retract dispatches to the shared truth verb
        (authority held internally, never laundered from the op, §C1)."""
        self._skipped = []
        collect: list[Assertion] | None = [] if classify in ("batch", "rules") else None
        prev_inline = self.classify_inline
        self.classify_inline = False
        prev_collect = self._classify_collect
        self._classify_collect = collect
        prev_cursor_auth = self._cursor_authoritative
        self._cursor_authoritative = cursor_authoritative
        try:
            appended: list[Assertion] = []
            for op in ops:
                if op["op"] == "assert":
                    # `frame` fills an unframed item inside the gate's
                    # normalization (GATE-AUTHORITY-V1 §4).
                    appended.extend(self._ingest_item(op["item"], frame))
                else:
                    appended.append(truth.retract(op["assertion_id"], op["reason"]))
            if collect:
                self._classifier.classify_rows(collect, model=(classify == "batch"))
            return appended
        finally:
            self.classify_inline = prev_inline
            self._classify_collect = prev_collect
            self._cursor_authoritative = prev_cursor_auth
            self.last_skipped = list(self._skipped or [])
            self._skipped = None

    def _cycle_reason(
        self, child: str, parent: str, frame: str, valid_from: float | None
    ) -> str | None:
        """The reason a containment edge would form a cycle, or None (HD 002
        finding 1). Both ids are already identity-resolved. Self-edges are
        detected unconditionally (no derived state). Transitive cycles are
        detected as-of the new edge's valid_from — best-effort: a back-dated
        edge closing a cycle only at a different valid-time isn't visible to a
        single write-time walk and remains caught by the read-time locate()
        guard. INGEST-HARDENING-V1: returns the reason; the caller SKIPS the
        single edge (typed receipt) rather than aborting the chunk."""
        if child == parent:
            return (f"cycle-forming containment edge: {child!r} cannot contain "
                    "itself (self-edge; append-only tree invariant, §4)")
        if self._containment_ancestors is None:
            return None
        if child in self._containment_ancestors(parent, frame, valid_from):
            return (f"cycle-forming containment edge: {child!r} is already an "
                    f"ancestor of {parent!r} as-of valid_from={valid_from} — "
                    "containment is a single-parent tree (§4)")
        return None

    def _edge_skip_reason(
        self, entity: str, attribute: str, value: Any, value_type: str,
        frame: str, valid_from: float | None,
    ) -> str | None:
        """The reason a single structural edge is invalid (containment cycle /
        self-edge / lateral self-loop), or None (INGEST-HARDENING-V1 Part B).
        Only structurally-invalid SINGLE edges are skippable; every other gate
        failure still raises."""
        if value_type != "entity" or not isinstance(value, str):
            return None
        if self._semantics.is_containment(attribute):
            return self._cycle_reason(entity, value, frame, valid_from)
        if self._semantics.is_lateral(attribute) and entity == value:
            # A lateral self-loop (X connects_to X) is extraction noise — it
            # adds no edge any walk can use (#19).
            return f"lateral self-loop: {entity!r} cannot {attribute} itself"
        return None

    def _entity_valued(self, attribute: str) -> bool:
        """An entity-valued predicate (GATE-AUTHORITY-V1 §7): one whose engine
        readers only ever see entity values — the containment and lateral
        families (declared members included, via semantics), `part_of`,
        `caused_by`, and the identity predicates other than `same_as`."""
        return (attribute in _ENTITY_VALUED
                or self._semantics.is_containment(attribute)
                or self._semantics.is_lateral(attribute))

    def _record_skip(self, entity: Any, attribute: Any, value: Any, reason: str,
                     detail: Any = None) -> None:
        logger.warning("ingest skipped edge: %s · %s · %r — %s%s",
                       entity, attribute, value, reason,
                       "" if detail is None else f" ({detail!r})")
        if self._skipped is not None:
            self._skipped.append(SkipRecord(entity, attribute, value, reason, detail))

    def _normalize_item(self, item: Any, call_frame: str | None) -> dict[str, Any] | None:
        """Step 1 of the gate (GATE-AUTHORITY-V1 §4): the item's shape only,
        on a copy — the caller's dict is never mutated and nothing is
        written. Returns the normalized item, or None once a
        `malformed_item` skip is receipted.

        - Not an object: skipped, with the item itself as the record's value.
        - Null means absent for every optional field: a null `frame` takes the
          call's default frame (else canon), a null `status` is `stated`, and
          null `aliases` means none. `value` is required but may be null (a
          null literal); a null `entity`/`attribute` counts as missing at
          step 3.
        - `frame` must be a non-empty string. A malformed frame is never
          defaulted to canon: that would leak a row meant for a private frame.
        - `aliases` becomes the list of its members: a string is one member
          (never one alias per character), a list its members, and any other
          value one member, dropped as a whole. Members that are not non-empty
          strings are dropped with an `invalid_alias` receipt where the alias
          rows are written (step 11), so an item skipped for another reason
          yields exactly one record.
        """
        if not isinstance(item, dict):
            self._record_skip(None, None, item, "malformed_item")
            return None
        norm = {k: v for k, v in item.items() if v is not None or k == "value"}
        # The call-level default frame (letter 028) fills an unframed item here
        # — it used to be filled by `_ingest_body` / `_apply_ops`.
        norm.setdefault("frame", CANON if call_frame is None else call_frame)
        norm.setdefault("status", "stated")
        frame = norm["frame"]
        if not isinstance(frame, str) or not frame:
            self._record_skip(norm.get("entity"), norm.get("attribute"),
                              norm.get("value"), "malformed_item",
                              detail={"field": "frame", "value": frame})
            return None
        aliases = norm.get("aliases")
        if aliases is not None:
            norm["aliases"] = ([aliases] if isinstance(aliases, str)
                               else list(aliases) if isinstance(aliases, (list, tuple))
                               else [aliases])
        return norm

    def _content_ok(self, item: dict[str, Any]) -> bool:
        """Step 3 of the gate (GATE-AUTHORITY-V1 §4), after authority: the
        content checks. Receipts the first failure and returns False; writes
        nothing. Record fields are the item's own (it is not canonicalized
        yet); fields it lacks are None."""
        entity, attribute = item.get("entity"), item.get("attribute")
        value = item.get("value")

        def skip(reason: str, detail: Any = None) -> bool:
            self._record_skip(entity, attribute, value, reason, detail=detail)
            return False

        missing = [field for field in _REQUIRED_FIELDS if field not in item]
        if missing:
            return skip("malformed_item", {"missing": missing})
        if not isinstance(entity, str):
            return skip("malformed_id")
        if not isinstance(attribute, str) or not attribute.strip():
            return skip("malformed_item", {"field": "attribute", "value": attribute})
        value_type = item.get("value_type")
        if value_type is not None and (
                not isinstance(value_type, str) or value_type not in VALUE_TYPES):
            return skip("invalid_field", {"field": "value_type", "value": value_type})
        for flag in ("timeless", "correction"):
            if flag in item and not isinstance(item[flag], bool):
                return skip("invalid_field", {"field": flag, "value": item[flag]})
        if "confidence" in item and not _finite_real(item["confidence"]):
            return skip("invalid_field",
                        {"field": "confidence", "value": item["confidence"]})
        if value_type == "entity" and not isinstance(value, str):
            return skip("malformed_id")
        return True

    def _authorize(self, item: dict[str, Any], aliases_given: bool) -> WriterRole:
        """Settle an item's write authority before its first write
        (GATE-AUTHORITY-V1 §3). Raises, never writes, never skips: an
        authority violation must raise even when the item is also malformed
        or a structurally invalid edge (INGEST-HARDENING-V1 Cx final).

        Reads only `status`, `frame` and side-field presence (`aliases_given`
        is judged on the value the host sent, before normalization). A status
        in the ingestor's grant writes under ingestor authority; `generated`
        passes letter 029's checks, then writes under resolver authority;
        anything else is refused by the ingestor role's own check(), so the
        message is the one the buffer used to raise after the declarations."""
        status = item["status"]
        if status != "generated":
            self._role.check(status)
            return self._role
        # Letter 029: host-authored generated rows land only in host-owned
        # named frames (plot:*), never canon or knows:*.
        frame_target = item["frame"]
        if frame_target == CANON or frame_target.startswith("knows:"):
            raise ValueError(
                "generated provenance through the gate is permitted only "
                "into host-owned named frames (e.g. plot:*) — never canon "
                "or knows:* (letter 029 guard)"
            )
        if self._resolver_role is None:
            raise ValueError("no resolver authority wired for generated rows")
        # The `source` meta and `alias` rows carry no frame: on a generated
        # item they would be generated rows in canon, which letter 029
        # forbids. (The other side rows carry fixed engine statuses inside the
        # ingestor's grant and need no check.)
        carried = [field for field, given in (
            ("source_doc", bool(item.get("source_doc"))),
            ("aliases", aliases_given),
        ) if given]
        if carried:
            raise RoleViolation(
                f"a generated item cannot carry {' or '.join(carried)}: those "
                "rows carry no frame and would be generated rows in canon "
                "(letter 029 guard)"
            )
        return self._resolver_role

    def _ingest_item(self, item: Any, call_frame: str | None = None) -> list[Assertion]:
        """One item through the gate, in GATE-AUTHORITY-V1 §0's order:
        normalize, authority, content checks, canonicalize, mechanism
        attribute, malformed ids, id-shaped values, identity / half-life /
        time / interval / per-edge checks, declarations, the main row, its
        side rows, classification. Everything that can refuse the item runs
        before its first write. ``call_frame`` is the call's default frame
        for an item that carries none (letter 028)."""
        out: list[Assertion] = []
        # 1. Normalize (§4): shape only, on a copy; no write.
        fields = self._normalize_item(item, call_frame)
        if fields is None:
            return out
        # 2. Authority FIRST (§3): settled before the content checks,
        # canonicalization, any declaration or the main row, so a violation
        # raises with nothing of the item written.
        write_role = self._authorize(fields, _aliases_given(item.get("aliases")))
        item = fields
        # 3. Content checks (§4): skips.
        if not self._content_ok(item):
            return out
        status = item["status"]
        frame = item["frame"]
        # 4. Canonicalize the attribute (existing). GATE-INVERSE-ALIAS-V1 §2's
        # swap follows immediately, once value_type is decided.
        attribute, receipt = self._canonicalize(item["attribute"])
        # RAW ids first (Cx final): validation must see what the author wrote,
        # not what resolution mapped it to — resolve happens AFTER the
        # malformed-id gate below.
        entity = item["entity"]
        # Exact-decimal symmetry: a JSON-origin host passes the tag form
        # ({"$decimal": "12.50"}), an in-process host a real Decimal — both
        # normalize to Decimal here (EXACT-DECIMAL-QUANTITIES-V1).
        value = decode_value(item["value"])
        # Entity inference requires the full id grammar, not a bare ":" —
        # a prose value with a colon ("repaired: the rival arrives") is a
        # literal, never a phantom entity reference (SHAPE-FIX-V1 4a).
        value_type = item.get("value_type") or (
            "entity" if isinstance(value, str) and ID_RE.fullmatch(value)
            else "literal"
        )
        # GATE-INVERSE-ALIAS-V1 §2: an inverse relation with an ENTITY value
        # swaps subject and object here — immediately after canonicalization,
        # before the malformed-id gate, identity resolution, interval checks
        # and the per-edge checks, so every later check sees the true
        # direction. A text value keeps the attribute as authored (§3).
        # Item-level identity data stays with the ORIGINAL subject.
        identity_subject = entity
        authored_detail: str | None = None   # set only when the gate swapped
        forward = self._inverse_of(attribute)
        if forward is not None and value_type == "entity" and isinstance(value, str):
            receipt = f"{_INVERSE_RECEIPT_PREFIX} {attribute}->{forward}"
            authored_detail = f"authored: {entity} {attribute} {value}"
            attribute = forward
            entity, value = value, entity
        timeless = item.get("timeless", False)    # a real bool (§4)
        valid_from = item.get("valid_from")
        # INGEST-LATENCY-V2 Win 3: in cursor-authoritative ingest (bible
        # source-build) the CURSOR governs the story-time axis — the per-item
        # valid_from is overridden and DEMOTED to a `source_valid_from` meta
        # (lossless), so a diegetic year ("612") can't invert the timeline.
        # Computed before the edge guard (which reads valid_from). Timeless rows
        # carry no story-time, so they are unaffected and never demote.
        demoted_vf = None
        if self._cursor_authoritative and not timeless:
            demoted_vf = valid_from   # may be None (nothing to demote)
            valid_from = self.cursor.position
        elif valid_from is None and not timeless:
            valid_from = self.cursor.position  # the pose stamps the row

        # 5. GATE-AUTHORITY-V1 §1: a mechanism attribute (retracts / resolved_by /
        # canonicalized_from) changes what OTHER rows mean and has exactly one
        # owning component. The gate never accepts one as an item, on any path
        # (ingest, ingest_structured, a commit_set assert op) — the real doors
        # are retract, resolve and the gate's own canonicalization receipt.
        if attribute in MECHANISM_ATTRIBUTES:
            self._record_skip(entity, attribute, value, "mechanism_attribute")
            return out

        # 6. Malformed-id gate (SHAPE-FIX-V1 4a): AFTER the authority gate (an
        # authority violation must still raise, never be swallowed by a skip —
        # the INGEST-HARDENING ordering), BEFORE the edge guard — and on the
        # RAW ids, before resolution touches them (Cx final).
        if not ID_RE.fullmatch(entity) or (
            value_type == "entity" and isinstance(value, str)
            and not ID_RE.fullmatch(value)
        ):
            self._record_skip(entity, attribute, value, "malformed_id",
                              detail=authored_detail)
            return out

        # 7. GATE-AUTHORITY-V1 §7: on an entity-valued predicate, a value with no
        # declared value_type that LOOKS like an id but fails the grammar
        # (`in: "Place:Cellar"`) is a typo, not text — stored as a literal it
        # would win the location fold and silently relocate its subject. The
        # same treatment the subject position gets. An explicit value_type is
        # the author's word: "entity" was checked above, "literal" stands.
        if ("value_type" not in item and isinstance(value, str)
                and ID_SHAPED_RE.match(value) and not ID_RE.fullmatch(value)
                and self._entity_valued(attribute)):
            self._record_skip(entity, attribute, value, "malformed_id")
            return out

        # 8. Identity resolution, the decay half-life, time values, interval
        # invariants and the per-edge structural skips (existing).
        raw_entity, raw_value = entity, value
        entity = self._registry.resolve(entity)
        if value_type == "entity" and isinstance(value, str):
            value = self._registry.resolve(value)
        identity_subject = self._registry.resolve(identity_subject)

        # Decay-policy declarations must be valid physics (TRACKING-MODE-V1
        # §B3): a malformed half-life is skip-receipted at the gate, never
        # silently active (DecayPolicy would ignore it — but a silent ignore
        # reads as "declared" to the author; the receipt says it fell).
        if attribute == "decay_halflife_seconds" and not (
            isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0
        ):
            self._record_skip(entity, attribute, value, "invalid_decay_halflife",
                              detail=authored_detail)
            return out

        # FOLD-CORRECTNESS-V1 §6: after cursor stamping, each time coordinate
        # is None or a finite real number — checked before the interval
        # invariants, which compare them. Skip-receipted with the offending
        # value in `detail`; under atomic=True the skip aborts the whole set.
        ok_from, valid_from = _time_value(None if timeless else valid_from)
        ok_to, row_valid_to = _time_value(item.get("valid_to"))
        for ok, coordinate in ((ok_from, valid_from), (ok_to, row_valid_to)):
            if not ok:
                self._record_skip(entity, attribute, value, "invalid_valid_time",
                                  detail=coordinate)
                return out
        eff_valid_from = valid_from

        # MOVED-EVENT-V1 §B.2: two general interval invariants the log lacked
        # (buffer accepted both shapes). A closing coordinate requires a numeric
        # opening one, and cannot precede it. Skip-receipted, never silently
        # stored; under atomic=True this skip aborts the whole set.
        if row_valid_to is not None:
            if eff_valid_from is None:
                self._record_skip(entity, attribute, value, "valid_to_without_valid_from",
                              detail=authored_detail)
                return out
            if row_valid_to < eff_valid_from:
                self._record_skip(entity, attribute, value, "valid_to_before_valid_from",
                              detail=authored_detail)
                return out

        # Edge-granular structural guard (Part B): a single invalid edge
        # (containment cycle / self-edge / lateral self-loop) is SKIPPED with a
        # typed receipt — the invariant holds (it never enters) and the rest of
        # the chunk still ingests. (Authority failures already raised above.)
        skip = self._edge_skip_reason(
            entity, attribute, value, value_type, frame, eff_valid_from,
        )
        if skip is not None:
            # INGESTION-FIDELITY-V2 §D: two raw ids that resolve to one
            # identity head post-`same_as` are a MERGE footprint, not an
            # authored self-edge — the distinct reason (raw ids retained)
            # makes the diagnosis actionable. Containment-only per the
            # GREEN'd spec; a merged lateral loop keeps its original
            # reason. Gate behavior is identical: the row never enters.
            if (entity == value and raw_entity != raw_value
                    and self._semantics.is_containment(attribute)):
                skip = (f"merged_self_edge: {raw_entity!r} and {raw_value!r} "
                        f"resolve to the same entity {entity!r} — {skip}")
            self._record_skip(entity, attribute, value, skip,
                              detail=authored_detail)
            return out  # nothing appended

        # 9. Declarations (GATE-AUTHORITY-V1 §5): a declaration the gate would
        # write must be in its axis vocabulary, validated before anything is
        # written. Authority first: the buffer's vocabulary-authority refusal
        # (a core attribute, or data already present) still raises ValueError
        # whatever the value, through the buffer's own check.
        is_manual_semantics_row = (
            entity.startswith(ATTR_PREFIX) and attribute in SEMANTICS_PREDICATES
        )
        if is_manual_semantics_row:
            self._buffer.check_declaration_authority(entity, attribute)
            if not valid_declaration(attribute, value):
                self._record_skip(entity, attribute, value,
                                  "invalid_semantics_declaration",
                                  detail={"field": attribute, "value": value,
                                          "source": "attr_row"})
                return out
        else:
            plan = self._declaration_plan(attribute, item)
            if plan is not None:
                declaration, source = plan
                self._buffer.check_declaration_authority(
                    f"{ATTR_PREFIX}{attribute}", next(iter(declaration)))
                invalid = [(predicate, declared) for predicate, declared
                           in declaration.items()
                           if not valid_declaration(predicate, declared)]
                if invalid:
                    # The whole item skips: writing its data row anyway would
                    # lock the attribute, since the buffer refuses any
                    # declaration once data exists. An invalid callback result
                    # is not marked checked, so every item on the attribute
                    # skips the same way until the host fixes the callback.
                    if source == "attribute_default":
                        self._attribute_default_checked.discard(attribute)
                    predicate, declared = invalid[0]
                    self._record_skip(entity, attribute, value,
                                      "invalid_semantics_declaration",
                                      detail={"field": predicate, "value": declared,
                                              "source": source})
                    return out
                out.extend(self._declare(attribute, declaration))

        # 10. The main row — or, for a raw `same_as`, the guarded merge (§2).
        row: Assertion | None
        if attribute == "same_as":
            merged = self._merge_raw_same_as(raw_entity, raw_value, value_type, frame)
            if merged is None:
                return out                          # skipped with a receipt
            out.extend(merged)
            # The merge's rows join the call's classification (all EVENT by
            # guardrail, zero model calls), and its `same_as` edge stands in
            # for the main row: the main-row side rows attach to it. On
            # `noop_already_merged` there is no main row, so they have nothing
            # to attach to and are not written; the subject-level rows still
            # are.
            to_classify = merged
            row = merged[1] if merged else None
        else:
            row = self._buffer.append(
                entity=entity,
                attribute=attribute,
                value=value,
                value_type=value_type,
                valid_from=eff_valid_from,
                valid_to=row_valid_to,
                frame=frame,
                status=status,
                confidence=item.get("confidence"),
                role=write_role,
            )
            out.append(row)
            to_classify = [row]
            if is_manual_semantics_row:
                self._semantics.rebuild()

        # 11. Side rows, in their existing order.
        if row is not None and demoted_vf is not None:
            # The per-item story-time coordinate the cursor overrode — preserved
            # losslessly (META_ATTRIBUTES-hidden) for host promotion to a typed
            # content fact (year/era) if wanted (INGEST-LATENCY-V2 Win 3).
            out.append(
                self._buffer.append(
                    entity=row.id, attribute="source_valid_from", value=demoted_vf,
                    status="inferred", role=self._role,
                )
            )
        if row is not None and receipt:
            out.append(
                self._buffer.append(
                    entity=row.id, attribute="canonicalized_from", value=receipt,
                    status="inferred", role=self._role,
                )
            )
        if row is not None and item.get("source_doc"):
            out.append(
                self._buffer.append(
                    entity=row.id, attribute="source", value=str(item["source_doc"]),
                    status=status, role=self._role,
                )
            )
        if row is not None and item.get("caused_by"):
            # Side-channel entity edge: same malformed-id gate as the main row
            # (SHAPE-FIX-V1 4a, Cx final) — a phantom cause never enters.
            caused_by = str(item["caused_by"])
            if not ID_RE.fullmatch(caused_by):
                self._record_skip(entity, "caused_by", caused_by, "malformed_id")
            else:
                out.append(
                    self._buffer.append(
                        entity=row.id, attribute="caused_by", value=caused_by,
                        value_type="entity", status="inferred", role=self._role,
                        # The effect-edge rides in its effect's frame: a non-canon
                        # effect's cause must be reachable from a frame-scoped read
                        # (else the situation lens false-deads it — Codex post-impl).
                        frame=frame,
                    )
                )
        if row is not None and self._observe_mode and not timeless:
            # The A2 rider: wall-clock learned-at is a gate invariant here.
            out.append(
                self._buffer.append(
                    entity=row.id, attribute="learned_at_wallclock",
                    value=self._clock(), status="observed", role=self._role,
                )
            )
        for alias in item.get("aliases", []):
            # GATE-AUTHORITY-V1 §4: a member that is not a non-empty string is
            # dropped with a receipt; the item's other rows still land.
            if isinstance(alias, str) and alias.strip():
                self._registry.add_alias(identity_subject, alias, status=status)
            else:
                self._record_skip(identity_subject, "alias", alias, "invalid_alias")
        if row is not None and item.get("correction"):
            # The proposal is itself logged (auditable; the promotion's
            # receipts chain ends here, at the utterance's chunk).
            out.append(
                self._buffer.append(
                    entity=row.id, attribute="correction_proposal", value=True,
                    status="inferred", role=self._role,
                )
            )
        if item.get("same_as"):
            # 036/019: an extractor holds single-call context — identity
            # merges are PROPOSED here, promoted where the whole world is
            # in view (promote_identity_proposals / self-check / tier-2).
            # Same malformed-id gate as the main row (SHAPE-FIX-V1 4a).
            same_as = str(item["same_as"])
            if not ID_RE.fullmatch(same_as):
                self._record_skip(identity_subject, "same_as", same_as, "malformed_id")
            else:
                self._registry.maybe_same_as(identity_subject, same_as,
                                             evidence="extractor late binding")
        # 12. Classification.
        for written in to_classify:
            if self.classify_inline:
                self._classifier.classify(written)
            elif self._classify_collect is not None:
                self._classify_collect.append(written)   # batched at end of the call
        return out

    def _merge_raw_same_as(
        self, entity: str, value: Any, value_type: str, frame: str
    ) -> list[Assertion] | None:
        """A raw `same_as` item is the guarded merge (GATE-AUTHORITY-V1 §2):
        the same body as the porcelain `merge` verb, on the raw ids, with
        evidence "same_as item". Its value must be a well-formed id string
        given as an entity, whatever `value_type` says — text, an id-shaped
        typo, or an id the item itself marks `literal` (which `closure()`
        would ignore) is `malformed_id`; identity is not perspectival, so it
        must be canon (`same_as_not_canon`); a hard veto skips it
        (`merge_vetoed`, with the merge receipt's veto and blocking edges).
        Returns the merge's rows in append order — none for a pair already
        merged, which is neither a write nor a skip — or None after a skip.
        The rows are `inferred` whatever the item's status: one merge shape,
        one provenance."""
        if not (value_type == "entity" and isinstance(value, str)
                and ID_RE.fullmatch(value)):
            self._record_skip(entity, "same_as", value, "malformed_id")
            return None
        if frame != CANON:
            self._record_skip(entity, "same_as", value, "same_as_not_canon",
                              detail={"field": "frame", "value": frame})
            return None
        receipt, rows = self._registry._guarded_merge(entity, value, "same_as item")
        if receipt["outcome"] == "vetoed":
            self._record_skip(entity, "same_as", value, "merge_vetoed",
                              detail={"veto": receipt["reason"],
                                      "blocking_edges": receipt["blocking_edges"]})
            return None
        return rows

    # ---------------------------------------------------------- extracted

    def extract(self, text: str, context: str = "",
                extract: str = "full", pov: str | None = None) -> list[dict[str, Any]]:
        """READ-ONLY extraction (INGEST-LATENCY-V2 Win 2): build the prompt, call
        the model, return the raw extracted item dicts. NO buffer write, no
        canonicalization/cursor/resolution (those happen in
        `ingest_structured`/`_ingest_item`). Stateless → safe to call
        concurrently: the host parallelizes N `extract()` calls in its own
        runtime (with its concurrency cap) then `ingest_structured()`s the
        results SERIALLY (the append-only writes stay serial). `extract` selects
        the full|lean rules block. ``pov`` (SHAPE-FIX-V1 4c): the viewpoint
        entity id — deixis pronouns bind to it instead of minting phantoms.
        Id-validated BEFORE prompt interpolation (never ride an unvalidated
        string into the model)."""
        if self._model is None:
            raise RuntimeError("no model callable injected; use ingest_structured")
        rules = _EXTRACT_RULES_LEAN if extract == "lean" else _EXTRACT_RULES_FULL
        if pov is not None:
            if not ID_RE.fullmatch(pov):
                raise ValueError(f"pov {pov!r} is not a valid entity id")
            rules += (
                # The FULL deictic family incl. possessives (HD 126: "my hand"
                # once bound sideways to the nearest NPC — fabricated canon).
                # Scoped per Cx 570: singular deixis is exclusively the POV;
                # plural deixis INCLUDES the POV without proving exclusive
                # ownership or licensing guessed members.
                f"- Viewpoint deixis: I, me, my, mine, myself — and you, your, "
                f"yours when the narration addresses the viewpoint character — "
                f"refer to {pov}; never mint a new entity for them, and a "
                f"singular possessee (my hand, your coat) is NEVER attributed "
                f"to any other present character. Plural we, us, our, ours "
                f"INCLUDE {pov}: never guess the other members and never "
                f"rebind the plural wholesale to a nearby character.\n"
            )
        prompt = f"{rules}{context}\n\nPASSAGE:\n{text}"
        # RAW output, verbatim (INGEST-LATENCY-V2; Cx 545): extract() returns the
        # model's item dicts untouched — including an explicit frame="canon"
        # stamp. Canon-vs-absent is equivalent at the INGEST GATE only; a raw
        # consumer auditing/persisting extraction output must see what the model
        # said. Re-targeting a batch (staging/quarantine) is host policy over a
        # COPY — see ADOPTION's strip idiom and the Receipt warning.
        return self._model(prompt, task_schema(_EXTRACT_SCHEMA))["items"]

    def ingest(self, text: str, context: str = "", frame: str | None = None,
               classify: str = "inline", extract: str = "full",
               cursor_authoritative: bool = False,
               pov: str | None = None) -> list[Assertion]:
        """Model-backed extraction through the same gate (= `extract` then
        `ingest_structured`, behavior-identical). ``frame`` is the DEFAULT frame for
        extracted rows that carry none (letter 028) — extracted items stamping their
        own frame (incl. an explicit canon) keep it; see ingest_structured. ``classify`` (HD 079): inline|batch|
        defer|rules durability. ``extract`` (HD 082): full|lean rules.
        ``cursor_authoritative`` (HD 084): the cursor governs valid_from (bible
        source-ingest); see ingest_structured. ``pov`` (SHAPE-FIX-V1 4c): the
        viewpoint entity id for deixis binding."""
        items = self.extract(text, context, extract, pov=pov)
        # MOVED-EVENT-V1 §B.3: the model path is prose-authored — the engine
        # authors movement timestamps, never the model. A host replicating this
        # path via extract()->ingest_structured() must likewise pass
        # extracted=True (ADOPTION/HOST-DISCIPLINE).
        return self.ingest_structured(
            items, frame=frame, classify=classify,
            cursor_authoritative=cursor_authoritative, extracted=True,
        )
