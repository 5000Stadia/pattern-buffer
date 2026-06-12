"""The chapter test (whitepaper §19.1): fresh ingestion of story.md,
delete the prose (the store is all that remains), interrogate cold,
score against the bible-derived fixtures.

Usage: .venv/bin/python evals/harness/run_chapter_test.py [--stub]
  --stub uses a no-op model (harness self-test of plumbing only; the
  scorecard is meaningless and is not written).

Discipline guards built in:
  * the ingestion input is scanned for bible markers and the run aborts
    if any are present (letter 004 item 1);
  * fixtures are expected values in the grader only — nothing from
    fixtures.py is ever passed to the model or the gate.
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

import fixtures as FX
from battery import run_battery
import scoring

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("chapter_test")

STORY = ROOT / "evals" / "last_honest_meter" / "story.md"
SEED_VERSION_FILE = ROOT / "evals" / "last_honest_meter" / "SEED_VERSION"
OUT = ROOT / "evals" / "results"

BIBLE_MARKERS = ("STORY BIBLE", "TEST ANNOTATIONS", "Pass condition",
                 "BIBLE ADDENDUM", "pass condition", "answer key")

# Narrative-time convention given to the extractor. Day 0 = the night the
# master meter went dark (the prose's own anchor: "Three days ago it had
# gone dark" in Ch.1; "Three days after the assembly" opens Ch.2; "three
# weeks" closes Ch.4). A reading convention, not bible content.
TIME_CONVENTION = (
    "TIMELINE CONVENTION: valid_from is a story-day number. Day 0 = the night "
    "the master meter went dark (the night Tovan died). Derive day offsets "
    "from the text's own cues (e.g. 'three days ago', 'three days after the "
    "assembly', 'three weeks'). Use fractions for within-day order (evening "
    "~ .5+). If the text gives no anchor for a fact's time, omit valid_from "
    "and the scene cursor will stamp it; mark permanent facts timeless=true. "
    "Events that happened BEFORE the current scene but are revealed now get "
    "their TRUE historical day, not the scene's day."
)

# Scene-cursor fallback day per chapter, from explicit prose cues only.
CHAPTER_DAYS = {1: 3.0, 2: 7.0, 3: 9.0, 4: 14.0}


def chunks(story_text: str):
    """(chapter_number, chunk_text) pairs; scenes split on '-----'."""
    chapters = []
    current_no, buf = None, []
    for line in story_text.splitlines():
        if line.startswith("## Chapter"):
            if current_no is not None:
                chapters.append((current_no, "\n".join(buf)))
            current_no = len(chapters) + 1
            buf = [line]
        else:
            buf.append(line)
    if current_no is not None:
        chapters.append((current_no, "\n".join(buf)))
    for no, text in chapters:
        for scene in text.split("\n-----\n"):
            scene = scene.strip()
            if len(scene) <= 80:
                continue
            # Sub-split oversized scenes on paragraph boundaries (~3.5k max):
            # extraction quality and call latency both degrade past that.
            while len(scene) > 3500:
                cut = scene.rfind("\n\n", 1500, 3500)
                if cut == -1:
                    cut = 3500
                yield no, scene[:cut].strip()
                scene = scene[cut:].strip()
            if len(scene) > 80:
                yield no, scene


def roster(world: World, limit: int = 120) -> str:
    """Known entities so far: id + primary name. Continuity context for
    the extractor — its own prior output, never fixture content."""
    by_entity: dict[str, str] = {}
    for row in world.buffer.all_rows():
        if row.attribute in {"name", "alias"} and isinstance(row.value, str):
            by_entity.setdefault(world.registry.resolve(row.entity), row.value)
        elif not row.entity.startswith("a:"):
            by_entity.setdefault(world.registry.resolve(row.entity), "")
    lines = [f"{eid} ({name})" if name else eid for eid, name in sorted(by_entity.items())]
    return "\n".join(lines[:limit])


def main() -> int:
    stub_mode = "--stub" in sys.argv
    skip = 0  # --resume-from N: skip the first N chunks (already ingested)
    only_chapters: set[int] | None = None  # --chapters=3,4: ingest only these
    for arg in sys.argv[1:]:
        if arg.startswith("--resume-from="):
            skip = int(arg.split("=")[1])
        if arg.startswith("--chapters="):
            only_chapters = {int(c) for c in arg.split("=")[1].split(",")}
    only_chunks: set[int] | None = None  # --chunks=7,8,9: exactly these indices
    for arg in sys.argv[1:]:
        if arg.startswith("--chunks="):
            only_chunks = {int(c) for c in arg.split("=")[1].split(",")}

    story = STORY.read_text()
    for marker in BIBLE_MARKERS:
        if marker in story:
            raise SystemExit(f"ABORT: bible marker {marker!r} found in ingestion input")
    seed_version = SEED_VERSION_FILE.read_text().split()[0]
    if seed_version != FX.SEED_VERSION:
        raise SystemExit(
            f"ABORT: fixtures are frozen against {FX.SEED_VERSION}; seed on disk is "
            f"{seed_version} — a changed story invalidates prior fixtures (letter 006)"
        )

    if stub_mode:
        from patternbuffer.testing import StubModel, rule_classifier_fallback
        model = StubModel(fallback=rule_classifier_fallback())
        model_name = "stub"
    else:
        from model_shim import claude_model, MODEL as model_name, QuotaExhausted
        model = claude_model

    run_dir = OUT / f"{date.today().isoformat()}-{seed_version}"
    run_dir.mkdir(parents=True, exist_ok=True)
    world_path = run_dir / "fresh_ingest.world"
    if (skip == 0 and only_chapters is None and only_chunks is None
            and "--grade-only" not in sys.argv):
        world_path.unlink(missing_ok=True)
    w = World(world_path, world_id="w:anchor_fresh", model=model)
    w.ingestor.classify_inline = False  # batch after each chunk

    grade_only = "--grade-only" in sys.argv
    t0 = time.time()
    if not stub_mode and not grade_only:
        for i, (chapter_no, scene) in enumerate(chunks(story)):
            if i < skip:
                continue
            if only_chapters is not None and chapter_no not in only_chapters:
                continue
            if only_chunks is not None and i not in only_chunks:
                continue
            w.ingestor.cursor.advance(CHAPTER_DAYS[chapter_no])
            context = (
                f"{TIME_CONVENTION}\n\nThis passage is from Chapter {chapter_no} "
                f"of four. Reuse entity ids from the roster below when the same "
                f"thing is referenced again; when a previously-unnamed entity is "
                f"named, keep its id and add the name via a 'name' item plus "
                f"same_as if you minted a new id.\n\nKNOWN ENTITIES:\n{roster(w)}"
            )
            n_before = w.buffer.head()
            try:
                w.ingest(scene, context=context)
            except QuotaExhausted as exc:
                # A quota-aborted world is partial: grading it would write
                # an invalid scorecard (the run-2 trap). Stop entirely.
                logger.error("quota exhausted at chunk index %d (ch%d); aborting "
                             "run before grading: %s", i, chapter_no, exc)
                print(f"QUOTA ABORT at chunk {i}; resume with --resume-from={i}; "
                      "no scorecard written (partial world)")
                return 1
            except Exception:
                logger.exception("chunk failed (ch%d); continuing", chapter_no)
            logger.info("ch%d chunk: +%d rows (total %d, %.0fs)",
                        chapter_no, w.buffer.head() - n_before, w.buffer.head(),
                        time.time() - t0)
            w.classifier.classify_all(batch_size=40)
    logger.info("ingestion done: %d rows in %.0fs", w.buffer.head(), time.time() - t0)

    w.truth.scan()
    # Delete the prose: from here on, only the store is interrogated.
    (run_dir / "ingest_dump.jsonl").write_text(dump(w.buffer))

    verdicts = run_battery(w)
    meta = {
        "date": date.today().isoformat(),
        "model": model_name,
        "log_rows": w.buffer.head(),
        "entities": len({r.entity for r in w.buffer.all_rows() if not r.entity.startswith("a:")}),
        "frames": len({r.frame for r in w.buffer.all_rows()}),
        "ingest_seconds": round(time.time() - t0),
    }
    if stub_mode:
        print("[stub mode] plumbing OK; battery ran; scorecard suppressed")
        for v in verdicts:
            print(f"  Q{v.qid:>2} {v.status:>11} {v.title}")
        return 0
    card = scoring.write(verdicts, meta, run_dir)
    print(f"scorecard: {card}")
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
