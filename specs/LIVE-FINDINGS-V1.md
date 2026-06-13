# LIVE-FINDINGS-V1 — three engine fixes from Construct live play

**Status:** DRAFT r2 (post-Codex-RED, revised). **Source:** HD letters 002
& 003 (live findings on the anchor world), relayed/prioritized by Kernos CC
letter 038. **Discipline:** spec-first → Codex review to GREEN → implement →
Codex review of implementation. Whitepaper wins; these are refinements
within P1/P2/§4/§7, not amendments.

**Revision note (r2):** r1 went RED on all three counts in independent
review — each counterexample was real and is addressed below. The
corrected designs are checked against the locked fold/ask test suite
(`tests/test_fold.py`, `tests/test_ingest_v2.py`, `tests/test_world.py`,
`tests/test_porcelain.py`); none of them regress.

Each fix is small, local, independently testable. Shared theme (038):
every post-freeze refinement comes from a consumer hitting an access
pattern the ingest-then-query-once evals could not — here, *grow-and-move*
play (a player leaving a document-placed location) and *natural-language*
asks ("where is my spoon?").

---

## Fix 1 — write-time containment-cycle rejection (HD 002, Finding 1)

### The bug
Extraction emitted `place:council_tier · in · place:council_tier` (a
containment self-edge) from transit prose, and the gate accepted it.
`locate()` only detects the cycle at *read* time (logs a warning, bails),
so canon is poisoned at write time and every later walk pays detection.
Single-parent containment is a tree by design (§4); a cycle-forming
`in`-family edge is never a legal world state.

### What is and isn't achievable at the gate (r2/r3)
Containment is **time-indexed**: each edge holds over `[valid_from,
valid_to)`. A cycle is per-valid-time. A single write-time check on one
edge **cannot** prevent all cycles. Two independent proofs of this bound:

1. **Back-dated edges** (Codex r1): `A in B @vf=10` present, then
   `B in A @vf=1` — the walk as-of vf=1 sees no cycle, but one exists at
   t≥10. Full temporal prevention would require walking every overlapping
   valid-time segment per write — not "cheap," and still defeatable by a
   later back-dated addition.
2. **Deferred classification** (Codex r3): when the host defers
   classification (`classify_inline=False`, the batch-commit path),
   `locate()` folds yet-unclassified rows as STATE-by-recency, which can
   diverge from the post-classification CONSTITUTIVE-earliest winner — so
   the transitive walk can miss a cycle that only materializes once the
   walked rows are classified. (Precondition is itself pathological: an
   entity carrying conflicting CONSTITUTIVE containment edges.)

So the **contract** is, deliberately and honestly:
- **Self-edge rejection is complete** — always enforced, no derived-state
  dependency. This is HD's reported bug.
- **Transitive cycle rejection is best-effort** — accurate when the walked
  containment rows are already classified (the live `classify_inline=True`
  play path Construct uses); best-effort under deferred classification or
  back-dating.
- **The read-time `locate()` guard is the guarantee that no cycle is ever
  *served*** (bounded walk, `seen`-set, no hang) — the backstop for every
  transitive case the gate's single-write check cannot reach.

### The fix
At the gate, for a write of `child · rel · parent` where, after identity
resolution and attribute canonicalization, `rel ∈ CONTAINMENT_FAMILY` and
`value_type == "entity"`:
- **Self-edge** (`child == parent`): reject **always**. Pure, complete, no
  derived-state dependency; this is HD's exact bug.
- **Transitive cycle as-of the edge's own `valid_from`**: reject if
  `child ∈ set(containment_ancestors(parent, frame, valid_as_of=valid_from))`.
  `valid_from` is `None` for timeless edges → walk as-of head. This catches
  the dominant forward-moving-play case (the player moves *now*, into a
  place whose current ancestry is well-defined). It is **best-effort**, not
  complete, for back-dated edges — see above.

Rejection raises `ValueError` (consistent with the §10 generated-frame
guard and the unknown-status/value_type guards). The offending row never
enters the log; append-only is preserved (we reject *before* the first
write, never by retraction after).

`containment_ancestors` walks the containment **family** (not just `in`):
it is `set(indexes.locate(parent, frame, valid_as_of))`, and `locate`
already folds `CONTAINMENT_FAMILY` as one key and resolves identity on
every hop — so the check spans the family and is identity-consistent with
the gate's own resolution.

### Wiring (engine-internal, host-blind)
`Ingestor.__init__` gains `containment_ancestors: Callable[[str, str,
float | None], set[str]] | None = None`. `World.__init__` passes a thin
lambda over `self.indexes.locate` (indexes exists before the ingestor is
built, so it is injected at construction — no post-hoc setter). When
unwired (bare `Ingestor` in unit tests), only the self-edge check runs;
the self-edge case needs no derived state and is always enforced.

### Tests
- `child in child` (entity-valued, containment family) → `ValueError`, log
  unchanged. Both HD rows (`a:1114` timeless, `a:1137` vf=1002) reproduce.
- `A in B` then `B in A @ same/forward valid_from` → second write raises
  (transitive cycle as-of vf).
- `A in B`, `B in C`, then `A in C` → legal (reparent, no cycle).
- A plain move (`X in B` after `X in A`, A/B unrelated) → accepted.
- Non-containment self-reference (`person:x · likes · person:x`, a
  `same_as` self-edge) → **not** rejected (containment family only).
- **Documented residual:** back-dated cycle (`A in B @vf=10`, then
  `B in A @vf=1`) is accepted at the gate and still caught by the
  read-time `locate()` guard — asserted as the explicit boundary of the
  write-time check, not a silent gap.
- **Documented residual (deferred classification):** under
  `classify_inline=False`, a transitive cycle can pass the gate (the walk
  folds unclassified rows by STATE-recency); `locate()` remains bounded
  and catches it at read time. Asserted as the second explicit boundary.

---

## Fix 2 — containment moves supersede across sources (HD 002, Finding 2)

### The bug
A player moved: direct stated `person:marn · in · place:wellhead @vf=1003`
was committed over canon's document-class `person:marn · in ·
place:council_tier @vf=4`. `_fold_state` split them into source classes
(`direct` vs `document`), ran cross-source reconciliation, and flagged a
§7.2 conflict — serving the *stale* location. A host could only unblock by
retracting true history (HD retracted `a:262`, losing as-of-t=4 history).

### Why valid-time equality (r1) and overlap are both wrong (r2)
The locked suite pins two cases that look like HD's but must keep flagging:
- `test_disagreeing_value_flags_and_keeps_incumbent`: document `{gte:40000}
  @vf=2` vs direct `12000 @vf=3` on `reserve_gap_liters` → **conflict**.
- `test_speakers_disagreeing_flag_and_ask`: speaker:dale `diesel @vf=1` vs
  speaker:meg `gasoline @vf=5` on `fuel` → **conflict**.

Both have *unequal, non-overlapping-after-truncation* valid_froms yet must
flag — so neither "same valid_from" nor "window overlap" is the
discriminator. The real difference is the **attribute kind**:
`reserve_gap_liters` and `fuel` are *measured/claimed values* (a later
disagreeing reading is a genuine contradiction worth asking about), while
`in` is the **containment/movement family** — relocation is inherently
time-sequential, so a later move *supersedes* an earlier placement
regardless of which source class observed it.

### The fix
In `_fold_state`, take an `is_containment` flag (passed by `fold_key`,
which already computes `fa == _FAMILY_KEY`). After grouping into
per-source-class in-class winners (`winners`, with the existing
same-`valid_from` simultaneity guard applied **within** each class):

- If `len(winners) == 1`: serve it (unchanged).
- **If `is_containment` and `len(winners) > 1`:** movement is
  time-sequential. Compute `top_vf = max(valid_from)` across the class
  winners; `current = those at top_vf`. If the `current` rows disagree in
  value → flag (`conflicting = current ids`, serve earliest-asserted) —
  this preserves the simultaneity guarantee *across* classes (two sources
  placing the entity in different places at the **same** latest valid-time
  is a real contradiction). Otherwise serve the latest (`current` agrees or
  is singleton). A later move thus supersedes an earlier cross-source
  placement; a same-time cross-source disagreement still flags.
- **Else (non-containment, `len(winners) > 1`):** the existing
  corroborate-vs-conflict machinery runs **unchanged** (incumbent =
  earliest-arrived; agreement corroborates to the more precise value;
  disagreement raises the §7.2 flag).

### Why this is safe against the suite
- `reserve_gap_liters`, `fuel` → non-containment → existing branch → still
  flag. (Both Codex/locked counterexamples preserved.)
- `test_stated_supersedes_observed_in_movement`, `test_same_speaker_
  supersedes_self` → single source class → unchanged path.
- No existing test asserts a *cross-source containment* conflict across
  *different* valid-times, so the new branch changes no locked expectation;
  it only fixes HD's case and any future cross-source move.
- As-of correctness is automatic: `visible(valid_as_of=t)` filters the
  later move out for t<1003, so as-of t=4 serves council_tier — history is
  intact, no retraction needed.

Scope note: move-supersession is applied to the **containment family
only** (the structural, unambiguously time-sequential key). Extending
last-write-wins-over-time to other mutable-but-non-structural STATE
attributes (mood, status) is deferred — it needs its own signal and isn't
what HD hit.

### Tests
- HD's exact case: document `in council_tier @vf=4` + direct `in wellhead
  @vf=1003` → `fold_key(marn,"in")` winner=wellhead, **not conflicted**;
  as-of t=4 → council_tier (history intact).
- Two sources placing the entity in different places at the **same**
  latest valid_from → still conflicted (cross-source simultaneity guard).
- Regression: `reserve_gap_liters` document-vs-direct disagreement → still
  conflicted. `fuel` speaker-vs-speaker disagreement → still conflicted.

---

## Fix 3 — ask-path refer parity (HD 003)

### The bug
`obj:brass_measuring_spoon` (name "brass measuring spoon", on a table)
resolves through the observe path, but `ask("Where is my brass measuring
spoon?", frame=knows:person:marn)` returned unanswered. Two gaps:
(a) `refer` does no possessive/article normalization, so "my brass
measuring spoon" misses the exact name; and (b) `ask` supplies no scope,
so the letter-018 zero-candidate escalation can't fire.

### Why scope-from-knows-frame fails as r1 wrote it (r2)
Codex: `knows:` frames are **sparse** — canon containment rows are not
copied into them (`test_world.py:82`). So resolving a reference *in* the
`knows:marn` frame, or expanding scope membership in that frame, finds
nothing: `contents(place:room, frame="knows:marn")` is `[]`. **Entity
identity and existence are canon questions** ("which entity is the
spoon?"); only the *answer* (does marn know where it is?) is
knowledge-scoped. So the binding step must run in **canon**, and the
answer fold stays in the requested frame.

### The fix

**(a) Determiner normalization in `refer` (benefits every caller).**
Add deterministic `_strip_determiner(description) -> str`: lowercase and
strip a single leading determiner token — articles (`the`/`a`/`an`) and
possessives (`my`/`your`/`his`/`her`/`its`/`their`/`our`). Apply in
`refer.__call__`:
- Tier 1a tries `by_alias` on **both** the raw description and the
  stripped core (union of hits); a single combined hit resolves. "my brass
  measuring spoon" → core "brass measuring spoon" → exact-name hit →
  RESOLVED, no scope needed (this alone fixes HD's reported case).
- `_kind_word` accepts the optional leading determiner set (article **or**
  possessive) in place of only `the`, so "my spoon" → kind "spoon" feeds
  tier-1c. Broadening only *adds* matches; every existing `the X` input
  still matches identically (no 018/refer regression). Possessive clitics
  ("marn's spoon") stay a tier-2 case (out of scope; kept simple).

**(b) `ask` derives a canon scope from a `knows:<id>` frame.**
When `ask` is called with `frame == "knows:<id>"`, the asker is `<id>`.
`ask` resolves each refer_target in **canon** with a scope mirroring the
observe path's scene scope:
`scope_roots = [asker, *self._w.locate(asker, valid_as_of=as_of)]`, calling
`self._w.refer(target, frame=CANON, scope=scope_roots, as_of=as_of)`.
`_scope_members` BFS-expands those roots via canon `contents()`, so the
asker, the asker's containers, **and the contents of those containers**
(the spoon on the table in the asker's room) all become candidates — the
018 escalation can now fire within that bounded canon scope.
The answer keys (`state`/`locate`/`events`) are still folded in the
original `frame`, so the answer remains knowledge-scoped: a spoon marn has
never encountered binds in canon but yields no in-frame fact →
`answered=False` (no location leak; absence preserved).
For a canon-frame ask (no `knows:` prefix) `ask` passes `scope=None` as
today (no asker; world-scope escalation stays refused per 018) — existing
ask tests (`test_ask_with_provenance_and_asks`, default frame) unchanged.

**(c) Frame-scope the location chain (incidental leak, found in review).**
`ask`'s `wants_location` path appends `f["chain"] = locate(eid)` computed
in the **default canon** frame regardless of the asked frame — a pre-
existing canon-containment leak into a `knows:` answer. Pass the asked
`frame` to `locate` so the chain is frame-scoped like the fold beside it.

No porcelain signatures change — `ask`/`refer` keep their frozen surfaces;
both changes are additive internals. (Resolving identity in canon while
answering in-frame is an internal strategy refinement, not part of the
frozen `ask` signature, and matches how the observe path already resolves
identity structurally.)

### Tests
- HD's case: `ask("Where is my brass measuring spoon?",
  frame=knows:person:marn)` binds the spoon via tier-1a name match and
  returns the located fact (when marn knows it).
- "my spoon" (kind-only) with exactly one spoon in marn's canon
  location-scope → resolves via tier-1c.
- `_strip_determiner` unit-tested: `the/a/an/my/your/his/her/its/their/our
  X` → "x"; a no-determiner phrase passes through unchanged.
- Canon-frame ask with a vocabulary-miss reference → still unresolved
  (world-scope escalation remains refused).
- Knowledge absence: an object marn doesn't know about binds in canon but
  the in-`knows:marn` answer is empty (no leak).
- Existing 018 observe-path and porcelain ask tests unchanged.

---

## Non-goals / invariants held
- **Append-only**: Fix 1 rejects before the append; no edit/delete path is
  introduced. Fixes 2–3 are read-path/derived only.
- **Derive-don't-store**: Fix 2 changes fold *computation*, stores nothing.
  Fix 1's ancestor walk reads the derived tree; the gate writes no durable
  cycle-state.
- **Host-blind**: Fix 1's ancestor check is an engine-internal callback
  over `indexes.locate`; no host concept enters the engine. Fix 3's scope
  derivation reads only the `knows:<id>` frame string the porcelain
  already accepts and the engine's own `locate`/`contents`.
- **Role-authority**: unchanged; all writes through the ingestor role, all
  reads through the indexes.
- **Frozen porcelain**: no signature changes to any of the five+1 verbs.
- **Frame absence (§ P4)**: Fix 3 resolves *identity* in canon but folds
  *answers* in-frame, so sparse-frame absence is preserved — no canon fact
  leaks into a `knows:` answer.
