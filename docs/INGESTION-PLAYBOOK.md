# INGESTION-PLAYBOOK.md — rules for deserializing narrative into a world

**Status: living document, pre-1.0.** Evidence-based: every rule cites where
it was learned. Sources so far: chapter-test run 1 (2026-06-11, sonnet via
CLI shim, 455 assertions, scored 21/33) and run 2 (same seed, revised
contract — in flight; deltas will be folded in). The chapter test grades
clean authored prose; the messy-dialogue micro-eval will extend this file to
conversational ingestion. Audience: anyone designing an ingest pipeline over
this engine, including the host adapter's ingest cohort (whitepaper §17.2).

## A. What the extractor must be told (the contract)

The headline lesson of run 1: **extraction quality is a contract problem
before it is a model-capability problem.** Every major run-1 miss traced to
an instruction the prompt didn't give, not to something the model couldn't
do. The load-bearing instructions, in order of damage when absent:

1. **Canon vs knowledge frames — state the discipline in the engine's own
   terms.** *(Run-1 failure, the costliest.)* The model put late-revealed
   canon (the memory core's true custody chain, revealed in Ch.3 about Ch.1
   events) into `knows:narrator` — so canon honestly had nothing at the
   probe time. The rule that fixes it: facts about the world are canon with
   their TRUE historical valid_time, even when revealed late or learned by a
   character; `knows:` rows are *additional* copies marking knowledge, never
   replacements. A telling scene emits frame rows only.
2. **Aliases are mandatory, identity is cheap to keep and expensive to
   repair.** *(Run-1 failure.)* Three entities for one clerk; "the vault"
   attached to one room. Every referring expression used for an entity goes
   on it as an alias; a later-named entity keeps its id and gains the name;
   a duplicate id gets `same_as`. Models WILL fragment identity unless told
   the id-reuse policy explicitly — and partially comply even then, so the
   gate's merge machinery (not the prompt) is the real guarantee.
3. **Convergent facts need convergent keys.** *(Run-1 failure.)* The
   letter's "over forty thousand liters" and the core's 41,200 landed on
   different entities and attributes, so the engine never saw them converge.
   Rules: approximate quantities as structured bounds (`{"gte": 40000}`);
   when a later source confirms/refines the same fact, SAME entity, SAME
   attribute. The corroborate-vs-conflict machinery is key-local; the
   extractor controls the keys.
4. **Relations are under-extracted by default; properties are not.**
   *(Run-1 failure.)* 5 connects_to edges for a story that walks a long
   route twice. Name each relational category you need (routes, containment,
   knowledge transfer, causality) and say "every one the text describes."
   With the equally explicit negative: never an edge the text doesn't
   support — proximity is not connectivity.
5. **Scope `timeless` to a whitelist.** *(Run-1 failure, minor.)* "timeless
   = permanent facts" produced timeless STATE rows (a dead man's status, a
   meter's location). Whitelist instead: identity and structure only (kind,
   names, fixed adjacency); everything that holds-at-a-time gets stamped.
6. **The never-invent floor and the texture negative hold well.** *(Run-1
   success.)* "Extract only what the text supports; atmosphere is not an
   assertion" produced zero phantom contents in two sealed containers and
   zero texture rows. The provenance vocabulary was used correctly unaided
   (stated/inferred/assumed all present and apt — the narrator's filed
   theory arrived as `assumed`, which is what let the engine catch its own
   incumbency bug). Document claims with `source_doc` worked first try.

## B. How to feed the text (mechanics)

7. **Chunk small; split on discourse boundaries.** ~3.5k chars per call.
   Oversized scenes (6.8k) degraded both latency and adherence; paragraph-
   boundary sub-splits cost nothing narratively. *(Run-1/2 operational.)*
8. **Thread a roster, not a transcript.** Each chunk's context carries the
   entity ids + primary names seen so far (the extractor's own prior
   output — never grading material). This is what keeps ids stable across
   chunks. It grows linearly; cap it and prefer recent + frequently-referenced
   entities when it overflows.
9. **Give one explicit time convention, anchored in the text's own cues.**
   "Day 0 = the night the meter went dark; derive offsets from the text's
   own statements" — the prose carries its own clock ("three days ago,"
   "three weeks"); the convention just names the origin. The scene cursor is
   the fallback stamp when a fact carries no textual anchor.
10. **Defer classification; batch it.** Inline per-row classification is a
    model call per ambiguous row. The sidecar is rebuildable by design, so:
    extract first, classify in batches of ~40 after each chunk. Same
    judgments, an order of magnitude fewer round trips.
11. **Harden the shim like any flaky network client.** Timeouts sized to
    the biggest chunk (600s beat 300s), retry with backoff (transient
    CLI/API exit-1 bursts are real), capture stdout AND stderr in errors,
    resume-by-chunk so a 45-minute run never restarts from zero. The
    subprocess CLI shim is the zero-setup choice, not the fast one; a direct
    SDK shim and parallel chunks are the known throughput levers. Learned in
    run 2 (2026-06-11): quota exhaustion is a distinguishable failure mode,
    and the CLI prints it to stdout, not stderr. A shim must detect quota
    exhaustion and stop or pause instead of burning retries; a monthly-spend
    limit killed 3 chunks, and the burst of failed retries cost the chunks
    outright.

## C. What the engine guards so the prompt doesn't have to

The gate's invariants caught real extractor sloppiness with no prompt help;
design pipelines to lean on them rather than over-tuning the contract:

12. **Attribute canonicalization with receipts** — `located_in` → `in`
    fired in run 1; the fold key never fragmented. *(Engine guard, worked.)*
13. **Cursor stamping** — every non-timeless row got a valid_from even when
    the model omitted one. *(Engine guard, worked.)*
14. **Role-checked appends + the never-promotable statuses** — nothing the
    extractor emits can become `generated` or `default`, and fixtures can't
    sneak past the gate. *(Engine guard, by construction.)*
15. **Truth maintenance over extraction noise** — the deliberate reactor
    contradiction survived ingestion *as a contradiction*: flagged, both
    rows alive, no silent merge. Conflict detection downstream of a noisy
    extractor is a feature, not a bug filter. *(Run-1 success.)*
16. **Assumption quarantine at the fold** — a character's filed theory
    (`assumed`) cannot hold incumbency over a later observation. Found BY
    run 1, fixed in the engine, not the prompt. *(Engine fix.)*

## D. Grading discipline (for anyone building an eval like ours)

17. **The grader must find the extractor's entities, not dictate them.**
    Score candidate entities by alias hits + id-slug matches + row counts;
    never break ties alphabetically. Half of run 1's apparent failures were
    grader resolution misses against a correct log.
18. **Classify failures by where the fix lives.** extraction = the log is
    missing/mangled content (fix the contract, re-run); shape = the engine
    misbehaved over correct rows (stop, whitepaper conversation). Verify
    every shape label against the raw dump before escalating — run 1's
    three "shape" flags resolved to two grader bugs and one real engine fix.
19. **Answer-key hygiene is structural, not behavioral.** The bible never
    reaches the ingestor (scan the input for markers and abort); fixtures
    are expected values in the grader only; the seed version is stamped on
    every scorecard and never compared across versions. *(Letters 004/006.)*

## E. Design direction: registry-first ingestion (minimal turns, no accuracy loss)

Where the minutes went in runs 1–2, ranked: (1) output-token volume — verbose
per-item JSON spends 100–200 generated tokens per ~25-token assertion;
(2) per-call fixed cost × call count — full contract re-sent per chunk
through a fresh CLI subprocess, no prompt caching; (3) a self-inflicted
serial chain — chunks sequence only to thread the entity roster;
(4) all-or-nothing retries; (5) classification as its own call series.

The system that falls out — three sequential rounds regardless of document
length:

- **Pass 0 — scaffold (1 turn).** A novella is ~7k tokens; read it WHOLE and
  emit only the skeleton: entity registry (ids/names/aliases/kinds), timeline
  + anchors, place graph. Identity becomes globally consistent by
  construction — full-document hindsight beats any forward roster, killing
  rules 1–2's failure modes at the root.
- **Pass 1 — extraction (N turns, parallel).** Scene chunks extract against
  the FIXED registry in a compact line grammar
  (`obj:core|in|place:seed_vault|vf=4|stated|canon`), deterministically
  parsed, malformed lines rejected at the gate. No roster threading → chunks
  independent → wall clock ÷ parallelism. Durability rides along as a
  per-line hint that guardrails validate, escalating only low-confidence
  rows.
- **Pass 2 — audit (1 turn).** Present the folded world + the gate's anomaly
  list (open conflicts, orphans, unstamped rows, alias collisions); take
  corrections through the proper write paths. Parallel-seam errors get
  caught here, so parallelism costs no accuracy.

Expected: ~17 sequential rounds → 3; output tokens ÷ ~4; SDK shim with
cached contract/registry prefixes removes the fixed overhead. Engine changes
required: none (asserted_at is log order — out-of-order parallel arrival is
already legal; merge/maybe_same_as absorbs residual identity seams).

### E.1 Measured durations (the baselines)

Per-chunk timings from the run logs (durations include the following
classification batch; rows/min = assertions landed per wall-clock minute):

| Approach | Wall clock | Rows | Throughput | Notes |
|---|---|---|---|---|
| Run 1 (serial chunks, JSON, 300s cap) | ~77 min across 3 invocations | 455 | ~6 rows/min effective | ~41 min of that was burned by 4 failed attempts (timeouts + exit-1 burst) and their retries |
| Run 1, successful calls only | ~36 min | 455 | ~13 rows/min | per-call: 176–482s |
| Run 2 (serial chunks, JSON, contract v2, 600s cap) | in flight; 48 min for first 410 | ~2× run-1 density | ~8.6 rows/min | richer contract → bigger outputs → slower calls (275–1008s); the 1008s chunk includes one 600s timeout + successful retry |

What the numbers pin down: successful-call generation runs ~45–50 tok/s
(model-typical), so **generation speed is the floor and tokens-per-assertion
is the lever**. Verbose JSON spends ~80–200 output tokens per assertion;
the compact grammar spends ~25. Failed attempts are the other large term:
every timeout costs its full cap with nothing salvaged.

### E.2 Registry-first, analytical estimate (same model, same ~45 tok/s)

To be validated when built; stated so the claim is checkable:

| Pass | Calls | Output tokens | Est. duration |
|---|---|---|---|
| 0 — scaffold (whole novella in) | 1 | ~2k (registry+timeline+graph) | ~60–90s |
| 1 — extraction (compact grammar) | ~8, parallel | ~700 assertions × 25 ≈ 17.5k total, ~2.2k/chunk | wall = slowest chunk ≈ ~90s |
| 2 — audit (folded world + anomalies in) | 1 | ~1k corrections | ~60s |
| **Total** | **10 calls, 3 sequential rounds** | **~20k out (vs ~80k+)** | **~4–5 min wall (vs 48–77)** |

Predicted: ~10–15× wall-clock, ~4× output-token cost, and the failure term
shrinks with the per-call output size (smaller outputs rarely hit caps;
per-chunk retries are cheap and parallel).

**Caveat:** pass-0-fits-in-context holds for a novella, not a million-word
archive — at scale the scaffold goes hierarchical (per-arc registries merged
through the identity machinery). Unbuilt; the natural moment is the
anchor.world production pipeline, which wants exactly this efficiency.

## Open items

- Run-2 deltas (validation or refutation of rules 1–5) — pending.
- Conversational/messy-dialogue ingestion rules — pending the micro-eval.
- Registry-first ingestion (§E) — designed, unbuilt; measure against runs
  1–2 as baselines when built.
