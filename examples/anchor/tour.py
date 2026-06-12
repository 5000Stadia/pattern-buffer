"""The zero-API-key tour of anchor.world (letter 005 item 5).

Every query below is deterministic — no model, no key, milliseconds.
The world is the ingested noir mystery *The Last Honest Meter*; the
prose is long gone, and the store answers anyway.

Usage:
  .venv/bin/python examples/anchor/build_anchor.py   # once
  .venv/bin/python examples/anchor/tour.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "src"))

from patternbuffer import World


def find(world: World, *aliases: str) -> str | None:
    """Resolve an entity by any of its aliases (no model: registry only)."""
    for alias in aliases:
        hits = world.registry.by_alias(alias)
        if hits:
            return sorted(hits)[0]
    return None


def main() -> int:
    stamp = json.loads((HERE / "STAMP.json").read_text())
    path = HERE / "anchor.world"
    if not path.exists():
        raise SystemExit("run build_anchor.py first")
    w = World(path, world_id=stamp["world_id"])  # no model injected: reads only

    core = find(w, "the memory core", "memory core")
    sela = find(w, "sela voss", "sela")
    locker = find(w, "tovan's footlocker", "the footlocker", "footlocker")

    print("=" * 64)
    print("ANCHOR — the mystery as a database. No prose, no model, no key.")
    print("=" * 64)

    print("\n1. THE TWO-CLOCK QUESTION")
    print("   'Where was the memory core during the Chapter One assembly?'")
    print("   (Nothing in Chapter One says. Chapter Three confesses it.)")
    if core:
        for day, label in [(2.0, "day 2 (the quiet days)"),
                           (4.5, "day 4, evening (THE ASSEMBLY)"),
                           (16.0, "after the tribunal")]:
            fold = w.state(core, "in", valid_as_of=day)
            where = fold.winner.value if fold.winner else "(no canon row)"
            print(f"   as-of {label:<28} -> {where}")

    print("\n2. THE KNOWLEDGE QUESTION")
    print(f"   'What does Sela know?' — her frame is the only window she has.")
    if sela:
        frame = f"knows:{sela}"
        rows = w.buffer.visible(frame=frame)
        for r in rows[:6]:
            print(f"   {r.entity} · {r.attribute} = {str(r.value)[:46]}")
        print(f"   ({len(rows)} rows in her frame; canon she never learned is "
              f"structurally absent)")

    print("\n3. THE SEALED QUESTION")
    print("   'What is in the footlocker?' — crimp 0447 was never cut.")
    if locker:
        contents = w.contents(locker)
        fold = w.state(locker, "contents")
        state = "unresolved thunk" if (fold.winner and fold.winner.value_type == "unresolved") \
            else "no contents assertion exists"
        print(f"   contents query: {contents or '[] — and that emptiness is honest'}")
        print(f"   stored state: {state}; the system never invented an answer")

    print("\n4. THE CONTRADICTION THAT SURVIVED")
    print("   Ch.1 says two reactors; Ch.3 says three. Nobody 'fixed' it.")
    flagged = w.truth.open_conflicts()
    for c in flagged[:4]:
        values = [w.buffer.get(a).value for a in c.assertion_ids if w.buffer.get(a)]
        print(f"   OPEN FLAG {c.kind}: {c.entity} · {c.attribute} = {values}")
    if not flagged:
        print("   (no open flags in this build)")

    print("\nEvery answer above: a deterministic fold over an append-only log.")
    w.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
