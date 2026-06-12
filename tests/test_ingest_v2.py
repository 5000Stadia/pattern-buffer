"""INGEST-V2 pipeline invariants (spec §7) — no model, all scripted."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "evals" / "harness"))

from patternbuffer import World
from patternbuffer.dump import dump
from patternbuffer.testing import StubModel, rule_classifier_fallback

import grammar
from audit import build_digest, run_audit
from pipeline import Pipeline
from registry import (
    EntityCard,
    RegistryWorldMismatch,
    TimelineSpec,
    WorldRegistry,
    seed_items,
)

WID = "w:test"


def make_registry() -> WorldRegistry:
    return WorldRegistry(
        world_id=WID,
        entities={
            "person:ilsa": EntityCard(kind="person", names=["Ilsa Renn"],
                                      aliases=["the clerk", "ilsa renn"]),
            "obj:core": EntityCard(kind="memory_core", names=["memory core"]),
            "place:vault": EntityCard(kind="room", names=["Seed Vault"]),
            "place:office": EntityCard(kind="room", names=["Allocation Office"]),
            "event:theft": EntityCard(kind="event", names=["the theft"]),
        },
        attributes={"reactor_count": "working_reactors",
                    "reactors_operational": "working_reactors"},
        timeline=TimelineSpec(origin="Day 0 = the night of the theft",
                              anchors={"assembly": 4.0}),
        places=[("place:office", "place:vault")],
    )


PASS1_LINES = {
    0: ["obj:core|in|@place:vault|vf=4,s=stated",
        "person:ilsa|role|clerk|t"],
    1: ["obj:core|in|@person:ilsa|vf=0,s=stated",
        "place:office|reactor_count|2|vf=1"],
}


def scripted_pipeline(tmp_path, lines_by_chunk):
    """A pipeline whose model returns scripted pass-1 lines per chunk."""
    calls = []

    def model(prompt, schema):
        calls.append(prompt)
        if "PASSAGE (chunk" in prompt:
            chunk_id = int(prompt.split("PASSAGE (chunk ")[1].split(")")[0])
            return {"lines": lines_by_chunk[chunk_id]}
        return rule_classifier_fallback()(prompt, schema)

    p = Pipeline(model, WID, tmp_path / "run", max_workers=2)
    return p, calls


CHUNKS = [(3.0, "scene one text"), (7.0, "scene two text")]


class TestRegistry:
    def test_world_partitioning(self, tmp_path):
        r = make_registry()
        r.save(tmp_path / "registry.json")
        with pytest.raises(RegistryWorldMismatch):
            WorldRegistry.load(tmp_path / "registry.json", expect_world_id="w:other")
        loaded = WorldRegistry.load(tmp_path / "registry.json", expect_world_id=WID)
        assert loaded.entities.keys() == r.entities.keys()
        assert loaded.places == r.places

    def test_merge_accretes_never_overwrites(self):
        a, b = make_registry(), make_registry()
        b.entities["person:ilsa"].kind = "imposter"  # conflicting later judgment
        b.entities["person:new"] = EntityCard(kind="person")
        b.attributes["reactors"] = "working_reactors"
        a.merge(b)
        assert a.entities["person:ilsa"].kind == "person"  # pinned
        assert "person:new" in a.entities
        assert a.attributes["reactors"] == "working_reactors"

    def test_seed_items_shape(self):
        items = seed_items(make_registry())
        kinds = [i for i in items if i["attribute"] == "kind"]
        assert all(i["timeless"] for i in items)
        assert any("aliases" in i for i in kinds)  # alias attachment rides kind
        assert any(i["attribute"] == "connects_to" for i in items)


class TestPipeline:
    def test_stage_all_commit_once_deterministic(self, tmp_path):
        p, _ = scripted_pipeline(tmp_path, PASS1_LINES)
        reg = make_registry()
        results = p.pass1(CHUNKS, reg)
        assert all(not r.failed and not r.orphans for r in results)
        w = p.commit(tmp_path / "a.world", reg)
        first = dump(w.buffer)
        w.close()

        # Same staged inputs, second commit target: byte-identical dump.
        p2, _ = scripted_pipeline(tmp_path, PASS1_LINES)
        p2.staging = p.staging  # same staged chunks
        w2 = p2.commit(tmp_path / "b.world", reg)
        assert dump(w2.buffer) == first
        w2.close()

    def test_failed_chunk_commits_nothing(self, tmp_path):
        def model(prompt, schema):
            if "PASSAGE (chunk 1)" in prompt:
                raise RuntimeError("boom")
            if "PASSAGE (chunk" in prompt:
                return {"lines": PASS1_LINES[0]}
            return rule_classifier_fallback()(prompt, schema)

        p = Pipeline(model, WID, tmp_path / "run", max_workers=2)
        reg = make_registry()
        results = p.pass1(CHUNKS, reg)
        assert any(r.failed for r in results)
        target = tmp_path / "x.world"
        with pytest.raises(RuntimeError, match="noncanonical"):
            p.commit(target, reg)
        assert not target.exists()  # zero rows incl. registry seeds
        assert len(list(p.staging.glob("chunk_*.jsonl"))) == 2  # resumable

    def test_orphan_quarantine_and_escape_repair(self, tmp_path):
        lines = dict(PASS1_LINES)
        lines[1] = ["obj:unknown_thing|in|@place:vault|vf=1"]  # unregistered subject
        repaired = {"called": False}

        def model(prompt, schema):
            if "PASSAGE (chunk 1)" in prompt:
                if repaired["called"]:
                    return {"lines": ["obj:unknown_thing|in|@place:vault|vf=1"]}
                return {"lines": lines[1]}
            if "PASSAGE (chunk" in prompt:
                return {"lines": lines[0]}
            if "WORLD REGISTRY" in prompt or "EXTENDING an existing registry" in prompt:
                repaired["called"] = True
                return {"entities": [{"id": "obj:unknown_thing", "kind": "object"}],
                        "attributes": [], "timeline": {"origin": "Day 0", "anchors": []},
                        "places": []}
            return rule_classifier_fallback()(prompt, schema)

        p = Pipeline(model, WID, tmp_path / "run", max_workers=1)
        reg = make_registry()
        results = p.pass1(CHUNKS, reg)
        orphaned = [r for r in results if r.orphans]
        assert orphaned and not orphaned[0].items  # quarantined, not committed
        results, escapes = p.repair_escapes(results, reg, CHUNKS)
        assert escapes == 1
        assert "obj:unknown_thing" in reg.entities  # registry extended
        assert all(not r.orphans for r in results)
        w = p.commit(tmp_path / "y.world", reg)
        rows = [r for r in w.buffer.all_rows() if r.entity == "obj:unknown_thing"]
        assert any(r.attribute == "in" for r in rows)  # repaired line landed
        w.close()

    def test_staged_world_mismatch_refused(self, tmp_path):
        p, _ = scripted_pipeline(tmp_path, PASS1_LINES)
        reg = make_registry()
        p.pass1(CHUNKS[:1], reg)
        staged = next(p.staging.glob("chunk_*.jsonl"))
        lines = staged.read_text().splitlines()
        header = json.loads(lines[0])
        header["world_id"] = "w:other"
        staged.write_text("\n".join([json.dumps(header)] + lines[1:]) + "\n")
        with pytest.raises(RegistryWorldMismatch):
            p.load_staged()

    def test_staged_items_replay_complete(self, tmp_path):
        p, _ = scripted_pipeline(tmp_path, PASS1_LINES)
        reg = make_registry()
        p.pass1(CHUNKS, reg)
        for r in p.load_staged():
            for item in r.items:
                assert item.get("timeless") or item.get("valid_from") is not None


class TestAudit:
    def _committed_world(self, tmp_path):
        p, _ = scripted_pipeline(tmp_path, PASS1_LINES)
        reg = make_registry()
        p.pass1(CHUNKS, reg)
        return p.commit(tmp_path / "w.world", reg), reg

    def test_digest_shape(self, tmp_path):
        w, reg = self._committed_world(tmp_path)
        digest = build_digest(w, reg)
        assert set(digest) == {"conflicts", "unstamped", "drift", "frame_anoms", "fold_winners"}
        assert digest["frame_anoms"] == []  # parse-time validation makes this empty
        w.close()

    def test_repair_ops_routing_and_conflict_protection(self, tmp_path):
        w, reg = self._committed_world(tmp_path)
        # Plant a CONSTITUTIVE conflict to protect.
        w.ingest_structured([
            {"entity": "place:office", "attribute": "working_reactors", "value": 3,
             "timeless": True},
        ])
        w.classifier.set(
            next(r.id for r in w.buffer.all_rows()
                 if r.attribute == "working_reactors" and r.value == 2), "CONSTITUTIVE")
        w.classifier.set(
            next(r.id for r in w.buffer.all_rows()
                 if r.attribute == "working_reactors" and r.value == 3), "CONSTITUTIVE")
        w.truth.scan()
        conflicted_ids = {a for c in w.truth.open_conflicts() for a in c.assertion_ids}
        assert conflicted_ids
        victim = next(iter(conflicted_ids))
        target = next(r.id for r in w.buffer.all_rows() if r.attribute == "role")

        def model(prompt, schema):
            return {"ops": [
                f"add|obj:core|condition|sealed|vf=5",
                f"retract|{victim}|auditor overreach",     # must be dropped
                f"retract|{target}|duplicate extraction",  # must apply
                "promote|a:1|nope",                        # unknown op kind
            ]}

        report = run_audit(w, reg, model)
        assert report.applied_adds == 1
        assert report.applied_retracts == 1
        assert len(report.dropped_ops) == 2
        # The conflict survives pass-2 with both rows alive.
        assert {a for c in w.truth.open_conflicts() for a in c.assertion_ids} == conflicted_ids
        assert w.buffer.get(victim) is not None
        w.close()


class TestReviewGaps:
    """Post-impl review (RED) closure: the named test gaps."""

    def test_commit_refuses_wrong_world_registry(self, tmp_path):
        p, _ = scripted_pipeline(tmp_path, PASS1_LINES)
        reg = make_registry()
        p.pass1(CHUNKS, reg)
        from registry import RegistryWorldMismatch as RWM
        alien = make_registry()
        alien.world_id = "w:other"
        target = tmp_path / "z.world"
        with pytest.raises(RWM, match="refusing to seed"):
            p.commit(target, alien)
        assert not target.exists()

    def test_escape_repair_reparses_before_reextracting(self, tmp_path):
        """The deterministic re-parse must repair without a second
        extraction call when the extended registry covers the orphans."""
        lines = dict(PASS1_LINES)
        lines[1] = ["obj:unknown_thing|in|@place:vault|vf=1"]
        extraction_calls = {1: 0}

        def model(prompt, schema):
            if "PASSAGE (chunk 1)" in prompt:
                extraction_calls[1] += 1
                return {"lines": lines[1]}
            if "PASSAGE (chunk" in prompt:
                return {"lines": lines[0]}
            if "EXTENDING an existing registry" in prompt:
                return {"entities": [{"id": "obj:unknown_thing", "kind": "object"}],
                        "attributes": [], "timeline": {"origin": "Day 0", "anchors": []},
                        "places": []}
            return rule_classifier_fallback()(prompt, schema)

        p = Pipeline(model, WID, tmp_path / "run", max_workers=1)
        reg = make_registry()
        results = p.pass1(CHUNKS, reg)
        assert extraction_calls[1] == 1
        results, escapes = p.repair_escapes(results, reg, CHUNKS)
        assert escapes == 1
        assert extraction_calls[1] == 1  # repaired by re-parse, NO second call
        assert all(not r.orphans for r in results)

    def test_serial_parallel_byte_identical(self, tmp_path):
        dumps = []
        for workers, name in ((1, "serial"), (3, "parallel")):
            p, _ = scripted_pipeline(tmp_path / name, PASS1_LINES)
            p.max_workers = workers
            reg = make_registry()
            p.pass1(CHUNKS, reg)
            w = p.commit(tmp_path / f"{name}.world", reg)
            from patternbuffer.dump import dump as dump_fn
            dumps.append(dump_fn(w.buffer))
            w.close()
        assert dumps[0] == dumps[1]

    def test_quota_abort_leaves_staging_intact(self, tmp_path):
        class QuotaExhausted(RuntimeError):
            pass

        def model(prompt, schema):
            if "PASSAGE (chunk 1)" in prompt:
                raise QuotaExhausted("monthly limit")
            if "PASSAGE (chunk" in prompt:
                return {"lines": PASS1_LINES[0]}
            return rule_classifier_fallback()(prompt, schema)

        p = Pipeline(model, WID, tmp_path / "run", max_workers=1)
        with pytest.raises(QuotaExhausted):
            p.pass1(CHUNKS, make_registry())
        assert (p.staging / "chunk_000.jsonl").exists()  # completed work kept

    def test_variant_attribute_produces_receipt(self, tmp_path):
        p, _ = scripted_pipeline(tmp_path, PASS1_LINES)
        reg = make_registry()
        p.pass1(CHUNKS, reg)
        w = p.commit(tmp_path / "r.world", reg)
        receipts = [r for r in w.buffer.all_rows()
                    if r.attribute == "canonicalized_from"]
        assert any("reactor_count->working_reactors" == r.value for r in receipts)
        # And the fold key never fragmented:
        fold = w.state("place:office", "working_reactors")
        assert fold.winner is not None and fold.winner.value == 2
        w.close()

    def test_registry_replay_after_build(self, tmp_path):
        from patternbuffer import World
        from patternbuffer.dump import build, dump as dump_fn
        p, _ = scripted_pipeline(tmp_path, PASS1_LINES)
        reg = make_registry()
        p.pass1(CHUNKS, reg)
        w = p.commit(tmp_path / "src.world", reg)
        text = dump_fn(w.buffer)
        w.close()
        rebuilt_buf = build(text, tmp_path / "rebuilt.world")
        rebuilt_buf.close()
        loaded = WorldRegistry.load(p.run_dir / "registry.json", expect_world_id=WID)
        w2 = World(tmp_path / "rebuilt.world", world_id=WID,
                   model=rule_classifier_fallback())
        for alias, canonical in loaded.attributes.items():
            w2.ingestor.add_attribute_alias(alias, canonical)
        rows = w2.ingest_structured([
            {"entity": "place:office", "attribute": "reactors_operational",
             "value": 2, "valid_from": 9.0},
        ])
        assert rows[0].attribute == "working_reactors"  # replayed map held
        w2.close()

    def test_audit_add_without_time_dropped(self, tmp_path):
        p, _ = scripted_pipeline(tmp_path, PASS1_LINES)
        reg = make_registry()
        p.pass1(CHUNKS, reg)
        w = p.commit(tmp_path / "t.world", reg)

        def model(prompt, schema):
            return {"ops": ["add|obj:core|condition|sealed",       # no vf=/t -> dropped
                            "add|obj:core|condition|sealed|vf=5"]}  # applied

        report = run_audit(w, reg, model)
        assert report.applied_adds == 1
        assert any("no explicit time" in d for d in report.dropped_ops)
        w.close()
