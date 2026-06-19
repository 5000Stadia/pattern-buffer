# CLASSIFIER-EVENT-SAFETY-V1 — the model may not assign the erasing class

**Status:** DRAFT → Cx GREEN before implementation. P1 correctness fix (Construct
059/060). Small, surgical change to the durability classifier.

## Problem (localized, confirmed)
The durability classifier asks the injected model to choose among
`{CONSTITUTIVE, DISPOSITIONAL, STATE, EVENT}` for any row the deterministic
guardrails leave ambiguous. **EVENT is uniquely destructive:** an EVENT row is
excluded from every fold (`fold_key` drops `durability == EVENT`), so it vanishes
from `state`/`current_state`/`materialize` while remaining in `all_rows()`.

At `anchor` scale the model nondeterministically classified a **standing, timeless,
literal arc row** — `clock:refusal · rung = "refusal"` — as EVENT (it reads
"rung refusal" as an occurrence), silently erasing it from reads. Value-correlated
(`rung="surface"` folds fine) and per-seal because it's model sampling variance.
This is a **silent read-completeness failure** — the worst class for a substrate
whose core promise is "served state never contradicts the buffer."

## Principle
The classifier already states an asymmetric-cost doctrine: *ambiguous → STATE; a
transient mistaken for structure decays, structure mistaken for transient is
flagged on contradiction — never silently erase.* Letting the model assign EVENT
violates it: EVENT is the one verdict that erases rather than degrades. And
**whether a row is an occurrence vs a standing fact is structural, not a per-row
judgment the model should sample** — events in this substrate are carried by
structure (`event:` entities, `caused_by` edges) or host declaration, per P6.

## The change
**The model may judge only the standing-durability spectrum
`{CONSTITUTIVE, DISPOSITIONAL, STATE}`. EVENT becomes deterministic-only.**
Applied to **BOTH** model paths — the per-row `_ask_model` *and* the batch
`_classify_batch` (Cx 062: the anchor/chapter scale path sets
`classify_inline=False` and goes through batch, which had its own EVENT-allowing
schema — the actual failure path).

1. `classify.py`: add `_STANDING_DURABILITIES = frozenset({CONSTITUTIVE,
   DISPOSITIONAL, STATE})` — defined once, used in both paths.
2. **Per-row:** `_MODEL_SCHEMA` `durability` enum → `sorted(_STANDING_DURABILITIES)`;
   `_ask_model` validation rejects a verdict not in `_STANDING_DURABILITIES`;
   drop the EVENT line from the prompt.
3. **Batch:** the `_classify_batch` schema enum → `sorted(_STANDING_DURABILITIES)`;
   the per-verdict acceptance check (`v["durability"] in DURABILITIES`) →
   `in _STANDING_DURABILITIES` (an EVENT verdict is rejected → falls to the
   existing `verdicts.get(i, default)` asymmetric default: containment →
   CONSTITUTIVE, else STATE — identical to `_ask_model`); drop the EVENT line from
   the batch prompt.
4. **Guardrails unchanged** — EVENT is still assigned deterministically by
   `_guardrails`: `event:`-prefixed entities, `caused_by`, `META_ATTRIBUTES`
   (the immutable-meta EVENT-like marker). Host event/structural declarations
   continue to short-circuit before the model. `Classifier.set()` (judgment
   injection) and `DURABILITIES` (the fold's universe) keep EVENT — only the
   *model's* assignable set narrows.
5. **Whitepaper amendment (Cx 062):** `docs/WHITEPAPER.md` currently says
   past-perfective-with-agent can signal EVENT in the classifier. Amend that line:
   occurrence-ness is **structural** (`event:` / `caused_by` / host declaration);
   the model judges only standing durability. (Whitepaper wins until amended — so
   this amendment is part of the change, not a doc-drift afterthought.)

Net: a standing row the host hasn't declared can no longer be *erased* by a model
flip — worst case it folds as STATE (visible, correctable). Events that are
actually structured stay EVENT.

## Non-goals / unchanged
- Does **not** change how genuine events are represented or detected (`event:` /
  `caused_by` / structural declaration). The eval EVENTS check (battery verdict 29)
  reads `caused_by` edges, not model-flat-EVENT — no regression.
- Does **not** touch the host's `structural` declaration path — that remains the
  way a host pins a known-durable attribute (and is the immediate unblock for
  `anchor`; this engine fix is the backstop for *undeclared* attrs).
- No porcelain/read surface change.

## Tests (tests/test_classifier_event_safety.py)
1. **Per-row:** a standing ambiguous row, model returns EVENT, `classify_inline`
   → classifies **STATE** and **folds** (the `rung="refusal"` repro: served by
   `state`/`materialize`).
2. **Batch (Cx 062, the scale path):** same row via `classify_all(batch_size=…)`
   with a model returning EVENT → **STATE** and folds. This is the path anchor uses.
3. `event:`-prefixed entity row → still EVENT (guardrail), both paths.
4. `caused_by` row → still EVENT (guardrail).
5. A `structural`-declared attribute → CONSTITUTIVE, model never consulted.
6. Both model schemas (`_MODEL_SCHEMA` and the `_classify_batch` schema) exclude
   `EVENT` from the `durability` enum.
7. Full suite green (no eval/classification regression).
