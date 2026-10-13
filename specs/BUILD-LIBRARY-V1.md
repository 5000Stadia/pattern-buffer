# BUILD-LIBRARY-V1: `patternbuffer.build`, registry-first world building as a shared library

**Status:** r1.4, answering pbr's r1.3 RED: candidates are sentence-scoped. Items cite their sentence, code enforces each candidate's gate sentence, and the gate is the effective first appearance. r1.3, answering pbr's r1.2 RED: a chunk's candidates are gated at its last sentence, and only reveals split chunks; one shape writer for every minted id; the error code list completed. r1.2, answering pbr's r1 RED: personas get an introduction anchor; a being's type is its own attribute beside `kind = person`, since R49 moves any other kind on a `person:` id to `role`; and the result schema has local handles, so ids are allocated before any fact is written. r1.1 added construct's read of r1 (m94f82c, its points marked *(k1–k7)*). r1 was for pbr review. Construct gave a shape read on the interface (m29b672), and its
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
Persona(name: str, intro_quote: str, reveal_quote: str)
```

- **What each entry is.** An entry is one identity. Two entries can share a name and a type
  (namesakes), and stay two. `namesakes` lists `(key_a, key_b, anchor_quote)` for pairs the author
  says a reader could confuse.
- **`type`** comes from the closed set: `person`, `animal`, `creature`, `place`, `object`, `group`
  and `event`. Every being is filed under `person:` (see §2). A role word ("condemned man") is
  refused as a type. An entry may also give `species`, a free word such as `dog` or `wraith`,
  allowed only for `animal` and `creature`.
- **Personas have two anchors** *(r1.2, pbr)*.
  - `intro_quote` is where the persona first appears. It gates the persona's candidacy.
  - `reveal_quote` is where the reader learns who it is. It splits the chunk and dates the
    `correlate`.
  - validate() refuses a reveal at or before the intro (`persona_reveal_before_intro`).
- **Anchors are exact quotes** *(c1)*. An author model can't count sentences. So each entry,
  persona and namesake gives `anchor_quote`: an exact sentence or phrase from the prose. The
  library resolves it to `(chapter, sentence)`.
  - **Matching:** after whitespace collapse and quote folding, the quote must occur **exactly once**
    in the whole text. Zero occurrences or two or more are refused.
  - This is also the "check the manifest against the prose" step.
  - *(k6)* **The expected quote is a whole sentence.** Phrases like "the gate" repeat, so hosts
    should prompt their author for full sentences. A shorter quote is accepted only when it is
    unique.
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
  - `persona_reveal_before_intro` *(r1.3)*;
  - `namesake_unknown_key`.

### 2. `Registry.from_manifest(manifest, text_by_chapter)`: ids minted by code

- **The id** comes from the type's namespace and the entry's first name, slugged by rule. *(r1.2,
  pbr)* **Entries, personas, mentions and escapes all draw from one allocator**, in a fixed order
  (manifest entries, then each entry's personas, in manifest order; mentions and escapes at commit,
  §5), so no two ever mint the same id:
  - `person:` for person, animal and creature *(c3: one namespace for beings, since construct
    branches on `person:`)*;
  - `place:`, `obj:`, `group:` and `event:` for the rest.

  A later entry with the same slug gets `_2`, `_3`, … in manifest order: `person:rex` and
  `person:rex_2`. Ids are never written by a model.
- **The durable shape of a type** *(r1.2, pbr)*. R49's gate moves any non-`person` kind on a
  `person:` id into `role`, with an inferred `kind = person`. So a being's type is **not** written
  as its `kind`:
  - **a being:** `kind = person` (R49's shape), `being_type` with exactly one of `person`, `animal`
    and `creature`, and `species` when the manifest gives one. A dog is `person:rex_2` with
    `kind = person`, `being_type = animal` and `species = dog`.
  - **anything else:** `kind = <type>` (`place`, `object`, `group`, `event`), as today.
  - `being_type` is the authority on what a being is, and the namespace is only a readable hint.
    R51 may later fold `being_type` into its own type layer. This shape is the one R49 permits now.
- **Type-hint compatibility:**
  - `being` matches any being type;
  - `person`, `animal` and `creature` match that `being_type` only;
  - `place`, `object`, `group` and `event` match that `kind`.

  The Rex rule: a hint of `animal` never resolves to a `being_type = person` entry.
- **`entries()`** *(c3)* returns `[{id, key, type, names, role, anchor: (chapter, sentence),
  personas: [{name, id, reveal: (chapter, sentence)}]}]` in manifest order. It's for a host's
  cast author.
- **Persona ids.** Each persona gets its own minted id, under its entry's namespace with the
  persona name slugged (`person:the_hooded_stranger`). It is a separate facet until its reveal
  (§5).
- **`resolve(surface, chapter, sentence)`** answers one of three things.
  - **The candidates** are the entries whose `anchor_quote`, and the personas whose `intro_quote`,
    is at or before `(chapter, sentence)`: the **per-entry time gate**.
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
- **Reveal splits.** A chunk that holds a persona's reveal sentence is **split before that
  sentence**: the reveal sentence opens the new chunk, and the earlier chunk ends just before it.
  No chunk holds both pre-reveal and reveal text.
- **Sentence-scoped candidates** *(r1.4, pbr; replaces r1.3's last-sentence gate)*.
  - **The effective gate.** Each entry's gate is its **effective anchor**: the earlier of the
    sentence holding `anchor_quote` and the first sentence whose text contains any of the entry's
    names, as a whole-token match (GRADE-LEAKS-V1's tokenizer). Each persona's gate is likewise the
    earlier of `intro_quote` and the persona name's first occurrence. So a gate is never later than
    the first time the text names the entity, however the author chose the quote, and it is
    computed by code.
  - **What a chunk receives:** every entry and persona whose effective gate is at or before the
    chunk's last sentence. Each candidate is annotated with its gate, as a sentence number in the
    chunk's own numbering.
  - **Numbered sentences.** The prompt shows the chunk with sentence numbers (`[s12]`). Every item
    the model writes **cites the sentence** it comes from. That is a new required field of INGEST-V2's
    line grammar.
  - **The code enforces the gate.** An item about candidate X (as subject or entity value) that cites
    a sentence before X's gate is **refused**: dropped, and recorded in the chunk result as
    `gate_refused`. An item citing a sentence outside the chunk is also refused.
  - So `resolve(surface, chapter, sentence)` and the chunk check apply **the same per-sentence
    gate**, and the two never disagree.
  - **Reveals still split:** the reveal sentence opens the next chunk. No chunk holds pre-reveal and
    reveal text, and a reveal is never a candidate, only `correlate`.
- **Per chunk:** `{index, chapter, first_sentence, last_sentence, text, candidates}`.
- **Deterministic:** the same text and manifest give the same plan, byte for byte.

### 4. `extract(plan, registry, model, *, workers=4)`: facts, in parallel

- **One labelled call per chunk** (BUILD-PROFILE-V1: `stage="extract"`, `unit="chunk:NN"`), in a
  pool.
  - *(k1)* **Every submission runs in its own `contextvars.copy_context().run(...)`,** taken at
    submission time inside the chunk's label. Every context variable the caller has set (the build
    label, and also a host's own, such as construct's timing log) follows into the worker.
  - *(k2)* `workers` is a free keyword argument, defaulting to 4. Construct passes 8. `PB_EVAL_STAGE_MODELS` routes it (STAGE-MODELS-V1),
  and the injected `model` is called as `(prompt, schema)`.
- **What the model sees:** the chunk text and its candidates (ids, types, names), never any later
  entry. It writes INGEST-V2's line grammar on candidate ids.
- **Every prompt has a stable, distinctive head** *(c4)*: `Extract world-state facts (build
  library, chunk)` for extraction and `Name the beings, places and things (build library,
  <category> pass)` for the category passes. Hosts that route by prefix, and timing logs, can tell
  the steps apart. The heads are module constants, and a test pins them.
- **Each chunk returns** *(r1.2, pbr: the result schema)*
  `ChunkResult(index, items, escapes, picks)`.
  - `items` are fact items whose `entity` (and `value`, for an entity value) is either a candidate
    id or a **local handle** `new:<k>` (k = 0, 1, … within the chunk).
  - `escapes` are `Escape(handle, type, name, species, quote)`, one per handle the chunk
    introduces for an entity not in the registry.
  - `picks` are `Pick(handle, surface, candidates, choice, evidence_quote)`, one per handle the
    chunk uses for an `Ambiguous` surface it chose.
  - Every handle an item uses is declared by exactly one escape or pick in the same chunk, and
    every declared handle is used. Otherwise the chunk is refused, as INGEST-V2 refuses orphans.
- **The code checks** every id it receives:
  - an id not among the chunk's candidates or escapes is refused, as INGEST-V2's grammar already
    does;
  - a `Pick` whose choice isn't one of its candidates is refused.

### 5. `commit(world, registry, results, *, time_of=None, ingest_kwargs=None)`: one serial writer

**Time** *(c2)*. `time_of(chunk_index) -> float` gives each chunk's story time. When it's
omitted, chunk *i* is committed at `i + 1`. `ingest_kwargs` (for example `cursor_authoritative`
or `classify="defer"`) pass through to every `ingest_structured` call, unchanged.

**The writes, in this order** *(r1.2, pbr: ids are allocated before any fact is written)*:
0. **The shape writer** *(r1.3, pbr)*. Every minted id, whether manifest entry, persona, escape or
   mention, gets its **shape rows first**, timeless and canon, from one function
   `shape_rows(id, type, species=None)`:
   - **a being** (`person`, `animal`, `creature`): `kind = person`, then `being_type = <type>`,
     then `species` when given;
   - **anything else:** `kind = <type>`.

   No other path writes `kind` on a minted id. So R49's reclassification never fires on a manifest,
   persona, escape or mention id, and the Rex result holds.
   - **The one exception** *(r1.4, pbr)*: a mention whose candidates are of mixed types and not all
     beings gets **no** shape rows (step 2a). Every other minted id gets its shape rows first.
1. **The manifest.**
   - For every entry: its shape rows *(c6)*, then its `name` and `alias` rows, then its `role`
     when given.
   - Then each persona id: its shape rows (its entry's type and species), then its name.
2. **Allocation, before any fact.** Each chunk's handles are visited in (chunk index, handle
   number) order, and each gets an id and its type fact:
   - **a pick handle** gets a **provisional id** `mention:<slug>_<n>`, minted by code (step 2a);
   - **an escape handle** joins an existing escape id or gets a new one, by the rules in step 4.

   Every item's handles are then **rewritten** to their ids. No fact is written under a handle,
   and no handle can attach to an id other than the one allocated here.
2a. **Mention shape.** A pick's provisional id gets its shape rows through the shape writer, with
    the type chosen like this:
   - first, a type fact *(k3)*:
     - when every candidate has one type, that type, with species only when all agree;
     - otherwise, when every candidate is a being, only `kind = person` and no `being_type`, so
       R49's role move still applies to an extracted role word;
     - otherwise, no shape rows, and the proposal carries the candidates;
   - then the facts the chunk wrote for that surface.
3. **Chunk facts,** with handles already rewritten, in chunk order, each chunk at `time_of(i)`.
4. **Escapes.** New entities are minted like manifest entries, shape rows first (step 0).
   - *(k4)* **A role word as the type** ("guard", "condemned man"), which is not in the closed set,
     is coerced at the library edge: `type = person` plus `role = <the word>`, R49's rule. It is
     never refused, because refusing would drop a real entity.
   - *(k5)* **Joining across chunks by code is limited, to avoid over-merging:**
     - **A proper name** (an escape whose name is not a definite or indefinite description) joins on
       (type, normalized name) across the whole build. Two chunks meeting "Mira Vell" converge.
     - **A description** ("the guard", "a ferryman": a name starting with an article, or made only
       of lowercase common words) joins only **within one chapter**. Across chapters, each
       chapter's description gets its own id, and a same-text description in a later chapter
       becomes a same_as **proposal**, never a join.
   - *(r1.2, pbr)* **A collision with the manifest.** An escape whose name resolves (§2) to one or
     more manifest entries or personas of a compatible type still gets **its own escape id**. Its
     facts go there, never onto a manifest id. Step 5 proposes it against **each** colliding
     candidate.
5. **Proposals, never merges** *(r1.2, pbr: sources and targets)*. Each is an item with a `same_as`
   field, written as a canon `maybe_same_as`:
   - **a pick:** source = its mention id, target = its `choice`, evidence = its `evidence_quote`;
   - **a colliding escape:** source = its escape id, with one proposal per colliding candidate,
     each with evidence = the escape's `quote`;
   - **a description across chapters (k5):** source = the later chapter's escape id, target = the
     earlier one, with evidence = the later `quote`.

   The host, or `merge_gate`, decides later. Nothing in this step merges anything.
6. **Hidden personas.** `correlate(persona_id, entry_id, evidence=<reveal quote>,
   at=time_of(reveal_chunk))`. That is a dated `aka`, never a collapse (consult point P2).
   - *(k7)* **This `correlate` is the only write that links a persona to its entry.** No alias,
     name or other row ties the persona's name to the entry id, and the entry's own names never
     include a persona name. Step 1 writes the persona's name on the persona id only. The validator
     already refuses a persona name that is also an alias (`persona_name_is_alias`).
   - So a narrator reading the entry before the reveal can't reach the persona, and vice versa. A
     host's hidden arc, authored after the commit, gets the link and the reveal anchor from
     `entries()`, never from the log's default reads.
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

1. **Rex** *(r1.2)*. A man and a dog both named Rex in the manifest become:
   - `person:rex`: `kind = person`, `being_type = person`;
   - `person:rex_2`: `kind = person`, `being_type = animal`, `species = dog`.

   No `role` row is produced for either, and R49's reclassification never fires on them. A chunk mentioning "Rex the dog" with a
   being hint resolves to the dog, and no merge or proposal ever joins them.
2. **Namesakes:** two Johns stay two ids, and a `distinct_from` row exists between them.
3. **Quote anchors:** a quote found once resolves, and quotes found 0 or 2 times are refused. A
   `ManifestError` lists every problem at once: three planted problems give three items.
4. **Time gate:**
   - the duke's entry anchored in chapter 3 is never a candidate for a chapter-2 chunk;
   - *(r1.4, pbr's case)* a chunk whose sentence 1 says "The hooded stranger took the key." and
     whose sentence 3 is the persona's chosen `intro_quote`: the effective gate is sentence 1 (the
     name's first occurrence), so the sentence-1 fact may bind to the persona;
   - *(r1.4)* an entry whose name first occurs at sentence 3 of a chunk: an item about it citing
     sentence 1 is `gate_refused`, and one citing sentence 3 is accepted. `resolve` gives the same
     answers at sentences 1 and 3;
   - *(r1.4)* an item citing a sentence outside its chunk, or citing no sentence, is refused;
   - a persona's reveal mid-chunk splits the chunk before the reveal sentence, so the reveal
     sentence opens the next chunk;
   - *(r1.3, r1.4)* a persona introduced mid-chunk is a candidate in that chunk, and its items
     are gated from its effective intro sentence.
5. **Personas:**
   - *(r1.2)* before its `intro_quote` the persona is not a candidate. Between intro and reveal,
     "the hooded stranger" resolves to the persona id;
   - *(r1.2)* a reveal at or before its intro is refused by validate();
   - commit writes one `aka` at `time_of(reveal chunk)`;
   - the persona's facts stay on the persona id;
   - default reads of the duke never show them.
6. **Picks:**
   - an `Ambiguous` "Mr. Holmes" picked as Sherlock puts its facts on `mention:…`, with its type
     first, and a canon `maybe_same_as` to Sherlock carrying the evidence quote;
   - nothing is merged;
   - a pick outside its candidates is refused.
7. **Escapes:**
   - two chunks in one chapter escaping "the barmaid" converge on one minted id;
   - *(k5)* "the guard" escaped in chapter 1 and again in chapter 3 stays two ids, with a same_as
     proposal between them;
   - "Mira Vell" escaped in chapters 1 and 3 converges;
   - an escape colliding with a manifest entry becomes a proposal, not a join;
   - *(k4)* an escape typed "condemned man" is minted `type = person` with `role = condemned man`.
6a. *(r1.2, pbr)* **Handles:**
    - a chunk that uses `new:0` without declaring it, or declares `new:1` without using it, is
      refused;
    - every committed row's entity and value are real ids, never `new:` handles;
    - an escape colliding with two manifest entries keeps its own id and gets two proposals, and
      its facts are never on a manifest id.
6b. *(r1.2, pbr)* **One allocator:** two personas whose names slug alike, or a persona slugging
    like an entry, mint distinct ids (`_2`).
7a. *(k3)* **A mixed-type pick:**
    - "Rex" picked among a man and a dog, with no type hint, puts `kind = person` on the mention,
      since both are beings;
    - "the Rex" picked among a person and a ship (an object) puts no type fact on the mention, and
      the proposal carries both candidates.
7b. *(k1)* **Context in workers:** a host context variable set before `extract()` is visible inside
    every worker call, checked by a fake model that reads it.
7c. *(k7)* **The persona link:** after commit, the only row linking a persona id and its entry id is
    the `aka`. No `name` or `alias` row on the entry carries the persona name, and the entry's
    default reads before the reveal time show none of the persona's facts.
8. **Shape first** *(r1.3)*:
   - for every minted id (manifest, persona, mention, escape), its first rows in the log are its
     shape rows;
   - beings carry `kind = person` and `being_type`, and no minted id ever gets a `role` row from
     R49's reclassification of a shape row;
   - a being whose chunk writes `kind = condemned man` ends up with a `role` (R49), never a kind
     conflict.
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
