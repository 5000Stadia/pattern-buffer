"""Materialize anchor.world from the canonical dump (letter 005).

The shippable artifact is the diffable JSONL dump + STAMP; the SQLite
file is disposable and is rebuilt here on demand. Never committed.

Usage: .venv/bin/python examples/anchor/build_anchor.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "src"))

from patternbuffer.dump import build


def main() -> int:
    stamp = json.loads((HERE / "STAMP.json").read_text())
    target = HERE / "anchor.world"
    if target.exists():
        print(f"{target} already exists; delete it to rebuild")
        return 0
    buffer = build((HERE / "anchor_dump.jsonl").read_text(), target)
    n = buffer.head()
    if buffer.world_id != stamp["world_id"]:
        buffer.close()
        target.unlink()
        raise SystemExit(
            f"STAMP world_id {stamp['world_id']!r} != dump world {buffer.world_id!r}"
        )
    buffer.close()

    # The classification sidecar ships as a derived-cache artifact (it is
    # normally model-rebuilt; a zero-key build loads the cache instead),
    # then conflicts re-derive deterministically.
    from patternbuffer import World

    world = World(target, world_id=stamp["world_id"])
    for line in (HERE / "classifications.jsonl").read_text().splitlines():
        c = json.loads(line)
        world.classifier.set(c["assertion_id"], c["durability"], c["confidence"])
    conflicts = world.truth.scan()
    world.close()
    print(f"built {target}: {n} assertions, {len(conflicts)} open conflict flags "
          f"(world {stamp['world_id']}, seed {stamp['seed_version']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
