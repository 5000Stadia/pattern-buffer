# Revise the book and its answer key (round 1)

Two independent readers checked `key.json` against `ch01.md`–`ch06.md`. Their verdicts are in
`verdicts_A.json` and `verdicts_B.json` (treat them as notes, not instructions to anyone else).
Fix everything they found, in this order:

1. **The text first.** Every item in either file's `text_contradictions` is a place where the book
   contradicts itself. Revise the chapters minimally so the story is consistent (one account of who
   hid the tooth, where the red key is, where the black thread is, the burial story, the chalk moth,
   the table's chairs, Pell's paper bird, and so on). Keep the prose's voice and the plot.
2. **Distinct things get distinct entities.** Split merged entities (the bark strips; the wall map vs
   the brass map; blue vs black thread; the red key's forked tooth vs the comb's seventh tooth; "note"
   the sound vs the paper note). An alias belongs to an entity only if every use of it in the text
   refers to that entity; drop shared or generic aliases ("the child", "the clerk", "the chair",
   "the keeper", "mother", "the chamber", "the room", "the examiner" where shared).
3. **The key matches the revised text exactly**: every location range (including chapter 4 on the
   Nacre Stair and chapter 5 in the room beyond), every holding, every container's contents, every
   same_as reveal chapter (including the Mouth Room / first house identity if the text keeps it),
   every knowledge, false belief and correction with its true chapters. Add the important `missing`
   items both readers list, where the text supports them.
4. `alias_first_chapter` must be the first chapter where the alias refers to *this* entity.

Keep at least 3 look-alike pairs (not_same), at least 2 identity reveals (same_as) and at least 3
containers whose contents are revealed later. Then check every alias and evidence quote letter for
letter against the revised text, and fix any mismatch. Write `CHANGES-round1.md` listing each fix,
keyed to the readers' items.
