# AXIS-HEAD-V1 — `axis_heads()` + `ingest_structured(at=)` (the last two residues)

**Status:** Cx deliberation done (cross-frame coordinate-scalar AGREED; all-rows
AGREED; porcelain-only `at=` AGREED; 1 fix adopted: renamed `horizon()` →
`axis_heads()` — "horizon" already names the play/read cutoff; lexicon
one-name-per-concept) → SHIPPED (impl GREEN first pass, 419 green). Trigger (HD 095): after BUILD-SESSION,
exactly TWO sub-porcelain residues remain between the first host and
zero-internal integration. Both additive one-liners.

## Win 1 — `p.axis_heads() -> {"asserted_head": int, "valid_head": float | None}`
The two-axis high-water mark of the log, as one read.
- `asserted_head` = the log head (seq). `valid_head` = `MAX(valid_from)` over
  ALL rows, all frames (None when no timed rows exist).
- **Why cross-frame is correct, not a leak:** the caller's need (a scenario
  entry epoch that sits ABOVE every pre-play coordinate wherever it landed —
  HD's canon-only attempt under-raised when a seeded `knows:` row carried a
  higher coordinate) requires the global max by construction. The read serves
  a **coordinate scalar**, never content — no entity, attribute, value, or
  frame name crosses; "the world's story-time extends to X" is the same class
  of fact as the log length. (Deliberation: over ALL rows, matching the
  host's regression-tested `all_rows()` behavior — a retracted row still
  anchors the epoch monotonically and harmlessly — vs visible-only. Spec
  says all rows: simpler, monotone, matches the proven need.)
- Plumbing: `buffer.max_valid_from()` (one SQL aggregate), porcelain wraps.

## Win 2 — `ingest_structured(..., at=None)`
The per-chunk cursor placement, mirroring `ingest(at=)` exactly: porcelain
advances the scene cursor before delegating (`cursor.advance(at)`), so the
parallel-extract path (extract concurrently, commit serially per chunk
coordinate) never touches `ingestor.cursor`. No engine-layer change —
`ingest(at=)` already set this precedent at the porcelain layer.

## Non-goals
No per-frame horizon variants; no min/valid_to heads (no proven need); no
engine `ingest_structured(at=)` param (the porcelain owns the pose, as with
`ingest`).

## Tests
- `axis_heads()` on a fresh world: `{asserted_head: N, valid_head: None}` with
  only timeless rows; picks up the max across canon AND a knows: frame (the
  HD regression case); monotone after later ingest.
- `ingest_structured(items, at=7.0)` stamps un-timed rows from 7.0 (cursor
  pose), matching `ingest(at=)` semantics; default unchanged.
- Full suite green.
