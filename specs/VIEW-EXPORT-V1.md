# VIEW-EXPORT-V1: the player's view as a document, kept in step by a feed

**Status:** r2. It answers pbr's r1 RED (m e8f8c102): the look values are literal-only, `del` and
`put` cover both layers, and every answer says `present_on`. It also folds in holo-emitter's shape
read (m095e7d): handles can come back in, containment slots, the birth address, and the §7 wording.
Changes are marked *(r2)*. r3 answers pbr's r2 RED (m 46bceec1): the standalone `record` result
leaked the id it had just unhandled. Its public answer is now a bare acknowledgement (§5, marked
*(r3)*). r3.1, from the build: a canon `kind` of `person` also makes a person (§2), and a
`record` failure of any kind answers the bare `refused` (§5). Author: pb, 2026-10-12.
**Source:** roadmap R40, S2 of `specs/proposals/UNIFIED-WORLD-ACCESS.md` §7, approved by Kabe on
2026-10-12 (gate gde97f3), including its point 5: *unopened contents can sit on the device, without
their meaning; accepted*. The monitor started this item for Kabe (note n662076).
**Builds on:** WORLD-SERVICE-V1 (S1: the service, its snapshot, its sessions and runner),
FRAME-CONTINUITY-V1 (`frame_scope`), READ-SURFACE-V1 §8 (`asserted_as_of`), RESOLVE-UNMARKED-V1
(`resolvable_for`, the closed aspect vocabulary).

## Need

holo-emitter's public manor is a static page on a phone, with no server (proposal §7, holo-emitter
R75). For it to play from a pattern-buffer world, the device needs a copy of the world that:
1. holds the **player's view**, the same facts a viewer's reads answer through the service;
2. also holds, as *things to draw*, **what is physically present but not yet perceived** in the
   places the view covers, so opening a drawer offline shows its contents within a frame;
3. carries **no meaning** in that second part: no relations, no knowledge, no ids that name a role
   ("obj:murder_weapon");
4. stays in step, when a service is reachable, by **changes since a log position**, with a gap or
   any doubt answered by starting again.

holo-emitter's own replica plan says the same in its words (`design/blueprint.md` §11): "snapshot +
monotonic envelope stream (version cursor on document and envelope; a gap re-snapshots)", with
knowledge filtering done on the host. No JS port of the engine is wanted (proposal §7), so the
device must never fold the log itself: it receives folded answers.

## Prior art (adopted and rejected)

- **Adopted: Replicache's pull protocol.** The client sends an opaque cookie; the server answers a
  patch of `put` / `del` / `clear` operations and a new cookie. A reset is `clear` followed by puts,
  so the client has one apply path. Here: `put` / `del` / `clear`, plus `reveal` (below).
- **Adopted: the CouchDB changes feed's opaque sequence token.** The client never interprets the
  cursor.
- **Rejected: shipping log rows** (an event-sourced feed of raw assertions). The rows are unfolded,
  carry other frames' rows and canon, and would need the engine on the device. The feed ships
  *folded state per subject* instead. It is computed as the difference between two exports, so it
  is correct by construction.

## The shape

A new module, `patternbuffer.mirror`, outside the engine core (the core never imports it), as with
`patternbuffer.service`. It uses only the porcelain's reads.

```python
feed(world, view_frame, since=None, *, at=None, key=None, frame_scope="exact") -> dict
export(world, view_frame, *, at=None, key=None, frame_scope="exact") -> dict
apply(document, feed_answer) -> dict        # pure; the reference for every client
```

- `export(...)` is `apply(EMPTY, feed(..., since=None))`: one definition, two forms.
- The service gains two viewer verbs, `export` and `feed` (§5). The runner serves them over
  `POST /call`. A CLI writes an export file for a static build (§6).

### 1. The document

```json
{"schema": "patternbuffer.view/1",
 "world_id": "w", "view_frame": "knows:person:mara", "at": 1220.0,
 "cursor": "<opaque>",
 "known":   {"obj:desk": {"facts": [["in", "place:study", "id"], ["colour", "oak", "lit"]],
                          "conflicted": []}},
 "present": {"h:3f9c0a1b2c4d5e6f7a8b": {"kind": "key",
                                        "in": ["in", "obj:desk"],
                                        "look": [["material", "iron", "lit"]]}}}
```

- **`known`**: the player's view. Its subjects are the canonical ids of every world entity that has
  a row in the view frame (under the host's `frame_scope`) as of `at`, excluding `a:` and `attr:`
  subjects. A subject's `facts` are, for each attribute it has rows for in that scope, the answer
  `state(subject, attribute, frame=view_frame, as_of=at, frame_scope=...)` gives:
  - `known`: one tuple `[attribute, value, type]`, or one per member for a set-valued key
    (`values`), or the derived quantity for an accrue key. `type` is `"id"` for an entity-valued
    fact and `"lit"` otherwise. Values leave as the porcelain's plain JSON (`encode_out`: an exact
    decimal is its tag dict).
  - `conflicted`: the attribute is listed in `conflicted`; no value is given.
  - `unresolved` or `unknown`: omitted. An undecided detail is resolved online, never guessed on
    the device.
  - Tuples are sorted by `(attribute, type, canonical JSON of value)`; `conflicted` is sorted.
  - **Why `state` per key, not `snapshot`:** `snapshot` takes no `frame_scope`. The document must
    equal what the same viewer's live reads answer, under the scope the host set at `attach`.
- **`present`**: what is physically there but not perceived. A drawable record per thing, keyed by
  an opaque **handle**. It exists only when a `key` is given; without one it is `null` and no canon
  data crosses at all. Its rules are §2.
- **`at`**: the valid time the document answers for. `None` means the log's latest valid time at
  `cursor`.
- **`cursor`**: opaque to clients (§3).

### 2. The present layer: what crosses from canon, and nothing more

**Roots.** Every subject in `known` that is **not a person** is a root. A person is any of these:
- an id whose identity closure has a member in the `person:` namespace;
- an id whose identity closure owns a `knows:` frame. These are the same owners R35 already
  recognises (`identity.py`, `frame_owner`);
- *(r3.1, found in the build)* an id whose canon `kind` folds to `person`. This catches a hidden
  NPC that has neither the namespace nor a frame of its own.

**The walk.** From each root, the walk takes canon's `contents(root, as_of=at)`, then each item's
own contents, recursively, with a visited set. It never descends into a person, and never emits
one. Every item reached that is not in `known` and is not a person gets one record:
- `kind`: canon's folded `kind`, or omitted when it is not `known`;
- `in`: `[relation, ref]`, or `[relation, ref, slot]` *(r2, holo-emitter b)*. The relation is the
  containment attribute that holds the item in its parent (`in`, `within`, `held_by`, `worn_by` or
  `carried_by`). `ref` is the parent's id if the parent is in `known`, otherwise the parent's handle.
  `slot` is canon's folded `slot` on the item (which drawer, which shelf), present only when it is
  known;
- `address` *(r2, holo-emitter d)*: canon's folded `address` on the item (a generator's birth
  address, such as `manor/study/desk:0`), present only when it is known;
- `look`: for each aspect declared `resolvable_for` the item's folded kind (the world's closed
  vocabulary of drawable aspects, E1), canon's folded value as `[aspect, value]` pairs, sorted. An
  aspect that is unresolved, conflicted or unknown is omitted.

**Literal only** *(r2, pbr 1)*. Every value in a present record (`kind`, `slot`, `address`, each
`look` value) is served only when the winning row's `value_type` is literal and the value is a
JSON scalar (string, number or boolean). Otherwise the field or aspect is omitted. That excludes:
- an entity-valued declared aspect (`made_by -> person:secret`, `points_to -> obj:x`), which would
  carry a canonical id and a relation across;
- a structured value (object or list), which can embed ids;
- a set-valued or accrue key.

`look` therefore carries no type column. The only ids in a present record are `ref`, which is a
known id or a handle.

**Words, not meaning.** `kind` and the look values are canon's own words. They are drawable by the
closed-vocabulary rule (proposal §3 and §8): the modules declare the kinds and aspects, and a term
outside the vocabulary is `other`, never free text. *(r2, holo-emitter c)* Mapping a declared kind
onto a renderer's catalogue is that vocabulary's job, not this export's.

**Additive** *(r2, holo-emitter d)*. Present records add to the contents a renderer generates for
a place itself; they never replace them.

**Nothing else crosses.** That excludes:
- any other attribute (no `owned_by`, no `knows`, no event, no relation between two items);
- any row of another `knows:` frame;
- any id of an unperceived thing. The item's canonical id appears only inside the handle's MAC;
  a container that is itself unperceived appears only as its handle;
- any non-literal value (above).

**Why persons are excluded.**
- A person's appearance in canon is who they are. Shipping it would undo disguise (proposal §2):
  the face under the hood.
- A person's contents are what they carry. Shipping them would put the gun under the coat on the
  phone. That goes beyond the drawer trade-off Kabe accepted.
- A host that wants a hidden person drawn adds them to the view, with their *perceived* appearance.

**Handles.** `"h:" + hex(HMAC-SHA256(key, world_id + "\x00" + canonical_id))[:20]`.
- They are stable across exports and feeds while the key and the canonical id stand.
- A merge that changes the representative changes the handle. The feed then answers `del` of the
  old handle and `put` of the new one.
- `key` is bytes, at least 16 long; a `str` is refused. The host keeps it (construct's config) and
  it never reaches a client.
- Two items with the same handle in one export raise `ValueError` (80 bits; never expected).

**Recipes.** The proposal's recipe rows (generator id, version, seed) do not exist in the engine
yet. When they come, they will be facts or look aspects like any other. This spec ships what the
log holds now and adds no recipe concept.

### 3. The cursor

- **What it holds:** a signed token, `base64url(json(body)) + "." + base64url(mac)`. The body is
  `{"v": 1, "w": world_id, "f": view_frame, "s": frame_scope, "h": head, "t": at, "d": digest,
  "p": present_on}`:
  - `head`: the committed log head (`buffer.head()`) the document was read at, used as
    `asserted_as_of`;
  - `digest`: SHA-256 of the canonical JSON (sorted keys, no spaces, UTF-8) of the document's
    `known` and `present`.
- **Signing.**
  - With a key, the MAC is HMAC-SHA256 under a key derived from it:
    `HMAC(key, "patternbuffer.view/1 cursor")`.
  - Without a key, the MAC part is empty and the cursor is unsigned.
  - **Why sign:** the feed recomputes the export at the cursor's `(head, at)`. An unsigned
    cursor would let a client name any past or future valid time and diff canon's drawer contents
    at that moment against now. Without a key no canon crosses, so the known layer, the player's
    own frame, is safe to answer at any `head ≤ current` and `at ≤ current at`.
- **`feed(since=c)`** answers `{"cursor": new, "at": at, "present_on": bool, "ops": [...]}`.
  `present_on` *(r2, pbr 3)* is public and in every answer, including a reset and an empty one. It
  says whether this answer's document has a present layer (a key was given). The signed cursor's
  `p` still detects a mode change, which forces a reset.
  1. `c is None` → ops are `clear` followed by a `put` for every subject.
  2. The answer is the same reset when:
     - `c` is malformed, its MAC fails, or its `v`, `w`, `f`, `s` or `p` differ from this call's;
     - its `head` is greater than the current head;
     - (unsigned only) its `at` is later than this call's `at`.
  3. Otherwise the feed recomputes the export at `(asserted_as_of=c.head, at=c.at)`. If its digest
     differs from `c.digest`, the answer is a reset: something the log position does not capture
     changed the past view, such as a classifier verdict, a merge's representative, or the engine
     itself. This is the "gap re-snapshots" rule, and it is self-checking.
  4. Otherwise the answer is the diff of old and new, in this order:
     - `reveal` ops: a handle in old `present` whose item is now in `known`, as
       `{"op": "reveal", "handle": h, "id": id}`, so a client can carry its local state across;
     - `del` ops, **in either layer** *(r2, pbr 2)*: a subject in the old layer and not in the new
       one, as `{"op": "del", "layer": "known"|"present", "key": k}`. A handle a `reveal` already
       removed gets no `del`. A known subject leaves when its last view row is retracted or ends
       before `at`;
     - `put` ops, **in either layer** *(r2, pbr 2)*: a subject new to its layer, or with a changed
       record, carrying the whole record, as
       `{"op": "put", "layer": "known"|"present", "key": k, "value": {...}}`.

     Within each kind of op, the order is sorted by `(layer, key)`.
  5. Same `(head, at)` and digest: `ops` is empty, and the cursor is unchanged.
- **`apply(doc, answer)`** runs the ops in order:
  - `clear` sets `known` to `{}`, and `present` to `{}` when the answer's `present_on` is true,
    else to `null` *(r2, pbr 3)*. A `put` to `present` while it is `null` is an error; the feed
    never emits one;
  - `reveal` drops `present[handle]`; the `put` of `known[id]` follows in the same answer;
  - `del` and `put` act on the named layer;
  - `cursor` and `at` are taken from the answer.

  An answer with no `clear` always has the same `present_on` as the document it applies to: a mode
  change resets.

  It is a pure function, and its prose here is the contract a JS client implements.
- **The defining property, tested:** for every position `c` a client could hold,
  `apply(export_at(c), feed(since=cursor_of(c)))` is byte-identical (canonical JSON) to `export()`
  now.

### 4. Time

- `at` is the valid time the view answers for. Through the service it is `svc.now()`, the host's
  coordinate, or the log's valid head when the world has no author. A caller cannot name it (§5).
- The feed reads the cursor's own `at` for the old side. A host that moves `now` backwards (a
  rewind) gets a correct diff, with no special case.

### 5. In the service

- `WorldService(..., mirror_key: bytes | None = None)`: the host's key, kept on the service.
- `Session.call("export")` and `Session.call("feed", since=None | str)`:
  - These are viewer verbs. They run on the reader thread against the current snapshot, like the
    `VIEWER_READS`, and never touch the World.
  - They are passed the view frame, the host's `frame_scope`, `now()` and the key.
  - A caller naming `frame`, `frame_scope`, `at`, `key` or anything except `since` is refused, as
    `_only` already does.
- They are listed in a new allowlist, `VIEWER_SERVICE_READS = ("export", "feed")`. They are not in
  `VIEWER_READS`, which stays porcelain verbs only, and the walk test covers both lists.
- The reader thread handles them as service verbs: `_run_read` dispatches them to `mirror.feed`
  and `mirror.export`.
- The runner: both verbs go through `POST /call`. The `GET /changes` placeholder (501, "the
  changes feed is S2") is **removed**, so there is one door. The runner gains
  `--mirror-key-file PATH`, a file of raw bytes of at least 16; with no key the present layer is
  off.
- A `set_view_frame` change makes every older cursor reset, because `f` differs. That is correct:
  a different player has a different view.
- **Handles come back in** *(r2, holo-emitter a)*. A player who opens a drawer offline sees its
  present records, but the device can't reveal them. On reconnect, it reports what was perceived by
  handle. Two doors map a handle back to its thing, both using the host's key, on the owner thread,
  against the live World:
  - `WorldService.unhandle(handle) -> str | None`, a host method, not a viewer verb. Under an
    author, construct receives the device's events and maps them with it before it commits. It
    answers the canonical id only for a handle in the present layer **as of now**: in the view's
    places, not a person, not already known. Otherwise it answers `None`: a stale, foreign, forged
    or person handle maps to nothing.
  - `record` on the standalone runner accepts a handle as an item's `entity`, or as its `value`
    when `value_type` is `entity`. The record job maps each handle through `unhandle` before the
    commit. If any handle maps to `None`, the whole batch is `refused` (`unknown_handle`) and
    nothing is written.
  - A recorded play event about the thing writes it into the view frame, as `record` already does.
    So the next feed answers `reveal` → `put`, and the device's knowledge and the world's agree.
  - **The public `record` answer is a bare acknowledgement** *(r3, pbr)*. Today
    `_do_record` returns the commit receipt, whose rows carry each committed row's `entity` and
    `frame`. After a handle has been mapped, that would hand the device the canonical id
    (`obj:murder_weapon`) the handle exists to hide. So a recorder session's `record` answers only
    one of two things, with nothing else:
    - `{"status": "recorded"}`;
    - `{"status": "refused"}`.

    There are no receipt rows, frames, canonicalization receipts, skips, causes or error text. This
    holds for every batch, with or without a handle, so the answer's shape gives nothing away.
    - The full outcome (receipt or `AtomicAbort` cause, and `unknown_handle`) is logged on the
      service side, at `INFO` for a commit and `WARNING` for a refusal.
    - It is also kept as `WorldService.last_record_outcome` for the trusted host. It never goes over
      the wire.
    - An unknown handle is therefore indistinguishable at the wire from any other refusal.
    - *(r3.1)* A failure of any other kind while recording (not only `AtomicAbort`) is answered
      the same bare `refused`, with its text kept for the host: an exception's message could name
      a mapped id.
    - This narrows S1's `record` answer, which was the receipt. Its tests move to the bare shape
      and read the logged outcome. No client depends on the receipt yet; the standalone runner has
      no consumer.
  - Neither door then leaks:
    - `unhandle` is the host's own method;
    - `record` answers `recorded` or `refused` alone;
    - the id becomes the device's only through the next feed's `reveal`. By then the recorded play
      event has put the thing in the view, so the player has perceived it.

### 6. For a static build

`python -m patternbuffer.mirror export --world PATH --world-id ID --view-frame F
[--at T] [--mirror-key-file K] [--frame-scope S] > view.json`

- It opens **no write handle** on the file. It takes an in-memory copy through SQLite's backup API
  from a `mode=ro` connection, the way `World.snapshot()` builds its copy, and reads that. The file's
  bytes and mtime are unchanged, and no journal file is created; a test checks both.
- The static manor ships `view.json`. With no service, the code routes decide the rest and the
  world still plays (proposal §7).

### 7. What a client must not assume

- A subject absent from `known` is unknown to the player. *(r2, holo-emitter's wording)*: **the
  client may hold drawables of unknown things (the present layer) but never their meaning, and treats
  them as unknown until perceived locally or revealed.** No tap, hint or notebook entry comes from a
  present record until then.
- A set-valued key arrives as several tuples with one attribute; a client folds them as a set. A
  conflicted key has no value; a renderer draws it at its own default, as unknown.
- **Superseded:** blueprint §3 says "in integrated mode the client never receives unknown
  entities". The offline mirror deliberately ships drawables of unknown things, under Kabe's point
  5. Online clients that call the service's other reads see only the view, as before.

## Tests (the build's acceptance)

1. **Frame absence.**
   - On a fixture world with secrets in canon and in another `knows:` frame, no value outside the
     view appears in `known`.
   - `present` holds only the keys `kind`, `in`, `address` and `look`, and `look` holds only
     declared aspects.
   - No canonical id of an unperceived thing appears anywhere in the document's text.
   - *(r2, pbr 1)* A declared entity-valued aspect (`made_by -> person:secret`), a structured
     value, and an entity-valued `slot`, `address` or `kind` are all omitted. The secret person's
     id appears nowhere in the document's text.
2. **Persons.** A person hidden in a known room, and a gun in their coat, appear nowhere. A person
   is never descended into.
3. **No key, no canon.** `present` is `null`; the cursor is unsigned; the same doc byte-for-byte
   whether canon holds drawer contents or not.
4. **The defining property.**
   - For every log position of a fixture history, `apply(export_at(c), feed(c)) == export()`
     byte-identically.
   - The same property on copies of construct's play worlds, sampled at 20 positions each. The
     copies use the backup API from `mode=ro`.
5. **Resets.**
   - A cursor is answered with `clear` when it is malformed, its MAC is bad, it names another
     frame, scope or world, its head is in the future, or it is unsigned with a future `at`.
   - A classifier verdict change after `c` is answered with `clear`, through the digest.
6. **Reveal.** Opening the drawer (the view gains the key) yields `reveal` → `put`. A client that
   applies the answer has the key known and the handle gone, with no `del` for that handle.
6a. **Both layers** *(r2, pbr 2)*. These cases each produce the named op, and the defining property
    holds after each:
    - a known subject whose last view row is retracted gives `del known`;
    - a known subject whose fact changes gives `put known`;
    - a new item in a covered drawer gives `put present`;
    - a present item whose look changes gives `put present`;
    - a present item that canon moves out of the covered places gives `del present`.
6b. **`present_on`** *(r2, pbr 3)*. Every answer carries it: a reset, an empty answer and a diff.
    A keyed document fed by a keyless service (and the reverse) is reset, and `apply` gives
    `present: null` (or `{}`) to match.
6c. **Handles back in** *(r2, holo-emitter a)*.
    - `unhandle` maps a current present handle to its id.
    - It answers `None` for a stale handle (the item since perceived or moved away), a forged one,
      another key's, or one for a person.
    - A standalone `record` naming a current handle writes the event, and the next feed reveals the
      item.
    - A batch with one bad handle is `refused` and writes nothing.
    - *(r3, pbr)* A `POST /call` `record` with `entity: h` answers exactly `{"result":
      {"status": "recorded"}}`. The response bytes contain neither the canonical id nor any row,
      frame or receipt detail. The next feed then answers `reveal` → `put`.
    - A batch refused for a bad handle and one refused for a barred attribute give byte-identical
      HTTP responses.
6d. **Slot and address** *(r2, holo-emitter b, d)*. A canon literal `slot` and `address` on a
    drawer item cross; absent ones are omitted.
7. **Handles.**
   - The same key gives the same handle across exports.
   - A different key gives different handles.
   - A representative change gives `del` + `put`.
8. **Determinism.** Two exports of one state are byte-identical.
9. **Service.**
   - Both verbs serve from the snapshot.
   - They refuse `frame`, `frame_scope`, `at` and `key`.
   - A `set_view_frame` resets old cursors.
   - The walk test covers `VIEWER_SERVICE_READS`.
   - The runner's `POST /call` serves both, and `GET /changes` is 404.
10. **CLI.** The world file's sha256 and mtime are unchanged and no journal appears.
11. **Shared vectors.**
    - `tests/vectors/view-feed-v1.json` holds a fixture's export and a sequence of feed answers,
      for holo-emitter's JS `apply` to check against.
    - The Python `apply` is checked against the same file.
12. **Cost, measured and reported.** On the largest construct world copy: export time, feed time
    (two exports) and the document's size. It fails above 5 s for a feed.

## Not in this spec

- The JS `apply` and the manor's use of the document. Those are holo-emitter's, from these
  vectors.
- Recipes and promotion (E3 and later).
- Pushing changes (a websocket). The feed is pull, matching holo-emitter's `?since=` poll.
- Any change to the engine core.

## Lexicon (added with the build)

- **offline mirror**: the device's copy of the player's view: a `patternbuffer.view/1` document
  kept in step by `feed`. It is distinct from `perceive_in`'s mirroring of resolved rows into a
  frame.
- **present layer**: the document's drawables of unperceived things in the places the view
  covers: kind, containment and declared look aspects, under handles.
- **handle**: the keyed, opaque id (`h:` + 20 hex) of an unperceived thing in the present layer.
- **view cursor**: the signed, opaque token a feed answers with and is next called with.
