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
    "properties": {"lines": {"type": "array", "items": {"type": "string"}}},
    "required": ["lines"],
}

_PASS0_PROMPT = """\
Read the source text and produce the WORLD REGISTRY: the complete skeleton
an extraction pass will be pinned to. Output REGISTRY LINES only, one per
line — no facts, no events, no states:

  E|<entity_id>|<kind>|<names ;-sep>|<aliases ;-sep>|<anchors ;-sep>
  A|<canonical_attribute>|<variant phrasings ;-sep>
  O|<timeline origin: what day 0 is, from the text's own cues>
  N|<anchor label>|<day offset number>     (negative = before origin)
  P|<place_id>|<place_id>                  (a traversable connects_to edge)

Rules:
- ENTITIES: every person, place, object, organization, document, and named
  event the text establishes. One id per individual across the WHOLE text:
  someone unnamed early who is named later is ONE entry whose aliases carry
  every referring expression used anywhere. Ids namespaced person:/place:/
  obj:/org:/doc:/event: + snake_case. Anchors = roles, recurring locations,
  distinguishing features (identity signals, not facts).
- SPACE, exhaustively: containers nest — emit entities for rooms AND the
  furniture in them AND the compartments in the furniture (a desk and each
  of its drawers are separate entities) when the text touches them. When
  one referring expression may denote two distinct things the text later
  splits ("the vault"), put that shared alias on BOTH entities.
- P| edges are TRAVERSABLE passage only, exactly as the text supports.
  A defunct, sealed, or impassable structure (a dead elevator, a bricked
  door) gets an E| entry but NEVER a P| edge through it — vertical or
  physical proximity is not connectivity.
- ATTRIBUTES: every fluent extraction will need, ONE canonical snake_case
  name each, variants listed (canonical working_reactors covers
  "reactors; reactor count"). Fixed structural names already exist: kind,
  in, connects_to, adjacent_to, caused_by, name, alias — do not redefine.
- TIMELINE: one O| line; every datable anchor as an N| line.
- Do not invent. The registry pins names; it asserts no facts.
{extend_note}
SOURCE TEXT:
{text}
"""

_EXTEND_NOTE = """
You are EXTENDING an existing registry. Its entries are PINNED — do not
rename, re-kind, or duplicate them; emit only genuinely NEW entities,
attributes, anchors, or edges. New aliases for an existing id: re-emit
that id's E| line with only the new aliases in the alias field.

EXISTING REGISTRY (ids and canonical attributes):
{prior}
"""


def _split_field(field: str) -> list[str]:
    return [part.strip() for part in field.split(";") if part.strip()]


def parse_registry_lines(
    lines: list[str], world_id: str
) -> tuple[WorldRegistry, list[str]]:
    """Deterministic parse of registry lines. Returns (registry, rejects)."""
    reg = WorldRegistry(world_id=world_id)
    rejects: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        kind, _, rest = line.partition("|")
        fields = rest.split("|")
        try:
            if kind == "E":
                eid = fields[0].strip()
                if not eid or ":" not in eid:
                    raise ValueError("bad entity id")
                card = reg.entities.setdefault(
                    eid, EntityCard(kind=fields[1].strip() if len(fields) > 1 else "thing")
                )
                if len(fields) > 2:
                    card.names += [n for n in _split_field(fields[2]) if n not in card.names]
                if len(fields) > 3:
                    card.aliases += [a.lower() for a in _split_field(fields[3])
                                     if a.lower() not in card.aliases]
                if len(fields) > 4:
                    card.anchors += [a for a in _split_field(fields[4]) if a not in card.anchors]
            elif kind == "A":
                canonical = fields[0].strip()
                if not canonical:
                    raise ValueError("bad attribute")
                for variant in _split_field(fields[1]) if len(fields) > 1 else []:
                    v = variant.lower().replace(" ", "_")
                    if v != canonical:
                        reg.attributes.setdefault(v, canonical)
            elif kind == "O":
                reg.timeline.origin = rest.strip()
            elif kind == "N":
                reg.timeline.anchors[fields[0].strip()] = float(fields[1])
            elif kind == "P":
                a, b = fields[0].strip(), fields[1].strip()
                if not a or not b:
                    raise ValueError("bad edge")
                if (a, b) not in reg.places:
                    reg.places.append((a, b))
            else:
                raise ValueError(f"unknown line kind {kind!r}")
        except (IndexError, ValueError) as exc:
            rejects.append(f"{line} ({exc})")
    return reg, rejects


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
        compact = "\n".join(
            [f"E|{eid}|{c.kind}" for eid, c in sorted(prior.entities.items())]
            + [f"A|{canon}" for canon in sorted(set(prior.attributes.values()))]
        )
        extend_note = _EXTEND_NOTE.format(prior=compact)
    out = model(_PASS0_PROMPT.format(extend_note=extend_note, text=text), _PASS0_SCHEMA)

    fresh, rejects = parse_registry_lines(out["lines"], world_id)
    if rejects:
        logger.warning("pass-0: %d rejected registry line(s): %s",
                       len(rejects), rejects[:5])

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
