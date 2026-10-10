"""Grade pass-0's world registry against the gold entity set (R23, PASS0-GRADER-V1).

Measures identity quality only: does the registry mint one id per gold entity
(no fragmentation), never one id for two (no fusion), and does it know every
gold name (coverage)? Deterministic, no model call. The gold is partial, so a
registry id that matches no gold mention is never charged.

Mentions are the gold alias strings; each entity's mentions are deduplicated
after normalization. A mention resolves to every registry id whose names or
aliases normalize to it.

Linking P/R/F1 is B-cubed over mentions, generalized to overlapping
predicted clusters: two mentions are *linked* when they resolve to at least
one common id. For mention m, precision = |linked(m) with the same gold
entity| / |linked(m)|, recall = |linked(m) with the same gold entity| /
|mentions of m's gold entity|; both include m itself. An unresolved mention
is linked to nobody (its own singleton predicted cluster), so it lowers
recall. Scores are averaged over all mentions. With one id per mention this
is exactly standard B-cubed.

CLI: python evals/harness/grade_registry.py RUN_DIR/registry.json --out DIR
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

_ARTICLES = ("the ", "a ", "an ")


def normalize(text: str) -> str:
    """Lowercase, trim outer space, drop one leading article."""
    s = " ".join(text.lower().split())
    for art in _ARTICLES:
        if s.startswith(art):
            s = s[len(art):].strip()
            break
    return s


def _registry_strings(registry: Any) -> dict[str, list[str]]:
    """id -> names + aliases, from a WorldRegistry, a loaded dict, or a path."""
    if isinstance(registry, (str, Path)):
        registry = json.loads(Path(registry).read_text())
    entities = registry["entities"] if isinstance(registry, Mapping) else registry.entities
    out: dict[str, list[str]] = {}
    for eid, card in entities.items():
        if isinstance(card, Mapping):
            out[eid] = list(card.get("names", [])) + list(card.get("aliases", []))
        else:
            out[eid] = list(card.names) + list(card.aliases)
    return out


def grade(registry: Any, gold: Mapping[str, list[str]] | None = None) -> dict[str, Any]:
    """Grade ``registry`` against ``gold`` (default: fixtures.ENTITIES).

    Returns a JSON-serializable dict: coverage, fragmentation, fusion,
    unresolved mentions per entity, and B-cubed linking precision/recall/F1.
    """
    if gold is None:
        try:
            from fixtures import ENTITIES as gold  # type: ignore[no-redef]
        except ImportError:
            from evals.harness.fixtures import ENTITIES as gold  # type: ignore[no-redef]

    strings = _registry_strings(registry)
    index: dict[str, set[str]] = {}
    for eid, ss in strings.items():
        for s in ss:
            index.setdefault(normalize(s), set()).add(eid)

    # mention = (gold key, normalized alias); resolved ids per mention
    mentions: list[tuple[str, str]] = []
    resolved: dict[tuple[str, str], frozenset[str]] = {}
    for key, aliases in gold.items():
        for norm in dict.fromkeys(normalize(a) for a in aliases):
            m = (key, norm)
            mentions.append(m)
            resolved[m] = frozenset(index.get(norm, ()))

    per_entity: dict[str, dict[str, Any]] = {}
    for key in gold:
        ms = [m for m in mentions if m[0] == key]
        ids = sorted({i for m in ms for i in resolved[m]})
        per_entity[key] = {
            "mentions": len(ms),
            "resolved": sum(1 for m in ms if resolved[m]),
            "unresolved": sorted(m[1] for m in ms if not resolved[m]),
            "ids": ids,
        }

    covered = sorted(k for k, v in per_entity.items() if v["resolved"])
    fragmented = {k: v["ids"] for k, v in per_entity.items() if len(v["ids"]) >= 2}

    by_id: dict[str, set[str]] = {}
    for m in mentions:
        for i in resolved[m]:
            by_id.setdefault(i, set()).add(m[0])
    fused = {i: sorted(ks) for i, ks in sorted(by_id.items()) if len(ks) >= 2}

    p_sum = r_sum = 0.0
    for m in mentions:
        ids = resolved[m]
        same_gold = sum(1 for o in mentions if o[0] == m[0] and (o == m or ids & resolved[o]))
        linked = sum(1 for o in mentions if o == m or ids & resolved[o])
        p_sum += same_gold / linked
        r_sum += same_gold / per_entity[m[0]]["mentions"]
    n = len(mentions) or 1
    precision, recall = p_sum / n, r_sum / n
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return {
        "gold_entities": len(gold),
        "mentions": len(mentions),
        "registry_ids": len(strings),
        "coverage": len(covered),
        "coverage_frac": len(covered) / len(gold) if gold else 0.0,
        "uncovered": sorted(set(gold) - set(covered)),
        "mentions_resolved": sum(1 for m in mentions if resolved[m]),
        "mentions_unresolved": sum(1 for m in mentions if not resolved[m]),
        "fragmentation_count": len(fragmented),
        "fragmentation": fragmented,
        "fusion_count": len(fused),
        "fusion": fused,
        "per_entity": per_entity,
        "b3_precision": round(precision, 4),
        "b3_recall": round(recall, 4),
        "b3_f1": round(f1, 4),
    }


def scorecard_md(result: Mapping[str, Any], title: str = "Pass-0 registry scorecard") -> str:
    """Render ``grade()`` output as a Markdown scorecard."""
    g = result
    lines = [
        f"# {title}", "",
        "| metric | value |", "|---|---|",
        f"| coverage | {g['coverage']}/{g['gold_entities']} |",
        f"| fragmented gold entities | {g['fragmentation_count']} |",
        f"| fused registry ids | {g['fusion_count']} |",
        f"| mentions resolved | {g['mentions_resolved']}/{g['mentions']} |",
        f"| B3 precision | {g['b3_precision']:.3f} |",
        f"| B3 recall | {g['b3_recall']:.3f} |",
        f"| B3 F1 | {g['b3_f1']:.3f} |",
        f"| registry ids (total) | {g['registry_ids']} |", "",
        "## Fragmentation (one gold entity, 2+ ids)", "",
    ]
    lines += [f"- `{k}`: {', '.join(f'`{i}`' for i in ids)}"
              for k, ids in sorted(g["fragmentation"].items())] or ["- none"]
    lines += ["", "## Fusion (one id, 2+ gold entities)", ""]
    lines += [f"- `{i}`: {', '.join(f'`{k}`' for k in ks)}"
              for i, ks in sorted(g["fusion"].items())] or ["- none"]
    lines += ["", "## Unresolved mentions by entity", ""]
    unres = [(k, v["unresolved"], v["mentions"]) for k, v in g["per_entity"].items() if v["unresolved"]]
    lines += [f"- `{k}` ({len(u)}/{n}): {', '.join(repr(a) for a in u)}"
              for k, u, n in unres] or ["- none"]
    lines.append("")
    return "\n".join(lines)


def write_scorecard(result: Mapping[str, Any], out_dir: str | Path,
                    stem: str = "scorecard", title: str = "Pass-0 registry scorecard") -> tuple[Path, Path]:
    """Write ``<stem>.md`` and ``<stem>.json`` into ``out_dir``; return both paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md, js = out / f"{stem}.md", out / f"{stem}.json"
    md.write_text(scorecard_md(result, title))
    js.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return md, js


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("registry", help="path to registry.json")
    ap.add_argument("--out", required=True, help="directory for scorecard.md/.json")
    args = ap.parse_args(argv)
    result = grade(args.registry)
    md, js = write_scorecard(result, args.out)
    print(f"{md}\n{js}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
