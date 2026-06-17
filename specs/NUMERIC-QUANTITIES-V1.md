# NUMERIC-QUANTITIES-V1 — numeric quantities: change them, compare them

**Status:** SPEC r3 — Codex r2 left findings 1/3/4/5 resolved; r3 fixes the
remainder (stale `_value_rows`-as-ledger text → `_ledger_rows`; `frame_diff`/
`ask` accrue-awareness; the `visible()`-kwargs contradiction removed).
Re-review pending. Merges the founder-ruled Imp 2 (value typing / comparison
predicates) and #20 (the `accrue` delta-counter) into one coherent "numbers"
capability, wired on **both** sides (engine + data structure). **Whitepaper
wins; a refinement within P1/P2.** Composes with ATTRIBUTE-SEMANTICS-V1 (the
`accrue` `fold_policy` it reserved is lit up here).

**r2 changelog (Codex RED r1 → fixes):** (a) **The accrue ledger must NOT
reuse `_value_rows`** — the projector materializes `_value_rows` as separate
facts (correct for set-valued), which would leak `gold=500`/`gold=-20` into
snapshots instead of the folded total. The total now flows through a new
`Materialization.quantities` channel and `FoldResult.quantity`; the ledger
rides a separate, non-materialized `_ledger_rows`. (b) **Accrue folds before
the EVENT/durability filter** (a delta the model classified EVENT would be
dropped) + a deterministic `delta → STATE` classifier guardrail. (c) **Phase-2
predicates compare in Python after folding**, not via SQL `CAST` (SQLite casts
non-numeric literals to `0.0`, so the `value_type` guard was unsound). (d)
`fold_policy` enum gains `accrue`; `VALUE_TYPES` and the extraction schema
gain `delta`; non-accrue folds drop `delta` rows.

**Founder decisions baked in:** int **and** float supported now; exact
decimal **deferred** (a documented limitation, not built speculatively); the
quantity-change ability lives in both the engine and the data structure.

## 0. Two sides, one foundation

A *fungible quantity* (gold, ammo, liters, charges) is a number that
**changes over time** and that you **compare**. Two capabilities:

- **Write/fold (Phase 1 — the founder's primary ask):** set a quantity, or
  `+qty` / `−qty` it, and have the engine maintain the running total
  deterministically and append-only (the `accrue` ledger).
- **Read (Phase 2):** range/comparison predicates over numeric values
  (`gold >= 20`, `temperature > 50`) — the original Imp 2.

Ship Phase 1 first (it is the small, high-value part), Phase 2 immediately
after. One spec, clean internal phasing.

## 1. The data-structure change (minimal, universal)

The engine already stores any value as JSON in `value` + a `value_type` that
says *how to interpret it*. Numbers already round-trip as JSON int/float —
**number storage is not the gap.** The gap is that the engine must now
*operate* on numbers (sum, compare), and one operation needs a new
interpretation:

- **New `value_type = "delta"`** — a *signed numeric increment* to be
  accumulated, as opposed to `literal` (an *absolute* value). This is the
  entire data-structure change: extend `VALUE_TYPES` (a frozenset; no SQL
  schema change), the gate's append validator and `dump.build` (both already
  validate against `VALUE_TYPES`, so they inherit it), and the model
  extraction schema's `value_type` enum. `entity`/`literal`/`unresolved` are
  untouched; entity-resolution and the containment cycle gate already key on
  `value_type == "entity"`, so a `delta` is correctly inert there. A
  deterministic classifier guardrail maps `delta → STATE` (no model call).

**Type universality principle (founder's question, answered):** give a value
its own `value_type` *only where the engine must operate on it*. Everything
else stays a `literal` (opaque JSON, equality-compared). So the only new
operational type is `delta`; we do **not** proliferate per-type value_types.

**Numbers:** `int` and `float` are both first-class (JSON-native; Python
arithmetic promotes mixed to float). **Exact decimal is out of v1** — floats
carry rounding error that never bites integer quantities (gold, ammo, counts)
and rarely bites fiction; exact-money tracking, if a workload ever needs it,
is a later addition (store decimals as strings + decimal arithmetic). This is
a documented limitation, called out in the adopter docs.

## 2. Phase 1 — the `accrue` fold (set / +qty / −qty)

An attribute declared **`fold_policy=accrue`** (ATTRIBUTE-SEMANTICS-V1's
reserved axis, now wired) folds numerically instead of last-write:

```
SET   →  person:you · gold · 500     value_type=literal   (absolute baseline)
+QTY  →  person:you · gold · +500    value_type=delta
−QTY  →  person:you · gold · -20      value_type=delta
```

**Fold hook (Codex r1 #1/#3):** `fold_key` checks `fold_policy == accrue`
**immediately after gathering visible rows and dropping unresolved
placeholders, but BEFORE the EVENT-drop and the durability split** — accrue
ignores durability entirely, and routing it through the EVENT filter would
drop a delta the model happened to classify EVENT. A deterministic classifier
guardrail (`value_type == "delta" → STATE, 1.0`) also ensures deltas never
hit the model or land as EVENT in the sidecar.

**Fold algorithm** (deterministic, append-only, as-of-correct):
1. Candidates = visible rows for the key (frame/valid_as_of/asserted_as_of
   filtered) that are `literal` (numeric) or `delta`.
2. `baseline` = the latest **absolute literal** numeric row by
   `(valid_from, asserted_at)`, or value `0` if none.
3. `contributing` = every **delta** row strictly after the baseline in
   `(valid_from, asserted_at)` order (all deltas if no baseline).
4. `total = baseline.value + sum(d.value for d in contributing)`.

**FoldResult** gains **`quantity: int | float | None`** (additive; populated
only for `accrue` keys) and a private **`_ledger_rows`** (the baseline +
contributing rows, `compare=False`/`repr=False`, for hosts that render
history). Crucially **`_value_rows` stays `()` for accrue** so the projector
does NOT expand the ledger into snapshot facts. `winner` = the most-recent
contributing row (provenance only — its `.value` is a delta, never the
total). `functional`/`set_valued` keys leave `quantity=None` unchanged.

**Surfacing the total (Codex r1 #1 — the critical fix).** A folded total is
*derived*, not any stored row's value, so it cannot ride `m.assertions`
(which are stored facts). `Materialization` gains **`quantities:
list[tuple[str, str, int|float]]`** (entity, attribute, total) — a separate
channel beside `unresolved`/`conflicted_keys`/`defaults`. The projector, on an
accrue result (`quantity is not None`), records `(entity, attr, quantity)`
there and does **not** append `winner` to `m.assertions`. Porcelain
`snapshot` surfaces `quantities`; `state(entity, attr)` adds `quantity` to its
response. This keeps `facts = stored rows` pure and totals derived.

**Other read consumers that must learn accrue (Codex r2 NEW-1).** Because an
accrue total is not in `m.assertions` and `winner.value` is a delta, two
porcelain reads need accrue-awareness or they go wrong:
- **`frame_diff`**: today it iterates `m_a.assertions` and compares each
  `row.value` to B's `winner.value`. For accrue keys it must instead diff the
  folded **`quantity`** — compare A's `quantity` (from `m_a.quantities`) to
  B's folded `quantity`, reporting the key when they differ. (A delta row must
  never be compared as a raw fact.)
- **`ask`**: when the asked key folds to an accrue result, the answer's value
  is the `quantity`, not `_fact(winner)` (which would return the last delta).
  `ask` surfaces the total for accrue keys.

**Properties this buys (the gold pouch):**
- Deterministic — the engine sums; the model never does mental math.
- Append-only ledger — every find/spend is one row; `_ledger_rows` is the
  auditable history; a wrong entry is fixed by retracting it (excluded by
  `visible()`), never by mutation.
- Concurrency-safe — two `−20` deltas both count; no last-write loss.
- As-of-correct — `state(you,"gold", as_of=t)` sums only through `t`.

**Declaration & ergonomics.** Declaring an attribute `accrue` is cheap via
ATTRIBUTE-SEMANTICS-V1's mechanisms — a per-item hint or, for a live host,
the `attribute_default` hook ("currency/quantity attributes default
`fold_policy=accrue`"). A `delta` row on a **non-accrue** attribute is
dropped by the functional fold *before* the durability split (Codex r1 #5 —
otherwise `_fold_state` would treat the delta as a competing absolute value);
the engine never rejects it (the rejection-test guardrail — declarations and
types govern *folding*, never *admission*), it simply isn't summed until the
attribute is `accrue`. Hosts model a quantity as `accrue` from its first row
(the immutability rule means a functional attribute can't silently flip to
`accrue` after it has folded data — consistent and intended).

## 3. Phase 2 — numeric comparison predicates (Imp 2)

Retrieval over numeric values by `>= / > / <= / < / ==`, not just equality.
Today `value` is JSON text, so SQL equality works but ordering is
lexicographic (`"500" < "60"`) — wrong for numbers.

**Approach (Codex r1 #4 — fold-then-compare in Python, not SQL `CAST`).**
SQLite `CAST(value AS REAL)` casts non-numeric literals (`"abc"`, `true`,
`null`, objects) to `0.0`, so a `value_type` guard cannot keep them from
satisfying bounds near zero — the SQL approach is unsound. Instead the numeric
predicate **folds each candidate entity and compares the folded number in
Python**, where `isinstance(v, (int, float)) and not isinstance(v, bool)`
cleanly excludes non-numbers:
- candidate entities = those carrying the attribute (closure-scoped, via the
  existing indexed `visible(attribute=…)` retrieval — the 037 read path);
- for each, the comparison target is the **folded** value: `quantity` for an
  `accrue` attribute, else the functional fold's `winner.value`;
- keep only candidates whose folded value is numeric and satisfies the op.

**Porcelain:** a thin additive read verb `where(attribute, op, value, frame=,
as_of=)` → entity ids whose folded value satisfies the predicate
(`op ∈ >=,>,<=,<,==`). Single-entity affordability ("can I afford the
torch?") needs no new verb — read `state(you,"gold").quantity` and compare
host-side. No existing signature changes.

If the per-candidate fold proves a read-path cost at scale, a derived numeric
column (a generated column populated only for numeric values, NULL otherwise
— NULL never satisfies a bound) is the indexed optimization. Noted, not v1
unless a measurement demands it.

## 4. Authority / invariants
- **Append-only:** `delta` rows are ordinary appends; corrections are
  retractions. No mutation path.
- **No new authority:** deltas enter through the gate under the normal
  ingestor/observer roles.
- **Frozen porcelain:** additive only (`value_type='delta'`,
  `FoldResult.quantity`, `Materialization.quantities`, the `where` verb;
  `snapshot`/`state` payloads gain a `quantities`/`quantity` key without
  changing existing keys). Phase 2 needs **no** `visible()` signature change —
  it folds candidates and compares in Python.
- **Derive-don't-store:** the running total is *computed* by the fold, never
  authored; the ledger is the rows.
- **Rejection-test guardrail:** numeric typing/policy never rejects a fact.

## 5. Tests
- **The gold ledger:** declare `gold` accrue; `gold·500 (literal)`,
  `gold·-20 (delta)` → `state(you,"gold").quantity == 480`; the result's
  `_ledger_rows` is the 2-row ledger and `_value_rows` is empty (no ledger
  leak into snapshots); as-of before the spend → `500`.
- **Snapshot surfaces the total, not the deltas:** `snapshot([you])` reports
  `gold=480` via `quantities`, and the delta/literal rows do NOT appear in
  the fact list.
- **+/- composition:** `+500`, `+300`, `-20` with no absolute → `780`;
  retract the `-20` → `800` (correction via retraction, not mutation).
- **Concurrency:** two `-20` deltas at distinct asserted_at, same valid_from →
  sum both (no last-write loss).
- **int+float:** `liters·40000.0 (literal)`, `-1250.5 (delta)` → `38749.5`
  (float); pure-int ledger stays int.
- **delta on non-accrue attribute:** ignored by the functional fold, not
  rejected; declaring the attribute accrue first makes it sum.
- **Immutability:** a functional attribute with folded data can't be
  redeclared accrue (rejected at append) — consistent with
  ATTRIBUTE-SEMANTICS-V1.
- **frame_diff over accrue:** `gold` accrue, canon total 480 vs
  `knows:player` total 500 → `frame_diff` reports the `gold` key as differing
  (quantity 480 vs 500), and never reports a raw delta row.
- **ask over accrue:** `ask("how much gold?")` on an accrue key returns the
  **total** (480), not the last delta (-20).
- **Phase 2 predicates:** `where("gold", ">=", 100)` returns only entities
  whose folded quantity qualifies; non-numeric attributes never match a
  numeric bound; `as_of` respected.
- **Defaults-preserve:** full existing suite green with zero accrue
  declarations and no delta rows.

## 6. Out of scope
- Exact decimal / fixed-point money (documented limitation; later if needed).
- Arithmetic beyond sum (min/max/avg folds, multiplication) — not asked,
  not built.
- Cross-attribute formulas / derived computed fields — host concern.

## 7. Docs to update on ship (founder directive)
Once wired, reflect the nuances for future adopters:
- **HOST-DISCIPLINE.md:** add the quantity axis to ingestion (when to model a
  scalar `accrue` quantity vs enumerated set-valued members vs a plain
  functional literal) and to retrieval (`.quantity`, the ledger, `where`).
- **ADOPTION.md:** `value_type='delta'`, `FoldResult.quantity`,
  `Materialization.quantities`, the `where` verb, the int/float-yes /
  decimal-deferred note.
- **LEXICON.md:** `delta`, `accrue`, "quantity / ledger".
- **WHITEPAPER.md:** a short note in the operation-algebra / fold section that
  `accrue` is a fold policy summing signed deltas over a baseline (amendment
  if it touches a load-bearing claim).
