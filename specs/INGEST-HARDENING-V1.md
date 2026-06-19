# INGEST-HARDENING-V1 — batched durability + edge-granular cycle rejection

**Status:** DRAFT → Cx GREEN before implementation. Additive/robustness on the
ingest path. Two independent improvements relayed by Kernos (070) from Construct's
profiling (074 §2). Both mesh-steered; no founder-preference fork (Kernos delegated
the porcelain-surface choice to PB).

## Part A — batch durability classification per ingest call (the matured shape)
**Finding (measured):** inline per-row classification was **~65% of build time**
(~400 model calls/1327s); the supported `classify_inline=False` + batched
`classify_all` cut it to ~17 calls/198s (build ~35→14 min). Per-row inline is the
anti-pattern; **boundary-batched is the matured default** (Kernos: same principle as
the fact-harvest's boundary-batching).

**Change — a first-class OPT-IN batched mode (NOT a default flip).** Cx review (RED)
established two reasons the default must not flip: (1) `_reject_cycle` walks
`locate → fold_key`, which **reads durability mid-loop** — so deferring
classification to end-of-call would make a later item's cycle check read earlier
same-call containment rows as unclassified (STATE not CONSTITUTIVE), a silent
semantics change for the default path; (2) the test `StubModel`/
`rule_classifier_fallback` only emit the per-row schema, not the batch `verdicts`
schema. So:
- **Default unchanged:** `classify_inline=True` stays per-row inline. Zero blast
  radius on existing callers/tests/evals.
- **New first-class mode:** `p.ingest_structured(items, classify="batch")` — defers
  per-row classification during the call and runs **one** `_classify_batch` over the
  call's model-needing rows at the end (guardrail rows still resolve with zero model
  calls). This is the clean surface for the value Construct already proved with the
  manual `classify_inline=False` + `classify_all` recipe (~65% build-time cut) —
  collapsed into one call. `classify="inline"` (default) and `classify="defer"`
  (the harness whole-build path, unchanged) are the other two values.
- **Cycle guard under batch — inherits the defer residual exactly (Cx re-review).**
  Batch mode IS the validated `classify_inline=False` defer path (auto-batched at
  end-of-call), so it inherits that path's documented behavior, no stronger: the
  **self-edge guard is durability-independent and always fires** (skips), and a
  cycle whose ancestors are already classified is caught at write-time; a same-call
  **transitive** cycle among as-yet-unclassified rows may slip the write-time walk
  (STATE-folded containment) and is caught by the **read-time `locate()` guard** —
  identical to the harness build today. The spec makes **no** stronger same-call
  transitive-cycle guarantee for batch than the shipped defer path provides.
- **Test double:** extend `StubModel`/`rule_classifier_fallback` to also answer the
  batch `verdicts` schema (per-row equivalents), so the batch path is testable.
- Factor `classify_all`'s guardrail-split-then-batch loop into a shared
  `_classify_rows(rows, batch_size=None)` used by both `classify_all` and the new
  batch ingest; preserve `classify_all(None)` per-row semantics exactly.

## Part B — edge-granular cycle rejection (skip the edge, not the chunk)
**Today:** `_reject_cycle` (containment cycle / self-edge) and the lateral-self-loop
guard **raise `ValueError`**, which aborts the **entire** `ingest_structured` call —
one bad edge discards every good row in the chunk. Construct added a host-side
per-chunk fail-open stopgap.

**Change (Kernos steer — fail per-unit, never the batch; "no silent caps"):** the
engine **skips the single offending edge** with a warning and a **typed receipt**,
and ingests the rest of the chunk.
- The three edge guards (containment cycle, containment self-edge, lateral
  self-loop) no longer raise; the offending row is **not appended** (the invariant
  holds — no cycle/self-loop enters the log), a `logger.warning` is emitted, and a
  structured skip record is collected.
- **Surfacing (no silent cap):** a typed internal `SkipRecord` is collected;
  porcelain `p.ingest_structured` returns them in its Receipt as a **new additive
  `skipped: [{entity, attribute, value, reason}]`** field (not overloaded onto
  `warnings` — Cx note). The engine-level `ingest_structured` **keeps returning
  `list[Assertion]`** (internal callers index it — `refer.py`); the skip records are
  exposed via a `last_skipped` accessor **reset at the start of every
  `ingest_structured` call** (Cx note).
- **Tests to update:** the existing tests that assert `ValueError` for self-edge /
  transitive cycle / lateral self-loop / deferred self-edge (`tests/test_world.py`
  ~78/89/101/150) move to asserting the skip-record + that the good rows landed.
- Only these **structurally-invalid single edges** are skipped — every other gate
  failure (bad role/authority, generated-into-canon, unknown value_type) still
  raises; this is not a blanket swallow.

## Non-goals
- No change to the cycle/self-loop **invariant** (still enforced — just edge-granular).
- No change to default reads, the role matrix, or any fold semantics.
- The whole-build `classify_all(batch_size)` harness path is unchanged.

## Tests
**Part A:** `p.ingest_structured(items, classify="batch")` over N model-needing rows
triggers **one** batch model call (assert call count via a counting stub) with all
rows classified on return; `classify="inline"` (default) is unchanged (per-row);
a same-call **self-edge** is still skipped under `classify="batch"` (durability-
independent guard); batch matches the **defer path's** residual for transitive
cycles (no stronger guarantee — read-time `locate()` is the backstop, as today);
`StubModel` answers the batch schema; full suite green (default path untouched).
**Part B:** a chunk with one cycle-forming edge + several good rows → the good rows
are ingested, the cycle edge is skipped, the skip is reported in the porcelain
Receipt (`reason` names the cycle), and `locate`/`contents` show no cycle; self-edge
and lateral-self-loop likewise skip-not-raise; a genuinely fatal gate error (e.g.
generated-into-canon) **still raises**.
