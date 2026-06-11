# pattern-buffer

> A data structure that maps whatever world it's shown — real or fiction.
> The memory under the holodeck.

**A pattern buffer that never degrades.**

One append-only log of perspective-scoped, time-indexed assertions about entities; every other structure — current state, space, knowledge, history, the rendered world — is a disposable projection over it. Fiction simulation and real-world tracking are the same machine under one policy switch.

> A player places a pipe in a drawer in session 12 of a D&D campaign. Two hundred sessions pass without a mention. At retirement, the player opens the drawer — and the pipe is there, exactly as placed, with the original moment's full history behind it. No maintenance was ever performed. In this architecture, **silence is persistence**: state is folded from the log, never re-inferred and never kept alive by mention. The world remembers so the model doesn't have to.

**Status: pre-1.0 engine spike, built and invariant-tested.** The engine — append-only buffer with enforced role authority, durability classification, spatial indexes, knowledge frames, thunks + resolver, `refer()` tier 1, the ingest gate, truth maintenance, deterministic dump/restore — passes its 56-test invariant suite. The chapter test (ingest a complete noir mystery, delete the prose, interrogate the store against a hand-authored answer key) is the acceptance gate now being graded. Not yet installable from PyPI; a shipped example world with a zero-API-key query tour lands after the ingestion pipeline is verified.

## What this is

A storage and retrieval substrate that lets a language model maintain a complete, queryable, durable model of a world — places, objects, people, relationships, histories, and unknowns — such that any state question is answered by a deterministic query, never by re-reading prose; the world accretes and is re-enterable; and the same engine serves authored fiction (a holodeck, a campaign, a mystery) and real-world tracking (a household, a job site, a vehicle), differing only in resolution policy and provenance discipline.

The buffer holds the pattern; materialization is re-entry; degradation is the failure we exist to prevent; the arch is how the operator steps outside the world to inspect it; and where nothing has been established, you don't get invented detail — **you see the grid.**

## Documents

- **[docs/WHITEPAPER.md](docs/WHITEPAPER.md)** — the canonical, comprehensive design reference. Principles, primitives, durability, frames, provenance, thunks, reference resolution, ingestion discipline, identity, the operation algebra, projection, both modes, embedding hazards, evaluation, and the decision record. Start here.
- **[docs/LEXICON.md](docs/LEXICON.md)** — the working vocabulary and its naming discipline.
- **[docs/ADOPTION.md](docs/ADOPTION.md)** — for agents (and humans) integrating the library: exact signatures, typed outcomes, the three-seam recipe, MUST/NEVER rules.
- **[docs/reference/assertion-world-model-original.md](docs/reference/assertion-world-model-original.md)** — the framework-agnostic design document this project was founded on, preserved verbatim for lineage.

## The road

1. ~~Recover and commit the *Last Honest Meter* eval seed (the chapter test's ground truth).~~ Done — v1-final, `evals/last_honest_meter/`.
2. ~~Engine spike: `PatternBuffer` + derived indexes + classifier + projector + resolver + `refer()` tier 1.~~ Done — `src/patternbuffer/`.
3. **The chapter test** (in progress): ingest one complete short fiction, delete the prose, interrogate a cold instance against the printed ground truth. The score gates everything after it.
4. The shipped example world: `examples/anchor/` — a bible-verified noir mystery as a queryable database, with a zero-API-key scripted tour ("where was the memory core during the assembly?").
5. The messy-dialogue micro-eval (the honest bridge from fiction ingestion to tracking-mode ingestion).
6. Host integration (adapter pattern — first host: [Kernos](https://github.com/5000Stadia/Kernos)) and the interactive-fiction milestone.

## License

MIT
