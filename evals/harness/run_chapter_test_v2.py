"""Chapter test, INGEST-V2 edition: registry-first three-round ingestion,
then the same interrogation battery against the same v1-final fixtures.

Rounds: pass-0 (whole story -> registry) -> pass-1 (parallel chunk
extraction, staged) -> escape repair -> single commit -> pass-2 audit ->
battery -> scorecard. Timing for each round is recorded against the
spec §E.2 estimate.

Usage (repo root):
    PYTHONPATH=src python evals/harness/run_chapter_test_v2.py \\
        [--out DIR] [--pass0 sequential|parallel] [--glean]

R26 BUILD-TIMINGS-V1: ``--out`` names the run directory (default: the old
dated ``...-v2pipeline-run4`` name); ``--pass0 parallel`` establishes each
chapter on its own and reduces by merge; ``--glean`` adds one missed-entity
call per segment. ``timings.json`` holds every stage; the registry is graded
raw and seeded (``registry_scorecard*``) and given the R24 alias index.
"""

from __future__ import annotations

import argparse
import copy
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=None,
                    help="run directory (default: results/<date>-<seed>-v2pipeline-run4)")
    ap.add_argument("--pass0", choices=("sequential", "parallel"), default="sequential",
                    help="sequential: establish then extend with prior (default); "
                         "parallel: establish each segment alone, reduce by merge")
    ap.add_argument("--glean", action="store_true",
                    help="after each segment's registry, one call for missed E| lines")
    return ap.parse_args(argv)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_registry_reports(registry, segments: list[str], run_dir: Path) -> dict:
    """Grade ``registry`` raw and seeded (``registry_scorecard*``, named apart
    from the battery's ``scorecard``) and write the R24 alias index. No model
    call. Returns the headline numbers."""
    from grade_registry import grade, seeded_registry, write_scorecard
    import alias_index

    raw = grade(registry)
    write_scorecard(raw, run_dir, stem="registry_scorecard",
                    title=f"Pass-0 registry scorecard ({run_dir.name})")
    # ALIAS-INDEX-V1 r4.2: graded as the commit finalizes it (Part B, then
    # reconcile), from the same segments pass-0 read
    seeded = grade(seeded_registry(registry, segments=segments))
    write_scorecard(seeded, run_dir, stem="registry_scorecard_seeded",
                    title=f"Pass-0 identity as the commit finalizes it ({run_dir.name})")
    alias_index.write_report(alias_index.build_report(registry, segments), run_dir,
                             title=f"Alias index ({run_dir.name})")
    return {"raw_b3_f1": raw["b3_f1"], "seeded_b3_f1": seeded["b3_f1"],
            "raw_fusion": raw["fusion_count"], "seeded_fusion": seeded["fusion_count"]}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    story = STORY.read_text()
    for marker in BIBLE_MARKERS:
        if marker in story:
            raise SystemExit(f"ABORT: bible marker {marker!r} in ingestion input")
    seed_version = SEED_VERSION_FILE.read_text().split()[0]
    if seed_version != FX.SEED_VERSION:
        raise SystemExit("ABORT: fixtures frozen against a different seed version")

    from model_shim import claude_model, MODEL as model_name

    run_dir = (Path(args.out) if args.out
               else OUT / f"{date.today().isoformat()}-{seed_version}-v2pipeline-run4")
    run_dir.mkdir(parents=True, exist_ok=True)
    pipe = Pipeline(claude_model, WORLD_ID, run_dir, max_workers=4)
    chunk_list = [(CHAPTER_DAYS[no], text) for no, text in chunks(story)]
    timings: dict[str, float] = {}

    def flush_timings() -> None:  # rewritten as stages finish, so a failed run keeps its split
        write_json(run_dir / "timings.json", {**timings, **pipe.timings})

    t = time.time()
    # Chapter-split scaffold: establish over Ch.1, extend over 2-4 (spec §3.2).
    segments = ["## Chapter" + part for part in story.split("## Chapter")[1:]]
    registry = pipe.pass0(segments=segments, parallel=args.pass0 == "parallel",
                          glean=args.glean)
    timings["pass0_s"] = round(time.time() - t, 1)
    logger.info("pass-0: %d entities, %d attr aliases, %d edges (%.0fs)",
                len(registry.entities), len(registry.attributes),
                len(registry.places), timings["pass0_s"])
    # Graded as pass-0 left it (comparable to R23); escape repair and commit
    # extend the live registry afterwards.
    pass0_registry = copy.deepcopy(registry)
    pass0_registry.save(run_dir / "registry_pass0.json")
    registry_summary = write_registry_reports(pass0_registry, segments, run_dir)
    flush_timings()

    t = time.time()
    results = pipe.pass1(chunk_list, registry)
    timings["pass1_s"] = round(time.time() - t, 1)
    flush_timings()
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
    flush_timings()

    t = time.time()
    from audit import run_audit
    audit_report = run_audit(world, registry, claude_model)
    timings["audit_s"] = round(time.time() - t, 1)

    (run_dir / "ingest_dump.jsonl").write_text(dump(world.buffer))

    t = time.time()
    verdicts = run_battery(world)
    timings["battery_s"] = round(time.time() - t, 1)
    timings["total_s"] = round(sum(v for k, v in timings.items() if k != "total_s"), 1)
    flush_timings()
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
        "pass0_mode": args.pass0,
        "glean": args.glean,
        "registry_pass0": registry_summary,
        "registry_after_commit_entities": len(registry.entities),
        "timings": timings,
    }
    write_json(run_dir / "meta.json", meta)
    card = scoring.write(verdicts, meta, run_dir)
    print(f"scorecard: {card}")
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
