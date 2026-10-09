# Whole book → world: prior art for pattern-buffer's ingestion (2026-10-08)

**Question.** What do current (2024–2026) systems do to turn a whole novel into a
faithful, queryable entity/state/time structure fast and cheaply? Which of their
techniques would cut pattern-buffer's whole-book build time and its main
measured failure, identity fragmentation (one person minted as several ids,
pass-0 registry quality)?

**Stopping point (set before starting).** At least 6 systems or papers with
measured results, each tagged ADOPT / ADAPT / REJECT. No implementation.

**Method.** One research helper used alphaXiv and the web, read-only, and nothing
was installed or run. Reviewed by pb. Items marked **[2026 preprint]** are recent
and unreplicated. No technique here has been adopted. This note informs the
vision question "book in, world out — whose job?" (`docs/VISION-DRAFT.md`, Q1).

**Safety pass.** Nothing external enters the codebase. Every technique below that
uses embeddings or vector retrieval is rejected under whitepaper §23.

## Answer

No one has solved end-to-end whole-novel → world-state. The nearest results all
point the way pattern-buffer's registry-first design already goes, and the
strongest evidence on fragmentation comes from book-scale coreference:

- **Roster first, then deterministic linking.** Given a known character list,
  BOOKCOREF's pipeline reaches 80.5 CoNLL-F1 on full books. BookNLP, Longdoc and
  Maverick score 41–47 off the shelf.
- **Book scale fails by fragmentation.** MUC stays above 80 while B3 and CEAF
  collapse. That is the signature `name_collisions` measures.
- **LLMs link well when handed the mentions.** GPT-4 scores 88.4 CoNLL with gold
  mentions and 62.9 when it must also find them.
- **Cheap fixes that need no embeddings are measured:**
  - global propagation of proper-name decisions (+3 CoNLL on long fiction, and
    +5–10 B3 above 20k tokens);
  - cannot-link from coordination ("A and B" are two people);
  - an alias stoplist (kinship and address terms are never merge evidence);
  - an LLM yes/no check on candidate merges in place of a similarity threshold.
- **Build time.** Published whole-screenplay builds on 16 workers take
  2.3–16 min. A ~15 min whole-book build is mid-field. The remaining levers are
  pass-0 serialization and the audit/commit tail.

## Sources

| System / paper | Link | Measured | Verdict |
|---|---|---|---|
| BOOKCOREF (2025) | arXiv 2507.12075 | 80.5 CoNLL with the pipeline on full books vs 41–47 off-shelf; fragmentation signature (MUC > 80, B3/CEAF collapse) | **ADOPT** the shape roster → deterministic explicit-mention linking → local expansion → stitching. **ADAPT** its scoring to grade pass-0 registry quality against gold. **REJECT** its trained models |
| Bourgois & Poibeau, French full-length fiction (2025) | arXiv 2510.15594 | Global proper-name pass: 72.64 → 74.32 CoNLL, +5–10 B3 above 20k tokens | **ADOPT** global-name propagation and cannot-link-from-coordination (deterministic). **REJECT** the trained scorer |
| Hicke & Mimno (2024) | arXiv 2401.17922 | Sentence-level coref, t5-3b CoNLL 88.5; names a prepended entity roster as the missing context | **REJECT** as a dependency. **ADOPT** the conclusion, which is PB's pass-1 roster slice |
| LLM coref, gold vs predicted mentions (via MEIC-DT tables) | arXiv 2512.24711 | GPT-4: 88.4 CoNLL with gold mentions, 62.9 with predicted | **ADOPT** the principle: hand the model candidates to link, never find-and-cluster in one shot |
| KGGen (2025) | arXiv 2502.09956 | MINE: 66.1% vs GraphRAG 47.8%; iterative cluster-then-validate | **ADAPT** a cluster-and-judge sweep over registry names only (a few calls). **ADOPT** a separate validation before any merge |
| iText2KG (2024) | arXiv 2409.03284 | Incremental seed-then-match; with a global roster as relation context, precision drops ~10 pts vs locally matched entities | **REJECT** the cosine merge. **ADAPT** the finding as an A/B of full-registry vs local-slice context in pass-1 |
| EDC (2024) | arXiv 2404.03868 | LLM-verified canonicalization, precision 0.956 vs clustering 0.724 | **ADAPT** for attribute canonicalization: propose, then LLM-verify against definitions, with no vector step |
| LightRAG (2024) | arXiv 2410.05779 | Incremental union; name-keyed dedupe | **ADOPT** incremental union (it fits append-only). **REJECT** vector retrieval |
| GraphRAG (2024) | arXiv 2404.16130 | 600- vs 2400-token chunks: ~2× entity references; "gleaning" (a "what did you miss" re-prompt) recovers the gap; 281 min for ~1M tokens | **ADAPT** gleaning as an alternative to smaller chunks. **REJECT** community summaries and "duplicates are harmless" |
| AriGraph (2024) | arXiv 2407.04363 | Beats full-history and RAG agents in text games; compares new claims only against edges on the same vertices | **ADAPT** the narrow comparison set (PB's fold already derives supersession). **REJECT** LLM-judged staleness and vectors |
| Zep / Graphiti (2025) | arXiv 2501.13956 | Bitemporal KG; entity resolution as candidates then LLM yes/no with "most complete name"; LongMemEval 71.2% vs full context 60.2% | **ADAPT** two-stage resolution with lexical candidates only. **REJECT** embedding candidates |
| Narrative World Model [2026 preprint] | arXiv 2607.05577 | Narrative multi-hop QA 0.898 vs Graphiti 0.574 vs GraphRAG 0.188; a cheaper extractor left Graphiti's accuracy unchanged | **ADOPT** as confirmation that canon at true time plus knowledge rows beats generic edges. Test a cheaper pass-1 model on PB itself |
| NarraWorld [2026 preprint] | arXiv 2609.32401 | Append-only store with per-character belief views; ids minted by the harness, never the model; ~200 calls per story | **ADOPT** "the harness mints ids": pass-0 emits local handles and the merge works over handles |
| ReverieMem / KBF-QA [2026 preprint] | arXiv 2606.25632 | Per-character visibility from scene presence rosters: 73.3 vs best prior 38.7; shared-index RAG refuses out-of-perspective questions only ~10% of the time | **ADAPT** later: derive `knows:` rows from scene presence as `inferred` (needs its own spec; touches provenance) |
| NS-ST-GraphRAG [2026 preprint] | arXiv 2609.05139 | Union-find merge −30% ids; kinship/address terms fused four servants; the model copied an example value into 54/120 chapters | **ADOPT** the alias stoplist, scene co-occurrence before merge, and the example-copy hazard check (re-locate evidence verbatim). Weak evidence: merge accuracy unmeasured |
| Narrative Knowledge Weaver [2026 preprint] | arXiv 2606.05724 | Screenplay build ~10 min on 16 workers (HippoRAG 2.3, GraphRAG 16.3); identity before state | **ADOPT** as a build-time reference point. **REJECT** episode/storyline layers (projections, not log) |
| PDDL-Mind [2026 preprint] | arXiv 2604.17819 | Deterministic transition verification is worth 5–11 pts | **REJECT** for book ingest. The lesson already lives in PB's gate |

## The three techniques most likely to move the numbers

1. **A deterministic alias-index pass between pass-0 and pass-1.** It targets
   fragmentation and costs no model call.
   - Build a normalized alias → entity index from the registry and scan the
     whole text: exact, title+surname and prefix matches.
   - Feed per-chunk hits to INGEST-V2 §4.2's lexical-alias slice rule.
   - Flag aliases that hit more than one entity, and never auto-merge them.
     Apply the kinship/address stoplist.
   - Surface capitalized strings that match no alias as escape candidates
     before pass-1.
   - Raise `distinct_from` *proposals* from coordination and from same-scene
     co-presence.
   - Grade pass-0 against the chapter-test gold roster (linking P/R/F1 plus a
     cluster metric).
2. **Handle-based incremental `extend` with a verified merge gate.** It targets
   fragmentation and removes pass-0's serial chain.
   - Segments emit local handles, and the harness mints the ids.
   - Candidates come by lexical overlap only: name tokens, kind, shared scene.
   - A batched LLM call gives a yes/no per pair, with "most complete name" as
     the canonical choice. Refusals stay separate.
   - Merges land as `same_as` rows, which are reversible, so the gate can start
     precision-first.
3. **Parallel map-reduce pass-0 plus gleaning.** It targets build time.
   - Map segment-local rosters in parallel, then reduce through technique 2's
     gate and technique 1's alias pass.
   - Add one gleaning pass per large chunk before shrinking chunks further.
   - Land techniques 1 and 2 first, because parallel mapping raises
     fragmentation pressure.

## Not verified

- **How the ~15 min splits by stage.** Per-stage timings are needed before
  committing to technique 3.
- **Per-novel build times.** No faithful, frame-aware build reports one.
- **Merge accuracy of union-find.** It is unmeasured in NS-ST.
- **BookNLP, Maverick and LingMess numbers.** They are second-hand, via BOOKCOREF
  and MEIC-DT.
- **FANToM, OpenToM and STAGE.** Not read in primary form.
- **Cost per book.** No source gives a usable dollar or token figure.
