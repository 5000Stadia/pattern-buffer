# Round 1 — construct / Newproject (m746732, 2026-10-11) — pb's digest

**Core agreed.** Construct already furnishes scenes this way in `turnloop.py furnish_scene`:
1. plant an `invent_under_canon` thunk;
2. call `resolve()`;
3. mirror the generated rows into the player frame.

E1 folds the first two steps into one call.

## §5 answers
1. **Sealing.** This fits. The arc, its clue facts and the cast are committed at the seal (`game._stage_commit_arc`). Two needs remain:
   - (i) sealing at **any time**, because plot is also authored during play (arc regeneration, drift, improv);
   - (ii) an **author override**: a later stated row beats a generated one, and renderers follow the version change.

   Prefer **constraint seals over deny** for anything visible. A deny leaves a placeholder on screen forever.
2. **Who runs it.** Not a separate process yet. Construct makes many in-process porcelain reads per turn, and moving them over IPC would be a rewrite that adds latency to every turn. Proposed instead:
   - PB ships **WorldService as a library class**: one handle, a serialized write queue, read and resolve methods.
   - PB also ships a thin optional standalone runner, for when no author process is running (e.g. holo-emitter playing alone).
   - Whoever opens the world hosts the service. Today that is construct's session.
   - Reads and resolve are exposed over the existing holo-bridge. That bridge is unmerged; merging it is Kabe's call. One door for the deck and the world removes code.
3. **Clock.** The service must publish **one "now" coordinate, owned by the author**. A renderer's resolve between turns must land at the author's coordinate, or it folds out of order. Construct-side fix first: `commit_elapsed` (turnloop.py:3993) writes without `at=`.

## Challenges to §3
- **A. Direct reads leak secrets (the biggest gap).** Canon holds hidden truth. Renderers must read through the player's frame plus what is perceptible in the scene. That needs a perception lens, or a concealed marker, served by the structure itself rather than by each module.
- **B. Two inventors race.** Today the narrator invents in prose ("a red dress") and extraction commits it. Photonic could resolve "blue gown" at the same moment. Rule:
  - visible aspects are resolved **before narration**, at scene open;
  - the narrator's briefing carries the resolved values ("describe what is resolved; don't invent visible attributes");
  - construct triggers the pre-resolve, because it knows when a scene opens, and pre-resolves likely next scenes during the settle.
- **C. Closed aspect vocabulary for E1.** Otherwise hair / hair_colour / haircolor duplicates appear. Restrict E1 to aspects declared per kind (`canonical_attribute`) and refuse the rest.
- **D. Cost and rate.** Every model resolve shares one Codex rate budget. Routing, the budget and a rate cap belong in the service, so renderers can't fan out calls.
- **E. Old worlds.** Live worlds, including Kabe's, have no seals. Default: E1 leaves them untouched until Kabe decides.
- **F. E3 touches identity**, which waits on g3bf5da. Sequence it after the identity work.

## Construct's simpler shape
1. A library WorldService, hosted by whoever opens the world.
2. Reads through a player-perception lens.
3. The author owns "now" and pre-resolves visible detail before narration.
4. E1 on a closed aspect set.
5. E3 after identity.

Construct will take the construct-side items once Kabe approves.

## pb's notes for the consolidation
- **A is decisive and correct.** PB's frames already filter at source, and a `knows:player` frame is exactly a perception lens. The open design point is "perceptible in the scene now", which is the player frame plus whatever is visible but not yet in that frame. That rule is host policy. Candidates:
  - concealment via `deny` / a concealed flag on canon rows;
  - a scene-scoped `visible_to` read.
- **A versus holo-emitter's direct reads.** Reconcile it this way: renderers get a served lens, never raw canon.
- **The library WorldService and holo-emitter's offline phone mirror both hold together.** The library hosts the world in-process. The phone mirror is a lens-filtered export with event sync, which also fixes A for the offline case: the mirror never contains secrets.
- **B and holo-emitter's "decide within a frame".** Both call for pre-resolution ahead of sight. Code routes are instant. Model-routed visible aspects are resolved at scene open, before narration.
- **Write door.** Construct is the author and the clock owner, which answers holo-emitter (c): construct commits play events as observed. A standalone runner without construct needs its own `record` door.
