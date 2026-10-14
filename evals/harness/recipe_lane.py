"""RECIPE-VOCAB-V1 §6: the recipe goldens, loaded and (lane 2) graded against a build.

Lane 1 (free, in the suite, ``tests/test_recipe_goldens.py``) loads each golden
``evals/recipes/<name>.facts.json`` into a fresh world opened under the recipe
vocabulary and reads it back. This module owns that loader, so lane 1 and lane 2
share it, and lane 2's runner:

    the recipe's story text -> ``patternbuffer.build`` (manifest, plan,
    ``extract(..., vocabulary=RECIPE)``, commit) -> a world -> graded against the
    golden on FOLDED reads (containment on the folded location, so any
    containment-family spelling of one container matches).

Lane 2 makes paid model calls (extraction, then the build's classification), so
each run waits for Kabe's yes. Three ways to invoke it:

    # what WOULD run: the manifest, the chunk count and the prompt with and without
    # the vocabulary; no model is imported or called, nothing is written
    PYTHONPATH=src python evals/harness/recipe_lane.py --dry-run [RECIPE ...]

    # a free wiring check: a scripted model that answers from the golden itself
    PYTHONPATH=src python evals/harness/recipe_lane.py --oracle OUT_DIR [RECIPE ...]

    # the metered run (needs Kabe's yes first); --vocabulary none is the baseline arm
    PYTHONPATH=src python evals/harness/recipe_lane.py --metered OUT_DIR [RECIPE ...] \\
        [--vocabulary recipe|none]

A metered run writes ``OUT_DIR/<recipe>/{prompt.txt, answers.json, build.world,
report.json}`` and ``OUT_DIR/report.json``.

Only entities whose names the story's text contains can be manifest entries (the
registry anchors each by an exact quote). The others (code-lock's door and
outside) must be declared by the model as escapes, and the grade reports whether
it did.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
RECIPE_DIR = ROOT / "evals" / "recipes"
SCHEMA = "patternbuffer.recipe-facts/1"
# RECIPE-VOCAB-V1 §6 (r1.4, r1.4.1): a fact's source is text or authored, never both.
TEXT_KEYS = frozenset({"chapter", "sentence"})
AUTHORED_KEYS = frozenset({"authored", "note"})
FIXED_AUTHORS = ("manifest", "holo-emitter planner")

from patternbuffer import World, build
from patternbuffer.build.extract import build_prompt
from patternbuffer.build.text import Book, contains_run, tokens
from patternbuffer.testing import StubModel, rule_classifier_fallback
from patternbuffer.vocab import RECIPE, Vocabulary, apply_aliases, attribute_default, check

logger = logging.getLogger("recipe_lane")

RECIPES = ("switched-light", "code-lock", "take-and-drop")
# The containment family folds as one key: a held thing and an in-place thing
# have one location.
CONTAINMENT = ("in", "held_by", "worn_by")
IDENTITY_ATTRIBUTES = ("kind", "name", "alias")
# Attributes the engine already names, beside the RECIPE terms (RECIPE-VOCAB-V1
# §4, "already canonical and not redeclared", plus the identity rows the loader writes).
ENGINE_CANONICAL = frozenset({
    "in", "held_by", "worn_by", "connects_to", "part_of", "kind", "role", "fixture",
    "posture", "sits_on", "name", "alias",
})


# ------------------------------------------------------------ the goldens


def golden_path(name: str) -> Path:
    return RECIPE_DIR / f"{name}.facts.json"


def load_golden(name: str) -> dict[str, Any]:
    """One golden, read and shape-checked: raises ``ValueError`` naming what is
    wrong (the schema, an entity carrying more than id/kind/names, a fact with
    neither ``valid_from`` nor ``timeless`` or without a source)."""
    golden = json.loads(golden_path(name).read_text())
    problems = golden_problems(golden)
    if problems:
        raise ValueError(f"golden {name}: " + "; ".join(problems))
    return golden


def source_problem(source: Any, sentences: int) -> str | None:
    """Why ``source`` is not one of the two source forms (RECIPE-VOCAB-V1 §6), or
    None when it is. ``sentences`` is the story's sentence count (``Book({1: story})``,
    1-based).

    text:     exactly ``{"chapter": 1, "sentence": N}``, N an int in 1..sentences
    authored: exactly ``{"authored": WHO}`` or ``{"authored": WHO, "note": str}``,
              WHO one of ``manifest``, ``holo-emitter planner``, ``Kabe YYYY-MM-DD``"""
    if not isinstance(source, dict) or not source:
        return "no source (it cites a sentence or names its author)"
    keys = set(source)
    if keys & TEXT_KEYS and keys & AUTHORED_KEYS:
        return f"source mixes the text and authored forms ({sorted(keys)})"
    if keys & TEXT_KEYS:
        if keys != TEXT_KEYS:
            return f"a text source is exactly chapter and sentence, not {sorted(keys)}"
        chapter, sentence = source["chapter"], source["sentence"]
        for label, number in (("chapter", chapter), ("sentence", sentence)):
            if not isinstance(number, int) or isinstance(number, bool):
                return f"source {label} {number!r} is not an integer"
        if chapter != 1:
            return f"source chapter is {chapter}, but a golden's story is chapter 1"
        if not 1 <= sentence <= sentences:
            return f"source sentence {sentence} is outside 1..{sentences}"
        return None
    if "authored" in keys and keys <= AUTHORED_KEYS:
        if not _author_ok(source["authored"]):
            return (f"authored {source['authored']!r} is not 'manifest', "
                    "'holo-emitter planner' or 'Kabe YYYY-MM-DD'")
        if "note" in source and not isinstance(source["note"], str):
            return f"source note {source['note']!r} is not a string"
        return None
    return f"source keys {sorted(keys)} are neither a text nor an authored source"


def _author_ok(who: Any) -> bool:
    if not isinstance(who, str):
        return False
    if who in FIXED_AUTHORS:
        return True
    if not who.startswith("Kabe "):
        return False
    day = who.removeprefix("Kabe ")
    try:
        return date.fromisoformat(day).isoformat() == day
    except ValueError:
        return False


def is_text(fact: Mapping[str, Any]) -> bool:
    """True when the story states ``fact`` (a text source: lane 2 grades it)."""
    return "chapter" in fact["source"]


def golden_problems(golden: Mapping[str, Any]) -> list[str]:
    """Every way ``golden`` departs from the ``patternbuffer.recipe-facts/1`` shape."""
    out: list[str] = []
    if golden.get("schema") != SCHEMA:
        out.append(f"schema is {golden.get('schema')!r}, not {SCHEMA!r}")
    for entity in golden.get("entities", []):
        if sorted(entity) != ["id", "kind", "names"]:
            out.append(f"entity {entity.get('id')!r} carries {sorted(entity)}, "
                       "not exactly id/kind/names")
    ids = {e.get("id") for e in golden.get("entities", [])}
    story = golden.get("story")
    sentences = len(Book({1: story}).sentences(1)) if isinstance(story, str) else 0
    for n, fact in enumerate(golden.get("facts", [])):
        where = f"fact {n} ({fact.get('entity')} {fact.get('attribute')})"
        if fact.get("entity") not in ids:
            out.append(f"{where}: its entity is not in `entities`")
        if ("valid_from" in fact) == bool(fact.get("timeless")):
            out.append(f"{where}: exactly one of valid_from or timeless")
        problem = source_problem(fact.get("source"), sentences)
        if problem:
            out.append(f"{where}: {problem}")
        if fact.get("value_type") not in ("entity", "literal"):
            out.append(f"{where}: value_type {fact.get('value_type')!r}")
    return out


def open_world(path: Path, world_id: str, *, model: Callable[[str, dict], Any] | None = None,
               vocabulary: Vocabulary | None = RECIPE) -> World:
    """A world opened as a host adopting ``vocabulary`` opens it: its
    ``attribute_default`` wired and its aliases applied. ``vocabulary=None`` is
    a bare world (the baseline arm)."""
    model = model or StubModel(fallback=rule_classifier_fallback())
    world = World(path, world_id=world_id, model=model,
                  attribute_default=attribute_default(vocabulary) if vocabulary else None)
    if vocabulary is not None:
        apply_aliases(world, vocabulary)
    return world


def golden_items(golden: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The golden as ``ingest_structured`` items: each entity's kind and names
    (timeless), then each fact in order, text or authored alike (the reference
    world is the whole golden)."""
    items: list[dict[str, Any]] = []
    for entity in golden["entities"]:
        items.append({"entity": entity["id"], "attribute": "kind",
                      "value": entity["kind"], "timeless": True})
        for name in entity["names"]:
            items.append({"entity": entity["id"], "attribute": "name",
                          "value": name, "timeless": True})
    for fact in golden["facts"]:
        item = {k: fact[k] for k in ("entity", "attribute", "value", "value_type", "frame")}
        if fact.get("timeless"):
            item["timeless"] = True
        else:
            item["valid_from"] = fact["valid_from"]
        items.append(item)
    return items


def load_into(world: World, golden: Mapping[str, Any]) -> Any:
    """Write ``golden`` into ``world`` through the porcelain's gate; returns the
    receipt. Raises ``ValueError`` when the gate skipped any item (a golden is
    written whole or it is wrong)."""
    receipt = world.porcelain.ingest_structured(golden_items(golden))
    if receipt.skipped:
        raise ValueError(f"golden {golden.get('recipe')}: the gate skipped {receipt.skipped}")
    return receipt


# ---------------------------------------------------------------- lane 2


def manifest_for(golden: Mapping[str, Any]) -> tuple[build.Manifest, list[str]]:
    """The build manifest for a golden's story, and the golden ids it cannot
    seed. An entity is an entry when one of its names occurs in the story as a
    whole-token run; its anchor quote is the first such sentence, whole (a
    sentence occurs once). A ``fixture`` fact sourced ``{"authored": "manifest"}``
    on an entity makes its entry ``fixture=True`` (the build library's host route). The
    unseeded entities are left for the model to declare as escapes."""
    story = golden["story"]
    book = Book({1: story})
    entries: list[build.Entry] = []
    unseeded: list[str] = []
    fixtures = {f["entity"] for f in golden["facts"]
                if f["source"].get("authored") == "manifest" and f["attribute"] == "fixture"}
    for entity in golden["entities"]:
        anchor = _anchor(book, story, entity["names"])
        if anchor is None:
            unseeded.append(entity["id"])
            continue
        namespace, _, suffix = entity["id"].partition(":")
        entries.append(build.Entry(
            key=suffix, type={"person": "person", "place": "place", "obj": "object"}[namespace],
            names=tuple(entity["names"]), anchor_quote=anchor,
            fixture=entity["id"] in fixtures))
    return build.Manifest(tuple(entries)), unseeded


def _anchor(book: Book, story: str, names: list[str]) -> str | None:
    wanted = [tokens(n) for n in names]
    for sentence in book.sentences(1):
        have = list(sentence.tokens)
        if any(contains_run(have, w) for w in wanted):
            return story[sentence.start:sentence.end]
    return None


def ids_by_name(golden: Mapping[str, Any],
                names_of: Mapping[str, list[str]]) -> dict[str, str | None]:
    """golden id -> the id in another world that carries one of its names
    (``names_of`` is that world's id -> names), or None when none does or
    several do."""
    out: dict[str, str | None] = {}
    for entity in golden["entities"]:
        wanted = {n.casefold() for n in entity["names"]}
        hits = sorted(i for i, names in names_of.items()
                      if wanted & {n.casefold() for n in names})
        out[entity["id"]] = hits[0] if len(hits) == 1 else None
    return out


def world_names(world: World) -> dict[str, list[str]]:
    """id -> its ``name`` values, in the canon frame."""
    out: dict[str, list[str]] = {}
    for fact in world.porcelain.facts("canon", attribute="name"):
        out.setdefault(fact["entity"], []).append(fact["value"])
    return out


def _say(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def served(world: World, entity: str, attribute: str, frame: str,
           back: Mapping[str, str]) -> list[str]:
    """The values a key serves, as a sorted list of JSON strings, entity ids
    translated through ``back`` (this world's id -> the golden's). A conflicted
    key serves ``"<conflicted>"``; an unknown one serves nothing."""
    if attribute in CONTAINMENT:
        chain = world.porcelain.locate(entity, frame=frame)
        return [_say(back.get(chain[0], chain[0]))] if chain else []
    state = world.porcelain.state(entity, attribute, frame)
    if state["status"] == "unknown":
        return []
    if state["status"] == "conflicted":
        return ["<conflicted>"]
    facts = state.get("values") or [state["fact"]]
    values = []
    for fact in facts:
        value = fact["value"]
        values.append(_say(back.get(value, value) if fact["value_type"] == "entity" else value))
    return sorted(values)


def grade(golden: Mapping[str, Any], reference: World, built: World,
          ids: Mapping[str, str | None]) -> dict[str, Any]:
    """Grade ``built`` against the golden on folded reads. ``reference`` is the
    golden loaded into a world; ``ids`` maps golden id -> ``built``'s id.

    Each distinct (entity, attribute, frame) of the golden's TEXT facts (identity
    rows aside; the containment family is one key, ``location``) is read in
    both worlds, and ``ok`` means the served values match. A golden entity the
    build has no id for fails its keys as ``entity_missing``. Authored facts
    (the story doesn't state them) are not graded: the report lists them under
    ``skipped_authored``, each with its author, beside ``text_facts`` and
    ``authored_facts`` counts. It also carries ``extra``: keys the build holds
    that the golden neither grades nor lists as authored (not graded)."""
    forward = {g: b for g, b in ids.items() if b is not None}
    back = {b: g for g, b in forward.items()}
    keys: list[tuple[str, str, str]] = []
    skipped_authored = [
        {"entity": f["entity"], "attribute": f["attribute"], "value": f["value"],
         "frame": f["frame"], "authored": f["source"]["authored"]}
        for f in golden["facts"] if not is_text(f)]
    text_facts = [f for f in golden["facts"] if is_text(f)]
    for fact in text_facts:
        attribute = reference.canonical_attribute(fact["attribute"])
        if attribute in IDENTITY_ATTRIBUTES:
            continue
        key = (fact["entity"], "location" if attribute in CONTAINMENT else attribute, fact["frame"])
        if key not in keys:
            keys.append(key)
    results = []
    for entity, attribute, frame in keys:
        read_as = "in" if attribute == "location" else attribute
        expected = served(reference, entity, read_as, frame, {})
        built_id = forward.get(entity)
        if built_id is None:
            results.append({"entity": entity, "attribute": attribute, "frame": frame,
                            "expected": expected, "observed": None, "ok": False,
                            "why": "entity_missing"})
            continue
        built_frame = frame
        if frame.startswith("knows:"):
            observer = forward.get(frame.removeprefix("knows:"))
            built_frame = f"knows:{observer}" if observer else frame
        observed = served(built, built_id, read_as, built_frame, back)
        results.append({"entity": entity, "attribute": attribute, "frame": frame,
                        "expected": expected, "observed": observed,
                        "ok": observed == expected})
    graded = {(r["entity"], r["attribute"]) for r in results}
    # an authored fact is listed under skipped_authored, not as an unexpected extra
    for fact in skipped_authored:
        attribute = reference.canonical_attribute(fact["attribute"])
        graded.add((fact["entity"], "location" if attribute in CONTAINMENT else attribute))
    extra = []
    for fact in built.porcelain.facts("canon", bookkeeping=False):
        entity = back.get(fact["entity"], fact["entity"])
        attribute = built.canonical_attribute(fact["attribute"])
        attribute = "location" if attribute in CONTAINMENT else attribute
        if (attribute in (*IDENTITY_ATTRIBUTES, "being_type", "species")
                or entity.startswith("world:") or (entity, attribute) in graded):
            continue
        extra.append({"entity": entity, "attribute": attribute, "value": fact["value"]})
    return {"passed": all(r["ok"] for r in results), "keys": results,
            "ok": sum(r["ok"] for r in results), "total": len(results),
            "text_facts": len(text_facts), "authored_facts": len(skipped_authored),
            "skipped_authored": skipped_authored, "extra": extra, "ids": dict(ids)}


def finding_dicts(world: World, vocabulary: Vocabulary | None) -> list[dict[str, Any]]:
    """``vocab.check`` on the world, as plain data (empty with no vocabulary)."""
    if vocabulary is None:
        return []
    return [{"kind": f.kind, "entity": f.entity, "attribute": f.attribute,
             "value": f.value, "detail": f.detail} for f in check(world, vocabulary)]


def oracle_model(golden: Mapping[str, Any], registry: build.Registry) -> Callable[[str, dict], Any]:
    """A scripted model that answers each prompt with the golden's facts as
    grammar lines (its text facts only, and only for the seeded entities: an
    authored fact is the host's or the manifest's, never a model's; kind, name and
    fixture rows are the build's and the host's). A free check that the lane's
    wiring (manifest, extract, commit, grade) holds; single-chunk stories only."""
    names_of = {i.id: list(i.names) for i in registry.identities}
    ids = ids_by_name(golden, names_of)

    def line(fact: Mapping[str, Any]) -> str | None:
        entity = ids.get(fact["entity"])
        if not is_text(fact) or entity is None or fact["attribute"] in (*IDENTITY_ATTRIBUTES, "fixture"):
            return None
        if fact["value_type"] == "entity":
            target = ids.get(fact["value"])
            if target is None:
                return None
            value = f"@{target}"
        else:
            value = _say(fact["value"])
        flags = ["t"] if fact.get("timeless") else []
        frame = fact["frame"]
        if frame != "canon":
            observer = ids.get(frame.removeprefix("knows:"))
            if observer is None:
                return None
            flags.append(f"f=knows:{observer}")
        tail = f"|{','.join(flags)}" if flags else ""
        return f"s{fact['source']['sentence']}|{entity}|{fact['attribute']}|{value}{tail}"

    lines = [text for fact in golden["facts"] if (text := line(fact)) is not None]

    def model(prompt: str, schema: dict) -> dict[str, Any]:
        return {"lines": lines, "escapes": [], "picks": []}

    return model


def run_recipe(name: str, out_dir: Path, model: Callable[[str, dict], Any], *,
               vocabulary: Vocabulary | None = RECIPE, oracle: bool = False) -> dict[str, Any]:
    """Build one recipe's story and grade it. With ``oracle=True``, ``model`` is
    ignored: the scripted oracle answers, and classification goes to the rule
    fallback (no model call anywhere)."""
    golden = load_golden(name)
    run_dir = out_dir / name
    run_dir.mkdir(parents=True, exist_ok=True)
    text = {1: golden["story"]}
    manifest, unseeded = manifest_for(golden)
    registry = build.Registry.from_manifest(manifest, text)
    chunks = build.plan(text, registry)
    if oracle:
        if len(chunks) != 1:
            raise ValueError(f"{name}: the oracle answers single-chunk stories only")
        model = oracle_model(golden, registry)
    (run_dir / "prompt.txt").write_text(
        build_prompt(chunks[0], registry.book, vocabulary))
    results = build.extract(chunks, registry, model, workers=1, vocabulary=vocabulary)
    (run_dir / "answers.json").write_text(json.dumps(
        [{"chunk": r.index, "error": r.error,
          "attempts": [{"error": a.error, "raw": a.raw} for a in r.attempts]}
         for r in results], indent=2, default=str) + "\n")
    refused = [r.index for r in results if r.error]
    report: dict[str, Any] = {
        "recipe": name, "vocabulary": vocabulary.name if vocabulary else None,
        "oracle": oracle, "unseeded": unseeded, "chunks": len(chunks), "refused_chunks": refused,
    }
    if refused:
        report["passed"] = False
        _write(run_dir / "report.json", report)
        return report
    classifier = StubModel(fallback=rule_classifier_fallback()) if oracle else model
    world = open_world(run_dir / "build.world", f"w:recipe-{name}", model=classifier,
                       vocabulary=vocabulary)
    reference = open_world(Path(tempfile.mkdtemp(prefix="recipe-ref-")) / "ref.world",
                           f"w:recipe-ref-{name}")
    try:
        load_into(reference, golden)
        receipt = build.commit(world, registry, results,
                               time_of=lambda i: float(chunks[i].chapter),
                               ingest_kwargs={"classify": "defer"})
        world.classifier.classify_all(batch_size=40)
        ids = ids_by_name(golden, world_names(world))
        report.update(grade(golden, reference, world, ids))
        report["findings"] = finding_dicts(world, vocabulary)
        report["skipped"] = list(receipt.skipped)
    finally:
        world.close()
        reference.close()
    _write(run_dir / "report.json", report)
    return report


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, default=str) + "\n")


def dry_run(names: list[str], vocabulary: Vocabulary | None) -> None:
    """Print what a run would do; no model is imported or called."""
    for name in names:
        golden = load_golden(name)
        manifest, unseeded = manifest_for(golden)
        registry = build.Registry.from_manifest(manifest, {1: golden["story"]})
        chunks = build.plan({1: golden["story"]}, registry)
        plain = build_prompt(chunks[0], registry.book, None)
        with_vocabulary = build_prompt(chunks[0], registry.book, vocabulary)
        print(f"{name}: {len(manifest.entries)} manifest entries "
              f"({', '.join(e.key for e in manifest.entries)}), unseeded {unseeded or 'none'}, "
              f"{len(chunks)} chunk(s) = {len(chunks)} extract call(s), plus classification")
        print(f"  prompt: {len(plain)} chars plain, {len(with_vocabulary)} chars "
              f"with the vocabulary ({len(with_vocabulary) - len(plain)} more)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("paths", nargs="*",
                        help=f"an OUT_DIR, and any of the recipes {', '.join(RECIPES)}")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would run; no model, no writes")
    parser.add_argument("--oracle", action="store_true",
                        help="a scripted model answers from the golden: free, no model call")
    parser.add_argument("--metered", action="store_true",
                        help="the paid run; needs Kabe's yes first")
    parser.add_argument("--vocabulary", choices=["recipe", "none"], default="recipe")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    vocabulary = RECIPE if args.vocabulary == "recipe" else None
    names = [p for p in args.paths if p in RECIPES] or list(RECIPES)
    others = [Path(p) for p in args.paths if p not in RECIPES]
    if len(others) > 1:
        parser.error(f"one OUT_DIR at most, got {[str(p) for p in others]}")
    out_dir = others[0] if others else None
    if args.dry_run:
        dry_run(names, vocabulary)
        return 0
    if out_dir is None or not (args.oracle or args.metered):
        parser.error("give --dry-run, or OUT_DIR with --oracle (free) or --metered (paid)")
    model: Callable[[str, dict], Any] = lambda prompt, schema: {}
    if args.metered:
        sys.path.insert(0, str(HERE))
        import model_shim
        model, _model_name = model_shim.get_model()   # (callable, name)
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = [run_recipe(n, out_dir, model, vocabulary=vocabulary, oracle=args.oracle)
               for n in names]
    _write(out_dir / "report.json", reports)
    for r in reports:
        print(f"{r['recipe']}: {'PASS' if r.get('passed') else 'FAIL'} "
              f"({r.get('ok', 0)}/{r.get('total', 0)} keys over {r.get('text_facts', 0)} text facts; "
              f"{r.get('authored_facts', 0)} authored facts skipped), "
              f"findings {len(r.get('findings', []))}")
        for skipped in r.get("skipped_authored", []):
            print(f"    skipped (authored by {skipped['authored']}): "
                  f"{skipped['entity']} {skipped['attribute']} {skipped['value']!r} "
                  f"[{skipped['frame']}]")
    return 0 if all(r.get("passed") for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
