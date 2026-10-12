# R27 and "M3 done": the case, for Kabe's conversation (2026-10-12)

## What R27 is meant to prove

The vision's first "finished" line: *hand it a book and walk in.* A whole novel becomes a
faithful world, in reasonable time and cost, and the result is measured, not claimed.
*Alice* is the standing example.

So R27 should answer three things:
1. **Time and cost.** What a whole book takes.
2. **Fidelity.** How right the world is.
3. **Reading, not remembering.** Whether the extractor read the text or recalled what it knows
   about *Alice*.

## Why the counterfeit edition, and why twice

- **The model has almost certainly memorized *Alice*.** Without a control, a good score could
  mean it remembered the book. Remembered facts would then enter canon with textual provenance,
  which is the lie the vision forbids.
- **The counterfeit edition is the control.** It is *Alice* with characters renamed and a set of
  scripted state changes (the key ends up somewhere else), each with its expected world change
  written down first. That gives exact gold by construction. A late edit that turns up early in
  the world shows knowledge leaking backwards.
- **Running each edition twice gives a noise floor.** A change smaller than the run-to-run
  wobble is not a result. Today's floor, from the chapter test, is about 0.02 F1 (R23's two
  runs).

## What it costs (estimated; nothing has run)

- **One build of the chapter-test story** (about 4,700 words) takes **32 minutes**, almost all
  of it serial model calls (R26).
- ***Alice* is about 26,000 words, roughly 5.5 times longer.** Scaling linearly, one build is
  **about 2.5–3 hours**.
- **The plan as decided (two editions, two runs each, four builds):** about **10–12 hours of
  model time**, plus the work of preparing the counterfeit edition and its expected changes.
- **Tokens and money: not known.** R26 did not log tokens. I would add token logging before any
  of these runs, so the first one produces a real cost receipt.
- **Original *Alice* has no gold roster.** Its fidelity can only be judged by spot checks, or
  through the counterfeit's scripted edits. The counterfeit is where the exact numbers come
  from.

## Cheaper or simpler options

| Option | What it proves | Cost |
|---|---|---|
| **A. A three-chapter rung first** *(my recommendation)*: chapters 1–3 of *Alice* (about 7,000 words), original and counterfeit, twice each | The counterfeit method works; how big the memorization effect is; edit recall and leaks; the noise floor at that size | 4 builds of about 45 minutes, **about 3 hours** |
| **B. The counterfeit only**, whole book, twice | Fidelity against exact gold, and the noise floor; no memorization gap number | 2 builds, **about 5–6 hours** |
| **C. *Alice* once, for time and cost only**; fidelity stays on the unmemorized chapter test (which already has gold) | Whole-book time and cost receipts; no fidelity claim at book scale | 1 build, **about 2.5–3 hours** |
| **D. As decided**: whole book, both editions, twice each | Everything | 4 builds, **about 10–12 hours** |

**Why A first.** It tests the expensive idea, the counterfeit and its edit checks, at a quarter of
the cost. If the memorization gap turns out small, B or C may be enough at whole-book scale. If
it turns out large, D is justified, and we will know what to look for.

The other parts of M3 (R24 Part B, merged; R25's merge gate, in build) make each build better and
are measured for free on stored registries first. Only R25's real-model check (about 72 small
calls, about 0.4 M tokens) and R27 itself are metered.

## What "M3 done" would then mean

- **As proposed earlier:** *the Alice receipts exist*: time, cost and fidelity for each run, a
  noise floor, and identity measures at or inside the chapter test's floor.
- **With option A first:** the same line, but reached in two steps. The rung decides whether the
  whole-book runs are D, or B or C.
- **A lighter "done", if you prefer:**

  > *A whole novel builds end to end with a time and cost receipt, and its fidelity, measured
  > on an edition the model cannot have memorized, is within the noise floor of the chapter
  > test.*

  That is option B or C plus the rung.

## The decision that is yours

Which option (A–D), and which "M3 done" line. Nothing metered runs until you choose.
