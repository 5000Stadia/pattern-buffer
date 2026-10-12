# R24 Part B: distinct_from for strong non-person pairs at commit (2026-10-12, r4.2)

Spec: `specs/ALIAS-INDEX-V1.md` (Part B, r4.2, pbr GREEN).
Method: the five stored registries, each run through the shared commit path
(`grade_registry.seeded_registry`: `seed_world`, then `alias_distinct_pass` when on, then
`finalize_identity`), graded with `grade_registry.grade`.
- No model calls and no new builds.
- Per-registry JSON (all three columns, what Part B wrote and kept report-only) is beside this file.
- `tests/test_alias_index_part_b.py` asserts the same numbers.

## The three columns (B3 F1 / fused ids / fragmented gold entities)

- **today:** `alias_distinct=False, reconcile=False`. What `Pipeline.commit` did before this item.
- **reconcile:** `alias_distinct=False, reconcile=True`. The measurement mode R23's "seeded" grade
  ran. It fuses the vaults.
- **default:** `Pipeline(reconcile="auto", alias_distinct=True)` with a source. Part B, then
  `reconcile`.

| Registry | today | reconcile (no Part B) | default |
|---|---|---|---|
| R23 run1 | 0.7517 / 0 / 1 | 0.7471 / 1 / 0 | **0.7517 / 0 / 0** |
| R23 run2 | 0.7347 / 0 / 1 | 0.7303 / 1 / 0 | **0.7347 / 0 / 0** |
| R26 seq | 0.7517 / 0 / 0 | 0.7517 / 0 / 0 | **0.7517 / 0 / 0** |
| R26 par1b | 0.8320 / 0 / 13 | 0.8264 / 1 / 4 | **0.8320 / 0 / 4** |
| R26 par2b | 0.7961 / 0 / 13 | 0.7910 / 1 / 7 | **0.7961 / 0 / 7** |

Part B wrote `place:records_vault` / `place:seed_vault` (`rejected`) in run1, run2, par1b and par2b,
and nothing in seq. In par1b it kept Cray/Marn and Sela Voss/Tovan Voss report-only (persons).

## Pass mark

1. **Fused ids are 0 on the default path in all five:** PASS. `reconcile` alone fuses the vaults
   in four of them.
2. **The Ilsa pair is merged** (run1, run2): PASS. Today's commit never merges it; `reconcile`
   and the default do.
3. **No new fusion, no new fragmentation:** PASS. The default's fused and fragmented sets are
   subsets of the `reconcile` column's, and the fragmented set is a subset of today's.
4. **F1 not lower than today's commit:** PASS, equal in all five. The gain is structural, not F1.
4a. **Fragmentation not higher than today's, lower where `reconcile` merges:** PASS. R23: 1 to 0;
   par1b: 13 to 4; par2b: 13 to 7; seq 0 to 0.
4b. **A real commit through `Pipeline.commit`:** PASS (see the modes below).
5. **No person pair gets a `distinct_from`:** PASS. The pseudonym fixture's later `correlate`
   succeeds. Card kind and folded kind are each tested, and par1b's two person pairs stay
   report-only.
6. **The modes:** PASS, asserted on a fixture `run_dir` with a staged chunk, committed through the
   real `Pipeline.commit`:

   | `(reconcile, alias_distinct)`, source | Vaults one id | Log |
   |---|---|---|
   | `("auto", True)`, with source (default) | no | reconciles, writes the `distinct_from`, Ilsa merged |
   | `("auto", True)`, no source | no | byte-identical to today, report `skipped: no_source` |
   | `("auto", False)` | no | byte-identical to today |
   | `(True, False)` | **yes** | reconciles without Part B |
   | `(False, False)` | no | byte-identical to today |

   "Today" in the test is a commit spelled out from engine calls (seed, replay, classify,
   promote, confirm owners, scan). The two scripted commits hashed before this item
   (`5e2f3d66e4019a44`, `7ff9f517a1a0d563`) still hash the same in the legacy modes.
   The chapter test with the default flags is a metered model run and is **not run**. It needs no
   harness change, since `pass0` writes `source_segments.json`, so it comes with R27, which goes
   back to Kabe first.
7. **Determinism and compatibility:** PASS.
   - A fresh `Pipeline` on the same `run_dir` gives a byte-identical log and report.
   - No source under the default flags gives today's log, with `part_b: skipped / no_source`.
   - A tampered or malformed source raises before any write.
   - An empty source raises before any write: a file holding `[]` with a matching digest, and an
     explicit `segments=[]`.
   - `registry_sha256` matches the post-repair `registry.json`.

On par1b, `place:vault` ("the vault") and `place:records_vault` stay merged in every column that
reconciles. The fusion goes to 0 because the Seed Vault no longer joins them.
