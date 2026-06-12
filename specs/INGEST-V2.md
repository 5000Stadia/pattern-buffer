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

The engine's only involvement remains `World.ingest_structured(...)` (the
gate) and the public read surface. Nothing in src/patternbuffer/ changes.

## 3. Pass 0 — the registry

### 3.1 Interface (letter-014 constraint #2: establish/extend, never read-once)

```python
@dataclass
class WorldRegistry:
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

One model call (batch pattern). Output: the registry as JSON (this is the
one place verbose JSON is fine — it's ~2k tokens, once). Instructions carry
the five run-1 lessons that are registry-shaped: every referring expression
becomes an alias; one id per individual across the whole text (late naming
binds to the early id); one canonical attribute name per fluent (the
reactor lesson: `working_reactors`, not three variants); places get
connects_to edges exactly as the text supports; the timeline names its
origin event and known anchors.

### 3.3 Seeding the gate

The registry pre-seeds the World before any pass-1 row arrives: entity kinds
+ names/aliases via `ingest_structured` (timeless, `stated`), attribute
aliases via `Ingestor.add_attribute_alias` (the canonicalization map —
receipts fire normally when pass-1 lines use variant names), place edges as
timeless structural rows. The fold key can no longer fragment on anything
the registry pinned.

## 4. Pass 1 — extraction in the line grammar

### 4.1 Grammar (one assertion per line)

```
entity|attribute|value|flags
```

- `value`: `@entity_id` (entity ref), bare scalar, `{json}` for structured
  literals (e.g. `{"gte":40000}`), `?{policy}` for unresolved.
- `flags`: comma-separated `vf=4.5`, `vt=9`, `t` (timeless), `f=knows:person:x`,
  `s=stated|observed|inferred|assumed`, `doc=doc:id`, `cb=event:id` (caused_by).
- Defaults: canon frame, `stated`, cursor-stamped valid_from.
- Example: `obj:memory_core|in|@place:seed_vault|vf=4.5,s=stated`

`grammar.parse(lines, registry) -> (items, rejects)`: deterministic; a line
referencing an entity id not in the registry is NOT dropped — it parses into
the item stream AND emits an **orphan record** `(chunk_id, line, entity_id)`
for pass-2 (014 constraint #1). Malformed lines go to `rejects` with line
numbers; rejects above a threshold (default 20%) fail the chunk for retry.

### 4.2 Parallelism and ordering

Chunks are independent given the frozen registry: run pass-1 with a thread
pool over the injected callable (subprocess CLI calls parallelize fine; an
SDK shim is a drop-in improvement later, not a dependency). Results land in
chunk order — completed chunks buffer until their predecessors commit, so
`asserted_at` keeps narrative order (cheap determinism for dump diffing; the
engine doesn't require it).

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

Input: the folded world's anomaly report, assembled deterministically:

1. **Registry escapes** (the §E-specific class): orphan records from 4.1 —
   entities pass-0 never pinned. Handling: extend the registry (one model
   call max), re-extract ONLY the affected chunks, re-fold. Escapes are
   reported in the scorecard's meta block — never silently absorbed.
2. Open truth-maintenance conflicts (expected: the reactor flag — left in).
3. Unstamped STATE/EVENT rows; rows whose attribute appears in no registry
   entry (drift candidates); frames containing rows for unknown persons.
4. One model call reviews the anomaly digest + a compact world summary and
   emits corrections in the same line grammar; corrections route through the
   gate like any pass-1 line (role-checked, receipts, classification). The
   deliberate reactor contradiction must survive pass-2 — the audit prompt
   explicitly forbids resolving flagged conflicts (they are questions for
   the author, not the auditor).

## 6. anchor.world stamping (decision C refinement)

The re-run writes: `ingest_dump.jsonl` (canonical-candidate), scorecard,
REPORT. Promotion to `examples/anchor/` = copy dump + policy row + builder
invocation + a STAMP file recording seed version, run id, score, and
bible-verification status — no rebuild, no re-ingestion. Bible-verification
corrections (letter 005 item 3) append through truth-maintenance/ingestor
paths on the stamped world and re-dump; the correction history stays visible
by design.

## 7. Test plan (no-model, deterministic)

- grammar: render→parse round-trip; every flag; reject handling; orphan
  emission on unregistered ids.
- registry: establish-then-extend equivalence (batch once ≡ incremental
  twice over split text, given identical model outputs — stub-scripted);
  gate seeding produces receipts on variant attribute use.
- pipeline: parallel pass-1 with a stub callable lands identical dumps to
  serial (ordering invariant); quota abort leaves a resumable state.
- audit: planted orphan → registry-escape report + targeted re-extract;
  planted flagged conflict survives pass-2 untouched.
- Existing 57-test engine suite untouched and green (engine unchanged).

## 8. Out of scope

SDK shim (drop-in later), hierarchical registries for archive-scale corpora
(interface allows; not built), the messy-dialogue micro-eval (next chapter),
porcelain verbs (post-adapter-spec), any engine change whatsoever.
