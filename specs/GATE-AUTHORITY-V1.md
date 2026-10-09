# GATE-AUTHORITY-V1: the gate decides by authority, and every refusal is a receipt

**Status:** DRAFT r1 (2026-10-08). Batch B of `docs/AUDIT-2026-10.md`; Kabe
approved the five batches. Next: pbr review, then a gated build. Every case
below was reproduced on `polish/audit-2026-10` (212754f) with a probe before it
was specified. Blast radius was measured read-only on construct's 213 world
files and the engine's three eval worlds (334,785 rows).

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

`_ingest_item` after this spec, in order. Steps marked *existing* keep their
code and their relative order: the audit's do-not-touch ordering is authority
raises first, then the malformed-id check, identity, intervals, per-edge skips.

1. **Normalize** (§4): shape only, no write.
2. **Authority** (§3): raises, no write. These are the existing letter-029
   checks, moved up. They read only `status`, `frame` and side-field presence,
   so for any item canonicalization accepts, running them first changes no
   outcome.
3. **Content checks** (§4): skips.
4. **Canonicalize** the attribute. *Existing.* GATE-INVERSE-ALIAS-V1 §2's
   swap sits immediately after this step.
5. **Mechanism attribute** (§1): skip.
6. **Malformed-id gate** on the raw ids. *Existing.*
7. **Id-shaped value on an entity-valued predicate** (§7): skip.
8. Identity resolution, decay half-life, time values (batch A §6), interval
   invariants, per-edge structural skips. *Existing.*
9. **Declarations** (§5): validated, then written.
10. **Main row**, or for `same_as` the guarded merge (§2).
11. Side rows, in the *existing* order. Dropped aliases are receipted here
    (§4).
12. Classification. *Existing*: §8 changes the classifier, not the gate.

With this order, everything that can refuse an item (as opposed to one of its
side rows) runs before the item's first write. What can still fail afterwards
is infrastructure (a database or clock error), which `atomic=True` already
covers.

**Skip vocabulary.** A `SkipRecord` is `{entity, attribute, value, reason[,
detail]}`.
- `reason` is a fixed code.
- `detail` is batch A's field, emitted only when set. It carries the offending
  input when that input is not the row's value.
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
| `invalid_valid_time` | batch A §6 | a time coordinate that is not a finite number | the value |
| `malformed_item` | §4 | not an object; `entity`/`attribute`/`value` absent; `attribute` or `frame` not a non-empty string | `{"missing": [...]}` or `{"field", "value"}`; none for a non-object |
| `invalid_field` | §4 | `value_type` outside its vocabulary; `timeless`/`correction` not a real bool; `confidence` not a finite number | `{"field", "value"}` |
| `invalid_alias` | §4 | one `aliases` member (or the whole field) that is not a non-empty string; the item's other rows still land | — |
| `mechanism_attribute` | §1 | the canonical attribute is `retracts`, `resolved_by` or `canonicalized_from` | — |
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

A **mechanism attribute** is one whose rows change what *other* rows mean.
Each has exactly one owning engine component:

| Attribute | Effect | Owner | Owner's mark |
|---|---|---|---|
| `retracts` | hides its target from every read | truth maintenance (`retract`) | status `retracted` |
| `resolved_by` | spends a thunk and names its memo | resolver | status `generated` |
| `canonicalized_from` | replayed into the attribute-alias map on open | the gate's own canonicalization receipt | status `inferred`, and its subject is an assertion whose attribute is the receipt's target |

The audit names only the first two. The third was found while writing this
spec. A forged `(a:3 · canonicalized_from · "allegiance->in")` installs a
permanent alias on the next open: `allegiance` becomes containment, and
`(bob · allegiance · place:hall)` puts Bob in the hall.

Rules:
1. **The gate never accepts one as an item.** A canonical attribute in
   `MECHANISM_ATTRIBUTES` is skipped `mechanism_attribute` on every path:
   `ingest`, `ingest_structured`, and a `commit_set` assert op. The real doors
   are `retract` (or the `commit_set` retract op), `resolve`, and, for
   receipts, the gate itself.
2. **The buffer refuses the wrong mark.** `PatternBuffer.append()` raises
   `RoleViolation` when a `retracts` row is not `retracted` or a `resolved_by`
   row is not `generated`. The check sits in `append()`, not `_insert()`, so
   `dump.build` still replays any old log.
3. **Readers honor only the owner's mark.**
   - `visible()`'s retraction subquery adds `AND r.status = 'retracted'`. The
     two-axis rule is unchanged, and so is the exclusion of retraction rows
     themselves.
   - `Resolver._resolved_marker` and `_fold_over_closure`'s spent-thunk filter
     honor only `generated` markers.
   - `_rebuild_alias_map` honors a receipt only when it is `inferred` and its
     subject is an existing assertion whose attribute equals the receipt's
     target. That is exactly the shape `_ingest_item` writes. It composes with
     GATE-INVERSE-ALIAS-V1 §4: built-ins are applied last, and `(inverse)`
     receipts are records, never map entries.

`model.py` holds the one definition that the buffer, the readers and the gate
share:
- `MECHANISM_STATUS = {"retracts": "retracted", "resolved_by": "generated"}`
- `MECHANISM_ATTRIBUTES = frozenset(MECHANISM_STATUS) | {"canonicalized_from"}`

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

**Hosts see:** an item carrying one of the three attributes is skipped
instead of silently retracting, resolving or aliasing.

**Byte-identical:**
- Every engine-written retraction, marker and receipt already carries its
  owner's mark (probe: `retract` writes `retracted`, `resolve` writes
  `generated`).
- The world scan found 0 counterexamples in 216 worlds.
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

At step 10, an item whose canonical attribute is `same_as` is handled in
three steps:
1. **Value.** It must be a well-formed id string, whatever `value_type` says.
   Otherwise skip `malformed_id`.
2. **Frame.** It must be canon (decision #1). Otherwise skip
   `same_as_not_canon`.
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

**Rows already in logs:** construct's worlds hold 27 raw (non-`inferred`)
`same_as` rows. 26 of them are in a `knows:` frame, for example `person:chen
same_as person:elias_chen` in `knows:person:chen`.
- They stay, since the log is append-only.
- How identity reads treat them is batch C's job: frame-scoped identity, plus
  the `identity_conflicts()` read for vetoes bypassed before this spec.

## §3 Authority is settled before an item's first write

Step 2 runs on the normalized item, before canonicalization, any declaration
or the main row:
- `status` in the ingestor's grant (`stated`/`observed`/`inferred`/`assumed`):
  ingestor authority.
- `generated`: today's letter-029 checks (never canon or `knows:*`; a resolver
  must be wired), then resolver authority.
- Anything else: `RoleViolation`, raised through the ingestor role's own
  `check()`, so the message is unchanged.
- A `generated` item carrying `source_doc` or a non-empty `aliases` value (a
  non-empty string or list, whatever its members): `RoleViolation`.
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
3. **`frame`** must be a non-empty string; otherwise `malformed_item`. A
   malformed frame is never defaulted to canon, because that would leak a row
   meant for a private frame.
4. **`aliases`:**
   - A string becomes a one-element list. Today it writes one alias per
     character, including `""`.
   - Members that are not non-empty strings are dropped, and so is a non-list,
     non-string value as a whole.
   - Each dropped member gets an `invalid_alias` receipt when the item's rows
     are written. An item skipped for another reason yields exactly one
     record.

After step 2 (authority) come the content checks of step 3:
- `entity`, `attribute` and `value` must be present, and the first two
  non-null. Otherwise `malformed_item {"missing": [...]}`.
- `entity` must be a string. Otherwise `malformed_id`.
- `attribute` must be a string that is non-empty after stripping. Otherwise
  `malformed_item`. Today `"  "` stores an attribute `""`.
- `value_type` must be one of `{entity, literal, unresolved, delta}`.
  Otherwise `invalid_field`. Today a bad value raises `ValueError` after a
  first-use declaration is written.
- `timeless` and `correction` must be real bools. Otherwise `invalid_field`.
  Today `"false"` makes a row timeless and writes a correction proposal.
- `confidence` must be a finite real number. Otherwise `invalid_field`. Today
  `"high"` is stored, and `confidence()` then raises `TypeError`.
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

**Hosts see:** bad items skip with receipts instead of raising mid-chunk or
writing garbage. Construct's source build (`game.py`) drops the remainder of
a chunk on any raise today; after this change it keeps the good items.

**Byte-identical:** every well-formed item. Normalization is a no-op on it.

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
- The rule applies when the item gave no `value_type`. An explicit `"entity"`
  is already caught at step 6.
- **Entity-valued predicates:**
  - the containment family and the lateral family, declared members included,
    via `semantics`;
  - `part_of` and `caused_by`;
  - `maybe_same_as`, `distinct_from` and `aka`.
  - `same_as` belongs to §2.
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
  (`invalid_valid_time`, its §6). It also introduces `SkipRecord.detail` and
  `to_dict()`.
  - This spec uses both and leaves `valid_from`/`valid_to` alone.
  - Whichever spec lands first introduces `detail` and `to_dict()`,
    byte-identically.
- **GATE-INVERSE-ALIAS-V1** keeps its swap immediately after canonicalization
  (§0 step 4).
  - §4's checks guarantee the swap never sees a non-string value.
  - §1's receipt backstop composes with its §4.
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
three eval worlds (334,785 rows):
- 0 forged mechanism rows;
- 0 invalid declarations;
- 0 runs of one-letter aliases (the string-alias bug);
- 0 id-shaped malformed structural values;
- 27 raw `same_as` rows (§2): untouched, batch C's;
- 4,501 bookkeeping `evidence` rows (§8): verdicts change only when
  reclassified, and nothing reads them;
- 74 literal values on structural predicates, 73 of them in construct's
  worlds (open question 1).

Docs on ship:
- ADOPTION: the new MUST/NEVER items; the `Receipt.skipped` vocabulary;
  remove the `p.ingest()` NOTE; the cursor rule; raw `same_as` is a guarded
  merge.
- LEXICON: **mechanism attribute** and **skip receipt**.
- WHITEPAPER §25.6: one bullet.
- `specs/STATUS.md`.

Ship notice to construct, listing:
- §2: merge rows replace the raw `same_as` row;
- §4: fewer chunk-aborting raises;
- §6: `p.ingest` receipts now list skips;
- §8: fewer model calls on sweeps.

## Tests

A new `tests/test_gate_authority.py` holds one test per oracle, by section. It
also holds two suite-level checks:
- `SKIP_REASONS` membership for every reason the suite records;
- byte-identity: a fixed corpus of well-formed items dumps identically before
  and after this spec, checked against a committed JSONL fixture.

Any existing test that encodes a wrong answer is updated in the same commit,
citing the audit finding. None is expected: `test_source_identity` O14 and
`test_moved_event` oracle 11 assert outcomes that a guarded merge preserves.
The full suite (577 tests on this branch, all green) stays green.

## Open questions for Kabe (each with a default)

1. **Should every literal on an entity-valued predicate be refused?**
   - `in: "stone"` drops its subject out of the containment tree, exactly as
     `"Place:Cellar"` does. Construct's worlds hold 73 such rows in 44 worlds,
     for example `in: "null"` and `connects_to: "ops"`.
   - *Default:* refuse only id-shaped values now (§7), and revisit with
     construct, since some literals may be deliberate coarse places.
