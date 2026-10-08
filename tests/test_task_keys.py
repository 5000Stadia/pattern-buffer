"""Model task keys: every schema the engine hands the model callable carries a
frozen `title` from MODEL_TASKS, so hosts route by task, never by prompt
wording; and each call gets a private copy of the schema."""

from __future__ import annotations

from patternbuffer.classify import _BATCH_SCHEMA, _MODEL_SCHEMA
from patternbuffer.ingest import _EXTRACT_SCHEMA
from patternbuffer.model import (
    MODEL_TASKS,
    TASK_ASK_PLAN,
    TASK_CLASSIFY,
    TASK_CLASSIFY_BATCH,
    TASK_EXTRACT,
    TASK_REFER,
    TASK_RESOLVE,
    task_schema,
)
from patternbuffer.porcelain import _ASK_PLAN_SCHEMA
from patternbuffer.refer import _TIER2_SCHEMA
from patternbuffer.thunks import _RESOLVE_SCHEMA


def test_every_task_schema_carries_its_frozen_title() -> None:
    titled = {
        TASK_EXTRACT: _EXTRACT_SCHEMA,
        TASK_CLASSIFY: _MODEL_SCHEMA,
        TASK_CLASSIFY_BATCH: _BATCH_SCHEMA,
        TASK_RESOLVE: _RESOLVE_SCHEMA,
        TASK_REFER: _TIER2_SCHEMA,
        TASK_ASK_PLAN: _ASK_PLAN_SCHEMA,
    }
    assert set(titled) == MODEL_TASKS
    for title, schema in titled.items():
        assert schema["title"] == title
    # Frozen spellings: a rename breaks every host that routes on them.
    assert sorted(MODEL_TASKS) == [
        "patternbuffer_ask_plan", "patternbuffer_classify",
        "patternbuffer_classify_batch", "patternbuffer_extract",
        "patternbuffer_refer", "patternbuffer_resolve",
    ]


def test_task_schema_is_a_private_copy() -> None:
    copy = task_schema(_EXTRACT_SCHEMA)
    copy["additionalProperties"] = False
    copy["properties"]["items"]["mutated"] = True
    assert "additionalProperties" not in _EXTRACT_SCHEMA
    assert "mutated" not in _EXTRACT_SCHEMA["properties"]["items"]


def test_live_calls_carry_titles(tmp_path) -> None:
    from patternbuffer import World

    seen: list[str | None] = []

    def model(prompt, schema):
        seen.append(schema.get("title"))
        if schema.get("title") == TASK_EXTRACT:
            return {"items": [{"entity": "obj:cup", "attribute": "in",
                               "value": "place:kitchen", "value_type": "entity",
                               "status": "stated"}]}
        if schema.get("title") == TASK_CLASSIFY:
            return {"durability": "STATE", "class_confidence": 0.9}
        if schema.get("title") == TASK_CLASSIFY_BATCH:
            return {"verdicts": []}
        raise AssertionError(f"unexpected task {schema.get('title')}")

    w = World(str(tmp_path / "t.world"), model=model, world_id="w:t")
    w.ingest("The cup is in the kitchen.")
    assert seen and all(t in MODEL_TASKS for t in seen)
    assert TASK_EXTRACT in seen
