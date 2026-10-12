"""The identity registry (whitepaper §11): anchors, aliases,
SAME_AS / MAYBE_SAME_AS, merges as logged events.

The registry is derived: edges are ordinary assertions; the closure is
computed (the connected component over visible same_as edges — at head, one
component map per log version, rebuilt when the log moves and never stored).
A merge appends — late binding leaves every earlier row intact and reachable
through the merged identity. A bad merge is repaired forward by retracting
the edge.
"""

from __future__ import annotations

import logging
import re

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import CONSTITUTIVE, DISPOSITIONAL
from patternbuffer.model import (
    ATTR_PREFIX,
    CANON,
    CONTAINMENT_FAMILY,
    MECHANISM_STATUS,
    META_ATTRIBUTES,
    Assertion,
)
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


# IDENTITY-ROOT-CAUSES-V1 §1: only a name-like anchor is identity evidence. An
# anchor is name-like when it has at most this many raw words (a sentence or
# clause is not a name) and does not open with a speaker-relative possessive
# ("my apprentice" names a different person for every speaker). Frozen:
# changing either is a spec change.
_NAME_MAX_WORDS = 5
_RELATIVE_POSSESSIVES = frozenset({"my", "our", "your", "his", "her", "their", "its"})

# IDENTITY-ROOT-CAUSES-V1 §3: who decided an identity merge.
DECIDED_BY_VALUES = ("host", "statement", "engine")

# The evidence prefixes of merges written before `decided_by` existed, and the
# value each derives (§3). Anything else reads `unknown`, which every policy
# treats as `engine` (the cheaper error: an unclear merge counts as automatic).
_LEGACY_DECIDED_BY = (
    ("reconcile:", "engine"),
    ("promoted from", "engine"),
    ("adjudicate_deferred:", "engine"),
    ("confirmed proposal:", "host"),
    ("retype absorb:", "host"),
)

# The proposal evidence reconcile records for a pair the auto gate declined
# for a named identity reason (§1, §4); any other decline keeps the generic text.
_PROPOSAL_EVIDENCE = {
    "not_name_like": "reconcile: shared anchor not name-like (adjudicate)",
    "frame_owner": "reconcile: frame owner, host confirmation required",
}
_GENERIC_PROPOSAL_EVIDENCE = "reconcile: shared anchor, gate declined (adjudicate)"


# REFER-LEARNING-V1 §2/§7: the `source` receipt prefix of every word refer
# learns. On a `learned_alias` row it is the receipt; on an `alias` row it marks
# a legacy learned alias, written by the retired pre-spec accrual path.
REFER_SOURCE_PREFIX = "refer:tier2:"


def ref_norm(text: str) -> str:
    """The one normalization refer's vocabulary matches under
    (REFER-LEARNING-V1 §5): outer whitespace and case. Interior whitespace
    is kept, as for names — "old  faithful" is not "old faithful"."""
    return text.strip().lower()


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


def _anchor_words(text: str) -> list[str]:
    """The raw words of an anchor (IDENTITY-ROOT-CAUSES-V1 §1(a)): lowercase,
    split on anything that is not a letter, a digit or an apostrophe, every
    word kept — articles and honorifics included. Not `_content_tokens`, which
    drops them: right for comparing names, wrong for spotting a sentence."""
    words = re.findall(r"(?:[^\W_]|')+", text.lower())
    return [w for w in words if any(c.isalnum() for c in w)]


def _name_like(text: str) -> bool:
    """Whether an anchor can be identity evidence (§1): at most five raw words,
    and not opening with a speaker-relative possessive. A non-name-like anchor
    stays a good `alias` row for lookup; only its weight as evidence is gone."""
    words = _anchor_words(text)
    if len(words) > _NAME_MAX_WORDS:
        return False
    return not (words and words[0] in _RELATIVE_POSSESSIVES)


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
        # Late-bound retract/classify providers (SHAPE-FIX-V1 `retype`): the
        # retraction authority lives in TruthMaintenance and the durability
        # verdict in the Classifier — both constructed after the registry, so
        # World wires them (same idiom as set_kind_provider).
        self._retract = None
        self._classify_rows = None
        # Late-bound fold + durability lookups for the durable-contradiction
        # veto (SHAPE-FIX-V1 Win 4, HD 089: the fused-protagonist incident).
        self._fold_of = None
        self._durability_of = None
        # The head-time identity view, derived per buffer log version: every
        # same_as endpoint -> its whole component, each multi-member
        # component's elected representative, and the first-seen seqs that
        # election reads (scanned on first demand only). See _components().
        self._view_version = -1
        self._component_of: dict[str, frozenset[str]] = {}
        self._representative: dict[frozenset[str], str] = {}
        self._first_seen: dict[str, int] | None = None
        # IDENTITY-REPRESENTATIVE-V1 §2: the honoured host designations at
        # head, (seq, id) ascending, scanned once per log version on the first
        # multi-member election and never stored.
        self._designations: list[tuple[int, str]] | None = None
        # IDENTITY-ROOT-CAUSES-V1 §2/§4: two more head-time views, derived per
        # log version and never stored — the retracted-merge edges, and which
        # entities own a `knows:` frame.
        self._retracted_version = -1
        self._retracted_edges: list[tuple[str, str]] = []
        self._owner_version = -1
        self._frame_owner: dict[str, bool] = {}

    def set_kind_provider(self, fn) -> None:
        """Install the kind-fold lookup the recall gate consults (§2)."""
        self._kind_of = fn

    def set_retract_provider(self, fn) -> None:
        """Install the retraction write (TruthMaintenance.retract) `retype` uses."""
        self._retract = fn

    def set_classify_provider(self, fn) -> None:
        """Install the rules-mode classifier pass for rows `retype` appends."""
        self._classify_rows = fn

    def set_fold_provider(self, fn) -> None:
        """Install the general key-fold lookup ((entity, attribute) ->
        FoldResult) the durable-contradiction veto reads through."""
        self._fold_of = fn

    def set_durability_provider(self, fn) -> None:
        """Install the durability lookup (assertion_id -> class)."""
        self._durability_of = fn

    # --------------------------------------------------------------- write

    def add_alias(self, entity: str, alias: str, status: str = "stated",
                  frame: str = CANON) -> None:
        """Append one `alias` row, normalized, in `frame`. Description is
        perspectival (FRAME-SCOPED-IDENTITY-V1 §1(c)): the gate passes the
        item's effective frame, so a name private to Alice stays in Alice's
        frame and only identity reads of that frame see it."""
        self._buffer.append(
            entity=entity, attribute="alias", value=alias.strip().lower(),
            status=status, role=self._ingestor, frame=frame,
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
        # FRAME-SCOPED-IDENTITY-V1 §2: a canon merge veto reads canon only.
        for row in self._buffer.visible(asserted_as_of=asserted_as_of, frame=CANON):
            if row.attribute not in family or row.value_type != "entity":
                continue
            if not isinstance(row.value, str):
                continue
            e, v = row.entity, row.value
            if (e in clos_a and v in clos_b) or (e in clos_b and v in clos_a):
                out.append(f"{e}·{row.attribute}·{v}")
        return out

    def distinct_block(self, a: str, b: str, asserted_as_of: int | None = None,
                       frame: str = CANON) -> list[str]:
        """`distinct_from` edge descriptor(s) relating a's closure to b's — the
        explicit anti-merge primitive (V2 §1, the mirror of `same_as`). A
        non-empty list is a HARD veto: the author declared these definitively
        not the same. Membrane-clean.

        Read in canon (FRAME-SCOPED-IDENTITY-V1 §2: a canon merge veto reads
        canon only). `frame` exists for `correlation_conflicts` alone (§3(b)):
        a contradiction is two edges in ONE frame."""
        clos_a = self.closure(a, asserted_as_of)
        clos_b = self.closure(b, asserted_as_of)
        out: list[str] = []
        for row in self._buffer.visible(attribute="distinct_from",
                                        asserted_as_of=asserted_as_of, frame=frame):
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
        # FRAME-SCOPED-IDENTITY-V1 §2: Alice's belief that two people are kin
        # never blocks canon's merge of them — the signal reads canon only.
        for row in self._buffer.visible(asserted_as_of=asserted_as_of, frame=CANON):
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

    def durable_contradictions(self, a: str, b: str) -> list[str]:
        """Shared attributes where BOTH sides hold present, DURABLE
        (CONSTITUTIVE/DISPOSITIONAL), and CONTRADICTORY folded values — the
        generalization of the kind veto to every standing fact (SHAPE-FIX-V1
        Win 4; HD 089: a retrieval lead and a defense apprentice fused because
        only `kind` was consulted). Two entities whose standing identities
        contradict are probably two things: a soft distinctness signal, same
        tier as a relating edge — auto-merge declines to a proposal; the host's
        guarded `merge` remains available. Transient STATE differences (mood,
        position) never trigger it. Descriptors `attr: va ≠ vb`."""
        if self._fold_of is None or self._durability_of is None:
            return []
        family = self._containment_family()
        clos_a, clos_b = self.closure(a), self.closure(b)

        def authored_attrs(clos: set[str]) -> set[str]:
            out = set()
            # FRAME-SCOPED-IDENTITY-V1 §2: the folds below are canon already;
            # the scan that picks their keys is scoped to match.
            for row in self._buffer.visible(frame=CANON):
                if row.entity not in clos:
                    continue
                if row.attribute in ("name", "alias", "kind") \
                        or row.attribute in _IDENTITY_ATTRS \
                        or row.attribute in META_ATTRIBUTES \
                        or row.attribute in family:
                    continue
                out.add(row.attribute)
            return out

        def norm(winner) -> object:
            v = winner.value
            if winner.value_type == "entity" and isinstance(v, str):
                return self.resolve(v)
            return v.strip().lower() if isinstance(v, str) else v

        out: list[str] = []
        for attr in sorted(authored_attrs(clos_a) & authored_attrs(clos_b)):
            fa, fb = self._fold_of(a, attr), self._fold_of(b, attr)
            if fa.winner is None or fb.winner is None:
                continue
            if norm(fa.winner) == norm(fb.winner):
                continue
            durable = {CONSTITUTIVE, DISPOSITIONAL}
            if self._durability_of(fa.winner.id) in durable \
                    and self._durability_of(fb.winner.id) in durable:
                out.append(f"{attr}: {fa.winner.value!r} vs {fb.winner.value!r}")
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

    def merge(self, a: str, b: str, evidence: str,
              decided_by: str = "engine",
              representative: str | None = None) -> str | None:
        """Identity merge, logged as an event (auditable, reversible by
        retraction). Returns the merge event's entity id, or None if vetoed.

        Non-bypassable containment veto (010): two entities related by a
        containment/location edge are never the same thing (a container is
        not its contents). The veto lives here so a direct/manual merge()
        cannot bypass it — not only at the ingest same_as→maybe_same_as gate.
        A vetoed pair is left distinct; the bad proposal stays unpromoted and
        is repaired forward by retracting the offending edge.

        ``decided_by`` records who decided the merge (IDENTITY-ROOT-CAUSES-V1
        §3): the caller says, nothing is inferred from the evidence text. A
        bare ``merge`` is the engine's own act unless the caller is a host."""
        rows = self._merge_rows(a, b, evidence, decided_by,
                                representative=representative)
        return None if rows is None else rows[0].entity

    def _merge_rows(self, a: str, b: str, evidence: str, decided_by: str,
                    extracted: bool = False,
                    representative: str | None = None) -> list[Assertion] | None:
        """`merge`'s body: re-check both hard vetoes, then append the merge's
        rows — the `identity_merge` event, the `same_as` edge (`inferred`,
        timeless), its `caused_by`, the evidence, who decided it
        (``decided_by``: host | statement | engine) and, for a statement that
        came from prose extraction, `extracted · true` — and return them in
        append order (None when vetoed). A host merge may also name the
        closure's ``representative`` (IDENTITY-REPRESENTATIVE-V1 §1): one more
        row on the event, written last."""
        if decided_by not in DECIDED_BY_VALUES:
            raise ValueError(
                f"decided_by must be one of {DECIDED_BY_VALUES}, got {decided_by!r}")
        if representative is not None:
            if decided_by != "host":
                raise ValueError("only a host merge may name a representative")
            self._check_representative(a, b, representative)
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
        event = self._buffer.append(
            entity=event_id, attribute="kind", value="identity_merge",
            status="inferred", role=self._ingestor,
        )
        edge = self._buffer.append(
            entity=a, attribute="same_as", value=b, value_type="entity",
            status="inferred", role=self._ingestor,
        )
        cause = self._buffer.append(
            entity=edge.id, attribute="caused_by", value=event_id, value_type="entity",
            status="inferred", role=self._ingestor,
        )
        proof = self._buffer.append(
            entity=event_id, attribute="evidence", value=evidence,
            status="inferred", role=self._ingestor,
        )
        decision = self._buffer.append(
            entity=event_id, attribute="decided_by", value=decided_by,
            status="inferred", role=self._ingestor,
        )
        rows = [event, edge, cause, proof, decision]
        if extracted:
            rows.append(self._buffer.append(
                entity=event_id, attribute="extracted", value=True,
                status="inferred", role=self._ingestor,
            ))
        if representative is not None:
            rows.append(self._buffer.append(
                entity=event_id, attribute="representative", value=representative,
                status="inferred", role=self._ingestor,
            ))
        logger.info("merge %s == %s (%s; decided by %s)", a, b, evidence, decided_by)
        return rows

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
        """Canonical representative of the entity's same_as closure: the id the
        latest honoured host designation names (IDENTITY-REPRESENTATIVE-V1 §2),
        else the first-seen member (stable across instances — both are log
        order)."""
        if not self._at_head(asserted_as_of):
            closure = self.closure(entity, asserted_as_of)
            if len(closure) == 1:
                return entity
            designated = self._designated(closure, self._honoured_designations(asserted_as_of))
            if designated is not None:
                return designated
            return self._elect(closure, self._first_seen_scan(closure, asserted_as_of))
        members = self._components().get(entity)
        if members is None or len(members) == 1:
            return entity
        rep = self._representative.get(members)
        if rep is None:
            if self._designations is None:
                self._designations = self._honoured_designations(None)
            rep = self._designated(members, self._designations)
            if rep is None:
                if self._first_seen is None:
                    merged = set()
                    for component in self._component_of.values():
                        if len(component) > 1:
                            merged |= component
                    self._first_seen = self._first_seen_scan(merged, None)
                rep = self._elect(members, self._first_seen)
            self._representative[members] = rep
        return rep

    def closure(self, entity: str, asserted_as_of: int | None = None) -> set[str]:
        if self._at_head(asserted_as_of):
            members = self._components().get(entity)
            return set(members) if members is not None else {entity}
        return self._walk(self._same_as_edges(asserted_as_of), entity)

    # ------------------------------------------- the derived head-time view

    def _at_head(self, asserted_as_of: int | None) -> bool:
        """Whether an asserted-axis bound selects exactly the head view: none,
        or one at/after the head (no row is asserted after the head). Only a
        bound strictly in the past reads the log afresh."""
        return asserted_as_of is None or (
            isinstance(asserted_as_of, (int, float))
            and asserted_as_of >= self._buffer.head()
        )

    def _components(self) -> dict[str, frozenset[str]]:
        """Every same_as endpoint visible at head -> its whole closure, rebuilt
        only when the buffer's log version moves (an append, a rollback). An id
        absent from the map is its own singleton closure."""
        version = self._buffer.log_version
        if self._view_version != version:
            edges = self._same_as_edges(None)
            component_of: dict[str, frozenset[str]] = {}
            for start in edges:
                if start not in component_of:
                    members = frozenset(self._walk(edges, start))
                    for member in members:
                        component_of[member] = members
            self._component_of = component_of
            self._representative = {}
            self._first_seen = None
            self._designations = None
            self._view_version = version
        return self._component_of

    def _same_as_edges(self, asserted_as_of: int | None) -> dict[str, set[str]]:
        """Visible canon same_as rows as an undirected adjacency map. Identity
        is canon's (FRAME-SCOPED-IDENTITY-V1 §2): a `same_as` outside canon is
        inert, so a belief frame can never hold a merge of its own, and every
        frame resolves ids through this one closure."""
        edges: dict[str, set[str]] = {}
        for row in self._buffer.visible(attribute="same_as",
                                        asserted_as_of=asserted_as_of, frame=CANON):
            if row.value_type == "entity":
                edges.setdefault(row.entity, set()).add(row.value)
                edges.setdefault(row.value, set()).add(row.entity)
        return edges

    @staticmethod
    def _walk(edges: dict[str, set[str]], entity: str) -> set[str]:
        """The connected component of `entity` in `edges` (itself if absent)."""
        out = {entity}
        frontier = [entity]
        while frontier:
            for nxt in edges.get(frontier.pop(), ()):
                if nxt not in out:
                    out.add(nxt)
                    frontier.append(nxt)
        return out

    def _first_seen_scan(self, members, asserted_as_of: int | None) -> dict[str, int]:
        """The seq at which each of `members` first appears in a visible canon
        row, as subject or as an entity value — the log order election reads.
        The election is "first seen among canon rows" (FRAME-SCOPED-IDENTITY-V1
        §2): a closure is canon's, and so is the name it is served under."""
        first_seen: dict[str, int] = {}
        for row in self._buffer.visible(asserted_as_of=asserted_as_of, frame=CANON):
            if row.entity in members and row.entity not in first_seen:
                first_seen[row.entity] = row.seq
            if (
                row.value_type == "entity"
                and isinstance(row.value, str)
                and row.value in members
                and row.value not in first_seen
            ):
                first_seen[row.value] = row.seq
        return first_seen

    def _honoured_designations(self, asserted_as_of: int | None) -> list[tuple[int, str]]:
        """Every honoured representative designation visible at the read, as
        (seq, id) in log order (IDENTITY-REPRESENTATIVE-V1 §2a). One visible
        `representative` row per designation; it is honoured when it carries
        the mechanism mark, and its event has a visible `kind · identity_merge`,
        a visible marked `decided_by · host`, and — for an edge-producing
        merge — a visible `same_as` edge named by a visible `caused_by`. An
        event no `caused_by` ever names is a re-point event and needs no edge.
        Membership of the closure is the caller's test. A world with no
        designation costs one query, which returns nothing."""
        buf = self._buffer
        rows = [r for r in buf.visible(attribute="representative", frame=CANON,
                                       asserted_as_of=asserted_as_of)
                if r.status == MECHANISM_STATUS["representative"]
                and isinstance(r.value, str)]
        if not rows:
            return []
        events = sorted({r.entity for r in rows})

        def per_event(attribute: str) -> list[Assertion]:
            out: list[Assertion] = []
            for i in range(0, len(events), 500):
                out.extend(buf.visible(entity_in=events[i:i + 500],
                                       attribute=attribute, frame=CANON,
                                       asserted_as_of=asserted_as_of))
            return out

        merges = {r.entity for r in per_event("kind") if r.value == "identity_merge"}
        host: set[str] = set()
        seen: set[str] = set()
        for r in per_event("decided_by"):
            if (r.entity not in seen and r.status == MECHANISM_STATUS["decided_by"]
                    and r.value in DECIDED_BY_VALUES):
                seen.add(r.entity)
                if r.value == "host":
                    host.add(r.entity)
        live_edges = {r.id for r in buf.visible(attribute="same_as", frame=CANON,
                                                asserted_as_of=asserted_as_of)}
        dead_edges = {r.id for r in buf.retracted_targets(
            attribute="same_as", frame=CANON, asserted_as_of=asserted_as_of)}
        # event -> whether a live edge names it. Only a `caused_by` on a
        # `same_as` row counts (any other row naming the event is not its edge),
        # and a link or edge a retraction hides still marks the event as
        # edge-producing, so it is withdrawn rather than read as a re-point.
        named: dict[str, bool] = {}
        for r in buf.visible(attribute="caused_by", value_type="entity",
                             frame=CANON, asserted_as_of=asserted_as_of):
            if r.value in host and r.entity in live_edges:
                named[r.value] = True
            elif r.value in host and r.entity in dead_edges:
                named.setdefault(r.value, False)
        for r in buf.retracted_targets(attribute="caused_by", frame=CANON,
                                       asserted_as_of=asserted_as_of):
            if r.value in host and (r.entity in live_edges or r.entity in dead_edges):
                named.setdefault(r.value, False)
        return [(r.seq, r.value) for r in rows
                if r.entity in merges and r.entity in host
                and named.get(r.entity, True)]

    @staticmethod
    def _designated(closure, designations: list[tuple[int, str]]) -> str | None:
        """The id named by the latest honoured designation that is a member of
        `closure`, or None (first-seen then elects)."""
        for _seq, ident in reversed(designations):
            if ident in closure:
                return ident
        return None

    def _check_representative(self, a: str, b: str, representative: str) -> None:
        """A designation must name `a`, `b` or a member of either's closure;
        anything else raises before any write (IDENTITY-REPRESENTATIVE-V1 §1)."""
        if representative not in self.closure(a) | self.closure(b):
            raise ValueError(
                f"representative {representative!r} is not a member of the "
                f"closure of {a!r} or {b!r}")

    def _repoint(self, a: str, evidence: str, representative: str) -> dict:
        """The re-point event (IDENTITY-REPRESENTATIVE-V1 §1a): on a pair
        already one closure, exactly four timeless `inferred` canon rows and
        no `same_as`, no `caused_by` — the event's kind, evidence, `decided_by
        · host` and the `representative`. Returns the Receipt: the outcome
        stays `noop_already_merged`, `canonical_id` is the closure's elected
        representative after the write, `repointed` is true."""
        event_id = f"event:merge_{self._buffer.head() + 1}"
        for attribute, value in (("kind", "identity_merge"), ("evidence", evidence),
                                 ("decided_by", "host"),
                                 ("representative", representative)):
            self._buffer.append(
                entity=event_id, attribute=attribute, value=value,
                status="inferred", role=self._ingestor,
            )
        logger.info("re-point %s -> %s (%s)", a, representative, evidence)
        receipt = self._receipt("noop_already_merged", self.resolve(a),
                                merge_event_id=event_id)
        receipt["repointed"] = True
        return receipt

    @staticmethod
    def _elect(closure, first_seen: dict[str, int]) -> str:
        """The first-seen member of a closure (lexical tie-break)."""
        return min(closure, key=lambda e: (first_seen.get(e, 1 << 62), e))

    def candidates(self, entity: str) -> set[str]:
        """Open canon maybe_same_as edges touching this entity's closure
        (FRAME-SCOPED-IDENTITY-V1 §2: proposals are canon's)."""
        closure = self.closure(entity)
        out = set()
        for row in self._buffer.visible(attribute="maybe_same_as", frame=CANON):
            if row.entity in closure:
                out.add(row.value)
            elif row.value in closure:
                out.add(row.entity)
        return out

    def typed_name_anchors(self, entity: str) -> set[tuple[str, str]]:
        """NAME-class anchors as ``(attribute, normalized_text)`` (IDENTITY-
        RECALL-V1 §3): like name_anchors but keeps the name-vs-alias kind so
        the recall gate can weight a proper name above a casual alias.
        ``normalized_text`` is ``strip().lower()`` (the grouping key)."""
        closure = self.closure(entity)
        out: set[tuple[str, str]] = set()
        # FRAME-SCOPED-IDENTITY-V1 §2: a canon merge anchors on canon names
        # only — a name known only to Alice never drives canon identity.
        for row in self._buffer.visible(frame=CANON):
            if row.entity in closure and row.attribute in ("name", "alias") \
                    and isinstance(row.value, str):
                out.add((row.attribute, row.value.strip().lower()))
        return out

    # -------------------- IDENTITY-ROOT-CAUSES-V1: decided-against and frame owners

    def _retracted_merge_edges(self) -> list[tuple[str, str]]:
        """The endpoints of every canon `same_as` row a marked retraction hides
        at head (§2) — each one a recorded decision that these two were judged
        not one thing. One buffer query per log version, like `_components()`;
        the head view only (the automatic paths are head-time)."""
        version = self._buffer.log_version
        if self._retracted_version != version:
            self._retracted_edges = [
                (row.entity, row.value)
                for row in self._buffer.retracted_targets(
                    attribute="same_as", frame=CANON)
                if row.value_type == "entity" and isinstance(row.value, str)
            ]
            self._retracted_version = version
        return self._retracted_edges

    def _settled_apart(self, a: str, b: str) -> bool:
        """Whether a retracted merge settles a and b apart (§2): some retracted
        `same_as` edge has one endpoint in a's closure and the other in b's.
        Only the edge counts — retracting the `identity_merge` event alone
        changes no closure and settles nothing. The automatic paths never
        merge such a pair and `reconcile` never re-proposes it; the host verbs
        (`merge`, `confirm`) can still decide it."""
        edges = self._retracted_merge_edges()
        if not edges:
            return False
        clos_a, clos_b = self.closure(a), self.closure(b)
        return any((x in clos_a and y in clos_b) or (x in clos_b and y in clos_a)
                   for x, y in edges)

    def _owns_frame(self, entity: str) -> bool:
        """Whether the entity's closure owns a frame (§4): some member `m` has
        a visible row in frame `knows:m`. A frame owner is a point of view;
        fusing two of them fuses who knows what. Derived per log version."""
        version = self._buffer.log_version
        if self._owner_version != version:
            self._frame_owner = {}
            self._owner_version = version
        for member in self.closure(entity):
            owns = self._frame_owner.get(member)
            if owns is None:
                owns = self._frame_owner[member] = bool(
                    self._buffer.visible(frame=f"knows:{member}"))
            if owns:
                return True
        return False

    def merge_decided_by(self, merge_event_id: str,
                         asserted_as_of: int | None = None) -> str:
        """Who decided a merge event (§3): `host`, `statement`, `engine` — or
        `unknown` for a merge written before `decided_by` existed whose
        evidence names no verb (every policy treats `unknown` as `engine`).
        The row is honored only on a `kind · identity_merge` event that carries
        this component's mark (`inferred`); a forged row decides nothing. Old
        merges derive from their evidence prefix at read time — nothing is
        written for them."""
        buf = self._buffer
        kinds = buf.visible(entity=merge_event_id, attribute="kind",
                            frame=CANON, asserted_as_of=asserted_as_of)
        if not any(k.value == "identity_merge" and k.status == "inferred"
                   for k in kinds):
            return "unknown"
        for row in buf.visible(entity=merge_event_id, attribute="decided_by",
                               frame=CANON, asserted_as_of=asserted_as_of):
            if row.status == "inferred" and row.value in DECIDED_BY_VALUES:
                return row.value
        for row in buf.visible(entity=merge_event_id, attribute="evidence",
                               frame=CANON, asserted_as_of=asserted_as_of):
            text = str(row.value)
            for prefix, derived in _LEGACY_DECIDED_BY:
                if text.startswith(prefix):
                    return derived
        return "unknown"

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
        """The single AUTO-merge gate (used by promote + reconcile): whether
        `_auto_verdict` is `merge`."""
        return self._auto_verdict(a, b) == "merge"

    def _auto_verdict(self, a: str, b: str) -> str:
        """The AUTO-merge decision, precision-biased (V2 §3): the author
        individuates through structure and the engine only auto-merges the
        obvious. Any distinctness signal downgrades to a proposal — a shared
        proper `name` merges at any length under non-conflicting kind, a shared
        `alias` merges only if specific (>=2 content tokens) with present-equal
        kind, BUT not if a relating edge joins them or the shared anchor is
        just the type word.

        IDENTITY-ROOT-CAUSES-V1: only a name-like anchor counts as evidence
        (§1); a pair a retracted merge settled apart is never merged (§2); and
        a pair either of whose closures owns a `knows:` frame is left to the
        host (§4). Returns `merge`, or the decline: `settled_apart` (never
        re-proposed), `not_name_like` or `frame_owner` (proposed with their own
        evidence), or `declined` (any other soft or hard decline)."""
        if self.resolve(a) == self.resolve(b):
            return "declined"
        if self.containment_related(a, b):     # hard: a thing is not its container
            return "declined"
        if self.distinct_block(a, b):          # hard: explicitly marked distinct (§1)
            return "declined"
        # FRAME-SCOPED-IDENTITY-V1 §3(c), amending AKA-CORRELATION-V1 §1: `aka`
        # is a SOFT auto-merge block. A timeless same_as would swallow a
        # valid-timed reveal and leak the masked figure's name to before it —
        # the backward leak `aka` exists to prevent. Host-authoritative merges
        # (merge, confirm, retype's absorb) stay available.
        if self._aka_relates(a, b):            # soft: correlated facets are two things
            return "declined"
        # FRAME-SCOPED-IDENTITY-V1 §3(c) (r2): correlate's group-level veto —
        # a canon `distinct_from` between a's correlation group and b's. The
        # merge would put it inside one group (a~b, b distinct_from x: merging
        # a with x joins x to b's group). In `correlate`'s order: after the
        # already-correlated test.
        if self._group_distinct_block(a, b):   # the world says the groups differ
            return "declined"
        # IDENTITY-ROOT-CAUSES-V1 §2: a retracted merge is a decision — settled
        # apart, like the hard blocks, for every automatic purpose.
        if self._settled_apart(a, b):
            return "settled_apart"
        if self.relating_edges_between(a, b):  # soft: related ⇒ probably distinct (§3a)
            return "declined"
        if self.durable_contradictions(a, b):  # soft: standing facts contradict (Win 4)
            return "declined"
        ta, tb = self.typed_name_anchors(a), self.typed_name_anchors(b)
        shared = {t for (_, t) in ta} & {t for (_, t) in tb}
        if not shared:
            return "declined"
        kind = self._kind_state(a, b)
        if kind == "conflict":
            return "declined"
        # §3b: a shared anchor whose text is just the entity's kind value (the
        # *type word*, e.g. name "bedroom" on kind bedroom) is non-distinctive —
        # it does not drive an auto-merge.
        kinds = self._kind_values(a) | self._kind_values(b)
        distinctive = [t for t in shared if t not in kinds]
        # IDENTITY-ROOT-CAUSES-V1 §1: of those, only a name-like anchor is
        # identity evidence; a sentence or a speaker-relative phrase is
        # description. Every shared anchor failing is its own decline.
        evidence = [t for t in distinctive if _name_like(t)]
        if distinctive and not evidence:
            return "not_name_like"
        agreed = False
        for text in evidence:
            name_strength = ("name", text) in ta or ("name", text) in tb
            if name_strength:
                agreed = True  # non-conflicting kind already ensured
                break
            if kind == "present_equal" and len(_content_tokens(text)) >= 2:
                agreed = True
                break
        if not agreed:
            return "declined"
        # IDENTITY-ROOT-CAUSES-V1 §4: a frame owner is a point of view; the
        # engine never fuses two on its own. The host says `confirm`.
        if self._owns_frame(a) or self._owns_frame(b):
            return "frame_owner"
        return "merge"

    def name_collisions(self, frame: str = CANON,
                        valid_as_of: float | None = None) -> list[dict]:
        """Fidelity read (INGESTION-FIDELITY-V1): normalized name/alias anchors
        carried by >1 distinct resolved entity — the coreference-fragmentation
        metric. Grouping is frame/as-of-scoped; per-pair status is computed from
        the identity predicates directly (never the global list-builders, which
        pre-filter hard-blocked/distinct pairs). A group is `live` (a real
        fragmentation the host re-extracts) iff any pair is
        unlinked/auto_declined/typing_slip; correlated/hard-blocked-only groups
        are reported for visibility but flagged resolved. Zero writes."""
        text_to_reps: dict[str, set[str]] = {}
        for row in self._buffer.visible(frame=frame, valid_as_of=valid_as_of):
            if row.attribute not in ("name", "alias") or not isinstance(row.value, str):
                continue
            if row.entity.startswith("a:") or row.entity.startswith(ATTR_PREFIX):
                continue
            text_to_reps.setdefault(
                row.value.strip().lower(), set()).add(self.resolve(row.entity))

        out: list[dict] = []
        for anchor in sorted(text_to_reps):
            reps = sorted(text_to_reps[anchor])
            if len(reps) < 2:
                continue
            pairs: list[dict] = []
            live = False
            for i in range(len(reps)):
                for j in range(i + 1, len(reps)):
                    a, b = reps[i], reps[j]
                    status, reason = self._collision_status(a, b, valid_as_of, frame)
                    entry = {"a": a, "b": b, "status": status}
                    if reason is not None:
                        entry["reason"] = reason
                    pairs.append(entry)
                    if status in ("unlinked", "auto_declined", "typing_slip"):
                        live = True
            # Folded kind per entity (parallel to `entities`) — the host weights
            # cross-kind collisions (person↔place) highest, and the folded kind
            # is truth where the id namespace can lie (a mistyped id). INGESTION-
            # FIDELITY-V1 follow-on (HD 107).
            kinds = [self._kind_label(e) for e in reps]
            out.append({"anchor": anchor, "entities": reps, "kinds": kinds,
                        "pairs": pairs, "live": live})
        return out

    def _collision_status(self, a: str, b: str, valid_as_of: float | None,
                          frame: str) -> tuple[str, str | None]:
        """Why a same-anchor pair isn't one entity — from the per-pair predicates
        in `_mergeable`'s own order (INGESTION-FIDELITY-V1)."""
        if b in self.correlation_set(a, valid_as_of=valid_as_of, frame=frame):
            return "correlated", None                    # an aka facet — not a gap
        if self.containment_block(a, b):
            return "hard_blocked", "containment"
        if self.distinct_block(a, b):
            return "hard_blocked", "distinct_from"
        if self._group_distinct_block(a, b):
            # FRAME-SCOPED-IDENTITY-V1 §3(c) (r2): a canon distinct_from between
            # their correlation groups — reconcile neither merges nor proposes
            # the pair, so it is settled, not a gap for reconcile to close.
            return "hard_blocked", "distinct_group"
        if self._settled_apart(a, b):
            # IDENTITY-ROOT-CAUSES-V1 §2: a retracted merge decided these apart;
            # reconcile neither merges nor re-proposes the pair — settled.
            return "hard_blocked", "retracted_merge"
        if self._kind_state(a, b) == "conflict" and (
                self._slip_asymmetry(a, b) or self._slip_asymmetry(b, a)):
            return "typing_slip", None                   # host fixes with retype(absorb=)
        if self._has_proposal(a, b):                     # a real open maybe_same_as edge
            code = self._decline_context(a, b)["code"]
            if code is not None:
                return "auto_declined", code             # a logged proposal the gate declined
        return "unlinked", None                          # no edge yet — host runs reconcile

    def _has_proposal(self, a: str, b: str) -> bool:
        """A visible canon maybe_same_as already relates a's closure to b's
        (FRAME-SCOPED-IDENTITY-V1 §2)."""
        clos_a, clos_b = self.closure(a), self.closure(b)
        for row in self._buffer.visible(attribute="maybe_same_as", frame=CANON):
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
        # FRAME-SCOPED-IDENTITY-V1 §2: proposals and their evidence are canon's.
        for row in list(self._buffer.visible(attribute="maybe_same_as", frame=CANON)):
            a, b = row.entity, row.value
            if not isinstance(b, str):
                continue
            if self._mergeable(a, b):
                ev = self._buffer.visible(entity=row.id, attribute="evidence",
                                          frame=CANON)
                self.merge(a, b, evidence=(
                    f"promoted from {row.id}: gated coreference"
                    + (f"; proposal evidence: {ev[0].value}" if ev else "")),
                    decided_by="engine")
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
        # FRAME-SCOPED-IDENTITY-V1 §2: canon reconcile reads canon names only.
        for row in self._buffer.visible(frame=CANON):
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
                    verdict = self._auto_verdict(a, b)
                    if verdict == "merge":
                        self.merge(a, b, evidence="reconcile: gated shared-anchor coreference",
                                   decided_by="engine")
                        merged += 1
                    elif verdict == "settled_apart":
                        continue  # IDENTITY-ROOT-CAUSES-V1 §2: decided apart; never re-proposed
                    elif (not self.containment_related(a, b)
                          and not self.distinct_block(a, b)
                          and not self._aka_relates(a, b)
                          and not self._group_distinct_block(a, b)
                          and not self._has_proposal(a, b)):
                        # soft-declined (relating edge / non-distinctive anchor /
                        # kind) → adjudicable proposal; HARD-blocked (containment /
                        # distinct_from) pairs are settled, never re-proposed, and
                        # so is a correlated pair (FRAME-SCOPED-IDENTITY-V1 §3(c)):
                        # two facets of one identity are two things by design —
                        # and so is a pair whose correlation groups a canon
                        # `distinct_from` separates (§3(c), r2).
                        self.maybe_same_as(a, b, evidence=_PROPOSAL_EVIDENCE.get(
                            verdict, _GENERIC_PROPOSAL_EVIDENCE))

        merged += self.promote_identity_proposals()
        if merged:
            logger.info("identity reconcile: %d merge(s)", merged)
        return merged

    # ------------------------------------ host reconciliation surface (#31)

    def guarded_merge(self, a: str, b: str, evidence: str,
                      decided_by: str = "host",
                      representative: str | None = None) -> dict:
        """Host-authoritative merge through the guarded path (MERGE-RECONCILE-
        VERB-V1/V2). Skips the soft discriminativeness heuristic (the host has
        judged) but NOT the hard vetoes — containment AND `distinct_from`. It
        likewise skips the automatic paths' own restraints: a pair a retracted
        merge settled apart, or whose closure owns a frame, merges here
        (IDENTITY-ROOT-CAUSES-V1 §2, §4). Records `decided_by` (host unless
        the caller is the gate). ``representative`` names the id the merged
        closure is served under (IDENTITY-REPRESENTATIVE-V1): it must be a
        member of a's or b's closure (``ValueError`` before any write), it rides
        the merge event, and on a pair already merged it writes a re-point
        event instead. Returns a Receipt."""
        return self._guarded_merge(a, b, evidence, decided_by,
                                   representative=representative)[0]

    def _guarded_merge(self, a: str, b: str, evidence: str, decided_by: str,
                       extracted: bool = False,
                       representative: str | None = None,
                       ) -> tuple[dict, list[Assertion]]:
        """The one guarded-merge body (GATE-AUTHORITY-V1 §2): the Receipt plus
        the rows the merge appended, in append order (none unless `merged`).
        Shared by the porcelain `merge` verb (through `guarded_merge`) and the
        ingest gate's raw `same_as` — no veto logic is copied anywhere."""
        if representative is not None:
            if decided_by != "host":
                raise ValueError("only a host merge may name a representative")
            self._check_representative(a, b, representative)
        ra = self.resolve(a)
        if ra == self.resolve(b):
            if representative is not None:
                return self._repoint(a, evidence, representative), []
            return self._receipt("noop_already_merged", ra), []
        blocks = self.containment_block(a, b)
        if blocks:
            return self._receipt(
                "vetoed", ra, reason="containment", blocking_edges=blocks), []
        dblocks = self.distinct_block(a, b)
        if dblocks:
            return self._receipt(
                "vetoed", ra, reason="distinct_from", blocking_edges=dblocks), []
        rows = self._merge_rows(a, b, evidence, decided_by, extracted, representative)
        if rows is None:  # defensive: _merge_rows re-checks both hard vetoes
            return self._receipt(
                "vetoed", ra, reason="containment_or_distinct",
                blocking_edges=self.containment_block(a, b) + self.distinct_block(a, b),
            ), []
        return self._receipt(
            "merged", self.resolve(a), merge_event_id=rows[0].entity), rows

    def reject(self, a: str, b: str) -> dict:
        """Assert `distinct_from(a, b)` — the sticky "these are definitively
        different" call (V2 §2), complement of confirm/merge. `reconcile`/
        `proposals` never re-surface the pair after this. Returns a Receipt:
        `rejected | noop_already_distinct | conflict_already_merged |
        conflict_already_correlated` (the last when b's closure is in a's
        canon correlation group — FRAME-SCOPED-IDENTITY-V1 §3(d))."""
        ra = self.resolve(a)
        if ra == self.resolve(b):
            # contradiction: can't be distinct AND already merged — name the
            # same_as / merge-event ids to retract first; write nothing.
            return self._receipt(
                "conflict_already_merged", ra, reason="already_merged",
                blocking_edges=self._same_as_path_ids(a, b),
            )
        if self._aka_relates(a, b):
            # FRAME-SCOPED-IDENTITY-V1 §3(d): b's closure is in a's canon
            # correlation group — facets of one identity cannot be definitively
            # different. Name every canon `aka` row inside the group (as
            # conflict_already_merged names the same_as ids); write nothing.
            # Ahead of noop_already_distinct: a pair both correlated and
            # distinct is already a contradiction, and the receipt says so.
            group = self.correlation_set(a, valid_as_of=None, frame=CANON)
            return self._receipt(
                "conflict_already_correlated", ra, reason="already_correlated",
                blocking_edges=self._group_aka_ids(group),
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
        # FRAME-SCOPED-IDENTITY-V1 §2: the closure is canon's, and so are the
        # rows that make it.
        for row in self._buffer.visible(attribute="same_as", frame=CANON):
            if (row.entity in clos and isinstance(row.value, str) and row.value in clos):
                out.append(row.id)
                for m in self._buffer.visible(entity=row.id, attribute="caused_by",
                                              value_type="entity", frame=CANON):
                    if isinstance(m.value, str):
                        out.append(m.value)
        return out

    def confirm(self, a: str, b: str, representative: str | None = None) -> dict:
        """Promote an existing maybe_same_as proposal through the guarded path.
        ``representative`` names the id the merged closure is served under
        (IDENTITY-REPRESENTATIVE-V1); given on an already-merged pair it
        writes a re-point event, and it never writes on `no_proposal`.
        Already merged => `noop_already_merged`; otherwise a missing live
        proposal => `no_proposal` (never a silent merge — keeps confirm=
        promote-judged honest vs merge=assert-new). C-014 / Codex post-impl."""
        if representative is not None:
            self._check_representative(a, b, representative)
        ra = self.resolve(a)
        if ra == self.resolve(b):
            if representative is not None:
                return self._repoint(a, "re-point: confirm", representative)
            return self._receipt("noop_already_merged", ra)
        if not self._has_proposal(a, b):
            return self._receipt("no_proposal", ra)
        ev = None
        # FRAME-SCOPED-IDENTITY-V1 §2: proposals and their evidence are canon's.
        for row in self._buffer.visible(attribute="maybe_same_as", frame=CANON):
            if not isinstance(row.value, str):
                continue
            clos_a, clos_b = self.closure(a), self.closure(b)
            if (row.entity in clos_a and row.value in clos_b) or \
                    (row.entity in clos_b and row.value in clos_a):
                evr = self._buffer.visible(entity=row.id, attribute="evidence",
                                           frame=CANON)
                ev = evr[0].value if evr else None
                break
        return self.guarded_merge(
            a, b, evidence=f"confirmed proposal: {ev or '(no evidence)'}",
            decided_by="host", representative=representative)

    # ------------------------------------------ SHAPE-FIX-V1 (buckets 1 + 2)

    def _distinctive_anchor_tokens(self, entity: str) -> set[str]:
        """Content tokens of the entity's name-class anchors, minus type-word
        anchors (an anchor that IS the kind value carries no identity) and
        anchors that are not name-like (a sentence or a speaker-relative phrase
        is description, not identity: IDENTITY-ROOT-CAUSES-V1 §1)."""
        kinds = self._kind_values(entity)
        out: set[str] = set()
        for _attr, text in self.typed_name_anchors(entity):
            if text in kinds or not _name_like(text):
                continue
            out.update(_content_tokens(text))
        return out

    def _anchor_subsumed(self, a: str, b: str) -> bool:
        """The decisive bucket-1 shape: one side's ENTIRE distinctive
        anchor-token set is contained in the other's — a pure fragment with no
        independent identity signal (`tovin` ⊆ {tovin, beck}). Two sides each
        holding distinctive non-shared tokens are two individuated things
        sharing a token — never decisive."""
        ta, tb = self._distinctive_anchor_tokens(a), self._distinctive_anchor_tokens(b)
        if not ta or not tb:
            return False
        return ta <= tb or tb <= ta

    def adjudicate_deferred(self) -> dict:
        """Merge the structurally-DECISIVE subset of live maybe_same_as
        proposals (SHAPE-FIX-V1 Win 1); return receipts + the residue for host
        adjudication. Opt-in — `reconcile()` is unchanged. Decisive = no hard
        block, zero relating edges, no `aka` correlation (non-collapsing by
        design), kind not in conflict, and anchor subsumption. Deterministic,
        zero model calls, idempotent."""
        merged: list[dict] = []
        seen: set[tuple[str, str]] = set()
        # FRAME-SCOPED-IDENTITY-V1 §2: proposals are canon's.
        for row in list(self._buffer.visible(attribute="maybe_same_as", frame=CANON)):
            if not isinstance(row.value, str):
                continue
            ra, rb = self.resolve(row.entity), self.resolve(row.value)
            if ra == rb:
                continue
            key = tuple(sorted([ra, rb]))
            if key in seen:
                continue
            seen.add(key)
            if self.containment_block(ra, rb) or self.distinct_block(ra, rb):
                continue
            if self.relating_edges_between(ra, rb):
                continue
            if self._aka_relates(ra, rb):
                continue  # correlated facets are two things by design (Cx #3);
                          # the one predicate _mergeable reads too (FSI-V1 §3(c))
            if self._group_distinct_block(ra, rb):
                continue  # a distinct_from separates their groups (FSI-V1 §3(c), r2)
            if self._settled_apart(ra, rb):
                continue  # a retracted merge decided these apart (IRC-V1 §2)
            if self._kind_state(ra, rb) == "conflict":
                continue
            if self.durable_contradictions(ra, rb):
                continue  # standing facts contradict (Win 4) — host judges
            if not self._anchor_subsumed(ra, rb):
                continue
            if self._owns_frame(ra) or self._owns_frame(rb):
                continue  # a point of view: the host confirms (IRC-V1 §4)
            event_id = self.merge(
                ra, rb, evidence="adjudicate_deferred: fragment subsumption",
                decided_by="engine",
            )
            if event_id is not None:
                merged.append(self._receipt(
                    "merged", self.resolve(ra), merge_event_id=event_id))
        if merged:
            logger.info("adjudicate_deferred: %d merge(s)", len(merged))
        return {"merged": merged, "residue": self.enumerate_proposals()}

    def _containment_rows_between(self, a: str, b: str) -> list[Assertion]:
        """The visible containment ROWS relating a's closure to b's — the
        would-be-self-edge artifacts a Case-B retype retracts (row form of
        `containment_block`, which serves descriptors)."""
        family = self._containment_family()
        clos_a, clos_b = self.closure(a), self.closure(b)
        out = []
        # FRAME-SCOPED-IDENTITY-V1 §2: the slip signature is a canon decision.
        for row in self._buffer.visible(frame=CANON):
            if row.attribute not in family or row.value_type != "entity":
                continue
            if not isinstance(row.value, str):
                continue
            e, v = row.entity, row.value
            if (e in clos_a and v in clos_b) or (e in clos_b and v in clos_a):
                out.append(row)
        return out

    def _outgoing_domain_rows(self, entity: str) -> list[Assertion]:
        """Domain facts authored ON the entity's closure — beyond naming, kind,
        identity, and meta. The slip signature's bare-ness measure: incoming
        children do NOT count (they are mis-bound rows about OTHER entities and
        re-point correctly after the absorb)."""
        clos = self.closure(entity)
        out = []
        # FRAME-SCOPED-IDENTITY-V1 §2: the slip signature is a canon decision.
        for row in self._buffer.visible(frame=CANON):
            if row.entity not in clos:
                continue
            if row.attribute in ("name", "alias", "kind") \
                    or row.attribute in _IDENTITY_ATTRS \
                    or row.attribute in META_ATTRIBUTES:
                continue
            out.append(row)
        return out

    def _incoming_children(self, entity: str) -> list[Assertion]:
        """Visible containment rows valued INTO the entity's closure."""
        family = self._containment_family()
        clos = {self.resolve(c) for c in self.closure(entity)}
        # FRAME-SCOPED-IDENTITY-V1 §2: the slip signature is a canon decision.
        return [
            row for row in self._buffer.visible(frame=CANON)
            if row.attribute in family and row.value_type == "entity"
            and isinstance(row.value, str) and self.resolve(row.value) in clos
        ]

    def _slip_asymmetry(self, spurious: str, target: str) -> bool:
        """The Case-B slip signature's structural asymmetry: the spurious side
        authored nothing of its own (outgoing-bare — where the inter-closure
        containment ARTIFACTS don't count: `obj:street in place:street` is
        evidence OF the slip, not independent structure); the target side is
        real (outgoing domain facts OR incoming children). A side with any
        non-artifact structure of its own — the locked chest — never reads as
        spurious, so retype can't bypass the merge veto."""
        artifact_ids = {r.id for r in self._containment_rows_between(spurious, target)}
        own = [r for r in self._outgoing_domain_rows(spurious)
               if r.id not in artifact_ids]
        if own:
            return False
        return bool(self._outgoing_domain_rows(target)
                    or self._incoming_children(target))

    def typing_conflicts(self) -> list[dict]:
        """Read-only surfacing of typing slips (SHAPE-FIX-V1, Cx-mandated):
        same-anchor cross-kind pairs carrying the slip signature. Proposals
        cannot show these — `reconcile()` never re-proposes hard-blocked pairs —
        so without this read the slips are invisible. Zero writes, zero model
        calls; the host adjudicates each with `retype(...)` or leaves it."""
        text_to_reps: dict[str, set[str]] = {}
        # FRAME-SCOPED-IDENTITY-V1 §2: a slip is a canon question, anchored on
        # canon names only — a name living in Marn's frame is not canon's.
        for row in self._buffer.visible(frame=CANON):
            if row.attribute not in ("name", "alias") or not isinstance(row.value, str):
                continue
            if row.entity.startswith("a:") or row.entity.startswith(ATTR_PREFIX):
                continue
            text_to_reps.setdefault(
                row.value.strip().lower(), set()).add(self.resolve(row.entity))
        out: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for text, reps in text_to_reps.items():
            members = sorted(reps)
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    a, b = members[i], members[j]
                    if self.resolve(a) == self.resolve(b):
                        continue
                    key = tuple(sorted([a, b]))
                    if key in seen:
                        continue
                    if self._kind_state(a, b) != "conflict":
                        continue
                    if self._slip_asymmetry(a, b):
                        spurious, target = a, b
                    elif self._slip_asymmetry(b, a):
                        spurious, target = b, a
                    else:
                        continue
                    seen.add(key)
                    artifact_ids = {
                        r.id for r in self._containment_rows_between(spurious, target)
                    }
                    out.append({
                        "spurious": spurious,
                        "target": target,
                        "kinds": [sorted(self._kind_values(spurious)),
                                  sorted(self._kind_values(target))],
                        "shared_anchor": text,
                        # The structural evidence the signature rests on — what
                        # makes one side spurious and the other real.
                        "asymmetry": {
                            "spurious_own_facts": len([
                                r for r in self._outgoing_domain_rows(spurious)
                                if r.id not in artifact_ids]),
                            "target_own_facts": len(
                                self._outgoing_domain_rows(target)),
                            "target_children": len(
                                self._incoming_children(target)),
                        },
                        "artifact_edges": self.containment_block(spurious, target),
                    })
        return sorted(out, key=lambda d: (d["spurious"], d["target"]))

    def retype(self, entity: str, to_kind: str, evidence: str,
               absorb: str | None = None) -> dict:
        """Typing correction — DISTINCT from merge (SHAPE-FIX-V1 Win 2). The
        containment veto correctly blocks merges; it must not block fixing a
        kind slip. Append-only: wrong kind rows are RETRACTED (meta-assertions),
        the correct kind appended and classified.

        Case A (absorb=None): correct one mistyped entity's kind.
        Case B (absorb=target): the entity is a spurious duplicate of `absorb`
        at the wrong kind — verify the slip signature (shared anchor + kind
        conflict + structural asymmetry), retract the slip kind row(s) and ONLY
        the direct inter-closure containment artifacts (would-be self-edges;
        incoming child containment is preserved untouched), then merge through
        the guarded path. A non-slip invocation is `vetoed_not_a_slip` — retype
        is never a veto bypass — and a `to_kind` that is not among the
        target's folded kinds is `vetoed_kind_mismatch` (FRAME-SCOPED-
        IDENTITY-V1 §8); neither writes anything."""
        if self._retract is None:
            raise RuntimeError("no retraction authority wired for retype")
        re_ = self.resolve(entity)
        retracted: list[str] = []

        def _retract_kind_rows(target_entity: str) -> None:
            clos = self.closure(target_entity)
            # FRAME-SCOPED-IDENTITY-V1 §2: a canon retype retracts canon kind
            # rows only — Marn's belief about what the thing is survives.
            for row in self._buffer.visible(attribute="kind", frame=CANON):
                if row.entity not in clos:
                    continue
                v = row.value
                if isinstance(v, str) and v.strip().lower() == str(to_kind).strip().lower() \
                        and absorb is None:
                    continue  # already-correct row survives in Case A
                self._retract(row.id, f"retype: {evidence}")
                retracted.append(row.id)

        if absorb is None:
            kinds = self._kind_values(re_)
            if kinds == {str(to_kind).strip().lower()}:
                receipt = self._receipt("noop_already_kind", re_)
                receipt["retracted"] = []
                return receipt
            _retract_kind_rows(re_)
            row = self._buffer.append(
                entity=re_, attribute="kind", value=to_kind,
                status="stated", role=self._ingestor,
            )
            self._buffer.append(
                entity=row.id, attribute="evidence", value=evidence,
                status="stated", role=self._ingestor,
            )
            if self._classify_rows is not None:
                self._classify_rows([row])
            receipt = self._receipt("retyped", re_)
            receipt["retracted"] = retracted
            receipt["kind_assertion_id"] = row.id
            return receipt

        rt = self.resolve(absorb)
        if re_ == rt:
            # IDENTITY-REPRESENTATIVE-V1 §1b: absorb designates the target, so
            # on a pair already merged it re-points the closure to it.
            receipt = self._repoint(entity, f"retype absorb: {evidence}", absorb)
            receipt["retracted"] = []
            return receipt
        if self.distinct_block(re_, rt):
            receipt = self._receipt(
                "vetoed", re_, reason="distinct_from",
                blocking_edges=self.distinct_block(re_, rt),
            )
            receipt["retracted"] = []
            return receipt
        shared = ({t for _, t in self.typed_name_anchors(re_)}
                  & {t for _, t in self.typed_name_anchors(rt)})
        if (not shared or self._kind_state(re_, rt) != "conflict"
                or not self._slip_asymmetry(re_, rt)):
            receipt = self._receipt("vetoed_not_a_slip", re_)
            receipt["retracted"] = []
            return receipt
        if str(to_kind).strip().lower() not in self._kind_values(rt):
            # FRAME-SCOPED-IDENTITY-V1 §8: absorbing into the target makes the
            # entity the target's kind — a `to_kind` that contradicts it was
            # silently ignored. Refused, after the slip check (a non-slip still
            # receipts vetoed_not_a_slip), with nothing written.
            receipt = self._receipt(
                "vetoed_kind_mismatch", re_, reason="to_kind_not_target_kind")
            receipt["retracted"] = []
            return receipt
        _retract_kind_rows(re_)
        for row in self._containment_rows_between(re_, rt):
            self._retract(row.id, f"retype artifact edge: {evidence}")
            retracted.append(row.id)
        result = self.guarded_merge(re_, rt, evidence=f"retype absorb: {evidence}",
                                    decided_by="host", representative=absorb)
        result["retracted"] = retracted
        return result

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
        # FRAME-SCOPED-IDENTITY-V1 §2: triage evidence for a canon merge is canon.
        for row in self._buffer.visible(frame=CANON):
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
        # FRAME-SCOPED-IDENTITY-V1 §2: proposals are canon's.
        for row in self._buffer.visible(attribute="maybe_same_as", frame=CANON):
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

        contradictions = self.durable_contradictions(a, b)
        if containment:
            code = "containment"
        elif self._aka_relates(a, b):
            # FRAME-SCOPED-IDENTITY-V1 §3(c): right after containment, in
            # _mergeable's order — a proposal between correlated facets is
            # declined by the soft aka block (distinct pairs never list).
            code = "correlated"
        elif self._group_distinct_block(a, b):
            # §3(c) (r2): a canon distinct_from between the two correlation
            # groups, right after `correlated` (correlate's own order). A
            # direct distinct pair never lists; this one does, declined.
            code = "distinct_group"
        elif self._settled_apart(a, b):
            # IDENTITY-ROOT-CAUSES-V1 §2, in _auto_verdict's order: a retracted
            # merge decided this pair apart (an existing proposal still lists).
            code = "settled_apart"
        elif any(r["relation_family"] != "containment" for r in related):
            code = "relating_edge"
        elif contradictions:
            code = "durable_contradiction"
        elif not shared:
            code = "no_shared_anchor"
        elif kind == "conflict":
            code = "kind_conflict"
        else:
            kinds = self._kind_values(a) | self._kind_values(b)
            distinctive = [t for t in shared if t not in kinds]
            # IDENTITY-ROOT-CAUSES-V1 §1: only name-like anchors are evidence.
            evidence = [t for t in distinctive if _name_like(t)]
            name_texts = ({t for (attr, t) in ta if attr == "name"}
                          | {t for (attr, t) in tb if attr == "name"})
            if not distinctive:
                code = "non_distinctive"
            elif not evidence:
                code = "not_name_like"
            elif any(t in name_texts for t in evidence):
                code = None          # a distinctive name merges at any length (mirror _mergeable)
            elif not any(len(_content_tokens(t)) >= 2 for t in evidence):
                code = "alias_not_specific"
            elif kind != "present_equal":
                code = "kind_absent"
            else:
                code = None          # specific alias + present-equal kind would have merged
            if code is None and (self._owns_frame(a) or self._owns_frame(b)):
                code = "frame_owner"  # IRC-V1 §4: would have merged, the host confirms
        return {
            "code": code,
            "kinds": [self._kind_context(a), self._kind_context(b)],
            "related_rows": related,
            "durable_contradictions": contradictions,
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
        if code == "durable_contradiction":
            cs = ctx.get("durable_contradictions") or []
            return f"durable_contradiction: {cs[0]}" if cs else code
        if code == "distinct_group":
            edges = self._group_distinct_block(a, b)
            return f"distinct_group: {edges[0]}" if edges else code
        return code

    def enumerate_proposals(self) -> list[dict]:
        """Visible un-promoted maybe_same_as as adjudicable proposals, each
        with its recomputed `auto_decline_reason`. De-duplicated by closure
        pair; stale (already-merged) proposals are skipped."""
        out: list[dict] = []
        seen: set[tuple[str, str]] = set()
        # FRAME-SCOPED-IDENTITY-V1 §2: proposals and their evidence are canon's.
        for row in self._buffer.visible(attribute="maybe_same_as", frame=CANON):
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
            evr = self._buffer.visible(entity=row.id, attribute="evidence", frame=CANON)
            ctx = self._decline_context(ra, rb)
            out.append({
                "a": ra, "b": rb,
                "evidence": evr[0].value if evr else None,
                "auto_decline_reason": self._format_decline(ra, rb, ctx),  # display/back-compat
                "auto_decline": ctx,                                # structured machine surface
            })
        return out

    def identity_conflicts(self, asserted_as_of: int | None = None) -> list[dict]:
        """Canon `same_as` closures (two or more members) that hold a pair the
        guarded merge would veto — a canon containment-family row
        (entity-valued) or a canon `distinct_from` row with both endpoints in
        the closure, at any valid time, the vetoes' own predicate
        (FRAME-SCOPED-IDENTITY-V1 §4). A raw or legacy `same_as` could merge
        such a pair before GATE-AUTHORITY-V1 routed raw rows through the
        guarded merge, and a `distinct_from` written later inside a closure by
        raw ingest lands the same way; nothing else says so.

        One entry per closure, sorted by `canonical_id`:
        `{canonical_id, members (sorted), containment_edges, distinct_edges,
        same_as: [{assertion_id, edge, merge_event_id[, decided_by]}]}` — edge
        lists in log order, `same_as` listing every canon `same_as` row inside
        the closure, `merge_event_id` from the row's `caused_by` (None for a
        raw row, which then has no `decided_by`; otherwise `decided_by` is
        `host` | `statement` | `engine` | `unknown`, IDENTITY-ROOT-CAUSES-V1 §3). The
        host decides which `same_as` to retract; the engine chooses no cut.
        Canon only (identity is canon's) and read-only."""
        edges = self._same_as_edges(asserted_as_of)
        component_of: dict[str, int] = {}
        components: list[set[str]] = []
        for start in edges:
            if start in component_of:
                continue
            members = self._walk(edges, start)
            for member in members:
                component_of[member] = len(components)
            components.append(members)
        if not components:
            return []
        family = self._containment_family()
        found: dict[int, dict[str, list]] = {}
        for row in self._buffer.visible(frame=CANON, asserted_as_of=asserted_as_of):
            if row.value_type != "entity" or not isinstance(row.value, str):
                continue
            index = component_of.get(row.entity)
            if index is None or component_of.get(row.value) != index:
                continue
            bucket = found.setdefault(
                index, {"containment": [], "distinct": [], "same_as": []})
            if row.attribute in family:
                bucket["containment"].append(f"{row.entity}·{row.attribute}·{row.value}")
            elif row.attribute == "distinct_from":
                bucket["distinct"].append(f"{row.entity}·distinct_from·{row.value}")
            elif row.attribute == "same_as":
                bucket["same_as"].append(row)
        out: list[dict] = []
        for index, bucket in found.items():
            if not bucket["containment"] and not bucket["distinct"]:
                continue
            members = components[index]
            same_as = []
            for row in bucket["same_as"]:
                causes = self._buffer.visible(
                    entity=row.id, attribute="caused_by", value_type="entity",
                    frame=CANON, asserted_as_of=asserted_as_of)
                entry = {
                    "assertion_id": row.id,
                    "edge": f"{row.entity}·same_as·{row.value}",
                    "merge_event_id": causes[0].value if causes else None,
                }
                if causes and isinstance(causes[0].value, str):
                    # IDENTITY-ROOT-CAUSES-V1 §3: who decided the merge (a raw
                    # row with no merge event has no decision to report).
                    entry["decided_by"] = self.merge_decided_by(
                        causes[0].value, asserted_as_of)
                same_as.append(entry)
            out.append({
                "canonical_id": self.resolve(next(iter(members)), asserted_as_of),
                "members": sorted(members),
                "containment_edges": bucket["containment"],
                "distinct_edges": bucket["distinct"],
                "same_as": same_as,
            })
        return sorted(out, key=lambda entry: entry["canonical_id"])

    def by_alias(self, alias: str, asserted_as_of: int | None = None,
                 frame: str = CANON) -> set[str]:
        """Entities an authored name or alias names exactly, identity-resolved,
        as of a log position: refer's tier 1a (whitepaper §9). Names assert
        identity too. Aliases match like names (REFER-LEARNING-V1 §5): both
        sides under `ref_norm`, so an alias stored as "The Memory Core"
        answers "the memory core". A legacy learned alias is not authored
        vocabulary and is skipped here; tier 1d reads it (§7). Description is
        perspectival (FRAME-SCOPED-IDENTITY-V1 §2): the rows are read in
        `frame` only, with no canon fallback for a non-canon frame — a name
        private to Alice resolves in Alice's frame, never in canon's."""
        rows = self._vocabulary_matches(alias, ("name", "alias"), asserted_as_of,
                                        frame=frame)
        legacy = self._legacy_learned(rows, asserted_as_of)
        return {self.resolve(row.entity, asserted_as_of)
                for row in rows if row.id not in legacy}

    def by_learned_alias(self, alias: str, asserted_as_of: int | None = None,
                         frame: str = CANON) -> set[str]:
        """Entities refer has learned `alias` as a word for (REFER-LEARNING-V1
        §3), identity-resolved, as of a log position: `learned_alias` rows and
        legacy learned aliases (§7). Read only by refer's tier 1d, after the
        world's own vocabulary found nothing. A `learned_alias` is never
        identity: no anchor, merge or collision read sees it."""
        rows = self._vocabulary_matches(alias, ("alias", "learned_alias"), asserted_as_of,
                                        frame=frame)
        legacy = self._legacy_learned(rows, asserted_as_of)
        return {self.resolve(row.entity, asserted_as_of)
                for row in rows if row.attribute == "learned_alias" or row.id in legacy}

    def _legacy_learned(self, rows: list[Assertion], asserted_as_of: int | None) -> set[str]:
        """Ids of the `alias` rows among `rows` that refer's retired accrual
        path wrote: those carrying a `source` row that starts
        `refer:tier2:` (REFER-LEARNING-V1 §7). One query, over the matching
        alias rows only. Never rewritten or hidden: every other read still
        sees them as the `alias` rows they are, identity anchors included.
        Reads every frame: the gate writes a row's `source` receipt in canon
        whatever frame the row itself is in."""
        ids = [row.id for row in rows if row.attribute == "alias"]
        if not ids:
            return set()
        return {
            src.entity
            for src in self._buffer.visible(
                entity_in=ids, attribute="source", asserted_as_of=asserted_as_of)
            if isinstance(src.value, str) and src.value.startswith(REFER_SOURCE_PREFIX)
        }

    def _vocabulary_matches(
        self, text: str, attributes: tuple[str, ...], asserted_as_of: int | None,
        frame: str = CANON,
    ) -> list[Assertion]:
        """The visible `attributes` rows whose string value equals `text`
        under `ref_norm` (REFER-LEARNING-V1 §5): the one read set behind
        refer's vocabulary, as of the caller's log position (§4).

        The frame half of this read is FRAME-SCOPED-IDENTITY-V1 §2's: rows
        are read in `frame` only, with no canon fallback for a non-canon frame,
        once, for names, aliases and learned words alike
        (§4: one frame rule for all of refer's vocabulary)."""
        needle = ref_norm(text)
        return [
            row for row in self._buffer.visible(
                attribute_in=list(attributes), asserted_as_of=asserted_as_of,
                frame=frame)
            if isinstance(row.value, str) and ref_norm(row.value) == needle
        ]

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

    # A correlation group (FRAME-SCOPED-IDENTITY-V1 §3) is the connected
    # component `correlation_set` computes: `aka` edges, each expanded through
    # the canon closure. The verbs that write or decide canon identity
    # (correlate, the auto-merger, reject) take it over canon `aka` edges at
    # every valid time — a merge or a `distinct_from` is timeless, so it
    # contradicts a reveal whenever the reveal lands. `correlation_conflicts`
    # takes it over its frame's edges, as-of.

    def _group_distinct_edges(self, group_a: set[str], group_b: set[str]) -> list[str]:
        """Descriptors of the canon `distinct_from` rows with one endpoint in
        `group_a` and the other in `group_b`, in log order
        (FRAME-SCOPED-IDENTITY-V1 §3(a))."""
        out: list[str] = []
        for row in self._buffer.visible(attribute="distinct_from", frame=CANON):
            if row.value_type != "entity" or not isinstance(row.value, str):
                continue
            e, v = row.entity, row.value
            if (e in group_a and v in group_b) or (e in group_b and v in group_a):
                out.append(f"{e}·distinct_from·{v}")
        return out

    def _group_distinct_block(self, a: str, b: str) -> list[str]:
        """Descriptors of the canon `distinct_from` rows between a's correlation
        group and b's, at every valid time — `correlate`'s group-level veto
        (FRAME-SCOPED-IDENTITY-V1 §3(a)). The auto-merger reads the same
        predicate (§3(c), r2): merging a with b would put a `distinct_from`
        inside one group, a contradiction `correlate` refuses to make. With no
        `aka` edge on either side the groups are the two closures, so this is
        `distinct_block` again."""
        return self._group_distinct_edges(
            self.correlation_set(a, valid_as_of=None, frame=CANON),
            self.correlation_set(b, valid_as_of=None, frame=CANON),
        )

    def _group_aka_ids(self, group: set[str]) -> list[str]:
        """Assertion ids of every canon `aka` row inside `group` (both
        endpoints in it), at every valid time, in log order — what a host
        retracts to undo a correlation (FRAME-SCOPED-IDENTITY-V1 §3(d))."""
        return [
            row.id for row in self._buffer.visible(attribute="aka", frame=CANON)
            if row.value_type == "entity" and isinstance(row.value, str)
            and row.entity in group and row.value in group
        ]

    def correlate(
        self, a: str, b: str, evidence: str, valid_from: float | None = None
    ) -> dict:
        """The guarded host correlate verb (mirror of guarded_merge): append a
        non-collapsing `aka` edge unless the pair is marked `distinct_from`
        (hard veto — a contradiction the host must adjudicate). `valid_from` is
        the reveal time. Returns a Receipt:
        `correlated | noop_already_correlated | vetoed_distinct`.

        The veto acts on whole correlation groups (FRAME-SCOPED-IDENTITY-V1
        §3(a)): after the direct check and the already-correlated noop (both in
        their old order), a canon `distinct_from` with one endpoint in a's
        group and the other in b's vetoes too — appending the edge would join
        two ids the world says are different. `blocking_edges` names them."""
        ra = self.resolve(a)
        dblocks = self.distinct_block(a, b)
        if dblocks:
            return self._receipt(
                "vetoed_distinct", ra, reason="distinct_from", blocking_edges=dblocks
            )
        if self._aka_relates(a, b):
            return self._receipt("noop_already_correlated", ra)
        group_blocks = self._group_distinct_block(a, b)
        if group_blocks:
            return self._receipt(
                "vetoed_distinct", ra, reason="distinct_from",
                blocking_edges=group_blocks,
            )
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
        """Every `distinct_from` in `frame` whose endpoints lie in one
        correlation group of `frame` as-of — a contradiction surfaced for host
        adjudication (a raw `aka` authored over a `distinct_from`). The guarded
        `correlate()` prevents this at the source; this read catches the
        raw-ingest path. One entry per resolved pair (FRAME-SCOPED-IDENTITY-V1
        §3(b)).

        A contradiction is two edges in ONE frame: the group is built from the
        frame's `aka` rows, each filtered on both time axes (Cx 057 #3 — an
        as-of-before-reveal view shows no conflict), and the `distinct_from`
        rows are the frame's own, valid-time-blind as before (asserted axis
        only). Alice's `aka` beside canon's `distinct_from` is contested truth,
        not a contradiction to retract.

        Direct entries come first, in log order of their `aka` row: a pair
        joined by one `aka` row, `{a, b, aka_edge, distinct_edges, aka_path:
        [aka_edge]}`. Group entries follow, in `distinct_from` log order:
        `{a, b, aka_edge: None, aka_path, distinct_edges}`, where `aka_path`
        is the shortest group path from a to b (neighbours visited in sorted
        order). A direct entry wins its pair."""
        out: list[dict] = []
        seen: set[tuple[str, str]] = set()
        aka_rows = [
            row for row in self._buffer.visible(
                attribute="aka", frame=frame,
                valid_as_of=valid_as_of, asserted_as_of=asserted_as_of,
            )
            if row.value_type == "entity" and isinstance(row.value, str)
        ]
        for row in aka_rows:
            a, b = row.entity, row.value
            dblocks = self.distinct_block(a, b, asserted_as_of, frame=frame)
            if not dblocks:
                continue
            key = tuple(sorted([self.resolve(a, asserted_as_of),
                                self.resolve(b, asserted_as_of)]))
            if key in seen:
                continue
            seen.add(key)
            edge = f"{a}·aka·{b}"
            out.append({
                "a": a, "b": b,
                "aka_edge": edge,
                "distinct_edges": dblocks,
                "aka_path": [edge],
            })
        # The frame's correlation groups over closure representatives: an
        # `aka` edge on any closure member joins the whole closure (the
        # `correlation_set` expansion). Between two representatives, the first
        # edge in log order names the hop.
        hops: dict[str, dict[str, str]] = {}
        for row in aka_rows:
            ra = self.resolve(row.entity, asserted_as_of)
            rb = self.resolve(row.value, asserted_as_of)
            if ra == rb:
                continue
            edge = f"{row.entity}·aka·{row.value}"
            hops.setdefault(ra, {}).setdefault(rb, edge)
            hops.setdefault(rb, {}).setdefault(ra, edge)
        for row in self._buffer.visible(attribute="distinct_from", frame=frame,
                                        asserted_as_of=asserted_as_of):
            if row.value_type != "entity" or not isinstance(row.value, str):
                continue
            a, b = row.entity, row.value
            ra, rb = self.resolve(a, asserted_as_of), self.resolve(b, asserted_as_of)
            key = tuple(sorted([ra, rb]))
            if key in seen:
                continue
            path = self._aka_path(hops, ra, rb)
            if path is None:
                continue
            seen.add(key)
            out.append({
                "a": a, "b": b,
                "aka_edge": None,
                "aka_path": path,
                "distinct_edges": self.distinct_block(a, b, asserted_as_of, frame=frame),
            })
        return out

    @staticmethod
    def _aka_path(hops: dict[str, dict[str, str]], start: str, target: str) -> list[str] | None:
        """The `aka` descriptors along the shortest path from `start` to
        `target` over `hops` (representative -> neighbour -> descriptor), a
        breadth-first walk visiting neighbours in sorted order; None when the
        two are not in one group, or are one closure (no `aka` joins them)."""
        if start == target:
            return None
        parent: dict[str, str | None] = {start: None}
        frontier = [start]
        while frontier:
            following: list[str] = []
            for node in frontier:
                for neighbour in sorted(hops.get(node, {})):
                    if neighbour in parent:
                        continue
                    parent[neighbour] = node
                    if neighbour == target:
                        path: list[str] = []
                        current = neighbour
                        while parent[current] is not None:
                            previous = parent[current]
                            path.append(hops[previous][current])
                            current = previous
                        return path[::-1]
                    following.append(neighbour)
            frontier = following
        return None
