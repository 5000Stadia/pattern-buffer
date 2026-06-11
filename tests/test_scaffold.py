"""Scaffold sanity: the package imports and the stub model behaves."""

import pytest

import patternbuffer
from patternbuffer.testing import StubModel, StubModelExhausted


def test_package_imports() -> None:
    assert patternbuffer.__version__


def test_stub_replays_in_order_and_records_calls() -> None:
    stub = StubModel([{"a": 1}, {"b": 2}])
    assert stub("first prompt", {"type": "object"}) == {"a": 1}
    assert stub("second prompt", {"type": "object"}) == {"b": 2}
    assert [p for p, _ in stub.calls] == ["first prompt", "second prompt"]


def test_unscripted_call_raises() -> None:
    stub = StubModel()
    with pytest.raises(StubModelExhausted):
        stub("surprise", {})
    assert len(stub.calls) == 1
