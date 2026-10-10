"""BUILD-TIMINGS-V1 (R26): stage timings, parallel pass-0, gleaning, runner options.
Stub models only: no real model call."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "evals" / "harness"))

from pipeline import Pipeline
from registry import EntityCard, WorldRegistry, glean

WID = "w:t"
SEGS = ["chapter one text", "chapter two text", "chapter three text"]


def seg_model(calls: list | None = None):
    """Per-segment lines keyed on the passage text; records every prompt."""
    lock = threading.Lock()

    def model(prompt, schema):
        with lock:
            if calls is not None:
                calls.append(prompt)
        if "chapter one" in prompt:
            return {"lines": ["E|person:a|person|Aye;Ayla|the clerk", "E|place:x|room|X",
                              "O|Day 0 = one", "N|start|0", "A|reactors|reactor count"]}
        if "chapter two" in prompt:
            return {"lines": ["E|person:a|person|Aye;Aya|the gray woman", "E|place:y|room|Y",
                              "O|Day 0 = two", "N|start|9", "N|later|3", "P|place:x|place:y"]}
        return {"lines": ["E|person:b|person|Bee", "E|person:a|person|Aye|the clerk"]}

    return model


class TestParallelReduce:
    def test_same_id_one_card_and_segment_order(self, tmp_path):
        p = Pipeline(seg_model(), WID, tmp_path / "run", max_workers=3)
        reg = p.pass0(segments=SEGS, parallel=True)
        assert list(reg.entities) == ["person:a", "place:x", "place:y", "person:b"]
        a = reg.entities["person:a"]
        assert a.names == ["Aye", "Ayla", "Aya"]               # segment order, one card
        assert a.aliases == ["the clerk", "the gray woman"]    # case-insensitive dedupe
        assert reg.places == [("place:x", "place:y")]
        assert reg.attributes == {"reactor_count": "reactors"}
        # first segment's timeline pins; later anchors only add (no overwrite)
        assert reg.timeline.origin == "Day 0 = one"
        assert reg.timeline.anchors == {"start": 0.0, "later": 3.0}
        assert (p.run_dir / "registry.json").exists()

    def test_each_segment_has_no_prior(self, tmp_path):
        calls: list[str] = []
        Pipeline(seg_model(calls), WID, tmp_path / "run").pass0(segments=SEGS, parallel=True)
        assert len(calls) == 3
        assert not any("EXTENDING an existing registry" in c for c in calls)

    def test_reduce_order_independent_of_completion_order(self, tmp_path):
        gate = threading.Event()

        def model(prompt, schema):
            if "chapter one" in prompt:
                gate.wait(5)                                   # segment 1 finishes last
            else:
                gate.set() if "chapter three" in prompt else None
            return seg_model()(prompt, schema)

        reg = Pipeline(model, WID, tmp_path / "run", max_workers=3).pass0(
            segments=SEGS, parallel=True)
        assert reg.timeline.origin == "Day 0 = one"
        assert list(reg.entities)[:2] == ["person:a", "place:x"]

    def test_prior_is_extended_in_place(self, tmp_path):
        prior = WorldRegistry(world_id=WID, entities={"obj:z": EntityCard(kind="obj")})
        reg = Pipeline(seg_model(), WID, tmp_path / "run").pass0(
            segments=SEGS, prior=prior, parallel=True)
        assert reg is prior and "obj:z" in reg.entities and "person:a" in reg.entities

    def test_quota_exhausted_propagates(self, tmp_path):
        class QuotaExhausted(RuntimeError):
            pass

        def model(prompt, schema):
            if "chapter two" in prompt:
                raise QuotaExhausted("limit")
            return {"lines": []}

        with pytest.raises(QuotaExhausted):
            Pipeline(model, WID, tmp_path / "run", max_workers=2).pass0(
                segments=SEGS, parallel=True)

    def test_timings_recorded(self, tmp_path):
        p = Pipeline(seg_model(), WID, tmp_path / "run")
        p.pass0(segments=SEGS, parallel=True)
        assert len(p.timings["pass0_segment_s"]) == 3
        assert {"pass0_wall_s", "pass0_reduce_s"} <= set(p.timings)


class TestSequentialDefault:
    def test_call_pattern_unchanged(self, tmp_path):
        calls: list[str] = []
        p = Pipeline(seg_model(calls), WID, tmp_path / "run")
        reg = p.pass0(segments=SEGS)
        assert len(calls) == 3                                  # no glean call
        assert "EXTENDING an existing registry" not in calls[0]
        assert all("EXTENDING an existing registry" in c for c in calls[1:])
        assert "E|person:a|person" in calls[1]                  # prior shown, compact
        assert reg.timeline.origin == "Day 0 = one"
        assert len(p.timings["pass0_segment_s"]) == 3
        assert "pass0_glean_s" not in p.timings

    def test_registry_matches_explicit_flags_off(self, tmp_path):
        a = Pipeline(seg_model(), WID, tmp_path / "a").pass0(segments=SEGS)
        b = Pipeline(seg_model(), WID, tmp_path / "b").pass0(
            segments=SEGS, parallel=False, glean=False)
        assert (tmp_path / "a" / "registry.json").read_text() == (
            tmp_path / "b" / "registry.json").read_text()
        assert a.entities.keys() == b.entities.keys()


class TestGlean:
    def test_glean_merges_missed_e_lines_only(self):
        reg = WorldRegistry(world_id=WID, entities={"person:a": EntityCard(
            kind="person", names=["Aye"])})
        prompts = []

        def model(prompt, schema):
            prompts.append(prompt)
            return {"lines": ["E|obj:key|obj|brass key|the key", "E|person:a|person||ayla",
                              "A|bogus|x", "O|nope", "P|place:q|place:r"]}

        out = glean("passage text", reg, model, WID)
        assert out is reg
        assert reg.entities["obj:key"].names == ["brass key"]
        assert reg.entities["person:a"].aliases == ["ayla"]
        assert not reg.attributes and not reg.places and not reg.timeline.origin
        assert len(prompts) == 1 and "E|person:a|person|Aye" in prompts[0]
        assert "passage text" in prompts[0]

    def test_pass0_glean_one_extra_call_per_segment(self, tmp_path):
        calls: list[str] = []
        base = seg_model(calls)

        def model(prompt, schema):
            if "MISSED" in prompt:
                calls.append(prompt)
                return {"lines": [f"E|obj:g{len(calls)}|obj|Gleaned"]}
            return base(prompt, schema)

        p = Pipeline(model, WID, tmp_path / "run")
        reg = p.pass0(segments=SEGS, glean=True)
        gleaned = [c for c in calls if "MISSED" in c]
        assert len(gleaned) == 3
        assert sum(1 for e in reg.entities if e.startswith("obj:g")) == 3
        assert len(p.timings["pass0_glean_s"]) == 3

    def test_parallel_glean_shows_only_own_segment_registry(self, tmp_path):
        seen = []

        def model(prompt, schema):
            if "MISSED" in prompt:
                seen.append(prompt)
                return {"lines": []}
            return seg_model()(prompt, schema)

        reg = Pipeline(model, WID, tmp_path / "run").pass0(
            segments=SEGS, parallel=True, glean=True)
        assert len(seen) == 3
        two = next(c for c in seen if "chapter two" in c)
        assert "person:b" not in two and "place:y" in two
        assert "person:b" in reg.entities

    def test_world_mismatch(self):
        from registry import RegistryWorldMismatch
        with pytest.raises(RegistryWorldMismatch):
            glean("t", WorldRegistry(world_id="w:other"), lambda p, s: {"lines": []}, WID)


class TestCommitTimings:
    def test_keys_present(self, tmp_path):
        p = Pipeline(lambda prompt, schema: {"lines": []}, WID, tmp_path / "run")
        reg = WorldRegistry(world_id=WID, entities={"person:a": EntityCard(
            kind="person", names=["Aye"])})
        w = p.commit(tmp_path / "run" / "x.world", reg)
        try:
            for key in ("commit_seed_s", "commit_replay_s", "commit_classify_all_s",
                        "commit_promotion_s", "commit_truth_scan_s"):
                assert isinstance(p.timings[key], float) and p.timings[key] >= 0
        finally:
            w.close()


class TestRunner:
    def test_arg_defaults_and_options(self):
        import run_chapter_test_v2 as r
        a = r.parse_args([])
        assert (a.out, a.pass0, a.glean) == (None, "sequential", False)
        b = r.parse_args(["--out", "d", "--pass0", "parallel", "--glean"])
        assert (b.out, b.pass0, b.glean) == ("d", "parallel", True)
        with pytest.raises(SystemExit):
            r.parse_args(["--pass0", "bogus"])

    def test_registry_reports_named_apart_from_battery_scorecard(self, tmp_path):
        import run_chapter_test_v2 as r
        reg = WorldRegistry(world_id=r.WORLD_ID, entities={"person:a": EntityCard(
            kind="person", names=["Aye"], aliases=["the clerk"])})
        out = r.write_registry_reports(reg, ["## Chapter 1\nthe clerk"], tmp_path)
        names = {p.name for p in tmp_path.iterdir()}
        assert {"registry_scorecard.md", "registry_scorecard.json",
                "registry_scorecard_seeded.md", "registry_scorecard_seeded.json",
                "alias_index.json", "alias_index.md"} <= names
        assert "scorecard.md" not in names and "scorecard.json" not in names
        assert set(out) == {"raw_b3_f1", "seeded_b3_f1", "raw_fusion", "seeded_fusion"}

    def test_write_json_roundtrip(self, tmp_path):
        import run_chapter_test_v2 as r
        r.write_json(tmp_path / "t.json", {"b": 1, "a": [1.5]})
        assert json.loads((tmp_path / "t.json").read_text()) == {"a": [1.5], "b": 1}
