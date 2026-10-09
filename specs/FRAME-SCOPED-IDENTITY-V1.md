# FRAME-SCOPED-IDENTITY-V1: identity is canon's, description is perspectival, an observer follows its identity

**Status:** DRAFT r1 (2026-10-08). Batch C of `docs/AUDIT-2026-10.md` (P1 #1, #7,
#8, the snapshot existence leak, the `identity_conflicts()` read). Not yet
reviewed by pbr. Founder decisions 1 and 2 (2026-10-08, below) are binding
inputs. Every case below reproduced on `212754f` (`polish/audit-2026-10`) before
it was written down. Host blast radius measured read-only on construct's 52
world files (`/home/k/Newproject/worlds/*.world`). Line numbers are at `212754f`.

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
  canon closure: an **observer frame**.

A perspectival identity *belief* ("Alice thinks the masked man is Bob") is an
`aka` row in Alice's frame, read by `correlations`/`state_union(frame=...)` as
AKA-CORRELATION-V1 already allows. It is never a `same_as`.

## §1 Identity writes carry the item's frame

**Rule.**
- **(a) Canon identity edges are canon-only.** An item whose canonicalized
  attribute is `same_as`, `maybe_same_as` or `distinct_from`, with an effective
  frame other than `canon`, is skipped with reason `identity_edge_outside_canon`.
  Nothing is appended for it.
- **(b) The side-channel `same_as` key** on a non-canon item is skipped with the
  same reason, as `SkipRecord(entity, "same_as", <value>, "identity_edge_outside_canon")`.
  The item's main row is admitted as usual. No `maybe_same_as` is written.
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
`item.get("frame", CANON)` after the call-level `frame=` default.
- Check (a) runs on the raw ids, after the authority gate (which still raises
  first) and after the malformed-id gate, and before identity resolution. So a
  generated `same_as` aimed at `knows:` still raises, and a malformed one still
  receipts `malformed_id`.
- Check (b) runs where the side key is handled today, after its own
  malformed-id check. It receipts the resolved entity, as that check does.
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
malformed-id gate (839–848) and resolution (849–852). The `aliases` loop
(971–972) and the `same_as` key (982–992) change. `identity.py` `add_alias`
(103) gains `frame: str = CANON`. In `refer.py`, the call's frame is threaded
through `_resolve_tier2` (225) into `_accrue_alias` (77–95). The reason string
joins the skip vocabulary in ADOPTION.

**Oracle** (Alice = `knows:person:alice`):
- 1a. Item `{person:hooded · kind · person, frame: Alice, aliases: ["the traitor"]}`.
  - Today the alias row's frame is `canon`.
  - After, it is `knows:person:alice`.
- 1b. The same item with `same_as: "person:bob"`.
  - Today it writes a canon `maybe_same_as`, and canon `proposals()` lists
    `(person:hooded, person:bob)`.
  - After: `skipped == [{person:hooded, same_as, person:bob, identity_edge_outside_canon}]`,
    no `maybe_same_as` row, and `proposals() == []`.
- 1c. A raw `person:stranger · same_as · person:bob` in Alice's frame.
  - Today it is appended, and the canon fold of `person:bob · occupation` serves
    the stranger's `"spy"`.
  - After it is skipped, and the canon fold is unknown.
- 1d. Raw `maybe_same_as` and `distinct_from` rows in `knows:` and in `plot:` are
  skipped with the same reason.
- 1e. A raw `aka` in Alice's frame is admitted in Alice's frame (unchanged).
- 1f. `ingest_structured([...non-canon same_as...], atomic=True, classify="rules")`
  raises `AtomicAbort(cause="gate_skip")` carrying the receipt, and nothing is
  visible.
- 1g. `refer("the traitor", frame=Alice)` with a tier-2 hit writes its alias row
  in Alice's frame.

**Hosts see.**
- `Receipt.skipped` gains `identity_edge_outside_canon` entries.
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
  reads `alias`/`name` rows in that frame only (through §7 when the frame is an
  observer frame). There is no canon fallback for a non-canon frame: frames never
  inherit canon in a read.
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

**Hosts see.**
- Construct calls `reject()` on cross-kind collision pairs (`game.py` ~513–526).
  A correlated pair now returns `conflict_already_correlated` instead of writing
  a `distinct_from`. Construct ignores the outcome.
- `auto_decline.code` gains the value `correlated`. Construct's residue triage
  (`game.py` ~281–303) rejects only `containment`/`relating_edge` and leaves
  such a proposal deferred.
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
  derives its keys from the rows visible in `frame` (§7 for observer frames).
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
  frame with a visible row, by canonical frame name (§7). It writes nothing and
  returns the list.
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
iff a visible subject row of its closure exists in `frame` (its observer frame,
§7) **or in canon**.
- Canon is the existence authority. HD 003: "identity/existence is a CANON
  question; only the answer is knowledge-scoped."
- A frame may add entities that canon lacks: a belief, a plot arc.
- `snapshot` (390–406) passes its `frame`.

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

## §7 `knows:` frames follow merges (decision 2)

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
  - In `live_telegram_8897888758_1*`, `reconcile` merged
    `annie/lillian/may/nora/pearl/rose` on the garbage alias "laughing into
    weather that had tried and failed to erase them".
  - In `live_telegram_8786956263_2`, it merged `mara/pavel/tom_apprentice` on
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

- **Historical identity.** Closures, and therefore observer frames, are computed
  at the log head even under `asserted_as_of`. This is the engine-wide known
  limitation (`indexes.py` 167–173, 544–547). Frames follow it so a fold never
  mixes two identity epochs.
- **Non-id `knows:` suffixes** (`knows:lysa`, `knows:person_lysa`) are opaque
  names. They are never resolved, and never unified with `knows:person:lysa`.
  18 of 52 construct worlds carry such a pair. The gate warning for them is
  surfaces trap 1, and ADOPTION already says MUST use the full id.
- **Write-time frame canonicalization.** Excluded; see §7.
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
    replacing the late-bound setters (P2-8). §7 adds one more setter.
- **The extraction prompt** is unchanged. The gate enforces §1 with receipts.

## Migration and notice

**No log rewrite and no schema migration.** Existing rows are read like this:

| Row already in a log | Read after this spec |
|---|---|
| `same_as` / `maybe_same_as` / `distinct_from` outside canon | Inert: no identity read consults it. Raw scans still list it |
| `name` / `alias` outside canon | Read in its own frame only |
| Canon `alias` / `maybe_same_as` that the gate wrote for a non-canon item | Stays canon; indistinguishable from authored canon rows |
| `knows:<id>` rows | Read through the observer frame of `<id>`; nothing rewritten |
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
| Observer frames with at least two stored names / stored names renamed | 15 in 11 worlds / 34 in 13 worlds |
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
- the new receipt reason (§1);
- the canon `refer`/`reconcile` deltas (§2);
- `correlate`/`reject` outcomes (§3);
- the new `identity_conflicts()` read (§4);
- that `fidelity_audit` no longer needs a scan (§5);
- the two snapshot paths without a fallback (§6);
- canonical `who_knows` names and the two fused observer frames on bad merges
  (§7);
- the `thedeep` confirm.

**Docs, in the build commit.**
- **ADOPTION.**
  - Identity is canon's: the skip reason, frame-scoped aliases, `by_alias`/`refer`
    take a frame.
  - Observer frames: `who_knows` returns canonical names.
  - The snapshot existence rule.
  - Drop the `open_conflicts` CAUTION (358–363).
  - Document `identity_conflicts`, `conflict_already_correlated` and
    `vetoed_kind_mismatch`.
- **WHITEPAPER.**
  - §6: one paragraph on observer frames.
  - §11 and §25.2: identity is canon's; `aka` soft-blocks auto-merge;
    `identity_conflicts`.
  - §25.4: `open_conflicts` is computed.
  - The next free amendment row.
- **LEXICON.**
  - New terms: *canon identity edge*, *observer frame* (with *canonical frame
    name*), *correlation group*, `identity_conflicts()`.
  - Updated entries: `Frame`, `who_knows()`, `distinct_from`, `aka`,
    `fidelity_audit()`.
- **MCP-WRAPPER** counts: 40 tools.
- `specs/STATUS.md`.

## Tests

- One test per oracle (1a–1g, 2a–2i, 3a–3f, 4a–4d, 5a–5f, 6a–6d, 7a–7i, §8)
  in a new `tests/test_frame_scoped_identity.py`. That file also holds two
  property tests:
  - over small generated worlds, `open_conflicts(F, as_of)` lists exactly the
    keys whose `state(...)` is `conflicted`;
  - after `merge(x, y)`, every frame-taking read over `knows:x` equals the same
    read over `knows:y`.
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
- **Q3.** The frame expansion sits at `visible()` (one choke point; the audit's
  "rule missing on a sibling path" theme), not at about 30 caller sites.
  Default: `visible()`. This is pbr's call on layering.
- **Q4.** Snapshot existence is the requested frame plus canon, not the strict
  requested frame only. Default as written (§6).
- **Q5.** `ask(frame=knows:X)` keeps resolving references against canon
  (HD 003), so X's private alias doesn't resolve there. Default: unchanged, and
  revisit with batch D/E.
