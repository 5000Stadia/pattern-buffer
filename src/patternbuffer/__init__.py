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
from patternbuffer.salience import SalienceIndex
from patternbuffer.semantics import AttributeSemantics
from patternbuffer.thunks import (
    INVENT_UNDER_CANON,
    OBSERVE_OR_UNKNOWN,
    POLICIES,
    Resolver,
)
from patternbuffer.tmaint import TruthMaintenance

__version__ = "0.0.1"

STANCES = frozenset({"fiction", "reality", "hypothetical"})  # letter 026; fixed enum
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
        stance: str = "fiction",
        title: str = "",
        description: str = "",
        attribute_default: Callable[[str], dict | None] | None = None,
    ) -> None:
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}")
        if stance not in STANCES:
            raise ValueError(f"unknown stance {stance!r} (fixed enum; letter 026)")
        self.world_id = world_id
        self.policy = policy
        self.buffer = PatternBuffer(path, world_id)
        self.semantics = AttributeSemantics(self.buffer)
        roles = _make_engine_roles()
        self.classifier = Classifier(self.buffer, model or _no_model, self.semantics)
        self.registry = IdentityRegistry(self.buffer, roles["ingestor"])
        self.indexes = Indexes(
            self.buffer, self.classifier, self.registry.resolve, self.semantics
        )
        self.indexes.set_closure_provider(self.registry.closure)
        self.salience_index = SalienceIndex(self.buffer, self.classifier, self.indexes)
        self.indexes.set_salience_provider(self.salience_index.salience)
        self.truth = TruthMaintenance(
            self.buffer, self.classifier, self.indexes, roles["truth_maintenance"],
            self.semantics,
        )
        self.resolver = Resolver(
            self.buffer, self.classifier, self.indexes, roles["resolver"],
            model or _no_model, policy,
        )
        self.projector = Projector(
            self.buffer, self.classifier, self.indexes, self.semantics,
            self.salience_index.salience,
        )
        self.ingestor = Ingestor(
            self.buffer, self.classifier, self.registry, roles["ingestor"],
            model, observe_mode=(policy == OBSERVE_OR_UNKNOWN), clock=clock,
            resolver_role=roles["resolver"],
            semantics=self.semantics,
            attribute_default=attribute_default,
            # Write-time containment-cycle gate (HD 002): the ancestor walk
            # is the derived containment chain — locate folds the family.
            containment_ancestors=lambda parent, frame, vf: set(
                self.indexes.locate(parent, frame=frame, valid_as_of=vf)
            ),
        )
        self.refer = Refer(self.buffer, self.indexes, self.registry, model,
                           ingestor=self.ingestor)
        # The World Charter (letter 026): a fresh world's genesis write
        # asserts its self-description — stance is ontological stored
        # truth (does this world claim to describe reality?), distinct
        # from operational policy. Ordinary appends; amendable forever.
        if self.buffer.head() == 0:
            charter = [
                {"entity": "world:self", "attribute": "kind", "value": "world",
                 "timeless": True},
                {"entity": "world:self", "attribute": "stance", "value": stance,
                 "timeless": True},
            ]
            if title:
                charter.append({"entity": "world:self", "attribute": "title",
                                "value": title, "timeless": True})
            if description:
                charter.append({"entity": "world:self", "attribute": "description",
                                "value": description, "timeless": True})
            self.ingestor.classify_inline = False
            self.ingest_structured(charter)
            self.ingestor.classify_inline = True
            for row in self.buffer.all_rows():
                self.classifier.set(row.id, "CONSTITUTIVE", 1.0)

    # Reads (deterministic, no LLM — P7).

    def locate(self, entity: str, **kw) -> list[str]:
        return self.indexes.locate(entity, **kw)

    def contents(self, container: str, **kw) -> list[str]:
        return self.indexes.contents(container, **kw)

    def state(self, entity: str, attribute: str, frame: str = CANON, **kw):
        return self.indexes.fold_key(entity, attribute, frame, **kw)

    def path(self, a: str, b: str, **kw) -> list[str] | None:
        return self.indexes.path(a, b, **kw)

    def salience(
        self, entity: str, frame: str = CANON, as_of: float | None = None
    ) -> float:
        return self.salience_index.salience(entity, frame, as_of)

    def confidence(
        self,
        entity: str,
        attribute: str,
        frame: str | list[str] = CANON,
        as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> dict:
        return self.indexes.confidence(
            entity, attribute, frame=frame, as_of=as_of,
            asserted_as_of=asserted_as_of,
        )

    def neighborhood(self, entity: str, **kw) -> dict:
        return self.indexes.neighborhood(entity, **kw)

    def aggregate(self, container: str, member_attribute: str, op: str, **kw) -> dict:
        return self.indexes.aggregate(container, member_attribute, op, **kw)

    def materialize(self, scope, **kw) -> Materialization:
        return self.projector.materialize(scope, **kw)

    # Writes (each behind its role).

    def ingest(self, text: str, context: str = "", frame: str | None = None) -> list:
        return self.ingestor.ingest(text, context, frame=frame)

    def ingest_structured(self, items: list[dict], frame: str | None = None) -> list:
        return self.ingestor.ingest_structured(items, frame=frame)

    def resolve(self, entity: str, aspect: str, frame: str = CANON, access=None):
        return self.resolver.resolve(entity, aspect, frame, access)

    @property
    def porcelain(self):
        """The frozen host surface (PORCELAIN-V1). Lazy; import-local to
        avoid circularity."""
        if not hasattr(self, "_porcelain"):
            from patternbuffer.porcelain import Porcelain
            self._porcelain = Porcelain(self)
        return self._porcelain

    def charter(self) -> dict[str, Any]:
        """The world's self-description, read from world:self (letter 026)."""
        out: dict[str, Any] = {}
        for attr, result in self.indexes.current_state("world:self").items():
            if result.winner is not None:
                out[attr] = result.winner.value
        return out

    def close(self) -> None:
        self.buffer.close()


def _no_model(prompt: str, schema: dict) -> Any:
    raise RuntimeError("no model callable injected for this operation")
