"""MICRO-EVAL-V1: the reality-divergence battery (spec GREEN, seed v1-final).

Tracking posture end to end: stance=reality, policy=observe_or_unknown,
conversational pass-1 contract (reality gate, speaker sources, corr
proposals, interval time, cursor humility), stance receipts staged per
utterance, correction promotion before audit, R1-R10 graded.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from patternbuffer import World
from patternbuffer.dump import dump

import grammar
from audit import promote_corrections, run_audit
from pipeline import Pipeline
from registry import WorldRegistry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("micro_eval")

SEED_DIR = ROOT / "evals" / "household_dialogue"
OUT = ROOT / "evals" / "results"
WORLD_ID = "w:household"

_CONV_PROMPT = """\
You are extracting WORLD STATE from a household conversation, for a
tracking system whose cardinal rule is: NEVER confabulate. Fiction trusts
the narrator; you trust no single utterance — you accumulate evidence.

For EACH numbered utterance, first classify its STANCE:
- declarative (a claim about present/past reality) -> extract rows
- irrealis (hypothetical/question/joke/sarcasm/conditional) -> NO rows
  (a hypothetical may emit ONE assumed row, s=assumed, conf low, only if
  it names a concrete possibility)
- intention (a plan/future promise) -> NO rows at all
- correction (same speaker amending an in-window prior) -> extract the
  corrected row WITH the corr flag

Then emit grammar lines for declaratives/corrections only:
  entity|attribute|value|flags
- flags: vf=<turn stamp> (use the [d.tt] stamp), src=person:<speaker>
  (ALWAYS — every fact carries its speaker), s=stated, corr when
  correcting, vt= for interval ends.
- Containment/location: attribute `in`; anchor ONLY on stated containers
  — the speaker's own location NEVER anchors anything they mention.
- Fuzzy past time ("last Tuesday sometime"): vf/vt as an honest interval
  on the day timeline (Monday of THIS week = day 0; last Tuesday = -6).
- Use ONLY registry entity ids; quantities as attributes on one entity.
- Atmosphere, banter, and rhetoric are not assertions.

Output BOTH:
- "stances": one entry per utterance: {{"turn": "<stamp>", "stance": "..."}}
- "lines": the grammar lines.

REGISTRY:
{registry_slice}

CONVERSATION (chunk {chunk_id}):
{text}
"""

_CONV_SCHEMA = {
    "type": "object",
    "properties": {
        "stances": {"type": "array", "items": {
            "type": "object",
            "properties": {"turn": {"type": "string"}, "stance": {"type": "string"}},
            "required": ["turn", "stance"]}},
        "lines": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["stances", "lines"],
}


class ConversationalPipeline(Pipeline):
    """INGEST-V2 with the conversational pass-1 contract + stance receipts."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.stance_receipts: dict[int, list] = {}

    def _extract_chunk(self, chunk_id, text, cursor, registry):
        prompt = _CONV_PROMPT.format(
            registry_slice=self._registry_slice(registry, text),
            chunk_id=chunk_id, text=text,
        )
        from pipeline import ChunkResult
        result = ChunkResult(chunk_id=chunk_id)
        for attempt in (1, 2):
            try:
                out = self.model(prompt, _CONV_SCHEMA)
            except Exception as exc:
                if type(exc).__name__ in ("QuotaExhausted", "CodexAuthError"):
                    raise
                result.error = str(exc)
                continue
            self.stance_receipts[chunk_id] = out.get("stances", [])
            items, orphans, rejects = grammar.parse(out["lines"], registry, cursor)
            if grammar.reject_rate(items, orphans, rejects) > self.reject_threshold:
                result.error = f"reject rate over threshold ({len(rejects)})"
                continue
            result.items, result.orphans, result.rejects = items, orphans, rejects
            return result
        result.failed = True
        return result


def main() -> int:
    seed_version = (SEED_DIR / "SEED_VERSION").read_text().split()[0]
    if seed_version != "v1-final":
        raise SystemExit("ABORT: seed not stamped v1-final")
    transcript = (SEED_DIR / "transcript.md").read_text()
    if "Answer key" in transcript or "R1 (" in transcript:
        raise SystemExit("ABORT: key text detected in transcript")

    from model_shim import get_model
    model, model_name = get_model()

    run_dir = OUT / f"{date.today().isoformat()}-micro-{seed_version}"
    run_dir.mkdir(parents=True, exist_ok=True)
    pipe = ConversationalPipeline(model, WORLD_ID, run_dir, max_workers=3)
    timings: dict[str, float] = {}

    # Segments = the three conversation days; registry grows incrementally
    # (the 014 establish/extend interface, first live incremental use).
    sections = ["##" + s for s in transcript.split("##")[1:]]
    cursors = [0.0, 2.0, 4.0]
    t = time.time()
    registry = pipe.pass0(segments=sections)
    timings["pass0_s"] = round(time.time() - t, 1)
    logger.info("registry: %d entities", len(registry.entities))

    t = time.time()
    chunks = list(zip(cursors, sections))
    results = pipe.pass1(chunks, registry)
    timings["pass1_s"] = round(time.time() - t, 1)
    if any(r.failed for r in results):
        raise SystemExit("noncanonical: chunk failure; staging retained")
    results, escapes = pipe.repair_escapes(results, registry, chunks)
    (run_dir / "stance_receipts.json").write_text(
        json.dumps(pipe.stance_receipts, indent=1))

    t = time.time()
    world_path = run_dir / "household.world"
    world_path.unlink(missing_ok=True)
    # Charter at genesis (026): reality stance — then commit replays into it.
    world = World(world_path, world_id=WORLD_ID, model=model,
                  policy="observe_or_unknown", stance="reality",
                  title="The Household", description="Dale and Meg's world, tracked.")
    for alias, canonical in sorted(registry.attributes.items()):
        world.ingestor.add_attribute_alias(alias, canonical)
    from registry import seed_items
    world.ingestor.classify_inline = False
    world.ingest_structured(seed_items(registry))
    for r in results:
        world.ingest_structured(r.items)
    world.classifier.classify_all(batch_size=40)
    promoted = promote_corrections(world)
    world.truth.scan()
    timings["commit_s"] = round(time.time() - t, 1)

    t = time.time()
    audit_report = run_audit(world, registry, model)
    timings["audit_s"] = round(time.time() - t, 1)
    timings["total_s"] = round(sum(timings.values()), 1)
    (run_dir / "ingest_dump.jsonl").write_text(dump(world.buffer))

    from battery_micro import run_battery_micro
    verdicts = run_battery_micro(world)
    import scoring
    meta = {
        "date": date.today().isoformat(), "model": model_name,
        "pipeline": "INGEST-V2 conversational (MICRO-EVAL-V1)",
        "seed": seed_version, "log_rows": world.buffer.head(),
        "registry_escapes": escapes, "corrections_promoted": promoted,
        "audit": {"adds": audit_report.applied_adds,
                  "retracts": audit_report.applied_retracts},
        "open_conflicts": len(world.truth.open_conflicts()),
        "timings": timings,
    }
    card = scoring.write(verdicts, meta, run_dir)
    n = sum(1 for v in verdicts if v.status == "PASS")
    print(f"SCORE: {n}/{len(verdicts)}")
    for v in verdicts:
        print(f"  {('R%d' % v.qid):>3} {v.status:<5} ({v.failure_class or '-'}): {v.detail[:90]}")
    world.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
