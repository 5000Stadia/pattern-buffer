# PLAY-BIND-V1: one deterministic matcher for a turn's mentions (R55)

**Status:** r1, for pbr review and construct's spec read. Author: pb, 2026-10-14. An additive porcelain read
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
  - `include`: explicit ids the host adds, such as pre-held things or the pre-move chain;
  - `widen`: namespaces (`"person"`, `"place"`, `"obj"`) whose every named entity existing at `as_of` joins the set.
    This is construct's narrator widening.

  An id that doesn't exist in `frame` at `as_of` is left out, and the result lists it under `excluded`.
- **`mint`:** the namespaces this call may mint in (a tuple, default empty). The host passes its channel's
  allowlist. `bind` never chooses or changes a namespace: an entity's namespace is the extracted id's, and the host
  decides whether a place may be created.
- **`frame`:** the frame whose names, existence and containment are read.

`bind` makes no model call and writes nothing: the log length and the sidecar are unchanged. The same inputs on the
same log give the same result.

## 2. One side, step by step

A row has a **subject side** (`entity`), and a **value side** when the value names an entity: `value_type ==
"entity"`, or `value_type` absent and the value is a string of the entity-id grammar in a `person`, `place` or `obj`
namespace. Each side is resolved alone, in this order:

1. **Malformed:** the id fails the entity-id grammar. Outcome `malformed`.
2. **Pass-through:** a namespace other than `person`, `place` or `obj` (for example `fact`, `event` or `doc`). Outcome
   `kept`, with the id unchanged. The host's own policy covers these namespaces.
3. **Exact id:** the id's `same_as` closure is a candidate. Outcome `bound`, signal `id`. If the closure exists at
   `as_of` but isn't a candidate, the outcome is `out_of_scope` with that id, and the host decides.
4. **Name:** compare the mention's surfaces with every compatible candidate's names.
   - **The mention's surfaces:** for a subject, the row's `name`, `names` and `aliases`, plus the id's slug read as
     words (`tomas_reed_chains` gives "tomas reed chains"). For a value, the slug only.
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
6. **Future-only:** steps 3–5 are run again over entities that exist at the head in `frame` but not at `as_of`. Any hit
   gives `future_only`, listing those ids. `bind` never binds to one and never mints over one. Refusing a
   future-only name, minting, or proposing `same_as` is the host's call (construct refuses in movement, equipment
   and Growth).
7. **Mint:** the namespace is in `mint`. Outcome `minted`, with a new id: the namespace plus the slug, collision-checked
   against **every id in the log, any frame, any time**, and against this call's earlier mints. A taken id gets `_2`,
   then `_3`, and so on. One call mints a given raw id once: every side that raised it gets the same new id.
8. **Otherwise:** `unknown`. The namespace isn't allowed to mint.

## 3. Number folding

Applied to every token of both keys, so "chain" meets "chains" and "berry" meets "berries":
- `…ies` (more than 4 letters) becomes `…y`;
- `…ches`, `…shes`, `…sses` and `…xes` drop `es`;
- otherwise a final `s` is dropped, if the token is longer than 3 letters and doesn't end `ss`.

So "glass", "bus" and "gas" keep their `s`. The fold is used only for matching and is never stored.

## 4. The result

```python
BindResult(rows: tuple[RowResult, ...], mints: Mapping[str, str], excluded: tuple[str, ...])
RowResult(index, admitted, row, subject: Side, value: Side | None)
Side(raw, outcome, id, candidates, signal)
```

- There is one `RowResult` for each input row, in order, keyed by `index`.
- **`admitted`** is true when every side is `bound`, `minted` or `kept`. Then `row` is a copy of the input with both
  ids rewritten. Otherwise `row` is None and the row's sides still carry their outcomes and ids, since construct's cast
  movement reads them on dropped rows.
- **A row with one failed side is never half-written:** a whole-row rejection, as `resolve_rows` does.
- **`bind` adds no `same_as` field and changes no `kind` row.** A host that wants a proposal for a `future_only` side
  attaches one to a row it admits. A proposal can therefore never reach ingest when its own row was denied
  (construct's condition).
- `mints` maps each raw id to its new id. `Side.outcome` is one of `bound`, `minted`, `kept`, `ambiguous`,
  `out_of_scope`, `future_only`, `unknown` or `malformed`.

## 5. Not in this spec

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
3. **Collision:** a mint whose slug is taken by any id, in any frame, at any time, gets `_2`; with `_2` taken too, `_3`.
   Two rows raising the same raw id in one call get the same new id.
4. **Ambiguity:** two in-scope entities matching by name give `ambiguous` with both listed; the row isn't admitted.
5. **Compatibility:** a `person:` side never binds an `obj`, and an `obj` side never binds a `person`.
6. **Pass-through and malformed:** a `fact:` or `event:` id is `kept` unchanged; a malformed id is `malformed`.
7. **Whole rows:** a good subject with an `unknown` value gives `admitted=False`, `row=None`, and both sides reported.
8. **Candidates:**
   - `scope` expands through `contents()` at `as_of` (a thing moved in later isn't a candidate);
   - `include` adds ids, and one that doesn't exist at `as_of` lands in `excluded`;
   - `widen=("place",)` adds every named place existing at `as_of`.
9. **Number folding:** "chains"/"chain", "berries"/"berry", "boxes"/"box" and "matches"/"match" fold together;
   "glass", "bus" and "gas" keep their `s`.
10. **No write and deterministic:** the log length and sidecar count are unchanged after `bind`, and the same call twice
    gives equal results.
11. **MCP:** the server lists 46 verbs, and `bind` round-trips the result as JSON.
12. Full suite green.
