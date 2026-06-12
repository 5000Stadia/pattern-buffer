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
    print(f"built {target}: {n} assertions (world {stamp['world_id']}, "
          f"seed {stamp['seed_version']}, run {stamp['run_id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
