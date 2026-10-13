# Faster book builds: the plan (2026-10-13)

**Decision:** Kabe paused the R27 book builds for speed work (gate g10c3af), then accepted all four
points of consult c4bb1f2 (gate g936be9). He also said yes to one 2-chapter profiling build on the
practice book once step 1 is merged. Round two (consult ce0ba1f) checked the revised plan: the
order is right, and it found five problems. Each is folded in below and marked *(r2)*.

Every step goes through spec, pbr review, build and merge. Nothing paid runs without Kabe's yes.

## Step 1. A bare harness: BARE-CALL-V1 (spec pbr GREEN, building)
- Every model-call attempt is one turn with no tools. It runs from an empty temporary directory,
  with a short fixed system prompt, no settings and no MCP servers, and a trimmed environment.
- A multi-turn answer is refused through the retry path.
- Then: a one-call smoke test, and the approved 2-chapter profiling build of *The Last Honest
  Meter* under BUILD-PROFILE-V1. That gives the real per-stage time, turns and tokens, and the
  measured output tokens per second.

## Step 2. Grading that sees the ending leak *(redesigned in r2)*
Round two showed that a "not one closure before the reveal" check measures nothing:
- **Canon identity has no story-time axis** (`identity.py`, `same_as` closures). The stranger *is*
  the duke in canon, at every time. A `same_as` join always fails such a check, and an `aka` join
  always passes it.
- **A dated `aka` never enters the closure** (AKA-CORRELATION-V1), so the existing B³ score would
  count every reveal as a split.

Canon identity therefore stays as it is: the truth, timeless. The grader gains three checks:
- **Provenance leaks.**
  - Every row from a chunk before a reveal's chapter that is written on the revealed identity, or
    that uses an alias whose `alias_first_chapter` is later, counts as a leak.
  - Rows carry their source chunk, and keys gain `alias_first_chapter` (the practice book's key
    has it already).
- **False beliefs and corrections,** which are graded for the first time (they are in the key,
  unread by `book_gold.py`):
  - a believed falsehood must never be canon;
  - where it is held, it belongs in the believer's `knows:` frame;
  - after its `corrected_chapter`, canon reads the corrected fact.

  This guards step 4: a chunk that knows only what the reader knows must not write the book's
  deceptions as canon.
- **Point of view:** per character, their `knows:` frame against the key's knowledge section.

## Step 3. A practice book (writing now)
- ChatGPT, through the Codex CLI, writes a second original novella: 6 chapters, about 12k words,
  with its own key including `alias_first_chapter`.
- Two readers verify the key, as for R27's book, and a mechanically renamed edition is added.
- **The development set** is this book plus *The Last Honest Meter*. *The Weather That Would Not
  Leave* is run only on frozen designs.

## Step 4. The whole-book cast call *(r2 checks added)*
- **The design:** one call writes the cast, and pass-1 runs fully in parallel.
- **The cast must carry time** *(r2)*. Today's registry holds untimed aliases and seeds them as
  timeless facts (`registry.py`), so a whole-book cast would leak a chapter-10 name into
  chapter 2. Each alias carries the chapter where the reader first meets it, chunks receive only
  the aliases known by then, and the seed path writes nothing a chunk couldn't know.
- **Size it before relying on it** *(r2)*.
  - The shim times out a call at 300 s and retries twice, so a long cast call could spend about
    15 minutes and abort.
  - From step 1's measured output tokens per second, project the cast call's length against the
    timeout and the CLI's output cap.
  - Run it once on the practice book first.
  - Split it if the projection needs it, for example cast first and reveals second.
- **Judging it:**
  - first, zero wrong merges across every look-alike pair;
  - then the step-2 checks (no provenance leaks, no false belief in canon, point of view);
  - then time and cost.

## How results are reported *(r2)*
- Every receipt states how many complete end-to-end runs it rests on.
- A tail figure such as p95 is reported only with enough runs. With two runs the report gives the
  range; otherwise it says "unmeasured".
- A frozen design is run at least twice on the held-out novella before any claim about it.

## Unchanged
The append-only log, the role-authority matrix, the ingest gate, canon identity as truth, and
precision over recall.
