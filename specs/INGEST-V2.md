# INGEST-V2 — registry-first ingestion

**Status:** draft for Codex review. **Authority:** decision A (confirmed,
founder + Kernos CC, 2026-06-11 — recorded in
`evals/results/2026-06-11-v1-final/REPORT.md`); design source: playbook §E +
letter-014 constraints + the decision-C stamping refinement. Whitepaper
invariants unconditionally in force; **the engine does not change** — this
spec is entirely harness/pipeline-side. Where this spec and the whitepaper
disagree, the whitepaper wins.

## 1. Problem and shape

Serial per-chunk extraction with a prose contract measured out at 77–96 min
per novella with partial, round-unstable compliance (runs 1–2: key
fragmentation, frame misfiles, identity splits — different failures under
differently-worded contracts). INGEST-V2 replaces it with three rounds:

- **Pass 0 — registry.** Establish/extend the world's skeleton from source
  text: entities (ids, names, aliases, kinds), canonical attribute names,
  timeline anchors, place graph.
- **Pass 1 — extraction.** Scene chunks extracted **in parallel** against
  the frozen registry, in a compact line grammar, parsed deterministically.
- **Pass 2 — audit.** The folded world + the gate's anomaly list reviewed
  once; corrections through proper write paths; **registry escapes** split
  out as their own failure class.

Acceptance (decision A's self-test): the chapter-test re-run clears most of
run 2's 16 extraction failures, at a small fraction of serial wall clock
(estimate ~4–5 min; 2–3× slippage planned for without changing the
decision). If it doesn't clear them, that is a finding about the approach —
stop and report, don't iterate silently.

## 2. Module layout (all under evals/harness/, importable for reuse)

```
evals/harness/
  registry.py     Pass-0: WorldRegistry dataclass + establish/extend calls
  grammar.py      The line grammar: render(prompt-side) + parse(gate-side)
  pipeline.py     Orchestration: pass-0 -> parallel pass-1 -> pass-2; quota-aware
  audit.py        Pass-2: anomaly collection, registry-escape detection, fix application
  model_shim.py   (exists) gains call_many(prompts) -> parallel execution
```

The engine's involvement is exactly three existing public seams —
`World.ingest_structured(...)` (the gate), `World.truth.retract(...)`
(corrections), and `world.ingestor.add_attribute_alias(...)` (the in-memory
canonicalization map, a non-log sidecar the harness replays from
`registry.json`) — plus the public read surface. Nothing in
src/patternbuffer/ changes.

## 3. Pass 0 — the registry

### 3.1 Interface (letter-014 constraint #2: establish/extend, never read-once)

```python
@dataclass
class WorldRegistry:
    world_id: str                     # partition key (whitepaper §16); checked on every use
    entities: dict[str, EntityCard]   # id -> {names, aliases, kind, anchors}
    attributes: dict[str, str]        # alias/variant -> canonical attribute
    timeline: TimelineSpec            # origin definition + named anchors (day offsets)
    places: list[tuple[str, str]]     # connects_to edges, per text only

def establish(text: str, model, prior: WorldRegistry | None = None) -> WorldRegistry
```

`prior=None` + whole document = the batch calling pattern (chapter test,
anchor.world). `prior=existing` + one turn of dialogue = the incremental
pattern (tracking mode, live play — the scene-cursor/lidar discipline).
The implementation may be identical; the *interface* must support both from
day one.

### 3.2 Pass-0 prompt contract

One model call per segment. Output: **compact registry lines** (E|/A|/O|/
N|/P|), deterministically parsed with rejects — run 3 measured the original
JSON output as the pipeline's dominant cost (29 of 66 min, incl. two
timeouts), so pass-0 got the same treatment as pass-1. The batch pattern
may pass `segments` (e.g. chapters) to scaffold incrementally:
establish over the first, extend over the rest — smaller calls, same
interface. The prompt carries the run-3 spatial-completeness rules:
nested containers as separate entities (desk AND its drawers), shared
aliases on split referents ("the vault" on both vaults), and P| edges only
for traversable passage (a defunct elevator is an entity, never an edge). Instructions carry
the five run-1 lessons that are registry-shaped: every referring expression
becomes an alias; one id per individual across the whole text (late naming
binds to the early id); one canonical attribute name per fluent (the
reactor lesson: `working_reactors`, not three variants); places get
connects_to edges exactly as the text supports; the timeline names its
origin event and known anchors.

### 3.3 Seeding the gate — inside the single commit (review r2)

Pass-1 never needs registry rows in the World: parsing and validation run
against the in-memory `WorldRegistry` (backed by `registry.json`), not
against World state. Registry seeding is therefore the **first phase of the
single commit** (§4.2), not a pre-pass-1 write. The commit sequence, total
and exact:

```
(pre-commit: all chunks staged OK; registry-escape repairs done)
1. seed registry      entity kinds + names/aliases (timeless, stated, via
                      ingest_structured); attribute aliases via
                      ingestor.add_attribute_alias; place edges (timeless)
2. replay chunks      staged items in chunk order, through the gate
3. post-commit audit  §5.2 repair ops (add via gate, retract via tmaint)
```

A failed run (any chunk permanently failed) commits **nothing** — including
registry seed rows; the failed-chunk test asserts the target World file is
absent/empty. The fold key can no longer fragment on anything the registry
pinned.

**World partitioning of harness artifacts (review r2):** `WorldRegistry`
carries `world_id`; `registry.json`, every staging file's header, and STAMP
all record it; the pipeline refuses to seed, replay, re-grade, or stamp when
the artifact's `world_id` differs from the target World's (whitepaper §16:
`world_id` partitions everything — including the harness's own artifacts).

**Registry durability (review r1):** `add_attribute_alias` is in-memory; the
engine's rebuildable map reads only logged receipts. Therefore the registry
itself is a persisted run artifact — `registry.json` beside the dump — and
the pipeline **replays alias seeding from it** on every resume/rebuild/
re-grade. Test: dump → build → re-seed from registry.json → variant-named
line canonicalizes identically, with a receipt. (The engine stays unchanged;
the harness owns registry persistence.)

## 4. Pass 1 — extraction in the line grammar

### 4.1 Grammar (one assertion per line)

```
entity|attribute|value|flags
```

- Split `entity|attribute` off with two `|` splits; fields 1–2 must match
  `[a-z][a-z0-9_:]*` (raw `|` is therefore impossible there). The value's
  end is found by **JSON boundary detection** (`raw_decode`) when it starts
  with `{`/`[`/`"`/`?{`, else by the next `|` — so delimiter characters
  inside JSON values can never split the line. *(Implementation note: a
  naive `split("|", 3)`, as r1–r4 of this spec said, corrupts JSON values
  containing `|`; caught at implementation, spec amended to match the
  correct behavior.)* The grammar is line-oriented, so newlines cannot
  occur inside a field. A `?` not followed by `{` is a reject — it signals
  intent-to-be-unresolved with a malformed policy, never a prose value.
- `value`: parsed as JSON when it starts with `{`, `[`, or `"` (covers any
  value containing `|` or commas — encode as a JSON string); `@entity_id`
  (entity ref); `?{policy}` for unresolved; otherwise a bare scalar
  (int/float/bool/str).
- `flags`: comma-separated `vf=4.5`, `vt=9`, `t` (timeless), `f=knows:person:x`,
  `s=stated|observed|inferred|assumed`, `doc=doc:id`, `cb=event:id` (caused_by).
- Defaults: canon frame, `stated`, cursor-stamped valid_from.
- Example: `obj:memory_core|in|@place:seed_vault|vf=4.5,s=stated`

`grammar.parse(lines, registry, cursor) -> (items, orphans, rejects)`:
deterministic. **Reference validation covers all four id positions** (review
r2): the subject entity, `@value` entity refs, `cb=` event ids, and the
entity inside `f=knows:<entity>` frames — a line with any unregistered id in
any position is **quarantined**: it goes to `orphans` as
`(chunk_id, line, entity_id, position)` and does **not** enter the item
stream; orphaned lines reach the log only after pass-2 extends the registry
and the affected lines re-parse (014 constraint #1 — escapes never pollute
the world they're meant to flag; review r1 blocker). `digest.frame_anoms`
(§5.2) remains as post-commit defense-in-depth only — with parse-time
validation it is expected empty, and a non-empty value indicates a pipeline
bug, not extraction noise. Malformed lines go to `rejects` with line
numbers. **Reject rate** = malformed nonblank lines ÷ total nonblank output
lines (orphans counted separately, they are not rejects); above the
threshold (default 20%) the chunk fails for retry.

**Staged items carry explicit `valid_from`** (review r2): the cursor default
is resolved at parse time — `parse` takes the chunk's cursor position and
stamps it into every item that neither carries `vf=` nor `t` — so staged
files are replay-complete and commit-time cursor state cannot drift from
extraction-time intent.

### 4.2 Parallelism, staging, and ordering (review r1: stage-all, commit-once)

Chunks are independent given the frozen registry: pass-1 runs a thread pool
over the injected callable (subprocess CLI calls parallelize fine; an SDK
shim is a drop-in improvement later, not a dependency). **No pass-1 output
touches the World during extraction.** Every chunk's parsed items stage to
disk (`staging/chunk_NNN.jsonl`); commit happens exactly once, replaying
staged items in chunk order through the gate, only after every chunk has
succeeded (including retries and registry-escape repairs). Consequences:
`asserted_at` deterministically follows source order (diffable dumps); a
run with permanently failed chunks is **noncanonical by definition** — it
never commits, and its staging directory is the resumable state.

**Registry slice for pass-1 prompts (review r1):** the full registry,
always, unless it exceeds a token cap (default ~6k tokens). Above the cap,
the deterministic fallback slice = the complete attribute map + timeline +
place graph + all person entities + any entity with a lexical alias hit in
the chunk text. Slicing is a size guard, not a relevance judgment.

Pass-1 prompt: the contract (compact: the grammar + the canon-vs-knows rule
+ never-invent floor) + the registry's relevant slice + the chunk text.
The canon-vs-knows rule gets its strongest phrasing here because it is the
one run-1/run-2 failure the registry cannot structurally prevent: *world
facts are canon rows at their true historical time; knows: rows are
additional copies; a revelation scene yields canon rows + knows rows, never
knows rows alone.*

### 4.3 Quota and failure behavior

`QuotaExhausted` aborts the run cleanly (already built). Per-chunk retry ≤2
with backoff; a failed chunk is recorded and the run continues (the
chunk-repair flags already exist). Timeout sized to grammar output
(~2.2k tokens/chunk → far under the 600s cap).

## 5. Pass 2 — audit

Pass-2 has two stages with different timing:

**5.1 Registry-escape repair (pre-commit).** Orphan records from 4.1 —
entities pass-0 never pinned. Handling: extend the registry (one model call
max, `establish(prior=registry)` over the orphaning lines' source text),
re-parse the quarantined lines (re-extract the chunk only if re-parse still
orphans), update `registry.json`. Runs before the single commit, so escapes
never enter the log at all. Escapes are reported in the scorecard's meta
block — never silently absorbed.

**5.2 World audit (post-commit).** The committed, folded world's anomaly
digest, assembled deterministically with **assertion ids throughout**:

```
digest = {
  conflicts:    [{key, kind, assertion_ids}],          # open TM flags
  unstamped:    [{assertion_id, entity, attribute}],    # STATE/EVENT, no valid_from
  drift:        [{assertion_id, attribute}],            # attribute in no registry entry
  frame_anoms:  [{frame, assertion_ids}],               # rows for unknown persons
  fold_winners: [{entity, attribute, value, assertion_id}],  # capped: entities in the
}                                                       # anomaly sets only, ≤200 rows
```

One model call reviews the digest and emits **repair ops**, not bare lines
(review r1 blocker — the grammar cannot express retraction, and corrections
must be retractions/supersessions, never edits, per letter 005):

```
add|<grammar line>                      -> World.ingest_structured (gate, role-checked)
retract|<assertion_id>|<reason>         -> World.truth.retract (truth-maintenance role)
```

No other op kinds exist; anything else in the output is a reject. **Audit
adds must carry an explicit time flag (`vf=` or `t`)** — there is no scene
cursor at audit time, so a defaulted valid_time would be fabricated; an
add without one is a dropped op (post-impl review note, made policy).
**Retracts apply only to exact duplicates** — the harness verifies another
surviving row carries the identical (entity, attribute, value, frame)
before applying; anything else the auditor wants gone is dropped with a
warning. (Run-3 lesson: handed drift anomalies, the auditor retracted
correct rows — Pell's age, Cray's credits. Wrongness beyond duplication is
the author's call, never the auditor's.) The
deliberate reactor contradiction must survive pass-2 — the audit prompt
explicitly forbids ops against flagged conflicts (they are questions for the
author, not the auditor), and the harness enforces it: a retract targeting
an assertion id listed in `digest.conflicts` is dropped with a logged
warning.

## 6. anchor.world stamping (decision C refinement)

The re-run writes: `ingest_dump.jsonl` (canonical-candidate), `registry.json`,
scorecard, REPORT. Promotion to `examples/anchor/` = copy dump + registry +
a STAMP file recording `world_id`, seed version, run id, score, and
bible-verification status — no rebuild, no re-ingestion. **The policy row is non-log metadata**
(a field in STAMP, read by the builder when materializing `anchor.world`) —
it is never an assertion row and never edited into a dump (review r1).
Bible-verification corrections (letter 005 item 3) append through
truth-maintenance/ingestor paths on the stamped world and re-dump; the
correction history stays visible by design.

## 7. Test plan (no-model, deterministic)

- grammar: parse coverage of every flag and value form (there is no
  `render()` — pass-1 emits lines; the model is the renderer); JSON-string
  values containing `|`/commas; reject-rate denominator (orphans excluded);
  **orphan quarantine** — quarantined lines absent from the item stream and
  from any committed log.
- registry: establish-then-extend equivalence (batch once ≡ incremental
  twice over split text, given identical model outputs — stub-scripted);
  gate seeding produces receipts on variant attribute use; **registry.json
  replay** — dump → build → re-seed → identical canonicalization with
  receipts.
- pipeline: parallel pass-1 with a stub callable lands a byte-identical dump
  to serial (stage-all/commit-once ordering invariant); a failed chunk →
  no commit **including zero registry seed rows** (target World file
  absent/empty); resumable staging; quota abort leaves staging intact;
  `world_id` mismatch on registry.json/staging/STAMP refuses to
  seed/replay/re-grade/stamp; staged items all carry explicit valid_from
  (replay needs no cursor state).
- audit: planted orphan → escape report + registry extension + re-parse,
  then commit with zero orphan rows; **repair-op routing** — `add` lands via
  the gate, `retract` via truth-maintenance, anything else rejected;
  planted flagged conflict survives pass-2 (retract against a conflicted id
  dropped with warning).
- Existing 57-test engine suite untouched and green (engine unchanged).

## 8. Out of scope

SDK shim (drop-in later), hierarchical registries for archive-scale corpora
(interface allows; not built), the messy-dialogue micro-eval (next chapter),
porcelain verbs (post-adapter-spec), any engine change whatsoever.


## 8. Accepted next-cycle design (letter 019 rulings; build with the next pipeline iteration)

- **Registry self-check — propose, never auto-merge.** A dedupe pass over
  the assembled registry (name/alias overlap heuristics) emits
  MAYBE_SAME_AS edges carrying their evidence; merges remain logged events
  confirmed at audit or by tier-2 judgment. Two deliberately-distinct
  same-named entities must survive the pass unmerged. (Letter-013's
  loop-closure rule at ingest time: recognition proposes, evidence
  collapses.)
- **`M|a|b` grammar line — proposal semantics only.** Parses as a
  MAYBE_SAME_AS proposal with chunk provenance; promotion to a merge event
  happens at pass-2/self-check where the whole world is in view. A parallel
  chunk never holds merge authority.
- **SDK shim may be pulled ahead of the micro-eval** (no upstream
  dependency; operational call) — it removes the CLI per-call floor and the
  max-turns failure class.
