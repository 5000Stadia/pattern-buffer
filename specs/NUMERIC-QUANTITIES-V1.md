# NUMERIC-QUANTITIES-V1 — numeric quantities: change them, compare them

**Status:** SPEC, pre-Codex-GREEN. Merges the founder-ruled Imp 2 (value
typing / comparison predicates) and #20 (the `accrue` delta-counter) into one
coherent "numbers" capability, wired on **both** sides (engine + data
structure), per the founder's direction. **Whitepaper wins; a refinement
within P1/P2.** Composes with ATTRIBUTE-SEMANTICS-V1 (the `accrue`
`fold_policy` it reserved is lit up here).

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
  schema change). `entity`/`literal`/`unresolved` are untouched.

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

**Fold algorithm** (deterministic, append-only, as-of-correct):
1. Gather visible candidates for the key (filtered by frame/valid_as_of/
   asserted_as_of as every fold is).
2. `baseline` = the latest **absolute literal** numeric row by
   `(valid_from, asserted_at)`, or value `0` if none.
3. `contributing` = every **delta** row strictly after the baseline in
   `(valid_from, asserted_at)` order (all deltas if no baseline).
4. `total = baseline.value + sum(d.value for d in contributing)`.

**FoldResult** gains **`quantity: int | float | None`** (additive; populated
only for `accrue` keys). `winner` = the most-recent contributing row (for
provenance: when/who last changed it); `_value_rows` = the full ledger
(baseline + contributing) so a host can render the transaction history.
`functional`/`set_valued` keys leave `quantity=None` (unchanged).

**Properties this buys (the gold pouch):**
- Deterministic — the engine sums; the model never does mental math.
- Append-only ledger — every find/spend is one row; `_value_rows` is the
  auditable history; a wrong entry is fixed by retracting it (excluded by
  `visible()`), never by mutation.
- Concurrency-safe — two `−20` deltas both count; no last-write loss.
- As-of-correct — `state(you,"gold", as_of=t)` sums only through `t`.

**Declaration & ergonomics.** Declaring an attribute `accrue` is cheap via
ATTRIBUTE-SEMANTICS-V1's mechanisms — a per-item hint or, for a live host,
the `attribute_default` hook ("currency/quantity attributes default
`fold_policy=accrue`"). A `delta` row on a **non-accrue** attribute does not
contribute to that attribute's functional fold (it is not an absolute value);
the engine never rejects it (the rejection-test guardrail — declarations and
types govern *folding*, never *admission*), it simply isn't summed until the
attribute is `accrue`. Hosts model a quantity as `accrue` from its first row
(the immutability rule means a functional attribute can't silently flip to
`accrue` after it has folded data — consistent and intended).

## 3. Phase 2 — numeric comparison predicates (Imp 2)

Retrieval over numeric values by `>= / > / <= / < / ==`, not just equality.
Today `value` is JSON text, so SQL equality works but ordering is
lexicographic (`"500" < "60"`) — wrong for numbers.

**Approach:** extend `PatternBuffer.visible()` with optional numeric bounds
(`value_gte` / `value_gt` / `value_lte` / `value_lt`), implemented in SQL with
a numeric interpretation of `value` guarded to numeric rows
(`value_type IN ('literal','delta')` + `CAST(value AS REAL)` compare). A
non-numeric value never satisfies a numeric bound. For an `accrue` attribute,
the *predicate target is the folded `quantity`*, not raw rows — so a
multi-entity numeric query folds per candidate then compares (closure-scoped,
like the 037 read path), rather than matching individual delta rows.

**Porcelain:** a thin additive read verb `where(attribute, op, value, frame=,
as_of=)` → entity ids whose folded value satisfies the predicate. (Single-
entity affordability — "can I afford the torch?" — needs no new verb: read
`state(you,"gold").quantity` and compare host-side.) No existing signature
changes; `where` and the `visible()` kwargs are additive.

If numeric indexing proves a read-path cost at scale, a derived numeric
column (SQLite generated column) is the optimization — noted, not v1 unless a
measurement demands it.

## 4. Authority / invariants
- **Append-only:** `delta` rows are ordinary appends; corrections are
  retractions. No mutation path.
- **No new authority:** deltas enter through the gate under the normal
  ingestor/observer roles.
- **Frozen porcelain:** additive only (`value_type='delta'`,
  `FoldResult.quantity`, `where`, numeric `visible()` kwargs).
- **Derive-don't-store:** the running total is *computed* by the fold, never
  authored; the ledger is the rows.
- **Rejection-test guardrail:** numeric typing/policy never rejects a fact.

## 5. Tests
- **The gold ledger:** declare `gold` accrue; `gold·500 (literal)`,
  `gold·-20 (delta)` → `state(you,"gold").quantity == 480`; `_value_rows` is
  the 2-row ledger; as-of before the spend → `500`.
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
- **ADOPTION.md:** `value_type='delta'`, `FoldResult.quantity`, `where`, the
  numeric `visible()` kwargs, the int/float-yes / decimal-deferred note.
- **LEXICON.md:** `delta`, `accrue`, "quantity / ledger".
- **WHITEPAPER.md:** a short note in the operation-algebra / fold section that
  `accrue` is a fold policy summing signed deltas over a baseline (amendment
  if it touches a load-bearing claim).
