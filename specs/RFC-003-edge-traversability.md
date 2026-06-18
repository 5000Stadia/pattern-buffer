# RFC-003 — Edge traversability as derived world detail

**Status:** DRAFT for deliberation → Codex + Conduit review against the five
gates → founder ratification before any implementation. Founder-directed
(vacuum → Jarvis → real-world thread), and re-anchored by the founder's key move:
**a blocked passage is not a labelled edge — it is a passage whose obstruction is
ordinary, durable, inspectable world detail.**

## §1 Thesis — traversability is derived, the "reason" is facts

Do **not** model `blocked` as a stored edge status, and do **not** invent a
reason vocabulary. Model the **world**: the door, its condition, the guard. Then
**derive** "can I pass A→B, and if not, why?" from those present facts.

- *rusted shut* → the **door** (an entity) carries durable states `condition:
  rusted`, `state: shut`. Inspect the door later (`neighborhood`/`materialize`)
  and it *is* a rusted, shut door — the detail stuck because it is a fact, not an
  annotation.
- *guarded* → a **guard** (a real entity, detailed: identity, location) related
  to the door (`guards` / `guarded_by`). The block is the guard's *presence in
  the world*, painted normally.

The four states are **derived classifications**, never stored:
- **clear** = a bare `connects_to` (no portal entity), OR a portal with an
  *established* passable state.
- **blocked** = a portal with an obstructing state or entity present.
- **removed** = the passage/portal's lateral edge **ceased in time** (`valid_to`)
  — strictly temporal (Cx gate 3), the substrate already shipped (as-of `path()`
  #32). A host `state: destroyed` is *evidence* that drives the host to end the
  edge (assert `valid_to`); the engine never hardcodes `destroyed ⇒ removed`.
- **obscured** = a portal whose traversability state is **unestablished**, **when
  a host-declared traversal policy establishes that the portal's state gates
  passage** — so its absence is a *meaningful* gap (RFC-002: absence is relational
  to a *declared* expectation). Under such a policy a stateless portal reads
  `obscured`, **never** a silent `clear` (a **false-clear** — a sealed mystery-way
  read as passable — is the worst failure; this is what makes A3 *fail safe*).
  **Without a declared policy the engine does not guess** — a stateless portal is
  `clear` (no expectation of a gating state). So mystery-safety is **opt-in via
  the declaration**: a host that cares declares the policy and gets `obscured`; a
  simple world declares nothing and stays `clear`. This reconciles C-019 (no
  false-clear) with Cx (no engine guessing from bare absence).

This is the round-robin precedent taken all the way: *the engine surfaces
structure; the host supplies meaning.* The obstructing facts ARE the meaning,
authored through the gate; the engine derives traversability and **never stores a
block, never parses a host reason string.**

## §2 Passages can be mediated by an entity (a door)

A bare `connects_to` edge has nowhere to carry obstruction. So a passage MAY be
mediated by a **portal entity** (door, gate, hatch) that:
- sits on the lateral path between two places (e.g. `room_a · connects_to · door`,
  `door · connects_to · room_b`, or a declared `portal_between` relation);
- carries its own **states** (`open`/`shut`/`locked`/`rusted`/`destroyed`) — the
  same fold machinery as any entity, so the *current* state is derived and the
  history sticks;
- carries **obstruction relations** (`guarded_by · guard`, `blocked_by · rubble`)
  whose objects are first-class, detailed entities.

A passage with no portal entity is just `connects_to` (always clear unless
`valid_to`). The portal is opt-in detail, added when the world has a door worth
describing — additive, no new requirement on simple worlds.

## §3 Who decides passability? (resolved: Cx + Conduit)

The engine must not hardcode "shut means impassable" (host vocabulary).
**Resolved: A for `route()`, B always surfaced, `path()` unchanged.**

- **A — host-declared *traversal policy*, a scoped sidecar (NOT a generic
  `AttributeSemantics` axis — Cx gate 2).** The host declares which portal
  states/relations gate passage, **scoped to a portal role/kind/relation** so a
  *shut cabinet*, *shut eyelid*, and *shut door* never accidentally share
  traversal semantics. `route()` reads this policy over portal facts and derives
  status. Behavior is host-declared data; the engine learns no vocabulary.
- **B — raw facts always surfaced.** `route()` returns each portal's current
  facts regardless, so the host owns the words AND the **navigation policy**
  (force the rusted door? hard no? detour? — Conduit's call, never the engine's).
- **Default with no declaration: the engine does not guess.** A portal gates
  passage only when `removed` (temporal); `blocked`/`obscured` semantics exist
  only under a declared policy (so a stateless portal is `clear` absent a policy,
  `obscured` under one — §1).

## §4 The read surface (Codex gate 5 — do not overload `path()`)

**`path()` stays strictly structural + temporal** (`list[str] | None`,
unchanged) — it never becomes passability-aware (Cx blocker 1; it has no channel
for "exists but blocked"). A **single** new read **`route()`** owns passability
(C-019: no `route()`/`traverse()` twin).

**`route()` is a two-pass search, never an edge-deletion BFS** (Cx blocker 2):
first compute the structural as-of route graph (the `path()` graph); then
classify each candidate segment under the declared traversal policy. Return a
**clear** route if one exists; else return the **structural** route with its
blocked/obscured segments flagged. Return `no_path` **only** when the as-of
lateral graph has no route at all — so "all known ways are blocked" never
collapses into "no path exists."

`route()` returns, per segment:
- **status** — a current segment is `clear` | `blocked` | `obscured` (Cx 051:
  `removed` is NOT a current-segment status — see the diagnostic rule below);
- for a **blocked** segment — the **obstructing facts** as assertion evidence: the
  portal, its blocking state row(s), the obstruction relation row(s) + objects,
  each `{entity, attribute, value, assertion_id, provenance}`;
- for an **obscured** segment — a separate **`unknown_basis`** shape, because
  relational absence has no row to cite and forcing a fake one would violate
  RFC-002 (Cx blocker 3): `{kind: "relational_absence" | "unresolved_thunk",
  portal, required_attribute, frame, as_of, horizon?}` — a thunk on
  `door.state` cites its row; a freshness/frame gap is *computed*, not stored.
- `route()` can compress `[room_a, door, room_b]` into one segment for host
  ergonomics (Cx) while the door stays the fact carrier.

**`removed` is diagnostic, not a current segment** (Cx 050 #3): a removed edge is
already filtered out of the as-of graph (`valid_to`), so it is never a *current*
status of a returned segment. `route()` reports it only as **diagnostic evidence
for a missing connection** — when no current route exists and a *former* passage
(a `valid_to` row, valid before `as_of`) would have linked the endpoints,
`route()` may surface it as `{former_passage, valid_to, …}` so the host can say
"the shaft is dead — it used to connect here." (And a `route(as_of=before)` of
course returns it as a live segment — history preserved.)

The host reads the facts / unknown_basis and supplies the words ("rusted shut",
"guarded by Bjorn", "you can't tell if the way is open") + the navigation policy;
the engine emits only structural facts + derived status.

## §5 The five acceptance gates (Codex/Conduit, pre-agreed)
1. Traversability stays **folded/derived**, never host-authored convenience.
2. `blocked` carries host vocabulary **as declared data / authored facts**, never
   engine-parsed host structure.
3. `removed` affects as-of pathing without erasing historical truth (shipped).
4. `obscured` follows the **unknown doctrine**, never collapses to clear/absent.
5. `path()`/`route()` distinguish no-path from blocked/obscured-path and annotate
   the reason; the frozen `path()` return is not overloaded.

## §6 Decisions made (deliberation closed — Cx 049/050/051 + C 019)
- **§3 fork → resolved:** **A** (declared traversal policy) for `route()`, **B**
  (raw facts) always surfaced, `path()` unchanged.
- **Portal modelling → resolved:** **waypoint entity** via `connects_to`; **no**
  new `portal_between` family (stays inside the lateral fold). `route()` may
  compress `[room_a, door, room_b]` into a segment.
- **`obscured` → resolved:** **both** forms — an `unresolved`/`deny` thunk when a
  portal aspect is established-unknown, and **relational absence** when a declared
  policy requires a fact not visible in the frame/time window — via the computed
  `unknown_basis`, only under a declared policy.
- **`removed` → resolved:** strictly **temporal** (`valid_to`); diagnostic-only
  (former-passage evidence), never a current segment. `destroyed` is host evidence
  that drives the host to end the edge, not an engine rule.

## §7 Non-goals
No stored `blocked` flag. No engine reason-vocabulary. No required portal entity
for simple worlds. No overload of `path()`'s return. No scoring of "how blocked."
