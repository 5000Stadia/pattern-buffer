# SITUATION-LENS-V1 — re-entry retrieval: standing truth ∪ live threads

**Status:** DRAFT r2 (effect-driven rewrite, resolving Codex r1's six findings)
→ seeking Codex GREEN before implementation.
**Kind:** passive, additive read. A fifth `materialize` lens "situation". No
fold-path, schema, or write-path change. Derived at read; nothing stored; no
housekeeping (the membrane — whitepaper A6, P2).

## Why

Re-entering a long-history scope (the party returns to the tavern after years;
the plumber reopens a repeat customer; Jarvis assembles context on a person)
must not drag the whole closed past along. The two existing lenses can't express
the middle path:

- `current_state` — the standing fold, but **zero events** → loses live threads
  (the assassin last seen here, the chest in the back room).
- `what_happened` — **all events**, including the long-dead (the brawl on visit
  2) → noise that crowds the budget.

`situation` is the middle: **the standing truth plus only the *live* threads
anchored to the scope, with closed history dropped.**

## The lens contract

`materialize(scope, lens="situation", frame=, as_of=, budget=, asserted_as_of=)`
→ `Materialization` with:

1. **Standing truth (the floor)** — identical to the `current_state` lens output
   for the scope. Always served; never truncated by budget.
2. **∪ Live events** — events whose live effect is anchored in the scope
   (§Algorithm), ordered by recency, cut to remaining budget (§Overflow).
3. **Closed history dropped** — non-live events are absent; a host queries
   `what_happened` / `events(participants=…)` directly when a scene reaches for
   them (the fail-safe blind spot, §Limits).

`LENSES` gains `"situation"`. Porcelain `snapshot(..., lens="situation")` passes
through unchanged (zero model calls, zero writes).

## The reframe: anchoring is effect-driven, not participant-driven

Codex r1/finding-4: reusing `_lens_events`' subject/object anchoring is **not
one-hop** — `_scope_entities` recursively includes contents, so a mobile
participant currently *in* the scope (Barliman standing in the tavern) would
drag in their unrelated events (his cousin's farm). Liveness alone doesn't save
it: "cousin runs a farm" is a surviving state, hence live.

The fix: **anchor an event by where its *live effect* sits, not by who
participated.** An event surfaces iff it produced a still-served state (or open
thread) **about an entity in the scope set.** This unifies anchoring and
liveness in one pass and matches the intuition exactly:

- "chest stashed in the back room" → live effect `location(chest)=back_room`,
  back_room ∈ scope → **anchored & live**. ✓
- "assassin last seen at the Pony" → live effect `location(assassin)=Pony` (if
  un-superseded), Pony ∈ scope → **anchored & live**. ✓ (Seen elsewhere later →
  effect superseded → dead → dropped.)
- "Barliman's cousin runs a farm" → live effect is about the farm, **not** in
  tavern scope → **not anchored**, even though Barliman is in scope. ✓

## Algorithm

Bucket 1 and bucket 2 share one traversal of the scope's **currently-served
rows**, so there is no per-event inverse N+1 (finding 6).

### Bucket 1 — standing truth + collect the served set

Run the existing `_lens_state` for the scope (unchanged output). While folding
each `(entity, key)`, collect the **served row ids** — the rows the fold
actually serves *now* (finding 3, the un-superseded test must match what the
projector serves):

- functional: `winner` + `_value_rows` (set-valued members);
- accrue: the `_ledger_rows` (a quantity fold serves via `m.quantities`, and its
  `winner` is only the latest contributor — ledger rows are the live effects);
- conflicted: also the `conflicting` ids (standing truth includes both sides);
- open: an `unresolved` row that is the current `fold_key(...).winner` for its
  key **and** has no visible `resolved_by` (finding 2 — a marker-only check is
  wrong because the fold drops a placeholder once concrete rows exist; the
  authoritative open test is "still the winner").

Call this set `served_ids` and remember which are `open` (unresolved-winner).

### Bucket 2 — live events from the served set

1. **Find effect→event edges in one batched read** (finding 6):
   `buffer.visible(entity_in=served_ids, attribute="caused_by",
   value_type="entity", frame=m.frame, asserted_as_of=m.asserted_as_of)`.
   Each such meta-row sits on an effect row (`entity` = the served effect-row
   id) and points (`value`) at its causing **event entity** (resolve via
   `_resolve`; a `caused_by` may name any closure member — resolution
   canonicalizes). All liveness reads use `m.frame`, `m.as_of`,
   `m.asserted_as_of` (finding 6).
   - effect row is concrete & served → its event is live by **(b) surviving
     effect**.
   - effect row is an `open` unresolved-winner → its event is live by **(a) open
     thread**.
2. **Event entities that are themselves open threads** — an `unresolved`-winner
   row whose own entity is EVENT-class (a deferred event) → live by (a). (Edge
   completeness; rare.)
3. `live_event_ids` = the resolved event entities from 1–2. For each, emit its
   **EVENT-durability** assertion rows visible in `m.frame` at the as-of/asserted
   bounds (consistent with `_lens_events`' row selection). Event entity id is
   `row.entity` resolved — never the assertion id (finding 1).

Anchoring is now implicit and correct: an event is emitted only because it
produced a still-served state/thread **about a scope entity**.

## Overflow ordering (finding 5 — protect the floor)

Bucket 1 is the floor and is **never** truncated. Bucket 2 is ordered by
**recency of last activity** — `(valid_from or -inf, seq)` descending — and cut
to the budget remaining after the floor. An ancient-but-still-open thread yields
to fresh ones. Recency, **not popularity** (popularity would surface the brawl,
which isn't even live).

`materialize` currently always calls `_shape_to_budget`, which protects only
CONSTITUTIVE rows and would re-truncate the standing-truth floor. For
`situation`: budget bucket 2 **internally** against `budget − |floor|`, then
**skip the global shaper** for this lens (or pass it a protected set = the floor
rows). Implementation note, not a new public surface.

**Open knob, deferred:** whether an (a) open-question outranks a (b) surviving
state of equal age. Default pure recency; add only if overflow proves common.

## Derived / never stored / no housekeeping

Liveness is recomputed every read from present facts. The alive→dead transition
is a side effect of ordinary appends (a resolution writing `resolved_by`; a
supersession writing a newer state) or the clock crossing `valid_to` — never a
maintenance pass, mutation, or stored "live" bit. Membrane-test: recomputable →
not a fact. Dead events stay in the log forever (P1); they merely stop being
surfaced.

## Limits (honest, accepted)

- **Dormant-but-critical-on-future-trigger** facts (a secret door named once long
  ago; an unmodeled warranty; an anniversary) are not surfaced — the same blind
  spot salience has, but failing *safe*: quiet omission, recoverable by a
  targeted host query, no wasted budget. The trigger is the host's to own.
- **Unlinked events** (no `caused_by` effect edge modeled) read as dead and do
  not surface. A host that wants event liveness models effects with the engine's
  existing `caused_by` mechanism. Fail-safe, consistent with the above.

## Tests (invariants, not just returns)

1. **Floor:** `situation` bucket-1 output equals `current_state` output for the
   same scope.
2. **Live kept (b):** an event whose produced state is still the fold winner
   appears; the surviving effect's entity is in scope.
3. **Dead dropped:** produce "damaged" then supersede with "repaired" → the
   event no longer appears.
4. **Open thread kept (a):** an event with an open unresolved-winner effect
   appears; after `resolve()`, the next read drops it (no lens write — the
   resolution append flips it).
5. **Expiry:** an event whose only effect has a past `valid_to` drops once
   `as_of` crosses it.
6. **Effect-anchoring, not participant:** Barliman is in tavern scope and has a
   live event whose effect is about the farm (not in scope) → it does NOT
   appear; an event whose effect is `location(chest)=back_room` (in scope) does.
7. **Accrue effect:** an accrue ledger row that is an event effect keeps its
   event live (finding 3 — ledger rows count as served).
8. **Conflicted effect:** a conflicting-but-served effect row keeps its event
   live (finding 3 — both sides served).
9. **Overflow:** with budget below the live-event count, the most-recent live
   events survive; standing truth is never truncated.
10. **Membrane:** the call writes nothing (assertion count unchanged).
11. **Frame:** out-of-frame effects/events are absent.
