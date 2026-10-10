"""PASS0-GRADER-V1: hand-made registries exercise each grader metric."""

from __future__ import annotations

import json

import pytest

from evals.harness.fixtures import ENTITIES
from evals.harness.grade_registry import grade, main, normalize, scorecard_md

GOLD = {
    "ilsa": ["ilsa renn", "ilsa", "the clerk"],
    "sela": ["sela voss", "sela"],
    "core": ["memory core", "the core"],
}


def reg(**cards: tuple[list[str], list[str]]) -> dict:
    return {"entities": {k: {"kind": "x", "names": n, "aliases": a} for k, (n, a) in cards.items()}}


PERFECT = reg(
    **{
        "person:ilsa": (["Ilsa Renn"], ["ilsa", "the clerk"]),
        "person:sela": (["Sela Voss"], ["sela"]),
        "obj:core": (["Memory Core"], ["the core"]),
        "obj:extra": (["Unrelated Thing"], []),  # not charged: gold is partial
    }
)


def test_normalize() -> None:
    assert normalize("  The Core ") == "core"
    assert normalize("An  Aquifer Map") == "aquifer map"
    assert normalize("anchor") == "anchor"
    assert normalize("a") == "a"


def test_perfect() -> None:
    g = grade(PERFECT, GOLD)
    assert g["coverage"] == 3 and g["fragmentation_count"] == 0 and g["fusion_count"] == 0
    assert g["mentions"] == 7 and g["mentions_unresolved"] == 0
    assert (g["b3_precision"], g["b3_recall"], g["b3_f1"]) == (1.0, 1.0, 1.0)


def test_split_entity_is_fragmentation() -> None:
    r = reg(
        **{
            "person:ilsa": (["Ilsa Renn"], ["ilsa"]),
            "person:clerk": (["the clerk"], []),
            "person:sela": (["Sela Voss"], ["sela"]),
            "obj:core": (["Memory Core"], ["the core"]),
        }
    )
    g = grade(r, GOLD)
    assert g["fragmentation"] == {"ilsa": ["person:clerk", "person:ilsa"]}
    assert g["fusion_count"] == 0 and g["coverage"] == 3
    assert g["b3_precision"] == 1.0
    # ilsa mentions: 2 in one id, 1 in the other -> recall 2/3, 2/3, 1/3 ; others 1.0 (4 mentions)
    assert g["b3_recall"] == pytest.approx((2 / 3 + 2 / 3 + 1 / 3 + 4) / 7, abs=1e-4)


def test_fused_ids() -> None:
    r = reg(
        **{
            "person:both": (["Ilsa Renn", "Sela Voss"], ["ilsa", "sela", "the clerk"]),
            "obj:core": (["Memory Core"], ["the core"]),
        }
    )
    g = grade(r, GOLD)
    assert g["fusion"] == {"person:both": ["ilsa", "sela"]}
    assert g["fragmentation_count"] == 0 and g["coverage"] == 3
    assert g["b3_recall"] == 1.0
    # 5 person mentions in one cluster: ilsa (3) precision 3/5, sela (2) 2/5; core 1.0 (2)
    assert g["b3_precision"] == pytest.approx((3 * 3 / 5 + 2 * 2 / 5 + 2) / 7, abs=1e-4)


def test_missing_entity_and_unresolved_mentions() -> None:
    r = reg(
        **{
            "person:ilsa": (["Ilsa Renn"], ["ilsa"]),  # 'the clerk' unresolved
            "person:sela": (["Sela Voss"], ["sela"]),
        }
    )
    g = grade(r, GOLD)
    assert g["coverage"] == 2 and g["uncovered"] == ["core"]
    assert g["per_entity"]["ilsa"]["unresolved"] == ["clerk"]
    assert g["per_entity"]["core"]["unresolved"] == ["core", "memory core"]
    assert g["mentions_unresolved"] == 3
    assert g["b3_precision"] == 1.0
    # unresolved mentions are singletons: recall = (ilsa 2*(2/3) + 1*(1/3) + sela 2 + core 2*(1/2)) / 7
    assert g["b3_recall"] == pytest.approx((2 * 2 / 3 + 1 / 3 + 2 + 2 * 0.5) / 7, abs=1e-4)


def test_case_and_article_variants_resolve() -> None:
    r = reg(
        **{
            "person:ilsa": (["  ILSA RENN "], ["The Clerk", "ILSA"]),
            "person:sela": (["A Sela Voss"[2:]], ["Sela"]),
            "obj:core": (["An Memory Core"[3:]], ["THE CORE"]),
        }
    )
    g = grade(r, GOLD)
    assert g["mentions_unresolved"] == 0 and g["b3_f1"] == 1.0


def test_accepts_registry_object_and_json_path(tmp_path) -> None:
    from evals.harness.registry import EntityCard, WorldRegistry

    wr = WorldRegistry(world_id="w:t")
    wr.entities["person:ilsa"] = EntityCard("person", ["Ilsa Renn"], ["ilsa", "the clerk"])
    assert grade(wr, GOLD)["coverage"] == 1
    p = tmp_path / "registry.json"
    wr.save(p)
    out = tmp_path / "o"
    assert main([str(p), "--out", str(out)]) == 0
    data = json.loads((out / "scorecard.json").read_text())
    assert data["gold_entities"] == len(ENTITIES) and data["coverage"] == 1
    assert "B3 F1" in (out / "scorecard.md").read_text()


def test_scorecard_lists_problems() -> None:
    md = scorecard_md(grade(reg(**{"a:1": (["ilsa", "sela"], [])}), GOLD))
    assert "`a:1`" in md and "Fusion" in md
