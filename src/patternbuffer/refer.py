"""refer(): reference resolution, the fourth boundary operation
(whitepaper §9; spec §9.3). Three-tier cascade, cheapest first; tier 1
is deterministic and makes no model call. Low confidence never guesses.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from patternbuffer.buffer import PatternBuffer
from patternbuffer.identity import IdentityRegistry
from patternbuffer.indexes import Indexes
from patternbuffer.model import ATTR_PREFIX, CANON

logger = logging.getLogger(__name__)

RESOLVED = "resolved"
CANDIDATES = "candidates"
UNDERDETERMINED = "underdetermined"

_TIER2_SCHEMA = {
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
        # Alias accrual (letter 018, mechanic 2) appends through the gate's
        # role; without an ingestor wired, resolution still works but the
        # world does not learn its users' words.
        self._ingestor = ingestor

    def _accrue_alias(self, description: str, entity_id: str, receipt: dict) -> None:
        """Memoize a tier-2 resolution as an alias assertion carrying the
        resolution receipt — each synonym costs one tier-2 call once, then
        is tier-1a forever. A learned alias never outranks an exact name
        (by_alias hits both; exact-name uniqueness still wins tier 1a, and
        a later collision is ordinary ambiguity -> tier 2)."""
        if self._ingestor is None:
            return
        rows = self._ingestor.ingest_structured([
            {"entity": entity_id, "attribute": "alias",
             "value": description.strip().lower(), "timeless": True,
             "status": "inferred"},
        ])
        self._buffer.append(
            entity=rows[0].id, attribute="source",
            value=f"refer:tier2:{json.dumps(receipt.get('signals', []))[:80]}",
            status="inferred", role=self._ingestor._role,
        )
        logger.info("alias accrued: %r -> %s", description, entity_id)

    def __call__(
        self,
        description: str,
        scope: str | list[str] | None = None,
        frame: str = CANON,
        constraints: list[tuple[str, str]] | None = None,
        as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> Resolution:
        # ---- Tier 1a: exact name/alias hit through the identity registry.
        # Try the raw expression and its determiner-stripped core (HD 003):
        # "my brass measuring spoon" misses the exact name otherwise.
        core = self._strip_determiner(description)
        hits = self._registry.by_alias(description)
        if core != description.strip().lower():
            hits = hits | self._registry.by_alias(core)
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
            members = self._scope_members(scope, frame, as_of, asserted_as_of)
            of_kind = [
                e for e in members
                if self._entity_kind(e, frame, as_of, asserted_as_of) == kind
            ]
            if len(of_kind) == 1:
                return Resolution(RESOLVED, of_kind[0],
                                  receipt={"tier": 1, "signals": ["unique_kind_in_scope"]})
            if len(of_kind) > 1:
                return self._resolve_tier2(description, tuple(sorted(of_kind)))
        if len(hits) > 1:
            return self._resolve_tier2(description, tuple(sorted(hits)))

        # ---- Zero-candidate escalation (letter 018, mechanic 1): a synonym
        # yields zero tier-1 matches; with a scope provided, that is exactly
        # tier 2's judgment — vocabulary miss must not masquerade as absence.
        # Scope-bounded ONLY: never world-scope for this path.
        if scope is not None:
            members = self._scope_members(scope, frame, as_of, asserted_as_of)
            if members:
                return self._resolve_tier2(description, tuple(sorted(members)))

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
                folded = self._indexes.fold_key(anchor, "in", frame, as_of, asserted_as_of)
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

    def _resolve_tier2(self, description: str, candidates: tuple[str, ...]) -> Resolution:
        """Strict-contract cheap call judging candidates; returns a
        resolution receipt. Below the floor -> tier 3: never guess."""
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
            out = self._model(prompt, _TIER2_SCHEMA)
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
            self._accrue_alias(description, out["entity_id"], receipt)
            return resolution
        # Tier 3 contract: the ask is the host's to deliver.
        return Resolution(UNDERDETERMINED, candidates=candidates, receipt=receipt)
