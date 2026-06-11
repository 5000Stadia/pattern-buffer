# pattern-buffer

**A pattern buffer that never degrades.**

One append-only log of perspective-scoped, time-indexed assertions about entities; every other structure — current state, space, knowledge, history, the rendered world — is a disposable projection over it. Fiction simulation and real-world tracking are the same machine under one policy switch.

> A player places a pipe in a drawer in session 12 of a D&D campaign. Two hundred sessions pass without a mention. At retirement, the player opens the drawer — and the pipe is there, exactly as placed, with the original moment's full history behind it. No maintenance was ever performed. In this architecture, **silence is persistence**: state is folded from the log, never re-inferred and never kept alive by mention. The world remembers so the model doesn't have to.

**Status: design phase.** The founding artifacts are complete; implementation begins with the engine spike and its acceptance gate (the chapter test). Nothing is installable yet.

## What this is

A storage and retrieval substrate that lets a language model maintain a complete, queryable, durable model of a world — places, objects, people, relationships, histories, and unknowns — such that any state question is answered by a deterministic query, never by re-reading prose; the world accretes and is re-enterable; and the same engine serves authored fiction (a holodeck, a campaign, a mystery) and real-world tracking (a household, a job site, a vehicle), differing only in resolution policy and provenance discipline.

The buffer holds the pattern; materialization is re-entry; degradation is the failure we exist to prevent; the arch is how the operator steps outside the world to inspect it; and where nothing has been established, you don't get invented detail — **you see the grid.**

## Documents

- **[docs/WHITEPAPER.md](docs/WHITEPAPER.md)** — the canonical, comprehensive design reference. Principles, primitives, durability, frames, provenance, thunks, reference resolution, ingestion discipline, identity, the operation algebra, projection, both modes, embedding hazards, evaluation, and the decision record. Start here.
- **[docs/LEXICON.md](docs/LEXICON.md)** — the working vocabulary and its naming discipline.
- **[docs/reference/assertion-world-model-original.md](docs/reference/assertion-world-model-original.md)** — the framework-agnostic design document this project was founded on, preserved verbatim for lineage.

## The road

1. Recover and commit the *Last Honest Meter* eval seed (the chapter test's ground truth).
2. Engine spike: `PatternBuffer` + derived indexes + classifier + projector + resolver + `refer()` tier 1.
3. **The chapter test:** ingest one complete short fiction, delete the prose, interrogate a cold instance against the printed ground truth. The score gates everything after it.
4. The messy-dialogue micro-eval (the honest bridge from fiction ingestion to tracking-mode ingestion).
5. Host integration (adapter pattern — first host: [Kernos](https://github.com/5000Stadia/Kernos)) and the interactive-fiction milestone.

## License

MIT
