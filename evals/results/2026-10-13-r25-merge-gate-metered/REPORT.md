# R25 part A: the merge gate with the real model (2026-10-13)

Kabe's yes on gate gf981cd: "1 seems important so yeah. why woldnt we?"

Run: `PYTHONPATH=src python evals/harness/run_merge_gate_metered.py <this dir> --reps 2`, on the
five stored registries as R24's commit leaves them. Model: claude-sonnet-4-6 (the build's model).
No pass-0 or pass-1 was re-run.

## Result: the pass mark is met in both repetitions

| | rep 1 | rep 2 |
|---|---|---|
| `same` on a pair gold says is different | **0** | **0** |
| gold-same pairs joined (pass ≥ 8 of 11) | **9** | **8** |
| F1 below R24's default in any registry | no | no |
| verdicts (different / same / unsure) | 780 / 31 / 31 | 766 / 30 / 46 |
| batch errors | 0 (842 answered) | 0 |

### What it does to the registries (F1, split entities, fused entities)

| Registry | R24 default | rep 1 | rep 2 |
|---|---|---|---|
| r23-run1 | 0.7517 / 0 / 0 | unchanged | unchanged |
| r23-run2 | 0.7347 / 0 / 0 | unchanged | unchanged |
| r26-seq | 0.7517 / 0 / 0 | unchanged | unchanged |
| r26-par1b (parallel pass-0) | 0.8320 / 4 / 0 | **0.8429 / 1 / 0** | **0.8429 / 1 / 0** |
| r26-par2b (parallel pass-0) | 0.7961 / 7 / 0 | **0.8339 / 1 / 0** | **0.8190 / 2 / 0** |

The gate removes most of what parallel pass-0 split (4 → 1 and 7 → 1–2 entities), with no fusion.
The oracle ceiling from the free run was 0.8483 / 0.8339, so the real model reaches or nearly
reaches it. This is the blocker R26 named for parallel pass-0: "it fragments the registry, so it
stays off until R24 Part B and R25." With the gate on, parallel pass-0's registries end up better
than sequential pass-0's on F1.

## What to watch

- **Run to run:** 29 pairs differ between the repetitions. Almost all are `different` ↔
  `unsure`, which changes nothing. Five involve a `same`.
- **Unlabelled merges (no gold either way):** 31 and 30 `same` verdicts, 22 per repetition on
  pairs gold doesn't cover. Most are right on reading: org/place splits of one office, and doc/obj
  splits of one ledger or letter. Two are wrong or doubtful, each in one repetition only:
  - `event:memory_core_theft` = `obj:master_meter_memory_core` (rep 2): an event merged into an
    object. This is a real fusion that gold does not see.
  - `obj:gallery_display` = `place:gallery` (rep 2): doubtful.
- **Proposed follow-up (small, deterministic):** bar event × non-event pairs from candidacy, as
  person × non-person already is. That removes the clear error class at no cost.
- **Time:** 47 minutes wall (72 serial calls, about 38 s each), not the 10–20 minutes estimated.
  Inside a build the gate adds this per book unless the batches run in parallel.
- **Size:** 1.54 M characters in and 0.29 M out, about 0.38 M and 0.07 M tokens (chars / 4). This
  run predates the token receipts (merged the same morning), so there is no exact count or price.

## Files

- `rep1/`, `rep2/`: per-registry effect plus the gate's full report.
- `scoring.json`, `SCORING.md`: the pass-mark scoring, differing pairs and sampled merges.
- `meta.json`: model, calls, wall time, characters.
