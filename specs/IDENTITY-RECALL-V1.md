# IDENTITY-RECALL-V1 — global coreference finalize pass (precision-hardened)

**Status:** DRAFT r3 (resolves Codex r1+r2). Seeking GREEN before implementation.
Precision-sensitive; one unified gate, kind-requirement differentiated by anchor
strength so proper-name merging is preserved while alias merging is tight.

## Problem (Construct 009/011 recall half)

`maybe_same_as` only forms *within* an extraction pass, so an entity introduced
under varying descriptions across chunks never gets a proposal — the memory core
projected as three un-merged closures (`obj:master_meter_memory_core` /
`obj:memory_core` / `obj:core`). Raise recall without dropping precision (two
distinct things sharing a casual alias must not fuse).

## §1 One unified gate (Codex r1 #1)

A single `_mergeable(a, b) -> bool` is used by BOTH the existing within-chunk
`promote_identity_proposals()` AND the new global pass — else a weak proposal one
path declines gets auto-merged by the other. `merge()` keeps the containment veto
as the non-bypassable invariant; `_mergeable` is the promotion *policy* above it.
`promote_identity_proposals()` is changed to promote a `maybe_same_as` only when
`_mergeable` holds; otherwise the proposal stays for host adjudication (#31).

`_mergeable(a,b)` ⇔ all of:
1. `resolve(a) != resolve(b)`;
2. not `containment_related(a, b)` (shipped veto);
3. **kind not in conflict** (§2);
4. a **qualifying shared anchor** with its kind condition met (§3+§4).

## §2 Kind state (Codex r2 #2 — conflicted-kind hole)

Read `ka = fold_key(a,"kind")`, `kb = fold_key(b,"kind")` (subject/closure
identity-resolved, as `refer.py` already reads kind). Entity-valued kind values
resolved through identity.
- if `ka.conflicted` or `kb.conflicted` → **not mergeable** (a contested type is
  never a merge basis); `fold_key.winner` alone is insufficient because it
  returns an earliest winner even under conflict.
- `present_a / present_b` = the winners' values if present, else `None`.
- if both present and unequal → **not mergeable**.
- otherwise kind is *non-conflicting* (equal, or one/both absent) — the per-anchor
  rule in §4 decides whether absent is acceptable.
(Generalizes to other functional CONSTITUTIVE keys; v1 keys on `kind`.)

## §3 Typed anchors (Codex r2 #3)

`name_anchors()` discards `row.attribute`. Add `typed_name_anchors(entity) ->
set[(attribute, normalized_text)]` where `attribute ∈ {name, alias}`, excluding
role/title as today. Candidate discovery groups closures by shared
**`normalized_text`** (NOT by `(attribute, text)` — else a cross-type
`name:"X"`↔`alias:"X"` pair, which merges today, would regress). For a candidate
pair sharing text `T`, the **anchor strength** is **`name`** if *either* closure
carries `T` as a `name`, else **`alias`** (Codex r3). §4 applies its rule by that
strength. **Normalization** (pinned): lowercase; strip
surrounding punctuation and apostrophes; drop leading articles (`the/a/an`),
possessive `'s`, and honorific/title prefixes; collapse whitespace; the remaining
whitespace-separated items are the **content tokens**.

## §4 Qualifying shared anchor — name vs alias (Codex r1 #2, r2 #1)

The over-merge Construct hit was a casual **alias** ("the core"), not a proper
name. So the kind requirement differs by anchor strength:

- **Name-strength `T`** (carried as `name` by *either* closure, incl. a
  cross-type `name`↔`alias` match): qualifies at **any length**, requiring only
  **non-conflicting** kind (absent kind is OK). Preserves the eval-validated
  proper-name merge — a genuine two-people-same-name clash is an authoring
  ambiguity resolved by split, not prevented here. (Fixes r2 #1: proper-name
  merges with absent kind do NOT regress to proposals.)
- **Alias-strength `T`** (carried only as `alias`, on both closures): qualifies
  **only if specific** (**≥2 content tokens** after §3 normalization) **AND** kind
  is **present-and-equal** on both. So
  `"the core"` → `["core"]` → 1 token → does not qualify (propose);
  `"memory core"` → 2 tokens + same kind → qualifies. A single-content-token
  alias (`"red"`, `"core"`) never auto-merges.

core-×3 auto-resolves via the multi-content-token alias `"memory core"` (and/or a
shared proper name) with equal kind; two `kind=person` closures sharing only
alias `"red"` correctly propose.

## §5 Deduped proposals (Codex r1 #4 — true idempotence)

Before emitting `maybe_same_as(a,b)`, skip if a visible `maybe_same_as` already
touches `resolve(a)`/`resolve(b)`'s closures. Rerun ⇒ zero appends (no duplicate
merges, no duplicate proposals).

## §6 Mechanics & regression (Codex r2 #1)

The global pass runs as a second phase of / right after
`promote_identity_proposals()`, sharing `_mergeable`. **Regression scope, exact:**
- proper-`name` merges are preserved at any length and with absent kind (only a
  *conflicting* kind blocks them);
- only **alias-based** promotions tighten — an alias-only promotion now requires
  ≥2 content tokens AND present-equal kind; alias-only, single-token, or
  kind-unconfirmed promotions become proposals.
Run full suite + chapter eval; report any eval merge that regresses (it would be
alias-only — repair by confirming via the verb or adding a corroborating anchor).

## §7 Tests (invariants)

1. **core-×3 recall:** three closures sharing multi-content-token alias
   `"memory core"`, equal kind, no containment → merge to one.
2. **casual-alias precision:** two `kind=person` sharing only single-token alias
   `"red"` → not merged; `maybe_same_as` exists.
3. **"the core" trap:** two same-kind non-contained objects sharing only alias
   `"the core"` (1 content token) → not merged → proposed.
4. **container precision:** containment-related pair never merged (veto).
5. **kind-conflict precision (different values):** shared specific alias, different
   `kind` → not merged.
6. **kind-conflicted precision (r2 #2):** shared specific alias, one closure's
   `kind` fold is `conflicted` → not merged.
7. **alias kind-absent:** shared specific alias but one closure lacks `kind` →
   propose, not merge.
8. **proper-name preserved, kind present:** shared single-token `name`, same kind,
   no containment → merge.
9. **proper-name preserved, kind ABSENT (r2 #1):** shared single-token `name`,
   neither has `kind`, no conflict → merge (no regression).
10. **two-cycle precision (r1 #1):** after the pass proposes "red", a subsequent
    `promote_identity_proposals()` does NOT merge them.
11. **idempotence (r1 #4):** rerun appends zero rows.
12. **membrane:** only log evidence written.
13. **cross-type name/alias preserved (Codex r3):** one closure has `name:"X"`,
    the other `alias:"X"`, absent kind, no containment → merge (name-strength;
    no regression vs today's untyped intersection).
