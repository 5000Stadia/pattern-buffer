"""Build any book with the INGEST-V2 pipeline and write a time and cost receipt
(R27, BOOK-RUN-V1 §2).

A book directory holds ``ch01.md`` ... ``chNN.md``, each starting
``# Chapter N: <title>``. The build reads only those files: it never opens the
book's answer key or its graded set, and it refuses a chapter that contains a
key marker. The sequence is ``run_chapter_test_v2``'s, without the battery
(``grade_book.py`` replaces it): pass-0, registry reports, pass-1, escape
repair, commit, audit.

Usage (repo root):
    PYTHONPATH=src python evals/harness/run_book.py --book evals/books/<slug> --out DIR \\
        [--pass0 sequential|parallel] [--merge-gate] [--glean] [--dry-run] \\
        [--pipeline ingest-v2|library]

``--dry-run`` reads the book, prints its segment and chunk counts with an
estimate, and imports no model. A real run is metered; run it only when it has
been approved.

With profiling on (the default; ``--no-profile`` turns it off) the build also
writes ``objectives.jsonl`` (one line per unit of work, with its attempts) and
every ``usage.jsonl`` line carries its stage, unit and attempt (BUILD-PROFILE-V1);
``profile_build.py DIR`` turns them into ``profile.md``.

With ``PB_EVAL_STAGE_MODELS`` set (STAGE-MODELS-V1) each stage runs on its own
model and effort, and ``meta.json`` records the map and its sha256.

``--pipeline library`` (BUILD-LIBRARY-V1 §7) builds with ``patternbuffer.build``
instead: category passes write the manifest (stage ``registry``), code mints the
registry and plans the chunks, ``extract`` runs one labelled call per chunk
(stage ``extract``), and ``commit`` writes the world (stage ``commit``). It adds
``manifest.json``, ``plan.json`` and ``build_receipt.json`` to ``DIR``, writes
the minted registry as ``registry_pass0.json`` and the spans as
``chunk_spans.json``, so ``grade_book.py`` grades it. INGEST-V2 stays the default.

``DIR`` receives ``timings.json`` and ``receipt.json`` (rewritten as each stage
finishes, so a failed run keeps what it spent), ``usage.jsonl`` (one line per
model call, this run only), ``meta.json``, the registry, the staged chunks, the
world (``fresh_ingest.world``) and its dump, and ``chunk_spans.json`` (GRADE-LEAKS-V1 §1:
per chunk, its chapter, cursor and inclusive ``seq`` span in the log), which
``grade_book.py`` reads to date every row.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterator

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from patternbuffer.dump import dump

import usage_ledger
from pipeline import Pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("run_book")

# A chapter that holds one of these is refused (the same guard as the chapter
# test's BIBLE_MARKERS, for the book key's own vocabulary). Matched without case.
KEY_MARKERS = ('"same_as"', '"not_same"', "answer key")
SCENE_BREAKS = frozenset({"* * *", "***", "---"})
TARGET_CHUNK_WORDS = 1200
USAGE_ENV = "PB_EVAL_USAGE_LOG"
STAGES = ("pass0", "pass1", "escape_repair", "commit", "audit")

# BUILD-LIBRARY-V1 §7: the pipelines a run can use; INGEST-V2 is the default.
PIPELINES = ("ingest-v2", "library")
LIBRARY_STAGES = ("registry", "extract", "commit")
# BUILD-DEFAULTS-V1: the library pipeline's defaults are the speed comparison's
# setting (iii), the fastest at equal quality (evals/results/2026-10-14-speed-compare).
LIBRARY_MAX_WORDS = 750
LIBRARY_EXTRACT_WORKERS = 8
LIBRARY_CLASSIFY_WORKERS = 4
# The chunk size of every library run that predates BUILD-SPEED-V1 and so
# recorded no max_words: re-planning one must cut it as it was built.
PRE_SPEED_MAX_WORDS = 1500
LIBRARY_MANIFEST_FILE = "manifest.json"

# R26's measured sequential build of The Last Honest Meter: its size and wall
# seconds (evals/results/2026-10-10-r26-build-timings). R26 recorded no tokens,
# so the token figures below are a rough prior per R26-sized build, replaced by
# the first receipt.
R26_WORDS = 4728
R26_WALL_S = 1921
R26_PRIOR_INPUT_TOKENS = 180_000
R26_PRIOR_OUTPUT_TOKENS = 40_000


class BookRefused(ValueError):
    """A book directory the runner will not build."""


class BookRunAborted(RuntimeError):
    """A run that stopped before it finished (the receipt keeps what it spent)."""


@dataclass
class BookPlan:
    """A book read for building."""

    slug: str
    chapters: list[tuple[int, str]]            # (chapter number, text)
    chunks: list[tuple[float, str]]            # (cursor = chapter number, text)

    @property
    def chunk_plan(self) -> list[tuple[int, int, float]]:
        """``(chunk_id, chapter, cursor)`` per chunk, in source order: what
        ``Pipeline.commit`` records in ``chunk_spans.json`` (GRADE-LEAKS-V1 §1)."""
        return [(i, int(cursor), cursor) for i, (cursor, _) in enumerate(self.chunks)]

    @property
    def segments(self) -> list[str]:
        return [text for _, text in self.chapters]

    @property
    def words(self) -> int:
        return sum(len(text.split()) for _, text in self.chapters)


def split_chunks(text: str) -> list[str]:
    """One chapter's pass-1 chunks: scenes when the chapter has break lines
    (``* * *``, ``***`` or ``---`` alone on a line), otherwise paragraphs grouped
    to about ``TARGET_CHUNK_WORDS`` words."""
    lines = text.splitlines()
    if any(line.strip() in SCENE_BREAKS for line in lines):
        groups, buf = [], []
        for line in lines:
            if line.strip() in SCENE_BREAKS:
                groups.append("\n".join(buf))
                buf = []
            else:
                buf.append(line)
        groups.append("\n".join(buf))
        return [g.strip() for g in groups if g.strip()]
    chunks, buf, words = [], [], 0
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        n = len(para.split())
        if buf and words + n > TARGET_CHUNK_WORDS:
            chunks.append("\n\n".join(buf))
            buf, words = [], 0
        buf.append(para)
        words += n
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


def load_book(book_dir: str | Path) -> BookPlan:
    """Read ``ch01.md`` ... ``chNN.md`` from ``book_dir``; nothing else in the
    directory is opened. Raises ``BookRefused`` for no chapters, a gap in the
    numbering, a chapter that does not start ``# Chapter N``, or a chapter that
    holds a key marker."""
    book = Path(book_dir)
    found: dict[int, Path] = {}
    for p in book.iterdir():
        m = re.fullmatch(r"ch(\d+)\.md", p.name)
        if m:
            found[int(m.group(1))] = p
    if not found:
        raise BookRefused(f"{book}: no chNN.md chapter files")
    if sorted(found) != list(range(1, len(found) + 1)):
        raise BookRefused(f"{book}: chapter numbers {sorted(found)} are not 1..{len(found)}")
    chapters: list[tuple[int, str]] = []
    for n in sorted(found):
        text = found[n].read_text()
        lowered = text.lower()
        for marker in KEY_MARKERS:
            if marker.lower() in lowered:
                raise BookRefused(f"key marker {marker!r} in {found[n].name}")
        first = next((ln for ln in text.splitlines() if ln.strip()), "")
        m = re.match(r"#\s+Chapter\s+(\d+)\b", first)
        if not m or int(m.group(1)) != n:
            raise BookRefused(f"{found[n].name} must start '# Chapter {n}: <title>', got {first!r}")
        chapters.append((n, text))
    chunks = [(float(n), c) for n, text in chapters for c in split_chunks(text)]
    return BookPlan(slug=book.resolve().name, chapters=chapters, chunks=chunks)


def estimate(plan: BookPlan) -> dict[str, Any]:
    """Scale R26's measured build to this book by word count."""
    scale = plan.words / R26_WORDS
    return {"words": plan.words, "scale_vs_r26": round(scale, 2),
            "est_wall_s_sequential": round(R26_WALL_S * scale),
            "est_input_tokens": round(R26_PRIOR_INPUT_TOKENS * scale),
            "est_output_tokens": round(R26_PRIOR_OUTPUT_TOKENS * scale),
            "basis": f"R26: {R26_WORDS} words, 4 segments, 11 chunks, {R26_WALL_S} s; "
                     "R26 recorded no tokens, so the token figures are a rough prior"}


def world_id_for(slug: str) -> str:
    """The build's world id (one book, one world)."""
    return "w:book_" + (re.sub(r"[^a-z0-9]+", "_", slug.lower()).strip("_") or "book")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


# ------------------------------------------------------------------ receipt

_COUNTS = ("calls", "calls_without_usage", "input_tokens", "output_tokens",
           "cache_read_tokens", "cache_write_tokens")


def fresh_usage_log(run_dir: Path, name: str = "usage.jsonl") -> Path:
    """Move any existing ``usage.jsonl`` aside (to ``usage.jsonl.<n>``, the next
    free n) and start an empty one, so the log holds only this run. ``name``
    picks another per-run log (``objectives.jsonl``) with the same rule."""
    log = run_dir / name
    if log.exists():
        n = 1
        while (run_dir / f"{name}.{n}").exists():
            n += 1
        log.rename(run_dir / f"{name}.{n}")
    log.write_text("")
    return log


class Receipt:
    """Per-stage and total spend for one run, from ``usage_ledger`` snapshots.

    A stage's receipt is the field-by-field difference between the snapshot
    after it and the snapshot before it. Its ``cost_known`` reads only the lines
    the stage appended to the per-call log, because the ledger's own flag is
    cumulative."""

    def __init__(self, path: Path, log: Path, on_stage: Callable[[str, float], None]) -> None:
        self.path, self.log, self.on_stage = path, log, on_stage
        self.stages: dict[str, dict[str, Any]] = {}

    def _lines(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    @staticmethod
    def _priced(lines: list[str]) -> bool:
        for line in lines:
            try:
                if json.loads(line).get("cost_usd") is None:
                    return False
            except ValueError:
                return False
        return True

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """Time and meter the enclosed work; the receipt is written even when it raises."""
        before, n0, t0 = usage_ledger.snapshot(), len(self._lines()), time.time()
        try:
            yield
        finally:
            seconds = round(time.time() - t0, 1)
            after = usage_ledger.snapshot()
            entry: dict[str, Any] = {"seconds": seconds}
            entry.update({f: after[f] - before[f] for f in _COUNTS})
            entry["cost_usd"] = round(after["cost_usd"] - before["cost_usd"], 6)
            entry["cost_known"] = self._priced(self._lines()[n0:])
            self.stages[name] = entry
            self.on_stage(name, seconds)
            self.flush()

    def total(self) -> dict[str, Any]:
        """The final ledger snapshot, with the run's wall seconds."""
        snap = usage_ledger.snapshot()
        out = {f: snap[f] for f in _COUNTS}
        out.update({"cost_usd": round(snap["cost_usd"], 6), "cost_known": snap["cost_known"],
                    "seconds": round(sum(s["seconds"] for s in self.stages.values()), 1)})
        return out

    def flush(self) -> None:
        write_json(self.path, {"stages": self.stages, "total": self.total()})


# ---------------------------------------------------------------------- run


def run_book(book_dir: str | Path, out_dir: str | Path, model: Callable[[str, dict], Any], *,
             pass0: str = "sequential", merge_gate: bool = False, glean: bool = False,
             model_name: str = "injected", profile: bool = True,
             pipeline: str = "ingest-v2", max_words: int = LIBRARY_MAX_WORDS,
             classify_workers: int = LIBRARY_CLASSIFY_WORKERS,
             extract_workers: int = LIBRARY_EXTRACT_WORKERS) -> dict[str, Any]:
    """Build the book in ``book_dir`` into ``out_dir`` with ``model``; return meta.

    Raises ``BookRefused`` before any model call for a book it will not build,
    and ``BookRunAborted`` when pass-1 leaves failed chunks (nothing is
    committed; the staging stays). ``pipeline="library"`` builds with
    ``patternbuffer.build`` instead (BUILD-LIBRARY-V1 §7, ``_run_library``);
    ``max_words``, ``classify_workers`` and ``extract_workers`` are its
    BUILD-SPEED-V1 options (INGEST-V2 refuses any non-default value)."""
    if pipeline not in PIPELINES:
        raise BookRefused(f"unknown pipeline {pipeline!r} (pipelines: {', '.join(PIPELINES)})")
    # BUILD-SPEED-V1: every speed option is checked by exact type and range
    # first, whatever the pipeline (so 1500.0 or True never pass as a default),
    # and only then is a valid non-default value refused on INGEST-V2.
    if type(max_words) is not int or max_words < 100:
        raise BookRefused(f"max_words must be an integer of at least 100, got {max_words!r}")
    for name, value in (("classify_workers", classify_workers),
                        ("extract_workers", extract_workers)):
        if type(value) is not int or value < 1:
            raise BookRefused(f"{name} must be an integer of at least 1, got {value!r}")
    if pipeline == "library":
        return _run_library(book_dir, out_dir, model, pass0=pass0, merge_gate=merge_gate,
                            glean=glean, model_name=model_name, max_words=max_words,
                            classify_workers=classify_workers,
                            extract_workers=extract_workers)
    if (max_words, classify_workers, extract_workers) != (
            LIBRARY_MAX_WORDS, LIBRARY_CLASSIFY_WORKERS, LIBRARY_EXTRACT_WORKERS):
        raise BookRefused("--max-words, --classify-workers and --extract-workers are "
                          "--pipeline library options; INGEST-V2 takes none of them")
    from audit import run_audit

    plan = load_book(book_dir)
    # STAGE-MODELS-V1: a refused stage map stops the run before any directory or call
    # (model_shim is imported here, never at module load: a dry run imports no model)
    from model_shim import StageMapError, stage_map_receipt
    try:
        stage_models = stage_map_receipt()
    except StageMapError as exc:
        raise BookRunAborted(f"stage map refused: {exc}") from exc
    run_dir = Path(out_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    world_id = world_id_for(plan.slug)
    log = fresh_usage_log(run_dir)
    prior_env = os.environ.get(USAGE_ENV)
    os.environ[USAGE_ENV] = str(log)
    usage_ledger.reset()
    if profile:
        fresh_usage_log(run_dir, "objectives.jsonl")
    pipe = Pipeline(model, world_id, run_dir, max_workers=4, merge_gate=merge_gate,
                    profile=profile)
    timings: dict[str, float] = {}

    def flush_timings() -> None:  # rewritten as stages finish, so a failed run keeps its split
        write_json(run_dir / "timings.json", {**timings, **pipe.timings})

    def stage_done(name: str, seconds: float) -> None:
        timings[f"{name}_s"] = seconds
        flush_timings()

    receipt = Receipt(run_dir / "receipt.json", log, stage_done)
    try:
        with receipt.stage("pass0"):
            registry = pipe.pass0(segments=plan.segments, parallel=pass0 == "parallel",
                                  glean=glean)
        logger.info("pass-0: %d entities, %d attr aliases, %d edges",
                    len(registry.entities), len(registry.attributes), len(registry.places))
        # Registry as pass-0 left it; escape repair and commit extend the live one.
        pass0_registry = copy.deepcopy(registry)
        pass0_registry.save(run_dir / "registry_pass0.json")
        import alias_index
        alias_index.write_report(alias_index.build_report(pass0_registry, plan.segments),
                                 run_dir, title=f"Alias index ({run_dir.name})")

        with receipt.stage("pass1"):
            results = pipe.pass1(plan.chunks, registry)
        failed = [r.chunk_id for r in results if r.failed]
        if failed:
            raise BookRunAborted(f"noncanonical: chunks {failed} failed; staging retained")

        with receipt.stage("escape_repair"):
            results, escapes = pipe.repair_escapes(results, registry, plan.chunks)

        world_path = run_dir / "fresh_ingest.world"
        world_path.unlink(missing_ok=True)
        with receipt.stage("commit"):
            world = pipe.commit(world_path, registry, chunk_plan=plan.chunk_plan)

        with receipt.stage("audit"):
            with usage_ledger.label(stage="audit"):
                audit_report = run_audit(world, registry,
                                         pipe.audit_model(model) if profile else model)
        (run_dir / "ingest_dump.jsonl").write_text(dump(world.buffer))
        timings["total_s"] = round(sum(v for k, v in timings.items() if k != "total_s"), 1)
        flush_timings()
        meta = {
            "date": date.today().isoformat(),
            "book": plan.slug,
            "world_id": world_id,
            "model": model_name,
            "pipeline": "INGEST-V2 (registry-first)",
            "chapters": len(plan.chapters),
            "chunks": len(plan.chunks),
            "words": plan.words,
            "log_rows": world.buffer.head(),
            "entities": len({r.entity for r in world.buffer.all_rows()
                             if not r.entity.startswith("a:")}),
            "registry_escapes": escapes,
            "audit": {"adds": audit_report.applied_adds,
                      "retracts": audit_report.applied_retracts,
                      "dropped": len(audit_report.dropped_ops)},
            "pass0_mode": pass0,
            "glean": glean,
            "merge_gate": merge_gate,
            "registry_after_commit_entities": len(registry.entities),
            "timings": timings,
            "receipt": receipt.total(),
        }
        if stage_models is not None:    # absent without PB_EVAL_STAGE_MODELS: meta is as it was
            meta["stage_models"] = stage_models
        write_json(run_dir / "meta.json", meta)
        world.close()
        return meta
    finally:
        if prior_env is None:
            os.environ.pop(USAGE_ENV, None)
        else:
            os.environ[USAGE_ENV] = prior_env


# --------------------------------------------- BUILD-LIBRARY-V1: --pipeline library


def ledger_labelled(model: Callable[[str, dict], Any]) -> Callable[[str, dict], Any]:
    """``model`` with each call made under the usage ledger's label for the
    library's build label (``patternbuffer.build.current_label``), so
    ``usage.jsonl`` records the call's stage and unit and the stage map routes
    it (STAGE-MODELS-V1). A call made outside a build label goes as it is."""
    from patternbuffer.build import current_label

    def call(prompt: str, schema: dict) -> Any:
        found = current_label()
        if found is None:
            return model(prompt, schema)
        with usage_ledger.label(stage=found["stage"], unit=found["unit"]):
            return model(prompt, schema)

    return call


def library_registry_view(registry: Any, world_id: str) -> Any:
    """The library registry as the harness's ``WorldRegistry`` (each minted
    entry and persona id with its type and names), saved as
    ``registry_pass0.json`` for GRADE-LEAKS-V1's registry-leak check."""
    from registry import EntityCard, WorldRegistry

    return WorldRegistry(world_id=world_id, entities={
        ident.id: EntityCard(kind=ident.type, names=list(ident.names))
        for ident in registry.identities})


def library_chunks(run_dir: str | Path, book_plan: BookPlan) -> list[tuple[int, str]] | None:
    """``(chapter, text)`` per chunk of a ``--pipeline library`` run, re-planned
    from the book and the run's ``manifest.json`` (the library's plan is a pure
    function of the two); None for a run without one (an INGEST-V2 run)."""
    run = Path(run_dir)
    if not (run / LIBRARY_MANIFEST_FILE).exists():
        return None
    from patternbuffer import build

    manifest = build.Manifest.from_dict(json.loads((run / LIBRARY_MANIFEST_FILE).read_text()))
    meta_path = run / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    text = dict(book_plan.chapters)
    registry = build.Registry.from_manifest(manifest, text)
    chunks = build.plan(text, registry, max_words=meta.get("max_words", PRE_SPEED_MAX_WORDS))
    return [(c.chapter, c.text) for c in chunks]


def _attempts_json(result: Any) -> list[dict[str, Any]]:
    """A ``ChunkResult``'s attempts as JSON: each call's error and raw output."""
    return [{"error": a.error, "raw": a.raw} for a in result.attempts]


def _run_library(book_dir: str | Path, out_dir: str | Path, model: Callable[[str, dict], Any], *,
                 pass0: str, merge_gate: bool, glean: bool, model_name: str,
                 max_words: int = LIBRARY_MAX_WORDS,
                 classify_workers: int = LIBRARY_CLASSIFY_WORKERS,
                 extract_workers: int = LIBRARY_EXTRACT_WORKERS) -> dict[str, Any]:
    """``run_book(pipeline="library")``: the book built with ``patternbuffer.build``.

    Stages (receipted like INGEST-V2's): ``registry`` (the category passes),
    ``extract`` (one labelled call per chunk) and ``commit`` (the library's
    commit, then one classification sweep and the truth scan, as INGEST-V2's
    commit ends). Each chunk is committed at its chapter number, as INGEST-V2
    poses its chunks. Raises ``BookRunAborted`` when the manifest does not
    validate or a chunk is refused (nothing is committed)."""
    from patternbuffer import World, build

    if pass0 != "sequential" or merge_gate or glean:
        raise BookRefused("--pass0, --merge-gate and --glean are INGEST-V2 options; "
                          "--pipeline library takes none of them")
    plan = load_book(book_dir)
    from model_shim import StageMapError, stage_map_receipt
    try:
        stage_models = stage_map_receipt()
    except StageMapError as exc:
        raise BookRunAborted(f"stage map refused: {exc}") from exc
    run_dir = Path(out_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    world_id = world_id_for(plan.slug)
    log = fresh_usage_log(run_dir)
    prior_env = os.environ.get(USAGE_ENV)
    os.environ[USAGE_ENV] = str(log)
    usage_ledger.reset()
    timings: dict[str, float] = {}

    def stage_done(name: str, seconds: float) -> None:
        timings[f"{name}_s"] = seconds
        write_json(run_dir / "timings.json", timings)

    receipt = Receipt(run_dir / "receipt.json", log, stage_done)
    labelled = ledger_labelled(model)
    text = dict(plan.chapters)
    try:
        with receipt.stage("registry"):
            manifest = build.category_passes(text, labelled)
        write_json(run_dir / LIBRARY_MANIFEST_FILE, manifest.to_dict())
        try:
            registry = build.Registry.from_manifest(manifest, text)
        except build.ManifestError as exc:
            write_json(run_dir / "manifest_problems.json", exc.problems)
            raise BookRunAborted(f"the category passes' manifest does not validate: "
                                 f"{len(exc.problems)} problem(s), see manifest_problems.json"
                                 ) from exc
        library_registry_view(registry, world_id).save(run_dir / "registry_pass0.json")
        chunks = build.plan(text, registry, max_words=max_words)
        write_json(run_dir / "plan.json", [c.to_dict() for c in chunks])

        with receipt.stage("extract"):
            results = build.extract(chunks, registry, labelled, workers=extract_workers)
        # Raw model output is diagnostic only: these files, never a world (k10).
        retried = [r for r in results if len(r.attempts) > 1]
        if retried:
            write_json(run_dir / "retried_chunks.json",
                       [{"chunk": r.index, "attempts": _attempts_json(r)} for r in retried])
        refused = [r.index for r in results if r.error]
        if refused:
            write_json(run_dir / "refused_chunks.json",
                       [{"chunk": r.index, "error": r.error, "attempts": _attempts_json(r)}
                        for r in results if r.error])
            raise BookRunAborted(f"chunks {refused} were refused at extraction; nothing committed")

        world_path = run_dir / "fresh_ingest.world"
        world_path.unlink(missing_ok=True)
        with receipt.stage("commit"):
            world = World(world_path, world_id=world_id, model=model)
            with usage_ledger.label(stage="commit"):
                built = build.commit(world, registry, results,
                                     time_of=lambda i: float(chunks[i].chapter),
                                     ingest_kwargs={"classify": "defer"})
                world.classifier.classify_all(batch_size=40, workers=classify_workers)
            world.truth.scan()
        write_json(run_dir / "chunk_spans.json", {"chunks": list(built.chunk_spans)})
        write_json(run_dir / "build_receipt.json", built.to_dict())
        (run_dir / "ingest_dump.jsonl").write_text(dump(world.buffer))
        timings["total_s"] = round(sum(v for k, v in timings.items() if k != "total_s"), 1)
        write_json(run_dir / "timings.json", timings)
        meta = {
            "date": date.today().isoformat(),
            "book": plan.slug,
            "world_id": world_id,
            "model": model_name,
            "pipeline": "BUILD-LIBRARY-V1 (patternbuffer.build)",
            "chapters": len(plan.chapters),
            "chunks": len(chunks),
            "words": plan.words,
            "log_rows": world.buffer.head(),
            "entities": len({r.entity for r in world.buffer.all_rows()
                             if not r.entity.startswith("a:")}),
            "manifest_entries": len(manifest.entries),
            "minted": len(built.minted),
            "mentions": built.mentions,
            "escapes": built.escapes,
            "proposals": built.proposals,
            "correlations": built.correlations,
            "rejections": built.rejections,
            "gate_refused": sum(len(r.gate_refused) for r in results),
            "refused_lines": sum(len(r.refused) for r in results),
            "max_words": max_words,
            "extract_workers": extract_workers,
            "classify_workers": classify_workers,
            "timings": timings,
            "receipt": receipt.total(),
        }
        if stage_models is not None:
            meta["stage_models"] = stage_models
        write_json(run_dir / "meta.json", meta)
        world.close()
        return meta
    finally:
        if prior_env is None:
            os.environ.pop(USAGE_ENV, None)
        else:
            os.environ[USAGE_ENV] = prior_env


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--book", required=True, help="book directory (ch01.md ... chNN.md)")
    ap.add_argument("--out", default=None, help="run directory (required unless --dry-run)")
    ap.add_argument("--pass0", choices=("sequential", "parallel"), default="sequential",
                    help="sequential: establish then extend with prior (default); "
                         "parallel: establish each chapter alone, reduce by merge")
    ap.add_argument("--merge-gate", action="store_true",
                    help="run the R25 merge gate at commit (one more model call per 25 candidates)")
    ap.add_argument("--glean", action="store_true",
                    help="after each segment's registry, one call for missed E| lines")
    ap.add_argument("--no-profile", action="store_true",
                    help="skip objectives.jsonl (calls are still labelled in usage.jsonl)")
    ap.add_argument("--dry-run", action="store_true",
                    help="read the book and print counts and an estimate; import no model")
    ap.add_argument("--pipeline", choices=PIPELINES, default="ingest-v2",
                    help="ingest-v2 (default) or library (BUILD-LIBRARY-V1: patternbuffer.build)")
    ap.add_argument("--max-words", type=int, default=LIBRARY_MAX_WORDS,
                    help="library pipeline: the most words in a chunk, an int of at least 100 "
                         f"(default {LIBRARY_MAX_WORDS})")
    ap.add_argument("--classify-workers", type=int, default=LIBRARY_CLASSIFY_WORKERS,
                    help="library pipeline: parallel classification batch calls at commit "
                         f"(default {LIBRARY_CLASSIFY_WORKERS}; 1 is serial)")
    ap.add_argument("--extract-workers", type=int, default=LIBRARY_EXTRACT_WORKERS,
                    help="library pipeline: parallel chunk extraction calls "
                         f"(default {LIBRARY_EXTRACT_WORKERS})")
    args = ap.parse_args(argv)
    if args.max_words < 100:
        ap.error("--max-words must be an integer of at least 100")
    if args.classify_workers < 1 or args.extract_workers < 1:
        ap.error("--classify-workers and --extract-workers must be at least 1")
    if not args.dry_run and not args.out:
        ap.error("--out is required unless --dry-run")
    return args


def main(argv: list[str] | None = None,
         model: Callable[[str, dict], Any] | None = None) -> int:
    """CLI entry. ``model`` is for tests (a scripted double); the CLI leaves it
    unset and the real shim is imported only for a real run."""
    args = parse_args(argv)
    try:
        plan = load_book(args.book)
        if args.dry_run:
            print(json.dumps({"book": plan.slug, "segments": len(plan.chapters),
                              "chunks": len(plan.chunks), **estimate(plan)}, indent=2))
            return 0
        if model is None:
            from model_shim import claude_model, MODEL
            model, model_name = claude_model, MODEL
        else:
            model_name = "injected"
        meta = run_book(args.book, args.out, model, pass0=args.pass0,
                        merge_gate=args.merge_gate, glean=args.glean, model_name=model_name,
                        profile=not args.no_profile, pipeline=args.pipeline,
                        max_words=args.max_words, classify_workers=args.classify_workers,
                        extract_workers=args.extract_workers)
    except (BookRefused, BookRunAborted) as exc:
        raise SystemExit(f"ABORT: {exc}") from exc
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
