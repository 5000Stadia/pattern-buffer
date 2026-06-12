"""Chapter test, INGEST-V2 edition: registry-first three-round ingestion,
then the same interrogation battery against the same v1-final fixtures.

Rounds: pass-0 (whole story -> registry) -> pass-1 (parallel chunk
extraction, staged) -> escape repair -> single commit -> pass-2 audit ->
battery -> scorecard. Timing for each round is recorded against the
spec §E.2 estimate.
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

from patternbuffer.dump import dump

import fixtures as FX
import scoring
from battery import run_battery
from pipeline import Pipeline
from run_chapter_test import BIBLE_MARKERS, CHAPTER_DAYS, STORY, SEED_VERSION_FILE, chunks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("chapter_test_v2")

OUT = ROOT / "evals" / "results"
WORLD_ID = "w:anchor_v2"


def main() -> int:
    story = STORY.read_text()
    for marker in BIBLE_MARKERS:
        if marker in story:
            raise SystemExit(f"ABORT: bible marker {marker!r} in ingestion input")
    seed_version = SEED_VERSION_FILE.read_text().split()[0]
    if seed_version != FX.SEED_VERSION:
        raise SystemExit("ABORT: fixtures frozen against a different seed version")

    from model_shim import claude_model, MODEL as model_name

    run_dir = OUT / f"{date.today().isoformat()}-{seed_version}-v2pipeline"
    run_dir.mkdir(parents=True, exist_ok=True)
    pipe = Pipeline(claude_model, WORLD_ID, run_dir, max_workers=4)
    chunk_list = [(CHAPTER_DAYS[no], text) for no, text in chunks(story)]
    timings: dict[str, float] = {}

    t = time.time()
    # Chapter-split scaffold: establish over Ch.1, extend over 2-4 (spec §3.2).
    segments = ["## Chapter" + part for part in story.split("## Chapter")[1:]]
    registry = pipe.pass0(segments=segments)
    timings["pass0_s"] = round(time.time() - t, 1)
    logger.info("pass-0: %d entities, %d attr aliases, %d edges (%.0fs)",
                len(registry.entities), len(registry.attributes),
                len(registry.places), timings["pass0_s"])

    t = time.time()
    results = pipe.pass1(chunk_list, registry)
    timings["pass1_s"] = round(time.time() - t, 1)
    failed = [r.chunk_id for r in results if r.failed]
    if failed:
        raise SystemExit(f"noncanonical: chunks {failed} failed; staging retained")

    t = time.time()
    results, escapes = pipe.repair_escapes(results, registry, chunk_list)
    timings["escape_repair_s"] = round(time.time() - t, 1)

    t = time.time()
    world_path = run_dir / "fresh_ingest.world"
    world_path.unlink(missing_ok=True)
    world = pipe.commit(world_path, registry)
    timings["commit_s"] = round(time.time() - t, 1)

    t = time.time()
    from audit import run_audit
    audit_report = run_audit(world, registry, claude_model)
    timings["audit_s"] = round(time.time() - t, 1)

    (run_dir / "ingest_dump.jsonl").write_text(dump(world.buffer))
    timings["total_s"] = round(sum(timings.values()), 1)

    verdicts = run_battery(world)
    meta = {
        "date": date.today().isoformat(),
        "model": model_name,
        "pipeline": "INGEST-V2 (registry-first)",
        "log_rows": world.buffer.head(),
        "entities": len({r.entity for r in world.buffer.all_rows()
                         if not r.entity.startswith("a:")}),
        "frames": len({r.frame for r in world.buffer.all_rows()}),
        "registry_escapes": escapes,
        "audit": {"adds": audit_report.applied_adds,
                  "retracts": audit_report.applied_retracts,
                  "dropped": len(audit_report.dropped_ops)},
        "timings": timings,
    }
    card = scoring.write(verdicts, meta, run_dir)
    print(f"scorecard: {card}")
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
