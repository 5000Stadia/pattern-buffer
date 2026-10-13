# Faster book builds: the plan (2026-10-13)

**Decision:** Kabe paused the R27 book builds for speed work (gate g10c3af), then accepted all four
points of consult c4bb1f2 (gate g936be9). He also said yes to one 2-chapter profiling build on the
practice book once step 1 is merged. Round two (consult ce0ba1f) checked the revised plan: the
order is right, and it found five problems. Each is folded in below and marked *(r2)*.

Every step goes through spec, pbr review, build and merge. Nothing paid runs without Kabe's yes.

## Step 1. A bare harness: BARE-CALL-V1 (merged; profiled, see below)
- Every model-call attempt is one turn with no tools. It runs from an empty temporary directory,
  with a short fixed system prompt, no settings and no MCP servers, and a trimmed environment.
- A multi-turn answer is refused through the retry path.
- Then: a one-call smoke test, and the approved 2-chapter profiling build of *The Last Honest
  Meter* under BUILD-PROFILE-V1. That gives the real per-stage time, turns and tokens, and the
  measured output tokens per second.

## Step 1b. Effort and models per stage (Kabe, 2026-10-13, after the profile)
- **The profile** (`evals/results/2026-10-13-profile-lhm2/REPORT.md`): about 96% of output tokens
  are hidden thinking, and latency is output-bound (R² 0.97). The harness is about 1%.
- **Kabe's answer**, asked whether to test effort settings: "Yes and further consider alternative
  models and speed. We may want to initially index complex concepts like motive and dynamics
  escellating on a plot, but mostly gathering details accurately already established should be
  fast chore work, much of which can be batched for speed and much of which can be parallelized".
- **Reading:** tier the build by how hard each judgment is.
  - Deep thinking stays only where the book asks for interpretation: motive, dynamics, escalation,
    reveals.
  - Extracting stated detail is chore work: low effort or a smaller fast model, batched and run in
    parallel.
- **Next:**
  - STAGE-MODELS-V1: a per-stage model and effort setting in the harness. The defaults stay
    today's.
  - Then a measured comparison on the practice book: low effort, medium effort, and a fast model
    for the chore stages, each graded against the verified key.

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

## Step 4. The registry first, as category passes *(r3: Kabe's passes, co-designed with construct)*
Kabe (via construct ma2f75e): "Pass for cast list, pass for locations, etc". Construct's proposal
is `/home/k/Newproject/docs/design/SEEDING-REGISTRY-FIRST.md`; pb's read is m52998c. This replaces
r2's single whole-book cast call.
- **Pass 0, the registry, as concurrent category passes:** beings, places, key things, groups.
  - Each pass reads the whole text and writes a short list on a fast tier at low effort, so the
    wall time is the slowest pass.
  - Each name carries the chapter where the reader first knows it.
  - Code merges the lists, using (type, normalized name) as a blocking key. The **registry entry
    is the identity**, so two namesakes the author lists stay two. Code mints the ids.
  - **Pass 0 never joins two names into one being.** Hidden identities are pass 2's, so the
    registry is leak-safe by construction.
- **Pass 1, facts:** per chunk, fully in parallel, against the registry slice the reader knows by
  that chunk.
  - Fragments ("Breck") resolve by code only to a unique compatible entry among names known by
    then. Anything else goes to one batched fast call.
  - New entities arrive as escapes, and code registers them.
- **Pass 2, interpretation:** on the top model, in a few calls (motive, dynamics, reveals). Joins
  are written with their reveal chapter.
- **Where it lives:** INGEST-V2 (`evals/harness/pipeline.py`, `registry.py`) is promoted to a
  host-usable library that construct and the book runner share. Name resolution runs in that
  pre-pass, never in the engine's ingest gate. R51's closed types come into the engine.
- **Judging it:**
  - first, zero wrong merges across look-alikes, the Rex test (a man and a dog both named Rex stay
    two from the first commit), zero leaks and zero false beliefs in canon;
  - then time and cost.
- Two fresh views (construct's) come before any build.

## How results are reported *(r2)*
- Every receipt states how many complete end-to-end runs it rests on.
- A tail figure such as p95 is reported only with enough runs. With two runs the report gives the
  range; otherwise it says "unmeasured".
- A frozen design is run at least twice on the held-out novella before any claim about it.

## Unchanged
The append-only log, the role-authority matrix, the ingest gate, canon identity as truth, and
precision over recall.
