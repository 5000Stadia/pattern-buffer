# SESSION-GUARDRAILS-V1: deferred classification still applies the guardrails, and a failed seal closes the session

**Status:** r1, for pbr review. Author: pb, 2026-10-13. An engine change, small.
**Source:** a status letter from construct's reviewer, on turn-time use of BUILD-SESSION-V1
(construct's TURN-CLASSIFY-ONCE): a seal-failure state leak, and a question about immediate
guardrails. pb's earlier advice to construct (m151ce5) wrongly said guardrail rows are classified
inside a session. Corrected in ma17d94.
**Builds on:** BUILD-SESSION-V1 (`begin_build`, `seal_build`, `abort_build`), INGEST-LATENCY-V2
(`classify="defer"`), the classifier's guardrails (`classify.py` `_guardrails`).

## Need

1. **When classification is deferred, nothing is classified until the seal.** That covers an open
   build session, the harness's `classify_inline = False`, and `classify="defer"`.
   - It includes rows whose class a guardrail fixes with zero model calls: deltas, events,
     `caused_by`, names and aliases, META, the containment and structural predicates, pinned
     durabilities, and the other deterministic short-circuits.
   - A host that reads its own new rows before the seal sees them unclassified. Construct reads
     its movement rows (`locate`) mid-turn, and that works today only because unclassified rows read
     as STATE.
2. **A failed seal leaves the session open.** `seal_build` restores `classify_inline` and clears
   the session only after `classify_rows` returns. If `classify_rows` raises (a model error with
   `model=True`), the session stays open and the next `begin_build` raises. The caller must know to
   call `abort_build`.

## The shape

### 1. Guardrails at ingest when classification is deferred

- **A new public classifier method.** `Classifier.classify_if_guarded(row) -> Classification |
  None` applies `_guardrails(row)`.
  - When a guardrail decides, it stores and returns the same `Classification` that `classify` or
    `classify_rows` would store for that row.
  - Otherwise it returns `None` and stores nothing. It never calls the model.
- **Ingest's classification step** (`_ingest_item` step 13, and the side-row path at `ingest.py`
  ~669) changes in one case: when the row is **not** classified inline, and **not** collected for a
  per-call batch.
  - It calls `classify_if_guarded(row)`.
  - A guardrail-decided row is therefore classified at ingest. An ambiguous row stays unclassified
    until the seal, `classify_all` or `classify_rows`, exactly as today.
- **Same verdicts, written earlier.** The guardrails are deterministic and `classify_rows` skips
  already-classified rows, so every row ends with the same verdict as before; only the moment
  differs.
  - A seal's or `classify_all`'s returned `classified` count may be lower, because those rows were
    classified already.
- **Unchanged:**
  - inline classification, and per-call `classify="batch"` or `"rules"` (they already classify at
    the call);
  - the guardrails themselves;
  - every receipt except the counts above.

### 2. A failed seal closes the session

- `seal_build` runs its classification pass in `try … finally`.
  - The `finally` restores `classify_inline` and clears the session (`_build_head`,
    `_build_prev_inline`) whether the pass returned or raised.
  - The exception is re-raised unchanged.
- **Rows the pass didn't reach stay unclassified.** A later `classify_all` or `classify_rows` can
  finish them. Nothing is rolled back, since the log is append-only and the sidecar verdicts
  already stored stand.
- `BUILD-SESSION-V1`'s `with p.build(...)` sugar keeps its behaviour. It already restores on an
  exception in the body, and now also when the seal itself fails.

## Not in this spec

- Sending fewer rows to the model, batch sizes, effort. Construct is measuring effort separately.
- Any change to the guardrails' content.

## Tests

1. **In a session:**
   - a `name` row, a delta, an event row and a containment row ingested inside `begin_build` are
     classified before the seal, with the same verdict `classify` would give;
   - an ambiguous domain row is not classified before the seal, and is classified at it;
   - the seal makes no model call for the guardrail rows.
2. **`classify="defer"` and the harness toggle** (`classify_inline = False`): guardrail rows are
   classified at ingest, ambiguous rows are not, and `classify_all` finishes them.
3. **Same verdicts:** a fixture ingested deferred and then sealed gives byte-identical classifier
   verdicts to the same fixture before this change. Compare verdict tables, not counts.
4. **A failed seal:**
   - a model that raises during `seal_build(model=True)` re-raises;
   - afterwards no session is open, `classify_inline` is restored, a new `begin_build` succeeds,
     and the unreached rows are unclassified;
   - a following `classify_all` classifies them.
5. **The sugar:** `with p.build(model=True):` whose seal raises leaves no session open.
6. Full suite green. The chapter-test and ingestion-fidelity numbers are unchanged, since the
   verdicts are identical.
