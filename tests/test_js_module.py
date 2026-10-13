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
