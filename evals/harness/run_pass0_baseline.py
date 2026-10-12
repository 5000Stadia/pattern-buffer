"""Pass-0-only baseline (R23): run pass-0 on the story exactly as the
chapter-test pipeline does (run_chapter_test_v2.py: chapter segments, the
establish/extend prompt, the eval model shim), then grade the registry.

Usage (from the repo root):
    PYTHONPATH=src python evals/harness/run_pass0_baseline.py OUT_DIR [--runs 2]

Each run lands in OUT_DIR/run<N>/ with registry.json, scorecard.md/.json,
scorecard_seeded.md/.json (identity after the engine's own merges) and
meta.json (date, model, segment count, wall time). No pass-1, no battery.
Stops with a nonzero exit if the model shim errors (quota, CLI missing).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from grade_registry import grade, seeded_registry, write_scorecard
from pipeline import Pipeline
from run_chapter_test import BIBLE_MARKERS, STORY

logger = logging.getLogger("pass0_baseline")
WORLD_ID = "w:anchor_v2"  # same world id as run_chapter_test_v2


def story_segments() -> list[str]:
    """The chapter-test v2 segmentation of story.md (one segment per chapter)."""
    story = STORY.read_text()
    for marker in BIBLE_MARKERS:
        if marker in story:
            raise SystemExit(f"ABORT: bible marker {marker!r} in ingestion input")
    return ["## Chapter" + part for part in story.split("## Chapter")[1:]]


def run_once(run_dir: Path, segments: list[str]) -> dict:
    """One pass-0 run into ``run_dir``; returns its meta dict."""
    from model_shim import MODEL, claude_model

    run_dir.mkdir(parents=True, exist_ok=True)
    pipe = Pipeline(claude_model, WORLD_ID, run_dir, max_workers=4)
    t = time.time()
    registry = pipe.pass0(segments=segments)
    wall = round(time.time() - t, 1)
    try:
        pipe.staging.rmdir()  # pass-0 stages nothing
    except OSError:
        pass
    result = grade(registry)
    write_scorecard(result, run_dir, title=f"Pass-0 registry scorecard ({run_dir.name})")
    # ALIAS-INDEX-V1 r4.2: graded as the commit finalizes it (Part B, then
    # reconcile), from the same segments pass-0 read
    write_scorecard(grade(seeded_registry(registry, segments=segments)), run_dir,
                    stem="scorecard_seeded",
                    title=f"Pass-0 identity as the commit finalizes it ({run_dir.name})")
    meta = {"date": date.today().isoformat(), "model": MODEL, "segments": len(segments),
            "wall_s": wall, "registry_ids": len(registry.entities)}
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    logger.info("%s: %s | coverage %d/%d frag %d fusion %d B3 F1 %.3f", run_dir.name, meta,
                result["coverage"], result["gold_entities"], result["fragmentation_count"],
                result["fusion_count"], result["b3_f1"])
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir")
    ap.add_argument("--runs", type=int, default=2)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    segments = story_segments()
    for n in range(1, args.runs + 1):
        run_once(Path(args.out_dir) / f"run{n}", segments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
