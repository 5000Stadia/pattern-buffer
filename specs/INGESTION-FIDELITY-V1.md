# INGESTION-FIDELITY-V1 — `fidelity_audit()`: the structural-gap read that makes ingestion measurable

**Status:** SHIPPED — Cx spec review to GREEN (3 passes: grounding, per-pair
predicate derivation, decline-context access) → implemented → Cx code review GREEN
(2 fixes: meta-attribute exclusion in `unstamped_timed`, `auto_declined` gated on a
real proposal). 428 green. Co-designed with Construct (letters 099/100). Collaboration with Construct
converged (PB→Construct letter 099 at `/home/k/Newproject/dev_inbox/`; HD's reply
`dev_inbox/100-from-hd-ingestion-fidelity-corpus-and-baseline.md`). Scope is now
crisp and **single-verb**: a deterministic, membrane-clean
`fidelity_audit()` read that surfaces where a freshly-built log is structurally
incomplete — as a **queryable checklist the host joins against and re-extracts
from**. The engine surfaces gaps; the host (which owns the model, the chunking,
and arc/cast meaning) drives repair. No second coreference path in the engine
(HD's line, and the whitepaper membrane).

## Why (the converged diagnosis)
Chapter-test run 4 = 22/33, all failures extraction-class. HD measured the live
analogue on `emberroad` (a full saga): **29 coreference splits** (distinct entity
ids sharing a name/alias) on the shipped build, 34 on a fresh rebuild —
extraction is non-deterministic run-to-run (§E, live). Crucially, HD confirmed
the shipped **SHAPE-FIX tools decline these merges *correctly*** — `mara ~
mara_thist` → `alias_not_specific`, `cinder_crown ~ crown` → `kind_conflict`,
`harth` isn't a typing-slip (both sides carry real facts → genuine two-entities-
one-name coreference). The conservative auto-merge is a **correct floor**; on real
prose it leaves the majority of bin A unmerged. That residue is invisible today
except as an eval grade. **Make it a read, and it becomes a number we drive
down** — the founder's steer ("make sure we're actually improving things").

## `fidelity_audit(frame="canon", as_of=None) -> dict`
A single deterministic read (no LLM, no new stored state) that surfaces categorized
structural gaps, each keyed by the **entity ids** involved so the host can **join
against its arc/cast registry for severity** (the engine stays arc-blind).

**Preconditions (Cx RED-1/RED-2):** the audit reads the world *as built*, and it
**never writes** (never calls `truth.scan()` or the classifier). Two things must be
current before it is meaningful, both produced by an ordinary build seal, neither
done by the read: (1) **classification** — `unstamped_timed` counts only rows
present in the durability sidecar (an unclassified row reads as STATE by default, so
pre-classification the count is noise); (2) **a current truth-maintenance sidecar** —
`open_conflicts` reflects the last `truth.scan()`, so the host runs `scan()` at seal
(or before calling the audit). The audit reads what the build produced; it does not
refresh it.

**Scoping (Cx RED-2):** the `frame`/`as_of` parameters scope the **collision
grouping** — which `name`/`alias` rows are considered — via
`buffer.visible(frame=frame, valid_as_of=as_of)`. The per-pair **identity status
predicates are world-level identity facts** and are computed with the engine's
existing (frame-independent) predicates: `distinct_from` and containment blocks are
global by design (a thing is not its container in *any* frame; two entities declared
distinct are distinct everywhere), and `correlation_set` is as-of-scoped. The audit
does **not** call the global list-builders (`reconcile`/`enumerate_proposals`/
`typing_conflicts`) — it reuses their per-pair *predicates* against its own scoped
candidate set. Default `frame="canon", as_of=None` (current) is the primary coreference-fidelity view.

**`name_collisions`** — THE coreference-fidelity metric (HD's 29-count). Group the
scoped `name`/`alias` rows by normalized text; keep texts carried by **>1 distinct
resolved entity**. For each group, compute each pair's `status` via the per-pair
predicates directly (NOT the pre-filtered proposal list, which skips hard-blocked
and distinct pairs): `correlated` (`correlation_set(a, as_of)` ∋ `b` — an expected
`aka` facet, **not** a gap) · `hard_blocked` (`containment_block` / `distinct_block`,
world-level) · `typing_slip` (the pair carries the slip signature directly — shared
anchor + kind conflict + `_slip_asymmetry`; the `obj:ilsa_renn_desk` class, which the
host fixes with `retype(absorb=)`) · `auto_declined` + `reason` (an open
`maybe_same_as` relates the closures and `_decline_context(a,b)["code"]` is
`alias_not_specific` / `kind_conflict` / `durable_contradiction` / …) · `unlinked`
(a shared anchor, no edge, no block). Group shape:
`{anchor, entities:[…], pairs:[{a, b, status, reason?}]}`. A group whose every pair
is `correlated`/`hard_blocked` is **reported for visibility, flagged resolved, and
NOT counted** in the headline; a group with ≥1 `unlinked`/`auto_declined`/
`typing_slip` pair is a **live fragmentation** the host re-extracts. (Typing slips
appear here as a per-pair status rather than a separate category — one place to look,
no double count.)

**`unstamped_timed`** — rows **classified** (present in the durability sidecar) as
**STATE or EVENT** with `valid_from is None`: a happened/holds-at-a-time fact off the
spine. CONSTITUTIVE/timeless rows are correctly excluded — the sidecar is what
distinguishes "should be stamped" from "legitimately timeless." **Meta/identity edges
(`META_ATTRIBUTES`: `same_as`/`distinct_from`/`aka`/`source`/…) are excluded** — they
are classified EVENT and carry no `valid_from` by design (bookkeeping, not spine
facts), so they are not a gap. (Run-4 Q10 = 37.)

**`orphan_entities`** — entities of the **movable/locatable kinds `obj:` and
`person:`** with **no current folded containment parent** (`indexes.locate(e, frame,
as_of)` empty): a floating node the ingestion never anchored to the map. `place:` is
**excluded** — a top-level place (the manor, the city) legitimately has no parent and
there is no root-place marker to tell a root from an orphan (Cx RED-2); all other
namespaces (`event:`/`doc:`/`prop:`/`process:`/`org:`/`attr:`/`a:`) are non-spatial
by design. Covers both never-anchored and dropped-out; a separate
`dangling_containment` category is **deliberately dropped** — distinguishing a
legitimately-ended containment (destroyed, consumed, left the tracked map) from a gap
needs destruction/exit semantics the engine must not guess (RFC-003 precedent:
`valid_to` is temporal visibility, never inferred destruction).

**`open_conflicts`** — the truth-maintenance sidecar (`truth.open_conflicts()`,
read-only): unresolved contradictions from the build (an overturned belief never
closed, a document claim that conflicted instead of converging). Reflects the last
`scan()` per the precondition; the audit never re-scans. (Q18/Q20.)

**`summary`** — per-category counts. **`name_collisions`** is the count of
**live-fragmentation groups only** (correlated-only and hard-blocked-only groups
excluded) — the headline number, the engine computing exactly the metric HD measures
by hand, so it becomes automatic and shared. The engine reports **unweighted
structural counts**; the host computes the **severity-weighted build score** by
joining the per-entity gaps against its arc/cast data (a split on the arc protagonist
is show-stopping; on a background prop, cosmetic — knowledge only the host has). The
engine never invents a severity weighting (a host-concept guess).

Porcelain-facing, `encode_out`-wrapped. Zero writes; the log is byte-identical before
and after.

## The loop it enables (host-side, for the record)
Construct's build seal already runs `reconcile` → `adjudicate_deferred` →
`typing_conflicts`/`retype`, then ships the residue. With this read it becomes:
seal → **`fidelity_audit()`** → join severity → **targeted second-pass extraction
on just the flagged spans/entities** → re-seal. The engine adds no re-extraction
loop (the host owns the model and chunking — membrane); it only makes the gaps
visible. `emberroad` is the **shared regression fixture**: HD re-runs it when this
lands and we watch 29 → lower. If the number doesn't move, we didn't improve.

## The seam (settled with HD)
- **Engine (this spec):** the `fidelity_audit()` read — derive the gaps from the
  log's own structure.
- **Engine (extractor contract, a *separate* follow-on if measurement shows it
  needed):** reliability of `same_as`/alias/`valid_to`/document-convergence
  emission. Deliberately **not bundled** — we ship the measurement first, then let
  the emberroad number tell us whether the contract or the host loop moves it.
- **Host (Construct):** chunking, the pass-0 registry, Entity Authority
  (play-time channel policy), the build-seal cleanup, the severity join, and the
  targeted re-extraction loop.

## Non-goals
- **No arc/severity/cast concept in the engine** — it returns joinable entity
  ids; the host ranks. No stored fidelity score (derive-don't-store; recomputed).
- **No second coreference path** — `name_collisions` composes the shipped identity
  *per-pair predicates* (`containment_block`/`distinct_block`, `correlation_set`,
  `_decline_context`, the slip signature) over its own scoped candidate set; it does
  not re-derive merging and does not call the global list-builders.
- **No engine-owned re-extraction loop** — the engine surfaces; the host repairs.
- No extractor-prompt changes in V1 (measurement first; contract is a measured
  follow-on).

## Tests
- Two ids sharing a `name` show a `name_collisions` group with the correct per-pair
  `status`/`reason`: an `alias_not_specific` decline; a `kind_conflict`; a
  `typing_slip` pair; a `distinct_from` → `hard_blocked`; an `aka` pair →
  `correlated` (reported but NOT counted).
- A group whose only pairs are `correlated`/`hard_blocked` is present in the list
  but excluded from `summary.name_collisions`; a group with an `unlinked`/
  `auto_declined`/`typing_slip` pair is counted.
- After `adjudicate_deferred()`/`retype()` collapse a live collision, it leaves the
  audit and `summary.name_collisions` drops — the read tracks repair.
- A **classified** STATE row with no `valid_from` appears in `unstamped_timed`; a
  timeless CONSTITUTIVE row does not; an unclassified row does not (precondition).
- An unanchored `obj:`/`person:` appears in `orphan_entities`; a contained one does
  not; a top-level `place:` and any `event:`/`doc:` never appear.
- An open truth-maintenance flag (after `scan()`) appears in `open_conflicts`.
- The audit calls no writer and no `scan()`/classifier — the log and sidecars are
  byte-identical before/after; the payload is `json.dumps`-able (decimal-safe);
  the grouping honors `frame`/`as_of`.
- Full suite green; defaults unchanged.
