# MERGE-GATE-VERB-V1: the measured merge gate as a report-only engine verb (roadmap R48)

**Status:** r1.1 (2026-10-13), for pbr's spec review. r1.1 adds construct's two report fields (m892d62): a per-call id with a no-cache contract, and the pairs exactly as requested (marked *(r1.1)*). Author: pb.
**Source:** construct asked for it (mba5a02): its build stops when one load-bearing character comes
out under two ids ("Tomas Breck" and "Breck"). cr refused a second, construct-made adjudicator:
a lexical rule can't tell "Breck the baker" from Tomas Breck, and one cheap verdict is a proposal,
not a confirmation. The engine's MERGE-GATE-V1 is that adjudicator, measured on 2026-10-13: no
`same` on any of the gold-different pairs, in both repetitions. It lives in `evals/harness`, which
construct must never import.
**Approval:** gate g9e7f39. The monitor answered for Kabe (note n7fd416): "write and review the
spec … then build it on pbr GREEN … Keep it the smallest verb construct needs: off by default,
the report-only mode (verdicts, no writes) so construct merges itself, and same scoring as the
measured gate. Merge to local main on pbr GREEN code, with construct's suite green on it. No push.
Exit: construct can call it from its build."
**Builds on:** MERGE-GATE-V1 r2.2 (the prompt, envelope, validation, components and election),
CLOSURE-READ-V1 (`distinct_between`), the injected model callable (whitepaper §17.1).

## The verb

```python
porcelain.merge_gate(pairs, *, context=None, batch_size=25) -> dict
```

- **Report-only.** It asks the world's injected model and returns verdicts. It writes nothing:
  no merge, no proposal, no `distinct_from`, no meta row. Construct reads the report and merges
  through `porcelain.merge` itself, with its own receipt checks. There is no `apply` argument.
- **Off by default.** Nothing calls it. `Pipeline`'s own gate stays as it is (`merge_gate=False`
  by default), and the verb adds no automatic path.
- **The model** is the world's injected callable, the one `ask` uses. With no model injected, the
  verb returns `{"status": "no_model"}` and calls nothing.
- **`pairs`**: a non-empty list of two-id lists or tuples. Each id is resolved to its closure's
  served representative. More than 500 pairs, or anything that is not a pair of non-empty
  strings, raises `ValueError` before any read.
- **`context`**: optional, `{id: [sentence, ...]}`, supplied by the host, because the engine holds
  no source text. A key may be any member of a closure. Sentences are taken in key order (sorted
  id), then list order, de-duplicated, and capped at `CONTEXT_SENTENCES` (2) per representative,
  the measured gate's cap. A sentence is any non-empty string, trimmed and cut to 400 characters.
  Without `context`, every side's `context` is `[]`.
- **`batch_size`**: a positive int, default 25, as measured.
- *(r1.1)* **No cache, ever.** Every call asks the model afresh for every asked pair. The verb
  keeps no memo, and reads no earlier report or row of its own (it writes none). So two calls are
  two independent askings, as far as the engine is concerned. Whether the injected model caches
  is the host's business, since the host injects it.

### Which pairs are asked

The asked pairs pass the measured gate's own candidate rules, apart from the lexical one (the
host chose these pairs):
1. Each pair becomes `(a, b)` with `a < b` over the representatives. Duplicates collapse to one.
   The asked pairs are sorted, and numbered `p0001` onward.
2. A pair that is not asked gets a `status` and no verdict:
   - `already_one`: both ids are in one closure;
   - `held_apart`: `distinct_between(a, b)` is non-empty;
   - `class_mismatch`: person against non-person, or event against non-event (r2.2's test, by
     namespace or folded canon kind);
   - `no_names`: either side has no canon `name` or `alias` row (the gate's cards are names).

### The question and the answer: one shared implementation

The prompt, the `merge_gate` schema, the envelope (`{"batch", "pairs"}` with sides
`{id, kind, names, aliases, context}`), `validate_batch` and its statuses (`answered`,
`batch_unparseable`, `missing`, `duplicate`, `bad_verdict`, `bad_keep`), the component rules
(`same` pairs joined, any `different` inside makes it `conflicting_component`), and the
representative election (keep votes, then longest name, then smallest id) move into a new module,
`patternbuffer/merge_gate.py`. The core never imports it; only the porcelain verb does, lazily.

`evals/harness/merge_gate.py` then imports those pieces from the engine module instead of
defining them, and keeps only what is harness-specific: lexical candidates (with the alias index's
stoplist), context from source segments, and `apply_verdicts`' writes. So the measured gate and
the verb are one implementation. The proof is MERGE-GATE-V1's existing tests passing unchanged,
including the byte-identical log and `merge_gate.json` tests.

`read_sides` and `_is_class` move too, as `patternbuffer.merge_gate.read_sides(w, ids=None)`: with
`ids`, only those closures are read. The harness calls it with `ids=None`, so its output is
unchanged.

### The report

```json
{"gate": "merge_gate", "call_id": "<32 hex>", "cached": false,
 "model": "<identity or null>", "batch_size": 25,
 "requested": [["…", "…"]],
 "counts": {"requested": 4, "asked": 3, "not_asked": {"already_one": 1},
            "batches": 1, "verdicts": {"same": 2, "unsure": 1},
            "statuses": {"answered": 3}, "stray": 0, "components": 1,
            "conflicting_components": 0},
 "pairs": [{"pair_id": "p0001", "a": "…", "b": "…", "a_names": […], "b_names": […],
            "verdict": "same", "keep": "a", "keep_id": "…", "reason": "…",
            "status": "answered", "batch": 1, "requested_as": [0, 2]}],
 "not_asked": [{"a": "…", "b": "…", "status": "already_one", "requested_as": [1]}],
 "stray": [], "batch_errors": [],
 "components": [{"members": […], "same_pairs": […], "different_pairs": [],
                 "votes": {"…": 2}, "status": "would_merge", "representative": "…"}]}
```

- A component's `status` is `would_merge` (the measured gate's `applied`, with nothing written)
  or `conflicting_component`, whose `representative` is null.
- A model call that raises leaves its batch `batch_unparseable`, recorded in `batch_errors`,
  and the other batches still run. No retries. The harness's `QuotaExhausted` re-raise stays
  harness-only: the engine re-raises nothing by class name.
- `model` is the injected callable's `identity` or `model_id` attribute, or null.
- *(r1.1)* `call_id` is a fresh `uuid4().hex` for each call. `cached` is always `false`, and it is
  in the report so a host can assert it. `requested` is the `pairs` argument echoed exactly as
  given, each pair as a two-item list. Every asked or not-asked entry lists, in `requested_as`,
  the indexes into `requested` that collapsed into it, so the indexes across all entries cover
  `0 … len(requested)-1` exactly once. A host can therefore check that an answer covers exactly
  the pairs it asked.

### Surfaces

- **Porcelain:** `merge_gate`, documented as reaching the model.
- **Service:** `VIEWER_EXCLUDED["merge_gate"] = "reaches the model"`. A viewer cannot call it.
- **MCP:** not exposed. It joins the MCP wrapper's list of porcelain verbs with no tool, with the
  same reason as `ask`'s exclusion pattern, if the wrapper test requires one. The tool count
  stays 45.
- **Lexicon:** "merge gate": a batched model check that answers same, different or unsure for
  pairs of closures; report-only as an engine verb.
- **Whitepaper:** a decision-record row: the gate ships report-only, and host merges stay the
  host's.

## Tests (the build's acceptance)

1. **Shared implementation.** `tests/test_merge_gate.py` passes unchanged, every test, including
   the byte-identical log and report tests and the pinned candidate counts (65/77/73/228/208).
2. **Report-only.** On a world with a scripted model answering `same` for every pair, the log's
   head and row count are identical before and after the call.
3. **Not asked:** one pair of each status (`already_one`, `held_apart`, `class_mismatch` both
   ways, `no_names`) is reported and never reaches the model.
4. **Canonicalization:** `(b, a)`, `(a, b)` and a member-id spelling of the same pair are asked
   once, as `p0001`, with `a < b` by representative.
5. **Context:** member-keyed sentences land on the representative, capped at 2 and trimmed; the
   model's request carries them; with no `context`, every side's context is `[]`.
6. **Same envelope as the harness.** For a given world and pairs, the verb's request for batch 1
   equals the harness's `build_batches` request for the same pairs and the same per-id context.
7. **Components:** two `same` pairs sharing an id make one `would_merge` component with the
   elected representative (pass mark 7's vote case reused). One `different` inside makes it
   `conflicting_component`.
8. **Failures:** a model that raises on batch 1 of 2 leaves batch 1's pairs `batch_unparseable`
   and batch 2 answered. No model injected gives `no_model`, and the scripted model is never
   called.
9. *(r1.1)* **Call identity and coverage:** two calls on the same pairs give different
   `call_id`s, both with `cached: false`, and the scripted model is called anew by the second.
   The `requested_as` indexes cover every requested index exactly once, including the duplicates
   and the not-asked pairs.
10. **Bad input:** an empty list, more than 500 pairs, a non-string id, `batch_size=0` or `True`
   each raise `ValueError` before any model call.
11. **Viewer walk:** `merge_gate` is in `VIEWER_EXCLUDED`, and the existing classification walk
    passes.
12. **Construct:** construct's full suite passes against the merged engine (the monitor's
    condition), run by construct on its side, with the result reported back before the merge
    is called done.

## Not in this spec

- An `apply` mode, or any write. Construct merges itself.
- Lexical candidate finding in the engine. The host names the pairs.
- MCP exposure.
- Any change to the measured gate's behaviour.
