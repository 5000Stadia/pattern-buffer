# R24 Part B: distinct_from for strong non-person pairs at commit (2026-10-12)

Spec: `specs/ALIAS-INDEX-V1.md` (Part B, r3, pbr GREEN).
Method: the five stored registries, each seeded as `Pipeline.commit` seeds them (`pipeline.seed_world`),
with and without Part B, then graded with `grade_registry.grade`.
- No model calls and no new builds.
- Per-registry JSON is beside this file.
- `tests/test_alias_index_part_b.py` asserts the same numbers.

| Registry | B3 F1, main → Part B | Fused ids | Fragmented entities | Part B wrote |
|---|---|---|---|---|
| R23 run1 | 0.7471 → 0.7517 | 1 → 0 | 0 → 0 | `place:records_vault` / `place:seed_vault` |
| R23 run2 | 0.7303 → 0.7347 | 1 → 0 | 0 → 0 | `place:records_vault` / `place:seed_vault` |
| R26 seq | 0.7517 → 0.7517 | 0 → 0 | 0 → 0 | nothing |
| R26 par1b | 0.8264 → 0.8320 | 1 → 0 | 4 → 4 (the same four) | the vault pair (two person pairs report-only) |
| R26 par2b | 0.7910 → 0.7961 | 1 → 0 | 7 → 7 (the same seven) | the vault pair |

## Pass mark

1. **Fused ids are 0 in all five registries:** PASS.
2. **The Ilsa pair is merged wherever main merges it** (run1 and run2): PASS.
3. **No new fusion, and fragmentation is the same set as main's:** PASS.
4. **F1 never falls:** PASS. It rises by 0.0046, 0.0044, 0, 0.0056 and 0.0051, all under the ~0.02
   noise floor. No F1 gain is claimed.
5. **No person pair gets a `distinct_from`:** PASS. The pseudonym fixture's later `correlate`
   succeeds. Card kind and folded kind are each tested, and par1b's Cray/Marn and Sela/Tovan Voss
   stay report-only.
6. **Flag off is byte-identical to today, and the suite is green:** PASS. Checked by hashing two
   scripted commits before and after the change. The **chapter test with the flag on is not run**:
   it is a metered model run. It needs no harness change, since `pass0` now writes
   `source_segments.json`, so it comes with the next metered build (R27), which goes back to Kabe
   first.
7. **Determinism and compatibility:** PASS.
   - A fresh `Pipeline` on the same `run_dir` gives a byte-identical log and report.
   - No source gives today's log, with `part_b: skipped / no_source`.
   - A tampered, malformed or empty source raises before any write.
   - `registry_sha256` matches the post-repair `registry.json`.

On par1b, `place:vault` ("the vault") and `place:records_vault` stay merged in main and in Part B
alike. The fusion goes to 0 because the Seed Vault no longer joins them.
