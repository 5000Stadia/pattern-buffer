# WORLD-RETRIEVAL-V1 — neighborhood retrieval + salience (the intelligent read)

**Status:** SPEC, pre-Codex-GREEN. Completes the read half of the substrate:
"surface the relevant detail about a subject and the things it's connected
to." The core read of a *generalized* world-relational tracker — every domain
(a life-assistant world model, a work/life/location tracker, a D&D campaign, a
narrative mystery) does it constantly. **Whitepaper wins; this is read-layer
only — derive-don't-store, additive, never changes stored data.**

**Scope discipline (P7 — the engine stays minimal).** This is NOT a query
language and NOT a graph database. It is two bounded, deterministic reads that
*package* walks the engine already does (`locate`/`contents`/`path`/`events`/
`caused_by`/the identity closure) and rank them by a projection-time salience
the whitepaper already defines. If it ever tempts toward arbitrary
pattern-matching, that's out of scope — host-composed, per the standing
position (Fork A: a verb only when a host proves a forbidden full-log scan).

## 1. Why this is generalized-essential, not bloat

The HOST-DISCIPLINE "correlation sweep" is a *host recipe* today (resolve →
snapshot → locate/contents → events → caused_by → recurse). For a shape meant
for many adopters, every one of them re-implements the same sweep, each
slightly differently, each paying multiple host↔engine round-trips. Promoting
it to one closure-scoped engine pass is consistency + efficiency for all of
them. And a *salience* ranking is what makes the read usable once a world
accumulates (a years-long assistant model, a long campaign): "show me what
matters about X," not "show me all 4,000 rows."

## 2. Part A — `neighborhood(entity, …)`

A new porcelain read verb (additive; LLM-free; P7):

```
neighborhood(entity, depth=1, frame="canon", as_of=None,
             edge_kinds=None, budget=None) -> dict
```

Returns the subject's own folded state plus the structurally-connected
neighborhood out to `depth` hops, salience-ranked and budget-shaped:

- **The subject:** its `current_state` fold (incl. `quantity` for accrue keys),
  its containment chain (`locate`), its contents (`contents`).
- **Edges walked** (the structural correlation axes, the only ones — no
  arbitrary attribute matching):
  - containment (up via `locate`, down via `contents`),
  - lateral graph (`connects_to`/`adjacent_to`, one hop),
  - entity-valued attributes of the subject (one hop to each referenced
    entity — the relationship neighborhood),
  - causal/temporal (`events` the subject participates in + their `caused_by`
    chain).
  `edge_kinds` (subset of `{containment, lateral, relations, events}`)
  restricts which axes are walked; default = all.
- **`depth`** bounds hops (default 1; hard cap, e.g. 3, to keep it bounded —
  this is a neighborhood, not a transitive-closure crawl).
- **Identity-closed:** each reached id is resolved through the identity
  closure (no fragment duplicates).
- **Frame/as-of** honored throughout (a `knows:X` neighborhood is X's
  *knowledge* neighborhood; an as-of neighborhood is the world at that time).

Output shape (JSON-serializable, additive — no existing payload changes):
```
{ "subject": <snapshot-like facts + quantities>,
  "neighbors": [ {"entity": id, "via": <edge_kind>, "hop": n,
                  "salience": float, "facts": [...] }, ... ],
  "truncated": <int dropped to budget> }
```

`neighbors` is salience-ranked (Part B); `budget` drops the lowest-salience
neighbors first (never the subject, never CONSTITUTIVE spine — the §10 budget
invariant).

## 3. Part B — salience (the ranking, made real)

The whitepaper §13 already defines salience as a **projection-time ranking,
never stored**: `recency + reinforcement count + reference frequency +
delta-from-baseline`. This spec implements it as a deterministic function over
the log and exposes it where retrieval needs prioritization:

```
salience(entity, frame="canon", as_of=None) -> float          # one entity
```
computed from (all closure-scoped, no model call):
- **recency** — how recently the entity was asserted/updated (max
  `asserted_at` among its rows, normalized),
- **reinforcement** — how many distinct valid-times its facts span (a thing
  touched across many moments matters more),
- **reference frequency** — how many other entities point at it (entity-valued
  rows whose value is this entity),
- **delta-from-baseline** — whether it has changed from a CONSTITUTIVE/
  establishing baseline (movement/change draws attention).

The exact weighting is a fixed, documented formula (tunable constant table,
not magic). Salience is **cached in a rebuildable derived index**, never
written to the log (P2). It powers `neighborhood`'s ranking and `materialize`'s
budget ordering; a host may also call it directly.

**Honest bound:** salience is a heuristic, not truth. A fact unmentioned for
three campaign-years has *zero salience and full validity* (whitepaper §13) —
ranking never gates correctness; `state`/`snapshot` still serve everything.

## 4. Invariants
- **Derive-don't-store:** both reads compute over the log; salience caches in a
  rebuildable index, nothing authored.
- **P7 / bounded:** deterministic, LLM-free, fixed edge axes, depth-capped — a
  neighborhood read, not a query engine.
- **Frozen porcelain:** `neighborhood` and `salience` are new additive verbs;
  no existing signature/payload changes.
- **Closure-scoped (037):** neighborhood/salience read the subject's closure
  and one-hop neighbors, never the whole log.
- **Frame absence:** a `knows:X` neighborhood contains only what X knows; no
  canon leak.

## 5. Tests
- `neighborhood(person)` returns the person's state + their location + items
  they hold + entities they relate to, one hop, ranked.
- `depth=2` reaches two hops; `depth` cap enforced; `edge_kinds=["containment"]`
  walks only containment.
- Identity: an aliased/merged neighbor appears once (closure-resolved).
- Frame/as-of: a `knows:X` neighborhood excludes canon X doesn't know; an
  as-of neighborhood reflects the world at that time.
- `budget` drops lowest-salience neighbors, never the subject/CONSTITUTIVE.
- Salience: a heavily-referenced, recently-changed entity outranks a stale
  unreferenced one; salience never alters what `state` serves.
- Rebuild: drop the salience index, rebuild → identical ranking.
- Defaults-preserve: full suite green; existing reads unchanged.

## 6. Out of scope
- Arbitrary attribute/pattern queries (`where x.foo='bar' and y.baz>3`) — host-
  composed; a verb only on demonstrated need (Fork A position holds).
- Cross-entity aggregation/analytics. Salience tuning beyond the fixed formula.
- Frame inheritance (#4) — its own decision/spec.

## 7. Docs on ship
HOST-DISCIPLINE.md (retrieval: the neighborhood read replaces the hand-rolled
correlation sweep; salience for budgeted reads), ADOPTION.md (`neighborhood`,
`salience` verbs), LEXICON.md (`neighborhood`, `salience`).
