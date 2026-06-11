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
from patternbuffer.model import CANON, STRUCTURAL_PREDICATES, Assertion
from patternbuffer.roles import WriterRole

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
                    "value_type": {"enum": ["entity", "literal", "unresolved"]},
                    "frame": {"type": "string"},
                    "status": {"enum": ["stated", "observed", "inferred", "assumed"]},
                    "timeless": {"type": "boolean"},
                    "valid_from": {"type": ["number", "null"]},
                    "confidence": {"type": ["number", "null"]},
                    "source_doc": {"type": ["string", "null"]},
                    "caused_by": {"type": ["string", "null"]},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["entity", "attribute", "value"],
            },
        }
    },
    "required": ["items"],
}


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
    ) -> None:
        self._buffer = buffer
        self._classifier = classifier
        self._registry = registry
        self._role = role
        self._model = model
        self._observe_mode = observe_mode
        self._clock = clock
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
        if attr in STRUCTURAL_PREDICATES or attr not in self._alias_map:
            return attr, None
        canonical = self._alias_map[attr]
        return canonical, f"{attr}->{canonical}"

    # -------------------------------------------------------- structured

    def ingest_structured(self, items: list[dict[str, Any]]) -> list[Assertion]:
        """The no-model gate entry: pre-extracted items, full discipline.
        Synthetic test content only — never bible-derived (spec §6)."""
        appended: list[Assertion] = []
        for item in items:
            appended.extend(self._ingest_item(item))
        return appended

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
        row = self._buffer.append(
            entity=entity,
            attribute=attribute,
            value=value,
            value_type=value_type,
            valid_from=None if timeless else valid_from,
            valid_to=item.get("valid_to"),
            frame=item.get("frame", CANON),
            status=item.get("status", "stated"),
            confidence=item.get("confidence"),
            role=self._role,
        )
        out.append(row)
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
        self._classifier.classify(row)
        return out

    # ---------------------------------------------------------- extracted

    def ingest(self, text: str, context: str = "") -> list[Assertion]:
        """Model-backed extraction through the same gate."""
        if self._model is None:
            raise RuntimeError("no model callable injected; use ingest_structured")
        prompt = (
            "Extract world-state assertions from this narrative passage.\n"
            "Return triples (entity, attribute, value). Rules:\n"
            "- entity ids namespaced: person:/place:/obj:/event:/doc: + snake_case.\n"
            "- attributes: use 'in' for all containment/location; 'connects_to' for "
            "passage; 'kind' for what a thing is; domain attributes freely otherwise.\n"
            "- value_type 'entity' when the value is another entity id.\n"
            "- frame 'canon' for narrator-established fact; 'knows:<person_id>' for "
            "what a character learns; document claims get source_doc=<doc id>.\n"
            "- status: 'stated' for asserted fact, 'inferred' for character inference, "
            "'assumed' for working assumption.\n"
            "- mark permanent facts timeless=true; give events/states valid_from on "
            "the provided timeline if the text anchors them.\n"
            "- NEVER invent: extract only what the text supports. Atmosphere and "
            "sensory texture are not assertions.\n"
            f"{context}\n\nPASSAGE:\n{text}"
        )
        out = self._model(prompt, _EXTRACT_SCHEMA)
        return self.ingest_structured(out["items"])
