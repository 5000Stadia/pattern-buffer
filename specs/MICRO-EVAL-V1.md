# MICRO-EVAL-V1 — the reality-divergence battery

**Status:** draft for Codex review. **Authority:** whitepaper §19.1 scope
honesty (the bridge from clean authored prose to sloppy conversational
fragments, gating any host commitment); letter 025 (scope decision: a
reality-divergence battery, one criterion per fiction/reality divergence);
letter 018 (the synonym criterion). Engine unchanged by intent; any
criterion that turns out to need engine support is a [DECISION] letter to
Kernos CC before building.

**Posture (permanent, from 025):** fiction mode trusts the narrator — the
page is always true. Tracking mode trusts no single utterance; it
accumulates evidence. The conversational ingest contract is written FROM
this posture, never adapted from the prose contract by deletion.

## 1. Shape

Same bones as the chapter test, new organs:

- **World policy under test:** `observe_or_unknown` — tracking mode's
  first graded run. The A1 wall-clock rider (learned-at meta-assertions)
  and the evidence-rank/assumption-quarantine machinery move from
  bystanders to graded surfaces.
- **Seed:** a hand-authored household-dialogue transcript (~40–60 turns,
  2 speakers + an assistant addressee) with a hand-authored answer key.
  The circularity rule stands: the key is never produced by the ingestor
  under test; the transcript never contains key text. Seed versioning per
  letter 006 (v0-draft → founder stamp).
- **Pipeline:** INGEST-V2 (registry-first) with a **conversational pass-1
  contract** (§3) — establish/extend gets its first incremental exercise
  (the registry grows turn-window by turn-window, the 014 interface used
  as designed).
- **Grading:** fixtures transcribed from the key; scorecard with seed
  version + predicted-vs-actual; failures classed extraction vs shape.

## 2. The battery (one planted case per criterion; grader notes inline)

| # | Criterion (origin) | Planted case | PASS condition |
|---|---|---|---|
| R1 | Irrealis filtering (025.1 — highest stakes) | a hypothetical ("maybe I left it in the car"), a question, a sarcastic line, a conditional | **zero** stated/observed rows from any of them; at most `assumed` with low confidence for the hypothetical; the sarcasm produces nothing |
| R2 | Intention vs fact (025.2) | "I'll move the drill to the van tomorrow" | the drill's location does NOT change; no stated/observed future row; at most one `assumed` future-valid row; rule: intentions are host-side objects, not world state |
| R3 | Self-correction grace (025.3a) | "3 bedrooms — well, 4 with the office" (same speaker, same turn-window) | folds to 4 with the 3-row retracted-or-superseded; **no conflict flag** |
| R4 | Genuine contradiction (025.3b) | speaker says X Monday, not-X Friday, no correction marker | conflict flag fires, both rows alive — the R3 path and R4 path must differ |
| R5 | Cursor humility (025.4) | "the fittings are in the van," said from the office | fittings anchor under the van; the office contributes nothing; speaker location ≠ assertion location |
| R6 | Fuzzy calendar time (025.5) | "last Tuesday sometime" | interval valid_time with honest slop; as-of inside the interval finds it, outside does not |
| R7 | Vocabulary drift (018) | key registers "cabinet"; speaker later says "the cupboard" | tier-2 resolves first use (receipt logged), tier-1a resolves second use (alias accrued, receipt logged) |
| R8 | Negation as information (025.7) | "I never ended up moving it" after an R2-style intention | the intention/assumption closes (retracted or valid_to'd); the OLD location is confirmed as an explicit row — distinct from unknown (the Dale stated-absence pattern) |
| R9 | Unknown stays unknown (mode floor) | a never-discussed container is queried | `UNKNOWN` — no invention, no kind-default promotion; the resolver's observe_or_unknown path graded live |
| R10 | Wall-clock rider (A1) | every STATE/EVENT row from the run | carries a `learned_at_wallclock` meta-assertion; staleness is computable |

R1/R2/R9 are the cardinal-sin criteria: in tracking mode a confabulated
assertion is acting on a false reality. A failure there is graded **shape
if the gate let it through structurally** (e.g., a stated row from an
explicitly irrealis input that the contract flagged) and extraction if the
model misjudged free prose; the dump audit adjudicates, as always.

## 3. The conversational ingest contract (pass-1, tracking posture)

Written fresh from the 025 posture. Deltas from the prose contract:

- **Reality gate first:** classify each utterance's stance before
  extracting — declarative-about-now/past (extract), irrealis/question/
  joke/conditional (NO factual rows; hypotheticals may emit `assumed`
  @ low confidence), intention/plan (emit nothing into the world store),
  performative-correction ("actually...", "I mean...") → emit the
  corrected value plus a retraction marker for the in-window prior.
- **Status defaults flip:** the prose contract's default `stated` becomes
  `observed` for first-person reports about the speaker's own actions and
  `stated` only for the speaker's assertions about standing facts;
  hearsay ("Dale said the parts came in") gets a document-style chain
  (`source` → `person:dale` utterance) — the §7.1 trust-chain machinery
  applied to spoken sources.
- **Cursor = conversation time only.** The scene cursor carries
  wall-adjacent conversational time for stamping `valid_from`; it NEVER
  contributes spatial anchoring (cursor humility — the speaker's location
  is not the assertion's location; anchor only on stated containers).
- **Interval stamping:** fuzzy time expressions map to explicit
  `valid_from`/`valid_to` intervals with the slop the language supports
  ("last Tuesday sometime" → that day's bounds), never a fabricated point.
- **Self-correction window:** within a turn-window, an amendment emits
  `retract`-marked replacement (grammar gains nothing; the existing
  `vt=` close + new row suffices — verify in drafting; if a retraction
  line proves necessary, that is the [DECISION]-letter trigger).

## 4. Engine-support audit (the 025 caveat, checked in advance)

- Interval valid_time: **supported** (`valid_from`/`valid_to` exist; R6
  needs only contract discipline).
- Explicit negatives: **supported** (a stated negative is an ordinary
  row; whitepaper §4 distinguishes stated absence from unknown).
- Intention exclusion: contract-level; nothing to build.
- Self-correction: expressible as `vt=` close + new row through the gate;
  **only open question** is whether pass-1 can emit a retraction op —
  currently retraction is truth-maintenance/audit authority, not
  extraction authority. Position taken by this spec: pass-1 emits the
  close-and-replace shape (no new authority); if drafting the seed shows
  that's insufficient, [DECISION] letter before building.
- R10: already a gate invariant with a test; the eval grades it end-to-end.

## 5. Deliverables and sequence

1. Seed: `evals/household_dialogue/transcript.md` + `key.md` (hand-
   authored here, founder-stamped per 006; the 003-style coverage list is
   §2's table).
2. Harness: `evals/harness/run_micro_eval.py` reusing pipeline/battery
   bones; conversational pass-1 prompt; R1–R10 graders.
3. Run on the codex shim (its first full-pipeline exercise — predicted,
   checkably: wall clock under 15 min end-to-end given ~10 model calls;
   zero irrealis leaks).
4. Scorecard + milestone report (predicted-vs-actual) + [MILESTONE]
   letter; §19.1's "honest bridge" judgment rendered: extraction-class
   failures iterate; shape-class stops the line.

## 6. Out of scope

Multi-speaker identity disputes (two people asserting different facts in
good faith — contested-truth frames exist but the eval plants only the
R4 contradiction); staleness *decay schedules* (R10 grades the rider, not
decay math); host-side plan/reminder objects (R2 only asserts they don't
enter the world); the 019 self-check/M-line machinery (next pipeline
iteration, not this eval).
