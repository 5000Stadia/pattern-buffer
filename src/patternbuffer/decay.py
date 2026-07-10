"""DecayPolicy: tracking-world time physics as declared, rebuildable data.

TRACKING-MODE-V1 §B3: in an `observe_or_unknown` world, a fact's freshness
decays with UNCONFIRMED WALL TIME — per-attribute half-lives declared as
ordinary rows (never stored results; the policy is read fresh at each read and
rebuilds from the log). Deliberately SEPARATE from `AttributeSemantics`: decay
is world physics, not fold semantics — a declaration on the inviolable-core
`in` key must configure, not be rejected.

Declaration rows:  `attr:<key> · decay_halflife_seconds · <finite positive n>`
World default:     `attr:__world__ · decay_halflife_seconds · <n>`

Lookup for a served winner authored as attribute A (deterministic, Cx 563):
  1. `attr:<A>` — exact policy for the winner's canonical authored attribute;
  2. if A is in the containment family: `attr:in` — the public family subject
     (the private `__containment__` fold sentinel is never host vocabulary);
  3. `attr:__world__` — the world default.
First hit wins. Later declarations fold at current head (latest visible per
subject). Policy resolution is CURRENT-physics-over-history by design: as-of
confidence applies today's declared physics to historical facts (documented).
"""

from __future__ import annotations

import math

from patternbuffer.buffer import PatternBuffer

PREDICATE = "decay_halflife_seconds"
WORLD_SUBJECT = "attr:__world__"


class DecayPolicy:
    def __init__(self, buffer: PatternBuffer, semantics) -> None:
        self._buffer = buffer
        self._semantics = semantics

    def resolve(self, authored_attribute: str) -> float | None:
        """The half-life (seconds) governing a winner authored as
        `authored_attribute`, or None (unconfigured)."""
        v = self._latest(f"attr:{authored_attribute}")
        if v is not None:
            return v
        family = (self._semantics.containment_family()
                  if self._semantics is not None else frozenset())
        if authored_attribute in family and authored_attribute != "in":
            v = self._latest("attr:in")
            if v is not None:
                return v
        return self._latest(WORLD_SUBJECT)

    def _latest(self, subject: str) -> float | None:
        """The latest visible valid declaration on `subject` (ordinary
        supersession at current head); malformed values never activate."""
        best = None
        for row in self._buffer.visible(entity=subject, attribute=PREDICATE):
            v = row.value
            if (isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) and v > 0):
                if best is None or row.asserted_at > best.asserted_at:
                    best = row
        return float(best.value) if best is not None else None
