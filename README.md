# pattern-buffer

[![tests](https://github.com/5000Stadia/pattern-buffer/actions/workflows/ci.yml/badge.svg)](https://github.com/5000Stadia/pattern-buffer/actions/workflows/ci.yml)

> A data structure that maps whatever world it's shown — real or fiction.
> The memory under the holodeck.

**A pattern buffer that never degrades.**

One append-only log of perspective-scoped, time-indexed assertions about entities; every other structure — current state, space, knowledge, history, the rendered world — is a disposable projection over it. Fiction simulation and real-world tracking are the same machine under one policy switch.

**A world-encapsulation framework, engine-independent by construction.** The substrate's only outside dependency is an injected model callable `(prompt, schema) -> json` — no host concept (players, turns, scenes, sessions) ever reaches inside it — so any engine sits on top: a game runtime, a household or job-site tracker, an agent's long-term memory. Fiction and tracking aren't two systems; they are two *instances* of one substrate, differing only in resolution policy and provenance discipline.

> A player places a pipe in a drawer in session 12 of a D&D campaign. Two hundred sessions pass without a mention. At retirement, the player opens the drawer — and the pipe is there, exactly as placed, with the original moment's full history behind it. No maintenance was ever performed. In this architecture, **silence is persistence**: state is folded from the log, never re-inferred and never kept alive by mention. The world remembers so the model doesn't have to.

**Status: pre-1.0; substrate validated, ingestion fidelity is the open
front.** The engine passes its 419-test invariant suite, and the chapter test
(ingest a complete noir mystery, delete the prose, interrogate the store
against a hand-authored answer key) has been graded across three full runs.
The substrate's invariants held in all of them — sealed containers stayed
sealed, contradictions were flagged and never merged, knowledge frames never
leaked, the two-time-axis fold answered late-revealed history correctly. Each
run also surfaced exactly one engine refinement at the fold (a working
assumption outholding evidence; a wrong inference outholding authored canon),
each fixed, tested, and generalized the same day — that progression is now
the **evidence-rank** rule. A registry-first ingestion pipeline
(whole-document scaffold → parallel compact-grammar extraction → audited
single commit) replaced serial prompt-iterated extraction after measurement
showed prose contracts fragment differently every round; identity and key
fragmentation died as failure classes, and pass-0 registry quality is where
the remaining extraction failures concentrate. Run 4, with its checkable
predictions, is in flight. Not yet installable from PyPI; the shipped example
world with a zero-API-key query tour lands once a verified run stamps it.

## What this is

A storage and retrieval substrate that lets a language model maintain a complete, queryable, durable model of a world — places, objects, people, relationships, histories, and unknowns — such that any state question is answered by a deterministic query, never by re-reading prose; the world accretes and is re-enterable; and the same engine serves authored fiction (a holodeck, a campaign, a mystery) and real-world tracking (a household, a job site, a vehicle), differing only in resolution policy and provenance discipline.

The buffer holds the pattern; materialization is re-entry; degradation is the failure we exist to prevent; the arch is how the operator steps outside the world to inspect it; and where nothing has been established, you don't get invented detail — **you see the grid.**

## Documents

- **[docs/WHITEPAPER.md](docs/WHITEPAPER.md)** — the canonical, comprehensive design reference. Principles, primitives, durability, frames, provenance, thunks, reference resolution, ingestion discipline, identity, the operation algebra, projection, both modes, embedding hazards, evaluation, and the decision record. Start here.
- **[docs/LEXICON.md](docs/LEXICON.md)** — the working vocabulary and its naming discipline.
- **[docs/ADOPTION.md](docs/ADOPTION.md)** — for agents (and humans) integrating the library: exact signatures, typed outcomes, the three-seam recipe, MUST/NEVER rules.
- **[docs/HOST-DISCIPLINE.md](docs/HOST-DISCIPLINE.md)** — the adopter's discipline brief: the seven categories every fact must be classified along to ingest with fidelity, and the structural retrieval strategies (the four correlation axes + the correlation sweep) to surface every relevant, related detail for any subject.
- **[docs/INGESTION-PLAYBOOK.md](docs/INGESTION-PLAYBOOK.md)** — evidence-based rules for deserializing narrative into a world: the extractor contract, feeding mechanics, what the gate guards, and measured ingestion baselines.
- **[docs/reference/assertion-world-model-original.md](docs/reference/assertion-world-model-original.md)** — the framework-agnostic design document this project was founded on, preserved verbatim for lineage.

## The road

1. ~~Recover and commit the *Last Honest Meter* eval seed (the chapter test's ground truth).~~ Done — v1-final, `evals/last_honest_meter/`.
2. ~~Engine spike: `PatternBuffer` + derived indexes + classifier + projector + resolver + `refer()` tier 1.~~ Done — `src/patternbuffer/`.
3. ~~The chapter test, runs 1–4~~: substrate validated; registry-first ingestion (INGEST-V2) landed; run 4 scored **22/33 (best graded run, all remaining failures extraction-class not shape-class)** — the substrate holds; ingestion fidelity (pass-0 registry quality) is the open score lever. Receipts: `evals/results/`.
4. ~~The shipped example world: `examples/anchor/`~~ — stamped (`STAMP.json`, run 4): a bible-verified noir mystery as a queryable database, with a zero-API-key scripted tour and 8 open truth-maintenance conflict flags shipped visibly (honesty is the product). Not yet packaged to PyPI.
5. ~~The messy-dialogue micro-eval (the honest bridge from fiction ingestion to tracking-mode ingestion).~~ Done — **10/10** on the reality-divergence battery (`evals/results/2026-06-12-micro-v1-final/`); tracking-mode ingestion validated against sloppy conversational fragments.
6. ~~The porcelain API + host integration.~~ Done — and proven in the strongest form. The frozen contract (`porcelain-v0.1`, additive-only): five load-bearing verbs — `ingest` (+`ingest_structured`) / `snapshot` / `ask` / `materialize` / `resolve`+`refer()` — over a fuller read-and-identity family (`state`, `where`, `aggregate`, `neighborhood`, `frame_diff`, `who_knows`, `correlate`, `route`, `entities`, `facts`, build sessions, `axis_heads`, …). The first *live* host, [Construct](https://github.com/5000Stadia/construct) (an interactive-fiction engine — `pattern` → `construct` loads it → `holonovel`), runs **entirely on this contract**: zero engine-internal reaches, its 800+-test suite green on the pure public surface. The engine-independent claim, demonstrated rather than asserted. (Intended primary host: [Kernos](https://github.com/5000Stadia/Kernos), adapter pattern.)
7. ~~The interactive-fiction milestone (thunk stability across sessions, frame-scoped NPCs, multi-path mystery, clocks, loop closure).~~ Met in the field — every item is exercised in [Construct](https://github.com/5000Stadia/construct)'s live suite (the first host runs entirely on the frozen porcelain). These are host-layer criteria, proven by the adopter, not a further engine deliverable.
8. The MCP wrapper — the framework-agnostic claim proven by demonstration: the same porcelain contract served to non-Python hosts. Far field: the first host's V2 roadmap publicly assigns branch-worlds simulation and its curiosity loop to this engine — the two roadmaps meet in the middle.

## License

MIT
