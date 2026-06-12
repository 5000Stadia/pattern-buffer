# Chapter-test scorecard — The Last Honest Meter

- **Seed version:** v1-final (results are never compared across seed versions)
- **Date:** 2026-06-11
- **Extractor model:** claude-sonnet-4-6
- **Log size:** 495 assertions, 68 entities, 6 frames
- **Score: 21/33 PASS** — 11 extraction-class failures (fixable), 1 shape-class failures (whitepaper conversation)

| Q | Battery item | Verdict | Class | Detail |
|---|---|---|---|---|
| 1 | containment tree >=4 deep | FAIL | extraction | max depth 3 |
| 2 | lateral graph: long way, no direct edge (feature 9) | FAIL | extraction | path=['place:council_tier', 'place:dead_elevator', 'place:seed_vault'] |
| 3 | fixture vs movable containment | PASS |  | fixture_ok=True movable_ok=True |
| 4 | object moving through relation types (maps chain) | FAIL | extraction | distinct holders over time: ['person:tovan_voss', 'place:south_lock'] |
| 5 | deliberate constitutive contradiction flagged (feature 8) | PASS |  | flag fired; values [2, 3] coexist |
| 6 | dispositional habits (+3x utterance, feature 10 lenient) | PASS |  | 27 dispositional rows |
| 7 | attribute superseded 3+ times (core custody) | PASS |  | core had 6 distinct holders: ['place:anchor', 'place:records_vault', 'obj:false_drawer', 'obj:master_meter', 'place:seed_vault', {'policy': 'invent_under_canon' |
| 8 | world_defining condition (water crisis/rationing) | PASS |  | 28 crisis-condition rows |
| 9 | transient mood -> STATE (asymmetric default) | PASS |  | 0 mood rows, 0 misclassified CONSTITUTIVE |
| 10 | narrative clock on the spine | FAIL | extraction | stamped=125 unstamped=17 distinct_times=12 |
| 11 | off-screen reveal: valid_time != asserted_at (e25) | PASS |  | core at day 4.5: chain=['place:seed_vault'] |
| 12 | future-scheduled/conditional event | FAIL | extraction | 0 future/conditional rows |
| 13 | derive-don't-store over time (no stored derivable ages) | PASS |  | 0 age rows, 0 derivable (violations) |
| 14 | one object at three timestamps (core) | FAIL | extraction | during the Ch.1 assembly (e25): ok; Days 1-3, in the false drawer (e16): ok; after the tribunal (e41): ['place:seed_vault'] |
| 15 | >=3 knowledge frames + canon-minus-everyone delta | PASS |  | populated frames: ['knows:person:marn', 'knows:person:narrator', 'knows:person:pell', 'knows:person:sela_voss', 'knows:person:tovan_voss'] |
| 16 | telling scene: frame transfer, canon unchanged (feature 5) | PASS |  | frame row a:343 after canon rows; provenance retained |
| 17 | contested truth (official story vs canon) | FAIL | extraction | 0 official-story rows |
| 18 | justified-but-wrong belief undermined | PASS |  | 36 belief rows; retraction present: True |
| 19 | inference/assumption distinguishable from narration | PASS |  | statuses present: ['inferred', 'observed', 'retracted', 'stated'] |
| 20 | document trust chain: per-claim fates (A4) | PASS |  | doc rows=18 quantity_converged=True false_claim_superseded=True |
| 21 | never-opened containers stay unresolved (N=2) | PASS |  | footlocker: PASS (no phantom contents); personal_case: PASS (no phantom contents) |
| 22 | walked-away branch stays frontier (aquifer outcome) | PASS |  | 0 premature aquifer-outcome rows |
| 23 | locked container changes hands unopened (feature 4/11) | FAIL | extraction | day7=[] day21=['place:condenser_station', 'place:rust_quarter', 'place:old_highway'] sealed=True |
| 24 | late binding: clerk == Ilsa Renn (feature 1) | FAIL | extraction | named identity reaches clerk rows: True; entities carrying the name: ['doc:inventory_ledger', 'person:ilsa_renn'] |
| 25 | one person referred 3+ ways | PASS |  | 6 referring expressions: ['custodian of the unified archive', 'ilsa renn', 'the clerk', 'the clerk with the tin ear', 'the small gray woman', 'the third clerk'] |
| 26 | coarse container differentiated (vault split, feature 3) | FAIL | shape | two vaults=True; refer('the vault')=resolved () |
| 27 | reference by constraint only (inversion) | PASS |  | resolved to obj:master_meter via ['constraint_inversion:contains(obj:memory_core)'] |
| 28 | two same-kind objects in scope | FAIL | extraction | only 0 drawer(s) under the desk: [] |
| 29 | causal chain >=3 links | PASS |  | 13 caused_by edges |
| 30 | hidden truth, >=2 discovery paths converge (letter + core) | PASS |  | corroborated key found: True |
| 31 | witness with breaking condition (Marn confronted) | FAIL | extraction | 0 confession/confrontation rows |
| 32 | consequence-of-inaction (clock material) | PASS |  | 4 depletion/clock rows |
| 33 | sensory atmosphere did NOT become assertions | PASS |  | 0 texture rows (should be 0) |

## Coverage honesty (letters 004/006, bible A5)

- Q2: lateral graph: planted non-connection landed in v1 (feature 9) — graded
- Q6: accrual-promotion candidate planted in v1 (feature 10, 3x utterance) — graded leniently
- Q21: never-opened containers: N=2 in v1 (footlocker + PERSONAL case)

## Reading the classes

- **extraction** — the engine's invariants held; the model-side extraction missed or mangled content. Fix the extractor contract and re-run.
- **shape** — the substrate itself misbehaved (silent merge, phantom contents, frame leak, canon mutation). Stop: whitepaper conversation.
