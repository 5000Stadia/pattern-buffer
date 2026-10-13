# Stage-model comparison: practice book, chapters 1–2 (2026-10-13)

Approved by Kabe after the profile ("Yes and further consider alternative models and speed").
- **Harness:** STAGE-MODELS-V1 maps (`evals/stage-maps/`), BARE-CALL-V1, BUILD-PROFILE-V1.
- **Book:** *The Address That Hummed*, chapters 1–2, 4,157 words.
- **Gold:** `graded_ch2.json` (`book_gold --through-chapter 2`).
- **Runs:** one per setting, run in sequence. With one run each, every time figure is a single
  observation, and tails are unmeasured.

## Results

| setting | outcome | wall | pass-0 | pass-1 | escape repair | commit | mean call latency | hidden-thinking share of output |
|---|---|---|---|---|---|---|---|---|
| (a) Sonnet, low effort | **complete** | **103 s** | 53 s | 18 s | 0 s | 29 s | 3–27 s by stage | 0.22–0.47 |
| (b) Sonnet, medium effort | **failed**: chunk 3 orphaned after escape repair | ~9 min before failing | 184 s | 200 s | 158 s | n/a | 79–135 s | 0.82–0.94 |
| (c) Haiku for pass-1 and commit (default effort), Sonnet medium for the rest | **failed**: chunk 2 orphaned after escape repair | ~20 min before failing | 358 s | 328 s | 493 s | n/a | Haiku 160 s; Sonnet 123–179 s | Haiku **0.97**; Sonnet 0.88–0.92 |

For reference, the earlier profile (Sonnet at the default effort, 2 chapters of *The Last Honest
Meter*) did not finish within an hour. About 96% of its output was hidden thinking.

## Findings

1. **Effort is the lever.** At low effort, hidden thinking fell from about 90% to 20–50% of output,
   calls ran 3–27 s instead of 80–180 s, and the whole build took 103 s.
2. **A smaller model is not faster by itself.** Haiku at its default effort thought even more (97%
   hidden) and averaged 160 s per call, with 99.5k output tokens across 5 calls. "Fast tier" has to
   mean low effort as well.
3. **Both failures are the pipeline, not the setting.** Medium and tiered failed the same way: an
   unresolved new entity (an orphan) survived escape repair, and the run refused to commit. That
   is the INGEST-V2 fragility that BUILD-LIBRARY-V1's handles, escapes and code allocation replace.
4. **Low-effort quality** (graded against chapters 1–2):
   - identity B³ precision 1.000, recall 0.625, F1 0.769;
   - no look-alike merged (6 of 6 kept apart), and the one reveal joined;
   - no false belief in canon;
   - **1 registry leak:** pass-0 joined Pell to "Eren Vell" before the reveal sentence. That is the
     failure the library's persona design prevents by construction;
   - **object movement is weak:** order 0.23, final container 0.18.

   Whether low effort causes the weak movement is **unmeasured**: no stronger setting completed on
   the same text.

## Next
- Build BUILD-LIBRARY-V1 (pbr GREEN r1.5).
- Re-run the comparison on the library pipeline: low against medium, and Haiku at low effort for the
  chore stages, graded, with two runs per setting for a range. A paid run, so it waits for Kabe's
  yes.
