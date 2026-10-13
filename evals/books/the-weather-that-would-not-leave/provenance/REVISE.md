# Revision brief

Your novella in this directory was read by an independent reader against ../BRIEF.md. Their full
report is ../AUDIT.md. Read it in full, then revise. The answer key must become exact gold: every
entry true to the text, and nothing important left out.

## Fix the text (keep the story, the world and its strangeness)
1. Remove every internal contradiction the audit lists, especially:
   - Mara's death date: one version only.
   - The rooms: the carved-names chamber, Mara's room and Vey's chair room are three distinct
     places with distinct names, and the text never fuses them.
   - Objects whose final whereabouts contradict each other (the seed, the vial, the key, the tin
     case): each ends in exactly one place.
   - Any other coherence item in the audit.
2. Chapter endings that stack extra paragraphs out of time order: weave them into the chapter in
   the right order, or cut them.
3. Make ambiguous references unambiguous where the audit flags a collision. For example, bare
   "flask" or "basin" should say which one whenever more than one is in play.
4. Keep each chapter around 2,000 words, and the whole around 25,000.
5. Make the Vey reveal a real reveal (she is met under another description before the reader can
   know who she is), or treat her open self-naming as plain fact and drop it from same_as. Either
   is fine; the key must match.

## Rebuild key.json
Apply the audit's corrections and fill its gaps:
- all named entities, including the missing objects and places;
- every alias, exactly as written;
- every pre-reveal description in same_as;
- every look-alike pair in not_same;
- holdings and locations for every object that moves;
- every container whose contents are revealed;
- false beliefs, including Or's belief that her mother is dead;
- knowledge, with "never learns" entries where the text makes them clear;
- corrections and lies.

Add a top-level "do_not_grade" list only for anything still genuinely ambiguous after the fixes,
with the reason. Aim for it to be empty.

## Finish with a check
Every alias and every evidence quote must appear letter for letter in the revised text, with the
text's own curly quotes and apostrophes. Fix any mismatch. Then list what you changed in a short
CHANGES.md.
