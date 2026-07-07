"""Value codec: exact-decimal quantities as tagged JSON scalars.

EXACT-DECIMAL-QUANTITIES-V1: a quantity that must fold exactly (money, any
real ledger) is a Python ``Decimal`` in memory and the reserved tag dict
``{"$decimal": "12.50"}`` on every JSON boundary — storage, dump, prompts,
host payloads. ``str(Decimal)`` preserves authored scale (``12.50`` stays
``12.50``); no float ever touches the number. Fiction floats stay floats:
the Decimal path is entered only by values that are Decimal.

Fold arithmetic (`exact_sum`/`exact_div`) runs under one explicit, fixed
context (`MONEY_CTX`) so builds are byte-deterministic across platforms
(P7) regardless of the process's ambient decimal context. Mixing exact
Decimal with float in one fold is an authoring smell and raises; Decimal
with int promotes losslessly.
"""

from __future__ import annotations

import decimal
from decimal import Decimal, localcontext
from typing import Any, Iterable

DEC_TAG = "$decimal"
"""Reserved key in value-space (LEXICON). Only an exact one-key dict whose
value parses as a finite Decimal is reconstructed; anything else passes
through untouched (the collision guard)."""

MONEY_CTX = decimal.Context(prec=50, rounding=decimal.ROUND_HALF_EVEN)
"""The one context all Decimal fold arithmetic runs under. Addition is
exact for any realistic ledger within prec=50; division (avg) rounds
HALF_EVEN — named and deterministic."""


def _is_finite_dec_str(s: object) -> bool:
    if not isinstance(s, str):
        return False
    try:
        return Decimal(s).is_finite()
    except decimal.InvalidOperation:
        return False


def encode_value(v: Any) -> Any:
    """One in-memory scalar -> its JSON-safe form (Decimal -> tag dict)."""
    if isinstance(v, Decimal):
        return {DEC_TAG: str(v)}
    return v


def decode_value(v: Any) -> Any:
    """One JSON-safe scalar -> in-memory (exact tag dict -> Decimal)."""
    if isinstance(v, dict) and set(v) == {DEC_TAG} and _is_finite_dec_str(v[DEC_TAG]):
        return Decimal(v[DEC_TAG])
    return v


def json_default(o: Any) -> Any:
    """``json.dumps(..., default=json_default)`` for internal serialization."""
    if isinstance(o, Decimal):
        return {DEC_TAG: str(o)}
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def decode_hook(d: dict) -> Any:
    """``json.loads(..., object_hook=decode_hook)``: reconstruct tag dicts."""
    return decode_value(d)


def encode_out(obj: Any) -> Any:
    """Recursively encode Decimal leaves in a host-facing payload.

    Porcelain/neighborhood public returns wrap in this at the return
    statement (one wrapper per verb) so no field — present or future —
    can leak a raw Decimal into the plain-JSON contract.
    """
    if isinstance(obj, Decimal):
        return {DEC_TAG: str(obj)}
    if isinstance(obj, dict):
        return {k: encode_out(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [encode_out(v) for v in obj]
    return obj


def check_no_mix(values: Iterable[Any], *, ids: Iterable[str] = ()) -> None:
    """Raise if exact Decimal and float coexist in one fold's value set.

    Runs before ANY rollup op (sum/avg/min/max — count validates with the
    rest): a mixed representation on one attribute is an authoring smell
    to surface, never to silently promote."""
    vals = list(values)
    if any(isinstance(v, Decimal) for v in vals) and any(
        isinstance(v, float) for v in vals
    ):
        where = ", ".join(ids)
        raise ValueError(
            "exact-decimal and float quantities mixed in one fold"
            + (f" ({where})" if where else "")
            + "; author one representation per attribute"
        )


def exact_sum(values: Iterable[Any], *, ids: Iterable[str] = ()) -> Any:
    """Sum a fold's values: any-Decimal => Decimal-exact under MONEY_CTX
    (ints promote losslessly); all-float/int => the native sum, unchanged."""
    vals = list(values)
    check_no_mix(vals, ids=ids)
    if any(isinstance(v, Decimal) for v in vals):
        with localcontext(MONEY_CTX):
            return sum(
                (v if isinstance(v, Decimal) else Decimal(v) for v in vals),
                Decimal(0),
            )
    return sum(vals)


def exact_div(total: Any, count: int) -> Any:
    """Division for avg: Decimal path under MONEY_CTX (HALF_EVEN), else native."""
    if isinstance(total, Decimal):
        with localcontext(MONEY_CTX):
            return total / Decimal(count)
    return total / count
