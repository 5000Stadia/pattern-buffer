"""Derived indexes: the durability-aware fold, the containment tree, the
lateral graph (whitepaper §13/§17; spec §7). Deterministic, no LLM,
rebuildable — these are views over the buffer, never truth.

`Indexes` is one class, assembled from one mixin per section — the core
(wiring, caches, helpers), the fold, the walks, knowledge (`who_knows`),
event records, the neighborhood and routes. The sections share the core's
state and call each other freely (every one rides the fold), so the split is
by file, not by object: callers see the one `Indexes` they always did.
"""

from __future__ import annotations

from patternbuffer.indexes._core import (
    _EVIDENCE_RANK,
    _FAMILY_KEY,
    FoldResult,
    IndexesCore,
)
from patternbuffer.indexes.events import (
    _EVENT_SINGLE_VALUED,
    MOVEMENT_KEYS,
    EventsMixin,
)
from patternbuffer.indexes.fold import _FAMILY_NAME, CONFIDENCE_PARAMS, FoldMixin
from patternbuffer.indexes.knowledge import KnowledgeMixin
from patternbuffer.indexes.neighborhood import (
    _NEIGHBORHOOD_DEPTH_CAP,
    _NEIGHBORHOOD_EDGES,
    NeighborhoodMixin,
)
from patternbuffer.indexes.routes import RoutesMixin
from patternbuffer.indexes.walks import WalksMixin


class Indexes(
    FoldMixin,
    WalksMixin,
    KnowledgeMixin,
    EventsMixin,
    NeighborhoodMixin,
    RoutesMixin,
    IndexesCore,
):
    """Fold + walks. Holds no durable state of its own (P2)."""


__all__ = [
    "CONFIDENCE_PARAMS",
    "FoldResult",
    "Indexes",
    "MOVEMENT_KEYS",
    "_EVENT_SINGLE_VALUED",
    "_EVIDENCE_RANK",
    "_FAMILY_KEY",
    "_FAMILY_NAME",
    "_NEIGHBORHOOD_DEPTH_CAP",
    "_NEIGHBORHOOD_EDGES",
]
