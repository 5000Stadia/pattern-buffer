# WHO-KNOWS-INVERSE-V1 — "given fact X, who knows it" (computed, not stored)

**Status:** Implemented; Cx pre-impl GREEN (inline). Additive on porcelain-v0.1.
Build item 3 (last) of the awareness-and-shape plan. Shape pre-ruled by the
round-robin (Cx 052/054, PB 060): the inverse of `frame_diff`, **computed**, with a
**stored `known_by` edge REJECTED** (it is recomputable from the `knows:` frames —
the exact RFC-002 membrane breach).

## Problem
The engine answers "what does observer O know?" (fold in `knows:O`). The
load-bearing inverse for a critical plot fact is "**who is aware of this?**" — which
NPCs know the culprit, who knows the cabinet is locked. Today that needs a scan.
This adds the inverse read directly, membrane-clean.

## The read
`who_knows(entity, attribute, value=None, as_of=None, asserted_as_of=None) ->
list[str]` — the `knows:*` observer frames for which the fact is **known** (folded,
not raw rows):
- gather the candidate frames: the distinct `knows:*` frames carrying a visible row
  on `(entity, attribute)` over the entity's identity closure (key/closure-scoped —
  only the frames that touched the key, never a full-log scan);
- for each candidate frame F, `fold_key(entity, attribute, frame=F)` — include F iff
  the fold has a winner **and** (`value is None` → the key is known at all, or the
  folded winner **value-matches** `value`, identity-aware: entity values compared by
  `resolve`, literals by equality);
- return the matching frames, sorted (stable).

Folded-not-raw means a **superseded or retracted** belief does not count (O no
longer "knows" a value they've updated away from), and identity merges are
respected — the transpose stays consistent with what `state(.., frame=O)` serves.

## Why computed, not a stored `known_by`
A `known_by` edge is recomputable from the `knows:` frames → storing it breaches the
membrane (RFC-002) and double-writes every belief. The inverse read is the transpose
of `frame_diff`: it derives the same answer from the frames that already exist. The
cost is closure-scoped to the queried key (the frames that touched it), **not** an
N-frame materialized lattice. If measurement later shows it hot, add a
frame-membership-by-fact **index** (a rebuildable sidecar) — never a stored edge.

## Porcelain + World (additive)
```python
p.who_knows(entity, attribute, value=None, as_of=None) -> [frame_id]   # knows:* frames
world.who_knows(entity, attribute, value=None, valid_as_of=None, asserted_as_of=None)
```

## Explicitly OUT of V1 (restraint)
- **Stored `known_by`** — rejected by doctrine (above).
- **Effective-knowledge public-union** (a frame "knows" X if X ∈ `knows:O ∪ public`)
  — Cx 052 marked this *optional*; deferred to V1.1. V1 is own-`knows:`-frame
  membership, which is exactly the hidden-secret case (a secret is not public, so it
  lives in specific `knows:` frames). The host can query `public`/`canon`
  separately. Adding the union later reuses the shipped multi-frame read-union.
- **Set-valued key membership** ("who knows alias X is among the names") — V1 folds
  functional keys + optional value; set-valued membership is a V1.1 nicety.
- A frame-membership index — only on a measured hot path.

## Tests (tests/test_who_knows.py)
1. A secret authored into `knows:alice` and `knows:bob` but not `knows:carol` →
   `who_knows(e, attr)` == `[knows:alice, knows:bob]`.
2. Value-matching: `who_knows(culprit, "identity", "person:ilsa")` returns frames
   that believe Ilsa, not those believing Marn.
3. Folded, not raw: a frame that asserted then **superseded** the value no longer
   matches the old value (and matches the new); a **retracted** belief drops.
4. Identity-aware value match (a frame believing `person:i` where `i` later merges
   with `ilsa` still matches `ilsa`).
5. `value=None` → every frame that knows the key at all.
6. Canon/non-`knows:` frames are not returned (V1 own-knows-frame scope).
7. Writes nothing; full suite green.
