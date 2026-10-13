# Profiling build: 2 chapters of *The Last Honest Meter* (2026-10-13)

Kabe approved this run after gates g10c3af and g936be9. It ran on the bare harness (BARE-CALL-V1)
with BUILD-PROFILE-V1 instrumentation.
- **Model:** `claude-sonnet-4-6`, the CLI default effort.
- **Book:** chapters 1–2, 2,710 words, 2 pass-0 segments and 4 pass-1 chunks.

**Outcome: the run did not finish.** The one-hour outer cap stopped it (exit 124) during escape
repair, which kept timing out at the shim's 300 s limit. Every number below is from the calls that
were made. The full per-call data is in `usage.jsonl`, `objectives.jsonl` and `profile.md`.

## Findings

1. **Almost all output is hidden thinking.**
   - The 7 successful calls wrote **107,864 output tokens**.
   - Their answers came to **17,815 characters**, about **4,500 tokens**.
   - So about **96% of the output tokens were never part of an answer**.
   - Examples: a pass-0 call wrote 16,156 tokens for a 7,313-character answer; a pass-1 call wrote
     6,558 tokens for 647 characters.
2. **Latency is output-bound.**
   - Latency against output tokens: R² 0.968, 11.1 s per 1k tokens (n = 7).
   - Against input tokens: R² 0.033.
   - Output runs at about 68 tokens/s, so a call's time is roughly its thinking length.
3. **The harness is no longer a factor.**
   - API time is 99.2–99.4% of each call's latency.
   - Harness overhead is 1–5 s per call.
   - Every call took exactly 1 turn.
   - The smoke test before the run: a bare call took 1.1 s, the legacy one 2.5 s.
4. **Calls hit the 300 s timeout.**
   - pass-1 chunk 0 timed out twice before succeeding, at 292 s on its retry.
   - pass-0 segment 1 timed out once.
   - Escape repair timed out repeatedly until the cap.
   - Parallelism can't help a stage whose single slowest call is 4–5 minutes: pass-1's floor equals
     its measured wall.
5. **Turns to objectives:** 1 of 4 pass-1 chunks needed a retry, which cost 292 s.

## Reading

The 2.9-hour estimate for the novella is mostly the model thinking before each answer. Neither the
harness nor reading the input accounts for it. The `--effort` flag (low … max) controls this, and
the shim sets none.

The open question is what lower effort does to accuracy. That is measured on the practice set
against the graders, never assumed.

## Not measured here
- Classification, commit and audit: the run never reached them.
- Quality: nothing was graded.
- A full build's time: not measured, so no tail figures (one incomplete run).
