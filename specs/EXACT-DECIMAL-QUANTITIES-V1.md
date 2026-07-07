# EXACT-DECIMAL-QUANTITIES-V1 — exact money without a float membrane

**Status:** SHIPPED — Cx shape deliberation (5/5 decisions settled) → spec GREEN →
impl reviewed to GREEN (2 RED passes: float-grouping byte-identity, payload
completeness). Additive
on NUMERIC-QUANTITIES-V1. **Default reads unchanged** — a world that never ingests a
decimal value is byte-identical (regression-locked). This is the one *likely-problem*
proactive fix under elegance-first: fiction quantities (HP, coins, distance) are fine as
floats, but the moment a world tracks **real money or any exact ledger**, float accrual is
silently lossy (`0.1 + 0.2 → 0.30000000000000004`) and corrupts the derived quantity
irreversibly across a long delta chain.

## The problem, precisely
The engine stores values as JSON and folds accrue attributes by summing them
(`indexes._fold_accrue`; member rollup `sum`/`avg` at `indexes.py:1029-1039`). JSON numbers
round-trip through Python `float`, and `float` addition is not exact. The loss is **not** in
single-value storage (JSON round-trips `0.1` faithfully) — it is in the **fold arithmetic**.
So the fix gives accrue an *exact* number type end to end, without imposing it on the 99% of
quantities that are happily float.

## Cx shape deliberation — the 5 settled decisions
1. **In-band tag, not `value_type="decimal"`** (Cx AGREE). `delta` is already a `value_type`,
   so a decimal *delta* couldn't also be marked; the in-band tag marks literal and delta
   **uniformly**. Reserved key `$decimal`, **finite-Decimal-only**, collision-guarded (below).
2. **Decimal+float MIXING RAISES** (Cx CHANGE, adopted). Silent float→Decimal promotion hides
   an authoring smell in an append-only ledger. `Decimal + int` is fine; any `float`
   coexisting with any `Decimal` in one fold/rollup **raises** with the offending row/entity
   ids. (No silent coercion. `Decimal(str(x))`, never `Decimal(x)`, only if a future explicit
   migration utility is ever built.)
3. **Explicit local Decimal context** (Cx CHANGE, adopted). The ambient context is
   process-mutable → a P7 determinism hazard. All Decimal fold/rollup arithmetic runs inside a
   fixed `localcontext` (below), so builds are byte-identical across CPython builds/platforms
   (Decimal is the platform-independent General-Decimal spec *given a fixed context*).
4. **Complete boundary audit** (Cx CHANGE, adopted). The naive list was incomplete; §2 below
   is the exhaustive list, split into internal-json sites (fixed by a codec `default=`/
   `object_hook=`) and outbound Python-object payloads (fixed by explicit `encode_out`).
5. **Core returns raw Decimal; porcelain pre-encodes** (Cx CHANGE, adopted). The frozen
   PORCELAIN-V1 contract promises plain-JSON payloads, so every porcelain- and
   neighborhood-facing payload carries the **tag dict**, never a raw Decimal.

## The codec (new `codec.py`)
```
_DEC_TAG = "$decimal"                         # reserved key, documented in LEXICON

def encode_value(v):                          # in-memory -> JSON-safe (one leaf)
    if isinstance(v, Decimal): return {_DEC_TAG: str(v)}
    return v

def decode_value(v):                          # JSON-safe -> in-memory (one leaf)
    if isinstance(v, dict) and set(v) == {_DEC_TAG} and _is_finite_dec_str(v[_DEC_TAG]):
        return Decimal(v[_DEC_TAG])
    return v

def encode_out(obj):                          # recursive: encode Decimal leaves in a payload
    # walks dict/list/tuple, applies encode_value to scalars; for porcelain/neighborhood out

def json_default(o):                          # json.dumps(default=...) hook
    if isinstance(o, Decimal): return {_DEC_TAG: str(o)}
    raise TypeError(...)

def decode_hook(d):                           # json.loads(object_hook=...) — reconstruct tag
    return decode_value(d)
```
- `str(Decimal("12.50"))` preserves the trailing zero and is the exact, deterministic
  serialization — **no float ever touches the number.** `sort_keys` keeps the one-key tag dict
  byte-stable.
- **Collision guard:** decode reconstructs *only* a dict that is exactly `{$decimal: s}` where
  `s` parses as a **finite** Decimal (rejects `"NaN"`/`"Infinity"` and non-numeric strings). A
  host literal dict with other keys, a multi-key dict, or a non-finite/non-decimal string
  passes through untouched. The tag key is reserved in the lexicon.

## §2 — the exhaustive boundary list
**Internal `json.dumps` (add `default=json_default`):**
- `buffer._insert` (`buffer.py:157`), `buffer.visible` value-match (`buffer.py:248`),
  `dump.dump` (`dump.py:47`), `classify._ask_model` prompt (`classify.py:139`),
  `classify._classify_batch` listing (`classify.py:265`), `thunks` constraint string
  (`thunks.py:241`).

**Internal `json.loads` (add `object_hook=decode_hook`):**
- `buffer` row read (`buffer.py:282`), `dump.build` (`dump.py:76`).

**Ingest normalize:** `ingest._ingest_item` (`ingest.py:378`) — `value = decode_value(item["value"])`
so a JSON-origin host may pass the tag form and an in-process host may pass a real `Decimal`;
both normalize to Decimal internally (symmetric).

**Outbound Python-object payloads (wrap in `encode_out`):**
- porcelain `_fact` / `_quantity_fact` (`porcelain.py:113,123`), and the aggregate,
  `frame_diff`, `ask`, `neighborhood` return payloads.
- porcelain `snapshot` quantities (`porcelain.py:243`), `state` top-level quantity
  (`porcelain.py:265`), `state_union` top-level quantity (`porcelain.py:413`),
  `events` values (`porcelain.py:477-483`), and the `divergent`/`b_value` fields
  in quantity diffs (`porcelain.py:595`).
- indexes `_fact_payload` (`indexes.py:1162`), `_state_payload` quantities
  (`indexes.py:1194`), and `route` evidence payloads (`indexes.py:1497`) — these
  dict payloads are host-facing and must carry the tag, not raw Decimal.
- **Rule of completeness:** any porcelain/neighborhood public return is
  `encode_out`-wrapped at the return statement (one wrapper per verb), not
  per-field — so a future field can't silently leak a raw Decimal.

No schema/DDL change (the value column is already JSON text).

## §3 — numeric recognition & types
- `Indexes._is_numeric` and `Porcelain._is_numeric` (`indexes.py:173`, `porcelain.py:143`):
  `isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)`.
- Type hints widened to include `Decimal`: `FoldResult.quantity` (`indexes.py:70`), the aggregate
  `values`/result (`indexes.py:1013`), `Materialization.quantities` (`project.py:55`),
  `_quantity_fact.quantity` (`porcelain.py:126`), `baseline_value` in `_fold_accrue`
  (`indexes.py:631`), and the quantity-diff numeric annotation (`porcelain.py:595`).
- `_values_agree` (`indexes.py:157`): make the approximate-bound branch Decimal-aware — when
  `new` is Decimal, coerce the bound via `Decimal(str(bound))` **for the comparison only**
  (a read-time comparison, never a stored ledger sum), so a Decimal refinement of an approx
  bound doesn't spuriously `TypeError`. Widen the `isinstance(new, (int,float))` guard to include
  Decimal.

## §4 — exact fold arithmetic (the mixing rule + context)
A shared helper centralizes the rule for both `_fold_accrue` and the member rollup.
**The mix check runs on the contributing value set BEFORE any op** — `sum`, `avg`,
`min`, `max` all validate (a mixed `min` comparison is the same authoring smell;
`count` needs no arithmetic but the rollup validates once up front for all ops):
```
_MONEY_CTX = decimal.Context(prec=50, rounding=ROUND_HALF_EVEN)

def _exact_sum(values, *, ids):               # values: mix of int/float/Decimal
    if any(isinstance(v, Decimal) for v in values):
        if any(isinstance(v, float) for v in values):
            raise ValueError("accrue mixes exact-decimal and float quantities; "
                             "pick one representation " + <offending ids>)
        with localcontext(_MONEY_CTX):
            return sum((Decimal(v) if isinstance(v, int) else v for v in values), Decimal(0))
    return <existing int/float sum, unchanged>
```
- **all-float** fold → the existing path, byte-identical (Decimal branch never entered).
- **all-Decimal / Decimal+int** → exact within `prec=50` (ample for money; `int` promotes
  losslessly).
- **Decimal+float** → raises with ids (authoring smell surfaced, not silently corrupted).
- `_fold_accrue`: `baseline_value` default `0` (int) composes cleanly; run the
  `baseline + Σdeltas` through `_exact_sum`.
- Rollup `avg` = `_exact_sum(values)/count` under `_MONEY_CTX` (ROUND_HALF_EVEN) — division is
  the one inherently-rounding op; precision+rounding are named/deterministic and documented.
  `min`/`max`/`sum`/`count` are exact.

## §5 — host-facing (ADOPTION note, no engine write)
Stored/dumped decimals and every porcelain/neighborhood payload carry the tag dict
`{"$decimal":"12.50"}` — plain-JSON-safe, contract-preserving. A host reads it back as a tagged
scalar (or `decode_value`s it to a `Decimal`). **`visible(value=…)` match is scale-sensitive:**
`Decimal("12.5")` does **not** match a stored `Decimal("12.50")` — authored scale is preserved
(append-only fidelity), so a value query must supply the authored scale. Documented in
ADOPTION + LEXICON.

## Non-goals (the over-complication line)
- No `value_type="decimal"`; no arbitrary-currency/unit system (unit + rounding *policy* is host
  meaning over frames); no global Decimal default (fiction floats stay floats); no
  fixed-precision/scale *enforcement* at ingest (append-only fidelity — the engine neither rounds
  nor pads authored input).

## Tests (assert invariants, not just returns)
- **Exactness:** baseline `Decimal("0.10")` + delta `Decimal("0.20")` folds to exactly
  `Decimal("0.30")` (float path gives `…04`).
- **Long chain:** 1000 deltas of `Decimal("0.01")` → exactly `Decimal("10.00")`.
- **Round-trip:** a Decimal literal survives `dump`→`build` byte-identical and reads back as
  `Decimal` with the same `str()` (trailing zeros preserved).
- **Ingest symmetry:** `{"$decimal":"12.50"}` and Python `Decimal("12.50")` produce the same
  stored row.
- **Mix raises:** Decimal baseline + float delta **raises** (ids in message); Decimal + int
  works.
- **Collision guard:** `{"$decimal":"x","note":1}`, `{"$decimal":"NaN"}`, `{"$decimal":"hi"}`
  round-trip untouched (never coerced to Decimal).
- **Context determinism:** avg over Decimals is HALF_EVEN to `_MONEY_CTX`; the same inputs give
  the same bytes; ambient-context mutation before the call does not change the result.
- **Default unchanged:** an all-float accrue world and a no-decimal dump are byte-identical to
  pre-change (regression lock).
- **Contract:** a porcelain snapshot / neighborhood / aggregate / frame_diff / ask payload
  containing a decimal is `json.dumps`-able with **plain** json (tag dict present, no raw
  Decimal); classifier ingest of a Decimal baseline doesn't crash the prompt serialization.
- Full suite green; every default (non-decimal) path byte-unchanged.
