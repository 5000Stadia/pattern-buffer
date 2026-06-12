# Chapter-test scorecard — The Last Honest Meter

- **Seed version:** v1-final (results are never compared across seed versions)
- **Date:** 2026-06-12
- **Extractor model:** codex:gpt-5.5
- **Log size:** 202 assertions, ? entities, ? frames
- **Score: 10/10 PASS** — 0 extraction-class failures (fixable), 0 shape-class failures (whitepaper conversation)

| Q | Battery item | Verdict | Class | Detail |
|---|---|---|---|---|
| 1 | irrealis filtering | PASS |  | stated/observed irrealis fact rows: multimeter=0 conditional=0 |
| 2 | intention is not fact | PASS |  | drill->van rows=0; drill@day1=obj:steel_shelf |
| 3 | self-correction grace (outcome: folds corrected, no flag) | PASS |  | entity=place:rental fold=4 conflicted=False stale-3-alive=False |
| 4 | genuine contradiction flags (cross-speaker) | PASS |  | conflicted=True parties=2 |
| 5 | cursor humility | PASS |  | chain=['place:van', 'place:van'] |
| 6 | fuzzy time as honest interval | PASS |  | pre-week rows=1 inside@-5.5=True outside@-8=False |
| 7 | vocabulary drift learns (018) | PASS |  | accrued=True receipted=True second_use=resolved |
| 8 | negation confirms the old state | PASS |  | day4 confirm rows=1 fold=obj:steel_shelf |
| 9 | unknown stays unknown | PASS |  | resolve=UNKNOWN generated_rows=0 |
| 10 | wall-clock rider (A1) | PASS |  | missing on 0 rows |

## Coverage honesty (letters 004/006, bible A5)

- Q2: lateral graph: planted non-connection landed in v1 (feature 9) — graded
- Q6: accrual-promotion candidate planted in v1 (feature 10, 3x utterance) — graded leniently
- Q21: never-opened containers: N=2 in v1 (footlocker + PERSONAL case)

## Reading the classes

- **extraction** — the engine's invariants held; the model-side extraction missed or mangled content. Fix the extractor contract and re-run.
- **shape** — the substrate itself misbehaved (silent merge, phantom contents, frame leak, canon mutation). Stop: whitepaper conversation.
