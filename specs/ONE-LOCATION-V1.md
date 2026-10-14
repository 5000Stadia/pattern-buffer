# ONE-LOCATION-V1: when a thing moves, extraction writes only where it ends up

**Status:** r1, for pbr review. Author: pb, 2026-10-14. A prompt change to the engine's Ingestor
(both rule sets) and the build library's extract prompt. It doesn't merge until its metered check
passes, and the check is a paid run that waits for Kabe's yes.
**Source:** construct's R20 run 11, checked by pb in a read-only copy of its play world.
- **The failure:** one extraction of one turn wrote `obj:key_ring in obj:belt`, restating where
  it already was, and `obj:key_ring in person:tomas_venn` at the same valid time. The
  containment key then read conflicted, and the next turn refused the object.
- **Whose prompt:** the engine's Ingestor `lean` prompt. Construct's player channel and narrator
  settle both call `porcelain.extract(..., extract='lean')` (construct mcf358d), and construct
  adds no prompt of its own.
- **Construct's mitigation:** it now drops a same-turn restated origin in its own settle
  (`docs/design/RESTATED-ORIGIN.md`). This spec stops the model writing the pair at all. The
  engine-side gate rule was withdrawn (RESTATED-ORIGIN-V1).

## The change

1. **The Ingestor, `_EXTRACT_RULES_FULL` and `_EXTRACT_RULES_LEAN`:** one new rule after the
   held/worn rule:
   > `- a thing or person is in one place at a time. When the passage moves it, write only where
   > it ends up ('in', 'held_by' or 'worn_by' the new place or holder), never a row for the place
   > it left: that is already known. The place it left belongs only in a moved event's 'origin'.`
2. **The build library, `extract._RULES`:** one sentence after "Attributes: 'in' for all
   containment and location.":
   > `A thing is in one place at a time: when the passage moves it, write only where it ends up,
   > never the place it left.`
3. **Nothing else.** No gate or fold change, and no change to the moved-event rule. Its
   `origin` key stays where an origin is recorded when the movement is narrated.
4. **The pinned prompt texts change.** Tests that pin a prompt are updated to the new text, and
   that's reported in the build. Any prompt hash used in a run's receipts changes too.

## The metered check (Kabe's yes, before merge)

Cheap and targeted. Sonnet 4.6 at low effort, one run each.

- **(a) A move probe:** `evals/probes/one-location/`, 10 short passages written fresh for this
  check (no play text), each a narrated move of a thing or person. A ring off a belt into a hand;
  a page from a book onto a table; a person from a hall into a study; a coat from a peg onto a
  shoulder; and so on.
  - **Two controls:** a passage where a thing is described but doesn't move, and a passage where
    a thing is put back where it was.
  - Each passage is extracted through the engine's `lean` and `full` Ingestor prompts, on the old
    prompt and the new.
  - **Pass:**
    - with the new prompt, no passage yields two containment-family rows for one entity at one
      valid time;
    - every moved thing's final location is written;
    - the controls keep their one location.
  - The old prompt's count of same-time pairs is reported beside it, as the baseline.
- **(b) No regression:** the practice book's chapters 1–2 through the library pipeline (as in the
  library comparison), graded with `--through-chapter 2`.
  - Pass: zero leaks, zero wrong merges, and order and final-container scores no lower than the
    last complete run's (order 0.411, final 0.273), within one run's noise. With one run, a drop
    is reported, not hidden.
- **Cost:** about 40 short calls for (a) and one 2-chapter build for (b), roughly $1.50 in all on
  Kabe's Claude plan.

## Tests (no model calls)

1. Both Ingestor rule sets contain the new rule exactly once, after the held/worn rule.
2. The build library's `_RULES` contains its sentence exactly once. Without a vocabulary,
   `build_prompt` is otherwise unchanged: the byte-identity test is re-pinned to the new text.
3. The moved-event rule text is unchanged.
4. The probe runner (`evals/harness/one_location_probe.py`) parses a stubbed answer and counts
   same-time pairs per entity. With a stub that writes a pair, it reports a fail.
5. Full suite green.
