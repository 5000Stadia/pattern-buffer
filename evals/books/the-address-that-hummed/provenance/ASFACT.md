# Add structured fact forms to the answer key (and change nothing else)

`key.json` describes the novella in `ch01.md`–`ch06.md`. Its `false_beliefs`, `corrections` and
`knowledge` entries are prose. A grader needs each one also as a single structured fact. Add these
fields and **change nothing else in key.json** (no other field, entry, order or text may change):

- A **fact form** is
  `{"entity": "<entity key>", "attribute": "<plain attribute>", "value": {"entity": "<entity key>"} | {"literal": <string, number or boolean>}}`.
  Every key named must be an entity key already in `key.json`. Use plain, short attribute words a
  reader would use (for example `in`, `held_by`, `status`, `is_alive`, `name`, `kind`, `relation_to_ivara`).
- `false_beliefs[i].as_fact`: the believed (false) fact.
- `corrections[i].as_fact`: the claim as first stated; `corrections[i].corrected_as_fact`: the true
  fact, or `null` when the correction only negates the claim.
- `knowledge[i].as_fact`: the fact learned (for `learns`) or never learned (for `never_learns`).
- When an entry cannot honestly be put as one fact, write `"as_fact": null` (and for corrections
  `"corrected_as_fact": null`). Do not force it.

Write `ASFACT-NOTES.md` with one line per entry saying what you chose or why it is null.
