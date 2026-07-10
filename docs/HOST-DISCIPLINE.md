# HOST-DISCIPLINE.md — the adopter's discipline: ingesting and retrieving with fidelity

**Audience:** any engine considering adopting pattern-buffer as its
world-state substrate (Construct, Kernos, your host). **Status: pre-1.0,
living.** This is the *discipline* brief — the mechanistic responsibilities
the **host** must hold so the buffer details and surfaces with utmost
proficiency. For the wiring contract and exact signatures see
[`ADOPTION.md`](ADOPTION.md); for narrative-extraction depth and measured
baselines see [`INGESTION-PLAYBOOK.md`](INGESTION-PLAYBOOK.md); for the
principles see [`WHITEPAPER.md`](WHITEPAPER.md). This document is the map
that ties them together.

## 0. The one principle the whole discipline derives from

**The engine never observes and never guesses.** It has no background
process, no will to look at the world, no inference it runs unbidden. It
documents *exactly* what you present through its one gate, and it surfaces
*exactly* what you ask for along the structure it maintains. Therefore:

> Fidelity in **both** directions is the host's responsibility, exercised
> through a disciplined contract. The engine's job is to make that
> discipline *enforceable and honest* — to refuse malformed truth, to never
> fabricate, and to keep every fact time-indexed, attributed, and
> queryable. Proficiency is a partnership: you categorize well going in,
> and you query along the grain coming out.

Everything below is the operationalization of that sentence.

---

# PART I — INGESTION: documenting so nothing relevant is lost

The mechanistic responsibility: **every fact you will ever want to retrieve
must arrive as a well-formed assertion through the gate, correctly
categorized along the axes below.** A fact that arrives mis-categorized is
not wrong data — it is *invisible* data: it lands on the wrong fold key, in
the wrong frame, at the wrong time, and no retrieval will find it. Ingestion
discipline *is* retrieval discipline, paid in advance.

## The categories every candidate fact must be classified along

For each thing you decide to record, the host (or its extractor) must pin
all seven. These are not optional metadata; they are what makes a fact
findable and correlatable.

1. **Identity — which entity, canonically.** A namespaced id
   (`person:`/`place:`/`obj:`/`event:`/`doc:` + snake_case). Attach *every*
   referring expression as an `alias`; when a thing is later named, keep its
   id and add the name; when you minted a duplicate, emit `same_as`.
   **Why it's load-bearing:** identity is the spine of retrieval — the
   engine's identity *closure* is what gathers all of a subject's facts
   under one query. Fragment the identity and you fragment the subject; a
   later query sees a third of the truth. Cheap to keep, expensive to
   repair.

2. **Attribute — the canonical key.** Use the engine's canonical names
   (`in` for *all* containment/location; `connects_to` for passages; `kind`
   for what a thing is) and stable domain vocabulary otherwise. Know whether
   a key is **functional** (one value at a time — `color`, `in`: later
   supersedes earlier) or **set-valued** (`alias`, `connects_to`: values
   accumulate, never conflict), and whether a numeric quantity is
   **accrue** (absolute baseline plus signed deltas). **Why:** the fold is key-local. Two names
   for the same attribute (`wall_color` vs `color`) split a fact across keys
   the corroborate/conflict machinery will never see meet. (The gate
   canonicalizes a built-in set for you — lean on it, but don't fragment
   what it doesn't know.)

3. **Value & value_type.** `entity` when the value is another id (so walks
   and correlations traverse it); `literal` for scalars/structured;
   `delta` for a signed numeric increment on an `accrue` attribute;
   `unresolved` for a deliberately-deferred aspect (a *thunk* — see §below).
   Express approximate quantities as **structured bounds** (`{"gte":
   40000}`) so a later precise reading *refines* rather than *contradicts*.
   For fungible quantities, use `fold_policy="accrue"` and numeric
   `literal`/`delta` rows; the engine sums int/float values and keeps the
   ledger append-only.

4. **Time — both axes, deliberately.** `valid_from`/`valid_to` is **world
   time** (when it was true in the world); the engine separately records
   `asserted_at` (when you told it). Stamp the world-time of the fact, not
   the moment of narration — a Ch.3 revelation about Ch.1 gets Ch.1's
   `valid_from`. Reserve **`timeless`** for identity and structure ONLY
   (kind, names, fixed adjacency); everything that holds-at-a-time gets a
   stamp. **Why:** as-of queries are first-class; mis-stamped time makes a
   fact unreachable at the moment it actually mattered.

5. **Frame — whose truth.** `canon` carries facts about the world *at their
   true historical time*, even when revealed late or learned by a character.
   `knows:<entity>` rows are **additional copies** marking that someone
   knows a thing — never replacements for canon. `plot:` holds host-owned
   arc structure. **Why (the costliest known ingestion failure):** putting
   late-revealed canon into a `knows:` frame leaves canon *honestly empty*
   at probe time — the fact exists, but not where ground-truth queries look.

6. **Provenance — how strongly, from whom.** `stated` (asserted fact) /
   `observed` / `inferred` (a deduction) / `assumed` (a working theory);
   `source_doc=<doc:id>` for document claims, a speaker id for reported
   speech; `correction` to supersede a prior wrong row. **Why:** provenance
   is the engine's immune system. Evidence rank decides folds (a stated fact
   overrides an assumed one without a false "conflict"); the source chain is
   what a downstream consumer reads to decide how much to trust an answer.

7. **Relations & causality — extract every one the text supports, none it
   doesn't.** Containment (`in`), the lateral graph (`connects_to`,
   `adjacent_to`), and causality (`caused_by` → an `event:` entity). Name
   each relational category you need or the extractor will under-emit them.
   The equally hard negative: **never an edge the text doesn't support —
   vertical proximity is not connectivity.** Relations *are* the
   correlation graph retrieval walks; an un-extracted edge is a correlation
   that can never surface.

### What you must NOT document (the discipline of restraint)

- **Atmosphere and texture are not assertions.** "The air smelled of rain"
  is not a fact about an entity.
- **Never invent the negative.** Absence of an assertion is not an assertion
  of absence. If the prose didn't say the wall was clean, do not record
  "no graffiti" — a later "was it clean?" must honestly return *unknown*,
  not *no*.
- **Never author what is derivable.** Location, emptiness, age, staleness,
  containment chains, salience — these are *computed* from the log on
  retrieval. Storing them as facts is the fragmentation the engine exists
  to prevent.

### Deferred truth: the thunk

When something is "not yet in view," do not invent it and do not omit the
entity. Record the aspect as `unresolved` with a policy
(`invent_under_canon` / `observe_or_unknown` / `deny`). It rides along
un-pinned (an object can *move* while its contents stay a sealed thunk)
until something forces it — at which point the resolution is memoized into
the log and is stable forever, across processes. This is how "my office
walls, color unknown" becomes "blue" the day it's painted, with everything
before that honestly unresolved.

### The unknown, and knowledge per observer (the doctrine — whitepaper A6)

The substrate discovers what *is*; it never stores or infers what is not. The
unknown has **three positive states**, and choosing the right one is a host
responsibility:
- **Unestablished** — no row. A query returns honest `unknown`. (Most things.)
- **Established-deferred** — an `unresolved` thunk: a real placeholder the
  resolver will later force (the box whose contents you'll define on open).
- **Established-unknowable** — a `deny` thunk **with a reason**: a *positive
  assertion that the thing is canonically unknown* (the mystery box that stays
  shut — everyone who looked inside died). Use `deny`, **not** an absent row
  (which reads as deferred and the resolver would invent an answer), and
  **not** a "mysterious" tag (a stored property → a membrane breach).

**Knowledge is per observer, sparse, and never a grid.** Each observer (player,
*each* NPC) is a `knows:<id>` frame holding only what *that* observer knows.
What an observer does **not** know is **structural absence** — never a stored
"X doesn't know Y" row. "What does X not know that's true?" is computed:
`frame_diff(canon, knows:X)` (dramatic irony); inter-character gaps are
`frame_diff(knows:A, knows:B)`. With N NPCs this is the same operation over more
pairs — **computed on demand, nothing materialized.** Record a character's
knowledge **only where load-bearing**; the 44th NPC who learned nothing has no
rows and reads as honest silence.

For effective knowledge that includes common/public facts, pass a b-frame
union: `frame_diff(canon, [knows:X, public], scope)`. A fact is covered if any
b-frame agrees; private false belief is reported only when no public/common
frame corrects it.

**The perception-write pattern (how a character learns during play).** When an
observer perceives or is told a fact, write **that one row** into their frame —
`knows:<id> · attribute · value`, the value **frozen at perception time** —
sparse, per-event, never a canon copy, never × N. Frozen is deliberate: if
canon later changes, their frame still holds the old value, and
`frame_diff(canon, knows:<id>)` surfaces it as **stale/false belief** — a
feature, not a bug. Do **not** store a marker that resolves to *current* canon
(it would silently auto-update what the character "knows"). Optionally log a
perception `event:` with `caused_by` as causal scaffolding; the frame row is the
durable fact.

**The membrane-test — the one guard against bloat and fabrication:** *could the
engine recompute this row from other present facts? If yes, it is derived —
never store it; only an irreducible observation may be a fact.* Staleness,
current-confidence, salience, "doesn't know," presumed-empty are all
recomputable → none stored. (Source-confidence *at assertion* is different — it
is irreducible provenance, legitimately the row's `confidence` field.)

### Standing patterns (numbers, completeness, trust)

- **Exact money / precision → integer minor-units.** Numbers are int *or*
  float already (`12.5`, `0.7` work). For *exact* money, model the minor unit
  as an integer (`$19.99 → 1999`): integer arithmetic is exact, the `accrue`
  ledger sums without float error, and no new type is needed.
- **Observed completeness → a positive fact, never read from absence.** "Is
  there a 4th key?" is honest `unknown` by default. If a character *counts*,
  assert it (`keyring · count · 3 (observed)` / a `complete_as_of` stamp); the
  "4th?" question is then relational (the asserted count vs the query), never an
  inference from missing rows. Closed-world *answers* without a closed-world
  *assumption*.
- **Trust / staleness → `confidence`, computed, never stored.** `confidence(e,
  attr)` returns a derived trust score (provenance × recency × corroboration)
  plus `last_observed_at` (valid-time) and — in tracking worlds —
  `last_confirmed_at_wallclock` + a mode-scoped `recency` (TRACKING-MODE-V1:
  wall-clock decay under your declared per-attribute half-lives; permanent in
  fiction — the page is true). Render staleness from the wallclock field. A
  three-campaign-years-stale fact keeps **full validity** and — in fiction —
  undiminished confidence; only wall-clock unconfirmed age (tracking worlds)
  decays trust. Never delete it, never store a decaying `confidence` row (the
  membrane).

## Feeding mechanics (summary; depth in INGESTION-PLAYBOOK.md)

- **Scaffold identity first.** Establish a registry (ids/names/aliases/kinds
  + timeline + place graph) before extracting facts, so identity is globally
  consistent by construction. In live play the registry grows turn by turn;
  in batch it's established once over the document — same interface
  (`establish`/`extend`), different calling pattern.
- **Chunk small, on discourse boundaries** (~3.5k chars); thread the
  registry, not a transcript.
- **One explicit time convention**, anchored in the text's own cues; the
  scene cursor is the fallback stamp.
- **Defer classification and batch it** — the durability sidecar is
  rebuildable by design.
- **Harden the model shim** like a flaky network client (timeouts, backoff,
  quota-exhaustion detection, resume-by-chunk).

## Lean on the gate — what the engine guards so your prompt doesn't have to

These fire with no prompt help; design pipelines to rely on them:
attribute **canonicalization** (with receipts in the log), **cursor
stamping** of any unstamped non-timeless row, **role-checked appends** (your
renderer/narrator *cannot* write; nothing you emit can become
`generated`/`default`), **truth maintenance** (a contradiction survives
ingestion *as* a flagged contradiction, both rows alive — never a silent
merge), **assumption quarantine** (a theory can't outrank a later
observation), **containment-cycle rejection** at the write gate, and the
**`WorldMismatch`** guard (foreign-world rows refused). Malformed rows are
rejected/quarantined, not silently swallowed — but they're also not stored,
so a quarantined row is a lost fact: get the categories right.

---

# PART II — RETRIEVAL: surfacing every relevant, correlated detail

The mechanistic responsibility: **relevant detail and its correlations
surface only if you query along the structure the engine maintains.** The
log is truth; reads are derived projections; the engine gives you a small
set of typed verbs that each follow one kind of structure. Proficiency is
choosing the right verb, scoping by the subject's *closure*, fixing the
perspective, and reading what comes back honestly.

## The retrieval discipline, in order

1. **Resolve the subject to its canonical identity FIRST.** A subject named
   in prose ("my brass measuring spoon", "the clerk") is not yet an id. Run
   it through `refer(description, scope=, frame=)` → a `Resolution`
   (`resolved` / `candidates` / `underdetermined`), or let `ask()` do it.
   `refer` strips articles/possessives and resolves through the **identity
   closure**, so aliases and `same_as` merges all collapse to one canonical
   id. **Skip this and you query a fragment** — facts logged under a sibling
   alias stay invisible. An `underdetermined` result is *your* ask to put to
   the user; the engine will not guess below its confidence floor.

2. **Choose the read that matches the question.** The verb map:

   | You want… | Use | Surfaces |
   |---|---|---|
   | one fact (a key's value) | `state(entity, attribute, …)` | the folded winner + conflict flag |
   | everything about a subject | `snapshot(ids, lens=…)` / `materialize` | a coherent bundle of folded facts |
   | entities satisfying a numeric bound | `where(attribute, op, value, …)` | ids whose folded numeric value matches |
   | a collection rollup | `aggregate(container, attribute, op, …)` | sum/count/min/max/avg over numeric folded values of `contents()` |
   | where something is | `locate(entity)` | containment chain, nearest container first |
   | what's inside / co-located | `contents(container)` | members (emptiness = `[]`, derived) |
   | is X reachable from Y | `path(a, b)` | a route, or `None` (no false connectivity) |
   | what structurally matters around X | `neighborhood(entity, depth=…, …)` | X's folded state plus bounded, salience-ranked correlates |
   | how likely X should survive a budget | `salience(entity, …)` | a derived ranking score, not truth |
   | what happened (to whom) | `events(participants=…, kind=, since=, until=)` | the event spine, filtered |
   | what A knows that B doesn't | `frame_diff(a, b, scope)` | divergent/absent facts; `b` may be a frame union |
   | a natural-language question | `ask(question, frame=, as_of=)` | one parse + refer + folds → `Answer` |
   | force a deferred aspect | `resolve(entity, aspect)` | the thunk's resolution per policy |

   Pick the **narrowest verb that answers the question** — `state` for one
   key, `snapshot` for the bundle. `ask` is the convenience front door (it
   composes refer + state + locate + events); the structured verbs give you
   control and zero model cost.

3. **Fix the perspective — frame and time — every read.** `frame` selects
   *whose* knowledge you're reading (`canon` for ground truth,
   `knows:<id>` for a character's beliefs — sparse by design, so absence
   there is meaningful). `as_of` selects *which world-time moment*; omit it
   for "now / head". You can also pin the knowledge axis (`asserted_as_of`)
   to ask "what did we know as of then". **Absence is honest:** a read that
   returns `unknown` means the world never recorded it in that frame at that
   time — that is an *answer*, not an error, and never means *false*.

4. **Follow correlations through the structure — the four axes.** To surface
   what's *related* to a subject, walk the edges the engine maintains rather
   than full-text scanning:
   - **Spatial:** `locate` (up the containment tree) and `contents` (down) —
     co-located objects, the room a person is in, what a container holds.
     `path` for connectivity across the lateral graph.
   - **Causal / temporal:** `events(participants=[X])` for X's history, and
     `caused_by` edges to trace *why* a state changed (the paint event
     behind the blue wall). Events are the scaffolding that orders change.
   - **Identity:** the closure already gathers facts logged under any of a
     subject's aliases/merged ids — which is why step 1 is non-negotiable.
   - **Knowledge:** `frame_diff(canon, knows:X, scope)` is the precise tool
     for "what is true that X doesn't know" (or the reverse) — perspective
     correlation, computed, not guessed.

5. **Read provenance and conflict on every fact — never launder.** Each
   `Fact` carries `{status, source_chain, assertion_id}`; a `state` read can
   come back `conflicted` with a *holding* `winner` and the `conflicting`
   ids. Surface the holding answer **and** the dispute to your consumer;
   don't silently pick a side the engine deliberately refused to. A
   `generated`/`default` value is render-coherence fill, **never a fact** —
   do not promote it.

6. **Use `neighborhood` for the common correlation sweep.** It packages the
   fixed structural axes — containment, lateral graph, entity-valued
   relations, and participant/causal event edges — into one bounded read.
   Set `edge_kinds` when you need only a subset, and use `budget` only to
   shape the returned neighbor list; it never invents, resolves, or paints
   the frontier. `salience()` is the same derived scorer used for ranking
   and materialization budgets.

7. **Scope by closure, not by log scan.** Query the subject *and its
   containment/identity closure*; let the engine's indexes do the
   retrieval. The read path is built so a fold costs the size of the
   subject's closure, not the size of the log — so never re-scan the whole
   world host-side to find correlates. Ask the structured verb; it already
   walks the index.

8. **Honor the typed outcomes.** `underdetermined` refer → your ask to the
   user. `UNKNOWN` from `resolve` in a tracking world → "I don't know" is a
   representable, correct answer. `Materialization.unresolved` names the
   frontier (thunks in scope), `defaults` are coherence fills, not facts,
   and `quantities` are derived totals, not stored ledger rows.
   Branch on these; don't coerce them into a guess.

9. **Never cache derived truth host-side.** Location, emptiness, current
   state, salience, staleness — re-query them. They are cheap, as-of-correct
   on every call, and the moment you cache one you've recreated the
   fragmentation the substrate exists to prevent.

## The correlation sweep — assembling everything relevant about a subject X

Use the engine's packaged bounded read for the usual case:

```
1. id = refer("…X…", scope, frame).entity_id
2. nb = neighborhood(id, depth=1, frame=, as_of=, budget=)
```

For specialized reads, compose the same primitives (`snapshot`, `locate`,
`contents`, `events`, `frame_diff`) directly. `neighborhood` is the default
replacement for a host-side correlation sweep because it is identity-closed,
frame/as-of scoped, fanout/depth bounded, and provenance-preserving.

---

## MUST / NEVER (retrieval companion to ADOPTION.md's ingestion list)

- **MUST** resolve a referring expression to a canonical id before querying;
  a fragment id returns a fragment of the truth.
- **MUST** pass `frame` and (when time matters) `as_of` on every read; a
  read with the wrong perspective is a confidently wrong answer.
- **MUST** treat `unknown` / `underdetermined` / `UNKNOWN` as first-class
  answers and route `underdetermined`/conflict to the consumer.
- **MUST** surface provenance and conflict; **NEVER** present a `conflicted`
  winner as settled or promote a `generated`/`default` to a fact.
- **NEVER** full-text-scan the log host-side for correlates — use
  `neighborhood()` or walk the structural edges
  (`locate`/`contents`/`path`/`events`/`caused_by`/closure).
- **NEVER** cache a derived value as truth; re-query.

The summary: **ingest along seven axes so nothing is invisible; retrieve
along the four structural correlations so nothing relevant stays buried —
and let the engine keep both honest.**

---

# Appendix — the discipline in practice (Construct, the first host)

This is not theory: [Construct](https://github.com/5000Stadia/construct)
(the first live host) already implements most of it, often under its own
names. If you're adopting, study its turn loop — it is the reference. The
mapping:

| Discipline (this brief) | Construct's named pattern |
|---|---|
| Ingest via the gate; renderer never writes | render-to-canon is a *separate* `ingest(prose, …)` step, gated by a `RENDER_LEASH` ("introduce no new entities/facts beyond the briefing") and a post-render **concealment audit** that flags unlicensed rows |
| `knows:<id>` are additive copies the host maintains | **`_mirror_rows()`** — after each `ingest`, touched canon facts are mirrored into the player frame; this *is* the host's discovery-gating |
| Deferred truth = a thunk you force | **`furnish_scene()`** — seed an `unresolved` scene description, `resolve()` it, mirror the result (the thunk lifecycle, concretely) |
| World-time stamping, avoid simultaneity ties | **`TURN_EPOCH`** — authoring rows at small coordinates, play rows at `1000+turn`, so authoring and play never tie on `valid_from` |
| Don't store derived/host state | pacing counters live in a **`session:main`** ledger frame *in the buffer*, reread each turn — not host memory |
| Frame perspective is structural | four frame namespaces treated as categories: `canon`, `knows:<id>`, `plot:<arc>`, `session:<host>` |
| The navigator/narrator two-lane (whitepaper A4) | implemented exactly: a deterministic **navigator** reads `plot:`; the **narrator** briefing is drawn solely from `knows:player` and provably carries zero `plot:` rows |
| Resolve identity before querying | **`refer(desc, frame="canon")`** at adjudication and movement, then `locate()` to verify |
| Scope reads by closure, not the log | **`arc_scope`** — the arc's entity closure, computed once at session zero, passed to every read |
| Bundle reads; don't N+1 the fold | **`SnapshotReads`** — a few `snapshot()` materializations per turn serve all condition atoms; per-key `state()` reads are counted as `point_reads` |
| `frame_diff` for perspective correlation | the **irony delta** — `frame_diff("canon", "knows:player", scope)` drives pacing |
| Honest absence / frontier | three-valued **`Truth.TRUE/FALSE/INDETERMINATE`** propagated through arc-condition expressions |

**Two workarounds the engine has since retired** (don't copy them into a new
host):
- Construct shipped a host-side **possessive/article-stripping retry** on
  `ask()` ("the host half"). The engine now normalizes determiners and
  derives a canon scope from a `knows:<id>` frame inside `ask`/`refer`
  (LIVE-FINDINGS Fix 3) — the host retry is now redundant.
- Construct caches the immutable arc structure in a sidecar (`arc_cache`)
  and leans on `SnapshotReads` because per-key folds once cost seconds at
  play scale. The read path is now closure-scoped and indexed (letter 037),
  so a fold costs the subject's closure, not the log — bulk-snapshot caching
  is still a fine optimization, but the multi-minute pressure that forced it
  is gone.

The lesson the reference implementation teaches: **almost every host
"workaround" was either (a) a discipline this brief now names as the
correct host responsibility, or (b) a temporary paper over an engine gap
that the engine then closed.** When you hit friction, ask which it is
before building around it — and tell the engine maintainers.
