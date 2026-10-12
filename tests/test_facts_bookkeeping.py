"""FACTS-BOOKKEEPING-V1: a frame scan without the engine's bookkeeping rows.

One test per check of specs/FACTS-BOOKKEEPING-V1.md (Tests 1-5, 2a).
"""

from __future__ import annotations

import pytest

from patternbuffer import World, model
from patternbuffer.mcp import dispatch
from patternbuffer.roles import _make_engine_roles
from patternbuffer.service import WorldService
from patternbuffer.testing import StubModel, rule_classifier_fallback

F = "knows:person:bea"
INGESTOR = _make_engine_roles()["ingestor"]


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path / "bk.world", world_id="w:bk",
              model=StubModel(fallback=rule_classifier_fallback()))
    w.ingest_structured([
        {"entity": "person:bea", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:ann", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "obj:lamp", "attribute": "colour", "value": "brass", "frame": F,
         "valid_from": 1.0},
        {"entity": "person:ann", "attribute": "mood", "value": "wary", "frame": F,
         "valid_from": 1.0},
        {"entity": "obj:lamp", "attribute": "durability", "value": "fragile", "frame": F,
         "valid_from": 1.0},
    ])
    for attribute, value in (("aka", "person:bea"), ("same_as", "person:bea"),
                             ("source", "doc:letter")):
        w.buffer.append(entity="person:ann", attribute=attribute, value=value,
                        value_type="entity", status="stated", role=INGESTOR, frame=F)
    yield w
    w.close()


def _attrs(facts: list[dict]) -> list[str]:
    return sorted(f["attribute"] for f in facts)


def _retract_one(w) -> None:
    (row,) = w.buffer.visible(entity="person:ann", attribute="mood", frame=F)
    w.porcelain.retract(row.id, "she was calm")


def test_1_bookkeeping_false_answers_only_world_facts_and_the_default_is_unchanged(world):
    _retract_one(world)
    p = world.porcelain
    assert p.facts(F) == p.facts(F, bookkeeping=True)
    assert {"aka", "same_as", "source"} <= set(_attrs(p.facts(F)))
    assert _attrs(p.facts(F, bookkeeping=False)) == ["colour", "durability"]


def test_2_a_rebinding_of_the_defining_sets_is_honoured(world, monkeypatch):
    p = world.porcelain
    assert "mood" in _attrs(p.facts(F, bookkeeping=False))
    with monkeypatch.context() as m:
        m.setattr(model, "META_ATTRIBUTES", model.META_ATTRIBUTES | {"mood"})
        assert "mood" not in _attrs(p.facts(F, bookkeeping=False))
    assert "mood" in _attrs(p.facts(F, bookkeeping=False))
    with monkeypatch.context() as m:
        m.setattr(model, "MECHANISM_ATTRIBUTES", model.MECHANISM_ATTRIBUTES | {"mood"})
        assert "mood" not in _attrs(p.facts(F, bookkeeping=False))
    assert "mood" in _attrs(p.facts(F, bookkeeping=False))


def test_2_every_bookkeeping_attribute_in_the_frame_is_excluded(world):
    names = sorted(model.META_ATTRIBUTES | model.MECHANISM_ATTRIBUTES)
    written = []
    for name in names:                  # every name a row in a knows: frame can carry
        try:
            world.buffer.append(entity="person:ann", attribute=name, value="x",
                                value_type="literal", status="stated", role=INGESTOR,
                                frame=F)
        except Exception:               # an owner-only mechanism row: not writable here
            continue
        written.append(name)
    assert len(written) >= len(model.META_ATTRIBUTES - model.MECHANISM_ATTRIBUTES) - 2
    scanned = set(_attrs(world.porcelain.facts(F)))
    assert set(written) <= scanned
    left = set(_attrs(world.porcelain.facts(F, bookkeeping=False)))
    assert not left & set(names)
    assert {"colour", "mood"} <= left


def test_2a_durability_is_a_world_fact_and_its_declaration_is_a_subject_matter(world):
    world.buffer.append(entity="attr:wingspan", attribute="durability", value="STATE",
                        value_type="literal", status="stated", role=INGESTOR, frame=F)
    p = world.porcelain
    assert "durability" not in model.META_ATTRIBUTES | model.MECHANISM_ATTRIBUTES
    entities = lambda facts: {(f["entity"], f["attribute"]) for f in facts}
    assert ("obj:lamp", "durability") in entities(p.facts(F, bookkeeping=False))
    assert ("attr:wingspan", "durability") not in entities(p.facts(F))
    assert ("attr:wingspan", "durability") not in entities(p.facts(F, bookkeeping=False))
    assert ("attr:wingspan", "durability") in entities(
        p.facts(F, include_meta=True, bookkeeping=False))


def test_3_include_meta_and_bookkeeping_compose(world):
    # two rows about an assertion id (a meta subject): provenance, and a note
    for attribute, value in (("source", "doc:letter"), ("note", "smudged")):
        world.buffer.append(entity="a:2", attribute=attribute, value=value,
                            value_type="literal", status="stated", role=INGESTOR, frame=F)
    p = world.porcelain
    meta = lambda facts: sorted(f["attribute"] for f in facts if f["entity"] == "a:2")
    assert meta(p.facts(F)) == []                                     # subject filter
    assert meta(p.facts(F, include_meta=True)) == ["note", "source"]
    assert meta(p.facts(F, include_meta=True, bookkeeping=False)) == ["note"]
    assert p.facts(F, attribute="same_as", bookkeeping=False) == []


def test_4_mcp_facts_takes_bookkeeping(world):
    out = dispatch(world, "facts", {"frame": F, "bookkeeping": False})["result"]
    assert _attrs(out) == _attrs(world.porcelain.facts(F, bookkeeping=False))


def test_5_a_viewer_may_narrow_its_own_scan(world):
    svc = WorldService()
    svc.attach(world, F)
    try:
        sess = svc.session("renderer")
        assert _attrs(sess.call("facts", bookkeeping=False)) == \
            _attrs(world.porcelain.facts(F, bookkeeping=False))
        assert "aka" in _attrs(sess.call("facts"))
    finally:
        svc.detach()
