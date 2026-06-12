from __future__ import annotations

from dataclasses import dataclass

import pytest

from evals.harness.grammar import Orphan, Reject, parse, reject_rate


@dataclass
class Registry:
    entities: dict[str, object]


@pytest.fixture
def registry() -> Registry:
    ids = {
        "obj:core",
        "obj:target",
        "obj:box",
        "person:ada",
        "event:start",
        "place:lab",
    }
    return Registry({entity_id: object() for entity_id in ids})


def test_round_trip_every_flag(registry: Registry) -> None:
    items, orphans, rejects = parse(
        [
            "obj:core|charge|5|vf=4.5,vt=9",
            "obj:core|kind|\"core\"|t",
            (
                "obj:core|visible|true|"
                "f=knows:person:ada,s=observed,doc=doc:alpha,cb=event:start"
            ),
        ],
        registry,
        cursor=12.0,
    )

    assert orphans == []
    assert rejects == []
    assert items[0] == {
        "entity": "obj:core",
        "attribute": "charge",
        "value": 5,
        "valid_from": 4.5,
        "valid_to": 9.0,
    }
    assert items[1] == {
        "entity": "obj:core",
        "attribute": "kind",
        "value": "core",
        "timeless": True,
    }
    assert items[2] == {
        "entity": "obj:core",
        "attribute": "visible",
        "value": True,
        "frame": "knows:person:ada",
        "status": "observed",
        "source_doc": "doc:alpha",
        "caused_by": "event:start",
        "valid_from": 12.0,
    }


def test_json_string_value_may_contain_pipe_and_commas(registry: Registry) -> None:
    items, orphans, rejects = parse(
        ['obj:core|note|"alpha|beta, gamma"|doc=doc:note'],
        registry,
        cursor=3.0,
    )

    assert orphans == []
    assert rejects == []
    assert items == [
        {
            "entity": "obj:core",
            "attribute": "note",
            "value": "alpha|beta, gamma",
            "source_doc": "doc:note",
            "valid_from": 3.0,
        }
    ]


def test_entity_ref_value(registry: Registry) -> None:
    items, orphans, rejects = parse(
        ["obj:core|in|@obj:box"],
        registry,
        cursor=1.0,
    )

    assert orphans == []
    assert rejects == []
    assert items == [
        {
            "entity": "obj:core",
            "attribute": "in",
            "value": "obj:box",
            "value_type": "entity",
            "valid_from": 1.0,
        }
    ]


def test_unresolved_policy_value(registry: Registry) -> None:
    items, orphans, rejects = parse(
        ['obj:core|contents|?{"policy":"invent_under_canon"}|s=assumed'],
        registry,
        cursor=2.0,
    )

    assert orphans == []
    assert rejects == []
    assert items == [
        {
            "entity": "obj:core",
            "attribute": "contents",
            "value": {"policy": "invent_under_canon"},
            "value_type": "unresolved",
            "status": "assumed",
            "valid_from": 2.0,
        }
    ]


def test_bare_scalar_coercions(registry: Registry) -> None:
    items, orphans, rejects = parse(
        [
            "obj:core|count|7",
            "obj:core|ratio|7.5",
            "obj:core|enabled|true",
            "obj:core|hidden|false",
            "obj:core|label|seven",
        ],
        registry,
        cursor=0.0,
    )

    assert orphans == []
    assert rejects == []
    values = [item["value"] for item in items]
    assert values[0] == 7
    assert values[1] == 7.5
    assert values[2] is True
    assert values[3] is False
    assert values[4] == "seven"


def test_field_regex_rejects(registry: Registry) -> None:
    items, orphans, rejects = parse(
        [
            "Obj:core|kind|core",
            "obj:core|9kind|core",
        ],
        registry,
        cursor=0.0,
    )

    assert items == []
    assert orphans == []
    assert [reject.line_no for reject in rejects] == [1, 2]
    assert [reject.reason for reject in rejects] == [
        "invalid entity field",
        "invalid attribute field",
    ]


def test_unknown_flag_rejects(registry: Registry) -> None:
    items, orphans, rejects = parse(
        ["obj:core|kind|core|x=1"],
        registry,
        cursor=0.0,
    )

    assert items == []
    assert orphans == []
    assert rejects == [Reject(line_no=1, line="obj:core|kind|core|x=1", reason="unknown flag 'x=1'")]


def test_bad_status_rejects(registry: Registry) -> None:
    items, orphans, rejects = parse(
        ["obj:core|kind|core|s=rumored"],
        registry,
        cursor=0.0,
    )

    assert items == []
    assert orphans == []
    assert rejects == [
        Reject(
            line_no=1,
            line="obj:core|kind|core|s=rumored",
            reason="invalid status 'rumored'",
        )
    ]


@pytest.mark.parametrize(
    ("line", "entity_id", "position"),
    [
        ("obj:missing|kind|core", "obj:missing", "subject"),
        ("obj:core|in|@obj:missing", "obj:missing", "value"),
        ("obj:core|changed|true|cb=event:missing", "event:missing", "caused_by"),
        ("obj:core|visible|true|f=knows:person:missing", "person:missing", "frame"),
    ],
)
def test_orphan_quarantine_for_each_reference_position(
    registry: Registry,
    line: str,
    entity_id: str,
    position: str,
) -> None:
    items, orphans, rejects = parse([line], registry, cursor=0.0)

    assert items == []
    assert rejects == []
    assert orphans == [
        Orphan(line_no=1, line=line, entity_id=entity_id, position=position)
    ]


def test_cursor_stamping(registry: Registry) -> None:
    items, orphans, rejects = parse(
        [
            "obj:core|mode|idle",
            "obj:core|kind|core|t",
            "obj:core|mode|active|vf=4.0",
        ],
        registry,
        cursor=12.5,
    )

    assert orphans == []
    assert rejects == []
    assert items[0]["valid_from"] == 12.5
    assert "valid_from" not in items[1]
    assert items[2]["valid_from"] == 4.0


def test_blank_and_comment_lines_are_skipped(registry: Registry) -> None:
    items, orphans, rejects = parse(
        [
            "",
            "   ",
            "# comment",
            "  # also a comment",
            "obj:core|kind|core",
            "obj:core",
        ],
        registry,
        cursor=1.0,
    )

    assert len(items) == 1
    assert orphans == []
    assert rejects == [
        Reject(line_no=6, line="obj:core", reason="expected entity|attribute|value")
    ]


def test_reject_rate_denominator_behavior() -> None:
    items = [{"entity": "obj:core"}]
    orphans = [Orphan(line_no=1, line="obj:missing|kind|core", entity_id="obj:missing", position="subject")]
    rejects = [Reject(line_no=2, line="bad", reason="bad")]

    assert reject_rate([], [], []) == 0.0
    assert reject_rate(items, orphans, rejects) == pytest.approx(1 / 3)
