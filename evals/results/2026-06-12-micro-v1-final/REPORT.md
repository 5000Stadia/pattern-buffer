# Milestone report: the micro-eval (reality-divergence battery) — 10/10

**For:** the founder and Kernos CC. Seed v1-final; run of 2026-06-12;
pipeline INGEST-V2 conversational; provider codex shim (first full
pipeline exercise). Template: the adopted five-part shape.

## 1. The claim and the test

Whitepaper §19.1's scope honesty: the chapter test reads clean authored
prose; reality doesn't. The micro-eval planted one case per
fiction/reality divergence (letter 025's seven + 018's synonym + the
mode floor + the A1 rider) in a hand-authored household conversation and
graded tracking mode end to end — stance=reality, observe_or_unknown,
speaker-source classes, correction proposals, stance receipts.

## 2. The number and its anatomy

**10/10.** The cardinal-sin criteria all held: zero irrealis leaks into
stated/observed (the multimeter hypothetical landed as `assumed`, exactly
the allowed outcome, with its stance receipt reading `irrealis`); the
intention never teleported the drill; the unknown stayed UNKNOWN with
zero generated rows. Speakers disagreeing flagged-and-held (fuel:
diesel/gasoline, both alive); the same speaker superseded themselves
without noise; the rental key's cabinet→keyring journey folded cleanly;
"last Tuesday sometime" landed as an honest interval ([-6,-5)) that as-of
finds inside and misses outside; "the cupboard" resolved by tier-2 once,
accrued with its receipt, and resolved by tier-1a forever after; every
STATE row carries its wall-clock learned-at.

Three grader bugs and one acceptable-mechanism ruling were fixed between
first grade (6/10) and final (10/10) — all four re-adjudications verified
against the dump per the standing discipline: identity rows are not fact
claims (R1); the single-utterance correction collapse is a VALID
mechanism (the model never asserts the withdrawn value; the corr
proposal correctly stands down — R3 now grades the outcome, not the
mechanism); the interval lived on the box entity (R6); R7's first-use
call must be scope-bounded per 018's own guard.

## 3. Predicted vs actual (015 standing section)

| Prediction | Actual | Verdict |
|---|---|---|
| Wall clock < 15 min | **3.3 min** (pass0 84s, pass1 70s, commit 28s, audit 16s) | **HIT** — the codex shim's no-spawn parallel calls land near the original §E.2 dream number |
| Zero irrealis leaks | zero | **HIT** |
| One prompt-iteration allowance | two (brace-escape crash; gpt-5.5 id-fidelity hardening) | MISS/soft — both <5 min cycles; the second is a real portability lesson |

## 4. What the test caught

- **Model portability of the grammar contract:** gpt-5.5 invented
  slash-ids and a `conf=` flag where sonnet inferred the format — every
  malformed line was rejected at the gate, chunks failed, commit refused,
  zero garbage landed. Fix: worked examples + an exact flag list in the
  prompt. Playbook rule: **compact-grammar contracts need worked examples
  per model family; the gate's reject machinery is the safety net that
  makes cheap iteration possible.**
- **The corr machinery's first live run** behaved exactly per the 027
  riders — including correctly standing down when no eligible prior
  existed (the collapse case).
- **Incremental establish/extend** (the 014 interface) had its first live
  use: the registry grew Monday→Wednesday→Friday, 24→32→34 entities.
- A regrade-side lesson: policy is physics-as-config (whitepaper §16) —
  reopening a world for grading must restate it; the charter records
  stance, not policy, by design.

## 5. What's next

**The porcelain freeze is now unblocked** — extraction is stable across
both postures (authored prose 22/33 substrate-validated; conversational
reality 10/10). Freeze flag goes to K with this report; HD's build clock
starts on the freeze. Post-freeze roadmap stands (frame-diff read,
accrual promotion, inclusion edges).

**What changed in the canonical docs because of this milestone:**
MICRO-EVAL-V1 r3 executed as specced (027 rulings live); the
conversational contract + stance receipts are now reference
implementation in run_micro_eval.py; playbook gains the
worked-examples-per-model rule (riding the freeze commit).

*Raw run artifacts preserved in git history at the commit carrying this
report; tree prunes to report + scorecard per letter 017.*
