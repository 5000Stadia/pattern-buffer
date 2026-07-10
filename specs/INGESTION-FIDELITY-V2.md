# INGESTION-FIDELITY-V2 — the standing-property contract (narrow) — r3

**Status:** r3 GREEN (Cx `<ba396774…>`; r2 folded the durability/valid-time
separation, the corrected §C premise, the declaration-path kinship guardrail;
r3 pinned the child→parent `father` directionality). Implemented → Cx code
review.
**Kind:** two prompt-seam amendments + one documented host recipe + one receipt
rider + regression pins. No schema change, no new verb, no fold change, no new
engine vocabulary. Evidence-gated: every amendment traces to a measured row on
the emberroad2 fixture (`evals/corpora/`, Construct feeder `<57c75397…>`,
bin-B table `logs/binb-reask-results.md`).

## The measured defect (root cause, corrected per Cx r1)

81 fixture rows sit in the audit's `unstamped_timed` bin: 41 genuinely timed
(recovered by Construct's host-side re-ask — no engine change), 24 unplaceable
bookkeeping, and **16 standing personal properties** (`age`, `build`,
`occupation`, `father`, `can_hunt`, `can_ride_well`, `scar_on_left_palm`, …)
authored timed-but-unstamped.

Two engine-owned causes, one per seam:

1. **The extract TIME clause has no bucket for standing properties** —
   "timeless=true ONLY for identity and structure (kind, names, fixed
   adjacency)" pushes every standing trait into the timed branch, and where
   the cursor is not authoritative it arrives unstamped.
2. **The durability classifier currently rules these rows STATE**, so the
   audit's existing (and correct) contract — the bin already includes only
   sidecar-classified STATE/EVENT rows (`__init__.py` `fidelity_audit`;
   pinned in `test_fidelity_audit.py`) — has no grounds to exclude them.

**Two orthogonal contracts, kept separate throughout (the r1 conflation,
corrected):** *valid time* (`timeless` means true across all world history —
WHITEPAPER §3; absence of a narrated onset does NOT license backward-forever
projection) and *durability* (a standing class may coexist with a
`valid_from`). `age=32` is the decisive case: mutable, time-relative, stays
STATE with a stamp — it exits the bin by STAMPING. `father` is the opposite
pole: kinship of origin, genuinely timeless, CONSTITUTIVE — it exits by
CLASS. Acquired standing facts (`occupation`, `scar`, learned skills) sit
between: durable in class, but historically acquired, so they carry valid
time at the earliest supported point.

## A. The extract TIME clause (both prompt variants, full + lean)

Replace the "ONLY identity and structure" guidance with:

> timeless=true ONLY for what holds across the world's whole history:
> identity/structure (kind, names, fixed adjacency) and facts of origin
> (kinship of origin, innate traits presented as what the person has always
> been). Everything acquired or mutable carries valid_from — a dated onset
> when the text gives one ("became a soldier at the war"); otherwise the
> earliest supported point (the entity's introduction or the scene cursor).
> Time-relative quantities (age) are current state at the cursor, never
> timeless. Standing-but-acquired properties (occupation, scars, learned
> skills) are NOT timeless — stamp them at their earliest supported time.

Negative controls pinned: the fixture's 41 re-stamped rows (e.g.
`has_been_farther_east_than` → chunk 5) must stay timed at their onsets, and
nothing in the clause invites the extractor to drop stamps it can support.

## B. The durability classifier

1. **Kinship of origin via the EXISTING declaration path — no engine
   hardcode, direction pinned (Cx r2).** The canonical host vocabulary is the
   fixture-exact **child→parent** form: `father` / `mother` (subject HAS
   father/mother; the measured row `person:mara_thist · father ·
   person:mara_thist_father` reaches the declaration as authored — the
   canonicalization gate does not touch kinship attributes). The host
   declares `attribute_default("father", structural=True)` (likewise
   `mother`), which already yields the deterministic `CONSTITUTIVE, 1.0`
   guardrail through `is_structural`. The inverse **parent→child** form
   (`father_of` / `mother_of`: subject IS father/mother of value) is a
   SEPARATE attribute a host declares only if it accepts that form — never a
   canonicalization target of `father` (that mapping would reverse meaning).
   The engine gains no domain names; the recipe (with both directions stated)
   ships in INGESTION-PLAYBOOK + ADOPTION. Generic/non-person `parent` and
   mutable kin (`spouse`, `ally`) remain model-judged. (Per Cx: an engine
   builtin would need canonical forward/inverse names, person-typing, and an
   inviolable-core justification — not warranted by 16 rows with a
   declaration path already live.)
2. **Model prompt amendment (one line after the mutability test, preference
   not prohibition):**
   > When the text presents a property as an enduring baseline of the person
   > — a physical trait, a capability, a continuing role — prefer
   > CONSTITUTIVE (what they are) or DISPOSITIONAL (how they tend) over
   > STATE; a temporary ability or condition, or a time-relative quantity
   > (age), remains STATE.
3. **Untouched:** EVENT safety (the model still cannot assign EVENT), the
   asymmetric STATE default for genuine ambiguity, the review floor,
   durability/valid-time orthogonality (a DISPOSITIONAL row may carry
   `valid_from`).

## C. The audit bin — existing contract, NO code change (corrected per Cx r1)

`fidelity_audit`'s bin already requires a sidecar entry and includes only
STATE/EVENT durabilities; CONSTITUTIVE exclusion and the classification
precondition are already pinned. r1's premise here was false and is withdrawn.
Standing-classified rows sit OUTSIDE this STATE/EVENT-only bin — which is
NOT a claim that standing facts need no stamp: acquired standing facts still
carry `valid_from` at the earliest supported point (§A); their valid-time
correctness is the extraction contract's, separately. This spec only
STRENGTHENS the regression pins: add a DISPOSITIONAL-classified
unstamped row (exits the bin) beside the existing CONSTITUTIVE pin, and pin
the STATE-classified unstamped row staying in. The single effective-defect bin
(rebuildable-sidecar-dependent) is ruled correct; an authorship/raw-extraction
view is out of scope absent evidence.

## D. Rider (GREEN'd r1): `merged_self_edge` receipt reason

When a containment edge's **raw** subject and value differ but both resolve to
one identity head post-`same_as`, the skip receipt's reason becomes
`merged_self_edge`; an authored self-edge keeps the original reason. Gate
behavior otherwise identical — the row still never enters. The receipt retains
the raw ids (subject, value as authored) so the merge diagnosis is actionable
(per Cx: pin raw-ids-differ-before / canonical-match-after).

## Oracles (row-level time+durability outcomes — not bin-shrink-by-relabeling)

1. Extract-prompt pin (both variants, line-local, word-bounded): the
   whole-history clause, the earliest-supported-stamp rule for acquired
   standing properties, and the age-is-state rule.
2. Classifier-prompt pin: the enduring-baseline preference line verbatim,
   including the temporary/time-relative STATE carve-out.
3. Declaration recipe (same canonical attribute as Oracle 6): with
   `attribute_default("father", structural=True)`, a child→parent `father`
   row classifies `CONSTITUTIVE, 1.0` deterministically (no model call);
   WITHOUT the declaration it defers to the model; `spouse` always defers;
   and `father` is pinned as NOT a canonicalization source or target (the
   authored attribute reaches the declaration unchanged, and no mapping to
   `father_of` exists).
4. Audit-bin pins (existing contract): unstamped+DISPOSITIONAL exits;
   unstamped+CONSTITUTIVE exits (already pinned — keep); unstamped+STATE
   stays; stamped rows never enter regardless of class.
5. Rider: merge-induced self-edge receipts `merged_self_edge` with both raw
   ids retained; raw ids differ pre-resolution, resolve equal post; authored
   self-edge keeps the original reason.
6. Row-level fixture outcomes (scripted sidecar-contract local run — the
   responder wires the §B2 verdicts; model-semantic evidence is the
   host-side fixture rerun — per-row not aggregate): `age` → STATE +
   stamped (exits by stamp); the measured a:64
   row `person:mara_thist · father · person:mara_thist_father`, with
   `attribute_default("father", structural=True)` declared (the SAME
   canonical attribute Oracle 3 exercises) → CONSTITUTIVE timeless, exits by
   class, no semantic reversal; `build`/`scar` → standing class with
   earliest-supported valid time honored if authored; `occupation`/`can_*` →
   DISPOSITIONAL (exit by class). The 41 re-stamped rows stay timed at their
   onsets; the 24 unplaceable are untouched.

## Non-goals (pinned)

- No gate-level plausibility conditioning (the no-bias invariant — permanent).
- No background-coreference contract (parked forever with cause: 4 residual
  fixture groups, all unvouched, none load-bearing, replay-proved harmless).
- No change to what the model may classify (EVENT stays structural).
- No engine kinship vocabulary; no new porcelain; no schema or fold change.
- No authorship/raw-extraction audit view (absent evidence).

## Docs on ship

INGESTION-PLAYBOOK (the whole-history timeless rule; the kinship-of-origin
`attribute_default` recipe), ADOPTION (same recipe at the host surface),
LEXICON (`merged_self_edge`; `unstamped_timed` entry gains the
STATE/EVENT-only clarification), HOST-DISCIPLINE (unchanged — the re-ask
recipe stays a host pattern).
