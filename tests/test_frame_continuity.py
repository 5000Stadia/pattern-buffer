"""FRAME-CONTINUITY-V1: widening a frame is an explicit choice, and every row
says where it lives (specs/FRAME-CONTINUITY-V1.md, r2).

One group of tests per Check in §6. The cast: Dan's frame is
`knows:person:dan`; Daniel (the same man, before he took the short name) and
Danny (another man who happens to share a nickname) have their own.
"""

from __future__ import annotations

import inspect
import sqlite3
import sys
from pathlib import Path

import pytest

from patternbuffer import World
from patternbuffer.ingest import SKIP_REASONS
from patternbuffer.model import INVIOLABLE_CORE
from patternbuffer.porcelain import Porcelain
from patternbuffer.testing import StubModel, rule_classifier_fallback

DAN = "knows:person:dan"
DANIEL = "knows:person:daniel"
DANNY = "knows:person:danny"


@pytest.fixture
def world(tmp_path):
    stub = StubModel(fallback=rule_classifier_fallback())
    w = World(tmp_path / "fc.world", world_id="w:fc", model=stub)
    yield w
    w.close()


def _row(entity, attribute, value, frame, valid_from=1.0, **extra) -> dict:
    return {"entity": entity, "attribute": attribute, "value": value,
            "frame": frame, "valid_from": valid_from, **extra}


def _seed(w) -> None:
    """Three persons, a shared subject, and a belief in each man's frame."""
    p = w.porcelain
    p.ingest_structured([
        {"entity": f"person:{n}", "attribute": "kind", "value": "person",
         "timeless": True} for n in ("dan", "daniel", "danny", "vera")
    ] + [
        {"entity": "place:cellar", "attribute": "kind", "value": "place",
         "timeless": True},
        {"entity": "obj:key", "attribute": "kind", "value": "object",
         "timeless": True},
    ])
    p.ingest_structured([
        _row("person:vera", "mood", "wary", DANIEL, 1.0),
        _row("person:vera", "mood", "calm", DAN, 5.0),
        _row("person:vera", "mood", "angry", DANNY, 9.0),
        _row("obj:key", "in", "place:cellar", DANIEL, 1.0),
    ])


def _ids(facts: list[dict]) -> list[str]:
    return [f["provenance"]["assertion_id"] for f in facts]


def _frames(facts: list[dict]) -> set[str]:
    return {f["provenance"]["frame"] for f in facts}


def _strip(value):
    """A payload without the new `provenance.frame` key, for byte comparison
    with a read that does not carry it."""
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items()
                if not (k == "frame" and "assertion_id" in value)}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


# ------------------------------------------------------- §1 every fact says


def test_1_provenance_frame_is_appended_after_the_existing_keys(world):
    _seed(world)
    fact = world.porcelain.state("person:vera", "mood", DAN)["fact"]
    assert list(fact["provenance"]) == ["status", "source_chain", "assertion_id", "frame"]
    assert fact["provenance"]["frame"] == DAN


def test_1_every_read_that_serves_facts_labels_them(world):
    p = world.porcelain
    _seed(world)
    # two top-rank rows at one stamp: conflicted, with a Fact on each side
    p.ingest_structured([_row("person:vera", "mood", "tense", DAN, 5.0)])
    st = p.state("person:vera", "mood", DAN)
    assert st["status"] == "conflicted"
    assert [f["provenance"]["frame"] for f in st["conflicting_facts"]] == [DAN, DAN]
    # a set-valued key lists its members, each labelled
    p.ingest_structured([
        _row("person:vera", "alias", "the quiet one", DAN, None, timeless=True),
        _row("person:vera", "alias", "ms vera", DAN, None, timeless=True),
    ])
    sv = p.state("person:vera", "alias", DAN)
    assert sv["values"] and _frames(sv["values"]) == {DAN}
    # state_union, facts, snapshot
    assert p.state_union("person:vera", "mood", DAN)["status"] == "conflicted"
    assert _frames(p.facts(DAN)) == {DAN}
    snap = p.snapshot(["person:vera"], frame=DAN)
    assert snap["facts"] and _frames(snap["facts"]) == {DAN}


def test_1_quantity_and_divergent_facts_carry_the_label(world):
    """_quantity_fact (an accrue total, in state and in frame_diff) and a
    divergent fact (frame_diff) take the stored frame too."""
    p = world.porcelain
    _seed(world)
    p.ingest_structured([
        {"entity": "attr:gold", "attribute": "fold_policy", "value": "accrue",
         "timeless": True},
    ])
    p.ingest_structured([
        _row("person:vera", "gold", 500, "canon", 1.0),
        _row("person:vera", "gold", -20, "canon", 2.0, value_type="delta"),
        _row("person:vera", "gold", 500, DAN, 1.0),
    ])
    total = p.state("person:vera", "gold", "canon")
    assert total["quantity"] == 480 and total["fact"]["provenance"]["frame"] == "canon"
    diff = p.frame_diff("canon", DAN, ["person:vera"])
    gold = [f for f in diff if f["attribute"] == "gold"]
    assert gold and gold[0]["divergent"] is True and gold[0]["b_value"] == 500
    assert gold[0]["provenance"]["frame"] == "canon"
    # a normal divergent fact, a normal missing one
    p.ingest_structured([_row("person:vera", "mood", "tense", "canon", 1.0),
                         _row("person:vera", "trade", "smith", "canon", 1.0)])
    mood = [f for f in p.frame_diff("canon", DAN, ["person:vera"])
            if f["attribute"] in ("mood", "trade")]
    assert {f["attribute"] for f in mood} == {"mood", "trade"}
    assert _frames(mood) == {"canon"}


def test_1_exact_payloads_keep_every_other_byte(world):
    """With exact scope the only difference from the pre-spec payload is the
    one new key: explicit `exact` is the default, and stripping the label
    leaves the old three-key provenance."""
    p = world.porcelain
    _seed(world)
    plain = p.state("person:vera", "mood", DAN)
    assert p.state("person:vera", "mood", DAN, frame_scope="exact") == plain
    assert p.facts(DAN, frame_scope="exact") == p.facts(DAN)
    assert p.state_union("person:vera", "mood", DAN, frame_scope="exact") == \
        p.state_union("person:vera", "mood", DAN)
    stripped = _strip(plain)
    assert set(stripped["fact"]["provenance"]) == {"status", "source_chain", "assertion_id"}
    assert list(stripped["fact"]) == ["entity", "attribute", "value", "valid",
                                      "provenance", "divergent", "b_value", "value_type"]


# ---------------------------------------------------------- §2 frame_scope


def test_2_continued_follows_declared_edges_transitively(world):
    p = world.porcelain
    _seed(world)
    p.continue_frame("person:daniel", "person:dan", "the same man; host decision")
    p.continue_frame("person:danny", "person:daniel", "an earlier spelling")
    exact = p.facts(DAN)
    wide = p.facts(DAN, frame_scope="continued")
    assert _frames(exact) == {DAN}
    assert _frames(wide) == {DAN, DANIEL, DANNY}          # transitive: danny -> daniel -> dan
    assert set(_ids(exact)) < set(_ids(wide))
    # one way: daniel reads danny but never dan; danny reads only itself
    assert _frames(p.facts(DANIEL, frame_scope="continued")) == {DANIEL, DANNY}
    assert _frames(p.facts(DANNY, frame_scope="continued")) == {DANNY}
    # a fold over the union is one row set under the ordinary rules: danny's
    # later "angry" (9.0) outranks dan's "calm" (5.0)
    assert p.state("person:vera", "mood", DAN, frame_scope="continued")["fact"]["value"] == "angry"
    assert p.state("person:vera", "mood", DAN)["fact"]["value"] == "calm"
    sel = p.state("person:vera", "mood", DAN, frame_scope="continued")
    assert sel["fact"]["provenance"]["frame"] == DANNY
    # state_union takes the scope too
    assert p.state_union("person:vera", "mood", DAN,
                         frame_scope="continued")["fact"]["value"] == "angry"


def test_2_continued_stops_at_a_retraction_and_honours_pinned_reads(world):
    p = world.porcelain
    _seed(world)
    before = world.buffer.head()
    receipt = p.continue_frame("person:daniel", "person:dan", "host decision")
    declared = world.buffer.head()
    edge = receipt.rows[0]["assertion_id"]
    p.retract(edge, "wrong man")
    retracted = world.buffer.head()
    assert _frames(p.facts(DAN, frame_scope="continued")) == {DAN}        # head: ended
    assert _frames(p.facts(DAN, frame_scope="continued",
                           asserted_as_of=declared)) == {DAN, DANIEL}     # as it stood
    assert _frames(p.facts(DAN, frame_scope="continued",
                           asserted_as_of=before)) == {DAN}               # before the event
    assert _frames(p.facts(DAN, frame_scope="continued",
                           asserted_as_of=retracted)) == {DAN}
    # transitive chain broken in the middle: the far end drops with it
    p.continue_frame("person:daniel", "person:dan", "again")
    second = p.continue_frame("person:danny", "person:daniel", "chain")
    assert _frames(p.facts(DAN, frame_scope="continued")) == {DAN, DANIEL, DANNY}
    p.retract(second.rows[0]["assertion_id"], "no")
    assert _frames(p.facts(DAN, frame_scope="continued")) == {DAN, DANIEL}


def test_2_merged_follows_the_canon_closure_only_never_aka(world):
    p = world.porcelain
    _seed(world)
    assert p.merge("person:dan", "person:daniel", "the same man")["outcome"] == "merged"
    p.correlate("person:dan", "person:danny", "a facet, not the same man")
    wide = p.facts(DAN, frame_scope="merged")
    assert _frames(wide) == {DAN, DANIEL}                  # closure yes, aka no
    assert _frames(p.facts(DANIEL, frame_scope="merged")) == {DAN, DANIEL}
    assert _frames(p.facts(DAN)) == {DAN}                  # the merge widens nothing by itself
    assert _frames(p.facts(DAN, frame_scope="continued")) == {DAN}
    assert p.state("obj:key", "in", DAN)["status"] == "unknown"
    assert p.state("obj:key", "in", DAN, frame_scope="merged")["fact"]["value"] == "place:cellar"
    assert p.state("obj:key", "in", DAN, frame_scope="merged")["fact"]["provenance"]["frame"] == DANIEL
    # a merge retracted ends the widening, at head and for pinned reads alike
    merge_edge = world.buffer.visible(attribute="same_as")[0]
    pinned = world.buffer.head()
    p.retract(merge_edge.id, "wrong merge")
    assert _frames(p.facts(DAN, frame_scope="merged")) == {DAN}
    assert _frames(p.facts(DAN, frame_scope="merged", asserted_as_of=pinned)) == {DAN, DANIEL}


def test_2_a_scope_that_adds_nothing_is_the_plain_read(world):
    p = world.porcelain
    _seed(world)
    assert p.facts(DAN, frame_scope="continued") == p.facts(DAN)
    assert p.facts(DAN, frame_scope="merged") == p.facts(DAN)
    assert p.state("person:vera", "mood", DAN, frame_scope="merged") == \
        p.state("person:vera", "mood", DAN)


def test_2_only_knows_frames_widen(world):
    p = world.porcelain
    _seed(world)
    for frame in ("canon", "plot:act_one", "public", "knows:"):
        for scope in ("continued", "merged"):
            with pytest.raises(ValueError, match="frame_scope"):
                p.facts(frame, frame_scope=scope)
            with pytest.raises(ValueError, match="frame_scope"):
                p.state("person:vera", "mood", frame, frame_scope=scope)
            with pytest.raises(ValueError, match="frame_scope"):
                p.state_union("person:vera", "mood", frame, frame_scope=scope)
        assert p.facts(frame, frame_scope="exact") is not None     # exact never refuses
    with pytest.raises(ValueError, match="frame_scope"):
        p.facts(DAN, frame_scope="everything")


def test_2_facts_and_entities_default_to_exact(world):
    p = world.porcelain
    _seed(world)
    p.continue_frame("person:daniel", "person:dan", "host decision")
    p.merge("person:dan", "person:daniel", "the same man")
    assert _frames(p.facts(DAN)) == {DAN}
    assert "obj:key" not in p.entities(DAN)               # never widens, in any case
    assert "obj:key" in p.entities(DANIEL)
    assert inspect.signature(Porcelain.facts).parameters["frame_scope"].default == "exact"


def test_2_only_the_all_fact_reads_accept_frame_scope(world):
    """The porcelain walk: exactly state, state_union and facts take
    `frame_scope`; every other public verb refuses it."""
    public = {n: m for n, m in inspect.getmembers(Porcelain, inspect.isfunction)
              if not n.startswith("_")}
    widenable = {n for n, m in public.items()
                 if "frame_scope" in inspect.signature(m).parameters}
    assert widenable == {"state", "state_union", "facts"}
    p = world.porcelain
    _seed(world)
    for call in (
        lambda: p.entities(DAN, frame_scope="merged"),
        lambda: p.confidence("person:vera", "mood", DAN, frame_scope="merged"),
        lambda: p.frame_diff(DAN, DANIEL, ["person:vera"], frame_scope="merged"),
        lambda: p.events(frame=DAN, frame_scope="merged"),
        lambda: p.in_transit(frame=DAN, frame_scope="merged"),
        lambda: p.locate("obj:key", frame=DAN, frame_scope="merged"),
        lambda: p.contents("place:cellar", frame=DAN, frame_scope="merged"),
        lambda: p.snapshot(["person:vera"], frame=DAN, frame_scope="merged"),
        lambda: p.where("mood", "==", 1, frame=DAN, frame_scope="merged"),
    ):
        with pytest.raises(TypeError, match="frame_scope"):
            call()


def test_2_events_and_in_transit_never_widen(world):
    p = world.porcelain
    _seed(world)
    p.ingest_structured([
        _row("event:walk", "kind", "moved", DANIEL, 2.0),
        _row("event:walk", "agent", "person:vera", DANIEL, 2.0),
        _row("event:walk", "origin", "place:cellar", DANIEL, 2.0),
        _row("event:walk", "destination", "place:cellar", DANIEL, 3.0, valid_to=None),
    ])
    p.continue_frame("person:daniel", "person:dan", "host decision")
    p.merge("person:dan", "person:daniel", "the same man")
    assert [e["id"] for e in p.events(frame=DANIEL)] == ["event:walk"]
    assert p.events(frame=DAN) == []
    assert p.in_transit(frame=DAN) == []
    assert p.in_transit(frame=DAN) == world.in_transit(frame=DAN)


def test_2_writes_never_widen(world):
    """A write lands in exactly the frame it names, and no write verb takes a
    scope."""
    p = world.porcelain
    _seed(world)
    p.continue_frame("person:daniel", "person:dan", "host decision")
    receipt = p.ingest_structured([_row("person:vera", "mood", "new", DAN, 7.0)])
    assert receipt.frames == [DAN]
    mutators = {"ingest_structured", "ingest", "commit_set", "retract", "merge",
                "confirm", "reject", "correlate", "retype", "continue_frame",
                "resolve", "reconcile", "adjudicate_deferred"}
    for name in mutators:
        assert "frame_scope" not in inspect.signature(getattr(Porcelain, name)).parameters


def test_2_each_wide_fact_names_its_stored_frame(world):
    p = world.porcelain
    _seed(world)
    p.continue_frame("person:daniel", "person:dan", "host decision")
    for f in p.facts(DAN, frame_scope="continued"):
        row = world.buffer.get(f["provenance"]["assertion_id"])
        assert f["provenance"]["frame"] == row.frame
    by_frame = {f["provenance"]["frame"] for f in p.facts(DAN, frame_scope="continued")
                if f["entity"] == "obj:key"}
    assert by_frame == {DANIEL}
    # state's conflicting facts, under a wide scope, name each side's own frame
    p.ingest_structured([_row("person:vera", "mood", "furious", DANIEL, 5.0),
                         _row("person:vera", "mood", "bored", DAN, 5.0)])
    st = p.state("person:vera", "mood", DAN, frame_scope="continued")
    assert st["status"] == "conflicted"
    assert {f["provenance"]["frame"] for f in st["conflicting_facts"]} == {DAN, DANIEL}


# ------------------------------------------------- §2a confidence, frame_diff


def test_2a_confidence_and_frame_diff_keep_their_semantics(world):
    p = world.porcelain
    _seed(world)

    def answers():
        return (p.confidence("person:vera", "mood", DAN),
                p.confidence("person:vera", "mood", [DAN]),
                p.confidence("person:vera", "mood", [DAN, DANIEL]),
                p.confidence("person:vera", "mood", DANIEL),
                p.frame_diff(DANIEL, DAN, ["obj:key"]),
                p.frame_diff(DANIEL, [DAN, DANIEL], ["obj:key"]))

    before = answers()
    p.continue_frame("person:daniel", "person:dan", "host decision")   # changes neither
    p.merge("person:dan", "person:daniel", "the same man")
    assert answers() == before
    plain, as_list, both, daniel, diff, covered = before
    assert as_list == plain and plain["conflicted"] is False
    assert both["conflicted"] is True            # the named frames disagree: their union is read
    assert daniel["conflicted"] is False
    # frame_diff compares exactly the named frames: daniel's key is absent from dan
    assert [f["value"] for f in diff] == ["place:cellar"] and covered == []
    assert diff[0]["provenance"]["frame"] == DANIEL
    # confidence serves no Fact, so it has no label to add; neither verb takes a scope
    assert "provenance" not in plain
    for name in ("confidence", "frame_diff"):
        assert "frame_scope" not in inspect.signature(getattr(Porcelain, name)).parameters


def test_2a_frame_diff_is_unchanged_apart_from_the_label(world):
    p = world.porcelain
    _seed(world)
    diff = p.frame_diff(DANIEL, DAN, ["person:vera", "obj:key"])
    assert {(f["entity"], f["attribute"]) for f in diff} == {
        ("person:vera", "mood"), ("obj:key", "in")}
    for f in diff:
        assert list(f["provenance"]) == ["status", "source_chain", "assertion_id", "frame"]
        assert f["provenance"]["frame"] == DANIEL
        assert world.buffer.get(f["provenance"]["assertion_id"]).frame == DANIEL


# ------------------------------------------------------ §3 the host's event


def test_3_the_verb_writes_canon_only(world):
    p = world.porcelain
    _seed(world)
    before = world.buffer.head()
    receipt = p.continue_frame("person:daniel", "person:dan", "the same man; host decision")
    assert receipt.frames == ["canon"] and receipt.skipped == []
    assert [(r["entity"], r["attribute"]) for r in receipt.rows] == [
        ("person:daniel", "frame_continues_as"), (receipt.rows[0]["assertion_id"], "evidence")]
    new_rows = [r for r in world.buffer.all_rows() if r.seq > before]
    assert len(new_rows) == 2 and {r.frame for r in new_rows} == {"canon"}
    edge, proof = new_rows
    assert (edge.value, edge.value_type, edge.status, edge.valid_from, edge.valid_to) == \
        ("person:dan", "entity", "stated", None, None)
    assert proof.value == "the same man; host decision" and proof.status == "stated"
    # idempotent: the same declaration writes nothing and says why
    again = p.continue_frame("person:daniel", "person:dan", "again")
    assert again.rows == [] and again.warnings and world.buffer.head() == before + 2


def test_3_the_verb_refuses_malformed_calls(world):
    p = world.porcelain
    head = world.buffer.head()
    for args in (("daniel", "person:dan", "e"), ("person:daniel", "dan", "e"),
                 ("person:dan", "person:dan", "e"), ("person:daniel", "person:dan", " ")):
        with pytest.raises(ValueError):
            p.continue_frame(*args)
    assert world.buffer.head() == head


def test_3_frame_names_are_never_resolved_through_identity(world):
    """The edge keeps the observer ids as the host gave them, so a merge of
    two names cannot swing it onto a different frame (P1)."""
    p = world.porcelain
    _seed(world)
    p.merge("person:daniel", "person:danny", "same")      # one closure, two stored names
    p.continue_frame("person:danny", "person:dan", "host decision")
    edge = world.buffer.visible(attribute="frame_continues_as")[0]
    assert (edge.entity, edge.value) == ("person:danny", "person:dan")
    assert _frames(p.facts(DAN, frame_scope="continued")) == {DAN, DANNY}


def test_3_prose_extraction_never_writes_it(world):
    p = world.porcelain
    _seed(world)
    item = {"entity": "person:daniel", "attribute": "frame_continues_as",
            "value": "person:dan", "timeless": True}
    receipt = p.ingest_structured([item], extracted=True)
    assert [s["reason"] for s in receipt.skipped] == ["host_only_predicate"]
    assert world.buffer.visible(attribute="frame_continues_as") == []
    # the gate's structured path (a host, not prose) accepts the canon item
    ok = p.ingest_structured([item])
    assert ok.skipped == [] and world.buffer.visible(attribute="frame_continues_as")
    # a commit_set assert op is authored, never prose
    assert "host_only_predicate" in SKIP_REASONS


def test_3_outside_canon_or_not_an_entity_is_refused(world):
    p = world.porcelain
    _seed(world)
    base = {"entity": "person:daniel", "attribute": "frame_continues_as",
            "value": "person:dan", "timeless": True}
    outside = p.ingest_structured([{**base, "frame": DAN}])
    assert [s["reason"] for s in outside.skipped] == ["identity_edge_outside_canon"]
    for bad in ({"value": "not an id"}, {"value": "person:dan", "value_type": "literal"},
                {"value": "Person:Dan"}):
        r = p.ingest_structured([{**base, **bad}])
        assert [s["reason"] for s in r.skipped] == ["malformed_id"], bad
    assert world.buffer.visible(attribute="frame_continues_as", frame="canon") == []
    # even with extracted set, the host-only refusal wins over the frame rule
    both = p.ingest_structured([{**base, "frame": DAN}], extracted=True)
    assert [s["reason"] for s in both.skipped] == ["host_only_predicate"]


def test_3_it_is_inviolable_and_cannot_be_redeclared(world):
    assert "frame_continues_as" in INVIOLABLE_CORE
    p = world.porcelain
    with pytest.raises(ValueError, match="inviolable core"):
        p.ingest_structured([{"entity": "attr:frame_continues_as", "attribute": "arity",
                              "value": "functional", "timeless": True}])
    assert not world.semantics.is_declared("frame_continues_as")


def test_3_no_identity_verb_writes_or_reads_it(world):
    p = world.porcelain
    _seed(world)
    p.merge("person:dan", "person:daniel", "same")
    p.correlate("person:dan", "person:danny", "facet")
    p.reject("person:vera", "person:danny")
    p.reconcile()
    p.adjudicate_deferred()
    assert world.buffer.visible(attribute="frame_continues_as") == []
    assert _frames(p.facts(DAN, frame_scope="continued")) == {DAN}


def test_3_the_declaration_is_bookkeeping_not_a_world_fact(world):
    p = world.porcelain
    _seed(world)
    p.continue_frame("person:daniel", "person:dan", "host decision")
    assert p.state("person:daniel", "frame_continues_as")["status"] == "unknown"
    assert all(f["attribute"] != "frame_continues_as"
               for f in p.snapshot(["person:daniel"])["facts"])
    assert p.fidelity_audit()["open_conflicts"] == []


# ------------------------------------------------------ §4 the battery grades


def _battery():
    root = Path(__file__).resolve().parent.parent / "evals" / "harness"
    sys.path.insert(0, str(root))
    try:
        import battery
    finally:
        sys.path.remove(str(root))
    return battery


def test_4_verdict_16_grades_the_engine_read_on_the_anchor(tmp_path):
    anchor = Path(__file__).resolve().parent.parent / "examples" / "anchor"
    if not (anchor / "anchor.world").exists():
        pytest.skip("anchor world not present")
    dst = tmp_path / "anchor.world"
    src = sqlite3.connect(f"file:{anchor / 'anchor.world'}?mode=ro", uri=True)
    out = sqlite3.connect(dst)
    src.backup(out)
    out.close()
    src.close()
    import json
    battery = _battery()
    w = World(dst, world_id=json.loads((anchor / "STAMP.json").read_text())["world_id"])
    try:
        verdicts = {v.qid: v for v in battery.run_battery(w)}
        assert verdicts[16].status == "PASS"
        assert "(knows:person:sela_voss)" in verdicts[16].detail     # the stored frame, labelled
    finally:
        w.close()


def test_4_verdict_16_source_reads_through_frame_scope():
    """No hand-built union of frames remains in the battery: verdict 16 reads
    Sela's frame through the engine."""
    source = inspect.getsource(_battery().run_battery)
    start = source.index("Verdict(16,")
    end = source.index("add(telling)", start)
    section = source[start:end]
    assert 'frame_scope="merged"' in section
    assert "buffer.visible(frame=f)" not in section and "registry.resolve" not in section


# -------------------------------------------- §5 the emberroad2 scan-then-retract


@pytest.mark.parametrize("scope", ["exact", "continued", "merged"])
def test_5_scan_then_retract_keyed_on_provenance_frame_stays_in_its_frame(world, scope):
    """P4's measured case, rebuilt small: a host cleans Sela's `knows:` frame
    by scanning and retracting. Under every scope, the loop keyed on
    `provenance.frame` retracts nothing stored in another character's frame."""
    p = world.porcelain
    mine, theirs = "knows:person:sela", "knows:person:sela_voss"
    p.ingest_structured([
        {"entity": "person:sela", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:sela_voss", "attribute": "kind", "value": "person",
         "timeless": True},
    ])
    p.ingest_structured([_row(f"obj:o{i}", "colour", "red", mine, 1.0) for i in range(8)])
    p.ingest_structured([_row(f"obj:t{i}", "colour", "blue", theirs, 1.0) for i in range(72)])
    p.continue_frame("person:sela_voss", "person:sela", "host decision")
    p.merge("person:sela", "person:sela_voss", "the same woman")

    scanned = p.facts(mine, frame_scope=scope)
    assert len(scanned) == (8 if scope == "exact" else 80)       # the scan widened only on request
    for fact in scanned:
        if fact["provenance"]["frame"] == mine:                   # the rule ADOPTION.md gives
            p.retract(fact["provenance"]["assertion_id"], "scrub")

    retracted = [world.buffer.get(r.entity) for r in world.buffer.all_rows()
                 if r.attribute == "retracts"]
    assert len(retracted) == 8 and {r.frame for r in retracted} == {mine}
    assert len(p.facts(theirs)) == 72 + 0                         # every row there survives
    assert p.facts(mine, frame_scope="exact") == []


def test_5_the_unlabelled_loop_is_what_hurts(world):
    """The control: the same loop with no `provenance.frame` check retracts
    the other frame's rows once the scan is widened. This is the harm the
    label exists to prevent; exact (the default) cannot do it."""
    p = world.porcelain
    mine, theirs = "knows:person:sela", "knows:person:sela_voss"
    p.ingest_structured([
        _row("obj:a", "colour", "red", mine, 1.0),
        _row("obj:b", "colour", "blue", theirs, 1.0),
    ])
    p.merge("person:sela", "person:sela_voss", "the same woman")
    for fact in p.facts(mine):                                    # default scope: safe
        assert fact["provenance"]["frame"] == mine
    widened = p.facts(mine, frame_scope="merged")
    assert {f["provenance"]["frame"] for f in widened} == {mine, theirs}


# ------------------------------------------------------------------ the MCP


def test_mcp_registers_the_verb_and_the_three_scopes():
    from patternbuffer.mcp import V1_MUTATIONS, build_registry

    reg = build_registry()
    assert "continue_frame" in V1_MUTATIONS and "continue_frame" in reg
    for read in ("state", "state_union", "facts"):
        assert reg[read]["inputSchema"]["properties"]["frame_scope"]["default"] == "exact"
    for read in set(reg) - {"state", "state_union", "facts"}:
        assert "frame_scope" not in reg[read]["inputSchema"]["properties"], read
    assert reg["continue_frame"]["annotations"]["readOnlyHint"] is False


def test_mcp_dispatch_refuses_frame_scope_on_other_reads(world):
    from patternbuffer.mcp import dispatch

    _seed(world)
    with pytest.raises(ValueError, match="frame_scope"):
        dispatch(world, "confidence",
                 {"entity": "person:vera", "attribute": "mood", "frame_scope": "merged"})
    out = dispatch(world, "facts", {"frame": DAN, "frame_scope": "continued"})
    assert set(out) == {"result"} and out["result"]
