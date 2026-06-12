# Chapter report: the spike, the chapter test, and what they proved

**For:** the founder, Kernos CC, and PB — the chapter-closing artifact for
joint review. Seed v1-final; runs of 2026-06-11. Presentation per the
letter-010 intentions: accuracy is the product; caveats in the open.

**About this document's shape (review this too):** the founder asked that
the presentation structure itself be on the table. The report runs in five
parts — (1) the claim and the test, (2) the number and its anatomy, (3) what
the test caught, (4) the demonstrable moment, (5) what this does not show,
and the decisions it opens. If this shape works, it becomes the template for
milestone reports.

---

## 1. The claim and the test

pattern-buffer claims a language model can keep a complete, durable,
queryable world — and that the way to prove it is to **ingest a whole story,
delete the prose, and interrogate the database against a hand-authored
answer key**. We did that: a four-chapter noir mystery (*The Last Honest
Meter*, written against a 33-point coverage matrix, with a story bible the
ingestor never sees) became an append-only log of assertions; every question
— where was the memory core during the assembly, what does Sela know, is the
footlocker still sealed — was answered by deterministic queries over the
log, in milliseconds, with zero model calls on the read path.

Two full ingestion runs were graded. Between them, exactly one variable
changed: the extraction contract (the instructions given to the model that
reads the prose). The engine is identical in both.

## 2. The number and its anatomy

| | Run 1 | Run 2 |
|---|---|---|
| Extraction contract | v1 (baseline) | v2 (run-1 lessons encoded) |
| Assertions / entities | 455 / 58 | 618 / 67 |
| Scorecard | **21/33** | **17/33** |
| Failures after dump audit | 12 extraction, **1 engine (fixed)** | 16 extraction, **0 engine** |

Two readings matter more than either number:

**The substrate held both times.** Every battery item that interrogates the
*engine* over correctly-filed rows passed in both runs: append-only survived
ingestion noise; sealed containers stayed sealed with zero phantom contents
(both runs, both containers); atmosphere never became assertions; knowledge
frames stayed structurally absent from canon payloads; the budget never
compacted structure; as-of folds answered correctly over whatever rows
existed. The generated scorecards each flagged 2 "shape" failures; dump
audits reclassified all of them — run 1's three shape flags resolved to two
grader bugs and **one real engine bug** (a character's filed theory held
fold incumbency over a later observation; fixed the same day as the
assumption-quarantine rule, with a test); run 2's two resolved to key
fragmentation and a frame misfile, both extraction.

**Extraction is the bottleneck, and contract iteration alone does not close
it.** Run 2 extracted 36% more, fixed targets the v2 contract named (the
letter's claims now converge on one key with the false location claim
correctly superseded; identity merges fired), and still scored lower —
because richer extraction fragmented *other* keys. The deliberate reactor
contradiction stopped firing not because the engine merged anything but
because the two values landed on three different attribute names; the core's
late-revealed custody chain landed in `knows:narrator` instead of canon —
in both runs, under two differently-worded contracts. The model partially
complies with any prose contract. The whitepaper's prior-art section called
fiction extraction "the weak front end"; that prediction is now measured.

## 3. What the test caught (it earned its keep in both directions)

- **One engine bug, found and closed:** assumption quarantine at the fold
  (`assumed` never holds incumbency against evidence). Found only because a
  real extractor filed a narrator's theory as `assumed` — no synthetic test
  had composed those statuses on one key.
- **A 19-rule ingestion playbook** (docs/INGESTION-PLAYBOOK.md), every rule
  citing the run that taught it: the canon-vs-knows discipline, mandatory
  aliases, convergent keys, relation under-extraction, the timeless
  whitelist; chunking, roster threading, deferred batch classification, shim
  hardening (incl. quota exhaustion as a distinguishable, fail-fast failure
  mode); the engine guards that worked unaided; grading discipline.
- **Grading lessons:** the grader must find the extractor's entities rather
  than dictate them, and every "shape" label must be audited against the raw
  dump before it escalates — the label means "stop the line," and it was
  wrong four times out of five.

## 4. The demonstrable moment

The drawer-test family of queries, run live against the run-2 world —
including the one that shows both the power and the bottleneck in a single
answer. The bible's hardest probe: *where was the memory core during the
Chapter One assembly?* — an event narrated nowhere, revealed three chapters
later, requiring the two-time-axis fold. The extractor misfiled the custody
rows into the narrator's knowledge frame. Query that frame, and the engine
answers perfectly over those rows:

```
core @ day 2.0  (knows:narrator) -> obj:clerk_desk    (the false-drawer days)
core @ day 4.5  (knows:narrator) -> place:vault       (moved during the assembly)
```

Late-revealed history, folded correctly, served as-of any moment — the
machinery works end to end; what failed was one filing decision by the
reading model. Alongside it: footlocker 0447 carries no contents row in any
frame (never invented, never opened); the run-1 world's reactor contradiction
stands flagged with both rows alive; every query above cost milliseconds and
zero tokens.

## 5. What this does not show, and the decisions it opens

**Not shown:** messy conversational ingestion (the dialogue micro-eval is
the bridge); the §19.2 interactive criteria (incl. letter 013's loop-closure
notes); tracking-mode staleness in the wild; throughput at archive scale.

**Decision A — how ingestion gets fixed (recommendation: registry-first,
not contract v3).** Serial contract iteration showed its ceiling in one
cycle. The playbook's §E design replaces it: pass 0 reads the *whole*
document once and pins the registry (entity ids, aliases, canonical
attribute names, timeline, place graph) — killing identity fragmentation and
key divergence by construction; pass 1 extracts scene chunks **in parallel**
against the frozen registry in a compact line grammar; pass 2 audits the
folded world against the gate's anomaly list through proper write paths.
Measured baselines vs the analytical estimate:

| Approach | Sequential rounds | Wall clock | Output tokens |
|---|---|---|---|
| Run 1 (serial, JSON, 300s cap) | ~17 | 77 min (36 min excl. failures) | ~80k+ |
| Run 2 (serial, JSON v2, 600s cap) | ~17 | ~96 min incl. quota outage | ~110k+ |
| Registry-first (§E, estimated) | **3** | **~4–5 min** | **~20k** |

Needs to build it: an SDK shim (replacing the CLI subprocess; enables prompt
caching + parallelism), the line-grammar parser at the gate (deterministic,
rejects malformed lines), the pass-0/pass-2 prompts, and quota-aware
operation (already landed). Engine changes: none. Natural moment: the
anchor.world production pipeline (letter 005) needs exactly this machinery —
one build serves both.

**Decision B — what "done" means for this chapter.** The whitepaper's gate
language says extraction failures are "fix and re-run." Recommendation:
declare the *substrate* validated (its failures were found, fixed, and
re-proven; nothing on the §18.1 checklist was compromised), hold the
*extraction* number open, and re-run the chapter test once registry-first
ingestion exists — predicted to clear most of the 16 extraction failures at
a tenth the wall clock. Alternative: a contract-v3 serial run now (~90 min,
quota exposure, diminishing returns).

**Decision C — sequencing after this chapter:** anchor.world + zero-key tour
(letter 005, riding Decision A's pipeline), the messy-dialogue micro-eval,
the 008 porcelain. Proposed order: A's build → chapter-test re-run →
anchor.world → micro-eval → porcelain.

---

*Artifacts: scorecards + dumps under evals/results/2026-06-11-v1-final*
*(run 2) and -run1/; the playbook at docs/INGESTION-PLAYBOOK.md; the*
*assumption-quarantine fix in commit history with its test; 57-test suite*
*green at every commit.*

---

## Decisions: CONFIRMED (founder + Kernos CC, 2026-06-11)

**A — registry-first over contract v3. Go.** Founder's analysis: the
run-1→run-2 inversion is structural evidence (partial compliance fragments
differently every round); the third options collapse into registry-first
(post-hoc canonicalization = a weaker pass-2; schema-constrained decoding
needs a vocabulary-generating first pass = pass-0). Residual risk is
concentrated in pass-0 quality, instrumented by the registry-escapes audit,
and cheap to discover — and A is the cheapest test of itself: if the re-run
doesn't clear most of the 16 extraction failures, that's a finding about the
approach, discovered for the price of a build the anchor.world pipeline
needed anyway.

**B — substrate validated; extraction number held open. Go.** Not
goalpost-moving: the whitepaper's failure taxonomy, written before any test
ran, prescribes exactly this (extraction = fix and re-run; shape = stop).
Zero open shape failures after dump audit across two runs; the one engine
bug was fixed, tested, re-proven. The public claim stays precise: substrate
invariants held; ingestion fidelity not yet passing.

**C — sequencing as proposed. Go.** Re-run → anchor.world is nearly one
motion (corrected output becomes the canonical dump by stamping);
micro-eval before porcelain because messy-dialogue ingestion informs
`ingest()`'s final signature; porcelain last because the Kernos adapter
builds against it.

---

**What changed in the canonical docs because of this milestone:**
WHITEPAPER.md gained amendments A1/A2 + the §24.1 amendment log;
specs/SPIKE-V1.md gained the assumption-quarantine fold rule;
docs/INGESTION-PLAYBOOK.md was created (19 rules + §E registry-first design,
incl. letter-014 constraints: registry escapes as a failure class,
establish/extend interface); README/ADOPTION.md/llms.txt landed per the
009/010 docs discipline.

*Raw run artifacts for this run are preserved in git history at commit `2734ea2`; the working tree carries reports and scorecards only (letter 017).*
