"""The second-writer guard: one live World per file (ADOPTION), enforced.

Construct's run 5 lost a turn when a second handle on its play file re-planned
an attribute declaration the first had already written: "cannot declare
semantics for attribute knows after folded data already exists". A handle that
notices another connection's commit now raises SecondWriter instead of
re-planning, serving stale reads or minting a clashing row id.
"""

import sqlite3

import pytest

from patternbuffer import SecondWriter, World
from patternbuffer.testing import StubModel, rule_classifier_fallback


def _world(path, **kw) -> World:
    return World(path, world_id="w:t",
                 model=StubModel(fallback=rule_classifier_fallback()), **kw)


def _knows_default(attr: str):
    return {"arity": "set_valued"} if attr == "knows" else None


def _item(value: str) -> dict:
    return {"entity": "person:mara", "attribute": "knows", "value": value,
            "valid_from": 0.0}


def test_the_construct_case_raises_second_writer(tmp_path) -> None:
    path = tmp_path / "play.world"
    a = _world(path, attribute_default=_knows_default)
    b = _world(path, attribute_default=_knows_default)
    a.porcelain.ingest_structured([_item("every sack by weight")], classify="defer")
    with pytest.raises(SecondWriter, match="One live World per file"):
        b.porcelain.ingest_structured([_item("the stink")], classify="defer")
    a.close()
    b.close()


def test_a_stale_reader_raises_instead_of_answering(tmp_path) -> None:
    path = tmp_path / "w.world"
    a = _world(path)
    b = _world(path)
    a.porcelain.ingest_structured([{"entity": "obj:key", "attribute": "in",
                                    "value": "place:hall", "valid_from": 0.0}],
                                  classify="defer")
    with pytest.raises(SecondWriter):
        b.locate("obj:key")
    # the guard latches: later calls keep raising
    with pytest.raises(SecondWriter):
        b.buffer.head()
    a.close()
    b.close()


def test_the_writer_itself_is_unaffected_and_a_reopen_sees_everything(tmp_path) -> None:
    path = tmp_path / "w.world"
    a = _world(path)
    b = _world(path)
    a.porcelain.ingest_structured([_item("x")], classify="defer")
    assert a.buffer.head() >= 1          # its own commits never trip it
    b.close()
    c = _world(path)                      # a reopen starts clean
    assert c.buffer.head() == a.buffer.head()
    a.close()
    c.close()


def test_sequential_reopen_after_close_is_fine(tmp_path) -> None:
    path = tmp_path / "w.world"
    a = _world(path)
    a.porcelain.ingest_structured([_item("x")], classify="defer")
    a.close()
    b = _world(path)
    b.porcelain.ingest_structured([_item("y")], classify="defer")
    b.close()


def test_a_raw_outside_commit_is_noticed(tmp_path) -> None:
    path = tmp_path / "w.world"
    a = _world(path)
    raw = sqlite3.connect(path)
    raw.execute("INSERT INTO world_meta (key, value) VALUES ('probe', '1')")
    raw.commit()
    raw.close()
    with pytest.raises(SecondWriter):
        a.buffer.head()
    a.close()
