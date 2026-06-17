# CONFIDENCE-MULTIFRAME-V1 — confidence over an observer's effective knowledge

**Status:** DRAFT → seeking Codex GREEN before implementation.
**Kind:** passive, additive read extension. Touches `confidence()` only; no
fold-path, schema, or write-path change. Computed at read, nothing stored
(the membrane — whitepaper A6).

## Why

`confidence()` (CONFIDENCE-V1) scores trust in one functional folded key from a
**single** frame. But an observer O's *effective* knowledge is not one frame —
it is the read-union of their own frame and the shared/public frame
(`knows:O ∪ public`), exactly the model we already built for multi-frame
`frame_diff` (#25) under the flat-frames + read-union doctrine (#24, A6). So an
observer's trust in a fact should be computable over that same union: a fact O
holds privately **and** sees corroborated publicly is more trustworthy than
either alone; a fact O believes privately that the public frame contradicts is
a conflicted belief.

This is the confidence sibling of multi-frame `frame_diff`. It is non-invasive
(a frame-list path inside one read) and contextually likely (the multi-NPC
effective-knowledge model is live), so it ships rather than waits.

## Shape

`frame` accepts `str | list[str]`, mirroring `frame_diff`'s `b: str | list[str]`.

- **`str` path: byte-for-byte unchanged.** Today's behavior, today's tests.
- **`list[str]` path:** confidence over the read-union of the listed frames.

A single-element (or fully-deduped-to-one) list `[f]` MUST reduce to exactly
`confidence(frame=f)` (the reduction invariant — a clean test anchor).
**Implementation guarantee (Codex r1):** a deduped single-frame list
**delegates to the str path** outright, so the reduction is byte-identical and
cannot drift from V1's `corroborated_by` accumulation.

## Algorithm (list path)

Reuses `fold_key` per frame; unions only at the scoring layer. No new fold.

0. **Degenerate lists.** An empty (or fully-deduped-empty) frame list names no
   knowledge → `_empty_confidence()` (never a canon read). A deduped
   single-frame list delegates to the str path.
1. **Per-frame fold.** Dedup the frame list (order-preserving). For each frame,
   `fold = fold_key(entity, attribute, frame, valid_as_of=as_of, asserted_as_of=...)`.
   Set-valued / accrue attributes return `_empty_confidence()` up front, same as
   V1 (functional-only).
2. **Effective winner.** Among per-frame folds with a non-None winner, the
   effective winner is the most-recent by `(valid_from or -inf, asserted_at)`.
   If no frame has a winner → `_empty_confidence()`.
3. **Conflict.** `conflicted = True` iff **either** any per-frame fold is itself
   `conflicted`, **or** two frames' winners carry non-equivalent values
   (strict, entity-resolved equivalence via the V1 `_confidence_values_equivalent`
   rule — NOT approximate-bounds agreement). As in V1, conflict halves the score.
4. **Provenance & recency.** Computed from the **effective winner**, identical
   to V1: provenance from `CONFIDENCE_PARAMS["provenance"]` floored by the
   winner's source-confidence clamped to `[0,1]`; recency `1/(1+age/scale)` where
   `age = ref - winner.valid_from`. When `as_of` is None, `ref` is the max
   `valid_from` over the closure rows visible in **any** listed frame (the union
   analogue of V1's single-frame closure reference).
5. **Corroboration.** Distinct `_source_class` values minus 1, counting only
   sources that attest the **effective served value** — never sources backing a
   *different* per-frame value (those are conflict, not corroboration; counting
   them would inflate trust in a contested value). Concretely the union of:
   (i) the strict cross-frame scan — the visible key rows of **all** listed
   frames whose value is strictly-equivalent to the effective winner (this
   recovers every agreeing frame's incumbents, exactly V1's recovery); plus
   (ii) the V1 loose-refinement `corroborated_by` rows of **only** the per-frame
   folds whose own winner is strictly-equivalent to the effective winner. This
   makes list-path corroboration a superset of the **effective frame's**
   single-frame corroboration (not of a frame that serves a different value),
   and cross-frame agreement raises trust as intended. (Source rows carry a
   single `frame` column, so the union is a clean set with no physical
   double-count.)
6. **Return** the same dict shape as V1:
   `{score, status, last_observed_at, corroboration, conflicted}` where `status`
   is the effective winner's status and `last_observed_at` its `valid_from`.

## Porcelain

`p.confidence(entity, attribute, frame=..., as_of=...)` — `frame` accepts
`str | list[str]`, pass-through. Return shape unchanged.

## Non-goals / invariants

- No stored multi-frame confidence (membrane). No precedence ordering among
  frames — union/OR semantics, identical to multi-frame `frame_diff` (private
  does NOT override public; disagreement is conflict, not silent override).
- Set-valued / accrue keys still return `score: None` (functional-only).
- Identity closure is current-head, the known engine-wide trait (documented in
  V1); unchanged here.

## Tests (invariants, not just returns)

1. Reduction: `confidence(e,a,frame=["knows:o"]) == confidence(e,a,frame="knows:o")`.
2. Cross-frame corroboration: same value in `knows:o` and `public` from distinct
   source classes → corroboration ≥ 1 and score strictly greater than either
   single frame alone.
3. Cross-frame conflict: `knows:o` says X, `public` says Y (non-equivalent) →
   `conflicted: True`, score halved.
4. Union recency: a fresh `public` observation lifts recency for an observer
   whose private fact is stale.
5. Absence: key absent in all listed frames → `_empty_confidence()`.
6. Membrane: the call writes nothing (assertion count unchanged across the call).
7. Set/accrue under a frame list → `score: None`.
