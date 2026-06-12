"""Pass-2 world audit (spec §5.2): deterministic anomaly digest -> one
model review -> typed repair ops through the proper write paths.

Ops: `add|<grammar line>` via the gate; `retract|<assertion_id>|<reason>`
via truth maintenance. Nothing else exists. Retracts against flagged
conflicts are dropped with a warning — open conflicts are questions for
the author, not the auditor.

Run-3 lesson, code-enforced: the auditor retracted *correct* rows when
handed drift anomalies. Retraction is therefore restricted to **exact
duplicates** — a retract applies only when another surviving row carries
the identical (entity, attribute, value, frame). Everything else the
auditor wants gone stays; wrongness beyond duplication is the author's
call, not the auditor's.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from patternbuffer import World
from patternbuffer.classify import EVENT, STATE
from patternbuffer.model import META_ATTRIBUTES

import grammar
from registry import WorldRegistry

logger = logging.getLogger(__name__)

_AUDIT_SCHEMA = {
    "type": "object",
    "properties": {"ops": {"type": "array", "items": {"type": "string"}}},
    "required": ["ops"],
}

_AUDIT_PROMPT = """\
You are auditing a freshly ingested world database against its anomaly
digest. Emit repair OPS, one per line, ONLY these two forms:

  add|entity|attribute|value|flags     (grammar line prefixed with 'add|')
  retract|<assertion_id>|<reason>

Rules:
- Repair only what the digest shows: stamp times you can derive from the
  timeline (as adds), and retract ONLY exact duplicates — a row whose
  entity, attribute, value, and frame all match another surviving row.
  A row that merely looks wrong, off-registry, or unstamped is NOT yours
  to retract; leave it.
- NEVER touch assertions listed under 'conflicts' — flagged contradictions
  are deliberate open questions; leave both sides standing.
- Additions follow the same canon-vs-knowledge and never-invent rules as
  extraction, and MUST carry an explicit time flag (vf=<day> or t) — an
  add without one is dropped. When in doubt, emit nothing for that anomaly.

TIMELINE: {timeline}

DIGEST:
{digest}

OPS:
"""


@dataclass
class AuditReport:
    digest: dict = field(default_factory=dict)
    applied_adds: int = 0
    applied_retracts: int = 0
    dropped_ops: list[str] = field(default_factory=list)


def build_digest(world: World, registry: WorldRegistry, cap: int = 200) -> dict:
    """The anomaly digest, assembled deterministically with assertion ids."""
    conflicts = [
        {"key": f"{c.entity}·{c.attribute}·{c.frame}", "kind": c.kind,
         "assertion_ids": list(c.assertion_ids)}
        for c in world.truth.open_conflicts()
    ]
    unstamped, drift, frame_anoms = [], [], []
    known_attrs = set(registry.attributes.values()) | set(registry.attributes)
    known_entities = set(registry.entities)
    for row in world.buffer.visible():
        if row.entity.startswith("a:") or row.attribute in META_ATTRIBUTES:
            continue
        durability = world.classifier.durability(row.id)
        if durability in {STATE, EVENT} and row.valid_from is None \
                and not row.entity.startswith("event:merge_"):
            unstamped.append({"assertion_id": row.id, "entity": row.entity,
                              "attribute": row.attribute})
        if row.attribute not in known_attrs and row.attribute not in {
            "kind", "name", "alias", "in", "connects_to", "adjacent_to", "caused_by",
        }:
            drift.append({"assertion_id": row.id, "attribute": row.attribute})
        if row.frame.startswith("knows:"):
            inner = row.frame.removeprefix("knows:")
            if inner not in known_entities:
                frame_anoms.append({"frame": row.frame, "assertion_ids": [row.id]})
    anomalous_entities = {u["entity"] for u in unstamped}
    fold_winners = []
    for entity in sorted(anomalous_entities):
        for attr, result in world.indexes.current_state(entity).items():
            if result.winner is not None and len(fold_winners) < cap:
                fold_winners.append({
                    "entity": entity, "attribute": attr,
                    "value": result.winner.value, "assertion_id": result.winner.id,
                })
    return {
        "conflicts": conflicts,
        "unstamped": unstamped[:cap],
        "drift": drift[:cap],
        "frame_anoms": frame_anoms[:cap],
        "fold_winners": fold_winners,
    }


def _is_exact_duplicate(world: World, target) -> bool:
    """True iff another surviving (visible) row carries the identical
    (entity, attribute, value, frame). The only retractable condition."""
    for row in world.buffer.visible(
        entity=target.entity, attribute=target.attribute, frame=target.frame
    ):
        if row.id != target.id and row.value == target.value:
            return True
    return False


def run_audit(
    world: World,
    registry: WorldRegistry,
    model: Callable[[str, dict], Any],
) -> AuditReport:
    report = AuditReport(digest=build_digest(world, registry))
    protected = {
        aid for c in report.digest["conflicts"] for aid in c["assertion_ids"]
    }
    out = model(
        _AUDIT_PROMPT.format(
            timeline=f"{registry.timeline.origin} | anchors: {registry.timeline.anchors}",
            digest=json.dumps(report.digest, indent=1),
        ),
        _AUDIT_SCHEMA,
    )
    _NO_TIME = -1e12  # sentinel: detects adds that omitted vf=/t
    add_lines: list[str] = []
    for op in out["ops"]:
        op = op.strip()
        if not op:
            continue
        kind, _, rest = op.partition("|")
        if kind == "add" and rest:
            add_lines.append(rest)
        elif kind == "retract" and rest:
            aid, _, reason = rest.partition("|")
            if aid in protected:
                logger.warning("audit op dropped (targets flagged conflict): %s", op)
                report.dropped_ops.append(op)
                continue
            target = world.buffer.get(aid)
            if target is None:
                logger.warning("audit op dropped (unknown assertion id): %s", op)
                report.dropped_ops.append(op)
                continue
            if not _is_exact_duplicate(world, target):
                logger.warning("audit op dropped (not an exact duplicate): %s", op)
                report.dropped_ops.append(op)
                continue
            world.truth.retract(aid, reason or "pass-2 audit: duplicate")
            report.applied_retracts += 1
        else:
            logger.warning("audit op dropped (unknown op kind): %s", op)
            report.dropped_ops.append(op)
    if add_lines:
        items, orphans, rejects = grammar.parse(add_lines, registry, cursor=_NO_TIME)
        for o in orphans:
            report.dropped_ops.append(f"add|{o.line} (orphan: {o.entity_id})")
        for j in rejects:
            report.dropped_ops.append(f"add|{j.line} (reject: {j.reason})")
        # Audit adds must state their time explicitly (vf= or t): there is
        # no scene cursor at audit time, and a silent day-0 default would
        # be a fabricated valid_time.
        timed = [it for it in items if it.get("valid_from") != _NO_TIME]
        for it in items:
            if it.get("valid_from") == _NO_TIME:
                report.dropped_ops.append(
                    f"add (no explicit time): {it['entity']}|{it['attribute']}"
                )
        if timed:
            world.ingest_structured(timed)
            world.classifier.classify_all(batch_size=40)
            report.applied_adds = len(timed)
    world.truth.scan()
    logger.info("audit: +%d adds, %d retracts, %d dropped",
                report.applied_adds, report.applied_retracts, len(report.dropped_ops))
    return report
