# FACTS-BOOKKEEPING-V1: a frame scan without the engine's bookkeeping rows

**Status:** r1, drafted. It waits on gate g4d7cf0 before going to pbr. Author: pb, 2026-10-12.
**Source:** construct's ask, mdd908f, an add-on to R42 (CLOSURE-READ-V1). Construct's reviewer, cr,
flagged the problem in code review.

## Need

- **What construct does.** Construct's frame-evidence scan (its IDENTITY-CONFIRM, step 2) reads
  the raw rows of `knows:<m>` with `facts(frame)`. It must skip the engine's own bookkeeping rows:
  identity edges, receipts, retractions and provenance.
- **How it does that today.** `construct/game.py` imports `patternbuffer.META_ATTRIBUTES` for the
  skip. cr ruled that this crosses the porcelain boundary: it is an engine constant, not a porcelain
  operation, so it will drift as the engine adds bookkeeping attributes. The sets grew five times
  this autumn: `frame_continues_as`, `learned_alias`, `decided_by`, `representative` and the
  semantics predicates.
- **What the host should do instead.** It should ask the porcelain, and hold no list.

## The shape

One new keyword argument on `facts`. The default leaves today's behaviour unchanged.

```python
facts(frame, entity=None, attribute=None, prefix=None, as_of=None,
      include_meta=False, asserted_as_of=None, frame_scope="exact",
      bookkeeping=True) -> list[dict]
```

- **`bookkeeping=False`** leaves out every row whose attribute is a **bookkeeping attribute**:
  `META_ATTRIBUTES | MECHANISM_ATTRIBUTES`, read from the engine at call time, so the list lives
  in one place.
  - That covers the identity edges (`same_as`, `maybe_same_as`, `distinct_from`, `aka`,
    `frame_continues_as`), `learned_alias`, receipts and provenance (`superseded_by`, `source`,
    `canonicalized_from`, `source_valid_from`, `correction_proposal`, `justified_by`,
    `world_defining`), and the mechanism attributes (`retracts`, `resolved_by`,
    `learned_at_wallclock`, `decided_by`, `representative`).
  - Rows about `attr:` subjects carry the semantics predicates, and the existing frame-wide scan
    already excludes them.
- **What it does not touch.**
  - `include_meta` keeps its meaning: it filters by *subject* (`a:` and `attr:`), while
    `bookkeeping` filters by *attribute*. The two compose.
  - With `bookkeeping=False` and `include_meta=True`, the scan answers meta-subject rows whose
    attribute is not bookkeeping. It answers no `retracts` row, for example.
- **`attribute` naming a bookkeeping attribute.** `facts(F, attribute="same_as",
  bookkeeping=False)` answers `[]`. That is consistent with the definition and needs no special
  case.
- **The name.** The lexicon's **mechanism attribute** is the narrower `MECHANISM_ATTRIBUTES`
  (rows honoured only with their owner's status mark). This flag covers both sets, so it takes a
  new lexicon term, **bookkeeping attribute**, rather than stretching an existing one. The service
  already says "bookkeeping" in its record refusal.
- **MCP and viewers.**
  - The MCP `facts` tool gains the parameter through the registry's schema.
  - A WorldService viewer may pass it: it only narrows the viewer's own frame scan.
  - No forced value is needed.

## Tests

1. On a frame holding a world fact plus `aka`, `same_as`, a retraction pair and a `source` row:
   - `bookkeeping=False` answers only the world fact;
   - the default answers what it answered before (byte-identical to a call without the argument).
2. Parity: every attribute in `META_ATTRIBUTES | MECHANISM_ATTRIBUTES` that can be written in a
   `knows:` frame is excluded. A later addition to either set is excluded with no change here; a
   test adds a name to a patched set to show it.
3. `include_meta=True, bookkeeping=False` composes as above.
4. MCP: the `facts` tool accepts `bookkeeping` and filters the same way.
5. A WorldService viewer's `facts(bookkeeping=False)` filters within the view frame, and the
   existing viewer tests are unchanged.

## Lexicon

- **bookkeeping attribute**: an attribute the engine writes to keep its own books rather than to
  state a world fact: every name in `META_ATTRIBUTES | MECHANISM_ATTRIBUTES` (identity edges,
  receipts, retractions, provenance). `facts(..., bookkeeping=False)` leaves their rows out, so a
  host scanning a frame for evidence holds no list of its own.
