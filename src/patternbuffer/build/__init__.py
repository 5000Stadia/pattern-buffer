"""``patternbuffer.build``: registry-first world building (BUILD-LIBRARY-V1).

Identity is decided once, first, by code. A package outside the engine core,
as ``service`` and ``mirror`` are: the core never imports it, and it writes
only through the porcelain (``ingest_structured``, ``correlate``, ``reject``),
so the ingestor does every write and the role-authority matrix holds.

Six functions:

1. :class:`Manifest` (with :class:`Entry`, :class:`Persona`): the cast, places
   and things, anchored by exact quotes; ``validate`` raises one
   :class:`ManifestError` listing every problem.
2. :meth:`Registry.from_manifest`: ids minted by code from one allocator;
   ``entries()`` for a host's cast author; ``resolve()`` with the effective
   per-sentence gate and type-hint compatibility.
3. :func:`plan`: chunks cut at paragraph breaks, split before reveals, with
   sentence-scoped candidates.
4. :func:`extract`: one labelled model call per chunk, in a pool, checked by
   code (:class:`ChunkResult`, :class:`Escape`, :class:`Pick`; a refused answer is
   asked once more, an unused declaration is a :class:`DroppedHandle`, every
   call a :class:`Attempt`).
5. :func:`commit`: one serial writer, shape rows first, ids allocated before any
   fact, proposals never merges, the persona link only by ``correlate``.
6. :func:`category_passes`: a manifest for prose with no author.

A typical build::

    registry = Registry.from_manifest(manifest, text_by_chapter)
    chunks = plan(text_by_chapter, registry)
    results = extract(chunks, registry, model, workers=8)
    receipt = commit(world, registry, results, time_of=lambda i: ...)
"""

from patternbuffer.build.categories import (
    CATEGORY_HEAD,
    CATEGORY_TYPES,
    DEFAULT,
    category_passes,
)
from patternbuffer.build.commit import BuildReceipt, CommitRefused, coerce_type, commit
from patternbuffer.build.extract import (
    EXTRACT_HEAD,
    Attempt,
    ChunkResult,
    DroppedHandle,
    Escape,
    Pick,
    Refusal,
    extract,
    read_output,
)
from patternbuffer.build.labels import current_label, label
from patternbuffer.build.manifest import (
    CODES,
    TYPES,
    Entry,
    Manifest,
    ManifestError,
    Persona,
)
from patternbuffer.build.plan import Candidate, Chunk, plan
from patternbuffer.build.registry import (
    HINTS,
    Ambiguous,
    Registry,
    Resolved,
    Unknown,
    shape_rows,
)

__all__ = [
    "Ambiguous", "Attempt", "BuildReceipt", "CATEGORY_HEAD", "CATEGORY_TYPES", "CODES", "Candidate",
    "Chunk", "ChunkResult", "CommitRefused", "DEFAULT", "DroppedHandle", "EXTRACT_HEAD", "Entry", "Escape",
    "HINTS", "Manifest", "ManifestError", "Persona", "Pick", "Refusal", "Registry",
    "Resolved", "TYPES", "Unknown", "category_passes", "coerce_type", "commit",
    "current_label", "extract", "label", "plan", "read_output", "shape_rows",
]
