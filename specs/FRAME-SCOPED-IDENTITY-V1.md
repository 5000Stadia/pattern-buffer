# FRAME-SCOPED-IDENTITY-V1: identity is canon's, description is perspectival

**Status:** r2 (2026-10-09; r1 2026-10-08). Batch C of `docs/AUDIT-2026-10.md`
(P1 #1, #7, #8, the snapshot existence leak, the `identity_conflicts()` read).
r1 was built gated on `impl/frame-scoped-identity-v1`, over batch B r1. pbr
returned RED on one point (§1's receipt codes) and ruled it; an internal
pre-review measured on copies of construct's live worlds that §7 leaks
knowledge. r2 is rebased onto batch B r2 (`impl/gate-authority-v1` at
`dddbb64`), withdraws §7 from this build pending Kabe's gate g3bf5da (consult
ccab80f), and resolves the rest: see "r2: review resolutions" at the end. Next:
pbr on r2. Founder decisions 1 and 2 (2026-10-08, below) are binding inputs;
§7, which builds decision 2, is held. Every case below reproduced on `212754f`
(`polish/audit-2026-10`) before it was written down. Host blast radius measured
read-only on construct's 52 world files (`/home/k/Newproject/worlds/*.world`).
Line numbers are at `212754f`.

**Why.** §6 promises that out-of-frame content is absent from every served
payload. Identity breaks that promise in both directions:
- a `same_as` written in Alice's belief frame merges canon, so canon serves a
  stranger's facts under Bob's id;
- a name or alias known only to Alice drives canon `reconcile`, canon `refer`,
  and canon `typing_conflicts`;
- a canon `retype` retracts a kind row in Marn's frame;
- `fidelity_audit(frame="canon")` lists a conflict that exists only in
  `knows:person:marn`, and `snapshot(..., frame="canon")` accepts an id that
  exists only in `plot:`.

Separately, the `aka` vetoes have holes (a chain bypasses `distinct_from`;
`reconcile` collapses a valid-timed reveal into a timeless merge), a raw
`same_as` can fuse a ring with the box that holds it and nothing reports it, and
`open_conflicts` is a stored table that only a below-porcelain call refreshes.

## Founder decisions (binding)

1. **`same_as` is canon-only.** The gate refuses it in any other frame, with a
   skip receipt. Aliases and names **are** frame-scoped: Alice may call Bob "the
   traitor" without canon learning it.
2. **`knows:` frames resolve through identity at read time.** After
   `merge(dan, daniel)`, what was written to `knows:person:daniel` is readable as
   `knows:person:dan`, and `who_knows` reports the surviving frame name.
   - *r2: held.* §7, which builds this, is withdrawn from this build pending
     Kabe's gate g3bf5da: on construct's live worlds, automatic merges would
     hand characters other characters' knowledge (§7).

## The model in three lines

- **Identity is canon's.** Which ids are one thing is one fact about the world,
  not a belief. The `same_as` closure, the edges that make, propose or forbid it
  (`same_as`, `maybe_same_as`, `distinct_from`: the **canon identity edges**),
  and every check that decides a canon merge read and write canon only. Every
  frame resolves ids through that one closure.
- **Description is perspectival.** What an entity is called (`name`, `alias`)
  and which ids someone takes to be facets of one person (`aka`) stay in the
  frame they were written in, and are read only there.
- **An observer is an identity.** A `knows:<id>` frame holds the knowledge of
  whoever `<id>` is, so it reads every stored `knows:<m>` for `m` in `<id>`'s
  canon closure: an **observer frame**. *(§7; withdrawn from this build in r2.
  In this build every frame reads only the rows stored under its own name.)*

A perspectival identity *belief* ("Alice thinks the masked man is Bob") is an
`aka` row in Alice's frame, read by `correlations`/`state_union(frame=...)` as
AKA-CORRELATION-V1 already allows. It is never a `same_as`.

## §1 Identity writes carry the item's frame

**Rule.**
- **(a) Canon identity edges are canon-only.** An item whose canonicalized
  attribute is `same_as`, `maybe_same_as` or `distinct_from`, with an effective
  frame other than `canon`, is skipped. Nothing is appended for it. The receipt
  (r2, pbr's ruling; r1 gave all three `identity_edge_outside_canon`):
  - a raw `same_as`: GATE-AUTHORITY-V1 §2's `same_as_not_canon`, with `detail:
    {field: "frame", value: <frame>}`. That code is B's public contract for any
    non-canon `same_as`;
  - a `maybe_same_as` or `distinct_from`: `identity_edge_outside_canon`, no
    `detail`.
- **(b) The side-channel `same_as` key** on a non-canon item is skipped with
  B's code and payload, as `SkipRecord(entity, "same_as", <value>,
  "same_as_not_canon", detail={"field": "frame", "value": <frame>})` (r2). The
  item's main row is admitted as usual. No `maybe_same_as` is written.
- **(c) The side-channel `aliases` key** writes each alias row in the item's
  effective frame (today: always canon).
- **(d) `aka` stays frame-scoped.** A raw `aka` row keeps its item's frame, as
  today.
- **(e) `refer`'s tier-2 alias accrual** writes in the frame `refer` was called
  with (today: always canon). Batch D (REFER-LEARNING-V1) decides *when* accrual
  happens; this rule fixes only *where* it lands.
- The registry's write verbs are unchanged and always write canon: `merge`,
  `maybe_same_as`, `reject`, `correlate`.

**Ordering.** The effective frame is the one the main row would carry:
`item.get("frame", CANON)` after the call-level `frame=` default. In
GATE-AUTHORITY-V1 r2's thirteen steps (r2):
- Check (a) for `maybe_same_as`/`distinct_from` runs at the head of step 9: on
  the raw ids, after the authority raises (step 2) and the malformed-id checks
  (steps 7 and 8), before identity resolution. So a generated edge aimed at
  `knows:` still raises, and a malformed one still receipts `malformed_id`.
- Check (a) for `same_as` is B's own, at step 11 in the guarded-merge path,
  after its value check: one refusal path for it, never two.
- Check (b) runs where the side key is handled (step 12), after its own
  malformed-id check. It receipts the item's original subject, resolved (the
  inverse swap's convention, GATE-INVERSE-ALIAS-V1), as that check does.
- Under `atomic=True` either skip aborts the set through the existing
  `gate_skip` path.

**Why `maybe_same_as` and `distinct_from` too** (decision 1 names only
`same_as`, so this is my reading; see open question Q1):
- Their only readers are the canon closure machinery: proposals, reconcile,
  promote and confirm, and the merge vetoes.
- Today, written outside canon, they leak. A belief-frame `distinct_from` vetoes
  a canon merge (probe 1e). The `same_as` key on Alice's item lands as a *canon*
  proposal that `proposals()` lists (probe 1b).
- After §2 they would be inert rows that no read consults. A receipt is the
  honest outcome, and `aka` in the frame expresses the belief.

**Location.** `ingest.py` `_ingest_item`: the new check goes between the
malformed-id gate (839–848) and resolution (849–852); on B r2, the head of step
9. The `aliases` loop (971–972) and the `same_as` key (982–992), step 12 on B
r2, change. `identity.py` `add_alias` (103) gains `frame: str = CANON`. In `refer.py`, the call's frame is threaded
through `_resolve_tier2` (225) into `_accrue_alias` (77–95). The reason string
joins the skip vocabulary in ADOPTION.

**Oracle** (Alice = `knows:person:alice`):
- 1a. Item `{person:hooded · kind · person, frame: Alice, aliases: ["the traitor"]}`.
  - Today the alias row's frame is `canon`.
  - After, it is `knows:person:alice`.
- 1b. The same item with `same_as: "person:bob"`.
  - Today it writes a canon `maybe_same_as`, and canon `proposals()` lists
    `(person:hooded, person:bob)`.
  - After: `skipped == [{person:hooded, same_as, person:bob, same_as_not_canon,
    detail: {field: frame, value: knows:person:alice}}]` (r2), no
    `maybe_same_as` row, and `proposals() == []`.
- 1c. A raw `person:stranger · same_as · person:bob` in Alice's frame.
  - Today it is appended, and the canon fold of `person:bob · occupation` serves
    the stranger's `"spy"`.
  - After it is skipped `same_as_not_canon`, and the canon fold is unknown.
- 1d. Raw `maybe_same_as` and `distinct_from` rows in `knows:` and in `plot:` are
  skipped `identity_edge_outside_canon`.
- 1e. A raw `aka` in Alice's frame is admitted in Alice's frame (unchanged).
- 1f. `ingest_structured([...non-canon same_as...], atomic=True, classify="rules")`
  raises `AtomicAbort(cause="gate_skip")` carrying the receipt, and nothing is
  visible.
- 1g. `refer("the traitor", frame=Alice)` with a tier-2 hit writes its alias row
  in Alice's frame.
- 1h (r2). The full extraction rules' ALIASES bullet tells the extractor to emit
  `same_as` on the entity's frame `canon` row.
- 1i (r2). A raw `same_as` and an item's `same_as` key, both in Alice's frame,
  give one identical receipt (`same_as_not_canon`, `detail: {field: frame,
  value: knows:person:alice}`); raw `maybe_same_as`/`distinct_from` there give
  `identity_edge_outside_canon`.

**The extraction prompt (r2; a prompt change for pbr).** The full rules'
ALIASES bullet said "if you minted a duplicate id for the same individual, emit
same_as." Under B and this section a `same_as` on a non-canon item is refused,
so a duplicate the extractor recognized in a `knows:` item would stay split.
The sentence now ends "emit same_as on that entity's row in frame 'canon'
(identity is canon-only)." The lean rules carry no `same_as` sentence and are unchanged.
Oracle 1h: the full rules' ALIASES bullet carries the new sentence.

**Hosts see.**
- `Receipt.skipped` gains `identity_edge_outside_canon` entries (a non-canon
  `maybe_same_as`/`distinct_from`) and `same_as_not_canon` entries for an
  item's non-canon `same_as` key (r2).
- Aliases supplied on non-canon items stop reaching canon (§2 then stops reading
  them in canon).

**Byte-identical.** Every canon item: same rows, same receipts.

**Existing logs.** Nothing is rewritten.
- Rows that today's gate put in canon on behalf of non-canon items stay canon,
  because the log does not record which item wrote them. That covers `aliases`
  rows and `maybe_same_as` rows from the `same_as` key.
- A heuristic estimate for construct: about 1,100 canon `alias` rows in 37 of 52
  worlds were written this way. The heuristic: the nearest earlier row about the
  same entity is non-canon.

## §2 Identity reads are canon reads

**Rule.** The identity registry decides canon identity from canon rows only.
Every `visible()` in `identity.py` that feeds such a decision passes
`frame=CANON`:
- **The closure.** `closure` (323), `resolve` (309: the representative election
  becomes "first seen among canon rows"), `_same_as_path_ids` (614, 617).
- **The vetoes and signals.**
  - `containment_block` (125), `distinct_block` (143),
    `relating_edges_between` (162) and `_relating_rows_between` (970).
  - `durable_contradictions` (193).
  - `_containment_rows_between` (716), `_outgoing_domain_rows` (733) and
    `_incoming_children` (748).
- **Anchors.** `typed_name_anchors` (354), `reconcile`'s name scan (530),
  `typing_conflicts`' name scan (776).
- **Proposals.** `candidates` (340), `_has_proposal` (491),
  `promote_identity_proposals` (506, 511), `confirm` (633, 639),
  `adjudicate_deferred` (677), `_candidate_bindings` (1003),
  `enumerate_proposals` (1082, 1094).
- **`retype`.** `_retract_kind_rows` (850) retracts canon `kind` rows only.
- The kind readers (`_kind_state`, `_kind_values`, `_kind_label`) already fold
  canon through the kind provider. No change.

`resolve`/`closure` feed every fold (`Indexes._resolve`/`_closure_of`), so
every frame now resolves ids through the canon closure. A belief frame can no
longer hold a merge of its own: that is decision 1.

**Frame-parameterized identity reads.**
- `name_collisions(frame)` grouping (435), and the `aka` rows of
  `correlation_set`/`correlations`/`correlation_conflicts` (1140, 1239), keep
  the caller's frame.
- `by_alias` gains it: `by_alias(alias, asserted_as_of=None, frame=CANON)`
  reads `alias`/`name` rows in that frame only. There is no canon fallback for a
  non-canon frame: frames never inherit canon in a read. So
  `refer("bobby", frame="knows:person:alice")` no longer resolves an alias only
  canon carries (the base engine read every frame's aliases); this goes in the
  ship notice (r2).
- `refer` tier 1a passes its own `frame` to both `by_alias` calls (110–112).
  `ask()` still resolves references against canon (HD 003, `porcelain.py`
  940–953), so an alias private to Alice does not resolve in
  `ask(frame=Alice)`. See Q5.
- `correlations()`' facet-ordering scan (1175) stays all-frames: it orders,
  never selects (Non-goals).

**Oracle:**
- 2a. A legacy `same_as` row in Alice's frame. A test appends it with the
  ingestor role, past the §1 gate.
  - Today `closure(person:stranger)` includes Bob, and the canon fold of
    `bob.occupation` is `"spy"`.
  - After, the closure is `{person:stranger}` and the fold is unknown.
- 2b. `person:hooded · name · "Bob"` only in Alice's frame, beside canon
  `person:bob · name · "Bob"`. `reconcile()` merges 0 pairs (today 1).
- 2c. `person:bob · alias · "the traitor"` only in Alice's frame.
  - `by_alias("the traitor") == set()` (today `{person:bob}`).
  - `by_alias("the traitor", frame=Alice) == {person:bob}`.
  - `refer("the traitor")` is underdetermined (today resolved);
    `refer("the traitor", frame=Alice)` resolves `person:bob`.
- 2d. `obj:crown` is `kind person` in canon and `kind ghost` in
  `knows:person:marn`. `retype(obj:crown, "relic")` retracts only the canon row;
  Marn's "ghost" survives (today it is retracted).
- 2e. Canon `place:harth` (named "Harth") and `person:harth`, whose name "Harth"
  lives only in `knows:person:marn`: `typing_conflicts() == []` (today 1).
- 2f. Two canon `"Clay"`s, with `clay1 · father_of · clay2` only in Alice's
  frame: `_mergeable` is `True`, by canon's own rules (today `False`, blocked by
  Alice's belief).
- 2g. `obj:a · in · obj:b` only in Alice's frame: canon `guarded_merge(a, b)`
  returns `merged` (today `vetoed`).
- 2h. `durable_contradictions` is byte-identical: its folds were already canon
  (probe: a contradiction carried only by a `knows:` attribute already returns
  `[]`). The scan is scoped for consistency only.
- 2i. Representative election on canon rows only re-elects 0 closures across
  construct's 52 worlds.
- 2j (r2, for the notice). Canon `person:bob` with alias "bobby": `refer("bobby")`
  resolves Bob; `refer("bobby", frame=Alice)` is underdetermined (the base engine
  resolved it).

**Hosts see.** Canon `refer`, `reconcile`, `proposals`, `typing_conflicts`,
`retype` and every merge veto stop seeing non-canon rows. Measured on construct:
- 23 alias texts change their canon `by_alias` answer. 4 go from ambiguous to
  unique, and 4 that only a `knows:` frame carried stop resolving in canon (for
  example `"oren pike"` in `ironhold*`).
- In the 5 `thedeep*` worlds, a `knows:`-frame `same_as` stops merging
  `person:chen` with `person:elias_chen` in canon (see Migration).

**Byte-identical.** Every identity answer in a world whose rows are all canon.
Elsewhere, only where a non-canon row used to reach an identity decision.

**Existing logs.** Legacy non-canon `same_as`/`maybe_same_as`/`distinct_from`
rows become inert: no identity read consults them, and raw scans
(`facts(include_meta=True)`) still list them. Non-canon `name`/`alias` rows are
read in their own frame only.

## §3 `aka` vetoes act on whole correlation groups

A **correlation group** is the connected component that
`correlation_set(x, ..., frame)` computes: `aka` edges, each expanded through
the canon closure. Which edges count depends on the verb:
- **(a), (c) and (d)** write or decide canon identity. They take the group over
  canon `aka` edges at every valid time (`valid_as_of=None`, `_aka_relates`'
  existing convention). A merge or a `distinct_from` is timeless, so it
  contradicts a reveal whenever the reveal lands.
- **(b)** takes the group over F's `aka` edges, as-of.

**(a) `correlate(a, b)` (1192).** The checks, in order:
1. A direct `distinct_from` between the two closures gives `vetoed_distinct`
   (unchanged).
2. Already in one group gives `noop_already_correlated` (unchanged).
3. **New:** a canon `distinct_from` with one endpoint in a's group and the other
   in b's gives `vetoed_distinct`, reason `distinct_from`, with `blocking_edges`
   naming those edges. Nothing is appended.
4. Otherwise the edge is appended.

Steps 1 and 2 keep today's order, so every existing outcome is unchanged.

**(b) `correlation_conflicts(valid_as_of, asserted_as_of, frame)` (1221).**
- A contradiction is two edges in one frame. The read now reports every
  `distinct_from` in frame F whose endpoints lie in one F-group as-of. The
  F-group filters each `aka` edge by both time axes; `distinct_from` stays
  valid-time-blind, as today.
- Today the read reports only a pair joined directly by one `aka` row, and it
  mixes F's `aka` with every frame's `distinct_from`.
  - Belief versus canon (Alice's `aka` beside canon's `distinct_from`) is
    contested truth (§6), not a contradiction to retract.
  - After §1, a non-canon `distinct_from` can only be legacy.
- **Direct entries come first**, in today's order with today's four keys and
  values. They gain `aka_path: [aka_edge]`.
- **Group entries follow**, in `distinct_from` log order:
  `{a, b, aka_edge: None, aka_path: [descriptors along the shortest group path, neighbours visited in sorted order], distinct_edges}`.
- One entry per resolved pair; a direct entry wins.
- `distinct_block` gains `frame: str = CANON` for this read.

**(c) The auto-merger never collapses a correlated pair.**
- `_mergeable` (385) returns `False` when `_aka_relates(a, b)`, placed right
  after the two hard vetoes.
- `reconcile` (551–557) does not propose such a pair: it is settled, like a
  hard-blocked one.
- `_decline_context` (1011) gains code `correlated`, right after `containment`,
  mirroring `_mergeable`'s order. A pre-existing proposal between correlated
  facets is listed with that code.
- `adjudicate_deferred`'s inline check (691) becomes `_aka_relates`. That is
  identical.
- Host-authoritative merges stay available: `merge`, `confirm`, and `retype`'s
  absorb.
- This **amends AKA-CORRELATION-V1 §1** ("the merger is neutral to it").
  Neutrality let an anchor-driven, timeless `same_as` swallow a valid-timed
  reveal, so the masked figure's name leaks to before the reveal: the exact
  backward leak `aka` exists to prevent. `aka` becomes a **soft** auto-merge
  block, never a hard veto.
- **(r2, pre-review NIT) The group-level `distinct_from` blocks the
  auto-merger too.** r1 blocked only a directly correlated pair: after `a~b`,
  `reject(b, x)` and a name shared by a and x, `reconcile()` merged a with x
  (the base engine does too), which puts b's `distinct_from` inside one
  correlation group, though `correlate(a, x)` refuses exactly that. Now
  `correlate`'s own group check (one helper, `_group_distinct_block`: a canon
  `distinct_from` with one endpoint in a's group and the other in b's, at every
  valid time) is read by:
  - `_mergeable`, right after the `aka` test (`correlate`'s order);
  - `reconcile`'s proposal guard: such a pair is settled, never proposed;
  - `adjudicate_deferred`'s inline checks, after the `aka` test;
  - `_decline_context`: code `distinct_group`, right after `correlated` (a
    direct distinct pair never lists); the display string names the first
    edge, `distinct_group: person:b·distinct_from·person:x`;
  - `name_collisions`' pair status: `hard_blocked`, reason `distinct_group`, so
    the group is not live (reconcile would never act on it).
  With no `aka` edge on either side the groups are the two closures, and the
  check is `distinct_block` again, already tested first: byte-identical on a
  world without `aka` (every construct world). The host's `merge`/`confirm`
  stay available, as for a correlated pair.

**(d) `reject(a, b)` (588).** After the `conflict_already_merged` check, if
b's closure is in a's canon group the verb returns `conflict_already_correlated`
and writes nothing:
`{outcome: "conflict_already_correlated", canonical_id, merge_event_id: None, reason: "already_correlated", blocking_edges: [...]}`.
- `blocking_edges` holds the assertion ids of every canon `aka` row inside the
  shared group. This mirrors how `conflict_already_merged` names `same_as` ids.
- It takes precedence over `noop_already_distinct`. A pair that is both
  correlated and distinct is already a contradiction, and the receipt should say
  so.

**Oracle:**
- 3a. Canon `a~b`, then `reject(a, c)`.
  - `correlate(b, c)` returns `vetoed_distinct` with
    `blocking_edges == ["person:a·distinct_from·person:c"]`, and the head is
    unchanged. Today it returns `correlated`.
- 3b. A raw `a aka b` (valid_from 2) and a raw `b aka c` (valid_from 5), both
  canon, plus `reject(a, c)` made before either.
  - `correlation_conflicts(as_of=6)` returns one entry:
    `{a: person:a, b: person:c, aka_edge: None, aka_path: [a·aka·b, b·aka·c], distinct_edges: [a·distinct_from·c]}`.
    Today it returns `[]`.
  - `as_of=3` returns `[]`.
- 3c. `person:masked` (alias "ilsa") and `person:ilsa` (name "Ilsa"), correlated
  at t=10.
  - `reconcile()` merges 0 and appends no proposal.
  - `fold_key(masked, "name", valid_as_of=5)` returns nothing.
  - Today they merge, and the name at t=5 is `"Ilsa"`.
- 3d. Given a `maybe_same_as` between them, `proposals()` lists it with
  `auto_decline.code == "correlated"`, and `promote_identity_proposals()`
  merges 0.
- 3e. After `correlate(p, q)`, `reject(p, q)` returns
  `conflict_already_correlated` naming the `aka` row id, and the head is
  unchanged. Today it returns `rejected` and writes the contradiction.
- 3f. `p.merge(masked, ilsa, ...)` still returns `merged`.
- 3g (r2). `a~b`, `reject(b, x)`, a and x both named "Vell": `correlate(a, x)`
  is `vetoed_distinct`; `reconcile()` merges 0 and proposes nothing (r1: merged
  them); `correlation_conflicts()` stays `[]`; the "vell" collision pair is
  `hard_blocked`/`distinct_group` and not live.
- 3h (r2). Given a canon `maybe_same_as(a, x)`: `proposals()` lists it with
  code `distinct_group` and reason `distinct_group: person:b·distinct_from·person:x`;
  `promote_identity_proposals()` merges 0; `adjudicate_deferred()` merges 0.

**Hosts see.**
- Construct calls `reject()` on cross-kind collision pairs (`game.py` ~513–526).
  A correlated pair now returns `conflict_already_correlated` instead of writing
  a `distinct_from`. Construct ignores the outcome.
- `auto_decline.code` gains the values `correlated` and (r2) `distinct_group`.
  Construct's residue triage (`game.py` ~281–303) rejects only
  `containment`/`relating_edge` and leaves such a proposal deferred.
- No construct world holds an `aka` row today. 0 of 52.

**Byte-identical.** A world without `aka` edges: every identity answer.
Existing `correlation_conflicts` entries keep their keys and values, plus
`aka_path`.

**Existing logs.** No rewrite. A group conflict already in a log becomes
visible through (b).

## §4 `identity_conflicts()`: merged groups that hold a vetoed pair

A raw or legacy `same_as` could merge a pair that the guarded merge vetoes, and
no read said so (probe: a raw `obj:ring same_as obj:box` merges a vetoed,
containment-related pair, and `locate(ring)` becomes `[]`). Batch B
(GATE-AUTHORITY-V1) routes new raw canon `same_as` through the guarded merge.
This read surfaces what is already in logs, and any `distinct_from` written
later inside a closure by raw ingest.

**Rule.** `IdentityRegistry.identity_conflicts(asserted_as_of=None) -> list[dict]`.
It covers each canon `same_as` closure of two or more members that contains a
pair the guarded merge would veto. That means a canon containment-family row
(entity-valued) or a canon `distinct_from` row, with both endpoints in the
closure, at any valid time (the vetoes' own predicate).

```
{"canonical_id": "obj:box",
 "members": ["obj:box", "obj:ring"],                       # sorted
 "containment_edges": ["obj:ring·in·obj:box"],              # log order
 "distinct_edges": ["obj:box·distinct_from·obj:ring"],      # log order
 "same_as": [{"assertion_id": "a:9", "edge": "obj:ring·same_as·obj:box",
              "merge_event_id": null}]}                     # every canon same_as row inside, log order
```

- `merge_event_id` comes from the row's `caused_by`. It is `None` for a raw row.
- Entries are sorted by `canonical_id`. The read writes nothing and is canon
  only (identity is canon's).
- The host decides which `same_as` to retract. The engine does not choose a cut.
- Not part of `fidelity_audit` (a frame-scoped read would then carry canon
  identity into a `knows:` audit).

**Surface.**
- World mirror: `World.identity_conflicts(asserted_as_of=None)`.
- Porcelain: additive `p.identity_conflicts() -> list[dict]` (encoded).
- MCP: `identity_conflicts` joins `V1_READS`, making 40 tools. Read-only and
  idempotent annotations.

**Oracle:**
- 4a. The probe world:
  - `obj:ring in obj:box`, then `reject(box, ring)`, then a raw canon `same_as`,
    appended with the ingestor role so the test is independent of batch B.
  - Result: one entry, with both edge lists populated and `same_as[0].merge_event_id is None`.
- 4b. Retract that `same_as`. The result is `[]`.
- 4c. A clean world, and `examples/anchor/anchor.world`, give `[]`.
- 4d. The head is unchanged by the call.

**Hosts see.** One new read. All 52 construct worlds return `[]` (no closure
holds an internal hard-veto edge).

**Byte-identical.** Everything else.

## §5 `open_conflicts` is computed on read, frame-scoped and as-of

**Rule.**
- `TruthMaintenance.open_conflicts(frame=CANON, valid_as_of=None, asserted_as_of=None)`
  derives its keys from the rows visible in `frame`.
  - A key is `(resolve(entity), fold key)`. The containment family is reported as
    `in`, as today.
  - It skips `a:`/`attr:` subjects and set-valued attributes, as today, and folds
    only keys with at least two visible rows (a conflict needs two).
  - It reports each conflicted fold as `Conflict(entity, attribute, frame, kind, assertion_ids)`.
    `kind` is `constitutive_contradiction` when the winner is CONSTITUTIVE, else
    `cross_source`, as today. `frame` is the requested string.
  - Results are sorted by `(entity, attribute)`, and the read writes nothing.
- **Invariant:** a key is listed iff `state(key, frame, as_of).status == "conflicted"`.
- `fidelity_audit(frame, as_of)` passes both through. No `truth.scan()` is
  needed first.
- `scan()` stays as a below-porcelain all-frames read: the union over every
  stored frame name with a visible row (r1 named them canonically through §7;
  r2 has no §7). It writes nothing and returns the list.
- **The `sidecar_conflicts` table is retired.**
  - `TruthMaintenance` stops creating, filling and reading it.
  - Existing files keep an inert copy. The engine runs no DDL against a host's
    file beyond `CREATE IF NOT EXISTS`, and a dump→build drops it naturally.

**Location.**
- `tmaint.py` `_SCHEMA`/`__init__` (24–33, 83), `scan` (85–127) and
  `open_conflicts` (129–134). The module docstring changes too.
- `__init__.py` `fidelity_audit` (285–337; conflicts at 317–321) and its
  docstring.
- `porcelain.py` `fidelity_audit` docstring (225–235).
- In-repo callers that read the table after `scan()` switch to `scan()`'s return
  value (same all-frames content): `evals/harness/audit.py:80`,
  `evals/harness/run_micro_eval.py:206`, `examples/anchor/tour.py:81`,
  `tests/test_ingest_v2.py:238,263`.

**Oracle:**
- 5a. Without `truth.scan()`: two kind rows in `knows:person:marn` give
  `fidelity_audit(frame="knows:person:marn")["open_conflicts"]` length 1. Today 0.
- 5b. After a `scan()`, `fidelity_audit(frame="canon")["open_conflicts"] == []`.
  Today it lists the `knows:` conflict, naming entity, frame and ids.
- 5c. Retract one side: the entry disappears. Today it is stale (still 1).
- 5d. `kind book @1`, `kind forgery @10`:
  - `as_of=5` gives `[]`, and `as_of=15` gives one entry.
  - Today both give 1.
- 5e. `examples/anchor/anchor.world`: `open_conflicts(frame="canon")` equals its 8
  stored rows field for field. Verified with today's `scan()` on a copy.
- 5f. `scan()` and `fidelity_audit()` leave the head and every sidecar table
  unchanged.

**Hosts see.**
- `fidelity_audit()["open_conflicts"]` is populated without the
  below-porcelain call, scoped to the asked frame, honest about `as_of`, and
  never stale.
- Construct never called `truth.scan()`, so its 52 worlds hold 0 stored
  conflict rows and its audits show none. Deriving them on copies under today's
  fold rules finds conflicts in 40 of the 52 worlds: 571 in canon, 189 in
  `knows:` frames and 109 in named frames.

**Byte-identical.** A canon world audited at head right after a `scan()` (5e).

**Existing logs.** Nothing to migrate: the table was a rebuildable derived layer.

## §6 `snapshot` existence follows perspective

**Rule.** `Porcelain._is_known(entity, frame)` (380). An id is known in `frame`
iff a visible subject row of its closure exists in `frame` **or in canon**.
- Canon is the existence authority. HD 003: "identity/existence is a CANON
  question; only the answer is knowledge-scoped."
- A frame may add entities that canon lacks: a belief, a plot arc.
- `snapshot` (390–406) passes its `frame`.
- **(r2, pre-review MINOR) One query.** `_is_known` reads the closure's rows
  with one `visible(entity_in=)` call, as the base engine did, and keeps those
  whose frame is `frame` or `canon`, in Python. r1 passed `frame=` to the
  query, and SQLite then picked the frame index over the entity index. On the
  pre-review's 100k-row perf world: 8.8 ms per id under r1 against 0.35 on the
  base engine and 0.34 under r2; a 200-id snapshot in a `knows:` frame takes
  1.85 s under r1, 0.11 s on base and under r2. Answers are identical to r1's:
  624 (id, frame) pairs on that world, and 101,422 (id, stored frame) pairs on
  copies of construct's 52 worlds ("r2: review resolutions", Checks).

**Why not "requested frame only".** `knows:` frames are sparse by design (ADOPTION
trap 2). Construct snapshots an NPC in the NPC's own frame for its character
sheet (`turnloop.py` ~2581, ~5269; `session.py` ~851). A strict rule would turn
those sheets into error payloads.

**Oracle:**
- 6a. `obj:ledger` exists only in `plot:twist`. `snapshot("obj:ledger", frame="canon")`
  returns `{"error": ..., "bad": ["obj:ledger"]}`, exactly like `obj:nothing`.
  Today it succeeds with empty facts.
- 6b. `snapshot("obj:ledger", frame="plot:twist")` succeeds.
- 6c. `snapshot("obj:ledger", frame="knows:person:marn")` errors.
- 6d. A canon entity with no rows in `knows:person:marn` still snapshots in that
  frame, with empty facts (unchanged).
- 6e (r2). Over ids known in canon, in one frame only, merged, or nowhere, and
  frames `canon`, `plot:`, two `knows:` and a merged member's `knows:`,
  `_is_known(e, F)` equals "a row in F or in canon" read per frame, and makes
  exactly one `visible(entity_in=)` call, without `frame=`.

**Hosts see.**
- A canon (or other-frame) snapshot whose scope contains an id that lives only in
  non-canon frames now errors.
- Construct's worlds hold 2,535 such ids. Most are host-control namespaces
  (`pin:`, `event:`, `arch:`, `clock:`, `beat:`, `pillar:`, `arc:`), plus 21
  `obj:`, 9 `place:` and 2 `fact:`.
- `_snap_or_empty` and the session cold open recover per id. Two construct paths
  have no fallback and would return empty: `Session.establishing_lines`
  (`session.py` ~1022) and `game.knows_inspect` (~2002). This goes in the ship
  notice.

**Byte-identical.** Every snapshot of a canon-known id, in any frame.

## §7 `knows:` frames follow merges (decision 2): withdrawn from this build

**r2: withdrawn from this build pending Kabe's gate g3bf5da (consult ccab80f).**
r1's build of this section is kept on `hold/frame-scoped-identity-v1-r1` (its
commit `cbbb93f`; head `c4c86b0`), and r2 carries none of it. In this build
every frame reads only the rows stored under its own name, as on the base
engine, and `who_knows` reports stored names.

Why it is held. An internal pre-review measured on copies of construct's live
worlds that following merges leaks knowledge, because automatic `reconcile`
merges on garbage aliases had fused characters:
- **"World B"** (`world B file 1`): the merged closure
  {tamsin, dorn, dorn_vale, ash_apprentice} includes the protagonist. Under r1
  the protagonist's frame serves 58 rows instead of its own 19, including the 4
  clues seeded into NPC Dorn's frame (3 genuine, 1 red herring).
- **"World C"** (`world C file 1` and 3 more):
  Lena's 2 clues and Opal's 1 become readable through the frames of mae,
  nell, ida and rue, merged on the alias "singing into a wind that had
  tried and failed to quiet them".
- **"World A"** (`world A file 1`):
  `person:anselm_varo` (the dock-guild president) was merged with
  `person:corin`, a fragment of the protagonist, on the alias "received corin
  in the guild hall"; their knowledge frames would fuse.
- **Retraction alone does not repair.** `reconcile()` re-merges at once (2
  merges for dorn, 5 for ida). A durable repair retracts the anchor alias
  rows too, or retracts and rejects every pair.
- **The write path** (pre-review MINOR): construct's frame-clearing loop scans
  `facts(knows:X)` and retracts what it finds; under r1 it retracts a merged
  partner's rows too (72 on `emberroad2` for `person:caldus`), and `facts()`
  does not say which stored frame a row came from.

Two outside model views and construct agreed that a frame reads only its own
stored name by default, and that widening one must be an explicit, logged
choice. That is the gate's point P1, which withdraws this section; P2–P4 (an
explicit, reversible widening event; identity's root causes fixed first;
row-level frame provenance before any cross-frame read ships) are Kabe's to
accept. If he rejects P1, §7 is restored from the hold branch. The three bad
live merges and their repair facts go to construct's repair list (its gate
g698a80), not to this build. r1's text follows, unchanged, for reference.

**Rule.**
- **The observer frame.** For a frame `knows:<s>` whose suffix `<s>` is in the
  gate's id grammar, a read covers the stored frames `knows:<m>` for every `m` in
  `closure(<s>)`.
  - The closure is canon (§2) at the log head: the engine-wide identity
    limitation; see Non-goals.
  - Every other frame name covers only itself: `canon`, `plot:*`, `public`, and
    a non-id suffix such as `knows:marn`.
- **Canonical frame name.** `knows:<resolve(<s>)>` is the surviving name, the
  same id that `entities()` reports.
- **One choke point.**
  - `PatternBuffer.visible(frame=F)` expands `F` through an injected resolver:
    `set_frame_resolver(fn)`, defaulting to "a frame names only itself", and
    wired by `World`.
  - One stored name uses `a.frame = ?`. Several use `a.frame IN (...)`, which is
    indexed by `ix_assertions_frame`.
  - The registry supplies `frames_read(frame) -> list[str]` and
    `canonical_frame(frame) -> str`. `Indexes` canonicalizes through its own
    resolver, so it needs no new setter.
  - No recursion: the closure reads `frame=canon`, which never consults
    identity.
  - No cache of its own. It rides the closure cache when `perf/read-caches`
    lands.
- **Writes are not rewritten.** Rows keep the frame string their author wrote,
  and `Receipt.frames` stays an echo. A merge's effect on frames is therefore
  reversible by retracting the `same_as`.

| Read | Observer frame behaviour |
|---|---|
| `state`, `state_union`, `snapshot`, `materialize`, `entities`, `facts`, `where`, `aggregate`, `locate`/`contents`/`route`/`neighborhood`/`salience`/`events`/`in_transit` (any frame-taking read) | Reads every stored name of the observer frame, through `visible()` |
| `snapshot()["frame"]`, `fidelity_audit()["frame"]`, `open_conflicts` entries' `frame` | Echo the caller's string, unchanged |
| `entities(F)` / `facts(F)` | One roster or scan over all stored names; ids identity-resolved as today |
| `frame_diff(a, b)` | Each side reads its observer frame. `a` and `b` naming one observer gives `[]` |
| `who_knows` | Candidate `knows:` frames are canonicalized, then deduplicated, then folded once each. **Returns canonical names** |
| `confidence(frame=[...])` | The list is deduplicated by canonical name *before* the single-frame reduction, so two names of one observer reduce to the `str` path byte for byte |
| `name_collisions`, `correlations`, `correlation_conflicts`, `open_conflicts` | Read the observer frame |
| `scan()` | Iterates canonical frame names |
| The gate's cycle check (`locate` in the item's frame) | Walks the observer frame |
| `ingest_structured(frame=)`, item `frame` | Stored as written |

**Location.**
- `buffer.py` `visible` frame clause (485–487) and the new setter.
- `identity.py`: the two new methods.
- `__init__.py` wiring (78–83).
- `indexes.py` `who_knows` (1159–1173) and `_confidence_multiframe` dedup
  (648–655).
- `tmaint.py` `scan`.

**Oracle.** `person:dan` is first-seen, `p.merge(dan, daniel)`, and
`obj:key · in · place:shed @1` was written to `knows:person:daniel`:
- 7a. `state(obj:key, "in", frame="knows:person:dan")` is `known` (today
  `unknown`). It is also known via `"knows:person:daniel"`.
- 7b. `who_knows(obj:key, "in") == ["knows:person:dan"]` (today
  `["knows:person:daniel"]`).
- 7c. `entities("knows:person:dan") == ["obj:key"]` (today `[]`). `facts` and
  `snapshot` likewise.
- 7d. `frame_diff("knows:person:dan", "knows:person:daniel", ["obj:key"]) == []`.
- 7e. `confidence(..., frame=["knows:person:dan", "knows:person:daniel"])` equals
  `confidence(..., frame="knows:person:dan")`.
- 7f. With `obj:key · in · place:barn @5` in `knows:person:dan`, either name
  serves `place:barn`: one observer, one fold.
- 7g. In the 7a world, without 7f's row, retract the `same_as`. The frames
  split again: `state(..., "knows:person:dan")` is `unknown` and `who_knows`
  gives `["knows:person:daniel"]`.
- 7h. `knows:dan` (a non-id suffix) never resolves.
- 7i. Stored rows keep `frame == "knows:person:daniel"`.

**Hosts see.** On construct:
- 11 of 52 worlds hold 15 observer frames with at least two stored names, which
  now read as one.
- 13 worlds hold 34 stored names whose canonical name differs, so `who_knows`
  reports the canonical one. Examples: `knows:person:caldus` becomes
  `knows:person:brother_caldus`, and `knows:person:jonas` becomes
  `knows:person:jonas_vale`.
- **Two of those observer frames sit on bad canon merges**, so the people
  wrongly merged now share one knowledge frame:
  - In `world C files`, `reconcile` merged
    `ida/lena/mae/nell/opal/rue` on the garbage alias "singing into
    a wind that had tried and failed to quiet them".
  - In `world B file 1`, it merged `tamsin/dorn/ash_apprentice` on
    "my apprentice"/"his apprentice".
  - Today the bad merge corrupts their canon facts. After, it also fuses their
    knowledge frames. Retracting those `same_as` rows splits both again, since
    nothing was rewritten. See Q2.

**Byte-identical.** Any world where no `knows:<id>` suffix belongs to a closure
of two or more members.

## §8 Rider: `retype(absorb=)` refuses a `to_kind` that contradicts the target

Identity audit P2-7(b). It sits in `retype`, which §2 already edits, and it
only tightens.

**Rule.** In Case B, after the slip-signature check (so a non-slip still
receipts `vetoed_not_a_slip`): if `to_kind`, stripped and lowercased, is not
among the target's folded kind values, return
`vetoed_kind_mismatch` with reason `to_kind_not_target_kind`, `retracted: []`,
and write nothing. Today `to_kind` is silently ignored.

**Location.** `identity.py` `retype` Case B (882–907).

**Oracle:**
- `retype(person:harth, "teapot", "slip", absorb=place:harth)` returns
  `vetoed_kind_mismatch` with the head unchanged. Today it returns `merged`, and
  the kind stays `place`.
- `retype(..., "place", absorb=place:harth)` returns `merged` (unchanged).

**Hosts see.** Nothing: construct passes the target's own kind (`game.py`
~494–500).

## Non-goals

- **Historical identity.** Closures are computed at the log head even under
  `asserted_as_of`. This is the engine-wide known limitation (`indexes.py`
  167–173, 544–547). (r1: observer frames followed it, so a fold never mixed
  two identity epochs; §7 is withdrawn in r2.)
- **Non-id `knows:` suffixes** (`knows:lysa`, `knows:person_lysa`) are opaque
  names. They are never resolved, and never unified with `knows:person:lysa`
  (r2: with §7 withdrawn, every frame name is opaque).
  18 of 52 construct worlds carry such a pair. The gate warning for them is
  surfaces trap 1, and ADOPTION already says MUST use the full id.
- **Write-time frame canonicalization.** Excluded; see §7 (withdrawn in r2).
- **Wider reference resolution in `knows:` frames.** No frame-list `by_alias`, no
  canon fallback, no change to `ask()`'s canon reference resolution (Q5).
- **A `frame=` parameter on `correlate()`.** A perspectival correlation stays a
  raw `aka` row in its frame.
- **Meta side-rows of a non-canon row.** `source`, `canonicalized_from`,
  `learned_at_wallclock` and `source_valid_from` are written in canon:
  `facts("canon", include_meta=True)` lists `a:3 · source · doc:diary` for a row
  that exists only in `knows:`. These are not identity, and are left as an
  observation for a later batch.
- **Accrual promotion keys** (raw entity, raw frame) and `correlations()`'
  ordering scan stay as they are.
- **Identity audit P2-5** (a set-valued attribute counted as a durable
  contradiction). It reproduces, but the fix *loosens* auto-merge. That is a
  precision-over-recall call for the founder, not bundled here.
- **Work owned elsewhere.**
  - Batch B: raw canon `same_as` through the guarded merge, `_normalize_item`
    (including null frames, which §1 evaluates through), and receipts for
    side rows.
  - Batch D: when refer learns, and `by_alias` normalization.
  - `perf/read-caches`.
  - The audit's P2 items: one merge-veto table (P2-1) and a single `bind()`
    replacing the late-bound setters (P2-8). (r1's §7 added one more setter;
    r2 adds none.)
- **The extraction prompt** beyond one sentence. r1 left it unchanged; r2
  changes the ALIASES bullet's `same_as` sentence so the extractor emits it in
  canon (§1). The gate still enforces §1 with receipts.

## Migration and notice

**No log rewrite and no schema migration.** Existing rows are read like this:

| Row already in a log | Read after this spec |
|---|---|
| `same_as` / `maybe_same_as` / `distinct_from` outside canon | Inert: no identity read consults it. Raw scans still list it |
| `name` / `alias` outside canon | Read in its own frame only |
| Canon `alias` / `maybe_same_as` that the gate wrote for a non-canon item | Stays canon; indistinguishable from authored canon rows |
| `knows:<id>` rows | Read under their own stored frame name, as before (r2: §7 withdrawn); nothing rewritten |
| `sidecar_conflicts` | Inert; never read |

**Measured on construct** (52 world files, read-only, 2026-10-08):

| Measure | Count |
|---|---|
| Non-canon `alias` rows | 1,140 in 23 worlds (871 duplicate a canon row for the same entity) |
| Non-canon `name` rows | 75 in 8 worlds (44 `knows:`, 31 `proposed:`) |
| Non-canon `same_as` rows | 5: one per `thedeep*` world, `person:chen same_as person:elias_chen` in `knows:person:chen` |
| Non-canon `maybe_same_as` / `distinct_from`; `aka` anywhere | 0 / 0; 0 |
| Canon `by_alias` texts whose answer changes | 23 (4 ambiguous→unique, 4 non-canon-only) |
| Closures re-elected by canon-only first-seen | 0 |
| Observer frames with at least two stored names / stored names renamed (§7 only; not in this build) | 15 in 11 worlds / 34 in 13 worlds |
| Ids carried only by non-canon frames (§6) | 2,535 |
| `sidecar_conflicts` rows; closures with an internal hard-veto edge | 0; 0 |

**The `thedeep` case.**
- Canon will no longer merge `person:chen` with `person:elias_chen`.
- Canon already holds an open proposal between them (`a:947 maybe_same_as`). A
  `p.confirm("person:chen", "person:elias_chen")` restores the merge, through
  the guarded path. The call is construct's to make.
- Read-only query listing every such row in any world:
  `SELECT id, entity, attribute, value, frame FROM assertions WHERE attribute IN ('same_as','maybe_same_as','distinct_from') AND frame != 'canon'`,
  minus rows targeted by a `retracts` row.

**Ship notice to construct**, after build and GREEN. It covers:
- the receipt reasons (§1): `identity_edge_outside_canon` for a non-canon
  `maybe_same_as`/`distinct_from`, and `same_as_not_canon` (B's code, with its
  `detail`) for an item's non-canon `same_as` key as for a raw one (r2);
- the extraction prompt's one-sentence change (§1, r2);
- the canon `refer`/`reconcile` deltas (§2), and that `refer(...,
  frame="knows:person:alice")` no longer falls back to canon aliases (r1
  documented it; construct always passes canon, so it sees no change);
- `correlate`/`reject` outcomes and the decline codes `correlated` and
  `distinct_group` (§3);
- the new `identity_conflicts()` read (§4);
- that `fidelity_audit` no longer needs a scan (§5), and that `open_conflicts`
  now lists what `state()` calls conflicted: 520 conflicts in 38 of the 52
  world copies, where the stored table held 0 (r2). Construct's
  `scripts/fidelity_audit.py` reads `summary.open_conflicts` into its score;
  its play path reads only `name_collisions`;
- (r2) that `name_collisions` statuses can move, and construct's build acts on
  them (it rejects cross-kind homonyms and merges `alias_not_specific` pairs).
  A pair whose correlation groups a canon `distinct_from` separates is
  `hard_blocked` with reason `distinct_group` (§3(c)), and only canon rows
  block a pair (§2). Measured on the copies: "the open ledger" (×2) is no
  longer blocked, since its `held_by` row is in `proposed:main`, not canon;
  "saint orven's step" moves to `typing_slip`;
- the two snapshot paths without a fallback (§6);
- the `thedeep` confirm.

r2: nothing about observer frames (§7 is held). The three bad live merges and
the durable-repair facts (§7) go to construct's repair list under its gate
g698a80, not to this build.

**Docs, in the build commit.**
- **ADOPTION.**
  - Identity is canon's: the skip reason, frame-scoped aliases, `by_alias`/`refer`
    take a frame.
  - (r1: observer frames, `who_knows` returning canonical names. Out in r2,
    with §7.)
  - The snapshot existence rule.
  - Drop the `open_conflicts` CAUTION (358–363).
  - Document `identity_conflicts`, `conflict_already_correlated` and
    `vetoed_kind_mismatch`.
- **WHITEPAPER.**
  - §6: one sentence: identity is canon's in every frame (r1's observer-frame
    paragraph is out in r2, with §7).
  - §11 and §25.2: identity is canon's; `aka` soft-blocks auto-merge;
    `identity_conflicts`.
  - §25.4: `open_conflicts` is computed.
  - The next free amendment row: A21 (r2; main holds A18 and A19, and B r2
    adds A20).
- **LEXICON.**
  - New terms: *canon identity edge*, *correlation group*,
    `identity_conflicts()` (r1's *observer frame* / *canonical frame name* is
    out in r2, with §7).
  - Updated entries: `Frame`, `distinct_from`, `aka`, `fidelity_audit()` (r1's
    `who_knows()` update is out in r2).
- **MCP-WRAPPER** counts: 40 tools.
- `specs/STATUS.md` (r2: at the merge, with the README test count, as for
  batches A and B).

## Tests

- One test per oracle (1a–1i, 2a–2j, 3a–3h, 4a–4d, 5a–5f, 6a–6e, §8) in a new
  `tests/test_frame_scoped_identity.py` (r2: 7a–7i are out with §7). That file
  also holds the property test: over small generated worlds,
  `open_conflicts(F, as_of)` lists exactly the keys whose `state(...)` is
  `conflicted`. (r1's second one, every frame read over `knows:x` equal to the
  same over `knows:y` after a merge, is out with §7.)
- Updated in the same commit, each citing the audit finding:
  - `tests/test_mcp_wrapper.py` (39 → 40 tools, plus an `identity_conflicts`
    entry);
  - `tests/test_ingest_v2.py` (`scan()` return value);
  - any `correlation_conflicts` equality that the additive `aka_path` touches.
- The full suite must stay green (577 at `212754f`).

## Open questions for pb (each with the default this draft takes)

- **Q1.** Does decision 1 extend to `maybe_same_as` and `distinct_from`? Default:
  yes (§1 says why). The alternative is to admit them, inert.
- **Q2.** Decision 2 fuses knowledge frames along bad merges (2 observer frames
  in construct today). Default: ship as decided, flag it in the notice, and let
  hosts repair by retraction. `identity_conflicts` cannot see a soft-bad merge.
  *r2: moot here. §7 is withdrawn from this build; the question is Kabe's gate
  g3bf5da, and retraction alone was measured not to repair (§7).*
- **Q3.** The frame expansion sits at `visible()` (one choke point; the audit's
  "rule missing on a sibling path" theme), not at about 30 caller sites.
  Default: `visible()`. This is pbr's call on layering. *r2: moot while §7 is
  withdrawn.*
- **Q4.** Snapshot existence is the requested frame plus canon, not the strict
  requested frame only. Default as written (§6).
- **Q5.** `ask(frame=knows:X)` keeps resolving references against canon
  (HD 003), so X's private alias doesn't resolve there. Default: unchanged, and
  revisit with batch D/E.

## Build notes for pbr (r1: gated implementation on `impl/frame-scoped-identity-v1`, 739 green)

- **One rule, two skip codes.** A raw `same_as` outside canon gets
  GATE-AUTHORITY-V1's `same_as_not_canon`. The side-key form gets this spec's
  `identity_edge_outside_canon`. pb recommends one code; please rule on which.
  *(Ruled: `same_as_not_canon` for both; built in r2.)*
- **Counts measured on this base are lower than the spec's.** The construct
  counts in this spec predate FOLD-CORRECTNESS-V1 and construct's 21:51 and
  22:15 rebuilds. Measured on this base:
  - 520 canon / 199 `knows:` / 102 named-frame conflicts across 40 worlds;
  - 17 `by_alias` texts;
  - 13 merged observers (§7, withdrawn in r2).

  Oracle 5e pins a one-id difference that batch A's evidence rank causes.
- **Reconciling D on top of C** was simulated, with no commits (776 green):
  - `by_alias`, `by_learned_alias` and `_vocabulary_matches` gain a
    `frame=CANON` parameter;
  - `refer` passes `frame` into tiers 1a and 1d;
  - D's three strict xfails drop their marker.

## r2: review resolutions (2026-10-09)

r1 went to pbr and to an internal pre-review. pbr returned **RED on one point**
(§1's receipt codes) and ruled it. The pre-review measured on copies of
construct's live worlds that §7 leaks knowledge (MAJOR), and found two MINORs
and a NIT. Meanwhile batch B r2 replaced B r1 under this branch. r2 resolves
each as below.

**Rebase onto B r2.** The branch now starts at `dddbb64` (B r2 on main
`950e351`, which holds batch A and GATE-INVERSE-ALIAS-V1). r1's commits were
replayed in order without `cbbb93f` (§7), each keeping its message; r1's head
stays on `hold/frame-scoped-identity-v1-r1` (`c4c86b0`). Conflicts:
- `ingest.py`: §1(a)'s check sits at the head of B r2's step 9, after the
  declaration plan and step 8's id-shaped check, before identity resolution.
  B r2's thirteen-step numbering, `_gate_number`, mechanism set and first-use
  declaration plan are untouched. The `aliases` and `same_as` side rows (step
  12) use B r2's `identity_subject`, the inverse swap's original subject.
- `tests/test_frame_scoped_identity.py`: §8's tests followed §7's, which are not
  carried.
- Docs: ADOPTION's skip block is B r2's, with §1's code added; LEXICON's
  observer-frame row came with §7 and is not carried; the whitepaper's
  amendment row follows A20 (renumbered below); r1's `specs/STATUS.md` edit is
  dropped, left for the merge as B does.

**pbr RED (§1): one receipt for a non-canon `same_as`.** pbr's ruling (b):
`same_as_not_canon`, B's public contract, for both a raw and a side-key
non-canon `same_as`; `identity_edge_outside_canon` only for a non-canon
`maybe_same_as` or `distinct_from`. r1's build already gave a raw one B's
code; r2 gives the side key the same code and `detail` (`{field: "frame",
value: <frame>}`), and §1's prose, ADOPTION, LEXICON and the whitepaper row say
so. Oracles 1b and 1f changed; 1i is new.

**§7 withdrawn (pre-review MAJOR).** Following merges leaks knowledge on live
worlds (the facts are under §7). Kabe's gate g3bf5da (consult ccab80f)
decides; its P1 withdraws §7. r2 carries none of it: no frame resolver in
`visible()`, no `frames_read`/`canonical_frame`/`observer_suffix`; `who_knows`,
`confidence(frame=[...])`, `frame_diff` and `scan()` read exact stored frames
as on the base engine; no §7 test, docstring, LEXICON term, ADOPTION rule or
whitepaper paragraph remains. The remaining tests already read exact frames.
Q2 points at the gate. The bad live merges and their durable repair (retract
the anchor aliases too, or retract and reject every pair) go to construct's
repair list under its gate g698a80, not to this build.

**Pre-review MINOR: §6's existence check was slow.** Fixed as the pre-review
measured it: one `visible(entity_in=)` call, filtered to `{frame, canon}` in
Python. Numbers in §6; oracle 6e pins the single call and the answers.

**Pre-review MINOR: a host's scan-then-retract loop.** Moot once §7 is out. A
frame scan (`facts(knows:X)`) returns only rows stored under `knows:X`, so a
host's frame-clearing loop retracts nothing of a merged partner's: on a fresh
`emberroad2` copy, construct's loop for `person:caldus` retracts its own 25
rows and 0 of `knows:person:brother_caldus`'s (r1 with §7: 97, 72 of them the
protagonist's). The row-level frame provenance the pre-review asked for
belongs to the gate's P4, before any cross-frame read ships.

**Pre-review NIT (§3(c)): the group-level `distinct_from`.** The auto-merger
read only a direct correlation, so `a~b`, `reject(b, x)` and a shared name let
`reconcile` merge a with x, which `correlate(a, x)` would veto. `correlate`'s
group check, now one helper, is read by `_mergeable`, `reconcile`'s proposal
guard, `adjudicate_deferred`, `_decline_context` (code `distinct_group`) and
`name_collisions` (§3(c); oracles 3g, 3h).

**The extraction prompt (for pbr).** One sentence of the full rules' ALIASES
bullet changes so the extractor emits `same_as` on the entity's canon row (§1;
oracle 1h). It changes what the model is asked, so its wording is pbr's to
review.

**Renumbering.** The whitepaper's §25.9 row is **A21** (main holds A18,
FOLD-CORRECTNESS-V1, and A19, GATE-INVERSE-ALIAS-V1; B r2 adds A20), and each
whitepaper reference this spec added reads A21. `specs/STATUS.md` and the
README test count follow the merge, as for A18–A20. The MCP count, which
`tests/test_mcp_wrapper.py` pins, stays 40 where the docs state it (ADOPTION and
the README's MCP road item).

**The notice** gains the side-key receipt, the prompt sentence,
`distinct_group`, and `refer(..., frame="knows:person:alice")` no longer
falling back to canon aliases (oracle 2j pins it; construct always passes
canon). It loses §7's canonical names and fused frames.

**Checks.**
- **Suite.** The full suite at r2's head: 779 collected, 775 passed, 4 skipped
  (B r2: 730, 727 and 3). The fourth skip is the opt-in 2i corpus check; run
  over copies of construct's 52 worlds, it passes (0 re-elections). Every
  rebased commit passes the full suite on its own. Of r2's eight new or
  changed oracle tests (1b, 1f, 1h, 1i, 2j, 3g, 3h, 6e), seven fail on the
  rebased pre-r2 code; 2j passes there, since it pins §2 behaviour r1 already
  had, for the notice.
- **Construct.** Fresh copies of the 52 world files, read through the
  pre-review's probe (each stored frame's roster and snapshot, NPC character
  sheets, `knows_inspect`, the establishing and situation sets, `who_knows` on
  every key a `knows:` frame touches, `by_alias` on every name and alias text,
  proposals, `typing_conflicts`, `fidelity_audit`, `identity_conflicts`), base
  `dddbb64` against r2:
  - 0 snapshots flip between ok and error.
  - "World B": `knows:person:ash_apprentice` serves its own 19
    rows (base 19; r1 with §7: 58, 39 of them from merged frames).
  - `emberroad2`'s frame-clearing loop for `person:caldus` retracts 0 partner
    rows (above).
  - `thedeep*` (5 files): `person:chen` and `person:elias_chen` unmerge (their
    only `same_as` is the `knows:`-frame row §2 makes inert; canon holds a
    proposal `confirm` promotes, "Migration and notice"). That accounts for all
    5 closure changes, all 15 changed frame snapshots, all 10 `who_knows`
    changes (`person:chen`'s alias and kind known by 2 frames instead of 5),
    and those files' `by_alias`, proposal, establishing, situation and
    collision changes. No other frame read changes anywhere.
  - `by_alias`, outside `thedeep`: two texts stop resolving in canon because
    only a `knows:` frame carries them (§2): "mara_thist"
    (`emberroad.preset.play`, in `knows:person:mara_thist`) and "ash
    apprentice" (`world B file 1`, an alias of
    `person:dorn_vale` in `knows:person:ash_apprentice`).
  - `typing_conflicts` (26 files): the slip signature reads canon only (§2).
    No pair is lost; 7 are gained, slips a non-canon row had masked ("saint
    orven's step" twice, "san pedro" in the 5 `thedeep` files); 92 pairs'
    `asymmetry` counts, and 6 `artifact_edges` lists, now count canon rows.
  - `name_collisions`, outside `thedeep`: "the open ledger"
    (`bodycase.critic_genreshift` ×2) was `hard_blocked` by a `held_by` row in
    `proposed:main` and is now `unlinked` (live, 2g's rule); "saint orven's
    step" (`emberroad.preset.play`) moves from `auto_declined`/`kind_conflict`
    to `typing_slip`.
  - `open_conflicts` in canon: 0 → 520, in 38 worlds (§5: computed on read;
    construct never ran `scan()`). `identity_conflicts()` is `[]` in all 52.
- **r2's code against the rebased pre-r2 code**, on the same copies:
  `_is_known` gives identical answers on 101,422 (id, stored frame) pairs (all
  2,542 ids that live only in non-canon frames × every stored frame, plus a
  seeded sample), in 25 s against 98 s. `proposals()`,
  `fidelity_audit()["name_collisions"]` and `reconcile()` give identical
  results (no construct world holds an `aka` row, so the group check is
  `distinct_block` again), in the same time (`reconcile` 200.0 s against
  199.7 s summed over the 52; base 286 s).
