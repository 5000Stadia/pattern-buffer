# PATH-TEMPORAL-V1 — as-of-aware path() (the `removed`/severed edge)

**Status:** DRAFT → Codex GREEN before implementation.
**Kind:** additive, backward-compatible (new optional param; default = today's
behavior). The doctrine-pure substrate for the `removed` reason-category
(RFC-003 gate 3): a dead edge is one whose *connectivity ended in time* — no host
vocabulary, no stored "dead" flag.

## Problem

`path()` is the only read on the surface that ignores valid-time entirely. Its
edge scan is `buffer.visible(asserted_as_of=…, frame=…)` with **no
`valid_as_of`**, so it unions in *every* `connects_to`/`adjacent_to` edge ever
asserted — including ones whose `valid_to` has passed. A host that models a
severed edge (the decommissioned elevator, C-009 A3) by ending it
(`valid_to` = the failure time) gets no effect: the dead edge is still traversed.

## Shape

Add `valid_as_of: float | None = None` to `path()` (and `p.path`), and filter the
lateral edges by valid-time when it is supplied:

```
world.path(a, b, frame="canon", valid_as_of=None, asserted_as_of=None) -> list[str] | None
p.path(a, b, as_of=None) -> list[str] | None
```

- **`valid_as_of=None` (default): unchanged.** No valid-time bound — today's
  behavior, today's tests. Backward-compatible, consistent with `locate`/
  `contents` which also default to no bound.
- **`valid_as_of=T`:** the edge scan passes `valid_as_of=T` to `buffer.visible`,
  so an edge with `valid_from > T` or `valid_to <= T` is **absent** from the
  graph. `path(a, b, valid_as_of=now)` therefore routes around a severed edge,
  while `path(a, b, valid_as_of=before_the_breach)` still shows it — **history is
  preserved** (gate 3). Removal is `valid_to`, derived at read, never a stored
  flag (membrane).

## Mechanism (one-line change)

In `Indexes.path`, thread `valid_as_of` into the single
`buffer.visible(asserted_as_of=…, frame=…)` call. Everything downstream (the
undirected BFS) is unchanged. `connects_to`/`adjacent_to` are lateral (path
unions all current edges; it does not fold by recency), so "removed" is expressed
**temporally** (`valid_to`), not by supersession — which is exactly why as-of
filtering is the right and only lever here.

## Non-goals (RFC-003, later)

This does NOT add `blocked` (a reversible obstruction — a declared edge status) or
`obscured` (unknown traversability — the thunk doctrine), nor reason annotation
on the result. It is *only* the temporal/`removed` substrate. `path()` still
returns `list[str] | None` (no reason payload yet); distinguishing "no path" from
"blocked/obscured" is RFC-003 gate 5.

## Tests

1. **severed edge dropped at now:** A↔B `connects_to` with `valid_to=t_breach`;
   `path(A, B, valid_as_of=after)` routes the long way / returns None (no direct),
   while the default `path(A, B)` (no bound) still includes it.
2. **history preserved:** `path(A, B, valid_as_of=before)` still shows the edge.
3. **future edge excluded:** an edge with `valid_from > T` absent at `valid_as_of=T`.
4. **default unchanged:** existing `path()` behavior/tests untouched (no bound).
5. **frame still honored:** out-of-frame edges absent, with and without `valid_as_of`.
6. **membrane:** the read writes nothing.
