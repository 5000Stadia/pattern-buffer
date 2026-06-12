# Chapter-test scorecard — The Last Honest Meter

- **Seed version:** v1-final (results are never compared across seed versions)
- **Date:** 2026-06-11
- **Extractor model:** claude-sonnet-4-6
- **Log size:** 618 assertions, 82 entities, 6 frames
- **Score: 17/33 PASS** — 14 extraction-class failures (fixable), 2 shape-class failures (whitepaper conversation)

| Q | Battery item | Verdict | Class | Detail |
|---|---|---|---|---|
| 1 | containment tree >=4 deep | FAIL | extraction | max depth 3 |
| 2 | lateral graph: long way, no direct edge (feature 9) | FAIL | extraction | path=None |
| 3 | fixture vs movable containment | PASS |  | fixture_ok=False movable_ok=True |
| 4 | object moving through relation types (maps chain) | PASS |  | distinct holders over time: ['person:tovan_voss', 'person:sela_voss', 'event:survey_departure'] |
| 5 | deliberate constitutive contradiction flagged (feature 8) | FAIL | shape | both rows present but NO flag fired (silent coexistence) |
| 6 | dispositional habits (+3x utterance, feature 10 lenient) | PASS |  | 29 dispositional rows |
| 7 | attribute superseded 3+ times (core custody) | FAIL | extraction | core had 3 distinct holders: ['obj:clerk_desk', 'place:vault', 'place:seed_vault'] |
| 8 | world_defining condition (water crisis/rationing) | PASS |  | 20 crisis-condition rows |
| 9 | transient mood -> STATE (asymmetric default) | PASS |  | 0 mood rows, 0 misclassified CONSTITUTIVE |
| 10 | narrative clock on the spine | FAIL | extraction | stamped=275 unstamped=36 distinct_times=13 |
| 11 | off-screen reveal: valid_time != asserted_at (e25) | FAIL | shape | core at day 4.5: chain=[] |
| 12 | future-scheduled/conditional event | PASS |  | 6 future/conditional rows |
| 13 | derive-don't-store over time (no stored derivable ages) | PASS |  | 2 age rows, 0 derivable (violations) |
| 14 | one object at three timestamps (core) | FAIL | extraction | during the Ch.1 assembly (e25): []; Days 1-3, in the false drawer (e16): []; after the tribunal (e41): ['place:vault'] |
| 15 | >=3 knowledge frames + canon-minus-everyone delta | PASS |  | populated frames: ['knows:narrator', 'knows:pell', 'knows:person:narrator', 'knows:person:sela_voss', 'knows:sela_voss'] |
| 16 | telling scene: frame transfer, canon unchanged (feature 5) | FAIL | extraction | no door-log row in Sela's frame |
| 17 | contested truth (official story vs canon) | PASS |  | 5 official-story rows |
| 18 | justified-but-wrong belief undermined | FAIL | extraction | 83 belief rows; retraction present: False |
| 19 | inference/assumption distinguishable from narration | PASS |  | statuses present: ['assumed', 'inferred', 'observed', 'stated'] |
| 20 | document trust chain: per-claim fates (A4) | FAIL | extraction | doc rows=21 quantity_converged=False false_claim_superseded=True |
| 21 | never-opened containers stay unresolved (N=2) | PASS |  | footlocker: PASS (no phantom contents); personal_case: PASS (no phantom contents) |
| 22 | walked-away branch stays frontier (aquifer outcome) | PASS |  | 0 premature aquifer-outcome rows |
| 23 | locked container changes hands unopened (feature 4/11) | FAIL | extraction | day7=['person:sela_voss', 'place:narrator_office', 'place:anchor'] day21=['place:sela_condensers', 'place:salt_flats'] sealed=True |
| 24 | late binding: clerk == Ilsa Renn (feature 1) | FAIL | extraction | named identity reaches clerk rows: True; entities carrying the name: ['obj:ilsa_desk', 'person:tin_ear_clerk'] |
| 25 | one person referred 3+ ways | FAIL | extraction | 2 referring expressions: ["ilsa's desk", "the clerk's desk"] |
| 26 | coarse container differentiated (vault split, feature 3) | FAIL | extraction | two vaults=False; refer('the vault')=resolved () |
| 27 | reference by constraint only (inversion) | PASS |  | resolved to place:vault via ['constraint_inversion:contains(obj:memory_core)'] |
| 28 | two same-kind objects in scope | FAIL | extraction | only 0 drawer(s) under the desk: [] |
| 29 | causal chain >=3 links | PASS |  | 20 caused_by edges |
| 30 | hidden truth, >=2 discovery paths converge (letter + core) | FAIL | extraction | corroborated key found: False |
| 31 | witness with breaking condition (Marn confronted) | PASS |  | 2 confession/confrontation rows |
| 32 | consequence-of-inaction (clock material) | PASS |  | 13 depletion/clock rows |
| 33 | sensory atmosphere did NOT become assertions | PASS |  | 0 texture rows (should be 0) |

## Coverage honesty (letters 004/006, bible A5)

- Q2: lateral graph: planted non-connection landed in v1 (feature 9) — graded
- Q6: accrual-promotion candidate planted in v1 (feature 10, 3x utterance) — graded leniently
- Q21: never-opened containers: N=2 in v1 (footlocker + PERSONAL case)

## Reading the classes

- **extraction** — the engine's invariants held; the model-side extraction missed or mangled content. Fix the extractor contract and re-run.
- **shape** — the substrate itself misbehaved (silent merge, phantom contents, frame leak, canon mutation). Stop: whitepaper conversation.
