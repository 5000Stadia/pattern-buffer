# SOURCE-IDENTITY-V1 — a source class is a source, not a category — r2.1

**Status:** r2.1 — **code GREEN** (pbr `<1766884f…>` at `236cc3c`); r2's sole
spec blocker was a stale §2.1 paragraph still prescribing the rejected
lexicographic tiebreak, contradicting §2.2(b), the implementation and the
rewritten oracles. r2.1 is that amendment only — **no code change**. pbr's
rulings: identity-closure canonicalization GREEN, the composite class ACCEPTED
(explicitly "keep it; do not switch to gate rejection"), conflict-parties-vs-
served-value GREEN, and `corroborated_by` to be left exactly as r2 has it.

Earlier lineage: r2 DRAFT → pbr (re-review after r1.1 RED). r1.1 landed on `main` as
`328ec7e` under founder direction ahead of any pbr verdict; pbr then returned
**RED on both spec (`<8b7ef3c6…>`) and code (`<c4111100…>`)** with three contract
gaps, all of which **pb reproduced against shipped code before repairing**. The
primary `document:<identity>` direction, the CONFIDENCE prose repair, `doc:`-over-
`person:` precedence, §6 scoping, and the flag→tmaint-sidecar→host-ask boundary
were all confirmed sound and are unchanged. r2 repairs only the three gaps (§2.2).

Originating evidence: `pbeo`'s TAKE-BACK (`<23084b48…>`, 2026-07-28) flagged the
corroboration face of this defect. pb probing found the root cause and a second,
more severe face in the fold algebra.

## 1. The defect

`Indexes._source_class` (`indexes.py:154-177`) maps an assertion to a **source
class**. That class is the unit of two separate contracts:

1. **Fold / supersession (§7.2).** `_fold_rows` groups rows `by_source`
   (`indexes.py:838-840`). *Within* a class, later `valid_from` supersedes.
   *Across* classes, disagreement raises the truth-maintenance flag and an ask.
2. **Corroboration (CONFIDENCE-V1 §2).** `corroboration = len(set of source
   classes agreeing) - 1` (`indexes.py:559`).

For speakers the class carries identity — `f"speaker:{m.value}"`, so
`speaker:person:ana` ≠ `speaker:person:bo`. **For documents it does not**: every
`doc:` source collapses to the bare literal `"document"` (`indexes.py:167`),
discarding *which* document.

The function's own comment states the equivalence its implementation breaks:

> Speaker-source class (027 Decision 2): **a speaker is a document that talks** —
> same speaker supersedes self, speakers disagreeing cross-source flag + ask (§7.2).

A speaker is a document that talks — but only the talking one kept its name.

### 1.1 Face A — §7.2 is violated (the severe one)

Whitepaper §7.2: *"Supersession-by-key is automatic only within a source class.
Conflicting observations from different source classes on the same key raise a
truth-maintenance flag and an ask […] **never a silent last-write-wins**."*

Two distinct documents disagreeing are one class today, so they silently
last-write-wins. Measured on shipped code (`order:8841 · count`, both
`observed`, sources `doc:supply_house`=20 then `doc:invoice`=12):

| case | `conflicted` | served |
|---|---|---|
| `doc:supply_house`(20) vs `doc:invoice`(12) | **`False`** | 12 (silent LWW) |
| `person:ana`(20) vs `person:bo`(12) — control | `True` | 20 + flag |
| `doc:invoice`(20) then `doc:invoice`(12) — control | `False` | 12 (correct supersession) |

The failing row is **§7.2's own worked example** — *"supply house says 20 arrived
Thursday — did that order actually land?"* The whitepaper illustrates the
contract with the exact case the code gets wrong.

### 1.2 Face B — corroboration undercount

N distinct documents independently agreeing score identically to one document
quoted N times, and identically to a single uncorroborated row. Measured:

| agreeing rows | `corroboration` | `score` |
|---|---|---|
| 1 row, no source | 0 | 0.750 |
| `doc:manual` + `doc:logbook` (independent) | **0** | **0.750** |
| `doc:a` + `doc:b` + `doc:c` (independent) | **0** | **0.750** |
| `doc:manual` + `doc:manual` (true echo) | 0 | 0.750 |
| `person:ana` + `person:bo` — control | 1 | 0.858 |
| `person:ana` + `person:ana` — control | 0 | 0.750 |

Three independent documents agreeing earn exactly nothing.

## 2. The change

One rule: **a document's class carries its identity, exactly as a speaker's
does.**

```python
if isinstance(m.value, str) and m.value.startswith("doc:"):
    return f"document:{m.value}"
```

That is the primary semantic change; §2.2 adds the three r2 repairs on top,
of which (b) supersedes r1.1's multi-source tiebreak. It restores the symmetry the function's own
comment asserts, and both faces close together because both read the same class.

### 2.1 Secondary: multi-source rows are order-dependent (pinned, not left)

The `for m in metas` loop returns on the first `doc:`-or-`person:` match, so a
row carrying **both** a `doc:` and a `person:` source classifies by whichever
`visible()` happens to return first. That is a live nondeterminism in a
load-bearing key.

**Pin: `doc:` sources take precedence over `person:` sources**, evaluated over
the full meta set rather than the first match. Rationale — §7.1's chain is
two-hop (*the story observed the letter; the letter claims the facts*); the
document is the outer, more specific evidentiary artifact, and a person named
alongside it is the attributed voice *within* that artifact.

**The same rule applies to both kinds.** Where several sources of the winning
kind sit on one row, the class is the **canonical composite of all of them** —
see §2.2(b) for the rule and its rationale — and nothing is receipted; a
multi-source single row is a writer choice, not an engine fault.

> **r2 correction.** r1/r1.1 pinned this as *"take the lexicographically
> least"*. That was rejected: selecting one attester by label spelling made
> evidentiary identity depend on sort order, and pbr reproduced identical
> provenance topology producing opposite outcomes under renaming. §2.2(b) is
> the normative rule; this paragraph previously contradicted it, which was the
> sole spec blocker on r2's code-GREEN. The r1.1 note — that whatever rule
> applies must apply to **both** kinds, not documents only — survives intact
> and is now satisfied by the composite.

This changes classification only for rows carrying more than one source, which
no shipped test exercised before r1.1.

## 2.2 r2 repairs — pbr's three RED findings

All three were reproduced on shipped code first, then fixed.

### (a) Source IDs are canonicalized through the identity closure

Raw source strings are not source *identities*. Write `doc:manual` and
`doc:manual_alias`, merge them afterwards, and un-canonicalized classes stay
distinct — **one logical document then self-corroborates.** Measured on r1.1:
corroboration stayed `1` across the merge; it must fall to `0`.

Collected `doc:`/`person:` ids now pass through `self._resolve` (current-head
closure, consistent with the engine's known historical-identity limitation).
**This gap was introduced by r1.1** — before it, every document collapsed to one
class, so aliases were handled correctly by accident. Oracle 14.

### (b) The class is a canonical COMPOSITE, never one member selected by spelling

r1.1's `min()` was deterministic but not semantic. pbr reproduced, and pb
confirmed, that identical two-row provenance topology flipped outcome purely on
renaming the shared source:

| shared source sorts | r1.1 result |
|---|---|
| lexically least | `conflicted=False`, served `'new'` |
| lexically greatest | `conflicted=True`, served `'old'` |

**Spelling decided which value was served.** A set of attesters is its own
identity, so the class is now every source of the winning kind, canonically
rendered: `document:` + `"|".join(sorted(ids))`. Sorting canonicalizes the
*rendering* only; it never selects an attester. A single-source row is
unchanged (`document:doc:x`, `speaker:person:x`). Oracle 15.

### (c) Conflict parties are recomputed against the final serving value

`serving` advances on refinement, but `conflicting` was anchored permanently to
`incumbent` (`indexes.py`). With `a={gte:10}`, `b=12`, `c=13` the fold served `b`
and reported `conflicting={a,c}` — **a pair that agrees** — while the real
incompatibility was `b↔c`. `TruthMaintenance.scan()` persisted the same wrong
pair, so the durable `cross_source` sidecar named the wrong evidence. This bug
**pre-dates this spec**; document-splitting makes the three-document shape newly
reachable, which is why it lands here. Oracle 16.

Two pins on the repair:

- **Compatibility is symmetric.** `_values_agree(old, new)` asks the directional
  question "does `new` refine `old`?", so `_values_agree({gte:10}, 12)` holds
  while the reverse does not. The recomputation asks a symmetric question and
  must test both directions, or an approximate row the served value satisfies is
  reported as a conflicting party.
- **`corroborated_by` keeps its existing meaning exactly — pbr ruled this
  settled (`<1766884f…>`), and for a stronger reason than the one that stayed
  my hand.** I reverted the change because it broke a shipped test and was an
  unasked widening. pbr's ruling is that the test encodes a deliberate
  contract: CONFIDENCE-V1 defines corroboration as **strict same-value**
  evidence, and `test_confidence.py::test_corroboration_is_strict_not_approximate`
  pins that a `{gte}` bound must NOT corroborate a precise value. So the
  resulting `corroboration: 0` on a two-row refinement pair is **intended, not
  an undercount**, and recomputing against the served value would have silently
  violated that contract rather than merely changed a tuple. The self-reference
  (winner listed among its own corroborators) is acknowledged as awkward
  *representation*; if it is ever cleaned up, the direction is to decouple
  refinement/convergence lineage from strict-value confidence — never to
  redefine this tuple in place. Original wording follows: — the challengers that
  agreed as the fold advanced, pinned by
  `test_fold.py::TestCrossSource::test_agreeing_value_corroborates`. An earlier
  draft of this repair recomputed corroboration against the final serving value
  too; that broke the shipped test and is an unasked contract change, so it was
  reverted. **Flagged for pbr rather than taken:** the old semantics can list the
  winner as its own corroborator, and `confidence()` unions the winner's class
  with `corroborated_by`'s classes — so a two-row refinement pair may undercount.
  That is a separate question, not folded in here.

## 3. What does NOT change

- **No log change, no migration, no stored value.** `_source_class` is a
  read-layer derivation; every world re-derives on next read (derive-don't-store).
- **No payload shape change.** Source classes are never serialized — not in
  `confidence()` (which exposes only the integer `corroboration`), not in
  `state()`, not on the wire. `document:doc:x` is an internal key only.
- **Speaker classification keeps its `speaker:person:…` string form**, and a
  single-speaker row classifies exactly as before. Symmetry is achieved by
  lifting documents to match speakers, never by lowering speakers. (The one
  speaker-visible change is §2.1's multi-speaker determinism.)
- **Same-document supersession is untouched** — one document correcting itself
  stays one class, still supersedes, still does not flag.
- **Non-`observed`/`stated` statuses** still classify by raw status; the
  evidence-rank quarantine (`indexes.py:834`) is untouched.
- **`direct` still pools.** See §6 — deliberately out of scope, not overlooked.

## 4. Oracles

Fold / §7.2:

1. Two distinct `doc:` sources disagreeing on one key → `conflicted=True`,
   `conflicting` names both rows, winner is **earliest-asserted** among the tied
   set (never last-write-wins). *Currently fails.*
2. One `doc:` source correcting itself (same id, later `valid_from`) →
   `conflicted=False`, later value served. *Currently passes; must stay.*
3. A `doc:` and a `person:` source disagreeing → `conflicted=True` (distinct
   classes both before and after).
4. Distinct `doc:` sources **agreeing** → `conflicted=False`; agreement across
   classes is corroboration, never conflict.
5. Containment keys: distinct-document movement stays time-sequential —
   latest-valid move wins across classes, only a same-`valid_from` disagreement
   flags (`is_containment` branch preserved).

Corroboration:

6. `doc:a` + `doc:b` agreeing → `corroboration == 1`. *Currently 0.*
7. `doc:a` + `doc:b` + `doc:c` agreeing → `corroboration == 2`. *Currently 0.*
8. `doc:a` + `doc:a` (echo) → `corroboration == 0`. *Currently 0; must stay.*
9. Speaker controls (`person:ana`+`person:bo` → 1; same speaker → 0) unchanged.
10. Frame-scoped: the multiframe union path (`indexes.py:672-700`) counts the
    same identities, and a deduped single-frame list still reduces to the `str`
    path byte-for-byte (CONFIDENCE-MULTIFRAME-V1's invariant holds).

Determinism (§2.1):

11. A row with both `doc:d` and `person:p` sources classifies `document:doc:d`
    regardless of meta insertion order — assert both orderings.
12. A row with `doc:b` and `doc:a` classifies `document:doc:a` (lexicographic
    least), both insertion orders.
12a. A row with `person:b` and `person:a` classifies `speaker:person:a`, both
    insertion orders (the r1.1 symmetry — same rule, both kinds).

No-degradation:

13. Full suite green + the new oracles. Any pre-existing test that changes
    verdict is a finding to report, **not** a test to edit — a shipped test
    asserting silent cross-document LWW would be asserting the violation.

### 4.1 Measured (r1.1 implementation)

Run on the `corroboration-source-identity` worktree (clean off `86ce3f4`), so
counts are lower than the founder tree's 536 — the uncommitted MOVED/ATOMIC
suites are not present here.

| run | result |
|---|---|
| clean `86ce3f4`, without this change | 481 passed, **1 failed** |
| with SOURCE-IDENTITY-V1 + 18 new oracles | 499 passed, **1 failed** |

`481 + 18 = 499`. **Zero pre-existing tests changed verdict.**

The single failure is `test_mcp_wrapper.py::test_stdio_initialize_list_call_shutdown`
(a verb-count assertion), and it is **pre-existing and unrelated** — reproduced
on the stashed clean tree at `86ce3f4` before this change. It is stale only in
the *committed* tree: the founder's working tree carries the uncommitted
ATOMIC-ACTIVATION work that registers `commit_set` as the 39th verb. Nothing
here touches MCP. Reported, not fixed, not absorbed.

Counter-check: the 18 oracles were also run against **pre-change** code and 10
fail there (O1, O6, O7, O10, O11×2, O12×2, O12a×2). They test the change, not
themselves.

## 5. Spec-text repair (CONFIDENCE-V1)

CONFIDENCE-V1 §2 currently defines corroboration as *"a de-duplicated count of
**independent** agreeing source classes"*. It counts **distinctly-classed**
agreeing sources. `pbeo`'s framing is correct and is the reason to touch the
prose: **the term promises more than the definition delivers** — a definition
whose name is wider than the thing behind it.

After §2 the count is over distinct source *identities*, which is materially
closer to independence but still not independence (see §6). Amend CONFIDENCE-V1
to say what it does: *"a de-duplicated count of distinct agreeing **source
identities** (`_source_class` values). Distinct identity is not proof of
independent origin — undeclared-origin rows are pooled (§6) and the engine holds
no attribution graph."* LEXICON's `confidence()` entry gets the same correction.

The implementation was faithful to its spec; patching `indexes.py` against the
old wording would have put code in conflict with a SHIPPED Codex-GREEN spec on
the strength of an outside reading. The prose moves with the code, in one change.

## 6. Deliberately out of scope — the undeclared-origin pool (**founder call**)

Rows that are `observed`/`stated` with **no** `source` meta all classify
`direct`. So N independent sensor readings agreeing score `corroboration == 0`
(measured: 1, 2, and 4 agreeing rows all score 0.750). `pbeo`'s flag 2 is that
mutual dependence is a plant's *default* — sensor polling sensor, a controller
echoing a setpoint — so this is the dominant tracking-mode shape, and the metric
is blindest to exactly it.

**This spec does not touch it, because the repair is a genuine crossroads and
both directions are wrong in opposite ways:**

- **Keep pooling** (status quo) — undercounts. In fiction it is *correct*: the
  narration is one narrator, not N witnesses.
- **Per-row origin** — each undeclared row its own origin. Fixes tracking, but
  systematically **overcounts** in precisely the echo-dense domain pbeo warns
  about, manufacturing confidence from undeclared echoes.

The honest third option is that undeclared origin means *unknown* independence —
neither corroborating nor proven-dependent — which argues for surfacing the gap
in the payload rather than picking a number, and connects to pbeo's flag 3
(**an assertion that originated a claim legitimately carries no attribution
edge; conflating "I originated this" with "I did not say" is the error**).
Choosing among these is a founder disposition on pbeo's take-back, plausibly
mode-scoped the way TRACKING-MODE-V1 made recency mode-scoped. It is recorded
here so the boundary of this spec is deliberate and visible.

## 7. Non-goals

- No attribution graph, no `justified_by` activation, no citation chains.
- No weight retuning; `CONFIDENCE_PARAMS` values are untouched.
- No new public read, no new vocabulary, no MCP surface change.
