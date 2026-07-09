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
from patternbuffer.model import ATTR_PREFIX, CANON, META_ATTRIBUTES
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
        self.registry = IdentityRegistry(self.buffer, roles["ingestor"], self.semantics)
        self.indexes = Indexes(
            self.buffer, self.classifier, self.registry.resolve, self.semantics
        )
        self.indexes.set_closure_provider(self.registry.closure)
        self.indexes.set_correlation_provider(self.registry.correlation_set)
        self.registry.set_kind_provider(lambda e: self.indexes.fold_key(e, "kind"))
        self.salience_index = SalienceIndex(self.buffer, self.classifier, self.indexes)
        self.indexes.set_salience_provider(self.salience_index.salience)
        self.truth = TruthMaintenance(
            self.buffer, self.classifier, self.indexes, roles["truth_maintenance"],
            self.semantics,
        )
        # SHAPE-FIX-V1 retype wiring: retraction authority + rules-mode
        # durability for the corrected kind row (the set_kind_provider idiom —
        # truth/classifier post-date the registry).
        self.registry.set_retract_provider(self.truth.retract)
        self.registry.set_classify_provider(
            lambda rows: self.classifier.classify_rows(rows, model=False)
        )
        # Win 4 (durable-contradiction veto, HD 089): the registry reads
        # standing folds + durability verdicts through late-bound lookups.
        self.registry.set_fold_provider(self.indexes.fold_key)
        self.registry.set_durability_provider(self.classifier.durability)
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

    # PLACE-FEATURE-ABSTRACTION-V1 — the compositional axis (part_of).
    def composition(self, entity: str, **kw) -> list[str]:
        return self.indexes.composition(entity, **kw)

    def features(self, place: str, **kw) -> list[str]:
        return self.indexes.features(place, **kw)

    # WHO-KNOWS-INVERSE-V1 — the computed "who knows X" read.
    def who_knows(self, entity: str, attribute: str, value: Any = None, **kw) -> list[str]:
        return self.indexes.who_knows(entity, attribute, value, **kw)

    def state(self, entity: str, attribute: str, frame: str = CANON, **kw):
        return self.indexes.fold_key(entity, attribute, frame, **kw)

    # AKA-CORRELATION-V1 — the explicit, opt-in correlated identity surface.
    def state_union(self, entity: str, attribute: str, frame: str = CANON, **kw):
        return self.indexes.state_union(entity, attribute, frame, **kw)

    def correlations(self, entity: str, **kw) -> list[str]:
        return self.registry.correlations(entity, **kw)

    def correlate(self, a: str, b: str, evidence: str, **kw) -> dict:
        return self.registry.correlate(a, b, evidence, **kw)

    def correlation_conflicts(self, **kw) -> list[dict]:
        return self.registry.correlation_conflicts(**kw)

    def path(self, a: str, b: str, **kw) -> list[str] | None:
        return self.indexes.path(a, b, **kw)

    def route(self, a: str, b: str, **kw) -> dict:
        return self.indexes.route(a, b, **kw)

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

    def fidelity_audit(self, frame: str = CANON, as_of: float | None = None) -> dict:
        """Structural ingestion-fidelity gaps, derived (INGESTION-FIDELITY-V1).
        Read-only; run after a build's classification + `truth.scan()` (it never
        classifies or scans). The engine surfaces gaps; the host joins arc/cast
        severity and drives targeted re-extraction."""
        from patternbuffer.classify import EVENT, STATE

        collisions = self.registry.name_collisions(frame=frame, valid_as_of=as_of)

        unstamped: list[dict] = []
        entities: set[str] = set()
        for row in self.buffer.visible(frame=frame):
            if row.entity.startswith("a:") or row.entity.startswith(ATTR_PREFIX):
                continue
            eid = self.registry.resolve(row.entity)
            if eid.startswith(("obj:", "person:")):
                entities.add(eid)
            # Meta/identity edges (same_as/distinct_from/aka/source…) are
            # classified EVENT and carry no valid_from BY DESIGN — bookkeeping,
            # never a spine fact; they are not an unstamped gap.
            if row.attribute in META_ATTRIBUTES:
                continue
            if row.valid_from is None and self.classifier.get(row.id) is not None \
                    and self.classifier.durability(row.id) in (STATE, EVENT):
                unstamped.append({"entity": eid, "attribute": row.attribute,
                                  "assertion_id": row.id})

        orphans = sorted(
            e for e in entities
            if not self.indexes.locate(e, frame=frame, valid_as_of=as_of)
        )

        conflicts = [
            {"entity": c.entity, "attribute": c.attribute, "frame": c.frame,
             "kind": c.kind, "assertion_ids": list(c.assertion_ids)}
            for c in self.truth.open_conflicts()
        ]

        live = sum(1 for g in collisions if g["live"])
        return {
            "frame": frame,
            "name_collisions": collisions,
            "unstamped_timed": unstamped,
            "orphan_entities": orphans,
            "open_conflicts": conflicts,
            "summary": {
                "name_collisions": live,          # live-fragmentation groups only
                "name_collisions_total": len(collisions),
                "unstamped_timed": len(unstamped),
                "orphan_entities": len(orphans),
                "open_conflicts": len(conflicts),
            },
        }

    def materialize(self, scope, **kw) -> Materialization:
        return self.projector.materialize(scope, **kw)

    # Writes (each behind its role).

    def ingest(self, text: str, context: str = "", frame: str | None = None,
               classify: str = "inline", extract: str = "full",
               cursor_authoritative: bool = False, pov: str | None = None) -> list:
        return self.ingestor.ingest(text, context, frame=frame, classify=classify,
                                    extract=extract,
                                    cursor_authoritative=cursor_authoritative,
                                    pov=pov)

    def extract(self, text: str, context: str = "", extract: str = "full",
                pov: str | None = None) -> list:
        """Read-only extraction (INGEST-LATENCY-V2): the host parallelizes these,
        then ingest_structured()s the results serially. No write. `pov`
        (SHAPE-FIX-V1 4c): the viewpoint entity id for deixis binding."""
        return self.ingestor.extract(text, context, extract=extract, pov=pov)

    def ingest_structured(self, items: list[dict], frame: str | None = None,
                          classify: str = "inline",
                          cursor_authoritative: bool = False) -> list:
        return self.ingestor.ingest_structured(
            items, frame=frame, classify=classify,
            cursor_authoritative=cursor_authoritative)

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
        # An open build session never outlives the buffer: abort (restore the
        # classify toggle, classify nothing) before closing (BUILD-SESSION-V1).
        if hasattr(self, "_porcelain"):
            self._porcelain.abort_build()
        self.buffer.close()


def _no_model(prompt: str, schema: dict) -> Any:
    raise RuntimeError("no model callable injected for this operation")
