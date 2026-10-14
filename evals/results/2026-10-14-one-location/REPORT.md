# ONE-LOCATION-V1 metered check (2026-10-14): the prompt rule does not fix it

Approved by Kabe (gate gbed229, "All ok seems reasonable go for it").
- **Setup:** Sonnet 4.6 at low effort, one run each. The 15 passages are in
  `evals/probes/one-location/` on branch `feat/one-location`: 10 narrated moves and 5 controls.
  Each was extracted through the engine's `lean` and `full` Ingestor prompts, on the old prompt
  text and the new.
- **The oracle is semantic:** each answer is ingested into a fresh world. A fail is two distinct
  containment targets with overlapping active intervals, or a conflicted fold.

## Result

| prompt | lean: passages failing | full: passages failing |
|---|---|---|
| old (baseline) | 9 / 15 | 9 / 15 |
| new (ONE-LOCATION-V1 r1.2) | 8 / 15 | 10 / 15 |

**The rule doesn't work.** With one run per arm the difference is noise. The same failure
dominates both arms: a moved thing is written at its old and its new place at the same valid
time:
- the ring on the belt and in Mara's hand;
- the coat on the peg and on Odile's shoulders;
- the map in the satchel, in Sorrel's hand and on the wall.

The new prompt helped the place-beside-a-river control (c5) and the dated-history control (c3) in
`lean`. It did not stop same-time pairs.

**The merge condition failed, so ONE-LOCATION-V1 stays unmerged.** Branch `feat/one-location` is
kept for reference. The planned 2-chapter regression build was stopped once the probe failed:
there was nothing left for it to clear for merge.

## Why a prompt can't fix it

- **All of a passage's rows share one valid time.** For movement, the engine authors timestamps
  and the model is told not to invent them (MOVED-EVENT-V1 §B.3). So the model can't say "the
  belt row ended and the hand row began". Both land at the passage's time, and the fold sees two
  parents.
- **The model is trying to say it.** Containment rows carrying a `valid_to` key rose from 9 of 54
  (old prompt) to 21 of 58 (new). Of the 20 whose entity matches a passage's expectation, 18
  are a non-final (old) location, marked with `"valid_to": null`: an end it has no number for. It knows the old place ended; the output shape
  gives it no way to say so.

## What would fix it (a proposal, for spec and review)

Give the model a way to say a fact **ended in this passage**, and let the engine stamp it, the
same way the moved event's `complete` flag already works:
- A row may carry `ended_here: true`. The gate stamps that row's `valid_to` at the passage's own
  time (the cursor), so its interval is closed when the new location's begins (half-open,
  adjacent, not overlapping).
- The prompt then says: "When something leaves a place in this passage, write that old place
  with ended_here: true, and write its new place."

This uses what the model already does, and keeps timestamps the engine's. It needs its own spec
and pbr review. It also needs a fresh metered probe (the same 15 passages, so the comparison is
direct).

Two failures are a different problem and are left out of this proposal:
- **m03 and m08:** a person walked somewhere and no containment row was written at all.
- **c1:** "hung from a hook beside the cellar door" is read as being in the door. That is a
  judgment call on the control itself.
