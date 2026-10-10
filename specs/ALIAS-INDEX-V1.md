# ALIAS-INDEX-V1: a deterministic alias pass between pass-0 and pass-1 (roadmap R24)

**Status:** draft r0 (2026-10-10). Nothing built. Research note technique 1
(`docs/research/book-to-world-extraction-2026-10.md`), reshaped by what R23
measured.

## What R23 changed about the target

R24 was written against fragmentation. R23's seeded grade
(`evals/results/2026-10-10-r23-pass0-baseline/REPORT.md`, "After seeding")
shows the engine's own `reconcile` already closes the one split pass-0 makes
(Ilsa Renn / "the clerk"). The failure that survives to the world is a
**fusion**: in both fresh runs the Records Vault and the Seed Vault become one
place, chained through a third card named "the vault" whose string both vaults
also carry as an alias. So the pass's most valuable output is the evidence
that two cards are *not* the same, and the ambiguity of shared generic
strings, not more merges.

## Part A: harness only, buildable now

`evals/harness/alias_index.py`, deterministic, no model call, no engine
change. Input: a registry and the source text (or its segments). Output, a
JSON report beside `registry.json`:

1. **The index.** Normalized names and aliases (the grader's `normalize`)
   mapped to ids; per segment, which ids are hit and by what string (exact,
   title + surname, prefix).
2. **Ambiguous strings.** A string that maps to two or more ids, with the
   ids. "the vault" is the test case.
3. **Stoplist.** Kinship and address terms (mother, sir, the boy, the
   clerk...) are never treated as identifying; the list lives in the module,
   with a test per entry class.
4. **Escape candidates.** Capitalized strings in the text that match no name
   or alias, ranked by frequency, before pass-1 runs.
5. **Distinctness evidence.** Pairs of ids that cannot be one entity:
   different proper names of the same kind (Records Vault / Seed Vault),
   coordination in one sentence ("Sela and Marn"), and co-presence in one
   scene. Each with the sentence that shows it.
6. **Merge candidates.** A full proper name on one card that another card of
   the same kind lists as an alias (the Ilsa case), unless item 5 has
   evidence against the pair.

Graded by the R23 grader: run on the stored R23 registries (free, no model
call), the report must list the vault pair under 5 and the Ilsa pair under 6
in both runs. Wiring the per-segment hits into pass-1's registry slice
(INGEST-V2 §4.2) is behind a flag, off by default, so the chapter test is
unchanged until a run measures it.

## Part B: writing identity, waits on gate g3bf5da (P3)

Turning item 5 into `distinct_from` rows and item 6 into proposals the engine
acts on is identity work, and P3 asks that identity's root causes be fixed
first, through pbr. Part B is specified after Kabe's answer. If P3 is
accepted, the vault fusion is also an engine question (a merge chain through a
third card between two different proper names), which belongs in P3's spec,
not here.

## Done means (Part A)

1. `alias_index.py` with unit tests on hand-made registries and texts; the
   full suite green.
2. Reports for R23's run1, run2 and the older registry, under
   `evals/results/2026-10-10-r23-pass0-baseline/`, with the vault and Ilsa
   pairs found in both fresh runs.
3. ROADMAP R24 notes Part A done and Part B waiting on g3bf5da.
