# REFER-LEARNING-V1: refer learns words, never picks

**Status:** DRAFT r1 (2026-10-08). Not yet reviewed by pbr. Rebased on C r2 (2026-10-09; see
"Rebased onto batch C r2" at the end). Built from batch D of
`docs/AUDIT-2026-10.md`: P1 #4, identity P2-9, and the gate auditor's `owned_by`
finding. A probe on `polish/audit-2026-10` (212754f) reproduced every defect
below before it was specced; line numbers are at that commit. A throwaway
prototype of this spec passed every oracle, and 576 of 577 existing tests were
unchanged. The one that changed is the test that encodes today's receipt (see
Tests). The spec changes served answers only where they are wrong. It waits on
Kabe's go-ahead, then pbr. Construct ranked it high: "the drawer" resolving to
the wrong drawer forever breaks the object permanence it promises players.

**Founder decisions (Kabe, via the colony monitor, 2026-10-08 evening).** All
four defaults are confirmed:
1. Adopt the rule as written: learn a word, never a pick.
2. `ask` never learns.
3. Legacy `refer:tier2:` aliases are honoured as learned words.
4. Amend whitepaper §9's last line.

pbr review is still the gate before merge. Kabe is listed to revisit this
batch.

**Why.** `refer()` saves every confident tier-2 answer as a canon alias.
- **A pick becomes permanent.** "The drawer" in a study with two drawers is a
  pick. Today it becomes a timeless, world-wide alias that wins tier 1 everywhere:
  - in the kitchen, whose only drawer tier 1c would have found;
  - in every frame;
  - at every as-of.
- **Reads grow the log.** A reference that stays ambiguous appends two rows on
  every read: 5 reads add 10 rows. `ask` writes through the same path.
- **Learned words are identity anchors.** A cabinet carrying a learned "the old
  cupboard" is merged by `reconcile()` with any other cabinet that carries the
  same text (probe).
- **Tier 1 ignores frame and log position.** It reads every frame and ignores
  `asserted_as_of`.
- **Aliases match case-sensitively.** `by_alias` compares alias rows exactly but
  lowercases names.
- **`owned_by` returns the wrong entity.** The constraint returns the
  possession's container, not its owner.

Letter 018 (Kernos, with the founder in the loop), as accepted into SPIKE-V1 §9.3,
asked for two guards:
- learning only of *a novel term*, "discourse-scoped first";
- "a learned alias never outranks another entity's exact name".

The shipped `_accrue_alias` dropped both. This spec restores them in engine terms.

## §1 The rule

> **refer learns a word, never a pick.**
> - **When it writes:** only when tier 1 found no candidate at all in a given
>   scope, and tier 2 mapped the expression onto one entity there.
> - **What it writes:** a `learned_alias` row: refer's memory of words, not
>   identity. It goes in the frame the call resolved in.
> - **When it is read back:** only after the world's own vocabulary (names,
>   aliases, a unique kind in scope) finds nothing, and only where its entity is
>   in the caller's scope.

Reasons:
1. **A pick is a fact about one utterance; a word is a fact about the
   expression.**
   - Which of two drawers someone meant depends on the conversation, and the
     engine has none: it is a host concept (§17.1). Storing the pick freezes a
     judgment while the one input that changes is missing.
   - §9 allows logging a resolution only as a "discourse-scoped" alias "with
     bounded lifetime". The engine cannot scope or bound anything by a
     conversation, so it logs no picks.
   - A host that wants per-conversation memory caches `Resolution`s under its
     own conversation key.
   - A word ("the old cupboard" = this cabinet) holds wherever that cabinet is in
     view.
2. **The scope comes from the call, not the row.** "Most referring expressions
   are scope-local" (§10). The engine already computes the scene (`scope` →
   members), so a membership test at read time is the scope. Nothing more is
   stored, since each candidate is recomputable (the membrane) or a host concept:
   - not a scope;
   - not a lifetime;
   - not a promotion counter.

   A learned alias is bounded in three ways:
   - by space: its entity must be in scope;
   - by precedence: any authored name, alias, or unique kind outranks it;
   - by retraction, which is the host's call.

   It is not bounded by a clock. Vocabulary doesn't expire with story time.
3. **Read where it was learned.** A word is learned on a vocabulary miss and read
   back only on one (tier 1d, after 1a–1c). That makes 018's "never outranks an
   exact name" structural. It is also what disarms every legacy pick (§7).
4. **Not identity.** A phrase used in one scene is no evidence that two things are
   one. A separate attribute keeps learned words out of `reconcile`,
   `name_collisions`, `typing_conflicts` and the merge gates by construction,
   without editing any of them.
5. **Storing a word passes the membrane.** Its input, the user's expression, is
   not in the log, so it cannot be recomputed from present facts. Everything else
   can be, or belongs to the host, so none of it is stored:
   - the pick;
   - the scope;
   - the lifetime;
   - any promotion.

Rejected:
- **Never learn; cache tier-2 answers in memory.** This is the cleanest for the
  membrane. But it drops the founder's synonym mandate (018). Construct's
  adjudication relies on it: "one cheap call once, deterministic thereafter"
  (`turnloop.py`). It also fails micro-eval R7.
- **Learn only on a vocabulary miss, still as a global canon alias.** This was
  the audit's first suggestion. It fixes the drawer but not words: "the old
  cupboard" learned in the kitchen then resolves to the kitchen cabinet from the
  garage (probe).
- **Valid-time-bounded aliases.** Any horizon is arbitrary, and story time and
  wall time differ by mode. The bound that matters, a conversation, belongs to the
  host.
- **Recording the learning scope on the row.** It is derivable at read time from
  membership, and it goes stale when things move.

## §2 Writing: only a vocabulary miss learns

Location: `refer.py`. `_accrue_alias` (77–95) is replaced by `_learn`.
`_resolve_tier2` (225–257) learns only when its caller asks it to.

**Which tier-2 calls may learn.** Tier 2 is reached from four places, and only one
may learn:
- The **zero-candidate escalation** (018 mechanic 1, `__call__` 142–149) may learn.
- These never write:
  - the kind pick (tier 1c, `len(of_kind) > 1`);
  - the authored-alias collision (`len(hits) > 1`);
  - the learned-alias collision (§3).

**When the escalation learns.** All of these must hold:
- The answer is `resolved`: the entity is among the candidates, at or above the
  0.75 floor.
- `asserted_as_of is None`. A read pinned to a past log position never writes.
- `learn=True`. This is a new keyword on `Refer.__call__`, default `True`.
- An ingestor is wired (unchanged).

**What is written.** One item, through `ingest_structured` (the gate, ingestor
role):

```python
{"entity": entity_id, "attribute": "learned_alias",
 "value": description.strip().lower(), "timeless": True, "status": "inferred",
 "frame": frame,  # the call's frame
 "source_doc": "refer:tier2:" + json.dumps(signals)[:80]}
```

- **The value is the raw expression, normalized** (as today), so "my bag" and
  "her bag" stay different words.
- **The gate writes the receipt.** `source_doc` makes the gate write the `source`
  receipt row, so refer's private reach into `ingestor._role` goes.
- **A gate skip is not an error.** An empty return is logged and the resolution
  stands; today `rows[0]` would raise.
- **Written once.** Nothing is written if a visible `learned_alias` in the call's
  frame already maps this value to this entity. At the head the cascade can't
  reach this case, because an in-scope word is a tier-1d hit. It is a guard, not
  a path.
- **`learned_alias` joins `META_ATTRIBUTES`** (`model.py` 50–66). The
  classifier's guardrail (`classify.py` 135) then stamps it EVENT with no model
  call. So a learned alias never:
  - folds;
  - appears as a standing fact;
  - counts as a durable contradiction, a relating edge or an unstamped row.

  Like `same_as` and `aka`, it is timeless bookkeeping. The observe-mode
  wall-clock rider doesn't stamp it.

**Oracle.** Setup: a kitchen and a garage, each holding one cabinet; "the old
cupboard" is nobody's name.
- `refer("the old cupboard", scope="place:kitchen")`, with tier 2 answering
  `obj:kitchen_cabinet` at 0.9:
  - resolves at tier 2;
  - appends exactly two rows: `(obj:kitchen_cabinet · learned_alias · "the old
    cupboard")` (canon, `inferred`, timeless) and its `source`
    `refer:tier2:[…]`;
  - makes one model call (no classifier call);
  - the row's durability is EVENT.
- **Pinned or opted out.** The same call with `asserted_as_of=<head>` or
  `learn=False` resolves the same way and appends nothing.
- **From a `knows:` frame.** Called from `frame="knows:person:alice"` (with
  Alice's own kitchen rows), the row lands in `knows:person:alice`.

## §3 Reading: tier 1d

Location: `refer.py` `__call__`. A new step goes after the alias-collision branch
(139–140) and before the escalation.

1. **When it runs.** Only when tier 1a found no authored hit, and tier 1c neither
   resolved nor picked.
2. **What it looks up.** The entities that a `learned_alias` row, or a legacy
   learned alias (§7), maps the expression to. Both texts tier 1a tries are used
   (the raw expression and its determiner-stripped core). The lookup:
   - uses tier 1a's frame rule and `asserted_as_of` (§4);
   - normalizes as §5 does;
   - resolves each entity through identity.
3. **The scope filter.**
   - With a `scope`, keep only the scope's members: the same `_scope_members` the
     escalation uses, computed once per call.
   - With no scope, keep all of them: the whole world is the scene.
4. **The result.**
   - One entity: `resolved`, receipt `{"tier": 1, "signals": ["learned_alias"]}`,
     no model call, no write.
   - More than one: tier 2 over them, no write.
   - None: the escalation, as today.

**Oracle** (continuing §2):
- **Kitchen again:** tier 1 `["learned_alias"]`, zero model calls, zero rows.
  Today: tier 1 `["alias_exact"]`.
- **Garage:** the kitchen cabinet is out of scope, so the escalation runs. Tier 2
  answers `obj:garage_cabinet`, and a second word row is learned for it. Today:
  `obj:kitchen_cabinet` through `alias_exact`, forever.
- **No scope, two learned referents:** tier 2, nothing written.
- **No merge, no collision.** `reconcile()` merges nothing, and
  `name_collisions()` lists nothing for the text. If learned words were `alias`
  rows, these same two cabinets would merge.
- **A kind in scope wins.** The kitchen gains `obj:pantry` (kind `cupboard`), and
  the cabinet carries a learned "the cupboard". `refer("the cupboard",
  scope="place:kitchen")` returns `obj:pantry` with `unique_kind_in_scope`.

## §4 Tier 1 reads in the caller's frame, as of the caller's log position

Location: `refer.py` 110–112 call `by_alias(text)` with neither the frame nor the
log position. `identity.py` `by_alias` (1104–1114) reads every frame.

- **The frame half is batch C's.** FRAME-SCOPED-IDENTITY-V1 (r1, `cee055b` on
  `spec/frame-scoped-identity-v1`, §2) does three things:
  - it gives `by_alias(alias, asserted_as_of=None, frame=CANON)`;
  - `by_alias` reads `alias`/`name` rows in that frame only (the exact stored
    frame, as C r2 reads every frame), with no canon fallback;
  - refer's tier 1a passes its own `frame`.

  D relies on all of it. §3's learned-alias lookup uses exactly the same read
  set, so there is one frame rule for all of refer's vocabulary.
- **The log-position half is D's.** Tier 1a passes `asserted_as_of` to both
  `by_alias` calls. §3's lookup does too.
- **If D lands before C,** D adds C's `frame` parameter with C's semantics, and C
  takes it over.
- **Valid time does not filter** names, aliases or learned aliases (unchanged).
  §9's historical reference ("the blacksmith's boy") relies on drifted anchors
  staying matchable. Anchors scoped by valid time are a separate question.

**Oracle** (the frame cases restate C's 2c through refer; the as-of cases are
D's):
- **A private alias.** `(obj:desk_drawer · alias · "the stash")` in
  `knows:person:alice`:
  - canon `refer("the stash")` is `underdetermined`. Today: `obj:desk_drawer`,
    `alias_exact`.
  - `refer("the stash", frame="knows:person:alice")` returns `obj:desk_drawer`,
    `alias_exact`.
- **A private name** ("Old Grey") behaves the same.
- **Before the alias existed.** `refer("the stash",
  frame="knows:person:alice", asserted_as_of=H)`, with H before the alias, is
  `underdetermined`. Today it resolves.
- **A learned alias written in `knows:person:alice`** is invisible to canon.

## §5 Aliases match like names

Location: the `identity.py` `by_alias` alias branch (1107–1109) compares
`row.value == needle`.

- **One normalization.** A single helper, `ref_norm(text) = text.strip().lower()`,
  is applied to the needle and to every `name`, `alias` and `learned_alias` value
  before comparing.
- **Which rows start matching.** `add_alias` already stores `ref_norm(alias)`, so
  aliases from an item's `aliases` list match as today. Rows written directly as
  an `alias` attribute keep their authored text, and they start matching.
- **Non-string values** never match (unchanged).

**Measured on construct's 52 live worlds:** 4 alias rows are stored
un-normalized. One text (`boy from veyrac fils`, in a `live_telegram` world)
gains its only referent.

**Oracle:**
- `(obj:core · alias · "The Memory Core")`: `refer("the memory core")` and
  `refer("  THE MEMORY CORE ")` both return `obj:core`. Today: `underdetermined`.
- An alias stored as `"  old  faithful "` matches `refer("old  faithful")` but not
  `refer("old faithful")`. Interior whitespace is not collapsed, as for names.

## §6 `owned_by` returns the owner

Location: `refer.py` `_invert` (165–171) folds the anchor's containment family
for both `owned_by` and `held_by`.

- **`("owned_by", anchor)` folds the anchor's own `owned_by` key.** An
  entity-valued winner, resolved through identity, is the referent: "the owner by
  the possession" (§9). Without one, the constraint does not resolve and the
  cascade continues.
- **`held_by` and `contains` are unchanged.**

**Oracle:**
- `obj:watch` is in `obj:desk_drawer` and `owned_by person:marn`.
  `refer(..., constraints=[("owned_by", "obj:watch")])` returns `person:marn`,
  signal `constraint_inversion:owned_by(obj:watch)`. Today: `obj:desk_drawer`.
- A cup with no `owned_by` row: the constraint does not resolve.
- `held_by(lantern)` still returns its holder, and `contains(watch)` the drawer.

## §7 Learned aliases already in host worlds

Today's learned aliases are `alias` rows whose `source` meta row starts
`refer:tier2:`. `_accrue_alias` wrote all of them, all canon and all timeless.
The engine never rewrites them.

- **Tier 1a skips them.** `by_alias` returns authored names and aliases only. The
  check reads the `source` rows of the matching alias rows only, in one query.
- **Tier 1d honours them** under §3's rule, like a `learned_alias`.
- **Why that is safe.**
  - **A legacy pick.** It was learned where tier 1a or tier 1c already had two or
    more candidates.
    - **An alias-collision pick.** The colliding aliases are still in the log
      (append-only). Wherever they are visible, tier 1a collides again before
      tier 1d.
    - **A kind pick** ("the drawer"). Any scope holding an entity of that kind
      resolves or picks at tier 1c first. With no scope, tier 1c sees every
      entity of the kind, the picked one included. A scope holding no entity of
      that kind doesn't hold the picked entity either, so §3's scope filter drops
      it.
    - **Where it can still surface.** Only where none of that is visible to the
      call: for example, a collision whose other aliases lived in `knows:` frames,
      which a canon call no longer reads (§4). There it acts as a word, filtered
      by scope. Construct has no such case (below).
  - **A legacy word** keeps working where its entity is in scope.
- **Every other read is unchanged.** Identity anchors, `state`, `snapshot` and
  `facts` keep seeing them as the `alias` rows they are. Nothing is hidden or
  rewritten. A host that judges a row wrong retracts it; one that wants it as a
  real name authors an `alias`.

**Recipe** (porcelain only; it goes into ADOPTION):

```python
legacy = [f for f in p.facts("canon", attribute="alias")
          if any(str(s).startswith("refer:tier2:")
                 for s in f["provenance"]["source_chain"])]
learned = p.facts(frame, attribute="learned_alias")   # words learned after this spec
```

**Measured on construct** (read-only):
- **Where they are.** 11 legacy rows sit in 6 of the 52 live world files. 18 sit
  in 12 files once `_retired/` and `attic/` are counted (165 files). All are
  canon.
- **Picks: 6 live, 11 overall.** These are alias-collision picks:
  - live: `veyr`, `persephone`, `lysa`, `the river-facing door`;
  - retired: `ada`, `brask`, `the mountain`, `the road`, `the evac bay`.

  In every one, two or more entities still carry the text as an authored canon
  alias. So tier 1d is never reached, and all are inert. Two live texts (`veyr`,
  `persephone`) were learned twice: ambiguous reads appending.
- **Words: 5 live, 7 overall.** They stay honoured where their entity is in
  scope:
  - live: `the token`, `the brass token`, `that token`;
  - retired: `this house`, `this parlor`.

**Oracle** (legacy rows seeded exactly as `_accrue_alias` writes them):
- **Legacy "the drawer" → `obj:desk_drawer`:**
  - in the kitchen: `obj:kitchen_drawer` (`unique_kind_in_scope`);
  - in the study: tier 2, nothing appended.
- **Legacy "the old cupboard" → the kitchen cabinet:**
  - in the kitchen: tier 1 `learned_alias`;
  - in the garage: re-judged.
- **The recipe** returns exactly the two legacy rows.

## §8 `ask` never learns

Location: `porcelain.py` `ask` (953) passes `learn=False`.

- **Why its words can't be learned.** `ask` binds every target in canon on
  purpose: identity is a canon question (LIVE-FINDINGS-V1 Fix 3). But it speaks
  for its asker.
  - Only a `knows:` ask has a scope, so only a `knows:` ask can reach the
    escalation.
  - The word it would learn is the asker's. Writing it in canon would put, say,
    Alice's private name for her hiding place into canon.
- **Canon asks** never escalate (they have no scope), so they never learned
  anyway.
- **So `ask` writes nothing.** It still reads learned aliases that direct `refer`
  calls wrote.

**Oracle:** an `ask` whose target is ambiguous, or a vocabulary miss, resolves as
today and appends no row. Today: +2 rows.

## What hosts see

| Case | Today | After |
|---|---|---|
| Ambiguous reference, confident tier 2 | resolved; +2 rows; the next call resolves at tier 1 `alias_exact` | resolved; no rows; the next call asks tier 2 again (one cheap call) |
| The same words in another room | the first room's entity, forever | that room's entity (tier 1c, or tier 2) |
| Vocabulary miss, first use | tier 2; +`alias` row in canon | tier 2; +`learned_alias` row in the call's frame |
| Second use | tier 1 `alias_exact`, anywhere | tier 1 `learned_alias`, only where the entity is in scope (anywhere if unscoped) |
| Name or alias in a `knows:` frame (batch C) | resolves in canon | resolves only in that frame |
| `asserted_as_of` before an alias | sees it | doesn't |
| Alias stored as `"The Memory Core"` | never matches | matches regardless of case and outer spaces |
| `owned_by` constraint | the possession's container | the owner, or no resolution |
| `ask` | may write 2 rows per target | writes nothing |
| Snapshots | learned words appear as `alias` facts (`current_state`, `establishing_set`, `situation`) | never a standing fact; listed in `what_happened`, like `same_as` and `aka` events |

**For construct:**
- **Adjudication.** The scoped `refer` behind adjudication stops pinning "the
  drawer" to one room. Synonyms still cost one call, once per scene, and are then
  deterministic.
- **The unscoped name check in `_identity`** no longer binds a name that exists
  only in an NPC's `knows:` frame. That is C's frame rule; C measured 23 alias
  texts whose canon answer changes across the 52 live worlds.
- **Legacy rows:** §7's counts.
- **Normalization:** §5's one text.

No other host calls `refer` (Kernos and holo-emitter checked). None matches on
receipt signal strings.

## What stays byte-identical

- **Most `refer` answers.** Every answer that involves none of these keeps its
  status, entity, candidates and receipt:
  - a learned row;
  - a non-canon or late alias;
  - an alias stored un-normalized;
  - an `owned_by` constraint.
- **The rest of the cascade:**
  - tier 1b `contains` and `held_by`;
  - tier 1c;
  - the escalation's candidates;
  - the tier-2 prompt, schema (`patternbuffer_refer`), floor and receipt shape.
- **Model calls.** No deterministic path gains a model call. The only extra calls
  are ambiguous references re-judged where today a learned pick short-circuits.
- **The log.** No row is rewritten, retracted or hidden. Worlds that never learned
  are unchanged, and the dump format is unchanged.
- **Identity reads are untouched by D:**
  - `closure`;
  - `reconcile`;
  - `proposals`;
  - `name_collisions`;
  - `fidelity_audit`.
- **`ask` otherwise:** the plan call, scope derivation, folds and `Answer` shape.

## Coordination

- **C — FRAME-SCOPED-IDENTITY-V1** (r1, `cee055b`).
  - **What C owns:**
    - `by_alias`'s frame, and refer's frame passthrough (C §2);
    - `add_alias`'s write frame (C §1c).
  - **What D adds on top:**
    - `asserted_as_of` (§4);
    - normalization (§5);
    - the legacy skip (§7).
  - **Shared code.** Both edit `by_alias` and `refer.py` 110–112. The second to
    land rebases; the semantics compose.
  - **One overlap: who writes the learned row.** C §1(e) and oracle 1g thread
    the call's frame into `_accrue_alias`, so a tier-2 hit writes its `alias` row
    in that frame. D replaces that write:
    - the frame rule is the same (the call's frame);
    - the row is a `learned_alias`;
    - only the vocabulary-miss path writes it.

    When D lands, 1g's test asserts a `learned_alias` written by a miss in
    Alice's scene.
  - **C's Q5** (`ask(frame=knows:X)` keeps binding in canon, revisit with D/E).
    D leaves the binding as it is and only stops `ask` writing (§8). The asker's
    private words go to E (decision 2).
  - **Legacy rows stay identity anchors.** C's anchor readers become canon-only,
    and legacy learned aliases are canon, so they remain anchors. If C also
    skipped refer-written aliases, legacy rows would leave identity too, and §7's
    last bullet would say so.
- **B — GATE-AUTHORITY-V1** (r1, `5a1ea49`).
  - **No conflict.** B refuses only its `MECHANISM_ATTRIBUTES` (`retracts`,
    `resolved_by`, `canonicalized_from`) at the gate. `learned_alias` is not
    among them and changes the meaning of no other row.
  - **D's item passes B's checks.** It is `inferred` (ingestor authority) and
    carries `source_doc`; B refuses `source_doc` only on `generated` items.
  - **B §8 keeps the classification.** Its new classifier rule touches only rows
    that no guardrail decides and whose subject is an assertion id.
    `learned_alias` has an entity subject and is decided EVENT by the existing
    META guardrail, and its `source` row (an assertion subject) is already EVENT.
- **E — READ-SURFACE-V1.** Its porcelain `refer` inherits this rule and should
  expose `learn=`.
- **`perf/read-caches`.** It caches identity per log head. D's `by_alias` edit
  sits nearby, so expect a rebase but no interaction in behaviour.
- **A and GATE-INVERSE-ALIAS-V1:** no overlap.

## Non-goals

- **Promoting a learned alias to a name.** A host that wants one authors an
  `alias` (§7 recipe).
- **Valid-time filtering** of names and aliases (§4).
- **Looser text matching.** No collapsing of interior whitespace. No matching a
  stored determiner ("the memory core") from a query without one ("memory
  core"): HD 003 strips the query, not stored text.
- **More determiners** ("this", "that"). Construct's legacy words include "this
  house" and "that token"; that is a separate change.
- **Other constraint behaviour (unchanged):**
  - `held_by` resolving to a non-agent container (a watch in a drawer resolves to
    the drawer);
  - inversions over a conflicted fold.
- **Whether identity and meta rows belong in `what_happened` at all.**
- **A vague expression on the miss path** ("the thing") that tier 2 answers
  confidently is learned as a word. The prompt already tells the model to return
  null when genuinely ambiguous. Scene scope bounds the damage, and a host can
  retract the row.
- **Authored kind-word aliases** ("the vault", attached at extraction) still win
  tier 1a over a unique kind in scope (chapter test #26). That is a separate
  question about shape.

## Decisions for Kabe (each with a default)

1. **The rule (§1).** It reshapes 018's accepted mechanic: scene scope replaces
   "promoted on recurrence", and learned words get their own attribute.
   *Default:* adopt as written.
2. **`ask` never learns (§8).** *Default:* yes. The alternative, learning into
   the asker's frame, needs `ask` to read the asker's words as well; that belongs
   with E's porcelain `refer`.
3. **Legacy rows honoured at tier 1d (§7)**, not ignored. *Default:* honour. It
   keeps construct's 7 words; the 11 picks are inert either way.
4. **Amend whitepaper §9's last line** at merge to: "refer never logs a pick; it
   logs a word learned on a vocabulary miss, scoped to the scene and below
   authored vocabulary (REFER-LEARNING-V1)." *Default:* amend, with an A-number,
   since today's line invites logging picks.

## Migration and notice

**Engine:** none. Nothing is rewritten, and legacy rows are read under §7 from the
next call.

**Ship notice to construct:** the host table, the recipe, and the measured counts.

**Docs, in the implementation commit:**
- **LEXICON:** an entry for "learned alias / `learned_alias`", retiring
  *accrued alias*.
- **ADOPTION:**
  - `refer`'s `asserted_as_of=` and `learn=`;
  - the rule;
  - the recipe;
  - `ask` writes nothing.
- **PORCELAIN-V1:** a dated note on the ask clause ("accrued-alias writes … the
  ONLY writes ask can cause").
- **The R7 eval:** `evals/household_dialogue/key.md` R7 and
  `evals/harness/battery_micro.py` R7 grade the `learned_alias` row and the
  `learned_alias` signal.

## Tests

- **New file:** `tests/test_refer_learning.py`, with one test per oracle in
  §2–§8.
- **An invariant test:** for each ambiguous path, N identical reads leave
  `buffer.head()` unchanged:
  - the tier 1a collision;
  - the tier 1c pick;
  - the tier 1d collision.
- **One existing test changes in the same commit**, citing audit P1 #4:
  `tests/test_world.py::TestRefer018Extensions::test_zero_candidate_escalation_scope_bounded`.
  - The second-use signal becomes `learned_alias`.
  - The learned row is a `learned_alias`.
  - Its scripted classify response goes unused.
- **The full suite stays green.**

## Rebased onto batch C r2 (2026-10-09)

D was built on C r1 (`c4c86b0`). C is now r2 (`7799598`, on B r2), so the nine
commits were replayed onto it; the pre-rebase head is kept as
`archive/refer-learning-v1-on-c-r1` (`99d4834`). D's behaviour is otherwise
unchanged.

- **Whitepaper row A22.** D's §25.9 row, which said A18, is **A22**, after A21
  (FRAME-SCOPED-IDENTITY-V1). Main holds A18 (FOLD-CORRECTNESS-V1) and A19
  (GATE-INVERSE-ALIAS-V1); B r2 holds A20; C r2 holds A21. Every reference to
  D's own row reads A22: the §9 amendment line, the LEXICON entry, `refer.py`'s
  module docstring, and the §1 commit message. No other row was touched.
  `specs/STATUS.md` and the README test count were never edited by D; they
  follow the merge.
- **Conflicts and how they were resolved.**
  - `docs/WHITEPAPER.md` (§25.9 table): kept C r2's A18-A21 rows, dropped C
    r1's A19 row, added D's row as A22.
  - `identity.py` `by_alias` docstring (twice: §5, then §7): C r2 had reworded
    the frame sentence; D's text is kept with its frame sentence in C r2's
    words.
  - `docs/ADOPTION.md` (the `refer` signature block): D's block kept, with
    C r2's example (an alias only canon carries does not resolve in `knows:X`).
  - `docs/LEXICON.md`: D's `learned alias` row kept above C r2's `distinct_from`
    row.
- **The §7 check (C's observer-frame following).** C r2 withdrew its §7: a
  `knows:<id>` frame reads only the rows stored under its own name, and merges
  do not widen it. Nothing in D's code or tests relied on it: every frame
  oracle uses one stored frame (`knows:person:alice`) and a name or alias
  stored in that same frame, and the suite passes unchanged. Four texts did
  lean on it and were corrected to exact-frame wording: this spec's §4 bullet
  ("an observer frame is read through identity (C §7)"), the `by_alias` and
  `_vocabulary_matches` docstrings ("an observer frame through its §7"), and
  ADOPTION's "(an observer frame through its stored names)". A learned word
  written in `knows:person:alice` is read in that frame only, as before.
- **Other C r2 changes.** The extraction-prompt sentence, `same_as_not_canon`,
  `distinct_group`, the `_is_known` speed fix and the group-level
  `distinct_from` check do not touch refer, and no D oracle changed. The
  coordination notes above still name C r1 and B r1 by SHA; those are the
  versions D was specced against.
