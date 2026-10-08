# GATE-INVERSE-ALIAS-V1: inverse predicates swap direction at the gate

**Status:** DRAFT r1.1 (2026-10-08; §5 output shape per construct's request), fast-tracked out of batch B of
`docs/AUDIT-2026-10.md` because it is **corrupting live host worlds**.

- Construct's play path (`p.ingest` over narration) reaches it whenever the
  extractor writes `holds` or `wearing`.
- 10 of 165 construct world files carry the inverted receipt. Live example:
  `person:callum held_by doc:school_archive_folder` puts Callum inside the
  folder, and `place:historical_rooms held_by` four different objects puts the
  room inside each of them.

It waits on Kabe's go-ahead, then pbr.

## The defect

`_BUILTIN_ALIASES` (ingest.py) maps two **inverse** relations onto forward ones:
`holds → held_by` and `wearing → worn_by`. `_canonicalize` renames the attribute
and never swaps subject and object. So `(ralph · holds · key)` is stored as
`(ralph · held_by · key)`: Ralph is located inside the key, and the key's
contents are Ralph. The only trace is the receipt `holds->held_by`.

Three further faults compound it (all reproduced by the gate auditor):
- **The repair is refused.** The correctly-directed `(key · held_by · ralph)` is
  then rejected as a containment cycle.
- **Text values leave the tree.** `(ralph · holds · "a lantern")` becomes Ralph's
  location, so Ralph drops out of the tree.
- **Removal doesn't stop it.** Deleting the entry does not stop it, because
  `_rebuild_alias_map` replays old `holds->held_by` receipts *after* the built-in
  table.

The comment "direction repaired by the extractor contract" is false: neither
extractor prompt mentions direction. No other built-in alias inverts direction
(checked: the `in` family, `connects_to`/`adjacent`, `part_of`, `kind`).

## §1 A separate inverse table

`_BUILTIN_INVERSE_ALIASES = {"holds": "held_by", "wearing": "worn_by"}`, removed
from `_BUILTIN_ALIASES`. The false comment goes.

## §2 Entity values swap; the receipt says so

When an item's attribute canonicalizes through the inverse table **and** its
value resolves to `value_type == "entity"`, the gate swaps entity and value
immediately after canonicalization. That is before the malformed-id gate,
identity resolution, interval checks and the per-edge checks, so every later
check sees the true direction.

- The receipt is `holds->held_by (inverse)`.
- Item-level identity data (`aliases`, `same_as`, `name`) stays with the
  **original subject**, the entity the item described, not the swapped one.
- Under `atomic=True` nothing changes beyond the corrected row.

## §3 Text values are not aliased

When the value is not an entity, the attribute stays `holds`/`wearing`: an
ordinary domain fact, never in the containment family. Swapping would make text
a subject; refusing would lose a real fact.

## §4 Built-ins beat replayed receipts

`_rebuild_alias_map` applies the replayed receipts first and both built-in tables
last, so a built-in mapping always wins. Old forward receipts `holds->held_by`
therefore no longer install a forward alias. The `(inverse)` receipts are
records, not map entries.

## §5 Finding rows already inverted (no new verb; the engine never rewrites)

Rows written before the fix keep their receipt and stay as they are (append-only).
A host lists and repairs them with the porcelain it already has:

```python
receipt_of = {f["entity"]: f["provenance"]["assertion_id"]
              for f in p.facts("canon", attribute="canonicalized_from", include_meta=True)
              if f["value"] in ("holds->held_by", "wearing->worn_by")}
inverted = []
for frame in host_frames:
    for f in p.facts(frame, attribute="held_by") + p.facts(frame, attribute="worn_by"):
        aid = f["provenance"]["assertion_id"]
        if aid in receipt_of:
            inverted.append({"assertion_id": aid, "frame": frame,
                             "entity": f["entity"], "attribute": f["attribute"],
                             "value": f["value"], "receipt_id": receipt_of[aid]})
        # repair: commit_set([retract(aid), assert(swapped)]) — host-judged
```

**r1.1: output shape per construct's request.** Per world, `inverted` holds one
dict per already-inverted row: `{assertion_id, frame, entity, attribute, value
(as stored), receipt_id}`, where `receipt_id` is the `canonicalized_from`
receipt row's own assertion id. The §5 test asserts this shape.

The recipe goes into ADOPTION. Repair is the host's call per row, because some
inverted rows may have been nonsense either way.

## §6 The extractor says which way possession points

Both extractor prompts gain one line: possession is `<thing> held_by <person>`
and clothing is `<garment> worn_by <person>`. That is fewer inverse items at the
source; the gate swap stays the guarantee.

## Non-goals

- `contains`, which is a sanctioned set-valued domain key (`test_fold.py`), not
  an inverse alias.
- Any engine-side rewrite of existing rows.
- Other gate items in batch B.

## Tests

- **§2 swap:** `(ralph holds key)` gives `locate(key) == [ralph]`, `locate(ralph)`
  unchanged, and the receipt `(inverse)`.
- **§2 again:** the correctly-directed follow-up is admitted, not refused as a
  cycle.
- **§2 identity data:** an item's `aliases` stay on the original subject.
- **§3:** `(ralph holds "a lantern")` stores a literal `holds`, and Ralph keeps
  his location.
- **§4:** a world carrying an old `holds->held_by` receipt, after
  rebuild/reopen, still swaps new `holds` items.
- **§5:** the recipe finds exactly the pre-fix rows in a seeded world.
- **`wearing`:** the same cases.
- **`atomic=True`:** a swapped item commits inside the unit.
- **Full suite green.**

## Internal pre-review (2026-10-08): RED on §5 only, gate GREEN-with-nits

Fix these before pbr signs off. Probes (p1–p13) are in the session scratchpad.

**§5 recipe**
1. **It misses receipt-less copies.** Construct re-ingests promoted values into
   canon already as `held_by`, which leaves 17 rows without a receipt across 3
   files. The fix: also report any `held_by`/`worn_by` row with the same
   (entity, attribute, value) as a receipted row, with `receipt_id: None`.
2. **Text-valued inverted rows can't be repaired by a swap.** There are 8 of
   them. Repair is retract, then re-assert as a literal `holds`/`wearing`. Add
   `value_type` to the output.
3. **Duplicates in one frame refuse each other's repair as a cycle.** The fix:
   group by (frame, triple), retract all, assert once.
4. **The output drops `valid`.** Add it.
5. **ADOPTION gap.** It should say that until repair, correct writes on those
   pairs are skipped as cycles, and atomic sets abort.

**Gate nits**
6. A skip record should carry the authored form as well as the swapped one.
7. **Alias rebuild order.** Rebuild as built-ins → receipts → pop the inverse
   keys. Record the first hop of an alias chain. Reject inverse keys in
   `add_attribute_alias`. Today the order discards host overrides such as
   `type->genre`.
8. **Older engines misread the new receipt.** An older engine reading
   `holds->held_by (inverse)` installs the alias `held_by (inverse)`. Put the
   marker first, or use a separate meta attribute.
9. **Prompt wording.**
   - The rules say "use 'in' for ALL containment" right beside the new line.
   - Say "an object physically held or carried", not "possession".
   - Drop the spec tag from the prompt.

**Host notes for construct**
- The settle guard checks `attribute == "in"` only.
- `wearing` is not in construct's set-valued list.
