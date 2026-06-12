"""INGEST-V2 orchestration (spec §4): pass-0 registry -> parallel pass-1
extraction (staged, never touching the World) -> single ordered commit ->
pass-2 audit.

Stage-all, commit-once: a run with permanently failed chunks is
noncanonical by definition — it commits nothing (including registry seed
rows) and leaves its staging directory as the resumable state.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from patternbuffer import World

import grammar
from registry import RegistryWorldMismatch, WorldRegistry, establish, seed_items

logger = logging.getLogger(__name__)

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
    ) -> None:
        self.model = model
        self.world_id = world_id
        self.run_dir = Path(run_dir)
        self.staging = self.run_dir / "staging"
        self.staging.mkdir(parents=True, exist_ok=True)
        self.max_workers = max_workers
        self.reject_threshold = reject_threshold

    # ------------------------------------------------------------- pass 0

    def pass0(self, text: str, prior: WorldRegistry | None = None) -> WorldRegistry:
        registry = establish(text, self.model, self.world_id, prior=prior)
        registry.save(self.run_dir / "registry.json")
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
        keep: dict[str, Any] = {}
        for eid, card in sorted(registry.entities.items()):
            hit = eid.startswith("person:") or any(
                a in lowered for a in card.aliases + [n.lower() for n in card.names]
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
        """Pre-commit: extend the registry over orphaning chunks' text, then
        re-extract those chunks. Returns (results, escape_count)."""
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
            repaired = self._extract_chunk(r.chunk_id, text, cursor, registry)
            results[r.chunk_id] = repaired
            self._stage(repaired)
        return results, escape_count

    # ------------------------------------------------------------- commit

    def commit(self, world_path: str | Path, registry: WorldRegistry) -> World:
        """The single commit (spec §3.3): seed registry -> replay chunks in
        order. Refuses if any chunk failed or still carries orphans."""
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
        w = World(world_path, world_id=self.world_id, model=self.model)
        w.ingestor.classify_inline = False
        for alias, canonical in sorted(registry.attributes.items()):
            w.ingestor.add_attribute_alias(alias, canonical)
        w.ingest_structured(seed_items(registry))
        for r in results:
            w.ingest_structured(r.items)
        w.classifier.classify_all(batch_size=40)
        w.truth.scan()
        logger.info("committed: %d rows", w.buffer.head())
        return w
