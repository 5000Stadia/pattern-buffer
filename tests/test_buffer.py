"""Buffer invariants: append-only, role authority, two time axes, 1:1 world."""

import sqlite3

import pytest

from patternbuffer.buffer import PatternBuffer, WorldMismatch
from patternbuffer.model import Assertion
from patternbuffer.roles import RoleViolation, WriterRole, _make_engine_roles


@pytest.fixture
def roles():
    return _make_engine_roles()


@pytest.fixture
def buf(tmp_path):
    b = PatternBuffer(tmp_path / "w.world", world_id="w:test")
    yield b
    b.close()


def _place_pipe(buf, ingestor, *, valid_from=1.0):
    return buf.append(
        entity="obj:pipe",
        attribute="in",
        value="obj:drawer",
        value_type="entity",
        valid_from=valid_from,
        status="stated",
        role=ingestor,
    )


class TestAppendOnly:
    def test_no_update_or_delete_api_exists(self, buf):
        public = {name for name in dir(buf) if not name.startswith("_")}
        assert not {"update", "delete", "edit", "remove"} & public

    def test_sql_update_raises(self, buf, roles):
        _place_pipe(buf, roles["ingestor"])
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            buf.raw_connection().execute("UPDATE assertions SET value = '\"x\"'")

    def test_sql_delete_raises(self, buf, roles):
        _place_pipe(buf, roles["ingestor"])
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            buf.raw_connection().execute("DELETE FROM assertions")

    def test_correction_is_an_append(self, buf, roles):
        a1 = _place_pipe(buf, roles["ingestor"])
        retraction = buf.append(
            entity=a1.id,
            attribute="retracts",
            value="mis-ingested",
            status="retracted",
            role=roles["truth_maintenance"],
        )
        assert buf.get(a1.id) is not None  # the row survives in the log
        assert retraction.seq == a1.seq + 1
        assert buf.visible(entity="obj:pipe") == []  # but folds exclude it


class TestRoleMatrix:
    def test_matrix_enforced_per_cell(self, buf, roles):
        allowed = {
            "ingestor": {"stated", "observed", "inferred", "assumed"},
            "resolver": {"generated"},
            "truth_maintenance": {"retracted", "inferred"},
        }
        all_statuses = {"stated", "observed", "inferred", "assumed", "generated", "default", "retracted"}
        for role_name, role in roles.items():
            for status in sorted(all_statuses):
                kwargs = dict(
                    entity="e:x", attribute="note", value=1, status=status, role=role
                )
                if status in allowed[role_name]:
                    buf.append(**kwargs)
                else:
                    with pytest.raises(RoleViolation):
                        buf.append(**kwargs)

    def test_no_role_may_append_default(self, buf, roles):
        for role in roles.values():
            with pytest.raises(RoleViolation):
                buf.append(entity="e:x", attribute="note", value=1, status="default", role=role)

    def test_capability_not_mintable(self):
        with pytest.raises(RoleViolation):
            WriterRole("rogue", frozenset({"stated"}))


class TestWorldInvariant:
    def test_reopen_with_wrong_world_refused(self, tmp_path):
        PatternBuffer(tmp_path / "w.world", world_id="w:one").close()
        with pytest.raises(WorldMismatch):
            PatternBuffer(tmp_path / "w.world", world_id="w:two")

    def test_every_row_stamped(self, buf, roles):
        row = _place_pipe(buf, roles["ingestor"])
        assert row.world_id == "w:test"

    def test_foreign_row_refused(self, buf):
        alien = Assertion(
            seq=1, id="a:1", world_id="w:other", entity="e", attribute="kind",
            value_type="literal", value="x", valid_from=None, valid_to=None,
            frame="canon", status="stated", confidence=None, asserted_at=1,
        )
        with pytest.raises(WorldMismatch):
            buf._insert(alien)


class TestTwoTimeAxes:
    def test_ids_and_transaction_time_are_log_order(self, buf, roles):
        a1 = _place_pipe(buf, roles["ingestor"])
        a2 = buf.append(entity="e:y", attribute="note", value=1, status="stated", role=roles["ingestor"])
        assert (a1.id, a1.asserted_at, a2.id, a2.asserted_at) == ("a:1", 1, "a:2", 2)

    def test_late_revealed_offscreen_move(self, buf, roles):
        """valid_time != asserted_at: the Ch.3-asserted move with a Ch.1-era
        valid_from is visible to as-of-Ch.1 queries only once asserted."""
        ing = roles["ingestor"]
        _place_pipe(buf, ing, valid_from=1.0)  # a:1 — core in drawer, t=1
        moved = buf.append(
            entity="obj:pipe", attribute="in", value="place:vault", value_type="entity",
            valid_from=4.0, status="stated", role=ing,
        )  # a:2 — asserted later, valid at t=4

        # As of world-time 5, but before the reveal was asserted: only the drawer row.
        before_reveal = buf.visible(entity="obj:pipe", valid_as_of=5.0, asserted_as_of=1)
        assert [r.value for r in before_reveal] == ["obj:drawer"]

        # Same world-time, after the reveal: both rows visible; the fold's
        # STATE winner (max valid_from) is the vault row.
        after = buf.visible(entity="obj:pipe", valid_as_of=5.0)
        assert {r.value for r in after} == {"obj:drawer", "place:vault"}
        assert moved.valid_from == 4.0 and moved.asserted_at == 2

    def test_valid_interval_bounds(self, buf, roles):
        buf.append(
            entity="e:window", attribute="open", value=True,
            valid_from=2.0, valid_to=6.0, status="stated", role=roles["ingestor"],
        )
        assert buf.visible(entity="e:window", valid_as_of=1.0) == []
        assert len(buf.visible(entity="e:window", valid_as_of=2.0)) == 1
        assert buf.visible(entity="e:window", valid_as_of=6.0) == []  # valid_to exclusive

    def test_timeless_rows_always_valid(self, buf, roles):
        buf.append(entity="e:room", attribute="kind", value="room", status="stated", role=roles["ingestor"])
        assert len(buf.visible(entity="e:room", valid_as_of=0.0)) == 1
