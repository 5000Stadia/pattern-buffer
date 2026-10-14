# Speed comparison: a whole practice book in under four minutes (2026-10-14)

Approved by Kabe (gate g460a1c, "All ok seems reasonable go for it").
- **Pipeline:** the library pipeline (BUILD-LIBRARY-V1 r1.9.1, with retries), Sonnet 4.6 at low
  effort, on a worktree pinned at main `c4a8eba`.
- **Book:** *The Address That Hummed*, the practice book. Three settings were run twice each on
  chapters 1–2, graded against `graded_ch2.json`, then one full 6-chapter build at the fastest
  setting, graded against the full key. The runner is `run_all.sh`.
- **The settings** (BUILD-SPEED-V1):
  - (i) today's defaults;
  - (ii) `--classify-workers 4`;
  - (iii) `--max-words 750 --extract-workers 8 --classify-workers 4`.

## Results

| run | wall | registry | extract (calls) | commit (calls) | cost | wrong merges | leaks | B³ F1 | order | final |
|---|---|---|---|---|---|---|---|---|---|---|
| i run 1 | 357 s | 14 s | 284 s (5) | 59 s (7) | $1.02 | 0 | 0 | 0.784 | 0.307 | 0.364 |
| i run 2 | 224 s | 15 s | 151 s (5) | 58 s (7) | $0.93 | 0 | 0 | 0.780 | 0.343 | 0.273 |
| ii run 1 | 164 s | 13 s | 129 s (5) | 23 s (7) | $0.89 | 0 | 0 | 0.780 | 0.307 | 0.364 |
| ii run 2 | 180 s | 15 s | 146 s (4) | 19 s (7) | $0.89 | 0 | 0 | 0.775 | 0.436 | 0.273 |
| iii run 1 | **112 s** | 14 s | 79 s (6) | 19 s (8) | $0.90 | 0 | 0 | 0.784 | 0.393 | 0.364 |
| iii run 2 | **119 s** | 14 s | 85 s (6) | 19 s (8) | $0.98 | 0 | 0 | 0.780 | 0.332 | 0.182 |
| **full book, iii** | **225 s** | 18 s | 158 s (18) | 49 s (20) | **$2.58** | 0 | 0 | 0.757 | 0.198 | 0.231 |

- **6 of 6 short runs and the full build completed.** Last night it was 1 of 6.
- Two runs per setting give a range, not a tail. With one full-book run, its time is a single
  observation.
- Costs are the CLI's reported figures, on Kabe's plan. The whole comparison cost about $8.20.

## Findings

1. **A whole book now builds in under four minutes.** The 6-chapter practice book (about 11.5k
   words) took 225 s and $2.58, with zero wrong merges, zero leaks and zero false beliefs in
   canon.
   - For comparison: R26's build of *The Last Honest Meter* took 32 minutes on the old pipeline,
     and the default-effort profile of two chapters did not finish within an hour.
2. **Parallel classification removes most of the commit tail.** Commit fell from 58–59 s to
   19–23 s at the same quality (setting ii vs i).
3. **Smaller chunks with more workers cut extraction roughly in half.** Extraction fell from
   129–284 s to 79–85 s, giving 112–119 s for two chapters against 224–357 s on today's
   settings. The wall is still the slowest chunk's call, now shorter.
4. **Quality held across settings.** Every run had zero wrong merges, zero leaks and an identity
   F1 of 0.775–0.784, so smaller chunks didn't cost identity.
   - **Object movement is the weak area,** and it varies run to run: final container 0.18–0.36,
     order 0.31–0.44. The full book is lower still (0.23 / 0.20).
   - This is the same weakness the one-location probe found: moved things written in two places
     at once (`../2026-10-14-one-location/REPORT.md`).
5. **The retry earned its place.** In run ii 1, a chunk's first answer was refused ("declared
   twice: new:1"), and the corrective retry (BUILD-LIBRARY-V1 r1.9.1) passed. That build
   finished, where yesterday it would have aborted.
   - Separately, in two runs (i run 1, chunk 2; i run 2, chunk 0) one chunk was called twice
     with no library retry recorded. That came from the call layer below the library, and the
     logs don't say why. It's worth a look, since the extra call there cost 140 s of the wall.

## Recommendation

- **Make setting (iii) the library pipeline's default:** `max_words=750`, 8 extract workers and 4
  classify workers. That's a harness-default change, through a small spec and pbr.
- **Next quality work is movement,** not speed. Order and final-container scores are the low
  numbers, and the one-location probe shows why. See its report for the proposal: the model
  marks an old place as ended, and the engine stamps it.
