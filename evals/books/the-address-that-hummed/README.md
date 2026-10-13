# The Address That Hummed

The **practice book** for the speed work (`docs/SPEED-PLAN-2026-10-13.md`, step 3). Designs are
tuned on this book and on *The Last Honest Meter*. *The Weather That Would Not Leave* stays held
out, run only on frozen designs (Kabe, gate g936be9, accepting consult c4bb1f2 point 4).

- **Writer:** ChatGPT, through the Codex CLI (`gpt-6-luna`, high reasoning), from
  `provenance/BRIEF.md`. The brief is R27's, at half the length, with a different premise required
  and `alias_first_chapter` added to the key.
- **Size:** 6 chapters, about 11,500 words.
- **Premise (the writer's note):** a civic registry tries to map rooms whose addresses depend on
  memory, and a clerk finds that an erased chamber still holds her sister and several conflicting
  histories.

## Files

| File | What it is | Read by the build? |
|---|---|---|
| `ch01.md` … `ch06.md` | the text | yes, and nothing else |
| `key.json` | the writer's answer key, frozen (sha256 below) | never |
| `verdicts_A.json`, `verdicts_B.json` | the two final readers' verdicts on that key | never |
| `graded.json`, `dropped.md` | the entries both final readers confirmed, and the rest with their notes (`book_gold.py`) | never (the grader only) |
| `provenance/` | the briefs, the earlier rounds' verdicts, the writer's change notes | no |

The key's sha256 is `bd914c39d776fc82e590da2269c0643aa2309e5c5b7d815e245b42efeee436bc`.

## How the key was checked

At most two revision rounds were allowed, the same exit rule as R27's book (monitor note n0a0c92).

1. **Draft, then completion.** ChatGPT wrote the book and a thin key, then completed the key
   against its own text (`provenance/COMPLETE.md`), adding one clarifying sentence to chapter 2.
2. **Round 1.** Two independent readers checked every entry: reader A (Claude Sonnet) and reader B
   (Claude Opus), in `provenance/round1_verdicts_*.json`. They found merged objects, shared aliases,
   location ranges running past where things were, and fifteen places where the text contradicted
   itself. ChatGPT fixed the text first, then the key (`provenance/REVISE.md`,
   `CHANGES-round1.md`).
3. **Round 2.** Two fresh readers (`provenance/round2_verdicts_*.json`) found a much smaller set,
   including lies filed as beliefs. ChatGPT fixed those (`provenance/REVISE2.md`,
   `CHANGES-round2.md`). A rule was added: a knowing lie is a correction, never a false belief.
4. **Final check.** Two fresh readers checked the final key (`verdicts_A.json`, `verdicts_B.json`).
   Both confirm every entity and almost every holding and container. Reader B finds one repeated
   location error: the cast is still in the Sump at the start of chapter 3. The book is also
   inconsistent on whether the Mouth Room and the first house are one room.
5. **What is graded:** only the entries both final readers mark `ok`. Every other entry is listed
   in `dropped.md` with both readers' notes.
   - **Graded (`graded.json`):**
     - 71 entities and 160 of 161 alias first-chapters;
     - 6 look-alike pairs and 11 containers;
     - 53 moves;
     - 1 identity reveal. The other two were judged unclear by one reader, because the book wavers
       on whether its rooms are one room.
   - **One reveal is thin.** The practice book alone can't settle identity questions;
     *The Last Honest Meter* adds its own.
   - **Converted exception lists.** The readers recorded alias first-chapter verdicts as lists of
     exceptions. Both stated they checked every alias. `provenance/fields_from_exceptions.py`
     converts those lists into GRADE-LEAKS-V1 per-field verdicts: an unlisted alias of an `ok`
     entity is `ok`, and a listed one is `wrong` with the reader's reason.

## Not yet in the key

`as_fact` structured forms for beliefs, corrections and knowledge (GRADE-LEAKS-V1 §2). They come
from a separate authoring pass, verified per field by two readers, after GRADE-LEAKS-V1 is merged.
