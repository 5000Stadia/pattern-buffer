# IDENTITY-ROOT-CAUSES-V1: automatic merges that the evidence can't support

**Status:** r1, spec for pbr review. Author: pb, 2026-10-12.
**Decision:** Kabe accepted gate g3bf5da's point P3 on 2026-10-12 (relayed by the monitor, note n02620e).
P1 and P2 were also accepted; P4 is still open. Consult: ccab80f (two outside views, Claude and Codex).

> P3 as accepted: "Fix identity's root causes before more identity work ships, as its own spec through
> pbr. Sentence-like aliases can no longer trigger automatic merges. A retracted merge stays retracted
> (today reconcile silently re-makes it). Every merge records who decided it (host or automatic) as
> structured provenance, which today's log cannot tell apart. reconcile never auto-merges an entity
> that owns a knows: frame without host confirmation (construct's suggestion). Construct's three bad
> live merges are repaired as data-quality incidents, on Kabe's yes, under gate g698a80."

**What this spec changes:** the engine's **automatic** identity decisions only. These are
`reconcile`, `promote_identity_proposals` and `adjudicate_deferred`, which all share the gate
`_mergeable` or its sibling checks. Host merges (`merge`, `confirm`, `retype(absorb=)`) keep every
current behaviour.

**What it never changes:**
- No stored row is rewritten, and no existing merge is undone. Append-only holds.
- A pair the new rules decline becomes an adjudicable `maybe_same_as` proposal, exactly as today's
  soft declines do. Nothing is lost; the host confirms or rejects it.

**Out of scope:**
- the live-world repairs (construct, gate g698a80);
- P2's explicit frame-combine event (its own spec);
- P4 (waiting on Kabe);
- R24 Part B and R25, which follow this spec.

## Measured on construct's worlds (copies; originals never opened)

- **Corpus:** all 52 files in `construct/worlds/`, copied with sqlite's backup API from a `mode=ro`
  source. Scripts: `scratchpad/p3/scan.py` and `rules.py`.
- **145 merges in all:**
  - `reconcile`: 93;
  - `adjudicate_deferred`: 32;
  - `retype` absorb: 14;
  - construct's own `fidelity-repair` merges, through the host verb: 6.
- **Automatic merges (reconcile, promotion, adjudication): 125.**
- **Retracted merges:** none in any world today. Construct's g698a80 repairs will create the first
  ones, which is why §2 must ship before those repairs.

| Root cause | Automatic merges it explains | Examples (shared anchor → fused ids) |
|---|---|---|
| Sentence-like anchor | 8 distinct pairs | "singing into a wind that had tried and failed to quiet them" → ida, lena, mae, nell, opal, rue; "received corin in the guild hall" → anselm_varo, corin; "kit sent tamsin through the loose floor hatch" → two different events; "the true tale of the crown" → a title fused with a group |
| Speaker-relative anchor | 6 distinct pairs | **"my apprentice" → tamsin, ash_apprentice and "his apprentice" → dorn_vale, ash_apprentice: this is the protagonist fusion**; "her prayer book", "his keys", "her father", "my father" (some may be right; none is evidence, since the words name a different thing for each speaker) |
| Merge touching a frame owner | 38 of 125 | includes the protagonist fusion tamsin = ash_apprentice, and the ida group; also many right ones (soren_vale = vale), which will now need one `confirm` each |

## §1 Sentence-like and speaker-relative anchors don't drive automatic merges

**Rule.** In `_mergeable` (the gate for promotion and reconcile), a shared name-class anchor (`name`
or `alias`) counts as merge evidence only if it is **name-like**. An anchor is name-like when both
hold:
- (a) it has at most **5 tokens**; a sentence or clause is not a name;
- (b) its first token is **not a speaker-relative possessive** (`_RELATIVE_POSSESSIVES`: `my`, `our`,
  `your`, `his`, `her`, `their`, `its`). "My apprentice" names a different person for every
  speaker.

`adjudicate_deferred`'s subsumption test (`_anchor_subsumed`) applies the same predicate to the
anchors it compares.

**Notes on the rule:**
- **Tokens** use the same tokenizer as `_content_tokens` (`identity.py:56`), so there is one notion
  of a word.
- **The existing alias rule stands.** Today an alias needs ≥2 content tokens with an equal kind.
  That lower bound is unchanged; (a) is an upper bound on the whole anchor.
- **Considered and dropped: a content-token cap.** "At most 3 content tokens" caught nothing that (a)
  missed in the corpus, and it would demote real names ("cafe de la digue").
- **Scope.** The rule applies to names as well as aliases. A real proper name over 5 tokens or 3
  content words ("Sir Reginald Fortescue Montague Smythe") becomes a proposal, not a merge. That is
  the precision bias V2 §3 already chose. Measured: none of the corpus's 320 canon `name` rows
  fails (a) or (b).
- **Non-qualifying anchors stay text.** A non-name-like anchor is still a perfectly good `alias` row:
  `by_alias`, `refer` and `ask` read it as before. Only its weight as **identity evidence** is
  removed. Description is not identity.
- **Declined pairs** whose only shared anchor fails the rule follow the existing soft-decline path.
  `reconcile` records a `maybe_same_as` with the evidence "reconcile: shared anchor not name-like
  (adjudicate)".

**Measured effect:** 35 of the 125 automatic merges, covering 14 distinct pairs, would have been
proposals instead. These are the 8 sentence-like pairs and the 6 possessive pairs, and they include
the protagonist fusion. Every other merge stands.

`_RELATIVE_POSSESSIVES` is frozen in code beside `_content_tokens`. Changing it is a spec change.

## §2 A retracted merge stays retracted

**Today.** A host undoes a merge by retracting its `same_as` row (`_same_as_path_ids` names it). The
next `reconcile` finds the same shared anchor and makes the merge again. The host's correction is
silently reversed.

**Rule.**
- A **retracted merge** is a `same_as` row whose `retracts` meta-row, carrying truth maintenance's
  mark, is visible. It records a decision: these two were judged **not** one thing.
- For the automatic paths, a pair (a, b) is **settled apart** when any retracted `same_as` row has
  one endpoint in a's closure and the other in b's.
- **Settled-apart pairs** are never merged by the automatic paths and are never re-proposed by
  `reconcile`. They are treated like the hard blocks for automatic purposes, but the host verbs can
  still decide them:
  - `merge` and `confirm` still merge such a pair; the host has re-judged.
  - `reject` still writes `distinct_from`.
- **Retracting a proposal** (`maybe_same_as`) is not covered here. Today's behaviour is unchanged:
  `reject` is the host's verb for "never again".
- **One reader.** Retracted rows are invisible to `visible()`, so the registry gets one new
  read-only buffer query: `retracted_targets(attribute="same_as", frame=CANON, asserted_as_of=...)`.
  It returns retracted rows whose retraction carries the mark. It is cached per log version, like
  `_components()`.
- **As of.** A pinned read (`asserted_as_of=`) sees exactly the retractions visible at that
  position.

**Effect on today's worlds:** none, since no world holds a retracted merge.

## §3 Every merge records who decided it

**Today.** All merge paths write identical rows through `_merge_rows` (`status=inferred`,
`role=ingestor`). Only the free-text evidence differs, and text matching misfires: `confirm`'s
evidence begins "confirmed proposal: reconcile: …".

**Rule.**
- `_merge_rows` appends one more row on the merge event: `event:merge_N · decided_by · <value>`.
  It is timeless and has `status=inferred`, like its siblings.
- **Values:**

| Value | Written by |
|---|---|
| `host` | the porcelain `merge` verb (`guarded_merge`), `confirm`, `retype(absorb=)` |
| `statement` | a `same_as` submitted through the ingest gate as an item, raw or as an item's `same_as` key. The row also carries `extracted · true` when the item came from prose extraction (`ingest(text)` or `ingest_structured(extracted=True)`) |
| `engine` | `reconcile`, `promote_identity_proposals`, `adjudicate_deferred` |

- **`decided_by` is a mechanism attribute** (GATE-AUTHORITY-V1 §1). It is added to
  `MECHANISM_ATTRIBUTES` with status mark `inferred`:
  - the gate never accepts it as an item;
  - readers honor it only on a `kind · identity_merge` event that has the identity component's mark.

  So a forged row decides nothing.
- **The read.** `identity_conflicts()` and the merge listing `proposals` already return merge events.
  Each merge they report gains `decided_by`. It is read from the row, or for merges written before
  this spec, **derived** from the evidence:

| Evidence prefix | Derived value |
|---|---|
| `reconcile:` | `engine` |
| `promoted from` | `engine` |
| `adjudicate_deferred:` | `engine` |
| `confirmed proposal:` | `host` |
| retype's absorb text | `host` |
| anything else | `unknown`, which every policy treats as `engine` |

  Treating `unknown` as `engine` follows the consult: an unclear merge counts as automatic, which is
  the cheaper error. The derivation is computed at read time; no row is written for old merges.
- **Measured on the corpus:**
  - 125 `engine`;
  - 14 `host` (retype);
  - 6 `unknown`: construct's `fidelity-repair`, made through the host verb, whose evidence text
    names no verb.

  Construct can confirm those 6 at repair time if it wants them counted as `host`.

## §4 No automatic merge of a frame owner

**Rule.**
- A closure **owns a frame** when any member `m` has a visible row in frame `knows:m`.
- The automatic paths never merge two closures when either one owns a frame. The pair becomes a
  `maybe_same_as` proposal, with the evidence "reconcile: frame owner, host confirmation required".
- `confirm` merges such a pair as usual.
- **Why:** a frame owner is a point of view. Fusing two of them fuses who knows what. Under P1 frames
  no longer follow merges, but the fused state reads (location, holdings) still mix the two people,
  which is the protagonist incident.

**Measured effect:**
- 38 of the 125 automatic merges in construct's worlds touch a frame owner.
- Among them are the protagonist fusion (tamsin = ash_apprentice) and the six-way ida fusion.
- Many are right (soren_vale = vale), and construct confirms those. The proposals arrive already
  deduplicated, one per pair.

**Book worlds have no host** (consult point 3):
- The eval pipeline is the host of a book world. It decides frame-owner proposals with an explicit
  step that calls `confirm` on each one that passes `_mergeable` without §4. That is
  `Pipeline.confirm_frame_owners()`, harness code, logged as `decided_by · host`.
- So a book run reaches the same merges as before, but each one is visibly a decision rather than a
  silent engine act.
- The engine keeps no book-specific switch.

## §5 Checks

1. **Unit tests, one per rule:**
   - §1: each of (a) and (b) declines a merge and writes a proposal, and the corpus
     sentences are reproduced as fixtures;
   - §2: retract → reconcile → still apart; host `merge` still merges; the as-of pin;
   - §3: every path writes its value, a forged item row is refused, and legacy derivation works;
   - §4: a frame owner yields a proposal and `confirm` merges it.
2. **Corpus run** on fresh copies of the 52 worlds: run `reconcile()` on a copy with main's engine
   and again with this one.
   - Main's run should make no merges in most worlds (they are already reconciled).
   - The report counts every pair the new engine declines that main would have merged, and every
     proposal it adds.
   - No existing merge changes, since none is undone.
   - Byte-identical reads for every world where neither run merges.
3. **Book side.** R23's seeded grade on `run1`/`run2` registries, plus the pipeline's
   `confirm_frame_owners` step. B3 F1 must stay within R23's noise floor (about 0.02) of today's
   seeded scores (0.826 / 0.791 on the R26 registries; the R23 runs as recorded). The Ilsa Renn merge
   must still happen.
4. **The full suite** stays green. Existing tests that assert an automatic merge of a sentence-like
   or frame-owner pair are listed and updated in this spec's r2, each with its reason. None is
   expected; checked at build.
5. **Construct's suite** runs on the branch before merge, as for batches A–E.

## Whitepaper

This adds row **A25**: automatic identity decisions take only name-like evidence, respect a retracted
merge, never fuse two points of view, and record who decided every merge. §11 is amended to match.
