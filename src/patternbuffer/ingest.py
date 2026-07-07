"""The ingest gate (whitepaper §10/§17): the ONLY path for stated truth.

Pipeline per item: canonicalize the attribute (receipts in the log, map
in a rebuildable sidecar) -> identity-resolve -> stamp valid_time from
the scene cursor -> role-checked append -> classify. The scene cursor is
the pose; anchoring never claims more precision than was observed.

A2 rider (whitepaper amendment log): in observe_or_unknown worlds the
gate stamps a wall-clock learned-at meta-assertion on every non-timeless
write — staleness decay computes from real time and silently breaks
without it.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import Classifier
from patternbuffer.codec import decode_value
from patternbuffer.identity import IdentityRegistry
from patternbuffer.model import ATTR_PREFIX, CANON, SEMANTICS_PREDICATES, Assertion
from patternbuffer.roles import WriterRole
from patternbuffer.semantics import AttributeSemantics

logger = logging.getLogger(__name__)

# The id grammar (SHAPE-FIX-V1 4a): namespaced snake_case, no stray slashes.
# A malformed id (person:/you) is SKIPPED with a typed receipt, never
# normalized — guessing person:you would manufacture the phantom well-formed.
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*:[a-z0-9_:]+$")

# Built-in attribute aliases: the fold key must never fragment. Domain
# vocabulary emerges freely; these structural repairs are fixed.
_BUILTIN_ALIASES = {
    "inside": "in",
    "located_in": "in",
    "location": "in",
    "contained_in": "in",
    "within": "in",
    "wearing": "worn_by",  # direction repaired by the extractor contract
    "holds": "held_by",
    "connected_to": "connects_to",
    "adjacent": "adjacent_to",
    "feature_of": "part_of",      # compositional axis (PLACE-FEATURE-ABSTRACTION-V1)
    "component_of": "part_of",
    "type": "kind",
    "is_a": "kind",
}

_EXTRACT_SCHEMA = {
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
    "- attributes: use 'in' for all containment/location; 'connects_to' for "
    "passage; 'kind' for what a thing is; domain attributes freely otherwise.\n"
    "- value_type 'entity' when the value is another entity id.\n"
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
    "- TIME: timeless=true ONLY for identity and structure (kind, names, "
    "fixed adjacency). Everything that happens or holds-at-a-time gets "
    "valid_from on the provided timeline.\n"
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
    "- attributes: 'in' for containment/location; 'connects_to' for passage; "
    "'kind' for what a thing is; domain attributes otherwise.\n"
    "- value_type 'entity' when the value is another entity id.\n"
    "- FRAMES: world facts are frame 'canon' (give their true historical "
    "valid_from even if revealed late); use 'knows:<person_id>' ONLY for the "
    "extra fact that a character learned something, never instead of canon.\n"
    "- aliases: attach referring expressions used for an entity.\n"
    "- ALWAYS extract location changes: X moves/leaves/arrives => a new 'in' "
    "row for X. Presence and departure are core state, never atmosphere "
    "(a departure that goes unrecorded makes presence lie).\n"
    "- timeless=true ONLY for identity/structure (kind, names, fixed adjacency); "
    "everything else gets valid_from.\n"
    "- NEVER invent: extract only what the text supports; atmosphere is not an "
    "assertion.\n"
    "- The narrative voice is not an entity: never emit person: entities for "
    "the narrator, an unnamed speaker, or the audience. Never mint a person "
    "from a bare pronoun; if a pronoun's referent is unknown, skip that "
    "assertion.\n"
)

_SEMANTICS_HINT_KEYS = ("arity", "relation_family", "fold_policy")
_SEMANTICS_DECL_KEYS = (*_SEMANTICS_HINT_KEYS, "structural")


@dataclass(frozen=True)
class SkipRecord:
    """An edge skipped at the gate (INGEST-HARDENING-V1 Part B): a single
    structurally-invalid edge (cycle / self-edge / lateral self-loop) dropped
    with a reason, while the rest of the chunk ingests. No silent caps — the
    host reads these off the porcelain Receipt's `skipped`."""

    entity: str
    attribute: str
    value: Any
    reason: str


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
        self._alias_map: dict[str, str] = dict(_BUILTIN_ALIASES)
        self._rebuild_alias_map()

    # -------------------------------------------------- canonicalization

    def _rebuild_alias_map(self) -> None:
        """The map is a sidecar judgment, rebuildable from the receipts in
        the log (spec §3.7, letter 002 Q6)."""
        self._alias_map = dict(_BUILTIN_ALIASES)
        for row in self._buffer.visible(attribute="canonicalized_from"):
            if isinstance(row.value, str) and "->" in row.value:
                src, dst = row.value.split("->", 1)
                self._alias_map[src.strip()] = dst.strip()

    def add_attribute_alias(self, alias: str, canonical: str) -> None:
        self._alias_map[alias.strip().lower()] = canonical

    def _canonicalize(self, attribute: str) -> tuple[str, str | None]:
        """Returns (canonical, receipt-or-None)."""
        attr = attribute.strip().lower().replace(" ", "_")
        if self._semantics.is_structural(attr) or attr not in self._alias_map:
            return attr, None
        canonical = self._alias_map[attr]
        return canonical, f"{attr}->{canonical}"

    # ---------------------------------------------------- attr semantics

    @staticmethod
    def _semantics_payload(source: dict[str, Any], keys) -> dict[str, Any]:
        return {k: source[k] for k in keys if k in source and source[k] is not None}

    def _maybe_declare_attribute(self, attribute: str, item: dict[str, Any]) -> list[Assertion]:
        """Emit first-use attr:* declarations before the triggering data row."""
        if self._semantics.is_core(attribute) or self._semantics.is_declared(attribute):
            return []
        declaration = self._semantics_payload(item, _SEMANTICS_HINT_KEYS)
        if not declaration and attribute not in self._attribute_default_checked:
            self._attribute_default_checked.add(attribute)
            if self._attribute_default is not None:
                default = self._attribute_default(attribute)
                if default:
                    declaration = self._semantics_payload(default, _SEMANTICS_DECL_KEYS)
        if not declaration:
            return []

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

    # -------------------------------------------------------- structured

    def ingest_structured(
        self, items: list[dict[str, Any]], frame: str | None = None,
        classify: str = "inline", cursor_authoritative: bool = False,
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
        remains the transitive-cycle backstop, as in the harness build)."""
        if classify not in ("inline", "batch", "defer", "rules"):
            raise ValueError(f"unknown classify mode {classify!r}")
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
            appended: list[Assertion] = []
            for item in items:
                if frame is not None and "frame" not in item:
                    item = {**item, "frame": frame}
                appended.extend(self._ingest_item(item))
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

    def _record_skip(self, entity: str, attribute: str, value: Any, reason: str) -> None:
        logger.warning("ingest skipped edge: %s · %s · %r — %s",
                       entity, attribute, value, reason)
        if self._skipped is not None:
            self._skipped.append(SkipRecord(entity, attribute, value, reason))

    def _ingest_item(self, item: dict[str, Any]) -> list[Assertion]:
        out: list[Assertion] = []
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
            "entity" if isinstance(value, str) and _ID_RE.fullmatch(value)
            else "literal"
        )
        timeless = bool(item.get("timeless", False))
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

        # Authority gate FIRST (INGEST-HARDENING-V1 Cx final): an authority
        # violation (generated-into-canon/knows:) must RAISE even if the row is
        # also a structurally-invalid edge — the skip must never swallow it.
        status = item.get("status", "stated")
        write_role = self._role
        if status == "generated":
            frame_target = item.get("frame", CANON)
            if frame_target == CANON or frame_target.startswith("knows:"):
                raise ValueError(
                    "generated provenance through the gate is permitted only "
                    "into host-owned named frames (e.g. plot:*) — never canon "
                    "or knows:* (letter 029 guard)"
                )
            if self._resolver_role is None:
                raise ValueError("no resolver authority wired for generated rows")
            write_role = self._resolver_role

        # Malformed-id gate (SHAPE-FIX-V1 4a): AFTER the authority gate (an
        # authority violation must still raise, never be swallowed by a skip —
        # the INGEST-HARDENING ordering), BEFORE the edge guard — and on the
        # RAW ids, before resolution touches them (Cx final).
        if not _ID_RE.fullmatch(entity) or (
            value_type == "entity" and isinstance(value, str)
            and not _ID_RE.fullmatch(value)
        ):
            self._record_skip(entity, attribute, value, "malformed_id")
            return out
        entity = self._registry.resolve(entity)
        if value_type == "entity" and isinstance(value, str):
            value = self._registry.resolve(value)

        # Edge-granular structural guard (Part B): a single invalid edge
        # (containment cycle / self-edge / lateral self-loop) is SKIPPED with a
        # typed receipt — the invariant holds (it never enters) and the rest of
        # the chunk still ingests. (Authority failures already raised above.)
        skip = self._edge_skip_reason(
            entity, attribute, value, value_type,
            item.get("frame", CANON), None if timeless else valid_from,
        )
        if skip is not None:
            self._record_skip(entity, attribute, value, skip)
            return out  # nothing appended

        is_manual_semantics_row = (
            entity.startswith(ATTR_PREFIX) and attribute in SEMANTICS_PREDICATES
        )
        if not is_manual_semantics_row:
            out.extend(self._maybe_declare_attribute(attribute, item))

        row = self._buffer.append(
            entity=entity,
            attribute=attribute,
            value=value,
            value_type=value_type,
            valid_from=None if timeless else valid_from,
            valid_to=item.get("valid_to"),
            frame=item.get("frame", CANON),
            status=status,
            confidence=item.get("confidence"),
            role=write_role,
        )
        out.append(row)
        if is_manual_semantics_row:
            self._semantics.rebuild()
        if demoted_vf is not None:
            # The per-item story-time coordinate the cursor overrode — preserved
            # losslessly (META_ATTRIBUTES-hidden) for host promotion to a typed
            # content fact (year/era) if wanted (INGEST-LATENCY-V2 Win 3).
            out.append(
                self._buffer.append(
                    entity=row.id, attribute="source_valid_from", value=demoted_vf,
                    status="inferred", role=self._role,
                )
            )
        if receipt:
            out.append(
                self._buffer.append(
                    entity=row.id, attribute="canonicalized_from", value=receipt,
                    status="inferred", role=self._role,
                )
            )
        if item.get("source_doc"):
            out.append(
                self._buffer.append(
                    entity=row.id, attribute="source", value=str(item["source_doc"]),
                    status=item.get("status", "stated"), role=self._role,
                )
            )
        if item.get("caused_by"):
            # Side-channel entity edge: same malformed-id gate as the main row
            # (SHAPE-FIX-V1 4a, Cx final) — a phantom cause never enters.
            caused_by = str(item["caused_by"])
            if not _ID_RE.fullmatch(caused_by):
                self._record_skip(entity, "caused_by", caused_by, "malformed_id")
            else:
                out.append(
                    self._buffer.append(
                        entity=row.id, attribute="caused_by", value=caused_by,
                        value_type="entity", status="inferred", role=self._role,
                        # The effect-edge rides in its effect's frame: a non-canon
                        # effect's cause must be reachable from a frame-scoped read
                        # (else the situation lens false-deads it — Codex post-impl).
                        frame=item.get("frame", CANON),
                    )
                )
        if self._observe_mode and not timeless:
            # The A2 rider: wall-clock learned-at is a gate invariant here.
            out.append(
                self._buffer.append(
                    entity=row.id, attribute="learned_at_wallclock",
                    value=self._clock(), status="observed", role=self._role,
                )
            )
        for alias in item.get("aliases", []):
            self._registry.add_alias(entity, alias, status=item.get("status", "stated"))
        if item.get("correction"):
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
            if not _ID_RE.fullmatch(same_as):
                self._record_skip(entity, "same_as", same_as, "malformed_id")
            else:
                self._registry.maybe_same_as(entity, same_as,
                                             evidence="extractor late binding")
        if self.classify_inline:
            self._classifier.classify(row)
        elif self._classify_collect is not None:
            self._classify_collect.append(row)   # batched at end of the call
        return out

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
            if not _ID_RE.fullmatch(pov):
                raise ValueError(f"pov {pov!r} is not a valid entity id")
            rules += (
                f"- First/second-person pronouns (I, you, we) referring to the "
                f"viewpoint character are {pov} — never mint a new entity for "
                f"them.\n"
            )
        prompt = f"{rules}{context}\n\nPASSAGE:\n{text}"
        return self._model(prompt, _EXTRACT_SCHEMA)["items"]

    def ingest(self, text: str, context: str = "", frame: str | None = None,
               classify: str = "inline", extract: str = "full",
               cursor_authoritative: bool = False,
               pov: str | None = None) -> list[Assertion]:
        """Model-backed extraction through the same gate (= `extract` then
        `ingest_structured`, behavior-identical). ``frame`` re-targets extracted
        rows to a named frame (letter 028). ``classify`` (HD 079): inline|batch|
        defer|rules durability. ``extract`` (HD 082): full|lean rules.
        ``cursor_authoritative`` (HD 084): the cursor governs valid_from (bible
        source-ingest); see ingest_structured. ``pov`` (SHAPE-FIX-V1 4c): the
        viewpoint entity id for deixis binding."""
        items = self.extract(text, context, extract, pov=pov)
        return self.ingest_structured(
            items, frame=frame, classify=classify,
            cursor_authoritative=cursor_authoritative,
        )
