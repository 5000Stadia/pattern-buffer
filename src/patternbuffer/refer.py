"""refer(): reference resolution, the fourth boundary operation
(whitepaper §9; spec §9.3). Three-tier cascade, cheapest first; tier 1
is deterministic and makes no model call. Low confidence never guesses.

refer learns a word, never a pick (REFER-LEARNING-V1 §1; whitepaper A18).
Only a vocabulary miss that tier 2 maps onto one entity in scope writes,
and what it writes is a `learned_alias` row in the call's frame. Tier 1d
reads it back only after the world's own vocabulary found nothing, and
only where its entity is in the caller's scope.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from patternbuffer.buffer import PatternBuffer
from patternbuffer.identity import REFER_SOURCE_PREFIX, IdentityRegistry, ref_norm
from patternbuffer.indexes import Indexes
from patternbuffer.model import ATTR_PREFIX, CANON, TASK_REFER, task_schema

logger = logging.getLogger(__name__)

RESOLVED = "resolved"
CANDIDATES = "candidates"
UNDERDETERMINED = "underdetermined"

_TIER2_SCHEMA = {
    "title": TASK_REFER,
    "type": "object",
    "properties": {
        "entity_id": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
        "signals": {"type": "array", "items": {"type": "string"}},
    },
    # No required fields (HD 081): "no match" is a FIRST-CLASS outcome — a
    # genuinely unresolvable reference (off-script/willy-nilly play) lets the
    # model omit `entity_id` entirely rather than violate a required field and
    # burn a re-ask. The consumer is fully `.get`-defended and treats a
    # missing/null entity_id (or sub-floor confidence) as UNDERDETERMINED
    # ("nothing here" — the host's ask), never an error.
    "required": [],
}
_TIER2_FLOOR = 0.75

# Leading determiners stripped before reference resolution (HD 003): a
# possessive or article in front of a referring expression is surface
# grammar, not identity ("my brass measuring spoon" is the spoon).
_DETERMINERS = frozenset(
    {"the", "a", "an", "my", "your", "his", "her", "its", "their", "our"}
)


@dataclass(frozen=True, slots=True)
class Resolution:
    status: str
    entity_id: str | None = None
    candidates: tuple[str, ...] = ()
    receipt: dict = field(default_factory=dict)  # tier, signals, confidence


class Refer:
    def __init__(
        self,
        buffer: PatternBuffer,
        indexes: Indexes,
        registry: IdentityRegistry,
        model: Callable[[str, dict], Any] | None = None,
        ingestor: "Any | None" = None,
    ) -> None:
        self._buffer = buffer
        self._indexes = indexes
        self._registry = registry
        self._model = model
        # Word learning (letter 018 mechanic 2, as REFER-LEARNING-V1 §2
        # reshapes it) writes through the gate; without an ingestor wired,
        # resolution still works but the world learns no words.
        self._ingestor = ingestor

    def _learn(self, description: str, entity_id: str, receipt: dict, frame: str) -> None:
        """Remember a word (REFER-LEARNING-V1 §2): the expression, normalized,
        names `entity_id` in `frame`. One timeless, inferred `learned_alias`
        item through the gate, whose `source_doc` makes the gate write the
        `source` receipt. The word passes the membrane — its input, the user's
        expression, is in no other row — while the pick, the scope and any
        lifetime are recomputable or the host's, so none of them is stored."""
        if self._ingestor is None:
            return
        word = ref_norm(description)
        if self._knows_word(word, entity_id, frame):
            # Written once (§2). At the head the cascade cannot get here — an
            # in-scope word is a tier-1d hit — so this is a guard, not a path.
            return
        rows = self._ingestor.ingest_structured(
            [{"entity": entity_id, "attribute": "learned_alias", "value": word,
              "timeless": True, "status": "inferred", "frame": frame,
              "source_doc": REFER_SOURCE_PREFIX
              + json.dumps(receipt.get("signals", []))[:80]}],
            # §2: the META guardrail decides it EVENT with no model call;
            # rules mode decides it even inside a deferred build session.
            classify="rules",
        )
        if not rows:
            # §2: a gate skip is not an error; the resolution stands.
            logger.warning("learned alias not written (gate skip): %r -> %s in %s",
                           word, entity_id, frame)
            return
        logger.info("learned alias: %r -> %s in %s", word, entity_id, frame)

    def _knows_word(self, word: str, entity_id: str, frame: str) -> bool:
        """A visible `learned_alias` in `frame` already maps `word` to
        `entity_id`'s identity (REFER-LEARNING-V1 §2)."""
        target = self._indexes.resolve_entity(entity_id)
        return any(
            isinstance(row.value, str) and ref_norm(row.value) == word
            and self._indexes.resolve_entity(row.entity) == target
            for row in self._buffer.visible(attribute="learned_alias", frame=frame)
        )

    def __call__(
        self,
        description: str,
        scope: str | list[str] | None = None,
        frame: str = CANON,
        constraints: list[tuple[str, str]] | None = None,
        as_of: float | None = None,
        asserted_as_of: int | None = None,
        learn: bool = True,
    ) -> Resolution:
        """Resolve a referring expression to one entity, a candidate set, or
        underdetermined (whitepaper §9).

        Tier 1 makes no model call: (1a) an authored name or alias; (1b)
        constraint inversion; (1c) the one entity of the named kind in scope;
        (1d) a word refer learned earlier, its entity in scope
        (REFER-LEARNING-V1 §3). Tier 2 judges two or more tier-1 candidates,
        or, given a `scope`, a vocabulary miss over the scene's members
        (letter 018). Below its floor the reference is underdetermined: the
        host's ask.

        `learn` (REFER-LEARNING-V1 §2): a vocabulary miss that tier 2 maps
        onto one entity is remembered as a word, a `learned_alias` row in
        `frame`, unless `learn=False` or the read is pinned to a past log
        position (`asserted_as_of`). No other path writes: an ambiguity pick
        is never learned.
        """
        # The scene's members, computed at most once per call: tier 1c, tier
        # 1d's scope filter and the escalation share it (REFER-LEARNING-V1 §3).
        scene: list[str] | None = None

        def members() -> list[str]:
            nonlocal scene
            if scene is None:
                scene = self._scope_members(scope, frame, as_of, asserted_as_of)
            return scene

        # ---- Tier 1a: exact name/alias hit through the identity registry.
        # Try the raw expression and its determiner-stripped core (HD 003):
        # "my brass measuring spoon" misses the exact name otherwise. Read as
        # of the caller's log position (REFER-LEARNING-V1 §4); the frame half
        # of this read is FRAME-SCOPED-IDENTITY-V1 §2's, at the registry's one
        # vocabulary read set, which tier 1d shares.
        core = self._strip_determiner(description)
        texts = (description,) if core == ref_norm(description) else (description, core)
        hits = {e for text in texts
                for e in self._registry.by_alias(text, asserted_as_of, frame=frame)}
        if len(hits) == 1:
            return Resolution(RESOLVED, next(iter(hits)),
                              receipt={"tier": 1, "signals": ["alias_exact"]})

        # ---- Tier 1b: constraint inversion — resolve the container by the
        # contained, the owner by the possession. Flip the lookup before
        # any linguistic judgment.
        if constraints:
            inverted = self._invert(constraints, frame, as_of, asserted_as_of)
            if inverted is not None:
                return inverted

        # ---- Tier 1c: unique-kind-in-scope ("the drawer" where the scene
        # holds exactly one drawer).
        kind = self._kind_word(description)
        if kind is not None:
            of_kind = [
                e for e in members()
                if self._entity_kind(e, frame, as_of, asserted_as_of) == kind
            ]
            if len(of_kind) == 1:
                return Resolution(RESOLVED, of_kind[0],
                                  receipt={"tier": 1, "signals": ["unique_kind_in_scope"]})
            if len(of_kind) > 1:
                # A kind pick: judged afresh on every read, never learned (§2).
                return self._resolve_tier2(description, tuple(sorted(of_kind)))
        if len(hits) > 1:
            # An authored-alias collision: judged, never learned (§2).
            return self._resolve_tier2(description, tuple(sorted(hits)))

        # ---- Tier 1d (REFER-LEARNING-V1 §3): a learned word, read back only
        # on a vocabulary miss — names, aliases and a unique kind in scope all
        # found nothing (one alias hit returned above; two or more went to
        # tier 2) — and only where its entity is in the caller's scope. With
        # no scope the whole world is the scene.
        learned = {e for text in texts
                   for e in self._registry.by_learned_alias(text, asserted_as_of, frame=frame)}
        if scope is not None:
            in_scene = set(members())
            learned = {e for e in learned if self._indexes.resolve_entity(e) in in_scene}
        if len(learned) == 1:
            return Resolution(RESOLVED, next(iter(learned)),
                              receipt={"tier": 1, "signals": ["learned_alias"]})
        if len(learned) > 1:
            # A learned-word collision: judged, never learned (§2).
            return self._resolve_tier2(description, tuple(sorted(learned)))

        # ---- Zero-candidate escalation (letter 018, mechanic 1): a synonym
        # yields zero tier-1 matches; with a scope provided, that is exactly
        # tier 2's judgment — vocabulary miss must not masquerade as absence.
        # Scope-bounded ONLY: never world-scope for this path. The one path
        # that learns (REFER-LEARNING-V1 §2), and never from a pinned read.
        if scope is not None and members():
            learn_frame = frame if learn and asserted_as_of is None else None
            return self._resolve_tier2(description, tuple(sorted(members())),
                                       learn_frame=learn_frame)

        # Nothing deterministic and no candidates: underdetermined.
        return Resolution(UNDERDETERMINED, receipt={"tier": 3, "signals": []})

    # ------------------------------------------------------------- tier 1

    def _invert(self, constraints, frame, as_of, asserted_as_of) -> Resolution | None:
        for relation, anchor in constraints:
            if relation == "contains":
                chain = self._indexes.locate(anchor, frame, as_of, asserted_as_of)
                if chain:
                    return Resolution(
                        RESOLVED, chain[0],
                        receipt={"tier": 1, "signals": [f"constraint_inversion:contains({anchor})"]},
                    )
            elif relation == "owned_by" or relation == "held_by":
                # The owner by the possession is the anchor's own owned_by key
                # (REFER-LEARNING-V1 §6), not its container; held_by folds the
                # containment family (unchanged). No entity winner: no answer.
                key = "owned_by" if relation == "owned_by" else "in"
                folded = self._indexes.fold_key(anchor, key, frame, as_of, asserted_as_of)
                if folded.winner is not None and folded.winner.value_type == "entity":
                    return Resolution(
                        RESOLVED, self._indexes.resolve_entity(folded.winner.value),
                        receipt={"tier": 1, "signals": [f"constraint_inversion:{relation}({anchor})"]},
                    )
        return None

    @staticmethod
    def _strip_determiner(description: str) -> str:
        """Lowercase and drop a single leading article/possessive token
        (HD 003). A no-determiner phrase passes through unchanged."""
        text = description.strip().lower()
        head, _, rest = text.partition(" ")
        if head in _DETERMINERS and rest:
            return rest.strip()
        return text

    def _kind_word(self, description: str) -> str | None:
        """A bare kind reference ("the drawer", "my spoon") → the kind
        token. Accepts an optional leading article or possessive (HD 003);
        broadening only adds matches, so "the X" still parses identically."""
        det = "|".join(sorted(_DETERMINERS))
        m = re.match(rf"^(?:{det})\s+([a-z][a-z_ ]*)$", description.strip().lower())
        return m.group(1).replace(" ", "_") if m else None

    def _scope_members(self, scope, frame, as_of, asserted_as_of) -> list[str]:
        if scope is None:
            # World scope: every entity with a kind row.
            return sorted(
                {
                    self._indexes.resolve_entity(r.entity)
                    for r in self._buffer.visible(
                        attribute="kind", frame=frame,
                        valid_as_of=as_of, asserted_as_of=asserted_as_of,
                    )
                    if not r.entity.startswith("a:")
                    and not r.entity.startswith(ATTR_PREFIX)
                }
            )
        roots = [scope] if isinstance(scope, str) else list(scope)
        members: set[str] = set()
        frontier = [self._indexes.resolve_entity(r) for r in roots]
        seen: set[str] = set()
        while frontier:
            e = frontier.pop(0)
            if e in seen:
                continue
            seen.add(e)
            members.add(e)
            frontier.extend(self._indexes.contents(e, frame, as_of, asserted_as_of))
        return sorted(members)

    def _entity_kind(self, entity, frame, as_of, asserted_as_of) -> str | None:
        result = self._indexes.fold_key(entity, "kind", frame, as_of, asserted_as_of)
        return result.winner.value if result.winner else None

    # ------------------------------------------------------------- tier 2

    def _resolve_tier2(
        self, description: str, candidates: tuple[str, ...],
        learn_frame: str | None = None,
    ) -> Resolution:
        """Strict-contract cheap call judging candidates; returns a
        resolution receipt. Below the floor -> tier 3: never guess.

        `learn_frame` is the frame a confident answer is learned into as a
        word. Only the zero-candidate escalation passes one
        (REFER-LEARNING-V1 §2); None never writes."""
        if self._model is None:
            return Resolution(CANDIDATES, candidates=candidates,
                              receipt={"tier": 2, "signals": ["no_model"]})
        prompt = (
            f"A reference must resolve to exactly one entity or none.\n"
            f"Reference: {description!r}\nCandidates: {list(candidates)}\n"
            "Judge by name match, recency, possession, and discourse context. "
            "If genuinely ambiguous, return entity_id=null with low confidence. "
            "If NO candidate matches at all (the referenced thing does not exist "
            "in this world), return entity_id=null — a genuine no-match is a "
            "valid, expected outcome, never an error."
        )
        try:
            out = self._model(prompt, task_schema(_TIER2_SCHEMA))
        except Exception:
            logger.exception("refer tier-2 model call failed")
            return Resolution(CANDIDATES, candidates=candidates,
                              receipt={"tier": 2, "signals": ["model_error"]})
        receipt = {
            "tier": 2,
            "candidates": list(candidates),
            "signals": out.get("signals", []),
            "confidence": out.get("confidence", 0.0),
        }
        if out.get("entity_id") in candidates and out.get("confidence", 0.0) >= _TIER2_FLOOR:
            resolution = Resolution(RESOLVED, out["entity_id"], receipt=receipt)
            if learn_frame is not None:
                self._learn(description, out["entity_id"], receipt, learn_frame)
            return resolution
        # Tier 3 contract: the ask is the host's to deliver.
        return Resolution(UNDERDETERMINED, candidates=candidates, receipt=receipt)
