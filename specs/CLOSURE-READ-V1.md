# CLOSURE-READ-V1: a host's read of identity closures

**Status:** r2. It answers pbr's r1 RED: the shared row helper takes a frame, as `distinct_block` already does for `correlation_conflicts`, and the as-of test spans a retraction. Marked *(r2)*. Author: pb, 2026-10-12.
**Source:** roadmap R42. Construct asked on 2026-10-12 (mfc2084, m92b797), and the monitor approved
it for Kabe (gate gc857b5, note ne26319): "build it right after S2 … host-only, outside the viewer
allowlist; distinct_between only if construct's swap needs it". Construct confirmed that it needs it.

## Need

- **What construct needs.** Construct's IDENTITY-CONFIRM stage (cr GREEN on r2) decides
  frame-owner pairs over closures, and its identity stop (`construct/game.py` `_held_apart`) asks
  one question: is a canon `distinct_from` row holding these two closures apart?
- **What construct does now.** The porcelain has no closure read, so construct walks canon `same_as`
  rows itself through `facts("canon", attribute="same_as")`. That is a copy of
  `IdentityRegistry._same_as_edges` and `_walk`.
- **Why that is a problem.** Each time the engine's identity rules change, that copy can drift:
  - R35 made a retracted `same_as` keep a pair settled apart;
  - IDENTITY-REPRESENTATIVE-V1 added re-point events.

  A host should ask the engine, not re-derive it (CLAUDE.md: the adapter absorbs host pressure, but
  never by duplicating engine logic it can read).

## The shape

Two read-only porcelain verbs, which write nothing:

```python
closure(entity: str, asserted_as_of: int | None = None) -> list[str]
distinct_between(a: str, b: str, asserted_as_of: int | None = None) -> list[str]
```

- **`closure`**
  - It answers the sorted members of the entity's identity closure, the entity included:
    `sorted(registry.closure(entity, asserted_as_of))`.
  - An id with no `same_as` edge answers `[entity]`.
  - A malformed id (`ID_RE`) raises `ValueError`, as the other id-taking reads do.
  - `asserted_as_of` reads the log as it stood at that position (READ-SURFACE-V1 §8), using the
    registry's own as-of walk.
- **`distinct_between`**
  - It answers the row ids (`a:N`, in log order) of the canon `distinct_from` rows with one
    endpoint in `a`'s closure and the other in `b`'s, at that log position. It is empty when none
    holds them apart.
  - It reads the same predicate as the registry's `distinct_block(a, b, asserted_as_of)` (canon,
    entity-valued rows), but answers row ids where `distinct_block` answers descriptors:
    - construct's stop uses the answer as a bool;
    - the ids let its error name what holds a pair apart;
    - the ids are what a repair would retract.
  - *(r2)* The registry gains
    `distinct_rows(a, b, asserted_as_of=None, *, frame=CANON) -> list[str]`, the one row-selection
    predicate.
    - `distinct_block(a, b, asserted_as_of, frame)` is rebuilt on it. It still answers descriptors,
      so legacy callers are unchanged.
    - `distinct_block` keeps its `frame` argument, which `correlation_conflicts` needs: a
      contradiction is two edges in one observer frame (FRAME-SCOPED-IDENTITY-V1 §3(b)).
    - The porcelain `distinct_between` always calls the canon default and takes no `frame`.
  - When `a` and `b` share a closure, a `distinct_from` inside it is still reported, as
    `identity_conflicts` already does. The read answers what the log holds and decides nothing.
- **Canon only.** Neither verb takes a frame. Identity is global, and a canon merge veto reads
  canon (FRAME-SCOPED-IDENTITY-V1 §2).

## Where they are served

- **The porcelain**, with docstrings.
- **MCP:** both verbs join `V1_READS`. The registry goes from 43 to 45 tools, and the count tests
  move with a comment, as each addition has.
- **WorldService:** both are **excluded** from viewers. They go in `VIEWER_EXCLUDED` as "a canon
  identity diagnostic", beside `proposals` and `identity_conflicts`. The service's walk test then
  classifies them. A viewer that asks is refused, so it learns nothing about canon's merges of
  unperceived ids.

## Tests

1. `closure` matches `registry.closure` on every entity of a fixture with merges, a retracted
   `same_as`, and a re-pointed representative. It matches as-of too, at each log position.
2. Construct's copy of the walk, `facts("canon", attribute="same_as")` walked, gives the same
   members as `closure` on that fixture. This is the parity that lets construct delete its copy.
3. `distinct_between`:
   - it gives the right row ids across closures in both directions (`a` holding a row on `b`'s
     member, and the reverse);
   - it is empty with no row;
   - a retracted `distinct_from` drops out;
   - *(r2)* as-of is a historical read across the row's life: empty before the row is asserted,
     the row's id at a position after it and before its retraction, and empty at and after the
     retraction.
3a. *(r2)* **The frame stays the caller's.** A non-canon `distinct_from` in a frame F, with a
   canon `distinct_from` as a decoy, shows that `distinct_block(..., frame=F)` and
   `correlation_conflicts` read only F, exactly as before. `distinct_between` reads only canon, and
   offers no way to name F.
4. `distinct_block`'s answers are unchanged: the existing identity suites pass untouched.
5. MCP has 45 tools; both verbs dispatch.
6. A viewer session's `closure` and `distinct_between` calls are refused with the excluded reason,
   and the walk test passes.

## Not in this spec

- A frame-scoped closure. P1 keeps a frame to its own stored names, and nothing asks for one.
- Any change to how merges are decided.
