"""The durability classifier and its rebuildable sidecar (whitepaper §5).

Durability is an index, not truth (P1): the class is a judgment about a
fact, keyed by assertion id, living in a sidecar table that can be
dropped and re-derived from the untouched log at any time. Deterministic
guardrails run first and short-circuit; the injected model judges only
what they leave ambiguous, under asymmetric-cost defaults.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from patternbuffer.buffer import PatternBuffer
from patternbuffer.codec import json_default
from patternbuffer.model import (
    ASSERTION_ID_RE,
    ATTR_PREFIX,
    META_ATTRIBUTES,
    RESOLUTION_POLICY,
    SEMANTICS_PREDICATES,
    TASK_CLASSIFY,
    TASK_CLASSIFY_BATCH,
    WORLD_PHYSICS_SUBJECT,
    Assertion,
    is_event_row,
    task_schema,
)
from patternbuffer.semantics import AttributeSemantics

logger = logging.getLogger(__name__)

CONSTITUTIVE = "CONSTITUTIVE"
DISPOSITIONAL = "DISPOSITIONAL"
STATE = "STATE"
EVENT = "EVENT"
DURABILITIES = frozenset({CONSTITUTIVE, DISPOSITIONAL, STATE, EVENT})
# The classes the MODEL may assign (CLASSIFIER-EVENT-SAFETY-V1). EVENT is
# excluded: it is the one verdict that ERASES a row from every fold
# (indexes drops EVENT before folding), so a model flip STATE->EVENT is a
# silent read-completeness failure. Occurrence-ness is structural — assigned
# only by the deterministic guardrails (event:/caused_by/META) or host
# declaration — never sampled per-row by the model. The model judges only the
# standing-durability spectrum; ambiguity defaults to STATE (visible,
# correctable), never erased.
_STANDING_DURABILITIES = frozenset({CONSTITUTIVE, DISPOSITIONAL, STATE})

# Review threshold: low-confidence CONSTITUTIVE verdicts silently corrupt
# every future materialization (whitepaper §5.1), so they are flagged.
_REVIEW_FLOOR = 0.6

# CONTAINMENT-DURABILITY-V1 §3: a model verdict of CONSTITUTIVE on a
# containment row below this confidence is stored STATE. A CONSTITUTIVE row
# outranks every later STATE move on its key, so a guessed permanence freezes
# a movable where it was first seen; a wrong STATE on a real fixture costs
# little. Not per-world: `attr:in` is inviolable core.
CONTAINMENT_CONSTITUTIVE_FLOOR = 0.95

_SIDECAR_SCHEMA = """
CREATE TABLE IF NOT EXISTS sidecar_classification (
  assertion_id     TEXT PRIMARY KEY,
  durability       TEXT NOT NULL,
  class_confidence REAL NOT NULL,
  needs_review     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sidecar_classifier_meta (
  key   TEXT PRIMARY KEY,
  value INTEGER NOT NULL
);
"""

# CONTAINMENT-DURABILITY-V1 §4: the one sentence both prompts carry.
_CONTAINMENT_CLAUSE = (
    "An object's location is STATE unless the object is clearly built into "
    "the place (a door, a window, a fixed fitting); when unsure, STATE."
)

_MODEL_SCHEMA = {
    "title": TASK_CLASSIFY,
    "type": "object",
    "properties": {
        "durability": {"enum": sorted(_STANDING_DURABILITIES)},
        "class_confidence": {"type": "number"},
    },
    "required": ["durability", "class_confidence"],
}

_BATCH_SCHEMA = {
    "title": TASK_CLASSIFY_BATCH,
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "durability": {"enum": sorted(_STANDING_DURABILITIES)},
                    "class_confidence": {"type": "number"},
                },
                "required": ["index", "durability", "class_confidence"],
            },
        }
    },
    "required": ["verdicts"],
}


@dataclass(frozen=True, slots=True)
class Classification:
    assertion_id: str
    durability: str
    class_confidence: float
    needs_review: bool


class Classifier:
    """classify(assertion, world_context) -> {durability, class_confidence}.

    Writes the sidecar only — never the log (role matrix §12).
    """

    def __init__(
        self,
        buffer: PatternBuffer,
        model: Callable[[str, dict], Any],
        semantics: AttributeSemantics | None = None,
    ) -> None:
        self._buffer = buffer
        self._model = model
        self._semantics = semantics or AttributeSemantics(buffer)
        # Read-through memo of sidecar rows (assertion id -> Classification, or
        # None when unclassified). Valid while neither the buffer's log version
        # (a rollback can discard sidecar writes) nor the connection's change
        # count (any row write — this classifier's, another one's, a rebuild's)
        # has moved since it was filled. Derived and disposable, like the
        # sidecar itself.
        self._memo: dict[str, Classification | None] = {}
        self._memo_key: tuple[int, int] | None = None
        # WORLD-SERVICE-V1 §7c: moves at every verdict write (and sidecar
        # rebuild), so a holder can tell a sidecar-only change from no change.
        # In memory only, never stored; meaningful within this instance.
        self._verdict_version = 0
        conn = buffer.raw_connection()
        conn.executescript(_SIDECAR_SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO sidecar_classifier_meta (key, value)"
            " VALUES ('version', 0)"
        )
        conn.commit()

    # ------------------------------------------------------------ judgment

    def _guardrails(self, row: Assertion) -> tuple[str, float] | None:
        """Deterministic short-circuits. Return None to defer to the model."""
        if row.value_type == "delta":
            return STATE, 1.0
        # An event row (EVENTS-ONE-READER-V1 §1): the predicate the fold and
        # the event reader share; the delta test above is its own first half.
        if is_event_row(row) or row.attribute == "caused_by":
            return EVENT, 1.0
        if row.attribute in {"name", "alias"}:
            return CONSTITUTIVE, 0.95  # identity anchors
        if row.attribute in META_ATTRIBUTES:
            # Meta-assertions ride with their subject; they never fold as
            # world facts. Classified EVENT-like for lens purposes: immutable.
            return EVENT, 1.0
        if row.entity.startswith(ATTR_PREFIX) and row.attribute in SEMANTICS_PREDICATES:
            # READ-SURFACE-V1 §1 step 5: a semantics declaration is
            # vocabulary bookkeeping. The four older predicates are META and
            # stop above; this catches the durability pin's own row, whose
            # predicate is also an ordinary domain word (not META).
            return EVENT, 1.0
        if row.entity == WORLD_PHYSICS_SUBJECT and row.attribute == RESOLUTION_POLICY:
            return CONSTITUTIVE, 1.0  # READ-SURFACE-V1 §7 step 6: the world's physics
        if row.value_type == "unresolved":
            return STATE, 1.0  # a thunk occupies its key like mutable state
        pin = self._semantics.durability_pin(row.attribute)
        if pin is not None:
            # READ-SURFACE-V1 §1 step 8: the host pinned this attribute's
            # class, so a pinned row never reaches the model on any path
            # (inline, batch, rules, a seal, classify_all, rebuild).
            return pin, 1.0
        if self._semantics.is_containment(row.attribute):
            if row.attribute in {"held_by", "worn_by", "carried_by"}:
                return STATE, 0.95  # things held by agents are movable
            if row.entity.startswith("place:"):
                # A place's containment is part of what the place IS — the
                # study does not move out of the home (fixture sub-rule).
                return CONSTITUTIVE, 0.9
            if row.entity.startswith("person:"):
                # CONTAINMENT-DURABILITY-V1 §1: beings move. A being is a
                # subject id in the `person:` namespace as written; the
                # classifier sees the buffer only, not identity closure.
                return STATE, 0.95
            if self._declared_fixture(row):
                # CONTAINMENT-DURABILITY-V1 §2: the host declared this thing
                # built into its container, as of the row's own position.
                return CONSTITUTIVE, 1.0
            # other objects: fixture vs movable is a judgment (falls to the
            # model, whose CONSTITUTIVE needs CONTAINMENT_CONSTITUTIVE_FLOOR)
        elif self._semantics.is_structural(row.attribute):
            return CONSTITUTIVE, 1.0
        if ASSERTION_ID_RE.fullmatch(row.entity):
            # GATE-AUTHORITY-V1 §8: a row about an assertion that no rule
            # above decides (learned_at_wallclock, a proposal's evidence, host
            # metadata like last_confirmed) is bookkeeping: STATE 0.5, the
            # verdict classify="rules" already gives it, never a paid model
            # call. Not EVENT — that would erase host-authored assertion
            # metadata from state(). Every derived read skips assertion
            # subjects, so no fold changes.
            return STATE, 0.5
        return None

    def _declared_fixture(self, row: Assertion) -> bool:
        """Whether the host declared ``row.entity`` a fixture, as of ``row``'s
        own log position (CONTAINMENT-DURABILITY-V1 §2). Reads the canon
        `fixture` rows visible then (retractions honoured); of the
        literal-boolean ones in force at the row's valid time, the
        latest-asserted decides. In force (r1.6): open-ended, and timeless or
        dated no later than the row's own ``valid_from`` (so a dated
        declaration never covers a timeless row). The subject is the id as
        written, with no identity closure. Bounded at ``row.seq``, so a
        declaration written later never reclassifies the row, on first
        classification or on rebuild()."""
        at = row.valid_from
        declared = [
            r for r in self._buffer.visible(
                entity=row.entity, attribute="fixture", frame="canon",
                asserted_as_of=row.seq)
            if r.valid_to is None
            and (r.valid_from is None or (at is not None and r.valid_from <= at))
            and r.value_type == "literal" and isinstance(r.value, bool)
        ]
        if not declared:
            return False
        return max(declared, key=lambda r: (r.asserted_at, r.seq)).value is True

    def _apply_containment_floor(
        self, row: Assertion, durability: str, confidence: float
    ) -> tuple[str, float]:
        """The one normalization of a model-judged containment verdict
        (CONTAINMENT-DURABILITY-V1 §3), shared by classify() and
        _classify_batch(): a CONSTITUTIVE below CONTAINMENT_CONSTITUTIVE_FLOOR
        is stored STATE, the model's confidence kept. Logged, not stored."""
        if (durability == CONSTITUTIVE
                and confidence < CONTAINMENT_CONSTITUTIVE_FLOOR
                and self._semantics.is_containment(row.attribute)):
            logger.info(
                "containment floor: %s judged CONSTITUTIVE at %.3f (< %.2f); "
                "stored STATE", row.id, confidence, CONTAINMENT_CONSTITUTIVE_FLOOR)
            return STATE, confidence
        return durability, confidence

    def classify(self, row: Assertion) -> Classification:
        verdict = self._guardrails(row)
        if verdict is not None:
            durability, confidence = verdict
        else:
            durability, confidence = self._apply_containment_floor(
                row, *self._ask_model(row))
        needs_review = durability == CONSTITUTIVE and confidence < _REVIEW_FLOOR
        c = Classification(row.id, durability, confidence, needs_review)
        self._store(c)
        return c

    def classify_if_guarded(self, row: Assertion) -> Classification | None:
        """SESSION-GUARDRAILS-V1: apply only the deterministic guardrails.

        When a guardrail decides the row, store and return the same
        ``Classification`` that ``classify`` / ``classify_rows`` would store for
        it. Otherwise return ``None``: no model call, nothing stored."""
        verdict = self._guardrails(row)
        if verdict is None:
            return None
        durability, confidence = verdict
        c = Classification(
            row.id, durability, confidence,
            durability == CONSTITUTIVE and confidence < _REVIEW_FLOOR,
        )
        self._store(c)
        return c

    def _ask_model(self, row: Assertion) -> tuple[str, float]:
        prompt = (
            "Classify the lifetime of this fact about a world.\n"
            f"Subject: {row.entity}\nAttribute: {row.attribute}\n"
            f"Value: {json.dumps(row.value, default=json_default)}\n\n"
            "CONSTITUTIVE: what the thing IS (identity, structure, fixtures, era). "
            "True at every moment unless the world is re-authored.\n"
            "DISPOSITIONAL: what it TENDS to be (habits, roles, recurring behavior). "
            "Generally true but defeasible.\n"
            "STATE: what it is RIGHT NOW (positions of movables, moods, conditions). "
            "One event could flip it.\n\n"
            "The mutability test resolves most ambiguity: could one event flip this "
            "without re-authoring the world? -> STATE. When the text presents a "
            "property as an enduring baseline of the person — a physical trait, a "
            "capability, a continuing role — prefer CONSTITUTIVE (what they are) or "
            "DISPOSITIONAL (how they tend) over STATE; a temporary ability or "
            "condition, or a time-relative quantity (age), remains STATE. "
            "Asymmetric defaults: an "
            "ambiguous property is STATE. " + _CONTAINMENT_CLAUSE
        )
        try:
            out = self._model(prompt, task_schema(_MODEL_SCHEMA))
            durability = out["durability"]
            confidence = float(out["class_confidence"])
            if durability not in _STANDING_DURABILITIES:
                raise ValueError(durability)
        except Exception:
            logger.exception("classifier model call failed for %s; defaulting", row.id)
            # Asymmetric default: ambiguous property -> STATE. Containment
            # returns CONSTITUTIVE 0.5 here, which the caller's containment
            # floor stores as STATE: a failed call never makes a location
            # permanent (CONTAINMENT-DURABILITY-V1 §3).
            if self._semantics.is_containment(row.attribute):
                return CONSTITUTIVE, 0.5
            return STATE, 0.5
        return durability, confidence

    # ------------------------------------------------------------- sidecar

    @property
    def verdict_version(self) -> int:
        """A counter that moves at each verdict write and each sidecar rebuild
        (WORLD-SERVICE-V1 §7c). Never stored; the stored ``version`` is the
        salience cache's key, this one is a holder's cheap change signal."""
        return self._verdict_version

    def _store(self, c: Classification) -> None:
        self._verdict_version += 1
        conn = self._buffer.raw_connection()
        conn.execute(
            "INSERT OR REPLACE INTO sidecar_classification"
            " (assertion_id, durability, class_confidence, needs_review)"
            " VALUES (?, ?, ?, ?)",
            (c.assertion_id, c.durability, c.class_confidence, int(c.needs_review)),
        )
        conn.execute(
            "UPDATE sidecar_classifier_meta SET value = value + 1"
            " WHERE key = 'version'"
        )
        conn.commit()

    @property
    def version(self) -> int:
        row = self._buffer.raw_connection().execute(
            "SELECT value FROM sidecar_classifier_meta WHERE key = 'version'"
        ).fetchone()
        return int(row[0]) if row else 0

    def set(self, assertion_id: str, durability: str, confidence: float = 1.0) -> None:
        """Judgment injection for components that hold the world context
        (e.g. the resolver knows invented contents are movables). Sidecar
        only — the log is untouched, and rebuild() re-derives."""
        if durability not in DURABILITIES:
            raise ValueError(durability)
        self._store(Classification(assertion_id, durability, confidence, False))

    def get(self, assertion_id: str) -> Classification | None:
        conn = self._buffer.raw_connection()
        if not isinstance(assertion_id, str):
            return self._read(conn, assertion_id)   # odd ids keep the uncached path
        key = (self._buffer.log_version, conn.total_changes)
        if key != self._memo_key:
            self._memo = {}
            self._memo_key = key
        try:
            return self._memo[assertion_id]
        except KeyError:
            c = self._memo[assertion_id] = self._read(conn, assertion_id)
            return c

    @staticmethod
    def _read(conn: Any, assertion_id: str) -> Classification | None:
        r = conn.execute(
            "SELECT assertion_id, durability, class_confidence, needs_review"
            " FROM sidecar_classification WHERE assertion_id = ?",
            (assertion_id,),
        ).fetchone()
        return Classification(r[0], r[1], r[2], bool(r[3])) if r else None

    def durability(self, assertion_id: str) -> str:
        """The fold's view. Unclassified rows read as STATE (conservative:
        a transient mistaken for structure decays; structure mistaken for
        transient gets flagged on contradiction) — classify_all() should
        leave none."""
        c = self.get(assertion_id)
        return c.durability if c else STATE

    def classify_all(self, batch_size: int | None = None) -> int:
        """Classify every row not yet in the sidecar. Returns count.

        With ``batch_size``, model-judged rows go to the model in batches
        (one call per N rows) — same judgments, fewer round trips."""
        pending = [r for r in self._buffer.all_rows() if self.get(r.id) is None]
        if not batch_size:
            for row in pending:
                self.classify(row)
            return len(pending)
        return self.classify_rows(pending, batch_size)

    def classify_rows(self, rows: list[Assertion], batch_size: int | None = None,
                      model: bool = True) -> int:
        """Classify a SPECIFIC set of rows (INGEST-HARDENING-V1): guardrails
        resolve immediately with zero model calls; model-needing rows go to one
        batch call (or `batch_size` chunks). The shared core of `classify_all`'s
        batch path and the opt-in batched ingest. Already-classified rows skip.

        ``model=False`` (INGEST-LATENCY-V2 `classify="rules"`): the ambiguous
        remainder gets the doctrine's primary asymmetric default STATE with NO
        LM call — fast and deterministic. Deliberately STATE (not the
        containment→CONSTITUTIVE except sub-rule) so a movable's containment
        recency-supersedes; `needs_review` is never raised (STATE isn't flagged).
        The standing-spectrum default is safe: durability is rebuildable and the
        erasing EVENT is barred (CLASSIFIER-EVENT-SAFETY)."""
        rows = [r for r in rows if self.get(r.id) is None]
        deferred: list[Assertion] = []
        for row in rows:
            verdict = self._guardrails(row)
            if verdict is not None:
                durability, confidence = verdict
                self._store(
                    Classification(
                        row.id, durability, confidence,
                        durability == CONSTITUTIVE and confidence < _REVIEW_FLOOR,
                    )
                )
            else:
                deferred.append(row)
        if deferred:
            if not model:
                for row in deferred:
                    self._store(Classification(row.id, STATE, 0.5, False))
            else:
                step = batch_size or len(deferred)
                for start in range(0, len(deferred), step):
                    self._classify_batch(deferred[start : start + step])
        return len(rows)

    def _classify_batch(self, rows: list[Assertion]) -> None:
        listing = "\n".join(
            f"{i}. {r.entity} · {r.attribute} · {json.dumps(r.value, default=json_default)}"
            for i, r in enumerate(rows)
        )
        prompt = (
            "Classify the lifetime of each fact about a world. Classes:\n"
            "CONSTITUTIVE: what the thing IS (identity, structure, fixtures, era); "
            "true at every moment unless the world is re-authored.\n"
            "DISPOSITIONAL: what it TENDS to be (habits, roles); defeasible.\n"
            "STATE: what it is RIGHT NOW (positions of movables, moods); one event "
            "could flip it.\n"
            "Mutability test: could one event flip it without re-authoring the "
            "world? -> STATE. Ambiguous property -> STATE. " + _CONTAINMENT_CLAUSE
            + "\n\nFacts:\n" + listing
        )
        verdicts: dict[int, tuple[str, float]] = {}
        try:
            out = self._model(prompt, task_schema(_BATCH_SCHEMA))
            for v in out["verdicts"]:
                # EVENT (or any non-standing verdict) is rejected -> the row
                # falls to the asymmetric default below, never erased.
                if v["durability"] in _STANDING_DURABILITIES:
                    verdicts[int(v["index"])] = (v["durability"], float(v["class_confidence"]))
        except Exception:
            logger.exception("batch classification failed; defaulting batch")
        for i, row in enumerate(rows):
            durability, confidence = self._apply_containment_floor(row, *verdicts.get(
                i,
                (CONSTITUTIVE, 0.5)
                if self._semantics.is_containment(row.attribute)
                else (STATE, 0.5),
            ))
            self._store(
                Classification(
                    row.id, durability, confidence,
                    durability == CONSTITUTIVE and confidence < _REVIEW_FLOOR,
                )
            )

    def promote_accruals(self, threshold: int = 3) -> int:
        """Accrual promotion (whitepaper §5.1): repeated STATE observations
        of the same (entity, attribute, value) — at distinct valid times —
        promote to DISPOSITIONAL in the sidecar. The world learns its
        habits; the log is untouched; rebuild() re-derives. Returns the
        number of rows promoted. Promotion frequency doubles as the
        salience baseline's input."""
        groups: dict[tuple, set] = {}
        rows_by_group: dict[tuple, list] = {}
        for row in self._buffer.visible():
            if (
                row.entity.startswith("a:")
                or row.entity.startswith(ATTR_PREFIX)
                or row.value_type in ("unresolved", "delta")
                or self._semantics.is_accrue(row.attribute)
                # READ-SURFACE-V1 §1: a declared class is not a habit to learn
                or self._semantics.durability_pin(row.attribute) is not None
            ):
                continue  # deltas / accrue quantities are summed, never a habit
            if self.durability(row.id) != STATE:
                continue
            key = (row.entity, row.attribute, row.frame, repr(row.value))
            groups.setdefault(key, set()).add(row.valid_from)
            rows_by_group.setdefault(key, []).append(row)
        promoted = 0
        for key, valid_times in groups.items():
            if len(valid_times) >= threshold:
                for row in rows_by_group[key]:
                    self.set(row.id, DISPOSITIONAL, 0.8)
                    promoted += 1
        if promoted:
            logger.info("accrual promotion: %d row(s) -> DISPOSITIONAL", promoted)
        return promoted

    def rebuild(self) -> int:
        """Drop the sidecar and re-derive it from the untouched log."""
        self._verdict_version += 1
        conn = self._buffer.raw_connection()
        conn.execute("DELETE FROM sidecar_classification")
        conn.commit()
        return self.classify_all()
