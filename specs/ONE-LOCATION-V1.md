# ONE-LOCATION-V1: when a thing moves, extraction writes only where it ends up

**Status:** r1.2 (construct's run 12, the first library-built world: three head-time conflicts from build extraction, a nested container written as two direct `in` rows and a place written `in` both its region and a river beside it; the rule gains the innermost-container and place-beside lines, and the probe gains their cases). r1.1 (pbr's r1 RED: the rule forbids only a former location active at the same time as the destination, so an expressly timed earlier interval is kept with its bounds; the probe's oracle is semantic, overlapping active intervals with distinct containers, and it gains a historical-move control). r1, for pbr review. Author: pb, 2026-10-14. A prompt change to the engine's Ingestor
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
   held/worn rule *(r1.1: narrowed)*:
   > `- a thing or person is in one place at a time. When the passage moves it, write where it
   > ends up ('in', 'held_by' or 'worn_by' the new place or holder), and never also write the
   > place it left as if it were still there at the same time. If the text dates an earlier
   > location ('at dawn it was on the belt; at noon she put it in the locker'), keep that
   > earlier row with its own time and end it where the move happens (valid_to).`
1a. *(r1.2, construct run 12)* Two more lines in both Ingestor rule sets, right after it:
   > `- write only a thing's innermost container: a peg in a cloth wrap in a pocket is 'in' the
   > wrap, and the wrap is 'in' the pocket; never the peg 'in' the pocket too.`
   > `- a place is 'in' at most one larger place (its town, region or building). A place beside
   > or along something (a river, a road, a coast) is 'adjacent_to' it, not 'in' it.`
   - **Why:** the containment family is one single-parent key, so a nested container written as
     two direct parents reads conflicted. The outer container is derived by `locate()` from the
     inner one's own location. A place's containment is CONSTITUTIVE by guardrail, so two
     parents for a place can never be settled by supersession (run 12's `place:ironhold`, in
     both a frontier region and a river).
2. **The build library, `extract._RULES`:** one sentence after "Attributes: 'in' for all
   containment and location." *(r1.1: narrowed)*:
   > `A thing is in one place at a time: when the passage moves it, write where it ends up, and
   > never also write the place it left as if it were still there.`
   *(r1.2)* And: `Write only the innermost container (a peg in a wrap in a pocket is in the
   wrap). A place is in at most one larger place; beside or along a river or road is
   adjacent_to, not in.`
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
  - **Five controls:**
    - a thing described that doesn't move;
    - a thing put back where it was;
    - *(r1.2)* **a nested container** ("The brass peg lay in a twist of oiled cloth in the
      courier's left pocket."). It passes when the peg has one container, the cloth, and the cloth is in
      the pocket;
    - *(r1.2)* **a place beside a river within a region** ("The fort of Greystone stands on the
      Wend river, in the northern marches."). It passes when the place has at most one
      `in` (the region), and the river relation, if written, is `adjacent_to`;
    - *(r1.1, pbr)* **a historical move with an expressly timed earlier location** ("At dawn the
      key hung on the belt. At noon she put it in the locker."). The earlier location must be
      kept, with an end at or before the move.
  - Each passage is extracted through the engine's `lean` and `full` Ingestor prompts, on the old
    prompt and the new, and ingested into a fresh world with `classify="rules"`.
  - *(r1.1, pbr)* **The oracle is semantic, read from the world, not raw row counts:**
    - **fail:** an entity with two distinct containment-family targets whose active intervals
      overlap, or a conflicted containment fold for the entity at any valid time where the
      passage gives it a place;
    - **not a fail:** adjacent half-open intervals (one ends where the next begins), and
      duplicate rows with the same target.
  - **Pass with the new prompt:**
    - no fails;
    - every moved thing's final location is written and is the served fold at the latest time;
    - the first two controls keep their one location;
    - the historical control keeps its earlier interval (served at an `as_of` inside it) and its
      later location.
  - The old prompt's fail count is reported beside it, as the baseline.
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
4. The probe runner (`evals/harness/one_location_probe.py`) applies the semantic oracle to
   stubbed answers:
   - a stub writing two distinct containers at one time fails;
   - adjacent half-open intervals pass;
   - duplicate same-target rows pass;
   - the historical control's two dated rows pass.
5. Full suite green.
