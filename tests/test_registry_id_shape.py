"""Pass-0 registry ids must pass the engine's id grammar (R23 finding).

Today's extractor read the prompt's "person:/place:/..." namespace list as a
prefix and minted ``person:/ilsa_renn``; the gate refuses those ids, so every
seed row and place edge was skipped. The parser repairs the slash.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals" / "harness"))

from patternbuffer.model import ID_RE
from registry import _PASS0_PROMPT, parse_registry_lines


def test_slash_after_namespace_is_repaired_in_entities_and_edges() -> None:
    reg, rejects = parse_registry_lines(
        ["E|person:/ilsa_renn|person|Ilsa Renn|the clerk|",
         "E|place:/records_vault|place|Records Vault||",
         "E|place:bazaar|place|the Bazaar||",
         "P|place:/records_vault|place:bazaar"],
        "w:t")
    assert rejects == []
    assert sorted(reg.entities) == ["person:ilsa_renn", "place:bazaar", "place:records_vault"]
    assert reg.places == [("place:records_vault", "place:bazaar")]
    for eid in reg.entities:
        assert ID_RE.fullmatch(eid)


def test_well_formed_ids_are_untouched() -> None:
    reg, _ = parse_registry_lines(["E|obj:memory_core|object|the memory core||"], "w:t")
    assert list(reg.entities) == ["obj:memory_core"]


def test_prompt_no_longer_lists_namespaces_with_slashes() -> None:
    assert "person:/place:/" not in _PASS0_PROMPT
    assert "person:ilsa_renn" in _PASS0_PROMPT
