# TRACKING-MODE-V1 — the reality eval: proving the second mode

**Status:** SHIPPED (r3 GREEN'd Cx 568/569; implementation reviewed Cx 604 →
repairs → shipped with the finite-clock contract, the three-level DecayPolicy
+ tracking-multiframe oracles, and the `evals/the_grey_house/` seed/build
artifact). The
last open front (founder go, full steam): the two-mode thesis is proven on the
fiction side and merely *implemented* on the tracking side. **Eval-first** — the
tracking chapter-test — plus the engine contracts the eval requires, now pinned.
Failures grade extraction-class vs shape-class (§19 discipline).

## The founder's rulings (design law, folded in)
1. **Time-moves-forward is SHARED between modes.** "It is the next day" happens
   in fiction and reality alike; worlds change off-screen in both.
2. **The engine applies NO plausibility judgment to observer reports — in
   either stance** (the no-bias invariant; see battery #12). `stance` is a pure
   world identifier for downstream consumers, consumed by no engine path.
3. **Fiction confidence does not decay** — the page is true until superseded.
   (This is a *deliberate behavioral amendment* to CONFIDENCE-V1, which
   currently decays fiction recency from story time; see Part B #2.)

## The three time axes (Cx 557 #1 — the engine distinguishes three axes;
tracking EVIDENCE carries all three, fiction rows omit the A1 wall stamp; the
mode difference is which axis DRIVES DECAY)
| axis | meaning | exists in | advances via |
|---|---|---|---|
| `valid_from/valid_to` | when the fact holds in the world | both | the scene cursor / `at=` ("it is the next day") |
| `asserted_at` | log sequence — when the store learned it | both | every append |
| `learned_at_wallclock` | when confirming evidence arrived, in real time | tracking (A1 rider) | the injected clock, sampled at each non-timeless tracking write; the eval's fake wall clock advances as a **separate harness operation** (a no-fact statement does not stamp wall time) |

**Decay driver:** fiction — none (canon holds; only salience/liveness shift).
Tracking — `learned_at_wallclock` age. Valid-time as-of reconstruction is
identical in both modes and never weakens.

## Part A — the eval
**Seed:** `the_grey_house` — household + vehicle over ~3 simulated weeks of
messy, out-of-order structured updates + a hand-authored ground-truth ledger
(what is true at every valid-time AND when each fact was last genuinely
confirmed in wall time). Structured items by design: this validates the
**store after classification** (tracking substrate/time-confidence behavior);
messy *conversational ingestion* is MICRO-EVAL-V1's claim and ingestion
fidelity is front #1's — this eval does not claim them.

**The battery:**

*Shared (both modes):*
1. **As-of reconstruction:** "where was the badge Tuesday?" at three timestamps
   spanning supersessions — exact in both modes.
2. **Time-advance statement:** cursor/wall advance with no new facts — standing
   truth unchanged; no phantom mutation.
3. **Pre-authored future events** land on the spine and are correctly filtered
   by `events(until=)` — due vs not-yet-due. (Narrowed per Cx: the engine
   stores `fires_when` data but has NO condition evaluator/scheduler; "fires
   when due" would overclaim. Execution stays a host concern.)
4. **Axis separation under disorder:** a fact valid Thursday, learned Monday:
   absent under an earlier `asserted_as_of`; reconstructs Thursday correctly
   once learned; **freshness age begins at the Monday wall stamp** — three
   axes, three different answers, one fact.

*Tracking-only:*
5. **Decay honesty:** after N unconfirmed days (explicit `now=`), the recency
   component on a fast key (vehicle location, short half-life) is low while a
   slow key (couch position, long half-life) stays high — **scored at the
   component level against the pinned formula** (Cx: a half-life does not
   halve the weighted total; HIGH/LOW alone is not an oracle).
6. **The staleness answer shape:** `confidence()` carries
   `last_confirmed_at_wallclock` (Part B #3) so a host joins `state()` +
   `confidence()` to render "last confirmed June 19 — three weeks unconfirmed."
   `state()` itself emits no staleness prose or stored fact.
7. **Re-confirmation:** observing the car again refreshes the wall stamp and
   restores the recency component; valid-time history remains queryable
   (as-of still answers the past).
8. **Quarantine never hardens:** the authoritative winner is asserted, the
   `assumed` row survives in history with its status intact, and there exist
   **zero promotion receipts and zero retractions of the winner** (exact
   counted row shapes, not a vague audit).
9. **Stated absence ≠ unknown:** one frozen explicit-negative representation
   (a declared functional key, e.g. `van · has_fittings · false`, `observed`)
   answers the has-question false; a never-asked key answers UNKNOWN; the two
   never conflate — and the negative is never inferred from empty
   `contents()`.
10. **Never-invent under pressure:** forcing unobserved aspects returns the
    UNKNOWN sentinel through `resolve()` and `ask` (the `ask` model plan is
    **scripted explicitly** — structured ingest removes the extractor, but ask
    is model-planned); zero `generated` rows in the log before AND after.
12. **Unexpected-reality fidelity (the aliens test; founder ruling):** an
    `observed` report of an unexpected entity in a reality-stanced world lands
    with exactly the provenance the reporter gave — same status, confidence
    treatment, and fold behavior as a mundane report. Skepticism enters
    structurally only (§7.2 cross-source conflict + corroboration), never
    ontologically. `stance` (letter 026; effectively the binary "claims to
    describe reality?") is present and readable in `charter()` and biases
    nothing — **on the write side or the read side** (Cx 559: weighting
    confidence/provenance by stance would reintroduce the forbidden prior).
    **Isolation methodology (Cx 559):** hold `policy`, the fake clock, the
    structured rows, and source provenance constant; vary ONLY `stance`;
    compare normalized fold + confidence results (identical apart from the
    charter row). Within the reality world, also compare the unexpected vs a
    mundane observed report (identical treatment). A later contradiction is
    asserted through the existing fold-conflict + `truth.scan()` surface —
    `ask().asks` represents unresolved references, not synthesized
    truth-maintenance questions, and the battery does not conflate them.

*Fiction control:*
11. The SAME seed in an `invent_under_canon` world: as-of/supersession answers
    match tracking exactly; the confidence **recency component does not decay**
    (Part B #2's amendment) — while log bytes, folds, state, snapshot, and
    every non-confidence read are byte-identical to today's fiction behavior.

*Restart/purity oracles (Cx 557 #4):*
13. Close and reopen the tracking world: policy rebuilds from the log; the
    same explicit `now=` reproduces identical confidence (restart-safe).
14. Confidence/staleness reads change nothing: head, row count, dump, state,
    snapshot all byte-identical before/after (read purity).

**Scoring:** hand-graded scorecard vs the ledger; component-level numeric
oracles where formulas are pinned; receipts under `evals/results/`.

## Part B — the engine contracts (pinned per Cx 557; each lands with unit tests)

### 1. `confidence(..., now=None)` — the wall-time axis, additive, never overloaded
`as_of` remains **valid time** (it feeds `fold_key`); `asserted_as_of` remains
sequence time; **`now` is wall time**, defaulting to the World's injected clock
in tracking worlds and unused in fiction. Carried through `Indexes` (single and
multiframe paths), `World`, porcelain, **and the MCP registry** (a classified
additive param + schema, per the registry's own discipline). Never a second
meaning for `as_of`.

**The frozen result contract (Cx 563 #1 / 565 #2) — additive payload, every
branch pinned, ONE shape.** The shipped payload (`score, status,
last_observed_at, corroboration, conflicted`) gains **three** fields —
`recency`, `recency_status`, `last_confirmed_at_wallclock` — present in EVERY
result, identical across single-frame, multiframe, and the one-frame reduction
path. `last_confirmed_at_wallclock` is the §B4 confirmation stamp on the
tracking/configured branch and **null everywhere else**: every non-tracking
result, `unconfirmed`, and the empty / set-valued / accrue payloads.

- **`recency: float | null`** — the recency COMPONENT itself (battery #5/#7
  assert it directly, never reconstructed from the weighted total).
- **`recency_status`** — one of:
  - `"permanent"` — non-tracking world (`invent_under_canon` or `deny`):
    `recency = 1.0`, constant (the page is true);
  - `"configured"` — tracking, policy found, valid confirmation stamp:
    `recency = 2 ** (−age/half_life)` with **`age = max(0, now − stamp)`**
    (clamped — an explicit historical `now` earlier than the stamp yields
    `recency = 1.0`, never > 1);
  - `"unconfigured"` — tracking, no decay policy resolves for the key and no
    world default: `recency = null`; the recency term is **excluded from the
    weighted total** and its weight renormalized over the remaining
    components (fail-closed: neither fake permanence 1.0 nor fake staleness
    0.0);
  - `"unconfirmed"` — tracking, policy exists, but no eligible same-value
    `stated`/`observed` row carries a valid A1 stamp: `recency = null`, same
    exclusion+renormalization, and `last_confirmed_at_wallclock = null` (the
    honest "we have never confirmed this" answer).
- **Total `score`:** unchanged formula when `recency_status ∈ {permanent,
  configured}`; the renormalized form for the two null branches; the
  empty-key payload stays `score=None, status=None` as shipped, now with all
  three additive fields null; set-valued/accrue keys keep `score=None`
  (functional-only, as shipped) with all three additive fields null.

### 2. Fiction confidence stops decaying — a deliberate amendment
Current CONFIDENCE-V1 computes recency from `valid_from` and decays fiction
scores (a test locks an old fiction fact scoring low). **The founder's ruling
wins:** in fiction worlds the recency component is constant (the page is true);
in tracking worlds recency computes from wall age (`now − last confirming
stamp`) under the decay policy. Amendment ripples, done as part of this spec:
`CONFIDENCE-V1` + `CONFIDENCE-MULTIFRAME-V1` status texts, ADOPTION,
HOST-DISCIPLINE, LEXICON, and the existing confidence tests (the old-fiction-
fact-scores-low lock inverts). The regression promise is **narrowed honestly**:
log bytes, folds, as-of, supersession, and all non-confidence fiction reads
unchanged; the confidence payload stays shape-compatible while its fiction
recency semantics intentionally change. Story-time recency remains available
where it always belonged: **salience** (liveness), not trust.

### 3. `DecayPolicy` — world physics as declared, rebuildable data (NOT an RFC-001 fold semantic)
A per-World, rebuildable reader over declared rows — **separate from
`AttributeSemantics`** (Cx: `decay_halflife` on `attr:in` would either be
rejected by the inviolable-core guard or silently unconsumed; decay is physics,
not fold semantics). Pins:
- **Subjects/lookup — deterministic candidate order (Cx 563 #2):** for a
  confidence read on key K whose effective winner row carries authored
  attribute A (possibly a domain-declared containment member, e.g. `worn_by`):
  1. `attr:<A>` — exact policy for the **winner's canonical authored
     attribute**;
  2. if A belongs to the containment family: `attr:in` — the **public family
     policy subject** (the private `__containment__` sentinel is NEVER host
     vocabulary);
  3. `attr:__world__` — the world default.
  First hit wins. Repeat/later declarations fold at current head (the latest
  visible declaration per subject is the policy — ordinary supersession). One
  precedence oracle in the battery: a world declaring all three levels serves
  the exact-attribute value for a `worn_by` winner, the `attr:in` value for an
  undeclared containment member, the world default otherwise.
- **Predicate/units/validation:** `decay_halflife_seconds` — finite, positive
  number; malformed declarations are skip-receipted at the gate, never
  silently active.
- **Formula (pinned — one formula everywhere, identical to §1's configured
  branch):** recency component = `2 ** (−age_seconds / half_life_seconds)`,
  **`age_seconds = max(0, now − last_confirmed_at_wallclock)`** (clamped;
  recency never exceeds 1; the numeric oracle covers `now < stamp`).
- **Missing policy:** an explicit world-default declaration
  (`attr:__world__ · decay_halflife_seconds · <n>`) OR an honest
  `"unconfigured"` recency status on the read — **never** silent
  fiction-style permanence for an undeclared tracking key.
- **Later declarations:** policy is read fresh at each read (derived,
  rebuildable) — a new declaration recomputes all subsequent reads under
  current physics; history is not migrated (as-of confidence is explicitly
  *current-physics over historical facts*, documented).
- **Reload:** declarations rebuild from the log; the injected clock and policy
  are supplied at World construction as before (battery #13 locks it).

### 4. `last_confirmed_at_wallclock` — a new explicit field, axis-honest
`last_observed_at` keeps its shipped valid-time meaning (frozen field, one
axis, both modes — never silently mode-switched). Confidence payloads gain
**`last_confirmed_at_wallclock`** (null in fiction): the latest visible A1
wall stamp among rows that **confirm the effective served value** — same
value-identity, `stated`/`observed` provenance only (an `assumed`/`inferred`/
conflicting/different-value row never refreshes it), frame- and
`asserted_as_of`-respecting; multiframe takes the same rule per effective
winner. **Fail-closed:** a tracking row missing its mandatory stamp
contributes no confirmation (and is a defect the eval counts), never a guessed
age.

### 5. The operational selector — `policy`, pinned, `deny` included (Cx 563 #3)
**Tracking versus non-tracking selects on `policy == "observe_or_unknown"`** —
exactly the selector A1 stamping uses today. The tracking branch gets A1
stamping, decay physics, and the default `now` from the injected clock; the
non-tracking branch gets the `"permanent"` recency. `invent_under_canon` AND **`deny`** both take the non-tracking branch
(`recency_status="permanent"`; no A1 stamps; `now` unused): `deny` is a
*resolution* policy (sealed gaps), not an epistemic mode — its worlds make no
claim of drifting external reality. `stance` selects nothing (below). Reopen
behavior is thereby checkable: the same `policy` + injected clock reproduce the
same physics (battery #13).

### 6. `stance` — ruled a pure identifier (founder; recorded as permanent)
Stored, readable, consumed by no engine path; gate-level plausibility
conditioning is a **permanent non-goal** (an earlier draft proposed it; the
founder reversed it — recorded so it is never re-proposed).

## Non-goals
- No extractor work; no conversational-ingestion claim (MICRO-EVAL-V1 owns it).
- No stored staleness/decay/confidence values, ever (computed at read).
- No scheduler, condition evaluator, or background time (P7): "time advances"
  is always a caller statement; `fires_when` execution stays a host concern.
- No plausibility/ontology judgment at any gate, either stance (founder).
- Fiction: no change to log bytes, folds, as-of, supersession, or any
  non-confidence read (battery #11 locks; the confidence recency amendment is
  the one deliberate, documented exception).

## Deliverables
- `evals/the_grey_house/` seed + ledger + build script (deterministic; fake
  wall clock injected; scripted `ask` plan).
- The 14-item battery as a runnable script + scorecard.
- Part-B engine work, each piece with unit tests, through the standard loop.
- CONFIDENCE-V1 / CONFIDENCE-MULTIFRAME-V1 / ADOPTION / HOST-DISCIPLINE /
  LEXICON amendment texts (Part B #2), **with payload examples carrying the
  frozen `recency`/`recency_status` fields** (Cx 563).
- Full suite green; the narrowed fiction regression promise holds throughout.
