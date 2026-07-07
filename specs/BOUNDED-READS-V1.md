# BOUNDED-READS-V1 — `entities()` + `facts()` (the sub-porcelain bypass closers) + lean `person.in`

**Status:** SHIPPED — Cx deliberation (splits + frame-required-bound + raw-rows
AGREED; 3 fixes adopted: `entities` requires `frame` — prefix-only enumeration
leaks cross-frame existence; `include_meta=False` in the `facts` signature; lean
`person.in` path check beyond the prompt pin) → impl reviewed to GREEN (1 RED:
runtime falsy-frame guards on both verbs — `visible(frame=None)` would have been
an unbounded cross-frame scan). Trigger (Kernos 077, blessed): Construct is
forced BELOW the porcelain — `world.buffer.visible(entity_prefix=...)` in the live
turn loop — because a legitimate recurring need isn't expressible on the surface.
HD 088 inventoried every touch and asked the spec to cover the **frame-scan case**;
one shape retires them all. Plus the 077 Ask-2 ruling: lean-extract must carry
`person.in` (core state, not atmosphere).

## The bypass inventory (HD 088 — what must become expressible)
- place rosters: `buffer.visible(entity_prefix="place:")` (turnloop.py:1444, 2430)
- journey accept-markers: `buffer.visible(entity="session:journey_accept", …)` (2208)
- Remembrancer sheet + knows-frame digests + SESSION/PLOT receipt scans:
  `buffer.visible(frame="knows:<id>")` / frame scans (remembrancer.py:50,77,
  game.py:1724, 2338-2540)

## Win 1 — `entities(frame, prefix=None, as_of=None) -> list[str]`
The roster verb: the entities carried by ONE frame's rows, identity-resolved,
deduped, sorted.
- **`frame` is REQUIRED** (Cx: prefix-only enumeration would leak cross-frame
  entity EXISTENCE — every read fixes perspective, same rule as `facts`).
  Construct's place roster is `entities("canon", prefix="place:")` — natural.
- `prefix` narrows by id namespace; `as_of` = valid-time gate (composes with
  the as-of play-horizon).
- Excludes meta rows (`a:*`) and attribute declarations (`attr:*`).
- Zero writes, zero model calls, no fold — an index read.

## Win 2 — `facts(frame, entity=None, attribute=None, prefix=None, as_of=None, include_meta=False) -> list[dict]`
The frame-scan read: the visible rows OF one frame, as standard fact payloads.
- **`frame` is REQUIRED** — the bounding scope (this is what makes it a bounded
  scan, not a dump). Optional narrowing: `entity` (one id), `attribute`,
  `prefix` (entity-id namespace). `as_of` valid-time gate.
- Returns the porcelain `Fact` dict shape (provenance/source-chain included),
  `encode_out`-wrapped (decimal contract). Raw log reads, NOT folds — the host
  wanting folded truth uses `state`/`snapshot`; `facts()` is the audited scan
  (receipt trails, knowledge digests, marker rows), which is exactly what the
  bypass call sites do today with `buffer.visible`.
- **Frame absence discipline unchanged:** the verb serves ONE named frame the
  host asked for — the same entitlement surface as `snapshot(frame=)`; nothing
  cross-frame, no inheritance.
- Meta rows (Cx-settled): an exact `entity="a:<n>"` target is ALWAYS served
  (receipt-chain scans); frame/prefix-wide listings exclude `a:*`/`attr:*`
  unless `include_meta=True` (in the signature).

## Win 3 — lean-extract carries `person.in` (the 077 Ask-2 ruling)
Ruling: **person/object location is the location spine — core state, never
lean-trimmable atmosphere.** A narrated departure that doesn't reach canon makes
presence LIE (canon holds departed NPCs in the room) — a correctness failure.
- Add to the LEAN rules block (full already carries it implicitly via the SPACE
  rule): *"ALWAYS extract location changes — X moves/leaves/arrives ⇒ a new
  `in` row for X; presence and departure are core state, never atmosphere."*
- **Path check beyond the prompt pin (Cx):** an end-to-end test drives
  `ingest(extract="lean")` with a scripted model emitting a departure `in`
  delta and asserts canon presence updates — pins the lean PATH engine-side;
  live model quality remains eval-guarded host-side (the 082 discipline).
- Concur with Kernos: the permanent host seam is the NARRATION (post-render
  extract), not classify (player-intent misses narrator-authored moves) — noted
  for Construct; no engine change beyond the prompt line.

## Non-goals
- No general query language (parked over-complication). No cross-frame union
  scan (`frames=[...]` waits for a proven need — multi-frame reads exist on
  `frame_diff`/`confidence` where the semantics are defined). No pagination
  (worlds are SQLite-local; the frame bound is the size control).

## Tests
- `entities(prefix="place:")` lists places only, resolved + sorted; requires a
  bound (no-arg raises); `frame="knows:x"` lists that frame's entities;
  `as_of` gates a later-valid entity out; `attr:*`/`a:*` excluded.
- `facts("knows:x")` returns that frame's rows as Fact dicts; `entity=`,
  `attribute=`, `prefix=` narrow; canon rows absent from a knows: scan;
  `as_of` gates; decimal values carry the tag (json.dumps-able).
- Lean rules block contains the location-spine line (prompt pin).
- Full suite green; defaults unchanged.
