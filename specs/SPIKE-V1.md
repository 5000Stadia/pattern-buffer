# SPIKE-V1 — the engine spike

**Status:** draft for independent review (Codex). Whitepaper §18 is the reviewer's rubric.
**Source of authority:** `docs/WHITEPAPER.md` (canonical; §22 defines this spike), the instructor rulings in dev_inbox letter 002 (carry spike authority; flagged for whitepaper amendment), and the eval handling rules in letters 003–006. Where this spec and the whitepaper disagree, the whitepaper wins.

## 1. Purpose and acceptance

Build the engine — `PatternBuffer` + derived indexes + classifier sidecar + projector + resolver + `refer()` tier 1 — in pure Python over SQLite, host-blind, with the chapter test (whitepaper §19.1) as the acceptance gate. The interrogation battery mirrors the 33-point coverage matrix (letter 003) 1:1; fixtures are mechanically transcribed from `evals/last_honest_meter/bible.md`, never produced by the ingestor under test, and the ingestor never sees the bible (letter 004).

Acceptance = the battery runs end-to-end and produces a scorecard classifying every failure as *extraction* (fix and re-run) or *shape* (stop; founder conversation). The correctness criterion is round-trip compatibility: `materialize(classify(ingest(W))) ≈ W` up to prose freedom and resolved gaps.

## 2. Scope

**In:** assertion log; derived indexes (current-state fold, containment tree, lateral graph, durability sidecar, identity registry, thunk table); classifier with deterministic guardrails; `materialize()` with the four lenses; resolver with the three policies; `refer()` tier 1 (tiers 2–3 as contracts); ingest gate (scene cursor, attribute canonicalization, identity resolution, provenance discipline); truth maintenance (constitutive-contradiction and cross-source flags, retraction); the JSONL dump format + deterministic builder seam (letter 005 item 6); the chapter-test harness, fixtures, battery, and scorecard.

**Out (stubbed or absent, per §22):** clocks, evidence graph, character engines, staleness decay schedules, `deny`/`reserve` policy beyond an enum that refuses, the `arch` CLI, MCP wrapper, frame-inclusion edges (letter 002 Q2: implement only if the seed's fixtures need them — they don't; the bible enumerates frame rows explicitly), tier-2/3 `refer()` behavior beyond the contract, embedding/vector anything.

## 3. The must-honor list (non-negotiable at spike scale)

From §22 plus the 002 rulings; each maps to at least one test in §12.

1. `world_id` partitioning from day one: file = the buffer (one SQLite file per world), **and** `world_id` stamped on every row as a cross-wiring guard (002 Q5).
2. Two time axes on every assertion; as-of queries first-class on both.
3. Append-only log + rebuildable sidecars. No code path updates or deletes an assertion row — enforced by code *and* by SQLite triggers that raise on UPDATE/DELETE.
4. Full provenance vocabulary (`stated`, `observed`, `inferred`, `assumed`, `generated`, `default`, `retracted`); `generated`/`default` never promotable.
5. The frame field with the absence discipline: out-of-frame rows are absent from served payloads, never marked or redacted; filtering at source.
6. Single-parent move semantics across the **containment family** (002 Q1): `in`, `within`, `held_by`, `worn_by`, `carried_by` fold as one logical key; a new family edge supersedes the prior one as one operation.
7. Attribute canonicalization at the ingest gate; receipts in the log, the alias map in a sidecar rebuildable from the receipts (002 Q6).
8. Role-authority matrix enforced in code (§6 below); test fixtures go through the ingestor, never the buffer directly.
9. The budget invariant: the CONSTITUTIVE spine is never compacted out of a materialization.
10. Open-world store / closed-world projection with `default` marking.
11. STATE and EVENT rows always carry `valid_time` (002 Q4); timeless is legal only for CONSTITUTIVE/DISPOSITIONAL.

## 4. Data model

### 4.1 Assertion row

The model is triples-on-triples (assertions are addressable; metadata is reified as assertions about assertions). Hot fields are denormalized into columns; nothing is special-cased.

```
assertions(
  seq         INTEGER PRIMARY KEY,        -- append order; THE transaction time (see §4.2)
  id          TEXT UNIQUE NOT NULL,       -- "a:<seq>"; stable, addressable
  world_id    TEXT NOT NULL,
  entity      TEXT NOT NULL,              -- entity id, or an assertion id (meta-assertion)
  attribute   TEXT NOT NULL,              -- canonicalized at the gate
  value_type  TEXT NOT NULL,              -- 'entity' | 'literal' | 'unresolved'
  value       TEXT NOT NULL,              -- entity id, JSON literal, or thunk sentinel
  valid_from  REAL,                       -- world time; NULL = timeless
  valid_to    REAL,                       -- NULL = open
  frame       TEXT NOT NULL DEFAULT 'canon',
  status      TEXT NOT NULL,              -- provenance vocabulary
  confidence  REAL,
  asserted_at INTEGER NOT NULL            -- == seq for normal appends (kept explicit for audit)
)
```

Triggers: `BEFORE UPDATE` and `BEFORE DELETE` on `assertions` → `RAISE(ABORT)`. The Python layer exposes no update/delete method; the triggers are belt-and-braces against future code.

Entities are not a table: an entity exists iff asserted (`assert(entity, kind)` appends `(entity · kind · <kind>)`). Kind defaults are renderer-side data, never rows.

### 4.2 Time

- `valid_time` is a numeric orderable scalar (REAL). For the chapter test it is a **spine ordinal**: the seed's event spine is a monotonic timeline whose positions map to numbers `1..N` (the bible's `e1..eN` labels map to their indices); the scene cursor always holds a position on it; the ingestor stamps every STATE/EVENT row `valid_from = current position` (002 Q4). Real timestamps (tracking mode) are just a timeline whose units are seconds — same machinery, no engine change.
- `asserted_at` is the **log sequence number — permanently**, not wall clock. This is a spec-level decision (flagged as a whitepaper-amendment candidate): transaction time means "when the system learned it," and learn order *is* log order; the deterministic builder (§10) must reproduce a byte-identical dump, which wall clock would break. When wall-clock learned-at matters (tracking mode, document trust chains §7.1), it is an ordinary reified meta-assertion on the row — the whitepaper's real-date examples are that meta-assertion, not the `asserted_at` column.
- As-of queries take `(valid_as_of, asserted_as_of)`, either optional; **omitted means "no bound"** — `valid_as_of` omitted = end of time (now), `asserted_as_of` omitted = the current log head. `materialize()`'s `as_of` is `valid_as_of`; it takes a separate optional `asserted_as_of` (defaulting to log head) so both axes are first-class on the read API.
- **Visibility, exactly:** a row is *visible* at `(valid_as_of, asserted_as_of)` iff `asserted_at <= asserted_as_of`, no retraction of it has `asserted_at <= asserted_as_of`, and it is valid at `valid_as_of` (`valid_from IS NULL OR valid_from <= valid_as_of`, and `valid_to IS NULL OR valid_to > valid_as_of`). Visibility is class-blind; **which visible row a fold serves is class-dependent and defined solely in §7** — there is no generic winner rule. For the STATE class, §7's winner is max by `(valid_from, asserted_at)` lexicographic, `NULL valid_from` ordered lowest; this is what makes the late-revealed off-screen move correct: the Ch.3-asserted move row carries a Ch.1-era `valid_from`, so as-of-the-assembly queries with `asserted_as_of` ≥ Ch.3 select it over the older drawer row.

### 4.3 Sentinels and structural predicates

- Thunk sentinel: `value_type='unresolved'`, value carries `{policy, constraints?}` JSON.
- Structural predicates fixed by the engine: `kind`, the containment family (`in`, `within`, `held_by`, `worn_by`, `carried_by`), `connects_to`, `adjacent_to`, `caused_by` (EVENT causality — a survival-checklist predicate, never left to free vocabulary), plus the engine's own meta-attributes (`superseded_by`, `retracts`, `source`, `same_as`, `maybe_same_as`, `canonicalized_from`, `resolved_by`, `justified_by`, `world_defining`). Domain vocabulary emerges freely through the canonicalization gate.

## 5. Module layout

```
src/patternbuffer/
  __init__.py   World: PatternBuffer + physics (policy, decay=off) + indexes; public API
  buffer.py     PatternBuffer: append-only store, schema, triggers, as-of row selection
  roles.py      role capabilities + the authority matrix (§6)
  indexes.py    current-state fold, containment tree, lateral graph (derived, rebuildable)
  classify.py   durability classifier: guardrails + injected-model judgment; sidecar
  identity.py   registry: anchors, aliases, SAME_AS / MAYBE_SAME_AS, merge-as-event
  thunks.py     thunk table (derived) + resolver (the only `generated` writer)
  project.py    materialize(): lenses, per-frame fold, budget, `default` marking
  refer.py      three-tier cascade: tier 1 deterministic; tiers 2–3 contracts
  ingest.py     the gate: scene cursor, canonicalization, identity, classify, append
  tmaint.py     truth maintenance: conflict detection (derived), retraction (log)
  dump.py       JSONL dump + deterministic builder (round-trip identical)
  testing.py    StubModel (exists)
evals/
  last_honest_meter/   story.md, bible.md (committed)
  harness/             fixtures.py (transcribed from bible), battery.py, scoring.py
```

`World("anchor.world", model=callable, policy=...)` is the only construction path. The engine imports nothing host-shaped; `model` is the single outside dependency.

## 6. Roles: the authority matrix in code

Each writer role is a class holding a private capability token; `PatternBuffer.append(assertion, role)` validates `assertion.status ∈ role.allowed_statuses` and rejects otherwise. Tokens are constructed only inside `World` wiring — application code (and tests) cannot mint one.

| Role | allowed statuses | notes |
|---|---|---|
| Ingestor | `stated`, `observed`, `inferred`, `assumed` | owns scene cursor, canonicalization, identity, provenance at the gate |
| Classifier | — (sidecar only) | never appends to the log |
| Resolver | `generated` | only under inherited constraints; inline, with append authority |
| TruthMaintenance | `retracted`, `inferred` meta-assertions | retraction/supersession meta-rows only |
| Projector | — | nothing durable; render-time `default` marks exist only in the materialization payload |
| Renderer | — | not in the engine at all; nothing to enforce because there is nothing it can call |

The deterministic executor (clocks) is out of spike scope; when it arrives it performs deferred Ingestor writes, no new authority.

**Test-fixture discipline (letter 001 §3, letters 004/005) — two strictly separate fixture kinds:**

- **Synthetic engine/harness fixtures** (unit tests, harness self-tests): worlds built through `World.ingest_structured(...)` — a no-model ingestor entry point that accepts pre-extracted assertion dicts but still runs the full gate (canonicalization, identity, stamping, classification, role-checked append). The gate is the API; only the LLM extraction step is bypassed. Content is invented for the test (micro-fixtures), **never derived from the bible or the story**.
- **Chapter-test grading fixtures** (bible-transcribed): *expected values only* — they live exclusively in the grader (`evals/harness/fixtures.py`) and are compared against query results. Bible content **categorically never passes through any ingest path or into any World**; the graded world is built solely by fresh ingestion of `story.md` through the model-backed ingestor under test (004 items 1–2, 005 item 4). The harness asserts this structurally: the grading world's log contains no row whose provenance source is the bible, and the ingestion input is scanned for bible markers (§11).

## 7. Derived indexes (deterministic, no LLM, rebuildable)

- **Current-state fold — durability-aware.** The fold consults the sidecar; recency-wins supersession applies **only to STATE** (whitepaper §13: "fold STATE by supersession"). Per durability class, among visible rows (§4.2 comparator) on one fold key, per frame — a belief fold never overwrites canon:
  - **STATE:** latest visible row wins — max `(valid_from, asserted_at)` per §4.2 — **within a source class** (whitepaper §7.2: supersession-by-key is automatic only within a source class; source class = the provenance status plus, for `observed` rows, the document-vs-first-person distinction of §7.1). **Evidence rank at the fold** (the assumption quarantine, generalized after run 3): source classes carry rank — `{stated, observed}` > `generated` > `inferred` > `assumed`. Lower-rank rows never hold incumbency against higher-rank rows on the same key: authored/observed truth arriving over an inference or assumption is confirmation or correction, never a conflict to ask about; provisional rows serve only while they are all that exists. The cross-source corroborate-vs-flag machinery below applies **between peer classes only** (e.g. `stated:document` vs `stated:direct`). *(Run 1: a narrator's `assumed` theory held off the actual discovery. Run 3: a narrator's wrong `inferred` theory outheld later `stated` canon. Same lesson, full generality.)*

Rank semantics, exactly (letter 015): ranks compare **within a frame only** — a belief fold never competes with canon; `retracted` is **excluded by visibility before ranking**, never ranked low. And the justification for `generated` > `inferred` is **mode-dependent by design**: in fiction mode `generated` is canon-by-invention (resolver-authored truth under constraints), while `inferred` is a belief *about* the world; in tracking mode the comparison cannot occur, because `observe_or_unknown` never mints `generated`. Do not "fix" the rank for tracking mode — it would break fiction and protect nothing. Across source classes, behavior depends on whether the values **conflict**: a newer visible row from a different source class whose value *agrees* with the in-class winner (equal, or a refinement of an approximate value) **corroborates** — no flag, no ask; the fold serves the more precise value and the convergence is visible as two provenance chains on the key (the letter's ~40,000 L and the core's 41,200 L converge, per letter 004). A newer different-source-class row whose value *disagrees* does **not** supersede: it fires the cross-source conflict flag (§7 conflict table) with an ask, the fold continues to serve the prior in-class winner, and the payload marks the key conflicted — never silent last-write-wins across source classes. Resolution is an explicit appended supersession/retraction (e.g. the answered ask), after which the fold follows it.
  - **DISPOSITIONAL:** defeasible — a later DISPOSITIONAL row on the same key defeats the earlier (whitepaper §5: "overridable by stronger later evidence"; recency is the spike's measure of strength).
  - **CONSTITUTIVE:** never superseded by recency. A second visible, non-identical CONSTITUTIVE row on a fold key fires the truth-maintenance flag (§7 conflict table); the fold serves the **earliest-established** value with the key marked conflicted in the payload, until an explicit retraction/supersession meta-assertion resolves it. A later row can never silently win.
  - **EVENT:** immutable; never folds, never superseded — `what_happened` serves the chain as appended.
  - Fold key = `(entity, attribute, frame)` — except the containment family, which folds as `(entity, FAMILY, frame)` (002 Q1): `relate(jacket, worn_by, morpheus)` supersedes `(jacket, in, box)` as one operation. (Family supersession is a STATE behavior; fixture containment is CONSTITUTIVE per the classifier sub-rule, so a fixture's edge is protected by the CONSTITUTIVE rule above.) Routine supersession is **purely derived** (P2); explicit `superseded_by` meta-assertions are written only for corrections, retractions, and identity re-binding.
- **Containment tree:** single-parent walk to root over the family's folded edges. `locate(x)`, `contents(x)` derive from it; emptiness is a query result, stored nowhere.
- **Lateral graph:** `connects_to`/`adjacent_to`, many-to-many; `path(a, b)` by BFS.
- **Durability sidecar:** `classification(assertion_id, durability, class_confidence)` table, rebuildable by re-running the classifier over the untouched log.
- **Identity registry:** anchors (names/aliases/roles/recurring locations/features) as ordinary assertions; `same_as`/`maybe_same_as` edges; merges logged as events, repaired forward by retraction. Reads resolve through the union-find closure of `same_as` at query time.
- **Thunk table:** the non-superseded `value_type='unresolved'` rows — the frontier. Thunks move without resolving: a containment-family supersession on the holder never touches the thunk row.
- **Canonicalization map:** alias → canonical attribute decisions, rebuildable from `canonicalized_from` receipts in the log (002 Q6).
- **Conflict table (truth maintenance):** derived detection of (a) contradicting CONSTITUTIVE rows on one fold key, (b) cross-source-class conflicts on one key (§7.2 whitepaper). A fired flag is a sidecar row pointing at both assertion ids; both rows coexist in the log untouched. Resolution, when it happens, is appended (retraction or supersession) — never required for the flag to stand. **The reactor contradiction in the seed must fire this flag and remain unresolved: flagged coexistence = PASS, silent merge = FAIL (letter 004 item 3).**

All sidecars carry a `rebuild()` that drops and re-derives from the log; tests assert fold/sidecar equality after rebuild.

## 8. Classifier

`classify(assertion, world_context) -> {durability, class_confidence}` via the injected callable, wrapped in deterministic guardrails that run first and short-circuit:

- structural containment of a fixture → CONSTITUTIVE; movable → STATE (the named sub-rule);
- `kind` and `connects_to` → CONSTITUTIVE;
- EVENT reification (rows written by `event()`) → EVENT;
- asymmetric defaults: ambiguous property → STATE; ambiguous fixture containment → CONSTITUTIVE; low-confidence CONSTITUTIVE verdicts marked for review in the sidecar;
- `world_defining` pin honored as an explicit input, never inferred.

Accrual promotion (STATE→DISPOSITIONAL on repetition) is implemented as a sidecar re-derivation rule but **not exercised by the seed** (letter 004: NOT PLANTED — the scorecard says so). Contradiction of a CONSTITUTIVE row raises the conflict flag (§7), never a rewrite.

## 9. Projector, resolver, refer()

### 9.1 `materialize(scope, as_of, frame, lens, budget, asserted_as_of=None) -> Materialization`

(`as_of` is `valid_as_of`; `asserted_as_of` defaults to the log head — both time axes first-class per §4.2.)

Lenses per whitepaper §13: `establishing_set` (CONSTITUTIVE + DISPOSITIONAL + establishing STATE — first by `valid_time`, tie-broken by `asserted_at`, qualifying iff the row carries no `caused_by` edge to an EVENT in the same frame (002 Q3); honors `world_defining`), `current_state`, `what_happened` (time-ordered EVENT chain with causality edges), `character_sheet`.

Algorithm as §13: in-scope, in-frame selection at `as_of` → per-frame fold → tree walk ordered by depth and salience → kind-default gap fill, every fill marked `default` in the payload only → forced thunks routed through the resolver (whose appends feed back through classification — closed under its own operations) → shape to budget, CONSTITUTIVE spine exempt. Salience = projection-time ranking (recency, reinforcement, reference frequency), cacheable, never authoritative, never stored as truth.

Frame discipline: the payload contains only rows whose `frame` matches the requested frame (strict self-containment, 002 Q2 — no canon inheritance, no inclusion edges in spike). Out-of-frame rows are structurally absent.

### 9.2 Resolver

`resolve(entity, aspect, frame='canon', access=None)` forces a thunk per its policy. The `access` parameter is the observer-position seam for access-gated resolution depth (whitepaper §8: detail resolves only to the level the observer's position grants); **access-gated depth is declared out of the spike's exercised behavior** — the seed's thunk cases don't exercise it — but the parameter exists from day one so gating lands as a behavior change, not a signature change. Per policy: `invent_under_canon` walks the containment chain collecting CONSTITUTIVE + DISPOSITIONAL constraints (plus the thunk's own stored constraints — which include history accreted while it moved), calls the model, appends results as `generated`, and appends a `resolved_by` meta-assertion — memoization is the fold; a second force serves the cache. `observe_or_unknown` never invents: it returns *unknown* unless observation rows exist. `deny`/`reserve` refuses. Force-once is asserted across World re-instantiation (the drawer test, literally).

### 9.3 `refer(description, scope, frame, constraints, as_of=None) -> Resolution`

Tier 1 (deterministic, spike-real): exact name/alias hit through the identity registry; unique-kind-in-scope under the scene cursor / given scope; **constraint inversion** (resolve the container by the contained, the owner by the possession — flip the lookup direction before calling any model). Tier 2 (contract + stub): strict-schema model call returning a resolution receipt (candidates, signals, confidence). Tier 3 (contract): returns `Underdetermined(candidates)` — the ask is the host's to deliver; the engine never guesses below the confidence floor. Historical reference (as-of over identity anchors) is supported by the explicit `as_of` parameter, honored in tier 1.

**Accepted post-spike extension (letter 018, lands with the micro-eval):** (1) zero-candidate escalation — tier 1 yielding zero matches with a scope provided routes to tier 2 with the scope's members as candidates (scope-bounded only, confidence floor unchanged), so vocabulary miss stops masquerading as absence; (2) alias accrual — a tier-2/confirmed resolution of a novel term appends an alias assertion carrying the resolution receipt, discourse-scoped first, promoted on recurrence; a learned alias never outranks another entity's exact name; collisions are ordinary ambiguity. Micro-eval criterion: a synonym never used at ingest resolves via tier 2 on first use, tier 1a on second, both receipts in the log.

## 10. Dump format and builder (the 005 seam)

- `dump(world) -> JSONL`: one assertion per line, ordered by `seq`, canonical key order, no derived data. Diffable; the shipped `examples/anchor/` artifact later (post-chapter-test) is exactly this dump plus policy row.
- `build(jsonl, path) -> World`: replays rows in order through a builder-privileged append that preserves `seq`/`id`/`asserted_at` byte-for-byte but still enforces append-only, schema, and the status vocabulary. Builder privilege is a distinct capability that exists only inside `dump.py` and cannot be reached from ingest paths; it performs **no judgment** (no classification, no canonicalization — the dump already carries the log as it was) and then triggers sidecar `rebuild()`. **Restore is not a second write authority:** `build` refuses unless the target file is empty/absent; the dump carries exactly one `world_id`, matching the target World; `seq` is contiguous from 1; `id == "a:<seq>"` and `asserted_at == seq` on every row; every status is in the §7-whitepaper vocabulary. Any violation aborts the build — no partial restore, no multi-world import path.
- Round-trip test: `dump(build(dump(w))) == dump(w)` byte-identical.
- The chapter test always grades **fresh ingestion**; the shipped world is demo, golden master, and drift detector (fresh-ingest vs canonical dump diff), never the answer key.

## 11. The chapter-test harness

- **Inputs:** `story.md` (prose only — harness asserts the ingestion input contains no bible text: literal scan for bible-only markers, e.g. "STORY BIBLE", "Pass condition", "§" headers from bible.md) and a model callable (real model for graded runs; StubModel with scripted extractions for harness self-tests).
- **Fixtures:** `evals/harness/fixtures.py` — mechanical transcription of the bible's explicit statements (registry, spine, custody chains, frame rows, quantities, pass conditions). Where the bible is silent, the battery doesn't ask (letter 004 item 2).
- **Battery:** one question (or negative assertion) per 003 matrix item, keyed `Q1..Q33`, each scoring PASS / FAIL(extraction) / FAIL(shape) / NOT-PLANTED. Coverage honesty encoded: item 2 marked LIGHT (no planted non-connected pair), item 6's accrual marked NOT PLANTED, item 21 noted N=1 (letter 004 item 5). **Items 30–32 (mystery: discovery paths, breaking condition, clock material) grade stored representation only** — the `discoverable_via`/breaking-condition/clock rows exist with correct shape and provenance — never executable evidence-graph traversal, NPC behavior, or clock firing, which are out of spike scope per §22.
- **Highlights bound to the seed (letter 004 item 4):** the core's 7-hop custody chain with the off-screen Ch.1-assembly move (as-of during the assembly → Seed Vault, exercising valid_time ≠ asserted_at); the vault and false-drawer splits as underdetermined anchors at two scales; footlocker 0447 as thunk stability + thunk-moves-unopened; the cigarette tin 5→4 as quantity supersession on one entity (must not fork into five tracked cigarettes); two permanently unnamed identities (narrator, Pell's mother) tolerated never-bound; the letter's claims vs the core's confirmations as separate converging provenance chains, including the letter's planted error (the second books were *not* where the originals are kept).
- **Scorecard:** per-question verdicts + the extraction-vs-shape classification; sent to the founder and the Kernos inbox. Shape failures stop the line.
- **Seed versioning (letter 006):** the seed is DRAFT (`evals/last_honest_meter/SEED_VERSION`, currently `v0-draft`) until the founder stamps FINAL. The harness skeleton, bible-absence assertion, scorecard format, and fixture *loaders* (which read a structured answer key) build now; the answer-key transcription itself — event-spine, frame, and adjacency fixtures, plus any question whose ground truth lives in a named gap — is frozen only against the FINAL seed and is never derived by interpreting the prose. Every scorecard records the seed version it graded against; results are never compared across seed versions. The battery therefore separates **harness self-tests** (run against synthetic micro-fixtures, build now) from **graded fixtures** (wait for v1-final).

## 12. Test plan (invariants, not return values)

| Invariant | Test |
|---|---|
| Append-only enforced | no update/delete API exists; SQL UPDATE/DELETE raises via trigger; corrections append |
| Derive-don't-store | emptiness/location/age asserted absent from schema and from every table; computed answers correct |
| Containment-family move | `worn_by` supersedes `in` in one operation; both rows remain in log; fold shows one parent |
| As-of correctness | both axes, including valid≠asserted divergence (the off-screen-move shape) |
| Role matrix | every (role, status) cell: allowed appends succeed, forbidden raise; no capability mintable from test code |
| Frame absence | out-of-frame rows absent from payload (structural scan of the payload, not behavioral) |
| Rebuildability | drop every sidecar, rebuild from log, fold/index/classification equality |
| Thunks | drawer test verbatim (place, silence, retrieve identical across re-instantiation); force-once; thunk moves unresolved; `observe_or_unknown` never invents |
| Truth maintenance | CONSTITUTIVE contradiction → flag with both rows coexisting; silent merge fails the suite |
| Durability-aware fold | a later CONSTITUTIVE row never wins by recency (fold serves earliest + conflicted mark); STATE folds by recency; EVENT never folds |
| Round-trip | `dump(build(dump(w)))` byte-identical; `materialize(classify(ingest(W))) ≈ W` on a micro-fixture |
| No-LLM reads | StubModel with zero scripted responses across every deterministic read path (P7) |
| Provenance discipline | `generated`/`default` promotion attempts raise; document trust chain representable as reified rows |

## 13. Sequencing within the spike

Inside-out, per letter 001 §2 step 3: buffer → indexes → classifier sidecar → `materialize()` → thunks + resolver → `refer()` tier 1 → harness → run, score, report. The dump/builder seam (§10) lands with the buffer (it is mostly the buffer's serialization). Approved-batch mode: once this spec is GREEN and founder-approved, run end-to-end; pause only at genuine architectural forks or shape-class failures.
