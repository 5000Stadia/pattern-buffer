# pattern-buffer

[![tests](https://github.com/5000Stadia/pattern-buffer/actions/workflows/ci.yml/badge.svg)](https://github.com/5000Stadia/pattern-buffer/actions/workflows/ci.yml)

> A data structure that maps whatever world it's shown — real or fiction.
> The memory under the holodeck.

**A pattern buffer that never degrades.**

One append-only log of perspective-scoped, time-indexed assertions about entities; every other structure — current state, space, knowledge, history, the rendered world — is a disposable projection over it. Fiction simulation and real-world tracking are the same machine under one policy switch.

**A world-encapsulation framework, engine-independent by construction.** The substrate's only outside dependency is an injected model callable `(prompt, schema) -> json` — no host concept (players, turns, scenes, sessions) ever reaches inside it — so any engine sits on top: a game runtime, a household or job-site tracker, an agent's long-term memory. Fiction and tracking aren't two systems; they are two *instances* of one substrate, differing only in resolution policy and provenance discipline.

> A player places a pipe in a drawer in session 12 of a D&D campaign. Two hundred sessions pass without a mention. At retirement, the player opens the drawer — and the pipe is there, exactly as placed, with the original moment's full history behind it. No maintenance was ever performed. In this architecture, **silence is persistence**: state is folded from the log, never re-inferred and never kept alive by mention. The world remembers so the model doesn't have to.

**Status: v0.2.0.** The engine has zero runtime dependencies and a frozen,
additive-only porcelain contract. Its invariant suite has about 2,588 tests.
The substrate works for both fiction and tracking: time-indexed facts, frames,
identity, containment, provenance, conflicts, and deterministic reads stay in
the log rather than being re-inferred from prose.

The registry-first build library turns a book into a world through a documented
pipeline. On 2026-10-14, the six-chapter practice book (about 11.5k words)
built in 225 seconds for $2.58, with zero wrong merges and zero leaks. Object
movement remains the weak area; it is an open fidelity problem, not hidden by
the score. See `evals/results/2026-10-14-speed-compare/REPORT.md`.

## Install

```bash
pip install pbuffer          # the engine (zero dependencies) — import patternbuffer
pip install pbuffer[mcp]     # + the MCP server: patternbuffer-mcp --world w.world --world-id w:id
```

*(The PyPI distribution is `pbuffer` — the exact name `patternbuffer` was taken
by an unrelated project; the import is `patternbuffer` throughout.)*

## Try it

The shipped example world — a complete noir mystery ingested into the
substrate, prose deleted — answers structured questions deterministically.
No model, no API key, milliseconds:

```bash
git clone https://github.com/5000Stadia/pattern-buffer && cd pattern-buffer
python examples/anchor/build_anchor.py   # rebuild anchor.world from the committed dump
python examples/anchor/tour.py           # the scripted interrogation tour
```

The tour walks the two-clock question (where was the memory core *as of*
each chapter), knowledge frames (what one character can see), sealed
containers, and the 8 open truth-maintenance conflict flags the world
ships with visibly.

## What this is

A storage and retrieval substrate that lets a language model maintain a complete, queryable, durable model of a world — places, objects, people, relationships, histories, and unknowns — such that any state question is answered by a deterministic query, never by re-reading prose; the world accretes and is re-enterable; and the same engine serves authored fiction (a holodeck, a campaign, a mystery) and real-world tracking (a household, a job site, a vehicle), differing only in resolution policy and provenance discipline.

The frozen porcelain API is additive-only. The bundled MCP server exposes 45
deterministic verbs — 31 reads and 14 mutations — over one world, and works
with any MCP client. [Construct](https://github.com/5000Stadia/construct)
runs entirely on this public contract and validates it with its suite.

The buffer holds the pattern; materialization is re-entry; degradation is the failure we exist to prevent; the arch is how the operator steps outside the world to inspect it; and where nothing has been established, you don't get invented detail — **you see the grid.**

## Documents

- **[docs/WHITEPAPER.md](docs/WHITEPAPER.md)** — the canonical, comprehensive design reference. Principles, primitives, durability, frames, provenance, thunks, reference resolution, ingestion discipline, identity, the operation algebra, projection, both modes, embedding hazards, evaluation, and the decision record. Start here.
- **[docs/LEXICON.md](docs/LEXICON.md)** — the working vocabulary and its naming discipline.
- **[docs/ADOPTION.md](docs/ADOPTION.md)** — for agents (and humans) integrating the library: exact signatures, typed outcomes, the three-seam recipe, MUST/NEVER rules.
- **[docs/HOST-DISCIPLINE.md](docs/HOST-DISCIPLINE.md)** — the adopter's discipline brief: the seven categories every fact must be classified along to ingest with fidelity, and the structural retrieval strategies (the four correlation axes + the correlation sweep) to surface every relevant, related detail for any subject.
- **[docs/INGESTION-PLAYBOOK.md](docs/INGESTION-PLAYBOOK.md)** — evidence-based rules for deserializing narrative into a world: the extractor contract, feeding mechanics, what the gate guards, and measured ingestion baselines.
- **[ROADMAP.md](ROADMAP.md)** — delivered milestones, open work, and the evidence behind each step.
- **[docs/reference/assertion-world-model-original.md](docs/reference/assertion-world-model-original.md)** — the framework-agnostic design document this project was founded on, preserved verbatim for lineage.

*A note on citations.* Specs and the whitepaper's decision record cite an
internal review trail: "the founder" is the project owner; "letter NNN",
"Cx NNN" and "AgentPost" refer to correspondence with independent review
agents; "pbr" is the dedicated reviewer and "c" the first live host
(Construct). The correspondence is private, but every decision it gates is
restated in the whitepaper and specs.

## The road

1. **M1 — Substrate.** Done. The append-only assertion log, derived indexes,
   deterministic fold, frames, provenance, and policy-separated fiction and
   tracking worlds form the durable core. Measured along the way: the chapter
   test (a whole noir mystery ingested, the prose deleted, the store graded
   against a hand-authored key) reached 22/33 on run 4, with every remaining
   failure in extraction rather than the substrate; the messy-dialogue battery
   scored 10/10; and tracking mode's wall-time trust decay shipped
   (TRACKING-MODE-V1). The graded example world is in `examples/anchor/`.
2. **M2 — Self-audit (October 2026).** Done. The engine's read, fold,
   classification, identity, and ingestion boundaries were audited and tightened
   against replayable evidence.
3. **M3 — Book in, world out.** Done. `patternbuffer.build` is the
   registry-first build library: it plans a book, extracts compact assertions,
   commits one world, and leaves receipts that can be graded.
4. **M4 — One world for every module.** Done. `WorldService` provides one
   serialized world handle; `view/1` exports a player's view plus a change feed
   for offline mirrors, with a small JavaScript `apply()` module. The public
   surface also includes author-side `record`, resolve requests and
   resolve-unmarked, closure and facts reads, `merge_gate`, tracked beats with
   author frames, and `patternbuffer.vocab` with recipe golden facts.
5. **Open work.** Whole-book fidelity and object movement need more measured
   improvement. The engine will keep reporting those failures rather than
   smoothing them over.

## License

MIT
