"""The package's self-reported version must match what it ships as.

`patternbuffer.__version__` sat at "0.0.1" through the 0.1 and 0.2
releases while pyproject said otherwise. A host doing capability or
compatibility detection against `__version__` — the obvious surface for
it — would have read a version three releases stale.

pyproject is the single source of truth; this test is the guard that
keeps the exported literal honest.
"""

import tomllib
from pathlib import Path

import patternbuffer

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _declared_version() -> str:
    with _PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def test_version_matches_pyproject():
    assert patternbuffer.__version__ == _declared_version(), (
        f"patternbuffer.__version__ is {patternbuffer.__version__!r} but "
        f"pyproject declares {_declared_version()!r} — update the literal in "
        "src/patternbuffer/__init__.py when bumping the release."
    )


def test_version_is_exported():
    """Hosts detect against it, so it stays a public name."""
    assert "__version__" in patternbuffer.__all__
