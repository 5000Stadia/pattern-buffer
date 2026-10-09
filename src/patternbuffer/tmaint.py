"""Truth maintenance: conflict detection (derived) and retraction (log).

A conflict is a folded key whose served rows disagree — both rows coexist
in the log untouched (whitepaper §5.1/§7.2). The flag stands until an
explicit retraction/supersession resolves it; resolution is never required
for the flag to exist, and a silent merge is the failure the chapter test's
feature 8 exists to catch.

Conflicts are computed on read, never stored (FRAME-SCOPED-IDENTITY-V1 §5):
`open_conflicts(frame, as_of)` derives them from the rows visible in one
frame, so a flag is scoped to the asked perspective, honest about time, and
never stale. The retired `sidecar_conflicts` table is neither created, filled
nor read; a file that has one keeps an inert copy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import Classifier
from patternbuffer.indexes import Indexes
from patternbuffer.model import ATTR_PREFIX, CANON, Assertion
from patternbuffer.roles import WriterRole
from patternbuffer.semantics import AttributeSemantics

logger = logging.getLogger(__name__)


class AtomicAbort(Exception):
    """Raised by an aborted `atomic=True` ingest / `commit_set` (ATOMIC-
    ACTIVATION-V1 §B6). Emitted ONLY after rollback is confirmed — the set is
    fully rolled back, nothing visible. Public import: `patternbuffer.AtomicAbort`.

    Fields (types frozen):
    - `cause`: `"gate_skip"` (a receipt-and-continue skip — malformed id / cycle /
      self-edge — aborted the set) or `"exception"` (a condition that RAISES on
      the non-atomic path — authority, semantics, unknown retract target, or an
      unexpected error).
    - `skipped`: the skip-receipt records `{entity, attribute, value, reason}`
      (the non-atomic path's shape), plus `detail` only on a record that
      carries one (the bad time coordinate of an `invalid_valid_time` skip,
      FOLD-CORRECTNESS-V1 §6; the authored form of a swapped inverse item,
      GATE-INVERSE-ALIAS-V1; the bad field, the merge veto or the declaration
      source of a GATE-AUTHORITY-V1 §0 code); `[]` when `cause="exception"`.
    - `error`: `None` when `cause="gate_skip"`; `{type, message}` otherwise.
    """

    def __init__(self, cause: str, skipped: list, error: dict | None) -> None:
        self.cause = cause
        self.skipped = skipped
        self.error = error
        super().__init__(
            f"atomic set aborted (cause={cause!r}, "
            f"skipped={len(skipped)}, error={error})")


@dataclass(frozen=True, slots=True)
class Conflict:
    entity: str
    attribute: str
    frame: str
    kind: str  # 'constitutive_contradiction' | 'cross_source'
    assertion_ids: tuple[str, ...]


class TruthMaintenance:
    def __init__(
        self,
        buffer: PatternBuffer,
        classifier: Classifier,
        indexes: Indexes,
        role: WriterRole,
        semantics: AttributeSemantics | None = None,
    ) -> None:
        self._buffer = buffer
        self._classifier = classifier
        self._indexes = indexes
        self._role = role
        self._semantics = semantics or AttributeSemantics(buffer)

    def open_conflicts(
        self,
        frame: str = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> list[Conflict]:
        """The conflicted folds of one frame, as of both axes — computed on
        read, never stored (FRAME-SCOPED-IDENTITY-V1 §5).

        Keys come from the rows visible in `frame` (an observer frame reads
        through its §7 names): `(resolve(entity), fold key)`, the containment
        family reported as `in`, skipping `a:`/`attr:` subjects and set-valued
        attributes. Only a key with two or more visible rows is folded (a
        conflict needs two). Each conflicted fold is one `Conflict`, `kind`
        `constitutive_contradiction` when its winner is CONSTITUTIVE, else
        `cross_source`; `frame` echoes the requested string. Sorted by
        `(entity, attribute)`; writes nothing.

        Invariant: a key is listed iff `state(entity, attribute, frame,
        as_of)` is `conflicted`."""
        family_key = self._indexes.fold_attribute("in")
        counts: dict[tuple[str, str], int] = {}
        for row in self._buffer.visible(
            frame=frame, valid_as_of=valid_as_of, asserted_as_of=asserted_as_of,
        ):
            if (
                row.entity.startswith("a:")
                or row.entity.startswith(ATTR_PREFIX)
                or self._semantics.is_set_valued(row.attribute)
            ):
                continue
            attribute = ("in" if self._indexes.fold_attribute(row.attribute) == family_key
                         else row.attribute)
            key = (self._indexes.resolve_entity(row.entity), attribute)
            counts[key] = counts.get(key, 0) + 1
        conflicts: list[Conflict] = []
        for (entity, attribute), rows in sorted(counts.items()):
            if rows < 2:
                continue
            result = self._indexes.fold_key(
                entity, attribute, frame, valid_as_of, asserted_as_of)
            if result.conflicted:
                kind = (
                    "constitutive_contradiction"
                    if result.winner is not None
                    and self._classifier.durability(result.winner.id) == "CONSTITUTIVE"
                    else "cross_source"
                )
                conflicts.append(
                    Conflict(entity, attribute, frame, kind, result.conflicting)
                )
        return conflicts

    def scan(self) -> list[Conflict]:
        """Every open conflict in every frame, at head: the union of
        `open_conflicts` over each frame with a visible row, sorted by
        `(entity, attribute, frame)`. A below-porcelain all-frames read
        (FRAME-SCOPED-IDENTITY-V1 §5) — it writes nothing and stores
        nothing; it returns the list."""
        frames = sorted({row.frame for row in self._buffer.visible()})
        conflicts: list[Conflict] = []
        for frame in frames:
            conflicts.extend(self.open_conflicts(frame))
        conflicts.sort(key=lambda c: (c.entity, c.attribute, c.frame))
        if conflicts:
            logger.info("truth maintenance: %d open conflict(s)", len(conflicts))
        return conflicts

    def retract(self, target: Assertion | str, reason: str) -> Assertion:
        """Append a retraction meta-assertion. The target survives in the
        log; folds exclude it from the retraction's asserted_at onward.

        Target validation (ATOMIC-ACTIVATION-V1 §C1/F5): the target must exist
        in the **pre-call committed log** — raise otherwise (no orphan `retracts`
        row). Under an open unit, a target minted by an earlier op in the same
        set (its `a:<seq>` id is not public vocabulary, §B3) is NOT eligible:
        its seq lies above the unit's pre-call head. Standalone (no unit) this is
        just "the target exists in the current log."""
        target_id = target if isinstance(target, str) else target.id
        row = self._buffer.get(target_id)
        precall_head = self._buffer.unit_precall_head
        eligible = row is not None and (precall_head is None
                                        or row.seq <= precall_head)
        if not eligible:
            raise ValueError(
                f"retract target {target_id!r} is not a committed assertion "
                "(a staged, in-set-minted id is not an eligible target)")
        return self._buffer.append(
            entity=target_id,
            attribute="retracts",
            value=reason,
            status="retracted",
            role=self._role,
        )
