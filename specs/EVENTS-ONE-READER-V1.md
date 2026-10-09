# EVENTS-ONE-READER-V1: every event read goes through one reader

**Status:** DRAFT r1 (2026-10-09). Roadmap R22: the item READ-SURFACE-V1 §10
deferred from batch E, together with the October audit's surfaces P2-5, folds
P2-7 and probe addendum E8 (`docs/AUDIT-2026-10.md`). Spec only: nothing is
built. Not yet reviewed by pbr.

**Its four decisions take their defaults** (pb's call: reversible engine
semantics, with pbr as the gate):
1. Event rows stay out of every fold even before classification (Rules A and C
   together).
2. `until` hides an event before its first stamped row.
3. `state()` answers from the event's own record, while `snapshot()`'s standing
   lenses stay standing-only.
4. Construct sees the host-impact section alongside this review, and its reply
   is folded in before the build.

- Every case below was reproduced on `main` (b03f427) with a probe on scratch
  worlds before it was specified (probes EV1–EV10, cited per oracle). Line
  numbers are at b03f427, where the suite is 634 passed, 3 skipped.
- Host impact was measured on copies of construct's 165 world files (52 live,
  20 attic, 93 retired), each opened only as a copy. A candidate reader, written
  beside the code, was compared with today's verbs call by call.
- READ-SURFACE-V1 §10's figures also counted three engine eval worlds; the
  figures here are construct's alone, re-measured. Two differ in kind, not
  just in base:
  - unclassified event rows: 1,577 here (1,575 there);
  - pseudo-events are counted as what `events()` actually returns (61 here),
    not as rows on non-event subjects that name an event (14 there).

**Why.** An event is read along six paths, each with its own rules.
- `events()` builds its list from the `what_happened` lens (porcelain.py
  744–748): EVENT-classified rows whose subject or value lies in a scope made
  of every `event:` id plus everything those ids contain. So it:
  - **misses events whose rows are not classified yet:** `classify="defer"`,
    an unsealed build, and every identity merge (`IdentityRegistry.merge`
    writes its `identity_merge` event and never classifies it). 171 events in
    71 files; 42 of them in 18 live files.
  - **invents events.** Any EVENT-classified row that touches an event makes
    its own subject an event. `obj:barn caused_by event:fire` lists an event
    `obj:barn` with kind null. So do an identity edge pointing at an event, and
    the identity edges of a thing contained in an event or merged with one. 61
    in 13 files, none live.
  - **lists a merged event once per stored id.** 17 stored ids in 13 files; 2
    live.
  - **windows row by row.**
    - `since` cuts an event's earlier and timeless rows. 61 live events read
      `kind: null` in a since-window, because their `kind` row is timeless.
    - `until` lists an event before it happens whenever one of its rows is
      timeless. 188 events in 18 live files appear, with `t: null`, in
      construct's horizon-capped reads before their time.
- `in_transit()` (`__init__.py` 176) reads `event:` rows itself,
  classification-blind and identity-resolved. It parses the movement keys a
  second time: it takes the first row by log order where `events()` takes the
  latest.
- `state()` folds, and the fold drops EVENT rows (indexes.py 471). An
  unclassified row reads STATE (classify.py 262), so `state(event:x, "kind")`
  is known until a sweep classifies the row and unknown after it (E8).
  - The event's kind is established either way. By the doctrine of the
    unknown (whitepaper A6), "unknown" means unestablished, so it is a wrong
    answer.
- `snapshot(person, lens="what_happened")` returns the one row that names the
  person, without the event's kind or its other participants (P2-7), plus the
  person's identity edges as though they were events.
- The `situation` lens emits a live event's EVENT-classified rows. It drops an
  unclassified event, and when a `caused_by` names a person, it emits that
  person's identity edges.
- `neighborhood()`'s event edges use interval visibility. A zero-duration move
  is unreachable at every numeric `as_of`, although `events(until=)` lists it.

**The principle.** An event is an entity (whitepaper §3.1) whose rows are its
**record**: what kind of occurrence it was, who and what took part, when.
- A record is read, never folded. Nothing supersedes an occurrence, and an
  occurrence is not a value of any other entity's key (whitepaper §5).
- One reader returns records, and every event read uses it.
- The fold never sees an event row, classified or not.

## §0 Dependencies, and the contract words used below

This lands after batches B–E (R16–R19). It builds on batch A, which is shipped
(`_recency_key`, `_top_evidence`, `_value_key`), and on MOVED-EVENT-V1.

| Section | Needs | Why |
|---|---|---|
| §1 | C §7 (soft) | The reader reads `visible(frame=F)`. With C, an observer frame `knows:<id>` covers every stored name of `<id>`; without C, a frame names only itself. Nothing here depends on which |
| §1 | C §2 (soft) | Event identity is `resolve()`. With C it reads canon `same_as` only. Every event merge in construct's worlds is in canon |
| §2 | E §8 | `events(asserted_as_of=)` is E's parameter; the reader carries it |
| §2 | B §2 | A passing raw `same_as` writes an `identity_merge` event. It is listed whether or not its rows were classified |
| §3 | E §8 | `in_transit(asserted_as_of=)` is the follow-up E §8 names. It is appended after E's parameters |
| §4 | E §4 | The record read returns a `FoldResult`, so E's payload (`values`, `conflicting_facts`, `value_type`, `unresolved`) applies to it; `values` extends to a record's description attributes |
| §4 | E §1 | E keeps EVENT out of the declarable classes; its O1f (an `event:` row on a pinned attribute is EVENT) holds. §4 makes the fold side structural as well |
| §4 | E §6 | `ask`'s key reads use `state()`'s point read. E §6's time cap is untouched |
| §4 | C §2 | Identity's kind lookup (Rule C) reads canon, as C requires of every identity read |

Batch D touches nothing here. If this spec has to land before E, §3's
`asserted_as_of` waits for E §8, and §4's `values` appears only once E §4 has
landed. Everything else stands alone.

The contract words are READ-SURFACE-V1 §0's: **additive**,
**result-correcting** and **new status value** (none here). One more is used
here: **internal**, meaning no change at any surface.

## §1 One reader: the event record

**Rule.**
- **An event row** is a row whose stored subject is an `event:` id and whose
  `value_type` is not `delta`.
  - It is exactly the set the classifier's guardrail makes EVENT because of
    the subject. A `delta` is checked first and is STATE, so an accrue ledger
    entry on an event still folds, as today.
  - One predicate, `is_event_row(row)` in `model.py`, is shared by the
    classifier's guardrail (classify.py 139, unchanged in effect), the fold
    (§4) and the reader.
- **The reader** is `Indexes.event_records(frame=CANON, *, ids=None,
  valid_as_of=None, asserted_as_of=None) -> dict[str, tuple[Assertion,
  ...]]`, named like every `Indexes` read.
  - **Identity.** An event is a resolved id. The reader groups the event rows
    visible in `frame` by `resolve(entity)`. A row on any other subject never
    makes an event: not a `caused_by` that names one, not an identity edge, not
    a thing contained in one.
    - An event merged into a closure whose canonical id is not an `event:` id
      is reported under that id, as `entities()` reports it: 8 events in 7
      files, none live (`event:tide` into `person:adelina_voss`,
      `event:theft_plan` into `place:casino_vault`, …).
  - **The record** is the event's rows minus the engine's machinery
    (`META_ATTRIBUTES`: identity edges, provenance, semantics declarations).
    Machinery rides beside a record, as it does for every entity
    (`current_state` skips it the same way). No event in the 165 files
    consists only of machinery rows.
  - **Never the sidecar.** The reader makes no classification lookup.
  - **The asserted axis** is `visible(asserted_as_of=)`, retractions included,
    as for every read.
  - **The valid axis**, one rule for every event read:
    - an event **has occurred by** `T` when `T` is None, or when it has no
      stamped row (a timeless event, such as a merge), or when its earliest
      stamped `valid_from` is ≤ `T`;
    - its record as of `T` is its timeless rows plus its rows stamped ≤ `T`;
    - `valid_to` never hides an event row. A closed or zero-duration event
      stays history (MOVED-EVENT-V1 §D.6).
  - `ids` limits the read to the named events, each through its identity
    closure. It serves the per-event callers in §4–§6.
- **The pick** is the one rule for every single value read from a record:
  among an attribute's rows, those at the top evidence rank (`_top_evidence`),
  then the one with the greatest `_recency_key`.
  - Rank comes first because batch A applies it to every fold: a later
    `assumed` kind never displaces a `stated` one (P5).
  - It changes no `events()` payload in the 165 files.
- **The parse** is `event_payload(event_id, rows) -> dict`, a pure function
  beside the reader. It builds MOVED-EVENT-V1 §E1's twelve-key dict from a
  record:
  - `kind`, `origin`, `destination`, `manner`: the pick. `origin_bound` and
    `destination_bound` are the pick's `value_type == "entity"`;
  - `agents`, `patients`, `caused_by`: every row's stored value, in
    `_recency_key` order;
  - `t`: the greatest `valid_from` in the record, or None when every row is
    timeless;
  - `valid_to`: the `valid_to` of the latest (`_recency_key`) movement-payload
    row (`kind`, `agent`, `origin`, `destination`, `manner`) that carries one.

  It is today's `events()` loop (porcelain.py 750–786) with rank applied first
  in the pick, run over a whole record instead of over the rows a window and the
  sidecar let through.
- **Order**, wherever events are listed: by `t` (None first), then by the
  event's earliest row in `_recency_key` order. This reproduces today's order.
  On 348 frames it differed in 8, all attic or retired, each where the record
  itself changed (a merge, or unclassified rows).

**Location.**
- `model.py`: the new `is_event_row`.
- `indexes.py`: the new `event_records`, `event_payload` and the pick, beside
  `event_participation` (1364).
- `classify.py` `_guardrails` (139).

**Oracle** (probes EV1–EV3, EV6, EV9):
- **O1a.** A move ingested with `classify="defer"`: `event_records()` holds
  it, and after `classify_all()` the records are equal.
- **O1b.** `obj:barn caused_by event:fire`; `reject(doc:note, event:fire)`;
  `person:ilsa in event:convoy` with `reject(person:ilsa, person:bo)`. The
  records are keyed `event:fire` and `event:convoy` only.
- **O1c.** `event:wedding` (kind) merged with `event:the_wedding` (agent): one
  record, keyed `event:wedding`, holding both ids' rows.
- **O1d.** `event:summons`, with a timeless `kind` and a `patient` at 8: no
  record as of 6; as of 8, both rows. `event:siege`, with its kind at 5 and an
  agent at 7: as of 6, the record is the kind row.
- **O1e.** A zero-duration move `[5,5)` has a record as of 5 and as of 9, and
  none as of 4.
- **O1f.** An event's `same_as`, `maybe_same_as` and `distinct_from` rows are
  not in its record. `facts(entity=)` still lists them.
- **O1g.** The pick: `kind` "meeting" (stated) and a later "assembly"
  (assumed), both at 2, give "meeting".
- **O1h.** Every classifier verdict in the existing suite is unchanged.

**Contract.** Internal.

**Byte-identical.** Every classification verdict: `is_event_row` is the
guardrail's existing test.

**MCP.** None.

## §2 `events()` reads records

**Rule.** `events(kind, participants, since, until, frame[, asserted_as_of])`:
1. reads `event_records(frame, valid_as_of=until,
   asserted_as_of=asserted_as_of)`;
2. builds `event_payload` for each record;
3. `since` keeps an event whose `t` is not None and is ≥ `since`;
4. filters by `kind` and `participants` as today (`participants` is all-of
   over the resolved `agents` ∪ `patients`);
5. lists them in §1's order, through `encode_out`.

`events()` no longer goes through `materialize`. `ask(wants_events)` calls it
and inherits the rule.

Each change corrects an answer that is wrong by the verb's own words
("reified events (`event:` entities) in a frame ... a valid-time window"):
- an event is listed whether or not its rows are classified;
- a non-event subject never is;
- a merged event is listed once, under its resolved id, with every stored
  id's rows: an entity is its identity closure, as `entities()` reports ids
  and as `in_transit()` already groups events;
- `since` no longer cuts an event's earlier or timeless rows;
- `until` no longer lists an event before its first stamped row.

Which events a window admits is otherwise today's. An event is in `[since,
until]` exactly when today's per-row test admitted one of its rows. This was
checked call by call on the 165 files: every inclusion difference is one of
the cases above.

**Location.** `porcelain.py` `events` (737–798).

**Oracle** (today → after):
- **O2a** (EV1). A move ingested with `classify="defer"`: today `events() ==
  []` while `in_transit()` lists it; after, both list it. `classify_all()`
  then changes neither.
- **O2b** (EV2), in O1b's world: today five events, namely `doc:note`,
  `person:ilsa` and `obj:barn` with kind null (`obj:barn` with `caused_by:
  ["event:fire"]`), plus `event:convoy` and `event:fire`; after, `event:convoy`
  and `event:fire`.
- **O2c** (EV3), in O1c's world, leaving aside the merge's own
  `identity_merge` event: today `event:wedding` (no agents) and
  `event:the_wedding` (kind null); after, one event, `event:wedding`, with kind
  wedding and agents `["person:ines"]`. `events(participants="person:ines")`
  returns it.
- **O2d** (EV4), in O1d's world:
  - `events(since=6)`: today siege and summons, both with `kind: null`; after,
    siege (kind siege, agents `["person:k"]`, t 7) and summons (kind summons,
    t 8);
  - `events(since=6, kind="summons")`: today `[]`; after, summons;
  - `events(until=6)`: today summons (`t: null`) and siege (t 5); after, siege
    only, without the agent it gains at 7.
- **O2e.** The existing `events()` tests pass unchanged: test_porcelain,
  test_tracking_mode B3, and test_moved_event oracles 6c and 11.
- **O2f.** No model call and no write.

**Contract.** Result-correcting.

**Byte-identical.**
- Every call in a `session:`, `plot:` or `knows:` frame. On the 165 files, 0 of
  2,194 calls differ, across every call shape: unfiltered, by each kind
  present, and `since` and `until` at each event time. construct's bookkeeping
  reads (turns, entries, episodes, arcs won and lost, clocks, pins, generation
  receipts) live in these frames.
- construct's per-turn canon window, `events(since=turn k−1, until=turn k)`:
  0 of 310 turns differ on its 52 live files.
- A canon event whose rows are all classified, with one stored id and no
  timeless row beside stamped ones: byte for byte, in any window.

**MCP.** No schema change. The `events` tool's results change as above.

Faster as well: with the candidate reader, canon `events()` on the largest live
files drops from 39–101 ms to 1–3 ms. Today's path walks the containment of
every event and scans the whole frame.

## §3 `in_transit()` reads records

**Rule.**
- It reads `event_records(frame, valid_as_of=as_of,
  asserted_as_of=asserted_as_of)` and builds `event_payload` for each. A
  record is a move when its `kind` (the pick) is `"moved"`.
- **Openness** is unchanged from MOVED-EVENT-V1 §E2:
  - with `as_of=None`, a move is open when its `valid_to` is None;
  - at `T`, it is open when it has occurred by `T` (§1) and its `valid_to` is
    None or `T < valid_to`.
- `agent` is the pick of the record's `agent` rows (its stored value).
  `origin`, `destination` and `manner` are the payload's. The identity-aware
  `agent` filter is unchanged.
- **The anchor** is MOVED-EVENT-V1's, read from the record: `(t, the least
  asserted_at among the record's movement-payload rows)`.
- The containment comparison is unchanged, and now also runs at
  `asserted_as_of`.
- **`asserted_as_of: int | None = None`** is appended last, on
  `World.in_transit` and on the porcelain alike, so the two signatures stay
  identical (MOVED-EVENT-V1 §E2). READ-SURFACE-V1 §8 deferred it because the
  lower layer lacked it; the reader carries it.
- `World._MOVE_PAYLOAD` retires. The movement keys are named once, beside
  `event_payload`.

Under MOVED-EVENT-V1's contract (one interval and one row per key for each
move) the two parses agree, and they agree on every measured world. They
differed only for a corrected move.

**Location.** `__init__.py` `World.in_transit` (174–233); `porcelain.py`
`in_transit` (800–807).

**Oracle:**
- **O3a** (EV5). A move whose `origin` is asserted twice at one stamp (hall,
  then barn): today `events()` says barn and `in_transit()` says hall; after,
  both say barn.
- **O3b.** MOVED-EVENT-V1's oracles 5e, 6a–6c, 11 and 11a pass unchanged.
- **O3c.** `in_transit(asserted_as_of=H)` with `H` before the move's rows
  gives `[]`; at the head, the move.

**Contract.** Result-correcting where the parses disagreed; additive
(`asserted_as_of`).

**Byte-identical.** 360 calls on the 165 files (`as_of` None, and each move's
`t` and `t + 0.5`): 0 differ.

**MCP.** The `in_transit` tool gains `asserted_as_of` (`integer|null`) from the
signature.

## §4 Event rows never fold, and a point read of an event reads its record (E8)

**Rule A: the fold drops event rows by structure.**
- `_fold_over_closure` (indexes.py 471) skips a row when `is_event_row(row)`
  or its durability is EVENT. Today it checks only the durability, and an
  unclassified event row reads STATE and folds.
- `Projector._establishing_scope` (project.py 95), the raw containment pick
  behind the establishing lens, skips event rows the same way, so that view
  agrees with `contents()`.
- So an event's own keys fold to nothing, and an event is never inside a
  container (`contents`, `locate`, `aggregate`, the snapshot scope walk),
  whether or not a sweep has run. "EVENT never folds" holds before
  classification as well as after it.

**Rule B: a point read falls back to the record.**
- `Indexes.event_attribute(entity, attribute, frame=CANON, valid_as_of=None,
  asserted_as_of=None, *, correlated=False) -> FoldResult` reads one attribute
  from the record of `entity`'s closure, as of the read (§1). With
  `correlated=True` it reads the records of the `aka` union, as
  `current_state(correlated=)` does.
  - No row, or an attribute in `META_ATTRIBUTES`: `FoldResult(winner=None)`.
  - `winner` is the pick.
  - `kind`, `origin`, `destination` and `manner` are single-valued. The event
    algebra (whitepaper §12, `event(kind, agents, patients, t, effects)`) and
    MOVED-EVENT-V1 give each of them one value. When the top-rank rows at the
    winner's stamp disagree (`_value_key`), the result is conflicted, and
    `conflicting` holds their ids in log order. This is the fold's own
    same-stamp contradiction test.
  - Every other attribute is description, and an occurrence may hold several
    values of it: participants, aliases, the place it happened `in`. It is
    never conflicted. `_value_rows` holds every row in `_recency_key` order.
    Once E §4 has landed, `state()` serves them as `values` whenever there are
    two or more: E §4's rule for a set-valued key, extended to a record's
    description.
- **The callers** are the porcelain's point reads: `state()`, `state_union()`
  (with `correlated=True`) and `ask`'s key reads. Each folds first and calls
  `event_attribute` only when the fold serves nothing.
  - For an event, the fold serves nothing (Rule A), so the record answers.
  - For any other entity the record is empty, so nothing changes.
  - For a closure that merges an event with a standing entity (a bad merge),
    standing keys keep their fold, and only the event's own attributes come
    from the record.
- So `state(event:x, a)` serves, for `kind` and the movement keys, exactly what
  `events()` reports, under the same frame, valid as-of and asserted as-of. An
  event that has not occurred by `as_of` is unknown in every attribute.

**Rule C: identity's kind lookup reads the same way.** `World` wires the
registry's kind provider (`__init__.py` 88) to the fold of `kind`, falling back
to `event_attribute(entity, "kind")`.
- Rule A alone would hide an event's kind from identity's merge gates during
  a build. construct reconciles inside a build session (`game.py`
  `_stage_reconcile_identity`, before `_stage_seal`). There every row is
  unclassified, an event's kind folds as STATE, and the gate sees it today.
  Rule C keeps that (O4h).
- After a sweep, today, an event's kind is invisible to identity, and the gate
  rates an event against a person "noncommittal": a shared proper name merges
  them. Rule C makes the pair a kind conflict, before the sweep and after it
  alike.
- The durable-contradiction veto is unaffected. It compares CONSTITUTIVE and
  DISPOSITIONAL winners, and an event row is never one.

**What stays standing-only.**
- The engine's `fold_key`, and so every engine caller of it. Rules B and C add
  their fallback outside it.
- `snapshot()`'s standing lenses: `current_state`, `establishing_set`,
  `character_sheet`, and `situation`'s floor. An event has no standing truth;
  its view is `snapshot(event, lens="what_happened")` (§5).
- The reads that compare or aggregate across entities and frames: `where`,
  `aggregate`, `who_knows`, `confidence` and `frame_diff` (see Non-goals).

**Location.**
- `indexes.py`: `_fold_over_closure` (471) and the new `event_attribute`.
- `project.py`: `_establishing_scope` (95–135).
- `porcelain.py`: `state` (420), `state_union` (661) and `ask`'s key loop (957).
- `__init__.py`: the kind-provider wiring (88).
- `World.state` and `Indexes.fold_key` are unchanged.

**Oracle** (EV6, EV1):
- **O4a.** `event:meeting` (kind meeting, `in place:study`, both at 2),
  ingested with `classify="defer"`:
  - today, before a sweep: `state(event:meeting, "kind")` is known;
    `contents(place:study) == ["event:meeting"]`; `snapshot("event:meeting")`
    has the facts `in` and `kind`; `events() == []`;
  - today, after `classify_all()`: `state` is unknown, `contents` is `[]`, the
    snapshot has no facts, and `events()` lists the meeting;
  - after, both before and after the sweep: `state(…, "kind")` is known
    "meeting" and `state(…, "in")` known "place:study"; `contents` is `[]`;
    the snapshot has no facts; `events()` lists the meeting.
- **O4b.** A move stamped 5: `state(event:walk_1, "kind", as_of=4)` is unknown;
  at 5 it is "moved", for a zero-duration move too.
- **O4c.** Same-stamp disagreement:
  - two stated `kind` rows at one stamp (or both timeless), "custom" then
    "time period": conflicted, with fact "time period" and both ids in
    `conflicting`;
  - O1g's world: known, "meeting" (rank);
  - two `participants` rows: known, with the later one as the fact, and both
    in `values` once E has landed.
- **O4d.** `state(event:x, "same_as")` is unknown, as for any entity.
- **O4e.** `ask` with a plan key on an event target: today "no folded facts on
  the asked keys"; after, the record's fact.
- **O4f.** A `delta` on an event's `accrue` attribute: the total is served,
  today and after.
- **O4g.** `where`, `who_knows` and `aggregate` never return an event because
  of its record.
- **O4h** (EV10). Identity: `event:wren` (kind storm, at 3) and `person:wren`
  (kind person) share the name "Wren Hollis".
  - In a build session (every row unclassified), `reconcile()` makes a
    proposal and no merge, today and after. With Rule A but without Rule C it
    would merge them.
  - In the same world swept (`classify="rules"`), `reconcile()` merges the
    event into the person today; after, it makes the same proposal as in the
    build.
- **O4i.** Classification-independence: on O4a's world, `state()` and
  `contents()` give the same answers before and after `classify_all()`.

**Contract.** Result-correcting. No new status value.
- `state` and `state_union` on an event's own attribute go from unknown to
  known, or to conflicted for a same-stamp disagreement on a single-valued key.
- Unclassified event rows stop folding. They leave `contents()`, `locate()`,
  the snapshot scope walk and every standing lens, as a sweep would remove
  them.
- Identity's gates see an event's kind after a sweep as they already do before
  it.

**Byte-identical.**
- Every fold where all event rows are classified (they were EVENT already).
- `state` of every entity that is not an event.
- construct's build-time identity view. Simulated on the live copies with
  every event row unclassified, identity's kind lookup gives the same answer
  for all 637 events with one `kind` row. Of the 11 with two, 5 give the same
  answer, and 6 report the same conflict (so the gate decides the same) while
  naming the later kind where today's fold names the earlier.
- Measured on the live copies:
  - 3,172 event keys go from unknown to known, and 6 go to conflicted: two
    kinds at one stamp, on `event:mending_night` and `event:fog_bell_hour`, in
    4 files;
  - the 119 event keys an unclassified row served keep their values;
  - Rule A takes 4 events out of `contents()` in 3 files. They are
    `event:message_delivery` in `place:liddell_warehouse`, in the two bodycase
    harness files, and `event:skid_smear` and `event:wet_trail`, in
    `thedeep.critic.ep.checkpoint`. Each took 7–9 facts, mostly aliases, into
    every snapshot of its place.
  - An unclassified event's salience loses its delta-from-baseline term, as it
    does after a sweep.
- Rule C after a sweep, measured on the 52 live copies (sealed worlds) with
  Rules A and C:
  - `proposals()` keeps every pair. In 15 files some pairs' decline context
    now names the event's kind (today null), and codes such as
    `alias_not_specific` and `kind_absent` become `kind_conflict`;
  - `typing_conflicts()` changes in 12 files, gaining 12 candidates in all:
    an event and an object or place that share an anchor
    (`event:woke` / `obj:cinder_crown` on "the iron woke");
  - `fidelity_audit()`'s `name_collisions` keep their groups and show event
    kinds in 21 files.
  - construct calls these reads only in its build stages, before the seal,
    where they already see event kinds.

**MCP.** The results of `state`, `state_union` and `snapshot` change, and so,
after a sweep, do the event kinds in `proposals`, `typing_conflicts` and
`fidelity_audit`. No schema change.

## §5 The lenses read records

**Rule.**
- **`what_happened`** (`Projector._lens_events`):
  - it reads `event_records(m.frame, valid_as_of=m.as_of,
    asserted_as_of=m.asserted_as_of)`;
  - an event is in scope when the scope is empty, when its id is in the scope,
    or when a row of its record has an entity value that resolves into the
    scope: an agent, a patient, the place it happened `in`, an event it was
    `caused_by`;
  - `since` keeps an event whose `t` is ≥ `since`;
  - it emits each event's whole record, events in §1's order and rows within
    an event in `_recency_key` order.
  - Rows on other subjects are never emitted: an identity edge, a
    subject-level `caused_by` (7 rows in the 165 files, 1 live), or the rows of
    a thing contained in an event.
- **`situation`** finds live events exactly as today: the resolved
  `caused_by` values of served rows (SITUATION-LENS-V1 bucket 2). It emits
  them from `event_records(m.frame, ids=live, valid_as_of=m.as_of,
  asserted_as_of=m.asserted_as_of)`, in recency order, budgeted as today. A
  live "event" with no event rows (a `caused_by` that names a person) emits
  nothing.
- `what_happened` keeps §13's row-level budget shaper (see Non-goals).

**Location.** `project.py` `_lens_events` (365–389) and `_lens_situation`
(304–363).

**Oracle:**
- **O5a** (EV7). `event:theft` (kind theft, agent person:rival, patient
  obj:pipe, at 5), and `reject(person:rival, person:other)`.
  `snapshot("person:rival", lens="what_happened")` facts:
  - today `[person:rival distinct_from person:other; event:theft agent
    person:rival]`;
  - after `[event:theft kind theft; event:theft agent person:rival;
    event:theft patient obj:pipe]`.
- **O5b.** `snapshot("place:study", lens="what_happened")` lists every event
  that happened `in` the study, whole.
- **O5c.** `test_what_happened_window` passes unchanged.
- **O5d** (EV8). A door broken at 4, `caused_by event:kick`, where the kick's
  rows are unclassified: today the situation bucket is empty; after, it holds
  the kick's record.
- **O5e.** A served row `caused_by person:lysa`: today the bucket emits
  person:lysa's identity edges; after, nothing.
- **O5f.** SITUATION-LENS-V1's tests pass unchanged.

**Contract.** Result-correcting.

**Byte-identical.**
- `situation` wherever the live events are classified event entities without
  identity edges. On construct's 771 live place scopes (83 with live events),
  736 are unchanged. In 35, 98 rows leave (identity edges, on live events and
  on non-event "causes"), and 2 rows of an unclassified live event join.
- construct never calls `what_happened`.

**MCP.** The `snapshot` results change.

## §6 `neighborhood()`'s event edges read records

**Rule.**
- `event_participation(entity, frame, valid_as_of, asserted_as_of)` returns
  the events whose record, as of the read, has an `agent` or `patient` row
  resolving into the entity's closure. Candidates still come from the indexed
  value lookup, kept only when the row is an event row.
- `caused_by_of(events, …)` returns the resolved `caused_by` values of their
  records, as of the read.
- So the edges follow §1's valid-axis rule, and a closed or zero-duration
  event stays reachable after it ends. A non-event subject with an `agent` row
  is not an event (4 such rows in live worlds).

**Location.** `indexes.py` `event_participation` (1364) and `caused_by_of`
(1390).

**Oracle:**
- **O6a** (EV9). `event:wave`, `[5,5)`, with agent person:mara.
  `neighborhood(person:mara, edge_kinds=["events"])`:
  - at `as_of=5` and at 9: today no event neighbour; after, `event:wave`;
  - at `as_of=None`: `event:wave`, before and after;
  - at 4: none, before and after.
- **O6b.** test_world_retrieval's event tests pass unchanged: a cause on a
  merged event's stored id is still reached.

**Contract.** Result-correcting.

**Byte-identical.** `as_of=None` reads of classified event entities. construct
makes no `neighborhood` call.

**MCP.** The `neighborhood` results change.

## What hosts see

| Read | Today | After |
|---|---|---|
| `events()` | needs classification; invents events from rows that point at one; lists a merged event per stored id | every event entity, classified or not, and nothing else; one entry per resolved id (§2) |
| `events(since=)` | cuts an event's earlier and timeless rows (`kind: null`) | whole records (§2) |
| `events(until=)` | lists an event before it happens, through a timeless row | only once its first stamped row is ≤ `until` (§2) |
| `in_transit()` | its own parse (the first row) | `events()`'s parse; `asserted_as_of=` (§3) |
| `state(event:x, a)` | known before a sweep, unknown after it | the record's value, either way (§4) |
| `contents(place)` | lists an event whose `in` row is unclassified | never lists an event (§4) |
| identity's kind gate | sees an event's kind before a sweep only | sees it always (§4) |
| `snapshot(…, lens="what_happened")` | the one row naming a scoped entity, plus its identity edges | the whole records of the events it is involved in (§5) |
| `snapshot(…, lens="situation")` | the EVENT rows of live "events", identity edges included | live events' records (§5) |
| `neighborhood` event edges | a closed or zero-duration event unreachable at a numeric `as_of` | reachable once it has occurred (§6) |

## Non-goals

- **Events in the lateral graph.** `path` and `route` still read
  `connects_to`/`adjacent_to` rows on event subjects: 18 rows in 7 files, 2 of
  them live, in one file. It is a raw walk, already classification-blind.
  Whether an event may be a node is its own question.
- **Knowledge, comparison and trust over events.** `who_knows`, `where`,
  `aggregate`, `confidence` and `frame_diff` stay standing-only. "Who knows
  the fight happened?" is a real question with its own semantics (a frame
  holding the event's record). Tripwire: a host asks it.
- **Other unclassified structural rows.** A `caused_by` on a non-event subject,
  and META rows, still read STATE until classified. The general fix, a fold
  that applies every deterministic guardrail before the sidecar, would also
  change unclassified `name`/`alias` rows, and is its own question.
- **`events(ids=)`.** `state()` answers per attribute, and a host that wants
  one whole dict filters `events()`. Tripwire: a host fetches one event's dict
  per turn.
- **Budgeting `what_happened` by whole events.** Its budget stays §13's
  row-level shaper.
- **`fidelity_audit`'s `unstamped_timed`** reads the sidecar by design: it runs
  after classification.
- **Classifying the merge path's rows.** After this spec no read depends on
  it, and a sweep still classifies them.

## Migration and notice

**Engine.** No log rewrite, no schema change, no sidecar change. Every read
changes on its next call.

**Ship notice to construct**, after build and GREEN. Measured on copies of its
165 files, 52 of them live.
- **Unchanged:**
  - every `events()` call in `session:main`, the `plot:` frames and the
    `knows:` frames (0 of 2,194 measured calls differ), so the bookkeeping
    reads by kind do not move;
  - the per-turn canon window `events(since=turn k−1, until=turn k)`
    (turnloop ~2867): 0 of 310 turns differ;
  - `in_transit()`, on every world;
  - `state(eid, "name")` (text.py): no event has a `name` row.
- **Canon `events()`** (game.py ~2449 unfiltered; game.py ~2990 and turnloop
  ~988 and ~3780 by kind):
  - 42 events appear in 18 live files, every one of them from unclassified
    rows: 14 `identity_merge`, 13 of kind `event`, two with no kind, and one or
    two each of meeting, errand, clock_strike, cry, body found, words over a
    warehouse matter, body, rockfall, summons and walk. None has a kind that
    construct's reads filter on (no live world's metadata sets
    `result_events`);
  - two stored ids collapse into their resolved id: `event:joss_sends_mara`
    into `event:mara_enters_radio_cabin`, in `live_telegram_8786956263_3` and
    its critic copy;
  - `event:quake`, in `thedeep.critic.ep.checkpoint`, gains `t: 0.0`;
  - no live world holds a pseudo-event, so game.py ~2449's
    `e.kind.replace(...)` never met one there; after this spec it cannot.
- **Canon `events(until=floor)`** (turnloop ~2869, `_prior_kinds`): differs on
  142 of 310 turns in 13 live files. Source events stamped after the floor stop
  appearing early (the 188-event horizon leak: Cx 253 §4's intent, now held),
  and the unclassified past events above appear.
- **`state()` on events:** `arc/conclusion.py` ~153's fallback,
  `state(event:arc_cancelled_<slug>, "kind", frame=SESSION)`, now answers from
  the record and agrees with its `events()` read.
- **Snapshots:**
  - the situation lens (session.py ~972) changes in 35 of 771 live place
    scopes. Identity edges leave the live-event bucket (98 rows), and one
    unclassified live event's record joins (2 rows);
  - snapshots of three places lose an unclassified event they "contained"
    (Rule A): `place:liddell_warehouse`, in the two bodycase harness files, and
    `place:belly_viewport` and `place:ore_lock_service_alcove`, in
    `thedeep.critic.ep.checkpoint`. They lose 7–9 facts each.
- **Identity: unchanged in construct's flows.** Its reconcile, deferred
  adjudication, typing-slip triage and name-collision vouching all run in
  build stages before the seal. There an event's kind is visible today
  (unclassified rows fold as STATE), and Rule C keeps it visible: the same
  answer for all 637 single-kind events, the same gate decision for the 11
  two-kind ones. After a seal, a caller of `proposals()`, `typing_conflicts()`
  or `fidelity_audit()` sees event kinds where today it sees none (15, 12 and
  21 live files), and an event no longer auto-merges with a non-event that
  shares a proper name (O4h).
- **Speed:** canon `events()` on the largest live files drops from 39–101 ms
  to 1–3 ms.

## Docs, in the build commit

- **WHITEPAPER:**
  - §5: an event row never folds, by structure;
  - §12: `state(e, a)` on an event reads its record;
  - §13: `what_happened` serves whole events, scoped by involvement, and
    `situation` emits records;
  - §25.1 and §25.4: one reader for `events`, `in_transit`, the two lenses and
    `neighborhood`; `in_transit(asserted_as_of=)`;
  - the next free amendment row after A–E's.
- **LEXICON:**
  - new: *event row*; *event record* (`event_records()`, the as-of rule, the
    pick);
  - updated: `kind=moved` / `in_transit()` (one parse, `asserted_as_of`), the
    `situation` lens and *live thread* (records), `neighborhood()`.
- **ADOPTION:** `events()` needs no sweep; its ids are resolved; the window
  rule; `state()` on an event; which lens shows an event.
- **Dated notes:**
  - MOVED-EVENT-V1: one parse; the anchor read from the record;
  - SITUATION-LENS-V1: bucket 2 emits records;
  - CLASSIFIER-EVENT-SAFETY-V1: the shared predicate; the fold side is
    structural too;
  - READ-SURFACE-V1: §10 delivered here, and §8's `in_transit` follow-up;
  - PORCELAIN-V1: `state()` on events.
- `specs/STATUS.md`.

## Tests

- A new `tests/test_events_one_reader.py` holds one test per oracle, by
  section.
- **Classification-independence**, a property test. On generated worlds
  (event rows with and without stamps, merges, corrections, several frames),
  these give the same answers before and after `classify_all()`: `events()`
  under every call shape, `in_transit()`, `state()` on every event key,
  `contents()`, and the `what_happened` lens.
- **Parity.** For every event, and each of `kind`, `origin`, `destination` and
  `manner`, `state(event, key)`'s fact value equals `events()`' field.
- The existing suite (634 passed, 3 skipped at b03f427) stays green unchanged.
  No existing test encodes one of the wrong answers above: a grep finds no
  test of `state`, `contents` or `locate` on an event entity.

## Decisions for Kabe (each with a default)

1. **Should an event row stay out of every fold even before classification
   runs, with identity's kind lookup reading the record** (§4 Rules A and C)?
   - *Default:* yes. Reads stop depending on whether a sweep has run, and §5's
     rule holds before the sweep as after it.
     - Three places in three live files lose an unclassified event from their
       snapshots, exactly as a sweep would remove it.
     - Rule C is what makes Rule A safe: without it a build-time reconcile
       could merge an event into a person (O4h). With it, construct's build
       sees the same kinds as today, and after a seal an event's kind stops
       being invisible to identity.
   - The alternative keeps unclassified event rows folding as STATE. `state()`
     then still flips at the sweep, `contents()` lists events until it, and
     identity keeps seeing event kinds before a sweep only.
2. **Should `until`, and every as-of, hide an event before its first stamped
   row** (§1)?
   - *Default:* yes. That is what construct's horizon cap is for (Cx 253 §4).
     188 source events in 18 live files stop appearing early, and construct's
     `_prior_kinds` changes on 142 of 310 turns.
   - The alternative keeps the row rule: a timeless row makes an event visible
     at every horizon, with `t: null`.
3. **Should `state()` answer an event's own attributes from its record, while
   `snapshot()`'s standing lenses stay standing-only** (§4)?
   - *Default:* yes. By the doctrine of the unknown, an established attribute
     is never "unknown". A lens selects classes (§13), and an event has no
     standing truth.
   - The alternatives: keep `state()` fold-only and send hosts to `events()`;
     or have the standing lenses list event records too.
4. **Construct at the table.** READ-SURFACE-V1 §10 asked for it, because
   `events()` changes what construct reads.
   - *Default:* send construct this spec's ship-notice section with the pbr
     request, and fold its reply in before the build.
