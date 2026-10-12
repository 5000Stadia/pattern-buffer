# ALIAS-INDEX-V1: a deterministic alias pass between pass-0 and pass-1 (roadmap R24)

**Status:** r4 (2026-10-12): it answers pbr's code RED.
- **A different finalization.** The grader's seeded measure ran `reconcile`; `Pipeline.commit`
  never does. So the r2 table measured a finalization that real book commits do not run.
- **What re-measuring showed.** Without `reconcile`, no registry fuses the vaults and none merges
  the Ilsa pair.
- **The fix.** r4 gives commit and grader one shared finalization that **adds `reconcile` to the
  book commit**, with Part B before it. It re-states the pass mark on that shared path, and it
  rejects an empty source (marked *(r4)*).

r3: it answered pbr's r2 RED. Commit reads a durable source, and a
fresh `Pipeline` reproduces the same commit (marked *(r3)*). r2: Part B specified. r1 (2026-10-10): Part A built
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

### *(r4)* What real commits do, and the finalization this spec gives them

- **What `Pipeline.commit` does today.** It finalizes identity with `promote_identity_proposals()`
  and `confirm_frame_owners` only. It never runs the engine's `reconcile`, the global
  shared-anchor pass.
- **What R23 assumed.** The "seeded" grade, `grade_registry.seeded_registry`, also ran
  `reconcile`. R23 read that as identity after commit; it is not what a book commit does.
- **The same five registries, measured both ways** (B3 F1 / fused / fragmented):

| Registry | commit today (no reconcile) | + reconcile | + reconcile + Part B |
|---|---|---|---|
| R23 run1 | 0.7517 / 0 / 1 (Ilsa split) | 0.7471 / 1 (vaults) / 0 | **0.7517 / 0 / 0** |
| R23 run2 | 0.7347 / 0 / 1 | 0.7303 / 1 / 0 | **0.7347 / 0 / 0** |
| R26 seq | 0.7517 / 0 / 0 | 0.7517 / 0 / 0 | **0.7517 / 0 / 0** |
| R26 par1b | 0.8320 / 0 / 13 | 0.8264 / 1 / 4 | **0.8320 / 0 / 4** |
| R26 par2b | 0.7961 / 0 / 13 | 0.7910 / 1 / 7 | **0.7961 / 0 / 7** |

- **`reconcile` alone** merges what should merge (Ilsa; 13 → 4 and 7 split entities in the
  parallel registries, the fragmentation that kept R26's parallel pass-0 off). It also fuses the
  vaults.
- **Part B before `reconcile`** keeps every one of those merges and removes the fusion. F1 equals
  today's commit in every registry. The gain is structural (fragmentation 1 → 0 and 13 → 4 / 7,
  fusion 0), not in F1.
- **Without `reconcile`,** Part B has nothing to prevent: its rows are written, but no merge path
  would have joined the vaults.

**The change.**
- **One shared finalization.** `pipeline.finalize_identity(w, *, reconcile: bool)` runs
  `promote_identity_proposals()`, then `reconcile()` when asked, then `confirm_frame_owners(w)`.
- **Both paths use it.** `Pipeline.commit` and `grade_registry.seeded_registry` both call
  `seed_world`, then `alias_distinct_pass` (when on, with a source), then, in commit only, the
  pass-1 replay and classification, then `finalize_identity`. Nothing else differs.
- **`Pipeline(reconcile=True)` by default.** Book commits now reconcile. `reconcile=False,
  alias_distinct=False` is today's commit, byte-identical.
- **Why default-on for both.** Reconcile without Part B fuses the vaults; Part B without reconcile
  does nothing. They are on together, and each can be turned off for measurement.

### The shape

- **Where.** In the harness's `Pipeline.commit`, right after the registry is seeded
  (`seed_items`) and before pass-1's items are replayed, classified and promoted.
  - The pipeline runs `alias_index.build_report(registry, segments)` on the same segments pass-0
    read.
- **The source is durable, not in memory** *(r3, pbr)*.
  - **`pass0` writes it.** `pass0` writes the exact parts it read (its `segments`, or `[text]`)
    to `run_dir/source_segments.json`, as `{"segments": [...], "sha256": <of the canonical JSON
    of the list>}`, beside `registry.json`.
  - **The file is the only source.** Nothing is cached in memory. A fresh `Pipeline` pointed at an
    already-staged `run_dir` reads the same file.
  - **`commit` takes an optional argument.** It becomes `commit(world_path, registry,
    segments=None)`. The source is chosen in this order:
    1. an explicit `segments` argument;
    2. otherwise `run_dir/source_segments.json`, whose `sha256` must verify (a mismatch raises
       before anything is written);
    3. otherwise **no source**. Part B is skipped, a warning is logged, and the report records
       `{"part_b": "skipped", "reason": "no_source"}`. The commit's log is then byte-identical to
       today's, so existing direct `commit()` callers are unaffected.
  - **The report is built at commit, from the registry being committed.** Any change
    `repair_escapes` makes to the registry (it extends the registry and saves it) is therefore
    included, with no separate binding step.
  - **`run_dir/alias_index.json`.** The report Part B acted on is written here, carrying
    `registry_sha256` (of the canonical registry JSON as seeded) and `segments_sha256`. A rerun
    can be checked against it.
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
  - **So the pass writes `distinct_from` only when neither id is a person.** *(r3)* A person is:
    - an id whose normalized form (`_norm_id`) is in the `person:` namespace; or
    - an id whose seeded **card** `kind` is `person`; or
    - an id whose canon `kind`, folded in the world after seeding, is `person`.

    The pass checks all three, and any one makes the pair report-only.
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

### Pass mark (fixed before the build; restated in r4)

On the five stored registries (R23 run1 and run2; R26 seq, par1b and par2b), each run through the
**shared** path above, which is exactly what `Pipeline.commit` runs minus the pass-1 replay. It is
compared with the same path with `alias_distinct=False` (reconcile on), and with **today's commit**
(both off). The engine is main's:

1. **Fused ids: 0** in all five. The vault fusion is gone wherever it occurred (four registries).
2. **The Ilsa pair is merged** in every registry where main merges it (run1, run2).
3. **No new fusion and no new fragmentation** in any registry: the fused-id and fragmented-entity
   sets are subsets of main's.
4. **F1 is not lower than today's commit** in any registry *(r4)*. It is measured equal.
4a. *(r4)* **Fragmentation is not higher than today's commit** in any registry, and is lower where
    `reconcile` merges (R23: 1 → 0; par1b: 13 → 4; par2b: 13 → 7).
4b. *(r4)* **A real commit is tested.** A fixture `run_dir` with staged chunks is committed through
    `Pipeline.commit` with both flags on, with Part B off, and with both off. The world logs show:
    - the vault-style fusion only with Part B off and reconcile on;
    - no fusion with both on;
    - today's log byte-for-byte with both off.
5. **No person pair gets a `distinct_from`.** A fixture with two person cards that have different
   proper names and share an alias gets no row, and a later `correlate` between them still
   succeeds.
6. The chapter test and the full suite are green with the flag on. With it off, a commit's log is
   byte-identical to today's.
7. *(r3)* **Determinism and compatibility.**
   - The same staged `run_dir` committed twice, once by the `Pipeline` that ran pass-0 and once by
     a fresh `Pipeline` constructed on that `run_dir`, produces byte-identical world logs and
     identical `alias_index.json` files.
   - A `run_dir` with no `source_segments.json`, and no `segments` argument, commits exactly as
     today, and its report says `skipped: no_source`.
   - A tampered `source_segments.json` raises before anything is written.
   - *(r4)* An **empty** segment list is not a source. A file holding `[]`, even with a matching
     digest, raises before any write, and so does an explicit `segments=[]`.
   - A registry changed by `repair_escapes` is the registry the report reads: its
     `registry_sha256` matches the saved `registry.json`.

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
