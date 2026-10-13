"""BUILD-PROFILE-V1 §3: where a book build's time, turns and tokens went.

Usage (repo root, no model call, deterministic):

    PYTHONPATH=src python evals/harness/profile_build.py RUN_DIR

Reads ``usage.jsonl`` (one line per model call), ``objectives.jsonl`` (one line
per unit of work, with its attempts), ``timings.json``, ``receipt.json`` and
``meta.json`` from a ``run_book`` directory, and writes ``profile.json`` and
``profile.md`` beside them. An older run (R26's has stage seconds only) gets the
stage totals, and every figure it cannot measure says ``unmeasured``; the report
never invents a value.

Every what-if is a lower bound: it replays the measured durations and assumes a
call takes as long with more calls in flight as it did with fewer, which R26
showed false (four parallel pass-0 calls each ran slower).

Percentiles are nearest-rank (an actual observed value). Stage wall seconds are
the run's own, rounded to 0.1 s by the receipt.
"""

from __future__ import annotations

import argparse
import heapq
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)

STAGES = ("pass0", "pass1", "escape_repair", "commit", "audit")
UNMEASURED = "unmeasured"
WHATIF_STAGES = ("pass0", "pass1")     # the stages that run on a worker pool
MIN_FIT_CALLS = 5
LOWER_BOUND_NOTE = ("Lower bound: call latency is assumed not to change with concurrency. "
                    "R26 measured four parallel pass-0 calls each running slower.")
OVERLAP_MODEL = (
    "Dependency model (hypothetical, not today's code): a pass-1 chunk's facts can be "
    "classified as soon as that chunk is accepted. The commit's K classification batches "
    "are spread over the N accepted chunks in acceptance order; batch j becomes ready when "
    "chunk ceil(j*N/K) has finished (facts per chunk assumed even). Batches run, with their "
    "measured durations, one at a time on a separate worker. Escape repair, the commit's "
    "other work (its wall minus the summed batch durations) and the audit stay serial after "
    "the last chunk and the last batch, as today. Pass-0 stays as measured.")


# ------------------------------------------------------------------ helpers


def pct(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile (``q`` in 0..1) of ``values``; None when empty."""
    if not values:
        return None
    s = sorted(values)
    return s[max(1, math.ceil(q * len(s))) - 1]


def _r(x: float | None, nd: int = 3) -> float | None:
    return None if x is None else round(x, nd)


def list_schedule(durations: Sequence[float], workers: int | None) -> tuple[float, list[float]]:
    """Give each duration, in order, to the first free worker. Returns the
    makespan and each item's finish time (in input order). ``workers`` None means
    unlimited, so the makespan is the longest item."""
    if not durations:
        return 0.0, []
    if workers is None or workers >= len(durations):
        return max(durations), list(durations)
    free = [0.0] * workers
    heapq.heapify(free)
    finish: list[float] = []
    for d in durations:
        start = heapq.heappop(free)
        heapq.heappush(free, start + d)
        finish.append(start + d)
    return max(finish), finish


def linear_fit(xs: Sequence[float], ys: Sequence[float]) -> dict[str, Any]:
    """Least-squares ``y = a + b*x`` with R². Fewer than ``MIN_FIT_CALLS`` points,
    or zero variance in x or y, is reported as unmeasured, never as a number."""
    n = len(xs)
    if n < MIN_FIT_CALLS:
        return {"n": n, "unmeasured": f"fewer than {MIN_FIT_CALLS} calls ({n})"}
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0:
        return {"n": n, "unmeasured": "zero variance in the token count"}
    if syy == 0:
        return {"n": n, "unmeasured": "zero variance in latency"}
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    return {"n": n, "r2": _r(sxy * sxy / (sxx * syy), 4),
            "seconds_per_1k_tokens": _r(slope * 1000, 3), "intercept_s": _r(my - slope * mx, 3)}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _num(x: Any) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


# ------------------------------------------------------------------- loading


def load_run(run_dir: Path) -> dict[str, Any]:
    """Everything the report reads from ``run_dir``. A missing file is None/[]."""
    return {
        "calls": _read_jsonl(run_dir / "usage.jsonl"),
        "objectives": _read_jsonl(run_dir / "objectives.jsonl"),
        "timings": _read_json(run_dir / "timings.json"),
        "receipt": _read_json(run_dir / "receipt.json"),
        "meta": _read_json(run_dir / "meta.json"),
        "ablation": _read_json(run_dir / "ablation.json"),
    }


def stage_walls(timings: dict | None, receipt: dict | None) -> dict[str, float]:
    """Wall seconds per stage: ``timings.json`` (``<stage>_s``), else the receipt."""
    walls: dict[str, float] = {}
    if receipt:
        for name, st in (receipt.get("stages") or {}).items():
            v = _num((st or {}).get("seconds"))
            if v is not None:
                walls[name] = v
    if timings:
        for name in (*STAGES, "battery"):
            v = _num(timings.get(f"{name}_s"))
            if v is not None:
                walls[name] = v
    return walls


def workers_for(stage: str, meta: dict | None) -> int:
    """Pool size of a stage in ``run_book``: pass-1 and parallel pass-0 run on 4
    workers; everything else is serial."""
    if stage == "pass1":
        return 4
    if stage == "pass0" and (meta or {}).get("pass0_mode") == "parallel":
        return 4
    return 1


def _max_concurrent(calls: Iterable[dict[str, Any]]) -> int | None:
    events: list[tuple[float, int]] = []
    for c in calls:
        s, lat = _num(c.get("started")), _num(c.get("latency_s"))
        if s is not None and lat is not None:
            events += [(s, 1), (s + lat, -1)]
    if not events:
        return None
    cur = best = 0
    for _, d in sorted(events, key=lambda e: (e[0], e[1])):
        cur += d
        best = max(best, cur)
    return best


# --------------------------------------------------------------- stage table


def _call_stats(calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Latency, rate, turn and API figures from one stage's calls."""
    lat = [v for c in calls if (v := _num(c.get("latency_s"))) is not None]
    out: dict[str, Any] = {"calls_with_latency": len(lat)}
    if not lat:
        out.update(latency_sum_s=UNMEASURED, latency_p50_s=UNMEASURED, latency_p90_s=UNMEASURED,
                   latency_max_s=UNMEASURED, out_tok_per_s_median=UNMEASURED,
                   out_tok_per_s_p10=UNMEASURED, max_concurrent_calls=UNMEASURED)
    else:
        rates = [c["output_tokens"] / c["latency_s"] for c in calls
                 if _num(c.get("latency_s")) and c.get("usage_reported") and c.get("output_tokens")]
        out.update(latency_sum_s=_r(sum(lat)), latency_p50_s=_r(pct(lat, 0.5)),
                   latency_p90_s=_r(pct(lat, 0.9)), latency_max_s=_r(max(lat)),
                   out_tok_per_s_median=_r(pct(rates, 0.5), 2) if rates else UNMEASURED,
                   out_tok_per_s_p10=_r(pct(rates, 0.1), 2) if rates else UNMEASURED,
                   max_concurrent_calls=_max_concurrent(calls))
    turns = [v for c in calls if (v := _num(c.get("num_turns"))) is not None]
    out["turns_per_call_median"] = _r(pct(turns, 0.5), 1) if turns else UNMEASURED
    out["turns_per_call_max"] = _r(max(turns), 1) if turns else UNMEASURED
    both = [(a / 1000.0, l) for c in calls
            if (a := _num(c.get("api_duration_ms"))) is not None
            and (l := _num(c.get("latency_s"))) is not None]
    if both and sum(l for _, l in both) > 0:
        api, tot = sum(a for a, _ in both), sum(l for _, l in both)
        out["api_time_share_of_latency"] = _r(api / tot, 3)
        out["harness_overhead_s"] = _r(tot - api)
    else:
        out["api_time_share_of_latency"] = UNMEASURED
        out["harness_overhead_s"] = UNMEASURED
    return out


def _tokens_cost(calls: list[dict[str, Any]]) -> dict[str, Any]:
    costs = [c.get("cost_usd") for c in calls]
    return {"calls": len(calls),
            "input_tokens": sum(int(c.get("input_tokens") or 0) for c in calls),
            "output_tokens": sum(int(c.get("output_tokens") or 0) for c in calls),
            "cached_tokens": sum(int(c.get("cache_read_tokens") or 0) for c in calls),
            "cost_usd": _r(sum(float(x) for x in costs if x is not None), 6),
            "cost_known": all(x is not None for x in costs)}


def stage_table(data: dict[str, Any], walls: dict[str, float]) -> list[dict[str, Any]]:
    calls, objs, meta, receipt = data["calls"], data["objectives"], data["meta"], data["receipt"]
    labelled = any(c.get("stage") for c in calls)
    seen = {c.get("stage") for c in calls} | {o.get("stage") for o in objs}
    names = [s for s in STAGES if s in walls or s in seen]
    names += sorted((seen | set(walls)) - set(STAGES) - {None})
    total = sum(walls.values())
    rows: list[dict[str, Any]] = []
    for name in names:
        wall = walls.get(name)
        sc = [c for c in calls if c.get("stage") == name] if labelled else []
        so = [o for o in objs if o.get("stage") == name]
        workers = workers_for(name, meta)
        row: dict[str, Any] = {
            "stage": name, "wall_s": _r(wall, 1) if wall is not None else UNMEASURED,
            "share": _r(wall / total, 4) if wall is not None and total else UNMEASURED,
            "workers": workers, "objectives": len(so) if objs else UNMEASURED}
        if labelled:
            row.update(_tokens_cost(sc))
            row.update(_call_stats(sc))
        else:
            rst = ((receipt or {}).get("stages") or {}).get(name)
            if rst:   # an R27-era run: spend by stage from the receipt, no per-call fields
                row.update(calls=rst.get("calls"), input_tokens=rst.get("input_tokens"),
                           output_tokens=rst.get("output_tokens"),
                           cached_tokens=rst.get("cache_read_tokens"),
                           cost_usd=rst.get("cost_usd"), cost_known=rst.get("cost_known"))
            else:
                row.update(calls=UNMEASURED, input_tokens=UNMEASURED, output_tokens=UNMEASURED,
                           cached_tokens=UNMEASURED, cost_usd=UNMEASURED, cost_known=UNMEASURED)
            row.update(_call_stats([]))
        s = row.get("latency_sum_s")
        row["utilization"] = (_r(s / (wall * workers), 4)
                              if isinstance(s, float) and wall else UNMEASURED)
        rows.append(row)
    if labelled:
        un = [c for c in calls if not c.get("stage")]
        if un:
            row = {"stage": "(unlabelled)", "wall_s": UNMEASURED, "share": UNMEASURED,
                   "workers": UNMEASURED, "objectives": UNMEASURED, "utilization": UNMEASURED}
            row.update(_tokens_cost(un))
            row.update(_call_stats(un))
            rows.append(row)
    return rows


# ----------------------------------------------------- model and effort (STAGE-MODELS-V1)


def model_effort_table(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (model, effort) for each stage that used more than one, with that
    group's tokens, cost and latency figures. A call line without ``effort`` (a run before
    STAGE-MODELS-V1) ran at the CLI default, so its effort is None. Stages that used a
    single (model, effort) have no rows: their table row already says it all."""
    rows: list[dict[str, Any]] = []
    stages = [s for s in dict.fromkeys(c.get("stage") for c in calls) if s]
    stages = [s for s in STAGES if s in stages] + sorted(set(stages) - set(STAGES))
    for stage in stages:
        groups: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
        for c in calls:
            if c.get("stage") == stage:
                groups.setdefault((str(c.get("model")), c.get("effort")), []).append(c)
        if len(groups) < 2:
            continue
        for (model, effort), cs in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
            rows.append({"stage": stage, "model": model, "effort": effort,
                         **_tokens_cost(cs), **_call_stats(cs)})
    return rows


# --------------------------------------------------------------------- turns


def _is_retry(attempts: list[dict[str, Any]], i: int) -> bool:
    """An attempt that follows one that did not settle the unit."""
    return i > 0 and attempts[i - 1].get("outcome") != "accepted"


def turns_table(objs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per stage: attempts-per-objective histogram, the units that needed a retry
    (an attempt after a failed one; a glean round after an accepted establish is
    not a retry) with the reasons, and the seconds the retries took."""
    out: list[dict[str, Any]] = []
    for stage in dict.fromkeys(o["stage"] for o in objs if o.get("stage")):
        so = [o for o in objs if o["stage"] == stage]
        hist: dict[str, int] = {}
        retried: list[dict[str, Any]] = []
        retry_s = 0.0
        for o in so:
            att = o.get("attempts") or []
            hist[str(len(att))] = hist.get(str(len(att)), 0) + 1
            idx = [i for i in range(len(att)) if _is_retry(att, i)]
            if idx:
                retried.append({"unit": o["unit"], "accepted": o.get("accepted"),
                                "reasons": [a.get("reason") or a.get("outcome")
                                            for a in att if a.get("outcome") != "accepted"]})
                retry_s += sum(att[i].get("seconds") or 0.0 for i in idx)
        out.append({"stage": stage, "objectives": len(so),
                    "accepted": sum(1 for o in so if o.get("accepted")),
                    "attempts_histogram": dict(sorted(hist.items())),
                    "retried": retried, "retry_seconds": _r(retry_s, 1)})
    return out


# ------------------------------------------------------------------ ceilings


def _ordered(objs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Objectives in measured submission order (first attempt's start)."""
    def key(o):
        att = o.get("attempts") or []
        return (att[0].get("started") if att else 0.0, str(o.get("unit")))
    return sorted(objs, key=key)


def stage_ceilings(stage: str, objs: list[dict[str, Any]], wall: float | None,
                   current_workers: int) -> dict[str, Any]:
    so = _ordered([o for o in objs if o.get("stage") == stage])
    full = [float(o.get("seconds") or 0.0) for o in so]
    first = [(o, float(((o.get("attempts") or [{}])[0]).get("seconds") or 0.0)) for o in so]
    never = [(o, s) for o, s in first if not o.get("accepted")]
    kept = [s for o, s in first if o.get("accepted")]
    longest = max(so, key=lambda o: o.get("seconds") or 0.0)
    res: dict[str, Any] = {
        "stage": stage, "objectives": len(so),
        "measured_wall_s": _r(wall, 1) if wall is not None else UNMEASURED,
        "current_workers": current_workers,
        "floor_s": _r(max(full), 3), "floor_unit": longest["unit"],
        "serial_sum_s": _r(sum(full), 3),
        "never_accepted": [{"unit": o["unit"], "first_attempt_s": _r(s, 3)} for o, s in never],
        "would_still_fail": len(never),
        "what_if": [], "note": LOWER_BOUND_NOTE}
    # only the pooled stages could use more workers; the others are serial in the code
    for w in sorted({1, current_workers, 4, 8}) if stage in WHATIF_STAGES else ():
        span, _ = list_schedule(full, w)
        nr, _ = list_schedule(kept, w)
        res["what_if"].append({"workers": w, "current": w == current_workers,
                               "all_attempts_s": _r(span, 3),
                               "no_retries_s": _r(nr, 3) if kept else UNMEASURED})
    return res


def overlapped_pipeline(objs: list[dict[str, Any]], walls: dict[str, float],
                        meta: dict | None) -> dict[str, Any]:
    """The hypothetical pipeline that classifies each chunk's facts as it is
    accepted (the dependency model is ``OVERLAP_MODEL``)."""
    base: dict[str, Any] = {"model": OVERLAP_MODEL, "note": LOWER_BOUND_NOTE}
    chunks = _ordered([o for o in objs if o.get("stage") == "pass1"])
    batches = sorted((o for o in objs if o.get("stage") == "commit"
                      and str(o.get("unit", "")).startswith("classify:")),
                     key=lambda o: o["unit"])
    if not chunks or not batches or "pass1" not in walls or "commit" not in walls:
        return {**base, UNMEASURED: "needs pass-1 chunk and classification-batch objectives "
                                   "and stage walls"}
    workers = workers_for("pass1", meta)
    _, fin = list_schedule([float(o["seconds"]) for o in chunks], workers)
    order = sorted(fin)                          # chunk completion times, ascending
    n, k = len(order), len(batches)
    cls_end, ready_at = 0.0, []
    for j, b in enumerate(batches, 1):
        ready = order[math.ceil(j * n / k) - 1]
        ready_at.append(ready)
        cls_end = max(cls_end, ready) + float(b["seconds"])
    phase = max(order[-1], cls_end)
    cls_total = sum(float(b["seconds"]) for b in batches)
    other_commit = max(walls["commit"] - cls_total, 0.0)
    total = (walls.get("pass0", 0.0) + phase + walls.get("escape_repair", 0.0) + other_commit
             + walls.get("audit", 0.0))
    return {**base, "pass1_phase_s": _r(phase, 3), "last_chunk_done_s": _r(order[-1], 3),
            "classification_done_s": _r(cls_end, 3), "classification_total_s": _r(cls_total, 3),
            "batch_ready_s": [_r(x, 3) for x in ready_at],
            "commit_other_s": _r(other_commit, 3), "total_s": _r(total, 3),
            "measured_total_s": _r(sum(walls.values()), 3),
            "saved_s": _r(sum(walls.values()) - total, 3)}


def build_whatifs(ceilings: list[dict[str, Any]], walls: dict[str, float],
                  overlap: dict[str, Any]) -> list[dict[str, Any]]:
    """Whole-build totals: the measured total with one stage's wall swapped for
    its replay."""
    measured = sum(walls.values())
    rows = [{"scenario": "measured", "total_s": _r(measured, 1)}]
    for c in ceilings:
        wall = walls.get(c["stage"])
        if wall is None:
            continue
        for w in c["what_if"]:
            if not w["current"]:
                rows.append({"scenario": f"{c['stage']} on {w['workers']} worker(s)",
                             "total_s": _r(measured - wall + w["all_attempts_s"], 1)})
        rows.append({"scenario": f"{c['stage']} with unlimited workers (floor)",
                     "total_s": _r(measured - wall + c["floor_s"], 1)})
        now = next((w for w in c["what_if"] if w["current"]), None)
        if now and now["no_retries_s"] != UNMEASURED and c["stage"] == "pass1":
            rows.append({"scenario": f"{c['stage']} without retries (first attempts only)",
                         "total_s": _r(measured - wall + now["no_retries_s"], 1)})
    if overlap.get("total_s") is not None:
        rows.append({"scenario": "overlapped pipeline (hypothetical)",
                     "total_s": overlap["total_s"]})
    return rows


# ------------------------------------------------------------ output-bound fit


def fit_report(calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Latency against output tokens and against input tokens (cached tokens
    counted as input), over every call and per stage."""
    def fits(cs: list[dict[str, Any]]) -> dict[str, Any]:
        pts = [c for c in cs if _num(c.get("latency_s")) is not None and c.get("usage_reported")]
        lat = [float(c["latency_s"]) for c in pts]
        out_t = [float(c.get("output_tokens") or 0) for c in pts]
        in_t = [float(int(c.get("input_tokens") or 0) + int(c.get("cache_read_tokens") or 0)
                      + int(c.get("cache_write_tokens") or 0)) for c in pts]
        return {"latency_vs_output_tokens": linear_fit(out_t, lat),
                "latency_vs_input_tokens": linear_fit(in_t, lat)}
    res = {"all": fits(calls)}
    for st in dict.fromkeys(c.get("stage") for c in calls if c.get("stage")):
        res[st] = fits([c for c in calls if c.get("stage") == st])
    return res


# ---------------------------------------------------------------- the report


def build_profile(run_dir: Path) -> dict[str, Any]:
    """The whole report as data (``profile.json``)."""
    data = load_run(run_dir)
    walls = stage_walls(data["timings"], data["receipt"])
    objs, calls, meta = data["objectives"], data["calls"], data["meta"]
    table = stage_table(data, walls)
    ceil_stages = [s for s in dict.fromkeys(o["stage"] for o in objs if o.get("stage"))
                   if s in STAGES]
    ceilings = [stage_ceilings(s, objs, walls.get(s), workers_for(s, meta)) for s in ceil_stages]
    overlap = overlapped_pipeline(objs, walls, meta)
    measured_latency = any(_num(c.get("latency_s")) is not None for c in calls)
    notes: list[str] = []
    if not calls:
        notes.append("no usage.jsonl lines: per-call figures are unmeasured")
    elif not measured_latency:
        notes.append("usage.jsonl has no latency_s (a run before BUILD-PROFILE-V1): "
                     "per-call figures are unmeasured")
    elif not any(c.get("stage") for c in calls):
        notes.append("usage.jsonl calls carry no stage label: per-stage call figures are unmeasured")
    if not objs:
        notes.append("no objectives.jsonl: turns, floors and what-ifs are unmeasured")
    if not walls:
        notes.append("no timings.json or receipt.json: stage wall seconds are unmeasured")
    ablation = data["ablation"] or {}
    return {
        "run_dir": run_dir.name,
        "notes": notes,
        "total_wall_s": _r(sum(walls.values()), 1) if walls else UNMEASURED,
        "stages": table,
        "by_model_effort": model_effort_table(calls),
        "turns": turns_table(objs),
        "ceilings": ceilings,
        "build_what_ifs": build_whatifs(ceilings, walls, overlap) if ceilings else UNMEASURED,
        "overlapped_pipeline": overlap,
        "output_bound_fit": fit_report(calls) if measured_latency else UNMEASURED,
        "ablation": [{"stage": s["stage"], "result": ablation.get(s["stage"], "not measured")}
                     for s in table if s["stage"] != "(unlabelled)"],
    }


def _f(x: Any, nd: int = 1) -> str:
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def _pc(x: Any) -> str:
    return f"{x * 100:.1f}%" if isinstance(x, float) else str(x)


def render_md(p: dict[str, Any]) -> str:
    """``profile.md``: the same report for a reader."""
    L: list[str] = [f"# Build profile: {p['run_dir']}", ""]
    L.append(f"Total wall: {_f(p['total_wall_s'])}{'' if p['total_wall_s'] == UNMEASURED else ' s'}. Percentiles are nearest-rank. "
             "Stage wall seconds are rounded to 0.1 s by the receipt.")
    for n in p["notes"]:
        L.append(f"- NOTE: {n}")
    L += ["", "## Per stage", "",
          "| stage | wall s | share | workers | calls | objectives | latency sum s | utilization | "
          "p50 s | p90 s | max s | tokens in | tokens out | cached | out tok/s median | "
          "out tok/s p10 | cost |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in p["stages"]:
        cost = r["cost_usd"]
        cost = (f"{cost:.4f}" + ("" if r.get("cost_known") is True else " (lower bound)")
                if isinstance(cost, float) else str(cost))
        L.append("| " + " | ".join([
            r["stage"], _f(r["wall_s"]), _pc(r["share"]), str(r["workers"]), str(r["calls"]),
            str(r["objectives"]), _f(r["latency_sum_s"]), _pc(r["utilization"]),
            _f(r["latency_p50_s"]), _f(r["latency_p90_s"]), _f(r["latency_max_s"]),
            str(r["input_tokens"]), str(r["output_tokens"]), str(r["cached_tokens"]),
            _f(r["out_tok_per_s_median"]), _f(r["out_tok_per_s_p10"]), cost]) + " |")
    L += ["", "### CLI turns and API time (claude shim only)", "",
          "| stage | turns/call median | turns/call max | API time share of latency | "
          "harness overhead s (latency minus API) | max concurrent calls |",
          "|---|---|---|---|---|---|"]
    for r in p["stages"]:
        L.append("| " + " | ".join([r["stage"], _f(r["turns_per_call_median"]),
                                    _f(r["turns_per_call_max"]), _pc(r["api_time_share_of_latency"]),
                                    _f(r["harness_overhead_s"]),
                                    str(r["max_concurrent_calls"])]) + " |")
    if p.get("by_model_effort"):
        L += ["", "### Stages that mixed models or efforts (STAGE-MODELS-V1)", "",
              "| stage | model | effort | calls | tokens in | tokens out | cached | latency sum s | "
              "p50 s | p90 s | out tok/s median | cost |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in p["by_model_effort"]:
            cost = r["cost_usd"]
            cost = (f"{cost:.4f}" + ("" if r.get("cost_known") is True else " (lower bound)")
                    if isinstance(cost, float) else str(cost))
            L.append("| " + " | ".join([
                r["stage"], r["model"], "default" if r["effort"] is None else str(r["effort"]),
                str(r["calls"]), str(r["input_tokens"]), str(r["output_tokens"]),
                str(r["cached_tokens"]), _f(r["latency_sum_s"]), _f(r["latency_p50_s"]),
                _f(r["latency_p90_s"]), _f(r["out_tok_per_s_median"]), cost]) + " |")
    L += ["", "## Turns to an objective", ""]
    if not p["turns"]:
        L.append(f"{UNMEASURED}: no objectives.jsonl.")
    for t in p["turns"]:
        L.append(f"- **{t['stage']}**: {t['objectives']} objectives, {t['accepted']} accepted; "
                 f"attempts per objective {t['attempts_histogram']}; "
                 f"retry seconds {_f(t['retry_seconds'])}.")
        for u in t["retried"]:
            L.append(f"  - {u['unit']} (accepted: {u['accepted']}): {u['reasons']}")
    L += ["", "## Ceilings", "", "Floor = the stage's longest single objective, the most "
          "parallelism can buy. " + LOWER_BOUND_NOTE, ""]
    if not p["ceilings"]:
        L.append(f"{UNMEASURED}: no objectives.jsonl.")
    for c in p["ceilings"]:
        L.append(f"### {c['stage']}: {c['objectives']} objectives, measured wall "
                 f"{_f(c['measured_wall_s'])} s, {c['current_workers']} worker(s) today")
        L.append(f"Floor {_f(c['floor_s'], 2)} s ({c['floor_unit']}); serial sum "
                 f"{_f(c['serial_sum_s'], 2)} s.")
        if c["what_if"]:
            L += ["", "| workers | list-scheduling replay s | no retries s |", "|---|---|---|"]
        for w in c["what_if"]:
            L.append(f"| {w['workers']}{' (today)' if w['current'] else ''} | "
                     f"{_f(w['all_attempts_s'], 2)} | {_f(w['no_retries_s'], 2)} |")
        L.append("")
        never = (f"Never accepted, shown separately (would still fail: {c['would_still_fail']}): "
                 + (", ".join(f"{u['unit']} ({_f(u['first_attempt_s'], 2)} s)"
                              for u in c["never_accepted"]) or "none") + ".")
        if c["what_if"]:
            L.append("No-retries replay: each objective's first attempt's duration, as if accepted. "
                     + never + " " + c["note"])
        else:
            L.append("Serial in the code, so no worker what-if. " + never)
        L.append("")
    L += ["", "### Whole-build totals", ""]
    if p["build_what_ifs"] == UNMEASURED:
        L.append(UNMEASURED)
    else:
        L += ["| scenario | total s |", "|---|---|"]
        L += [f"| {r['scenario']} | {_f(r['total_s'])} |" for r in p["build_what_ifs"]]
        L += ["", LOWER_BOUND_NOTE]
    ov = p["overlapped_pipeline"]
    L += ["", "### Overlapped pipeline (hypothetical)", "", ov["model"], ""]
    if UNMEASURED in ov:
        L.append(f"{UNMEASURED}: {ov[UNMEASURED]}.")
    else:
        L.append(f"Pass-1 plus classification phase {_f(ov['pass1_phase_s'], 2)} s (last chunk "
                 f"{_f(ov['last_chunk_done_s'], 2)} s, classification done "
                 f"{_f(ov['classification_done_s'], 2)} s); build total {_f(ov['total_s'])} s "
                 f"against measured {_f(ov['measured_total_s'])} s (saves {_f(ov['saved_s'])} s). "
                 + ov["note"])
    L += ["", "## Is a call slow because of what it writes or what it reads?", ""]
    fit = p["output_bound_fit"]
    if fit == UNMEASURED:
        L.append(f"{UNMEASURED}: no call latencies.")
    else:
        L += ["Least squares of latency on tokens (input counts cached tokens). A fit under "
              f"{MIN_FIT_CALLS} calls, or with zero variance, is unmeasured.", "",
              "| scope | vs output tokens | vs input tokens |", "|---|---|---|"]

        def cell(f: dict) -> str:
            if "unmeasured" in f:
                return f"{UNMEASURED} ({f['unmeasured']})"
            return (f"R2 {f['r2']:.3f}, {f['seconds_per_1k_tokens']:.2f} s per 1k tokens, "
                    f"n={f['n']}")
        for scope, f in fit.items():
            L.append(f"| {scope} | {cell(f['latency_vs_output_tokens'])} | "
                     f"{cell(f['latency_vs_input_tokens'])} |")
    L += ["", "## Which stages matter for quality (ablation)", "",
          "Measured by ablation runs against the answer key (`grade_book.py`): metered runs, "
          "not part of this report. Filled from `ablation.json` (stage to result) when it exists.",
          "", "| stage | ablation result |", "|---|---|"]
    L += [f"| {a['stage']} | {a['result']} |" for a in p["ablation"]]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir", help="a run_book output directory")
    args = ap.parse_args(argv)
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        raise SystemExit(f"ABORT: {run_dir} is not a directory")
    profile = build_profile(run_dir)
    (run_dir / "profile.json").write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n")
    md = render_md(profile)
    (run_dir / "profile.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
