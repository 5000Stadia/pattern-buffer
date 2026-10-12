# IDENTITY-REPRESENTATIVE-V1: a host merge can name the id the closure is served under

**Status:** r3. It answers pbr's r2 RED on the already-merged path (§1a, §1b). pbr agreed the
election rule; r2 folded in construct's answers (mc29a14). Author: pb, 2026-10-12.

**Source.** Construct's ask m0243e8 (its gate gc53c58), a root cause found on a fresh build of the
ironhold seed:
1. Construct's build folds a fragment into the arc's protagonist with
   `merge("person:elias", "person:elias_venn", …)`.
2. Election makes the closure's representative its first-seen member, which here is
   `person:elias_venn`.
3. So the committed arc row reads back as `person:elias_venn`, while the beats watch
   `knows:person:elias`.

Under P1, frames don't follow merges, so the hero's knowledge lands in a frame no beat reads. This is
the protagonist split from runs 2, 4 and 5.

The host has no way to choose the survivor. Its only workaround is rewriting every id in its
authored arc after each merge.

**Builds on:**
- IDENTITY-ROOT-CAUSES-V1 (`decided_by`, settled-apart pairs);
- FRAME-SCOPED-IDENTITY-V1 §2 (election reads canon rows);
- GATE-AUTHORITY-V1 §1 (mechanism attributes).

## Rule

1. **The designation.**
   - `merge(a, b, evidence, representative=None)` and `confirm(a, b, representative=None)` take an
     optional `representative`.
   - **`retype(spurious, kind, absorb=target)` designates `target` implicitly** *(r2, construct)*.
     Absorbing a slip id into its target always keeps the target as the representative.
     - **Why:** construct calls it at build time (`typing_conflicts` then `retype`). If the slip id
       was seen first, today it becomes the canonical id, so a wrong-kind id (`person:harth` for
       `place:harth`) would be served as the place.
     - **Scope:** this applies to future retype calls only. Earlier absorbs carry no designation and
       elect as before.
   - The value must be `a`, `b`, or a member of either one's closure. Anything else raises
     `ValueError` before any write.
   - When given, the merge event gains one row, `event:merge_N · representative · <id>`.
     - It is timeless, has status `inferred`, and is written in the same unit as the merge's other
       rows.
   - **`representative` is a mechanism attribute** with status mark `inferred`. The gate never
     accepts it as an item, so prose, extraction and forged items can't write it.
   - Readers honour it only on a `kind · identity_merge` event whose `decided_by` is `host`. Engine
     merges never write one.
1a. **The re-point event** *(r3)*. When the pair is already one closure and a designation is
    requested, the engine writes a **re-point event**. It carries no `same_as` and no `caused_by`.
    - Its exact rows, all timeless, status `inferred`, canon, in one unit:
      - `event:merge_N · kind · identity_merge`
      - `event:merge_N · evidence · <the call's evidence, or "re-point: <verb>">`
      - `event:merge_N · decided_by · host`
      - `event:merge_N · representative · <id>`
    - This is how a host re-points a closure it already merged.
1b. **Every verb, every outcome** *(r3)*. A designation is requested when `merge` or `confirm` is
    given `representative=`, and implicitly by `retype(..., absorb=target)`, which designates
    `target`.

    | Outcome | What is written |
    |---|---|
    | `merged` | The merge's ordinary rows plus the `representative` row on its event. |
    | `noop_already_merged` (merge, confirm or retype absorb) | The re-point event (§1a). The outcome stays `noop_already_merged`, and the Receipt gains `"repointed": true`. `confirm` and `retype` reach this write on their existing early-return path; it doesn't wait until `guarded_merge`. |
    | Any other (`vetoed`, `no_proposal`, a retype refusal) | Nothing. The Receipt's outcome says why, as today. No designation is ever silently dropped. |

2. **The election.** A closure's representative is:
   - **(a)** the id named by the **latest** honoured designation (highest seq). A designation is
     **honoured** when all of these hold *(r3: exact visibility predicates)*:
     - its `representative` row is visible, carries the mechanism mark `inferred`, and names an id
       that is a member of the closure as of the read;
     - its event's `decided_by` row is visible, marked, and `host`;
     - its event's `kind · identity_merge` row is visible;
     - **for an edge-producing merge:** the event's `same_as` edge, found through the edge's
       `caused_by` row naming the event, is visible;
     - **for a re-point event (§1a):** there is no edge to check, so the visible rows above suffice.

     Retracting any one of these rows withdraws that designation.
   - **(b)** otherwise the first-seen member, exactly as today.

   Election stays a pure function of the visible log, so it is stable across instances and
   rebuildable.
3. **Reversible.** Retracting the designation row, the merge event's `same_as` edge, or the no-op
   event ends that designation from that log position. Election then falls back to the next
   honoured designation, or to first-seen. `asserted_as_of` reads elect as of their position.
4. **Later merges.** Merging a third id into a designated closure without `representative` keeps the
   standing designation (the latest one still holds). A newer host designation replaces it.
5. **Engine and legacy merges** elect first-seen, as now. A closure with no honoured designation is
   byte-identical to today.

6. **The receipt names the representative** *(r2, construct)*.
   - Every merge, confirm and retype Receipt already carries `canonical_id`, which is `resolve(a)`
     after the write. It **is** the elected representative, and this spec pins that meaning in a
     test.
   - A host asserts `receipt["canonical_id"] == <its arc id>` before writing plot rows.
   - For a vetoed merge the field still reads the pre-merge closure's id, as today.

## What changes, and for whom

- **Only closures with an honoured host designation** change the canonical id they are served
  under. Everything that resolves ids follows the elected representative, as it already does.
- **Frames do not follow** (P1). Designating `person:elias` means knowledge written to
  `knows:person:elias` stays the hero's, and the arc reads back `person:elias`, which is construct's
  need.
- **Existing worlds** have no designations, so every read is byte-identical.

## Checks

1. **Construct's case.** merge(elias, elias_venn, representative=elias) means `resolve` of either
   id is `person:elias`. Without `representative`, it is `person:elias_venn`, as today.
2. **Latest wins.** A newer designation re-points the closure. A third id merged without one keeps
   the standing representative. That is construct's requirement: the arc's id must not move when a
   later fold adds a fragment.
2a. **Retype.** `retype(person:harth, "place", absorb=place:harth)` keeps `place:harth` as the
    representative even when `person:harth` was seen first.
2b. **Receipt.** `canonical_id` equals the designated representative after merge, confirm and
    retype.
3. **Retraction.**
   - Retracting the designation row reverts to the prior designation or first-seen.
   - Retracting the merge's `same_as` edge cancels its designation and splits the closure (R35 §2
     settles the pair).
   - `asserted_as_of` pins see each stage.
4. **Mechanism.** A `representative` item is refused at the gate (`mechanism_attribute`). A forged
   row with the wrong status, or on a non-host merge event, elects nothing.
5. **Validation.** A representative outside both closures raises before any write.
5a. **Re-point** *(r3)*:
    - `merge`, `confirm` and `retype(absorb=)` on an already-merged pair each write exactly the
      §1a rows, with no `same_as` or `caused_by`, and report `noop_already_merged` with
      `repointed: true`;
    - retracting the re-point event's `kind` row, or its `representative` row, withdraws it;
    - a `vetoed` or `no_proposal` outcome writes nothing, with or without `representative=`.
6. **Byte-identity.** On copies of construct's worlds, which hold no designations, `resolve` and
   every read are identical to main.
7. The full suite passes, and construct's suite passes on the branch.

## Whitepaper

This adds row **A29**: a host merge may name the closure's representative, and the latest honoured
designation elects it. First-seen remains the rule otherwise. §11 is amended to match.
