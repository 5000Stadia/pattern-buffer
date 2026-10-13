# The Weather That Would Not Leave

The test book for R27, "hand it a book and walk in". It is an original novella written for this
test, so no model can have read it before.

Kabe, 2026-10-13: "Make chatgpt write the fiction so its anonymous and original - tell it to try
to make something out there and original."

- **Writer:** ChatGPT, through the Codex CLI (`gpt-6-luna`, high reasoning), from
  `provenance/BRIEF.md`.
- **Size:** 12 chapters, about 25,300 words.
- **Premise (the writer's note):** a town stores weather in vessels and has forgotten the path that
  once let a storm pass through. Or Senn follows a chain of objects, records and disputed
  memories to find what was sealed away and who was erased from the town's history.

## Files

| File | What it is | Read by the build? |
|---|---|---|
| `ch01.md` … `ch12.md` | the text | yes, and nothing else |
| `key.json` | the writer's answer key, frozen (sha256 below) | never |
| `verdicts_A.json`, `verdicts_B.json` | the two readers' final verdicts on that key | never |
| `graded.json` | what is graded: the entries both readers confirmed (`book_gold.py`) | never (the grader only) |
| `dropped.md` | everything left out of `graded.json`, with both readers' notes | no |
| `provenance/` | the briefs, the first audit, the round-2 verdicts, the writer's change notes | no |

The key's sha256 is `27fc2aa57144a5922a34f65bfec767f6fcb0699abbd21bc37f46f984f4a165f3`.

## How the key was checked

There were at most two revision rounds (the monitor's exit rule, note n0a0c92).

1. **Draft:** ChatGPT wrote the book and key. A fresh reader (Claude Sonnet) audited them
   (`provenance/AUDIT-round1.md`): usable, but the key needed fixes and the text contradicted
   itself in places.
2. **Revision 1:** ChatGPT fixed the text and rebuilt the key (`provenance/REVISE.md`). Two fresh
   readers then checked every entry: reader A (Claude Sonnet) and reader B (Claude Opus). Their
   verdicts are in `provenance/round2_verdicts_*.json`.
3. **Revision 2, the last:** ChatGPT fixed every contradiction and entry both readers raised
   (`provenance/REVISE2.md`).
4. **Final check:** the same two readers verified the final key entry by entry against the final
   text (`provenance/VERIFY.md`). An entry is graded only if **both** marked it `ok`.
5. **Entities (BOOK-RUN-V1 r2.2):** an entity is graded on its kind and aliases only.
   - Four entities (`vey`, `old_cistern`, `nameless_jar`, `western_corridor`) had been marked
     down only for their `first_chapter`, which the grader never reads.
   - Both readers re-judged those four on kind and aliases alone, after re-checking the text, and
     found all four ok. Their answers are in `entities_fields` in each verdict file.

## What is graded

| Section | In the key | Graded |
|---|---|---|
| entities | 87 | 87 (3 aliases dropped) |
| same_as (reveals) | 17 | 16 |
| not_same (look-alikes) | 29 | 29 |
| locations and holdings | 115 | 99 |
| containers | 13 | 13 |
| knowledge, false beliefs, corrections | 51 | not graded in V1 (counts only) |

The 17 dropped entries and 3 dropped aliases are listed in `dropped.md`. Most are chapter ranges
the text leaves open, plus a few entries both readers found wrong.

## Known soft spots

The readers' final lists still name 12 and 17 small contradictions in the text (for example, whose
repaired cup it is in ch9). The entries they touch are among the dropped. The full lists are in
the verdict files, under `text_contradictions`.
