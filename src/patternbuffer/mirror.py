"""The offline mirror (VIEW-EXPORT-V1): the player's view as a document, kept in
step by a signed-cursor feed.

A library module that sits OUTSIDE the engine core (the engine never imports
it), like `patternbuffer.service`. It uses the porcelain's reads, plus the
registry and the log's visibility for identity and ownership, and writes
nothing.

- `export(world, view_frame, ...)` is the whole `patternbuffer.view/1`
  document: `known` (the player's view) and `present` (drawables of unperceived
  things in the places the view covers, under keyed handles, with no meaning).
- `feed(world, view_frame, since, ...)` answers the ops that move a client's
  copy from the cursor it holds to now. Any doubt is a reset (`clear` + puts).
- `apply(document, answer)` is the pure reference every client implements.

An opt-in third layer, `people` (VIEW-PEOPLE-V1), puts persons' canon whereabouts
and host-named facts on the device for a single-player host that accepts the
exposure. It is off by default and then changes nothing.

`python -m patternbuffer.mirror export ...` writes an export for a static build,
from a read-only copy of the world file.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import hmac
import json
import logging
import math
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Callable, NamedTuple, Sequence

from patternbuffer.model import (ATTR_PREFIX, CANON, CANON_IDENTITY_EDGES,
                                 CONTAINMENT_FAMILY, MECHANISM_ATTRIBUTES,
                                 META_ATTRIBUTES, SEMANTICS_PREDICATES)
from patternbuffer.semantics import AttributeSemantics, valid_declaration

logger = logging.getLogger(__name__)

SCHEMA = "patternbuffer.view/1"
CURSOR_VERSION = 1
_CURSOR_LABEL = b"patternbuffer.view/1 cursor"
MIN_KEY_BYTES = 16
HANDLE_RE = re.compile(r"^h:[0-9a-f]{20}$")
# The folded canon kind that makes an entity a person whatever its id (spec §2).
PERSON_KIND = "person"

# The containment relations a present record may name (spec §2): the built-in
# family. Anything else a world declares is served as plain `in`.
_RELATIONS = frozenset({"in", "within", "held_by", "worn_by", "carried_by"})
_MISSING = object()

# The people layer (VIEW-PEOPLE-V1 §2): the walk up a person's containment chain
# stops after this many ancestors, and a canon kind of `place` makes a place.
PLACE_KIND = "place"
MAX_CHAIN_DEPTH = 32
# An attribute a host may not name as a person fact: position is `place` and
# `in`; `kind` is the person test's own key; the rest is the same barred set
# the service refuses a recorder (mechanism, semantics, canon identity, meta).
_PEOPLE_BARRED = (CONTAINMENT_FAMILY | {"kind"} | MECHANISM_ATTRIBUTES
                  | SEMANTICS_PREDICATES | CANON_IDENTITY_EDGES | META_ATTRIBUTES)
_Q_RE = re.compile(r"^[0-9a-f]{64}$")


# ----------------------------------------------------------------- helpers


def canonical_json(obj: Any) -> str:
    """The one serialization every digest, comparison and file uses: sorted
    keys, no spaces, non-ASCII kept (encode the result as UTF-8)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _check_key(key: Any) -> bytes | None:
    if key is None:
        return None
    if isinstance(key, str) or not isinstance(key, (bytes, bytearray)):
        raise TypeError("the mirror key is bytes (a str is refused)")
    if len(key) < MIN_KEY_BYTES:
        raise ValueError(f"the mirror key is at least {MIN_KEY_BYTES} bytes")
    return bytes(key)


def handle_for(key: bytes, world_id: str, ident: str) -> str:
    """The keyed, opaque handle of an unperceived thing:
    ``"h:" + hex(HMAC-SHA256(key, world_id + NUL + canonical_id))[:20]``."""
    mac = hmac.new(key, f"{world_id}\x00{ident}".encode("utf-8"), hashlib.sha256)
    return "h:" + mac.hexdigest()[:20]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _scalar(value: Any) -> bool:
    """A JSON scalar a present record may carry: str, int, float (finite), bool."""
    if isinstance(value, bool) or isinstance(value, (str, int)):
        return True
    return isinstance(value, float) and math.isfinite(value)


def normalize_people(people: Sequence[str] | None,
                     canonical: Callable[[str], str] | None = None
                     ) -> tuple[str, ...] | None:
    """The people layer's person-fact names as ONE tuple (VIEW-PEOPLE-V1 §2): each
    name passed through `canonical` (a world's `canonical_attribute`), then
    deduplicated and sorted. That tuple is what is validated, what the
    extraction reads and what the cursor's `q` hashes. ``None`` is off; ``()`` is
    on with position only.

    Without `canonical` (a service not yet attached to a world) a name gets the
    gate's plain normalization (strip, lowercase, spaces to `_`) and no alias map.

    A `people` that is not a list or tuple of strings is a `TypeError` (a bare
    `str` included); a name that is blank, or in the containment family, `kind`,
    or a mechanism, semantics, canon-identity or meta attribute, is a `ValueError`."""
    if people is None:
        return None
    if not isinstance(people, (list, tuple)):
        raise TypeError("people is None or a list or tuple of attribute names "
                        "(a bare str is refused)")
    names: set[str] = set()
    for name in people:
        if not isinstance(name, str):
            raise TypeError(f"a person fact is named by a str, got {type(name).__name__}")
        folded = ("_".join(name.strip().lower().split()) if canonical is None
                  else canonical(name))
        if not folded or not folded.strip():
            raise ValueError("a person fact needs a name")
        if folded in _PEOPLE_BARRED:
            raise ValueError(f"{name!r} cannot be a person fact ({folded!r} is position, "
                             "the person test's key, or bookkeeping)")
        names.add(folded)
    return tuple(sorted(names))


def _people_q(attrs: tuple[str, ...]) -> str:
    """The cursor's `q`: SHA-256 of the canonical JSON of the normalized names."""
    return hashlib.sha256(canonical_json(list(attrs)).encode("utf-8")).hexdigest()


def _empty_document(world_id: str, view_frame: str) -> dict:
    return {"schema": SCHEMA, "world_id": world_id, "view_frame": view_frame,
            "at": None, "cursor": None, "known": {}, "present": None}


# ------------------------------------------------------------ the cursor


def _mint_cursor(key: bytes | None, body: dict) -> str:
    payload = _b64(canonical_json(body).encode("utf-8"))
    if key is None:
        return payload + "."
    derived = hmac.new(key, _CURSOR_LABEL, hashlib.sha256).digest()
    mac = hmac.new(derived, payload.encode("ascii"), hashlib.sha256).digest()
    return payload + "." + _b64(mac)


def _read_cursor(key: bytes | None, cursor: Any) -> dict | None:
    """The cursor's body, or None when it is malformed or its MAC fails. With a
    key the MAC must verify; without one the MAC part must be empty."""
    if not isinstance(cursor, str) or cursor.count(".") != 1:
        return None
    payload, mac = cursor.split(".")
    try:
        if key is None:
            if mac:
                return None
        else:
            derived = hmac.new(key, _CURSOR_LABEL, hashlib.sha256).digest()
            want = hmac.new(derived, payload.encode("ascii"), hashlib.sha256).digest()
            if not hmac.compare_digest(_unb64(mac), want):
                return None
        body = json.loads(_unb64(payload).decode("utf-8"))
    except (ValueError, UnicodeError, TypeError):
        return None
    if not isinstance(body, dict):
        return None
    head, at = body.get("h"), body.get("t")
    if (not isinstance(head, int) or isinstance(head, bool) or head < 0
            or not isinstance(body.get("d"), str)
            or not isinstance(body.get("p"), bool)
            or not isinstance(body.get("w"), str) or not isinstance(body.get("f"), str)
            or not isinstance(body.get("s"), str)
            or not ("q" not in body or (isinstance(body["q"], str)
                                        and _Q_RE.fullmatch(body["q"])))
            or not (at is None or (isinstance(at, (int, float))
                                   and not isinstance(at, bool)))):
        return None
    return body


# ------------------------------------------------------- one side of a diff


class _Side(NamedTuple):
    """One read of the world: the document's two layers, and (not in the
    document) which canonical id each handle stands for."""
    known: dict[str, dict]
    present: dict[str, dict] | None
    handles: dict[str, str]
    people: dict[str, dict] | None = None

    def digest(self) -> str:
        doc: dict[str, Any] = {"known": self.known, "present": self.present}
        if self.people is not None:
            doc["people"] = self.people
        text = canonical_json(doc)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _Reader:
    """The reads of one export, at one `(head, at)`. Every read takes
    `asserted_as_of=head`, so the feed can recompute an old side."""

    def __init__(self, world: Any, view_frame: str, head: int, at: float | None,
                 frame_scope: str) -> None:
        self.world, self.view_frame = world, view_frame
        self.head, self.at, self.frame_scope = head, at, frame_scope
        self.p = world.porcelain
        self._canon: dict[str, str] = {}
        self._person: dict[str, bool] = {}
        self._owner: dict[str, bool] = {}
        self._place: dict[str, bool] = {}
        self._by_handle: dict[str, str] = {}
        self._declared: dict[str, frozenset[str]] | None = None

    # identity, as the log stood at `head`
    def canon(self, ident: str) -> str:
        out = self._canon.get(ident)
        if out is None:
            out = self._canon[ident] = self.world.registry.resolve(ident, self.head)
        return out

    def is_person(self, ident: str) -> bool:
        """A `person:` id, one whose identity closure owns a `knows:` frame (the
        owners R35 recognises, `identity._owns_frame`, here as of `head`), or
        one whose canon kind folds to `person` (spec §2, r3.1)."""
        out = self._person.get(ident)
        if out is None:
            members = self.world.registry.closure(ident, self.head) | {ident}
            out = (any(m.startswith("person:") or self._owns_frame(m) for m in members)
                   or self.literal(ident, "kind") == PERSON_KIND)
            self._person[ident] = out
        return out

    def is_place(self, ident: str) -> bool:
        """A place (VIEW-PEOPLE-V1 §2): a member of its identity closure in the
        `place:` namespace, or one whose canon kind folds to `place`. Being a
        containment root is not enough."""
        out = self._place.get(ident)
        if out is None:
            members = self.world.registry.closure(ident, self.head) | {ident}
            out = (any(m.startswith("place:") for m in members)
                   or self.literal(ident, "kind") == PLACE_KIND)
            self._place[ident] = out
        return out

    def handle(self, key: bytes, ident: str) -> str:
        """The keyed handle of `ident`; one handle never stands for two ids."""
        h = handle_for(key, self.world.world_id, ident)
        if self._by_handle.setdefault(h, ident) != ident:
            raise ValueError(f"two items share the handle {h}")
        return h

    def _owns_frame(self, member: str) -> bool:
        owns = self._owner.get(member)
        if owns is None:
            owns = self._owner[member] = bool(self.world.buffer.visible(
                frame=f"knows:{member}", asserted_as_of=self.head))
        return owns

    def declared_aspects(self) -> dict[str, frozenset[str]]:
        """aspect -> kinds it is declared `resolvable_for`, from the declaration
        rows as of `head`."""
        if self._declared is None:
            found: dict[str, set[str]] = {}
            for row in self.world.buffer.visible(
                    entity_prefix=ATTR_PREFIX, attribute="resolvable_for",
                    asserted_as_of=self.head):
                name = row.entity[len(ATTR_PREFIX):]
                if (valid_declaration("resolvable_for", row.value)
                        and not AttributeSemantics.is_unresolvable(name)):
                    found.setdefault(name, set()).add(row.value)
            self._declared = {k: frozenset(v) for k, v in found.items()}
        return self._declared

    def state(self, ident: str, attribute: str, frame: Any) -> dict:
        return self.p.state(ident, attribute, frame=frame, as_of=self.at,
                            asserted_as_of=self.head,
                            **({"frame_scope": self.frame_scope}
                               if frame == self.view_frame else {}))

    def literal(self, ident: str, attribute: str) -> Any:
        """Canon's folded value of a key when it is known and a literal JSON
        scalar, else `_MISSING`."""
        out = self.state(ident, attribute, CANON)
        if out.get("status") != "known":
            return _MISSING
        fact = out["fact"]
        if fact["value_type"] != "literal" or not _scalar(fact["value"]) \
                or "values" in out:
            return _MISSING
        return fact["value"]

    # ----------------------------------------------------------- the layers

    def known(self) -> dict[str, dict]:
        keys: dict[str, set[str]] = {}
        for fact in self.p.facts(self.view_frame, as_of=self.at,
                                 asserted_as_of=self.head,
                                 frame_scope=self.frame_scope):
            keys.setdefault(self.canon(fact["entity"]), set()).add(fact["attribute"])
        known: dict[str, dict] = {}
        for subject in sorted(keys):
            tuples: set[str] = set()
            conflicted: set[str] = set()
            rows: list[list[Any]] = []
            for attribute in sorted(keys[subject]):
                out = self.state(subject, attribute, self.view_frame)
                status = out.get("status")
                if status == "known":
                    for fact in out.get("values") or [out["fact"]]:
                        row = [fact["attribute"], fact["value"],
                               "id" if fact["value_type"] == "entity" else "lit"]
                        text = canonical_json(row)
                        if text not in tuples:
                            tuples.add(text)
                            rows.append(row)
                elif status == "conflicted":
                    conflicted.add(out["fact"]["attribute"])
                # unresolved / unknown: omitted
            rows.sort(key=lambda r: (r[0], r[2], canonical_json(r[1])))
            known[subject] = {"facts": rows, "conflicted": sorted(conflicted)}
        return known

    def present(self, known: dict[str, dict], key: bytes) -> tuple[dict, dict]:
        present: dict[str, dict] = {}
        handles: dict[str, str] = {}

        def handle(ident: str) -> str:
            return self.handle(key, ident)

        roots = sorted(s for s in known if not self.is_person(s))
        queue = list(roots)
        visited = set(roots)
        while queue:
            parent = queue.pop(0)
            for child in self.p.contents(parent, as_of=self.at, frame=CANON,
                                         asserted_as_of=self.head):
                child = self.canon(child)
                if child in visited:
                    continue
                visited.add(child)
                if child in known or self.is_person(child):
                    continue            # a known item is a root; a person is never entered
                queue.append(child)
                record = self._record(child, parent, known, handle)
                h = handle(child)
                present[h] = record
                handles[h] = child
        return present, handles

    def _record(self, item: str, parent: str, known: dict, handle: Any) -> dict:
        kind = self.literal(item, "kind")
        held = self.state(item, "in", CANON)
        relation = held["fact"]["attribute"] if "fact" in held else "in"
        if relation not in _RELATIONS:
            relation = "in"
        where: list[Any] = [relation, parent if parent in known else handle(parent)]
        slot = self.literal(item, "slot")
        if slot is not _MISSING:
            where.append(slot)
        record: dict[str, Any] = {"in": where, "look": []}
        if kind is not _MISSING:
            record["kind"] = kind
        address = self.literal(item, "address")
        if address is not _MISSING:
            record["address"] = address
        if isinstance(kind, str):
            look = []
            for aspect, kinds in sorted(self.declared_aspects().items()):
                if kind in kinds:
                    value = self.literal(item, aspect)
                    if value is not _MISSING:
                        look.append([aspect, value])
            look.sort(key=lambda pair: (pair[0], canonical_json(pair[1])))
            record["look"] = look
        return record

    # -------------------------------------------------------- the people layer

    def people(self, known: dict[str, dict], key: bytes | None,
               attrs: tuple[str, ...]) -> dict[str, dict]:
        """Persons' canon whereabouts and the host-named facts, keyed by canonical
        id (VIEW-PEOPLE-V1 §2). Never descends into a person; a person whose
        record would be empty is left out."""
        raw: set[str] = set()
        for fact in self.p.facts(CANON, as_of=self.at, asserted_as_of=self.head,
                                 bookkeeping=False):
            if not fact["entity"].startswith(("a:", ATTR_PREFIX)):
                raw.add(fact["entity"])
        subjects = {self.canon(e) for e in raw}
        out: dict[str, dict] = {}
        for person in sorted(subjects):
            if not self.is_person(person):
                continue
            record = self._person_record(person, known, key, attrs)
            if record:
                out[person] = record
        return out

    def _parent(self, ident: str) -> tuple[str, str] | None:
        """`(relation, canonical parent)` when canon folds a known entity-valued
        containment row for `ident`, else None (no parent, conflicted, unresolved
        or a literal)."""
        held = self.state(ident, "in", CANON)
        if held.get("status") != "known" or "fact" not in held:
            return None
        fact = held["fact"]
        if fact["value_type"] != "entity" or not isinstance(fact["value"], str):
            return None
        relation = fact["attribute"] if fact["attribute"] in _RELATIONS else "in"
        return relation, self.canon(fact["value"])

    def _place_of(self, person: str, first: str) -> str | None:
        """The nearest place on the containment chain above `person`, whose
        immediate parent is `first`; None when the chain ends without one. A cycle
        or a chain longer than `MAX_CHAIN_DEPTH` stops the walk (logged)."""
        seen = {person}
        current: str | None = first
        while current is not None:
            if current in seen:
                logger.warning("people layer: a containment cycle above %s; no place",
                               person)
                return None
            if len(seen) > MAX_CHAIN_DEPTH:
                logger.warning("people layer: the chain above %s is longer than %d; "
                               "no place", person, MAX_CHAIN_DEPTH)
                return None
            seen.add(current)
            if self.is_place(current):
                return current
            step = self._parent(current)
            current = step[1] if step else None
        return None

    def _ref(self, target: str, known: dict, key: bytes | None, *,
             places: bool) -> str | None:
        """How a target crosses: its id when it is known, a person (or a place,
        when `places`), else its handle with a key, else not at all."""
        if target in known or self.is_person(target) or (places and self.is_place(target)):
            return target
        return self.handle(key, target) if key is not None else None

    def _person_record(self, person: str, known: dict, key: bytes | None,
                       attrs: tuple[str, ...]) -> dict:
        record: dict[str, Any] = {}
        first = self._parent(person)
        place = self._place_of(person, first[1]) if first else None
        if place is not None:
            record["place"] = place
        if first is not None and first[1] != place:
            ref = self._ref(first[1], known, key, places=False)
            if ref is not None:
                where: list[Any] = [first[0], ref]
                slot = self.literal(person, "slot")
                if slot is not _MISSING:
                    where.append(slot)
                record["in"] = where
        rows: list[list[Any]] = []
        seen: set[str] = set()
        for attribute in attrs:
            out = self.state(person, attribute, CANON)
            if out.get("status") != "known":
                continue
            for fact in out.get("values") or [out["fact"]]:
                row = self._person_fact(fact, known, key)
                if row is not None and canonical_json(row) not in seen:
                    seen.add(canonical_json(row))
                    rows.append(row)
        rows.sort(key=lambda r: (r[0], r[2], canonical_json(r[1])))
        if place is None and "in" not in record and not rows:
            return {}
        record["facts"] = rows
        return record

    def _person_fact(self, fact: dict, known: dict, key: bytes | None) -> list[Any] | None:
        kind, value = fact["value_type"], fact["value"]
        if kind == "literal" and _scalar(value):
            return [fact["attribute"], value, "lit"]
        if kind == "entity" and isinstance(value, str):
            ref = self._ref(self.canon(value), known, key, places=True)
            return [fact["attribute"], ref, "id"] if ref is not None else None
        return None             # structured, delta or unresolved: never guessed


def _resolve_at(world: Any, at: float | None) -> float | None:
    if at is not None:
        return at
    return world.buffer.max_valid_from()


def _build(world: Any, view_frame: str, head: int, at: float | None,
           key: bytes | None, frame_scope: str,
           people: tuple[str, ...] | None = None) -> _Side:
    reader = _Reader(world, view_frame, head, at, frame_scope)
    known = reader.known()
    if key is None:
        present, handles = None, {}
    else:
        present, handles = reader.present(known, key)
    crowd = reader.people(known, key, people) if people is not None else None
    return _Side(known, present, handles, crowd)


def present_handles(world: Any, view_frame: str, *, at: float | None,
                    key: bytes | None, frame_scope: str = "exact") -> dict[str, str]:
    """handle -> canonical id for the present layer of `world` as of now: the
    host's own map (the service's `unhandle`). Empty without a key."""
    key = _check_key(key)
    if key is None:
        return {}
    head = world.buffer.head()
    return _build(world, view_frame, head, _resolve_at(world, at), key,
                  frame_scope).handles


# --------------------------------------------------------------- the feed


def feed(world: Any, view_frame: str, since: str | None = None, *,
         at: float | None = None, key: bytes | None = None,
         frame_scope: str = "exact", people: Sequence[str] | None = None) -> dict:
    """The ops that bring a client holding cursor `since` up to now.

    Answers ``{"cursor", "at", "present_on", "ops"}`` (plus ``"people_on": true``
    when the people layer is on). A missing, malformed, foreign, future or stale
    cursor is answered with a reset (`clear`, then a `put` for every subject);
    otherwise the ops are the difference between the old export (recomputed at the
    cursor's log position and valid time) and the new one, in the order reveal,
    del, put.

    `people` is None (off: nothing changes) or the person facts that cross in the
    people layer (see `export`)."""
    key = _check_key(key)
    attrs = normalize_people(people, world.canonical_attribute)
    q = _people_q(attrs) if attrs is not None else None
    head = world.buffer.head()
    now_at = _resolve_at(world, at)
    new = _build(world, view_frame, head, now_at, key, frame_scope, attrs)
    present_on = key is not None
    body = {"v": CURSOR_VERSION, "w": world.world_id, "f": view_frame,
            "s": frame_scope, "h": head, "t": now_at, "d": new.digest(),
            "p": present_on}
    if q is not None:
        body["q"] = q
    cursor = _mint_cursor(key, body)

    def answer(ops: list[dict]) -> dict:
        out = {"cursor": cursor, "at": now_at, "present_on": present_on, "ops": ops}
        if attrs is not None:
            out["people_on"] = True
        return out

    def reset() -> dict:
        ops: list[dict] = [{"op": "clear"}]
        ops += [{"op": "put", "layer": "known", "key": k, "value": v}
                for k, v in sorted(new.known.items())]
        if new.present is not None:
            ops += [{"op": "put", "layer": "present", "key": k, "value": v}
                    for k, v in sorted(new.present.items())]
        if new.people is not None:
            ops += [{"op": "put", "layer": "people", "key": k, "value": v}
                    for k, v in sorted(new.people.items())]
        return answer(ops)

    old_cursor = _read_cursor(key, since) if since is not None else None
    if old_cursor is None:
        return reset()
    if (old_cursor["v"] != CURSOR_VERSION or old_cursor["w"] != world.world_id
            or old_cursor["f"] != view_frame or old_cursor["s"] != frame_scope
            or old_cursor["p"] != present_on or old_cursor.get("q") != q
            or old_cursor["h"] > head):
        return reset()
    old_at = old_cursor["t"]
    if key is None and old_at is not None and (now_at is None or old_at > now_at):
        return reset()
    if old_cursor["h"] == head and old_at == now_at:
        old = new
    else:
        old = _build(world, view_frame, old_cursor["h"], old_at, key, frame_scope, attrs)
    if old.digest() != old_cursor["d"]:
        return reset()
    return answer(_diff(world, old, new, head))


def _diff(world: Any, old: _Side, new: _Side, head: int) -> list[dict]:
    reveals: list[dict] = []
    revealed: set[str] = set()
    if old.present is not None:
        for h in sorted(old.handles):
            ident = world.registry.resolve(old.handles[h], head)
            if ident in new.known:
                reveals.append({"op": "reveal", "handle": h, "id": ident})
                revealed.add(h)
    dels: list[dict] = []
    puts: list[dict] = []
    layers = [("known", old.known, new.known, set())]
    if old.present is not None and new.present is not None:
        layers.append(("present", old.present, new.present, revealed))
    if old.people is not None and new.people is not None:
        layers.append(("people", old.people, new.people, set()))
    layers.sort(key=lambda layer: layer[0])         # ops sort by (layer, key)
    for layer, before, after, skip in layers:
        for k in sorted(before):
            if k not in after and k not in skip:
                dels.append({"op": "del", "layer": layer, "key": k})
        for k in sorted(after):
            if before.get(k) != after[k]:
                puts.append({"op": "put", "layer": layer, "key": k, "value": after[k]})
    return reveals + dels + puts


def apply(document: dict, answer: dict) -> dict:
    """A document with a feed answer applied: pure, the reference for every
    client. Runs the ops in order; `cursor` and `at` come from the answer.

    - `clear`: `known` becomes `{}`, `present` becomes `{}` when the answer's
      `present_on` is true, else `null`;
    - `reveal`: drops `present[handle]` (the `put` of `known[id]` follows);
    - `del` / `put`: act on the named layer. A `put` to a `null` present layer
      is an error (the feed never emits one), as is one to a `people` layer the
      document does not have.

    The people layer (VIEW-PEOPLE-V1): `clear` sets `people` to `{}` when the
    answer says `people_on` and removes the key otherwise; an answer without a
    `clear` must keep the document's people mode."""
    out = copy.deepcopy(document)
    present_on = answer["present_on"]
    people_on = answer.get("people_on", False) is True
    no_clear = not any(op["op"] == "clear" for op in answer["ops"])
    if (out["present"] is not None) != present_on and no_clear:
        raise ValueError("an answer without a clear must keep the document's present_on")
    if ("people" in out) != people_on and no_clear:
        raise ValueError("an answer without a clear must keep the document's people mode")
    for op in answer["ops"]:
        kind = op["op"]
        if kind == "clear":
            out["known"] = {}
            out["present"] = {} if present_on else None
            if people_on:
                out["people"] = {}
            else:
                out.pop("people", None)
        elif kind == "reveal":
            if out["present"] is None:
                raise ValueError("reveal on a document with no present layer")
            out["present"].pop(op["handle"], None)
        elif kind in ("del", "put"):
            layer = out.get(op["layer"])
            if layer is None:
                raise ValueError(f"{kind} to the {op['layer']} layer while it is null")
            if kind == "del":
                layer.pop(op["key"], None)
            else:
                layer[op["key"]] = copy.deepcopy(op["value"])
        else:
            raise ValueError(f"unknown op {kind!r}")
    out["cursor"] = answer["cursor"]
    out["at"] = answer["at"]
    return out


def export(world: Any, view_frame: str, *, at: float | None = None,
           key: bytes | None = None, frame_scope: str = "exact",
           people: Sequence[str] | None = None) -> dict:
    """The whole `patternbuffer.view/1` document: `apply(EMPTY, feed(None))`.

    `people` (VIEW-PEOPLE-V1) is None (off: no `people` key, nothing else
    changes) or a list or tuple of attribute names, the **person facts**; `()` is
    the layer on with position only. With it on, the document gains a `people`
    layer: every person's canon `place` (the nearest place on its containment
    chain), its immediate `in` when that differs, and the named facts, keyed by
    canonical id. The exposure is for single-player hosts that accept it. Naming
    an appearance attribute ships canon looks and undoes a disguise: that trade
    is the host's to make for its game, not the engine's. Names are
    canonicalized, deduplicated and sorted (a bare `str` is a `TypeError`;
    containment attributes, `kind` and bookkeeping attributes a `ValueError`)."""
    answer = feed(world, view_frame, None, at=at, key=key, frame_scope=frame_scope,
                  people=people)
    return apply(_empty_document(world.world_id, view_frame), answer)


# ------------------------------------------------------------------- CLI


def open_read_only_copy(path: str | Path, world_id: str) -> Any:
    """A sealed World over an in-memory copy of a world file, taken with
    SQLite's backup API from a `mode=ro` connection: the file is never opened
    for writing (no journal, bytes and mtime unchanged)."""
    from patternbuffer import World

    uri = "file:" + urllib.parse.quote(str(Path(path).resolve())) + "?mode=ro"
    source = sqlite3.connect(uri, uri=True)
    try:
        copied = sqlite3.connect(":memory:", check_same_thread=False)
        try:
            source.backup(copied)
        except BaseException:
            copied.close()
            raise
    finally:
        source.close()
    try:
        world = World(path, world_id, _connection=copied)
    except BaseException:
        copied.close()
        raise
    world.buffer.seal_log()
    return world


def main(argv: list[str] | None = None) -> int:
    """`python -m patternbuffer.mirror export --world PATH --world-id ID
    --view-frame F [--at T] [--mirror-key-file K] [--frame-scope S] [--people
    [--people-attr NAME ...]]`."""
    parser = argparse.ArgumentParser(
        prog="patternbuffer.mirror",
        description="Write the player's view of a world as a patternbuffer.view/1 "
                    "document for a static build. Opens no write handle.")
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="write the export document to stdout")
    exp.add_argument("--world", required=True, help="path to the .world file")
    exp.add_argument("--world-id", required=True)
    exp.add_argument("--view-frame", required=True)
    exp.add_argument("--at", type=float, default=None,
                     help="valid time (default: the log's latest)")
    exp.add_argument("--mirror-key-file", default=None,
                     help="raw key bytes (>= 16); without it the present layer is off")
    exp.add_argument("--frame-scope", choices=("exact", "continued", "merged"),
                     default="exact")
    exp.add_argument("--people", action="store_true",
                     help="turn on the people layer (persons' canon whereabouts); "
                          "single-player hosts only")
    exp.add_argument("--people-attr", action="append", default=[], metavar="NAME",
                     help="a person fact to cross in the people layer (repeatable; "
                          "needs --people)")
    args = parser.parse_args(argv)
    if args.people_attr and not args.people:
        parser.error("--people-attr needs --people")
    people = tuple(args.people_attr) if args.people else None
    try:
        normalize_people(people)
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    key = Path(args.mirror_key_file).read_bytes() if args.mirror_key_file else None
    world = open_read_only_copy(args.world, args.world_id)
    try:
        doc = export(world, args.view_frame, at=args.at, key=key,
                     frame_scope=args.frame_scope, people=people)
    finally:
        world.close()
    sys.stdout.buffer.write(canonical_json(doc).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
