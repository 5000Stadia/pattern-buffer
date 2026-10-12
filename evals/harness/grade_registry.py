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


def seeded_registry(registry: Any, segments: list[str] | None = None) -> dict[str, Any]:
    """The registry as the engine leaves it: seed it into a scratch world
    (stub model, no pass-1), run identity promotion and ``reconcile``, and
    fold each merged group into one card under its surviving id. Grading this
    measures identity after commit, where the engine's own merges count.

    Ids are first repaired as ``registry.parse_registry_lines`` repairs them
    (a stored registry from before that fix may carry ``person:/x`` ids,
    which the gate would refuse).

    With ``segments`` (the story text pass-0 read) the registry is seeded with
    ALIAS-INDEX-V1 Part B exactly as ``Pipeline.commit`` does it: the seed and
    the pass are ``pipeline.seed_world`` and ``pipeline.alias_distinct_pass``,
    shared with the commit, and the pass runs before promotion and
    ``reconcile``. The pass's report is returned under ``"alias_report"``."""
    import tempfile

    from patternbuffer import World

    try:
        from pipeline import alias_distinct_pass, seed_world
        from registry import EntityCard, TimelineSpec, WorldRegistry, _norm_id
    except ImportError:
        from evals.harness.pipeline import alias_distinct_pass, seed_world
        from evals.harness.registry import EntityCard, TimelineSpec, WorldRegistry, _norm_id

    if isinstance(registry, (str, Path)):
        registry = json.loads(Path(registry).read_text())
    if not isinstance(registry, Mapping):
        from dataclasses import asdict
        registry = asdict(registry)
    reg = WorldRegistry(
        world_id=registry["world_id"],
        entities={_norm_id(k): EntityCard(**v) for k, v in registry["entities"].items()},
        attributes=dict(registry.get("attributes", {})),
        timeline=TimelineSpec(**registry.get("timeline", {})),
        places=[(_norm_id(a), _norm_id(b)) for a, b in registry.get("places", [])],
    )

    with tempfile.TemporaryDirectory() as tmp:
        w = World(Path(tmp) / "seeded.world", world_id=reg.world_id,
                  model=lambda prompt, schema: {})
        w.ingestor.classify_inline = False
        seed_world(w, reg)
        alias_report = alias_distinct_pass(w, reg, segments) if segments is not None else None
        w.registry.promote_identity_proposals()
        w.registry.reconcile()
        entities: dict[str, dict[str, list[str]]] = {}
        merged_into: dict[str, str] = {}
        for eid, card in sorted(reg.entities.items()):
            root = w.registry.resolve(eid)
            if root != eid:
                merged_into[eid] = root
            merged = entities.setdefault(root, {"names": [], "aliases": []})
            merged["names"] += [n for n in card.names if n not in merged["names"]]
            merged["aliases"] += [a for a in card.aliases if a not in merged["aliases"]]
        w.close()
    out: dict[str, Any] = {"world_id": reg.world_id, "entities": entities,
                           "merged_into": merged_into}
    if alias_report is not None:
        out["alias_report"] = alias_report
    return out


def part_b_effect(registry: Any, segments: list[str]) -> dict[str, Any]:
    """What ALIAS-INDEX-V1 Part B changes on one registry (no model call): the
    registry seeded without it (main) and with it exactly as ``Pipeline.commit``
    does, each graded. Returns, per side, B3 F1, the fused ids and fragmented
    gold entities, and for every Part A merge candidate whether the pair ended
    as one id; plus what Part B ``written`` and kept ``report_only``."""
    sides: dict[str, dict[str, Any]] = {}
    report: dict[str, Any] = {}
    for label, segs in (("main", None), ("part_b", segments)):
        seeded = seeded_registry(registry, segments=segs)
        g = grade(seeded)
        report = seeded.get("alias_report", report)
        sides[label] = {"seeded": seeded, "grade": g}
    candidates = report["merge_candidates"] + report["merge_excluded"]
    out: dict[str, Any] = {}
    for label, side in sides.items():
        g, into = side["grade"], side["seeded"]["merged_into"]
        root = lambda i: into.get(i, i)  # noqa: E731
        out[label] = {
            "b3_f1": g["b3_f1"],
            "fusion_count": g["fusion_count"],
            "fusion": g["fusion"],
            "fragmentation_count": g["fragmentation_count"],
            "fragmentation": sorted(g["fragmentation"]),
            "merge_candidates_merged": sorted(
                f"{c['holder']} + {c['named']}" for c in candidates
                if c["holder"] in into or c["named"] in into
                if root(c["holder"]) == root(c["named"])),
        }
    out["written"] = report["written"]
    out["report_only"] = report["report_only"]
    return out


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
    ap.add_argument("--part-b", action="store_true",
                    help="also write part_b_effect.json: this registry seeded without and with "
                         "ALIAS-INDEX-V1 Part B over the chapter-test story (needs PYTHONPATH=src)")
    args = ap.parse_args(argv)
    result = grade(args.registry)
    md, js = write_scorecard(result, args.out)
    print(f"{md}\n{js}")
    if args.part_b:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        import run_pass0_baseline  # the segmentation lives there

        effect = part_b_effect(args.registry, run_pass0_baseline.story_segments())
        path = Path(args.out) / "part_b_effect.json"
        path.write_text(json.dumps(effect, indent=2, sort_keys=True) + "\n")
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
