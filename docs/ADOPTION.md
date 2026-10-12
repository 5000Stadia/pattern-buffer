# ADOPTION.md — integrating pattern-buffer

**Audience:** agents (and humans) wiring this library into a host.
**Status: pre-1.0.** Hosts integrate against the **porcelain**
(`world.porcelain`): the frozen, additive-only contract `porcelain-v0.1`, all
I/O JSON-serializable (whitepaper §25.1; also served over MCP). The plumbing
surface further down is the layer below it, kept as reference — a host that
reaches into it is signalling a missing porcelain verb (report it; don't build
on the reach).

## The contract in one paragraph

The engine is a library below your host, not a peer beside it. It imports
nothing of yours and never calls you. You hand `World(...)` one callable
`(prompt: str, schema: dict) -> json` at construction — that is the entire
harness interface. From the engine's side every host is indistinguishable;
from your side the engine is indistinguishable from sqlite3.

## The three seams a host supplies

1. **The model shim** — two lines around your provider:
   ```python
   def shim(prompt: str, schema: dict) -> dict:
       return your_provider.complete(prompt, json_schema=schema)
   world = World("campaign.world", world_id="w:campaign", model=shim)
   ```
   The engine calls this callable **synchronously and unbounded** — every model
   path (extraction, classification, thunk resolution, `refer` tier-2, `ask`)
   blocks until your shim returns. **Bounding the call is yours, not the
   engine's** (see MUST/NEVER): a hung provider read will wedge the calling
   build until *your* timeout fires, so wrap the shim in your own runtime's
   deadline (and recycle the worker — a blocked socket read can't be cancelled
   in-thread, only abandoned). The engine cannot bound it for you without
   reaching into process-global signal state or leaking the very thread it
   couldn't kill — both worse than honest blocking, both violations of "the
   engine never reaches into the host." Best of all, avoid the call: rows you
   know are durable should be declared `structural` via `attribute_default` (or
   pinned to a durability class, see "Host-control vocabulary" below) so the
   classifier skips the model entirely.
2. **The binding table** — your scoping unit (workspace, channel, space) →
   `world_id`. Many scopes → one world is allowed; one scope → many worlds is
   not. Fiction scopes bind to private worlds; all real-life scopes bind to
   *the* member's one world, with frames doing the scoping you expect.
3. **Frame entitlement** — which consumer sees which frames. Your existing
   disclosure machinery acts as one consumer policy over frames; frames remain
   the storage mechanism.

## The plumbing below the porcelain (reference)

```python
World(path, world_id, model=None, policy=None, clock=time.time)
  # policy: "invent_under_canon" (fiction) | "observe_or_unknown" (tracking) | "deny"
  # A world file carries its physics (READ-SURFACE-V1 §7): a new world records its
  # policy as the physics row `attr:__world__ · resolution_policy · <policy>`
  # (canon, timeless, immutable), and every later open runs under it. Omit policy=
  # to run under the stored physics (invent_under_canon for a world that records
  # none); an explicit policy= that disagrees raises WorldPhysicsMismatch (a
  # ValueError) and writes nothing. A world created before this records its policy
  # the first time it is opened with an explicit policy= (one row, permanent).
  # world.policy reads the effective physics; facts("canon", entity="attr:__world__")
  # lists the row. A world that needs other physics is a new world.

# Writes — each behind its enforced role; you cannot mint write authority:
world.ingest(text, context="", frame=None) -> list[Assertion]   # LLM extraction via the gate
world.ingest_structured(items, frame=None) -> list[Assertion]   # pre-extracted items, same gate
#   frame= targets a NAMED frame (knows:<id> seeding, plot: arcs) — letter
#   028: frame is a write TARGET through full gate discipline, never an
#   authority escape; per-item frames win over the default.
world.resolve(entity, aspect, frame="canon", access=None)  # force a thunk per policy
world.truth.retract(assertion_or_id, reason) -> Assertion  # corrections append

# Reads — deterministic, zero model calls (P7):
world.locate(entity) -> list[str]              # containment chain, nearest first
world.contents(container) -> list[str]         # emptiness is [] — derived, never stored
world.state(entity, attribute, frame="canon", valid_as_of=None, asserted_as_of=None) -> FoldResult
world.path(a, b, valid_as_of=None) -> list[str] | None   # None = not connected; proximity is not connectivity
#   valid_as_of=T routes as the lateral graph stood at T: a SEVERED edge (its
#   connects_to/adjacent_to given a valid_to at the failure) drops from current
#   routing, while an earlier as-of still shows it (history preserved). Removal
#   is temporal, never a stored flag. NOTE: connects_to is a many-to-many
#   passage edge (path unions all current edges, no recency-fold) — to retire an
#   edge, end it with valid_to; a later connects_to does NOT supersede an old one.
world.salience(entity, frame="canon", as_of=None) -> float
world.neighborhood(entity, depth=1, frame="canon", as_of=None,
                   edge_kinds=None, max_fanout=64, budget=None) -> dict
world.materialize(scope, as_of=None, frame="canon",
                  lens="current_state",        # | establishing_set | what_happened | character_sheet | situation
                  budget=None, asserted_as_of=None) -> Materialization
#   lens="situation" (re-entry): standing-truth fold ∪ only the LIVE events
#   anchored to the scope, closed history dropped. Live = an open thread OR a
#   still-served (un-superseded) produced effect; anchored by where the live
#   effect sits (walk back via caused_by), not by who participated. The
#   standing-truth floor is never truncated by budget; live events yield to it
#   by recency. Derived every read, nothing stored.
#   ADOPTER NOTE: the lens is only as live as your caused_by links. An event
#   with no caused_by-bound surviving effect (or open thread) about a scope
#   entity reads as DEAD and won't surface — fail-safe, not an error, but it
#   means situation returns the standing floor only until you wire durable
#   consequences to their causing event. Model the residue, link it, it lights up.
#   Which lens shows an event (EVENTS-ONE-READER-V1): lens="what_happened" serves
#   the whole RECORDS of the events the scope is involved in — its id is in scope,
#   or its record names a scope entity (an agent, a patient, the place it happened
#   `in`, a cause) — as of as_of; situation emits its live events as records. The
#   standing lenses (current_state, establishing_set, character_sheet) never show
#   an event's rows: an event row never folds, classified or not, so an event is
#   never inside a container either (contents/locate/the scope walk).
world.confidence(entity, attribute, frame="canon", as_of=None,
                 asserted_as_of=None) -> dict
#   frame accepts str | list[str]: a list is trust over an observer's EFFECTIVE
#   knowledge = the read-union of those frames (knows:O ∪ public), mirroring
#   multi-frame frame_diff. Derived; functional-only.
world.refer(description, scope=None, frame="canon",
            constraints=None, as_of=None, asserted_as_of=None,
            learn=True, model=True) -> Resolution
#   model=False (READ-SURFACE-V1 §9): tier 1 only — where tier 2 would judge,
#   the result is candidates with signal "no_model", and nothing is learned.
#   On the porcelain: p.refer (below).
#   Tier 1 (no model call): a name/alias ("alias_exact"); a constraint
#   (contains / owned_by -> the owner / held_by); the one entity of a kind in
#   scope ("unique_kind_in_scope"); a word refer learned ("learned_alias").
#   Tier 2 judges two or more candidates, or a vocabulary miss in `scope`.
#   asserted_as_of: tier 1 reads as of that log position, and nothing is
#   written. learn=False: nothing is written. See "refer learns words, never
#   picks" below.
#   Tier 1 reads names, aliases and learned words in `frame` only, never
#   canon's for a non-canon frame (an alias only canon carries does not
#   resolve in knows:X); a learned word lands in `frame`
#   (FRAME-SCOPED-IDENTITY-V1 §1(e), §2).
world.registry.by_alias(text, asserted_as_of=None, frame="canon") -> set[str]
```

### refer learns words, never picks

`refer` writes exactly one thing, and only on a **vocabulary miss**
(REFER-LEARNING-V1): tier 1 found no candidate in your `scope`, and tier 2
mapped the expression onto one entity there. It then appends one
`learned_alias` row — the expression, normalized, as a word for that entity:
timeless, `inferred`, in the call's `frame`, with a `source` receipt
`refer:tier2:…`. The next time, that word resolves at tier 1
(`["learned_alias"]`, zero model calls), but only after every authored name,
alias and unique kind in scope has found nothing, and only where its entity is
in the caller's scope (with no scope, the whole world is the scene). So
"the old cupboard" learned in the kitchen is re-judged in the garage.

- **A pick is never written.** "The drawer" in a room with two drawers is
  judged by tier 2 on every read and appends nothing. Reads don't grow the
  log. If you want per-conversation memory of picks, cache `Resolution`s
  under your own conversation key; the engine has no conversation.
- **Never written:** with `learn=False`, from a pinned read
  (`asserted_as_of`), or by `ask` (which writes nothing at all).
- **Not identity.** A learned word never merges entities, never shows up in
  `name_collisions`, and never stands as a fact in a snapshot (it is EVENT
  bookkeeping, like `same_as`). To make a word a real name, author an
  `alias`. To drop a wrong one, retract it.
- **Legacy rows.** Before this rule, refer wrote a canon `alias` for every
  confident tier-2 answer. Those rows are never rewritten. `refer` reads them
  as learned words (tier 1d, scoped), and every other read still sees them
  as the `alias` rows they are. To list them, and the words learned since:

```python
legacy = [f for f in p.facts("canon", attribute="alias")
          if any(str(s).startswith("refer:tier2:")
                 for s in f["provenance"]["source_chain"])]
learned = p.facts(frame, attribute="learned_alias")   # words learned after this spec
```

### Typed outcomes, not exceptions

Domain outcomes are values you must branch on:

- `Resolution.status` ∈ `resolved | candidates | underdetermined` — an
  underdetermined reference is YOUR ask to deliver to the user; the engine
  never guesses below its confidence floor.
- `FoldResult.conflicted` — the key is under an open truth-maintenance flag;
  `winner` is the engine's holding answer, `conflicting` lists both sides. On
  the porcelain, `state()` adds `conflicting_facts` (one Fact per side) and
  answers `unresolved` when the served row is a placeholder (READ-SURFACE-V1
  §4).
- `FoldResult.quantity` — for attributes declared `fold_policy="accrue"`,
  the folded numeric total. The `winner` is provenance for the latest ledger
  row, not the value a host should read.
- `resolve()` returns the module-level sentinel `UNKNOWN` in
  `observe_or_unknown` worlds when nothing was observed. "I don't know" is a
  representable answer; treat it as one.
- `Materialization.unresolved` names the frontier in scope; `defaults` are
  render-coherence fills marked `default` — never facts.
- `Materialization.quantities` carries derived totals as `(entity,
  attribute, value)` tuples. These totals are not stored assertions.

### Numeric quantities

For fungible counts such as gold, ammo, liters, or charges, declare the
attribute with `fold_policy="accrue"` before its first data row. A `literal`
numeric row is an absolute baseline; a `value_type="delta"` row is a signed
increment. The fold computes `baseline + later deltas`, with the ledger
available as `FoldResult._ledger_rows` for audit. `int` and `float` are
supported for game-grade quantities.

**Exact decimal (money, real ledgers).** When a quantity must fold exactly
(`0.10 + 0.20 == 0.30`, never `0.30000000000000004`), author it as a Python
`Decimal` (in-process) or the tag form `{"$decimal": "12.50"}` (JSON) — both
normalize to the same stored row. Rules that follow from append-only fidelity:

- **Pick one representation per attribute.** A fold mixing exact-decimal and
  `float` **raises** (an authoring smell, surfaced not silently promoted);
  `Decimal` + `int` folds exactly.
- **Authored scale is preserved.** `12.50` round-trips as `12.50`; a
  `visible(value=...)` match is scale-sensitive (`12.5` does not match `12.50`).
- **Porcelain payloads carry the tag dict**, never a raw `Decimal` — every
  verb's return stays plain-`json.dumps`-able. Core reads (`World.state`,
  `materialize`) return real `Decimal` objects; if you re-serialize those
  yourself, use `patternbuffer.codec.encode_out` (or `json_default`).
- `avg` over decimals divides under a fixed context (prec=50, HALF_EVEN) —
  deterministic; sums are exact. Currency codes, units, and rounding *policy*
  are host meaning — model them as ordinary facts, not value forms.

### Declaring what the resolver may invent: `resolvable_for`

By default `resolve(entity, aspect)` invents only for a placeholder somebody
planted first; with none, a story world answers `[]`. A host opts an aspect in
with set-valued `attr:<aspect> · resolvable_for · <kind>` rows (a lowercase kind
name; one row per kind), written through `ingest_structured` or supplied from
`attribute_default` (`{"resolvable_for": ["person"]}`, applied when an item on
the attribute is first ingested; for an aspect that is never ingested as a row,
such as `contents`, write the `attr:` rows once). Read them with
`world.semantics.resolvable_kinds(aspect)`. When an entity of a declared kind
holds no value for the aspect (for `contents`, holds nothing), `resolve` plants
the resolver's own `generated` placeholder and forces it in one atomic unit,
and the result says `"planted": true`; the next call is the memo. The
placeholder sits at `at` (default: the scene cursor), or timeless when the
aspect's durability pin is `CONSTITUTIVE` or `DISPOSITIONAL`. `at` poses the
cursor exactly as `ingest_structured(at=)` does, on every path. In a world with
at least one declaration, an aspect or kind nobody opened answers
`{"status": "undeclared", "reason": ...}`; a world with none answers exactly as
before. The engine never decides what may be invented: the host declares
it, and a declaration on a core attribute (`in`, `kind`, `name`, ...) skips
`invalid_semantics_declaration`. Unlike the other declarations it may follow
existing data.

### Host-control vocabulary: the durability pin and `last_write`

Two declarations (READ-SURFACE-V1 §1–§2) let a host fix how its OWN
bookkeeping attributes behave, without the model. Both are ordinary
`attr:<name>` declarations, from `attribute_default` or a manual `attr:` row;
neither is an item hint.

- **The durability pin** — `{"durability": "STATE" | "DISPOSITIONAL" |
  "CONSTITUTIVE"}` (never `EVENT`: occurrence stays structural). Every row of
  the attribute takes that class at confidence 1.0, before `structural` and the
  model, on every classification path; the model is never asked, the row is
  never `needs_review`, and accrual promotion skips it. Undeclared vocabulary
  stays per-row and model-judged. A pin on `name`, `alias` or a META attribute
  could never take effect, and a non-`CONSTITUTIVE` pin beside
  `structural: true` contradicts it: both skip `invalid_semantics_declaration`
  with `detail.conflicts_with`.
- **`fold_policy: "last_write"`** — the key serves its latest row by
  `(valid_from, asserted_at)` among the rows of the top evidence rank, whatever
  their durability: never conflicted, no cross-source flag. A later
  `inferred`/`assumed` row still never displaces a `stated` one. Functional
  attributes outside the containment family only (beside `arity: set_valued` or
  `relation_family: containment` it skips, `conflicts_with` naming the other
  axis). `fold_policy: "move"` is no longer declarable (it skips); the
  containment family's cross-source move rule is unchanged.

They are two orthogonal axes: the pin decides the class (which lens serves the
row, budget exemption, whether the model is asked), the fold policy decides
which row of a key is served. The recipe:

```python
def attribute_default(attribute):
    if attribute in MUTABLE_HOST_CONTROL:      # e.g. an arc phase you rewrite
        return {"durability": "STATE", "fold_policy": "last_write"}
    if attribute in IMMUTABLE_HOST_ENUMS:      # set once, never changed
        return {"durability": "CONSTITUTIVE"}  # or {"structural": True}, as before
    return None
```

A STATE pin alone still conflicts when you rewrite a key at the same stamp or
timelessly; `last_write` alone still sends every row to the model. Two
cautions:

- A timeless STATE row is listed in `fidelity_audit`'s `unstamped_timed`.
  Timeless bookkeeping should pin `DISPOSITIONAL` or `CONSTITUTIVE`.
- **Declarations precede data.** Once an attribute has a row, any declaration
  on it raises. Attributes that already carry rows (an existing `status` or
  `phase`) keep their behavior; the levers apply to new attribute names or new
  worlds.

## MUST / NEVER

- **MUST** route every write through the gate — on the porcelain, `ingest` /
  `ingest_structured` / `commit_set` / `resolve` / `retract`. There is no other
  write path; do not look for one.
- **MUST** use ids in the gate's grammar — `^[a-z][a-z0-9_]*:[a-z0-9_:]+$`:
  lowercase, digits, `_` and `:` only (`thing:press_N1`, `person:jean-luc` and
  `doc:letter.1` are all malformed). A malformed id is **skipped with a typed
  `malformed_id` receipt, never raised and never normalized** (normalizing would
  be an identity guess). **MUST** check `Receipt.skipped` after every write.
- **MUST** name knowledge frames by the full entity id: `knows:person:daniel`,
  never `knows:daniel`. Nothing validates the suffix today, so a short form
  silently becomes a different frame.
- **Identity is canon's** (FRAME-SCOPED-IDENTITY-V1). `same_as`,
  `maybe_same_as` and `distinct_from` are written and read in canon only.
  Outside canon the gate skips them: a `same_as`, whether a raw item or an
  item's `same_as` key, with `same_as_not_canon` (`detail: {field: "frame",
  value: <frame>}`; for the key, the item's own row still lands), and a
  `maybe_same_as` or `distinct_from` with `identity_edge_outside_canon`. A
  belief about identity ("Alice thinks the masked man is Bob") is an `aka` row
  in the believer's frame. Legacy non-canon identity edges are inert.
- **Description is perspectival.** An item's `aliases` land in the item's
  frame, and `name`/`alias` rows are read only in their own frame:
  `registry.by_alias(text, frame=)` and `refer(..., frame=)` read the asked
  frame only, with no canon fallback, so Alice's private alias for Bob
  resolves in `knows:person:alice` and never in canon. `ask()` in a
  non-canon frame binds the asker's own words first — the asked frame's
  tier 1 alone (its names, aliases, learned words, a kind unique in its view
  of the scene), model-free and learning nothing — and otherwise resolves
  against canon (HD 003; READ-SURFACE-V1 §6). Canon `reconcile`,
  `proposals`, `typing_conflicts`, `retype` and every merge veto read canon
  rows only.
- **MAY** pass any spelling of an attribute to a read: every porcelain
  argument that names an attribute (`state`, `state_union`, `where`,
  `aggregate`, `facts`, `confidence`, `who_knows`, `resolve`, each `ask` plan
  key) passes through the gate's own canonicalization first, so
  `state(e, "located_in")` reads the `in` key the gate stored
  (READ-SURFACE-V1 §3). `p.canonical_attribute(name)` returns the gate's name;
  use it instead of copying the alias map. Payloads echo the stored name.
  Inverse spellings (`holds`, `wearing`) are not renamed.
- **MUST** treat a `status` you do not recognize as not known.
  `state()`/`state_union()` answer `unknown`, `known`, `conflicted` or
  `unresolved` (READ-SURFACE-V1 §4: the served row is an unresolved
  placeholder — its `fact.value` is the thunk spec, never a value to show or
  copy into another frame).
- **NEVER** reopen a world under other physics: `World(..., policy=)` that
  disagrees with the world's stored physics row raises `WorldPhysicsMismatch`.
  Omit `policy=` to run a world as it was made (READ-SURFACE-V1 §7).
- **MUST**, after reopening a world, place the scene cursor before the first
  untimed write (`at=`, e.g. from `axis_heads()["valid_head"]`): the cursor
  starts at 0.0 on every open, so an untimed row otherwise lands at t=0 and
  loses to every later-stamped row on its key.
- **SHOULD** load bulk structured data with `ingest_structured(..., atomic=True)`:
  one transaction instead of a commit per row. A 3.4k-row case loaded in ~1.2 s,
  against ~43 s without it, and the world was byte-identical.
- **MUST** give an instant a non-zero interval: valid time is half-open, so a
  row with `valid_from == valid_to` is never visible. Write `[t, t+1)` (or omit
  `valid_to`). A second value asserted over the same window is a same-time
  contradiction (the key reads `conflicted`): to correct a value, `retract` the
  old row first.
- **NEVER** write a mechanism attribute as an item (GATE-AUTHORITY-V1 §1):
  `retracts`, `resolved_by`, `canonicalized_from`, `learned_at_wallclock`,
  `source_valid_from` and `correction_proposal` are rows the engine writes
  *about* other rows. The gate skips such an item (`mechanism_attribute`) on
  every path, and the engine reads one only with its owner's mark, so a copied
  or forged row never hides, spends, aliases or refreshes anything. Use the
  doors: `retract`
  (or a `commit_set` retract op), `resolve`, an item's `correction: true`; the
  gate writes its own receipts, tracking stamps and demoted coordinates. If you
  feed engine rows to an extractor as context, expect the model to copy some:
  they come back as receipts, never as effects.
- **MUST** assert identity in canon. A raw `same_as` item **is a guarded merge**
  (GATE-AUTHORITY-V1 §2): it goes through the same path as `p.merge` (the
  containment and `distinct_from` vetoes are absolute) and writes the merge's
  four `inferred` rows (the `identity_merge` event, the `same_as` edge, its
  `caused_by`, the evidence) instead of one `stated` row. A raw one outside
  canon is skipped `same_as_not_canon` (identity is not perspectival), a vetoed
  one `merge_vetoed` (`detail` names the veto and the blocking edges), a value
  that is not an id `malformed_id`; a pair already merged writes nothing. When
  a refused one names a real duplicate, route the receipt to `p.confirm` (a
  canon proposal exists) or `p.merge`. (An item's `same_as` *field* still only
  proposes, as a canon `maybe_same_as`; on a non-canon item it is skipped
  `same_as_not_canon` too — FRAME-SCOPED-IDENTITY-V1 §1.)
- **MUST** read `Receipt.skipped` as the whole refusal record: every write
  path fills it, `p.ingest()` included, and a malformed item (a non-object, a
  missing field, a bad `frame`, a `confidence` or flag of the wrong type, an
  invalid semantics declaration) is skipped with a code instead of raising
  mid-chunk or being stored. Authority violations (a status outside the
  ingestor's grant, `generated` into canon/`knows:*`) still **raise**, before
  anything of the item is written. The codes are in THE PORCELAIN below.
- **Inverse predicates (`holds`, `wearing`) — GATE-INVERSE-ALIAS-V1.** The gate
  now swaps direction: `person:ralph holds thing:key` is stored as `thing:key
  held_by person:ralph` (receipt `(inverse) holds->held_by`); `wearing` likewise
  to `worn_by`. A text value (`ralph holds "a lantern"`) is NOT aliased — it
  stays an ordinary `holds` domain fact. Prefer writing `<thing> held_by
  <person>` directly. `add_attribute_alias("holds", ...)` raises `ValueError`.
  A skip record for a swapped item carries `detail: "authored: person:ralph
  holds thing:key"` (the field is present only when set).

  **Rows written BEFORE the fix** were renamed without the swap (Ralph stored
  inside the key) and keep their forward receipt `holds->held_by` /
  `wearing->worn_by`; the engine never rewrites them. **Until you repair them,
  the CORRECT write on the same pair is refused** (`thing:key held_by
  person:ralph` is a containment cycle against the inverted row): it is skipped
  with a `Receipt.skipped` cycle reason, and inside `atomic=True` / `commit_set`
  it aborts the whole set. Two shapes the receipt alone does not find: a host
  that re-ingests promoted values into `canon` leaves **receipt-less copies**
  (the same `held_by`/`worn_by` triple with no receipt, possibly in another
  frame), and a **text-valued** inverted row (`ralph held_by "a lantern"`) is
  not an edge at all. The recipe reports both. Run it with the porcelain you
  already have; repair is your call per group (some rows may have been nonsense
  either way):

  <!-- recipe:inverted-rows (executed verbatim by tests/test_ingest_hardening.py) -->
  ```python
  import re
  ID_RE = re.compile(r"^[a-z][a-z0-9_]*:[a-z0-9_:]+$")   # the gate's id grammar
  FORWARD_OF = {"holds": "held_by", "wearing": "worn_by"}
  INVERSE_OF = {v: k for k, v in FORWARD_OF.items()}
  receipt_of = {f["entity"]: f["provenance"]["assertion_id"]
                for f in p.facts("canon", attribute="canonicalized_from", include_meta=True)
                if f["value"] in ("holds->held_by", "wearing->worn_by")}
  scanned = [(frame, f) for frame in host_frames
             for f in p.facts(frame, attribute="held_by") + p.facts(frame, attribute="worn_by")]
  triple = lambda f: (f["entity"], f["attribute"], f["value"])
  receipted = {triple(f) for _, f in scanned if f["provenance"]["assertion_id"] in receipt_of}
  inverted = []            # one dict per already-inverted row
  for frame, f in scanned:
      aid = f["provenance"]["assertion_id"]
      if aid in receipt_of or triple(f) in receipted:      # receipt-less copies included
          inverted.append({"assertion_id": aid, "frame": frame,
                           "entity": f["entity"], "attribute": f["attribute"],
                           "value": f["value"], "valid": f["valid"],
                           "value_type": ("entity" if isinstance(f["value"], str)
                                          and ID_RE.fullmatch(f["value"]) else "literal"),
                           "receipt_id": receipt_of.get(aid)})   # None = receipt-less copy

  def repair_ops(group):
      """One group = every copy of one (frame, entity, attribute, value). Retract
      them ALL, assert ONCE (a second copy would be refused as a cycle). Returns
      the `commit_set` ops; commit one group per call so one failure aborts only
      that group."""
      first = min(group, key=lambda d: (d["valid"][0] is None, d["valid"][0] or 0.0))
      ops = [{"op": "retract", "assertion_id": d["assertion_id"],
              "reason": "GATE-INVERSE-ALIAS-V1 repair: inverted row"} for d in group]
      item = {"frame": first["frame"], "valid_to": first["valid"][1]}
      if first["valid"][0] is None:
          item["timeless"] = True              # keep the original interval
      else:
          item["valid_from"] = first["valid"][0]
      if first["value_type"] == "entity":      # swap: the person is the value
          item.update(entity=first["value"], attribute=first["attribute"],
                      value=first["entity"], value_type="entity")
      else:                                    # text: a literal holds/wearing, never a swap
          item.update(entity=first["entity"], attribute=INVERSE_OF[first["attribute"]],
                      value=first["value"], value_type="literal")
      return ops + [{"op": "assert", "item": item}]

  groups = {}
  for d in inverted:
      groups.setdefault((d["frame"], d["entity"], d["attribute"], d["value"]), []).append(d)
  # for g in groups.values(): p.commit_set(repair_ops(g))   # host-judged
  ```

  Receipt rows live in `canon` whatever frame the row they describe is in;
  post-fix swapped rows carry the `(inverse)` receipt and are not matched.
  `valid` is the original `[valid_from, valid_to]`; the re-assert keeps the
  earliest-starting copy's interval (first copy on a tie).
- **NEVER** let your renderer/narrator append. The component that speaks must
  not decide what is true. Resolution-as-a-tool is fine — the tool's
  implementation is the resolver, which holds the append authority.
- **NEVER** map a host scope to more than one world, or split one world
  across buffers (the 1:1 invariant). Bind scopes; don't partition.
- **NEVER** write a world file through one `World` while another `World` — in
  another process, or a second handle in this one — holds the same file open.
  Each `World` is its file's only writer: it tracks the log head and its
  derived read caches in memory and does not see another connection's appends
  until it is reopened. One live `World` per file; route readers through it.
  Enforced: a handle that notices another connection's commit raises
  `SecondWriter` on its next operation (and every one after; reopen to
  recover). A `World` is also bound to the thread that opened it (SQLite's
  own check): hand work to that thread rather than sharing the handle.
- **MUST** preserve frame absence: serve consumers only frames they are
  entitled to; out-of-frame content is absent from the payload already — do
  not re-add it from caches.
- **NEVER** store anything derivable (location, emptiness, age, staleness,
  salience) on your side as truth; query it.
- **MUST** treat `generated`/`default` provenance as non-promotable; in
  tracking mode kind-defaults may render but never become facts.
- **MUST**, in `observe_or_unknown` worlds, let the gate stamp wall-clock
  learned-at meta-assertions (it does this automatically; do not strip them —
  staleness decay computes from them).
- **MUST** bound the model callable in your own runtime. The engine invokes it
  synchronously and unbounded on every model path; it deliberately adds no
  timeout (a real cancellable deadline can only live where you own the
  worker/process — the engine could only abandon-and-leak the thread or hijack
  process signals, both forbidden). A flaky provider's blocked read otherwise
  hangs the build indefinitely. Prefer declaring known-durable rows `structural`
  so the classifier never calls the model at all. A wedged build is **truth-safe
  but not atomic**: `ingest_structured` appends a row then classifies it inline,
  so a timed-out classifier can leave a committed log prefix and an unclassified
  sidecar row. Truth is intact (the log is append-only, the sidecar rebuildable,
  unclassified reads fall back to `STATE`) — but a killed bulk build is **not** an
  all-or-nothing artifact. If atomic scenario publication matters, build in a
  staging world; after recycling a timed-out model worker, finish classification
  before serving or swapping the world.

## THE PORCELAIN (frozen at porcelain-v0.1; additive-only henceforth)

`world.porcelain` — the typed, JSON-serializable host surface
(specs/PORCELAIN-V1.md is the contract):

```python
p = world.porcelain
p.extract(text, scene=None, extract="full"|"lean", pov=None) -> [item dict]
   # INGEST-LATENCY-V2: READ-ONLY extraction (no write). Parallelize N extract() calls
   # in YOUR runtime (your concurrency cap), then ingest_structured() the results SERIALLY
   # (append-only writes stay serial). The engine doesn't add concurrency (membrane).
   # pov (SHAPE-FIX-V1): the viewpoint entity id — the full scoped deictic family (singular I/me/my/mine/myself + addressed you/your/yours exclusively; plural we/us/our/ours inclusively — a singular possessee never attributes sideways)
   #   bind to it instead of minting a phantom person:you. Id-validated before the prompt.
p.ingest(text, source=None, scene=None, at=None, frame=None,
         classify="inline"|"batch"|"defer"|"rules", extract="full"|"lean",
         cursor_authoritative=False, pov=None) -> Receipt
   # classify (HD 079/083): "batch" = ONE durability call/passage; "rules" = guardrails +
   #   STATE default, ZERO LM calls (fast+deterministic, eval-guard quality); "defer" skips.
   # extract (HD 082): "lean" trims the prompt (marginal input-side lever; eval-guard).
   # cursor_authoritative (HD 084): the cursor governs valid_from for all rows — bible
   #   source-ingest, so a diegetic year can't invert the story-time axis; the overridden
   #   per-item valid_from is preserved losslessly as a `source_valid_from` meta (host
   #   promotes to a typed year/era fact if wanted). Default off = per-item valid_from wins.
p.ingest_structured(items, frame=None, classify="inline"|"batch"|"defer"|"rules",
                    cursor_authoritative=False, at=None, extracted=False,
                    atomic=False) -> Receipt
   # The extract() -> ingest_structured() recipe MUST pass extracted=True (MOVED-EVENT-V1
   #   §B.3): prose-mode items get engine-authored movement timestamps; without it,
   #   model-written times survive. atomic=True (ATOMIC-ACTIVATION-V1): all-or-none —
   #   any gate skip aborts the whole call with AtomicAbort (see below).
   # INGEST-HARDENING-V1: classify="batch" defers durability + runs ONE batch model
   # call per ingest call (the first-class form of classify_inline=False + classify_all;
   # ~65% build-time cut on generate-path builds) — use it for bulk/scenario ingest.
   # "inline" (default) = per-row; "defer" = no classify (host runs classify_all later);
   # "rules" = guardrails+STATE, zero LM.
   # at (AXIS-HEAD-V1): places the scene cursor before the commit — the per-chunk pose for
   #   parallel-extract/serial-commit paths (mirrors ingest(at=)). A call that raises with
   #   nothing written (an authority violation, a bad classify mode, a failing model, an
   #   AtomicAbort) leaves the cursor where it was; after a partial non-atomic write it
   #   stays at `at`, where those rows were stamped (GATE-AUTHORITY-V1 §6; ingest(at=) too).
   # frame= is a DEFAULT for unframed items, NOT an override (letter 028) — per-item frame
   #   keys WIN, which mixed batches require (a telling scene's knows:B rows must survive).
   #   NOTE: extract() returns RAW model output, and extracted items MAY carry their own
   #   frame (the schema declares it optional; live providers commonly stamp canon
   #   explicitly) — never ASSUME extraction output is unframed. To quarantine/
   #   stage a batch wholesale, apply YOUR policy to a COPY first (strip or reject item
   #   frames — retaining knows:* bypasses your quarantine; stripping erases knowledge
   #   semantics; which is right is your world-policy call, not the engine's or the
   #   model's). When frame= is given and items keep a different own frame, the Receipt
   #   carries a warning (never silent — HD 121).
   # The Receipt's `skipped: [{entity, attribute, value, reason[, detail]}]` lists what the
   # gate refused, on every write path, p.ingest() included (its extraction call's skips,
   # then its source= stamping call's). `reason` is a fixed code from
   # patternbuffer.ingest.SKIP_REASONS (GATE-AUTHORITY-V1 §0), or one of three legacy
   # per-edge prose reasons ("cycle-forming containment edge: …", "lateral self-loop: …",
   # "merged_self_edge: …"; match substrings). The codes:
   #   malformed_id     an id outside the grammar in any position — person:/you,
   #                    thing:press_N1, person:jean-luc, or an id-shaped typo on an
   #                    entity-valued predicate (in: "Place:Cellar"); never normalized
   #   malformed_item   not an object; entity/attribute/value missing; a blank attribute;
   #                    a frame that is not a non-empty string (never defaulted to canon)
   #   invalid_field    value_type outside entity|literal|unresolved|delta; timeless or
   #                    correction not a bool (0/1 read as false/true); confidence not a
   #                    finite number (numeric strings are coerced, like times)
   #   invalid_alias    one aliases member that is not a non-empty string (the rest of the
   #                    item lands; a string is ONE alias, a tuple/set a list)
   #   invalid_valid_time, valid_to_without_valid_from, valid_to_before_valid_from,
   #   invalid_decay_halflife, moved_marker_invalid, moved_open_with_arrival,
   #   moved_complete_attribute_not_durable
   #   mechanism_attribute, same_as_not_canon, merge_vetoed (see MUST / NEVER)
   #   identity_edge_outside_canon   a maybe_same_as / distinct_from row outside canon
   #                    (FRAME-SCOPED-IDENTITY-V1 §1; a same_as there, raw or an item's
   #                    same_as key, is same_as_not_canon)
   #   invalid_semantics_declaration   an arity/relation_family/fold_policy/structural/
   #                    durability value outside its vocabulary (fold_policy is last_write|
   #                    accrue — `move` is gone; durability is STATE|DISPOSITIONAL|
   #                    CONSTITUTIVE, never EVENT), or a declaration that could never take
   #                    effect or contradicts another on the attribute (detail.conflicts_with:
   #                    "guardrail", "structural=true", "durability=<class>",
   #                    "arity=set_valued", "relation_family=containment",
   #                    "fold_policy=last_write") — the WHOLE item skips, nothing declared
   # `detail` appears only when set: the bad field and value, the merge veto and blocking
   # edges, the declaration's source (item | attribute_default | attr_row), the bad time,
   # or the authored form of a swapped inverse item. Authority violations still RAISE,
   # before anything of the item is written. One bad item is skipped; the rest of the
   # chunk still ingests (no silent cap).
p.resolve(entity, aspect, frame="canon", at=None)
   -> {status: resolved|unknown|denied|undeclared, facts, receipt, planted?, reason?}
p.retract(assertion_id, reason) -> Receipt
p.snapshot(scope_ids, frame=, as_of=, lens=, budget=, since=, correlated=False, features=False,
           asserted_as_of=None) -> dict
   # contractually ZERO model calls and ZERO writes; id-only scopes; includes quantities
   # asserted_as_of (READ-SURFACE-V1 §8) — on this and every read below that takes a
   #   valid-time bound (not salience, fidelity_audit or ask; in_transit too, since
   #   EVENTS-ONE-READER-V1 §3): a log position.
   #   Rows asserted after it are invisible and retractions asserted after it don't apply;
   #   it reaches every fold, walk, source chain, the existence check (an id first written
   #   after it errors like an unknown id) and the charter. Identity closures and
   #   salience ranking are still read at the head.
   # existence follows perspective (FRAME-SCOPED-IDENTITY-V1 §6): an id is KNOWN in `frame`
   #   iff some row about it lives in `frame` or in canon (canon is the existence authority;
   #   a frame may add entities canon lacks). An id only another frame carries (a plot:-only
   #   object) returns {"error", "bad"} exactly like an unknown id — recover per id.
   # lens="situation": re-entry view — standing truth ∪ live threads, closed history dropped
   # correlated=True (AWARENESS-READS-V1.1): fold each entity over its `aka` correlation
   #   union — the whole reveal scene (masked-figure ∪ revealed identity) in one snapshot;
   #   as-of-before a reveal returns the uncorrelated view (no leak). The scene-wide state_union.
   # features=True: inline each scope place's `part_of`-feature children (the burrow under the
   #   hillside) one level. Both opt-in, orthogonal to `lens`; default off = unchanged.
p.state(entity, attribute, frame=, as_of=, value=None, asserted_as_of=None, frame_scope="exact")
   -> {status: unknown|known|conflicted|unresolved, fact, quantity?, conflicting?,
       conflicting_facts?, values?, matches?}
   # READ-SURFACE-V1 §4: the whole key. status: nothing served -> unknown; the fold flags ->
   #   conflicted; the served row is an unresolved placeholder -> unresolved (`fact` is the
   #   placeholder, its value the thunk spec — never a value to show; treat any status you
   #   don't recognize as not known); else known. values: a set-valued key's current
   #   members, in member order (`fact` stays the latest). conflicting_facts: one Fact per
   #   `conflicting` id, in that order. value= (any JSON; a {"$decimal"} tag decodes):
   #   adds matches — does this frame's fold hold it? who_knows's test, for any frame
   #   (False on unknown; a set's members, an accrue key's total).
   # on an EVENT (EVENTS-ONE-READER-V1 §4): an event's rows never fold, so its own
   #   attributes are read from its record, the same before a sweep as after it —
   #   kind/origin/destination/manner answer exactly what events() reports (top evidence
   #   rank, then latest; conflicted when two disagree at one stamp); a set-valued key
   #   (alias, name, connects_to) lists its members in values, as for any entity, and any
   #   other description key with several rows lists them all; every key is unknown until
   #   the event has occurred (its first stamped row <= as_of). state_union reads the
   #   records of the aka union. where/aggregate/who_knows/confidence/frame_diff stay
   #   standing-only.
   # frame_scope (FRAME-CONTINUITY-V1 §2) — "exact" (default, byte-identical to before: the
   #   rows stored under `frame`) | "continued" (plus the frames the host declared continue
   #   into this one with continue_frame, transitively, as of the read) | "merged" (plus the
   #   frames of the observer's canon same_as closure; never aka). Wider scopes take a
   #   `knows:` frame only (ValueError otherwise) and fold the union as ONE row set; every
   #   served fact says which stored frame it came from (provenance.frame). Offered on
   #   state, state_union and facts ONLY — every other read refuses it.
p.canonical_attribute(name) -> str
   # READ-SURFACE-V1 §3: the gate's name for an attribute ("Located In" -> "in", "type" ->
   # "kind"; holds/wearing stay as they are). Every attribute argument already passes
   # through it.
p.where(attribute, op, value, frame="canon", as_of=None, asserted_as_of=None) -> [entity_id]
   # op in >=, >, <=, <, ==; compares folded numeric values
p.aggregate(container, member_attribute, op, frame="canon", as_of=None, recursive=False,
            asserted_as_of=None) -> dict
   # op in sum, count, min, max, avg; numeric rollup over contents()
p.locate(entity, as_of=None, frame="canon", asserted_as_of=None) -> [entity_id]
p.contents(container, as_of=None, frame="canon", asserted_as_of=None) -> [entity_id]
p.path(a, b, as_of=None, frame="canon", asserted_as_of=None) -> [entity_id] | None
   # READ-SURFACE-V1 §8: frame= (after as_of, so positional calls survive) reads the
   # rows stored under that frame's own name; default canon, as before.
p.composition(entity, frame="canon", as_of=None, asserted_as_of=None) -> [entity_id]
   # PLACE-FEATURE-ABSTRACTION-V1: the `part_of` chain up (the entity's place in the
   # structure) — compositional sibling of locate(). A separate axis from containment:
   # a burrow part_of a hillside does NOT put an actor in the burrow "in" the hillside.
p.features(place, frame="canon", as_of=None, asserted_as_of=None) -> [entity_id]
   # the place's `part_of`-children (its structural sub-features) — sibling of contents().
   # The sub-place is ONE entity answering both lenses (place: locate/contents/route/state;
   # feature: these). part_of is valid-timed; both reads HALT on a conflicted parent
   # (never silently pick) — the conflict surfaces via state(child,"part_of").
p.route(a, b, frame="canon", as_of=None, asserted_as_of=None) -> {route, status, segments}
   # passability-aware routing (RFC-003). status/segment: clear|blocked|obscured
   # (removed is temporal/diagnostic, in former_passages). A blocked segment
   # carries obstructing-fact `evidence`; an obscured one a computed
   # `unknown_basis`. Two-pass: a clear route if one exists, else a structural
   # route with flagged segments, else no_path. Obstruction = ordinary facts on a
   # PORTAL entity (a door's state, a guarded_by relation); traversability is
   # DERIVED, never stored. A portal kind gates passage only under a host-declared
   # `traversal:<kind>` policy (blocks_when_state / blocks_when_relation), scoped
   # to the kind; no policy => clear (no engine guess). The host supplies the words.
p.confidence(entity, attribute, frame=, as_of=, now=, asserted_as_of=None) -> {score, status, last_observed_at,
                       corroboration, conflicted, recency, recency_status, last_confirmed_at_wallclock}
   # derived trust over a functional key; never stored; functional-only (set/accrue -> score None)
   # frame is str | list[str]: a list = trust over the read-union (knows:O ∪ public);
   # cross-frame agreement raises corroboration, disagreement is conflict (score halved)
   # TRACKING-MODE-V1: recency is MODE-SCOPED. Fiction/deny -> recency 1.0,
   #   recency_status="permanent" (the page is true; story-time age never erodes trust).
   #   observe_or_unknown -> recency = 2**(-max(0, now - last_confirmed_at_wallclock)/half_life)
   #   under your declared DecayPolicy rows (attr:<key> . decay_halflife_seconds . n;
   #   exact-key > attr:in family > attr:__world__ default); now= is WALL time (defaults to
   #   the injected clock; as_of stays valid-time - never overloaded). Fail-closed:
   #   "unconfigured"/"unconfirmed" -> recency null, excluded + renormalized (never faked).
   #   Render "last confirmed <t> - N days unconfirmed" by joining state() + this payload.
p.correlate(a, b, evidence, at=None) -> Receipt
   # AKA-CORRELATION-V1: link two entities as facets of one identity (non-collapsing
   # `aka`) WITHOUT merging — reveals, dual personas, amalgamation. `at` = the reveal's
   # valid_from. Outcomes: correlated | noop_already_correlated | vetoed_distinct
   # (the hard distinct_from veto is absolute, and acts on whole correlation groups: a
   # distinct_from between a's group and b's vetoes too — FRAME-SCOPED-IDENTITY-V1 §3).
   # NOT a merge: resolve()/closure() and every DEFAULT read ignore aka; each entity
   # keeps its own rows. A correlated pair is never AUTO-merged (reconcile/promotion/
   # adjudicate_deferred: a soft block, decline code "correlated" — a timeless same_as
   # would leak the reveal backward), nor is a pair whose correlation groups a canon
   # distinct_from separates (decline code "distinct_group": correlate would refuse to
   # join them); your merge()/confirm() still can.
p.correlations(entity, as_of=None, frame="canon", asserted_as_of=None) -> [entity_id]
   # the facets correlated with entity as-of (first-seen ordered). Empty before a
   # reveal's valid_from — the mystery is intact. Zero writes.
p.state_union(entity, attribute, frame="canon", as_of=None, value=None, asserted_as_of=None,
              frame_scope="exact")
   -> {status, fact, quantity?, conflicting?, conflicting_facts?, values?, matches?}
   # the EXPLICIT correlated read: fold attribute over entity ∪ its aka facets, as-of.
   # Same shape as p.state. Returns the SAME view whether facts were on one entity or
   # split across correlated facets (retrieval-invariance). NOT a default read —
   # state/snapshot/ask never union; as-of-before a reveal returns the uncorrelated view.
   # Divergent facets use existing fold conflict semantics (no new blanket rule).
p.correlation_conflicts(as_of=None, frame="canon", asserted_as_of=None)
   -> [{a, b, aka_edge, aka_path, distinct_edges}]
   # raw aka authored over a distinct_from (a contradiction) surfaced for adjudication;
   # the guarded correlate() prevents it at the source. FRAME-SCOPED-IDENTITY-V1 §3: every
   # distinct_from in `frame` whose endpoints lie in one correlation group of `frame`
   # as-of (both edges the frame's own). Direct entries (one aka row joins the pair) come
   # first, aka_path = [aka_edge]; group entries follow with aka_edge None and the
   # shortest aka_path joining them.
p.reconcile() -> {merges, proposals}                      # global finalize; host-invoked
p.proposals() -> [{a, b, evidence, auto_decline_reason, auto_decline}]
   # open maybe_same_as with a structured auto_decline (gate-failure code + evidence);
   # code "durable_contradiction" names contradictory standing facts (SHAPE-FIX-V1 Win 4);
   # code "correlated" a proposal between aka facets, code "distinct_group" one whose
   # correlation groups a canon distinct_from separates (FRAME-SCOPED-IDENTITY-V1 §3)
p.confirm(a, b) / p.merge(a, b, evidence) / p.reject(a, b)
   -> {outcome, canonical_id, merge_event_id, reason, blocking_edges}   # an identity receipt
   # confirm = promote a proposal; merge = assert (guarded, hard vetoes absolute);
   # reject = distinct_from (sticky anti-merge). reject of two facets of one canon
   # correlation group returns conflict_already_correlated (reason already_correlated,
   # blocking_edges = the group's aka assertion ids) and writes nothing — retract the
   # aka first (FRAME-SCOPED-IDENTITY-V1 §3).
p.identity_conflicts() -> [{canonical_id, members, containment_edges, distinct_edges, same_as}]
   # FRAME-SCOPED-IDENTITY-V1 §4: merged canon closures that hold a pair the guarded merge
   # would veto (a containment-family or distinct_from row with both endpoints inside) —
   # what a raw or legacy same_as merged past the vetoes. same_as = every canon same_as
   # row inside: [{assertion_id, edge, merge_event_id (None for a raw row)}]. YOU pick
   # which same_as to retract; the engine chooses no cut. Canon only; zero writes.
p.adjudicate_deferred() -> {merged: [Receipt], residue: [proposal]}
   # SHAPE-FIX-V1: merge only the structurally-DECISIVE open proposals (anchor subsumption:
   # a pure fragment whose whole distinctive anchor set ⊆ the other's — tovin ⊆ tovin beck).
   # Blocked: relating edges, aka correlation, kind conflict, durable contradiction. The
   # semantic trap (two individuated things sharing a token) stays residue. reconcile()
   # unchanged; zero model calls; idempotent.
p.typing_conflicts() -> [{spurious, target, kinds, shared_anchor, asymmetry, artifact_edges}]
   # SHAPE-FIX-V1: read-only surfacing of typing slips (same-anchor cross-kind pairs with the
   # slip signature: an outgoing-bare spurious twin beside a structurally real entity —
   # person:harth beside place:harth). Proposals can't show these; adjudicate with retype().
p.retype(entity, to_kind, evidence, absorb=None) -> Receipt
   # SHAPE-FIX-V1: typing correction, DISTINCT from merge (the containment veto blocks a
   # merge, never a kind fix). absorb=None: correct one mistyped entity's kind (wrong kind
   # rows retracted, correct kind appended + classified). absorb=<target>: absorb a spurious
   # duplicate — slip signature verified, ONLY inter-closure artifact edges retracted (child
   # containment preserved), then guarded merge. Non-slip => vetoed_not_a_slip; distinct_from
   # absolute; with absorb=, a to_kind that is not the target's kind => vetoed_kind_mismatch
   # (reason to_kind_not_target_kind, nothing written — FRAME-SCOPED-IDENTITY-V1 §8).
   # Retracts CANON kind rows only: a knows: belief about the kind survives (§2).
   # Outcomes: retyped | merged | vetoed_not_a_slip | vetoed_kind_mismatch | vetoed | noop_*.
p.entities(frame, prefix=None, as_of=None, asserted_as_of=None) -> [entity_id]
   # BOUNDED-READS-V1: the roster read — entity ids carried by ONE frame's rows, resolved +
   # sorted. frame REQUIRED (a prefix-only enumeration leaks cross-frame existence; every
   # read fixes perspective). Your place roster is entities("canon", prefix="place:").
p.facts(frame, entity=None, attribute=None, prefix=None, as_of=None, include_meta=False,
        asserted_as_of=None, frame_scope="exact") -> [Fact]
   # BOUNDED-READS-V1: the frame-scan — ONE frame's visible rows as Fact dicts (provenance
   # included). RAW log reads for AUDITED scans (receipt trails, knowledge digests, marker
   # rows), NOT folds (folded truth = state/snapshot). frame REQUIRED. An exact a:<n>
   # receipt-chain target is always served; wide scans exclude a:*/attr:* unless include_meta.
   # frame_scope (FRAME-CONTINUITY-V1) defaults to "exact" — a scan never widens unless you
   #   say so. Under "continued"/"merged" the scan serves rows from several stored frames:
   #   KEY ANY WRITE OFF provenance.frame (see "Scanning then retracting" below).
p.continue_frame(source, into, evidence) -> Receipt
   # FRAME-CONTINUITY-V1 §3: declare that what `source` knew is part of what `into` knows —
   #   p.continue_frame("person:daniel", "person:dan", "the same man; host decision"). Both
   #   are observer ids, kept exactly as given (never resolved through identity). Writes one
   #   timeless canon row `source · frame_continues_as · into` (stated) plus its evidence;
   #   read with frame_scope="continued" on knows:<into>. One way (source gains nothing).
   #   Retract the row to end it (asserted_as_of reads see it as it stood). Already declared
   #   -> nothing written, a Receipt warning. Host-only: prose extraction cannot write it
   #   (skip host_only_predicate), nor a non-canon item (identity_edge_outside_canon). No
   #   merge/confirm/reconcile/aka/retype writes or reads it: identity never widens a frame.
p.begin_build(at=None) / p.seal_build(model=False, scope="session"|"all") / p.abort_build() -> dict
   # BUILD-SESSION-V1: a build session defers durability classification for everything
   # ingested inside it (the session wins over per-call classify=), then seal runs ONE pass
   # (scope="all" sweeps the whole log for pre-session deferred rows). abort/World.close()
   # restore the toggle and classify NOTHING. `with p.build(at=, model=, scope=):` is sugar
   # (seals on clean exit, aborts on exception). Retires the classify_inline / classify_all
   # / cursor.advance reach — use it for scenario/source builds.
p.fidelity_audit(frame="canon", as_of=None) -> {name_collisions, unstamped_timed, orphan_entities, open_conflicts, summary}
   # INGESTION-FIDELITY-V1: structural ingestion gaps as a queryable checklist, DERIVED
   # (zero writes; run AFTER seal). open_conflicts is COMPUTED on read for `frame` as of
   # `as_of` (FRAME-SCOPED-IDENTITY-V1 §5): no truth.scan() needed, never stale, and a
   # key is listed iff state(key, frame, as_of) is conflicted. name_collisions groups = {anchor, entities,
   # kinds (FOLDED, parallel to entities — weight cross-kind person<->place highest; the id
   # namespace can lie), pairs:[{a,b,status,reason?}], live}. status = WHY the pair isn't
   # merged (correlated | hard_blocked | typing_slip | auto_declined+reason | unlinked;
   # hard_blocked's reason is containment, distinct_from or distinct_group) — route
   # repair by it: reject() genuine homonyms (harth person<->place), adjudicate_deferred/retype
   # true same-kind splits. summary.name_collisions counts LIVE groups only (the tracked number).
   # unstamped_timed = classified STATE/EVENT rows with no valid_from (off the time spine).
   # Rows the sidecar judges CONSTITUTIVE/DISPOSITIONAL sit OUTSIDE this STATE/EVENT-only
   # bin; their valid-time correctness is a separate extraction contract (acquired standing
   # facts — occupation, scars, learned skills — still carry valid_from at the earliest
   # supported point; durability never licenses backward-forever projection).
   # Kinship-of-origin recipe (INGESTION-FIDELITY-V2): declare child->parent vocabulary
   # structural (attribute_default returning {"structural": True} for "father"/"mother")
   # -> deterministic CONSTITUTIVE, no model call; father_of (inverse) is a separate
   # opt-in attribute, never a canonicalization of father.
   # orphan_entities = unanchored obj:/person:. open_conflicts = the truth-maintenance flags.
   # The engine SURFACES gaps keyed by entity; the HOST joins arc/cast severity and drives
   # targeted re-extraction of the flagged spans (membrane: engine never repairs).
p.axis_heads() -> {asserted_head: int, valid_head: float|None}
   # AXIS-HEAD-V1: the log's two-axis high-water mark. valid_head = MAX(valid_from) over ALL
   # rows, ALL frames — the entry-epoch read (a pre-play coordinate must sit above every
   # seeded row wherever it landed). A coordinate scalar, never content.
p.salience(entity, frame=, as_of=) -> float
p.neighborhood(entity, depth=, frame=, as_of=, edge_kinds=, max_fanout=, budget=,
               asserted_as_of=None) -> dict
p.events(kind=, participants=str|list, since=, until=, frame=, asserted_as_of=None) -> [Event]
   # EVENTS-ONE-READER-V1 §2: each event is its RECORD (the event's rows minus identity /
   #   provenance machinery), read whole. No sweep needed: an event is listed whether or
   #   not its rows are classified (a build session, classify="defer", an identity merge's
   #   own identity_merge event). Only event entities are listed (a row on another subject
   #   that names an event never makes one), once per RESOLVED id (a merged event is one
   #   entry, under its canonical id, holding every stored id's rows). The window:
   #   until=T lists an event once it has occurred — its first stamped row <= T, or it has
   #   none (a timeless event, such as a merge) — with its record as of T; since=S keeps
   #   an event whose t (its latest stamp) >= S, its earlier and timeless rows included.
   #   kind/origin/destination/manner are the pick (top evidence rank, then latest).
   #   Ordered by t (None first), then by the event's earliest row.
p.frame_diff(a, b, scope, as_of=, asserted_as_of=None) -> [Fact]   # b is str|list[str]; divergent values marked
p.who_knows(entity, attribute, value=None, as_of=None, asserted_as_of=None) -> [frame_id]
   # WHO-KNOWS-INVERSE-V1: the knows:* frames that KNOW a fact — the computed inverse of
   # frame_diff (no stored known_by). A frame qualifies iff its fold serves a CONCRETE value
   # (a placeholder is not knowledge) and, value given, the FOLDED value matches it
   # (READ-SURFACE-V1 §5): identity-aware; any current member of a set-valued key; an
   # accrue key's total, numerically; a {"$decimal"} tag decodes first.
   # Superseded/retracted beliefs drop. Own-knows:-frame membership (the hidden-secret
   # case); the knows:O ∪ public union stays yours to apply. state(..., frame=F, value=v)
   # ["matches"] is the same test for one frame.
   # A frame's whole knowledge as folded truth: snapshot(entities(F, as_of=h), frame=F,
   # as_of=h). (snapshot(person, frame=F) covers that ONE entity and its contents, not
   # what the person knows about others; facts(F) is raw rows, superseded ones included.)
p.refer(description, scope=None, frame="canon", as_of=None, constraints=None,
        asserted_as_of=None, learn=True, model=True)
   -> {status: resolved|candidates|underdetermined, entity_id, candidates, receipt}
   # READ-SURFACE-V1 §9: world.refer on the porcelain, encoded. constraints are
   # [relation, anchor] pairs (contains | owned_by | held_by). model=False is tier 1 only:
   # where tier 2 would judge, status candidates with receipt {"tier": 2, "signals":
   # ["no_model"]}, no model call, nothing learned. learn (REFER-LEARNING-V1): only a
   # vocabulary miss in scope that tier 2 maps onto one entity writes a learned word; a
   # pick never does; asserted_as_of reads as of that log position and never writes.
p.ask(question, frame=, as_of=) -> Answer      # 1 parse call + refer's cascade; facts from folds only
   # REFER-LEARNING-V1 §8: ask writes NOTHING. Its refer calls pass learn=False: it
   # reads words direct refer calls learned, and never learns its asker's.
   # READ-SURFACE-V1 §6: one effective time t — your as_of, lowered (never raised) by a
   # valid plan as_of (a finite number; anything else is ignored) — governs the asker's
   # scope, the bindings, every fold, the location chain and events. Pass your play
   # horizon as as_of and nothing after it is told. In a non-canon frame the asker's own
   # words bind first (that frame's tier 1, model-free), then canon's.
   # READ-SURFACE-V1 §4: a placeholder key is never served as a fact — it is named in
   # Answer.unresolved ([[entity, attribute]]); a set-valued key serves one Fact per
   # member; a conflicted key serves its winner and is named in Answer.conflicted.
```

Every write returns a per-assertion Receipt; every fact carries
`{status, source_chain, assertion_id}` provenance and its row's `value_type`
(`entity`, `literal`, `unresolved` or `delta`; a derived accrue total is
`literal` — READ-SURFACE-V1 §4).

## THE MCP SERVER (non-Python hosts)

`pip install pbuffer[mcp]` →
`patternbuffer-mcp --world w.world --world-id w:id` (env:
`PATTERNBUFFER_WORLD`, `PATTERNBUFFER_WORLD_ID`) serves ONE world over stdio
(the 1:1 invariant; multi-world = multiple servers). `--policy` (env
`PATTERNBUFFER_POLICY`) names the world's physics: a fresh world records it;
absent, the world's stored physics apply; a mismatch fails startup
(`WorldPhysicsMismatch`, READ-SURFACE-V1 §7). The 43 deterministic
porcelain verbs are MCP tools; results arrive as
`structuredContent = {"result": <the porcelain return>}` (Receipts as dicts;
exact-decimals as `{"$decimal": …}` tags) with the same object serialized in
the text block.

MCP-specific narrowings (the genuinely model-free subset — the server's World
has no model callable): `ingest_structured.classify` accepts `"rules"|"defer"`
only (default `"rules"`); forced parameters are omitted from the schemas,
refused if a client sends one, and filled by the server (`FORCED_PARAMS`):
`seal_build` runs with `model=False` (always rules-only), and `refer` with
`model=False, learn=False` — tier 1 only, read-only and idempotent; an
ambiguous reference returns its `candidates` for the client to judge
(READ-SURFACE-V1 §11). Model-backed verbs (`extract`/`ingest`-prose/`ask`/
`resolve`, `refer` tier 2) are V1.1 via MCP sampling. Trust boundary: a
connected MCP client is a **fully trusted world principal** — it can name any
frame; tool annotations are hints, never authorization. Put untrusted consumers (players, NPCs) behind YOUR
host-mediated surface; frame entitlement is a host concern.

## SCANNING THEN RETRACTING (`provenance.frame`, FRAME-CONTINUITY-V1)

Every Fact, from every read, carries `provenance.frame`: the frame the row is
**stored** under. A host that scans and then retracts (a scrub, a re-ingest, a
dedupe) keys the retraction on it:

```python
FRAME = "knows:person:sela"
for f in p.facts(FRAME, frame_scope=scope):            # exact, continued or merged
    if f["provenance"]["frame"] == FRAME:              # the rule: only rows stored HERE
        p.retract(f["provenance"]["assertion_id"], "scrub")
```

`facts()` defaults to `exact`, so the unkeyed loop is safe by default; the rule
is what keeps it safe when a caller (or you, later) widens the scan.
Retractions are permanent log rows, and a scan that spans frames hands the
loop rows from frames it never meant to touch: the emberroad2 measurement was
72 retractions written into another character's frame that way. Without the
key, `merged` and `continued` return exactly those rows. A host that only needs to
*read* a widened view never needs the rule; one that *writes* from a scan always
does. Check `provenance.frame` against the frame you meant to change, not
against the one you asked for.

## ATOMIC ACTIVATION SETS (`commit_set` / `atomic=True`)

When a change spans several rows and a *prefix* would be incoherent — an
ancestry insertion (retract the old parent edge, then append the interposed
one), an arc adoption (retract the manifest's old main, append the new) — commit
it **all-or-none**:

- **`commit_set(ops)`** — the general door. `ops` is an ordered list of
  `{"op":"assert","item":{…}}` and `{"op":"retract","assertion_id","reason"}`.
  Applied as ONE unit of work: one commit on success, one rollback on any fault.
- **`ingest_structured(items, atomic=True)`** — the assert-only sugar.
- **Model-free only:** pass `classify="rules"` or `"defer"` (an omitted/`inline`/
  `batch` classify under `atomic=True` raises — those call the model inside the
  open transaction). `commit_set` defaults to `"rules"`.
- **Ordered, never re-sorted:** ops apply in author order; each sees the staged
  prefix for cycle/ancestry/recency checks. A `retract` may target only an
  assertion committed **before the call** — not one an earlier op in the same set
  minted (its `a:<seq>` id is not addressable). Recency is world-time
  progression: give the superseding row a later `valid_from` (equal-time,
  different-value is a flagged simultaneous contradiction, not an update).
- **Failure — `AtomicAbort{cause, skipped, error}`** (`from patternbuffer import
  AtomicAbort`), raised only after rollback is confirmed, nothing visible:
  `cause="gate_skip"` (any skip that would receipt-and-continue on the
  non-atomic path — a malformed id or item, a cycle, a mechanism attribute, a
  vetoed `same_as`… — `skipped` carries the records, `error=None`);
  `cause="exception"` (authority/semantics/unknown-retract-target — `error=
  {type,message}`, `skipped=[]`). Over MCP the abort is `isError:true` with
  `structuredContent={cause,skipped,error}`.
- **Non-idempotent:** a death/response-loss AFTER commit leaves a complete
  durable set; a blind re-run DUPLICATES. On an ambiguous outcome, probe a
  postcondition (is the new main loadable? does the head carry the set?) before
  retrying — atomicity is not exactly-once.

## MOVEMENT EVENTS (`kind=moved` / `in_transit()`)

A movement is a reified `kind=moved` event with `agent`/`origin`/`destination`/
`manner` rows (a novel endpoint is a `literal` string — never invented into an
entity). In prose ingestion the **engine** authors the timestamps: a `complete`
move is a zero-duration `[t,t)` event and the arrival becomes a **standing**
containment (`locate()` flips at `t`); an open move has no arrival and
`in_transit(agent, as_of)` reports it with the last-known containment (it reads
`events()`'s records and parse — one parse, so the two agree on a corrected move —
and takes `asserted_as_of`, EVENTS-ONE-READER-V1 §3). `events()`
additively carries `origin`/`destination`/`manner`/`valid_to`/`origin_bound`/
`destination_bound` for every event. The host doorway is preserved: a moved event
never synthesizes a containment row — an `in` row exists only if extraction
authored it in the same batch.
