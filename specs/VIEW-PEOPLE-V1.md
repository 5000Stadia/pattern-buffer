# VIEW-PEOPLE-V1: people on the device, where the world says they are

**Status:** r2 (pbr r1 RED: P1 a real place predicate, P2 the attribute list normalized), for pbr review and for Photonic's review as the host that needs it. Author: pb,
2026-10-13. The open questions to Photonic (m27078b) are marked *(Photonic?)*. Their answers can
change names, not the shape.
**Source:** roadmap R46. Photonic's SEAM (b) (m019da7): "Offline, the phone must know where people
are in rooms the player hasn't seen, so walking in finds them where the world says. The present
layer excludes persons by design … a 'people' layer of persons' canon position and activity on the
device. A curious single player could read it, which seems acceptable for a game." Kabe said yes on
gate gf985f8 ("2 agree"), **with that exposure accepted for single-player** (relayed in ma3a689).
**Builds on:** VIEW-EXPORT-V1 (the document, the feed, the cursor, `apply`, handles, the service
verbs, the CLI), AUTHOR-RECORD-V1 (how Photonic's people facts reach canon).

## Need

VIEW-EXPORT-V1 §2 keeps every person off the device. A person's canon looks would undo a disguise,
and their contents would put the gun under the coat on the phone. That suits a mystery manor. It
doesn't suit Photonic's game:
- The phone plays offline.
- The people move while the player isn't looking.
- When the player walks into a room nobody has shown them, the phone must already know who is
  there, and whether they are sitting or standing.

So the host needs a way to put **people's whereabouts and posture** on the device, and nothing
more. Kabe accepted that a curious player could read them.

## The shape

A third document layer, **`people`**, which is **off by default** and turned on by the host.

```python
export(world, view_frame, *, at=None, key=None, frame_scope="exact", people=None) -> dict
feed(world, view_frame, since=None, *, at=None, key=None, frame_scope="exact", people=None) -> dict
```

`people` is `None` (off) or a sequence of attribute names, the **person facts** that cross. The
empty tuple `()` means on, with position only.

### 1. Off is byte-identical to today

With `people=None`:
- the document has **no `people` key**;
- feed answers have **no `people_on` key**;
- the cursor body has **no `q` field**.

Every existing document, answer, cursor and digest is therefore unchanged. That includes
`tests/vectors/view-feed-v1.json` and holo-emitter's JS against it. A cursor minted before this spec
stays valid with people off.

### 2. The layer

```json
"people": {
  "person:mara": {"place": "place:parlour",
                  "in": ["in", "h:3f9c0a1b2c4d5e6f7a8b"],
                  "facts": [["heading", "place:kitchen", "id"], ["posture", "sitting", "lit"]]}
}
```

**Who is in it.** Every subject with a canon row as of `(head, at)` that is a person by
VIEW-EXPORT-V1 §2's test, keyed by its canonical id (the registry's representative as of `head`):
- a `person:` closure member;
- or an owner of a `knows:` frame;
- or a canon `kind` that folds to `person`.

That includes persons the player knows, because the view's facts about them can be stale and the
people layer is canon now. It also includes the player, which is harmless. A person whose record
would be empty (no place and no facts) is left out.

**Keyed by canonical id** *(Photonic? q2)*. The device's cast has to match these people to draw
them, so the key is the id the author wrote, such as `person:mara`. This is the exposure Kabe
accepted. Authors should name person ids neutrally (`person:mara`, not `person:the_killer`); the
spec can't enforce that.

**A place** *(r2, pbr P1)*. A subject is a place when it is either:
- a member of its identity closure (as of `head`) in the `place:` namespace;
- or a subject whose canon `kind` folds to `place`.

Being a containment root is **not** enough. An unattached safe, weapon or machine (`obj:*` with no
parent) is not a place, and its id never crosses as one.

**`place`**: the **nearest** place on the person's canon containment chain.
- The walk goes from the person up through the containment family (`in`, `within`, `held_by`,
  `worn_by`, `carried_by`, folded as one key, canon, as of `(head, at)`).
- The first ancestor that is a place gives its canonical id as `place`. It is whereabouts, so its
  id crosses. The nearest is chosen because a room inside a house is where the player walks in.
- No place on the chain (the chain ends at a non-place root, or the person has no parent): there
  is no `place`.
- A cycle, or a chain longer than 32, stops the walk, and `place` is omitted (logged at
  `WARNING`).

**`in`**: the person's immediate parent, only when it differs from `place`, as
`[relation, ref]` or `[relation, ref, slot]`. The relation and `slot` follow VIEW-EXPORT-V1 §2.
`ref` is:
- the parent's id if it is in `known`, or is a person (another person carrying a child: keyed in
  this layer);
- otherwise its **handle**, when a key is given. That is the same handle the present layer would
  give it, so a wardrobe the player can see as a drawable is the same wardrobe here;
- otherwise (no key) `in` is omitted.

The id of an unperceived container a person hides in never crosses. Only its handle does.

**`facts`**: for each host-named person fact, canon's answer
`state(person, attribute, frame=CANON, as_of=at, asserted_as_of=head)`. Only `known` answers
cross:
- a literal JSON scalar crosses as `[attribute, value, "lit"]`;
- an entity value crosses as `[attribute, ref, "id"]`. The `ref` is the id when the target is in
  `known`, is a person, or is a place (by the predicate above, not by being a root). Otherwise it is the
  target's handle with a key, or the fact is omitted without one;
- a set-valued key crosses as one tuple per member, by the same rules;
- an accrue key's derived quantity crosses as a literal;
- structured values (objects, lists), `conflicted`, `unresolved` and `unknown` are omitted. A
  conflicted posture is unknown to the device, never guessed.

Tuples are sorted as `known`'s are: `(attribute, type, canonical JSON of value)`.

**Normalized once** *(r2, pbr P2)*. At construction (service, runner, CLI) or at the call (`export`
and `feed`), `people` becomes one tuple: each name passed through `canonical_attribute`, then
deduplicated and sorted. `("Posture", "posture", "activity")` becomes `("activity", "posture")`.
That one tuple is what is validated, what the extraction reads, and what `q` hashes. Aliases and
repeats therefore give one fact tuple each and the same `q`. A `people` that is not a list or tuple
of strings is refused (`TypeError`).

**Which attributes may be named.** Each normalized name is checked. A name is
refused (`ValueError` at the call, or at service or runner start) when it is any of these:
- in the containment family (position is `place` and `in`);
- a mechanism, semantics, canon-identity or meta attribute (`_RECORD_BARRED_ATTRIBUTES`);
- `kind`, which is the person test's own key.

The host chooses the rest. *(Photonic? q1)* Photonic's names are expected to be something like
`posture`, `activity` and `heading`.
- **The spec's warning, in the docstring:** naming an appearance attribute ships canon looks, and
  that undoes a disguise. That trade is the host's to make for its game, not the engine's.

**Still never crosses**, even with the layer on:
- a person's contents (what they carry or wear). The walk never descends into a person, as in
  VIEW-EXPORT-V1 §2;
- any attribute the host didn't name;
- any `knows:` frame's rows;
- the id of an unperceived non-person, non-place thing.

### 3. Feed, cursor and apply

- **Cursor.** With people on, the body gains `"q": sha256(canonical JSON of the sorted canonical
  attribute list)`.
  - A cursor whose `q` differs from this call's (including absent vs present) is answered with a
    reset. Turning the layer on or off, or changing its attributes, therefore resets.
  - `_read_cursor` accepts an absent `q` (people off) or a 64-hex string.
- **Digest.** With people on, the digest covers `{"known", "present", "people"}`. With people off
  it covers `{"known", "present"}`, as today.
- **The answer.** With people on, it carries `"people_on": true`, and its ops can name
  `"layer": "people"`.
  - A reset puts every person after the other layers' puts.
  - A diff gives `del` and `put` for people, ordered like the other layers (by `(layer, key)`
    within each kind of op).
  - There is no `reveal` for people: they are keyed by id throughout.
- **`apply`.**
  - `clear` sets `people` to `{}` when the answer has `people_on: true`, and otherwise removes the
    key.
  - An answer without a `clear` whose people mode differs from the document's (a `people` key
    present vs `people_on` true) is an error, as for `present_on`. The feed never emits one.
  - `del` and `put` to `people` while the document has no `people` key is an error.
- **The defining property holds with the layer on:** `apply(export_at(c), feed(since=c)) ==
  export()` byte-identically, for every position.

### 4. In the service, the runner and the CLI

- `WorldService(..., people: Sequence[str] | None = None)` is the host's setting, validated at
  construction and kept on the service. `export` and `feed` pass it. A caller naming `people` is
  refused, as `frame` is.
- Runner:
  - `--people` turns the layer on;
  - `--people-attr NAME`, repeatable, names the person facts;
  - `--people-attr` without `--people` fails at start.
- CLI: `python -m patternbuffer.mirror export ... [--people] [--people-attr NAME ...]`, with the
  same rules.
- `unhandle` is unchanged.
  - A person is never in the handle map: persons are keyed by id.
  - A handle used as a person's `in` ref is a thing's handle. If that thing is in the present
    layer, `unhandle` maps it, as today. If not (the wardrobe sits in an unseen room), it doesn't.
    The device has nothing to report about an unseen wardrobe.

## Prior art

None needed beyond VIEW-EXPORT-V1's (Replicache's patches, CouchDB's opaque cursor). This is one
more folded layer through the same diff.

## Not in this spec

- Motion or paths. Photonic stores facts at rest; the device animates between them.
- A people layer for a multi-player or adversarial world. The exposure is accepted for
  single-player only (Kabe's gf985f8). A host that needs secrecy leaves the layer off.
- Perceived appearance. A person the player sees is in `known`, with the view's facts.
- JS. R47's module applies this layer from these vectors.

## Tests (the build's acceptance)

1. **Off is unchanged.**
   - With `people=None`, every document, answer and cursor in `tests/vectors/view-feed-v1.json`
     regenerates byte-identically.
   - A pre-spec cursor feeds with no reset.
2. **On, position.** On a fixture:
   - a person in an unseen room has `place` set to that room's id;
   - a person in a wardrobe in that room has `in` as the wardrobe's handle with a key, or no `in`
     without one;
   - a child carried by a parent has `in` as `["carried_by", "person:parent"]`;
   - a person with no parent has no `place`.
   - *(r2, pbr P1)* A person standing at an unattached `obj:safe` (no parent, not a place) has no
     `place`. An entity fact pointing to that safe crosses as its handle with a key, and is
     omitted without one. The safe's id appears nowhere in the document's text.
   - A person in `obj:wardrobe` in `place:bedroom` in `place:house` has `place` set to
     `place:bedroom` (the nearest), and `in` as the wardrobe's handle.
   - A root whose canon kind is `place`, under a non-`place:` id, counts as a place.
3. **On, facts.**
   - Named literal facts cross.
   - An entity fact crosses as an id when it points to a place, a person or a known thing, as a
     handle when it points to an unseen thing (with a key), and is omitted without a key.
   - Conflicted, unresolved and structured facts are omitted.
   - A fact the host didn't name never appears.
4. **Still never crosses.**
   - A gun carried by a person (`carried_by`) appears nowhere: no person's contents are walked.
   - An appearance attribute the host didn't name, and the person's rows in another `knows:`
     frame, appear nowhere in the document's text.
   - The id of an unseen wardrobe appears nowhere.
5. **Feed.**
   - An author moves a person (AUTHOR-RECORD-V1) and the next feed is a `put people` for them,
     with no `known` op.
   - A person's last canon row retracted gives `del people`.
   - The defining property holds over every position of a fixture history with the layer on, and
     on copies of construct's play worlds at 20 sampled positions each.
6. **Mode changes reset.** On to off, off to on, and a changed attribute list each answer `clear`.
   `apply` adds or removes the `people` key to match.
7. **Refused names.** `in`, `carried_by`, `kind`, `same_as` and a meta attribute are each refused
   at the call, at service construction and at runner start.
7a. *(r2, pbr P2)* **Normalization.** `("Posture", "posture")`, `("posture",)` and
    `["posture", "posture"]` give the same document and the same `q`, with one `posture` tuple per
    person. `"posture"` (a bare string) is refused.
8. **Service.** A viewer naming `people` is refused. `export` and `feed` serve the host's setting
   from the snapshot.
9. **Vectors.** `tests/vectors/view-feed-people-v1.json` holds a fixture export and feed sequence
   with the layer on, for R47's JS `apply`. The Python `apply` is checked against it.
10. **Cost.** On the largest construct world copy with the layer on: a feed (two exports) stays
    under VIEW-EXPORT-V1's 5 s.

## Lexicon (added with the build)

- **people layer**: the offline mirror's opt-in layer of persons' canon whereabouts (`place`,
  `in`) and the host-named **person facts**, keyed by canonical id. It is for single-player hosts
  that accept the exposure.
- **person facts**: the attributes a host names to cross in the people layer.
