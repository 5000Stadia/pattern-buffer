"""the_grey_house — the deterministic tracking-eval seed (TRACKING-MODE-V1).

The single source of truth for the eval scenario: the battery tests import
THESE rows (via importlib), and the module is runnable standalone to build a
replayable world file:

    .venv/bin/python evals/the_grey_house/seed.py /tmp/grey.world

Ground truth lives in README.md's ledger; the battery is
tests/test_tracking_mode.py (receipts = the suite).
"""

from __future__ import annotations

import sys

DAY = 86400.0

# Decay physics: declared data, not config (DecayPolicy reads these fresh).
DECAY_ROWS = [
    {"entity": "attr:in", "attribute": "decay_halflife_seconds",
     "value": 2 * DAY, "timeless": True},          # vehicle/object location: fast
    {"entity": "attr:position", "attribute": "decay_halflife_seconds",
     "value": 60 * DAY, "timeless": True},         # furniture: slow
    {"entity": "attr:__world__", "attribute": "decay_halflife_seconds",
     "value": 14 * DAY, "timeless": True},         # everything else
]

# The household + vehicle, first observations at wall t=0.
SEED_ROWS = DECAY_ROWS + [
    {"entity": "place:house", "attribute": "kind", "value": "place", "timeless": True},
    {"entity": "place:driveway", "attribute": "kind", "value": "place", "timeless": True},
    {"entity": "place:garage", "attribute": "kind", "value": "place", "timeless": True},
    {"entity": "obj:car", "attribute": "kind", "value": "vehicle", "timeless": True},
    {"entity": "obj:couch", "attribute": "kind", "value": "furniture", "timeless": True},
    {"entity": "obj:badge", "attribute": "kind", "value": "object", "timeless": True},
    {"entity": "obj:couch", "attribute": "position", "value": "north wall",
     "valid_from": 1.0, "status": "observed"},
    {"entity": "obj:car", "attribute": "in", "value": "place:driveway",
     "value_type": "entity", "valid_from": 1.0, "status": "observed"},
]


class FakeClock:
    """The eval's injected wall clock — advanced as an explicit harness op."""

    def __init__(self, t: float = 0.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def seed(world) -> None:
    """Ingest the seed into an already-constructed World (rules-mode)."""
    world.ingest_structured(list(SEED_ROWS), classify="rules")


def build(path, clock: FakeClock | None = None):
    """Construct the tracking world at `path`, seeded. Returns (world, clock)."""
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    from patternbuffer.thunks import OBSERVE_OR_UNKNOWN

    clock = clock or FakeClock(0.0)
    world = World(path, world_id="w:grey",
                  model=StubModel(fallback=rule_classifier_fallback()),
                  policy=OBSERVE_OR_UNKNOWN, clock=clock)
    seed(world)
    return world, clock


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: seed.py <path/to/out.world>")
    w, _ = build(sys.argv[1])
    n = w.buffer.head()
    w.close()
    print(f"the_grey_house built: {sys.argv[1]} ({n} assertions)")
