# IDENTITY-REPRESENTATIVE-V1: a host merge can name the id the closure is served under

**Status:** r1, spec for pbr review before code. Author: pb, 2026-10-12.

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
     optional `representative`. Construct's ask covers only these two verbs; `retype(absorb=)` is
     left out of r1 and can follow.
   - The value must be `a`, `b`, or a member of either one's closure. Anything else raises
     `ValueError` before any write.
   - When given, the merge event gains one row, `event:merge_N · representative · <id>`.
     - It is timeless, has status `inferred`, and is written in the same unit as the merge's other
       rows.
   - **`representative` is a mechanism attribute** with status mark `inferred`. The gate never
     accepts it as an item, so prose, extraction and forged items can't write it.
   - Readers honour it only on a `kind · identity_merge` event whose `decided_by` is `host`. Engine
     merges never write one.
   - A merge that is a no-op (already merged) with `representative` given still records the
     designation: the same rows, on a new event with `decided_by · host` and no new `same_as` edge.
     This lets a host re-point an existing closure.
2. **The election.** A closure's representative is:
   - **(a)** the id named by the **latest** honoured designation (highest seq) whose:
     - named id is still a member of the closure;
     - merge's `same_as` edge is still visible (the edge from its `caused_by`). For a no-op
       designation, which has no edge, the event itself must be unretracted.
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
   the standing representative.
3. **Retraction.**
   - Retracting the designation row reverts to the prior designation or first-seen.
   - Retracting the merge's `same_as` edge cancels its designation and splits the closure (R35 §2
     settles the pair).
   - `asserted_as_of` pins see each stage.
4. **Mechanism.** A `representative` item is refused at the gate (`mechanism_attribute`). A forged
   row with the wrong status, or on a non-host merge event, elects nothing.
5. **Validation.** A representative outside both closures raises before any write. A no-op merge
   with `representative` re-points without a new edge.
6. **Byte-identity.** On copies of construct's worlds, which hold no designations, `resolve` and
   every read are identical to main.
7. The full suite passes, and construct's suite passes on the branch.

## Whitepaper

This adds row **A29**: a host merge may name the closure's representative, and the latest honoured
designation elects it. First-seen remains the rule otherwise. §11 is amended to match.
