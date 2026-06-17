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

## Building now (passed all three)
| Item | Characteristic | Shape | Spec |
|---|---|---|---|
| **aggregate** | emergent collection properties (total weight, headcount, value, max level) | bounded derive-don't-store rollup over `contents` (sum/count/min/max/avg) | WORLD-RETRIEVAL-V2 |
| **multi-frame `frame_diff`** (#25) | an observer's *effective* knowledge = own frame ∪ `public` | `b`-side accepts a frame list; union-of-presences | WORLD-RETRIEVAL-V2 |

## Already supported / doc-only (no build)
| Item | Status |
|---|---|
| **Decimals (non-integer numbers)** | **Already in** — the value field holds any JSON number; `12.5`, `0.7`, `98.6` work today (int *and* float). |
| **Exact-precision money** | **Doc pattern** — model as **integer minor-units** (`$19.99 → 1999`); exact integer arithmetic, no float error, no new type. Native `decimal` would be a *guess on top of a solved problem*. |
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

| Item | Imprint | Passive/Invasive | Fails on |
|---|---|---|---|
| **Nested belief** (frames-about-frames) | **heavy — a new dimension** | **INVASIVE** (expands the frame model + threads belief-depth into reads, used or not) | overlap + shape + bulk — *the "multidimensional knowledge tracker" risk* |
| **General query** (`where x.foo and y.bar>3`) | medium-heavy — a query engine | **INVASIVE** (overlap/"which read?" exists on sight) | overlap + shape + P7. Trigger: a forbidden host full-log scan |
| **Native exact-decimal value-type** | medium — value layer | **INVASIVE** (every value path must handle it, used or not) | already solved by minor-units |
| **accrue min/max/avg folds** | light — a fold-policy value | **passive** (dormant unless declared) | reflexive need (thin) |
| **Salience tuning (config)** | light — defaulted weights | **passive** (learned version would be invasive) | premature |
| **Set/accrue confidence** | light — a `confidence` branch | **passive** | no need + unclear best-default |
| **Freshness-horizon verb** | light — a thin read | **passive** (whisker of redundancy w/ `last_observed_at`) | redundant |

## Resolved — actively decided against (not parked)
- **Frame-inclusion edges (#15.3)** — superseded by **flat-frames + read-union**:
  a *stored* inheritance delta would go stale into a lie; we compute the union
  at read instead. Closed.
- **MCP wrapper / `arch` CLI** — tooling mirrors, not data-structure shape.
