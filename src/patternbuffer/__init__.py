"""patternbuffer: an append-only world-state substrate.

One append-only log of perspective-scoped, time-indexed assertions per
world; every other structure — current state, space, knowledge, history,
the rendered world — is a disposable projection over it.

The engine is host-blind: its single outside dependency is an injected
model callable ``(prompt, schema) -> json``. See docs/WHITEPAPER.md.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import Classifier
from patternbuffer.identity import IdentityRegistry
from patternbuffer.indexes import Indexes
from patternbuffer.ingest import Ingestor
from patternbuffer.model import CANON
from patternbuffer.project import Materialization, Projector
from patternbuffer.refer import Refer, Resolution
from patternbuffer.roles import _make_engine_roles
from patternbuffer.thunks import (
    INVENT_UNDER_CANON,
    OBSERVE_OR_UNKNOWN,
    POLICIES,
    Resolver,
)
from patternbuffer.tmaint import TruthMaintenance

__version__ = "0.0.1"
__all__ = ["World", "Materialization", "Resolution", "__version__"]


class World:
    """The named, individual unit: one PatternBuffer + its physics
    (resolution policy, decay configuration) + derived indexes (§16).

    ``World("campaign.world", world_id="w:campaign", model=callable)`` is
    the entire harness interface — a parameter, not a framework. Role
    capabilities are minted here and nowhere else.
    """

    def __init__(
        self,
        path: str | Path,
        world_id: str,
        model: Callable[[str, dict], Any] | None = None,
        policy: str = INVENT_UNDER_CANON,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}")
        self.world_id = world_id
        self.policy = policy
        self.buffer = PatternBuffer(path, world_id)
        roles = _make_engine_roles()
        self.classifier = Classifier(self.buffer, model or _no_model)
        self.registry = IdentityRegistry(self.buffer, roles["ingestor"])
        self.indexes = Indexes(self.buffer, self.classifier, self.registry.resolve)
        self.truth = TruthMaintenance(
            self.buffer, self.classifier, self.indexes, roles["truth_maintenance"]
        )
        self.resolver = Resolver(
            self.buffer, self.classifier, self.indexes, roles["resolver"],
            model or _no_model, policy,
        )
        self.projector = Projector(self.buffer, self.classifier, self.indexes)
        self.ingestor = Ingestor(
            self.buffer, self.classifier, self.registry, roles["ingestor"],
            model, observe_mode=(policy == OBSERVE_OR_UNKNOWN), clock=clock,
        )
        self.refer = Refer(self.buffer, self.indexes, self.registry, model)

    # Reads (deterministic, no LLM — P7).

    def locate(self, entity: str, **kw) -> list[str]:
        return self.indexes.locate(entity, **kw)

    def contents(self, container: str, **kw) -> list[str]:
        return self.indexes.contents(container, **kw)

    def state(self, entity: str, attribute: str, frame: str = CANON, **kw):
        return self.indexes.fold_key(entity, attribute, frame, **kw)

    def path(self, a: str, b: str, **kw) -> list[str] | None:
        return self.indexes.path(a, b, **kw)

    def materialize(self, scope, **kw) -> Materialization:
        return self.projector.materialize(scope, **kw)

    # Writes (each behind its role).

    def ingest(self, text: str, context: str = "") -> list:
        return self.ingestor.ingest(text, context)

    def ingest_structured(self, items: list[dict]) -> list:
        return self.ingestor.ingest_structured(items)

    def resolve(self, entity: str, aspect: str, frame: str = CANON, access=None):
        return self.resolver.resolve(entity, aspect, frame, access)

    def close(self) -> None:
        self.buffer.close()


def _no_model(prompt: str, schema: dict) -> Any:
    raise RuntimeError("no model callable injected for this operation")
