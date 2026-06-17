# RFC-002 — The Unknown: a doctrine for deliberation

**Status:** DRAFT for three-way deliberation (Kernos · Construct · Codex).
**Origin:** a founder design conversation on how the substrate must treat the
unknown. The goal of circulating this is to **ratify (or correct) the doctrine
before broader adoption locks the shape** — and, if ratified, fold it into the
whitepaper as a sharpened principle. **Whitepaper wins; this proposes to
*sharpen* P3/P2/P4, not contradict them.** This is doctrine, not code — but it
governs the read layer now in flight (salience/neighborhood) and the open
frame-inheritance decision (#4).

## 0. The founder's framing (the lidar)

A robot vacuum's lidar anchors its first observed object, then grows the world
relationally outward; everything unobserved is *nothing* until reached. The
substrate is the same: **it discovers what is there and never presumes, queries,
or fabricates what is not.** A box with an undefined object inside is fine — the
box is real, its contents an explicit placeholder; you define the contents and
they become canon; "some produce" later refines to "a banana" by supersession.
We never model "dynamics of the unknown inside the box."

This is correct and it is already the architecture (P3 — *nothing exists until
referenced*; the `frontier`; the `default`-provenance quarantine). The doctrine
below affirms it and sharpens two edges.

## 1. The three states of the unknown (all positive, none a void)

| State | Representation | Query answer |
|---|---|---|
| **Unestablished** | no row | `unknown` (honest silence) |
| **Established-deferred** | an `unresolved` thunk (`invent_under_canon`/`observe_or_unknown`) | resolves on force, memoized |
| **Established-unknowable** | a `deny` thunk + reason | stays unknown — *as canon* |

The third is the mystery box (everyone who looked inside died; nobody ever
learns): a **positive assertion that the thing is unknowable**. "It is known to
be unknown" is a presence, not a void. No new mechanism — `deny` thunks exist
(the sealed-footlocker test).

## 2. Sharpening #1 — absence is RELATIONAL, never ABSOLUTE

"Don't query what isn't there" is *almost* the rule, but taken literally it
forbids the substrate's best feature. The precise law:

> **Absence is never a stored thing and never an inference. It is only ever the
> computed *gap between two populations of present facts*.**

- *"What's in the box?"* with nothing recorded → `unknown`. Silence. ✓
- *"What does the player not yet know that's true?"* → `frame_diff(canon,
  knows:player)` → a real, essential answer. This **is** reasoning about the
  unknown, and it is legitimate, because it is *canon-presences minus
  player-presences* — a set difference of things that exist, never a query into
  a void.

So the engine **does** deal in the unknown, constantly (dramatic irony,
knowledge gaps, false belief) — but always *relationally* (the shadow cast by
two sets of real facts), never *absolutely* (a structured void you store,
enumerate, or invent).

## 3. Sharpening #2 — the one fenced channel for expectation

The substrate is not purely ascetic about the unobserved: `kind` carries
default expectations (a room has walls; a box probably holds *something*). But
those are **render-fill marked `default` provenance, and can never become
canon**. Expectation about the unknown exists — fenced off from truth by the
provenance membrane. The discipline is the fence, not abstinence.

## 4. Where the real danger is (the thing to actually guard)

The risk in the read layer is **not** "querying the void" — the architecture
forbids that. It is **derived/expected hardening into stored/asserted**:
- a salience score treated as truth instead of a disposable ranking;
- a frame model that stores *"X does not know Y"* as a row (a fabricated
  negative — the actual betrayal);
- a `neighborhood`/`materialize` read that "fills in" a thunk so output looks
  complete (painting the frontier).

The guard is the **membrane between *derived/expected* and *stored/asserted***
(P1/P2 + provenance). Keeping it perfectly intact is what makes this a
discovery engine, not a hallucination engine. The failure mode to police is
membrane-leakage, not unknown-reasoning.

## 5. Consequences (what the doctrine commits us to)

- **Reads never paint the frontier.** `neighborhood`/`materialize` report an
  `unresolved`/`deny` thunk *as* unresolved (with its policy), never filled.
  (Already a projector rule; carried into WORLD-RETRIEVAL.)
- **Salience is disposable ranking, never truth.** Rebuildable sidecar, never
  logged; ranking never gates correctness — a fact unmentioned for years has
  zero salience and full validity.
- **Frame inheritance (#4) must never store a negative.** "What X doesn't know"
  stays *structural absence* (P4) computed by `frame_diff`, never a stored row.
  This nudges #4 toward **read-resolution only**, or toward **keeping flat
  frames** (where the unknown is purely the absence of a row — the cleanest
  possible expression of the doctrine).
- **Negation-as-asserted-fact is legitimate and different.** "The vault is
  sealed," an alibi ("Marn was not at the scene"), an *observed* empty box —
  these are discovered *positive* facts with negative-sounding values, not
  inferences about a void. Emptiness-by-default (no contents row ⇒ presume
  empty) is forbidden; emptiness-as-observed is fine.

## 6. The deliberation — what each reviewer is asked

**Kernos (philosophy / V2):**
- Is "absence is relational, never absolute" the right law, or is there a case
  it breaks?
- Does a *continuous real-world* World Model need unknown-handling this doctrine
  doesn't cover — **stale belief** ("I used to know where the keys were"),
  **confidence decay**, **lapsed observation** (the value was X when last seen,
  now unknown)? Are those new states of the unknown, or just time-scoped
  presences/frame_diffs?
- Is the membrane-leakage framing the correct location of the risk?

**Construct (the narrative-mystery consumer):**
- Do the three states (+ the relational/`frame_diff` unknown) cover every
  narrative unknown you actually run — red herrings, unreliable narration,
  a clue known-to-exist-but-not-found, a lie a character believes?
- Is the `deny`-thunk-with-reason the right shape for a permanent mystery, or
  do you model "nobody knows" differently today?
- Anywhere your host is tempted to store a negative or paint a frontier (so we
  can give it the doctrine-honoring pattern instead)?

**Codex (engine audit):**
- Audit the codebase against the doctrine: any path where **derived/expected
  leaks into stored/asserted**, where **absence is treated as a primitive**
  (a stored negative, a presumed-empty, an enumerated void), or where a read
  **paints the frontier**? Include the in-flight WORLD-RETRIEVAL read layer.
- Is the `default`-provenance fence actually unbreakable (no role can promote
  `default`/`generated` to canon)?

## 7. If ratified
Fold §2 (relational absence) + §4 (the membrane) into the whitepaper as a
sharpening of P2/P3/P4; record the three-state taxonomy + the `deny`-thunk
pattern in HOST-DISCIPLINE.md / LEXICON; resolve #4 frame-inheritance per §5.
