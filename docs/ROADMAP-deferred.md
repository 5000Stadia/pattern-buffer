# ROADMAP-deferred.md — the deferred backlog, on display

**What this is.** A generalized world/reality tracker is proven *general* not by
pre-building every characteristic, but by every characteristic slotting in
**additively** when a real world needs it. This file records the characteristics
not yet built, their **additive path**, and the verdict — so the architecture's
*extensibility* is visible without carrying the *surface*.

**The decision criterion** (refined with the founder). A candidate is built
proactively when **all three** hold; otherwise it waits — and the file records
*which* axis it fails, because that is the real reason:
1. **Reflexive need** — would any world-tracker reflexively reach for this to
   hold valid, relevant, long-term context?
2. **No overlap (anti-dilution)** — it *deepens* a concept along its own axis or
   fills a *clean gap*; it does **not** add a second, competing way to express
   or retrieve something (which forces an adopter to ask "which do I use?").
3. **Shape-confidence** — the best-default shape is inherent/knowable now, not a
   guess we'd be stuck with (pre-v1 the freeze is soft, but a wrong *shape* is
   still churn).

Pre-v1, the surface is malleable; this file is revised as worlds reveal needs.

---

## Shipped
| Item | Characteristic | Shape | Spec |
|---|---|---|---|
| **exact-decimal quantities** | money / any exact ledger folds without float drift | opt-in `Decimal` value + reserved `{"$decimal":"…"}` tagged scalar on every JSON boundary; one value codec; fixed-context (prec=50, HALF_EVEN) folds → byte-deterministic; raise-on-mix (`Decimal`+`float`); authored scale preserved. **Founder-directed 2026-07, superseding the minor-units doc-pattern verdict below** (an exact ledger is a reflexive tracker need; the tag is additive, dormant for float worlds). | EXACT-DECIMAL-QUANTITIES-V1 |
| **identity shape-fix** | phantom/typing/fragment repair from lived play | `adjudicate_deferred` (anchor-subsumption merge), `retype`/`typing_conflicts` (kind-slip correction distinct from merge), the durable-contradiction veto, the malformed-id gate + `pov` deixis binding | SHAPE-FIX-V1 |
| **bounded roster/scan reads** | a host's frame-scoped enumeration without reaching below the porcelain | `entities(frame, prefix=)` / `facts(frame, …)`; frame-required (no cross-frame existence leak) | BOUNDED-READS-V1 |
| **build lifecycle + axis-heads** | scenario/source builds on the pure porcelain | `begin_build`/`seal_build`/`abort_build` (+`build()`), `axis_heads()` (two-axis high-water mark) | BUILD-SESSION-V1, AXIS-HEAD-V1 |
| **multi-frame `confidence`** | trust over an observer's *effective* knowledge = own frame ∪ `public` | `frame` accepts a list; per-frame fold, effective winner = most-recent, conflict = any per-frame conflict or cross-frame disagreement, corroboration = union of per-fold V1 classes + strict cross-frame scan; a deduped single-frame list delegates to the str path (reduction invariant) | CONFIDENCE-MULTIFRAME-V1 |
| **`situation` lens** | re-entry retrieval: standing truth ∪ *live* threads, closed history dropped; liveness = open thread (a) OR surviving un-superseded effect (b); effect-driven anchoring; recency overflow over a protected floor | a 5th `materialize` lens; derived every read, nothing stored; proven against a 3-domain adversarial battery ((a)+(b) shown exhaustive for engine-knowable present relevance) | SITUATION-LENS-V1 |
| **aggregate** | emergent collection properties (total weight, headcount, value, max level) | bounded derive-don't-store rollup over `contents` (sum/count/min/max/avg) | WORLD-RETRIEVAL-V2 |
| **multi-frame `frame_diff`** (#25) | an observer's *effective* knowledge = own frame ∪ `public` | `b`-side accepts a frame list; union-of-presences | WORLD-RETRIEVAL-V2 |

## Already supported / doc-only (no build)
| Item | Status |
|---|---|
| **Decimals (non-integer numbers)** | **Already in** — the value field holds any JSON number; `12.5`, `0.7`, `98.6` work today (int *and* float). |
| **Exact-precision money** | **SHIPPED as a native type** (EXACT-DECIMAL-QUANTITIES-V1, above) — the minor-units doc-pattern was the pre-decimal answer; the founder ruled an exact ledger a reflexive tracker need and directed the native `Decimal`/`$decimal` value, opt-in and dormant for float worlds. This row is retained for lineage. |
| **Observed completeness** ("is there a 4th key?") | **Doc pattern** — assert a positive fact (`keyring · count · 3 (observed)` / `complete_as_of`); "is there a 4th?" is then relational. Closed-world *answers* without a closed-world *assumption*. |
| **Norms / goals / modality / units / habits** | **Already expressible by composition** — norms = facts about norm-entities; goals = facts about agents; possibility/counterfactual = branch-worlds (A5) + the `hypothetical` stance; measurements = structured literals; habits = DISPOSITIONAL + accrual promotion. |

## Strong follow-on (passes; its own spec next)
| Item | Characteristic | Shape | Why not bundled |
|---|---|---|---|
| **confidence / freshness read** (C) | belief that ages; "is this still current?" (reality / V2) | a *derived read under the membrane* — confidence = temporal salience (recency × corroboration × provenance), freshness = `now − t`; Kernos-shaped | read-layer, host-computable today; no overlap → a clean follow-on, not bundled with V2 |

## Deferred — passive vs invasive, and the axis each fails

**The discriminator (founder).** *Passive* = a dormant branch / optional verb /
policy value that does nothing if unused — pre-building costs ~nothing and it
provides shape the moment it's used. *Invasive* = it touches a core path, the
shared mental model, or overlaps an existing thing, so it imposes cost **whether
or not anyone calls it**. **Founder directive: hold the invasive ones; surface
them for a deliberate discussion after the lined-up work — never auto-build.**
The passive ones are afternoon-jobs added when a real need shapes them; no
urgency, no loss in waiting.

**Refined rule (founder).** *Passive AND contextually-likely-for-use → it's in*
(dormant cost ~zero, the shape is wanted). *Passive but not contextually likely*
→ **tossed**, not parked (below). *Invasive* → held + surfaced for a deliberate
discussion, never auto-built.

### Held — invasive (surface for discussion, never auto-build)
| Item | Imprint | Why invasive | Fails on |
|---|---|---|---|
| **Nested belief** (frames-about-frames) | **heavy — a new dimension** | expands the frame model + threads belief-depth into reads, used or not | overlap + shape + bulk — *the "multidimensional knowledge tracker" risk* |
| **General query** (`where x.foo and y.bar>3`) | medium-heavy — a query engine | overlap/"which read?" exists on sight | overlap + shape + P7. Trigger: a forbidden host full-log scan |

*(Native exact-decimal, formerly held here as invasive, was **built** 2026-07 at founder direction — see Shipped. The concern it named — "every value path must handle it, used or not" — was answered by making it opt-in and codec-centralized: float worlds never enter the Decimal path and are byte-identical.)*

### Pending founder read
| Item | Imprint | Note |
|---|---|---|
| **Salience tuning (config)** | light — defaulted weights, passive | weakly-likely at best; ship the config object now or stay tossed until a host misranks. Learned/adaptive version is invasive (held above). |

### Tossed — passive but not contextually likely (decided against, not parked)
- **accrue min/max/avg folds** — a delta-ledger rarely wants min/max/avg; thin reflexive need.
- **Set/accrue confidence** — best-default shape unclear (trust over a *set* of values? a running total?); no live need.
- **Freshness-horizon verb** — redundant with `last_observed_at` already on `confidence`.

## Resolved — actively decided against (not parked)
- **Frame-inclusion edges (#15.3)** — superseded by **flat-frames + read-union**:
  a *stored* inheritance delta would go stale into a lie; we compute the union
  at read instead. Closed.
- **MCP wrapper / `arch` CLI** — tooling mirrors, not data-structure shape.
