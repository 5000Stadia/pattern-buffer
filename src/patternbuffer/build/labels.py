"""The build label: which step a model call serves (BUILD-LIBRARY-V1 §4, §6).

Every model call the library makes runs inside a label, ``{"stage", "unit"}``
(BUILD-PROFILE-V1's scheme): ``stage="extract"``, ``unit="chunk:NN"`` for a
chunk, and ``stage="registry"``, ``unit="pass:<category>"`` for a category
pass. The label is a ``contextvars.ContextVar``. Each pool submission is run in
its own ``contextvars.copy_context()``, taken at submission time inside its
label (k1), so the label, and every context variable the caller set before the
call, is visible inside the worker.

A host reads the label from its model callable or its timing log with
:func:`current_label`; the eval harness copies it into its usage ledger,
whose stage map then routes the call (STAGE-MODELS-V1).
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator

_LABEL: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "patternbuffer_build_label", default=None)


@contextmanager
def label(*, stage: str, unit: str) -> Iterator[None]:
    """Label every model call made inside this block."""
    token = _LABEL.set({"stage": stage, "unit": unit})
    try:
        yield
    finally:
        _LABEL.reset(token)


def current_label() -> dict[str, str] | None:
    """The label in force here, as ``{"stage", "unit"}``, or None outside one."""
    found = _LABEL.get()
    return dict(found) if found is not None else None


def labelled_context(stage: str, unit: str) -> contextvars.Context:
    """A copy of the current context taken inside the label: what one pool
    submission runs in (``ctx.run(task)``). One copy per submission, never
    shared."""
    with label(stage=stage, unit=unit):
        return contextvars.copy_context()
