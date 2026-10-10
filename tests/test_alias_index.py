"""ALIAS-INDEX-V1 Part A: hand-made registries and texts exercise each report item."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "evals" / "harness"))

import alias_index as ai
from alias_index import build_report, is_proper_name, slice_ids, stoplist_class
from pipeline import Pipeline, REGISTRY_TOKEN_CAP
from registry import EntityCard, WorldRegistry


def reg(**cards: tuple[list[str], list[str]]) -> dict:
    return {"world_id": "w:t",
            "entities": {k: {"kind": k.split(":")[0], "names": n, "aliases": a}
                         for k, (n, a) in cards.items()}}


VAULTS = reg(**{
    "place:/records_vault": (["Records Vault"], ["the vault", "vault"]),
    "place:/seed_vault": (["Seed Vault"], ["the vault"]),
    "place:/vault": (["the vault"], []),
    "person:/ilsa_renn": (["Ilsa Renn"], ["renn"]),
    "person:/tin_ear_clerk": (["the clerk"], ["the gray woman", "ilsa renn"]),
})


def pair(report: dict, a: str, b: str) -> dict | None:
    return next((p for p in report["distinctness_evidence"] if set(p["ids"]) == {a, b}), None)


# ---------------------------------------------------------------- item 1


def test_index_maps_normalized_strings_to_repaired_ids() -> None:
    r = build_report(VAULTS, ["He walked into the Seed Vault."])
    assert r["index"]["seed vault"] == ["place:seed_vault"]
    assert r["id_repairs"]["place:seed_vault"] == "place:/seed_vault"
    assert "the vault" not in r["index"] and "vault" in r["index"]  # article dropped


def test_per_segment_hits_exact() -> None:
    r = build_report(VAULTS, ["Nothing here.", "Seed Vault, then the Seed Vault again."])
    assert [h["segment"] for h in r["segment_hits"]] == [1]
    hit = r["segment_hits"][0]["ids"]["place:seed_vault"]
    assert hit == [{"ambiguous": False, "count": 2, "match": "exact", "string": "seed vault"}]


def test_exact_is_whole_word_and_longest_first() -> None:
    cards = reg(**{"obj:/ink": (["ink"], []), "obj:/ink_well": (["ink well"], [])})
    r = build_report(cards, ["The inkwell and the ink well, and think of ink."])
    ids = {i: [h["count"] for h in hs] for i, hs in r["segment_hits"][0]["ids"].items()}
    assert ids == {"obj:ink_well": [1], "obj:ink": [1]}  # not 'ink' inside 'inkwell'/'think'


def test_title_surname_and_prefix_matches() -> None:
    cards = reg(**{"person:cray": (["Marshal Dane Cray"], []),
                   "person:ilsa": (["Ilsa Renn"], [])})
    r = build_report(cards, ["Warden Cray frowned. Ilsa said nothing."])
    kinds = {i: hs[0]["match"] for i, hs in r["segment_hits"][0]["ids"].items()}
    assert kinds == {"person:cray": "title_surname", "person:ilsa": "prefix"}


def test_prefix_skips_ordinary_sentence_initial_word() -> None:
    cards = reg(**{"place:records": (["Records Vault"], [])})
    r = build_report(cards, ["Records were kept. The records piled up. Records Vault was cold."])
    hs = r["segment_hits"][0]["ids"]["place:records"]
    assert [(h["match"], h["count"]) for h in hs] == [("exact", 1)]


# ---------------------------------------------------------------- item 2


def test_ambiguous_string_the_vault() -> None:
    r = build_report(VAULTS, ["She sealed the vault. The vault stayed shut."])
    amb = {a["string"]: a for a in r["ambiguous_strings"]}
    assert amb["vault"]["ids"] == ["place:records_vault", "place:seed_vault", "place:vault"]
    assert amb["vault"]["same_kind"] and amb["vault"]["text_mentions"] == 2
    assert amb["vault"]["spellings"] == ["the vault", "vault"]
    assert [h["ambiguous"] for h in r["segment_hits"][0]["ids"]["place:vault"]] == [True]


def test_ambiguous_flags_mixed_kinds() -> None:
    cards = reg(**{"org:office": (["Allocation Office"], []),
                   "place:office": (["Allocation Office"], [])})
    (a,) = build_report(cards, [""])["ambiguous_strings"]
    assert a["same_kind"] is False


# ---------------------------------------------------------------- item 3


@pytest.mark.parametrize("text,cls", [
    ("mother", "kinship"), ("my mother", "kinship"), ("his Brother", "kinship"),
    ("sir", "address"), ("ma’am", "address"),
    ("the boy", "role"), ("the clerk", "role"), ("an old man", "role"),
    ("she", "pronoun"), ("Her", "pronoun"),
])
def test_stoplist_classes(text: str, cls: str) -> None:
    assert stoplist_class(text) == cls


def test_stoplist_does_not_catch_identifying_strings() -> None:
    for s in ("the gray woman", "Ilsa Renn", "the clerk's desk", "Mother Superior Vale"):
        assert stoplist_class(s) is None


def test_stoplisted_strings_are_not_identifying() -> None:
    cards = reg(**{"person:a": (["Sela Voss"], ["the boy", "sir"]),
                   "person:b": (["Tovan Voss"], ["the boy", "mother"])})
    r = build_report(cards, ["The boy said sir to mother."])
    assert r["ambiguous_strings"] == []
    assert "boy" not in r["index"] and r["segment_hits"] == []
    assert r["stoplisted"]["boy"] == {"class": "role", "ids": ["person:a", "person:b"]}
    assert r["stoplisted"]["mother"]["class"] == "kinship"
    assert r["stoplisted"]["sir"]["class"] == "address"


def test_stoplisted_string_is_not_a_merge_or_escape() -> None:
    cards = reg(**{"person:a": (["Sela Voss"], []), "person:b": (["the boy"], ["Sela Voss"])})
    r = build_report(cards, ["Mother Sela called. The Boy ran."])
    assert [(m["holder"], m["named"]) for m in r["merge_candidates"]] == [("person:b", "person:a")]
    assert all(e["string"] not in ("boy", "mother") for e in r["escape_candidates"])


# ---------------------------------------------------------------- item 4


def test_escape_candidates_ranked_by_frequency() -> None:
    cards = reg(**{"person:sela": (["Sela Voss"], ["Sela"])})
    text = ("Sela met Marn Teck at the gate. Later Marn Teck left, and later still it rained. "
            "Then came Cistern Three, and then the dark. The water ran. Water Steward Vail laughed. "
            "“Marn Teck,” she said.")
    r = build_report(cards, [text])
    got = [(e["string"], e["count"]) for e in r["escape_candidates"]]
    assert got[0] == ("marn teck", 3)
    assert ("cistern three", 1) in got and ("steward vail", 1) in got
    assert all(s not in ("sela", "the", "later", "then", "water") for s, _ in got)


def test_escape_marks_partial_names_and_skips_headings() -> None:
    cards = reg(**{"person:ilsa": (["Ilsa Renn"], [])})
    r = build_report(cards, ["## Chapter Nine\n\nThe road ran. Renn waited."])
    (e,) = r["escape_candidates"]
    assert e["string"] == "renn" and e["overlaps"] == ["person:ilsa"]


# ---------------------------------------------------------------- item 5


def test_distinct_proper_names_of_same_kind() -> None:
    r = build_report(VAULTS, ["The vault was cold."])
    p = pair(r, "place:records_vault", "place:seed_vault")
    assert p["strength"] == "strong"
    (e,) = p["evidence"]
    assert e["type"] == "distinct_proper_names"
    assert e["evidence"] == "different proper names: 'Records Vault' vs 'Seed Vault'"
    # a generic card with no proper name is not distinct from either
    assert pair(r, "place:records_vault", "place:vault") is None


def test_name_containment_is_not_distinctness() -> None:
    cards = reg(**{"place:a": (["Seed Vault"], ["the vault"]),
                   "place:b": (["Vault"], ["the vault"])})
    assert build_report(cards, ["The vault."])["distinctness_evidence"] == []


def test_different_kinds_are_not_compared() -> None:
    cards = reg(**{"place:a": (["Seed Vault"], ["vault"]), "obj:b": (["Records Vault"], ["vault"])})
    assert build_report(cards, ["Vault."])["distinctness_evidence"] == []


def test_coordination_in_one_sentence() -> None:
    cards = reg(**{"person:sela": (["Sela Voss"], ["sela"]), "person:marn": (["Marn Teck"], ["marn"]),
                   "person:tovan": (["Tovan Voss"], ["tovan"])})
    text = "Sela and Marn watched. Later, Tovan left. Sela, Marn, and Tovan met."
    r = build_report(cards, [text])
    sm = pair(r, "person:marn", "person:sela")
    assert sm["strength"] == "strong"
    (e,) = sm["evidence"]
    assert e["type"] == "coordination" and e["count"] == 2
    assert e["evidence"] == "Sela and Marn watched."
    assert pair(r, "person:sela", "person:tovan")["evidence"][0]["count"] == 1
    # "Marn watched. Later, Tovan" crosses a sentence: no evidence from it
    assert pair(r, "person:marn", "person:tovan")["evidence"][0]["count"] == 1


def test_coordination_ignores_ambiguous_and_comma_only() -> None:
    r = build_report(VAULTS, ["The vault and the Seed Vault. Renn, the gray woman."])
    # 'vault' is ambiguous; a comma without 'and' is an apposition
    assert pair(r, "place:seed_vault", "place:vault") is None
    # the apposition is no coordination (only weak co-presence, for the shared 'ilsa renn')
    assert [e["type"] for e in pair(r, "person:ilsa_renn", "person:tin_ear_clerk")["evidence"]] == ["co_presence"]


def test_co_presence_is_weak_and_for_risk_pairs_only() -> None:
    cards = reg(**{"person:a": (["the miller"], ["voss", "tovan"]), "person:b": (["the weaver"], ["voss", "sela"]),
                   "person:c": (["the cooper"], ["marn"])})
    text = "Tovan met Sela and Marn.\n\nVoss was elsewhere.\n\nTovan sat with Sela, and nobody else."
    r = build_report(cards, [text])
    ab = pair(r, "person:a", "person:b")
    assert ab["strength"] == "weak"
    assert [(e["type"], e["strength"], e["count"]) for e in ab["evidence"]] == [("co_presence", "weak", 2)]
    # 'Sela and Marn': coordination (strong) for any pair; b and c share no string, so no co-presence
    bc = pair(r, "person:b", "person:c")
    assert bc["strength"] == "strong" and [e["type"] for e in bc["evidence"]] == ["coordination"]
    assert pair(r, "person:a", "person:c") is None  # never coordinated, not a risk pair


def test_weak_evidence_alone_has_weak_strength() -> None:
    cards = reg(**{"person:a": (["the miller"], ["voss", "tovan"]), "person:b": (["the weaver"], ["voss", "sela"])})
    r = build_report(cards, ["Tovan lingered by Sela's door."])
    p = pair(r, "person:a", "person:b")
    assert p["strength"] == "weak" and p["evidence"][0]["type"] == "co_presence"
    assert p["why_checked"] == ["shared string 'voss'"]


# ---------------------------------------------------------------- item 6


def test_merge_candidate_ilsa_case() -> None:
    r = build_report(VAULTS, ["Renn kept the ledger."])
    (m,) = r["merge_candidates"]
    assert (m["holder"], m["named"], m["string"]) == ("person:tin_ear_clerk", "person:ilsa_renn", "ilsa renn")
    assert m["weak_evidence_against"] == []
    assert r["merge_excluded"] == []
    # co-presence of the two cards' own strings is weak: it annotates, never excludes
    r = build_report(VAULTS, ["Renn, the gray woman, kept the ledger."])
    assert [m["weak_evidence_against"] for m in r["merge_candidates"]] == [["co_presence"]]


def test_merge_candidate_excluded_by_strong_evidence() -> None:
    cards = reg(**{"place:a": (["Records Vault"], ["seed vault"]),
                   "place:b": (["Seed Vault"], [])})
    r = build_report(cards, ["Records Vault."])
    assert r["merge_candidates"] == []
    (x,) = r["merge_excluded"]
    assert x["holder"] == "place:a" and x["named"] == "place:b"
    assert "'Records Vault' vs 'Seed Vault'" in x["excluded_by"][0]


def test_weak_evidence_annotates_but_does_not_exclude_merge() -> None:
    text = "Renn spoke with the gray woman."
    cards = reg(**{"person:i": (["Ilsa Renn"], ["renn"]),
                   "person:c": (["the clerk"], ["ilsa renn", "the gray woman"])})
    r = build_report(cards, [text])
    (m,) = r["merge_candidates"]
    assert m["holder"] == "person:c" and m["weak_evidence_against"] == ["co_presence"]
    assert r["merge_excluded"] == []


def test_single_word_person_alias_is_not_a_full_name() -> None:
    cards = reg(**{"person:a": (["Sela Voss"], []), "person:b": (["the miller"], ["sela voss"]),
                   "person:c": (["Sela"], []), "person:d": (["Tovan Voss"], ["sela"])})
    pairs = {(m["holder"], m["named"]) for m in build_report(cards, [""])["merge_candidates"]}
    assert pairs == {("person:b", "person:a")}  # 'sela' on d names no full proper name


def test_is_proper_name() -> None:
    assert is_proper_name("Seed Vault") and is_proper_name("SEED VAULT")
    assert is_proper_name("The Last Honest Meter") and is_proper_name("Order of the Meter")
    for s in ("the vault", "the clerk", "Seed Vault hatch", "Ilsa Renn's desk", ""):
        assert not is_proper_name(s)


# ----------------------------------------------------- report as a whole


def test_report_is_deterministic_json_and_accepts_dataclass() -> None:
    text = ["Sela and Marn went to the Seed Vault. The vault was cold."]
    a = build_report(VAULTS, text)
    assert json.dumps(a, sort_keys=True) == json.dumps(build_report(VAULTS, text), sort_keys=True)
    wr = WorldRegistry(world_id="w:t", entities={"place:x": EntityCard(kind="place", names=["Seed Vault"])})
    assert build_report(wr, text)["index"] == {"seed vault": ["place:x"]}


def test_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    rp = tmp_path / "registry.json"
    rp.write_text(json.dumps(VAULTS))
    story = tmp_path / "story.md"
    story.write_text("# T\n\n## Chapter One\n\nThe vault, the Seed Vault.\n\n## Chapter Two\n\nRenn waited.\n")
    out = tmp_path / "out"
    assert ai.main([str(rp), "--story", str(story), "--out", str(out)]) == 0
    r = json.loads((out / "alias_index.json").read_text())
    assert r["segments"] == 2 and r["counts"]["merge_candidates"] == 1
    md = (out / "alias_index.md").read_text()
    assert "Ambiguous strings" in md and "place:records_vault" in md
    assert json.loads(rp.read_text()) == VAULTS  # input untouched


# ------------------------------------------------- pass-1 slice wiring


def big_registry() -> WorldRegistry:
    """Over the size guard so the deterministic slice applies."""
    ents = {f"obj:filler_{i}": EntityCard(kind="obj", names=[f"Filler Thing {i}"],
                                          anchors=["x" * 200]) for i in range(400)}
    ents["place:records_vault"] = EntityCard(kind="place", names=["Records Vault"], aliases=["the vault"])
    ents["place:seed_vault"] = EntityCard(kind="place", names=["Seed Vault"], aliases=["the vault"])
    ents["person:ilsa"] = EntityCard(kind="person", names=["Ilsa Renn"])
    ents["obj:cat"] = EntityCard(kind="obj", names=["cat"])
    return WorldRegistry(world_id="w:t", entities=ents)


def slice_keys(p: Pipeline, registry: WorldRegistry, text: str) -> set[str]:
    return set(json.loads(p._registry_slice(registry, text))["entities"])


def test_default_pipeline_slice_unchanged(tmp_path: Path) -> None:
    registry = big_registry()
    assert len(json.dumps({"e": {k: [c.names, c.aliases] for k, c in registry.entities.items()}})) > 0
    p = Pipeline(lambda prompt, schema: {}, "w:t", tmp_path)
    assert p.alias_slice is False
    text = "She locked the Records Vault; a locat of caterpillars crawled."
    # the original rule, restated: persons + raw substring hits of names/aliases
    lowered = text.lower()
    expected = {eid for eid, c in registry.entities.items()
                if eid.startswith("person:")
                or any(a in lowered for a in c.aliases + [n.lower() for n in c.names])}
    full = json.dumps({"entities": {eid: {"kind": c.kind, "names": c.names, "aliases": c.aliases}
                                    for eid, c in sorted(registry.entities.items())},
                       "attributes": registry.attributes,
                       "places": [list(x) for x in registry.places]}, indent=0)
    assert len(full) > REGISTRY_TOKEN_CAP * 4
    assert slice_keys(p, registry, text) == expected
    assert "obj:cat" in expected  # the substring rule's known false hit ('cat' in 'caterpillars')


def test_alias_slice_flag_is_boundary_aware_and_keeps_siblings(tmp_path: Path) -> None:
    registry = big_registry()
    p = Pipeline(lambda prompt, schema: {}, "w:t", tmp_path / "r", alias_slice=True)
    keys = slice_keys(p, registry, "She locked the Records Vault; caterpillars crawled.")
    assert "obj:cat" not in keys
    assert {"place:records_vault", "place:seed_vault", "person:ilsa"} <= keys  # sibling via 'the vault'
    assert not any(k.startswith("obj:filler") for k in keys)


def test_alias_slice_does_not_change_small_registry(tmp_path: Path) -> None:
    small = WorldRegistry(world_id="w:t", entities={"obj:cat": EntityCard(kind="obj", names=["cat"])})
    a = Pipeline(lambda p_, s: {}, "w:t", tmp_path / "a")
    b = Pipeline(lambda p_, s: {}, "w:t", tmp_path / "b", alias_slice=True)
    assert a._registry_slice(small, "caterpillar") == b._registry_slice(small, "caterpillar")


def test_slice_ids_direct() -> None:
    assert slice_ids(VAULTS, "Seed Vault.") == {"place:seed_vault", "place:records_vault", "place:vault"}
    assert slice_ids(VAULTS, "Nothing.") == set()
