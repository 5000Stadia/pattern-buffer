# RESTATED-ORIGIN-V1: a move written as both ends keeps only where the thing went

**Status:** r1.1 (pbr's r1 RED: the group holds only containment items that pass every individual pre-write check, staged without side effects; and the family is every effective containment-family member, declared ones included). r1, for pbr review. Author: pb, 2026-10-14. An engine change at the ingest gate:
deterministic, with no model and no prompt change.
**Source:** construct's R20 run 11 (engine 42d0c23, letter "R20 run 11 … one engine-shaped
question"), checked by pb in a read-only copy of the play world:
- `obj:key_ring · in · obj:belt` at 0.0 (a:2643);
- then **one extraction, in one `ingest_structured` call**, wrote at the same valid time
  1001027.0 both `obj:key_ring · in · obj:belt` (a:5798, restating where it was) and
  `obj:key_ring · in · person:tomas_venn` (a:5799, where it went).
- `state()` serves the ring conflicted, and the next turn refused the narrated object.
- Construct agreed this fix ("(b) first"). Its settle promotes each turn in one
  `ingest_structured` call, so the rule sees the whole pair.
**Builds on:** the containment family as one functional key (`model.CONTAINMENT_FAMILY`, spec §7,
letter 002 Q1), and the gate's typed skips (`SKIP_REASONS`, `last_skipped`).

## Need

A single extraction of a move often names both ends: "the key-ring leaves the belt for your
hand". At one valid time, two containers on one functional key is a contradiction, and the fold
honestly serves it conflicted. But one timestamp can't express order. There is exactly one
reading in which both rows are true: the thing was at the old place, and is now at the new one.
The old place is already in the log, so the restatement adds nothing and only breaks the read.

## The rule

Within **one** gate call (`ingest_structured`, or `ingest`'s structured pass):

0. **Staged validation, without side effects** *(r1.1, pbr)*.
   - Before any containment row of the call is written, each item is run through every individual
     pre-write check it would face. That includes canonicalization, frame, identity resolution,
     the stamped valid time, the interval checks, the edge and cycle checks, and every other
     per-item skip.
   - This stage writes nothing: no declarations, no rows, no receipts.
   - An item that fails a check keeps its existing skip reason, recorded once, exactly as today.
     It never joins a group.
   - Only the **eligible writes**, items that would otherwise enter, are grouped below.
1. **The group.** Eligible writes whose attribute is in the **effective containment family**
   *(r1.1, pbr)*: the built-in family (`in`, `within`, `held_by`, `worn_by`, `carried_by`) and
   every attribute the world declares `relation_family: containment`
   (`AttributeSemantics.containment_family()`). For an item whose first use would declare its
   attribute, the family is projected from its declaration plan (`_family_after()`), as the gate
   already does. The group's rows have:
   - the same resolved entity, frame and valid time;
   - an explicit or cursor-stamped `valid_from`. Timeless rows are never grouped;
   - an entity value.

   A group of one is untouched.
2. **The origin.** The entity's containment fold in that frame, read **as of the log head before
   the call** (asserted-time bound) at the group's valid time. That's the existing `fold_key`
   read on the containment family. The origin is its served winner's container, identity-resolved,
   when the fold has a single winner. Otherwise there is no origin.
3. **Restatement.** A row restates the origin when its resolved container equals the origin.
   - The attribute may differ within the family. `held_by person:x` restates an origin of `in
     person:x`: the family is one key and the container is the same.
4. **The drop.** If the group holds **at least one restating row and at least one non-restating
   row**, every restating row is skipped with the typed receipt **`restated_origin`**.
   - Its `detail` holds `{"origin": <container>, "kept": [<the non-restating rows' containers>]}`.
   - Nothing is written for it. The non-restating rows are written as usual.
   - Two or more non-restating rows still disagree with each other and read conflicted, as
     today.
5. **Everything else is unchanged.** Specifically:
   - no origin;
   - every row in the group restates (duplicates);
   - none restates (two new places);
   - rows at different valid times, or written in different calls.

   Each of these is written exactly as today. The rule never drops a row that changes where a
   thing is, and never chooses between two new places.

- **Order inside the call doesn't matter.** The group is formed over the whole call before any of
  its containment rows is written, and the origin is read before the call.
- **Atomic sets:** `restated_origin` is a gate skip like any other. Under `atomic=True` it aborts
  the set with `AtomicAbort` (ATOMIC-ACTIVATION-V1 §B6). A host writing an atomic set sees why and
  fixes its input.
- **Authority:** the rule applies to every caller and mode (host or extracted), because the
  contradiction is the same whoever writes it.
- **The moved event** (MOVED-EVENT-V1) is untouched. Its `origin` key is where an origin belongs
  when the move itself is history. Its matched arrival `in` is a non-restating row, so it is
  kept.

## Not in this spec

- The extraction prompts (construct's option (a): "a thing has one location at a time; when it
  moves, write only where it ends up"). That is the root fix, but it's a prompt change: a later
  item with a metered check, which needs Kabe's yes.
- Anything across calls or across valid times.

## Tests (no model calls)

1. **The run-11 case:** `ring in belt` at 0, then one call with `ring in belt` and `ring in
   person:tomas` at 10.
   - The first is skipped `restated_origin`, with detail origin `obj:belt` and kept
     `[person:tomas]`.
   - `state(ring, "in", as_of=10)` is `person:tomas`, not conflicted. As of 5 it is `obj:belt`.
2. **Item order:** the same pair in the reverse order gives the same result.
3. **Across the family:** origin `in person:tomas`, then one call with `held_by person:tomas` and
   `in place:hall` at the same time. The `held_by` row is skipped; the `in place:hall` row is
   written.
3a. *(r1.1)* **A declared containment predicate:** `attr:stowed_in` declared
    `relation_family: containment`, origin `ring stowed_in obj:belt`, then one call with `ring
    stowed_in obj:belt` and `ring in person:tomas`. The restatement is skipped `restated_origin`.
    The same holds when `stowed_in`'s first use in this very call declares it containment
    (projected family).
3b. *(r1.1)* **A rejected change beside a restatement:** origin `ring in obj:belt`, then one call
    with `ring in obj:belt` and `ring in obj:ring` (a self-containment cycle).
    - The cycle edge is skipped with its existing reason, exactly once.
    - No `restated_origin` receipt is written, and the restating row is written as today.
    - Under `atomic=True`, the abort names only the cycle skip.
4. **Left as written:**
   - no prior location (both written, conflicted);
   - both rows new places (both written, conflicted);
   - both restating (both written, as today's duplicate);
   - different valid times in one call (both written);
   - the pair across two calls (both written);
   - timeless rows (untouched);
   - a different frame for each row (untouched).
5. **Identity:** the origin is `obj:belt`, and the restating row names its merged twin
   `obj:leather_belt` (`same_as` before the call). That row is recognised as a restatement and
   skipped.
6. **Atomic:** the run-11 pair under `atomic=True` raises `AtomicAbort` naming `restated_origin`,
   and nothing is written.
7. **Receipts:** `restated_origin` is in `SKIP_REASONS`, and `last_skipped` carries it with its
   detail.
8. **Full suite green**, with every existing test unchanged. A test that today expects a
   same-call conflict built this way is reported in the build, not silently edited.
