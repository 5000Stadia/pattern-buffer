# MERGE-RECONCILE-VERB-V1 — the host-reconciliation porcelain surface

**Status:** DRAFT → Construct poke + Codex GREEN before implementation.
**Kind:** additive on porcelain-v0.1 (new verbs only; no signature changes).
Consumer requirements: Construct 012 + 013. All writes go through the existing
**guarded** merge path (containment veto is the non-bypassable invariant);
nothing stored outside the log (no parallel resolution table — derive-don't-store
/ P7).

## Why

A host running multi-chunk ingestion must reconcile cross-chunk identities the
auto-resolver leaves as proposals. `reconcile()` exists on `world.registry` but
below the frozen surface; the host has no porcelain way to (a) run the finalize
pass, (b) see the residual proposals, or (c) confirm/assert a merge with an
actionable outcome. This adds those three, as one surface.

## The four verbs

```
p.reconcile() -> {merges: int, proposals: [Proposal]}
p.proposals() -> [Proposal]
p.confirm(a, b) -> Receipt
p.merge(a, b, evidence) -> Receipt
```

- **`reconcile()`** runs the global finalize pass (`IdentityRegistry.reconcile`)
  and returns the count merged plus the residual `proposals()` (so one call both
  resolves the clean cases and hands back the adjudication workload). Host-
  invoked — never auto-run by `ingest` (it is a whole-world pass; the host calls
  it at its reconcile point). Zero model calls.
- **`proposals()`** enumerates the visible un-promoted `maybe_same_as` as the
  residue to adjudicate (no merge, no model call).
- **`confirm(a, b)`** promotes an existing proposal; **`merge(a, b, evidence)`**
  asserts a merge with no proposal required. Both go through the same guarded
  path and return the same `Receipt`.

## `Proposal` (JSON)

```
{ "a": <canonical id>, "b": <canonical id>,
  "evidence": <proposal evidence string | null>,
  "auto_decline_reason": "containment"
                       | "kind_conflict: <kindA>↔<kindB>"   # the kind PAIR (C-014)
                       | "alias_not_specific" | "kind_absent" | null }
```

`auto_decline_reason` is **recomputed** (never stored) — *why* the auto-gate did
not promote it, so the host can triage. **The `kind_conflict` reason carries the
kind PAIR** (C-014, load-bearing): bare `"kind_conflict"` bundles a genuine
coreferent (`obj↔place` — a vault, a room named for its function → confirm) with
false-positives (`obj↔person` possession / `person↔place` location → reject), all
reading alike. The pair = the two folded `kind` winner values (entity-resolved,
sorted, joined `↔`), e.g. `"kind_conflict: object↔place"`. If the conflict is from
a *contested* (conflicted) kind fold rather than differing values, the reason is
`"kind_conflict: contested"`. Derived from `containment_related` / `_kind_state` /
`_content_tokens` at read time; it is also the exact signal a future narrow
`obj↔place` auto-rule would key on.

## `Receipt` (JSON) — the load-bearing part (C-012)

```
{ "outcome": "merged" | "noop_already_merged" | "vetoed" | "no_proposal",
  "canonical_id": <id the pair resolves to after the op>,
  "merge_event_id": <event id | null>,         # set iff outcome == merged
  "reason": <str | null>,                       # set iff outcome == vetoed
  "blocking_edges": [<"entity·attr·value">] }   # set iff outcome == vetoed
```

- **`merged`** — the guarded merge appended; `merge_event_id` + `canonical_id`
  returned (so the host updates its references and can retract-to-repair forward
  without hunting).
- **`noop_already_merged`** — idempotent; `a` and `b` already share a closure.
  Not an error (finalize passes / retries must not throw).
- **`no_proposal`** — `confirm(a,b)` ONLY, and ONLY when the pair is **not
  already merged** and no live `maybe_same_as` relates them (e.g. a retract
  removed the proposal). A branchable outcome, never a silent merge — keeps
  `confirm` honest vs `merge`. (Already-merged is `noop_already_merged`, checked
  first — it is the truthful outcome, not `no_proposal`.) `merge()` never
  returns `no_proposal`. C-014 / Codex post-impl.
- **`vetoed`** — a containment/location edge relates them; `reason` +
  `blocking_edges` name the specific edge(s) (e.g.
  `"obj:memory_core·in·obj:false_drawer"`). This is what lets the host decide
  retract-the-bad-edge-and-retry vs accept-the-veto — a bare failure would blind
  it (the `path()` lesson). The containment veto is absolute: even an explicit
  `merge()` is vetoed (repair by retracting the edge first), so an object and its
  container can never fuse.

**Authority boundary:** `confirm`/`merge` are *host-authoritative past the
discriminativeness heuristic* — they do NOT re-apply the auto-gate's
alias-specificity/kind policy (the host has judged). They are gated ONLY by the
hard containment invariant. (The heuristic gates *auto*-promotion in `reconcile`/
`promote_identity_proposals`; an explicit host confirm overrides it.)

## Engine changes (minimal)

1. **`containment_block(a, b) -> list[str]`** — the edge descriptor(s) relating
   `closure(a)↔closure(b)`; `containment_related` becomes `bool(containment_block)`.
   Lets the receipt name the blocking edges.
2. A private **`_guarded_merge(a, b, evidence) -> Receipt`** the two verbs share:
   resolve-equal → `noop_already_merged`; `containment_block` non-empty →
   `vetoed` (+ reason/edges); else `merge()` → `merged` (+ event id). `merge()`
   itself is unchanged (still the non-bypassable veto).

Identity is **global** (frame-agnostic `closure()`), so a confirm holds across
`canon` and every `knows:<id>` (C-012). No new storage.

## Tests (invariants)

1. **reconcile receipt:** after seeding mergeable + residual cases,
   `p.reconcile()` returns `merges>0` and `proposals` listing the residue.
2. **proposals enumerate + reason:** a containment proposal reads
   `auto_decline_reason="containment"`; a single-token alias
   `"alias_not_specific"`; a kind-conflict one carries the **pair**
   `"kind_conflict: object↔place"` (C-014) — and an `obj↔person` pair reads
   differently from an `obj↔place` pair.
2b. **no_proposal:** `confirm(a,b)` with no visible `maybe_same_as` →
   `outcome="no_proposal"`, no merge.
3. **confirm merges a proposal:** `confirm(a,b)` on a residual proposal →
   `outcome="merged"`, `merge_event_id` set, `resolve(a)==resolve(b)`.
4. **merge asserts without a proposal:** `merge(a,b,ev)` with no proposal →
   `merged`.
5. **idempotent noop:** `merge(a,b)` when already merged → `noop_already_merged`,
   no throw, no new merge event.
6. **vetoed with edges:** `merge(core, drawer)` where `core·in·drawer` →
   `outcome="vetoed"`, `reason` set, `blocking_edges` names the edge; still
   distinct.
7. **host overrides heuristic:** `confirm` of a single-token-alias proposal the
   auto-gate declined → `merged` (host-authoritative past the heuristic, gated
   only by containment).
8. **global identity:** a confirm holds when queried under a `knows:<id>` frame.
9. **membrane / serializable:** receipts + proposals are plain JSON; the reads
   write nothing; `confirm`/`merge` append only guarded-merge log evidence.
```
