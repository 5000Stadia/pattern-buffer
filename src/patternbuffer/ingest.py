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
import time
from dataclasses import dataclass
from typing import Any, Callable

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import Classifier
from patternbuffer.identity import IdentityRegistry
from patternbuffer.model import ATTR_PREFIX, CANON, SEMANTICS_PREDICATES, Assertion
from patternbuffer.roles import WriterRole
from patternbuffer.semantics import AttributeSemantics

logger = logging.getLogger(__name__)

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

_SEMANTICS_HINT_KEYS = ("arity", "relation_family", "fold_policy")
_SEMANTICS_DECL_KEYS = (*_SEMANTICS_HINT_KEYS, "structural")


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
        self, items: list[dict[str, Any]], frame: str | None = None
    ) -> list[Assertion]:
        """The no-model gate entry: pre-extracted items, full discipline.
        Synthetic test content only — never bible-derived (spec §6).

        ``frame`` (letter 028): default frame for items that carry none —
        the sanctioned doorway to named-frame authoring (knows:<id>
        session-zero seeding, plot: arcs). Frame is a TARGET only; every
        other gate discipline (provenance, canonicalization, cursor,
        roles) applies unchanged. Per-item frames still win."""
        appended: list[Assertion] = []
        for item in items:
            if frame is not None and "frame" not in item:
                item = {**item, "frame": frame}
            appended.extend(self._ingest_item(item))
        return appended

    def _reject_cycle(
        self, child: str, parent: str, frame: str, valid_from: float | None
    ) -> None:
        """Reject a cycle-forming containment edge before it enters the log
        (HD 002 finding 1; spec LIVE-FINDINGS §Fix 1). Both ids are already
        identity-resolved.

        Self-edges are rejected unconditionally (complete, no derived
        state). Transitive cycles are rejected as-of the new edge's own
        valid_from — best-effort: a back-dated edge that closes a cycle only
        at a different valid-time is not visible to a single write-time
        walk and remains caught by the read-time locate() guard."""
        if child == parent:
            raise ValueError(
                f"cycle-forming containment edge: {child!r} cannot contain "
                "itself (self-edge; append-only tree invariant, §4)"
            )
        if self._containment_ancestors is None:
            return
        if child in self._containment_ancestors(parent, frame, valid_from):
            raise ValueError(
                f"cycle-forming containment edge: {child!r} is already an "
                f"ancestor of {parent!r} as-of valid_from={valid_from} — "
                "containment is a single-parent tree (§4)"
            )

    def _ingest_item(self, item: dict[str, Any]) -> list[Assertion]:
        out: list[Assertion] = []
        attribute, receipt = self._canonicalize(item["attribute"])
        entity = self._registry.resolve(item["entity"])
        value = item["value"]
        value_type = item.get("value_type") or (
            "entity" if isinstance(value, str) and ":" in value else "literal"
        )
        if value_type == "entity" and isinstance(value, str):
            value = self._registry.resolve(value)
        timeless = bool(item.get("timeless", False))
        valid_from = item.get("valid_from")
        if valid_from is None and not timeless:
            valid_from = self.cursor.position  # the pose stamps the row

        is_manual_semantics_row = (
            entity.startswith(ATTR_PREFIX) and attribute in SEMANTICS_PREDICATES
        )
        if not is_manual_semantics_row:
            out.extend(self._maybe_declare_attribute(attribute, item))

        if self._semantics.is_containment(attribute) and value_type == "entity":
            self._reject_cycle(entity, value, item.get("frame", CANON),
                               None if timeless else valid_from)
        if (
            self._semantics.is_lateral(attribute)
            and value_type == "entity"
            and entity == value
        ):
            # A lateral self-loop (X connects_to X / adjacent_to X) is
            # extraction noise — it adds no edge any walk can use. Reject it
            # at the gate, the same class as the containment self-edge (#19).
            raise ValueError(
                f"lateral self-loop: {entity!r} cannot {attribute} itself"
            )
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
            out.append(
                self._buffer.append(
                    entity=row.id, attribute="caused_by", value=str(item["caused_by"]),
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
            self._registry.maybe_same_as(entity, str(item["same_as"]),
                                         evidence="extractor late binding")
        if self.classify_inline:
            self._classifier.classify(row)
        return out

    # ---------------------------------------------------------- extracted

    def ingest(self, text: str, context: str = "", frame: str | None = None) -> list[Assertion]:
        """Model-backed extraction through the same gate. ``frame``
        re-targets extracted rows to a named frame (letter 028) — used for
        seeding a character's knowledge from prose; canon discipline is
        unchanged when frame is None."""
        if self._model is None:
            raise RuntimeError("no model callable injected; use ingest_structured")
        prompt = (
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
            f"{context}\n\nPASSAGE:\n{text}"
        )
        out = self._model(prompt, _EXTRACT_SCHEMA)
        return self.ingest_structured(out["items"], frame=frame)
