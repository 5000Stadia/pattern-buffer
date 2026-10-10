# PASS0-GRADER-V1: grade pass-0's registry against gold (roadmap R23)

**Status:** r1 (2026-10-10). Measurement only: no engine code changes. M3's first
item: before any technique from `docs/research/book-to-world-extraction-2026-10.md`
lands (the alias-index pass, handle-based `extend`, parallel pass-0), there is a
number that says whether it helped.

## What it measures

Pass-0 (`evals/harness/registry.py`, `establish()`) builds the world registry:
one `EntityCard` (kind, names, aliases) per id the extractor mints. The audit and
the research note name its failure mode: **fragmentation**, one person minted as
several ids, and its opposite, two people fused into one id.

The gold set is the one that already exists: `evals/harness/fixtures.py`
`ENTITIES`, 28 entities of *The Last Honest Meter*, each with the alias set
transcribed from the bible. The gold is partial (it names what the bible names),
so the grader never charges a registry id that matches no gold entity.

Each gold alias string is a **mention**. A mention resolves to the registry ids
whose names or aliases match it (normalized: lowercase, outer space and a
leading article stripped). From that:

- **Coverage:** gold entities with at least one resolved mention, of 28.
- **Fragmentation:** gold entities whose mentions resolve to two or more ids,
  with the ids listed.
- **Fusion:** registry ids that receive mentions of two or more gold entities.
- **Linking P/R/F1:** B³ over the resolved mentions. Recall falls with
  fragmentation, precision with fusion. Unresolved mentions count against
  recall (they are missed links) and are reported by entity.

## What "done" means

1. A grader, `evals/harness/grade_registry.py`, that takes a `registry.json` and
   the gold `ENTITIES` and writes a scorecard (Markdown) plus the numbers
   (JSON). Deterministic, no model call.
2. Unit tests on hand-made registries: perfect, split, fused, missing, and
   article/case variants. They pass, and the full suite stays green.
3. **A first baseline, recorded:** pass-0 run on the story exactly as the
   chapter-test pipeline runs it (same segments, same prompt, the eval model
   shim), **twice**, so the baseline carries a run-to-run noise floor. Both
   registries, both scorecards and a short `REPORT.md` go under
   `evals/results/2026-10-10-r23-pass0-baseline/`.
4. ROADMAP R23 marked done, pointing at the report.

Not in scope: changing pass-0, a second gold book, or the counterfeit-Alice
control (that is R27's, gate g6cee1d).
