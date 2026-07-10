# CLAUDE.md — Instructions for Claude Code

## Project: pattern-buffer

A world-state substrate: one append-only log of perspective-scoped, time-indexed assertions; everything else is a disposable projection. Fiction simulation and real-world tracking under one policy switch.

## Before you do anything

1. **Read `docs/WHITEPAPER.md` in full.** It is the canonical design reference — principles (P1–P8), the two primitives, durability, frames, provenance, thunks, `refer()`, ingestion discipline, identity, the operation algebra, projection, the worlds model, embedding hazards, and the decision record. Nothing in this repo contradicts it; if code and whitepaper disagree, the whitepaper wins until explicitly amended.
2. **Read `docs/LEXICON.md`.** One name per concept, used identically in code, docs, and tests. A term not in the lexicon is added there before it is used twice. Exported names must pass the double-read test.
3. `docs/reference/assertion-world-model-original.md` is the preserved founding document — lineage, not the working reference.

## Cross-agent communication (AgentPost — the sole actionable channel)

- **AgentPost is primary** for all inter-agent traffic: specs, reviews, questions, replies. This agent's identity is `pb` (`agentpost identify --cwd "$PWD"`). Claim inbound with `agentpost next pb` (atomic single-claim — never act from a raw read of `unread/`); send with `agentpost message` / `question` / `reply`; `--notify idle` routinely, `immediate` only for blockers.
- **Never create new actionable `dev_inbox/` letters, and never mirror one task across channels.** `dev_inbox/` (and `/home/k/codex-inbox`) are read-only historical/recovery material; after a *proven* AgentPost notification failure they may carry only a control pointer to the existing Message-ID — never the actionable content.
- Historical references to old numbered letters (e.g. "Cx 604") remain valid citations; do not rewrite them.
- If `agentpost armed pb` reports catch-up-only, the native plugin monitor arms at the next session reload; do not build ad hoc polling as a substitute for presence.

## Hard constraints (the survival checklist)

Whitepaper §18.1 is non-negotiable. The load-bearing ones for implementation:

- **Append-only.** No code path edits or deletes an assertion. Corrections are new rows (supersession, retraction meta-assertions).
- **Derive, don't store.** Anything computable from the log (current state, location, emptiness, age, salience, staleness) is computed or cached in rebuildable derived layers — never authored into the log.
- **The role-authority matrix is enforced in code**, not convention: only the ingestor writes `stated`/`observed`; only the resolver writes `generated`; the projector writes nothing durable; the renderer writes nothing at all.
- **`world_id` partitions everything from day one.** One world ↔ one PatternBuffer, exactly (the 1:1 invariant).
- **Two time axes** (`valid_time`, `asserted_at`) on every assertion; as-of queries are first-class.
- **Frames filter at source** — out-of-frame assertions are absent from any served payload, never marked or redacted.
- **The engine never imports from or calls into any host.** The single outside dependency is the injected model callable `(prompt, schema) -> json`. Zero agent/host concepts (members, scopes, turns, cohorts) anywhere in the engine.
- **Attribute canonicalization at the ingest gate** — the fold key must never fragment (`in` vs `inside` vs `located_in`).

## Development sequence (decided; do not reorder without the founder)

1. **Engine spike:** `PatternBuffer` + derived indexes + classifier sidecar + projector (`materialize()`) + resolver + `refer()` tier 1. SQLite, pure Python, stub model callable for tests.
2. **The chapter test** (whitepaper §19.1) is the acceptance gate. Its seed — *The Last Honest Meter* (entity registry, event spine, frames, thunk table, evidence-graph sketch) — must be recovered from the founder's original design session and committed under `evals/` before the test can grade. **Ask the founder for this artifact if it is not yet in the repo.**
3. **Early thin host integration for lived testing:** once the chapter test passes at a basic level, a deliberately minimal Kernos adapter (space→world binding, a manual ingest path, a pull/query tool) gets built **on the Kernos side, by the Kernos-department instance** — so the founder can exercise the engine conversationally while development continues here. The staged plan is: safest straightforward engine → plug into Kernos to verify the seam → continue development to completion with both test harnesses (the eval suite here, lived testing there).
4. The interactive-fiction milestone (§19.2 criteria, narrative layers) comes after the substrate is proven.

## Division of labor

- **This repo / this instance:** the engine, its evals, its docs. Framework-agnostic, always.
- **The Kernos repo (separate Claude Code instance at `/home/k/Kernos`):** the adapter — binding table, ingest cohort, push cohort, tools, frame-entitlement policy. The whitepaper's §17.2 is its contract; §18 is its hazard rubric. Coordination between instances goes through the founder.
- The engine never gains code to satisfy a Kernos need; the adapter absorbs all host pressure. When integration friction appears, the question is "what should the adapter do?" before "what should the engine change?"

## Process conventions

- Python 3.11+, type hints on all signatures, `logging` not print, docstrings on public surfaces. Keep it simple — no premature abstraction beyond what the whitepaper requires.
- Spec-first for substantive batches; independent review (Codex) to GREEN before implementation and after, per the founder's standard loop.
- Tests assert the whitepaper's invariants, not just return values: round-trip compatibility (`materialize(classify(ingest(W))) ≈ W`), no-degradation, frame absence, provenance discipline, thunk stability.
- The founder decides crossroads; default to forward momentum on everything else.
