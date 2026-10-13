# PERSON-ROLES-V1: a person is a person for life; what they are at a time is a role

**Status:** r1.1. It answers pbr's r1 RED (P1: a distinct gate reclassification receipt, never `canonicalized_from`; P2: the synthesized `kind = person` is `inferred`). It also takes construct's shape read (m9a8701: no role in force answers `unknown`). For pbr review. Author: pb, 2026-10-13.
**Source:** roadmap R49 (construct m02bdb6). Kabe's answer on gate g9c3792 (2026-10-13), in his
words: "imagine a character whose spans a story of a lifetime there may be different erad of that
character they may be a prisoner, one chapter and a hero the next, so build an elegant structure
accordingly." My reading, recorded on the gate:
- a person's kind is `person`, fixed for life;
- what they are at a time (prisoner, hero, a father) is a separate **role**. A role is
  time-indexed, and several roles can hold at once;
- so a life reads as overlapping **eras** on the valid-time axis, not as one label;
- a change of role never splits a person into two.

## Need

Both extraction prompts (`ingest.py`, `_EXTRACT_RULES_FULL` and `_EXTRACT_RULES_LEAN`) say only
"'kind' for what a thing is". So a person comes out as `kind = condemned man` in one chapter and
`kind = person` (or `hero`) in another. Two things then break:

1. **Identity.** `kind` folds as one structural key. Two ids for the same man, one `condemned man`
   and one `person`, are a `kind_conflict`, and the auto-gate never merges them. Construct's run 8
   stopped on exactly this ("Tomas Breck" vs "Breck"). Construct asked for R49 so those pairs
   become `alias_not_specific` and can go to R48's merge gate.
2. **Time.** One person's kind rows disagree across chapters, so the fold calls the key
   conflicted. The story's actual shape is lost: prisoner first, hero later.

## The shape

Three parts. None changes an existing world.

### 1. `role`: built-in semantics

- `role` joins the built-in vocabulary as **set-valued** (`SET_VALUED_ATTRIBUTES`). A person can be
  a prisoner and a father at once.
- Its durability is left to the classifier, as for any domain attribute. The expected class is
  STATE, which changes over time.
- Each role row carries its own `valid_from`, and `valid_to` when the text ends it.
- **Reads need no new verb.**
  - `state(person, "role", as_of=t)` answers the roles that hold at `t`, as `values`.
  - `facts(frame, entity=person)` lists every role row with its interval.
  - An era is one role's span. It is derived from the rows and never stored (P3: derive, don't
    store).
- A host may still declare `role` differently, or pin its durability. The usual declaration rules
  apply.

### 2. The ingest gate moves a person's non-person kind into `role`

This is attribute canonicalization at the gate, the place CLAUDE.md's hazard rule names (the fold
key must never fragment). It is deterministic, so it holds however the model answers.

- **When.** An item whose attribute canonicalizes to `kind`, with a literal value, on a **person
  subject**, where the value (stripped, lowercased) is not `person`.
  - A person subject is one whose id, or a member of its identity closure as of the item, is in the
    `person:` namespace;
  - or one whose canon `kind` already folds to `person` before the item.
- **What is written.**
  - The row is written as `role = <the value, as given>`, in the item's frame, with the item's
    status, `valid_from`, `valid_to` and source. The text did say this about the person, so the
    status is kept.
  - *(r1.1, pbr P1)* **This is a reclassification, not canonicalization.** `canonicalized_from` is
    a durable, global attribute-alias declaration: `_rebuild_alias_map` replays it on reopen. A
    contextual move (only a person's non-person literal kinds) is not a global alias, so it must
    never be recorded as one.
    - The move writes its own gate-owned side row on the role row:
      `<role row id> · reclassified_from · "kind"`, `inferred`, in the META set (hidden from
      reads, like the other receipts).
    - It is never read by `_rebuild_alias_map` or any alias machinery. The alias map and
      `canonical_attribute` are unchanged by R49.
    - A real spelling normalization still gets its `canonicalized_from` receipt as today. An item
      `type -> kind`, then moved to `role`, carries both: `canonicalized_from` (`type -> kind`,
      the global spelling) and `reclassified_from: "kind"` (the contextual move).
- **Kind `person`.** If the subject has no `kind` row valued `person` in that frame, the gate also
  writes one, timeless, in the same frame.
  - *(r1.1, pbr P2)* It is **`inferred`**, not the item's status: the input didn't state it.
    It is derived from the `person:` namespace or the already-folded kind. Only the ingestor writes
    it, so the role-authority matrix holds.
  - Its derivation receipt is `<kind row id> · derived_by · "person_subject"`: `inferred`,
    gate-owned, META and never replayed.
  - The `person:` namespace already says what the subject is; this row says it in the key identity
    reads. Without it, a pair would decline on `kind_absent` instead of reaching
    `alias_not_specific`.
  - It is written once per subject and frame.
- **What is unchanged.**
  - An entity-valued kind (`kind -> obj:some_type`) on a person is left alone, and logged at
    `WARNING`. V1 has no rule for it.
  - Every non-person subject keeps its kind exactly as given: an object's, a place's, an event's.
    **This is a test:** `obj:lamp · kind · brass lamp` is stored as given.
  - `kind = person` is stored as given.
- **The receipts are META.** `reclassified_from` and `derived_by` join `META_ATTRIBUTES`. They are
  hidden from reads and bookkeeping, and barred from a recorder or author `record`, like the
  other receipts.
- **Order inside one batch.** The person test reads canon as it stands before the item, plus the
  `person:` namespace. A non-`person:` id whose `kind = person` arrives in the same batch as its
  `kind = smuggler` is judged by the order of the items. That is documented and tested. A `person:`
  id, the usual case, never depends on order.

### 3. Both extraction prompts

`_EXTRACT_RULES_FULL` and `_EXTRACT_RULES_LEAN` gain one rule each, worded the same:

> "- a person's 'kind' is always 'person'. What they are at a time (prisoner, captain, widow,
> hero) is 'role', with valid_from when it begins and valid_to when the text ends it; a person can
> hold several roles at once."

`'kind' for what a thing is` stays for everything else. The gate (§2) catches any person kind the
model still gets wrong, so the prompt reduces gate work but correctness doesn't rest on it.

## What it does for construct's pairs

On construct's run-8 shape, both ids are now `kind = person` (`present_equal`). A pair named
"Tomas Breck" and "Breck" therefore passes the kind check. It falls to `alias_not_specific`, or
merges on a distinctive name, and R48's `merge_gate` can judge it. The test reproduces this on a
fixture modelled on that shape. No construct world is written.

## Existing worlds

Nothing is rewritten. Append-only rules out any migration that edits rows.
- A world built before R49 keeps its person kinds and its `kind_conflict` declines.
- A host that wants the new shape rebuilds, or ingests `role` rows itself. A rebuild is construct's
  run 9, which it is already doing.

## Not in this spec

- An `eras(person)` read verb. The rows already answer "what was she in chapter 3" (`state`
  `as_of`) and "her whole life" (`facts`). A verb waits until a host needs a shape the rows don't
  give.
- Roles for non-persons ("the inn used to be a prison"). A place's kind stays as given. A later
  item can extend §2 if a book needs it.
- Inferring a role's end. A role the text never ends stays current: conservative, and correct for
  the fold.
- Changing `kind_conflict` itself. Identity is unchanged; only what reaches it changes.

## Tests (the build's acceptance)

1. **The gate.**
   - `person:tomas · kind · condemned man` (timed, chapter 1) is stored as `role` with the item's
     status and a `reclassified_from: "kind"` receipt, and no `canonicalized_from`.
   - It comes with one timeless `kind = person` in canon, `inferred`, with a
     `derived_by: "person_subject"` receipt.
   - A second non-person kind (`hero`, chapter 7) adds `role = hero` and no second `kind` row.
1a. *(r1.1, pbr P1)* **The alias map is untouched.**
    - Ingest `person:x · kind · prisoner` and `person:y · type · warden` (spelling `type -> kind`,
      then moved), then close and reopen the world.
    - `canonical_attribute("kind")` is still `kind`, and `canonical_attribute("type")` is still
      `kind`, exactly as before R49.
    - No alias maps to `role`, and the reopened alias map equals a pre-R49 world's.
    - The `type` item carries both receipts, and the `kind` item only `reclassified_from`.
    - `obj:lamp · kind · brass lamp` is still stored as `kind`, with no receipt.
2. **Eras.** With `prisoner` valid over [1, 5) and `hero` from 7:
   - `state(role, as_of=3)` is `{prisoner}`;
   - *(r1.1, construct)* `as_of=6` answers `status: "unknown"`, not `known` with empty values;
   - `as_of=8` is `{hero}`;
   - overlapping roles (`prisoner` and `father` at 3) answer both.
3. **Non-persons unchanged.** `obj:lamp · kind · brass lamp`, `place:inn · kind · tavern` and
   `event:x · kind · moved` are stored exactly as given, with no receipt.
4. **Person by kind.** `npc:smuggler` with canon `kind = person` already folded: a later
   `kind = smuggler` becomes a role. The same-batch order case behaves as §2 says.
5. **Frames.** A `knows:person:mara` item `person:tomas · kind · traitor` becomes a role in that
   frame, and the frame gets its own `kind = person`. Canon is untouched.
6. **Identity.** On a fixture modelled on construct's run-8 shape:
   - "Tomas Breck" (`kind = condemned man`) and "Breck" (`kind = person`) are, before R49, a
     `kind_conflict`, built the old way with rows written directly;
   - ingested after R49, the pair's decline is no longer `kind_conflict`;
   - `porcelain.merge_gate` lists the pair as askable, not `class_mismatch`.
7. **Prompts.** Both prompt constants contain the new rule. The rule text is identical in both.
8. **Existing worlds.** A world file built before the change reads byte-identically after it.
   Only new ingests are affected.
9. **The entity-valued kind** on a person is left alone and logged.
10. **Full suite green.** The ingestion-fidelity and chapter-test fixtures are unchanged, or any
    movement is reported and explained in the build note.

## Lexicon (added with the build)

- **role**: what a person is at a time (prisoner, captain, hero). A set-valued, time-indexed
  attribute, distinct from `kind`, which for a person is always `person`. The ingest gate moves a
  person's non-person kind into `role`.
- **`reclassified_from`**: the gate's receipt on a row it moved to another attribute in context
  (R49: a person's non-person kind, moved to `role`). It is META and never replayed. It is
  distinct from `canonicalized_from`, which records a global spelling alias.
- **`derived_by`**: the gate's receipt on an `inferred` row it derived rather than received
  (R49: a person subject's `kind = person`). It is META.
- **era**: one role's span on a person's valid-time axis. It is derived from the role rows and
  never stored.
