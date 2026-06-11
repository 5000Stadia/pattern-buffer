"""The role-authority matrix, enforced in code (whitepaper §12, spec §6).

Every append to the buffer requires a ``WriterRole`` capability whose
``allowed_statuses`` admits the row's provenance status. Capabilities
cannot be minted by application code: the constructor demands a
module-private token reachable only through the factory functions below,
which are called from ``World`` wiring (and, for the builder role, from
``dump.build`` alone).

The classifier, projector, and renderer hold no capability at all —
there is nothing they can call that writes the log.
"""

from __future__ import annotations

from patternbuffer.model import STATUSES

_TOKEN = object()


class RoleViolation(PermissionError):
    """An append was attempted outside the role-authority matrix."""


class WriterRole:
    """A write capability: a name plus the statuses it may append."""

    __slots__ = ("name", "allowed_statuses")

    def __init__(self, name: str, allowed_statuses: frozenset[str], *, _token: object = None) -> None:
        if _token is not _TOKEN:
            raise RoleViolation(
                "WriterRole cannot be constructed by application code; "
                "capabilities are minted only in World wiring"
            )
        bad = allowed_statuses - STATUSES
        if bad:
            raise ValueError(f"unknown statuses: {sorted(bad)}")
        self.name = name
        self.allowed_statuses = allowed_statuses

    def check(self, status: str) -> None:
        if status not in self.allowed_statuses:
            raise RoleViolation(
                f"role {self.name!r} may not append status {status!r} "
                f"(allowed: {sorted(self.allowed_statuses)})"
            )

    def __repr__(self) -> str:  # pragma: no cover
        return f"WriterRole({self.name!r})"


def _make_engine_roles() -> dict[str, WriterRole]:
    """Mint the engine's writer roles. Called only from World wiring.

    Note what is absent: no role may append ``default`` — it exists only
    in materialization payloads, never in the log (whitepaper §7).
    """
    return {
        "ingestor": WriterRole(
            "ingestor", frozenset({"stated", "observed", "inferred", "assumed"}), _token=_TOKEN
        ),
        "resolver": WriterRole("resolver", frozenset({"generated"}), _token=_TOKEN),
        "truth_maintenance": WriterRole(
            "truth_maintenance", frozenset({"retracted", "inferred"}), _token=_TOKEN
        ),
    }


def _make_builder_role() -> WriterRole:
    """Mint the dump-replay capability. Called only from ``dump.build``.

    The builder may replay any logged status (the dump already carries
    the log as it was) except ``default``, which never appears in a log
    and therefore never in a dump.
    """
    return WriterRole("builder", STATUSES - {"default"}, _token=_TOKEN)
