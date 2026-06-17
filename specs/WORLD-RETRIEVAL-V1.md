# WORLD-RETRIEVAL-V1 — neighborhood retrieval + salience (the intelligent read)

**Status:** SPEC r3 — Codex r2 left 3/4 resolved; r3 fixes the last: salience
uses **absolute** (not candidate-relative) normalization so a per-entity score
is cacheable; `event_participation` reads indexed visible event rows (events
are EVENT-dropped by `fold_key`); `incoming_refs` iterates the full identity
closure; `max_fanout` added to the signature; `classifier_version` counter
pins cache invalidation. Re-review pending. The
*shape* passed r1 (bounded, P7, additive, derive-don't-store all GREEN); the
RED was operational — the existing surfaces this would reuse (`path()`,
`events()`, incoming-ref counting) scan global state, so reusing them as-is
would break this spec's own closure-scoped bound. r2 adds the bounded one-hop
index helpers, pins the salience formula + cache invalidation, builds salience
first, and *replaces* the materialize budget ordering.

Completes the read half of the substrate:
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
             edge_kinds=None, max_fanout=64, budget=None) -> dict
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
invariant). **Budget shapes OUTPUT only — it never gates expansion** (Codex
r1): traversal is bounded by `depth` + a **visited set** (each identity-closed
id expanded at most once) + a **per-hop fanout cap** (`max_fanout`, default
e.g. 64; what's dropped is reported in `truncated`). Depth alone is not a
bound — `contents()`/lateral fanout can be wide.

### 2.5 Bounded one-hop index helpers (build these FIRST — Codex r1)

The existing reads this packages scan global state, which would break the
bound. Add deterministic, closure-scoped one-hop helpers on `Indexes`, each
using indexed `visible(...)` filters (never the whole log), and have
`neighborhood` walk over **folded** results, not raw visible rows:
- `lateral_neighbors(entity, frame, as_of)` — one hop over
  `connects_to`/`adjacent_to` from `entity`'s closure (not the whole graph as
  `path()` builds).
- `event_participation(entity, frame, as_of)` — events whose `agent`/`patient`
  row points at `entity`'s closure. **Events are EVENT-classified and
  `fold_key` drops EVENT rows, so this does NOT fold** — it reads indexed
  visible rows directly: `visible(attribute_in=["agent","patient"],
  value=<closure id>, frame, valid_as_of)` per closure id, collecting the
  `event:` subjects. (Scoped, not all `event:` rows.)
- `caused_by_of(event_ids, …)` — the `caused_by` edge(s) of given events via
  `visible(entity_in=event_ids, attribute="caused_by")` (a one-hop traversal
  helper; today only a private row-effect check exists).
- `incoming_refs(entity, frame, as_of)` — entities with an entity-valued row
  whose value is in `entity`'s **identity closure** (iterate every closure id,
  not just the canonical entity). **Needs a cheap reverse lookup:** add a
  value-leading index (`ix_assertions_value`) and an additive `value_type=`
  filter to `visible()`, so this is `visible(value=<closure id>,
  value_type="entity")` per id — indexed, not a Python scan. The `value=`
  match is against the JSON-encoded value (as `visible(value=…)` already does).
`path()`/`events()` stay as-is for their own callers; neighborhood uses these
bounded helpers instead.

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

**The fixed formula — ABSOLUTE normalization (Codex r2, the key fix).**
Candidate-relative normalization is incoherent for a cacheable per-entity
score (an entity would rank differently in different neighborhoods). So each
component is an **absolute** function of the entity alone, in `[0,1]`, making
`salience(entity, frame, as_of)` a stable, cacheable scalar; *ranking is just
sorting by it*.
```
salience = 0.40*recency + 0.25*reference_frequency
         + 0.20*reinforcement + 0.15*delta_from_baseline
```
- `recency` = `max_asserted_at(entity) / head` (0..1; newer → higher), a
  stable function of the entity's last touch vs the current log head.
- `reference_frequency` = `min(1, log1p(incoming_ref_count) / log1p(REF_SCALE))`
  — absolute log-scaled count of incoming entity refs (constant `REF_SCALE`).
- `reinforcement` = `min(1, log1p(distinct_valid_times) / log1p(REINF_SCALE))`.
- `delta_from_baseline` = 1.0 if a STATE/move row supersedes the entity's
  establishing baseline, else 0.0.
Weights and the two scale constants live in one module-level table — tunable,
documented, not scattered magic. No candidate set enters the formula or the
API.

**Caching + invalidation (pinned).** Salience caches in a **rebuildable
derived sidecar** (mirroring the classifier/semantics sidecars), never written
to the log (P2). Cache entry key = `(entity, frame, as_of)`; each entry stores
the `head` and `classifier_version` it was computed at, and is recomputed when
either differs. **`classifier_version`** is a counter the `Classifier` bumps
on every sidecar mutation (`set`/`promote_accruals`/`rebuild`) — durability can
change `delta_from_baseline`/the budget spine without moving the log head.
Identity-closure changes need no separate version: a `same_as`/merge/retract is
an append, so it moves `head`. When in doubt, recompute — it's cheap and
closure-scoped. Salience powers `neighborhood`'s ranking and `materialize`'s
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

## 5.5 Implementation order (Codex r1 — salience before neighborhood)

`neighborhood` ranking and the `materialize` budget both depend on salience,
so build bottom-up:
1. **Bounded one-hop index helpers** (§2.5): `lateral_neighbors`,
   `event_participation`, `caused_by_of`, `incoming_refs` (+ the
   `ix_assertions_value` index and the additive `visible(value_type=)` filter).
2. **Salience** — the pinned formula + the rebuildable sidecar with the
   pinned cache key/invalidation. Tests first (it's the foundation).
3. **Replace** `materialize`'s budget ordering (today: `all_rows()` global
   reference counts, ignoring frame/as_of/closure) **with** salience,
   preserving the CONSTITUTIVE-spine exemption (a *replacement*, not a mirror).
4. **`neighborhood`** traversal (visited set + per-hop fanout cap) + ranking +
   budget shaping.
5. **Porcelain/World verbs** + docs.

A trivial deterministic salience may scaffold neighborhood traversal tests,
but the real formula must land before ship (the ranking + budget behavior
depend on it).

## 6. Out of scope
- Arbitrary attribute/pattern queries (`where x.foo='bar' and y.baz>3`) — host-
  composed; a verb only on demonstrated need (Fork A position holds).
- Cross-entity aggregation/analytics. Salience tuning beyond the fixed formula.
- Frame inheritance (#4) — its own decision/spec.

## 7. Docs on ship
HOST-DISCIPLINE.md (retrieval: the neighborhood read replaces the hand-rolled
correlation sweep; salience for budgeted reads), ADOPTION.md (`neighborhood`,
`salience` verbs), LEXICON.md (`neighborhood`, `salience`).
