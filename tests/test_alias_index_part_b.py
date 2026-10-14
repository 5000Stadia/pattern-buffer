"""ALIAS-INDEX-V1 Part B: the commit writes the host's `distinct_from` for strong
non-person distinctness pairs, from a durable source. Hand-made registries and
scripted models; the pass mark (spec items 1-4) reads the stored registries."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "evals" / "harness"))

from patternbuffer import World
from patternbuffer.dump import dump
from patternbuffer.testing import rule_classifier_fallback

import alias_index as ai
from grade_registry import grade, part_b_effect, seeded_registry
from pipeline import (ALIAS_INDEX_FILE, SOURCE_SEGMENTS_FILE, Pipeline, canonical_sha256,
                      finalize_identity, read_source_segments, seed_world,
                      write_source_segments)
from registry import EntityCard, TimelineSpec, WorldRegistry

WID = "w:partb"
SEGS = ["## Chapter 1\nThe Records Vault held the ledgers.\n\nThe Seed Vault held the seeds."]
RESULTS = ROOT / "evals" / "results"


def vault_registry() -> WorldRegistry:
    return WorldRegistry(
        world_id=WID,
        entities={
            "place:records_vault": EntityCard(kind="room", names=["Records Vault"],
                                              aliases=["the vault"]),
            "place:seed_vault": EntityCard(kind="room", names=["Seed Vault"],
                                           aliases=["the vault"]),
            "place:vault": EntityCard(kind="room", names=["the vault"]),
            "person:ilsa_renn": EntityCard(kind="person", names=["Ilsa Renn"], aliases=["renn"]),
            "person:tin_ear_clerk": EntityCard(kind="person", names=["the clerk"],
                                               aliases=["ilsa renn"]),
        },
        attributes={"in": "in"},
        timeline=TimelineSpec(origin="Day 0"),
    )


def pseudonym_registry() -> WorldRegistry:
    """Two person cards, different proper names, one shared alias: possibly one
    person under a false name (the disguise and the reveal)."""
    return WorldRegistry(
        world_id=WID,
        entities={
            "person:sela_voss": EntityCard(kind="person", names=["Sela Voss"],
                                           aliases=["the steward"]),
            "person:tovan_voss": EntityCard(kind="person", names=["Tovan Voss"],
                                            aliases=["the steward"]),
        },
        timeline=TimelineSpec(origin="Day 0"),
    )


def stub(prompt, schema):
    return rule_classifier_fallback()(prompt, schema)


def pipeline(tmp_path, name="run", **kw) -> Pipeline:
    return Pipeline(stub, WID, tmp_path / name, max_workers=1, **kw)


def distinct_rows(w: World) -> list:
    return [r for r in w.buffer.all_rows() if r.attribute == "distinct_from"]


def alias_json(p: Pipeline) -> dict:
    return json.loads((p.run_dir / ALIAS_INDEX_FILE).read_text())


# ----------------------------------------------------------------- the write


def test_vault_pair_gets_distinct_from_and_is_recorded(tmp_path):
    p = pipeline(tmp_path)
    w = p.commit(tmp_path / "a.world", vault_registry(), segments=SEGS)
    rows = distinct_rows(w)
    assert len(rows) == 1
    assert {rows[0].entity, rows[0].value} == {"place:records_vault", "place:seed_vault"}
    assert w.registry.resolve("place:records_vault") != w.registry.resolve("place:seed_vault")
    rep = alias_json(p)
    assert rep["part_b"] == "applied" and rep["source"] == "explicit"
    (entry,) = rep["written"]
    assert entry["ids"] == ["place:records_vault", "place:seed_vault"]
    assert entry["outcome"] == "rejected"
    assert "different proper names" in entry["evidence"]
    assert rep["segments_sha256"] == canonical_sha256(SEGS)
    # the Ilsa pair is a merge candidate and stays report-only: no distinct_from for it
    assert any({m["holder"], m["named"]} == {"person:ilsa_renn", "person:tin_ear_clerk"}
               for m in rep["merge_candidates"])
    w.close()


def test_strong_pair_is_seeded_before_any_replay_row(tmp_path):
    """The pass runs right after the seed: its row precedes pass-1's rows."""
    lines = {0: ["place:vault|reactor_count|2|vf=1"]}

    def model(prompt, schema):
        if "PASSAGE (chunk" in prompt:
            return {"lines": lines[0]}
        return stub(prompt, schema)

    p = Pipeline(model, WID, tmp_path / "run", max_workers=1)
    reg = vault_registry()
    p.pass1([(1.0, "text")], reg)
    w = p.commit(tmp_path / "o.world", reg, segments=SEGS)
    pos = {r.id: i for i, r in enumerate(w.buffer.all_rows())}  # log order
    rows = list(w.buffer.all_rows())
    d = pos[next(r.id for r in rows if r.attribute == "distinct_from")]
    first_replay = pos[next(r.id for r in rows if r.attribute == "reactor_count")]
    last_seed = max(pos[r.id] for r in rows
                    if r.attribute in ("kind", "name") and r.entity in reg.entities)
    assert last_seed < d < first_replay
    w.close()


def test_conflict_outcome_writes_nothing_and_never_retracts(tmp_path):
    reg = vault_registry()
    w = World(tmp_path / "c.world", world_id=WID, model=stub)
    w.ingestor.classify_inline = False
    seed_world(w, reg)
    w.porcelain.merge("place:records_vault", "place:seed_vault", "test merge")
    before = w.buffer.head()
    report = ai.build_report(reg, SEGS)
    acted = ai.apply_distinctness(w, reg, report)
    (entry,) = acted["written"]
    assert entry["outcome"] == "conflict_already_merged"
    assert w.buffer.head() == before
    assert w.registry.resolve("place:records_vault") == w.registry.resolve("place:seed_vault")
    w.close()


# ------------------------------------------------- 5: persons are report-only


def test_pseudonym_pair_gets_no_row_and_correlate_still_succeeds(tmp_path):
    reg = pseudonym_registry()
    report = ai.build_report(reg, ["Sela Voss spoke. The steward left."])
    strong = [p for p in report["distinctness_evidence"] if p["strength"] == "strong"]
    assert [p["ids"] for p in strong] == [["person:sela_voss", "person:tovan_voss"]]  # not vacuous
    p = pipeline(tmp_path)
    w = p.commit(tmp_path / "p.world", reg, segments=["Sela Voss spoke. The steward left."])
    assert distinct_rows(w) == []
    rep = alias_json(p)
    assert rep["written"] == []
    assert [(x["ids"], x["reason"]) for x in rep["report_only"]] == [
        (["person:sela_voss", "person:tovan_voss"], "person")]
    receipt = w.porcelain.correlate("person:sela_voss", "person:tovan_voss",
                                    "the steward was Sela all along")
    assert receipt["outcome"] == "correlated"
    w.close()


@pytest.mark.parametrize("a_id, a_kind, b_id, b_kind, why", [
    ("obj:sela", "person", "obj:tovan", "room", "person_card_kind"),   # card kind alone
    ("obj:sela", "room", "obj:tovan", "room", None),                   # control: neither
])
def test_person_by_card_kind(tmp_path, a_id, a_kind, b_id, b_kind, why):
    reg = WorldRegistry(world_id=WID, entities={
        a_id: EntityCard(kind=a_kind, names=["Sela Voss"], aliases=["the steward"]),
        b_id: EntityCard(kind=b_kind, names=["Tovan Marsh"], aliases=["the steward"]),
    })
    w = World(tmp_path / "k.world", world_id=WID, model=stub)
    w.ingestor.classify_inline = False
    seed_world(w, reg)
    acted = ai.apply_distinctness(w, reg, ai.build_report(reg, ["x"]))
    if why:
        assert acted["written"] == []
        assert acted["report_only"][0]["detail"] == {a_id: why}
    else:
        assert [e["outcome"] for e in acted["written"]] == ["rejected"]
    w.close()


def test_person_by_folded_canon_kind(tmp_path):
    """A card that says `room` whose canon `kind` folds to `person` after seeding."""
    reg = WorldRegistry(world_id=WID, entities={
        "obj:sela": EntityCard(kind="room", names=["Sela Voss"], aliases=["the steward"]),
        "obj:tovan": EntityCard(kind="room", names=["Tovan Marsh"], aliases=["the steward"]),
    })
    w = World(tmp_path / "f.world", world_id=WID, model=stub)
    w.ingestor.classify_inline = False
    seed_world(w, reg)
    w.ingest_structured([{"entity": "obj:sela", "attribute": "kind", "value": "person",
                          "value_type": "literal", "valid_from": 5.0}])  # a later kind row wins the fold
    # SESSION-GUARDRAILS-V1: the deferred `kind` rows are now classified at ingest
    # (CONSTITUTIVE, a guardrail). This test reads the fold with them unclassified
    # (STATE, "a later kind row wins"), so restore that reading explicitly.
    for r in w.buffer.visible(entity="obj:sela", attribute="kind"):
        w.classifier.set(r.id, "STATE")
    assert w.state("obj:sela", "kind").winner.value == "person"
    acted = ai.apply_distinctness(w, reg, ai.build_report(reg, ["x"]))
    assert acted["written"] == []
    assert acted["report_only"][0]["detail"] == {"obj:sela": "person_folded_kind"}
    w.close()


# ---------------------------------------------- 6: the flag and old callers


def test_flag_off_is_todays_commit_exactly(tmp_path):
    off = pipeline(tmp_path, "off", alias_distinct=False)
    w_off = off.commit(tmp_path / "off.world", vault_registry(), segments=SEGS)
    assert not (off.run_dir / ALIAS_INDEX_FILE).exists()  # nothing read, nothing written
    assert distinct_rows(w_off) == []
    dump_off = dump(w_off.buffer)
    w_off.close()

    # No source: the pass is skipped, and the log is the same bytes as with the flag off.
    skip = pipeline(tmp_path, "skip")
    w_skip = skip.commit(tmp_path / "skip.world", vault_registry())
    assert dump(w_skip.buffer) == dump_off
    w_skip.close()

    # A source with nothing strong to write: also the same bytes.
    none = pipeline(tmp_path, "none")
    reg = WorldRegistry(world_id=WID, entities={
        "person:ada": EntityCard(kind="person", names=["Ada Lin"])})
    w_a = none.commit(tmp_path / "n1.world", reg, segments=["Ada Lin walked."])
    w_b = pipeline(tmp_path, "none2", alias_distinct=False).commit(tmp_path / "n2.world", reg)
    assert dump(w_a.buffer) == dump(w_b.buffer)
    w_a.close(); w_b.close()


def test_flag_off_ignores_a_tampered_source(tmp_path):
    p = pipeline(tmp_path, alias_distinct=False)
    write_source_segments(p.run_dir, SEGS)
    (p.run_dir / SOURCE_SEGMENTS_FILE).write_text("not json")
    w = p.commit(tmp_path / "t.world", vault_registry())
    assert distinct_rows(w) == []
    w.close()


def test_no_source_skips_with_a_warning_and_a_skipped_report(tmp_path, caplog):
    p = pipeline(tmp_path)
    with caplog.at_level("WARNING"):
        w = p.commit(tmp_path / "s.world", vault_registry())
    assert "Part B skipped" in caplog.text
    assert distinct_rows(w) == []
    assert alias_json(p) == {"part_b": "skipped", "reason": "no_source"}
    w.close()


# ------------------------------------- 7: durable source, determinism, tamper


def scripted_pass0(prompt, schema):
    if "PASSAGE (chunk" in prompt:
        return {"lines": ["place:records_vault|reactor_count|2|vf=1"]}
    if "WORLD REGISTRY" in prompt or "EXTENDING an existing registry" in prompt:
        return {"lines": ["E|place:records_vault|room|Records Vault|the vault",
                          "E|place:seed_vault|room|Seed Vault|the vault",
                          "E|person:ada|person|Ada Lin|the clerk",
                          "O|Day 0 = the start"]}
    return stub(prompt, schema)


def staged_run(tmp_path) -> tuple[Pipeline, WorldRegistry]:
    p = Pipeline(scripted_pass0, WID, tmp_path / "run", max_workers=1)
    reg = p.pass0(segments=list(SEGS))
    p.pass1([(1.0, SEGS[0])], reg)
    return p, reg


def test_pass0_writes_the_source_with_its_sha(tmp_path):
    p, _ = staged_run(tmp_path)
    data = json.loads((p.run_dir / SOURCE_SEGMENTS_FILE).read_text())
    assert data["segments"] == SEGS
    blob = json.dumps(SEGS, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert data["sha256"] == hashlib.sha256(blob.encode()).hexdigest()
    assert read_source_segments(p.run_dir / SOURCE_SEGMENTS_FILE) == SEGS
    q = Pipeline(scripted_pass0, WID, tmp_path / "run2")
    q.pass0(text="one text")  # a single text is the one part
    assert json.loads((q.run_dir / SOURCE_SEGMENTS_FILE).read_text())["segments"] == ["one text"]


def test_fresh_pipeline_reproduces_the_commit_byte_for_byte(tmp_path):
    p, reg = staged_run(tmp_path)
    w1 = p.commit(tmp_path / "one.world", reg)
    dump1, rep1 = dump(w1.buffer), (p.run_dir / ALIAS_INDEX_FILE).read_bytes()
    assert distinct_rows(w1) and json.loads(rep1)["source"] == "file"
    w1.close()

    fresh = Pipeline(stub, WID, p.run_dir, max_workers=1)  # nothing in memory
    reg2 = WorldRegistry.load(p.run_dir / "registry.json", WID)
    w2 = fresh.commit(tmp_path / "two.world", reg2)
    assert dump(w2.buffer) == dump1
    assert (fresh.run_dir / ALIAS_INDEX_FILE).read_bytes() == rep1
    w2.close()


def test_tampered_source_raises_before_anything_is_written(tmp_path):
    p, reg = staged_run(tmp_path)
    path = p.run_dir / SOURCE_SEGMENTS_FILE
    data = json.loads(path.read_text())
    data["segments"][0] += " tampered"
    path.write_text(json.dumps(data))
    reg_before = (p.run_dir / "registry.json").read_bytes()
    (p.run_dir / ALIAS_INDEX_FILE).unlink(missing_ok=True)
    target = tmp_path / "t.world"
    with pytest.raises(ValueError, match="sha256"):
        p.commit(target, reg)
    assert not target.exists()
    assert not (p.run_dir / ALIAS_INDEX_FILE).exists()
    assert (p.run_dir / "registry.json").read_bytes() == reg_before
    for bad in ("{", json.dumps({"segments": "x", "sha256": "y"}), json.dumps({})):
        path.write_text(bad)
        with pytest.raises(ValueError):
            p.commit(target, reg)
        assert not target.exists()
    # an explicit segments argument is the first choice and needs no file at all
    w = p.commit(target, reg, segments=SEGS)
    assert alias_json(p)["source"] == "explicit"
    w.close()


def test_repaired_registry_is_the_registry_the_report_reads(tmp_path):
    state = {"repaired": False}

    def model(prompt, schema):
        if "PASSAGE (chunk" in prompt:
            return {"lines": ["obj:unknown_thing|in|@place:seed_vault|vf=1"]}
        if "WORLD REGISTRY" in prompt or "EXTENDING an existing registry" in prompt:
            if "unknown_thing" in prompt or state["repaired"]:
                state["repaired"] = True
                return {"lines": ["E|obj:unknown_thing|object|Odd Thing"]}
            return scripted_pass0(prompt, schema)
        return stub(prompt, schema)

    p = Pipeline(model, WID, tmp_path / "run", max_workers=1)
    reg = p.pass0(segments=list(SEGS))
    results = p.pass1([(1.0, SEGS[0])], reg)
    state["repaired"] = True
    results, escapes = p.repair_escapes(results, reg, [(1.0, SEGS[0])])
    assert escapes == 1 and "obj:unknown_thing" in reg.entities
    w = p.commit(tmp_path / "r.world", reg)
    rep = alias_json(p)
    saved = json.loads((p.run_dir / "registry.json").read_text())
    assert rep["registry_sha256"] == canonical_sha256(saved)
    assert "obj:unknown_thing" in saved["entities"]
    assert "obj:unknown_thing" in rep["index"].get("odd thing", [])  # the report read the repaired one
    w.close()


# ------------------------------------- 4b, 6: the modes, through a real commit


def chunk_model(prompt, schema):
    if "PASSAGE (chunk" in prompt:
        return {"lines": ["place:records_vault|reactor_count|2|vf=1"]}
    return stub(prompt, schema)


def commit_mode(tmp_path, name, *, with_source, **flags) -> World:
    """A fixture run_dir with one staged chunk, committed by a fresh Pipeline
    through the real ``Pipeline.commit`` under ``flags``."""
    staged = Pipeline(chunk_model, WID, tmp_path / name, max_workers=1)
    reg = vault_registry()
    staged.pass1([(1.0, "text")], reg)
    if with_source:
        write_source_segments(staged.run_dir, SEGS)
    p = Pipeline(stub, WID, staged.run_dir, max_workers=1, **flags)
    return p.commit(tmp_path / f"{name}.world", reg)


def legacy_dump(tmp_path) -> str:
    """Today's commit (before ALIAS-INDEX-V1), spelled out from engine calls:
    seed, replay the staged items, classify, promote, confirm owners, scan."""
    staged = Pipeline(chunk_model, WID, tmp_path / "legacy", max_workers=1)
    reg = vault_registry()
    staged.pass1([(1.0, "text")], reg)
    w = World(tmp_path / "legacy.world", world_id=WID, model=stub)
    w.ingestor.classify_inline = False
    seed_world(w, reg)
    for r in staged.load_staged():
        for item in r.items:
            w.ingest_structured([item])
    w.classifier.classify_all(batch_size=40)
    w.registry.promote_identity_proposals()
    Pipeline.confirm_frame_owners(w)
    w.truth.scan()
    out = dump(w.buffer)
    w.close()
    return out


def vaults_one(w: World) -> bool:
    return w.registry.resolve("place:records_vault") == w.registry.resolve("place:seed_vault")


def test_the_five_modes_through_a_real_commit(tmp_path):
    today = legacy_dump(tmp_path)
    modes = {
        "default_with_source": dict(with_source=True),
        "default_no_source": dict(with_source=False),
        "auto_no_part_b": dict(with_source=True, alias_distinct=False),          # ("auto", False)
        "reconcile_only": dict(with_source=True, alias_distinct=False, reconcile=True),
        "both_off": dict(with_source=True, alias_distinct=False, reconcile=False),
    }
    worlds = {name: commit_mode(tmp_path, name, **kw) for name, kw in modes.items()}
    dumps = {name: dump(w.buffer) for name, w in worlds.items()}
    # the vault-style fusion appears only where reconcile runs without Part B
    assert {n: vaults_one(w) for n, w in worlds.items()} == {
        "default_with_source": False, "default_no_source": False, "auto_no_part_b": False,
        "reconcile_only": True, "both_off": False}
    # the default (Part B, then reconcile) reconciles, keeps the vaults apart, and writes the row
    assert distinct_rows(worlds["default_with_source"])
    assert worlds["default_with_source"].registry.resolve("person:tin_ear_clerk") == \
        worlds["default_with_source"].registry.resolve("person:ilsa_renn")  # reconcile merged Ilsa
    assert dumps["default_with_source"] != today
    # the three legacy modes are today's commit, byte for byte
    for name in ("default_no_source", "auto_no_part_b", "both_off"):
        assert dumps[name] == today, name
        assert distinct_rows(worlds[name]) == []
    assert dumps["reconcile_only"] != today
    # no source: skipped report, and nothing reconciled
    rep = json.loads((tmp_path / "default_no_source" / ALIAS_INDEX_FILE).read_text())
    assert rep == {"part_b": "skipped", "reason": "no_source"}
    assert json.loads((tmp_path / "default_with_source" / ALIAS_INDEX_FILE).read_text()
                      )["reconcile"] is True
    for w in worlds.values():
        w.close()


def test_forced_reconcile_runs_even_without_a_source(tmp_path):
    w = commit_mode(tmp_path, "forced", with_source=False, reconcile=True)
    assert vaults_one(w)  # reconcile without Part B: the measured fusion
    w.close()
    w = commit_mode(tmp_path, "forced_off", with_source=True, reconcile=False)
    assert distinct_rows(w) and not vaults_one(w)  # Part B writes its row, nothing reconciles
    w.close()


def test_reconcile_knob_is_validated(tmp_path):
    for bad in ("yes", 1, None, "AUTO"):
        with pytest.raises(ValueError, match="reconcile"):
            Pipeline(stub, WID, tmp_path / "v", reconcile=bad)


def test_finalize_identity_is_the_shared_finalization(tmp_path):
    """promote, then reconcile only when asked, then confirm owners."""
    reg = vault_registry()
    for flag, fused in ((False, False), (True, True)):
        w = World(tmp_path / f"fi{flag}.world", world_id=WID, model=stub)
        w.ingestor.classify_inline = False
        seed_world(w, reg)
        finalize_identity(w, reconcile=flag)
        assert vaults_one(w) is fused
        w.close()


# ---------------------------------------- 7: an empty source is not a source


def test_empty_source_raises_before_any_write(tmp_path):
    p, reg = staged_run(tmp_path)
    path = p.run_dir / SOURCE_SEGMENTS_FILE
    reg_before = (p.run_dir / "registry.json").read_bytes()
    (p.run_dir / ALIAS_INDEX_FILE).unlink(missing_ok=True)
    target = tmp_path / "e.world"
    # a file holding [] with a matching digest
    path.write_text(json.dumps({"segments": [], "sha256": canonical_sha256([])}))
    with pytest.raises(ValueError, match="empty"):
        p.commit(target, reg)
    # an explicit segments=[] (the file now valid again)
    write_source_segments(p.run_dir, SEGS)
    with pytest.raises(ValueError, match="empty"):
        p.commit(target, reg, segments=[])
    assert not target.exists()
    assert not (p.run_dir / ALIAS_INDEX_FILE).exists()
    assert (p.run_dir / "registry.json").read_bytes() == reg_before
    with pytest.raises(ValueError, match="empty"):
        read_source_segments(_write_raw(tmp_path, {"segments": [], "sha256": canonical_sha256([])}))
    with pytest.raises(ValueError, match="empty"):
        seeded_registry(STORED["r23-run1"] / "registry.json", segments=[])
    # pbr code r2: an explicit source is a non-empty list of strings, checked
    # before anything is written (a bare string is not read as its characters)
    for bad in ("one whole chapter as a bare string", ["a segment", 7], ("a", "tuple")):
        with pytest.raises(ValueError, match="list of strings"):
            p.commit(target, reg, segments=bad)
        assert not target.exists()
        assert not (p.run_dir / ALIAS_INDEX_FILE).exists()
        assert (p.run_dir / "registry.json").read_bytes() == reg_before
        with pytest.raises(ValueError, match="list of strings"):
            seeded_registry(STORED["r23-run1"] / "registry.json", segments=bad)


def _write_raw(tmp_path, payload) -> Path:
    path = tmp_path / "raw_source.json"
    path.write_text(json.dumps(payload))
    return path


# --------------- 1-4a: the pass mark, on the five stored registries (3 columns)

STORED = {
    "r23-run1": RESULTS / "2026-10-10-r23-pass0-baseline" / "run1",
    "r23-run2": RESULTS / "2026-10-10-r23-pass0-baseline" / "run2",
    "r26-seq": RESULTS / "2026-10-10-r26-build-timings" / "seq",
    "r26-par1b": RESULTS / "2026-10-10-r26-build-timings" / "par1b",
    "r26-par2b": RESULTS / "2026-10-10-r26-build-timings" / "par2b",
}
#: (B3 F1, fused, fragmented) per column, as measured on the shared path.
EXPECTED = {
    "r23-run1": {"today": (0.7517, 0, 1), "reconcile": (0.7471, 1, 0), "default": (0.7517, 0, 0)},
    "r23-run2": {"today": (0.7347, 0, 1), "reconcile": (0.7303, 1, 0), "default": (0.7347, 0, 0)},
    "r26-seq": {"today": (0.7517, 0, 0), "reconcile": (0.7517, 0, 0), "default": (0.7517, 0, 0)},
    # r26-par1b reconcile/default fragmented 4 -> 5 (SESSION-GUARDRAILS-V1: guardrail
    # `kind` rows are now classified at the deferred call, so one reconcile merge
    # (23 -> 22) is blocked as in a classified world; classify_all gives the same
    # numbers; the old 4 measured a never-classified, all-STATE world).
    "r26-par1b": {"today": (0.8320, 0, 13), "reconcile": (0.8264, 1, 5),
                  "default": (0.8320, 0, 5)},
    "r26-par2b": {"today": (0.7961, 0, 13), "reconcile": (0.7910, 1, 7),
                  "default": (0.7961, 0, 7)},
}
ILSA = "person:tin_ear_clerk + person:ilsa_renn"


@pytest.fixture(scope="module")
def story_segments() -> list[str]:
    import run_pass0_baseline
    return run_pass0_baseline.story_segments()


@pytest.fixture(scope="module")
def effects(story_segments) -> dict[str, dict]:
    return {name: part_b_effect(d / "registry.json", story_segments) for name, d in STORED.items()}


@pytest.mark.parametrize("name", sorted(STORED))
def test_pass_mark_1_to_4a_on_stored_registries(effects, name):
    e = effects[name]
    today, rec, default = e["today"], e["reconcile"], e["default"]
    for col, got in (("today", today), ("reconcile", rec), ("default", default)):
        f1, fused, frag = EXPECTED[name][col]
        assert (got["fusion_count"], got["fragmentation_count"]) == (fused, frag), col
        assert got["b3_f1"] == pytest.approx(f1, abs=1e-4), col
    # 1: fused ids 0 on the default commit path
    assert default["fusion_count"] == 0
    # 3: no new fusion, no new fragmentation (subsets of the unfixed reconcile column's, and today's)
    assert set(default["fusion"]) <= set(rec["fusion"])
    assert set(default["fragmentation"]) <= set(today["fragmentation"])
    assert set(default["fragmentation"]) <= set(rec["fragmentation"])
    # 4: F1 not lower than today's commit (measured equal)
    assert default["b3_f1"] >= today["b3_f1"]
    assert default["b3_f1"] == pytest.approx(today["b3_f1"], abs=1e-4)
    # 4a: fragmentation not higher than today's, lower where reconcile merges
    assert default["fragmentation_count"] <= today["fragmentation_count"]
    if name != "r26-seq":
        assert default["fragmentation_count"] < today["fragmentation_count"]
    # reconcile alone is what fuses the vaults
    assert rec["fusion_count"] == (0 if name == "r26-seq" else 1)


@pytest.mark.parametrize("name", ["r23-run1", "r23-run2"])
def test_pass_mark_2_ilsa_pair_is_merged(effects, name):
    e = effects[name]
    assert ILSA not in e["today"]["merge_candidates_merged"]  # commit today never merges it
    assert ILSA in e["reconcile"]["merge_candidates_merged"]
    assert ILSA in e["default"]["merge_candidates_merged"]


@pytest.mark.parametrize("name", sorted(STORED))
def test_the_only_writes_are_the_vault_split_and_persons_stay_report_only(effects, name):
    e = effects[name]
    for w in e["written"]:
        assert w["outcome"] == "rejected"
        assert w["ids"] == ["place:records_vault", "place:seed_vault"]
    assert len(e["written"]) == (0 if name == "r26-seq" else 1)
    for r in e["report_only"]:
        assert r["reason"] == "person"
    if name == "r26-par1b":
        assert sorted(r["ids"] for r in e["report_only"]) == [
            ["person:cray", "person:marn"], ["person:sela_voss", "person:tovan_voss"]]


def test_seeded_registry_default_is_todays_commit_without_a_source(story_segments):
    """The grader's knobs mirror the Pipeline's: no segments, no reconcile."""
    reg = STORED["r23-run1"] / "registry.json"
    no_src = seeded_registry(reg)
    assert "alias_report" not in no_src
    assert no_src == seeded_registry(reg, alias_distinct=False, reconcile=False)
    assert grade(no_src)["fragmentation_count"] == 1  # the Ilsa split, unreconciled
    default = seeded_registry(reg, segments=story_segments)
    assert default["alias_report"]["part_b"] == "applied"
    assert grade(default)["fusion_count"] == 0
    assert grade(seeded_registry(reg, segments=story_segments, alias_distinct=False,
                                 reconcile=True))["fusion_count"] == 1
    with pytest.raises(ValueError, match="reconcile"):
        seeded_registry(reg, reconcile="maybe")
