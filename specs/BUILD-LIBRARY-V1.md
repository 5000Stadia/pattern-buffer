# BUILD-LIBRARY-V1: `patternbuffer.build`, registry-first world building as a shared library

**Status:** r1, for pbr review. Construct gave a shape read on the interface (m29b672), and its
six points are folded in, marked *(c1–c6)*. Author: pb, 2026-10-13.

**Source:**
- **Kabe** (relayed in construct's design): "things that are literal name matching that don't
  have any nondeterministic discernment should be programmatic and not an LLM call … a Rex person
  and a Rex dog are initially and immediately identifiable in separation"; and "Pass for cast
  list, pass for locations, etc".
- **Kabe's answer on construct's gate g2fd391:** "Full agree on your 5 directions".
- **The design:** construct's `docs/design/SEEDING-REGISTRY-FIRST.md` r4, after two consult rounds
  (cb0483e, c33a2ae).
- **Speed plan:** `docs/SPEED-PLAN-2026-10-13.md` step 4 (Kabe's yes on g936be9).

**Builds on:**
- INGEST-V2 (`evals/harness/pipeline.py`, `registry.py`, `grammar.py`), whose registry, slice,
  grammar and escapes become this library's internals;
- FRAME-SCOPED-IDENTITY-V1 (identity is canon's);
- AKA-CORRELATION-V1 (`correlate`);
- PERSON-ROLES-V1 (R49);
- GRADE-LEAKS-V1 (the leak grade this design must pass);
- STAGE-MODELS-V1 and BUILD-PROFILE-V1 (labels and routing).

## Need

**Identity today is a side effect of fact extraction.**
- Each chunk's model call writes its own id strings, blind to the other chunks.
- The gate then joins entities by string equality only. So a man and a dog both written `person:rex`
  fuse at write time, while `person:holt_2` and `person:signe_holt` split.
- Construct's run 10 stopped on exactly this pair, and every build since R49 has shown it.

**The repairs come later:** reconcile, `adjudicate_deferred`, retype, the cast step's `_2`
remaps, and the merge gate.

**Two copies of the build.** pattern-buffer's book pipeline (INGEST-V2) is already registry-first.
But it lives in the eval harness, a model writes its ids, and its aliases aren't time-gated.
Construct's build doesn't use it.

**The fix:** decide identity **once, first, by code**, and share one implementation.

## The shape

A package `patternbuffer.build`, **outside the engine core**, as `service` and `mirror` are. The
core never imports it. It writes only through the porcelain (`ingest_structured`, `correlate`,
`reject`), so the ingestor does every write and the role-authority matrix holds. Six functions:

### 1. `Manifest`: the cast, places and things, with anchors by quote

```python
Manifest(entries: list[Entry], namesakes: list[tuple[str, str, str]] = ())
Entry(key: str, type: str, names: list[str], anchor_quote: str,
      personas: list[Persona] = (), role: str | None = None)
Persona(name: str, reveal_quote: str)
```

- **What each entry is.** An entry is one identity. Two entries can share a name and a type
  (namesakes), and stay two. `namesakes` lists `(key_a, key_b, anchor_quote)` for pairs the author
  says a reader could confuse.
- **`type`** comes from the closed set: `person`, `animal`, `creature`, `place`, `object`, `group`
  and `event`. Every being is filed under `person:` (see §2). A role word ("condemned man") is
  refused as a type.
- **Anchors are exact quotes** *(c1)*. An author model can't count sentences. So each entry,
  persona and namesake gives `anchor_quote`: an exact sentence or phrase from the prose. The
  library resolves it to `(chapter, sentence)`.
  - **Matching:** after whitespace collapse and quote folding, the quote must occur **exactly once**
    in the whole text. Zero occurrences or two or more are refused.
  - This is also the "check the manifest against the prose" step.
- **Sentences** are split deterministically. A chapter's text splits after `.`, `!`, `?` or `…`,
  optionally followed by closing quotes or brackets, then whitespace. A quote's sentence is the one
  holding its first character.
- **`validate(text_by_chapter)`** checks everything and raises **one** `ManifestError` listing
  *every* problem as structured items `{where, code, detail}` *(c5)*. So a host can re-ask its
  author once with the whole list. The codes:
  - `unknown_type`, `role_as_type`;
  - `duplicate_key`;
  - `quote_not_found`, `quote_not_unique`;
  - `persona_name_is_alias`: a persona name that also appears as a plain alias of any entry
    (consult c33a2ae);
  - `persona_reveal_before_entry`;
  - `namesake_unknown_key`.

### 2. `Registry.from_manifest(manifest, text_by_chapter)`: ids minted by code

- **The id** comes from the type's namespace and the entry's first name, slugged by rule:
  - `person:` for person, animal and creature *(c3: one namespace for beings, since construct
    branches on `person:`)*;
  - `place:`, `obj:`, `group:` and `event:` for the rest.

  A later entry with the same slug gets `_2`, `_3`, … in manifest order: `person:rex` and
  `person:rex_2`. Ids are never written by a model.
- **The type fact is the authority** (R51). The namespace is only a readable hint: a dog is
  `person:rex_2` with `kind = dog`.
- **`entries()`** *(c3)* returns `[{id, key, type, names, role, anchor: (chapter, sentence),
  personas: [{name, id, reveal: (chapter, sentence)}]}]` in manifest order. It's for a host's
  cast author.
- **Persona ids.** Each persona gets its own minted id, under its entry's namespace with the
  persona name slugged (`person:the_hooded_stranger`). It is a separate facet until its reveal
  (§5).
- **`resolve(surface, chapter, sentence)`** answers one of three things.
  - **The candidates** are the entries and personas whose anchor is at or before
    `(chapter, sentence)`: the **per-entry time gate**.
  - **Matching** is on any of a candidate's names, after normalization (lowercase, quote folding,
    leading titles from a fixed list). A **fragment** ("Breck") matches a candidate whose name
    holds it as a whole token.
  - **Before its reveal,** a persona's name resolves to the persona id. After the reveal it
    resolves to the persona id too: the facet keeps its facts, and the joining is the `aka`'s job.
  - **The answers:**
    - `Resolved(id)`: exactly one compatible candidate;
    - `Ambiguous(candidates)`: two or more;
    - `Unknown`: none.
  - **A type hint**, when the caller gives one (a being or a place), limits the candidates to
    compatible types. That is the Rex rule in code.

### 3. `plan(text_by_chapter, registry, *, max_words=1500)`: the chunks

- **The cuts.** Chapters are cut into chunks at paragraph breaks, under `max_words`, as today.
- **Reveal splits.** A chunk that holds a persona's reveal sentence is **split at that sentence**,
  so the text after the reveal starts a new chunk. No chunk straddles a reveal.
- **Per chunk:** `{index, chapter, first_sentence, text, candidates}`, where `candidates` are the
  registry entries and personas gated in by the chunk's first sentence.
- **Deterministic:** the same text and manifest give the same plan, byte for byte.

### 4. `extract(plan, registry, model, *, workers=4)`: facts, in parallel

- **One labelled call per chunk** (BUILD-PROFILE-V1: `stage="extract"`, `unit="chunk:NN"`), in a
  pool, with the label copied per submission. `PB_EVAL_STAGE_MODELS` routes it (STAGE-MODELS-V1),
  and the injected `model` is called as `(prompt, schema)`.
- **What the model sees:** the chunk text and its candidates (ids, types, names), never any later
  entry. It writes INGEST-V2's line grammar on candidate ids.
- **Every prompt has a stable, distinctive head** *(c4)*: `Extract world-state facts (build
  library, chunk)` for extraction and `Name the beings, places and things (build library,
  <category> pass)` for the category passes. Hosts that route by prefix, and timing logs, can tell
  the steps apart. The heads are module constants, and a test pins them.
- **Each chunk returns:**
  - `items` on resolved ids;
  - `Escape(type, name, chunk, quote)` for an entity not in the registry;
  - `Pick(surface, candidates, choice, evidence_quote, chunk)` when a surface was `Ambiguous` and
    the model chose.
- **The code checks** every id it receives:
  - an id not among the chunk's candidates or escapes is refused, as INGEST-V2's grammar already
    does;
  - a `Pick` whose choice isn't one of its candidates is refused.

### 5. `commit(world, registry, results, *, time_of=None, ingest_kwargs=None)`: one serial writer

**Time** *(c2)*. `time_of(chunk_index) -> float` gives each chunk's story time. When it's
omitted, chunk *i* is committed at `i + 1`. `ingest_kwargs` (for example `cursor_authoritative`
or `classify="defer"`) pass through to every `ingest_structured` call, unchanged.

**The writes, in this order:**
1. **The manifest.**
   - **For every minted id, its type fact first** *(c6)*: `kind = <type>`, timeless, canon. A
     being's kind is its type, never a role, so R49's gate sees a person from the first row.
   - Then its `name` and `alias` rows, and its `role` when given.
   - Then each persona id: its type fact first, then its name.
2. **Mentions.** A `Pick`'s facts go on a **provisional id** `mention:<slug>_<n>`, minted by code:
   - first, a type fact taken from the candidates' common type;
   - then the facts the chunk wrote for that surface.
3. **Chunk facts,** in chunk order, each chunk at `time_of(i)`.
4. **Escapes.** New entities are **joined by code** across chunks on (type, normalized name), so
   two chunks that meet the same new barmaid converge on one id.
   - Each is minted like a manifest entry, type fact first.
   - A name that collides with a manifest entry of a compatible type does **not** auto-join. It
     becomes a `Pick`-style proposal (step 5).
5. **Proposals, never merges.** For each `Pick`, and each colliding escape, an item with a
   `same_as` field proposes `mention:… → <choice>` as a canon `maybe_same_as`, with the evidence
   quote. The host, or `merge_gate`, decides later.
6. **Hidden personas.** `correlate(persona_id, entry_id, evidence=<reveal quote>,
   at=time_of(reveal_chunk))`. That is a dated `aka`, never a collapse (consult point P2).
7. **Namesakes.** `reject(key_a_id, key_b_id)` for each listed pair, so `distinct_from` keeps the
   auto-gate off them.

It returns a `BuildReceipt`:
- every write receipt's skips, gathered together;
- the minted ids;
- the mention, escape, proposal, correlation and rejection counts;
- `time_of` for each chunk.

### 6. `category_passes(text_by_chapter, model, *, categories=DEFAULT)`: a manifest for imported prose

For a book with no author (construct passes its author's manifest instead):
- **Concurrent passes** over the whole text, one per category: beings, places, things, groups.
  - Each is labelled (`stage="registry"`, `unit="pass:<category>"`) and routed by the stage map.
  - Each writes a short list of `(type, name, aliases, first quote)`.
- **Merging is code:**
  - entries merge on (type, normalized name) **only** when no pass marks them distinct;
  - **a pass never joins two names into one being.** Hidden identities are interpretation (a later
    pass) and are written as personas plus reveals, never as merged names.
- **Anchors** are each name's first quote.
- **The result** is a `Manifest`, which goes through `validate()` like an author's.

### 7. What moves, and what stays

- **The internals move into the package:** INGEST-V2's grammar, registry slice and escape handling.
- **The book runner** gains `run_book --pipeline library`. INGEST-V2 stays the default until the
  library matches it on the chapter test and passes this spec's tests. A later item retires the
  harness copy.
- **No engine change.** The library uses existing porcelain verbs only.

## Prior art (from construct's design and pb's survey)

- **Adopted:**
  - KGGen's two passes: relations against a fixed entity list;
  - GraphRAG's (type, name) key, as a blocking key only;
  - BookNLP's fragment and honorific rules as code;
  - Splink and Fellegi-Sunter's block-then-discern.
- **Rejected:**
  - GraphRAG's exact-name merge as identity, because it fuses namesakes;
  - a new `denotes` predicate (`same_as` proposals cover it);
  - neutral ids (Kabe rejected P4).

## Not in this spec

- **Construct's side:** its author schema returning the manifest, its rosters filtering `mention:`,
  and the planted-trap acceptance stories.
- **Choosing models or effort.** That's STAGE-MODELS-V1's map.
- **Interpretation passes** (motive, dynamics), beyond personas and reveals.
- **Retiring INGEST-V2's harness copy and the repair stages.** A later item, after the measurements.

## Tests (no model calls; fake models)

1. **Rex.** A man and a dog both named Rex in the manifest become `person:rex` (`kind = person`)
   and `person:rex_2` (`kind = dog`) from the first commit. A chunk mentioning "Rex the dog" with a
   being hint resolves to the dog, and no merge or proposal ever joins them.
2. **Namesakes:** two Johns stay two ids, and a `distinct_from` row exists between them.
3. **Quote anchors:** a quote found once resolves, and quotes found 0 or 2 times are refused. A
   `ManifestError` lists every problem at once: three planted problems give three items.
4. **Time gate:** the duke's entry anchored in chapter 3 is never a candidate for a chapter-2
   chunk. A persona's reveal mid-chunk splits the chunk at the reveal sentence.
5. **Personas:**
   - before the reveal, "the hooded stranger" resolves to the persona id;
   - commit writes one `aka` at `time_of(reveal chunk)`;
   - the persona's facts stay on the persona id;
   - default reads of the duke never show them.
6. **Picks:**
   - an `Ambiguous` "Mr. Holmes" picked as Sherlock puts its facts on `mention:…`, with its type
     first, and a canon `maybe_same_as` to Sherlock carrying the evidence quote;
   - nothing is merged;
   - a pick outside its candidates is refused.
7. **Escapes:** two chunks escaping "the barmaid" converge on one minted id. An escape colliding
   with a manifest entry becomes a proposal, not a join.
8. **Type first:** for every minted id (manifest, persona, mention, escape), the first row about it
   in the log is its `kind` row. A being whose chunk writes `kind = condemned man` ends up with a
   `role` (R49), never a kind conflict.
9. **No leaks by construction:** a fake build of a toy book with one reveal, graded by
   GRADE-LEAKS-V1, has zero chunk leaks and zero registry leaks.
10. **`time_of` and `ingest_kwargs`** pass through: rows carry the mapped times, and the kwargs reach
    every `ingest_structured` call.
11. **Prompt heads:** both constants are pinned, and every call made starts with its head.
12. **Category passes:**
    - they run concurrently (fake latencies overlap);
    - their merge never joins two names a pass listed separately;
    - their output validates as a `Manifest`.
13. **Determinism:** `plan` and the minted ids are byte-identical across runs.
14. **The book runner:** `--pipeline library` builds the toy book and grades it.
    - INGEST-V2 (the default) stays byte-identical.
    - The chapter-test battery on *The Last Honest Meter*'s seeded registry is unchanged under the
      default.
15. **Full suite green.**

## Lexicon (added with the build)

- **manifest:** a host's or author's list of a story's entries (one identity each), with type,
  names, an anchor quote, personas and reveals. The registry is built from it.
- **mention id:** a provisional, type-first `mention:` id holding the facts of an ambiguous
  surface, joined to an entry only through a proposed `same_as`.
- **persona:** a hidden facet of an entry, with its own id, correlated to the entry by a dated
  `aka` at its reveal.
