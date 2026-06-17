# WORLD-RETRIEVAL-V2 — aggregates + multi-frame knowledge reads

**Status:** SPEC, pre-Codex-GREEN. Two read-layer additions the generalized
world-tracker reflexively needs, both **derive-don't-store**, **additive**, and
**non-overlapping** with existing verbs (the dilution test): a bounded
*aggregate* read over collections, and the *multi-frame* `frame_diff` that
completes the flat-frames + read-union knowledge model (#4 / RFC-002 §7.6).
**Whitepaper wins; read-layer only, no stored-shape change. P7-bounded — not a
query engine.**

## Part A — `aggregate(container, member_attribute, op, …)`

### What it addresses
Every collection has **emergent properties** — a backpack's total weight, a
room's headcount, a portfolio's value, a party's max level. A world-tracker
reflexively wants these, and they are **computed, never stored** (derive-don't-
store: the total is a fold over members, not an authored fact).

### Shape (additive porcelain + World + Indexes read)
```
aggregate(container, member_attribute, op,
          frame="canon", as_of=None, recursive=False) -> dict
```
- `op ∈ {sum, count, min, max, avg}`.
- **Members** = the container's `contents()` (closure-scoped, the 037 indexed
  read). `recursive=True` walks the whole containment subtree (bounded by the
  tree; visited-set guarded) — default `False` = direct members only.
- For each member, **fold `member_attribute`** (its current value via
  `state`/`fold_key`, incl. `quantity` for accrue keys); collect the numeric
  ones (`isinstance(v,(int,float)) and not bool`, the same guard as `where`).
- `sum`/`min`/`max`/`avg` reduce the numeric values; `count` = number of
  members carrying a numeric value at that key.
- Output: `{"op": op, "value": <number|None>, "count": <int>,
  "members": [<entity ids contributing>], "container": <id>}`. Empty / no
  numeric members → `value=None` (or `0` for sum/count), `members=[]`.
- Honors `frame`/`as_of` throughout (a `knows:X`-frame aggregate sums only what
  X knows; an as-of aggregate is the collection at that time).
- **Non-numeric / missing** members are skipped (never an error, never a
  fabricated zero) — an honest aggregate over what *is* numeric.

### Bounded / non-overlapping
Deterministic, LLM-free, closure-scoped over `contents()`. **No overlap:** no
existing read reduces a collection (neighborhood *traverses* structure;
`where` *filters* entities; `state` reads *one* key) — `aggregate` fills a
clean gap. Not a query engine: one container, one member attribute, one of five
fixed ops.

## Part B — multi-frame `frame_diff` (the #25 read affordance)

### What it addresses
The flat-frames + read-union model (#4): an observer's *effective* knowledge is
`knows:O ∪ public` — never a stored inheritance. This read makes the union a
single call.

### Shape (additive — `b` gains a list form)
`frame_diff(a, b, scope, as_of=None)` — `b` accepts a **str OR a list of
frames**. `frame_diff(canon, [knows:marn, public], scope)` = what's true in `a`
that the observer (own frame ∪ public) doesn't effectively know.

### Semantics (pinned — "union of presences, agreement covers")
For each fact in `a`'s materialization, against the set of `b`-frames:
- **Covered (not reported):** *any* `b`-frame holds the key with an equivalent
  value (the observer can know the truth through some frame — private ignorance
  is corrected by common knowledge).
- **Divergent (reported, `divergent=True`, `b_value`):** some `b`-frame holds
  the key with a *different* value **and** none holds an equivalent one (a false
  belief the public frame doesn't correct). `b_value` = the most-recent
  divergent value across the `b`-frames.
- **Absent (reported):** no `b`-frame has the key at all.
Single-string `b` behaves exactly as today (a one-element set). Set-valued and
accrue keys diff as in V1 (membership / quantity), now across the `b`-union.

### Non-overlapping
This *deepens* the existing `frame_diff` along its own axis (the `b` side gains
a union form); it does not add a second knowledge model. No new verb.

## Invariants
- **Derive-don't-store:** both reads compute over the log; nothing authored.
- **Frozen porcelain (pre-v1, but still additive):** `aggregate` is a new verb;
  `frame_diff`'s `b` gains a list form with the str behavior unchanged — no
  existing signature/payload broken.
- **P7 bounded:** fixed ops / fixed union semantics; closure-scoped; no model.
- **Frame absence / the unknown doctrine (A6):** `aggregate` skips non-numeric
  and missing members (never fabricates a zero — honest aggregate over what is
  present); `frame_diff` reports the gap, never paints it.

## Tests
- `aggregate(backpack, "weight", "sum")` = sum of members' weights; `"count"` =
  how many; `"max"`/`"min"`/`"avg"` correct; empty container → `value None`/`0`.
- `recursive=True` sums a nested subtree; direct-only by default.
- accrue member: `aggregate` over a `gold` accrue key uses the folded quantity.
- non-numeric/missing members skipped, not errored, not zero-filled.
- frame/as_of honored (a `knows:X` aggregate; an as-of aggregate).
- `frame_diff(canon, [knows:o, public], scope)`: a fact in `public` is
  **covered** (not reported); a fact in neither is **absent**; a wrong value in
  `knows:o` with no public correction is **divergent**; a wrong value in
  `knows:o` that `public` corrects is **covered**.
- single-string `frame_diff` unchanged (regression).
- defaults-preserve: full existing suite green.

## Out of scope (and why)
- **General query / multi-condition retrieval** (Fork A) — overlaps `where`/
  `neighborhood`/`state` → dilution; host-composed until a forbidden full-log
  scan appears.
- **Nested belief** (frames-about-frames) — a *second* knowledge model →
  dilution; shape not confidently knowable. Deferred (ROADMAP-deferred).
- **Confidence/freshness read** (C) — strong candidate (reflexive for reality;
  Kernos-shaped; no overlap) but read-layer and host-computable today; its own
  follow-on spec, not bundled here.
- **accrue min/max, salience tuning** — thin scenarios.

## Docs on ship
HOST-DISCIPLINE.md (aggregate as the collection-rollup read; multi-frame
`frame_diff` for effective knowledge); ADOPTION.md (`aggregate`, `frame_diff`
list form); LEXICON.md (`aggregate`).
