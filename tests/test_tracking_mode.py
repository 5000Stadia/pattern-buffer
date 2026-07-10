"""TRACKING-MODE-V1: the reality battery — proving the second mode.

The 14-item battery from the spec, run as deterministic tests with an injected
fake wall clock. Shared items run in BOTH modes (the founder's ruling:
time-advance is shared; the difference is which axis drives decay); tracking
items exercise decay/staleness/quarantine/absence/no-invent; the fiction
control locks the anti-decay amendment; restart + purity oracles close it.
"""

import importlib.util
import json
import pathlib

import pytest

from patternbuffer import World
from patternbuffer.dump import dump
from patternbuffer.thunks import OBSERVE_OR_UNKNOWN, UNKNOWN
from patternbuffer.testing import StubModel, rule_classifier_fallback

# The eval seed is the single source of truth (Cx 604 #4): the battery imports
# the replayable artifact rather than duplicating the scenario.
_SEED_PATH = (pathlib.Path(__file__).parent.parent
              / "evals" / "the_grey_house" / "seed.py")
_spec = importlib.util.spec_from_file_location("grey_house_seed", _SEED_PATH)
grey_house = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(grey_house)

DAY = grey_house.DAY


class FakeClock(grey_house.FakeClock):
    def __init__(self, t=1000.0):
        super().__init__(t)


def _tracking(tmp_path, name="grey", clock=None):
    stub = StubModel(fallback=rule_classifier_fallback())
    return World(tmp_path / f"{name}.world", world_id="w:grey", model=stub,
                 policy=OBSERVE_OR_UNKNOWN, clock=clock or FakeClock())


def _fiction(tmp_path, name="fict"):
    stub = StubModel(fallback=rule_classifier_fallback())
    return World(tmp_path / f"{name}.world", world_id="w:grey", model=stub)


def _seed(w):
    """The shared grey-house seed — imported from the eval artifact."""
    grey_house.seed(w)


# ---------------------------------------------------- shared battery (1-4)

@pytest.mark.parametrize("mode", ["tracking", "fiction"])
def test_b1_as_of_reconstruction_both_modes(tmp_path, mode):
    w = _tracking(tmp_path) if mode == "tracking" else _fiction(tmp_path)
    try:
        w.ingest_structured([
            {"entity": "obj:badge", "attribute": "kind", "value": "object",
             "timeless": True},
            {"entity": "place:desk", "attribute": "kind", "value": "place", "timeless": True},
            {"entity": "place:office", "attribute": "kind", "value": "place", "timeless": True},
            {"entity": "obj:badge", "attribute": "in", "value": "place:desk",
             "value_type": "entity", "valid_from": 10.0, "status": "observed"},
            {"entity": "obj:badge", "attribute": "in", "value": "place:office",
             "value_type": "entity", "valid_from": 20.0, "status": "observed"},
        ], classify="rules")
        assert w.locate("obj:badge", valid_as_of=15.0)[0] == "place:desk"
        assert w.locate("obj:badge", valid_as_of=25.0)[0] == "place:office"
        assert w.locate("obj:badge", valid_as_of=5.0) == []
    finally:
        w.close()


@pytest.mark.parametrize("mode", ["tracking", "fiction"])
def test_b2_time_advance_changes_nothing(tmp_path, mode):
    clock = FakeClock()
    w = _tracking(tmp_path, clock=clock) if mode == "tracking" else _fiction(tmp_path)
    try:
        _seed(w)
        before = w.porcelain.snapshot(["obj:couch"], as_of=100.0)
        w.ingestor.cursor.advance(100.0)        # "it is the next day" (story)
        clock.t += DAY                          # wall day passes (harness op)
        after = w.porcelain.snapshot(["obj:couch"], as_of=100.0)
        assert before == after                  # standing truth unchanged
    finally:
        w.close()


@pytest.mark.parametrize("mode", ["tracking", "fiction"])
def test_b3_future_events_filtered_by_until(tmp_path, mode):
    w = _tracking(tmp_path) if mode == "tracking" else _fiction(tmp_path)
    try:
        w.ingest_structured([
            {"entity": "event:inspection", "attribute": "kind",
             "value": "inspection", "valid_from": 500.0},
        ], classify="rules")
        assert w.porcelain.events(until=100.0) == []          # not yet due
        due = w.porcelain.events(until=600.0)
        assert [e["id"] for e in due] == ["event:inspection"]  # due
    finally:
        w.close()


def test_b4_three_axes_one_fact(tmp_path):
    # valid Thursday (t=400), learned Monday (wall 5000, seq later), three
    # different answers on three axes
    clock = FakeClock(1000.0)
    w = _tracking(tmp_path, clock=clock)
    try:
        _seed(w)
        head_before = w.buffer.head()
        clock.t = 5000.0                                     # Monday, wall
        w.ingest_structured([
            {"entity": "obj:badge", "attribute": "in", "value": "place:garage",
             "value_type": "entity", "valid_from": 400.0,     # Thursday, story
             "status": "observed"},
        ], classify="rules")
        # sequence axis: absent before it was learned
        assert w.locate("obj:badge", valid_as_of=450.0,
                        asserted_as_of=head_before) == []
        # valid axis: reconstructs Thursday once learned
        assert w.locate("obj:badge", valid_as_of=450.0)[0] == "place:garage"
        # wall axis: freshness ages from the Monday stamp
        c = w.confidence("obj:badge", "in", now=5000.0)
        assert c["last_confirmed_at_wallclock"] == 5000.0
        assert c["recency"] == 1.0                            # just confirmed
    finally:
        w.close()


# ------------------------------------------------- tracking battery (5-10)

def test_b5_decay_honesty_component_level(tmp_path):
    clock = FakeClock(0.0)
    w = _tracking(tmp_path, clock=clock)
    try:
        _seed(w)
        # after 2 unconfirmed days: car (half-life 2d) at exactly one half-life;
        # couch (60d) barely moved — component-level oracle, pinned formula
        car = w.confidence("obj:car", "in", now=2 * DAY)
        couch = w.confidence("obj:couch", "position", now=2 * DAY)
        assert car["recency_status"] == couch["recency_status"] == "configured"
        assert abs(car["recency"] - 0.5) < 1e-9               # 2**(-2d/2d)
        assert abs(couch["recency"] - 2 ** (-(2 / 60))) < 1e-9
        assert couch["recency"] > 0.97
        # clamped: a historical now BEFORE the stamp yields recency 1.0, not >1
        past = w.confidence("obj:car", "in", now=-100.0)
        assert past["recency"] == 1.0
    finally:
        w.close()


def test_b5b_unconfigured_and_unconfirmed_fail_closed(tmp_path):
    clock = FakeClock(0.0)
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "uncfg.world", world_id="w:grey", model=stub,
              policy=OBSERVE_OR_UNKNOWN, clock=clock)
    try:
        # NO decay declarations at all -> unconfigured
        w.ingest_structured([
            {"entity": "obj:box", "attribute": "kind", "value": "object",
             "timeless": True},
            {"entity": "obj:box", "attribute": "state", "value": "sealed",
             "valid_from": 1.0, "status": "observed"},
        ], classify="rules")
        c = w.confidence("obj:box", "state", now=100.0)
        assert c["recency"] is None and c["recency_status"] == "unconfigured"
        assert c["last_confirmed_at_wallclock"] is None
        assert 0.0 < c["score"] <= 1.0        # renormalized, not zeroed/faked
        # policy exists but the row was ASSUMED -> no confirming stamp
        w.ingest_structured([
            {"entity": "attr:__world__", "attribute": "decay_halflife_seconds",
             "value": DAY, "timeless": True},
            {"entity": "obj:box", "attribute": "note", "value": "probably empty",
             "valid_from": 2.0, "status": "assumed"},
        ], classify="rules")
        c2 = w.confidence("obj:box", "note", now=100.0)
        assert c2["recency"] is None and c2["recency_status"] == "unconfirmed"
    finally:
        w.close()


def test_b6_b7_staleness_answer_and_reconfirmation(tmp_path):
    clock = FakeClock(0.0)
    w = _tracking(tmp_path, clock=clock)
    try:
        _seed(w)
        stale = w.confidence("obj:car", "in", now=21 * DAY)   # three weeks
        assert stale["last_confirmed_at_wallclock"] == 0.0    # the June-19 shape
        assert stale["recency"] < 0.001                       # honest: very stale
        # re-confirmation refreshes the stamp and restores recency...
        clock.t = 21 * DAY
        w.ingest_structured([
            {"entity": "obj:car", "attribute": "in", "value": "place:driveway",
             "value_type": "entity", "valid_from": 500.0, "status": "observed"},
        ], classify="rules")
        fresh = w.confidence("obj:car", "in", now=21 * DAY)
        assert fresh["last_confirmed_at_wallclock"] == 21 * DAY
        assert fresh["recency"] == 1.0
        # ...while valid-time history still answers the past
        assert w.locate("obj:car", valid_as_of=2.0)[0] == "place:driveway"
    finally:
        w.close()


def test_b8_quarantine_never_hardens(tmp_path):
    w = _tracking(tmp_path)
    try:
        _seed(w)
        w.ingest_structured([
            {"entity": "obj:car", "attribute": "in", "value": "place:garage",
             "value_type": "entity", "valid_from": 50.0, "status": "assumed"},
            {"entity": "obj:car", "attribute": "in", "value": "place:driveway",
             "value_type": "entity", "valid_from": 60.0, "status": "observed"},
        ], classify="rules")
        # the observed winner is authoritative
        assert w.locate("obj:car", valid_as_of=70.0)[0] == "place:driveway"
        # the assumed row SURVIVES in history with its status intact
        assumed = [r for r in w.buffer.visible(attribute="in")
                   if r.status == "assumed"]
        assert len(assumed) == 1 and assumed[0].value == "place:garage"
        # zero promotions: no row's status ever changed (append-only means a
        # promotion would be a NEW stated/observed row carrying the assumed
        # value later than the observed winner) and zero retractions exist
        promoted = [r for r in w.buffer.visible(attribute="in")
                    if r.value == "place:garage" and r.status in ("stated", "observed")]
        assert promoted == []
        retractions = [r for r in w.buffer.all_rows() if r.attribute == "retracts"]
        assert retractions == []
    finally:
        w.close()


def test_b9_stated_absence_vs_unknown(tmp_path):
    w = _tracking(tmp_path)
    try:
        _seed(w)
        w.ingest_structured([
            {"entity": "obj:van", "attribute": "kind", "value": "vehicle",
             "timeless": True},
            # the frozen explicit-negative representation: a declared
            # functional key, observed false — never inferred from contents()
            {"entity": "obj:van", "attribute": "has_fittings", "value": False,
             "valid_from": 5.0, "status": "observed"},
        ], classify="rules")
        neg = w.state("obj:van", "has_fittings")
        assert neg.winner is not None and neg.winner.value is False
        assert neg.winner.status == "observed"                # real information
        unknown = w.state("obj:van", "has_nipples")           # never asked
        assert unknown.winner is None                         # honest unknown
    finally:
        w.close()


def test_b10_never_invent_under_pressure(tmp_path):
    def scripted(prompt, schema):
        if "query plan" in prompt:
            return {"refer_targets": ["the footlocker"],
                    "keys": [{"target_index": 0, "attribute": "contents"}],
                    "wants_location": False}
        return {"durability": "STATE", "class_confidence": 0.9}

    stub = StubModel(fallback=scripted)
    w = World(tmp_path / "ni.world", world_id="w:grey", model=stub,
              policy=OBSERVE_OR_UNKNOWN, clock=FakeClock())
    try:
        w.ingest_structured([
            {"entity": "obj:footlocker", "attribute": "kind", "value": "object",
             "timeless": True},
            {"entity": "obj:footlocker", "attribute": "name",
             "value": "the footlocker", "timeless": True},
            # no per-thunk policy: the WORLD's observe_or_unknown governs —
            # exactly the never-invent discipline under test
            {"entity": "obj:footlocker", "attribute": "contents", "value": {},
             "value_type": "unresolved", "valid_from": 1.0},
        ], classify="rules")
        assert w.resolve("obj:footlocker", "contents") is UNKNOWN
        answer = w.porcelain.ask("what is in the footlocker?")
        assert not any("generated" in json.dumps(f) for f in answer.facts)
        generated = [r for r in w.buffer.all_rows() if r.status == "generated"]
        assert generated == []                                # zero, before & after
    finally:
        w.close()


# ------------------------------------------------ no-bias + fiction control

def test_b12_aliens_no_bias_stance_isolated(tmp_path):
    # vary ONLY stance; hold policy, clock, rows, provenance constant
    ROWS = [
        {"entity": "obj:box", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "person:alien", "attribute": "kind", "value": "alien", "timeless": True},
        {"entity": "obj:box", "attribute": "state", "value": "sealed",
         "valid_from": 1.0, "status": "observed"},
        {"entity": "person:alien", "attribute": "state", "value": "in the basement",
         "valid_from": 1.0, "status": "observed"},
    ]
    results = {}
    for stance in ("reality", "fiction"):
        stub = StubModel(fallback=rule_classifier_fallback())
        w = World(tmp_path / f"s_{stance}.world", world_id="w:grey", model=stub,
                  policy=OBSERVE_OR_UNKNOWN, clock=FakeClock(), stance=stance)
        try:
            w.ingest_structured(list(ROWS), classify="rules")
            results[stance] = {
                "alien": w.confidence("person:alien", "state", now=10.0),
                "box": w.confidence("obj:box", "state", now=10.0),
                "alien_row": [(r.status, r.value) for r in w.buffer.visible()
                              if r.entity == "person:alien" and r.attribute == "state"],
                "stance": w.charter()["stance"],
            }
        finally:
            w.close()
    # the identifier is present and correct...
    assert results["reality"]["stance"] == "reality"
    assert results["fiction"]["stance"] == "fiction"
    # ...and biases NOTHING: identical treatment across stances
    assert results["reality"]["alien"] == results["fiction"]["alien"]
    assert results["reality"]["alien_row"] == results["fiction"]["alien_row"]
    # ...and within the reality world, unexpected == mundane treatment
    r = results["reality"]
    assert r["alien"]["status"] == r["box"]["status"] == "observed"
    assert r["alien"]["score"] == r["box"]["score"]
    assert r["alien"]["recency_status"] == r["box"]["recency_status"]


def test_b11_fiction_control_no_decay(tmp_path):
    w = _fiction(tmp_path)
    try:
        _seed(w)      # same seed, invent_under_canon world
        c = w.confidence("obj:car", "in", now=21 * DAY)
        assert c["recency"] == 1.0 and c["recency_status"] == "permanent"
        assert c["last_confirmed_at_wallclock"] is None       # null in fiction
        # as-of/supersession identical to tracking
        assert w.locate("obj:car", valid_as_of=2.0)[0] == "place:driveway"
    finally:
        w.close()


# --------------------------------------------- restart + purity oracles

def test_b13_restart_reproduces_confidence(tmp_path):
    clock = FakeClock(0.0)
    p = tmp_path / "restart.world"
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(p, world_id="w:grey", model=stub,
              policy=OBSERVE_OR_UNKNOWN, clock=clock)
    _seed(w)
    before = w.confidence("obj:car", "in", now=3 * DAY)
    w.close()
    w2 = World(p, world_id="w:grey", model=stub,
               policy=OBSERVE_OR_UNKNOWN, clock=FakeClock(999.0))
    try:
        after = w2.confidence("obj:car", "in", now=3 * DAY)   # same explicit now
        assert before == after           # policy rebuilt from the log; identical
    finally:
        w2.close()


def test_b14_reads_are_pure(tmp_path):
    w = _tracking(tmp_path)
    try:
        _seed(w)
        conn = w.buffer.raw_connection()
        head, d, changes = w.buffer.head(), dump(w.buffer), conn.total_changes
        w.confidence("obj:car", "in", now=5 * DAY)
        w.confidence("obj:car", "in", frame=["canon", "public"], now=5 * DAY)
        w.porcelain.snapshot(["obj:car"])
        assert w.buffer.head() == head
        assert dump(w.buffer) == d
        assert conn.total_changes == changes
    finally:
        w.close()


def test_gate_rejects_malformed_decay_declarations(tmp_path):
    w = _tracking(tmp_path)
    try:
        receipt = w.porcelain.ingest_structured([
            {"entity": "attr:in", "attribute": "decay_halflife_seconds",
             "value": -5, "timeless": True},
            {"entity": "attr:in", "attribute": "decay_halflife_seconds",
             "value": "fast", "timeless": True},
        ], classify="rules")
        assert len(receipt.skipped) == 2
        assert all(s["reason"] == "invalid_decay_halflife" for s in receipt.skipped)
    finally:
        w.close()


# ------------------------------- Cx 604: finite-clock + precedence + multiframe

def test_finite_clock_contract(tmp_path):
    # a NaN/inf STORED stamp falls to the honest unconfirmed branch (never a
    # fabricated-fresh confirmation); a non-finite NOW fails loudly.
    for bad in (float("nan"), float("inf"), float("-inf")):
        clock = FakeClock(bad)
        w = _tracking(tmp_path, name=f"badclock_{repr(bad)}", clock=clock)
        try:
            w.ingest_structured([
                {"entity": "attr:__world__", "attribute": "decay_halflife_seconds",
                 "value": 10.0, "timeless": True},
                {"entity": "obj:b", "attribute": "kind", "value": "object",
                 "timeless": True},
                {"entity": "obj:b", "attribute": "state", "value": "sealed",
                 "valid_from": 1.0, "status": "observed"},   # stamped with `bad`
            ], classify="rules")
            c = w.confidence("obj:b", "state", now=100.0)
            assert c["recency_status"] == "unconfirmed"       # never "configured"
            assert c["recency"] is None
            assert c["last_confirmed_at_wallclock"] is None
            json.dumps(c)                                     # strict-JSON safe
            # explicit non-finite now fails loudly, never computes
            with pytest.raises(ValueError, match="finite"):
                w.confidence("obj:b", "state", now=bad)
        finally:
            w.close()
    # an injected clock returning non-finite at read time also fails loudly
    clock = FakeClock(0.0)
    w = _tracking(tmp_path, name="latebad", clock=clock)
    try:
        _seed(w)
        clock.t = float("nan")
        with pytest.raises(ValueError, match="finite"):
            w.confidence("obj:car", "in")                     # defaults to clock
    finally:
        w.close()


def test_decay_precedence_three_levels_one_world(tmp_path):
    # the frozen B3 oracle: exact authored attr > attr:in family > world
    # default, all declared in ONE world (half-lives 10/20/40; age 10 ->
    # recencies 0.5 / 2**-0.5 / 2**-0.25).
    clock = FakeClock(0.0)
    w = _tracking(tmp_path, name="prec", clock=clock)
    try:
        w.ingest_structured([
            {"entity": "attr:worn_by", "attribute": "decay_halflife_seconds",
             "value": 10.0, "timeless": True},
            {"entity": "attr:in", "attribute": "decay_halflife_seconds",
             "value": 20.0, "timeless": True},
            {"entity": "attr:__world__", "attribute": "decay_halflife_seconds",
             "value": 40.0, "timeless": True},
            {"entity": "person:ana", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "obj:ring", "attribute": "kind", "value": "object",
             "timeless": True},
            {"entity": "obj:coat", "attribute": "kind", "value": "object",
             "timeless": True},
            {"entity": "obj:lamp", "attribute": "kind", "value": "object",
             "timeless": True},
            # winner authored worn_by -> the EXACT policy (10)
            {"entity": "obj:ring", "attribute": "worn_by", "value": "person:ana",
             "value_type": "entity", "valid_from": 1.0, "status": "observed"},
            # winner authored held_by (containment member, no exact declaration)
            # -> falls through to the attr:in FAMILY policy (20)
            {"entity": "obj:coat", "attribute": "held_by", "value": "person:ana",
             "value_type": "entity", "valid_from": 1.0, "status": "observed"},
            # unrelated key -> the WORLD default (40)
            {"entity": "obj:lamp", "attribute": "shade", "value": "green",
             "valid_from": 1.0, "status": "observed"},
        ], classify="rules")
        ring = w.confidence("obj:ring", "worn_by", now=10.0)
        coat = w.confidence("obj:coat", "held_by", now=10.0)
        lamp = w.confidence("obj:lamp", "shade", now=10.0)
        assert abs(ring["recency"] - 0.5) < 1e-12               # exact: 10s
        assert abs(coat["recency"] - 2 ** -0.5) < 1e-12         # family: 20s
        assert abs(lamp["recency"] - 2 ** -0.25) < 1e-12        # default: 40s
        assert {ring["recency_status"], coat["recency_status"],
                lamp["recency_status"]} == {"configured"}
    finally:
        w.close()


def test_tracking_multiframe_confirmation_over_frame_union(tmp_path):
    # a CONFIGURED tracking multiframe read: the effective winner's stamp comes
    # from eligible same-value confirming rows in the entitled frame union;
    # an assumed row never refreshes it; asserted_as_of rolls it back.
    clock = FakeClock(100.0)
    w = _tracking(tmp_path, name="mfconf", clock=clock)
    try:
        w.ingest_structured([
            {"entity": "attr:__world__", "attribute": "decay_halflife_seconds",
             "value": 100.0, "timeless": True},
            {"entity": "obj:torch", "attribute": "kind", "value": "object",
             "timeless": True},
            {"entity": "obj:torch", "attribute": "state", "value": "lit",
             "valid_from": 1.0, "status": "observed"},          # canon @100
        ], classify="rules")
        head_after_first = w.buffer.head()
        clock.t = 300.0
        w.ingest_structured([
            {"entity": "obj:torch", "attribute": "state", "value": "lit",
             "valid_from": 2.0, "frame": "public", "status": "observed"},  # @300
        ], classify="rules")
        clock.t = 500.0
        w.ingest_structured([
            {"entity": "obj:torch", "attribute": "state", "value": "lit",
             "valid_from": 3.0, "status": "assumed"},           # NEVER refreshes
        ], classify="rules")
        c = w.confidence("obj:torch", "state", frame=["canon", "public"],
                         now=300.0)
        assert c["recency_status"] == "configured"
        assert c["last_confirmed_at_wallclock"] == 300.0        # the public row
        assert c["recency"] == 1.0                              # not the assumed 500
        # a frame union WITHOUT public sees only the canon confirmation
        c2 = w.confidence("obj:torch", "state", frame=["canon", "knows:person_x"],
                          now=300.0)
        assert c2["last_confirmed_at_wallclock"] == 100.0
        # asserted_as_of before the public row rolls the stamp back
        c3 = w.confidence("obj:torch", "state", frame=["canon", "public"],
                          asserted_as_of=head_after_first, now=300.0)
        assert c3["last_confirmed_at_wallclock"] == 100.0
    finally:
        w.close()
