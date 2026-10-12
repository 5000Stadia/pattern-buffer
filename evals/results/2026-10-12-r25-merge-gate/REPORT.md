# R25 part A: the verified merge gate, free measurements (2026-10-12)

Spec: `specs/MERGE-GATE-V1.md` (r2.1, pbr GREEN). No model was called. The five stored registries go
through R24's default commit path, with the gate step added. Per-registry JSON is beside this file.
`tests/test_merge_gate.py` asserts every number below.

## Free pass mark

| Item | Result |
|---|---|
| 1. Candidate recall | **11 of 11** split gold pairs are candidates (par1b 4, par2b 7). Candidate counts: 83, 97, 92, 286, 284, in 4, 4, 4, 12, 12 batches of 25 |
| 2. Oracle ceiling | split 0 and fused 0 everywhere. F1: run1 0.7517, run2 0.7347, seq 0.7517 (unchanged); **par1b 0.8320 → 0.8483**; **par2b 0.7961 → 0.8339** |
| 3. Gate off, or all-`unsure` | log sha256 identical to R24's default on all five, and through a real `Pipeline.commit` |
| 4. Malformed answers | one test per status (`batch_unparseable`, `stray`, `duplicate`, `missing`, `bad_verdict`, `bad_keep`); each pair ends `unsure`, with nothing merged |
| 4a. Overlap | one representative and no re-point; judging order does not change the log; a tie elects a third member by longest name; the vault-chain shape writes nothing (`conflicting_component`) |
| 5. Determinism | byte-identical log and `merge_gate.json` from the original and a fresh `Pipeline` |
| 6. Persons and vetoes | no person×non-person candidate; the vault pair (held apart by R24) is never a candidate; a vetoed `same` writes nothing and reports why |
| 7. `keep` is a vote | votes beat name length; a single-pair component honours its `keep` |

## Against the prototype

The candidate counts are one lower than the scratch prototype's (84, 98, 92, 287, 285) in four
registries. The cause is the spec's "not already held apart" filter, which drops the Records Vault /
Seed Vault pair. That pair is gold-different, so the gold-different total is **39**, not 43
(4, 8, 4, 15, 8). Recall and the oracle numbers are unchanged.

## The metered measurement (not run; for Kabe's yes)

The dry run counts the calls without calling any model (`dry_run.txt`):

| | Candidates | Calls | Est. tokens in | Est. tokens out |
|---|---|---|---|---|
| One repetition (five registries) | 842 | 36 | ~194 k | ~39 k |
| **Two repetitions** | | **72** | **~388 k** | **~78 k** |

So about **0.47 M tokens** in all, no rebuilds. Judged against: 0 `same` among the 39
gold-different pairs in either repetition; at least 8 of the 11 gold-same merged in each; F1 not
below R24's default anywhere. Unlabelled `same` verdicts are counted, with 20 sampled for Kabe, and
run-to-run disagreements are listed.

To run it, after Kabe's yes:
`PYTHONPATH=src python evals/harness/run_merge_gate_metered.py OUT_DIR --reps 2`

It writes per-repetition JSON, `meta.json`, `scoring.json` and `SCORING.md`, and exits 1 if the
pass mark is missed.
