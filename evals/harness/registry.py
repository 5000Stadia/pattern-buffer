"""Pass-0 of INGEST-V2: the world registry (spec §3).

`establish()` builds or extends a WorldRegistry from source text — the
batch calling pattern passes a whole document once with prior=None; the
incremental pattern (tracking mode, live play) passes one turn with the
existing registry. The interface supports both from day one; only batch
is exercised in this chapter.

The registry is a persisted, world-partitioned harness artifact
(registry.json). It never enters the log itself; its content seeds the
gate as phase 1 of the pipeline's single commit (spec §3.3).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class RegistryWorldMismatch(ValueError):
    """A registry artifact was used against the wrong world (spec §3.3)."""


@dataclass
class EntityCard:
    kind: str
    names: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)  # roles, recurring locations, features


@dataclass
class TimelineSpec:
    origin: str = ""                                  # prose definition of t=0
    anchors: dict[str, float] = field(default_factory=dict)  # label -> offset


@dataclass
class WorldRegistry:
    world_id: str                       # partition key (whitepaper §16); checked on every use
    entities: dict[str, EntityCard] = field(default_factory=dict)
    attributes: dict[str, str] = field(default_factory=dict)  # alias/variant -> canonical
    timeline: TimelineSpec = field(default_factory=TimelineSpec)
    places: list[tuple[str, str]] = field(default_factory=list)  # connects_to edges

    # ------------------------------------------------------------ persist

    def save(self, path: str | Path) -> None:
        payload = asdict(self)
        payload["places"] = [list(p) for p in self.places]
        Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True))

    @classmethod
    def load(cls, path: str | Path, expect_world_id: str) -> "WorldRegistry":
        raw = json.loads(Path(path).read_text())
        if raw.get("world_id") != expect_world_id:
            raise RegistryWorldMismatch(
                f"registry at {path} belongs to world {raw.get('world_id')!r}, "
                f"not {expect_world_id!r}"
            )
        return cls(
            world_id=raw["world_id"],
            entities={k: EntityCard(**v) for k, v in raw["entities"].items()},
            attributes=dict(raw["attributes"]),
            timeline=TimelineSpec(**raw["timeline"]),
            places=[tuple(p) for p in raw["places"]],
        )

    # ------------------------------------------------------------- update

    def merge(self, other: "WorldRegistry") -> None:
        """Extend in place. New entities/attributes/edges accrete; existing
        entries are never overwritten (pass-0 decisions are pinned — a
        conflicting later judgment is a registry escape to investigate,
        not a silent rewrite)."""
        if other.world_id != self.world_id:
            raise RegistryWorldMismatch(
                f"cannot merge registry of {other.world_id!r} into {self.world_id!r}"
            )
        for eid, card in other.entities.items():
            if eid in self.entities:
                mine = self.entities[eid]
                mine.names += [n for n in card.names if n not in mine.names]
                mine.aliases += [a for a in card.aliases if a not in mine.aliases]
                mine.anchors += [a for a in card.anchors if a not in mine.anchors]
            else:
                self.entities[eid] = card
        for alias, canonical in other.attributes.items():
            self.attributes.setdefault(alias, canonical)
        self.timeline.anchors.update(
            {k: v for k, v in other.timeline.anchors.items()
             if k not in self.timeline.anchors}
        )
        if not self.timeline.origin:
            self.timeline.origin = other.timeline.origin
        for edge in other.places:
            if edge not in self.places:
                self.places.append(edge)


_PASS0_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string"},
                    "names": {"type": "array", "items": {"type": "string"}},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "anchors": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "kind"],
            },
        },
        "attributes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "canonical": {"type": "string"},
                    "variants": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["canonical"],
            },
        },
        "timeline": {
            "type": "object",
            "properties": {
                "origin": {"type": "string"},
                "anchors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"label": {"type": "string"}, "offset": {"type": "number"}},
                        "required": ["label", "offset"],
                    },
                },
            },
            "required": ["origin"],
        },
        "places": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
                "required": ["a", "b"],
            },
        },
    },
    "required": ["entities", "attributes", "timeline", "places"],
}

_PASS0_PROMPT = """\
Read the source text and produce the WORLD REGISTRY: the complete skeleton
an extraction pass will be pinned to. Output only the registry — no facts,
no events, no states. Rules:

- ENTITIES: every person, place, object, organization, document, and named
  event that the text establishes. One id per individual across the WHOLE
  text: if someone unnamed early is named later, ONE entry whose aliases
  carry every referring expression used anywhere ("the clerk with the tin
  ear" and "Ilsa Renn" are one entity). Ids namespaced person:/place:/obj:/
  org:/doc:/event: + snake_case. anchors = roles, recurring locations,
  distinguishing features (for identity, not facts).
- ATTRIBUTES: every fluent the extraction will need, ONE canonical
  snake_case name each, with the variant phrasings the text suggests
  (e.g. canonical working_reactors covers "reactors", "reactor count").
  Fixed structural names already exist: kind, in, connects_to, adjacent_to,
  caused_by, name, alias — do not redefine them.
- TIMELINE: define the origin (t=0) from the text's own cues and list every
  datable anchor as a day offset (negative = before origin).
- PLACES: connects_to edges exactly as the text supports (routes, stairs,
  gates). Never an edge the text doesn't state — proximity is not
  connectivity.
- Do not invent. The registry pins names; it asserts no facts.
{extend_note}
SOURCE TEXT:
{text}
"""

_EXTEND_NOTE = """
You are EXTENDING an existing registry. Its current entries are below and
are PINNED — do not rename, re-kind, or duplicate them; emit only genuinely
new entities/attributes/anchors/edges, and new aliases for existing ids go
on those ids.

EXISTING REGISTRY:
{prior}
"""


def establish(
    text: str,
    model: Callable[[str, dict], Any],
    world_id: str,
    prior: WorldRegistry | None = None,
) -> WorldRegistry:
    """Establish (prior=None) or extend (prior=registry) the registry."""
    extend_note = ""
    if prior is not None:
        if prior.world_id != world_id:
            raise RegistryWorldMismatch(
                f"prior registry is for {prior.world_id!r}, not {world_id!r}"
            )
        compact = {
            "entities": {eid: {"kind": c.kind, "names": c.names, "aliases": c.aliases}
                         for eid, c in prior.entities.items()},
            "attributes": prior.attributes,
            "timeline_origin": prior.timeline.origin,
        }
        extend_note = _EXTEND_NOTE.format(prior=json.dumps(compact, indent=1))
    out = model(_PASS0_PROMPT.format(extend_note=extend_note, text=text), _PASS0_SCHEMA)

    fresh = WorldRegistry(world_id=world_id)
    for e in out["entities"]:
        fresh.entities[e["id"]] = EntityCard(
            kind=e["kind"],
            names=list(e.get("names", [])),
            aliases=[a.strip().lower() for a in e.get("aliases", [])],
            anchors=list(e.get("anchors", [])),
        )
    for a in out["attributes"]:
        for variant in a.get("variants", []):
            v = variant.strip().lower().replace(" ", "_")
            if v != a["canonical"]:
                fresh.attributes[v] = a["canonical"]
    fresh.timeline = TimelineSpec(
        origin=out["timeline"]["origin"],
        anchors={t["label"]: float(t["offset"]) for t in out["timeline"].get("anchors", [])},
    )
    fresh.places = [(p["a"], p["b"]) for p in out["places"]]

    if prior is None:
        logger.info("registry established: %d entities, %d attribute aliases",
                    len(fresh.entities), len(fresh.attributes))
        return fresh
    prior.merge(fresh)
    logger.info("registry extended: now %d entities", len(prior.entities))
    return prior


def seed_items(registry: WorldRegistry) -> list[dict]:
    """The registry's gate items — phase 1 of the single commit (spec §3.3).
    Entity kinds, names, aliases, and place edges as timeless stated rows;
    attribute aliases are seeded separately via add_attribute_alias."""
    items: list[dict] = []
    for eid, card in sorted(registry.entities.items()):
        kind_item: dict = {"entity": eid, "attribute": "kind", "value": card.kind,
                           "value_type": "literal", "timeless": True}
        if card.aliases:
            kind_item["aliases"] = card.aliases
        items.append(kind_item)
        for name in card.names:
            items.append({"entity": eid, "attribute": "name", "value": name,
                          "value_type": "literal", "timeless": True})
    for a, b in registry.places:
        items.append({"entity": a, "attribute": "connects_to", "value": b,
                      "value_type": "entity", "timeless": True})
    return items
