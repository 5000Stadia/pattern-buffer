# PLAY-BIND-V1: one deterministic matcher for a turn's mentions (R55)

**Status:** r1.3, built and pbr-GREEN (bd4eb76, 4f58897; §2a says domain rows, matching the code). r1.3 (pbr's r1.2 RED, and its AMBER: §2a's canonical mapping excludes pass-through ids; an id outside `person`, `place` and `obj` is always kept unchanged and never identity-resolved; the exact-id step applies to those three namespaces only; the value predicate says `value_type == "entity"` explicitly). r1.2 (pbr's r1 RED: a value side is exactly what ingest would write as entity-valued, in any namespace; an exact id's existence is checked before any name match, so a future-only id is never bound by its slug; number folding becomes a pair rule with a minimum stem and a finite exception list; the collision universe and identity normalization are defined). r1.1 (construct's spec read, mc5d1c9: one decision per raw id per call, using every row's name evidence; a value is an entity side only when `value_type == "entity"`, typed by the host; future-only search is global; `include` is exact and `widen` means name rows; movement's entitled matcher is out of scope; the host's duties are listed, and admitted means bound, not permission). r1, for pbr review and construct's spec read. Author: pb, 2026-10-14. An additive porcelain read
(`bind`) and one read-only MCP verb. No write path, gate, fold or prompt changes.
**Source:**
- R55, placed first in M5 "Continuity in play". Kabe, via the monitor, settled g70803c on 2026-10-14: "R55 comes out of
  Later and goes next; it's the continuity core the framework stands on."
- construct's twin cases:
  - run 11: `straw`;
  - run 12: `obj:hold` minted beside `place:laundry_hold`;
  - run 13: `obj:chain` minted for the held `obj:tomas_reed_chains`, so its `broken` condition landed on the twin.
- pbr's code survey (2026-10-14): pattern-buffer's extract-to-ingest path binds nothing. It follows only `same_as`,
  and a grammar-valid model id is written as is. construct's host binder (`resolve_rows`, all three live channels)
  does the binding today: a unique whole-token match over a bounded candidate set, with no number folding, no learned
  aliases and no collision allocation.
- construct's shape read (`~/.config/colony/shared/r55-construct-binding.md`, ma4dae7). Build `bind()` as the
  matcher and allocator, with a result for each input row and a context argument. Every permission stays
  host-side: voice and deixis, mint allowlists, frame partition, containment canonicalization, protected keys,
  stub gates, place creation, and refusing future-only names. construct will swap its candidate matching for
  `bind()` and keep its gates around it.

**Why the engine, not the adapter.** The adapter can bind, and does today. The reasons for an engine read:
- The framework vision wants one cohesive engine, so every host should bind the same way.
- The facts a correct binder needs are the engine's own: authored and learned names, the
  same_as closure, which entity exists at a time, and every id ever written, which the collision check needs.
- `refer()` tier 1 and the build library's `name_key` matching already implement most of this, so the engine
  gives it one home.

## 1. The read

```python
porcelain.bind(rows, *, as_of, scope=(), include=(), widen=(), mint=(),
               frame="canon") -> BindResult
```

- **`rows`:** the extracted items, as `extract()` returns them. Each is a dict with `entity`, `attribute`, `value`
  and optional `value_type`, `name`, `names` and `aliases`. They are read, never mutated.
- **`as_of`:** the valid time the turn reads at (construct's horizon). Required.
- **The candidate set** is the union of three sources, with every member existing in `frame` at `as_of`:
  - `scope`: entity ids, each expanded through `contents()` recursively at `as_of`, as `refer()`'s scope does;
  - `include`: explicit ids the host adds, such as pre-held things or the pre-move chain. *(r1.1)* This is an exact
    roster: each id joins as itself and is not expanded through `contents()`;
  - `widen`: namespaces (`"person"`, `"place"`, `"obj"`) whose every named entity existing at `as_of` joins the set.
    This is construct's narrator widening. *(r1.1)* "Named" means at least one `name` or alias row visible in `frame`
    at `as_of`; a slug alone doesn't count.

  An id that doesn't exist in `frame` at `as_of` is left out, and the result lists it under `excluded`.
- **`mint`:** the namespaces this call may mint in (a tuple, default empty). The host passes its channel's
  allowlist. `bind` never chooses or changes a namespace: an entity's namespace is the extracted id's, and the host
  decides whether a place may be created.
- **`frame`:** the frame whose names, existence and containment are read.

`bind` makes no model call and writes nothing: the log length and the sidecar are unchanged. The same inputs on the
same log give the same result.

## 2. One raw id, step by step

A row has a **subject side** (`entity`), and a **value side** exactly when ingest would write the value as
entity-valued. *(r1.2, pbr)* That is ingest's own inference (`ingest.py`, the gate's `value_type` line). A value is a
side when its `value_type` is `"entity"`, or when `value_type` is absent or empty and the value is a string matching
`model.ID_RE`, in any namespace. *(r1.3)* Any other given type (`literal`, `unresolved`, `delta`) is not a side. `bind` imports that one predicate, so a row it admits can never be written with an
unchecked entity value. The host types values before calling (construct's detector, with explicit literal
suppression), so a literal `name · "obj:chain"` arrives as `value_type: "literal"` and is never a side.

*(r1.1)* **One decision per raw id per call.** `bind` first gathers every distinct raw id raised by any side of any
row. A raw id's surfaces are the union of every row's `name`, `names` and `aliases` where it is the subject, plus its
slug read as words. That evidence applies to its value sides too. Each raw id is resolved once, in the order below, and
the decision applies to every side that raised it.

1. **Malformed:** the id fails the entity-id grammar. Outcome `malformed`.
2. **Pass-through** *(r1.3: moved before identity)*: an id in any namespace other than `person`, `place` or `obj` (for
   example `event:`, `fact:` or `doc:`). Outcome `kept`, with the id unchanged, whether or not it exists. It is still
   classified as a side, by ingest's predicate, but it is never identity-resolved, rewritten, or checked for
   existence. Its identity policy is the host's.
3. **Exact id, first** *(r1.2, pbr; `person`, `place` and `obj` only)*. Take the raw id's canonical representative
   (§2a).
   - If it **exists at `as_of`** and is a candidate, the outcome is `bound`, signal `id`.
   - If it exists at `as_of` but isn't a candidate, `out_of_scope` with that id.
   - If it exists at the head but **not at `as_of`**, `future_only`, listing it. That ends the decision: no name or
     kind match can bind a future-only id to a current entity.
4. **Name:** compare the mention's surfaces with every compatible candidate's names.
   - **The raw id's surfaces:** gathered across the call as above (`tomas_reed_chains` gives "tomas reed chains").
     *(r1.1)* When the surfaces disagree, every surface is tried. If they match different candidates, the outcome is
     `ambiguous`, listing all of them; one candidate matched by several surfaces is a single match.
   - **A candidate's names:** its authored names and aliases, and its learned aliases, visible in `frame` at
     `as_of`, plus its slug read as words.
   - **Keys:** each is `build.text.name_key`, then **number-folded** token by token (§3).
   - **A match:** a surface key equals a candidate name key, or is a whole-token run inside one (`contains_run`, the
     build library's fragment rule). A key of articles alone matches only exactly.
   - **Compatibility:** a `person` side matches only `person` candidates. A `place` or `obj` side matches `place` or
     `obj` candidates; construct already binds across these two.
   - One matching candidate gives `bound`, signal `name`. Two or more give `ambiguous`, listing them.
5. **Kind:** no name matched. If exactly one compatible candidate's folded `kind` equals the side's folded slug, the
   outcome is `bound`, signal `kind` (refer's unique-kind-in-scope). Two or more give `ambiguous`.
6. **Future-only by name or kind:** steps 4–5 are run again over entities that exist at the head in `frame` but not
   at `as_of`. *(r1.1)*
   This search is **global**: every compatible entity in the frame, whatever `scope`, `include` and `widen` hold.
   Any hit gives `future_only`, with the ids in `Side.candidates`, so the host can tell a plain miss from a known
   later entity. `bind` never binds to one and never mints over one. Refusing a
   future-only name, minting, or proposing `same_as` is the host's call (construct refuses in movement, equipment
   and Growth).
7. **Mint:** the namespace is in `mint`. *(r1.1)* `mint` constrains only `person`, `place` and `obj`. The `fact`, `event`
   and `doc` namespaces are deliberately left alone: they are pass-through (step 2), and the host's own policy governs
   them. Outcome `minted`, with a new id: the namespace plus the slug, collision-checked
   against **every id in the log, any frame, any time**, and against this call's earlier mints. *(r1.2, pbr)* "Every id"
   means every row subject, every entity value (by ingest's predicate, above), and every `same_as` and `aka`
   endpoint. A forward reference that so far appears only as a value is taken too. A taken id gets `_2`,
   then `_3`, and so on. One call mints a given raw id once: every side that raised it gets the same new id.
8. **Otherwise:** `unknown`. The namespace isn't allowed to mint.

### 2a. Identity and existence *(r1.2, pbr)*

- **Canonical representative:** every `person`, `place` or `obj` raw id that reaches steps 3–8, and every `scope`
  member, `include` member and candidate, is first mapped through
  the `same_as` closure as the identity registry holds it at the head (`IdentityRegistry.resolve`), the same mapping
  ingest applies at its gate. Candidates are a set of canonical ids, and a bound side carries the canonical id.
- **Exists at `t`:** some member of the closure has a domain row (not one of the engine's `META_ATTRIBUTES`
  bookkeeping rows, such as refer's timeless `learned_alias`) in `frame`, asserted at or before the head, whose
  `valid_from` is at or before `t`, or which is timeless. A closure exists at `as_of` if any member does, and binds
  as its canonical id. Ending (`valid_to`) doesn't un-exist an entity: a broken pot still exists.
- **Exists at the head:** some member has any domain row in `frame`.
- **A candidate's names:** the `name` and alias rows of every closure member, visible in `frame` at `as_of`, plus
  learned aliases. Each member's slug is read as words.

## 3. Number matching *(r1.2: a pair rule, never a stem)*

Two tokens `a` and `b` match when they are equal, or when one is the other's plural by exactly one of these, with the
shorter at least 3 letters:
- `b == a + "s"` (chain/chains, key/keys, dog/dogs);
- `b == a + "es"`, where `a` ends in `ch`, `sh`, `s`, `x` or `z` (match/matches, box/boxes, bus/buses);
- `a` ends in a consonant plus `y`, and `b == a[:-1] + "ies"` (berry/berries);
- `a` ends in a consonant plus `o`, and `b == a + "es"` (hero/heroes, potato/potatoes).

A plural outside these rules (mouse/mice) simply doesn't match. A miss falls to the next step, never to a false bind.

Nothing is stemmed on its own, so "analysis", "status", "series" and "news" are never cut down. A finite exception list
blocks pairs whose plural has its own sense: news/new, means/mean, arms/arm, goods/good, glasses/glass,
papers/paper, works/work, customs/custom, quarters/quarter, manners/manner, spirits/spirit. The comparison is used only
for matching and is never stored.

## 4. The result

```python
BindResult(rows: tuple[RowResult, ...], mints: Mapping[str, str], excluded: tuple[str, ...])
RowResult(index, admitted, row, subject: Side, value: Side | None)
Side(raw, outcome, id, candidates, signal)
```

- There is one `RowResult` for each input row, in order, keyed by `index`.
- **`admitted`** is true when every side is `bound`, `minted` or `kept`. *(r1.1)* It means the row's identities are
  bound. It is not permission to ingest: every permission gate in §5 still runs on admitted rows. Then `row` is a copy of the input with both
  ids rewritten. Otherwise `row` is None and the row's sides still carry their outcomes and ids, since construct's cast
  movement reads them on dropped rows.
- **A row with one failed side is never half-written:** a whole-row rejection, as `resolve_rows` does.
- **`bind` adds no `same_as` field and changes no `kind` row.** A host that wants a proposal for a `future_only` side
  attaches one to a row it admits. A proposal can therefore never reach ingest when its own row was denied
  (construct's condition).
- `mints` maps each raw id to its new id. `Side.outcome` is one of `bound`, `minted`, `kept`, `ambiguous`,
  `out_of_scope`, `future_only`, `unknown` or `malformed`.

## 5. Not in this spec

*(r1.1)* **The host's duties, in order around `bind`.** These are construct's today, and `bind` assumes them:
1. **Before `bind`:**
   - the frame partition (strip or refuse per-item frames);
   - voice and deixis (narrator tokens dropped; "I" and "you" bound to the protagonist, or to the NPC under an NPC's
     POV);
   - containment canonicalization;
   - typing entity values (`value_type`).
2. **`bind`:** matching and allocation only.
3. **After `bind`, on admitted rows:**
   - suppressing a `kind` row on a bound entity;
   - refusing `person · in · obj`-shaped rows;
   - restated-origin;
   - protected-key licensing and the quarantine;
   - stub gates and channel denials;
   - refusing future-only names, or attaching a `same_as` proposal;
   - narrated-objects-land;
   - then ingest.

**Movement's entitled matcher is out of scope** *(r1.1, construct)*. construct can offer a destination while withholding
its protected name or kind. `bind` reads every visible name and alias of a candidate and has no per-candidate surface
restriction, so it replaces `resolve_rows`' matcher only, not movement's.

- **Voice and deixis** ("I", "you", the narrator's tokens), the frame partition, containment canonicalization,
  restated-origin, protected keys, the quarantine, stub gates, narrated-objects-land, and place creation (the move
  channel, Growth). These stay with construct, around `bind`.
- `refer()` tier 2 (the model pick). `bind` is deterministic, and an ambiguity is the host's.
- Any change to `extract()`, `ingest_structured()` or the gate.
- R57 (`ended_here`), which comes next in M5.

## 6. Surfaces

- `Porcelain.bind` and `World.bind`, plus the dataclasses, exported from `patternbuffer`. The porcelain contract grows
  additively.
- An MCP read verb `bind` (the server goes from 45 to 46 verbs) with the same arguments, returning the result as JSON.
- LEXICON gains `bind()` and **future-only** (an entity that exists at the head but not at the read's `as_of`),
  and ADOPTION.md gains `bind` beside `refer`.

## 7. Tests (no model calls)

1. **The three cases from construct's runs:**
   - run 13: a row for `obj:chain` with scope containing the player, who holds `obj:tomas_reed_chains`
     (named "Tomas Reed's chains"), binds to it. Signal `name`, by fragment plus number folding;
   - run 12: `obj:hold`, with `place:laundry_hold` (named "laundry hold") in scope, binds across obj and place;
   - run 11: `obj:straw`, with one in-scope entity named "straw pile", binds by fragment.
2. **Future-only:** an entity first asserted at valid time 10, read at `as_of=5`, is never bound. Its exact id, a
   name match and a kind match each give `future_only` listing it. With `mint=("obj",)` it still isn't minted over.
   *(r1.1)* It is found even when it is outside `scope`, `include` and `widen`.
3. **Collision:** a mint whose slug is taken by any id, in any frame, at any time, gets `_2`; with `_2` taken too, `_3`.
   Two rows raising the same raw id in one call get the same new id.
4. **Ambiguity:** two in-scope entities matching by name give `ambiguous` with both listed; the row isn't admitted.
5. **Compatibility:** a `person:` side never binds an `obj`, and an `obj` side never binds a `person`.
6. **Pass-through and malformed:** a `fact:` or `event:` id is `kept` unchanged; a malformed id is `malformed`.
7. **Whole rows:** a good subject with an `unknown` value gives `admitted=False`, `row=None`, and both sides reported.
7a. *(r1.1)* **One decision per raw id:**
    - `obj:chain` as a subject with `name: "chain"` in one row and as a value in another binds the same candidate in
      both;
    - a raw id minted in one row has the same new id in every row;
    - two rows naming the same raw id with surfaces matching different candidates give `ambiguous` in both.
7b. *(r1.1)* **Value typing is the host's:** an untyped `in · person:you` has no value side, and `name · "obj:chain"`
    with `value_type` absent or `literal` is never a side.
8. **Candidates:**
   - `scope` expands through `contents()` at `as_of` (a thing moved in later isn't a candidate);
   - `include` adds exactly its ids, with no expansion, and one that doesn't exist at `as_of` lands in `excluded`;
   - `widen=("place",)` adds every place with a name or alias row existing at `as_of`, and not a place with only a
     slug.
9. **Number matching:**
   - chains/chain, keys/key, berries/berry, boxes/box, matches/match, buses/bus, gases/gas and heroes/hero match;
   - news/new, glasses/glass and arms/arm don't (the exception list);
   - analysis/analysi, status/statu and series/sery never arise, since nothing is stemmed: "analysis" matches only
     "analysis";
   - gas/ga doesn't, since the shorter token is under 3 letters.
9a. *(r1.2)* **Value sides follow ingest:**
   - an untyped `in · event:later` is a side, `kept` unchanged, *(r1.3)* even when `event:later` exists only at the
     head. Identity for that namespace is the host's;
   - `value_type: "literal"`, `"unresolved"` or `"delta"` with an id-shaped value is not a side;
   - an untyped `in · person:you` is a side;
   - the predicate is the one ingest uses (a test pins both to the same function).
9b. *(r1.2)* **Exact id before name:** a head-only `obj:lantern_2`, read where an in-scope `obj:lantern` exists, gives
    `future_only`, never `bound` to `obj:lantern`.
9c. *(r1.2)* **Collision universe:** a slug that so far appears only as an entity value elsewhere gets `_2` when
    minted.
9d. *(r1.2)* **Closure:** with `obj:a same_as obj:b`, where only `obj:b` has a row before `as_of`, a mention of `obj:a`
    binds the canonical id and counts as existing.
10. **No write and deterministic:** the log length and sidecar count are unchanged after `bind`, and the same call twice
    gives equal results.
11. **MCP:** the server lists 46 verbs, and `bind` round-trips the result as JSON.
12. Full suite green.
