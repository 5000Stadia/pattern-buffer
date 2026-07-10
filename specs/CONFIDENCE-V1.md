# CONFIDENCE-V1 — the confidence/freshness read (temporal trust, derived)

> **AMENDED by TRACKING-MODE-V1 (2026-07, founder ruling):** the recency component no longer decays with story time. In non-tracking worlds (`invent_under_canon`, `deny`) recency is PERMANENT (1.0 — the page is true; story-time liveness is salience's axis, not trust's). In `observe_or_unknown` worlds recency = `2**(−max(0, now − last_confirmed_at_wallclock)/half_life)` under the declared `DecayPolicy`, with fail-closed `unconfigured`/`unconfirmed` null branches (recency excluded + weights renormalized). The payload gains `recency`, `recency_status`, `last_confirmed_at_wallclock` on every result. Example (tracking, configured): `{score: 0.62, status: "observed", last_observed_at: 400.0, corroboration: 0, conflicted: false, recency: 0.5, recency_status: "configured", last_confirmed_at_wallclock: 5000.0}`. Example (fiction): `{…, recency: 1.0, recency_status: "permanent", last_confirmed_at_wallclock: null}`.

**Status:** SHIPPED (Codex r1 GREEN; corroboration pinned as de-duplicated distinct source classes; amended by TRACKING-MODE-V1 — see banner). The deliberated "strong follow-on" (RFC-002
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
confidence(entity, attribute, frame="canon", as_of=None, now=None) -> dict
```
(`now`, added by TRACKING-MODE-V1, is a **wall-clock** reference for tracking
worlds — defaults to the world clock; it is never a valid-time `as_of`, and a
non-finite `now` raises.) Operates on the **functional** fold winner for the
key. Returns:
```
{ "score": <float 0..1>, "status": <provenance status>,
  "last_observed_at": <winner.valid_from>, "corroboration": <int>,
  "conflicted": <bool>,
  "recency": <float 0..1 | null>,
  "recency_status": <"permanent"|"configured"|"unconfigured"|"unconfirmed">,
  "last_confirmed_at_wallclock": <finite float | null> }
```
(the last three fields are the TRACKING-MODE-V1 additive amendment; every
result shape — including empty/set-valued/accrue — carries them.)
- **`score`** = absolute-normalized weighted sum (pinned table):
  `0.45*provenance + 0.30*recency + 0.25*corroboration`, then **halved if
  `conflicted`** (a contested key is not trustworthy).
  - **provenance** — from `status`: `stated`/`observed`=1.0, `inferred`=0.6,
    `assumed`=0.3, `generated`=0.4, `default`=0.0; floored by the row's
    `confidence` field when present (source-confidence-at-assertion — the
    irreducible provenance input, RFC-002 §4.2).
  - **recency** — **mode-scoped (TRACKING-MODE-V1 amendment; the original
    story-time formula `1/(1 + (ref − valid_from)/RECENCY_SCALE)` is retired —
    lineage only).** Non-tracking worlds: `1.0`, `recency_status "permanent"`
    (the page is true; story-time liveness is salience's axis, not trust's).
    Tracking worlds (`observe_or_unknown`):
    `2**(−max(0, now − last_confirmed_at_wallclock)/half_life)` under the
    declared `DecayPolicy` (exact authored attribute → `attr:in` containment
    family → `attr:__world__` default); no declared half-life →
    `"unconfigured"`, no finite same-value confirmation stamp →
    `"unconfirmed"` — in both null branches `recency` is `null`, excluded from
    the score, and the remaining weights renormalize
    (`(w_p·p + w_c·c)/(w_p + w_c)`). Non-finite stored stamps never qualify;
    a non-finite explicit or injected `now` raises.
  - **corroboration** — a **de-duplicated** count of *independent agreeing
    source classes* (Codex r1): take the union of the winner's source class +
    `FoldResult.corroborated_by` rows' source classes + any same-value visible
    rows' source classes, as a **set of distinct `_source_class` values**, so a
    row counted via `corroborated_by` is never recounted in the same-value scan.
    `n = len(that set) - 1` (agreeing sources *beyond* the winner's own);
    log-scaled (`log1p(n)/log1p(CORROB_SCALE)`).
- **`last_observed_at`** = the winner's `valid_from` — a valid-time
  coordinate, kept for provenance. **(Amended)** Trust-staleness is NOT
  computed from it: staleness is wall-clock — render it from
  `last_confirmed_at_wallclock`, which the engine itself decays in tracking
  worlds ("staleness is derived, never stored" now lives inside the recency
  component).
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
  three-campaign-years-stale fact keeps *full* validity — and **(amended)**
  undiminished recency in a fiction world; only wall-clock unconfirmed age
  decays trust, and only in tracking worlds.
- **Frozen porcelain:** `confidence` is a new additive verb; no existing
  signature/payload changes.
- **P7 bounded:** deterministic, closure-scoped, LLM-free, fixed formula.

## 4. Tests
- A `stated`, recent, multi-source-corroborated fact → high score.
- An `assumed`, old, single-source fact → scores below a `stated` fact
  **(amended:** age contributes nothing; provenance still ranks**)**.
- A `conflicted` key → `conflicted: true` and a halved score.
- `last_observed_at` = the winner's `valid_from`; **(amended)** recency `1.0`
  + `"permanent"` in non-tracking worlds regardless of age or timelessness.
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
HOST-DISCIPLINE.md (confidence as the trust read; **(amended)** staleness
rendered from `last_confirmed_at_wallclock` in tracking worlds); ADOPTION.md
(`confidence`); LEXICON.md (`confidence`).
