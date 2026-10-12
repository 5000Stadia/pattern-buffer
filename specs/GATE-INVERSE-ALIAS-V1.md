# GATE-INVERSE-ALIAS-V1: inverse predicates swap direction at the gate

**Status:** DRAFT r1.2 (2026-10-08; r1.1: §5 output shape per construct's request; r1.2: pre-review fixes, see the last section), fast-tracked out of batch B of
`docs/AUDIT-2026-10.md` because it is **corrupting live host worlds**.

- Construct's play path (`p.ingest` over narration) reaches it whenever the
  extractor writes `holds` or `wearing`.
- 10 of 165 construct world files carry the inverted receipt. Live example:
  `person:cole held_by doc:school_folder` puts Cole inside the
  folder, and `place:archive_rooms held_by` four different objects puts the
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

- The receipt is `(inverse) holds->held_by` — marker FIRST (r1.2, pre-review item 8): an engine that predates the swap splits a receipt on `->` and would otherwise install the alias `held_by (inverse)`; with the marker first it reads the source `(inverse) holds`, an attribute that never occurs, and installs nothing.
- Item-level identity data (`aliases`, `same_as`, `name`) stays with the
  **original subject**, the entity the item described, not the swapped one.
- Under `atomic=True` nothing changes beyond the corrected row.

## §3 Text values are not aliased

When the value is not an entity, the attribute stays `holds`/`wearing`: an
ordinary domain fact, never in the containment family. Swapping would make text
a subject; refusing would lose a real fact.

## §4 Built-ins beat replayed receipts

`_rebuild_alias_map` (r1.2) runs **built-ins → replayed receipts (in log order;
each records the first hop applied) → pop the inverse keys**. A host override of
another built-in (`type->genre`) therefore outranks the built-in and survives
reopen, while old forward receipts `holds->held_by` can never install a forward
alias for an inverse relation. `(inverse) …` receipts are records, not map
entries. `add_attribute_alias` raises `ValueError` for an inverse key.

## §5 Finding rows already inverted (no new verb; the engine never rewrites)

Rows written before the fix keep their receipt and stay as they are (append-only).
A host lists and repairs them with the porcelain it already has. The recipe is
the executable block in `docs/ADOPTION.md` (marked `recipe:inverted-rows`; the
§5 test runs that block verbatim). Its contract (r1.2):

- **Finds** every `held_by`/`worn_by` row, in any host frame, that either carries
  a pre-fix receipt (`holds->held_by`, `wearing->worn_by`) **or has the same
  (entity, attribute, value) as a receipted row** — the receipt-less copies a
  host leaves by re-ingesting promoted values into canon (`receipt_id: None`).
- **Output** per row: `{assertion_id, frame, entity, attribute, value,
  value_type, valid, receipt_id}`. `valid` is the original `[valid_from,
  valid_to]`; `receipt_id` is the `canonicalized_from` row's own id, or `None`.
  `value_type` is `entity` if the value fits the gate's id grammar, else `literal`.
- **Repair is per group**, keyed by (frame, entity, attribute, value): retract
  **all** copies, assert **once**, in one `commit_set`. (Repairing copies one by
  one refuses the second as a cycle.) An entity-valued group is re-asserted
  swapped (`value held_by entity`); a **text-valued** group cannot be swapped — it
  is re-asserted as a literal `holds`/`wearing` (retract + re-assert, never a
  swap). The re-assert keeps the original interval (`timeless` when the row had
  no `valid_from`).
- **Until repaired**, the correct write on those pairs (`key held_by ralph`) is
  skipped as a containment cycle, and an `atomic=True`/`commit_set` containing it
  aborts (`AtomicAbort`, cause `gate_skip`). ADOPTION says so.

Repair is the host's call per group, because some inverted rows may have been
nonsense either way.

## §6 The extractor says which way possession points

Both extractor prompts gain one line: an object physically held or carried is
`<thing> held_by <person>` and a garment worn is `<garment> worn_by <person>` (r1.2:
the adjacent "use 'in' for all containment" line is reworded to "'in' for where a
thing or person is (a place or a container)" so the two read together; no spec tag
appears in the prompt text). That is fewer inverse items at the
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
- **§5:** the recipe (ADOPTION block, run verbatim) finds receipted rows, receipt-less
  copies, text-valued rows and nothing else; a grouped `commit_set` repair clears
  them; before repair the correct write is skipped / aborts an atomic set.
- **Skip detail:** a swapped item's skip record carries `detail: "authored: …"`;
  unswapped skips omit the key.
- **Alias rebuild:** `type->genre` survives reopen; `add_attribute_alias("holds")`
  raises; an older engine's `split("->")` replay of a post-fix world installs no
  attribute-matching alias.
- **`wearing`:** the same cases.
- **`atomic=True`:** a swapped item commits inside the unit.
- **Full suite green.**

## Internal pre-review (2026-10-08): RED on §5 only, gate GREEN-with-nits

**r1.2: pre-review fixes.** Every item below is resolved:
(1) the recipe also reports receipt-less copies (same triple as a receipted row, any frame, `receipt_id: None`); (2) `value_type` is in the output and a text-valued row is repaired by retract + re-assert as a literal `holds`/`wearing`; (3) repair groups by (frame, entity, attribute, value): retract all, assert once; (4) `valid` is in the output and the re-assert keeps it; (5) ADOPTION states that until repair correct writes are cycle-skipped and atomic sets abort; (6) `SkipRecord.detail` (optional, emitted only when set) carries the authored form of a swapped item; (7) rebuild order is built-ins → receipts → pop inverse keys, `add_attribute_alias` rejects inverse keys, `type->genre` survives reopen; (8) the receipt is `(inverse) holds->held_by`, verified against the base engine's replay logic (4404cc0); (9) both prompts reworded, spec tag dropped. Checked against copies of the construct worlds: see the commit message of r1.2. The findings follow as originally recorded.

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
