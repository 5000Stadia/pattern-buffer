"""MERGE-GATE-V1 measurement runner (R25 part A): the metered pass mark (part 2),
a dry run that counts it without a model, and the free pass-mark measures.

The registries are the five stored ones; no pass-0 or pass-1 is re-run. Each
registry is seeded as R24's commit leaves it, then the REAL gate (the pipeline's
model, here ``model_shim.get_model()``) is asked every batch of lexical
candidates and its `same` verdicts are applied, exactly as ``Pipeline.commit``
does. Two repetitions show the run-to-run disagreement.

    # what WOULD run: candidate / batch / call counts and a token estimate;
    # no model is imported or called, nothing is written
    PYTHONPATH=src python evals/harness/run_merge_gate_metered.py --dry-run

    # the metered measurement (72 calls at batch size 25): needs Kabe's yes first
    PYTHONPATH=src python evals/harness/run_merge_gate_metered.py OUT_DIR [--reps 2]

    # the free measures (no model): gold-oracle gate and all-unsure gate
    PYTHONPATH=src python evals/harness/run_merge_gate_metered.py --free OUT_DIR

Metered mode writes ``OUT_DIR/rep<N>/<registry>.json`` (the effect, with the
gate's full report), ``OUT_DIR/meta.json`` and the scoring against the spec's
part-2 pass mark (``scoring.json``, ``SCORING.md``):

- precision: no `same` on any pair whose cards resolve to different gold
  entities, in either repetition;
- recall: at least 8 of the 11 gold-same pairs merged, in each repetition;
- F1 not below R24's default in any registry, in each repetition;
- unlabelled candidates: the number of `same` verdicts, with 20 sampled pairs
  to look over (not scored);
- run to run: the pairs whose verdict differs between the repetitions.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import grade_registry as gr
import merge_gate as mg

logger = logging.getLogger("merge_gate_metered")

RESULTS = ROOT / "evals" / "results"
REGISTRIES: dict[str, Path] = {
    "r23-run1": RESULTS / "2026-10-10-r23-pass0-baseline" / "run1" / "registry.json",
    "r23-run2": RESULTS / "2026-10-10-r23-pass0-baseline" / "run2" / "registry.json",
    "r26-seq": RESULTS / "2026-10-10-r26-build-timings" / "seq" / "registry.json",
    "r26-par1b": RESULTS / "2026-10-10-r26-build-timings" / "par1b" / "registry.json",
    "r26-par2b": RESULTS / "2026-10-10-r26-build-timings" / "par2b" / "registry.json",
}
#: Part-2 pass mark (spec): recall floor over the 11 gold-same pairs, sample size.
RECALL_MIN, RECALL_OF, SAMPLE_SIZE, SAMPLE_SEED = 8, 11, 20, 25
#: Token estimates: ~4 characters per token in; the answer is one short entry per pair.
CHARS_PER_TOKEN, OUT_TOKENS_PER_PAIR, OUT_TOKENS_PER_CALL = 4, 45, 30
#: What ``model_shim.claude_model`` wraps around a prompt (instruction text, schema JSON).
SHIM_WRAPPER_CHARS = 200


def story_segments() -> list[str]:
    import run_pass0_baseline  # the chapter-test segmentation lives there
    return run_pass0_baseline.story_segments()


def select(names: Sequence[str] | None) -> dict[str, Path]:
    if not names:
        return dict(REGISTRIES)
    unknown = [n for n in names if n not in REGISTRIES]
    if unknown:
        raise SystemExit(f"unknown registries {unknown}; choose from {sorted(REGISTRIES)}")
    return {n: REGISTRIES[n] for n in names}


# ---------------------------------------------------------------- dry run


def count_registry(path: Path, segments: list[str], batch_size: int) -> dict[str, Any]:
    """The exact candidates, batches and prompts the real gate would be sent for
    one registry, by running the gate step with a recorder that answers
    all-`unsure` (no model, nothing sent anywhere)."""
    prompts: list[str] = []
    schema_chars: list[int] = []

    def recorder(prompt: str, schema: Any) -> dict[str, Any]:
        prompts.append(prompt)
        schema_chars.append(len(json.dumps(schema)))
        return {"verdicts": [{"pair_id": p["pair_id"], "verdict": "unsure"}
                             for p in mg.batch_request(schema)["pairs"]]}

    out = gr.seeded_registry(path, segments=segments, gate=recorder, gate_batch_size=batch_size)
    counts = out["gate_report"]["counts"]
    chars = sum(len(p) for p in prompts) + sum(schema_chars) + SHIM_WRAPPER_CHARS * len(prompts)
    tokens_in = chars // CHARS_PER_TOKEN
    tokens_out = counts["candidates"] * OUT_TOKENS_PER_PAIR + len(prompts) * OUT_TOKENS_PER_CALL
    return {"candidates": counts["candidates"], "batches": counts["batches"],
            "calls": len(prompts), "prompt_chars": chars,
            "est_tokens_in": tokens_in, "est_tokens_out": tokens_out}


def dry_run(registries: Mapping[str, Path], reps: int, batch_size: int,
            segments: list[str] | None = None) -> dict[str, Any]:
    """Count the metered run without a model. Returns (and prints) per-registry
    and total candidate / batch / call counts and an estimated token total."""
    segments = story_segments() if segments is None else segments
    per = {name: count_registry(path, segments, batch_size) for name, path in registries.items()}
    one = {k: sum(v[k] for v in per.values())
           for k in ("candidates", "batches", "calls", "prompt_chars",
                     "est_tokens_in", "est_tokens_out")}
    total = {k: v * reps for k, v in one.items()}
    result = {"batch_size": batch_size, "reps": reps, "per_registry": per,
              "per_repetition": one, "total": total,
              "est_tokens_total": total["est_tokens_in"] + total["est_tokens_out"]}
    print(f"MERGE-GATE-V1 metered measurement: DRY RUN (no model is called)\n"
          f"batch size {batch_size}, {reps} repetition(s)\n")
    print(f"{'registry':<11}{'candidates':>11}{'batches':>9}{'calls':>7}{'prompt chars':>14}"
          f"{'est tok in':>12}{'est tok out':>13}")
    for name, c in per.items():
        print(f"{name:<11}{c['candidates']:>11}{c['batches']:>9}{c['calls']:>7}"
              f"{c['prompt_chars']:>14}{c['est_tokens_in']:>12}{c['est_tokens_out']:>13}")
    print(f"{'one rep':<11}{one['candidates']:>11}{one['batches']:>9}{one['calls']:>7}"
          f"{one['prompt_chars']:>14}{one['est_tokens_in']:>12}{one['est_tokens_out']:>13}")
    print(f"\ntotal over {reps} repetition(s): {total['calls']} calls, "
          f"~{total['est_tokens_in']:,} tokens in + ~{total['est_tokens_out']:,} out "
          f"= ~{result['est_tokens_total']:,} tokens")
    print(f"(estimate: {CHARS_PER_TOKEN} characters per token in, {OUT_TOKENS_PER_PAIR} tokens "
          f"out per pair + {OUT_TOKENS_PER_CALL} per call)")
    return result


# ------------------------------------------------------------ the metered run


class Metered:
    """The real gate model, counting its own calls. Exposes ``identity`` so the
    gate's report records which model answered."""

    def __init__(self, model: Callable[[str, dict], Any], identity: str) -> None:
        self.model, self.identity = model, identity
        self.calls = 0
        self.seconds = 0.0
        self.chars_in = 0
        self.chars_out = 0

    def __call__(self, prompt: str, schema: Any) -> Any:
        t = time.perf_counter()
        try:
            out = self.model(prompt, schema)
        finally:
            self.calls += 1
            self.seconds += time.perf_counter() - t
            self.chars_in += len(prompt) + len(json.dumps(schema))
        self.chars_out += len(json.dumps(out)) if out is not None else 0
        return out

    def stats(self) -> dict[str, Any]:
        return {"calls": self.calls, "seconds": round(self.seconds, 1),
                "chars_in": self.chars_in, "chars_out": self.chars_out}


def _same_pairs(effect: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(p["a"], p["b"]): p for p in effect["gate_report"]["pairs"] if p["verdict"] == "same"}


def score(reps: Sequence[Mapping[str, Mapping[str, Any]]], *, seed: int = SAMPLE_SEED
          ) -> dict[str, Any]:
    """Score repetitions (``reps[i][registry] = merge_gate_effect(...)``) against
    the spec's part-2 pass mark. Pure: reads effects only."""
    per_rep: list[dict[str, Any]] = []
    for effects in reps:
        wrong, joined, of, f1, unlabelled = {}, 0, 0, {}, 0
        for name, e in effects.items():
            labels = e["pair_labels"]
            wrong[name] = sorted(p["pair_id"] for p in e["gate_report"]["pairs"]
                                 if p["verdict"] == "same" and labels[p["pair_id"]] == "different")
            joined += e["split_pairs_joined"]
            of += len(e["split_pairs"])
            f1[name] = {"default": e["default"]["b3_f1"], "gated": e["gated"]["b3_f1"],
                        "not_below": e["gated"]["b3_f1"] >= e["default"]["b3_f1"]}
            unlabelled += sum(1 for p in e["gate_report"]["pairs"]
                              if p["verdict"] == "same" and labels[p["pair_id"]] == "unknown")
        per_rep.append({
            "precision_same_on_gold_different": wrong,
            "precision_ok": not any(wrong.values()),
            "recall_joined": joined, "recall_of": of, "recall_ok": joined >= RECALL_MIN,
            "f1": f1, "f1_ok": all(v["not_below"] for v in f1.values()),
            "unlabelled_same": unlabelled,
            "statuses": _sum_counts(e["statuses"] for e in effects.values()),
            "verdicts": _sum_counts(e["verdicts"] for e in effects.values()),
        })
    complete = bool(reps) and all(len(r) == len(REGISTRIES) for r in reps)
    # run to run: pairs whose verdict differs between repetitions
    verdicts: dict[tuple[str, str, str], list[str]] = {}
    for i, effects in enumerate(reps):
        for name, e in effects.items():
            for p in e["gate_report"]["pairs"]:
                verdicts.setdefault((name, p["a"], p["b"]), [""] * len(reps))[i] = p["verdict"]
    differing = [{"registry": k[0], "a": k[1], "b": k[2], "verdicts": v}
                 for k, v in sorted(verdicts.items()) if len(set(v)) > 1]
    # 20 sampled unlabelled `same` pairs (union over repetitions) for Kabe to look over
    pool: dict[tuple[str, str, str], dict[str, Any]] = {}
    for i, effects in enumerate(reps):
        for name, e in effects.items():
            for p in e["gate_report"]["pairs"]:
                if p["verdict"] == "same" and e["pair_labels"][p["pair_id"]] == "unknown":
                    pool.setdefault((name, p["a"], p["b"]), {
                        "registry": name, "a": p["a"], "b": p["b"], "a_names": p["a_names"],
                        "b_names": p["b_names"], "keep_id": p["keep_id"], "reason": p["reason"],
                        "same_in_reps": []})["same_in_reps"].append(i + 1)
    keys = sorted(pool)
    sample = [pool[k] for k in sorted(random.Random(seed).sample(keys, min(SAMPLE_SIZE, len(keys))))]
    ok = complete and all(r["precision_ok"] and r["recall_ok"] and r["f1_ok"] for r in per_rep)
    return {"complete": complete, "pass": ok, "per_rep": per_rep,
            "unlabelled_same_pairs": len(pool), "sample": sample,
            "run_to_run_differing_pairs": differing}


def _sum_counts(counters) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in counters:
        for k, v in c.items():
            out[k] = out.get(k, 0) + v
    return dict(sorted(out.items()))


def scoring_md(s: Mapping[str, Any]) -> str:
    lines = ["# MERGE-GATE-V1 part 2: scoring against the pass mark", "",
             f"Complete (all five registries): **{s['complete']}**. Pass: **{s['pass']}**.", "",
             "| rep | no `same` on gold-different | gold-same merged (>= 8 of 11) | F1 not below default "
             "| unlabelled `same` |", "|---|---|---|---|---|"]
    for i, r in enumerate(s["per_rep"], 1):
        bad = sum(len(v) for v in r["precision_same_on_gold_different"].values())
        lines.append(f"| {i} | {'PASS' if r['precision_ok'] else f'FAIL ({bad})'} "
                     f"| {'PASS' if r['recall_ok'] else 'FAIL'} ({r['recall_joined']} of {r['recall_of']}) "
                     f"| {'PASS' if r['f1_ok'] else 'FAIL'} | {r['unlabelled_same']} |")
    lines += ["", f"## Pairs whose verdict differs between repetitions "
              f"({len(s['run_to_run_differing_pairs'])})", ""]
    lines += [f"- `{d['registry']}` {d['a']} / {d['b']}: {d['verdicts']}"
              for d in s["run_to_run_differing_pairs"]] or ["- none"]
    lines += ["", f"## {len(s['sample'])} sampled unlabelled `same` pairs of "
              f"{s['unlabelled_same_pairs']} (not scored)", ""]
    lines += [f"- `{d['registry']}` {d['a']} {d['a_names']} / {d['b']} {d['b_names']} "
              f"(keep {d['keep_id']}; reps {d['same_in_reps']}): {d['reason']}"
              for d in s["sample"]] or ["- none"]
    return "\n".join(lines) + "\n"


def run(out_dir: Path, model: Callable[[str, dict], Any], identity: str, *, reps: int = 2,
        batch_size: int = mg.DEFAULT_BATCH_SIZE, registries: Mapping[str, Path] | None = None,
        segments: list[str] | None = None) -> dict[str, Any]:
    """The metered measurement. ``model`` answers the gate (the real one, from the
    command line; any callable with the model signature in tests). Writes per-rep
    JSON as it goes and the scoring at the end."""
    registries = dict(REGISTRIES if registries is None else registries)
    segments = story_segments() if segments is None else segments
    out_dir = Path(out_dir)
    metered = Metered(model, identity)
    results: list[dict[str, dict[str, Any]]] = []
    started = time.time()
    for rep in range(1, reps + 1):
        rep_dir = out_dir / f"rep{rep}"
        rep_dir.mkdir(parents=True, exist_ok=True)
        effects: dict[str, dict[str, Any]] = {}
        for name, path in registries.items():
            effects[name] = gr.merge_gate_effect(path, segments, metered, batch_size=batch_size)
            (rep_dir / f"{name}.json").write_text(
                json.dumps(effects[name], indent=2, sort_keys=True) + "\n")
            logger.info("rep %d %s: %d candidates, %s", rep, name,
                        effects[name]["candidates"], effects[name]["verdicts"])
        results.append(effects)
    scoring = score(results)
    (out_dir / "scoring.json").write_text(json.dumps(scoring, indent=2, sort_keys=True) + "\n")
    (out_dir / "SCORING.md").write_text(scoring_md(scoring))
    (out_dir / "meta.json").write_text(json.dumps({
        "date": date.today().isoformat(), "model": identity, "reps": reps,
        "batch_size": batch_size, "registries": sorted(registries),
        "wall_s": round(time.time() - started, 1), **metered.stats()}, indent=2) + "\n")
    return scoring


# ------------------------------------------------------------- free measures


def run_free(out_dir: Path, registries: Mapping[str, Path] | None = None,
             batch_size: int = mg.DEFAULT_BATCH_SIZE, segments: list[str] | None = None
             ) -> dict[str, Any]:
    """The free pass-mark measures (spec part 1, items 1-3) on the stored
    registries: no model. Writes ``OUT_DIR/<registry>.json`` and returns the table."""
    registries = dict(REGISTRIES if registries is None else registries)
    segments = story_segments() if segments is None else segments
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def all_unsure(prompt: str, schema: Any) -> dict[str, Any]:
        return {"verdicts": [{"pair_id": p["pair_id"], "verdict": "unsure"}
                             for p in mg.batch_request(schema)["pairs"]]}

    table: dict[str, Any] = {}
    for name, path in sorted(registries.items()):
        oracle = gr.merge_gate_effect(path, segments, gr.gold_oracle_gate(), batch_size=batch_size)
        base = gr.seeded_registry(path, segments=segments, with_log=True)
        unsure = gr.seeded_registry(path, segments=segments, gate=all_unsure,
                                    gate_batch_size=batch_size, with_log=True)
        row = {
            "registry": name,
            "candidates": oracle["candidates"], "batches": oracle["batches"],
            "recall": oracle["recall"], "labels": oracle["labels"],
            "default": oracle["default"], "oracle": oracle["gated"],
            "oracle_merges": oracle["merges"],
            "all_unsure_log_identical": base["log_sha256"] == unsure["log_sha256"],
            "log_sha256": base["log_sha256"],
            "split_pairs": oracle["split_pairs"],
            "oracle_report_counts": oracle["gate_report"]["counts"],
        }
        table[name] = row
        (out_dir / f"{name}.json").write_text(json.dumps(row, indent=2, sort_keys=True) + "\n")
        logger.info("%s: %d candidates, recall %d/%d, oracle F1 %s (default %s)", name,
                    row["candidates"], row["recall"]["found"], row["recall"]["of"],
                    row["oracle"]["b3_f1"], row["default"]["b3_f1"])
    return table


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir", nargs="?", help="where the metered run (or --free) writes")
    ap.add_argument("--dry-run", action="store_true",
                    help="count candidates, batches, calls and tokens; no model, no writes")
    ap.add_argument("--free", action="store_true",
                    help="the free measures (gold-oracle and all-unsure gates); no model")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--batch-size", type=int, default=mg.DEFAULT_BATCH_SIZE)
    ap.add_argument("--registry", action="append", help="only this registry (repeatable)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.dry_run else logging.INFO,
                        format="%(asctime)s %(name)s %(message)s")
    registries = select(args.registry)
    if args.dry_run:
        dry_run(registries, args.reps, args.batch_size)
        return 0
    if not args.out_dir:
        ap.error("out_dir is required unless --dry-run")
    if args.free:
        run_free(Path(args.out_dir), registries, args.batch_size)
        return 0
    from model_shim import get_model  # the metered path only; --dry-run never imports it

    model, identity = get_model()
    scoring = run(Path(args.out_dir), model, identity, reps=args.reps,
                  batch_size=args.batch_size, registries=registries)
    print(scoring_md(scoring))
    return 0 if scoring["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
