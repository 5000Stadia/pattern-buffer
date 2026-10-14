# Library-pipeline comparison: practice book, chapters 1–2 (2026-10-14)

Approved by Kabe (monitor note n97dfba): "Approved for it to run with detailed benchmark and time
logging to identify most efficient run speed and how to improve it's effective build time."
- **Pipeline:** BUILD-LIBRARY-V1 (`run_book --pipeline library`): category passes for the
  registry, chunk extraction, then commit (which classifies).
- **Code:** a worktree pinned at 42d0c23 (`run_all.sh` is the runner as it ran).
- **Book:** *The Address That Hummed*, chapters 1–2.
- **Gold:** `../2026-10-13-stage-compare/graded_ch2.json` (`--through-chapter 2`).
- **Settings:** each one uses a single model and effort for every stage
  (`evals/stage-maps/map_a_low.json`, `map_b_medium.json`, `map_d_haiku_low.json`).
- **Runs:** two per setting, run in sequence.
- **Cost:** costs are the CLI's reported figures, on Kabe's Claude plan.

## Results

| setting | run | outcome | wall | registry (4 parallel calls) | extract (4 parallel chunk calls) | commit | output tokens | hidden share | reported cost |
|---|---|---|---|---|---|---|---|---|---|
| (a) Sonnet 4.6, low | 1 | **refused**: chunk 2 "declared but not used: new:0" | 120 s | 5–15 s | 57–105 s | n/a | 28.7k | 13% / 78% | $0.68 |
| (a) Sonnet 4.6, low | 2 | **complete** | **246 s** | 4–18 s | 30–170 s | 58 s (7 serial calls, ~8 s each) | 36.0k | 13% / 79% / 22% | $0.86 |
| (b) Sonnet 4.6, medium | 1 | **timed out**: chunk 0 failed 3 attempts at the 300 s call limit | 18 min | 18–142 s | 140 s – 300 s (limit) | n/a | 58.6k | 88% / 89% | $1.11 |
| (b) Sonnet 4.6, medium | 2 | **timed out**: chunks 0 and 2, same | 17 min | 17–62 s | 128 s – 300 s (limit) | n/a | 35.7k | 84% / 90% | $0.73 |
| (d) Haiku 4.5, "low" | 1 | **refused**: chunk 2 "declared but not used: new:3" | 359 s | 67–126 s | 181–234 s | n/a | 150.6k | 94% / 96% | $0.83 |
| (d) Haiku 4.5, "low" | 2 | **refused**: chunk 3 "declared but not used: new:4, new:5" | 383 s | 57–159 s | 154–223 s | n/a | 139.0k | 96% / 95% | $0.77 |

- **Hidden share** is per stage (registry / extract / commit). It is the share of output tokens
  not in the visible answer, estimated at 4 characters per token.
- **Complete runs:** 1 of 6. Every time figure below is a single observation, and tails are
  unmeasured.

## Quality of the one complete build (a, run 2), against INGEST-V2 at the same setting

| measure | library (this run) | INGEST-V2 (stage-compare, a) |
|---|---|---|
| wrong merges across look-alikes | **0** (6 of 6 kept apart) | 0 |
| leaks | **0** | 1 (registry leak: Pell joined to Eren Vell before the reveal) |
| false beliefs in canon | 0 | 0 |
| identity B³ precision / recall / F1 | 0.983 / **0.652** / **0.784** | 1.000 / 0.625 / 0.769 |
| reveal joined | 1 of 1 | 1 of 1 |
| order (mean LCS) | **0.411** | 0.23 |
| final container | **0.273** | 0.18 |
| wall | 246 s | **103 s** |

- **What improved.** The library has no leaks, by construction: a persona joins its entry only
  at the reveal. Movement is better (order 0.41 vs 0.23, final container 0.27 vs 0.18), and
  recall is slightly higher.
- **One fused closure:** `mouth_room` with `tin_orchard`. The book itself wavers on whether its
  rooms are one room (see the book's README), so this may be the text, not the build.
- **Recall gaps are mostly small objects never registered:** a petition, a ledger, a hall map,
  the seventh tooth, and others.

## Findings

1. **The build's main problem now is robustness, not speed.** 3 of 6 runs, at both models, were
   refused for the same reason. A model declared a new-entity handle (`new:k`) that no accepted
   line used, and extract refuses the whole chunk on any handle imbalance (r1.7). One chunk
   refusal then aborts the run, with nothing committed.
   - `used` is counted only over lines that passed the grammar. So a declared entity whose only
     line was refused, for example as malformed, turns a one-line refusal into a whole-chunk
     refusal.
   - The raw model output of a refused chunk isn't kept. So these runs can't tell that cascade
     apart from a model that declared an entity and wrote nothing about it. That's a logging gap.
2. **Medium effort can't reliably extract a chunk within the 300 s call limit.** Of its 16 extract
   calls, retries included, 11 hit the limit, and the rest took 128–209 s. Medium is not a usable
   setting for chunk extraction at this chunk size.
3. **Haiku 4.5 at "low" is slower than Sonnet at low.**
   - Its registry calls took 57–159 s against Sonnet's 4–18 s, and its extract calls 154–234 s
     against 30–170 s.
   - 94–96% of its output is hidden thinking, the same as Haiku at default effort in the
     stage-compare.
   - So the effort setting shows no measurable effect on Haiku 4.5 here. On this harness,
     "fast tier" means Sonnet at low effort, not a smaller model.
4. **At Sonnet low, the extract stage is the wall** (170 of 246 s): four chunk calls run in
   parallel, and the wall is the slowest one.
   - Its output is still 79% hidden thinking, against 13% for the short-list registry calls.
   - The commit's classification is 58 s of serial calls, about 8 s each.
5. **The library is slower than INGEST-V2 at the same setting** (246 s vs 103 s) and better on
   every judging measure. The time is in extraction's per-chunk calls, which are long and
   reasoned. INGEST-V2's pass-1 calls were short (18 s in all).

## What would make it faster and finish (proposed, each through spec and pbr)

1. **Finish every run** (BUILD-LIBRARY-V1 r1.9):
   - an unused declared handle is dropped with a typed receipt instead of refusing the chunk. It
     mints nothing, so nothing is lost;
   - a refused chunk gets one corrective retry with its refusal reasons, the BARE-CALL-V1 pattern;
   - the raw output of every refused chunk is kept in the run.
2. **Smaller chunks, more parallel calls.** The wall is the slowest chunk's call, so more and
   shorter chunks lower it, at the cost of more calls. To measure.
3. **Classification in parallel, or by rules where the guardrails already decide.** The commit's
   58 s is serial.
4. **Effort per stage:** low for the registry and extraction (Sonnet). Medium only for a later
   interpretation pass (motive, dynamics, reveals), where its time is spent on judgment.
5. Then rerun (a) twice, and a 6-chapter build, for a real range. That is a paid run, so it
   waits for Kabe's yes.
