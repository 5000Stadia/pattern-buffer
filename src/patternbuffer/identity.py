"""The identity registry (whitepaper §11): anchors, aliases,
SAME_AS / MAYBE_SAME_AS, merges as logged events.

The registry is derived: edges are ordinary assertions; the closure is
computed (union-find over visible same_as edges). A merge appends — late
binding leaves every earlier row intact and reachable through the merged
identity. A bad merge is repaired forward by retracting the edge.
"""

from __future__ import annotations

import logging
import re

from patternbuffer.buffer import PatternBuffer
from patternbuffer.model import ATTR_PREFIX, CANON, CONTAINMENT_FAMILY, META_ATTRIBUTES
from patternbuffer.roles import WriterRole

# Identity edges — never a "relating edge" for the distinctness signal.
_IDENTITY_ATTRS = frozenset({"same_as", "maybe_same_as", "distinct_from", "aka"})

logger = logging.getLogger(__name__)

# Content-token normalization for the alias-specificity test (IDENTITY-RECALL-V1
# §3): a discriminative alias has >=2 *informative* tokens after dropping
# articles, possessives, honorific/title prefixes, and punctuation.
_ARTICLES = frozenset({"the", "a", "an"})
_HONORIFICS = frozenset({
    "mr", "mrs", "ms", "dr", "sir", "lord", "lady", "master", "mister",
    "madam", "prof", "professor", "captain", "king", "queen", "saint", "st",
})


def _content_tokens(text: str) -> list[str]:
    """Normalized informative tokens of a name/alias string."""
    t = text.strip().lower()
    t = re.sub(r"'s\b", "", t)          # drop possessive 's
    t = re.sub(r"[^\w\s]", " ", t)      # punctuation -> space
    out = []
    for tok in t.split():
        if len(tok) <= 1:               # stray single chars (possessive remnants)
            continue
        if tok in _ARTICLES or tok in _HONORIFICS:
            continue
        out.append(tok)
    return out


class IdentityRegistry:
    def __init__(
        self, buffer: PatternBuffer, ingestor: WriterRole, semantics=None
    ) -> None:
        self._buffer = buffer
        self._ingestor = ingestor
        # AttributeSemantics, for the declared containment family the merge
        # veto consults; falls back to the base family if not wired.
        self._semantics = semantics
        # Late-bound kind fold provider (entity -> FoldResult), wired by World
        # after Indexes exists (mirrors indexes.set_closure_provider). The
        # recall gate reads kind through it; absent provider => kind unknown.
        self._kind_of = None

    def set_kind_provider(self, fn) -> None:
        """Install the kind-fold lookup the recall gate consults (§2)."""
        self._kind_of = fn

    # --------------------------------------------------------------- write

    def add_alias(self, entity: str, alias: str, status: str = "stated") -> None:
        self._buffer.append(
            entity=entity, attribute="alias", value=alias.strip().lower(),
            status=status, role=self._ingestor,
        )

    def _containment_family(self) -> set[str]:
        if self._semantics is not None:
            return self._semantics.containment_family()
        return set(CONTAINMENT_FAMILY)

    def containment_block(self, a: str, b: str, asserted_as_of: int | None = None) -> list[str]:
        """The containment/location edge descriptor(s) relating a member of a's
        closure to a member of b's closure (either direction). A non-empty list
        is the merge veto (010): a thing is never identical to what holds it.
        Descriptors `entity·attr·value` name the blocking edge so a receipt can
        tell the host which edge to retract (MERGE-RECONCILE-VERB-V1). Membrane-
        clean: computed from present edges, never stored."""
        family = self._containment_family()
        clos_a = self.closure(a, asserted_as_of)
        clos_b = self.closure(b, asserted_as_of)
        out: list[str] = []
        for row in self._buffer.visible(asserted_as_of=asserted_as_of):
            if row.attribute not in family or row.value_type != "entity":
                continue
            if not isinstance(row.value, str):
                continue
            e, v = row.entity, row.value
            if (e in clos_a and v in clos_b) or (e in clos_b and v in clos_a):
                out.append(f"{e}·{row.attribute}·{v}")
        return out

    def distinct_block(self, a: str, b: str, asserted_as_of: int | None = None) -> list[str]:
        """`distinct_from` edge descriptor(s) relating a's closure to b's — the
        explicit anti-merge primitive (V2 §1, the mirror of `same_as`). A
        non-empty list is a HARD veto: the author declared these definitively
        not the same. Membrane-clean."""
        clos_a = self.closure(a, asserted_as_of)
        clos_b = self.closure(b, asserted_as_of)
        out: list[str] = []
        for row in self._buffer.visible(attribute="distinct_from", asserted_as_of=asserted_as_of):
            if row.value_type != "entity" or not isinstance(row.value, str):
                continue
            e, v = row.entity, row.value
            if (e in clos_a and v in clos_b) or (e in clos_b and v in clos_a):
                out.append(f"{e}·distinct_from·{v}")
        return out

    def relating_edges_between(self, a: str, b: str, asserted_as_of: int | None = None) -> list[str]:
        """Visible NON-identity, NON-containment, entity-valued edges relating
        a's closure to b's (V2 §3a) — the soft "related ⇒ probably distinct"
        signal (round-robin: any relating edge is evidence against identity).
        Spans the lateral family and generic relations (`father_of`, `ally_of`,
        …). Containment is the *hard* veto, handled separately; identity/meta
        rows and `kind` are excluded. Membrane-clean."""
        family = self._containment_family()
        clos_a = self.closure(a, asserted_as_of)
        clos_b = self.closure(b, asserted_as_of)
        out: list[str] = []
        for row in self._buffer.visible(asserted_as_of=asserted_as_of):
            if row.value_type != "entity" or not isinstance(row.value, str):
                continue
            if row.attribute in family or row.attribute in _IDENTITY_ATTRS:
                continue
            if row.attribute in META_ATTRIBUTES or row.attribute in ("kind", "caused_by"):
                continue  # structural/meta edges are not domain relating edges
            if row.entity.startswith("a:") or row.entity.startswith(ATTR_PREFIX):
                continue
            e, v = row.entity, row.value
            if (e in clos_a and v in clos_b) or (e in clos_b and v in clos_a):
                out.append(f"{e}·{row.attribute}·{v}")
        return out

    def _kind_values(self, entity: str) -> set[str]:
        """Lowercased folded-kind value(s) for an entity (winner + contested),
        entity-resolved — the set a §3b non-distinctive-anchor check compares a
        shared name against."""
        fold = self._kind_of(entity) if self._kind_of is not None else None
        if fold is None or fold.winner is None:
            return set()

        def _norm(value, value_type):
            v = self.resolve(value) if value_type == "entity" and isinstance(value, str) else value
            return str(v).strip().lower()

        vals = {_norm(fold.winner.value, fold.winner.value_type)}
        if fold.conflicted:
            for cid in fold.conflicting:
                row = self._buffer.get(cid)
                if row is not None:
                    vals.add(_norm(row.value, row.value_type))
        return vals

    def containment_related(self, a: str, b: str, asserted_as_of: int | None = None) -> bool:
        return bool(self.containment_block(a, b, asserted_as_of))

    def merge(self, a: str, b: str, evidence: str) -> str | None:
        """Identity merge, logged as an event (auditable, reversible by
        retraction). Returns the merge event's entity id, or None if vetoed.

        Non-bypassable containment veto (010): two entities related by a
        containment/location edge are never the same thing (a container is
        not its contents). The veto lives here so a direct/manual merge()
        cannot bypass it — not only at the ingest same_as→maybe_same_as gate.
        A vetoed pair is left distinct; the bad proposal stays unpromoted and
        is repaired forward by retracting the offending edge."""
        if self.containment_related(a, b):
            logger.warning(
                "merge vetoed: %s and %s are containment-related (a thing is "
                "not what holds it); leaving distinct (%s)", a, b, evidence
            )
            return None
        if self.distinct_block(a, b):
            logger.warning(
                "merge vetoed: %s and %s are marked distinct_from; leaving "
                "distinct (%s)", a, b, evidence
            )
            return None
        event_id = f"event:merge_{self._buffer.head() + 1}"
        self._buffer.append(
            entity=event_id, attribute="kind", value="identity_merge",
            status="inferred", role=self._ingestor,
        )
        edge = self._buffer.append(
            entity=a, attribute="same_as", value=b, value_type="entity",
            status="inferred", role=self._ingestor,
        )
        self._buffer.append(
            entity=edge.id, attribute="caused_by", value=event_id, value_type="entity",
            status="inferred", role=self._ingestor,
        )
        self._buffer.append(
            entity=event_id, attribute="evidence", value=evidence,
            status="inferred", role=self._ingestor,
        )
        logger.info("merge %s == %s (%s)", a, b, evidence)
        return event_id

    def maybe_same_as(self, a: str, b: str, evidence: str) -> None:
        """Ambiguity is represented, not forced: the edge survives until
        a force collapses it (split/underdetermined anchors, §11)."""
        edge = self._buffer.append(
            entity=a, attribute="maybe_same_as", value=b, value_type="entity",
            status="assumed", role=self._ingestor,
        )
        self._buffer.append(
            entity=edge.id, attribute="evidence", value=evidence,
            status="assumed", role=self._ingestor,
        )

    # ---------------------------------------------------------------- read

    def resolve(self, entity: str, asserted_as_of: int | None = None) -> str:
        """Canonical representative: the first-seen member of the entity's
        same_as closure (stable across instances — first-seen is log order)."""
        closure = self.closure(entity, asserted_as_of)
        if len(closure) == 1:
            return entity
        first_seen: dict[str, int] = {}
        for row in self._buffer.visible(asserted_as_of=asserted_as_of):
            if row.entity in closure and row.entity not in first_seen:
                first_seen[row.entity] = row.seq
            if (
                row.value_type == "entity"
                and isinstance(row.value, str)
                and row.value in closure
                and row.value not in first_seen
            ):
                first_seen[row.value] = row.seq
        return min(closure, key=lambda e: (first_seen.get(e, 1 << 62), e))

    def closure(self, entity: str, asserted_as_of: int | None = None) -> set[str]:
        edges: dict[str, set[str]] = {}
        for row in self._buffer.visible(attribute="same_as", asserted_as_of=asserted_as_of):
            if row.value_type == "entity":
                edges.setdefault(row.entity, set()).add(row.value)
                edges.setdefault(row.value, set()).add(row.entity)
        out = {entity}
        frontier = [entity]
        while frontier:
            for nxt in edges.get(frontier.pop(), ()):
                if nxt not in out:
                    out.add(nxt)
                    frontier.append(nxt)
        return out

    def candidates(self, entity: str) -> set[str]:
        """Open maybe_same_as edges touching this entity's closure."""
        closure = self.closure(entity)
        out = set()
        for row in self._buffer.visible(attribute="maybe_same_as"):
            if row.entity in closure:
                out.add(row.value)
            elif row.value in closure:
                out.add(row.entity)
        return out

    def name_anchors(self, entity: str) -> set[str]:
        """NAME-class anchors only (names + aliases, lowercased) — the
        high-weight identity signal. Role/title tokens deliberately
        excluded (036: a shared title register must never carry a merge)."""
        closure = self.closure(entity)
        out: set[str] = set()
        for row in self._buffer.visible():
            if row.entity in closure and row.attribute in ("name", "alias") \
                    and isinstance(row.value, str):
                out.add(row.value.strip().lower())
        return out

    def typed_name_anchors(self, entity: str) -> set[tuple[str, str]]:
        """NAME-class anchors as ``(attribute, normalized_text)`` (IDENTITY-
        RECALL-V1 §3): like name_anchors but keeps the name-vs-alias kind so
        the recall gate can weight a proper name above a casual alias.
        ``normalized_text`` is ``strip().lower()`` (the grouping key)."""
        closure = self.closure(entity)
        out: set[tuple[str, str]] = set()
        for row in self._buffer.visible():
            if row.entity in closure and row.attribute in ("name", "alias") \
                    and isinstance(row.value, str):
                out.add((row.attribute, row.value.strip().lower()))
        return out

    def _kind_state(self, a: str, b: str) -> str:
        """Kind relation for the recall gate (§2): 'conflict' (a contested or
        differing kind — never a merge basis), 'present_equal' (both folded
        kinds present and equal), or 'noncommittal' (equal-or-absent)."""
        if self._kind_of is None:
            return "noncommittal"
        ka, kb = self._kind_of(a), self._kind_of(b)
        if (ka is not None and ka.conflicted) or (kb is not None and kb.conflicted):
            return "conflict"

        def _kind_value(fold):
            if fold is None or fold.winner is None:
                return None
            v = fold.winner.value
            # entity-valued kinds resolve through identity (§2): two kind
            # entities later merged are the same kind, not a conflict.
            if fold.winner.value_type == "entity" and isinstance(v, str):
                return self.resolve(v)
            return v

        va, vb = _kind_value(ka), _kind_value(kb)
        if va is not None and vb is not None:
            return "present_equal" if va == vb else "conflict"
        return "noncommittal"

    def _mergeable(self, a: str, b: str) -> bool:
        """The single AUTO-merge gate (used by promote + reconcile), now
        precision-biased (V2 §3): the author individuates through structure and
        the engine only auto-merges the obvious. Any distinctness signal
        downgrades to a proposal — a shared proper `name` merges at any length
        under non-conflicting kind, a shared `alias` merges only if specific
        (>=2 content tokens) with present-equal kind, BUT not if a relating edge
        joins them or the shared anchor is just the type word."""
        if self.resolve(a) == self.resolve(b):
            return False
        if self.containment_related(a, b):     # hard: a thing is not its container
            return False
        if self.distinct_block(a, b):          # hard: explicitly marked distinct (§1)
            return False
        if self.relating_edges_between(a, b):  # soft: related ⇒ probably distinct (§3a)
            return False
        ta, tb = self.typed_name_anchors(a), self.typed_name_anchors(b)
        shared = {t for (_, t) in ta} & {t for (_, t) in tb}
        if not shared:
            return False
        kind = self._kind_state(a, b)
        if kind == "conflict":
            return False
        # §3b: a shared anchor whose text is just the entity's kind value (the
        # *type word*, e.g. name "bedroom" on kind bedroom) is non-distinctive —
        # it does not drive an auto-merge.
        kinds = self._kind_values(a) | self._kind_values(b)
        for text in shared:
            if text in kinds:
                continue  # non-distinctive type-word anchor
            name_strength = ("name", text) in ta or ("name", text) in tb
            if name_strength:
                return True  # non-conflicting kind already ensured
            if kind == "present_equal" and len(_content_tokens(text)) >= 2:
                return True
        return False

    def _has_proposal(self, a: str, b: str) -> bool:
        """A visible maybe_same_as already relates a's closure to b's."""
        clos_a, clos_b = self.closure(a), self.closure(b)
        for row in self._buffer.visible(attribute="maybe_same_as"):
            if not isinstance(row.value, str):
                continue
            if (row.entity in clos_a and row.value in clos_b) or \
                    (row.entity in clos_b and row.value in clos_a):
                return True
        return False

    def promote_identity_proposals(self) -> int:
        """Whole-world promotion pass (036): a maybe_same_as proposal promotes
        to a logged merge iff the unified gate `_mergeable` holds (proper-name
        or specific-alias-with-equal-kind, never a casual single-token alias,
        never a containment pair). Otherwise it stays a proposal for explicit
        host confirmation (#31). Returns merges performed."""
        promoted = 0
        for row in list(self._buffer.visible(attribute="maybe_same_as")):
            a, b = row.entity, row.value
            if not isinstance(b, str):
                continue
            if self._mergeable(a, b):
                ev = self._buffer.visible(entity=row.id, attribute="evidence")
                self.merge(a, b, evidence=(
                    f"promoted from {row.id}: gated coreference"
                    + (f"; proposal evidence: {ev[0].value}" if ev else "")))
                promoted += 1
        if promoted:
            logger.info("identity promotion: %d merge(s)", promoted)
        return promoted

    def reconcile(self) -> int:
        """Global coreference finalize pass (IDENTITY-RECALL-V1): discover
        cross-closure candidates by shared NAME-class text — the cross-chunk
        coreferents that never co-occurred in one extraction pass and so never
        got a within-chunk proposal — and resolve them through the same gate.
        Mergeable candidates merge; the rest are recorded as (deduped)
        maybe_same_as proposals for host adjudication. Then promote any
        pre-existing within-chunk proposals through the same gate. Idempotent.
        Returns merges performed."""
        text_to_closures: dict[str, set[str]] = {}
        for row in self._buffer.visible():
            if row.attribute not in ("name", "alias") or not isinstance(row.value, str):
                continue
            if row.entity.startswith("a:"):
                continue
            rep = self.resolve(row.entity)
            text_to_closures.setdefault(row.value.strip().lower(), set()).add(rep)

        merged = 0
        for _text, reps in text_to_closures.items():
            members = sorted(reps)
            if len(members) < 2:
                continue
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    a, b = members[i], members[j]
                    if self.resolve(a) == self.resolve(b):
                        continue  # collapsed by an earlier merge this pass
                    if self._mergeable(a, b):
                        self.merge(a, b, evidence="reconcile: gated shared-anchor coreference")
                        merged += 1
                    elif (not self.containment_related(a, b)
                          and not self.distinct_block(a, b)
                          and not self._has_proposal(a, b)):
                        # soft-declined (relating edge / non-distinctive anchor /
                        # kind) → adjudicable proposal; HARD-blocked (containment /
                        # distinct_from) pairs are settled, never re-proposed.
                        self.maybe_same_as(a, b, evidence="reconcile: shared anchor, gate declined (adjudicate)")

        merged += self.promote_identity_proposals()
        if merged:
            logger.info("identity reconcile: %d merge(s)", merged)
        return merged

    # ------------------------------------ host reconciliation surface (#31)

    def guarded_merge(self, a: str, b: str, evidence: str) -> dict:
        """Host-authoritative merge through the guarded path (MERGE-RECONCILE-
        VERB-V1/V2). Skips the soft discriminativeness heuristic (the host has
        judged) but NOT the hard vetoes — containment AND `distinct_from`.
        Returns a Receipt."""
        ra = self.resolve(a)
        if ra == self.resolve(b):
            return self._receipt("noop_already_merged", ra)
        blocks = self.containment_block(a, b)
        if blocks:
            return self._receipt("vetoed", ra, reason="containment", blocking_edges=blocks)
        dblocks = self.distinct_block(a, b)
        if dblocks:
            return self._receipt("vetoed", ra, reason="distinct_from", blocking_edges=dblocks)
        event_id = self.merge(a, b, evidence)
        if event_id is None:  # defensive: merge() re-checks both hard vetoes
            return self._receipt(
                "vetoed", ra, reason="containment_or_distinct",
                blocking_edges=self.containment_block(a, b) + self.distinct_block(a, b),
            )
        return self._receipt("merged", self.resolve(a), merge_event_id=event_id)

    def reject(self, a: str, b: str) -> dict:
        """Assert `distinct_from(a, b)` — the sticky "these are definitively
        different" call (V2 §2), complement of confirm/merge. `reconcile`/
        `proposals` never re-surface the pair after this."""
        ra = self.resolve(a)
        if ra == self.resolve(b):
            # contradiction: can't be distinct AND already merged — name the
            # same_as / merge-event ids to retract first; write nothing.
            return self._receipt(
                "conflict_already_merged", ra, reason="already_merged",
                blocking_edges=self._same_as_path_ids(a, b),
            )
        if self.distinct_block(a, b):
            return self._receipt("noop_already_distinct", ra)
        self._buffer.append(
            entity=ra, attribute="distinct_from", value=self.resolve(b),
            value_type="entity", status="stated", role=self._ingestor,
        )
        return self._receipt("rejected", ra)

    def _same_as_path_ids(self, a: str, b: str) -> list[str]:
        """Visible `same_as` assertion ids + their merge-event ids within the
        (now shared) closure of a and b — what the host retracts to undo the
        merge before asserting distinctness (V2 §2)."""
        clos = self.closure(a)
        out: list[str] = []
        for row in self._buffer.visible(attribute="same_as"):
            if (row.entity in clos and isinstance(row.value, str) and row.value in clos):
                out.append(row.id)
                for m in self._buffer.visible(entity=row.id, attribute="caused_by", value_type="entity"):
                    if isinstance(m.value, str):
                        out.append(m.value)
        return out

    def confirm(self, a: str, b: str) -> dict:
        """Promote an existing maybe_same_as proposal through the guarded path.
        Already merged => `noop_already_merged`; otherwise a missing live
        proposal => `no_proposal` (never a silent merge — keeps confirm=
        promote-judged honest vs merge=assert-new). C-014 / Codex post-impl."""
        ra = self.resolve(a)
        if ra == self.resolve(b):
            return self._receipt("noop_already_merged", ra)
        if not self._has_proposal(a, b):
            return self._receipt("no_proposal", ra)
        ev = None
        for row in self._buffer.visible(attribute="maybe_same_as"):
            if not isinstance(row.value, str):
                continue
            clos_a, clos_b = self.closure(a), self.closure(b)
            if (row.entity in clos_a and row.value in clos_b) or \
                    (row.entity in clos_b and row.value in clos_a):
                evr = self._buffer.visible(entity=row.id, attribute="evidence")
                ev = evr[0].value if evr else None
                break
        return self.guarded_merge(a, b, evidence=f"confirmed proposal: {ev or '(no evidence)'}")

    @staticmethod
    def _receipt(outcome, canonical_id, merge_event_id=None, reason=None,
                 blocking_edges=None) -> dict:
        return {
            "outcome": outcome,
            "canonical_id": canonical_id,
            "merge_event_id": merge_event_id,
            "reason": reason,
            "blocking_edges": list(blocking_edges) if blocking_edges else [],
        }

    def _kind_label(self, entity: str) -> str | None:
        """The folded-kind label for one entity: the winner's value, or the
        '/'-joined value SET when the kind fold is contested (so a contested
        side never hides a same-kind overlap — C-015). None if kind absent."""
        fold = self._kind_of(entity) if self._kind_of is not None else None
        if fold is None or fold.winner is None:
            return None

        def _norm(value, value_type):
            return self.resolve(value) if value_type == "entity" and isinstance(value, str) else value

        vals = {str(_norm(fold.winner.value, fold.winner.value_type))}
        if fold.conflicted:
            for cid in fold.conflicting:
                row = self._buffer.get(cid)
                if row is not None:
                    vals.add(str(_norm(row.value, row.value_type)))
        return "/".join(sorted(vals))

    def _kind_pair(self, a: str, b: str) -> str | None:
        """The sorted folded-kind pair for a kind_conflict reason, e.g.
        'object↔place' or (contested) 'narrator/person↔person' (C-014/015).
        The folded kind is the *agnostic* plausibility signal — same-kind is a
        confirm candidate, different-kind a likely reject — without the engine
        parsing host id namespaces."""
        la, lb = self._kind_label(a), self._kind_label(b)
        if la is None or lb is None:
            return None
        return "↔".join(sorted([la, lb]))

    # -------------------------------------- structured triage (TRIAGE-CONTEXT-V1)

    def _relation_family(self, attribute: str) -> str:
        """Declared structural relation family of an attribute (containment /
        lateral / none), with a membership fallback when semantics is unwired."""
        if self._semantics is not None:
            return self._semantics.semantics(attribute).relation_family
        if attribute in self._containment_family():
            return "containment"
        if attribute in ("connects_to", "adjacent_to"):
            return "lateral"
        return "none"

    def _relating_rows_between(self, a: str, b: str) -> list[dict]:
        """All relating edges between a's closure and b's — containment INCLUDED
        — as `{attribute, relation_family, assertion_id}`. The decisive triage
        evidence (round-robin: any relating edge is evidence against identity).
        Excludes identity/meta/kind/caused_by edges and a:/attr: subjects."""
        clos_a, clos_b = self.closure(a), self.closure(b)
        out: list[dict] = []
        for row in self._buffer.visible():
            if row.value_type != "entity" or not isinstance(row.value, str):
                continue
            if row.attribute in _IDENTITY_ATTRS or row.attribute in META_ATTRIBUTES:
                continue
            if row.attribute in ("kind", "caused_by"):
                continue
            if row.entity.startswith("a:") or row.entity.startswith(ATTR_PREFIX):
                continue
            e, v = row.entity, row.value
            if (e in clos_a and v in clos_b) or (e in clos_b and v in clos_a):
                out.append({
                    "attribute": row.attribute,
                    "relation_family": self._relation_family(row.attribute),
                    "assertion_id": row.id,
                })
        return out

    def _kind_context(self, entity: str) -> dict:
        """Per-side kind context for triage: `{entity, value, conflicted}`."""
        fold = self._kind_of(entity) if self._kind_of is not None else None
        if fold is None or fold.winner is None:
            return {"entity": self.resolve(entity), "value": None, "conflicted": False}
        v = fold.winner.value
        if fold.winner.value_type == "entity" and isinstance(v, str):
            v = self.resolve(v)
        return {"entity": self.resolve(entity), "value": v, "conflicted": bool(fold.conflicted)}

    def _candidate_bindings(self, a: str, b: str) -> list[str]:
        """All visible `maybe_same_as` assertion ids relating the closures
        (live bindings are not unique — plural, Codex r1)."""
        clos_a, clos_b = self.closure(a), self.closure(b)
        out: list[str] = []
        for row in self._buffer.visible(attribute="maybe_same_as"):
            if not isinstance(row.value, str):
                continue
            if (row.entity in clos_a and row.value in clos_b) or \
                    (row.entity in clos_b and row.value in clos_a):
                out.append(row.id)
        return out

    def _decline_context(self, a: str, b: str) -> dict:
        """The single source of truth for why the auto-gate did not merge a
        proposal — `code` in the exact order `_mergeable` fails, plus the
        structured evidence. `decline_reason()` formats its string from this."""
        related = self._relating_rows_between(a, b)
        containment = [r for r in related if r["relation_family"] == "containment"]
        ta, tb = self.typed_name_anchors(a), self.typed_name_anchors(b)
        shared = {t for (_, t) in ta} & {t for (_, t) in tb}
        kind = self._kind_state(a, b)

        if containment:
            code = "containment"
        elif any(r["relation_family"] != "containment" for r in related):
            code = "relating_edge"
        elif not shared:
            code = "no_shared_anchor"
        elif kind == "conflict":
            code = "kind_conflict"
        else:
            kinds = self._kind_values(a) | self._kind_values(b)
            distinctive = [t for t in shared if t not in kinds]
            name_texts = ({t for (attr, t) in ta if attr == "name"}
                          | {t for (attr, t) in tb if attr == "name"})
            if any(t in name_texts for t in distinctive):
                code = None          # a distinctive name merges at any length (mirror _mergeable)
            elif not distinctive:
                code = "non_distinctive"
            elif not any(len(_content_tokens(t)) >= 2 for t in distinctive):
                code = "alias_not_specific"
            elif kind != "present_equal":
                code = "kind_absent"
            else:
                code = None          # specific alias + present-equal kind would have merged
        return {
            "code": code,
            "kinds": [self._kind_context(a), self._kind_context(b)],
            "related_rows": related,
            "candidate_bindings": self._candidate_bindings(a, b),
        }

    def decline_reason(self, a: str, b: str) -> str | None:
        """Display/back-compat string, formatted from `_decline_context`'s code
        so string and struct never diverge (recomputed, never stored)."""
        return self._format_decline(a, b, self._decline_context(a, b))

    def _format_decline(self, a: str, b: str, ctx: dict) -> str | None:
        code = ctx["code"]
        if code is None:
            return None
        if code == "kind_conflict":
            pair = self._kind_pair(a, b)
            return f"kind_conflict: {pair}" if pair else "kind_conflict: contested"
        if code == "relating_edge":
            attrs = sorted({r["attribute"] for r in ctx["related_rows"]
                            if r["relation_family"] != "containment"})
            return f"relating_edge: {attrs[0]}" if attrs else "relating_edge"
        return code

    def enumerate_proposals(self) -> list[dict]:
        """Visible un-promoted maybe_same_as as adjudicable proposals, each
        with its recomputed `auto_decline_reason`. De-duplicated by closure
        pair; stale (already-merged) proposals are skipped."""
        out: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for row in self._buffer.visible(attribute="maybe_same_as"):
            if not isinstance(row.value, str):
                continue
            ra, rb = self.resolve(row.entity), self.resolve(row.value)
            if ra == rb:
                continue  # collapsed since proposed
            if self.distinct_block(ra, rb):
                continue  # settled distinct (rejected) — never re-surface (V2 §2)
            key = tuple(sorted([ra, rb]))
            if key in seen:
                continue
            seen.add(key)
            evr = self._buffer.visible(entity=row.id, attribute="evidence")
            ctx = self._decline_context(ra, rb)
            out.append({
                "a": ra, "b": rb,
                "evidence": evr[0].value if evr else None,
                "auto_decline_reason": self._format_decline(ra, rb, ctx),  # display/back-compat
                "auto_decline": ctx,                                # structured machine surface
            })
        return out

    def by_alias(self, alias: str, asserted_as_of: int | None = None) -> set[str]:
        needle = alias.strip().lower()
        hits = set()
        for row in self._buffer.visible(attribute="alias", asserted_as_of=asserted_as_of):
            if row.value == needle:
                hits.add(self.resolve(row.entity, asserted_as_of))
        # Names assert identity too: check 'name' rows.
        for row in self._buffer.visible(attribute="name", asserted_as_of=asserted_as_of):
            if isinstance(row.value, str) and row.value.strip().lower() == needle:
                hits.add(self.resolve(row.entity, asserted_as_of))
        return hits

    # ----------------------------------- AKA-CORRELATION-V1 (the third lane)
    # `aka` is the NON-collapsing identity relation — between `same_as`
    # (collapse) and `distinct_from` (separate). It NEVER enters resolve()/
    # closure() (those read `same_as` only) and NEVER folds by default. It is
    # read only through the explicit, valid-time-gated walkers below.

    def correlation_set(
        self,
        entity: str,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
        frame: str = CANON,
    ) -> set[str]:
        """The connected component of `entity` over visible `aka` edges, each
        independently as-of/frame filtered (transitive — an edge not yet valid
        is never traversed, so no future reveal leaks backward). Computed fresh;
        never stored; never elects a canonical id. Default => {entity}.

        Closure-aware throughout (Cx 057 #1): the start frontier is the entity's
        whole `same_as` closure, and a reached correlated node is expanded
        through ITS `same_as` closure before traversing further — so an `aka`
        edge attached to any closure member is found from any other member
        (retrieval-invariance across the identity model)."""
        edges: dict[str, set[str]] = {}
        for row in self._buffer.visible(
            attribute="aka", frame=frame,
            valid_as_of=valid_as_of, asserted_as_of=asserted_as_of,
        ):
            if row.value_type != "entity" or not isinstance(row.value, str):
                continue
            edges.setdefault(row.entity, set()).add(row.value)
            edges.setdefault(row.value, set()).add(row.entity)
        out = set(self.closure(entity, asserted_as_of))
        frontier = list(out)
        while frontier:
            for nxt in edges.get(frontier.pop(), ()):
                if nxt not in out:
                    for member in self.closure(nxt, asserted_as_of):
                        if member not in out:
                            out.add(member)
                            frontier.append(member)
        return out

    def correlations(
        self,
        entity: str,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
        frame: str = CANON,
    ) -> list[str]:
        """The facets correlated with `entity` as-of — the correlation set minus
        the entity's own `same_as` closure. Ordered first-seen/log order with a
        lexical tie-break (never a canonical election — Cx 056). Writes nothing."""
        cset = self.correlation_set(entity, valid_as_of, asserted_as_of, frame)
        own = self.closure(entity, asserted_as_of)
        facets = cset - own
        if not facets:
            return []
        first_seen: dict[str, int] = {}
        for row in self._buffer.visible(asserted_as_of=asserted_as_of):
            if row.entity in facets and row.entity not in first_seen:
                first_seen[row.entity] = row.seq
            if (row.value_type == "entity" and isinstance(row.value, str)
                    and row.value in facets and row.value not in first_seen):
                first_seen[row.value] = row.seq
        return sorted(facets, key=lambda e: (first_seen.get(e, 1 << 62), e))

    def _aka_relates(self, a: str, b: str, asserted_as_of: int | None = None) -> bool:
        """Whether b is already in a's correlation COMPONENT (Cx 057 #2): the
        transitive connected component, not a one-edge test — so `correlate(A,C)`
        with A-aka-B-aka-C is a noop, matching the read semantics. valid_as_of is
        unfiltered here (any visible aka edge, regardless of reveal time, means
        the pair is already correlated — a duplicate append is redundant)."""
        comp = self.correlation_set(a, valid_as_of=None, asserted_as_of=asserted_as_of)
        return bool(self.closure(b, asserted_as_of) & comp)

    def correlate(
        self, a: str, b: str, evidence: str, valid_from: float | None = None
    ) -> dict:
        """The guarded host correlate verb (mirror of guarded_merge): append a
        non-collapsing `aka` edge unless the pair is marked `distinct_from`
        (hard veto — a contradiction the host must adjudicate). `valid_from` is
        the reveal time. Returns a Receipt:
        `correlated | noop_already_correlated | vetoed_distinct`."""
        ra = self.resolve(a)
        dblocks = self.distinct_block(a, b)
        if dblocks:
            return self._receipt(
                "vetoed_distinct", ra, reason="distinct_from", blocking_edges=dblocks
            )
        if self._aka_relates(a, b):
            return self._receipt("noop_already_correlated", ra)
        edge = self._buffer.append(
            entity=a, attribute="aka", value=b, value_type="entity",
            status="stated", role=self._ingestor, valid_from=valid_from,
        )
        self._buffer.append(
            entity=edge.id, attribute="evidence", value=evidence,
            status="stated", role=self._ingestor,
        )
        rec = self._receipt("correlated", ra)
        rec["aka_assertion_id"] = edge.id
        logger.info("correlate %s aka %s (%s)", a, b, evidence)
        return rec

    def correlation_conflicts(
        self,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
        frame: str = CANON,
    ) -> list[dict]:
        """Pairs carrying BOTH an `aka` and a `distinct_from` between their
        closures (closure-aware, bidirectional) — a contradiction surfaced for
        host adjudication (a raw `aka` authored over a `distinct_from`). The
        guarded `correlate()` prevents this at the source; this read catches the
        raw-ingest path. Deduped by resolved pair.

        The `aka` rows are filtered by `valid_as_of`/`frame`/`asserted_as_of`
        (Cx 057 #3) — an as-of-before-reveal view shows no conflict. NOTE:
        `distinct_from` is global by current engine convention (asserted-axis
        only), so the distinctness side is not valid-time scoped."""
        out: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for row in self._buffer.visible(
            attribute="aka", frame=frame,
            valid_as_of=valid_as_of, asserted_as_of=asserted_as_of,
        ):
            if row.value_type != "entity" or not isinstance(row.value, str):
                continue
            a, b = row.entity, row.value
            dblocks = self.distinct_block(a, b, asserted_as_of)
            if not dblocks:
                continue
            key = tuple(sorted([self.resolve(a, asserted_as_of),
                                self.resolve(b, asserted_as_of)]))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "a": a, "b": b,
                "aka_edge": f"{a}·aka·{b}",
                "distinct_edges": dblocks,
            })
        return out
