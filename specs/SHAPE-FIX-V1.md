# SHAPE-FIX-V1 — deferred-coreference adjudication, retype, phantom suppression

**Status:** SHIPPED — Cx shape deliberation (Q1 anchor-subsumption AGREED; 6 fixes
adopted) → spec GREEN → impl reviewed to GREEN (1 RED pass: raw-id validation
ordering, side-channel edges, asymmetry field) → Win 4 added mid-flight from a live
incident (HD 089, the fused protagonist) and delta-reviewed GREEN. Founder ruling (via Kernos 076): *"fix the
problem with the SHAPE; we do NOT want appending a bunch of rules on how to handle a
misshapen set of information."* Live cases: one pencil minted three ways
(`obj:pencil`/`obj:pencil_1`/`obj:plain_pencil`); `place:street` + `obj:street` with a
person located in the object; `person:harth` (empty) beside `place:harth` (has
villagers); phantom `person:narrator`/`person:/you` minted from narration voice.
Buckets per Kernos 075/076: **1** name-fragment coreference (engine), **2** typing
slips (engine retype, distinct from merge), **3** the semantic trap (HOST judges —
protected, not solved), **4** phantom non-diegetic entities (engine extraction+gate).

## Sequencing principle (the elegance)
Retype (bucket 2) runs conceptually BEFORE fragment adjudication (bucket 1): once a
relic mis-typed `person:` is corrected to `obj:`, the trap pair (`person:mara` relic ~
`person:mara_thist` protagonist) becomes a `kind_conflict` and is *structurally*
excluded from any auto-merge — the typed-context precedent enforced by data, not by a
rule. Pairs with no structural trace of distinctness remain proposals for the host
(bucket 3 stays the host's; the engine never decides it).

## Win 1 — `adjudicate_deferred()` (bucket 1: confident fragment coreference)
A host-invoked porcelain verb (opt-in — `reconcile()` is frozen and unchanged) that
walks live `maybe_same_as` proposals and merges ONLY the structurally-decisive
subset, returning receipts + the residue (with the existing `auto_decline` (C)
bundles) for host adjudication.

**The decisive gate — fragment subsumption.** A proposal merges iff ALL hold:
1. No hard block (containment, `distinct_from`), **zero relating edges** between
   the closures (the existing `relating_edges_between` — a bound pair is two
   things), and **no `aka` correlation between them** (Cx: correlation is
   deliberately non-collapsing — a correlated pair is two facets by design and
   must never auto-merge; the host's `merge` remains the only collapse path).
2. Kind state is NOT `conflict` (post-retype, the mara trap lands here).
3. **Anchor subsumption:** one side's entire *distinctive* anchor-token set (anchors
   minus type-words, split to content tokens) is ⊆ the other side's anchor tokens.
   The fragment has NO independent identity signal — `tovin` ⊆ {tovin, beck};
   `crown` ⊆ {cinder, crown}. Counter-cases stay proposals: `mara`(relic, aliases
   "the crown"…) vs `mara_thist` — each side has distinctive non-shared tokens (two
   individuated things sharing a token); `ansel_letter` vs `sealed_letter` — ditto.
   Decisive means *subsumed*, not merely overlapping.
4. The merge routes through the existing guarded path (`merge()` re-checks hard
   vetoes; evidence records `adjudicate_deferred: fragment subsumption`).

Return shape: `{"merged": [receipts...], "residue": [proposals-with-auto_decline]}`.
Zero model calls; deterministic; idempotent (merged proposals collapse, residue
re-enumerates). **Not solved here:** a same-kind, no-edge, subsumed-anchor pair that
is *semantically* two things — that shape is indistinguishable in structure by
premise (Kernos's trap); it is exactly why the verb is opt-in and why authors
individuate through structure (`distinct_from`, the V2 doctrine). The (C) bundle on
the residue is already shipped (TRIAGE-CONTEXT-V1 `auto_decline`).

## Win 2 — `retype(entity, to_kind, evidence, absorb=None)` (bucket 2)
A distinct operation from merge: the containment veto correctly blocks *merges* but
must not block a *typing correction*. Two cases, one verb:

- **Case A — mistyped entity** (`obj:cinder_crown` carrying `kind=person`):
  `retype(e, "relic", evidence)` **retracts** the visible conflicting `kind` row(s)
  (ordinary `truth.retract` meta-assertions — append-only preserved) and appends the
  correct `kind` (status `stated`, ingest authority). No identity change.
- **Case B — spurious duplicate at the wrong kind** (`person:harth` empty beside
  `place:harth` with villagers): `retype(spurious, to_kind, evidence,
  absorb="place:harth")` — verifies the **slip signature** first: shared name-class
  anchor + kind conflict + structural asymmetry (the spurious side has no
  containment children and no domain facts beyond the slip; the target side is
  structurally richer). Then (1) retracts the spurious `kind` row, (2) retracts
  ONLY the **direct inter-closure containment artifacts** — containment edges
  relating the two closures themselves, which would become self-edges after the
  merge (Cx: the merge veto checks only inter-closure edges, so nothing broader
  may be touched; incoming child containment — the villagers in `place:harth` —
  is preserved untouched), and (3) merges through the guarded path (which now
  passes, the artifact edges gone). If the signature does NOT hold (both sides
  structurally rich, or no kind conflict), return a `vetoed_not_a_slip` receipt —
  the host is trying to use retype as a veto bypass, and that door stays shut.
- **The new `kind` row is classified** (Cx): it routes through the ordinary
  classifier path so the sidecar carries its durability verdict (the existing
  `kind` guardrail → CONSTITUTIVE), not an unclassified hole.
- **`typing_conflicts()` — the surfacing read (Cx: mandated, not optional).**
  Host discovery is NOT enough: `enumerate_proposals()` only shows
  `maybe_same_as`, and `reconcile()` deliberately never re-proposes
  containment-hard-blocked pairs — so the slips are invisible on the current
  surface. A read-only porcelain verb enumerates same-anchor cross-kind pairs
  carrying the slip signature: `[{a, b, kinds, shared_anchor, asymmetry,
  artifact_edges}]`. Zero writes, zero model calls; the host adjudicates each
  with `retype(...)` or leaves it. `reconcile()` itself is byte-unchanged.

## Win 3 — phantom non-diegetic entities (bucket 4: kill at the source)
- **4a — malformed ids (gate):** `_ingest_item` validates entity ids and
  entity-valued values against the id grammar (`^[a-z][a-z0-9_]*:[a-z0-9_:]+$`,
  no stray slashes). A malformed id is **skipped with a typed receipt**
  (`SkipRecord`, reason `malformed_id` — the shipped edge-granular machinery), never
  normalized: guessing `person:/you` → `person:you` would *manufacture* the phantom
  properly-shaped. Reject; the receipt tells the host what fell. **Ordering (Cx):
  the validation runs AFTER the authority gate**, exactly like the structural
  edge-skip (INGEST-HARDENING final) — an authority violation must still RAISE
  even on a malformed row; the skip never swallows it.
- **4b — narrative-voice suppression (extractor):** one line in BOTH extract rule
  blocks (full + lean): *"The narrative voice is not an entity — never emit
  person: entities for the narrator, an unnamed speaker, or the audience."* This is
  HOST-DISCIPLINE's restraint principle moved to the source. No referent exists;
  suppression, not retype.
- **4c — deixis binding (extractor + param):** `extract()`/`ingest()` gain optional
  `pov: str | None = None` — an entity id, no host concept (the `frame="knows:<id>"`
  pattern). **Validated against the id grammar BEFORE prompt interpolation** (Cx:
  never interpolate an unvalidated string into the extractor prompt — a malformed
  `pov` raises `ValueError`, it does not ride into the model). When set, the prompt
  enumerates the **full scoped deictic family** (amended per HD 126 / Cx 570 — the
  original `(I, you, we)` shorthand let "my hand" bind sideways to the nearest NPC,
  fabricating canon): *singular first-person (`I, me, my, mine, myself`) and
  addressed second-person (`you, your, yours`) refer exclusively to `<pov>` — never
  mint for them, and a singular possessee ("my hand", "your coat") is NEVER
  attributed to any other present character; plural (`we, us, our, ours`) INCLUDES
  `<pov>` without proving exclusive ownership — never guess the other members,
  never rebind the plural wholesale to a nearby character.* When unset:
  *"never mint a person from a bare pronoun; if the referent is unknown, skip that
  assertion."* Porcelain threads `pov=` through. The contract test pins the
  instruction LINE itself (word-bounded, rules-section-only — a whole-prompt
  substring search false-passes on look-alike words).

## Win 4 — the durable-contradiction veto (HD 089: the fused-protagonist incident)
Live failure: reconcile fused `person:pavel_orra` (role: retrieval lead) into
`person:tom_apprentice` (defense apprentice) as `same_as` — the value-rewrite
repointed `arc:main.protagonist` and bound the player to the wrong character. Only
`kind` was consulted; both sides held CONTRADICTORY standing `role` rows. The
engine-true generalization (not a hardcoded role list): **shared attributes where
both sides hold present, DURABLE (CONSTITUTIVE/DISPOSITIONAL), contradictory folded
values are a soft distinctness signal** — the kind veto extended to every standing
fact. Auto-merge (`_mergeable`, `adjudicate_deferred`) declines to a proposal;
the host's guarded `merge` remains available (soft, not hard). Transient STATE
differences (mood, position) never trigger it. Surfaces as decline code
`durable_contradiction` with the contradicting descriptors on the (C) bundle.
Registry reads folds + durability via late-bound providers (the kind-provider
idiom). Tests: the pavel/tom pair stays a proposal; a same-role fragment pair
still merges; decline context carries the descriptors.

## Non-goals (the over-complication line)
- No auto-retype pass, no retype heuristics inside `reconcile()` (v1:
  `typing_conflicts()` surfacing + host-invoked op only). No confidence scores on
  adjudication (the gate is binary and structural). No new `value_type`/schema.
  Bucket 3 gets no engine heuristic — by design, per the typed-context precedent.
  No id normalization/repair.

## Cx deliberation record (settled)
1. **Anchor subsumption — AGREED** as the decisive line; overlap alone over-merges;
   `ansel_letter~sealed_letter` correctly stays a proposal.
2. **Case B narrowed:** retract only direct inter-closure containment artifacts;
   incoming child containment preserved (adopted above).
3. **`typing_conflicts()` mandated** — proposals can't surface the slips (adopted).
4. **`pov=` membrane-safe but id-validated** before prompt interpolation (adopted).
5. **Hazard guards explicit:** no auto-merge across `aka` (non-collapsing by
   design); retype's new `kind` row classifies through the ordinary path
   (CONSTITUTIVE guardrail); malformed-id skip runs after the authority gate
   (adopted above).

## Tests
- Win 1: pencil trio merges (subsumption); mara~mara_thist stays residue in BOTH
  pre-retype (each side distinctive tokens) and post-retype (kind_conflict) worlds;
  relating-edge pair never merges; an `aka`-correlated pair never merges; residue
  carries `auto_decline`; idempotent second call merges nothing; `reconcile()`
  behavior byte-unchanged.
- Win 2: Case A retracts+appends kind (fold serves new kind; history preserved
  as-of; new row classified CONSTITUTIVE); Case B absorbs the empty duplicate,
  retracts ONLY the inter-closure artifact edge (child containment intact —
  villagers still in the place), guarded merge passes; non-slip invocation returns
  `vetoed_not_a_slip`; `distinct_from` still absolute; `typing_conflicts()` lists
  the harth/street shapes and is empty on a clean world.
- Win 3: `person:/you` skipped with `malformed_id` receipt (rest of chunk ingests);
  authority violations still raise BEFORE skip; malformed `pov` raises before any
  model call; extractor prompts contain the suppression + pov lines
  (prompt-content pins); pov threading porcelain→extract.
- Full suite green; all default paths unchanged.
