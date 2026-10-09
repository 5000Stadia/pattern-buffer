# GATE-AUTHORITY-V1: the gate decides by authority, and every refusal is a receipt

**Status:** r2 (2026-10-09; r1 2026-10-08). Batch B of `docs/AUDIT-2026-10.md`;
Kabe approved the five batches. r1 was built gated on `impl/gate-authority-v1`;
pbr returned RED on one point of §1 plus two rulings, and the internal
pre-review returned GREEN-with-nits. r2 is rebased onto main (batch A and
GATE-INVERSE-ALIAS-V1 merged) and resolves all of it: see "r2: review
resolutions" at the end. Next: pbr on r2. Every r1 case was reproduced on
`polish/audit-2026-10` (212754f) with a probe before it was specified. r1's
blast radius was measured read-only on construct's 213 world files and the
engine's three eval worlds (334,785 rows); r2 re-measured on 2026-10-09's
copies (165 construct world files, 256,473 rows; the eval worlds 4,834 rows).

**Why.** The ingest gate is P8's single door, and it is uneven in two ways
(audit P1 #6 and #13, plus the batch-B P2 items):
- **It trusts names where it should check authority.** A row counts as a
  retraction, a thunk's resolution or an attribute-alias receipt because of its
  attribute name alone, so an ingestor item can forge all three. A raw
  `same_as` row merges two ids past both hard vetoes.
- **It refuses some bad inputs after it has started writing them, and drops
  others silently.**
  - A `generated` item with `source_doc` raises after its main row is saved.
  - `aliases: "the vault"` writes nine one-letter aliases.
  - A null `frame` crashes mid-chunk.
  - `p.ingest()` never reports its skips.
  - An uppercase id in the value position becomes text and wins the location
    fold.

The rule this spec makes uniform: **authority is settled before an item's
first write, and every refusal that is not an authority violation is a typed
skip receipt.** No fold rule changes. An item that passes every check writes
the same rows as today, except a raw `same_as`, which becomes a guarded merge
(§2).

**Founder decisions this relies on** (audit "Decisions for Kabe", all approved
as recommended):
- **#1, identity is not perspectival for merges.** `same_as` is canon-only, and
  the gate refuses it in other frames with a receipt.
  - §2 applies this to raw `same_as` rows.
  - Batch C applies it to the item-level `same_as` field and to identity
    reads.
- **#4, second half (`fold_policy`).** Batch E may settle `last_write|move`
  either way. §5 validates against `semantics.FOLD_POLICIES` by reference, so
  it follows whatever E decides.
- **#6, the connection facade.** It gets simplified later; this spec adds no
  facade surface.

## §0 The gate's order, and the skip vocabulary

`_ingest_item` after this spec, in order (r2: thirteen steps, the inverse swap
numbered in). Steps marked *existing* keep their code and their relative order:
the audit's do-not-touch ordering is authority raises first, then the
malformed-id check, identity, intervals, per-edge skips.

1. **Normalize** (§4): shape only, no write. Only a non-object is refused here.
2. **Authority** (§3): raises, no write. First the status grant, then the
   frame's shape (a malformed frame is `malformed_item`, r2), then the
   existing letter-029 checks for `generated`, moved up. They read only
   `status`, `frame` and side-field presence, so for any item canonicalization
   accepts, running them first changes no outcome.
3. **Content checks** (§4): skips. A numeric-string `confidence` is coerced
   here (r2).
4. **Canonicalize** the attribute. *Existing.*
5. **Inverse swap** (GATE-INVERSE-ALIAS-V1 §2). *Existing* (merged before r2):
   once `value_type` is decided, an inverse relation with an entity value swaps
   subject and object, before every later check.
6. **Mechanism attribute** (§1): skip.
7. **Malformed-id gate** on the raw ids. *Existing.*
8. **Id-shaped value on an entity-valued predicate** (§7): skip. The item's
   first-use declaration (§5) is planned here, without a write, so this step
   and step 9's per-edge checks judge the attribute's relation family as the
   item's own declaration will leave it (r2).
9. Identity resolution, decay half-life, time values (batch A §6), interval
   invariants, per-edge structural skips. *Existing.*
10. **Declarations** (§5): validated, then written.
11. **Main row**, or for `same_as` the guarded merge (§2).
12. Side rows, in the *existing* order. Dropped aliases are receipted here
    (§4).
13. Classification. *Existing*: §8 changes the classifier, not the gate.

With this order, everything that can refuse an item (as opposed to one of its
side rows) runs before the item's first write. What can still fail afterwards
is infrastructure (a database or clock error), which `atomic=True` already
covers.

**Skip vocabulary.** A `SkipRecord` is `{entity, attribute, value, reason[,
detail]}`.
- `reason` is a fixed code.
- `detail` is batch A's field, emitted only when set. It carries the offending
  input when that input is not the row's value. (Merged before r2:
  GATE-INVERSE-ALIAS-V1 also sets it, to the authored form, on a skip of an
  item the gate swapped, where the table below shows none.)
- Fields the item lacks are null.

`ingest.py` gains `SKIP_REASONS`, the frozen set of codes. A suite-wide check
fails on any recorded reason that is neither a member nor one of the three
legacy prose forms below.

| Code | Owner | Meaning | `detail` |
|---|---|---|---|
| `malformed_id` | SHAPE-FIX-V1; widened by §2, §4, §7 | an id outside the grammar, in any position | — |
| `invalid_decay_halflife` | TRACKING-MODE-V1 | not a finite positive half-life | — |
| `valid_to_without_valid_from`, `valid_to_before_valid_from` | MOVED-EVENT-V1 §B.2 | interval invariants | — |
| `moved_marker_invalid`, `moved_open_with_arrival`, `moved_complete_attribute_not_durable` | MOVED-EVENT-V1 | movement-group failures | — |
| `invalid_valid_time` | batch A §6 | a time coordinate that is not a finite number (a numeric string is coerced first) | the value as authored |
| `malformed_item` | §4 | not an object; `entity`/`attribute`/`value` absent; `attribute` or `frame` not a non-empty string | `{"missing": [...]}` or `{"field", "value"}`; none for a non-object |
| `invalid_field` | §4 | `value_type` outside its vocabulary; `timeless`/`correction` neither a real bool nor the int 0/1; `confidence` not a finite number (a numeric string is coerced first) | `{"field", "value"}`, the value as authored |
| `invalid_alias` | §4 | one `aliases` member (or the whole field) that is not a non-empty string; the item's other rows still land | — |
| `mechanism_attribute` | §1 | the canonical attribute is a mechanism attribute: `retracts`, `resolved_by`, `canonicalized_from`, and (r2) `learned_at_wallclock`, `source_valid_from`, `correction_proposal` | — |
| `same_as_not_canon` | §2 | a raw `same_as` outside canon | `{"field": "frame", "value": <frame>}` |
| `merge_vetoed` | §2 | a raw `same_as` refused by a hard veto | `{"veto", "blocking_edges"}`, the guarded-merge receipt's `reason` and `blocking_edges` |
| `invalid_semantics_declaration` | §5 | a declaration the gate would write has a value outside its axis vocabulary | `{"field", "value", "source"}`, `source` ∈ `item` / `attribute_default` / `attr_row` |

The per-edge structural reasons stay prose and byte-identical:
`cycle-forming containment edge: …`, `lateral self-loop: …` and
`merged_self_edge: …`. Tests and hosts match substrings of them, so recoding
them is out of scope.

Under `atomic=True`:
- every new skip aborts the set with `AtomicAbort(cause="gate_skip")`, through
  the existing `_skip_aborting`;
- every new raise is an `exception`-cause abort, through the existing envelope.

## §1 Mechanism attributes are recognized by authority, not by name

A **mechanism attribute** is one whose rows the engine writes about *other*
rows: they change what those rows mean, or record what the gate did to them.
Each has exactly one owning engine component:

| Attribute | Effect | Owner | Owner's mark |
|---|---|---|---|
| `retracts` | hides its target from every read | truth maintenance (`retract`) | status `retracted` |
| `resolved_by` | spends a thunk and names its memo | resolver | status `generated` |
| `canonicalized_from` | replayed into the attribute-alias map on open | the gate's own canonicalization receipt | status `inferred`, and its subject is an assertion whose attribute is the receipt's target |
| `learned_at_wallclock` (r2) | the confirmation stamp `confidence()` recency reads in tracking worlds | the gate's A1 rider (`observe_or_unknown` worlds) | status `observed` |
| `source_valid_from` (r2) | records the coordinate a cursor-authoritative write demoted; no engine read | the gate (INGEST-LATENCY-V2 Win 3) | status `inferred` (no reader to check it) |
| `correction_proposal` (r2) | proposes its subject's supersession; no engine read, but a host promoter retracts the prior row on it | the gate, from the item's `correction` field | status `inferred` (no reader to check it) |

The audit names only the first two. The third was found while writing this
spec. A forged `(a:3 · canonicalized_from · "allegiance->in")` installs a
permanent alias on the next open: `allegiance` becomes containment, and
`(bob · allegiance · place:hall)` puts Bob in the hall. The last three joined
in r2 (pre-review F5; see "r2: review resolutions"): the extractor copies
engine rows from its context into its items, and no host path writes any of
the three as an item.

Rules:
1. **The gate never accepts one as an item.** A canonical attribute in
   `MECHANISM_ATTRIBUTES` is skipped `mechanism_attribute` on every path:
   `ingest`, `ingest_structured`, and a `commit_set` assert op. The real doors
   are `retract` (or the `commit_set` retract op), `resolve`, and, for the
   gate's own rows, the gate itself: its receipt, its tracking stamp, its
   demoted coordinate, and the `correction` field's proposal.
2. **The buffer refuses the wrong mark.** `PatternBuffer.append()` raises
   `RoleViolation` when a `retracts` row is not `retracted`, a `resolved_by`
   row is not `generated`, or (r2) a `learned_at_wallclock` row is not
   `observed`. The check sits in `append()`, not `_insert()`, so `dump.build`
   still replays any old log.
3. **Readers honor only the owner's mark.**
   - `visible()`'s retraction subquery adds `AND r.status = 'retracted'`. The
     two-axis rule is unchanged, and so is the exclusion of retraction rows
     themselves.
   - `Resolver._resolved_marker` and `_fold_over_closure`'s spent-thunk filter
     honor only `generated` markers.
   - `_rebuild_alias_map` honors a receipt only when it is `inferred` and its
     subject is an existing assertion whose attribute equals the receipt's
     target. That is exactly the shape `_ingest_item` writes. It composes with
     GATE-INVERSE-ALIAS-V1 §4's established order, which r2 states correctly
     (r1 said built-ins are applied last; that was wrong, pbr RED): **built-ins
     first, then the replayed receipts in log order (each records the first
     hop applied), keeping only those with this mark, then the inverse keys
     are popped.** A host override such as `type->genre` therefore outranks
     its built-in and survives reopen, a receipt without the mark displaces
     nothing, an old forward `holds->held_by` receipt can never install an
     alias, and `(inverse)` receipts are records, never map entries.
   - (r2) `confidence()`'s confirmation stamp honors only `observed`
     `learned_at_wallclock` rows. `source_valid_from` and
     `correction_proposal` have no engine reader, so rule 1 is their whole
     guard.

`model.py` holds the one definition that the buffer, the readers and the gate
share:
- `MECHANISM_STATUS = {"retracts": "retracted", "resolved_by": "generated",
  "learned_at_wallclock": "observed"}`
- `MECHANISM_ATTRIBUTES = frozenset(MECHANISM_STATUS) | {"canonicalized_from",
  "source_valid_from", "correction_proposal"}`

**Oracle** (today → after):
- Ann's mood is row `a:3`. An item `(a:3 · retracts · "forged")` through
  `ingest_structured`:
  - today it is written as `stated`, and the mood reads unknown;
  - after, it is skipped `mechanism_attribute`, nothing is written, and the
    mood stays `calm`.
- The same item in `commit_set`, including the set `[assert mood, assert
  (<the id that first op mints> · retracts)]`:
  - today both rows land and the new row is born retracted, which bypasses
    ATOMIC-ACTIVATION-V1 §C1;
  - after, `AtomicAbort(gate_skip)` is raised and the log is unchanged.
- `(a:<head+3> · retracts)` written before `a:<head+3>` exists: today that row
  is born invisible. After, the item is skipped and the row is visible when
  minted.
- `(<thunk id> · resolved_by · ["a:1"])`:
  - today `resolve()` serves the world charter's `kind` row with zero model
    calls, and the thunk leaves the thunk table;
  - after, the item is skipped, the thunk stays open, and `resolve()` invents
    with one model call.
- `(a:3 · canonicalized_from · "allegiance->in")`, then reopen: today
  `allegiance` aliases `in`. After, the item is skipped and there is no alias
  after reopening.
- A log carrying forged rows of all three kinds, built with `dump.build` from
  a JSONL fixture: it builds; the target is visible, the thunk open, the alias
  absent.
- `buffer.append(attribute="retracts", status="inferred",
  role=truth_maintenance)` raises `RoleViolation`; with `status="retracted"`
  it appends. Likewise `resolved_by` under the ingestor role (raises) and the
  resolver role (appends).
- A domain row `(person:ann · retracts · "her statement")` is skipped. Today
  it is admitted but never folds (a META attribute classifies EVENT), so
  nothing readable is lost.
- (r2, pbr RED) A world holding a host override `type->genre` (a marked
  receipt), a receipt `is_a->allegiance` with status `stated`, a receipt
  `inside->fealty` whose subject's attribute is not `fealty`, and an old
  marked `holds->held_by` receipt, reopened: `type` aliases `genre`, `is_a`
  and `inside` keep their built-ins, and `holds` is no alias.
- (r2) `(a:3 · learned_at_wallclock · …)`, `(a:3 · source_valid_from · 612)`
  and `(a:3 · correction_proposal · true)` are each skipped
  `mechanism_attribute` through `ingest_structured`, the model path and
  `commit_set` (`AtomicAbort(gate_skip)`); nothing is written. Today each is
  written as `stated`.
- (r2) A tracking world whose fact was stamped at wall time 0 with a one-day
  half-life reads recency 0.25 at day 2. An item copying a stamp at day 2:
  today it is written and recency reads 1.0; after, it is skipped and recency
  stays 0.25. `buffer.append(attribute="learned_at_wallclock",
  status="stated")` raises `RoleViolation`. A log carrying a `stated` stamp,
  built with `dump.build`, confirms nothing: recency 0.25.

**Hosts see:** an item carrying a mechanism attribute is skipped instead of
silently retracting, resolving, aliasing, refreshing a tracking stamp, or
forging the gate's own records.

**Byte-identical:**
- Every engine-written retraction, marker, receipt and side row already
  carries its owner's mark (probe: `retract` writes `retracted`, `resolve`
  writes `generated`; the gate has written its tracking stamps `observed` and
  its demotions and proposals `inferred` since each was introduced).
- The world scan (r2 correction, pre-review F5; r1 said "0 counterexamples in
  216 worlds", which was wrong): on 2026-10-09's copies of construct's 165
  world files, 2 of 127 `canonicalized_from` rows lack the gate's mark. Both
  are `holds->held_by`, status `stated`, in `knows:` frames
  (`emberroad.preset.play`, `ironhold.critic_displaced.play`): rows the model
  copied from its context. They are harmless on reopen: unmarked, they install
  nothing, and `holds` is popped anyway. Every other mechanism row carries its
  mark (234 `retracts`, 124 `resolved_by`, 1,731 `source_valid_from`, 21
  `correction_proposal`; no `learned_at_wallclock` in these fiction worlds);
  the engine's three eval worlds hold none unmarked.
- `retract`, the `commit_set` retract op and `resolve()` are unchanged.

## §2 A raw `same_as` is a guarded merge

A **raw `same_as`** is an item whose attribute is `same_as`. It differs from
the item-level `same_as` field, which only proposes. Today the raw row is
appended as an ordinary row, and `closure()` merges on it:
- It ignores the containment and `distinct_from` vetoes. `(key · same_as ·
  box)` with the key inside the box merges them, and `locate(key)` goes empty.
- It merges canon from a `knows:` frame.
- It stores literal and malformed values silently.

HOST-DISCIPLINE tells hosts to emit `same_as` for a duplicate they minted, so
the row stays legal. It now goes through the one guarded path.

At step 11, an item whose canonical attribute is `same_as` is handled in
three steps:
1. **Value.** It must be a well-formed id string, whatever `value_type` says.
   Otherwise skip `malformed_id`.
2. **Frame.** It must be canon (decision #1). Otherwise skip
   `same_as_not_canon`. That code is this spec's public contract for a
   non-canon `same_as` (pbr ruling (b)): batch C reuses it, unchanged, for
   the item-level `same_as` field.
3. **Merge**, on the raw ids, with evidence `"same_as item"`, through
   `IdentityRegistry`'s guarded path: the same body as the porcelain `merge`
   verb.
   - `guarded_merge`'s logic moves into one private method returning
     `(receipt, rows)`; `guarded_merge` still returns the receipt as today.
   - **No veto logic is copied into the gate.** The audit's P2 already finds
     eight drifted copies.
   - In every outcome but `vetoed`, the item's subject-level rows (aliases, the
     item-level `same_as` proposal) are written as for any item.
   - Outcome `merged`: the merge's four rows replace the main row. They are
     the `identity_merge` event, the `same_as` edge (`inferred`, timeless),
     its `caused_by`, and the evidence.
     - They are returned in append order, so the Receipt lists them.
     - They join the call's classification and all resolve by guardrail to
       EVENT, with zero model calls.
     - Main-row side rows (`source`, `caused_by`, `correction_proposal`)
       attach to the `same_as` edge.
   - Outcome `noop_already_merged` (including `x same_as x`): there is no main
     row and no skip. Main-row side rows have nothing to attach to and are not
     written.
   - Outcome `vetoed`: skip `merge_vetoed`, with nothing written.

The merge's rows are `inferred` whatever the item's status. That is exactly
how the porcelain `merge` verb records a host's merge: one merge shape, one
provenance.

**Oracle:**
- `key in box`, then `(key · same_as · box)`:
  - today the two merge and `locate(key) == []`;
  - after, the item is skipped `merge_vetoed` with `{veto: "containment",
    blocking_edges: ["obj:key·in·obj:box"]}`, the closure is unchanged, and
    `locate(key) == ["obj:box"]`.
- `reject(a, b)`, then `(a · same_as · b)`:
  - today the two merge, and a second `reject` says `conflict_already_merged`;
  - after, the item is skipped `merge_vetoed` with veto `distinct_from`.
- `(x · same_as · y)` with no veto:
  - today it writes one `stated` row stamped by the cursor;
  - after, it writes the four rows that `p.merge(x, y, evidence="same_as
    item")` would write, and `resolve(x) == resolve(y)`.
- `(person:x · same_as · person:z)` in `knows:person:x`: today it merges
  canon. After, it is skipped `same_as_not_canon` and nothing is written.
- Values `"Person:Y"` or `"the same guy"`, or `"person:y"` with an explicit
  `value_type: "literal"`: today these are stored as literals that `closure()`
  ignores. After, they are skipped `malformed_id`.
- An item for a pair already merged, or `x same_as x`: today a redundant row
  is written. After, nothing is written and there is no skip.
- `commit_set`: a vetoed raw `same_as` aborts with `gate_skip`; a passing one
  commits its merge rows with the set.
- `test_source_identity` O14 and `test_moved_event` oracle 11 write passing
  raw `same_as` rows. They must stay green unchanged.

**Hosts see:**
- Vetoed, non-canon and malformed raw `same_as` rows skip with receipts.
- A passing one writes a merge event and an `inferred` edge instead of one
  `stated` row.
- `p.ingest(source=)` stamps `source` on the merge event's two rows, like any
  other new non-meta row.

**Byte-identical:**
- what a passing raw `same_as` does to identity (`closure`, `resolve`);
- the item-level `same_as` proposal;
- `guarded_merge`, `merge`, `confirm` and `retype`.

**Rows already in logs:** construct's worlds held 27 raw (non-`inferred`)
`same_as` rows at r1, 26 of them in a `knows:` frame, for example `person:chen
same_as person:elias_chen` in `knows:person:chen`. On 2026-10-09's copies
(r2) there are 11, 10 in `knows:` frames: `chen`/`elias_chen` (six `thedeep`
files), `beatrice`/`beatrice_harrow`, `eddie`/`eddie_kroll`, and
`aunt_helena` same as itself (two files); the one canon row is
`obj:master_meter`/`obj:meter`.
- They stay, since the log is append-only.
- How identity reads treat them is batch C's job: frame-scoped identity, plus
  the `identity_conflicts()` read for vetoes bypassed before this spec.
- (r2, pre-review F1) The three real pairs were merged *only* by these
  `knows:` rows: each pair also has a canon `maybe_same_as` that was never
  promoted. Under this spec a new such row is refused `same_as_not_canon`,
  and construct's play path ignores `Receipt.skipped`, so a duplicate the
  extractor recognizes in a `knows:` frame would stay unmerged. The ship
  notice tells construct what to do about it.

## §3 Authority is settled before an item's first write

Step 2 runs on the normalized item, before canonicalization, any declaration
or the main row, in this order (r2):
1. **The status grant.**
   - `status` in the ingestor's grant (`stated`/`observed`/`inferred`/
     `assumed`): ingestor authority.
   - Anything else but `generated`: `RoleViolation`, raised through the
     ingestor role's own `check()`, so the message is unchanged.
   - It runs before the frame check (pre-review F4), so an ungranted status
     raises whatever the frame, as on the base engine: `{status: "bogus",
     frame: ""}` is a `RoleViolation`, not a skip.
2. **The frame's shape** (§4): a non-empty string, else `malformed_item`. It
   sits here because letter 029 needs a well-formed frame to judge, so a
   `generated` item with a malformed frame is `malformed_item` too.
3. **`generated`:** today's letter-029 checks (never canon or `knows:*`; a
   resolver must be wired), then resolver authority.
   - A `generated` item carrying `source_doc` or a non-empty `aliases` value (a
     non-empty string, list, tuple or set, whatever its members):
     `RoleViolation`.
   - Their rows would be `generated` rows in canon, because `source` meta and
     `alias` rows carry no frame. Letter 029 forbids that.
   - Batch C may lift the `aliases` half once aliases are written in the item's
     frame.

The other side rows carry fixed engine statuses inside the ingestor's grant,
need no check, and are unchanged: `canonicalized_from`, `source_valid_from`,
`caused_by`, `correction_proposal`, `learned_at_wallclock`, and the proposal
with its evidence.

**Oracle:**
- `generated` into `plot:arc1` with `source_doc`: today the main row is saved,
  then `RoleViolation`. After, `RoleViolation` with the head unchanged. The
  same holds with `aliases: ["the shadow"]`.
- `status` `retracted`, `default` or `bogus` on a first-use attribute with an
  `arity` hint: today an `attr:*` declaration is left behind, then
  `RoleViolation`. After, `RoleViolation` with the head unchanged.
- Plain `generated` into `plot:`, and `generated` with `caused_by` or
  `correction`: unchanged.
- A non-atomic call `[ok item, violating item, ok item]`: the first item
  stays, the violating item writes nothing, and the call raises. The per-row
  contract is unchanged.
- (r2) `{status: "bogus", frame: ""}` and `{status: "bogus", frame: 5}` raise
  `RoleViolation` with the head unchanged; with `status: "stated"`, or
  `generated`, the same frames are `malformed_item`.

**Hosts see:** the same exception types, raised before anything of the item
lands.

**Byte-identical:** every item that passes.

## §4 One `_normalize_item`

`_ingest_item(item, call_frame)` begins with `_normalize_item(item,
call_frame)`. It works on a copy, so the caller's dict is never mutated. That
is step 1:
1. **Not an object:** `malformed_item`, with the item as the record's
   `value`.
2. **Null means absent** for every optional field.
   - A null `frame` takes the call's default frame, else canon. Today it is a
     NOT NULL crash mid-chunk.
   - A null `status` is `stated`. Today it raises `RoleViolation`.
   - A null `aliases` means no aliases. Today it raises `TypeError` after the
     main row.
   - `value` is required but may be null: a null literal, as today.
   - (r2, pre-review F6) A `value_type` of `""` or `False` is absent too, and
     the type is inferred: the base engine read it so (`item.get("value_type")
     or …`). Any other value outside the vocabulary, `0` included, still fails
     at step 3.
3. **The boolean flags** (r2, pre-review F3): `timeless` and `correction`
   read exactly the ints `0` and `1` as false and true, as the base engine
   did. A real bool stays a bool; any other non-bool fails at step 3.
4. **`aliases`:**
   - A string becomes a one-element list. Today it writes one alias per
     character, including `""`.
   - A list or tuple is its members in order; (r2, F3) a set or frozenset is
     its members in sorted order, so the log never depends on hash order.
   - Members that are not non-empty strings are dropped, and so is any other
     value as a whole.
   - Each dropped member gets an `invalid_alias` receipt when the item's rows
     are written. An item skipped for another reason yields exactly one
     record.

**`frame`** must be a non-empty string; otherwise `malformed_item`. A
malformed frame is never defaulted to canon, because that would leak a row
meant for a private frame. (r2, pre-review F4) The check runs at step 2,
right after the status grant (§3), so it never pre-empts an authority
violation.

After step 2 (authority) come the content checks of step 3:
- `entity`, `attribute` and `value` must be present, and the first two
  non-null. Otherwise `malformed_item {"missing": [...]}`.
- `entity` must be a string. Otherwise `malformed_id`.
- `attribute` must be a string that is non-empty after stripping. Otherwise
  `malformed_item`. Today `"  "` stores an attribute `""`.
- `value_type` must be one of `{entity, literal, unresolved, delta}`.
  Otherwise `invalid_field`. Today a bad value raises `ValueError` after a
  first-use declaration is written.
- `timeless` and `correction` must be real bools (after step 1 reads `0`/`1`).
  Otherwise `invalid_field`. Today `"false"` makes a row timeless and writes a
  correction proposal.
- `confidence` must be a finite real number. Otherwise `invalid_field`, with
  the value as authored in `detail`. Today `"high"` is stored, and
  `confidence()` then raises `TypeError`.
  - (r2, pbr ruling (a)) An unambiguous numeric string is coerced first,
    exactly like batch A's time coordinates: `"0.9"` (which SQLite used to
    coerce silently) is stored as `0.9`. It must parse to a finite real;
    bools are invalid; malformed and non-finite strings (`"high"`, `"nan"`,
    `"inf"`) get the normal `invalid_field` receipt. An int past SQLite's
    64-bit range becomes a float, as a time does.
  - One gate helper, `_gate_number`, reads every number an item carries:
    `confidence` here, and the time coordinates at step 9. Batch A's
    `_time_value` is refactored onto it, so the two rules cannot drift.
- An explicit `value_type: "entity"` with a non-string value is
  `malformed_id`. Today `in: 5` is stored and `locate()` returns `[5]`.

Two existing paths change to fit:
- The call-frame fill moves out of `_ingest_body` and `_apply_ops` into
  `_normalize_item`.
- `_apply_moved_coordinate_pass` passes non-object items through untouched,
  so they reach the receipt. Today they raise `AttributeError` in
  `extracted=True` mode.

The audit named string aliases, null `frame`/`aliases` and entity-typed
integers. Six more members of the same class were each reproduced by probe:
non-object items, blank attributes, `value_type`, the two bools, `confidence`
and a null `status`.

**Oracle** (each case also asserts that the rest of the call still ingests):
- `aliases: "the vault"` writes one alias row, `"the vault"`, and
  `by_alias("the vault") == {obj:vault}`.
- `aliases: None` writes no alias rows and no skip.
- `aliases: ["", "  ", 5, "ok"]` writes one alias row and three
  `invalid_alias` records. `aliases: 5` gives one `invalid_alias`, and the main
  row lands.
- `frame: None`:
  - lands in canon, or in the call's `frame=` if given;
  - `generated` with a call frame of `plot:x` lands in `plot:x`;
  - `generated` with no call frame lands in canon, which raises letter 029.
- `frame: 5` or `""` gives `malformed_item`.
- Missing `attribute`, `value` or `entity` gives `malformed_item`. Today it is
  a `KeyError` that ends the chunk with its earlier items committed.
- `entity: 5` gives `malformed_id`. `attribute: 7` or `"  "` gives
  `malformed_item`.
- A bare string item gives `malformed_item`, in both ordinary and
  `extracted=True` mode.
- `in: 5` with `value_type: "entity"` gives `malformed_id`.
- `value_type: "thing"` gives `invalid_field`, and no declaration is left
  behind.
- `timeless: "false"`, `correction: "false"` and `confidence: "high"` each give
  `invalid_field`.
- `status: None` reads as `stated`.
- Under `atomic=True`, `aliases: None` commits, and `aliases: [5]` aborts with
  `gate_skip`.
- (r2, ruling (a)) `confidence` `"0.9"`, `" 0.25 "`, `"1"` and `2**70` are
  stored as floats with no skip; `"high"`, `"nan"`, `"inf"`, `"-inf"`, `""`,
  `True` and `[0.5]` each give `invalid_field` with the authored value.
- (r2, ruling (a)) For each value in a battery (numeric strings, ints, floats,
  an oversize int, text, non-finite strings, `""`, bools, a list, a `$decimal`
  tag), the time path and the confidence path admit or refuse it together,
  store the same number, and receipt the same authored value.
- (r2, F3) `timeless: 1` is timeless, `timeless: 0` is stamped by the cursor,
  `correction: 1` writes the proposal, `correction: 0` does not; `2`, `1.0`
  and `"1"` still give `invalid_field`.
- (r2, F3) `aliases` as a tuple writes its members in order, as a set in
  sorted order; a `generated` item carrying a non-empty set raises (§3).
- (r2, F6) `value_type` `""` or `False` is inferred: `in: "place:hall"`
  locates, `mood: "calm"` is a literal, `in: "Place:Hall"` is still caught by
  §7; `value_type: 0` is still `invalid_field`.

**Hosts see:** bad items skip with receipts instead of raising mid-chunk or
writing garbage. Construct's source build (`game.py`) drops the remainder of
a chunk on any raise today; after this change it keeps the good items.

**Byte-identical:** every well-formed item. Normalization is a no-op on it.
So is every item the base engine read the same way: a numeric-string
`confidence` or time, a `0`/`1` flag, a tuple or set of aliases, an empty or
false `value_type`.

## §5 Semantics declarations are validated

A declaration the gate would write must be in its axis vocabulary:
- `arity` ∈ `ARITIES`
- `relation_family` ∈ `RELATION_FAMILIES`
- `fold_policy` ∈ `FOLD_POLICIES`
- `structural` a real bool

The vocabularies are read from `semantics.py` by reference, through one
`valid_declaration(predicate, value)` there. The rule applies by source:
- **First-use hints on an item, and the host's `attribute_default` output.**
  - An invalid value skips the **whole item** with
    `invalid_semantics_declaration`, writing nothing.
  - Writing the data row anyway would lock the attribute: the buffer refuses
    any declaration once data exists, so the host's intent could never be
    recovered.
  - An invalid `attribute_default` result does not mark the attribute checked.
    Every item on it skips the same way until the host fixes its callback.
  - (r2) The declaration is *planned* before step 8 and written at step 10
    (§7 reads its relation family). Planning writes nothing and marks
    nothing: the callback counts as consulted only once an item on the
    attribute reaches step 10, so an item refused in between (an id-shaped
    typo, a bad time, a cycle) never costs a later item its declaration. The
    base engine asked only items that reached the declaration; the outcome
    is the same, and the callback may be asked again after such a refusal.
- **Manual `attr:<name> · <predicate> · <value>` rows.**
  - The buffer's vocabulary-authority refusal (a core attribute, or data
    already present) still raises `ValueError` first, whatever the value.
  - The gate runs that same check before the value check, keeping authority
    first. It goes through one buffer method shared with `_insert`.
  - A row that passes the authority check but has an invalid value skips.
- **Hints the gate would not write** (the attribute is already declared, or
  core) are ignored, as today.
- **Read side.** `AttributeSemantics.semantics()` ignores a declared value
  that fails `valid_declaration`, and that axis takes its built-in default.
  Only a real `True` is structural.

**Oracle:**
- Hint `arity: "many"`:
  - today it is stored and `allies` folds as functional, so two allies
    conflict, and a correct redeclaration raises forever;
  - after, the item is skipped with `{field: "arity", value: "many", source:
    "item"}` and nothing is written. A later item with `arity: "set_valued"`
    declares it, and two allies coexist.
- `relation_family: "container"` and `fold_policy: "acrue"`: skipped. Today
  both are silently ignored, and a delta row never sums.
- `attribute_default` returning `{"arity": "multi"}`: each item on that
  attribute is skipped with source `attribute_default`, and no declaration is
  written.
- Manual `attr:mood2 · structural · "false"`: today it makes `mood2`
  structural, so its rows classify CONSTITUTIVE. After, it is skipped; with
  `True` it is written.
- A manual declaration on `in`, or after data exists, raises `ValueError` even
  with an invalid value.
- A log carrying `structural: "false"` and `arity: "many"`, built from a JSONL
  fixture: `is_structural` is false and `arity == "functional"`.

**Hosts see:** an invalid declaration skips its item instead of silently
misbehaving forever.

**Byte-identical:**
- every valid declaration;
- construct's `attribute_default`, which returns only valid values;
- the world scan found 0 invalid declarations.

## §6 `p.ingest()` receipts its skips, and a rejected call leaves the cursor where it was

- **`p.ingest()`** sets `Receipt.skipped`: first the extraction call's skips,
  then those of the `source=` stamping call. Each is captured right after its
  own gate call. Today the field is always empty, and the `source=` call
  overwrites `last_skipped`.
- **Cursor.** `p.ingest(at=)` and `p.ingest_structured(at=)` snapshot the
  cursor and the log head before applying `at`.
  - If the call raises, the head has not moved and the buffer is not poisoned,
    the cursor is restored.
  - This subsumes ATOMIC-ACTIVATION-V1 §B4 pin (a).
  - After a partial non-atomic write, the cursor stays at `at`, because the
    rows already written were stamped there.

**Oracle:**
- An extraction yielding `person:/you` and a self-edge: `skipped` lists both
  (`malformed_id`, then the cycle reason). The same holds with `source=`.
- From a cursor at 5, each of these calls leaves the cursor at 5:
  - `classify="bogus", at=99` (today it ends at 99);
  - a generated-into-canon raise with `at=77`;
  - a failing model with `at=42`;
  - `atomic=True` with `classify="inline"` and `at=60`.
- `[ok item, generated-into-canon]` with `at=70`: the cursor stays at 70, and
  the first row's `valid_from` is 70.
- `AtomicAbort` restores the cursor, unchanged.

**Hosts see:** `p.ingest()` receipts list their skips. Construct's atomic
growth path already treats any non-empty `skipped` as a failure. It uses
`commit_set` and `ingest_structured`, which already filled the field.

**Byte-identical:**
- the Receipt's shape;
- every successful call;
- the `ingest_structured` and `commit_set` receipts.

## §7 Malformed ids in the value position of entity-valued predicates

An **entity-valued predicate** is one whose engine readers only ever see
entity values. When such a predicate's value is an id-shaped string that fails
the grammar, the item is skipped `malformed_id`, the same treatment the
subject position already gets.
- The rule applies when the item gave no `value_type` (`""` and `False` count
  as none, r2). An explicit `"entity"` is already caught at step 7.
- **Entity-valued predicates:**
  - the containment family and the lateral family, declared members included,
    via `semantics`;
  - (r2, pre-review F6) an attribute the item's own first-use declaration puts
    in either family: its `relation_family` hint, or the host's
    `attribute_default` output for it;
  - `part_of` and `caused_by`;
  - `maybe_same_as`, `distinct_from` and `aka`.
  - `same_as` belongs to §2.
- (r2, F6) The family is judged as the item's own declaration will leave it.
  §7 runs at step 8, before the declaration is written at step 10, so r1
  missed `{attribute: "stowed_in", value: "Place:Cellar", relation_family:
  "containment"}`: the typo was admitted as a literal, then the attribute was
  declared containment, and the literal won the fold. The fix keeps the order
  (nothing is written before every refusal) and plans the declaration early
  instead (§5). The same reading extends to step 9's per-edge checks, which
  had the same gap: a first-use containment declaration with a self-edge or a
  cycle, or a first-use lateral one with a self-loop, was admitted and then
  declared. Both now skip with their existing reasons.
- **Id-shaped** means matching `^[A-Za-z][A-Za-z0-9_]*:(?!\s)`: a letter-led
  word, a colon, and no whitespace right after it.
  - Id-shaped: `Place:Cellar`, `place:/cellar`, `place:the cellar`, `place:`.
  - Not id-shaped: `repaired: the rival arrives`, `12:30`, `a drawer at home`.

The audit named containment, passage and `part_of`. Two more join:
- `caused_by`, because its side-field form already enforces the grammar.
- The identity predicates, because `distinct_block` and `correlation_set`
  ignore non-entity values, so a malformed anti-merge silently does not exist.

`model.py` gains `ID_RE`, moved from `ingest.py` and `porcelain.py` (which
import it), and `ID_SHAPED_RE`.

**Oracle:**
- Ann is `in place:cellar`, then an item gives `in: "Place:Cellar"`:
  - today it is stored as a literal that wins the fold, so `locate(ann) ==
    []` and the cellar is empty;
  - after, it is skipped `malformed_id` and Ann stays in the cellar.
- `malformed_id` for each of: `in: "place:/cellar"`, `in: "place:the
  cellar"`, `connects_to: "Place:Hall"`, `part_of: "Place:House"`, `held_by:
  "person:Bob"`, `caused_by: "Event:Fire"`, `distinct_from: "Person:B"`.
- Admitted as today: `in: "repaired: the rival arrives"`, `in: "12:30"`,
  `mood: "Note:see"`, and `in: "Place:Cellar"` with an explicit `value_type:
  "literal"`.
- (r2, F6) With nothing declared: `stowed_in: "Place:Cellar"` with
  `relation_family: "containment"`, `links_to: "Place:Yard"` with
  `relation_family: "lateral"`, and `lodged_in: "Place:Cellar"` where the
  host's `attribute_default` declares `lodged_in` containment each give
  `malformed_id`. `tucked_in: <itself>` (containment hint) and `lodged_in:
  <itself>` (callback) give the cycle reason, and `opens_on: <itself>`
  (lateral hint) the self-loop reason. Nothing is written and nothing is
  declared; a later good `lodged_in` item still gets the callback's
  declaration and locates its subject.

**Hosts see:** a value-position id typo is receipted instead of silently
relocating its subject.

**Byte-identical:**
- every well-formed id;
- every literal that is not id-shaped, and every explicit literal;
- every other attribute;
- the world scan found 0 id-shaped malformed values on these predicates.

## §8 Bookkeeping rows never reach the model

`Classifier._guardrails` gains one final rule. A row that no existing
guardrail decides, and whose subject is an assertion id (`^a:[0-9]+$`,
`model.ASSERTION_ID_RE`), is classified `(STATE, 0.5)` with no model call.
That is the verdict `classify="rules"` already gives it.
- Rows already decided keep their guardrail: META attributes on an assertion
  subject stay EVENT.
- A host id merely shaped like the namespace (`a:artifact`) is not an
  assertion id and is classified as today.
- EVENT, the auditor's suggestion, is rejected. It would erase host-authored
  assertion metadata (whitepaper §3.2's own `(A1 · last_confirmed · …)`) from
  `state()`, a change no reader needs.

**Oracle:**
- A tracking world with five tracked writes, `classify="defer"`, then
  `classify_all()`: today 10 per-row model calls, 5 of them for
  `learned_at_wallclock` rows. After, 5 calls, and the bookkeeping rows are
  `STATE 0.5`.
- `seal_build(model=True)`: today the batch prompt lists `a:3 ·
  learned_at_wallclock · …`. After, it has no `a:N` line.
- The proposal's evidence row makes no model call.
- Host metadata `(a:3 · last_confirmed · 12.0)`: one model call today, none
  after. `state("a:3", "last_confirmed")` still serves it.
- A rules-mode world's sidecar is byte-identical.

The inline path classifies only main rows, so the paid calls happen on sweeps
(`classify_all`, `rebuild`, `seal_build(model=True)`), not on each inline
write. Measured on construct's worlds: of 4,464 `evidence` rows, 2,760 were
judged by the model, 1,234 of them as CONSTITUTIVE.

**Hosts see:** fewer model calls on sweeps. A bookkeeping row's sidecar
verdict becomes `STATE 0.5` when it is next classified. No read uses those
verdicts, because every derived read skips assertion subjects.

**Byte-identical:** all folds, and every row a guardrail already decides.

## Coordination with the other audit specs

- **Batch A (FOLD-CORRECTNESS-V1)** owns time-value validation
  (`invalid_valid_time`, its §6). It introduced `SkipRecord.detail` and
  `to_dict()` (merged; this spec uses both).
  - This spec leaves `valid_from`/`valid_to` validation where A put it. r2
    moves A's `_time_value` onto the one gate helper `_gate_number` that
    `confidence` shares (pbr ruling (a)); A's tests pass unchanged. One
    receipt changes, toward A's own rule: a non-finite numeric string
    (`"inf"`) now carries the string as authored in `detail`, where A carried
    the parsed float.
- **GATE-INVERSE-ALIAS-V1** (merged) keeps its swap immediately after
  canonicalization, once `value_type` is decided: §0 step 5 (r2 numbers it).
  - §4's checks guarantee the swap never sees a non-string value.
  - §1's receipt mark composes with its §4 rebuild order (built-ins →
    marked receipts → pop the inverse keys).
  - Aliases and the item-level `same_as` proposal stay with the original
    subject; this spec's `invalid_alias` receipts name it too.
- **Batch C (FRAME-SCOPED-IDENTITY-V1):**
  - reuses `same_as_not_canon` for the item-level `same_as` field;
  - scopes identity reads and writes;
  - may relax §3's `aliases` rule once aliases are written in-frame.
  - Its `identity_conflicts()` read surfaces raw `same_as` rows that bypassed
    the vetoes before this spec.
- **Batch E:** a durability pin (`attr:<name> · durability`) should validate
  through §5's `valid_declaration` and skip with
  `invalid_semantics_declaration`.

## Non-goals

- Literal values on entity-valued predicates beyond the id-shaped case (open
  question 1).
- Recoding the legacy prose skip reasons.
- An MCP schema for `items` (a surfaces P2 item).
- `world_defining` pins, `source` pointers, and host `caused_by` or metadata
  rows on assertion ids. Hosts author these by design, and they stay
  item-writable.
- Validating `delta` values or thunk specs.
- Any rewrite of existing rows. Forged rows from before this spec are
  neutralized on read (§1); raw `same_as` rows from before it are batch C's.
- Item-level frames for the `source`, `alias` and `correction_proposal` side
  rows (batch C).

## Migration and notice

No log rewrite and no schema change: old logs rebuild and reopen unchanged.

Blast radius, measured read-only on construct's 213 worlds and the engine's
three eval worlds (334,785 rows) at r1:
- 2 forged mechanism rows (r2 correction, pre-review F5: r1 said 0). Both
  are `canonicalized_from` receipts (`holds->held_by`, status `stated`, in
  `knows:` frames) that the model copied from its context; harmless on
  reopen (§1). Re-measured on 2026-10-09's 165 world files;
- 0 invalid declarations;
- 0 runs of one-letter aliases (the string-alias bug);
- 0 id-shaped malformed structural values;
- 27 raw `same_as` rows at r1, 11 on 2026-10-09 (§2): untouched, batch C's;
- 4,501 bookkeeping `evidence` rows (§8): verdicts change only when
  reclassified, and nothing reads them;
- 74 literal values on structural predicates, 73 of them in construct's
  worlds (open question 1).

r2 reopened copies of eleven construct worlds (the six `thedeep*` files,
`bodycase.critic.play`, `emberroad.preset.play`,
`ironhold.critic_displaced.play`, `latch.preset.play`,
`final_exhaustive.final.ep.checkpoint`) under main and under this branch: the
alias map, the visible rows, identity resolution, `locate()` for every entity,
`state()` for every (entity, attribute, frame) key (12,419 keys), the thunk
table, attribute semantics, the proposals and the head are identical, and
nothing was written on open.

Docs on ship:
- ADOPTION: the new MUST/NEVER items; the `Receipt.skipped` vocabulary;
  remove the `p.ingest()` NOTE; the cursor rule; raw `same_as` is a guarded
  merge.
- LEXICON: **mechanism attribute** and **skip receipt**.
- WHITEPAPER §25.6: one bullet, and the §25.9 amendment row A20 (r2: both are
  on the branch, with ADOPTION and LEXICON, so it merges ready).
- `specs/STATUS.md` (at the merge, with the README test count).

Ship notice to construct, listing:
- §2: merge rows replace the raw `same_as` row;
- §4: fewer chunk-aborting raises;
- §6: `p.ingest` receipts now list skips;
- §8: fewer model calls on sweeps;
- (r2, pre-review F1) **identity in `knows:` frames.** 10 of construct's 11
  raw `same_as` rows are in `knows:` frames, and they were the only thing
  merging three real duplicates (`thedeep`: `person:chen`/`person:elias_chen`;
  `latch`: `person:beatrice`/`person:beatrice_harrow`; `final_exhaustive`:
  `person:eddie`/`person:eddie_kroll`). Each pair also has a canon
  `maybe_same_as` that was never promoted. From this spec on, a new raw
  `same_as` outside canon is refused with `same_as_not_canon` (`detail:
  {field: "frame", value: <frame>}`), and construct's play path ignores
  `Receipt.skipped`, so such a duplicate would silently stay split. Route
  those receipts to identity: `p.confirm(entity, value)` when a canon
  proposal for the pair exists, else `p.merge(entity, value, evidence=…)`
  (both are guarded by the hard vetoes); or have the extraction stage emit
  identity rows in canon. Batch C will refuse the item-level `same_as` field
  outside canon with the same code.
- (r2, pre-review F2) **a test patch to update.** `tests/test_atomic_swap.py`
  patches the private `Ingestor._ingest_item(self, it)`. This spec gives it a
  second parameter (`_ingest_item(self, item, call_frame=None)`: the call's
  default frame), so the patched function receives an extra argument; the
  `TypeError` surfaces as an `AtomicAbort` inside the unit and the fault never
  fires. Production code is unaffected. The fix is one line, `def item(self,
  it, *a, **kw):`, and passing the extras on (`return real_item(self, it, *a,
  **kw)`) keeps a framed `commit_set` right. Checked on a copy: 34/34 pass on
  main, the first case fails on this branch unpatched, and 34/34 pass with
  the fix (with the def line alone too, since every current `commit_set` call
  uses the default frame).

## Tests

A new `tests/test_gate_authority.py` holds one test per oracle, by section. It
also holds two suite-level checks:
- `SKIP_REASONS` membership for every reason the suite records;
- byte-identity: a fixed corpus of well-formed items dumps identically before
  and after this spec, checked against a committed JSONL fixture.

Any existing test that encodes a wrong answer is updated in the same commit,
citing the audit finding. None is expected: `test_source_identity` O14 and
`test_moved_event` oracle 11 assert outcomes that a guarded merge preserves.
The full suite (577 tests at r1's base, all green) stays green. r2: main
carries 637 tests (batch A and GATE-INVERSE-ALIAS-V1 merged); r1 adds 70 and
r2 23 more, one per r2 oracle, under "r2: review resolutions" in the same
file: 730 collected, 727 passed and 3 skipped, as on main.

## Open questions for Kabe (each with a default)

1. **Should every literal on an entity-valued predicate be refused?**
   - `in: "stone"` drops its subject out of the containment tree, exactly as
     `"Place:Cellar"` does. Construct's worlds hold 73 such rows in 44 worlds,
     for example `in: "null"` and `connects_to: "ops"`.
   - *Default:* refuse only id-shaped values now (§7), and revisit with
     construct, since some literals may be deliberate coarse places.


## Build notes for pbr (gated implementation on `impl/gate-authority-v1`)

- **One inconsistency to rule on** (r1; ruled, see r2). §4 refused a
  numeric-string `confidence` (`"0.9"`, which SQLite used to coerce
  silently). FOLD-CORRECTNESS-V1 r3 §6 *coerces* numeric-string times for the
  same reason.
  - pb recommended coercing here too: one rule at the gate, "an unambiguous
    numeric string is a number", applied to times and to confidence.
  - pbr ruled to coerce, through one shared helper. r2 builds it (§4).
- **Implementer's readings.**
  - §2 follows the oracle over the prose: the value must be a well-formed id
    *given as an entity*.
  - §2 side rows attach every main-row side row (including
    `canonicalized_from`, `source_valid_from` and `learned_at_wallclock`) to
    the `same_as` edge.
  - §3 judges "carries aliases" on what the host sent.
  - §5's declarability check (refused on core attributes, or once data exists)
    also runs first for item hints and `attribute_default`.
- **Lexicon.** "skip receipt" and "mechanism attribute" were added before their
  second use.

## r2: review resolutions (2026-10-09)

r1 went to pbr and to an internal pre-review. pbr returned **RED on one
point** (§1's alias-map prose) and **two rulings**; the pre-review returned
**GREEN-with-nits** with six findings (F1–F6). r2 resolves each as below.
Meanwhile batch A (FOLD-CORRECTNESS-V1 r3) and GATE-INVERSE-ALIAS-V1 r1.2 were
pbr-GREEN and merged to main, so r2 is rebased onto main first.

**Rebase onto main.** The branch's commits keep their messages. Conflicts
were in `ingest.py` (`_rebuild_alias_map`, `_ingest_item`, the id grammar's
home), `tmaint.py` (the `AtomicAbort.skipped` docstring) and nothing else.
- `SkipRecord` is batch A's shape (`to_dict()`, optional `detail`, emitted
  only when set), already shared by main.
- The alias rebuild keeps the inverse-alias spec's order (built-ins → replayed
  receipts → pop the inverse keys), with §1's receipt mark applied inside it.
- The inverse swap sits right after `value_type` is decided and before every
  later check; r2 numbers it §0 step 5, so the gate has thirteen steps.
- Aliases, the item-level `same_as` proposal and their skip receipts use the
  swap's original subject.

**pbr RED (§1).** r1's §1 said built-ins are applied last in the alias-map
rebuild. That contradicts GATE-INVERSE-ALIAS-V1 §4 and its r1.2 fix, and would
discard a host override such as `type->genre` on reopen. §1 now states the
established order, with the receipt mark retained inside it. The code
already matched after the rebase; one oracle test pins the composed order.

**pbr ruling (a): numeric strings.** An unambiguous numeric-string
`confidence` is coerced before validation, exactly like batch A's time
coordinates. One gate helper, `_gate_number`, serves both, and A's
`_time_value` is refactored onto it, so the two cannot drift: a finite real,
never a bool; a numeric string becomes a float; an int past 64 bits becomes a
float; anything else is `invalid_field` (or `invalid_valid_time`) with the
value as authored in `detail`. A's tests pass unchanged; the one change to A's
receipts is that a non-finite numeric string's `detail` is now the authored
string, not the parsed float. Three oracle tests, one of them the
shared-rule battery.

**pbr ruling (b): `same_as_not_canon`.** For a non-canon `same_as`, raw (here)
and side-key (batch C), the receipt reason is `same_as_not_canon`, this spec's
public contract. Nothing in B said otherwise; §2 now says so explicitly. No
code change.

**F1 (ship notice).** Construct's `knows:`-frame raw `same_as` rows were the
only thing merging three real duplicates; under §2 new ones are refused with
`same_as_not_canon` and construct ignores `skipped`. The ship notice
("Migration and notice") tells construct to route those receipts to
`confirm`/`merge`, or to emit identity in canon. §2's "Rows already in logs"
records the counts.

**F2 (ship notice).** Construct's `tests/test_atomic_swap.py` patches the
private `Ingestor._ingest_item(self, it)`; §4's new `call_frame` parameter
breaks that test (not production). The notice gives the one-line fix, verified
on a copy (34/34).

**F3 (decided: as the base engine read them).** `timeless` and `correction`
accept exactly the ints `0`/`1` as false/true; bools stay bools; every other
non-bool still skips `invalid_field`. `aliases` given as a tuple is its
members in order and as a set its members in sorted order (deterministic
logs). §4; two oracle tests.

**F4 (decided: authority first).** The status grant runs before the frame's
shape check, so `{status: "bogus", frame: ""}` raises `RoleViolation`, as on
the base engine, instead of skipping `malformed_item`. The frame check moved
from step 1 into step 2, between the status grant and letter 029 (which needs
a well-formed frame). §3, §4; one oracle test.

**F5 (corrected, and the mechanism set widened).** r1's "0 forged mechanism
rows" was wrong: two forged `canonicalized_from` rows exist in construct's
worlds (model-copied into `knows:` frames, status `stated`, both
`holds->held_by`, harmless on reopen). §1 and "Migration and notice" now say
so, with the 2026-10-09 counts. The pre-review asked which other engine-only
rows an item could forge, since the extractor copies engine rows from its
context. Investigated (specs, ADOPTION, HOST-DISCIPLINE, tests, construct's
code):
- `learned_at_wallclock`: written only by the gate's A1 rider (`observed`);
  `confidence()` recency reads any visible stamp, so a copied one refreshes a
  stale fact. TRACKING-MODE-V1 has no host path that writes it (the
  whitepaper calls it "a gate invariant with a test, not a convention";
  ADOPTION says to let the gate stamp it; backdating is done with the
  injected clock). **Refused as an item**, plus §1's rules 2 and 3: the
  buffer refuses a stamp that is not `observed`, and the confidence reader
  honors only `observed` stamps.
- `source_valid_from`: written only by the cursor-authoritative demotion
  (`inferred`); no engine read. INGEST-LATENCY-V2 has the host promote it to
  a *different* typed attribute (`year`/`era`); no host path writes it.
  **Refused as an item.**
- `correction_proposal`: written only by the gate from the item's
  `correction` field (`inferred`); no engine read, but a host promoter (the
  eval harness's `promote_corrections`) retracts the prior row on any visible
  proposal. HOST-DISCIPLINE's route is the `correction` field. **Refused as
  an item.**
- Not refused: `source` and `world_defining` (sanctioned host items, this
  spec's non-goals; `p.ingest(source=)` writes `source` through the gate);
  `justified_by` (construct writes it as an item on `beat:` subjects in
  `plot:main`); `evidence` (written by the identity verbs, read only as text,
  and a plausible domain attribute); `superseded_by` (no writer or reader
  anywhere).

`MECHANISM_STATUS` gains `learned_at_wallclock: observed`;
`MECHANISM_ATTRIBUTES` gains the three. The scan found no unmarked row of any
of them. Two oracle tests (the item refusals on every path; the tracking
stamp end to end).

**F6 (fixed by planning early; `value_type` falsy is absent).** §7 ran
before the declaration step, so an item declaring `relation_family:
containment` with an id-shaped typo value slipped through, and step 9's
per-edge checks had the same gap for a first-use containment or lateral
declaration with a self-edge, cycle or self-loop. r2 keeps the write order
and plans the item's first-use declaration (hints, else `attribute_default`)
before step 8, without writing or marking; steps 8 and 9 judge the family the
item's own declaration will leave, and the callback counts as consulted only
when an item reaches step 10 (§5, §7). Separately, `value_type` given as `""`
or `False` is absent and inferred, as on the base engine (§4). Two oracle
tests.

**Renumbering.** `_ingest_item`'s step comments and §0 now number thirteen
steps (the inverse swap is step 5); §2's merge is step 11.

**Docs.** The whitepaper's §25.9 row **A20** and §25.6 bullet, ADOPTION's
items and the LEXICON's widened **mechanism attribute** ship on the branch,
so it merges ready; `specs/STATUS.md` and the README count follow the merge,
as for A18/A19.

**Checks.** Full suite: 727 passed, 3 skipped (730). Eleven construct worlds
read identically under main and r2 ("Migration and notice").
