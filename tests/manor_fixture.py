"""A small manor world for the VIEW-EXPORT-V1 tests and vectors (not a test module).

Canon holds the drawer's contents, a hidden butler with a gun in his coat, a
thief who owns a `knows:` frame, and secrets (`owned_by`, `made_by`, a
structured tag). The player (`knows:person:mara`) has perceived the study, the
desk, a vase and her own person, and nothing else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from patternbuffer import World

WORLD_ID = "w:manor"
VF = "knows:person:mara"
OTHER_FRAME = "knows:person:butler"
KEY = b"manor-test-key-0123456789"
OTHER_KEY = b"another-test-key-9876543210"

# every canonical id the player has NOT perceived: none may appear in a document
UNPERCEIVED = ("obj:key", "obj:ring", "obj:safe", "obj:gun", "obj:coat", "obj:loot",
               "obj:amulet", "obj:relic", "person:butler", "npc:thief", "place:hall",
               "obj:murder_weapon", "obj:vault")
SECRET_WORDS = ("butler", "thief", "murder", "pistol", "stash-zz", "the butler did it")


def T(entity: str, attribute: str, value: Any, value_type: str = "literal",
      **extra: Any) -> dict:
    """A timeless item (the default); pass ``timeless=False, valid_from=`` for a timed one."""
    item = {"entity": entity, "attribute": attribute, "value": value,
            "value_type": value_type, "timeless": True}
    item.update(extra)
    return item


def E(entity: str, attribute: str, value: str, **extra: Any) -> dict:
    return T(entity, attribute, value, "entity", **extra)


def _no_model(prompt: str, schema: dict) -> Any:
    return {"durability": "STATE", "class_confidence": 0.9, "verdicts": []}


CANON = [
    T("place:study", "kind", "room"), T("place:hall", "kind", "room"),
    T("obj:desk", "kind", "desk"), E("obj:desk", "in", "place:study"),
    T("obj:desk", "secret_note", "the butler did it"),
    # the drawer's contents
    T("obj:key", "kind", "key"), E("obj:key", "in", "obj:desk"),
    T("obj:key", "slot", "top drawer"), T("obj:key", "address", "manor/study/desk:0"),
    T("obj:key", "material", "iron"), E("obj:key", "made_by", "person:butler"),
    T("obj:key", "tag", {"owner": "person:butler"}), E("obj:key", "points_to", "obj:safe"),
    E("obj:key", "owned_by", "person:butler"), E("obj:key", "role", "obj:murder_weapon"),
    # an unperceived container, and what it holds
    T("obj:safe", "kind", "safe"), E("obj:safe", "in", "place:study"),
    T("obj:ring", "kind", "ring"), E("obj:ring", "in", "obj:safe"),
    T("obj:ring", "material", "gold"),
    # entity-valued slot / address / kind must never cross
    T("obj:amulet", "kind", "amulet"), E("obj:amulet", "in", "obj:safe"),
    E("obj:amulet", "slot", "person:butler"), E("obj:amulet", "address", "obj:vault"),
    E("obj:relic", "kind", "obj:murder_weapon"), E("obj:relic", "in", "obj:safe"),
    # persons: never emitted, never entered
    T("person:butler", "kind", "person"), E("person:butler", "in", "place:study"),
    E("obj:coat", "worn_by", "person:butler"), T("obj:coat", "kind", "coat"),
    T("obj:gun", "kind", "pistol"), E("obj:gun", "in", "obj:coat"),
    T("npc:thief", "kind", "figure"), E("npc:thief", "in", "place:study"),
    E("obj:loot", "carried_by", "npc:thief"), T("obj:loot", "kind", "loot"),
    # the player's neighbours
    T("obj:vase", "kind", "vase"), E("obj:vase", "in", "place:study"),
    T("person:mara", "kind", "person"), E("person:mara", "in", "place:study"),
]
DECLARATIONS = [
    T("attr:material", "resolvable_for", "key"), T("attr:material", "resolvable_for", "ring"),
    T("attr:made_by", "resolvable_for", "key"), T("attr:tag", "resolvable_for", "key"),
    T("attr:points_to", "resolvable_for", "key"),
]
VIEW = [
    T("place:study", "kind", "room"),
    T("obj:desk", "kind", "desk"), E("obj:desk", "in", "place:study"),
    T("obj:vase", "kind", "vase"),
    T("person:mara", "kind", "person"), E("person:mara", "in", "place:study"),
]
OTHER = [T("obj:desk", "stash", "butler-stash-zz"), T("person:butler", "kind", "person")]


def build_manor(tmp_path: Path, name: str = "manor.world", *, drawer: bool = True,
                model: Any = None) -> World:
    """The manor world. ``drawer=False`` leaves the drawer's contents out of canon."""
    w = World(tmp_path / name, WORLD_ID, model=model or _no_model)
    canon = CANON if drawer else [
        i for i in CANON if i["entity"] not in ("obj:key", "obj:safe", "obj:ring",
                                                "obj:amulet", "obj:relic")]
    w.ingest_structured(canon, classify="rules")
    w.porcelain.ingest_structured(DECLARATIONS, classify="rules")
    w.ingest_structured(VIEW, frame=VF, classify="rules")
    w.ingest_structured(OTHER, frame=OTHER_FRAME, classify="rules")
    # the thief is a point of view too (an owner of a frame, though no `person:`)
    w.ingest_structured([T("obj:desk", "stash", "thief-stash-zz")],
                        frame="knows:npc:thief", classify="rules")
    return w


def view(w: World, *items: dict) -> None:
    """Write rows into the player's view frame."""
    w.ingest_structured(list(items), frame=VF, classify="rules")


def canon(w: World, *items: dict) -> None:
    w.ingest_structured(list(items), classify="rules")
