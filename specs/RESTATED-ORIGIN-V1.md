# RESTATED-ORIGIN-V1: a move written as both ends keeps only where the thing went

**Status:** r1.4 (pbr's r1.3 RED: the host's `attribute_default` contract is unchanged, because a call that would consult it skips the rule entirely; and the rollback's log-version bump is stated, not denied). r1.3 (pbr's r1.2 RED: the dry run is a dedicated mode with no classification or sidecar work at all, the injected clock isn't called in it, and the host's `attribute_default` is still asked once per attribute, its dry-run answer handed to the real run). r1.2 (pbr's r1.1 RED: the eligible group must see the call's own earlier identity merges and declarations exactly as the real write does, so it is found by a rolled-back dry run of the whole call with ordinary sequential semantics, not by checking each item against the pre-call state). r1.1 (pbr's r1 RED: the group holds only containment items that pass every individual pre-write check, staged without side effects; and the family is every effective containment-family member, declared ones included). r1, for pbr review. Author: pb, 2026-10-14. An engine change at the ingest gate:
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

0. **A dry run finds the eligible writes** *(r1.2, pbr; replaces r1.1's per-item staging)*.
   - When the call holds two or more items, the gate first runs the **whole call**, unchanged and
     in input order, inside an isolated unit that is always rolled back. It uses the existing
     machinery: `buffer.atomic_unit` with the ingestor's view snapshot and restore
     (ATOMIC-ACTIVATION-V1 §B4).
   - So every earlier item's effect on later ones is exactly the real path's. That covers an
     earlier `same_as` changing what a later container resolves to, an earlier manual
     `attr:stowed_in · relation_family · containment` making later `stowed_in` rows containment,
     a first-use declaration, alias receipts and cursor stamping.
   - The dry run records, for every containment row that would be written, its item index,
     resolved entity, frame, stamped valid time and resolved container. Its family is the one in
     force at that row's write: built-in, declared before the call, or declared earlier in the
     same call.
   - **Nothing survives the dry run:**
     - the transaction rolls back;
     - the ingestor's in-memory views are restored from the snapshot. That covers the alias map,
       the attribute-default memo, the scene cursor and `last_skipped`; the build extends the
       snapshot with any other view the call mutates;
     - the semantics and identity views are refreshed from the restored log, keyed on the log
       version;
     - its skip receipts are discarded.
   - *(r1.3, pbr)* **A dedicated dry-run mode, not `defer`.** Inside the dry run the ingestor
     does **no classification work of any kind**. There is no inline, batch or rules
     classification, and no `_classify_guarded_since`, so `Classifier.classify_if_guarded` and
     its `_store` are never reached. Nothing touches the classifier's sidecar, memo or verdict
     state, and there's no commit. The dry run records would-be writes and appends rows only
     inside its rolled-back unit.
   - *(r1.3, pbr)* **No external calls in the dry run:**
     - **The injected clock is not called.** Where the gate would stamp `learned_at_wallclock`
       from `self._clock()`, the dry run uses a fixed placeholder. The value can't affect any
       eligibility check, since it is a meta row on the new assertion. The real run calls the
       clock exactly as today: same count, same values.
     - *(r1.4, pbr; replaces r1.3's recorded asks)* **The host's `attribute_default` is never
       asked by the dry run, and its contract is unchanged.**
       - Before any dry run, the gate checks whether the call would consult the callback. That
         is, whether a callback is set and any item's attribute is one the callback has not been
         asked about: its pre-call canonical name is not in the ingestor's checked set, carries
         no declaration, and isn't core.
       - If so, **the rule is skipped for the whole call:** no dry run, and the call is written
         exactly as today, with the callback consulted at the real declaration step as now.
       - This costs little. The callback is consulted once per attribute per world, so only a
         call introducing a new attribute name skips the rule. Construct's per-turn settle calls
         mostly reuse known attributes.
       - Both alternatives were rejected. Calling the callback speculatively would make it
         observable for a first use that ends up dropped, which pre-feature behaviour never
         does. Requiring every host's callback to be speculation-safe would be a new contract.
     - The build lists every external call the gate path can make (the model, the clock, the
       `attribute_default` callback, any other injected callable it finds). A test proves the
       dry run makes none of them.
   - **No trace** now also means: the classifier's sidecar table, in-memory verdicts and memo
     are unchanged by the dry run alone. Only the rolled-back unit ever saw its rows.
   - *(r1.4, pbr)* **The log version moves, by design.** Like every rolled-back atomic unit, the
     dry run's rollback calls `_forget_view()`, which advances `log_version`. That is a cache
     invalidation, not a change of truth: every derived view rebuilds from the restored log on
     its next read and serves the same answers. The rule doesn't restore the old version number,
     which would let a stale cache survive. The test asserts equal reads and an equal dump, not
     an equal version.

   - **Item rejected in the dry run:** an item rejected by any ordinary gate check is never an
     eligible write, so it never joins a group, and its skip is recorded once, by the real run
     (r1.1's 3b holds).
   - **The real run** is then the call exactly as today, with each dropped item (step 4)
     replaced by its `restated_origin` skip at its input position. It is authoritative for
     everything written.
   - Dropping a restatement removes only an edge that already exists in the fold. It can't
     create a cycle, a merge or a declaration that the dry run didn't see, so the real run's
     other rows are the dry run's.
   - **A call of one item** skips the dry run: a group needs two rows.
   - **Atomic calls:** the dry run is its own rolled-back unit, finished before the real atomic
     unit opens. The units are never nested.
1. **The group.** The dry run's eligible containment writes. Each one's attribute is in the **effective containment family** at its write
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
3c. *(r1.2, pbr)* **An earlier merge in the same call:** origin `ring in obj:belt`; then one call
    with `obj:leather_belt same_as obj:belt` first, then `ring in obj:leather_belt` and `ring in
    person:tomas` at one time. The second spelling resolves to the origin, so it is skipped
    `restated_origin`, and the merge is written as today.
3d. *(r1.2, pbr)* **An earlier manual declaration in the same call:** one call with
    `attr:stowed_in · relation_family · containment` first, then `ring stowed_in obj:belt`
    (origin `ring in obj:belt` before the call) and `ring in person:tomas` at one time. The
    `stowed_in` row is skipped `restated_origin`, and the declaration is written.
3e. *(r1.2)* **Atomic versions** of 1, 3c and 3d: `atomic=True` with `classify="rules"` gives the
    same rows. Any skip still aborts the set, as `restated_origin` is a skip.
3f. *(r1.2)* **The dry run leaves no trace:**
    - after a call whose dry run held a merge, a declaration, a first-use declaration and an
      alias receipt, the world's dump equals that of a twin world given the same call with the
      dropped items removed by hand (the same rows, ids and seqs);
    - the ingestor's views equal a fresh reopen's;
    - *(r1.4, pbr's scenario)* A recording `attribute_default` declares `stowed_in`
      containment. With prior `ring in obj:belt`, one call holds `ring stowed_in obj:belt`
      (stowed_in's first use) and then `ring in person:tomas`.
      - The rule is skipped for the call: no dry run, and no `restated_origin`.
      - The callback is asked about `stowed_in` once, by the real run, exactly as without the
        feature.
      - Both rows are written, and the key reads conflicted, as today.
      - The same call after `stowed_in` is already known (a prior call used it) runs the rule
        and drops the restatement, with the callback not asked again;
    - *(r1.4)* a call with no callback set, or with only known attributes, runs the rule;
    - *(r1.3, r1.4)* the dry run alone (exercised through a test seam that stops after it)
      leaves the classifier's sidecar rows, its in-memory verdicts and memo, the dump and every
      read unchanged. `log_version` advances, and the next read rebuilds the same answers. That holds for a call with guardrailed rows (a `person:` containment
      row, a `name` row) and a structural row;
    - *(r1.3)* observe mode: a counting clock is called the same number of times, and the stored
      `learned_at_wallclock` values are the same, as for the same call with the rule disabled;
    - a one-item call makes no dry run (spy on `atomic_unit`).
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
