"""The establishing_set lens orders its scope deterministically: its roots come
in the order the scope names them, as every other lens's scope walk does, never
in set iteration order, which follows the per-process string hash seed."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[1] / "src")

ROOMS = [f"room:r{i}" for i in range(12)]

SCRIPT = textwrap.dedent("""
    import json, sys
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback

    rooms = json.loads(sys.argv[2])
    w = World(sys.argv[1], world_id="w:order",
              model=StubModel(fallback=rule_classifier_fallback()))
    try:
        w.ingest_structured([{"entity": r, "attribute": "kind", "value": "room",
                              "timeless": True} for r in rooms])
        m = w.materialize(list(reversed(rooms)), lens="establishing_set")
        print(json.dumps(list(m.scope)))
    finally:
        w.close()
""")


def _scope_order(tmp_path: Path, seed: int) -> list[str]:
    env = dict(os.environ, PYTHONHASHSEED=str(seed), PYTHONPATH=SRC)
    done = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(tmp_path / f"w{seed}.world"), json.dumps(ROOMS)],
        env=env, capture_output=True, text=True, check=True,
    )
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_establishing_scope_roots_follow_the_scope_order(tmp_path):
    """Twelve root rooms, named in reverse: the lens's scope lists them in that
    order under three different hash seeds (before the fix, the roots came
    from a set, so the order changed from one process to the next)."""
    orders = [_scope_order(tmp_path, seed) for seed in (1, 2, 3)]
    assert orders[0] == orders[1] == orders[2] == list(reversed(ROOMS))
