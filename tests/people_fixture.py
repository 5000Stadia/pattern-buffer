"""A small house of people for the VIEW-PEOPLE-V1 tests and vectors (not a test module).

Canon holds a house with rooms, a wardrobe and an unattached safe, and persons in
unusual places: in a wardrobe in the bedroom, carried by another person, at the
unattached safe, in a room whose id is not in the `place:` namespace, and with no
parent at all. They carry host-named facts (posture, heading, ...) and facts
the host does not name (a face, an alibi in another `knows:` frame, a gun).
The player (`knows:person:mara`) has perceived the study, the desk and herself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from manor_fixture import KEY, E, T, _no_model  # noqa: F401  (KEY re-exported)
from patternbuffer import World

WORLD_ID = "w:people"
VF = "knows:person:mara"
OTHER_FRAME = "knows:person:butler"
ATTRS = ("posture", "heading", "activity", "gold", "name", "plan", "gear", "watching",
         "holding", "pursuing")

# ids of things the player has not perceived and that are not persons or places:
# none may appear in a document's text
UNSEEN = ("obj:wardrobe", "obj:safe", "obj:cup", "obj:gun")
# words that must never cross
SECRET_WORDS = ("scarred", "garden-zz", "stash-zz", "pistol")

CANON = [
    T("place:house", "kind", "house"),
    T("place:bedroom", "kind", "room"), E("place:bedroom", "in", "place:house"),
    T("place:kitchen", "kind", "room"), E("place:kitchen", "in", "place:house"),
    T("place:study", "kind", "room"), E("place:study", "in", "place:house"),
    T("place:hall", "kind", "room"), E("place:hall", "in", "place:house"),
    T("obj:desk", "kind", "desk"), E("obj:desk", "in", "place:study"),
    T("obj:wardrobe", "kind", "wardrobe"), E("obj:wardrobe", "in", "place:bedroom"),
    T("obj:cup", "kind", "cup"), E("obj:cup", "in", "place:kitchen"),
    # an unattached safe: a root, but not a place
    T("obj:safe", "kind", "safe"),
    # a root that IS a place, under an id outside the `place:` namespace
    T("obj:annex", "kind", "place"),
    # the player
    T("person:mara", "kind", "person"), E("person:mara", "in", "place:study"),
    T("person:mara", "posture", "standing"),
    # a person hidden in a wardrobe in the bedroom (in the house)
    T("person:butler", "kind", "person"), E("person:butler", "in", "obj:wardrobe"),
    T("person:butler", "posture", "crouching"), T("person:butler", "face", "scarred"),
    # the cook: a room, several kinds of fact, a gun she carries
    T("person:cook", "kind", "person"), E("person:cook", "in", "place:kitchen"),
    T("person:cook", "posture", "sitting"), E("person:cook", "heading", "place:hall"),
    E("person:cook", "watching", "obj:desk"), E("person:cook", "holding", "obj:cup"),
    E("person:cook", "pursuing", "person:butler"),
    T("person:cook", "activity", "peeling"), T("person:cook", "gear", {"apron": True}),
    T("person:cook", "name", "Cookie"), T("person:cook", "name", "Mrs Cook"),
    T("person:cook", "face", "scarred"),
    T("obj:gun", "kind", "pistol"), E("obj:gun", "carried_by", "person:cook"),
    # a child carried by a nanny in the kitchen: place is the kitchen, in is the nanny
    T("person:nanny", "kind", "person"), E("person:nanny", "in", "place:kitchen"),
    T("person:baby", "kind", "person"), E("person:baby", "carried_by", "person:nanny"),
    T("person:baby", "posture", "asleep"),
    # a person with no parent
    T("person:drifter", "kind", "person"), T("person:drifter", "posture", "standing"),
    # at the unattached safe
    T("person:guard", "kind", "person"), E("person:guard", "in", "obj:safe"),
    E("person:guard", "heading", "obj:safe"), T("person:guard", "posture", "kneeling"),
    # in a place that is not under the `place:` namespace
    T("person:ghost", "kind", "person"), E("person:ghost", "in", "obj:annex"),
    # a person by kind only, and a thief by owning a frame
    T("npc:smuggler", "kind", "person"), E("npc:smuggler", "in", "place:hall"),
    T("npc:smuggler", "posture", "leaning"),
    T("npc:thief", "kind", "figure"), E("npc:thief", "in", "place:hall"),
    T("npc:thief", "posture", "lurking"),
    # a person with conflicting postures at one stamp
    T("person:twin", "kind", "person"), E("person:twin", "in", "place:hall"),
    T("person:twin", "posture", "sitting", timeless=False, valid_from=1.0),
    T("person:twin", "posture", "standing", timeless=False, valid_from=1.0),
    # an accrued quantity and an unresolved fact
    T("person:nanny", "gold", 10, timeless=False, valid_from=1.0),
    T("person:nanny", "gold", 5, "delta", timeless=False, valid_from=2.0),
]
DECLARATIONS = [T("attr:gold", "fold_policy", "accrue")]
VIEW = [
    T("place:study", "kind", "room"),
    T("obj:desk", "kind", "desk"), E("obj:desk", "in", "place:study"),
    T("person:mara", "kind", "person"), E("person:mara", "in", "place:study"),
]
OTHER = [T("person:butler", "alibi", "garden-zz"), T("person:cook", "stash", "stash-zz")]
THIEF = [T("person:cook", "stash", "stash-zz")]


def build_people(tmp_path: Path, name: str = "people.world", model: Any = None) -> World:
    w = World(tmp_path / name, WORLD_ID, model=model or _no_model)
    w.porcelain.ingest_structured(DECLARATIONS, classify="rules")   # before the data
    w.ingest_structured(CANON, classify="rules")
    w.ingest_structured(
        [{"entity": "person:cook", "attribute": "plan", "value": {"policy": "deny"},
          "value_type": "unresolved"}], classify="rules")
    w.ingest_structured(VIEW, frame=VF, classify="rules")
    w.ingest_structured(OTHER, frame=OTHER_FRAME, classify="rules")
    w.ingest_structured(THIEF, frame="knows:npc:thief", classify="rules")
    return w
