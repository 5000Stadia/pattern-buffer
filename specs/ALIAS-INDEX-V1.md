# ALIAS-INDEX-V1: a deterministic alias pass between pass-0 and pass-1 (roadmap R24)

**Status:** r2 (2026-10-12): Part B specified, for pbr's review. r1 (2026-10-10): Part A built
and merged to local main (evals only). Part B was unblocked by g3bf5da P3 and R35, and the
monitor started it for Kabe (note nd86f34). Research note technique 1
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

## Part B: writing identity (r2)

### What was measured first (the pass mark rests on it)

Measured on the stored registries, at no model cost, by seeding each one as `grade_registry.seeded_registry`
does and adding Part B before promotion and `reconcile` (a scratch prototype; the build reproduces it as a committed harness check). B3 F1, fused
ids (one id, 2+ gold entities) and fragmented gold entities:

| Registry | main | Part B (distinct only) | Part B + merge candidates |
|---|---|---|---|
| R23 run1 | 0.7471, fused 1 (the vaults), frag 0 | 0.7517, fused 0, frag 0 | 0.7517, fused 0 |
| R23 run2 | 0.7303, fused 1, frag 0 | 0.7347, fused 0, frag 0 | 0.7347, fused 0 |
| R26 seq | 0.7517, fused 0, frag 0 | unchanged (no strong pair) | unchanged |
| R26 par1b | 0.8264, fused 1, frag 4 | 0.8320, fused 0, frag 4 | 0.8320, fused 0 |
| R26 par2b | 0.7910, fused 1, frag 7 | 0.7961, fused 0, frag 7 | 0.7961, fused 0 |

The findings:
- **The vault fusion is gone** in every registry that had it, and nothing else moves.
- **The Ilsa pair** stays merged wherever main merges it (run1 and run2). The engine's own
  `reconcile` already closes it, so Part B adds no merge for it.
- **F1 rises by +0.0045 to +0.0056.** That is well under the ~0.02 run-to-run noise floor, because
  the vaults are two of many gold entities. Part B cannot show an F1 gain above noise on these
  registries. **The fused-id count is the decisive measure,** and it is deterministic.
- **Merge candidates add nothing measurable.** They can also be wrong where a string is ambiguous:
  par1b proposes `place:vault` → `place:records_vault`, while "the vault" is exactly the string
  shared by two vaults. They stay a report.
- **The parallel registries' fragmentation (4 and 7) is untouched.** That is R25's work, not this
  pass's.

### The shape

- **Where.** In the harness's `Pipeline.commit`, right after the registry is seeded
  (`seed_items`) and before pass-1's items are replayed, classified and promoted.
  - The pipeline runs `alias_index.build_report(registry, segments)` on the same segments pass-0
    read.
  - For each **strong** distinctness pair (Part A item 5: different proper names, or coordination)
    whose two ids are both seeded, it writes `porcelain.reject(a, b)`, the host's `distinct_from`.
  - Then the engine's own gate, `promote_identity_proposals` and `reconcile`, respect it as they
    respect any `distinct_from`.
  - It is a host act: the pipeline is the book world's host (as in R35 §4's
    `confirm_frame_owners`). The engine is unchanged.
- **Persons are excluded.**
  - **Pseudonyms.** Two person cards with different proper names can be one person under a
    false name: the disguise, the reveal. A `distinct_from` is a hard veto. It would block the
    later `merge`, and it would also block `correlate`, the reveal path (FRAME-SCOPED-IDENTITY-V1
    §3(a)).
  - **So the pass writes `distinct_from` only when neither id is a person.** The person namespace,
    and a `kind` of `person`, are the same test S2 uses.
  - **Strong person pairs are written to the report only.** In par1b these are Sela Voss / Tovan
    Voss and Cray / Marn. A host may act on them.
- **Merge candidates stay report-only** (above).
- **What is recorded.**
  - Each `reject` is listed in the run's `alias_index.json` under `written`, with the evidence
    sentence and the receipt's outcome (`rejected`, `noop_already_distinct`,
    `conflict_already_merged`, `conflict_already_correlated`).
  - A `conflict_*` outcome writes nothing and is reported. The pass never retracts a merge.
- **The flag.** `Pipeline(alias_distinct=True)` is on by default.
  - It writes only non-person strong pairs. On every stored registry its one effect is the vault
    split.
  - The chapter test is re-run with it on, and must stay green.
  - `alias_distinct=False` restores today's commit exactly.

### Pass mark (fixed before the build)

On the five stored registries (R23 run1 and run2; R26 seq, par1b and par2b), each seeded with Part
B exactly as `Pipeline.commit` does, under the same engine as main:

1. **Fused ids: 0** in all five. The vault fusion is gone wherever it occurred (four registries).
2. **The Ilsa pair is merged** in every registry where main merges it (run1, run2).
3. **No new fusion and no new fragmentation** in any registry: the fused-id and fragmented-entity
   sets are subsets of main's.
4. **F1 is not lower than main's** in any registry. A gain is reported, not claimed: the measured
   +0.005 is under the noise floor.
5. **No person pair gets a `distinct_from`.** A fixture with two person cards that have different
   proper names and share an alias gets no row, and a later `correlate` between them still
   succeeds.
6. The chapter test and the full suite are green with the flag on. With it off, a commit's log is
   byte-identical to today's.

No new metered build is run for this item. A run that measures it end to end belongs to R27, which
comes back to Kabe first.

## Done means (Part A)

1. `alias_index.py` with unit tests on hand-made registries and texts; the
   full suite green.
2. Reports for R23's run1, run2 and the older registry, under
   `evals/results/2026-10-10-r23-pass0-baseline/`, with the vault and Ilsa
   pairs found in both fresh runs.
3. ROADMAP R24 notes Part A done and Part B waiting on g3bf5da.

## Build notes (Part A, 2026-10-10)

Taken in the build, each documented in `alias_index.py`:
- Only **strong** distinctness evidence (different proper names, coordination)
  excludes a merge candidate. Co-presence is reported as weak and only
  annotates: read literally, co-presence would exclude the Ilsa pair whenever
  "Renn" and "the gray woman" share a paragraph.
- Co-presence is per **paragraph**, not per segment: the segments are whole
  chapters, so segment co-presence would link nearly every pair.
- Different-proper-names and co-presence are checked only on **risk pairs**
  (pairs sharing an identifying string, or one listing the other's name);
  coordination on every same-kind pair. Checking all pairs lists thousands of
  unrelated ones.
- "the vault" and "vault" normalize to one key, `vault`; the report keeps the
  spellings. Ids are reported repaired (`_norm_id`), originals under
  `id_repairs`.
- Escape candidates are noisy on this story (sentence-initial words,
  surname-only "Voss"); they are a pre-pass-1 list to read, not a gate.
- Results: in run1 and run2 the vault pair is found (strong) and `vault` is
  ambiguous across three ids; the Ilsa pair is a merge candidate in all three
  registries. `Pipeline(alias_slice=False)` is the default and leaves the
  slice unchanged; turning it on is for a measured chapter-test run.
