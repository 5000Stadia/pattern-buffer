"""The knowledge section of `Indexes`: who holds a value for a key
(`who_knows`, the transpose of `frame_diff`) and the value test it shares with
`state(value=)`.
"""

from __future__ import annotations

from typing import Any

from patternbuffer.indexes._core import FoldResult, _FAMILY_KEY
from patternbuffer.model import Assertion


class KnowledgeMixin:
    """The knowledge section of `Indexes`."""

    # --------------------------------- WHO-KNOWS-INVERSE-V1 (transpose of frame_diff)

    def who_knows(
        self,
        entity: str,
        attribute: str,
        value: Any = None,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> list[str]:
        """The `knows:*` observer frames for which `(entity, attribute)` is KNOWN
        (WHO-KNOWS-INVERSE-V1) — the inverse of `frame_diff`, computed not stored
        (a `known_by` edge would breach the membrane). A frame knows the fact iff
        its fold serves a concrete value (a placeholder is not knowledge) and,
        when `value` is given, `fold_matches` holds: a set's folded value is its
        members, an accrue key's its total (READ-SURFACE-V1 §5). Folded-not-raw:
        a superseded/retracted belief no longer counts. Candidate frames are
        key/closure-scoped (only frames that touched the key), never a full-log
        scan. Own-`knows:`-frame membership; the `knows:O ∪ public` union stays
        a host heuristic."""
        entity = self._resolve(entity)
        fa = self.fold_attribute(attribute)
        attrs = sorted(self._semantics.containment_family()) if fa == _FAMILY_KEY else [attribute]
        closure = sorted(self._closure_of(entity))
        candidates: set[str] = set()
        for row in self._buffer.visible(
            entity_in=closure, attribute_in=attrs,
            valid_as_of=valid_as_of, asserted_as_of=asserted_as_of,
        ):
            if row.frame.startswith("knows:"):
                candidates.add(row.frame)
        known: list[str] = []
        for frame in candidates:
            result = self.fold_key(entity, attribute, frame, valid_as_of, asserted_as_of)
            if result.winner is None or result.winner.value_type == "unresolved":
                continue
            if value is None or self.fold_matches(result, value):
                known.append(frame)
        return sorted(known)

    def fold_matches(self, fold: FoldResult, value: Any) -> bool:
        """Whether a fold's served value matches `value` (READ-SURFACE-V1 §5),
        the one test `who_knows` and `state(value=)` share. False when the fold
        serves nothing or an unresolved placeholder. An accrue key matches on
        its folded total, numerically (`Decimal` and `int` compare exactly, as
        in `where`); a set-valued key when some current member value-matches;
        any other key when the served row value-matches (identity-aware,
        `_value_matches`)."""
        if fold.winner is None or fold.winner.value_type == "unresolved":
            return False
        if fold.quantity is not None:
            return self._is_numeric(value) and fold.quantity == value
        if fold._value_rows:
            return any(self._value_matches(row, value) for row in fold._value_rows)
        return self._value_matches(fold.winner, value)

    def _value_matches(self, winner: Assertion, value: Any) -> bool:
        """Identity-aware value match: entity values compare by resolved id,
        literals by equality."""
        if winner.value_type == "entity" and isinstance(winner.value, str) \
                and isinstance(value, str):
            return self._resolve(winner.value) == self._resolve(value)
        return winner.value == value
