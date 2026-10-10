"""The extraction prompt states the id grammar the gate enforces.

The old rule listed namespaces as "person:/place:/obj:/...", which current
models read as the prefix `person:/`; the gate refuses such ids (SHAPE-FIX-V1
never repairs them), so construct's R20 probe lost 266 facts in one run.
Hyphenated ids (`event:a-b`) were lost the same way.
"""

import re

import pytest

from patternbuffer.ingest import _EXTRACT_RULES_FULL, _EXTRACT_RULES_LEAN


@pytest.mark.parametrize("rules", [_EXTRACT_RULES_FULL, _EXTRACT_RULES_LEAN])
def test_rules_do_not_show_a_slash_after_the_namespace(rules: str) -> None:
    assert "person:/" not in rules and "place:/" not in rules
    assert "<namespace>:<snake_case_name>" in rules
    assert "never hyphens" in rules


@pytest.mark.parametrize("rules", [_EXTRACT_RULES_FULL, _EXTRACT_RULES_LEAN])
def test_no_id_placeholder_is_spelled_with_hyphens(rules: str) -> None:
    """pbr RED: the movement rule showed `event:<short-occurrence-slug>`, which
    prescribes the hyphenated ids the gate refuses."""
    assert not re.search(r"[a-z]+:<[^>]*-[^>]*>", rules)


def test_movement_rule_spells_its_event_id_in_snake_case() -> None:
    assert "event:<short_occurrence_slug>" in _EXTRACT_RULES_FULL
    assert "short-occurrence-slug" not in _EXTRACT_RULES_FULL
