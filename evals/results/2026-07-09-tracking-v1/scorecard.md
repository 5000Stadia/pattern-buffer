# Tracking-mode scorecard — the_grey_house (TRACKING-MODE-V1)

- **Date:** 2026-07-09 · **Spec:** TRACKING-MODE-V1 r3 (Cx GREEN-to-build, 568/569)
- **Score: 14/14 PASS** (18 tests; deterministic, injected fake wall clock)
- **Classes:** 0 shape-class failures. The three pre-audit gaps were confirmed
  and FIXED as Part-B engine work before grading (below) — they were the
  build's purpose, not graded failures.

| # | Battery item | Verdict | Note |
|---|---|---|---|
| 1 | as-of reconstruction (both modes) | PASS | identical answers, tracking & fiction |
| 2 | time-advance changes nothing (both modes) | PASS | cursor + wall advance; snapshot byte-equal |
| 3 | future events filtered by `events(until=)` | PASS | narrowed claim (no evaluator overclaim) |
| 4 | three axes, one fact | PASS | absent@earlier-seq; Thursday@valid; ages-from-Monday@wall |
| 5 | decay honesty (component level) | PASS | 2d key = 0.5 at one half-life; 60d key > 0.97; clamp holds (`now<stamp` → 1.0) |
| 5b | fail-closed null branches | PASS | unconfigured + unconfirmed → recency null, renormalized score |
| 6 | staleness answer shape | PASS | `last_confirmed_at_wallclock` = the "June 19, three weeks unconfirmed" join |
| 7 | re-confirmation | PASS | stamp refreshes; valid-time history intact |
| 8 | quarantine never hardens | PASS | assumed row survives as-is; zero promotions; zero retractions |
| 9 | stated absence ≠ unknown | PASS | observed `has_fittings=false` vs honest UNKNOWN |
| 10 | never-invent under pressure | PASS | resolve→UNKNOWN; scripted ask; zero `generated` rows |
| 11 | fiction control (anti-decay) | PASS | recency permanent; wallclock field null; as-of identical |
| 12 | the aliens test (no-bias) | PASS | stance varied alone: byte-identical treatment; unexpected == mundane |
| 13 | restart reproducibility | PASS | policy rebuilt from log; same `now` → identical payload |
| 14 | read purity | PASS | head/dump/`total_changes` unchanged across reads |

## The three pre-audit gaps — confirmed, then fixed (Part B)
1. **No decay machinery existed** (World's "decay physics" was a docstring) →
   `DecayPolicy`: declared `decay_halflife_seconds` rows, exact-key > family
   (`attr:in`) > `attr:__world__`, read fresh each read, gate-validated.
2. **The A1 wall stamp was written but never consumed** (confidence recency read
   story time) → `confidence(now=)` + `last_confirmed_at_wallclock` +
   the frozen `recency`/`recency_status` branches.
3. **Fiction confidence decayed with story time** → the founder's anti-decay
   amendment: `recency_status="permanent"` in non-tracking worlds
   (`invent_under_canon` and `deny`); one prior test inverted, documented.

## Claim boundary (per Cx 559)
This validates **tracking substrate/time-confidence behavior**. Combined with
MICRO-EVAL-V1 (10/10, messy-dialogue ingestion) it supports the broader
tracking story; it does not claim conversational-ingestion validation.
