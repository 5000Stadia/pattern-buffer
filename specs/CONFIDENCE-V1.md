# CONFIDENCE-V1 — the confidence/freshness read (temporal trust, derived)

**Status:** SPEC, pre-Codex-GREEN. The deliberated "strong follow-on" (RFC-002
§4.2; ROADMAP-deferred C). A real-world tracker's beliefs **age** — "how sure
should I be of this *now*, given how it was observed, how recently, and whether
anything corroborates it?" Kernos's framing: **confidence = temporal salience**
— a *derived* read over present facts, **never stored** (the membrane-test).
**Whitepaper wins; read-layer only, additive, P7-bounded, derive-don't-store.**

## 1. What it addresses & why it passes the criterion
- **Reflexive need:** any tracker of a *changing reality* (an assistant world
  model, a long campaign) needs "is this still trustworthy?" — a stale or
  weakly-sourced fact should read as low-confidence without being deleted
  (validity ≠ confidence; the fact stays, the *trust* decays).
- **No overlap (anti-dilution):** distinct from `state` (raw value + provenance
  *chain*), from `salience` (how *relevant*, not how *trustworthy*), and from
  the unknown doctrine (this is about *held* facts, not absence). It synthesizes
  a trust *score* nothing else produces.
- **Shape-confidence:** the components are fixed by Kernos (provenance rank ×
  recency × corroboration); the weights are a pinned constant table (same
  approach as `salience`).

## 2. Shape — `confidence(entity, attribute, …)`

A new additive read (Indexes + World + Porcelain; LLM-free; derived, never
stored — computed on demand, closure-scoped, no sidecar in v1):
```
confidence(entity, attribute, frame="canon", as_of=None) -> dict
```
Operates on the **functional** fold winner for the key. Returns:
```
{ "score": <float 0..1>, "status": <provenance status>,
  "last_observed_at": <winner.valid_from>, "corroboration": <int>,
  "conflicted": <bool> }
```
- **`score`** = absolute-normalized weighted sum (pinned table):
  `0.45*provenance + 0.30*recency + 0.25*corroboration`, then **halved if
  `conflicted`** (a contested key is not trustworthy).
  - **provenance** — from `status`: `stated`/`observed`=1.0, `inferred`=0.6,
    `assumed`=0.3, `generated`=0.4, `default`=0.0; floored by the row's
    `confidence` field when present (source-confidence-at-assertion — the
    irreducible provenance input, RFC-002 §4.2).
  - **recency** — `winner.valid_from` vs a reference time `ref` (= `as_of` if
    given, else the max `valid_from` in the entity's closure — the entity's
    "current time"); normalized so newer → higher (e.g.
    `1 / (1 + (ref - valid_from)/RECENCY_SCALE)`); `1.0` for a timeless winner.
  - **corroboration** — count of independent agreeing rows on the key
    (`FoldResult.corroborated_by` + same-value visible rows across distinct
    source classes), log-scaled (`log1p(n)/log1p(CORROB_SCALE)`).
- **`last_observed_at`** = the winner's `valid_from` — the host computes
  staleness/age against *its own* clock (the engine doesn't presume a global
  "now" beyond the closure's latest fact; freshness is the host's reference,
  the doctrine's "staleness is derived, never stored").
- **`conflicted`** = the fold's flag (passed through).

Weights + scales live in one module constant table, tunable, documented.

**v1 scope:** functional keys only. **Set-valued and accrue confidence are
deferred** (different semantics — per-member / over-the-ledger — and no
demonstrated need; ROADMAP-deferred). A non-functional or absent key returns
`{"score": None, ...}` (honest "no single value to score").

## 3. Invariants
- **Derive-don't-store / membrane (A6):** computed from present facts, never
  written to the log; no `confidence: 0.6` *current-belief* row is ever
  authored. (The stored `confidence` *field* is the source-confidence input,
  not this derived output — RFC-002 §4.2.)
- **Validity untouched:** `confidence` never changes what `state` serves; a
  three-campaign-years-stale fact has low confidence and *full* validity.
- **Frozen porcelain:** `confidence` is a new additive verb; no existing
  signature/payload changes.
- **P7 bounded:** deterministic, closure-scoped, LLM-free, fixed formula.

## 4. Tests
- A `stated`, recent, multi-source-corroborated fact → high score.
- An `assumed`, old, single-source fact → low score.
- A `conflicted` key → `conflicted: true` and a halved score.
- `last_observed_at` = the winner's `valid_from`; a timeless winner → recency
  `1.0`.
- `confidence` never alters `state`/`snapshot` output (separate read).
- Derived: no log writes; rebuild-independent (it reads the log fresh).
- Functional-only: a set-valued/accrue/absent key → `score None`.
- Defaults-preserve: full suite green.

## 5. Out of scope
- Set-valued / accrue confidence (per-member / ledger) — deferred.
- A stored or decaying confidence *fact* — forbidden (membrane).
- An explicit freshness-horizon verb (`fresh_within(H)`) — thin variant;
  `last_observed_at` + the host clock covers it; add only on demonstrated need.

## 6. Docs on ship
HOST-DISCIPLINE.md (confidence as the trust read; staleness = host computes age
from `last_observed_at`); ADOPTION.md (`confidence`); LEXICON.md (`confidence`).
