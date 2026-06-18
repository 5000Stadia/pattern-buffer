# TRIAGE-CONTEXT-V1 — structured `auto_decline` context on proposals

**Status:** DRAFT r2 (resolves Codex r1's 8 findings) → Codex + Conduit GREEN.
Additive, read-side only (enriches `enumerate_proposals`); no new verb, no write
path. Round-robin (C) conclusion, precedent: **engine surfaces structure; host
supplies meaning.**

## Why
A declined proposal carries only a display string. The host needs *structured*
signals to triage confirm/reject/defer — and the round-robin landed on **the
relating edges between the two closures** as the decisive evidence, `code` as the
primary branch key, kinds as supporting context. All data the engine owns; none
parsed from host id strings.

## Single source of truth (Codex r1 #1)
`_decline_context(a, b) -> dict` computes everything once; **`decline_reason()`
(the kept string) is formatted FROM it**, so string and struct can never diverge.
`enumerate_proposals()` attaches `auto_decline = _decline_context(ra, rb)` and
`auto_decline_reason` = the formatted string.

## Shape
```json
{ "a":"...", "b":"...", "evidence":"...",
  "auto_decline_reason": "relating_edge: father_of",        // kept: display
  "auto_decline": {
    "code": "relating_edge",
    "kinds": [ {"entity":"a","value":"person","conflicted":false},
               {"entity":"b","value":"person","conflicted":false} ],
    "related_rows": [ {"attribute":"father_of","relation_family":"none","assertion_id":"a:.."} ],
    "candidate_bindings": ["a:.."] } }
```

- **`code`** — the primary branch key, in the **exact order the shipped
  `_mergeable` gate fails** (Codex r1 #1/#2): `containment` → `relating_edge` →
  `no_shared_anchor` → `kind_conflict` → `non_distinctive` (every shared anchor
  equals a kind value) → `alias_not_specific` → `kind_absent`. (`distinct_from`
  pairs are excluded from proposals, so never carry a code.) For overlaps the
  earliest-failing gate wins (a relating-edge + kind-conflict pair reads
  `relating_edge`).
- **`kinds`** — per side `{entity, value, conflicted}` from a new
  `_kind_context(entity)` reading `self._kind_of(entity)` directly (Codex r1 #6),
  entity-resolved. Supporting context, never a rule.
- **`related_rows`** — THE decisive field: **every** relating edge between the
  closures, **containment included** (Codex r1 #3/#7), each
  `{attribute, relation_family, assertion_id}`. `relation_family ∈ {containment,
  lateral, none}` via `self._semantics.semantics(attr).relation_family`, falling
  back to `builtin_default(attr)` / a containment-vs-lateral membership check when
  semantics is unwired (Codex r1 #4). Containment lives here (with
  `relation_family:"containment"`) — that, plus `code=="containment"`, is the
  hard-veto signal; **no separate `hard_veto` field** (it duplicated this — Codex
  r1 #7, and avoids "which do I use?"). Host reading: *any* relating edge is
  evidence against identity.
- **`candidate_bindings`** — **plural** (Codex r1 #5): all visible `maybe_same_as`
  assertion ids relating the closures (live bindings are not unique). The host
  can act/retract precisely.

## Mechanism
- `_relating_rows_between(a, b) -> list[dict]` — structured sibling of
  `relating_edges_between`/`containment_block`: visible entity-valued rows
  relating the closures (containment + lateral + generic; excluding identity/meta/
  kind/caused_by + a:/attr: subjects), each `{attribute, relation_family,
  assertion_id}`.
- `_kind_context(entity) -> {value, conflicted}` from the kind fold.
- `_decline_context` composes code (gate-order), kinds (both sides),
  related_rows, candidate_bindings; `decline_reason` returns a string formatted
  from `code` (+ the kind pair for `kind_conflict`, the attr for `relating_edge`).
- All read-time; writes nothing.

## Non-goals (lean)
No new verb, no scoring, no stored state, no host-vocabulary interpretation, no
`hard_veto` duplicate. Host composes confirm/reject/defer from `code` +
`related_rows`.

## Tests (invariants)
1. `code` per case: `containment`, `relating_edge` (father_of), `kind_conflict`,
   `non_distinctive` (name==kind), `alias_not_specific`, `kind_absent`,
   `no_shared_anchor`.
2. **Overlap priority** (Codex r1 #8): a pair with BOTH a `father_of` edge AND a
   kind conflict reads `code:"relating_edge"` (earlier gate wins).
3. `related_rows` lists **all** relating edges incl. containment, with correct
   `relation_family` (`in`→containment, `connects_to`→lateral, `father_of`→none)
   and assertion ids.
4. `kinds` per side `{value, conflicted}`; a contested side reads `conflicted:true`.
5. **Multi-binding** (Codex r1 #5): two `maybe_same_as` rows across the closures →
   `candidate_bindings` lists both.
6. `auto_decline_reason` string present and consistent with `code`.
7. JSON-serializable; read writes nothing (membrane).
