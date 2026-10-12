# Roadmap

## Vision

**The memory under the holodeck: a world that never degrades.**

Show pattern-buffer a world — a book, a campaign, a case file, a household's
messy conversation — and from then on it holds that world's truth. Every question
about it is answered by lookup, not by re-reading or guessing: where the key is,
where it was at midnight, who knows the steward lied, what the player hasn't found
yet. A pipe left in a drawer in session 12 is still there in session 200, with its
whole history, because nothing had to remember it. Silence is persistence.

It is one engine for two kinds of world. In a story, the page is true forever and
undecided detail is invented once, under the world's own rules, then kept. In real
life, it never invents: it says what it observed, when, and how stale that is, and
"I don't know" is always an honest answer. Same log, same reads, two physics.

It is part of a family. **construct** tells the story and holds its arc;
**pattern-buffer** holds what is true as the story unfolds; **holo-emitter** turns
that truth into a place you stand in. pattern-buffer is the floor both stand on:
it never speaks, never decides what happens next, and never calls them. Any other
host — Kernos, a game, an agent's long-term memory — sits on it the same way.

**What it fundamentally is.** One append-only log of facts, each with who-knows-it,
when-it-held, when-we-learned-it, and how-we-know-it. Everything else — the current
state, the map, each character's knowledge, the briefing a narrator reads — is
computed from the log and can be thrown away and rebuilt. Characters cannot leak
what was never in their view, because it isn't there.

**What finished and excellent mean.**
- *Hand it a book and walk in.* A whole novel (Alice is the standing example)
  becomes a world that answers every state question the text supports, correctly
  and from any character's point of view, in reasonable time and cost — and says
  plainly where the text was silent. Making a whole book a faithful world, fast,
  is pattern-buffer's own job and its next big front.
- *It never lies about the world.* No fact without its provenance; no invention
  dressed as canon; no contradiction silently overwritten.
- *Any host, no reaching in.* A host builds on the frozen contract alone — Python
  directly, anything else over the wire — and never needs the engine's insides.
- *Measured, not claimed.* The chapter test, the tracking battery and the
  fidelity metric grade it against ground truth; the open front (reading prose
  into facts faithfully) is a number that goes down build over build. The finish
  is held to the TNG pattern buffer of "Relics": seventy-five years, zero
  degradation, perfect retrieval.

**Settled with this vision.**
- The family is the proving ground. The public library (PyPI, docs, other
  adopters) is kept clean as a by-product, not chased as a separate goal.
- The engine stays behind construct, not in the browser. A browser path becomes
  a deliberate choice only when holo-emitter needs truth with no server.
- Real-world tracking (Kernos, the household) is kept healthy, not driven, until
  Kernos returns to it.

**Where this narrows what was asked.** It does not render, narrate, pace drama, or
search by meaning; those belong to holo-emitter, construct and the hosts. It holds
symbolic truth, not geometry.


## M1 — The substrate: one log, two physics, a frozen contract

- [x] R1 The *Last Honest Meter* seed recovered; the engine spike (PatternBuffer, derived indexes, classifier, projector, resolver, `refer()` tier 1) (`specs/SPIKE-V1.md`, `evals/last_honest_meter/`)
- [x] R2 The chapter test, runs 1–4: substrate validated, every remaining failure extraction-class; run 4 22/33 (README "The road" 3; `evals/results/`)
- [x] R3 Registry-first ingestion, then latency and hardening (`specs/INGEST-V2.md`, `INGEST-LATENCY-V2.md`, `INGEST-HARDENING-V1.md`)
- [x] R4 The messy-dialogue micro-eval, 10/10 (`specs/MICRO-EVAL-V1.md`)
- [x] R5 The frozen porcelain; the first host (construct) runs on it with zero internal reaches (`specs/PORCELAIN-V1.md`, whitepaper §25.1)
- [x] R6 The read and identity layers, composition, traversability, exact decimals, the build lifecycle (`specs/STATUS.md` Shipped table; whitepaper §25.2–§25.8)
- [x] R7 The MCP wrapper: 39 deterministic verbs over stdio (`specs/MCP-WRAPPER-V1.md`)
- [x] R8 Tracking mode proven: decay by unconfirmed wall time, 14/14 (`specs/TRACKING-MODE-V1.md`, `evals/the_grey_house/`)
- [x] R9 The ingestion-fidelity contract (`specs/INGESTION-FIDELITY-V1.md`, `V2.md`)
- [x] R10 Movement events, all-or-none activation, source identity (`specs/MOVED-EVENT-V1.md`, `ATOMIC-ACTIVATION-V1.md`, `SOURCE-IDENTITY-V1.md`)
- [x] R11 Published as `pbuffer` 0.2.0 on PyPI (README "Install")

## M2 — Correct and elegant: the October 2026 self-audit

Kabe asked for a self-audit because the engine was built with weaker models. The
ranked findings and the five fix batches are in `docs/AUDIT-2026-10.md`. Each
batch goes spec → pbr GREEN → build → pbr GREEN → ship-notice to construct. Branch
state is in `docs/HANDOFF-2026-10-09.md`.

- [x] R12 Five-part audit, every P1 reproduced; ranked note (`docs/AUDIT-2026-10.md`)
- [x] R13 Behaviour-preserving polish and read caches, byte-identical, on main (`docs/AUDIT-2026-10.md` "Done on polish/audit-2026-10")
- [x] R14 holds/wearing stored backwards, live in construct's worlds — pbr GREEN, merged 2026-10-09 (`specs/GATE-INVERSE-ALIAS-V1.md`; whitepaper A19)
- [x] R15 Batch A, fold correctness — pbr GREEN, merged 2026-10-09 (`specs/FOLD-CORRECTNESS-V1.md` r3; whitepaper A18)
- [x] R16 Batch B, gate authority — pbr GREEN, merged 2026-10-09 (`specs/GATE-AUTHORITY-V1.md` r2; whitepaper A20)
- [x] R17 Batch C, frame-scoped identity — pbr GREEN, merged 2026-10-09 without §7 (`specs/FRAME-SCOPED-IDENTITY-V1.md` r2; whitepaper A21). §7 (frames following merges) withdrawn: Kabe accepted g3bf5da P1 on 2026-10-12, so a frame reads only its own name by default. The r1 build stays on `hold/frame-scoped-identity-v1-r1` as history
- [x] R18 Batch D, refer learns words, not picks — pbr GREEN, merged 2026-10-09 (`specs/REFER-LEARNING-V1.md`; whitepaper A22)
- [x] R19 Batch E, the additive read surface: construct's three asks — pbr GREEN, merged 2026-10-09 (`specs/READ-SURFACE-V1.md` r1.1; whitepaper A23)
- [~] R20 Ship notices to construct as each batch lands; construct repairs its worlds with the holds/wearing recipe (live player worlds are Kabe's call; construct brings him the list) (`docs/ADOPTION.md` "Inverse predicates"). A and R14 noticed 2026-10-09; construct's 1,542 tests green on them, nothing to re-baseline. B noticed 2026-10-09; construct green on it (1,544 tests) after a one-line fix to its private-API test patch. C noticed 2026-10-09; construct green on it (1,544 tests); it confirms thedeep's chen/elias_chen with the g698a80 repairs. D noticed 2026-10-09; construct green on it (1,544 tests), watching the cost of re-judging ambiguous references in its latency work. E noticed 2026-10-09; construct green on it (1,544 tests, one of its tests updated for the `in` spelling rule); the five junk protagonist-frame aliases E's first-own-words rule binds join the g698a80 repair list; construct adopts E's levers in daytime. R22 merged after construct's own run on the branch (1,545 tests), with its kind-less events guarded
- [~] R21 P2 structure: one merge-veto gate table, one rows-between scan, `indexes.py` split behind its facade, the classifier rubric unified (`docs/AUDIT-2026-10.md` "P2"); the split is proposed to Kabe in `docs/proposals/R21-INDEXES-SPLIT.md`, Kabe approved the split 2026-10-12 (g2c1aa1); building on `refactor/indexes-split`
- [~] R35 Identity's root causes (g3bf5da P3, accepted 2026-10-12): name-like anchors only, retracted merges stay retracted, `decided_by` on every merge, no automatic merge of a frame owner (`specs/IDENTITY-ROOT-CAUSES-V1.md`, in pbr spec review). R24 Part B and R25 follow it
- [ ] R36 Widening a frame is an explicit, logged host choice: a frame-continuity/combine event, reversible by retraction; book readers opt in per read; the battery grades the engine's own frame read (g3bf5da P2, accepted 2026-10-12)
- [x] R22 `events()` from one reader, shared with `in_transit`; `state()` on event entities — pbr GREEN, construct green on the branch, merged 2026-10-10 (`specs/EVENTS-ONE-READER-V1.md`; whitepaper A24)

## M3 — Book in, world out

The vision's next front: a whole book becomes a faithful world, fast. Prior art
and the three most promising techniques are in
`docs/research/book-to-world-extraction-2026-10.md`. Its weighed-advice section
adds a memorization control: a counterfeit edition plus a noise floor, so Alice
measures reading, not recall.

- [x] R23 Grade pass-0 registry quality directly against gold (linking P/R/F1 plus a cluster fragmentation metric), so every change is measured (research note "Answer") — done 2026-10-10: `evals/harness/grade_registry.py`; baseline in `evals/results/2026-10-10-r23-pass0-baseline/REPORT.md` (two runs: B3 F1 0.752 / 0.735, noise floor ~0.02). Pass-0 splits Ilsa Renn in every run; after seeding, the engine's reconcile closes that split but fuses the Records Vault with the Seed Vault in both fresh runs (evidence for g3bf5da P3). Also found and fixed: today's model minted `person:/x` ids the engine refuses (`fix/pass0-id-shape`)
- [~] R24 A deterministic alias-index pass between pass-0 and pass-1: global name propagation, a kinship/address stoplist, `distinct_from` proposals from coordination and co-presence (research note, technique 1) — Part A done 2026-10-10 (`evals/harness/alias_index.py`; `specs/ALIAS-INDEX-V1.md`): on R23's registries it finds the vault pair as distinct and the Ilsa pair as a merge candidate. Part B (writing identity rows) waits on g3bf5da P3
- [ ] R25 Handle-based incremental `extend` with a verified merge gate: the harness mints the ids, and merges are checked by a yes/no call (research note, technique 2)
- [~] R26 Per-stage build timings, then parallel map-reduce pass-0 plus gleaning (research note, technique 3) — measured 2026-10-10 (`evals/results/2026-10-10-r26-build-timings/REPORT.md`, 4 runs): a build is 32 min, pass-0 46%, pass-1 29%, classification 13%, audit 10%, engine work <1%. Parallel pass-0 cuts pass-0 to 449-517 s and meets the pass mark by the letter, but fragments the registry (13 split entities vs 0), so it stays off until R24 Part B and R25. Gleaning not run (cap)
- [ ] R27 A whole book end to end, Alice as the standing example: time, cost and fidelity receipts (vision "Hand it a book and walk in"). Kabe (g6cee1d, 2026-10-12): run the original and a counterfeit edition (renamed characters plus scripted state edits), each twice, and report a run-to-run noise floor

## M4 — One world for every module

Kabe approved 2026-10-12 (gate gde97f3): "Full agree on establishing that service and adopting the unified methods discussed in the round robin." The agreed structure is `specs/proposals/UNIFIED-WORLD-ACCESS.md`. construct, holo-emitter and Photonic build their own sides.

- [ ] R37 E2: the generator receives a structured resolve request (`entity`, `kind`, `aspect`, `constraints`, `as_of`) beside the prompt
- [ ] R38 E1: resolve the unmarked. In an opted-in story world, `resolve()` on a declared aspect with nothing known plants and forces it in one call; anything undeclared is refused
- [ ] R39 S1: the WorldService library (one handle, a serialized write queue, reads and resolve for every module, a rate cap) and an optional standalone runner with a `record` door
- [ ] R40 S2: the player's-view export plus a change feed, for offline mirrors
- [ ] R41 E3: worn things are objects (`worn_by`), promoted like furniture, after R35

## Later

- [ ] R28 Simplify the connection facade to a small gated API; back through pbr (`docs/AUDIT-2026-10.md` decision 6)
- [ ] R29 Undeclared-origin pooling, decided on merit (`specs/STATUS.md` open questions; `specs/SOURCE-IDENTITY-V1.md` §6)
- [ ] R30 The pbeo take-back: take 3 / adapt 3 / add 1, including the corroboration gradient (`specs/STATUS.md` open questions)
- [ ] R31 A knowledge sheet as an overlay on canon (case probe S9/E5; `evals/case_1660_probe/` on `research/case-1660-probe-r4`)
- [ ] R32 Deferred characteristics, each waiting on its named tripwire: nested belief, general query, salience tuning, looping time, rate quantities (`docs/ROADMAP-deferred.md`)
- [ ] R33 A browser path for the engine, only when holo-emitter needs truth with no server (vision, "Settled")
- [ ] R34 The Kernos adapter for real-world tracking, when Kernos returns to it (vision, "Settled"; whitepaper §17.2)
