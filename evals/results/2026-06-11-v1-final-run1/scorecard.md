# Chapter-test scorecard — The Last Honest Meter

- **Seed version:** v1-final (results are never compared across seed versions)
- **Date:** 2026-06-11
- **Extractor model:** claude-sonnet-4-6
- **Log size:** 455 assertions, 58 entities, 7 frames
- **Score: 21/33 PASS** — 10 extraction-class failures (fixable), 2 shape-class failures (whitepaper conversation)

| Q | Battery item | Verdict | Class | Detail |
|---|---|---|---|---|
| 1 | containment tree >=4 deep | PASS |  | max depth 5 |
| 2 | lateral graph: long way, no direct edge (feature 9) | FAIL | extraction | path=None |
| 3 | fixture vs movable containment | PASS |  | fixture_ok=True movable_ok=True |
| 4 | object moving through relation types (maps chain) | PASS |  | distinct holders over time: ['person:tovan_voss', 'person:sela_voss', 'obj:waterproof_tube'] |
| 5 | deliberate constitutive contradiction flagged (feature 8) | PASS |  | flag fired; values [True, 2, 3] coexist |
| 6 | dispositional habits (+3x utterance, feature 10 lenient) | PASS |  | 25 dispositional rows |
| 7 | attribute superseded 3+ times (core custody) | PASS |  | core had 4 distinct holders: ['obj:false_drawer', 'place:seed_vault', 'place:allocation_vault', 'person:narrator'] |
| 8 | world_defining condition (water crisis/rationing) | PASS |  | 17 crisis-condition rows |
| 9 | transient mood -> STATE (asymmetric default) | PASS |  | 0 mood rows, 0 misclassified CONSTITUTIVE |
| 10 | narrative clock on the spine | FAIL | extraction | stamped=213 unstamped=9 distinct_times=12 |
| 11 | off-screen reveal: valid_time != asserted_at (e25) | FAIL | shape | core at day 4.5: chain=[] |
| 12 | future-scheduled/conditional event | PASS |  | 5 future/conditional rows |
| 13 | derive-don't-store over time (no stored derivable ages) | PASS |  | 1 age rows, 0 derivable (violations) |
| 14 | one object at three timestamps (core) | FAIL | extraction | during the Ch.1 assembly (e25): []; Days 1-3, in the false drawer (e16): []; after the tribunal (e41): ['place:allocation_vault', 'org:allocation_office', 'plac |
| 15 | >=3 knowledge frames + canon-minus-everyone delta | PASS |  | populated frames: ['knows:narrator', 'knows:person:marn', 'knows:person:narrator', 'knows:person:sela_voss', 'knows:person:tovan_voss', 'knows:sela_voss'] |
| 16 | telling scene: frame transfer, canon unchanged (feature 5) | FAIL | extraction | no door-log row in Sela's frame |
| 17 | contested truth (official story vs canon) | PASS |  | 1 official-story rows |
| 18 | justified-but-wrong belief undermined | FAIL | extraction | 50 belief rows; retraction present: False |
| 19 | inference/assumption distinguishable from narration | PASS |  | statuses present: ['assumed', 'inferred', 'observed', 'stated'] |
| 20 | document trust chain: per-claim fates (A4) | FAIL | extraction | doc rows=18 quantity_converged=False false_claim_superseded=None |
| 21 | never-opened containers stay unresolved (N=2) | PASS |  | footlocker: PASS (no phantom contents); personal_case: PASS (no phantom contents) |
| 22 | walked-away branch stays frontier (aquifer outcome) | PASS |  | 0 premature aquifer-outcome rows |
| 23 | locked container changes hands unopened (feature 4/11) | PASS |  | day7=['place:bazaar', 'place:anchor'] day21=['place:condenser_station'] sealed=True |
| 24 | late binding: clerk == Ilsa Renn (feature 1) | FAIL | extraction | named identity reaches clerk rows: False; entities carrying the name: ['person:ilsa_renn', 'person:unknown_badge_wearer'] |
| 25 | one person referred 3+ ways | FAIL | extraction | 1 referring expressions: ['ilsa renn'] |
| 26 | coarse container differentiated (vault split, feature 3) | FAIL | shape | two vaults=True; refer('the vault')=resolved () |
| 27 | reference by constraint only (inversion) | PASS |  | resolved to place:allocation_vault via ['constraint_inversion:contains(obj:memory_core)'] |
| 28 | two same-kind objects in scope | FAIL | extraction | only 0 drawer(s) under the desk: [] |
| 29 | causal chain >=3 links | PASS |  | 3 caused_by edges |
| 30 | hidden truth, >=2 discovery paths converge (letter + core) | PASS |  | corroborated key found: True |
| 31 | witness with breaking condition (Marn confronted) | FAIL | extraction | 0 confession/confrontation rows |
| 32 | consequence-of-inaction (clock material) | PASS |  | 11 depletion/clock rows |
| 33 | sensory atmosphere did NOT become assertions | PASS |  | 0 texture rows (should be 0) |

## Coverage honesty (letters 004/006, bible A5)

- Q2: lateral graph: planted non-connection landed in v1 (feature 9) — graded
- Q6: accrual-promotion candidate planted in v1 (feature 10, 3x utterance) — graded leniently
- Q21: never-opened containers: N=2 in v1 (footlocker + PERSONAL case)

## Reading the classes

- **extraction** — the engine's invariants held; the model-side extraction missed or mangled content. Fix the extractor contract and re-run.
- **shape** — the substrate itself misbehaved (silent merge, phantom contents, frame leak, canon mutation). Stop: whitepaper conversation.
