"""VIEW-JS-V1: the JS view module's drift guard and its end-to-end test.

`node --test` replays the committed vectors against the JS port of
`mirror.apply` (tests 1-4, 3a, 6 of the spec); this file runs it, so the Python
suite fails when the JS drifts from the vectors. Test 5 drives a real Runner
from node over `httpTransport` and compares the JS document with
`mirror.export` of the same world.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from patternbuffer import World, mirror
from patternbuffer.service import Runner, make_runner_callable
from people_fixture import ATTRS, KEY, VF, WORLD_ID, build_people

ROOT = Path(__file__).resolve().parent.parent
JS_TESTS = sorted((ROOT / "js" / "test").glob("*.test.mjs"))
E2E_CLIENT = ROOT / "tests" / "js_e2e_client.mjs"
TIMEOUT = 120


def _node() -> str | None:
    """The node binary when it is at least version 18, else None."""
    path = shutil.which("node")
    if path is None:
        return None
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True,
                             timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    found = re.match(r"v(\d+)\.", out.strip())
    return path if found and int(found.group(1)) >= 18 else None


NODE = _node()
needs_node = pytest.mark.skipif(NODE is None, reason="node >= 18 is not on PATH")


@needs_node
def test_7_the_js_tests_pass_against_the_committed_vectors():
    assert JS_TESTS, "js/test has no *.test.mjs files"
    # the files are named, not the directory: node >= 21 reads a directory
    # argument as a file to run, node 18 as a tree to walk
    done = subprocess.run([NODE, "--test", *map(str, JS_TESTS)], cwd=ROOT,
                          capture_output=True, text=True, timeout=TIMEOUT)
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-2000:]
    assert re.search(r"^# fail 0$", done.stdout, re.M)


def _export(path: Path) -> dict:
    w = mirror.open_read_only_copy(path, WORLD_ID)
    try:
        return mirror.export(w, VF, key=KEY, people=ATTRS)
    finally:
        w.close()


@needs_node
def test_5_a_js_view_syncs_a_runner_queues_an_author_record_and_sees_it(tmp_path):
    build_people(tmp_path, "run.world").close()
    world_file = tmp_path / "run.world"
    before = _export(world_file)
    model, route = make_runner_callable(None)
    runner = Runner(lambda gated: World(world_file, WORLD_ID, model=gated(model)), VF,
                    port=0, model_route=route, authors=("photonic",),
                    mirror_key=KEY, people=ATTRS).start()
    try:
        done = subprocess.run(
            [NODE, str(E2E_CLIENT), f"http://127.0.0.1:{runner.port}", WORLD_ID, VF,
             "viewer", "photonic"],
            capture_output=True, text=True, timeout=TIMEOUT, cwd=ROOT)
        assert done.returncode == 0, done.stderr[-4000:]
        got = json.loads(done.stdout)
    finally:
        runner.stop()
    after = _export(world_file)

    # the JS view equals the Python export, as JSON values
    assert got["first"] == before
    assert got["first"]["people"] and got["first"]["present"] is not None
    # the queued author record flushed: one call, recorded, nothing left waiting
    assert (got["waiting"], got["sent"], got["left"]) == (1, 1, 0)
    # the next sync shows the move in the people layer, and equals the new export
    assert before["people"]["person:cook"]["place"] == "place:kitchen"
    assert got["second"]["people"]["person:cook"]["place"] == "place:bedroom"
    assert got["second"] == after
    assert got["second"]["cursor"] != got["first"]["cursor"]
    # and a further sync with nothing new changes nothing
    assert got["third"] == got["second"]


def _post(port: int, body: dict) -> dict:
    import urllib.request
    req = urllib.request.Request(f"http://127.0.0.1:{port}/call",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _deliver(world_file: Path, body: dict, times: int) -> None:
    model, route = make_runner_callable(None)
    runner = Runner(lambda gated: World(world_file, WORLD_ID, model=gated(model)), VF,
                    port=0, model_route=route, authors=("photonic",),
                    mirror_key=KEY, people=ATTRS).start()
    try:
        for _ in range(times):
            assert _post(runner.port, body) == {"result": {"status": "recorded"}}
    finally:
        runner.stop()


@pytest.mark.parametrize("item", [
    {"entity": "person:cook", "attribute": "in", "value": "place:bedroom",
     "value_type": "entity"},
    {"entity": "person:cook", "attribute": "in", "value": "place:bedroom",
     "value_type": "entity", "valid_to": 9.0},
], ids=["open", "interval"])
def test_r2_1_a_retried_queued_call_is_equivalent_to_one_delivery(tmp_path, item):
    """VIEW-JS-V1 §3 r2.1 (pbr): the queue persists the call's own `at`, so a
    retry after a lost answer sends the same body. Delivered twice it reads
    exactly as delivered once (an at-least-once duplicate folds away)."""
    body = {"session": "photonic", "verb": "record",
            "args": {"items": [item], "at": 5.0, "frame": "canon"}}
    once, twice = tmp_path / "once.world", tmp_path / "twice.world"
    build_people(tmp_path, "once.world").close()
    build_people(tmp_path, "twice.world").close()
    _deliver(once, body, 1)
    _deliver(twice, body, 2)
    a, b = _export(once), _export(twice)
    a.pop("cursor"), b.pop("cursor")                 # the log heads differ by design
    assert a == b
    assert a["people"]["person:cook"]["place"] == "place:bedroom"
    for t in (6.0, 10.0):                            # inside and after the interval
        sa = mirror.open_read_only_copy(once, WORLD_ID)
        sb = mirror.open_read_only_copy(twice, WORLD_ID)
        try:
            ra = sa.porcelain.state("person:cook", "in", as_of=t)
            rb = sb.porcelain.state("person:cook", "in", as_of=t)
            assert (ra["status"], ra.get("fact", {}).get("value")) == \
                   (rb["status"], rb.get("fact", {}).get("value"))
        finally:
            sa.close(), sb.close()
