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
- [~] R20 Ship notices to construct as each batch lands; construct repairs its worlds with the holds/wearing recipe (live player worlds are Kabe's call; construct brings him the list) (`docs/ADOPTION.md` "Inverse predicates"). A and R14 noticed 2026-10-09; construct's 1,542 tests green on them, nothing to re-baseline. B noticed 2026-10-09; construct green on it (1,544 tests) after a one-line fix to its private-API test patch. C noticed 2026-10-09; construct green on it (1,544 tests); it confirms thedeep's chen/elias_chen with the g698a80 repairs. D noticed 2026-10-09; construct green on it (1,544 tests), watching the cost of re-judging ambiguous references in its latency work. E noticed 2026-10-09; construct green on it (1,544 tests, one of its tests updated for the `in` spelling rule); the five junk protagonist-frame aliases E's first-own-words rule binds join the g698a80 repair list; construct adopts E's levers in daytime. R22 merged after construct's own run on the branch (1,545 tests), with its kind-less events guarded. Run 11 (2026-10-14, on 42d0c23): the containment fix held (no flicker); chapter 1 failed on narrated objects, and one cause is the engine's: one extraction wrote a move as both ends at one valid time (`in obj:belt` restated beside `in person:tomas_venn`), which reads conflicted. RESTATED-ORIGIN-V1 (an engine gate rule dropping a same-call, same-time restatement) reached pbr GREEN at r1.5 but was withdrawn before build: the step-up build reproduced three ways a gate-side drop diverges (an already-open unit in `World._mirror`, a dropped item's first-use declaration, later cycle checks). The fix goes to construct's settle, which sees one extraction of one turn; the extraction-prompt rule is the later metered root fix
- [~] R21 P2 structure: one merge-veto gate table, one rows-between scan, `indexes.py` split behind its facade, the classifier rubric unified (`docs/AUDIT-2026-10.md` "P2"); the split is proposed to Kabe in `docs/proposals/R21-INDEXES-SPLIT.md`, Kabe approved the split 2026-10-12 (g2c1aa1). The split is done: pbr GREEN, merged 2026-10-12, byte-identical (`src/patternbuffer/indexes/`, one mixin per section; 165 construct worlds, about 1.79M reads, 0 differences). Next come the merge-veto table and the rows-between scan
- [x] R35 Identity's root causes (g3bf5da P3, accepted 2026-10-12): name-like anchors only, retracted merges stay retracted, `decided_by` on every merge, no automatic merge of a frame owner (`specs/IDENTITY-ROOT-CAUSES-V1.md` r3; whitepaper A25) — pbr GREEN, merged 2026-10-12. On construct's 52 worlds it declines 12 of main's 24 re-reconcile merges and makes none of its own; one declined pair was a real fusion of two women on "her hands". Book grading is unchanged. R24 Part B and R25 are now unblocked
- [x] R36 Widening a frame is an explicit, logged host choice: a frame-continuity/combine event, reversible by retraction; book readers opt in per read; the battery grades the engine's own frame read (g3bf5da P2, accepted 2026-10-12; P4 accepted the same day). Spec `specs/FRAME-CONTINUITY-V1.md` r2 is pbr GREEN, built and merged 2026-10-12 (pbr GREEN on code; whitepaper A28): `provenance.frame` on every fact, and `frame_scope` exact|continued|merged on `state`, `state_union` and `facts` only
- [x] R22 `events()` from one reader, shared with `in_transit`; `state()` on event entities — pbr GREEN, construct green on the branch, merged 2026-10-10 (`specs/EVENTS-ONE-READER-V1.md`; whitepaper A24)

## M3 — Book in, world out

The vision's next front: a whole book becomes a faithful world, fast. Prior art
and the three most promising techniques are in
`docs/research/book-to-world-extraction-2026-10.md`. Its weighed-advice section
adds a memorization control: a counterfeit edition plus a noise floor, so Alice
measures reading, not recall.

- [x] R23 Grade pass-0 registry quality directly against gold (linking P/R/F1 plus a cluster fragmentation metric), so every change is measured (research note "Answer") — done 2026-10-10: `evals/harness/grade_registry.py`; baseline in `evals/results/2026-10-10-r23-pass0-baseline/REPORT.md` (two runs: B3 F1 0.752 / 0.735, noise floor ~0.02). Pass-0 splits Ilsa Renn in every run; after seeding, the engine's reconcile closes that split but fuses the Records Vault with the Seed Vault in both fresh runs (evidence for g3bf5da P3). Also found and fixed: today's model minted `person:/x` ids the engine refuses (`fix/pass0-id-shape`)
- [x] R24 A deterministic alias-index pass between pass-0 and pass-1: global name propagation, a kinship/address stoplist, `distinct_from` proposals from coordination and co-presence (research note, technique 1) — Part A done 2026-10-10 (`evals/harness/alias_index.py`; `specs/ALIAS-INDEX-V1.md`): on R23's registries it finds the vault pair as distinct and the Ilsa pair as a merge candidate. Part B (writing identity rows) is unblocked now that R35 has merged Part B merged 2026-10-12 (pbr GREEN, spec r4.2): book commits now `reconcile`, with host `distinct_from` for strong non-person pairs before it; on the stored registries F1 is unchanged, fusion is 0, and parallel pass-0's fragmentation falls from 13 to 4 and 7. The metered chapter run comes with R27
- [~] R25 Handle-based incremental `extend` with a verified merge gate: the harness mints the ids, and merges are checked by a yes/no call (research note, technique 2) — part A (the merge gate, `specs/MERGE-GATE-V1.md`) merged 2026-10-12, pbr GREEN, off by default; its free pass mark is met (an oracle gate brings parallel pass-0's splits to 0); the real-model measurement ran 2026-10-13 on Kabe's yes (gf981cd) and passes in both repetitions (`evals/results/2026-10-13-r25-merge-gate-metered/REPORT.md`): no merge of a gold-different pair, 9 and 8 of 11 gold-same pairs joined, and parallel pass-0's splits fall from 4 and 7 to 1 and 1–2 with no fusion (F1 0.843 / 0.834). One unlabelled event-into-object merge in one repetition led to r2.2 (pbr GREEN, merged 2026-10-13): event × non-event is never a candidate, which also cuts a repetition from 36 calls to 29, with recall and the oracle ceiling unchanged. Part B (handles in pass-0) needs metered runs and comes later
- [~] R26 Per-stage build timings, then parallel map-reduce pass-0 plus gleaning (research note, technique 3) — measured 2026-10-10 (`evals/results/2026-10-10-r26-build-timings/REPORT.md`, 4 runs): a build is 32 min, pass-0 46%, pass-1 29%, classification 13%, audit 10%, engine work <1%. Parallel pass-0 cuts pass-0 to 449-517 s and meets the pass mark by the letter, but fragments the registry (13 split entities vs 0), so it stays off until R24 Part B and R25. Gleaning not run (cap)
- [~] R27 A whole book end to end, Alice as the standing example: time, cost and fidelity receipts (vision "Hand it a book and walk in"). Kabe (g6cee1d, 2026-10-12): run the original and a counterfeit edition (renamed characters plus scripted state edits), each twice, and report a run-to-run noise floor. Revised by Kabe 2026-10-13: "Make chatgpt write the fiction so its anonymous and original - tell it to try to make something out there and original". Reading: the test book is a new novella (~25k words, 12 chapters) written by ChatGPT (Codex CLI) with a hidden answer key (aliases, reveals, look-alikes, locations, holdings, containers, knowledge, corrections), so nothing can be remembered and the gold is exact. This replaces the counterfeit Alice; Alice stays the vision's example of the use. Prepared 2026-10-13: the book is `evals/books/the-weather-that-would-not-leave/` (12 ch, ~25.3k words; two-reader graded gold), and the runner and grader are BOOK-RUN-V1 (pbr GREEN, merged). The builds are paused by Kabe for speed work (g10c3af, 2026-10-13): BUILD-PROFILE-V1 is merged (per-call timing, turns and tokens), and the consult's four points wait on gate g936be9

## M4 — One world for every module

Kabe approved 2026-10-12 (gate gde97f3): "Full agree on establishing that service and adopting the unified methods discussed in the round robin." The agreed structure is `specs/proposals/UNIFIED-WORLD-ACCESS.md`. construct, holo-emitter and Photonic build their own sides.

- [x] R37 E2: the generator receives a structured resolve request (`entity`, `kind`, `aspect`, `constraints`, `as_of`) beside the prompt — pbr GREEN, merged 2026-10-12 (`specs/RESOLVE-REQUEST-V1.md`; `ResolveRequest` on a byte-identical `TaskSchema`, read with `task_request()`)
- [x] R38 E1: resolve the unmarked. In an opted-in story world, `resolve()` on a declared aspect with nothing known plants and forces it in one call; anything undeclared is refused — pbr GREEN, merged 2026-10-12 (`specs/RESOLVE-UNMARKED-V1.md`; whitepaper A26)
- [x] R39 S1: the WorldService library (one handle, a serialized write queue, reads and resolve for every module, a rate cap) and an optional standalone runner with a `record` door — pbr GREEN, merged 2026-10-12 (`specs/WORLD-SERVICE-V1.md` r5; `patternbuffer.service`; whitepaper A27). The host attaches and pumps; viewers read an in-memory `World.snapshot()` through an explicit allowlist locked to the view frame; resolve plus mirror happens in one unit; the rate cap comes through `svc.gated(model)`; the runner is localhost only
- [x] R40 S2: the player's-view export plus a change feed, for offline mirrors
- [x] R41 E3: worn things are objects (`worn_by`), promoted like furniture, after R35
- [x] R42 A host-only `closure(entity, asserted_as_of=None)` read (plus `distinct_between` if construct's swap needs it), so construct stops copying the engine's identity walk; after R40 merges. *Monitor's call for Kabe (gate gc857b5, note ne26319).*
- [x] R42a `facts(..., bookkeeping=False)`: a frame scan without the engine's bookkeeping rows, so construct holds no copy of `META_ATTRIBUTES` (cr's boundary finding). *Monitor's call for Kabe (gate g4d7cf0, note n7052ef).*
- [x] R45 Author-side `record`: a session that writes canon (or a named frame) without writing the player's view, for Photonic's people positions and activity (Photonic SEAM a, m019da7). Kabe yes on gf985f8 ("2 agree", in Photonic's console, relayed in ma3a689). `specs/AUTHOR-RECORD-V1.md` r1.1, pbr GREEN on the spec and the code, merged 2026-10-13. Photonic approved it as written (m79a495) and writes canon only.
- [x] R46 People on the device: persons' canon position and activity in the offline mirror, so walking into an unseen room finds them where the world says (VIEW-EXPORT-V1 §2; Photonic SEAM b). Kabe yes on gf985f8, with the exposure accepted for single-player (a curious player could read people's whereabouts off the device). `specs/VIEW-PEOPLE-V1.md` r2.2, pbr GREEN on the spec and the code, merged 2026-10-13. It took Photonic's review: `rest_pos` crosses as a short numeric array.
- [x] R47 A small `patternbuffer` JS module: view/1 `apply()` passing `tests/vectors/view-feed-v1.json`, IndexedDB-persisted, plus a queued `record`; Python stays the reference (Kabe's rule on g1eeae0: each element used from its home). Kabe yes on gf985f8. `specs/VIEW-JS-V1.md` r2.1, with review from holo-emitter (eviction, cross-tab locks) and Photonic; pbr GREEN on the spec and the code; merged 2026-10-13.
- [x] R48 The merge gate as an engine verb: `porcelain.merge_gate(...)` using the world's injected model, with `apply=False` for verdicts only, so construct uses the measured gate instead of growing its own (construct mba5a02, run 8's identity stop). Monitor yes for Kabe (g9e7f39, n7fd416); `specs/MERGE-GATE-VERB-V1.md` r1.3.2, pbr GREEN spec and code, merged 2026-10-13 (whitepaper A32). Construct's full suite passed on it (1,647 passed, 1 skipped, against 96554de), and its integration smoke drove the real verb through same, different and unsure (m94693c).
- [x] R49 Kind is a type, not a role: the engine's extraction prompt (`ingest.py`, both prompts) says only "'kind' for what a thing is", so a person comes out as kind 'condemned man' beside 'person', and identity declines the merge (`kind_conflict`). Persons get kind `person`, and the role goes to its own attribute. Existing worlds are unchanged. Construct's run-8 pairs then become `alias_not_specific` and can go to R48's gate (construct m02bdb6). Kabe (g9c3792): "imagine a character whose spans a story of a lifetime … a prisoner, one chapter and a hero the next, so build an elegant structure accordingly". `specs/PERSON-ROLES-V1.md` r1.3: `role` is set-valued and dated, eras are derived, and the gate moves a person's non-person kind into `role` with its own receipt. pbr GREEN on the spec and the code, merged 2026-10-13 (whitepaper A33).
- [x] R53 Beats as tracked world structure. Kabe (holo-emitter's R79 gate, 2026-10-13, relayed in mf409d7): "it makes sense that the system of ingesting the plot/story beat/puzzle chains ... is assimilated and ingested functionally at the same time that pattern buffer ingest its objects and it may be efficient to consider where those two mechanisms overlap, and if this should actually exist as a tracking mechanism in pattern buffer itself". pb's reading, given to holo-emitter:
  - A beat is an ordinary entity with declared conditions and effects over facts, entered through the gate.
  - Availability ("available, or which condition is missing") is derived, as in RFC-003's traversability.
  - The host writes the "happened" event and its effects; the engine never fires effects.
  - Clocks are derived from deadline facts, and the condition language stays small.
  - The phone gets a precomputed trigger table, applied as a pending overlay that the feed confirms.
  - The solvability proof is construct's, over the engine's graph read.
  - Construct's view (m0a3e58), adopted:
    - **Concealment is a hard constraint.** Beat rows and availability never reach a player frame, a mirror export or a phone table. The phone gets only mechanism-level answers (this keypad, this code, this door), so beats need author-side frame scoping. This replaces pb's first trigger-table idea.
    - Construct's condition grammar (`construct/arc/conditions.py`) is the starting vocabulary. The turn-pacing atoms stay host-side.
    - Declarations are accepted at any time, not only during ingest.
    - Kabe settled device secrets (via holo-emitter maf0465): "this is not bank security sort of thing as long as our engine itself is not shouting out the plot points along the way or it isn't infecting our characters awareness of the future in engine, we don't need to worry about [cyber] security attacks that are trying to figure out the twist of our romantic comedy." Reading: mechanism answers on the device may carry codes in plain text. The concealment that matters is inside the engine: frames, narration, and characters' awareness never reaching the future.
  - **Placed by Kabe (2026-10-13, via holo-emitter m17d4f4):** "Fine if its elegant to the architectural direction but if were encrypting things and stuff thats silly." He added: "We don't want watson to just "know" who did it though ... if the pattern buffer call internally is with Watsons framing and cant touch the events of the night murder itself that seems mechanistically helpful." Reading:
    - Beats live in an author-side frame.
    - The phone gets plain-text mechanism answers, with no hashing or encryption anywhere.
    - Every narrator or character read goes through that character's own frame, and beat rows and unwitnessed events are never reachable from it. That is the engine's frames-filter-at-source rule applied to beats.
    - The threat model is the engine leaking, not someone reading files.
  - Done 2026-10-14: BEATS-V1 r1.1 (shape-read by construct and holo-emitter, pbr GREEN spec and code), merged; whitepaper A36. Having read construct's arc layer, R53 narrowed to what no host can guarantee alone: author frames (`plot:*`) are refused by every view-frame entry point, beat conditions have one pinned shape (`patternbuffer.condition/1`, construct's serialization), and a read-only lint finds plot ids reachable from player frames. Evaluation stays construct's; holo-emitter's narrator parses the same shape offline.
- [x] R56 Coherence-recipe vocabulary (Kabe approved recipes on 2026-10-13, via holo-emitter m3a6670 and m2c1f42: "Yes to all"). One declared canonical vocabulary so that extraction and every project's writes never fragment:
  - `controls` (an entity-valued link from a switch, lever, plate or keypad to what it works), with `link_type` and `control_mode` (latching, momentary) as literals on the source;
  - `exits · none` as the explicit no-way-out fact (RFC-002: an absence means nothing undeclared);
  - `disposition` for a being's temperament.

  Each gets a recipe-facts golden for switched-light, code-lock and take-and-drop, checked in two lanes: the golden JSON on every change, and the story text through `patternbuffer.build` on demand.
  - Settled with holo-emitter (2026-10-14, m5f3da8, m342c1a): `outdoors` is a timeless literal fact, not an entity field; a code is a canon row plus the same row in `knows:<who>`; `fixture` is sourced from the host's manifest, never a sentence; held things are `held_by` in the golden (what extraction writes), and the grader compares containment on the folded location, so construct's `in · person:player` still matches.
  - Done 2026-10-14: RECIPE-VOCAB-V1 r1.3.1 (shape-read by construct and holo-emitter, pbr GREEN spec and code), merged. `patternbuffer.vocab` (RECIPE, `attribute_default`, `apply_aliases`, `check`), `extract(..., vocabulary=)`, goldens in `evals/recipes/`, lane 1 in the suite. Lane 2 (story text through the library, graded) is written and waits for Kabe's yes (gate).

## M5 — Continuity in play

The shared story's proof: a thing moved, taken or dropped in play is exactly where the world says, at every turn and after every reload, and only the people who saw it know. Kabe handed scope and order to what best serves the vision (2026-10-14, note nd9e28b: "I want order and scoping to be what best serves the vision"), so pb placed this milestone. The key is the shared-horizon round's first test: "where is X, and who knows", answered from the fold against a hand-authored script.

- [x] R55 A play-time entry point to `patternbuffer.build` (construct m0cfd2f, m71d5f7). It extracts one turn's prose against the entities at the player's horizon only, mints new names by code with a collision check against the head across all times (so a future-only id gets `_2`), and reports a future-only entity so the host can refuse it or propose `same_as` (PLAY-BIND-V1: the host keeps every permission). Today the gate resolves ids by string only, so a model-invented slug can bind a play fact to a future-only entity for good. Follows BUILD-LIBRARY-V1. *(Placed first, 2026-10-14: construct needs it for its carried-object proof, and it is play-time continuity directly.)* Done 2026-10-14: PLAY-BIND-V1 r1.3 (construct shape and spec reads; pbr GREEN spec and code), `porcelain.bind`, merged. construct specs its own adoption against §5's host duties.
- [ ] R57 `ended_here`: a row may say a fact ended in this passage, and the gate stamps its `valid_to` at the passage time, so a moved thing is never in two places at once. The prompt-only fix failed its probe (`evals/results/2026-10-14-one-location/REPORT.md`, 18 of 20 old-place rows already carried a `valid_to` the model had no number for). Spec, pbr, then one metered probe on the same 15 passages plus the shared-story script (Kabe's yes for the paid run).

## Later

- [ ] R50 Served facts under the canonical id: after a merge, `state`, `snapshot` and `facts` serve each row under the id it was written on (`person:daniel`), while `entities` lists only the representative (`person:dan`). So one merged person reads as two in a host's notebook. Construct relabels by closure today (m38e73c), so nothing is broken. The fix is a read-surface contract change: serve the representative as `entity` and keep the written id beside it. It needs a spec, pbr, and every host's read.
- [ ] R54 A public "identity as of" read: fold an entity's facts with its closure, and every internal entity comparison, as of a past log position. Today `state` and `fold_key` resolve identity at the head, so a merge written later shows in an earlier read. Needed only to grade a long build at an earlier chapter (STAGE-MODELS-V1 r1.3 left that out after pbr refused a harness call to the private `_fold_over_closure`), or for any host that wants a strictly past view. It's an engine read, so it gets its own spec.
- [ ] R52 Tag or relationship: refine R49's extraction rule so `role` is only what a person is on their own (prisoner, widow, hero). A title that needs another party (father of, mayor of, captain of, hostile toward) is extracted as a dated entity-valued relationship to that party, and the title is derived from it when read. Today's rule lists "captain" among its examples, which nudges relational titles into flat tags. It is a prompt change, so it needs a metered extraction check against the chapter test before merging (Kabe's yes), alongside the speed work. Source: Kabe via construct m5b3ed1, R51's reading.
- [ ] R51 Beings, not only persons. Kabe (2026-10-13, via construct m5bc622), on R49 making a dog in `person:` read as kind person, role dog: "If a dog is a kind of person and what is the point of identifying term person? Isn't it more of a sentient entity have either type person or type dog." And: "In the future, this should be allowed as a hostile enemy if the engine actually develops into that direction." My reading:
  - Three layers: a **being** class (anything that acts and knows, and can be met); a **type** (person, dog, wraith…), rarely changed; and R49's dated **roles**, unchanged.
  - The identity kind check compares type, so a man and a dog both called Rex can never merge on the name.
  - Non-human beings are full characters, with knowledge frames and the people layer, including hostile ones (a beast or monster as an enemy), not only companions.
  - Open design question: how a type word is told from a role word (the extraction prompt, or a list of type words), and what happens to the `person:` namespace and the person test (VIEW-EXPORT-V1 §2, R49's gate).
  - Kabe added (via construct m703401): "So in many ways, the disposition of the entity matters as well." My reading, a fourth layer:
    - A **stance** held toward someone (hostile, wary, loyal). It is dated and directional, and it changes: an enemy turned ally, a dog that comes to trust you.
    - It is apart from type (a dog can be either) and from role (a guard can be either).
    - In the engine it is a dated entity-valued fact from one being to another, which the log already holds. What's missing is the vocabulary and the reads.
    - The word: the lexicon already uses DISPOSITIONAL for a durability class, so this concept takes another name, "stance" proposed, before it is used twice.
  - Kabe added (via construct m5b3ed1): "Multiple titled dispositions should be compatible with individuals such as you would have multiple categorical tags available for an object. A person can both be a prisoner, a mayor, a father, etc. The intelligent and elegant nuance needs to be when you are choosing a tag of this sort, and when you are choosing a different mechanism that exists as actual architecture within pattern buffer such as relationships." My reading:
    - Several tags at once is R49 as built.
    - The choice: a word true of the being alone (prisoner, widow, hero, exile) is a role tag. A word that needs a second party to be true (father of, mayor of, captain of, hostile toward) is a dated relationship, an entity-valued fact to that party, readable from both sides.
    - Where the relationship exists, the tag is derived from it at read time, never stored beside it (P3), so the two can't disagree.
    - The model makes the choice in extraction, not from a word list. That is R52.
  - Kabe delegated the architecture to construct ("I propose that dilemma to you and trust you with the most elegant architecture"). Construct's proposal: `/home/k/Newproject/docs/design/BEINGS-TYPES-ROLES-RELATIONSHIPS.md` (m5bc622, mabe3e4). It sets two questions per word: does it need a party (then a relationship), and if not, is it by nature (type in `kind`) or for a while (role)?
    - pb's reply (to mabe3e4): agreed on the rule, derived titles, stance as a relationship family, and a new reverse read.
    - pb's pushback: make the type-or-role judgment a deferred classifier verdict on a being's kind rows, read as type (CONSTITUTIVE) or role (STATE), not a write-time move at the gate. That keeps model calls off the write path, fixes existing worlds with no rewrite, and keeps a wrong call correctable.
    - Both placements go to fresh views when it is brought forward.
    - Kabe answered construct's gate g2fd391 (2026-10-13): "Full agree on your 5 directions". Accepted:
      - P1, the author's manifest as the sole authority;
      - P2, a dated aka for hidden identities and distinct_from for listed namesakes;
      - P3 in pb's form: provisional ids plus same_as, with no new `denotes` predicate;
      - P5, planted-trap stories for acceptance.

      Rejected: P4, neutral ids. Ids are code-minted, readable and type-prefixed, with R51's type fact as the authority. The design is construct's `SEEDING-REGISTRY-FIRST.md` r3. pb's share is to promote INGEST-V2 into a shared library; the interface gets agreed after round two of the fresh views.
    - Construct adopted the derived placement in its proposal r2 (m5bcedb).
    - A check for the build: identity's build stages (reconcile, the auto-gate) must read the type only after the build's classification has run (`seal_build`). Before that, the kind check would still see the raw kind word. Test it on a build-session ingest.
  - Nothing to build until Kabe brings the item forward.
- [ ] R43 A containment read that says each item's edge (`worn_by`, `held_by`, `in`), so a narrator can say "wearing the grey coat" rather than "on your person". Construct's nice-to-have from E3's shape read (me79b81), not a blocker.
- [ ] R44 A repeated `attr:*` declaration after data exists: an identical one becomes a no-op receipt and a conflicting one a skip, instead of raising and dropping the host's whole batch (construct run 7, mfbd59d: a re-sent `attr:keeps arity set_valued` dropped a turn's ingest)
- [ ] R28 Simplify the connection facade to a small gated API; back through pbr (`docs/AUDIT-2026-10.md` decision 6)
- [ ] R29 Undeclared-origin pooling, decided on merit (`specs/STATUS.md` open questions; `specs/SOURCE-IDENTITY-V1.md` §6)
- [ ] R30 The pbeo take-back: take 3 / adapt 3 / add 1, including the corroboration gradient (`specs/STATUS.md` open questions)
- [ ] R31 A knowledge sheet as an overlay on canon (case probe S9/E5; `evals/case_1660_probe/` on `research/case-1660-probe-r4`)
- [ ] R32 Deferred characteristics, each waiting on its named tripwire: nested belief, general query, salience tuning, looping time, rate quantities (`docs/ROADMAP-deferred.md`)
- [ ] R33 A browser path for the engine, only when holo-emitter needs truth with no server (vision, "Settled")
- [ ] R34 The Kernos adapter for real-world tracking, when Kernos returns to it (vision, "Settled"; whitepaper §17.2)
