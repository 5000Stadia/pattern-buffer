# MOVED-EVENT-V1 — movement as a first-class extraction event — r6

**Status:** r6 DRAFT → pbr (re-review after r5 partial). r5 re-review
(`<2a953605…>`): **F1/F2/F4/F5 GREEN, F3 RED (sole)** — pbr caught a real
self-contradiction: stamping the co-emitted arrival `in` with `valid_to=cursor`
makes it `[t,t)`, invisible to `locate()` forever, so the destination could
never become the standing location. r6 applies the strict payload/containment
split below (§ Review response r5→r6). pbr is the founder-resolved PB reviewer
(Cx/cr out of scope per the 2026-07-11 routing policy). Shape collaboration:
founder-reviewed (2026-07-12), Construct host-side read folded + consumption
rule locked (c `<70fc2e97…>`, `<2e966e46…>`, `<5c0d98ee…>`), binding commitments
confirmed (`<5a972667…>`).

## Review response (r5 → r6)

| finding | r5 defect (pbr) | r6 resolution |
|---|---|---|
| **F3** RED | the coordinate pass gave the matched arrival `in` the event's *closing* coordinate — `valid_to=cursor` — making the destination containment `[t,t)`, invisible at `t` and every later valid-time read (buffer.py:258-262), so `locate()` could never flip to the destination (contradicting § D.7 and ordinary standing-in). | **strict split** (§ B.3, § D.5): the movement PAYLOAD rows (`kind`/`agent`/`origin`/`destination`/`manner`) get `valid_to=cursor` when `complete` (the zero-duration EVENT); the matched arrival `in` gets `valid_from=cursor` and **`valid_to` absent** — it is the new STANDING destination from `t` onward, not part of the event interval. New decisive oracle (5e): `locate(agent, t)` and `locate(agent, t+1)` both return the destination. Plus two cleanups: `complete` schema is `{type:"boolean"}` (not `boolean\|null`); the porcelain signature spelled with `at=` retained. |

Frozen GREEN (r5): **F1** (literal endpoint), **F2** (no global aliases),
**F4** (payload-row anchor, decision-only permutation oracle, five-key result,
stored `agent` value + identity-aware filter, no-head semantics), **F5**
(per-occurrence id). Scope GREEN: `origin/destination`; `in_transit()`.
**Kind:** one extraction rule (both prompt variants, coordinate-free) + a
`valid_to` schema declaration + a **moved-event coordinate pass** at the gate +
two gate invariants (`valid_to >= valid_from`; non-null `valid_to` requires a
numeric `valid_from`) + an additive `events()` read-payload + one thin derived
read (`in_transit()`) + eval bars. No fold change, no containment-behavior
change, no new mutation verb, no locate() change. Evidence-gated: every clause
traces to live prose in Construct's #80/D-series probe logs
(the Construct host repo's `logs/` and `worlds/` trees; external, not shipped here).

### Prior round (r4 → r5)

| finding | r4 pin (pbr) | r5 resolution |
|---|---|---|
| **F3** YELLOW | the design is right, but `complete` is undeclared (not in `_EXTRACT_SCHEMA`), its item-placement unstated (a model could omit it, emit conflicting booleans across rows, or author `attribute="complete"` as a durable row — breaking derive-don't-store), and the co-emitted arrival `in`↔event match is undefined (the `in` row carries no event id); `extracted` signature/MCP unpinned | **`complete: boolean` declared** in `_EXTRACT_SCHEMA`, owned by the **`kind=moved` item only**; extracted-mode **group validation** requires exactly one boolean marker per moved id, `attribute="complete"` is never authored, and a missing/non-boolean/duplicate/conflicting marker **fails closed** (skip the whole moved group + its matched arrival `in`, one typed receipt). The **arrival-match rule** is pinned deterministically. `ingest_structured` signatures pinned with `extracted: bool=False`; `World.ingest` sets it internally. |
| **F4** YELLOW | the result shape/`last_known_containment`/no-head/signature are closed, but the anchor overclaims order-independence: `asserted_at` is physical-append-allocated, so `min(asserted_at)` is stable for one stored event, NOT identical across separate ingests, and `attr:*` default rows can shift the minimum | anchor redefined as **`min(asserted_at)` over the event's persisted MOVEMENT PAYLOAD rows only** (exactly `kind`/`agent` + present `origin`/`destination`/`manner`, excluding `attr:*` meta-rows); oracle 11a now holds the containment **decision** invariant under payload-row permutation, not the absolute tuple across independent writes. `agent` in the result is the **stored** event agent value; the agent **filter** is identity-aware (matching `events()`). |

### Prior round (r3 → r4)

| finding | r3 defect (pbr, verified) | r4 resolution |
|---|---|---|
| **F3** RED | the prose rule was still unenforceable: `extract()` is cursor-blind + verbatim, the model path defaults `cursor_authoritative=False`, and `valid_to` always passes straight through — so a model-invented `valid_from`/`valid_to` pair survives, and the `extract()→ingest_structured()` recipe is indistinguishable from a genuine structured caller | **enforceable coordinate-source transition** (§ B.3, § D). The prompt now emits a **coordinate-free** movement + a `complete` boolean, never a timestamp. A **moved-event coordinate pass** at the gate, run in **extracted (prose) mode**, STRIPS any model-supplied movement timestamp and stamps `valid_from` = the scene cursor on every event row + the co-emitted arrival `in` row; `complete`→`valid_to`=cursor, else none. `World.ingest()` and the documented public recipe both carry the `extracted` signal; a structured caller (default) keeps its own numeric coordinates. New general invariant: a non-null `valid_to` with null/timeless `valid_from` is skipped. Anti-invention oracles added. |
| **F4** YELLOW | 3 of 4 gaps closed; remaining: the `(valid_from, asserted_at)` event-start tuple is not uniquely supplied (an event has several rows sharing `valid_from`, each a different `asserted_at`); `in_transit()` result byte-shape + `last_known_containment` semantics unpinned; World-vs-porcelain signature parity unstated | (§ E) the event-start anchor is pinned to **`(valid_from, min asserted_at over the event's rows)`** (order-independent; permutation-tested); `in_transit()` result byte-shape pinned (`{agent, origin, destination, manner, last_known_containment}`, `last_known_containment` = the resolved containment value or `None`); the signature is stated identical on World and porcelain. |

Frozen GREEN (r3): **F1** (novel endpoint = `literal`, resolver-inert),
**F2** (no global aliases; exact keys prompt-pinned; no normalizer added),
**F5** (fresh per-occurrence id in the instruction + two-move oracle). Scope
GREEN: `origin/destination` naming; `in_transit()` as an engine-derived read.

### Prior round (r2 → r3) — for lineage

| finding | r2 defect (pbr, verified) | r3 resolution |
|---|---|---|
| **F3** RED | "the cursor at the arrival clause supplies the coordinate" is not implementable — `SceneCursor` is ONE scalar per ingest call (ingest.py:191-198), `extract()` never sees it (604-644), cursor-authoritative overwrites every `valid_from` from the one scalar while `valid_to` passes raw+unvalidated (420-437,510-516); the extractor must not invent a numeric coordinate from "that evening"; and `[t,t)` is EMPTY under exclusive valid_to visibility (buffer.py:258-262), not a visible point | **prose authors zero-duration or open, never an invented interval** (§ D). Model-backed movement stamps `valid_from` = the single cursor; `valid_to` is absent (open) or equals `valid_from` (zero-duration completion). Only STRUCTURED callers with explicit numeric coordinates may author a nonzero interval. New gate invariant `valid_to >= valid_from`. Zero-duration `[t,t)` semantics named exactly. |
| **F4** YELLOW | four exact contract gaps: (1) `*_bound` can't rest on grammar/existence — the gate accepts an entity-valued *unregistered* place and a literal string that looks bound (pbr reproduced both); (2) "omitted or null" is two shapes; (3) the join is under-defined at equal valid-times / no head; (4) MCP read registry + LEXICON + whitepaper catalogue not named | (§ E, rewritten) `*_bound` ≡ stored `value_type == "entity"` (authoritative boolean; grammar backstop **dropped**); one fixed payload byte-shape (six keys always present, `None`-defaulted); the join pinned to pbr's `(valid_from, asserted_at)` tuple rule; every public surface (World, porcelain, MCP read registry, LEXICON, whitepaper catalogue) named. |

Frozen GREEN (r2): **F1** (novel endpoint = `literal`, resolver-inert),
**F2** (no global aliases; exact keys prompt-pinned; event-scoped normalization
stays future/separately-specified — r3 adds no normalizer), **F5** (fresh
per-occurrence id in the instruction + two-move oracle). Scope GREEN:
`origin/destination` naming; `in_transit()` as an engine-derived read.

### Prior round (r1 → r2) — for lineage

| finding | r1 defect | r2 resolution |
|---|---|---|
| **F1** RED | novel endpoint carried as `value_type=unresolved`; a raw string has no `{policy,constraints}`, so `resolve()` (thunks.py:145) falls back to `world_policy`=INVENT_UNDER_CANON and can mint a literal — a never-invent breach | novel endpoint is `value_type=**literal**` (raw place-name string). Literals are resolver-inert (only `unresolved` rows are forced), so zero invention. True host-binding of the name → entity is deferred V-next (§ Non-goals, tripwired). |
| **F2** RED | four global `_BUILTIN_ALIASES` entries collapse distinct predicates world-wide (occupation, transport-mode, provenance, standing route) | **no global aliases.** The rule prompt-pins the exact keys `agent/origin/destination/manner` on moved events; event-scoped normalization (`event:*` ∧ `kind=moved` only) is the sanctioned fallback, never a global map entry. `origin` on an event and a document's `origin` coexist under the fold key — no collision without a rewrite. |
| **F3** RED | interval/containment claims self-contradict; `valid_to` undeclared; no arrival cursor; "locate() shows neither" false while `in` row stands | **one contract** (§ D). Standing `in` untouched → locate() during transit = **last-known origin** (r1's "neither" retracted); in-transit is a **distinct derived read**; all reified rows share one `[valid_from, valid_to)`; **`valid_to` declared in `_EXTRACT_SCHEMA`**; arrival containment stamped at the **arrival** cursor; cross-ingest closure = V-next. |
| **F4** RED | claimed in-transit join has no public surface — `events()` (porcelain.py:680-695) drops `origin/destination/manner/valid_to` | **additive `events()` payload** (§ E) exposing `origin/destination/manner/valid_to` + endpoint discriminator, absent-safe; **`in_transit()`** centralizes the as-of-sensitive join engine-side (host-requested). Host-confirmed additive-only. |
| **F5** YELLOW | unique per-occurrence id lived only in rationale, not the instruction | the **instruction** (both variants) now requires a fresh unique `event:<occurrence>` id per occurrence, all rows sharing it; two-moves oracle added. |

GREEN in r1 and retained: single `moved` kind with optional ends (not a
`departed`/`arrived` pair); person-only firing as a measured V1 boundary; no
inferred group/vehicle (never-invent); manner-value drift has ~zero *fold-key*
pressure because EVENT rows are excluded from standing folds.

## The measured defect

Prose movement extracts only as containment (`person · in · <place>`), which
loses the verb — and the verb is where movement semantics live. Two failures,
both live-proven in Construct's #80 acceptance:

1. **False positives:** within-scene texture ("keeps to the threshold",
   "stays by the hearth") extracts the same way as genuine exits — one settle
   produced six unbindable position rows. The host narrowed fail-closed
   (only a destination provably outside the scene licenses an exit), which
   killed this class but bought:
2. **An accepted false negative:** an exit to a place the world has not seen
   cannot fire at all. Measured instance (probe80-1783745562): Edda's
   licensed exit — "takes up the two covered pails from beside the door, and
   goes out to the well house" — narrated, licensed by the host's gate, and
   lost, because extraction authored no row the gate could consume.

Containment alone cannot say *left*; only the verb can, extraction is the
only layer that sees the verb, and the current contract discards it.

## A. The rule (both prompt variants, full + lean)

**Insertion point, per-variant (editorial, pbr):** the lean block has a
literal "location changes" clause; the full block does NOT. Implementation
specifies the insertion site independently in each block (after the
location/containment guidance in each) rather than relying on a clause name
that exists in only one variant.

> - MOVEMENT: when the text narrates a person actually leaving or arriving
>   at a place (goes out, slips away, comes in, arrives, departs, walks/
>   rides/drives from A to B), ALSO emit an event with a FRESH UNIQUE id of
>   the form `event:<short-occurrence-slug>` — a new id for every distinct
>   movement, never reused — and give that event these attributes, all
>   sharing the one id: `kind=moved`; `agent=<person id>`; `origin=<place>`
>   and/or `destination=<place>` exactly as the text gives them — a bound
>   place is its entity id, a named-but-unregistered place is that name as a
>   plain string (value_type=literal), an unnamed end is simply absent;
>   `manner`=<the verb's own mode: walk/run/crawl/ride/drive/fly/swim> when
>   the verb says it, omitted otherwise. Use exactly the attribute names
>   `agent`, `origin`, `destination`, `manner` — not `actor`, `from`, `to`,
>   `source`, `target`, `mode`. Do NOT emit any timestamp: never author
>   `valid_from` or `valid_to` for a movement — the engine stamps the
>   timeline from the scene, and a number invented from prose ("that evening")
>   is forbidden. Instead put a single boolean field `complete` on the
>   `kind=moved` item itself (not a separate row, never an `attribute`):
>   `complete: true` when the SAME passage narrates the finished arrival,
>   `complete: false` when only the departure is narrated — exactly one
>   `complete` per moved event. A bound destination whose arrival is narrated
>   (`complete: true`) also gets its ordinary `in` row (no timestamp on it
>   either — the engine stamps it). Only actual displacement by a person is
>   movement: intent or
>   facing ("turned toward the door", "keeps to the threshold"), preparation
>   ("takes up the pails"), moving atmosphere (air, rain, light), and
>   repositioning within the same place are NOT moved events.

Design decisions carried in the rule, with their reasons:

1. **One kind (`moved`) with optional ends, not a `departed`/`arrived`
   family.** Which ends are present *is* the direction: origin-dominant =
   exit, destination-dominant = arrival, both = transfer. A kind pair forces
   an arbitrary choice on "drove from LA to Vegas" and hands the extraction
   model a classification burden it will fumble; a single kind keeps the
   vocabulary un-fragmentable. Construct confirmed the filter form
   (kind=moved ∧ `origin` bound in-scene) is *preferred* over a dedicated
   exit kind — their gate keys on person+ends, not kind vocabulary.
2. **Person-typed agent is a firing condition, not a host filter.** The
   probe corpus moves air, rain, and light constantly ("Cold air comes in
   for the moment the door is open"); non-person motion is atmosphere.
   No measured animal/object-movement case exists; broadening waits for one.
3. **`manner` is verb-derived only** — soft vocabulary, raw verb accepted,
   never inferred beyond the verb (never `manner=drive` from "went to
   Vegas"). Per-occurrence event entities do not fold, so free-ish values
   carry no fold-key fragmentation pressure (pbr r1: confirmed near-zero).
4. **The novel end is a `literal`, not an `unresolved` thunk (F1).** A
   named-but-unregistered destination is the place-name as a plain string
   with `value_type=literal`. This is the never-invent-safe carrier: the
   resolver forces only `unresolved` rows, so a literal is inert — it can
   never inherit `INVENT_UNDER_CANON` and mint a phantom place. It is honest
   evidence ("the text said *the well house*; the world has no such entity
   yet") that a host may later bind by registering the entity. A true
   binding thunk (`refer()`-based, with deterministic bind/receipt/
   projection) is V-next, not V1 (§ Non-goals).
5. **Exact attribute keys are pinned in the prompt, not aliased globally
   (F2).** The rule names `agent/origin/destination/manner` verbatim; there
   are **no** `_BUILTIN_ALIASES` additions. If measured drift appears, the
   fallback is event-scoped normalization applied only where entity id
   matches `event:*` and `kind=moved` — never a world-global rewrite that
   would corrupt an occupation's `actor`, a device's `mode`, a document's
   `origin`, or a caravan's standing `destination`. (`origin`/`destination`
   as literal event attribute names are safe precisely because nothing is
   rewritten: a document's `origin` and an event's `origin` are distinct
   `(entity, attribute)` folds.)
6. **A fresh unique `event:<occurrence>` id per occurrence (F5).** Every
   movement mints its own id; all of its rows (`kind/agent/origin/
   destination/manner`) share exactly that id. Two moves by one person are
   two events; ids are never reused, so histories never conflate.

## B. Schema + gate invariant (F3a, F3)

1. **Declare `valid_to`.** It is consumed at `ingest.py:516`
   (`item.get("valid_to")`) but **absent** from `_EXTRACT_SCHEMA` (line 56;
   only `valid_from` at line 71). Permissive additional-properties tolerance
   is not a contract. r3 declares `valid_to` in
   `_EXTRACT_SCHEMA.items.properties` as `{"type": ["number", "null"]}`,
   mirroring `valid_from`. **Also declare `complete`** as `{"type": "boolean"}`
   (F3) — the moved-event completion marker is a first-class item field, not an
   ad-hoc key, so the schema tolerates it by contract and it can never be
   mistaken for an attribute. It is conditionally optional (present only on a
   `kind=moved` item) but when present must be a genuine boolean — NOT
   `boolean|null`, since the gate treats a null marker as non-boolean and
   fails the moved group closed (§ B.4).
2. **Two general gate invariants (F3).** The buffer currently accepts an
   inverted interval and a dangling upper bound (pbr: no check between 510-516).
   The gate rejects, as a malformed row (receipt-and-continue on the normal
   path; abort under `atomic=True`): (a) a non-null `valid_to < valid_from`;
   (b) a non-null `valid_to` with a null/timeless *effective* `valid_from` — a
   closing coordinate requires a numeric opening one. Equality is allowed
   (`valid_to == valid_from` is the zero-duration case, § D). Both are general
   (not movement-specific) invariants the log lacked; no current caller emits
   either shape, so no existing path changes.
3. **The moved-event coordinate pass (F3) — the enforceable transition.**
   Because `extract()` is cursor-blind and the model is untrusted for timing,
   movement timestamps are authored by the ENGINE, never the model:
   - **`extracted` (prose) mode.** `ingest_structured` carries an `extracted`
     signal (default `False`). `World.ingest()` sets it `True`; the documented
     public `extract()→ingest_structured()` recipe MUST pass it `True` (so a
     host replicating the model path gets identical treatment — closing the
     "indistinguishable from a structured caller" gap pbr named). In this mode a
     batch-aware gate step identifies each `kind=moved` event id and, having
     stripped any model-supplied `valid_from`/`valid_to` from BOTH the event's
     rows and its matched arrival `in` (a coordinate the model invented from
     prose never enters), applies a **strict split (F3):**
     - **movement PAYLOAD rows** (`kind`/`agent`/`origin`/`destination`/
       `manner`): `valid_from` = cursor; `valid_to` = cursor when `complete`
       is true (the zero-duration EVENT), absent when open. These are the
       event, and `[t,t)` is exactly right for them (§ D.6: history-visible,
       as-of-invisible, never in-transit).
     - **the matched arrival `in` row** (the new standing location): `valid_from`
       = cursor; **`valid_to` MUST remain absent.** It is the destination
       containment from `t` onward — an ordinary open-ended standing row, NOT
       part of the event interval — so `locate()` flips to the destination at
       `t` and stays there. Giving it `valid_to=cursor` would make it `[t,t)`
       and invisible forever (the r5 bug). This holds whether the move is
       complete or open (an open move has no arrival `in` at all).
     The `complete` marker is gate-consumed authoring metadata — it decides the
     EVENT rows' `valid_to`, is **never** stored as a durable attribute row
     (derive-don't-store), and never touches the arrival row's timeline.
   - **Structured mode** (`extracted=False`, the default for a host authoring
     real rows). Movement coordinates supplied by the caller are numeric truth
     and are **preserved** — this is where a genuine journey interval lives —
     subject only to the § B.2 invariants. The gate does not stamp or strip.
   - This scopes `extracted` narrowly: in V1 its ONLY effect is the moved-event
     coordinate pass; every other row behaves exactly as today.
4. **Extracted-mode group validation, fail-closed (F3).** The marker owns the
   `kind=moved` item and exactly one boolean is required per moved id. Before
   stamping, the pass validates each moved group and, on any of — **marker
   missing, non-boolean, duplicated across the event's rows, or conflicting** —
   **fails closed:** it skips the ENTIRE moved group AND its matched arrival `in`
   row, emits one typed receipt (`moved_marker_invalid`), and stamps nothing.
   It never silently defaults to open, and never leaves an arrival containment
   row without its event. An `attribute="complete"` row is not the signal and is
   itself a malformed movement row (skipped) — the marker is item metadata only.
5. **The arrival-match rule (F3) — deterministic, synthesizes nothing.** The
   co-emitted arrival `in` row carries no event id, so the pass matches it to its
   event by exact tuple: for a `complete=true` moved event with an entity-valued
   `destination`, the arrival containment is the batch row with **same batch and
   frame, `entity` == the event's stored `agent`, canonical `attribute` == `in`,
   `value` == that `destination` entity**. Every exact match gets
   `valid_from`=cursor and `valid_to` absent (§ B.3 split); NO containment row is
   ever synthesized (no-second-doorway, § F). A literal (unbound) destination has
   no arrival `in` (nothing to match), by § A.4.
6. **Exact `ingest_structured` signatures (F3).** `extracted: bool = False` is
   added as the final keyword on both layers, AFTER each layer's existing
   parameters:
   - core `World.ingest_structured(items, frame=None, classify="inline",
     cursor_authoritative=False, extracted=False)`.
   - porcelain `ingest_structured(items, frame=None, classify="inline",
     cursor_authoritative=False, at=None, extracted=False)` — the existing `at`
     (AXIS-HEAD-V1, porcelain.py:290) is retained before `extracted`.
   `World.ingest()` calls `ingest_structured(..., extracted=True)` internally;
   the documented public `extract()→ingest_structured()` recipe passes
   `extracted=True`. The MCP `ingest_structured` schema **does** expose
   `extracted` (a host replicating the extract path needs it); it defaults
   `False` so existing structured callers are unaffected.

## C. Canonicalization — none added

r1's four global aliases are **removed** (F2). `_BUILTIN_ALIASES` gains no
entry from this spec. The whole global-alias approach is withdrawn in favor of
prompt pinning (§ A.5). Any future event-scoped normalization is namespace-
gated to `event:*`/`kind=moved` and specified separately if a measured drift
forces it.

## D. The interval / containment contract (one contract, F3)

The single coherent story, replacing r1's self-contradiction:

1. **The standing `in` row is untouched.** A moved event does not close,
   supersede, or alter any containment row (membrane-clean).
2. **Therefore `locate()` during transit returns LAST-KNOWN ORIGIN**, not
   "neither." r1's "locate() shows neither origin nor destination" claim is
   **retracted** — it is false while the `in` row stands. Last-known is the
   honest containment read for a person mid-journey.
3. **In-transit is a distinct DERIVED READ, not a locate() change** (§ E's
   `in_transit()`). It reads an *open* moved event (no `valid_to` at/≤ the
   read's as-of) whose agent's `locate()`-head predates the event, and
   reports "in transit between `origin` and `destination`." This read — never
   `locate()` — is the only thing that says "in transit."
4. **The EVENT's reified rows share one interval; the arrival containment does
   NOT (F3).** The `kind/agent/origin/destination/manner` rows carry the event's
   `valid_from` and, when closed, the same `valid_to` — one event interval, no
   participant/endpoint row on a divergent timeline. The co-emitted arrival `in`
   row is a **separate standing containment**, not an event row: it shares
   `valid_from` but its `valid_to` stays absent (§ B.3 split, § D.5).
5. **The coordinate source is enforced at the gate, not requested of the model
   (F3).** There is exactly ONE `SceneCursor.position` per ingest call
   (ingest.py:191-198); `extract()` is cursor-blind and returns model items
   verbatim, and the model path defaults `cursor_authoritative=False` with
   `valid_to` passing straight through — so a *request* that the model behave is
   not enforcement. The § B.3 coordinate pass makes it structural:
   - **Prose / model-backed (`extracted=True`):** the model emits a
     coordinate-free movement + `complete`; the gate strips any model timestamp
     from both the event rows and the arrival `in`, then applies the § B.3
     split — event rows get `valid_from`=cursor and `valid_to`=cursor(complete)/
     absent(open); the arrival `in` gets `valid_from`=cursor and `valid_to`
     **absent** (the standing destination). No nonzero interval, and no
     model-invented number, can ever enter from prose.
   - **Structured callers (`extracted=False`, default):** a host supplying
     explicit numeric coordinates authors a nonzero `[valid_from, valid_to)`
     directly; the gate preserves them, subject to the § B.2 invariants. This is
     where a real journey duration lives when a caller actually has the numbers.
6. **Zero-duration `[t, t)` semantics, named exactly (F3).** Under the
   engine's exclusive upper-bound valid-time visibility (buffer.py:258-262:
   `valid_to > valid_as_of`), a `[t, t)` interval is **empty** for any
   as-of/valid-time-filtered read at `t` — pbr confirmed zero event rows
   visible there. But `events()` reads history WITHOUT valid-time filtering,
   so a zero-duration movement IS visible through `events()` as a completed
   historical occurrence. And it is never `in_transit()` (open requires
   `valid_to` absent or `> t`; § D.7). This is the exact, intended behavior: a
   zero-duration move is a fact that happened, not a state you can be caught
   inside. Cross-*ingest* arrival closure (departure in one call, arrival in a
   later call, reconciled into one interval) remains **V-next** — closing an
   open event from a later call needs a reopen/close path V1 does not build.
7. **As-of tie-break, pinned in the contract:** an event is OPEN as-of `t` iff
   it has no `valid_to`, or `valid_to > t` (strict — `valid_to == t` reads
   CLOSED as-of `t`; the destination is inclusive from its stamp onward, the
   origin exclusive at it). During the open interval `locate()` returns
   last-known origin; `in_transit()` returns the event (§ E2 gives the full
   containment-comparison rule). Any consumer that recomposes the join must
   match this bit-for-bit — which is why the join ships as one engine read.

## E. The public read/join contract (additive, F4)

`events()` (porcelain.py:671-706) today projects each event to
`{id, kind, agents, patients, t, caused_by}` and drops `origin/destination/
manner` and the closing coordinate. c confirmed (adapter.py:124-133) the
adapter maps a fixed key set via `.get()` and ignores unknown keys, so the
following is inert to every existing read. r3 pins the four exact contract
gaps pbr flagged.

**E1 — additive `events()` payload, one fixed byte-shape (F4.2).** Every event
dict — moved or not — ALWAYS carries these six additional keys, so the shape is
a contract, not "omitted-or-null":

| key | value | default when N/A |
|---|---|---|
| `origin` | endpoint value (entity id or literal string) | `None` |
| `destination` | endpoint value (entity id or literal string) | `None` |
| `manner` | verb-derived string | `None` |
| `valid_to` | closing coordinate; `None` = open event | `None` |
| `origin_bound` | `bool` when `origin` present, else `None` | `None` |
| `destination_bound` | `bool` when `destination` present, else `None` | `None` |

`t` keeps its meaning (`= valid_from`), unchanged. All prior keys and defaults
are untouched.

**The discriminator is `value_type`, not grammar (F4.1).** `origin_bound` /
`destination_bound` are defined as *the stored `value_type == "entity"`* on the
endpoint row — `true` for an entity-valued endpoint, `false` for a `literal`.
The r2 "bound ⇒ resolvable `kind:slug` id / literal ⇒ never matches the
grammar" backstop is **dropped**: pbr reproduced both an entity-valued
*unregistered* place (accepted, no target rows) and a literal string that looks
bound, so the grammar claim is false against the gate (ingest.py:420-468 infers
`value_type` with no existence check). The boolean is authoritative and honest
about exactly what the engine stored; a host wanting existence still runs its
own `exists()` (Construct already does, growth.py) — the engine does not
promise registration, only the value-type it recorded.

**E2 — `in_transit()` thin derived read**, fully defined (F4.3). "In transit"
is temporal world-state, not host judgment, so it is one engine-derived read,
tested once (the host hit as-of drift re-deriving it — Cx 253 §4).

- **signature — identical on World and porcelain (F4.4).**
  `in_transit(agent: str | None = None, as_of: float | None = None,
  frame: str = CANON) -> list[dict]` on BOTH `World` and the porcelain (the
  porcelain result is `encode_out`-encoded, same keys); MCP derives its read
  schema from that one signature.
- **result byte-shape (F4), fixed keys:** each result is
  `{agent, origin, destination, manner, last_known_containment}`.
  `last_known_containment` is the **resolved containment value** (the place
  entity id) or `None` — the same value-space as `locate()`, never an assertion
  payload. `origin`/`destination`/`manner` mirror the § E1 endpoint values
  (`None` when absent). `agent` is the **stored** event agent value (matching
  `events()`, which emits stored participant values); the `agent` filter
  argument, however, is **identity-aware** — it resolves before comparing, so a
  caller may pass any alias of the agent.
- **openness.** `as_of=None`: open iff `valid_to is None` (a zero-duration or
  closed event is not in-transit), evaluated against the current containment
  head. Numeric `t`: open iff `valid_from <= t` AND (`valid_to is None` OR
  `t < valid_to`).
- **the event-start anchor, defined without overclaiming (F4).** A moved event
  has several rows sharing `valid_from`, each with a different `asserted_at`
  (allocated by physical append order), so a bare "(valid_from, asserted_at)" is
  ambiguous. The anchor is **`(valid_from, min(asserted_at) over the event's
  persisted MOVEMENT PAYLOAD rows)`**, where that row set is EXACTLY `kind` +
  `agent` + the present `origin`/`destination`/`manner` rows — **excluding**
  `attr:*` default-declaration meta-rows (which can be inserted before whichever
  event attribute is seen first, and would otherwise shift the minimum). The
  claim is deliberately narrow: the anchor is stable for one *stored* event and
  the containment include/exclude DECISION is invariant under payload-row
  permutation (oracle 11a) — NOT that the absolute tuple is identical across
  separate, independently-ingested writes.
- **containment comparison (pbr's tuple rule, against that anchor).** An
  otherwise-open event is EXCLUDED (the agent has arrived/relocated, not in
  transit) only when a containment winner exists for the agent whose
  `(valid_from, asserted_at)` is **at or after** the event-start anchor. If the
  only containment head predates the anchor, the agent is in transit with
  `last_known_containment` = that head's value; if there is no head at all, in
  transit with `last_known_containment = None`. This distinguishes a same-cursor
  origin `in` asserted *before* the event (in transit, last-known = origin) from
  an arrival `in` asserted *after* it (arrived, excluded).
- **derived read only** — writes nothing durable (projector/renderer
  discipline intact), adds no mutation verb, changes neither the fold nor
  `locate()`. A sibling of `events()`/`locate()`.

**E3 — every public surface named (F4.4).** The additive `events()` fields and
`in_transit()` are exported on **`World`**, the **porcelain**, and the
**explicit MCP read registry** (`mcp.py` — the registry does not reflect
additions automatically; the `events()` read schema gains the six fields and
`in_transit()` is registered as a new read tool). `in_transit()` and the
enriched `events()` payload are added to **LEXICON** and the **whitepaper
shipped-surface catalogue** as exported reads.

## F. The no-second-doorway invariant (binding host commitment)

kind=moved events and any co-emitted `in` rows travel in the SAME extraction
items batch through the SAME ingest gate. The engine gains **no** separate
commit path for narration-derived containment, and a moved event **never
synthesizes** a containment row post-gate — an `in` row exists only if
extraction authored it as an item in the batch. This is what lets a host
lane (Construct's `_partition_cast_moves`; rules 1/2/5, receipt
confirmation, protagonist exclusion) remain the licensed doorway for cast
containment: the event is evidence the gate consumes, never a bypass.
Confirmed binding with Construct (`<5a972667…>`).

## Oracles

1. **Prompt pins** (both variants, line-local, word-bounded): the movement
   rule, the person-typed condition, the exact-key pin (`agent/origin/
   destination/manner`, not the synonyms), the displacement-only exclusion.
2. **The Edda exit** (probe80-1783745562 prose, verbatim fixture): the
   passage yields exactly ONE moved event — fresh `event:*` id,
   agent=person:edda, origin=<the kitchen>, destination=<the well house>
   (bound if registered → `destination_bound=true`, else a `literal` raw
   string → `destination_bound=false`), with the co-emitted `in` row only
   when the destination is bound AND arrival is narrated. The preparatory
   sentence (pails, shawl) and the cold-air sentence yield NO moved event.
   This is the measured false negative, closed.
3. **The D1 arrival** ("The latch lifts. Rain-grey morning comes in with a
   man from the mill"): destination-dominant — moved with
   destination=<the taproom>, origin=<the mill> (bound or `literal` as the
   registry has it), plus the ordinary `in` row stamped at arrival.
4. **The novel-destination exit** (the false-negative class in isolation):
   an exit to a never-registered place → moved with `destination` a `literal`
   raw string, `destination_bound=false` (the `value_type=="entity"` test,
   not grammar). NO `in` row invented for it. The resolver, run against the
   world afterward, mints **zero** entities for that name (the F1 never-invent
   oracle); the endpoint survives an ingest reopen and reads back verbatim
   through `events()`; exactly one endpoint is exposed. Companion negative
   (F4.1): an entity-valued but UNREGISTERED endpoint reads `*_bound=true`
   (honest to the stored `value_type`), and a literal whose text looks like an
   id still reads `*_bound=false` — the boolean tracks `value_type`, never the
   string's shape.
5. **The journey — two modes, prose never invents a coordinate (F3):**
   (a) PROSE (`extracted=True`): "K drove from Los Angeles to Las Vegas,
   arriving that evening" → the model emits a coordinate-free moved event with
   `complete=true`; the gate stamps the EVENT rows `valid_from`=cursor,
   `valid_to`=cursor (zero-duration), and the arrival `in`=Vegas
   `valid_from`=cursor with `valid_to` ABSENT (standing). The event is visible
   via `events()` (history), returns no event rows at any as-of read at `t`, and
   is never `in_transit()`; the Vegas containment is a live standing row.
   (b) STRUCTURED (`extracted=False`): the same journey authored by a caller with
   explicit numeric departure and arrival coordinates → a nonzero `[valid_from,
   valid_to)` on the event; `in_transit()` returns K between the coordinates,
   `locate()` shows origin before and Vegas at/after `valid_to`.
5b. **Anti-invention (F3), the load-bearing oracle:** in `extracted=True` mode,
   feed a model stub that RETURNS a bogus numeric `valid_from` and `valid_to` on
   the moved event AND on the arrival `in` → the gate strips them and applies the
   § B.3 split: event rows get cursor coordinates, and the arrival `in`'s bogus
   `valid_to` is stripped to **None (absent), NOT rewritten to `t`** (proving the
   arrival stays a standing row). NO bogus coordinate reaches the log. Run the
   SAME batch through the documented `extract()→ingest_structured(extracted=True)`
   recipe and through `World.ingest()` → byte-identical (the parallel path
   carries prose mode, closing pbr's indistinguishability gap). A structured
   caller (`extracted=False`) passing the same numerics KEEPS them. And a
   non-null `valid_to` with null `valid_from` is skipped (§ B.2b).
5c. **Marker discipline, fail-closed (F3):** in `extracted` mode, a moved event
   whose `complete` marker is missing / non-boolean / duplicated across rows /
   conflicting → the WHOLE moved group and its matched arrival `in` are skipped
   with one `moved_marker_invalid` receipt; nothing is stamped, no arrival row
   is orphaned, no open event is silently assumed. A model emitting
   `attribute="complete"` as a row → that row is a malformed movement row
   (skipped), never a durable `complete` fact. A well-formed single
   `complete:true`/`complete:false` stamps as § B.3.
5d. **Arrival match is exact and synthesizes nothing (F3):** for `complete=true`
   with an entity-valued `destination`, only the batch `in` row with
   `entity`==agent, canonical `attribute`==`in`, `value`==destination, same
   frame gets `valid_from`=cursor / `valid_to`=absent; a decoy `in` row for a
   different entity or place in the same batch is untouched; no `in` row is ever
   synthesized; a literal destination has no arrival `in`.
5e. **The decisive prose-completion oracle (F3):** after a `complete` prose move
   to a bound destination at cursor `t`, all three hold at once — `events()`
   shows the zero-duration historical moved event; `in_transit(agent)` returns
   NONE (the event is closed); and `locate(agent, as_of=t)` AND
   `locate(agent, as_of=t+1)` BOTH return the destination (the standing arrival
   `in` is live from `t` onward, the r5 bug's exact inverse).
6. **Interval integrity** (F3): (a) an open event (no arrival) → `locate()`
   returns last-known origin, `in_transit()` returns the event with
   `last_known_containment`=origin, no `valid_to` authored; (b) a structured
   closed interval → containment flips to the destination only at/after
   `valid_to`, never before, and `in_transit()` stops returning it exactly at
   `valid_to` (the § D.7 strict tie-break, `valid_to == t` reads closed);
   (c) a zero-duration `[t,t)` event → invisible to every as-of valid-time
   read at `t` (buffer.py:258-262 exclusive bound), visible through `events()`
   as history, never `in_transit()`; (d) an inverted `valid_to < valid_from`
   is rejected at the gate (§ B.2).
7. **Two moves, one person** (F5): two distinct movements by the same agent
   yield two distinct `event:*` ids, each with its own endpoints; no rows
   cross-wire between them; histories do not conflate.
8. **Global-predicate safety** (F2): an unrelated entity carrying `origin`,
   `destination`, `mode`, or `actor` as its own attribute is **unchanged** by
   this spec — no global canonicalization touches it; only `event:*`/
   `kind=moved` rows use the movement keys, and the fold keeps them distinct.
9. **The anti-oracle battery** (all live prose from the probe logs), zero
   moved events from each: threshold-lingering ("keeps to the threshold, as
   if the dismissal has not quite settled the matter" — the rule-5-stall
   pattern: a host-vetoed exit gracefully stalled by the narrator must not
   have the machinery manufacture the departure it just vetoed); intent/
   facing ("turned toward the door"); non-person motion ("Cold air comes in
   for the moment the door is open"); descriptive motion ("rain running off
   his shoulders"); same-scene repositioning ("Brann the carter has taken a
   place near your end of the table").
10. **No-second-doorway pin** (scripted): a batch whose extraction contains
    a moved event commits containment rows ONLY from `in` items present in
    that batch; nothing is synthesized from the event post-gate.
11. **Public read/join** (F4): every event dict carries the six additive keys
    in the § E1 fixed byte-shape (`None`-defaulted when N/A — asserted exactly,
    not "absent-safe"); `*_bound` reflects stored `value_type=="entity"`; each
    `in_transit()` result is the fixed five-key shape `{agent, origin,
    destination, manner, last_known_containment}` with `last_known_containment`
    a resolved place value or `None`; the World and porcelain signatures match.
    `in_transit()` returns the correct set for an open exit, a structured
    interval, and a zero-duration completion, entirely through the public
    surface, honoring the § E2 anchor rule (same-cursor origin-before-event → in
    transit; arrival-after-event → excluded; no head → `None`).
11a. **Anchor decision-invariance** (F4): the anchor is
    `(valid_from, min asserted_at over the event's MOVEMENT PAYLOAD rows)` —
    `kind`/`agent`/`origin`/`destination`/`manner`, excluding `attr:*` rows.
    Permuting the payload-row identities within fixed event slots (and inserting
    a first-use `attr:*` declaration) leaves `in_transit()`'s include/exclude
    DECISION unchanged for a same-cursor origin-before vs arrival-after pair. The
    oracle asserts the decision, NOT that the absolute anchor tuple matches
    across independent writes (asserted_at is physical-append-allocated).
12. **No-degradation:** the existing eval suites and fidelity pins stay
    green; the location-changes clause keeps firing (the moved rule is ALSO,
    never INSTEAD); `events()`'s prior fields and defaults are unchanged.

Eval seeds: fixture passages extracted from Construct's probe corpus
(worlds/probe80_castmoves.\*, worlds/probe_d1_drift.\*, probe_d2/d3 for the
anti-patterns) into `evals/` per house practice.

## Non-goals (pinned)

- **No containment-behavior change.** An event-only exit does NOT auto-close
  or supersede the standing `in` row; last-known-location remains the
  containment read, and in-transit is a derived read (§ D.3, § E2) for a lens
  or host to make. RFC-002's unknown exists but is not invoked — machinery
  without a measured victim doesn't ship.
- **No `refer()`-based endpoint binding in V1.** The novel endpoint is a
  `literal` string (§ A.4); binding that name to a later-registered entity
  via a true reference-thunk (deterministic bind/receipt/projection) is
  V-next. **Tripwire:** a measured host case that needs a narrated novel
  endpoint bound to an entity registered afterward, with the event's
  endpoint expected to follow the binding.
- **No cross-ingest arrival closure** (departure in one call, arrival in a
  later call, reconciled into one interval) — V-next. **Tripwire:** a
  measured multi-scene journey whose single interval a consumer needs.
- No group movement (per-agent events suffice), no vehicle inference
  (`manner=drive` never mints the car; the text must name it), no non-person
  agents. **Tripwire (each):** a measured case in the corpus.
- No new **mutation** verb, no fold or `locate()` change. `in_transit()` is
  an additive derived READ (a sibling of `events()`/`locate()`), and the
  `events()` change is additive projection only.
- **No model-authored movement timestamps, ever.** In `extracted` mode the gate
  is the sole author of movement coordinates (§ B.3); the `extracted` signal's
  ONLY V1 effect is that coordinate pass — no other row behaves differently.
- Lean-variant parity is required (the rule lands in both blocks), but lean
  *enablement* stays separately eval-guarded, unchanged by this spec.
- No gate-level plausibility conditioning (the no-bias invariant, permanent).

## Docs on ship

INGESTION-PLAYBOOK (the movement rule; the `extracted`-mode coordinate pass; the
`extract()→ingest_structured(extracted=True)` recipe; `in_transit()`), LEXICON
(`moved` — the event kind; `in_transit()` — the derived read; `extracted` — the
prose-authoring signal), ADOPTION + HOST-DISCIPLINE (the no-second-doorway
statement; the additive `events()` payload + the `value_type`-based endpoint
discriminator; `in_transit()`; the requirement that a host replicating the
extract path pass `extracted=True`), the **whitepaper shipped-surface
catalogue** (the enriched `events()` payload + `in_transit()` as exported reads;
the two gate invariants), the **explicit MCP read registry** (`mcp.py` — the six
`events()` fields + `in_transit()`), STATUS.md (Open → Shipped).
