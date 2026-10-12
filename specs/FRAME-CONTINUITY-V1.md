# FRAME-CONTINUITY-V1: widening a frame is an explicit choice, and every row says where it lives

**Status:** r1, spec for pbr review before code. Author: pb, 2026-10-12. Roadmap R36.

**Decisions.** Gate g3bf5da (consult ccab80f):
- **P2:** accepted by Kabe on 2026-10-12.
- **P4:** accepted on 2026-10-12 by the monitor, which Kabe had asked to take the best
  recommendation.
- **P1** (frames read only their own names; FRAME-SCOPED-IDENTITY-V1 §7 withdrawn) is in force,
  and this spec builds on it.

> **P2:** "Widening a frame becomes an explicit, logged choice, never implied by identity: a
> host-controlled frame-continuity/combine event, with provenance and reversible by retraction.
> Book worlds have no host, so a reader answering a book character's point of view can opt in per
> read. The eval battery then grades the engine's own frame read instead of computing its own
> union."
>
> **P4:** "Before any read that crosses frames or merges ships, every row it returns says which
> stored frame it came from, and frame scans default to the exact frame. Otherwise a host's
> scan-then-retract loop writes permanent retractions into another character's frame (measured: 72
> rows on emberroad2)."

**Where we start.** Every frame-taking read already reads exactly the rows stored under the frame
name it is given (P1). Nothing crosses frames by default. This spec adds the **only** two ways to
cross, both explicit, and the labelling P4 requires before either ships.

## §1 Every fact says its stored frame (P4)

- **The label.** `Fact.provenance` gains `"frame": <the row's stored frame>` on every fact, from
  every read. One shape everywhere; no read has a different payload.
- **Additive.** The new key sits after the existing keys. A host that reads `provenance["status"]`,
  `["source_chain"]` or `["assertion_id"]` is unaffected. A host that compares whole provenance
  dicts for equality sees the new key; construct's suite is the check (§6).
- **A host's scan-then-retract loop** retracts only facts whose `provenance.frame` is the frame it
  meant to clean. ADOPTION.md gains that rule, worked through the emberroad2 case.

## §2 Frame scope: exact by default, wider only on request

Every porcelain read that takes `frame` gains **`frame_scope`**: `"exact"` (default) |
`"continued"` | `"merged"`.

| Scope | Rows read for frame `knows:X` |
|---|---|
| `exact` | Those stored under `knows:X`. **This is today's behaviour, byte-identical.** |
| `continued` | `exact`, plus those stored under every `knows:Y` that the host declared continues into `knows:X` (§3), transitively, as of the read. |
| `merged` | `exact`, plus those stored under `knows:m` for every `m` in X's canon `same_as` closure, as of the read. This is the per-read opt-in for worlds with no host to declare continuity (books). It never follows `aka` correlation; facets stay two things. |

- **Which frames are affected.** Only `knows:` frames widen. For `canon`, `plot:*` and any other
  frame, `frame_scope` other than `exact` is refused (`ValueError`), not ignored.
- **Labelled.** Under `continued` or `merged`, folds run over the union of the selected stored
  frames as one row set, by the ordinary fold rules. Every served fact carries its stored frame
  (§1), so a reader can tell which character's knowledge each row came from.
- **Scans never widen silently.** `facts()` and `entities()` take `frame_scope` like every other
  read and default to `exact`. A scan widens only when the caller says so, and then every row says
  its stored frame.
- **Writes never widen.** Every write lands in exactly the frame it names. `frame_scope` exists on
  reads only.
- **Implementation.** The porcelain resolves the scope to a tuple of stored frames once per call.
  The indexes and `buffer.visible(frame=...)` accept that tuple, as an `IN` clause, wherever they
  accept a frame name today. Caches key on the tuple. The `exact` scope passes the plain string, so
  its code path and caches are unchanged.

## §3 The host's continuity event (P2)

- **The write.** A new porcelain verb, `continue_frame(source, into, evidence)`. It declares that
  what `source` knew is part of what `into` knows. Both are observer ids, e.g.
  `continue_frame("person:daniel", "person:dan", "the same man; host decision")`. It writes:
  - one canon row, `person:daniel · frame_continues_as · person:dan`, timeless, status `stated`;
  - an `evidence` row, as merges carry.

  The verb returns a Receipt.
- **Host only.** `frame_continues_as` is accepted only through this verb, or as a canon,
  entity-valued item in a host's structured ingest. It is **never** accepted from prose
  extraction: an item with `extracted` set skips it, with reason `host_only_predicate`. It is also
  never accepted outside canon (`identity_edge_outside_canon` covers the frame rule, since this is
  identity-adjacent canon structure).
- **Direction.** One way. `into` reads `source`'s knowledge under `continued`. `source` gains
  nothing. A host that wants both directions writes two events.
- **Reversible.** Retracting the row ends the continuity from that log position. `asserted_as_of`
  reads see it as it stood.
- **Never implied.** No merge, `confirm`, `reconcile`, `aka` or `retype` writes or reads it. Under
  P1, identity never widens a frame.
- **Vocabulary.** `frame_continues_as` joins `INVIOLABLE_CORE` (a host cannot redeclare its
  semantics) and the lexicon.

## §4 The battery grades the engine's read

`evals/harness/battery.py` verdict 16 today builds its own union: every `knows:` frame whose
observer resolves to Sela. It changes to read Sela's frame through the engine, with
`frame_scope="merged"`, and grades what the engine serves. Any other battery verdict that unions
frames by hand moves the same way, and the build lists them.

## §5 Interaction with WORLD-SERVICE-V1

A viewer session's adapter refuses a caller-supplied `frame_scope`. The service uses the scope the
host configured at `attach` (default `exact`), so a viewer cannot widen its own view through
`merged`. This is noted to WORLD-SERVICE-V1, which is in review, as a one-line addition there.

## §6 Checks

1. **§1:** every porcelain read's facts carry `provenance.frame`. With `exact`, every other byte of
   every payload is unchanged: on copies of construct's worlds, with the new key stripped, the
   payloads are compared against main.
2. **§2:**
   - `exact` equals today on every read.
   - `continued` follows declared edges transitively and stops at a retraction.
   - `merged` follows the canon closure only, never `aka`.
   - Non-`knows:` frames refuse a non-exact scope.
   - `facts()` and `entities()` default to exact.
   - Under a wide scope, each fact's `provenance.frame` names its stored frame.
3. **§3:** the verb writes canon only. An extracted `frame_continues_as` item skips
   `host_only_predicate`, and one outside canon is refused. Retraction ends the continuity, and
   pinned reads honour it.
4. **§4:** verdict 16 on the stamped anchor world gives the same PASS or FAIL as today's hand union
   (both are run and compared).
5. **The emberroad2 scenario:** a scan-then-retract loop keyed on `provenance.frame` retracts zero
   rows outside its own frame under every scope. This is P4's measured 72-row case, rebuilt on a
   copy.
6. The full suite passes, and construct's suite on the branch is green before merge.
