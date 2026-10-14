# Recipe goldens (RECIPE-VOCAB-V1)

Three coherence recipes, each a story and the facts a world should hold for it,
in schema `patternbuffer.recipe-facts/1`: `switched-light`, `code-lock`,
`take-and-drop`. The attribute names are `patternbuffer.vocab.RECIPE`'s.

- **Shape.** `entities` carry only `id`, `kind`, `names`. `facts` carry `entity`,
  `attribute`, `value`, `value_type`, `frame`, `valid_from` or `timeless`, and a
  `source`: `{"chapter", "sentence"}`, or `{"manifest": true}` for a host's
  declaration (the door's `fixture`).
- **Lane 1** (every change, no model): `tests/test_recipe_goldens.py` loads each
  golden into a fresh world under the vocabulary and checks it is clean and reads
  as the recipe says.
- **Lane 2** (on demand, metered): `evals/harness/recipe_lane.py` builds the story
  text with `patternbuffer.build` and `vocabulary=RECIPE`, then grades the world
  against the golden on folded reads. `--dry-run` shows what would run, `--oracle`
  wires the whole lane with a scripted model (free), `--metered` is the paid run and
  waits for Kabe's yes.

## Where each golden came from

- `switched-light` and `code-lock`: holo-emitter's drafts (`lab/recipes/`, from
  pb's rows m046211), corrected by the points settled on 2026-10-14. In
  `code-lock`: `outdoors` is timeless; the door's `fixture` is a timeless
  manifest row (the draft gave it `valid_from` 0); the door is `locked · true`
  and also `state · shut` (r1.2/r1.3); the draft cited sentence 5 but the story
  has four sentences, so the door, keypad and outside cite sentence 4.
- `take-and-drop`: holo-emitter's story and shape (a study and a hall joined by an
  open doorway; a book on a table, a page in the book; another table in the hall).
  Containment is `in` throughout (the engine has no separate `on`). pb added, for
  placement and routes: the doorway and the study table are `in place:study`, and
  `place:study connects_to obj:doorway`, so a route study, doorway, hall exists. The
  play (the book taken, `held_by person:player`, then put down `in obj:hall_table`,
  folding to the hall table) is not canon in the golden: the lane-1 test writes it.

## Known limit of lane 2

A manifest entry is anchored by an exact quote, so only entities whose names the
story contains can be seeded. `code-lock`'s story never says "door" or "outside":
the build can only get them as model-declared escapes, and the grade reports
whether it did.
