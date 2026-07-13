"""MCP-WRAPPER-V1: the porcelain over MCP — registry, dispatch, wire, membrane.

The wrapper is a pure adapter over the frozen porcelain: an explicit 37-tool
registry (never reflective), the genuinely model-free parameter subset (spy-
proven), one mechanical wire envelope, the exact annotations table, and the
core/extra import membrane. The stdio smoke test runs against the real SDK.
"""

import inspect
import json
import subprocess
import sys

import pytest

from patternbuffer import World
from patternbuffer.mcp import (
    DESTRUCTIVE,
    IDEMPOTENT_MUTATIONS,
    OMITTED_PARAMS,
    SCHEMA_OVERRIDES,
    V1_MUTATIONS,
    V1_READS,
    V1_TOOLS,
    build_registry,
    dispatch,
)
from patternbuffer.porcelain import Porcelain
from patternbuffer.testing import StubModel, rule_classifier_fallback


class ModelSpy:
    """A raising spy: ANY model-path call is a test failure."""

    def __init__(self):
        self.calls = 0

    def __call__(self, prompt, schema):
        self.calls += 1
        raise AssertionError("model path reached by a V1 MCP tool")


@pytest.fixture
def spy_world(tmp_path):
    spy = ModelSpy()
    w = World(tmp_path / "mcp.world", world_id="w:mcp", model=spy)
    yield w, spy
    w.close()


def _seed(world):
    dispatch(world, "ingest_structured", {"items": [
        {"entity": "place:room", "attribute": "kind", "value": "place",
         "timeless": True},
        {"entity": "obj:coin", "attribute": "kind", "value": "object",
         "timeless": True},
        {"entity": "obj:coin", "attribute": "in", "value": "place:room",
         "value_type": "entity", "valid_from": 1.0},
        {"entity": "person:ana", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:ana", "attribute": "name", "value": "ana",
         "timeless": True},
    ]})


# ------------------------------------------------------------- registry

def test_registry_is_exactly_the_declared_37():
    reg = build_registry()
    assert len(reg) == 37 and set(reg) == set(V1_TOOLS)
    assert "state_union" in reg                       # the Cx-caught omission
    for absent in ("extract", "ingest", "ask", "resolve"):   # V1.1, not V1
        assert absent not in reg


def test_registry_completeness_vs_porcelain_surface():
    # every public porcelain verb is either a V1 tool or explicitly classified
    # V1.1 (model-backed) — a NEW verb fails here until classified.
    V1_1 = {"extract", "ingest", "ask", "resolve"}      # model-backed (sampling)
    PYTHON_SUGAR = {"build"}    # context manager over begin/seal/abort — the
                                # verbs are the portable surface (BUILD-SESSION-V1)
    public = {n for n, m in inspect.getmembers(Porcelain, inspect.isfunction)
              if not n.startswith("_")}
    unclassified = public - set(V1_TOOLS) - V1_1 - PYTHON_SUGAR
    assert not unclassified, f"unclassified porcelain verbs: {unclassified}"


def test_schema_overrides_cover_exactly_the_unannotated_params():
    # the three unannotated params carry declared overrides; nothing else is
    # unannotated (who_knows.value is Any -> permissive by annotation)
    unannotated = set()
    for name in V1_TOOLS:
        sig = inspect.signature(getattr(Porcelain, name))
        for p in list(sig.parameters.values())[1:]:
            if p.annotation is inspect.Parameter.empty:
                unannotated.add((name, p.name))
    assert unannotated == {("snapshot", "scope"), ("frame_diff", "scope"),
                           ("where", "value")}
    assert unannotated <= set(SCHEMA_OVERRIDES)


def test_no_annotated_param_degrades_to_permissive_schema():
    # Cx 533 #1 regression lock: postponed annotations must be RESOLVED, never
    # string-compared into a silent {}. The only permissive schema on the whole
    # surface is who_knows.value, annotated Any on the frozen signature.
    reg = build_registry()
    empty = [(t, p) for t, spec in reg.items()
             for p, s in spec["inputSchema"]["properties"].items() if s == {}]
    assert empty == [("who_knows", "value")]
    # spot-check resolved types (the exact params Cx proved permeable)
    assert reg["state"]["inputSchema"]["properties"]["entity"] == {"type": "string"}
    assert reg["ingest_structured"]["inputSchema"]["properties"]["items"] == {
        "type": "array", "items": {"type": "object"}}
    assert reg["facts"]["inputSchema"]["properties"]["frame"] == {"type": "string"}
    assert reg["begin_build"]["inputSchema"]["properties"]["at"] == {
        "type": ["number", "null"]}


def test_schemas_shape():
    reg = build_registry()
    snap = reg["snapshot"]["inputSchema"]
    assert "anyOf" in snap["properties"]["scope"]         # str | list[str]
    ing = reg["ingest_structured"]["inputSchema"]
    assert ing["properties"]["classify"]["enum"] == ["rules", "defer"]
    assert "model" not in reg["seal_build"]["inputSchema"]["properties"]
    assert ("seal_build", "model") in OMITTED_PARAMS
    for spec in reg.values():
        assert spec["outputSchema"]["required"] == ["result"]


def test_annotations_table():
    reg = build_registry()
    for name in V1_READS:
        a = reg[name]["annotations"]
        assert a["readOnlyHint"] and a["idempotentHint"]
        assert a["openWorldHint"] is False and "destructiveHint" not in a
    for name in V1_MUTATIONS:
        a = reg[name]["annotations"]
        assert a["readOnlyHint"] is False
        assert a["destructiveHint"] is (name in DESTRUCTIVE)
        assert a["idempotentHint"] is (name in IDEMPOTENT_MUTATIONS)
    # the explicit complement: begin/abort_build are NOT destructive
    assert reg["begin_build"]["annotations"]["destructiveHint"] is False
    assert reg["abort_build"]["annotations"]["destructiveHint"] is False


# --------------------------------------------------- zero-model + validation

def test_every_v1_tool_makes_zero_model_calls(spy_world, tmp_path):
    world, spy = spy_world
    _seed(world)
    smoke_args = {
        "snapshot": {"scope": ["place:room"]},
        "state": {"entity": "obj:coin", "attribute": "in"},
        "state_union": {"entity": "obj:coin", "attribute": "in"},
        "where": {"attribute": "in", "op": "==", "value": 1},
        "aggregate": {"container": "place:room", "member_attribute": "kind",
                      "op": "count"},
        "confidence": {"entity": "obj:coin", "attribute": "in"},
        "locate": {"entity": "obj:coin"},
        "contents": {"container": "place:room"},
        "composition": {"entity": "place:room"},
        "features": {"place": "place:room"},
        "path": {"a": "place:room", "b": "place:room"},
        "route": {"a": "place:room", "b": "place:room"},
        "neighborhood": {"entity": "obj:coin"},
        "salience": {"entity": "obj:coin"},
        "frame_diff": {"a": "canon", "b": "knows:person:ana",
                       "scope": "place:room"},
        "who_knows": {"entity": "obj:coin", "attribute": "in"},
        "events": {},
        "entities": {"frame": "canon"},
        "facts": {"frame": "canon"},
        "fidelity_audit": {},
        "axis_heads": {},
        "proposals": {},
        "correlations": {"entity": "person:ana"},
        "correlation_conflicts": {},
        "typing_conflicts": {},
        "ingest_structured": {"items": [
            {"entity": "obj:coin", "attribute": "state", "value": "dusty",
             "valid_from": 2.0}]},
        "retract": {"assertion_id": "a:1", "reason": "test"},
        "reconcile": {},
        "adjudicate_deferred": {},
        "confirm": {"a": "person:ana", "b": "obj:coin"},
        "merge": {"a": "person:x1", "b": "person:x2", "evidence": "t"},
        "reject": {"a": "person:y1", "b": "person:y2"},
        "correlate": {"a": "person:z1", "b": "person:z2", "evidence": "t"},
        "retype": {"entity": "obj:coin", "to_kind": "relic", "evidence": "t"},
        "begin_build": {},
        "seal_build": {},
        "abort_build": {},
    }
    assert set(smoke_args) == set(V1_TOOLS)
    for name in V1_TOOLS:
        out = dispatch(world, name, smoke_args[name])
        assert set(out) == {"result"}, name
    assert spy.calls == 0                       # the whole surface, no model


def test_rejected_modes_fail_before_dispatch(spy_world):
    world, spy = spy_world
    with pytest.raises(ValueError, match="rules"):
        dispatch(world, "ingest_structured",
                 {"items": [], "classify": "inline"})
    with pytest.raises(ValueError, match="rules"):
        dispatch(world, "ingest_structured",
                 {"items": [], "classify": "batch"})
    dispatch(world, "begin_build", {})
    with pytest.raises(ValueError, match="model"):
        dispatch(world, "seal_build", {"model": True})
    dispatch(world, "abort_build", {})
    with pytest.raises(ValueError, match="unknown tool"):
        dispatch(world, "ask", {"question": "?"})       # V1.1, not V1
    with pytest.raises(ValueError, match="unknown argument"):
        dispatch(world, "locate", {"entity": "obj:x", "bogus": 1})
    assert spy.calls == 0


# ------------------------------------------------------------- wire envelope

def _fresh(tmp_path, name):
    stub = StubModel(fallback=rule_classifier_fallback())
    return World(tmp_path / f"{name}.world", world_id="w:wire", model=stub)


def test_wire_shapes_deep_equal_direct_calls(tmp_path):
    # the oracle (Cx 533 #2): DEEP equality against the direct porcelain call
    # after the declared envelope/normalization — for ALL FIVE return shapes.
    # Receipt is sequence-dependent, so it is compared across two fresh worlds
    # given the identical operation (same seq -> identical to_dict()).
    ITEMS = [{"entity": "place:hall", "attribute": "kind", "value": "place",
              "timeless": True},
             {"entity": "place:hall", "attribute": "name", "value": "the hall",
              "timeless": True}]
    wa = _fresh(tmp_path, "a")
    wb = _fresh(tmp_path, "b")
    try:
        # Receipt (dataclass) — full deep equality via the two-world oracle
        via_mcp = dispatch(wa, "ingest_structured", {"items": ITEMS})
        direct = wb.porcelain.ingest_structured(ITEMS, classify="rules")
        assert via_mcp["result"] == direct.to_dict()
        # dict
        assert dispatch(wa, "snapshot", {"scope": "place:hall"})["result"] \
            == wa.porcelain.snapshot("place:hall")
        # list
        assert dispatch(wa, "entities", {"frame": "canon"})["result"] \
            == wa.porcelain.entities("canon")
        # primitive (float)
        assert dispatch(wa, "salience", {"entity": "place:hall"})["result"] \
            == wa.porcelain.salience("place:hall")
        # None — path() between unconnected entities returns None, exactly
        direct_none = wa.porcelain.path("place:hall", "place:hall")
        env = dispatch(wa, "path", {"a": "place:hall", "b": "place:hall"})
        assert env["result"] == direct_none
        no_route = dispatch(wa, "path", {"a": "place:hall",
                                         "b": "place:hall"})
        json.dumps(no_route)
        # a genuinely-None case: two isolated places
        dispatch(wa, "ingest_structured", {"items": [
            {"entity": "place:isle", "attribute": "kind", "value": "place",
             "timeless": True}]})
        env2 = dispatch(wa, "path", {"a": "place:hall", "b": "place:isle"})
        assert env2["result"] is None
        assert env2["result"] == wa.porcelain.path("place:hall", "place:isle")
        for e in (via_mcp, env, env2):
            json.dumps(e)
    finally:
        wa.close()
        wb.close()


# ------------------------------------------------------------- lifecycle

def test_startup_mismatched_world_id_fails_loudly(tmp_path):
    pytest.importorskip("mcp")  # without the SDK, main() exits at the extra guard
    from patternbuffer.buffer import WorldMismatch
    from patternbuffer.mcp import main
    p = tmp_path / "owned.world"
    w = World(p, world_id="w:original")
    w.close()
    with pytest.raises(WorldMismatch):
        main(["--world", str(p), "--world-id", "w:imposter"])


def test_close_after_shutdown_is_final(tmp_path):
    import sqlite3
    w = _fresh(tmp_path, "shut")
    w.close()
    w.close()                                     # idempotent-safe double close
    with pytest.raises(sqlite3.ProgrammingError):
        w.buffer.visible()                        # closed means closed


def test_abort_open_build_on_shutdown_leaves_rows_unclassified(tmp_path):
    # Cx 533 #2: the meaningful assertion is post-REOPEN state — the aborted
    # session classified nothing, and the toggle did not leak into the file.
    p = tmp_path / "buildshut.world"
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(p, world_id="w:bs", model=stub)
    dispatch(w, "begin_build", {})
    dispatch(w, "ingest_structured", {"items": [
        {"entity": "obj:ghost", "attribute": "kind", "value": "object",
         "timeless": True},
        {"entity": "obj:ghost", "attribute": "state", "value": "half",
         "valid_from": 1.0}],
        "classify": "defer"})
    row_ids = [r.id for r in w.buffer.visible() if r.entity == "obj:ghost"]
    assert row_ids
    w.close()                                     # server shutdown: abort, close
    assert w.porcelain._build_head is None        # session did not survive
    w2 = World(p, world_id="w:bs", model=stub)    # reopen
    try:
        assert w2.ingestor.classify_inline is True     # toggle back to default
        for rid in row_ids:
            assert w2.classifier.get(rid) is None      # NOTHING was classified
    finally:
        w2.close()


@pytest.mark.anyio
async def test_mutations_serialize_under_concurrent_tasks(tmp_path):
    # the SDK executes handlers on one event loop; interleaved async dispatches
    # must produce a consistent, complete, contiguous log.
    import anyio
    w = _fresh(tmp_path, "conc")
    try:
        async def burst(tag, n):
            for i in range(n):
                dispatch(w, "ingest_structured", {"items": [
                    {"entity": f"obj:{tag}_{i}", "attribute": "kind",
                     "value": "object", "timeless": True}]})
                await anyio.sleep(0)              # force interleaving
        async with anyio.create_task_group() as tg:
            tg.start_soon(burst, "left", 10)
            tg.start_soon(burst, "right", 10)
        rows = w.buffer.all_rows()
        seqs = [r.seq for r in rows]
        assert seqs == list(range(1, len(rows) + 1))   # contiguous, no loss
        ents = {r.entity for r in rows}
        assert all(f"obj:left_{i}" in ents and f"obj:right_{i}" in ents
                   for i in range(10))
    finally:
        w.close()


# ------------------------------------------------------------- membrane

def test_core_import_never_pulls_mcp():
    code = ("import sys; import patternbuffer; "
            "assert 'mcp' not in sys.modules, 'core imported mcp'; "
            "assert 'patternbuffer.mcp' not in sys.modules; print('clean')")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0 and "clean" in out.stdout, out.stderr


def test_entry_point_requires_both_args(tmp_path):
    from patternbuffer.mcp import main
    with pytest.raises(SystemExit):
        main([])                                    # missing world/world-id
    with pytest.raises(SystemExit):
        main(["--world", str(tmp_path / "w.world")])   # missing id


# ------------------------------------------------------------- stdio smoke

@pytest.mark.anyio
async def test_stdio_initialize_list_call_shutdown(tmp_path):
    mcp_types = pytest.importorskip("mcp.types")
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    world_path = tmp_path / "smoke.world"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "patternbuffer.mcp",
              "--world", str(world_path), "--world-id", "w:smoke"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) == 37
            by_name = {t.name: t for t in tools.tools}
            assert by_name["snapshot"].annotations.readOnlyHint is True
            assert by_name["retract"].annotations.destructiveHint is True
            # a write then a read, over the wire
            r = await session.call_tool("ingest_structured", {"items": [
                {"entity": "place:deck", "attribute": "kind", "value": "place",
                 "timeless": True}]})
            assert not r.isError
            assert r.structuredContent["result"]["world_id"] == "w:smoke"
            r2 = await session.call_tool("entities", {"frame": "canon"})
            # world:self is the charter genesis row — present in any fresh world
            assert r2.structuredContent["result"] == ["place:deck", "world:self"]
            # the text block serializes the SAME envelope object
            assert json.loads(r2.content[0].text) == r2.structuredContent
            # input validation is live (SDK-side, from our schema)
            r3 = await session.call_tool("ingest_structured",
                                         {"items": [], "classify": "inline"})
            assert r3.isError
            # ordinary TYPE violations are rejected by schema, never reaching
            # engine code (Cx 533 #1 regression lock)
            for bad_call in (
                ("state", {"entity": 7, "attribute": []}),
                ("ingest_structured", {"items": "not-an-array"}),
                ("facts", {"frame": 123, "include_meta": "yes"}),
                ("begin_build", {"at": "tomorrow"}),
            ):
                rbad = await session.call_tool(*bad_call)
                assert rbad.isError, bad_call
                text = rbad.content[0].text
                assert "validation error" in text.lower(), bad_call


@pytest.fixture
def anyio_backend():
    return "asyncio"
