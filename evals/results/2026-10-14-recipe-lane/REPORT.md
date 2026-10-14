# Recipe lane 2 (2026-10-14): the library builds the demo stories from text, graded against the goldens

Approved by Kabe (gate gc281c6, "All ok seems reasonable go for it").
- **Setup:** RECIPE-VOCAB-V1 lane 2 (`evals/harness/recipe_lane.py --metered`), Sonnet 4.6 at low
  effort, with the recipe vocabulary in the extraction prompt. Each recipe's story text goes
  through the build library and is graded key by key against its golden in `evals/recipes/`.
- **A false start:** the first attempt failed before any model call, because the runner used the
  shim's `(callable, name)` pair as the model. That was fixed in `b379538` and rerun; nothing was
  spent on it.

## Results

| recipe | keys matched | findings (`vocab.check`) |
|---|---|---|
| switched-light | 9 / 11 | 0 |
| code-lock | 11 / 23 | 0 |
| take-and-drop | 4 / 9 | 1 |
| **all** | **24 / 43** | 1 |

## What the misses are

**Most misses are facts the story text never states.** The goldens mix what the story says with
what the demo authored around it:
- **code-lock (12 misses).** The story never names a door or the outdoors ("the only way to exit
  the room is a keypad with a four digit number"), and it never gives the code's digits. So the
  door's location, fixture, lock, state and connection, `place:outside` and its looks, and the
  code 4071 (in canon and in the dog's knowledge) can't come from the text.
  - The keypad's `controls` and `control_mode` refer to the unnamed door, so they can't either.
  - These are the host's (holo-emitter's planner and manifest).
- **switched-light and code-lock:** "the light is off" and "the dog is on all fours" are implied,
  not stated (the dog is "a person who thinks they're a dog" in holo-emitter's note, not in the
  story text).

**Genuine extraction errors (3):**
- **take-and-drop: "a book lies on a table"** was written as the book `in place:study`, not
  `in obj:study_table`. This is the same nesting weakness as the one-location probe's c4.
- **take-and-drop: `exits` misused as a relation** (`place:study exits place:hall`). `vocab.check`
  flagged it as `wrong_value_type`, which is the lint working. The prompt gloss for `exits` should
  say plainly that it is only the word `none`.
- **take-and-drop:** the doorway and the study table weren't placed in the study, and no
  `connects_to` was written for the doorway. The story says "joined by an open doorway", which
  the model didn't turn into an edge.

## What this means

1. **Goldens need two kinds of key: stated and authored.**
   - A key the story states is graded in lane 2.
   - A key the host authors (planner choices, manifest facts, hidden codes) comes from the
     manifest or the host, so lane 2 should skip it, or seed it as the manifest does.

   Proposal: a per-key `source` of `"text"` or `"authored"` in `patternbuffer.recipe-facts/1`,
   with lane 2 grading only `text` keys. That's for holo-emitter to agree, then a small spec.
2. **On the keys the text does state, the build mostly holds.** The real errors are nesting ("on
   a table"), a vocabulary gloss (`exits`) and a passage-to-edge gap ("joined by a doorway").
3. **The `exits` gloss gets one plain sentence:** "only the word none; ways out are connects_to".
   That's a prompt change to the opt-in vocabulary section only.
