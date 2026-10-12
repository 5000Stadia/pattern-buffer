"""INGEST-V2 orchestration (spec §4): pass-0 registry -> parallel pass-1
extraction (staged, never touching the World) -> single ordered commit ->
pass-2 audit.

Stage-all, commit-once: a run with permanently failed chunks is
noncanonical by definition — it commits nothing (including registry seed
rows) and leaves its staging directory as the resumable state.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from patternbuffer import World

try:
    import grammar
    from registry import RegistryWorldMismatch, WorldRegistry, establish, glean, seed_items
except ImportError:  # imported as evals.harness.pipeline (e.g. via grade_registry)
    from evals.harness import grammar
    from evals.harness.registry import (RegistryWorldMismatch, WorldRegistry, establish,
                                        glean, seed_items)

logger = logging.getLogger(__name__)

_glean = glean  # pass0 has a ``glean`` parameter that shadows the function

REGISTRY_TOKEN_CAP = 6000  # ~chars/4; above this the deterministic slice applies

_PASS1_PROMPT = """\
Extract world-state assertions from the passage as GRAMMAR LINES, one per
line, no other output:

  entity|attribute|value|flags

- value: @entity_id for entity refs; JSON ({{...}}, [...], "...") for
  structured/delimiter-bearing literals (approximate quantities as bounds:
  {{"gte": 40000}}); ?{{"policy": "invent_under_canon"}} for explicitly
  unresolved aspects; bare scalar otherwise.
- flags (comma-separated): vf=<day> valid-from on the timeline; vt=<day>
  valid-to; t timeless (ONLY identity/structure: kind, names, fixed
  adjacency); f=knows:<person_id> knowledge-frame row; s=<status> one of
  stated|observed|inferred|assumed; doc=<doc:id> document-claimed;
  cb=<event:id> caused-by.
- Use ONLY entity ids from the registry below. If the passage truly
  introduces something the registry lacks, still emit the line with your
  best id — it will be quarantined and repaired, never silently dropped.
- Attributes: use the registry's canonical attribute names; 'in' for all
  containment/location.
- CANON VS KNOWLEDGE: facts about the world are canon rows (no f= flag) at
  their TRUE historical time — including facts revealed late: a character's
  Ch.N confession about earlier events yields canon rows with the EARLIER
  vf. f=knows:X rows are ADDITIONAL copies marking that X knows it — never
  replacements. A scene where A tells B an established fact yields knows:B
  rows only.
- Status: stated for asserted fact; inferred for a character's deduction;
  assumed for a working theory. Document claims carry doc=.
- Never invent; atmosphere and sensory texture are not assertions.

TIMELINE: {timeline}

REGISTRY:
{registry_slice}

PASSAGE (chunk {chunk_id}):
{text}
"""

_PASS1_SCHEMA = {
    "type": "object",
    "properties": {"lines": {"type": "array", "items": {"type": "string"}}},
    "required": ["lines"],
}


SOURCE_SEGMENTS_FILE = "source_segments.json"
ALIAS_INDEX_FILE = "alias_index.json"


def canonical_sha256(obj: Any) -> str:
    """sha256 of the canonical JSON of ``obj`` (sorted keys, no spaces, UTF-8)."""
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def registry_payload(registry: WorldRegistry) -> dict[str, Any]:
    """The registry as ``WorldRegistry.save`` writes it (places as lists)."""
    payload = asdict(registry)
    payload["places"] = [list(p) for p in registry.places]
    return payload


def write_source_segments(run_dir: Path, parts: list[str]) -> Path:
    """Write the exact parts pass-0 read, with their sha256, beside registry.json
    (ALIAS-INDEX-V1 Part B r3). Commit reads this file, never memory."""
    path = Path(run_dir) / SOURCE_SEGMENTS_FILE
    path.write_text(json.dumps({"segments": list(parts), "sha256": canonical_sha256(list(parts))},
                               indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return path


def read_source_segments(path: Path) -> list[str]:
    """Read and verify ``source_segments.json``. A malformed file or a sha256
    that does not match the segments raises ``ValueError``."""
    try:
        data = json.loads(Path(path).read_text())
        parts, digest = data["segments"], data["sha256"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"{path}: unreadable source segments ({exc})") from exc
    if not isinstance(parts, list) or not all(isinstance(x, str) for x in parts):
        raise ValueError(f"{path}: segments must be a list of strings")
    if canonical_sha256(parts) != digest:
        raise ValueError(f"{path}: sha256 does not match its segments (tampered or truncated)")
    require_source(parts, str(path))
    return parts


def require_source(parts: Any, where: str = "segments") -> None:
    """A source is a non-empty list of strings (ALIAS-INDEX-V1 r4): anything
    else raises before any write. A bare string is refused rather than read as
    its characters."""
    if not isinstance(parts, list) or not all(isinstance(x, str) for x in parts):
        raise ValueError(f"{where}: segments must be a list of strings")
    if not parts:
        raise ValueError(f"{where}: an empty segment list is not a source")


def resolve_reconcile(mode: Any, part_b_runs: bool) -> bool:
    """Whether to run the engine's ``reconcile`` (ALIAS-INDEX-V1 r4.2). ``"auto"``
    reconciles exactly when Part B runs (``alias_distinct`` on and a source);
    ``True`` / ``False`` force it either way, for measurement."""
    if not (mode == "auto" or mode is True or mode is False):
        raise ValueError(f"reconcile must be 'auto', True or False, got {mode!r}")
    return part_b_runs if mode == "auto" else bool(mode)


def finalize_identity(w: World, *, reconcile: bool) -> None:
    """The one identity finalization (ALIAS-INDEX-V1 r4), shared by
    ``Pipeline.commit`` and ``grade_registry.seeded_registry``:
    ``promote_identity_proposals()``, then ``reconcile()`` when asked, then the
    host's ``confirm_frame_owners``."""
    w.registry.promote_identity_proposals()
    if reconcile:
        w.registry.reconcile()
    Pipeline.confirm_frame_owners(w)


def seed_world(w: World, registry: WorldRegistry) -> None:
    """Phase 1 of the single commit: attribute aliases, then the registry's rows.
    Shared by ``Pipeline.commit`` and ``grade_registry.seeded_registry`` so a
    seeded grade is the world the commit builds."""
    for alias, canonical in sorted(registry.attributes.items()):
        try:
            w.ingestor.add_attribute_alias(alias, canonical)
        except ValueError as exc:
            # The engine refuses some aliases (an inverse relation such as
            # `holds` cannot be renamed, GATE-INVERSE-ALIAS-V1). A registry
            # proposing one loses that alias, not the world build.
            logger.warning("commit: attribute alias %r -> %r refused: %s",
                           alias, canonical, exc)
    w.ingest_structured(seed_items(registry))


def alias_distinct_pass(w: World, registry: WorldRegistry, segments: list[str]) -> dict[str, Any]:
    """ALIAS-INDEX-V1 Part B: with the registry seeded into ``w`` and nothing
    after it, build the alias report over ``segments`` and write the host's
    ``distinct_from`` for its strong non-person pairs. Returns the report
    ``commit`` saves as ``alias_index.json`` (Part A report, plus ``written``,
    ``report_only``, ``registry_sha256``, ``segments_sha256``). An empty
    ``segments`` raises ``ValueError``."""
    require_source(segments)
    try:  # lazy: a commit with the pass off never loads it
        import alias_index
    except ImportError:
        from evals.harness import alias_index

    report = alias_index.build_report(registry, segments)
    acted = alias_index.apply_distinctness(w, registry, report)
    return {**report, "part_b": "applied", **acted,
            "registry_sha256": canonical_sha256(registry_payload(registry)),
            "segments_sha256": canonical_sha256(list(segments))}


@dataclass
class ChunkResult:
    chunk_id: int
    items: list[dict] = field(default_factory=list)
    orphans: list[grammar.Orphan] = field(default_factory=list)
    rejects: list[grammar.Reject] = field(default_factory=list)
    failed: bool = False
    error: str = ""


class Pipeline:
    def __init__(
        self,
        model: Callable[[str, dict], Any],
        world_id: str,
        run_dir: str | Path,
        max_workers: int = 4,
        reject_threshold: float = 0.20,
        alias_slice: bool = False,
        alias_distinct: bool = True,
        reconcile: Any = "auto",
    ) -> None:
        self.model = model
        self.world_id = world_id
        self.run_dir = Path(run_dir)
        self.staging = self.run_dir / "staging"
        self.staging.mkdir(parents=True, exist_ok=True)
        self.max_workers = max_workers
        self.reject_threshold = reject_threshold
        # R24 ALIAS-INDEX-V1: when True, the size-guard slice keeps the ids the
        # alias index hits (plus ids sharing a string with them) instead of the
        # raw substring test. Off by default: the slice is unchanged.
        self.alias_slice = alias_slice
        # R24 ALIAS-INDEX-V1 Part B: at commit, right after the registry is
        # seeded, write the host's `distinct_from` for strong non-person
        # distinctness pairs found in the source. False restores the
        # pre-Part-B commit exactly (nothing read, nothing written).
        self.alias_distinct = alias_distinct
        # ALIAS-INDEX-V1 r4.2: whether the commit runs the engine's `reconcile`.
        # "auto" = exactly when Part B runs (alias_distinct on and a source), so
        # a commit with no source is today's commit; True/False force it.
        resolve_reconcile(reconcile, False)  # validates
        self.reconcile = reconcile
        # R26 BUILD-TIMINGS-V1: wall seconds per stage, filled by pass0 and
        # commit (the runner adds the rest). Observation only.
        self.timings: dict[str, Any] = {}

    # ------------------------------------------------------------- pass 0

    def pass0(
        self,
        text: str | None = None,
        prior: WorldRegistry | None = None,
        segments: list[str] | None = None,
        parallel: bool = False,
        glean: bool = False,
    ) -> WorldRegistry:
        """Establish/extend the registry. With ``segments`` the document is
        scaffolded incrementally (establish over the first segment, extend
        over each subsequent one) — smaller calls, same interface.

        ``parallel=True`` (R26): each segment is established on its own (no
        prior) on the worker pool, then the segment registries are reduced in
        segment order with ``WorldRegistry.merge`` (same id, one card; first
        decisions pinned). ``glean=True``: after a segment's registry is made,
        one more call asks only for entities it missed. Per-segment call
        seconds land in ``self.timings``."""
        parts = segments if segments is not None else [text or ""]
        if parallel:
            registry = self._pass0_parallel(parts, prior, glean)
        else:
            registry = prior
            seg_s: list[float] = []
            glean_s: list[float] = []
            for part in parts:
                t = time.perf_counter()
                registry = establish(part, self.model, self.world_id, prior=registry)
                seg_s.append(round(time.perf_counter() - t, 2))
                if glean:
                    t = time.perf_counter()
                    registry = _glean(part, registry, self.model, self.world_id)
                    glean_s.append(round(time.perf_counter() - t, 2))
            self.timings["pass0_segment_s"] = seg_s
            if glean:
                self.timings["pass0_glean_s"] = glean_s
        assert registry is not None
        registry.save(self.run_dir / "registry.json")
        # Part B r3: the source is durable, so a fresh Pipeline on this run_dir
        # commits the same world. The exact parts this call read.
        write_source_segments(self.run_dir, parts)
        return registry

    def _pass0_one(self, part: str, glean: bool) -> tuple[WorldRegistry, float, float]:
        t = time.perf_counter()
        reg = establish(part, self.model, self.world_id, prior=None)
        call_s = round(time.perf_counter() - t, 2)
        glean_s = 0.0
        if glean:
            t = time.perf_counter()
            reg = _glean(part, reg, self.model, self.world_id)
            glean_s = round(time.perf_counter() - t, 2)
        return reg, call_s, glean_s

    def _pass0_parallel(
        self, parts: list[str], prior: WorldRegistry | None, glean: bool
    ) -> WorldRegistry:
        if prior is not None and prior.world_id != self.world_id:
            raise RegistryWorldMismatch(
                f"prior registry is for {prior.world_id!r}, not {self.world_id!r}"
            )
        t0 = time.perf_counter()
        pool = ThreadPoolExecutor(max_workers=self.max_workers)
        try:
            futures = [pool.submit(self._pass0_one, part, glean) for part in parts]
            done = [f.result() for f in futures]  # segment order; first failure raises
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)  # QuotaExhausted etc. propagate
            raise
        pool.shutdown()
        self.timings["pass0_wall_s"] = round(time.perf_counter() - t0, 2)
        self.timings["pass0_segment_s"] = [d[1] for d in done]
        if glean:
            self.timings["pass0_glean_s"] = [d[2] for d in done]
        t = time.perf_counter()
        registry = prior
        for reg, _, _ in done:
            if registry is None:
                registry = reg
            else:
                registry.merge(reg)
        self.timings["pass0_reduce_s"] = round(time.perf_counter() - t, 3)
        assert registry is not None
        return registry

    # ------------------------------------------------------------- pass 1

    def _registry_slice(self, registry: WorldRegistry, chunk_text: str) -> str:
        full = json.dumps(
            {
                "entities": {eid: {"kind": c.kind, "names": c.names, "aliases": c.aliases}
                             for eid, c in sorted(registry.entities.items())},
                "attributes": registry.attributes,
                "places": [list(p) for p in registry.places],
            },
            indent=0,
        )
        if len(full) <= REGISTRY_TOKEN_CAP * 4:
            return full
        # Deterministic size-guard slice (spec §4.2): attribute map +
        # timeline + place graph + persons + lexical alias hits.
        lowered = chunk_text.lower()
        alias_keep: set[str] | None = None
        if self.alias_slice:
            import alias_index  # lazy: the default path never loads it

            alias_keep = alias_index.slice_ids(registry, chunk_text)
        keep: dict[str, Any] = {}
        for eid, card in sorted(registry.entities.items()):
            hit = eid.startswith("person:") or (
                eid in alias_keep if alias_keep is not None else any(
                    a in lowered for a in card.aliases + [n.lower() for n in card.names]
                )
            )
            if hit:
                keep[eid] = {"kind": card.kind, "names": card.names, "aliases": card.aliases}
        return json.dumps(
            {"entities": keep, "attributes": registry.attributes,
             "places": [list(p) for p in registry.places]},
            indent=0,
        )

    def _extract_chunk(
        self, chunk_id: int, text: str, cursor: float, registry: WorldRegistry
    ) -> ChunkResult:
        prompt = _PASS1_PROMPT.format(
            timeline=f"{registry.timeline.origin} | anchors: {registry.timeline.anchors}",
            registry_slice=self._registry_slice(registry, text),
            chunk_id=chunk_id,
            text=text,
        )
        result = ChunkResult(chunk_id=chunk_id)
        for attempt in (1, 2):
            try:
                out = self.model(prompt, _PASS1_SCHEMA)
            except Exception as exc:
                if type(exc).__name__ == "QuotaExhausted":
                    raise
                result.error = str(exc)
                continue
            items, orphans, rejects = grammar.parse(out["lines"], registry, cursor)
            if grammar.reject_rate(items, orphans, rejects) > self.reject_threshold:
                result.error = f"reject rate over threshold ({len(rejects)} rejects)"
                continue
            result.items, result.orphans, result.rejects = items, orphans, rejects
            return result
        result.failed = True
        return result

    def pass1(
        self,
        chunks: list[tuple[float, str]],   # (cursor, text) in source order
        registry: WorldRegistry,
    ) -> list[ChunkResult]:
        """Parallel extraction. Stages every chunk to disk; touches no World."""
        results: dict[int, ChunkResult] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self._extract_chunk, i, text, cursor, registry): i
                for i, (cursor, text) in enumerate(chunks)
            }
            for fut in as_completed(futures):
                r = fut.result()
                results[r.chunk_id] = r
                self._stage(r)
                logger.info("chunk %d: %s (%d items, %d orphans, %d rejects)",
                            r.chunk_id, "FAILED" if r.failed else "ok",
                            len(r.items), len(r.orphans), len(r.rejects))
        return [results[i] for i in sorted(results)]

    def _stage(self, r: ChunkResult) -> None:
        path = self.staging / f"chunk_{r.chunk_id:03d}.jsonl"
        header = {"world_id": self.world_id, "chunk_id": r.chunk_id,
                  "failed": r.failed, "error": r.error,
                  "orphans": [o.__dict__ for o in r.orphans],
                  "rejects": [j.__dict__ for j in r.rejects]}
        lines = [json.dumps(header, sort_keys=True)]
        lines += [json.dumps(it, sort_keys=True) for it in r.items]
        path.write_text("\n".join(lines) + "\n")

    def load_staged(self) -> list[ChunkResult]:
        out = []
        for path in sorted(self.staging.glob("chunk_*.jsonl")):
            lines = path.read_text().splitlines()
            header = json.loads(lines[0])
            if header["world_id"] != self.world_id:
                raise RegistryWorldMismatch(
                    f"staged chunk {path} belongs to {header['world_id']!r}"
                )
            r = ChunkResult(chunk_id=header["chunk_id"], failed=header["failed"],
                            error=header.get("error", ""))
            r.orphans = [grammar.Orphan(**o) for o in header["orphans"]]
            r.rejects = [grammar.Reject(**j) for j in header["rejects"]]
            r.items = [json.loads(l) for l in lines[1:]]
            out.append(r)
        return out

    # -------------------------------------------- escape repair (spec §5.1)

    def repair_escapes(
        self,
        results: list[ChunkResult],
        registry: WorldRegistry,
        chunks: list[tuple[float, str]],
    ) -> tuple[list[ChunkResult], int]:
        """Pre-commit escape repair (spec §5.1): extend the registry over the
        orphaning chunks' text, then **re-parse the quarantined lines** —
        deterministic, no model call — and re-extract a chunk only if its
        lines still orphan. Repaired lines append after the chunk's accepted
        items (chunk-internal order shifts deterministically)."""
        orphaned = [r for r in results if r.orphans]
        if not orphaned:
            return results, 0
        escape_count = sum(len(r.orphans) for r in orphaned)
        source = "\n\n".join(chunks[r.chunk_id][1] for r in orphaned)
        logger.info("registry escapes: %d orphan(s) across %d chunk(s); extending",
                    escape_count, len(orphaned))
        establish(source, self.model, self.world_id, prior=registry)
        registry.save(self.run_dir / "registry.json")
        for r in orphaned:
            cursor, text = chunks[r.chunk_id]
            lines = [o.line for o in r.orphans]
            items, still_orphaned, rejects = grammar.parse(lines, registry, cursor)
            if still_orphaned or rejects:
                logger.info("chunk %d: re-parse insufficient; re-extracting", r.chunk_id)
                repaired = self._extract_chunk(r.chunk_id, text, cursor, registry)
            else:
                repaired = ChunkResult(
                    chunk_id=r.chunk_id,
                    items=r.items + items,
                    rejects=r.rejects,
                )
            results[r.chunk_id] = repaired
            self._stage(repaired)
        return results, escape_count

    # ------------------------------------------------------------- commit

    @staticmethod
    def confirm_frame_owners(w: World) -> int:
        """The book pipeline's host decision (IDENTITY-ROOT-CAUSES-V1 §4): the
        engine never auto-merges a closure that owns a `knows:` frame, so such
        a pair waits as a proposal with auto-decline code `frame_owner` — a
        pair that passes the automatic gate in every other respect. A book
        world has no host, so the pipeline is it: it `confirm`s each one,
        logged as `decided_by · host`. A book run reaches the same merges as
        before, each now a visible decision instead of a silent engine act.
        Proposals are re-read after every merge, because a merge changes what
        the next pair relates to. Returns the merges made."""
        merged = 0
        tried: set[tuple[str, str]] = set()
        while True:
            pending = [
                p for p in w.registry.enumerate_proposals()
                if p["auto_decline"]["code"] == "frame_owner"
                and (p["a"], p["b"]) not in tried
            ]
            if not pending:
                break
            p = pending[0]
            tried.add((p["a"], p["b"]))
            receipt = w.registry.confirm(p["a"], p["b"])
            if receipt["outcome"] == "merged":
                merged += 1
        if merged:
            logger.info("confirm_frame_owners: %d merge(s)", merged)
        return merged

    def _alias_source(self, segments: list[str] | None) -> tuple[list[str] | None, str]:
        """The source Part B reads (ALIAS-INDEX-V1 r3): an explicit ``segments``
        argument, else the verified ``run_dir/source_segments.json`` (a bad
        sha256 raises), else none. An empty list, explicit or in the file, raises
        (r4)."""
        if segments is not None:
            require_source(segments)
            return list(segments), "explicit"
        path = self.run_dir / SOURCE_SEGMENTS_FILE
        if path.exists():
            return read_source_segments(path), "file"
        return None, "none"

    def commit(
        self,
        world_path: str | Path,
        registry: WorldRegistry,
        segments: list[str] | None = None,
    ) -> World:
        """The single commit (spec §3.3): seed registry -> (Part B) -> replay
        chunks in order. Refuses if any chunk failed or still carries orphans.

        ALIAS-INDEX-V1 r4: identity is finalized by ``finalize_identity``
        (promote, ``reconcile`` per ``self.reconcile``, confirm frame owners).
        ALIAS-INDEX-V1 Part B (``alias_distinct``, default on): after the seed,
        strong non-person distinctness pairs found in the source get
        ``distinct_from``, and ``run_dir/alias_index.json`` records what was
        written. The source is ``segments`` if given, else the verified
        ``run_dir/source_segments.json``; with neither, Part B is skipped (a
        warning, a ``skipped`` report) and, under ``reconcile="auto"``, nothing
        reconciles either: the log is exactly the pre-Part-B log. A source that fails its sha256 raises before anything is written."""
        if registry.world_id != self.world_id:
            raise RegistryWorldMismatch(
                f"registry is for {registry.world_id!r}; commit target is "
                f"{self.world_id!r} — refusing to seed (spec §3.3)"
            )
        source, source_kind = (self._alias_source(segments) if self.alias_distinct
                               else (None, "off"))
        results = self.load_staged()
        bad = [r for r in results if r.failed or r.orphans]
        if bad:
            raise RuntimeError(
                f"noncanonical run: chunks {[r.chunk_id for r in bad]} failed or "
                "orphaned; nothing committed (staging retained)"
            )
        world_path = Path(world_path)
        if world_path.exists():
            raise RuntimeError(f"commit target {world_path} already exists")
        t_seed = time.perf_counter()
        registry.save(self.run_dir / "registry.json")  # the artifact always
        w = World(world_path, world_id=self.world_id, model=self.model)  # rides beside the dump
        w.ingestor.classify_inline = False
        seed_world(w, registry)
        alias_s = 0.0
        do_reconcile = resolve_reconcile(self.reconcile,
                                         self.alias_distinct and source is not None)
        if self.alias_distinct:
            t_alias = time.perf_counter()
            if source is None:
                logger.warning("commit: no source segments for the alias pass "
                               "(no argument, no %s); Part B skipped", SOURCE_SEGMENTS_FILE)
                alias_report: dict[str, Any] = {"part_b": "skipped", "reason": "no_source"}
            else:
                alias_report = alias_distinct_pass(w, registry, source)
                alias_report["source"] = source_kind
                alias_report["reconcile"] = do_reconcile
            (self.run_dir / ALIAS_INDEX_FILE).write_text(
                json.dumps(alias_report, indent=2, sort_keys=True) + "\n")
            alias_s = time.perf_counter() - t_alias
        t_replay = time.perf_counter()
        # Per-item ingest with gate quarantine: the engine's write-time
        # guards (e.g. the containment self-edge rejection, LIVE-FINDINGS
        # Fix 1) raise on a malformed extracted row. Append-only means a
        # half-applied batch can't be retried (it would duplicate the rows
        # that landed before the raise), so we ingest one item at a time and
        # quarantine the offenders — like orphans/rejects — rather than let
        # one bad row abort the whole world build.
        quarantined: list[dict] = []
        for r in results:
            for item in r.items:
                try:
                    w.ingest_structured([item])
                except ValueError as exc:
                    # genuine gate failure (e.g. generated-into-canon) still raises
                    quarantined.append({"item": item, "error": str(exc)})
                    logger.warning("commit quarantine (chunk %d): %s — %s",
                                   r.chunk_id, exc, item)
                else:
                    # INGEST-HARDENING-V1: a structurally-invalid edge (cycle /
                    # self-edge / lateral self-loop) is now SKIPPED (not raised)
                    # with a typed receipt — surface those as quarantine too.
                    for s in w.ingestor.last_skipped:
                        quarantined.append({"item": item, "error": s.reason})
                        logger.warning("commit quarantine (chunk %d): skipped %s — %s",
                                       r.chunk_id, item, s.reason)
        if quarantined:
            (self.run_dir / "quarantined.json").write_text(
                json.dumps(quarantined, indent=0, sort_keys=True))
            logger.info("commit: %d item(s) quarantined at the gate", len(quarantined))
        t_classify = time.perf_counter()
        w.classifier.classify_all(batch_size=40)
        t_promote = time.perf_counter()
        # 036: gate same_as now proposes; promotion happens HERE, where the
        # whole world is in view. IDENTITY-ROOT-CAUSES-V1 §4: the engine leaves
        # a pair that owns a `knows:` frame to the host; a book world's host is
        # this pipeline. ALIAS-INDEX-V1 r4: the shared finalization, with
        # `reconcile` per the mode (Part B's rows are already in the log).
        finalize_identity(w, reconcile=do_reconcile)
        t_scan = time.perf_counter()
        w.truth.scan()
        t_end = time.perf_counter()
        self.timings.update({
            "commit_seed_s": round(t_replay - t_seed - alias_s, 2),
            "commit_replay_s": round(t_classify - t_replay, 2),
            "commit_classify_all_s": round(t_promote - t_classify, 2),
            "commit_promotion_s": round(t_scan - t_promote, 2),
            "commit_truth_scan_s": round(t_end - t_scan, 2),
        })
        if self.alias_distinct:
            self.timings["commit_alias_distinct_s"] = round(alias_s, 2)
        logger.info("committed: %d rows", w.buffer.head())
        return w
