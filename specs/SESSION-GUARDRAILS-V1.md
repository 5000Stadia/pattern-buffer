# SESSION-GUARDRAILS-V1: deferred classification still applies the guardrails, and a failed seal closes the session

**Status:** r1.1, answering pbr's r1 RED: one end-of-call hook over every row the call appended, by log position; and the failed-seal test raises from the pass itself, with the classifier's own fallback unchanged. For pbr review. Author: pb, 2026-10-13. An engine change, small.
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
- **One end-of-call hook** *(r1.1, pbr)*. Rows reach the log through several writers, not only
  `_ingest_item` step 13:
  - the registry's `add_alias` (the `aliases` side key);
  - the `maybe_same_as` edge and its evidence;
  - the §12 side rows (`source_valid_from`, `canonicalized_from`, `correction_proposal`,
    `learned_at_wallclock`, `derived_by`, `reclassified_from`, `source`);
  - `_declare`.

  So the hook doesn't sit at each writer. At the **end of every ingest call**
  (`ingest_structured`, `ingest`, `commit_set` and the porcelain paths that call them), when
  classification for that call was **neither inline nor collected for a per-call batch**, the
  ingestor runs `classify_if_guarded(row)` on **every row appended during the call**: every row with
  `seq` in `(head before the call, head after it]`, whatever wrote it.
  - Rows already classified are skipped.
  - Inline and per-call `batch`/`rules` behaviour is unchanged. Those rows are classified already,
    or collected.
  - A guardrail-decided row is therefore classified by the time the call returns. An ambiguous row
    stays unclassified until the seal, `classify_all` or `classify_rows`, exactly as today.
  - An ingest call that raises classifies nothing further. Rows its atomic unit appended are rolled
    back by the existing atomic path; anything left stands as today.
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

- **The classifier's own failure contract is unchanged** *(r1.1, pbr)*. A model error inside
  `_ask_model` or `_classify_batch` is caught there and gives the asymmetric fallback verdicts, and
  the seal returns `sealed`. This spec doesn't touch that.
- **Exceptions that do escape.** What can reach `seal_build` is an exception that propagates out of
  the pass itself (from `classify_rows`, the sidecar store, or anything other than the model call
  the classifier already guards).
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
   - *(r1.1, pbr)* an item with an `aliases` side key: its `alias` rows, written by `add_alias`, are
     classified before the seal;
   - *(r1.1)* an item that produces a META side row (`source` via `source_doc`, or
     `canonicalized_from` via an aliased attribute) has that row classified before the seal;
   - an ambiguous domain row is not classified before the seal, and is classified at it;
   - the seal makes no model call for the guardrail rows.
2. **`classify="defer"` and the harness toggle** (`classify_inline = False`): guardrail rows are
   classified at ingest, ambiguous rows are not, and `classify_all` finishes them.
3. **Same verdicts:** a fixture ingested deferred and then sealed gives byte-identical classifier
   verdicts to the same fixture before this change. Compare verdict tables, not counts.
4. **A failed seal** *(r1.1)*:
   - `classify_rows` monkeypatched to raise during `seal_build` re-raises that exception;
   - separately, a model that raises during `seal_build(model=True)` still seals (the classifier's
     fallback, unchanged), with the fallback verdicts;
   - afterwards no session is open, `classify_inline` is restored, a new `begin_build` succeeds,
     and the unreached rows are unclassified;
   - a following `classify_all` classifies them.
5. **The sugar:** `with p.build(model=True):` whose seal raises leaves no session open.
6. Full suite green. The chapter-test and ingestion-fidelity numbers are unchanged, since the
   verdicts are identical.
