# Commit-id map, 2026-10-12 rebuild

On 2026-10-12, the 126 commits made after `b1e10b7` were rebuilt before they were pushed (Kabe, gate g76aa42: text from actual play is kept out from here on). The final tree is identical, and the engine code (`src/`) is unchanged in every commit.

- **What changed:** only the specs, tests and handoff that had quoted a live player world got neutral labels.
- **What that does to ids:** older notes in this repo, and other projects' pins, cite the pre-rebuild ids. This table maps them. The old commits remain locally on the `backup/main-pre-clean` branch.

| Old | New | Commit |
|---|---|---|
| `ae73e81` | `ae73e81` | Docs: g3bf5da P1 withdraws FSI §7 in the whitepaper; g6cee1d recorded on R27 |
| `ce8c1c6` | `ce8c1c6` | Merge feat/resolve-request: RESOLVE-REQUEST-V1 (E2, R37), pbr GREEN |
| `f420438` | `f420438` | Docs: E2 merged (pbr GREEN), README 1090, STATUS, roadmap |
| `b23d1ae` | `b23d1ae` | Merge refactor/indexes-split: R21 indexes.py becomes a package of section mixins, byte-ide |
| `1bc887b` | `1bc887b` | Docs: R21 split merged (pbr GREEN, byte-identical); main green with E2 |
| `208c2dd` | `208c2dd` | Merge feat/resolve-unmarked: RESOLVE-UNMARKED-V1 (E1, R38), pbr GREEN |
| `5e97c40` | `5e97c40` | Docs: E1 merged (pbr GREEN), README 1134, STATUS, roadmap |
| `0bc194a` | `0bc194a` | Handoff 2026-10-12: R21, E2, E1 shipped; R35 in review; decisions waiting |
| `91376b3` | `99af804` | Merge spec/identity-root-causes-v1: IDENTITY-ROOT-CAUSES-V1 (R35, g3bf5da P3), pbr GREEN |
| `bcd14e1` | `011b782` | Docs: R35 merged (pbr GREEN), README count, STATUS, roadmap, handoff |
| `4b794ee` | `4d34c74` | Handoff: counts and order after R35 |
| `a92de08` | `9d2f4ff` | Roadmap/handoff: R36 and S1 specs GREEN, building; P4 accepted |
| `f929175` | `8ef7181` | Merge spec/frame-continuity-v1: FRAME-CONTINUITY-V1 (R36; g3bf5da P2+P4), pbr GREEN |
| `00949bf` | `472efd0` | Docs: R36 merged (pbr GREEN), README 1215, STATUS, roadmap, handoff |
| `c44ad49` | `134eb8f` | Merge spec/world-service-v1: WORLD-SERVICE-V1 (S1, R39), pbr GREEN |
| `48085fd` | `2824285` | Docs: S1 merged (pbr GREEN), README 1483, STATUS, roadmap, handoff |
| `00e2105` | `3510765` | Merge spec/identity-representative-v1: IDENTITY-REPRESENTATIVE-V1, pbr GREEN |
| `f275e40` | `23a98b8` | Merge feat/resolve-request-current: RESOLVE-REQUEST-V1.1 (ResolveRequest.current), pbr GRE |
| `e00235b` | `8d472a1` | Docs: IDENTITY-REPRESENTATIVE-V1 and RESOLVE-REQUEST-V1.1 merged (pbr GREEN); README count |
| `ebdd53e` | `e431546` | Handoff: construct pins its live engine (now f275e40); its protagonist-split fix uses repr |
| `470e04a` | `397b252` | Handoff: holo-bridge and g698a80 were settled overnight by the monitor (ga11d4a, g82aabc); |
| `8a95aff` | `2ac7e9f` | ROADMAP: R40 (S2) in progress, spec VIEW-EXPORT-V1 r1 with pbr |
| `db7f5d6` | `84f6413` | ROADMAP: R42 host-only closure read for construct (gate gc857b5, monitor's call) |
| `188e310` | `f83f1e9` | Merge feat/view-export-v1: VIEW-EXPORT-V1 (S2/R40, offline mirror + feed), pbr GREEN on sp |
| `10b9c3b` | `e38820e` | Docs: VIEW-EXPORT-V1 merged (S2/R40, pbr GREEN): STATUS, whitepaper A30, README 1615, R40  |
| `9f6600e` | `aa1e7b1` | Merge feat/closure-read-v1: CLOSURE-READ-V1 (R42, host-only closure/distinct_between), pbr |
| `0cfa276` | `bee6ac7` | Docs: CLOSURE-READ-V1 merged (R42, pbr GREEN): STATUS, README 1628, R42 done |
| `96bdb33` | `2c78dbb` | Handoff: S2 (R40) and R42 merged |
| `0e44d5d` | `0ff7451` | ROADMAP: R42a facts(bookkeeping=False) (gate g4d7cf0, monitor's call) |
| `0eb4e3f` | `5a9e826` | Merge feat/facts-bookkeeping-v1: FACTS-BOOKKEEPING-V1 (R42a, facts bookkeeping=False), pbr |
| `2e27a8a` | `ae0418f` | Docs: FACTS-BOOKKEEPING-V1 merged (R42a, pbr GREEN): STATUS, README 1635, roadmap, handoff |
| `2cce315` | `2ec9ab3` | ROADMAP: R41 (E3) in progress, spec WORN-OBJECTS-V1 r1 |
| `f3e306d` | `6494b0a` | ROADMAP Later: containment read with each item's edge (construct, me79b81) |
| `b7a4020` | `9173b6b` | ROADMAP: number the Later item R43 |
| `a3398ba` | `98007eb` | Handoff: construct pins 0eb4e3f (R42 + R42a); its identity branch uses the new reads |
| `d04d236` | `c41a630` | Merge feat/worn-objects-v1: WORN-OBJECTS-V1 (E3/R41, attire mints worn things; generated n |
| `55f3bf2` | `b86f5e8` | Docs: WORN-OBJECTS-V1 merged (E3/R41, pbr GREEN): STATUS, whitepaper A31, README 1668, R41 |
| `afebf5e` | `fffe362` | Handoff: R24 Part B in spec review (measured first); proposed one-line M3 'done' for Kabe |
| `d8fae35` | `6083637` | Merge feat/alias-index-part-b: ALIAS-INDEX-V1 Part B (R24; book commits reconcile with Par |
| `55b8e62` | `0814b96` | Docs: ALIAS-INDEX-V1 Part B merged (R24, pbr GREEN): STATUS, README 1700, R24 done, handof |
| `d265f74` | `5ec6639` | R27 case for Kabe's conversation: purpose, counterfeit, cost estimate, options A-D, M3 don |
| `a13c9a9` | `5a2cf59` | Merge feat/merge-gate-v1: MERGE-GATE-V1 (R25 part A, verified merge gate, off by default), |
| `b12f5b1` | `a91f352` | Merge chore/relabel-player-worlds: replace live-player world text with neutral labels (Kab |
| `ae7a336` | `6e49834` | Docs: MERGE-GATE-V1 merged (R25 part A, pbr GREEN, off by default): STATUS, README 1775, R |
