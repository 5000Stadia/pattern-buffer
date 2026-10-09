# READ-SURFACE-V1: the porcelain reads what the gate writes

**Status:** r1.1, built (2026-10-09; r1.1 answers pbr's RED on the build, see the last section). Spec pbr GREEN at 9cb2b92; built on batch D
(d7ae0bb) on `impl/read-surface-v1`, with C §7's three references amended (C
shipped without it); the code goes to pbr next. See "Build notes for pbr" at the
end. Batch E of `docs/AUDIT-2026-10.md`: P1 #10–#12, the batch-E row, and the
five places where construct rebuilds what the porcelain should give. Kabe
approved the five batches and every "Decision for Kabe" as recommended; this
spec relies on #3 (persist physics) and #4 (the durability pin).

**Its three open decisions take their defaults.** Kabe's standing approval of
2026-10-08 covers the audit's batches "as recommended". He is listed to
revisit these:
1. `ask` tries the asker's own words first, deterministically, learning
   nothing.
2. A world created before this change records its policy the first time it is
   opened with an explicit `policy=`.
3. `fold_policy: move` is removed.

- Every case below was reproduced with a probe on `main` (dba01d7) before it was
  specified (probes E1–E10, cited per oracle). Line numbers are at dba01d7.
- Blast radius was measured read-only on 168 world files: construct's 52 live,
  20 attic and 93 retired worlds, plus the engine's three eval worlds. Fold-level
  counts were taken on copies.
- One brief item is deferred to its own batch (§10, `events()`).

**Why.** The write side is careful and the read side is not. The gate
canonicalizes attribute names, folds by class and records what is unresolved.
The porcelain then:
- reads `located_in` literally, so `state(ann, "located_in")` says unknown where
  the gate stored `in`;
- serves one member of a set, conflict ids without their values, and an
  unresolved placeholder as a known value;
- has `who_knows` match the last delta row instead of the total, miss every set
  member but the latest, and never match an exact-decimal tag;
- lets `ask()` answer from after the caller's time;
- forgets a world's physics on reopen, so a tracking world reopened without
  `policy=` runs as fiction;
- sends construct below it for `refer`, the alias map and a re-fold of `in`.

Two host-control levers are also missing: a way to fix a host attribute's
durability without the model, and a fold where the latest host write simply
wins.

**Founder decisions this relies on** (all approved as recommended):
- **#3:** persist `policy` at creation; on reopen default to it and raise on
  mismatch (§7).
- **#4:** the durability pin `attr:<name> · durability ·
  STATE|DISPOSITIONAL|CONSTITUTIVE`, never EVENT, read before the model (shape
  agreed with construct); and `fold_policy` is either given its meaning or
  removed (§1, §2).
- **Batch D's confirmed defaults** (Kabe, 2026-10-08 evening): refer learns a
  word, never a pick; `ask` never learns. §6 and §9 build on them.
- **Batch C's #1:** identity is canon's. §6 relies on C's frame-scoped
  vocabulary. C's #2 (`knows:` frames follow merges, C §7) is held for Kabe's
  gate g3bf5da and is not built (amended at build, 2026-10-09): §8's `frame=`
  reads the exact stored frame, and no E behaviour depends on C §7.

## §0 Dependencies, and the contract words used below

E lands last, after A–D and GATE-INVERSE-ALIAS-V1 (the audit's order).

| E section | Needs | Why |
|---|---|---|
| §1, §2 | B §5 | `valid_declaration` and the `invalid_semantics_declaration` skip; E extends both |
| §2 | A §1, A §4 | `_recency_key`; evidence rank in every class |
| §3 | GATE-INVERSE-ALIAS-V1 | `holds`/`wearing` leave the forward alias map. On the old map, a read of `ralph holds` would read Ralph's `held_by` key: the wrong entity |
| §6 | A §6 | the "finite real number" predicate for time values |
| §6 | C §2 | `by_alias(frame=)`. Without it the asker's pass sees every frame, which is harmless: it then binds what canon would |
| §6, §9 | D | `learn=`, tier 1d, refer's `asserted_as_of`, `ask` never learns |
| §7 | B §0 | the authority step the physics check joins |
| §8 | C §6 | snapshot existence by frame. C §7 (observer frames following merges) is held for g3bf5da, so §8 reads the exact stored frame |
| §11 | C §4 | `identity_conflicts` (tool 40); the counts below say which base they assume |

If the batch has to split, §4, §5, §7 and §8 need none of A–D and can land first
(§7's gate check then sits at the top of `_ingest_item`). §9 can too, gaining
`learn=` when D lands.

Each section is classified with one or more of:
- **additive:** a new verb, a new parameter (defaulted, appended last), a new key
  or a new declaration. Existing calls return what they return today.
- **result-correcting:** an existing call returns a different answer where
  today's answer is wrong by the verb's own documented meaning.
- **new status value:** an existing field gains a value it never had.

## §1 The durability pin

**Rule.**
- The declaration is `attr:<name> · durability · <class>`, where `<class>` is
  exactly `STATE`, `DISPOSITIONAL` or `CONSTITUTIVE`.
  - Never `EVENT`. Occurrence stays structural (CLASSIFIER-EVENT-SAFETY-V1,
    whitepaper A8), and EVENT erases a row from every fold.
- `durability` joins `SEMANTICS_PREDICATES`, so ATTRIBUTE-SEMANTICS-V1 §5
  applies unchanged:
  - the inviolable core cannot be pinned (`ValueError` at the buffer);
  - declare before data: once the attribute has a row (any frame; any subject
    but `attr:`/`a:`), a pin raises `ValueError`;
  - the shared insert validator holds on `append` and `dump.build` alike;
  - the semantics view rebuilds the pin from the log.
- **Who declares:** the host's `attribute_default` (its output keys,
  `_SEMANTICS_DECL_KEYS`, gain `durability`) or a manual `attr:` row. Not an item
  hint: `_SEMANTICS_HINT_KEYS` is unchanged, exactly as for `structural`. A pin
  decides which rows the model sees and which lens serves them. That is the
  host's decision about its own vocabulary, made once, not something a
  model-written item carries in.
- **Validation** (B §5, extended): `valid_declaration("durability", v)` accepts
  exactly the three classes. Anything else, `EVENT` included, is skipped
  `invalid_semantics_declaration`.
- **Coherence** (new; §2 uses the same check). A declaration that could never
  take effect, or that contradicts another declaration on the attribute, is
  skipped with the same code. Its `detail` gains a `conflicts_with` key:
  - a pin on `name`, `alias` or a META attribute: a guardrail fixes their class
    before the pin is read (`conflicts_with: "guardrail"`);
  - a pin other than `CONSTITUTIVE` beside `structural: true`, in either order
    (`conflicts_with: "structural=true"` or `"durability=<class>"`).
  - A log that carries such a pair anyway (a dump, or rows from before this
    spec) is read in guardrail order: the pin is consulted before `structural`.
- **The classifier.** `Classifier._guardrails` after this spec, in order (new
  steps in bold):
  1. a `delta` row → STATE (existing);
  2. an `event:` subject or a `caused_by` row → EVENT (existing);
  3. `name`/`alias` → CONSTITUTIVE (existing);
  4. a META attribute → EVENT (existing);
  5. **a semantics declaration (an `attr:` subject with a semantics predicate) →
     EVENT, 1.0.** The four older predicates are caught at step 4 already; this
     step catches the pin's own row;
  6. **the physics row (§7) → CONSTITUTIVE, 1.0;**
  7. an unresolved placeholder → STATE (existing);
  8. **a pinned attribute → the pinned class, 1.0;**
  9. the containment sub-rules, `structural`, B §8's bookkeeping rule, then the
     model (existing).

  So a pinned row never reaches the model on any path: inline, `batch`, `rules`,
  a seal, `classify_all` or `rebuild`. It is never `needs_review`.
- `promote_accruals` skips pinned attributes: a declared class is not a habit to
  learn.
- **`durability` does not join `META_ATTRIBUTES`.** `META_ATTRIBUTES` lists its
  four semantics predicates by name instead of taking the whole set.
  - "Durability" is an ordinary domain word (a sword's durability). A META
    attribute is erased from every fold and skipped by `current_state` and by
    identity's contradiction checks.
  - A semantics predicate means something only on an `attr:` subject, and every
    semantics reader already checks the subject (the buffer validator, the
    semantics rebuild, the gate's manual-row path). Step 5 keeps the pin row
    model-free.

**This amends ATTRIBUTE-SEMANTICS-V1 §2.** That spec kept durability "per-row and
model-judged" and called attribute-level durability "schema rigidity ...
forbidden" (the Kernos seam). Decision #4 narrows the rule: undeclared vocabulary
stays per-row and model-judged, and a host may declare that its own attribute is
invariant, as `structural: true` already does for CONSTITUTIVE.

**Location.** `model.py` `SEMANTICS_PREDICATES` (43) and `META_ATTRIBUTES`
(50–66). `semantics.py` `Semantics` (80; gains `durability: str | None = None`),
`builtin_default` (89), `_overlay` (144), a new `durability_pin()`, B's
`valid_declaration` and the new coherence check. `classify.py` `_guardrails`
(135) and `promote_accruals` (360). `ingest.py` `_SEMANTICS_DECL_KEYS` (238).

**Oracle** (today → after):
- **O1a** (probe E1). A manual `attr:arc_status · durability · STATE`, then
  `arc:main · arc_status · "open"` (timeless), classified inline:
  - today 2 model calls (the declaration row and the data row), and the
    declaration does nothing;
  - after 0 model calls; the data row is STATE 1.0 and the declaration row EVENT.
- **O1b.** `attribute_default` returns `{"durability": "CONSTITUTIVE"}` for
  `rung`. The declaration lands before the first `rung` row, which is
  CONSTITUTIVE with no model call.
- **O1c.** A `rung` row first, then the pin: `ValueError`, head unchanged.
- **O1d.** Pin values `"EVENT"`, `"state"` and `1` are each skipped
  `invalid_semantics_declaration` with nothing written. Coming from
  `attribute_default`, the item is skipped and the attribute is not marked
  checked (B §5).
- **O1e.**
  - A pin on `in`: `ValueError`.
  - A pin on `alias` in a fresh world: skipped, `conflicts_with: "guardrail"`.
  - `{"structural": true, "durability": "STATE"}` from `attribute_default`: the
    item is skipped, `conflicts_with: "structural=true"`.
- **O1f.** `event:bell · arc_status · "rung"`, with `arc_status` pinned STATE,
  classifies EVENT.
- **O1g.** One pinned-STATE value at t=1, 2 and 3: `promote_accruals()` promotes
  0 rows.
- **O1h.** `classifier.rebuild()` gives identical verdicts with 0 model calls.
- **O1i.** `obj:sword · durability · 80` (a domain row): `state(sword,
  "durability")` is known 80, today and after.

**Contract.** Additive: a new declaration. 0 `durability` rows on `attr:` subjects
exist in 168 world files.

**Byte-identical.** Every world without a pin: classification, folds, lenses.
Step 5 changes no existing verdict.

**MCP.** None. Declarations travel through `ingest_structured` and `commit_set`.

## §2 `fold_policy: last_write` gets its meaning, and `move` is removed

**Rule.**
- An attribute *declared* `fold_policy: last_write` folds by recency, whatever
  its durability:
  1. the existing pre-fold filters run unchanged: EVENT rows never fold; on a
     non-accrue key `delta` rows drop; a spent thunk drops; a placeholder drops
     once a concrete row exists;
  2. keep the rows of the top evidence rank (the `_fold_state` rank table, which
     batch A §4 applies to every class);
  3. serve the row with the greatest `_recency_key` (A §1: `(valid_from or −∞,
     asserted_at)`).
- A last_write fold is never conflicted. `conflicting` and `corroborated_by` are
  empty, and source classes take no part (no §7.2 flag).
- Rank stays because last_write is about time, not trust. A later `inferred` or
  `assumed` row never displaces a `stated` one: P5's assumption quarantine, as
  batch A applies it everywhere.
- It applies to a functional attribute outside the containment family.
  - The §1 coherence check skips `last_write` beside `arity: set_valued` (a
    set's members already supersede one by one) or `relation_family:
    containment` (the family folds as one key under its own rule).
    `conflicts_with` names the other axis.
  - On read, if a log carries the pair anyway, set-valued and containment win.
- Undeclared attributes stop carrying the label `last_write`. `builtin_default`
  gives them an internal `by_class`: the fold by durability class, exactly
  today's. `by_class` is not declarable. The declarable `FOLD_POLICIES` becomes
  `{last_write, accrue}`.
- **`move` is removed.**
  - The containment family's cross-source move rule (HD 002) is untouched: the
    code always keyed it on `relation_family`, never on `fold_policy`.
  - `fold_policy: move` was "recorded but not wired" (ATTRIBUTE-SEMANTICS-V1 §2).
    After this spec a `move` declaration is skipped `invalid_semantics_declaration`
    (B §5), and an old one in a log is ignored on read (B §5's read side).
  - 0 `move` and 0 `last_write` declarations exist in 168 world files.

**The pin and last_write are both needed.** They are two orthogonal axes:
- the pin decides the **class**: which lens serves the row, budget exemption,
  accrual promotion, and whether the model is ever asked;
- the fold policy decides **which row of a key is served**.

Construct's mutable host-control rows need both:
- A STATE pin alone still conflicts when the host rewrites a key at the same
  stamp or timelessly (a per-class tie; probe E2). That is the EP2 stale-arc
  serve that `hostcontrol.py` guards against today.
- `last_write` alone still sends every row to the model, and the model's class
  still picks the lens.

The recipe:
- a mutable host-control attribute declares `{"durability": "STATE",
  "fold_policy": "last_write"}`;
- an immutable host enum declares `{"durability": "CONSTITUTIVE"}`, or
  `structural: true` as today.

Two cautions go into ADOPTION:
- A timeless STATE row is listed in `fidelity_audit`'s `unstamped_timed`.
  Timeless bookkeeping should pin DISPOSITIONAL or CONSTITUTIVE.
- Declarations precede data. Construct's existing `status`/`phase` keys already
  have rows in every world, so the levers apply to new attribute names or new
  worlds.

**Location.** `semantics.py` constants (45–51), `builtin_default` (89) and a new
`is_last_write()`. `indexes.py` `_fold_over_closure` (400–495): a new branch
right after the set-valued branch, into a new `_fold_last_write`.

**Oracle** (probe E2):
- **O2a.** `arc_phase` declared last_write; "setup", then "climax", at one cursor
  stamp (5.0):
  - today conflicted, serving "setup", `conflicting: [a:4, a:5]`;
  - after known "climax", with no `conflicting`.
- **O2b.** The same, timeless: today conflicted "a"; after known "b".
- **O2c.** Pinned CONSTITUTIVE plus last_write, timeless "one" then "two": today
  (declared `structural`) conflicted "one"; after known "two".
- **O2d.** `posture` last_write: "sitting" at t=1 (`source_doc: doc:x`),
  "standing" at t=2 (`doc:y`). After: known "standing", unconflicted, and
  `as_of=1.5` serves "sitting". Today, with `move` declared: conflicted.
- **O2e.** Stated "a" at t=1, then inferred "b" at t=2: "a".
- **O2f.** An `event:`-subject row on a last_write attribute is never served.
- **O2g.** `attribute_default` returning `{"arity": "set_valued", "fold_policy":
  "last_write"}`: the item is skipped, `conflicts_with: "arity=set_valued"`.
- **O2h.** A `fold_policy: "move"` hint: today recorded, with no effect; after
  skipped `invalid_semantics_declaration`.
- **O2i.** An undeclared attribute holding two values at one stamp is still
  conflicted.

**Contract.** Gives an advertised value its meaning, and narrows the declaration
vocabulary by `move`. No world declares either.

**Byte-identical.** Every undeclared attribute, the containment family, accrue.

**MCP.** None.

## §3 One attribute name on both sides of the gate

**Rule.**
- One function names an attribute: `Ingestor.canonical_attribute(name) -> str`,
  which is `_canonicalize(name)[0]`. That is the gate's own normalization (strip,
  lowercase, spaces to `_`) and its forward alias map (built-ins, replayed
  receipts, runtime `add_attribute_alias` entries), skipped for a structural
  attribute, exactly as the gate applies it.
- **Inverse spellings are not renamed.** After GATE-INVERSE-ALIAS-V1, `holds` and
  `wearing` are not in the forward map:
  - their entity-valued facts are stored on the other entity (`key held_by
    ralph`), read with `contents(ralph)`;
  - their text-valued facts stay under the spelling itself (`ralph holds "a
    lantern"`).
- `World.canonical_attribute(name)` delegates. The porcelain exposes
  `canonical_attribute(name: str) -> str`.
- **Every porcelain argument that names an attribute passes through it first:**
  `state.attribute`, `state_union.attribute`, `where.attribute`,
  `aggregate.member_attribute`, `facts.attribute` (when given),
  `confidence.attribute`, `who_knows.attribute`, `resolve.aspect`, and each `ask`
  plan key's `attribute`.
- Payloads keep echoing the log: a served Fact's `attribute` is the stored name.
  A non-string argument passes through unchanged.
- This happens at the porcelain boundary only. `World` and `Indexes` keep taking
  canonical names, which every engine caller already passes.
- Construct's `turnloop.py` `_canonicalize_containment` (1412) copies the alias
  map, including the dead `within` entry. It retires onto `p.canonical_attribute`.

**Location.** `ingest.py` `_canonicalize` (326); `__init__.py` `World` (a new
delegator); `porcelain.py`, the nine verbs above plus the new verb.

**Oracle** (probe E3):
- `state(ann, "located_in")`: today unknown; after known, with the same payload
  as `state(ann, "in")`.
- `facts("canon", attribute="located_in")`: 0 rows → 1.
- `who_knows(ann, "located_in")` equals `who_knows(ann, "in")`.
- `confidence(ann, "located_in")["value"]`: None → `"place:hall"`.
- `state(box, "type")` equals `state(box, "kind")`.
- `canonical_attribute`: "Located In" → "in"; "type" → "kind"; "holds" →
  "holds"; "Mood" → "mood"; "in" → "in".
- After `world.ingestor.add_attribute_alias("allegiance", "loyal_to")` (test setup
  below the porcelain), `state`, `where` and `aggregate` answer the same for
  either spelling.
- An `ask` plan key "located_in" serves the `in` fact.
- `resolve(e, "Contents")` finds the `contents` thunk.

**Contract.** Result-correcting for an argument that isn't already the gate's
name (an alias spelling, a case or space variant). The new verb is additive.

**Byte-identical.** Every argument that is already canonical maps to itself.
- Measured in 168 world files: 0 rows stored under a forward-alias spelling, and
  0 stored attributes that aren't normalized. No stored row becomes unreachable.
- The one way one could: rows written under a spelling before that spelling
  became an alias. A wide `facts(frame, include_meta=True)` scan still lists
  them.

**MCP.** One new V1 read, `canonical_attribute`.

## §4 `state()` serves the whole key

**Rule.** For `state` and `state_union`, which share one payload builder:
- **`status`** is one of `unknown`, `known`, `conflicted` and the new
  **`unresolved`**, decided in this order:
  1. the fold serves nothing → `unknown`;
  2. the fold flags → `conflicted`;
  3. the served row is an unresolved placeholder (`value_type == "unresolved"`)
     → **`unresolved`**;
  4. otherwise `known`.

  For `unresolved`, `fact` is the placeholder; its `value` is the thunk spec
  (policy, constraints). This is the doctrine's "established-deferred" state
  (whitepaper A6), which `snapshot` already names in `unresolved` and never
  serves as a fact.
- **`values: [Fact]`** is present when the key is set-valued and has members:
  every current member, in the fold's member order (assertion order). `fact`
  stays the most recent member, as today.
- **`conflicting_facts: [Fact]`** is present whenever `conflicting` is: one Fact
  per id, in the same order. Construct's `game.py` `_live_in_candidates` (2175),
  a re-fold of raw `in` rows that is less correct than the fold (folds auditor
  Q1: no closure, rank, class or EVENT exclusion), retires onto it.
- **`Fact.value_type`** is a new field on every Fact, from every verb (`state`,
  `state_union`, `snapshot`, `facts`, `frame_diff`, `resolve`, `ask`). It is the
  row's value type; a derived accrue total is `"literal"`. It is appended after
  `b_value`, so existing keys keep their order.
- New keys follow the existing ones: `status`, `fact`, `quantity`,
  `conflicting`, then `conflicting_facts`, `values`, and §5's `matches`.

Where `ask` serves a key:
- a placeholder is not served as a fact. It is named in a new `Answer.unresolved:
  [[entity, attribute]]` (snapshot's shape);
- a set-valued key serves one Fact per member;
- a conflicted key serves its winner, as today, and is named in a new
  `Answer.conflicted: [[entity, attribute]]`;
- `answered` keeps its meaning (some fact was served), and `unknown_reason` keeps
  its three strings.

**The new status value.** PORCELAIN-V1 types `state()` as `Fact | Unknown |
Conflicted`; this adds `Unresolved`. The field keeps its type, a string, but
gains a value, and a placeholder key that answered `known` now answers
`unresolved`.
- A host that branches on `status` must treat a value it doesn't recognize as
  not known.
- Construct's four `status` readers already do:
  - the mirror (`turnloop.py` ~1967) and `hostcontrol.collapse_state` (36) stop
    passing a thunk spec off as a value. Today the mirror's point-read fallback
    can copy `{"policy": …}` into the player's frame as a literal;
  - `furnish_scene` (~1991) and `remembrancer._standing_values` (155) behave as
    before.
- Measured on copies of the 168 world files: 199 keys in 75 worlds serve a
  placeholder today (188 in canon, 9 in `knows:` frames, 2 in `proposed:`). Each
  answers `unresolved` after.

**Location.** `porcelain.py` `Fact` (53), `_fact` (123), `_quantity_fact` (133),
`state` (427), `state_union` (668), `Answer` (67), `ask` (927).

**Oracle** (probe E4):
- **O4a.** `obj:tin · contains`, declared set-valued, with three cigarettes:
  today the keys are `[fact, status]` and `fact` is cig_3; after, `values` holds
  cig_1, cig_2 and cig_3, and `fact` is still cig_3.
- **O4b.** `person:p` in `place:a` and in `place:b` at one stamp: after, also
  `conflicting_facts` with values `[place:a, place:b]`, in `conflicting`'s order.
- **O4c.** A `description` placeholder: today `known` with value `{"policy":
  "invent_under_canon"}`; after `unresolved`, with `fact.value_type ==
  "unresolved"`.
- **O4d.** Every Fact from `snapshot`, `facts`, `frame_diff` and `resolve` carries
  `value_type`; an accrue total carries `"literal"`.
- **O4e.** `ask`:
  - with a placeholder key: today `answered`, with the spec served as a fact;
    after `facts == []`, `unresolved == [["place:study", "description"]]` and
    `answered` False;
  - with the tin key: 3 facts;
  - with p's `in` key: 1 fact and `conflicted == [["person:p", "in"]]`.
- **O4f.** `state_union` over an `aka` pair has the same shape.
- **O4g.** Every payload round-trips through `json.dumps`.

**Contract.** Additive keys. One new status value, result-correcting for
placeholder keys. `ask` is result-correcting for placeholder and set-valued keys.

**Byte-identical.** Every key and value of `state`/`state_union` for a known,
functional, unconflicted key, except the new `value_type` inside `fact`.

**MCP.** Payload keys only; tool outputs are the untyped `{"result": …}` envelope.

## §5 `who_knows` matches the folded value

**Rule.** One predicate in `Indexes`, `fold_matches(fold, value) -> bool`, is
shared by `who_knows` and `state(value=)`:
- false when the fold serves nothing or a placeholder;
- an accrue key: the folded quantity equals `value` (numerically; `Decimal` and
  `int` compare exactly, as in `where`);
- a set-valued key: some current member value-matches;
- otherwise: the served row value-matches (identity-aware `_value_matches`,
  unchanged).

The porcelain decodes `value` with `decode_value` first, so the `$decimal` tag
works over JSON and MCP, as it already does in `where`.

- **`who_knows`:** a `knows:*` frame qualifies iff its fold serves a concrete
  value and, when `value` is given, `fold_matches` holds. A frame holding only a
  placeholder no longer qualifies (§4's status, applied here).
- **`state(..., value=None)` and `state_union(..., value=None)`:** when `value` is
  given, the payload gains `"matches": bool` (also on `unknown`, where it is
  False). This is `who_knows`'s test for any frame. Construct's `adapter.py`
  `assertion_in_frame` (101) compares the raw winner value, so it misses merged
  ids and set members; it retires onto `matches`.

This changes results within the verb's documented meaning. WHO-KNOWS-INVERSE-V1
and the LEXICON define knowing as "the folded winner is present and
value-matches". A set's folded value is its members (WHO-KNOWS-INVERSE-V1 deferred
exactly this as "V1.1"), and an accrue key's folded value is its total. The
ADOPTION CAUTION at lines 399–402 retires.

**Location.** `indexes.py` `who_knows` (1139–1173) and `_value_matches` (1175);
`porcelain.py` `who_knows` (816), `state` and `state_union`.

**Oracle** (probe E5):
- Set member `person:x`, the older of two allies in `knows:person:alice`: today
  `[]`; after `["knows:person:alice"]`.
- Accrue total 15 (baseline 10, delta 5) in `knows:person:carol`:
  - today `who_knows(…, 15) == []` and `who_knows(…, 5) == ["knows:person:carol"]`;
  - after, the reverse.
- `{"$decimal": "12.50"}` in `knows:person:dana`: today `[]`; after
  `["knows:person:dana"]`. A `Decimal("12.50")` matches before and after.
- A frame holding only a placeholder for the key: today listed; after not.
- `state("person:bob", "ally", frame="knows:person:alice", value="person:x")
  ["matches"]` is True. With `value="person:z"` it is False, and on an unknown
  key False.
- Over MCP, `dispatch(world, "who_knows", {…, "value": {"$decimal": "12.50"}})`
  gives `["knows:person:dana"]`.

**Contract.** Result-correcting (`who_knows`); additive (`value=` and `matches`).

**Byte-identical.** `who_knows` on a functional, non-accrue key, queried with a
non-tag value, over frames that serve a concrete value. Measured on copies:
1,281 set-valued `knows:` keys hold two or more members, and a query naming any
member but the latest changes from not-known to known; 0 accrue keys and 0
`$decimal` values sit in `knows:` frames.

**MCP.** `state.value` and `state_union.value` join `who_knows.value` as the
deliberately permissive (any JSON) parameters.

## §6 `ask()`: one effective time, and the asker's own words

**Rule A: one effective time.**
- `t` is the caller's `as_of`, unless the plan gives a valid `as_of` (a finite
  real number, not a bool: batch A §6's predicate). Then `t` is the plan's when
  the caller's is None, and `min(caller, plan)` otherwise. An invalid plan value
  is ignored.
- `t` governs every step: the asker's scope (`locate(asker)`), both refer passes
  (rule B), every key fold, the location fold and its chain, and
  `events(until=t)`.
- This amends PORCELAIN-V1 §5's "honors the plan's as_of" to "honors the plan's
  as_of up to the caller's". The caller's `as_of` is a ceiling the model's parse
  can lower but never raise. Construct passes its play horizon there (Cx 255) so
  that nothing after it is told.

**Rule B: the asker's own words.**
- In a non-canon frame F, `ask` first binds each target by F's own tier 1:
  `refer(target, scope=ask_scope, frame=F, as_of=t, learn=False, model=False)`,
  kept only if `resolved`. That is F's names, aliases and learned words, and a
  kind unique in F's view of the scene. The pass makes zero model calls and zero
  writes (§9's `model=False`).
- If it doesn't resolve, `ask` binds exactly as today: canon, the asker's scope,
  `learn=False` (D §8).
- Canon stays the binding authority wherever F cannot bind the reference by
  itself (HD 003, unchanged for every such reference). The asker's private name for a thing
  binds in the asker's own question and in no one else's. Nothing is learned (D's
  decision 2 stands).
- This settles D's open item (an asker's private words) and C's Q5. With C, an
  alias that only Alice holds no longer binds in canon at all. Without rule B,
  Alice could not use it in her own question.

**Location.** `porcelain.py` `ask` (927–997).

**Oracle:**
- **O6a** (probe E6). The badge is in `place:a` from t=1 and in `place:b` from
  t=10. Caller `as_of=5`, plan `as_of=50`: today `place:b`; after `place:a`.
- **O6b.** Caller 20, plan 5, a key on `in`: today the key folds at 20 (`place:b`)
  while the location folds at 5; after, both fold at 5.
- **O6c.** Caller None, plan 5: `place:a`, before and after.
- **O6d.** Plan `as_of: "yesterday"`, caller 5: today the location answers as if
  at the end of time (`place:b`; in SQLite every number sorts below text), and
  `wants_events` raises `TypeError`; after, both use the caller's 5.
- **O6e.** `wants_events` with caller 5 and plan 50: an event at t=40 is listed
  today and not after.
- **O6f** (with C). Alice's item `{obj:desk_drawer · state · "locked", frame:
  knows:person:alice, aliases: ["the stash"]}`; canon has no such alias.
  - `ask("is the stash locked?", frame="knows:person:alice")` with a plan key
    `state`: after, the fact "locked", 1 model call (the plan), head unchanged.
  - A canon `ask` of the same question: underdetermined, with an entry in `asks`.
- **O6g.** Canon alias "the stash" on `obj:safe`, Alice's on `obj:desk_drawer`:
  Alice's ask binds the drawer; a canon ask binds the safe.
- **O6h.** `TestAskReferParity` (HD 003) passes unchanged.

**Contract.** Result-correcting. `ask` no longer answers from after the caller's
time, and an ask in a frame that has its own word for a thing binds that frame's
referent.

**Byte-identical.** Canon asks whose plan `as_of` is absent or not later than the
caller's; non-canon asks where the frame's own vocabulary resolves nothing.

**MCP.** None (`ask` is V1.1).

## §7 A world file carries its physics

**Rule.**
- **The physics row** is `attr:__world__ · resolution_policy · <policy>`: canon,
  timeless, `stated`, ingestor authority, CONSTITUTIVE.
  - `attr:__world__` already carries the world's decay default
    (TRACKING-MODE-V1), so a world's physics live together.
  - They sit outside every world-fact read (`attr:` subjects are excluded
    everywhere) and outside the charter, which letter 026 kept for
    self-description ("stance ... distinct from operational policy").
- **One writer:** `World.__init__`, by a direct ingestor-role append (no gate,
  no cursor, no `attribute_default`):
  - at genesis, after the charter rows;
  - when a world created before this spec (head > 0, no physics row) is opened
    with an explicit `policy=`. The host is stating the physics it runs the
    world under (Decision for Kabe 2).
- **At every open**, `World(..., policy: str | None = None)`:
  1. an explicit `policy` outside `POLICIES` raises `ValueError` (unchanged);
  2. the buffer opens (`WorldMismatch` first, unchanged);
  3. `stored` is the physics row's value, if one is visible;
  4. if an explicit `policy` and `stored` disagree, the buffer is closed and
     `WorldPhysicsMismatch` is raised: a `ValueError`, defined beside
     `WorldMismatch` and exported from `patternbuffer`. Nothing is written;
  5. the effective policy is `stored`, else the explicit one, else
     `invent_under_canon`.
- **The physics row is immutable.**
  - The buffer's shared insert validator (`append` and `dump.build`) admits at
    most one physics row per log, only in canon, only with a value in
    `POLICIES`. Anything else raises `ValueError`, so a tampered dump fails to
    build.
  - The gate refuses an item addressing the physics key. It is an authority
    violation: `ValueError` at B §0 step 2, before any write; under
    `atomic=True`, an `exception` abort.
  - `TruthMaintenance.retract` refuses the physics row (`ValueError`, its
    convention for an ineligible target).
  - Why: the log was written under its physics. The gate stamps wall-clock
    learned-at only in observe worlds (A1's rider), and the resolver invents only
    in invent worlds. Switching physics later would leave rows authored under
    the other discipline. A world that needs other physics is a new world.
- **`stance`, `title`, `description`** are already persisted at genesis as the
  charter (letter 026). Reopen arguments for them stay ignored, as
  `test_existing_world_not_recharted` pins. They describe the world and are
  never read to change behaviour (the no-bias invariant), so a disagreeing
  argument can't drift physics. Nothing changes for them.
- **The MCP launcher** gains `--policy {invent_under_canon,observe_or_unknown,deny}`
  (env `PATTERNBUFFER_POLICY`), passed to `World`. Absent, the stored physics
  apply. A mismatch fails startup, as a mismatched world id does.
- **Reading the physics:** `world.policy`; on the porcelain,
  `facts("canon", entity="attr:__world__")` lists the row.

**Location.** `__init__.py` `World.__init__` (56–149) and `__all__` (44).
`buffer.py` `_insert` (380), a new `_validate_physics_insert`, and the new
exception beside `WorldMismatch`. `model.py`: the subject, the predicate and the
policy vocabulary (`thunks.POLICIES` re-exports it, so the buffer needs no
`thunks` import). `ingest.py`: the authority step. `tmaint.py` `retract` (136).
`classify.py`: step 6 of §1. `mcp.py` `main` (297–332).

**Oracle:**
- **O7a** (probe E7). A tracking world reopened without `policy=`:
  - today the policy is `invent_under_canon`, and a new timed row gets no
    learned-at stamp;
  - after, the policy is `observe_or_unknown`, and the row is stamped.
- **O7b.** The same world reopened with `policy="invent_under_canon"`:
  `WorldPhysicsMismatch`. The file is unchanged and reopens normally afterwards.
- **O7c.** A fresh world holds the physics row right after the charter.
  Construction with a raising model makes no model call.
- **O7d.** A pre-spec world, built from a dump fixture without a physics row:
  - opened without `policy=`: head unchanged, policy `invent_under_canon`;
  - opened with `policy="observe_or_unknown"`: head +1;
  - reopened without `policy=`: `observe_or_unknown`.
- **O7e.** `ingest_structured([{"entity": "attr:__world__", "attribute":
  "resolution_policy", "value": "deny"}])`: `ValueError`, head unchanged. With
  `atomic=True`: `AtomicAbort(cause="exception")`.
- **O7f.** `retract(<the physics row's id>, "x")`: `ValueError`.
- **O7g.** Dump → build → reopen keeps the physics. A dump with two physics rows
  fails to build, and its file is removed.
- **O7h.** MCP: start with `--policy observe_or_unknown` on a fresh path, then
  restart without the flag and ingest a timed row: it carries a learned-at stamp.
  Restarting with `--policy invent_under_canon` fails startup.
- **O7i.** Reopening with `stance="reality"` is ignored, as today.

**Contract.**
- Additive at the constructor: `policy` now defaults to None, which resolves as
  before for every existing world.
- A new raise when an explicit `policy` disagrees with the stored one.
- One more genesis row on every new world, so a new world's later `a:<seq>` ids
  shift by one. No existing log changes.
- One row on the first explicit-policy open of a pre-spec world.

**Byte-identical.** Every pre-spec world opened without `policy=`.
- Measured: 0 physics rows in 168 world files; every construct world is fiction.
- Construct creates and opens worlds without `policy=` (`game.py` `_world`), so
  this rule never writes to its existing worlds.

**MCP.** `--policy` / `PATTERNBUFFER_POLICY`.

## §8 `frame=` and `asserted_as_of=` on the reads

**Rule.**
- **`frame=` on `locate`, `contents` and `path`**, after `as_of`, so positional
  calls survive: `locate(entity, as_of=None, frame="canon", asserted_as_of=None)`,
  and likewise `contents(container, …)` and `path(a, b, …)`.
  - They pass it to the `World`/`Indexes` signatures, which already take it.
  - Docstrings stop saying "in canon".
  - Each reads the rows stored under that frame's own name. C §7 (`knows:`
    frames following merges) is held for Kabe's gate g3bf5da and is not built
    (amended at build, 2026-10-09).
- **`asserted_as_of: int | None = None`**, a log position: rows asserted after it
  are invisible, and retractions asserted after it don't apply.
  - It is appended to every porcelain read that takes a valid-time bound
    (`as_of`, or `events`' `until`), except four (below). That is twenty reads:
    `snapshot`, `state`, `state_union`, `where`, `aggregate`, `entities`,
    `facts`, `locate`, `contents`, `composition`, `features`, `path`, `route`,
    `neighborhood`, `correlations`, `correlation_conflicts`, `confidence`,
    `events`, `who_knows`, `frame_diff`.
  - Six were asked for by name (`state`, `snapshot`, `facts`, `entities`,
    `frame_diff`, `confidence`). The other fourteen already carry the parameter
    in their lower layer, and one rule is easier to keep than a list.
- It reaches every fold, walk and `visible()` the verb makes, and also:
  - `_fact`'s source-chain lookup (a `source` row asserted after H is not in the
    chain);
  - `snapshot`'s existence check: an id first asserted after H errors like an
    unknown id (C §6 adds the frame);
  - `snapshot`'s `charter` (`World.charter(asserted_as_of=None)`).
- **Not here**, and why:
  - `salience` and `in_transit`: their lower layers don't carry it yet;
  - `fidelity_audit`: C rebuilds `open_conflicts`;
  - `ask`: model-backed, and its refer passes would need it too.

  These are a follow-up.
- **Known limits, unchanged:** identity closures are computed at the head (C's
  non-goal); budget shaping in `snapshot` and `neighborhood` ranks by current
  salience (A's non-goal, audit P1 #14).

**Location.** `porcelain.py`: each verb listed, `_fact` (123) and `_is_known`
(380). `__init__.py` `charter` (392).

**Oracle:**
- **O8a.** `obj:key` is in `obj:box` in canon and in `obj:drawer` in
  `knows:person:alice`:
  - `locate("obj:key", frame="knows:person:alice")[0] == "obj:drawer"`;
  - `locate("obj:key")[0] == "obj:box"`;
  - `locate("obj:key", 5.0)` still means `as_of=5.0`;
  - likewise for `contents` and `path`.
- **O8b.** One property test: seed rows up to H, then add a later value, a later
  `source` row, a later retraction and a new entity. Every verb above at
  `asserted_as_of=H` answers as it did at H, before the later rows existed.
- **O8c.** `snapshot(<an id first asserted after H>, asserted_as_of=H)` returns
  the error payload.

**Contract.** Additive.

**Byte-identical.** Every call that omits the new parameters.

**MCP.** New typed parameters on existing tools.

## §9 A porcelain `refer`

**Rule.**

```python
p.refer(description: str, scope: str | list[str] | None = None,
        frame: str = "canon", as_of: float | None = None,
        constraints: list[list[str]] | None = None,
        asserted_as_of: int | None = None,
        learn: bool = True, model: bool = True) -> dict
```

- It returns the `Resolution` as a plain dict, encoded: `{"status": "resolved" |
  "candidates" | "underdetermined", "entity_id", "candidates", "receipt"}`.
- `constraints` are `[relation, anchor]` pairs, since JSON has no tuples:
  `contains`, `owned_by` (with D's fix) and `held_by` (whitepaper §9, tier 1b).
- `learn` is D's. "Learn a word, never a pick" applies unchanged.
- **`model=False`** (new, on `Refer.__call__` too) means tier 1 only. Wherever
  tier 2 would run, the result is `{"status": "candidates", …, "receipt":
  {"tier": 2, "signals": ["no_model"]}}`, exactly today's no-model shape, so
  nothing is learned. `model` is the name `seal_build(model=)` already uses for
  "consult the model or not".
- Whitepaper §25.1 already lists `refer` among the porcelain's verbs; this makes
  that true.
- Construct's six below-porcelain `world.refer()` calls (`turnloop.py` ~618,
  ~3715, ~4542, ~5092, ~5152; `reshape.py` ~153) use `scope`, `frame` and `as_of`
  and read `status`, `entity_id` and `candidates`. They move over one-for-one.

**Location.** `porcelain.py` (the new verb); `refer.py` `__call__` (97) and
`_resolve_tier2` (225).

**Oracle:**
- **O9a.** `p.refer("the pipe")` equals the encoded `asdict(world.refer("the
  pipe"))`: resolved, `obj:pipe`, tier 1 `alias_exact`.
- **O9b.** "the drawer" in a study holding two drawers, `model=False`:
  `candidates` naming both, signal `no_model`, 0 model calls, head unchanged.
- **O9c.** A vocabulary miss in scope with `learn=False`: resolved at tier 2,
  head unchanged (D).
- **O9d.** `constraints=[["contains", "obj:spoon"]]`: the spoon's container,
  signal `constraint_inversion:contains(obj:spoon)`.
- **O9e.** `frame` and `asserted_as_of` pass through: D's oracles hold through
  the porcelain.
- **O9f.** Every return round-trips through `json.dumps`.

**Contract.** Additive: a new verb, and `model=` new on `Refer.__call__`.

**Byte-identical.** `world.refer` for every caller that doesn't pass `model`.

**MCP.** A new V1 read (§11).

## §10 Deferred: `events()` from one reader

This item moves to its own batch. It is not additive, and it is not in the
approved batch-E row: it is the surfaces audit's P2-5.

Reproduced (probe E10): with classification deferred, `events()` returns `[]`.
After `classify_all` it lists a pseudo-event, `obj:barn`, made from `(obj:barn ·
caused_by · event:fire)`.

Measured read-only in 168 world files:
- 1,575 `event:` rows are unclassified in 80 files (20 of them live), and
  `events()` silently omits them today. The commonest kinds among them are
  `identity_merge` (67 events) and `event` (33).
- 14 EVENT-classified rows on non-event subjects carry an `event:` id as their
  value, in 6 files, and each becomes a pseudo-event: 12 identity edges
  (`maybe_same_as`, `same_as`, `distinct_from`), one `caused_by` and one `in`.

Construct reads `events()` by kind for its session bookkeeping, and in unfiltered
windows (`turnloop.py` ~2860). Fixing both defects changes what it reads, so the
fix needs construct at the table.

The proposed shape for that batch:
- one `World._event_rows(frame, asserted_as_of)` that groups `event:`-subject rows
  by resolved id, without consulting the sidecar;
- `events()` and `in_transit()` both consume it;
- `events()` keeps its window rules, and its payload byte for byte, on a fully
  classified world without pseudo-events.

§8's `asserted_as_of` on `events()` is independent of this and lands in E.

## §11 The MCP surface

**Rule.**
- **Two new V1 reads:** `canonical_attribute` and `refer`. The registry grows
  from 39 to 41 on today's base, or 42 with C's `identity_conflicts`.
- **`refer` is served deterministic.** Tier 1 is V1, and tier 2 stays V1.1 (MCP
  sampling), as MCP-WRAPPER-V1 already says.
  - The server forces `model=False` and `learn=False`, so the tool makes no model
    call and no write even on a World that has a model.
  - Its annotations are read-only and idempotent.
  - A client gets the candidates and judges them itself.
- **One table replaces the special case:** `FORCED_PARAMS = {("seal_build",
  "model"): False, ("refer", "model"): False, ("refer", "learn"): False}`.
  - These parameters are omitted from the schemas (`OMITTED_PARAMS =
    frozenset(FORCED_PARAMS)`).
  - A client that sends one is refused before dispatch, with a message naming
    the parameter.
  - Dispatch fills the forced value.
- New parameters (§4–§9) appear in the generated schemas from their
  annotations; none needs an override. `state.value` and `state_union.value` are
  `Any` by contract.
- The launcher gains `--policy` (§7).
- **The completeness test stays meaningful**, in three checks:
  - every public porcelain verb is a V1 tool, V1.1 or Python sugar (unchanged);
  - every forced parameter is omitted, and every omitted parameter is forced;
  - the permissive-schema allowlist names exactly `who_knows.value`,
    `state.value` and `state_union.value`.

**Location.** `mcp.py` `V1_READS` (38), `OMITTED_PARAMS` (107), `dispatch` (212),
`main` (297).

**Oracle:**
- The registry holds exactly the declared tools, and the completeness test passes
  with `refer` and `canonical_attribute` classified.
- The zero-model smoke test (a raising-spy model) covers `refer` with an
  ambiguous kind word, and `canonical_attribute`: 0 calls, 0 writes.
- `dispatch(world, "refer", {"description": "x", "model": True})`, and the same
  with `"learn": True`, raise before dispatch. `seal_build` with `model` still
  raises.
- `who_knows` with a tag value over dispatch (§5).

**Contract.** Additive.

## What hosts see

| Change | Today | After |
|---|---|---|
| `state(e, "located_in")` | unknown | the `in` fold (§3) |
| A set-valued key | one member in `fact` | `fact` plus `values` (§4) |
| A conflicted key | ids in `conflicting` | plus `conflicting_facts` (§4) |
| An unresolved placeholder | `known`, the spec as the value | `unresolved` (§4) |
| Every Fact | — | `value_type` (§4) |
| `who_knows` on a set or a total, or with a `$decimal` tag | misses | matches (§5) |
| `ask` with a plan `as_of` after the caller's | answers from the plan's time | capped at the caller's (§6) |
| `ask` in a frame with its own word for a thing | binds by canon only | binds that frame's referent (§6) |
| A tracking world reopened without `policy=` | runs as fiction | runs under its stored physics (§7) |
| Reopen with a disagreeing `policy=` | silently runs it | `WorldPhysicsMismatch` (§7) |
| A new world | 2–4 genesis rows | one more: the physics row (§7) |
| `locate`/`contents`/`path` | canon only | `frame=` (§8) |
| As-of-the-log reads | none on the porcelain | `asserted_as_of=` on 20 reads (§8) |
| `refer` | below the porcelain | `p.refer` (§9) |

**Construct's reaches retire** (the audit's list):

| Reach | Retires onto |
|---|---|
| `game.py` `_live_in_candidates` (2175) | `state(…)["conflicting_facts"]` (§4) |
| `remembrancer.py`/`session.py` hand-folding `facts(knows:…)` | ADOPTION's frame-knowledge recipe (already on main), plus `state(…)["values"]` (§4) |
| `turnloop.py` `_canonicalize_containment` (1412) | `p.canonical_attribute` (§3) |
| Six `world.refer()` calls | `p.refer` (§9) |
| `adapter.py` `assertion_in_frame` (101) | `state(…, value=)["matches"]` (§5) |

## Non-goals

- `events()` from one reader (§10).
- `asserted_as_of` on `salience`, `in_transit`, `fidelity_audit` and `ask` (§8).
- Semantics hints on model-extracted items. Today a model item may carry
  `arity`/`relation_family`/`fold_policy` hints on first use, and after §2
  `last_write` is one of them. Restricting hints to host callers is a gate
  question for a later batch.
- A porcelain read of durability verdicts, or of physics beyond `facts()`.
- Changing a world's physics after creation (a physics-migration operation).
- Facts carrying pre-merge ids (audit P2).
- Historical identity under `asserted_as_of` (C's non-goal).

## Migration and notice

**Engine.** No log rewrite and no schema change.
- Pre-spec worlds open unchanged. The first open that names a `policy=` records
  the physics row (§7).
- New worlds carry one more genesis row.

**Ship notice to construct**, after build and GREEN:
- §1–§2: the two host-control levers and the recipe. They need new attribute
  names or new worlds (declare before data).
- §3: alias spellings now read; `p.canonical_attribute` for
  `_canonicalize_containment`.
- §4: the `unresolved` status (199 placeholder keys in 75 of its worlds now say
  so), `Fact.value_type`, `values`, `conflicting_facts`. The mirror stops copying
  thunk specs into the player's frame.
- §5: `who_knows` corrections (1,281 set-valued `knows:` keys); `matches` for
  `assertion_in_frame`.
- §6: the time cap (construct's play-horizon intent, Cx 255, now holds against
  the parse), and the player's own words binding first in the player's asks.
- §7: the physics row on new worlds and the `a:<seq>` shift; nothing for
  existing worlds, since construct passes no `policy=`.
- §8: `frame=` and `asserted_as_of=`.
- §9: `p.refer` for its six calls.
- The reach table above.

**Docs, in the build commit:**
- **ADOPTION:**
  - `canonical_attribute`, and the rule that attribute arguments are
    canonicalized;
  - the durability pin and `last_write`, with the host-control recipe and both
    cautions;
  - the `unresolved` status, `values`, `conflicting_facts`, `value_type`,
    `matches`;
  - retire the `who_knows` CAUTION;
  - `ask`'s time cap and binding order;
  - the physics row, `WorldPhysicsMismatch` and `--policy`;
  - `frame=` and `asserted_as_of=`;
  - `p.refer`, `model=` and `learn=`;
  - the MCP narrowings for `refer`.
- **LEXICON:**
  - new: *durability pin*, *fold policy* (`by_class`/`last_write`/`accrue`),
    *world physics row* (`resolution_policy`), `canonical_attribute()`;
  - updated: `who_knows()` (membership, totals, placeholders), *exact decimal*
    (a folded value match is numeric, as in `where`; the scale-sensitive match is
    the stored-row lookup `visible(value=)`).
- **WHITEPAPER:**
  - §5.1: host-declared pins;
  - §10: canonicalization holds at the read boundary too;
  - §13: the fold policies;
  - §16: "one file plus its policy row" is now literal;
  - §25.1: `refer` is on the porcelain, and `state()` adds Unresolved;
  - the next free amendment row after A–D's.
- **Dated notes** in PORCELAIN-V1 (Unresolved; the `ask` clause),
  ATTRIBUTE-SEMANTICS-V1 (§1's amendment; the fold vocabulary),
  WHO-KNOWS-INVERSE-V1 (its V1.1 membership, delivered) and MCP-WRAPPER-V1
  (counts, `refer`, forced parameters, `--policy`).
- `specs/STATUS.md`.

## Tests

- A new `tests/test_read_surface.py` holds one test per oracle, by section, plus
  §8's property test.
- Updated in the same commit, each citing the audit finding:
  - `tests/test_mcp_wrapper.py`: the counts, the smoke arguments for the two new
    tools, the permissive allowlist, the forced-parameter checks;
  - `tests/test_who_knows.py`, if any expectation encodes a winner-only match.
- A test that pins an absolute `a:<seq>` of a fresh World's rows shifts by one
  (§7). A grep finds none outside raw-buffer tests, which build no World.
- The full suite stays green.

## Decisions for Kabe (each with a default)

1. **Should `ask` bind the asker's own words before canon's?** (§6 rule B; D's
   open item and C's Q5.) It changes HD 003's precedence only where the asked
   frame binds the reference by itself (its own word for the thing, or the one
   thing of that kind it knows in the scene).
   - *Default:* yes, tier 1 only, never learning.
   - The alternative keeps canon-only binding; after C, a name only the asker
     holds then never binds in the asker's own questions.
2. **Should a pre-spec world record its physics the first time it is opened
   with `policy=`?** (§7.) The row is permanent.
   - *Default:* yes. The host is stating the physics it already runs the world
     under. Construct passes no `policy=`, so none of its worlds is written.
   - The alternative leaves every pre-spec world without physics, and without
     mismatch protection, forever.
3. **Remove `fold_policy: move` rather than give it a meaning?** (§2.)
   - *Default:* remove. No world declares it, and the containment rule stays
     keyed on `relation_family`.
   - The alternative gives a non-containment attribute the containment family's
     cross-source rule, a feature nobody has asked for.

## Build notes for pbr

Built 2026-10-09 on batch D (d7ae0bb, code-identical to main's merge of D) on
`impl/read-surface-v1`, against the independent oracle tests
(`tests/test_read_surface.py`, written from this spec alone). One commit per
section, in order; §9 and §11 share one. Each section's commit passes the
existing suite on its own, with its own and every earlier section's oracles
green.

**C §7 is held, so three places are amended** (commit 1297cd3). C shipped
without §7 (`knows:` frames following merges; Kabe's gate g3bf5da). The
"Founder decisions" bullet on C's #1 and #2, the §0 row for §8 ("C §6, C §7")
and §8's bullet "With C, an observer frame reads through identity" now say §7
is held and that §8's `frame=` reads the rows stored under the frame's own
name. No E behaviour depends on C §7, and no oracle uses a merge.

**Implementer's readings.**
- §1, the coherence check, is `AttributeSemantics.conflict(attribute,
  declaration)`. It judges a declaration against the attribute's effective
  semantics (built-in defaults under the declarations already in the log) and
  the other keys of the same declaration. Within one declaration the pin, or
  the fold policy, is the key refused: `{"structural": true, "durability":
  "STATE"}` reports `field: durability`, `conflicts_with: "structural=true"`
  (O1e), and `{"arity": "set_valued", "fold_policy": "last_write"}` reports
  `field: fold_policy`, `conflicts_with: "arity=set_valued"` (O2g). In the
  other order the later key is refused, naming the earlier one
  (`"durability=<class>"`, `"fold_policy=last_write"`). "Beside `arity:
  set_valued`" includes a built-in set, so `last_write` on `alias` skips: it
  could never take effect. The value is validated first (a bad value skips
  without `conflicts_with`), then coherence; either way the
  `attribute_default` callback stays unconsulted.
- §2: `is_last_write()` carries the read-side rule (set-valued and
  containment win over a stored `last_write`). `MOVE` is gone from
  `semantics.py`; `BY_CLASS` is the internal label.
- §3: `Ingestor.canonical_attribute` is `_canonicalize(name)[0]`. The
  porcelain's one helper passes a non-string through unchanged, and the
  `canonical_attribute` verb uses the same helper.
- §4: `ask` applies the key rules to its location fold too (it is the `in`
  key): a placeholder location is named in `unresolved`, not served with a
  chain; a conflicted one is served and named. `unresolved`/`conflicted`
  entries are de-duplicated and name the containment family `in`, as
  snapshot does. `values` is left out of an `unresolved` key's payload, so a
  set holding only placeholders never lists one as a member.
- §6: "a finite real number, not a bool" is read strictly: an int or float,
  finite, never a bool. A numeric-string plan `as_of` is ignored like any
  other invalid value (the gate coerces numeric strings for stored
  coordinates; a parse is not one). Rule B runs in every non-canon frame; a
  `plot:` frame has no asker scope, so it binds by its own vocabulary over
  its whole roster. `Refer.__call__(model=)` (§9's) landed in §6's commit
  because rule B needs it.
- §7: the buffer's validator also refuses a `retracts` row that targets the
  physics row. "Immutable" has to cover a retraction replayed from a tampered
  dump: a hidden physics row would leave the world unable to record its own
  (a second one is refused). The gate's refusal sits at the head of B §0
  step 2 (before the status grant) and matches the item's attribute after
  canonicalization. `World.policy` stays a plain attribute holding the
  effective policy. The policy vocabulary moved to `model.py`; `thunks`
  re-exports it.
- §8: `World.charter(asserted_as_of=)`; the porcelain threads the log
  position into each Fact's source chain.
- §9: `constraints` must be `[relation, anchor]` string pairs (ValueError
  otherwise) and reach `Refer` as tuples.
- §11: each new MCP piece landed with the section that introduced it, so
  every commit stays green: `canonical_attribute` with §3 (41 tools), the
  permissive allowlist with §5, `--policy` with §7, `refer` and
  `FORCED_PARAMS` with §9 (42). A forced parameter's refusal message names
  it.

**Oracle tests.** 116 collected: 114 pass; the 2 O7h launcher tests skip here
because the `mcp` SDK is not installed (both pass against a stand-in module
that lets `main()` reach `World`).
- Corrected, because the spec wins over the test: §3's confidence oracle
  read `confidence(ann, "located_in")["value"]`, as the spec's own oracle
  line does, but the confidence payload has no `value` key (CONFIDENCE-V1
  keeps it distinct from state's served value) and §3 adds none. The test
  now checks the rule itself: the alias spelling returns the `in` key's
  payload (score set, status stated), where it scored an empty key before.
- Strengthened: O4d also checks a served fact's `value_type` (resolve on a
  key that already holds concrete state), not only the denied path's empty
  list.
- AMBIGUOUS readings, settled as the tests read them: O1h (a whole-world
  rebuild still sends the charter's `stance`/`title`/`description` rows to
  the model, as before E; the pin, its data and the physics row make no
  call); O8b (neighbourhood salience is read at the head, a stated known
  limit, so it is compared without salience); §11 (42 on this base, C
  landed).

**Existing tests changed.**
- `tests/test_mcp_wrapper.py` (§3, §5, §11): the count (40 -> 42), the
  zero-model smoke arguments for `canonical_attribute` and `refer`, the
  permissive allowlist (exactly `who_knows.value`, `state.value`,
  `state_union.value`), the `FORCED_PARAMS` table and refer's forced
  parameters refused before dispatch.
- `tests/test_gate_authority.py` and its two fixtures (§7). The spec said a
  grep finds no absolute `a:<seq>` pins outside raw-buffer tests; batch B's
  tests, merged since, pin them. `_ann_calm` (`a:3` -> `a:4`), the raw
  `same_as` merge rows (`event:merge_6`/`a:7` -> `event:merge_7`/`a:8`), and
  the corpus log and sidecar fixtures, re-baselined. The new fixtures equal
  the old ones with each world's physics row inserted at seq 3 and every
  later id shifted by one, checked mechanically, so B's byte-identity pin
  still holds for everything else.
- `tests/test_who_knows.py`: unchanged; no expectation there encodes a
  winner-only match.

**Byte-identical, measured** on fresh copies of construct's 52 live world
files (snapshot of 04:30; no live file has changed since), base d7ae0bb
against the built head, `attribute_default` wired, a plan-scripted stub model
(refer tier 2 answers no-match), `PYTHONHASHSEED=0`. Every difference is one
this spec names; none is unexplained.
- Classifier guardrail verdicts: 72,583 rows, 0 differ. All 52 worlds open as
  `invent_under_canon` with 0 writes; 0 stored attribute names change under
  `canonical_attribute` (§3's measurement holds).
- `snapshot` per stored frame, NPC character sheets, the arc scope's
  establishing and situation lenses, `facts` per frame, `events` per frame,
  `locate`/`contents` (15,064), `path` (2,867 pairs): identical apart from
  `Fact.value_type`. The porcelain's `locate`/`contents(frame=)` equal
  `World`'s (10,384).
- `state` and `state_union`, 38,897 keys each: 32,834 identical apart from
  `value_type`; 31 placeholder keys (17 worlds) answer `unresolved`; 5,197
  set-valued keys gain `values` (49 worlds); 835 conflicted keys gain
  `conflicting_facts` (40 worlds).
- `who_knows`, 10,212 queries: 9,884 identical; 326 set-member queries now
  match (35 worlds); 2 placeholder-only frames drop (1 world).
- `world.refer`, 8,054 calls (every stored name and alias, canon and each
  storing frame): identical, 0 writes.
- `ask`, 8,054 scripted asks: 7,390 identical (1,130 of them now name a
  conflicted key); 37 stop serving a placeholder as a fact (4 of those flip
  to unanswered); 420 serve every member of a set; 207 non-canon asks bind
  the asker's own word (rule B). Of the 207, 206 are references canon could
  not bind; one overrides a canon binding. In
  `live_telegram_8786956263_2`, Bee's frame aliases "the camp" to
  `person:inez_calder` alone; canon carries that alias on four people, so
  canon binds the one camp in Bee's scene, `place:drainage_camp`, by kind.
  Rule B, as specified, puts Bee's alias first, and here that serves an
  extraction-made alias over the likelier place (the root cause gate g3bf5da
  also names). Default 1 is on Kabe's list to revisit; this is its one live
  case of overriding canon.
- Outside E: `snapshot(lens="establishing_set")` orders its facts and
  defaults by a set's iteration order (`Projector._establishing_scope`), so
  the order varies with `PYTHONHASHSEED` on base and new alike. Pre-existing;
  the measurement fixes the seed.

**For pbr's eye.** The readings above that go past the spec's letter: the
buffer refusing a retraction of the physics row (§7), `ask`'s location fold
under §4's rules, coherence judged against built-in arity (§1/§2), and the
strict `as_of` predicate (§6). And rule B's one live override of a canon
binding (above), which rests on default 1. `specs/STATUS.md` and the README's test count
move at merge, as B, C and D did.

## r1.1: pbr's RED on the build (2026-10-09)

pbr returned the build RED on one point of §7: the physics-row replay check
validated only the row's frame and value. A dump whose one physics row carried
`status="retracted"` built; on reopen the row was hidden from every read, so
the world ran as fiction, while `physics_row_id()` still found it, so the file
could never record the physics it runs under. The insert validator that
`append` and `dump.build` share now checks the row's whole shape, the one
World writes: `stated`, `literal`, timeless (no `valid_from`/`valid_to`), no
`confidence`, in canon, with a value in `POLICIES`, at most once. One
parametrized test builds a dump with the row in each wrong shape (two
statuses, an entity value type, either time, a confidence); each fails to
build and leaves no file. Nothing else changed.
