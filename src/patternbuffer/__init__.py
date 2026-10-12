"""patternbuffer: an append-only world-state substrate.

One append-only log of perspective-scoped, time-indexed assertions per
world; every other structure — current state, space, knowledge, history,
the rendered world — is a disposable projection over it.

The engine is host-blind: its single outside dependency is an injected
model callable ``(prompt, schema) -> json``. See docs/WHITEPAPER.md.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

from patternbuffer.buffer import (
    PatternBuffer,
    ReadOnlyWorld,
    SecondWriter,
    WorldPhysicsMismatch,
)
from patternbuffer.classify import Classifier
from patternbuffer.identity import IdentityRegistry
from patternbuffer.indexes import MOVEMENT_KEYS, Indexes
from patternbuffer.ingest import Ingestor
from patternbuffer.model import (
    ATTR_PREFIX,
    CANON,
    META_ATTRIBUTES,
    RESOLUTION_POLICY,
    WORLD_PHYSICS_SUBJECT,
    ResolveRequest,
    task_request,
)
from patternbuffer.project import Materialization, Projector
from patternbuffer.codec import encode_out
from patternbuffer.refer import Refer, Resolution
from patternbuffer.roles import _make_engine_roles
from patternbuffer.salience import SalienceIndex
from patternbuffer.semantics import AttributeSemantics
from patternbuffer.thunks import (
    INVENT_UNDER_CANON,
    OBSERVE_OR_UNKNOWN,
    POLICIES,
    UNKNOWN,
    Resolver,
)
from patternbuffer.tmaint import AtomicAbort, TruthMaintenance

# Kept in lockstep with pyproject's `version` by
# tests/test_version.py::test_version_matches_pyproject — the literal drifted
# to 0.0.1 through the 0.1/0.2 releases, so a host pinning capability
# detection to `__version__` read a version three releases stale. The test is
# the guard; pyproject remains the single source of truth.
__version__ = "0.2.0"

STANCES = frozenset({"fiction", "reality", "hypothetical"})  # letter 026; fixed enum
__all__ = ["World", "Materialization", "Resolution", "AtomicAbort",
           "SecondWriter", "ReadOnlyWorld", "WorldPhysicsMismatch",
           "ResolveRequest", "task_request", "__version__"]


class World:
    """The named, individual unit: one PatternBuffer + its physics
    (resolution policy, decay configuration) + derived indexes (§16).

    ``World("campaign.world", world_id="w:campaign", model=callable)`` is
    the entire harness interface — a parameter, not a framework. Role
    capabilities are minted here and nowhere else.

    A world file carries its physics (READ-SURFACE-V1 §7): the resolution
    policy is recorded at genesis as the physics row, and every later open
    runs under it. An explicit ``policy=`` that disagrees with the stored one
    raises ``WorldPhysicsMismatch`` and writes nothing; omitted, the stored
    physics apply (``invent_under_canon`` for a world that records none).
    """

    def __init__(
        self,
        path: str | Path,
        world_id: str,
        model: Callable[[str, dict], Any] | None = None,
        policy: str | None = None,
        clock: Callable[[], float] = time.time,
        stance: str = "fiction",
        title: str = "",
        description: str = "",
        attribute_default: Callable[[str], dict | None] | None = None,
        _connection: sqlite3.Connection | None = None,
    ) -> None:
        if policy is not None and policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}")
        if stance not in STANCES:
            raise ValueError(f"unknown stance {stance!r} (fixed enum; letter 026)")
        self.world_id = world_id
        self._clock = clock
        # `_connection` is private: `snapshot()` constructs a World normally
        # over the in-memory copy it made (WORLD-SERVICE-V1 §7a).
        self.buffer = PatternBuffer(path, world_id, connection=_connection)
        # READ-SURFACE-V1 §7: the stored physics, if the world records any.
        # The physics row is immutable (the buffer refuses a second one or a
        # retraction of it), so the visible row is the only one.
        physics = self.buffer.visible(entity=WORLD_PHYSICS_SUBJECT,
                                      attribute=RESOLUTION_POLICY)
        stored = physics[0].value if physics else None
        if policy is not None and stored is not None and policy != stored:
            self.buffer.close()
            raise WorldPhysicsMismatch(
                f"world {world_id!r} at {self.buffer.path} records the physics "
                f"{stored!r}; it cannot be opened as {policy!r} — omit policy= "
                "to run it under its own")
        self.policy = stored or policy or INVENT_UNDER_CANON
        # Recorded at genesis, and on the first explicit-policy open of a world
        # created before the physics row existed: the host is stating the
        # physics it runs the world under. Opened without policy=, such a
        # world is never written to.
        genesis = self.buffer.head() == 0
        record_physics = genesis or (stored is None and policy is not None)
        self.semantics = AttributeSemantics(self.buffer)
        roles = _make_engine_roles()
        self.classifier = Classifier(self.buffer, model or _no_model, self.semantics)
        self.registry = IdentityRegistry(self.buffer, roles["ingestor"], self.semantics)
        self.indexes = Indexes(
            self.buffer, self.classifier, self.registry.resolve, self.semantics
        )
        self.indexes.set_closure_provider(self.registry.closure)
        self.indexes.set_correlation_provider(self.registry.correlation_set)
        # TRACKING-MODE-V1: tracking-vs-non-tracking selects on policy ONLY
        # (never stance — the no-bias invariant); deny is a resolution policy,
        # not an epistemic mode, so it takes the non-tracking branch.
        self.indexes.set_time_physics(self.policy == OBSERVE_OR_UNKNOWN, clock)
        self.registry.set_kind_provider(self._kind_read)
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
            model or _no_model, self.policy,
            semantics=self.semantics,
            # RESOLVE-UNMARKED-V1: an undated placeholder sits at the cursor
            # (the ingestor is built below; the lookup is late-bound).
            cursor=lambda: self.ingestor.cursor.position,
        )
        self.projector = Projector(
            self.buffer, self.classifier, self.indexes, self.semantics,
            self.salience_index.salience,
        )
        self.ingestor = Ingestor(
            self.buffer, self.classifier, self.registry, roles["ingestor"],
            model, observe_mode=(self.policy == OBSERVE_OR_UNKNOWN), clock=clock,
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
        if genesis:
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
        if record_physics:
            # One writer, by a direct ingestor-role append: no gate, no cursor,
            # no attribute_default. Classified CONSTITUTIVE by its guardrail.
            physics_row = self.buffer.append(
                entity=WORLD_PHYSICS_SUBJECT, attribute=RESOLUTION_POLICY,
                value=self.policy, status="stated", role=roles["ingestor"],
            )
            self.classifier.classify(physics_row)

    # Reads (deterministic, no LLM — P7).

    def canonical_attribute(self, name: str) -> str:
        """The gate's name for an attribute (READ-SURFACE-V1 §3): its
        normalization and forward alias map, as applied on write."""
        return self.ingestor.canonical_attribute(name)

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

    # MOVED-EVENT-V1 § E2 — "in transit" is temporal world-state, not host
    # judgment, so it is one engine-derived read (a sibling of locate()/events()).
    # Writes nothing durable; adds no mutation verb; changes neither the fold nor
    # locate(). Identical signature on World and the porcelain.
    def in_transit(self, agent: str | None = None, as_of: float | None = None,
                   frame: str = CANON, asserted_as_of: int | None = None) -> list[dict]:
        """Open moved events whose agent has not yet arrived, read from event
        records (EVENTS-ONE-READER-V1 §3): `events()`'s reader and its parse,
        as of both time axes. A record is a move when its `kind` (the pick)
        is `moved`; openness, the anchor and the containment comparison are
        MOVED-EVENT-V1 §E2's."""
        indexes = self.indexes
        wanted = self.registry.resolve(agent) if agent is not None else None
        out: list[dict] = []
        # The reader applies the valid axis: a record as of `as_of` exists only
        # once the move has occurred, and `valid_to` never hides its rows.
        for eid, record in indexes.event_records(
                frame, valid_as_of=as_of, asserted_as_of=asserted_as_of).items():
            ev = indexes.event_payload(eid, record)
            if ev["kind"] != "moved":
                continue
            # openness (§ E2). as_of=None: open iff valid_to is None. At t: it
            # has occurred by t (the reader) AND (valid_to is None OR t <
            # valid_to). A zero-duration (complete) or closed move is never in
            # transit.
            valid_to = ev["valid_to"]
            if valid_to is not None and (as_of is None or as_of >= valid_to):
                continue
            agent_row = indexes.event_pick([r for r in record if r.attribute == "agent"])
            agent_val = agent_row.value if agent_row is not None else None
            if wanted is not None and (agent_val is None
                                       or self.registry.resolve(agent_val) != wanted):
                continue
            # event-start anchor = (t, min asserted_at over the record's
            # movement-payload rows only).
            anchor = (ev["t"] if ev["t"] is not None else float("-inf"),
                      min(r.asserted_at for r in record if r.attribute in MOVEMENT_KEYS))
            # containment comparison (pbr's tuple rule). Exclude (arrived) only
            # when a containment winner exists whose (valid_from, asserted_at) is
            # AT OR AFTER the anchor; a head predating the anchor = last-known.
            last_known = None
            if agent_val is not None:
                winner = self.state(self.registry.resolve(agent_val), "in",
                                    frame=frame, valid_as_of=as_of,
                                    asserted_as_of=asserted_as_of).winner
                if winner is not None:
                    w_anchor = (winner.valid_from if winner.valid_from is not None
                                else float("-inf"), winner.asserted_at)
                    if w_anchor >= anchor:
                        continue  # arrived / relocated — not in transit
                    last_known = (self.registry.resolve(winner.value)
                                  if winner.value_type == "entity" else winner.value)
            out.append({"agent": agent_val, "origin": ev["origin"],
                        "destination": ev["destination"], "manner": ev["manner"],
                        "last_known_containment": last_known})
        return sorted(out, key=lambda d: (str(d["agent"]), str(d["destination"])))

    def state(self, entity: str, attribute: str, frame: str = CANON, **kw):
        return self.indexes.fold_key(entity, attribute, frame, **kw)

    def _kind_read(self, entity: str):
        """Identity's kind lookup (EVENTS-ONE-READER-V1 §4 Rule C): the canon
        fold of `kind`, falling back to the event record when the fold serves
        nothing. An event's rows never fold (Rule A), so without the fallback
        identity's merge gates would lose an event's kind in a build (where it
        used to fold as unclassified STATE); with it they see the kind before a
        sweep and after it alike, and an event never auto-merges with a
        non-event over a shared proper name."""
        fold = self.indexes.fold_key(entity, "kind")
        if fold.winner is None:
            fold = self.indexes.event_attribute(entity, "kind")
        return fold

    # AKA-CORRELATION-V1 — the explicit, opt-in correlated identity surface.
    def state_union(self, entity: str, attribute: str, frame: str = CANON, **kw):
        return self.indexes.state_union(entity, attribute, frame, **kw)

    def correlations(self, entity: str, **kw) -> list[str]:
        return self.registry.correlations(entity, **kw)

    def correlate(self, a: str, b: str, evidence: str, **kw) -> dict:
        return self.registry.correlate(a, b, evidence, **kw)

    def correlation_conflicts(self, **kw) -> list[dict]:
        return self.registry.correlation_conflicts(**kw)

    # FRAME-SCOPED-IDENTITY-V1 §4 — merged canon closures holding a vetoed pair.
    def identity_conflicts(self, asserted_as_of: int | None = None) -> list[dict]:
        return self.registry.identity_conflicts(asserted_as_of=asserted_as_of)

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
        now: float | None = None,
    ) -> dict:
        # `now` is WALL time (TRACKING-MODE-V1): the staleness reference in
        # tracking worlds, defaulting to the injected clock; unused in fiction.
        # Never a second meaning for as_of (which stays valid time).
        return self.indexes.confidence(
            entity, attribute, frame=frame, as_of=as_of,
            asserted_as_of=asserted_as_of, now=now,
        )

    def neighborhood(self, entity: str, **kw) -> dict:
        return self.indexes.neighborhood(entity, **kw)

    def aggregate(self, container: str, member_attribute: str, op: str, **kw) -> dict:
        return self.indexes.aggregate(container, member_attribute, op, **kw)

    def fidelity_audit(self, frame: str = CANON, as_of: float | None = None) -> dict:
        """Structural ingestion-fidelity gaps, derived (INGESTION-FIDELITY-V1).
        Read-only; run after a build's classification (it never classifies).
        `open_conflicts` is computed on read for `frame` as of `as_of`
        (FRAME-SCOPED-IDENTITY-V1 §5) — no `truth.scan()` is needed first. The
        engine surfaces gaps; the host joins arc/cast severity and drives
        targeted re-extraction."""
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
            for c in self.truth.open_conflicts(frame=frame, valid_as_of=as_of)
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
        self.buffer.require_writable()
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
                          cursor_authoritative: bool = False,
                          extracted: bool = False, atomic: bool = False) -> list:
        # `extracted` (MOVED-EVENT-V1 §B.3): prose-authored mode — the engine
        # authors movement timestamps (the moved-event coordinate pass). Default
        # False keeps structured callers byte-identical; World.ingest sets it.
        # `atomic` (ATOMIC-ACTIVATION-V1 §A): all-or-none visibility, default off.
        self.buffer.require_writable()
        return self.ingestor.ingest_structured(
            items, frame=frame, classify=classify,
            cursor_authoritative=cursor_authoritative, extracted=extracted,
            atomic=atomic)

    def commit_set(self, ops: list[dict], *, classify: str = "rules",
                   frame: str = CANON, cursor_authoritative: bool = False) -> list:
        # The typed activation door (ATOMIC-ACTIVATION-V1 §C): ordered
        # assert/retract ops applied as one all-or-none unit of work.
        self.buffer.require_writable()
        return self.ingestor.commit_set(
            ops, self.truth, classify=classify, frame=frame,
            cursor_authoritative=cursor_authoritative)

    def resolve(self, entity: str, aspect: str, frame: str = CANON, access=None,
                at: float | None = None, perceive_in: str | None = None):
        """Force an aspect (whitepaper §8). With ``perceive_in`` set
        (WORLD-SERVICE-V1 §7b) the plant, the force (or memo) and the mirror
        into that frame run in ONE atomic unit; ``at`` is the mirror's valid
        time (the scene cursor when omitted). Without it, E1's behavior."""
        if perceive_in is None:
            return self.resolver.resolve(entity, aspect, frame, access)
        return self._resolve_perceived(entity, aspect, frame, at, perceive_in)[0]

    def _resolve_perceived(self, entity: str, aspect: str, frame: str,
                           at: float | None, perceive_in: str):
        """``resolve(perceive_in=)``'s one unit: plant (if declared), force or
        serve the memo, then mirror what resolved into ``perceive_in`` as
        ``observed`` rows through the gate, at ``at`` or the scene cursor, only
        the rows that frame does not already hold. Returns
        ``(out, planted, perceived)`` where ``perceived`` is the frame's own
        rows for what resolved (new and already held). The unit owns commit and
        rollback: a failure anywhere, a gate refusal of the mirror included,
        leaves no placeholder, no generated row and no mirror."""
        if not isinstance(perceive_in, str) or not perceive_in:
            raise ValueError("perceive_in must name a frame")
        if perceive_in == frame:
            raise ValueError("perceive_in must differ from the frame being resolved")
        when = at if at is not None else self.ingestor.cursor.position

        def body():
            out, planted = self.resolver.resolve_planted(
                entity, aspect, frame, joined=True)
            rows = [] if out is UNKNOWN else [r for r in out if r is not None]
            return out, planted, self._mirror(rows, aspect, frame, perceive_in, when)

        return self.ingestor.run_unit(body)

    def _mirror(self, rows: list, aspect: str, frame: str, perceive_in: str,
                when: float | None) -> list:
        """Mirror resolved rows into ``perceive_in`` as the observer's
        perception (WORLD-SERVICE-V1 §4). Contents mint entities whose `kind`
        and `name` are rows of their own, so those are mirrored with the
        containment edge — without them the observer would perceive an
        unnamed thing."""
        sources = list(rows)
        if aspect == "contents":
            for edge in rows:
                sources += [r for r in self.buffer.visible(entity=edge.entity, frame=frame)
                            if r.status == "generated" and r.attribute in ("kind", "name")]
        perceived: list = []
        items: list[dict] = []
        for src in sources:
            held = [r for r in self.buffer.visible(
                        entity=src.entity, attribute=src.attribute, frame=perceive_in)
                    if r.value_type == src.value_type and r.value == src.value]
            if held:
                perceived.append(held[-1])
                continue
            items.append({"entity": src.entity, "attribute": src.attribute,
                          "value": encode_out(src.value), "value_type": src.value_type,
                          "status": "observed", "valid_from": when})
        if items:
            written = self.ingestor.ingest_structured(
                items, frame=perceive_in, classify="rules")
            if self.ingestor.last_skipped:
                raise AtomicAbort(
                    "gate_skip", [s.to_dict() for s in self.ingestor.last_skipped], None)
            perceived += [r for r in written
                          if r.frame == perceive_in and r.attribute not in META_ATTRIBUTES
                          and not r.entity.startswith("a:")]
        return perceived

    def snapshot(self) -> "World":
        """A read-only World over an in-memory copy of this one (WORLD-SERVICE-V1
        §7a): the owner connection is backed up into a fresh in-memory
        database (opened for use from another thread), a World is constructed
        normally over the copy, and only then is the copy's log sealed — every
        append, the gate, retraction and every unit raise ``ReadOnlyWorld``.
        The copy's derived sidecars stay writable (its own disposable layer).
        The source's file and ``data_version`` are not touched. Call it on the
        owner's thread, outside any atomic unit; hand the copy to ONE other
        thread."""
        if self.buffer.unit_open:
            raise RuntimeError("World.snapshot() cannot run inside an atomic unit")
        source = self.buffer._live_conn()   # poison / second-writer guard
        copy = sqlite3.connect(":memory:", check_same_thread=False)
        try:
            source.backup(copy)
            snap = World(self.buffer.path, self.world_id, clock=self._clock,
                         _connection=copy)
        except BaseException:
            copy.close()
            raise
        if snap.buffer.head() != self.buffer.head():
            snap.buffer.close()
            raise RuntimeError("snapshot construction wrote to the copy's log")
        snap.buffer.seal_log()
        return snap

    @property
    def porcelain(self):
        """The frozen host surface (PORCELAIN-V1). Lazy; import-local to
        avoid circularity."""
        if not hasattr(self, "_porcelain"):
            from patternbuffer.porcelain import Porcelain
            self._porcelain = Porcelain(self)
        return self._porcelain

    def charter(self, asserted_as_of: int | None = None) -> dict[str, Any]:
        """The world's self-description, read from world:self (letter 026), as
        of a log position when one is given (READ-SURFACE-V1 §8)."""
        out: dict[str, Any] = {}
        for attr, result in self.indexes.current_state(
                "world:self", asserted_as_of=asserted_as_of).items():
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
