# MERGE-GATE-V1: a yes/no check on lexical merge candidates (roadmap R25, part A)

**Status:** r1 (2026-10-12), for pbr's spec review. The monitor approved specifying R25 for Kabe
(gate g90c34b, note ndfbe02): spec it through pbr, fix the pass mark on what is free to measure, and
bring the metered measurement to Kabe, with its cost, run count and pass mark, before anything
metered runs.
**Source:** research note technique 2 (`docs/research/book-to-world-extraction-2026-10.md`), taken
from Zep/Graphiti (lexical candidates, then an LLM yes/no with "most complete name") and NarraWorld
(the harness mints ids).
**Builds on:** ALIAS-INDEX-V1 Part B (R24: one shared `finalize_identity`; book commits
`reconcile`), IDENTITY-REPRESENTATIVE-V1 (a host merge names its survivor), IDENTITY-ROOT-CAUSES-V1
(host merges record `decided_by: host`).

## R25 split in two

R25 reads "handle-based incremental `extend` with a verified merge gate". It is two separable
pieces, and only the second can be measured without new metered builds:

- **Part B, later: handles in pass-0.** Segments emit local handles and the harness mints the ids.
  This changes pass-0's output, and only metered pass-0 runs can measure it. It gets its own spec
  after part A has landed.
- **Part A, this spec: the verified merge gate.** It works on any registry already committed, and
  it can be measured now on the five stored registries. It addresses exactly the fragmentation R24
  left behind.

## What is left after R24 (measured, no model calls)

All five stored registries were run through R24's default commit path (`seeded_registry` with
their segments), and the remaining split entities were listed:

| Registry | Split gold entities after R24 | What they are |
|---|---|---|
| R23 run1, run2; R26 seq | 0 | nothing |
| R26 par1b | 4 | Ilsa (the two cards share only "the clerk"); her desk, as "Ilsa Renn's desk" and "Ilsa's desk"; the vial crate; Wellhead (as an `org` and as a `place`) |
| R26 par2b | 7 | Ilsa; the desk; the memory core; the false drawer; Tovan's letter (`doc` and `obj`); the aquifer maps (`doc` and `obj`); Wellhead (`org` and `place`) |

None of these is something the engine's `reconcile` should merge on its own:
- possessive names are not name-like anchors (R35);
- "the clerk" is a shared generic alias;
- a cross-kind pair is never an automatic merge.

They are exactly the cases a judge reading the cards can decide. A host `merge` joins every one of
them, the three cross-kind pairs included (probed on par2b).

## The shape

### Candidates (deterministic, no model)

After `finalize_identity` has run `promote_identity_proposals` and `reconcile`, the gate takes
each pair of distinct closure representatives, `(a, b)`, that:
- **shares an identifying token.** The token is a content word from either card's names or
  aliases: lowercased, possessive `'s` removed, at least 3 characters, not a stop word (the
  articles, possessive pronouns, `of`, `old`, `new` and the like), and not in the alias index's
  kinship/address stoplist. **Or** the two cards share an exact normalized name or alias string,
  even a stoplisted one: "the clerk" is how the Ilsa pair is found;
- **is not person against non-person**;
- **is not already held apart.** The pass skips any pair with `distinct_between(a, b) != []`
  (R42), whether written by R24's pass or by anyone else;
- **is not already one closure.**

Candidates are sorted by `(a, b)` and sent in batches of `batch_size` (default 25).

### The gate (one model call per batch)

- **The call.** The pipeline's injected model is called with a `merge_gate` schema.
- **Per pair, the request gives:**
  - each side's id, kind, names and aliases, read from the world's own `name`/`alias` rows on
    the closure, in canon;
  - up to two source sentences per side that mention one of its names. These come from the alias
    index's mention hits on the same durable `source_segments.json` R24 reads. With no source,
    the sentences are omitted and the pair is still asked.
- **Per pair, the answer is** `{"pair": [a, b], "verdict": "same" | "different" | "unsure",
  "keep": a | b, "reason": "<one line>"}`. `keep` is the id whose name is the most complete one.
- **Malformed answers are unsure.** A missing pair, an unknown pair, a duplicate pair, an unknown
  verdict, or a `keep` that is neither side is treated as `unsure` for that pair and logged. A
  batch whose whole answer is unparseable makes every pair in it `unsure`. The gate never retries.

### What is written

- **`same`.** The pipeline writes `porcelain.merge(a, b, evidence="merge gate: <reason>",
  representative=keep)`, a host merge (`decided_by: host`, R35). Being a `same_as`, it can be
  reversed by retraction. A vetoed merge (a containment or `distinct_from` veto the engine applies)
  writes nothing and is reported.
- **`different` and `unsure`.** Nothing is written; both are reported. The gate starts
  precision-first, as the research note advises. Writing `distinct_from` for a `different` is a
  later choice, to make once the gate's measured precision justifies it.
- **The report.** `run_dir/merge_gate.json` lists every candidate, the batch it went in, the
  verdict, `keep`, the reason, and the receipt outcome of any merge. It also records the counts
  and the model's identity string, if the injected model exposes one.

### Where it sits, and the flag

- **One step added to the shared finalization.** `finalize_identity(w, *, reconcile, gate)` now
  runs promote, then reconcile, then **the gate**, then `confirm_frame_owners`. `Pipeline.commit`
  and the grader both get it.
- **`Pipeline(merge_gate=False)` by default.** The gate needs a real model, and its precision on
  real answers is not yet measured. It turns on only after the metered measurement below passes
  and Kabe says yes.
- **Off means unchanged.** With the gate off, the commit is exactly R24's default, byte for byte.
- **For the free measures,** `seeded_registry(..., gate=<callable>)` accepts a gate callable in
  place of the model.

## Pass mark, part 1: free, fixed before the build

All on the five stored registries, through the shared path, with no model calls:

1. **Candidate recall.** Every pair of ids that the grader reports as one split gold entity after
   R24 is a candidate: **11 of 11** (par1b 4, par2b 7). The candidate count is reported: 84, 98,
   92, 287 and 285 today, which is 4, 4, 4, 12 and 12 batches of 25.
2. **Oracle ceiling.** A test gate answers `same` exactly for the candidates whose two cards
   resolve to the same single gold entity, and `unsure` for every other pair. With it:
   - split entities are **0** in all five registries;
   - fused ids are **0**;
   - **F1 is never below R24's default.** It is at least **0.8483** on par1b (0.8320 today) and at
     least **0.8339** on par2b (0.7961 today).
3. **An all-`unsure` gate, and the gate off,** both give a log byte-identical to R24's default
   commit.
4. **Malformed answers.** Each malformed shape listed under the gate (missing, unknown, duplicate,
   bad verdict, bad `keep`, an unparseable batch) merges nothing for the pairs it touches. It is
   logged and reported, and the other pairs in the batch are unaffected.
5. **Determinism.** The same gate answers give a byte-identical log and `merge_gate.json`, from the
   original `Pipeline` and from a fresh one on the same `run_dir`.
6. **Persons and vetoes.**
   - A person×non-person pair is never a candidate.
   - A pair already held apart by `distinct_from` is never a candidate. The R24 vault pair is the
     witness.
   - A `same` verdict that the engine vetoes writes nothing, and is reported with the veto's
     reason.
7. **`keep` is honoured.** The merged closure is served under the id `keep` names
   (IDENTITY-REPRESENTATIVE-V1).

## Pass mark, part 2: the metered measurement, for Kabe's yes (not run by this spec)

- **What runs.** The real gate (the pipeline's model) on the candidate lists of the five stored
  registries. No pass-0 or pass-1 is re-run: the registries are the stored ones.
- **Runs.** Two repetitions, to see the run-to-run disagreement.
- **Expected cost.** 36 batched calls per repetition (4+4+4+12+12), so **72 calls**.
  - Each call carries about 25 pairs, roughly 4–6 k tokens in and under 1 k out: about **0.4 M
    tokens** in all.
  - It takes about 10–20 minutes of wall clock, at the R26 runs' observed call latency.
  - The build reports the exact counts before asking.
- **Judged against:**
  - **Precision.** No `same` on any pair whose cards resolve to different gold entities, in
    either repetition: 0 of the 43 gold-different candidates (run1 5, run2 9, seq 4, par1b 16, par2b
    9).
  - **Recall.** At least **8 of the 11** gold-same pairs merged, in each repetition.
  - **F1 not below R24's default** in any registry, in each repetition.
  - **Unlabelled candidates** (most pairs have no gold label): the number of `same` verdicts is
    reported, with 20 sampled pairs listed for Kabe to look over. They are not scored.
  - **Run to run:** the pairs whose verdict differs between the two repetitions are listed.
- **If it passes:** a separate one-line change, with Kabe's yes, turns `merge_gate` on by default.

## Not in this spec

- Part B (handles in pass-0) and parallel pass-0 by default (R26). Both need metered builds and
  come later, each with its own ask.
- Writing `distinct_from` for `different` verdicts.
- Any engine change: the gate uses the porcelain's `merge` and the R42 reads.
