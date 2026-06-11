"""Scorecard assembly: per-question verdicts, extraction-vs-shape split,
seed version stamped on every card (letter 006 — never compare across
seed versions).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from battery import Verdict
import fixtures as FX


def render(verdicts: list[Verdict], meta: dict) -> tuple[str, dict]:
    n_pass = sum(1 for v in verdicts if v.status == "PASS")
    n_fail = sum(1 for v in verdicts if v.status == "FAIL")
    extraction = [v for v in verdicts if v.failure_class == "extraction"]
    shape = [v for v in verdicts if v.failure_class == "shape"]

    lines = [
        "# Chapter-test scorecard — The Last Honest Meter",
        "",
        f"- **Seed version:** {FX.SEED_VERSION} (results are never compared across seed versions)",
        f"- **Date:** {meta.get('date', date.today().isoformat())}",
        f"- **Extractor model:** {meta.get('model', '?')}",
        f"- **Log size:** {meta.get('log_rows', '?')} assertions, "
        f"{meta.get('entities', '?')} entities, {meta.get('frames', '?')} frames",
        f"- **Score: {n_pass}/{len(verdicts)} PASS** — "
        f"{len(extraction)} extraction-class failures (fixable), "
        f"{len(shape)} shape-class failures (whitepaper conversation)",
        "",
        "| Q | Battery item | Verdict | Class | Detail |",
        "|---|---|---|---|---|",
    ]
    for v in verdicts:
        detail = v.detail.replace("|", "\\|")[:160]
        lines.append(
            f"| {v.qid} | {v.title} | {v.status} | {v.failure_class or ''} | {detail} |"
        )
    lines += [
        "",
        "## Coverage honesty (letters 004/006, bible A5)",
        "",
    ]
    for qid, note in sorted(FX.COVERAGE_NOTES.items()):
        lines.append(f"- Q{qid}: {note}")
    lines += [
        "",
        "## Reading the classes",
        "",
        "- **extraction** — the engine's invariants held; the model-side extraction "
        "missed or mangled content. Fix the extractor contract and re-run.",
        "- **shape** — the substrate itself misbehaved (silent merge, phantom "
        "contents, frame leak, canon mutation). Stop: whitepaper conversation.",
        "",
    ]
    payload = {
        "seed_version": FX.SEED_VERSION,
        "meta": meta,
        "score": {"pass": n_pass, "fail": n_fail, "total": len(verdicts),
                  "extraction_failures": len(extraction), "shape_failures": len(shape)},
        "verdicts": [v.__dict__ for v in verdicts],
    }
    return "\n".join(lines), payload


def write(verdicts: list[Verdict], meta: dict, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md, payload = render(verdicts, meta)
    (out_dir / "scorecard.md").write_text(md)
    (out_dir / "scorecard.json").write_text(json.dumps(payload, indent=2))
    return out_dir / "scorecard.md"
