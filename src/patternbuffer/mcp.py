"""The MCP wrapper (MCP-WRAPPER-V1): the frozen porcelain served over MCP.

Any MCP client drives a world with zero Python — the engine-independence claim
(whitepaper §17.2) demonstrated beyond the Python host. Pure adapter: an
explicit registry of the porcelain's deterministic verbs, a dispatch layer, and
one mechanical wire envelope over `world.porcelain.*` — no engine surface, no
reflection, no model callable (the server's World has none, and the exposed
parameter domains are the genuinely model-free subset).

The engine core never imports this module; the `mcp` SDK is imported lazily and
ships in the `patternbuffer[mcp]` extra. Trust boundary: a connected client is a
FULLY TRUSTED world principal (it can name any frame; annotations are hints,
never authorization) — untrusted consumers go through a host-mediated surface.
"""

from __future__ import annotations

import argparse
import dataclasses
import inspect
import json
import logging
import os
import threading
import types as _pytypes
import typing
from typing import Any

from patternbuffer import World
from patternbuffer.codec import encode_out

logger = logging.getLogger(__name__)

# ------------------------------------------------------------- the registry
# Explicit and exhaustive (Cx 521 #2): the 37 deterministic tools. A porcelain
# addition CANNOT appear here by reflection — it must be classified V1/V1.1 and
# added deliberately (the registry-completeness test enforces this).

V1_READS = (
    "snapshot", "state", "state_union", "where", "aggregate", "confidence",
    "locate", "contents", "composition", "features", "path", "route",
    "neighborhood", "salience", "frame_diff", "who_knows", "events",
    "entities", "facts", "fidelity_audit", "axis_heads", "proposals",
    "correlations", "correlation_conflicts", "typing_conflicts",
)
V1_MUTATIONS = (
    "ingest_structured", "retract", "reconcile", "adjudicate_deferred",
    "confirm", "merge", "reject", "correlate", "retype",
    "begin_build", "seal_build", "abort_build",
)
V1_TOOLS = V1_READS + V1_MUTATIONS

# V1.1 (MCP sampling), deliberately absent: extract, ingest, ask, resolve.

# Conservatively destructive (Cx 521 #4): retracts, collapses identity, or
# supersedes the effective view. The complement of this set within mutations —
# including begin_build/abort_build — is explicitly destructiveHint=False.
DESTRUCTIVE = frozenset({
    "retract", "merge", "confirm", "retype", "adjudicate_deferred",
    "reconcile", "seal_build",
})
# Retry-safe mutations only (reads are all idempotent).
IDEMPOTENT_MUTATIONS = frozenset({"abort_build", "reject", "correlate"})

# Declared schema overrides (Cx 521 #2): exactly the parameters whose frozen
# signatures don't carry a sufficient annotation, plus the model-free domain
# narrowings (Cx 521 #1).
_STR_OR_LIST = {"anyOf": [{"type": "string"},
                          {"type": "array", "items": {"type": "string"}}]}
SCHEMA_OVERRIDES: dict[tuple[str, str], dict] = {
    ("snapshot", "scope"): _STR_OR_LIST,
    ("frame_diff", "scope"): _STR_OR_LIST,
    ("where", "value"): {"anyOf": [
        {"type": "number"},
        {"type": "object",
         "properties": {"$decimal": {"type": "string"}},
         "required": ["$decimal"], "additionalProperties": False},
    ]},
    # The genuinely model-free subset: inline/batch REACH the model path even
    # on a no-model World (the _no_model sentinel fires; the classifier falls
    # back) — so the tool exposes only rules|defer, defaulting to rules.
    ("ingest_structured", "classify"): {"type": "string",
                                        "enum": ["rules", "defer"],
                                        "default": "rules"},
}
# Parameters omitted from the tool surface entirely (the server always uses
# the safe value): seal_build(model=) would reach the batch model path.
OMITTED_PARAMS: frozenset[tuple[str, str]] = frozenset({("seal_build", "model")})

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"result": {}},   # the envelope: {"result": <JSON value>}
    "required": ["result"],
}


def _annotation_to_schema(ann: Any) -> dict:
    """A frozen-signature annotation → JSON schema (explicit map, no guessing)."""
    if ann is inspect.Parameter.empty or ann is Any:
        return {}
    origin = typing.get_origin(ann)
    if origin in (typing.Union, _pytypes.UnionType):
        args = typing.get_args(ann)
        parts = [_annotation_to_schema(a) for a in args]
        if type(None) in args and len(args) == 2:
            other = next(a for a in args if a is not type(None))
            inner = _annotation_to_schema(other)
            if list(inner.keys()) == ["type"]:
                return {"type": [inner["type"], "null"]}
        return {"anyOf": parts}
    if origin is list:
        (item,) = typing.get_args(ann) or (Any,)
        return {"type": "array", "items": _annotation_to_schema(item)}
    return {
        str: {"type": "string"}, bool: {"type": "boolean"},
        int: {"type": "integer"}, float: {"type": "number"},
        dict: {"type": "object"}, type(None): {"type": "null"},
    }.get(ann, {})


def _input_schema(name: str) -> dict:
    from patternbuffer.porcelain import Porcelain
    method = getattr(Porcelain, name)
    sig = inspect.signature(method)
    # Porcelain uses postponed annotations (`from __future__ import
    # annotations`), so signature annotations are STRINGS — resolve them to
    # runtime types first (Cx 533 #1: comparing strings against types silently
    # emitted `{}` for 83 params, letting typed garbage cross SDK validation).
    hints = typing.get_type_hints(method)
    props: dict[str, dict] = {}
    required: list[str] = []
    for p in list(sig.parameters.values())[1:]:          # skip self
        if (name, p.name) in OMITTED_PARAMS:
            continue
        schema = SCHEMA_OVERRIDES.get((name, p.name))
        if schema is None:
            ann = hints.get(p.name, inspect.Parameter.empty)
            schema = _annotation_to_schema(ann)
            if not schema and ann not in (inspect.Parameter.empty, Any):
                # an annotated param MUST map to a real schema — a silent {}
                # is exactly the 533 failure mode; fail at registry build.
                raise TypeError(f"{name}.{p.name}: unmapped annotation {ann!r}")
            if p.default is not inspect.Parameter.empty and p.default is not None:
                schema = {**schema, "default": p.default}
        props[p.name] = schema
        if p.default is inspect.Parameter.empty:
            required.append(p.name)
    out = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        out["required"] = required
    return out


def _annotations(name: str) -> dict:
    """The exact ToolAnnotations table (Cx 521 #4) — explicit complement."""
    read = name in V1_READS
    out = {
        "readOnlyHint": read,
        "idempotentHint": read or name in IDEMPOTENT_MUTATIONS,
        "openWorldHint": False,          # a bound local world is a closed domain
    }
    if not read:
        out["destructiveHint"] = name in DESTRUCTIVE
    return out


def build_registry() -> dict[str, dict]:
    """name -> {description, inputSchema, outputSchema, annotations}."""
    from patternbuffer.porcelain import Porcelain
    reg: dict[str, dict] = {}
    for name in V1_TOOLS:
        doc = (inspect.getdoc(getattr(Porcelain, name)) or name).strip()
        reg[name] = {
            "description": doc.split("\n\n")[0],
            "inputSchema": _input_schema(name),
            "outputSchema": _OUTPUT_SCHEMA,
            "annotations": _annotations(name),
        }
    return reg


# ------------------------------------------------------------- dispatch

def _normalize(ret: Any) -> Any:
    """Porcelain return → plain JSON value (Receipt/any dataclass → dict)."""
    if hasattr(ret, "to_dict"):
        return ret.to_dict()
    if dataclasses.is_dataclass(ret) and not isinstance(ret, type):
        return dataclasses.asdict(ret)
    return ret


def dispatch(world: World, name: str, arguments: dict[str, Any],
             lock: threading.Lock | None = None) -> dict:
    """Validate, call the porcelain verb, wrap in the wire envelope.

    Runtime validation (Cx 521 #1) rejects the model-reaching modes BEFORE
    dispatch — enforcement, not description. Mutations serialize under `lock`
    (build-session state is server/world state, not per-request state)."""
    if name not in V1_TOOLS:
        raise ValueError(f"unknown tool {name!r}")
    verb = getattr(world.porcelain, name)
    allowed = set(inspect.signature(verb).parameters)
    args = dict(arguments or {})
    unknown = set(args) - allowed
    if unknown:
        raise ValueError(f"{name}: unknown argument(s) {sorted(unknown)}")
    if name == "ingest_structured":
        classify = args.setdefault("classify", "rules")
        if classify not in ("rules", "defer"):
            raise ValueError(
                "ingest_structured over MCP accepts classify='rules'|'defer' "
                "only — 'inline'/'batch' reach the model path, which this "
                "no-model server does not carry (MCP-WRAPPER-V1)")
    if name == "seal_build":
        if "model" in args:
            raise ValueError(
                "seal_build over MCP does not accept 'model' — the batch "
                "model path is not carried by this no-model server; the seal "
                "always runs rules-only (MCP-WRAPPER-V1)")
        args["model"] = False
    if name in V1_MUTATIONS and lock is not None:
        with lock:
            ret = verb(**args)
    else:
        ret = verb(**args)
    return {"result": encode_out(_normalize(ret))}


# ------------------------------------------------------------- the server

def build_server(world: World):
    """Bind the registry + dispatch to an MCP low-level Server (lazy SDK)."""
    from mcp.server.lowlevel import Server   # the [mcp] extra
    from mcp import types

    registry = build_registry()
    lock = threading.Lock()
    server = Server("patternbuffer")

    @server.list_tools()
    async def _list_tools() -> list:
        return [
            types.Tool(
                name=name,
                description=spec["description"],
                inputSchema=spec["inputSchema"],
                outputSchema=spec["outputSchema"],
                annotations=types.ToolAnnotations(**spec["annotations"]),
            )
            for name, spec in registry.items()
        ]

    @server.call_tool()   # SDK validates input, wraps dict as structuredContent
    async def _call_tool(name: str, arguments: dict) -> dict:
        # Returning the envelope dict: the SDK places it in structuredContent
        # AND serializes the same object into one TextContent block — the
        # spec's wire convention, natively.
        return dispatch(world, name, arguments, lock=lock)

    return server


def main(argv: list[str] | None = None) -> int:
    """`patternbuffer-mcp --world PATH --world-id ID` (env fallbacks)."""
    parser = argparse.ArgumentParser(
        prog="patternbuffer-mcp",
        description="Serve one pattern-buffer world over MCP (stdio). "
                    "One server, one world (the 1:1 invariant).")
    parser.add_argument("--world", default=os.environ.get("PATTERNBUFFER_WORLD"),
                        help="path to the .world file (env PATTERNBUFFER_WORLD)")
    parser.add_argument("--world-id",
                        default=os.environ.get("PATTERNBUFFER_WORLD_ID"),
                        help="the world's id (env PATTERNBUFFER_WORLD_ID); "
                             "required — a mismatch against an existing file "
                             "fails loudly (WorldMismatch)")
    args = parser.parse_args(argv)
    if not args.world or not args.world_id:
        parser.error("--world and --world-id are both required "
                     "(or PATTERNBUFFER_WORLD / PATTERNBUFFER_WORLD_ID)")
    try:
        from mcp.server.stdio import stdio_server
    except ImportError:
        parser.error("the MCP SDK is not installed — pip install 'patternbuffer[mcp]'")

    world = World(args.world, world_id=args.world_id)   # no model callable
    server = build_server(world)

    import anyio

    async def _run() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    try:
        anyio.run(_run)
    finally:
        world.close()   # aborts any open build session; buffer closed
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
