"""Dump/builder seam: byte-identical round-trip; restore is not a write path."""

import json

import pytest

from patternbuffer.buffer import PatternBuffer
from patternbuffer.dump import DumpError, build, dump
from patternbuffer.roles import _make_engine_roles


@pytest.fixture
def populated(tmp_path):
    buf = PatternBuffer(tmp_path / "w.world", world_id="w:test")
    roles = _make_engine_roles()
    ing = roles["ingestor"]
    buf.append(entity="place:study", attribute="kind", value="room", status="stated", role=ing)
    buf.append(
        entity="obj:pipe", attribute="in", value="place:study", value_type="entity",
        valid_from=1.0, status="stated", role=ing,
    )
    buf.append(
        entity="obj:drawer", attribute="contents", value={"policy": "invent_under_canon"},
        value_type="unresolved", valid_from=1.0, status="assumed", role=ing,
    )
    yield buf
    buf.close()


def test_round_trip_byte_identical(populated, tmp_path):
    first = dump(populated)
    rebuilt = build(first, tmp_path / "copy.world")
    assert dump(rebuilt) == first
    rebuilt.close()


def test_build_refuses_existing_target(populated, tmp_path):
    target = tmp_path / "w.world"  # the populated buffer's own file
    with pytest.raises(DumpError, match="not a write path"):
        build(dump(populated), target)


def test_build_refuses_multi_world(populated, tmp_path):
    lines = dump(populated).splitlines()
    row = json.loads(lines[1])
    row["world_id"] = "w:other"
    lines[1] = json.dumps(row, sort_keys=True)
    with pytest.raises(DumpError, match="exactly one"):
        build("\n".join(lines), tmp_path / "x.world")


def test_build_refuses_gapped_seq(populated, tmp_path):
    lines = dump(populated).splitlines()
    with pytest.raises(DumpError, match="contiguous"):
        build("\n".join([lines[0], lines[2]]), tmp_path / "x.world")


def test_build_refuses_default_status(populated, tmp_path):
    lines = dump(populated).splitlines()
    row = json.loads(lines[0])
    row["status"] = "default"
    lines[0] = json.dumps(row, sort_keys=True)
    with pytest.raises(DumpError, match="cannot appear in a log"):
        build("\n".join(lines), tmp_path / "x.world")


def test_failed_build_leaves_nothing(populated, tmp_path):
    lines = dump(populated).splitlines()
    target = tmp_path / "x.world"
    with pytest.raises(DumpError):
        build("\n".join(lines[:1] + lines[2:]), target)  # gap at seq 2
    assert not target.exists()
