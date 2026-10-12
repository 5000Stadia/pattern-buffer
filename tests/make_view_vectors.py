"""Generates tests/vectors/view-feed-v1.json (VIEW-EXPORT-V1 test 11).

The file holds sequences of `{start document, feed answers, the document after
each}` over the manor fixture, for holo-emitter's JS `apply` to replay: apply
each answer to the running document and compare it to `expect`. The Python
`apply` is checked against the same file by tests/test_view_export.py, which
also fails if this generator's output differs from the committed file.

Run `python tests/make_view_vectors.py` to rewrite it (after a deliberate
change to the document shape).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from manor_fixture import (KEY, VF, WORLD_ID, E, T, build_manor,  # noqa: E402
                           canon, view)
from patternbuffer import mirror  # noqa: E402

VECTORS = HERE / "vectors" / "view-feed-v1.json"


def _empty() -> dict:
    return {"schema": mirror.SCHEMA, "world_id": WORLD_ID, "view_frame": VF,
            "at": None, "cursor": None, "known": {}, "present": None}


def _run(w, name: str, key, steps: list[tuple[str, object]], start: dict | None = None
         ) -> dict:
    """One sequence: the first step is a reset from `start`; each later step
    mutates the world (a callable) and feeds from the cursor the document holds."""
    doc = start if start is not None else _empty()
    out = {"name": name, "start": doc, "steps": []}
    for label, mutate in steps:
        if callable(mutate):
            mutate(w)
        answer = mirror.feed(w, VF, doc["cursor"], key=key)
        doc = mirror.apply(doc, answer)
        out["steps"].append({"name": label, "answer": answer, "expect": doc})
    return out


def build_vectors(tmp: Path) -> dict:
    w = build_manor(tmp)
    keyed = [
        ("reset from nothing (no cursor)", None),
        ("nothing changed: empty ops", None),
        ("the view gains a fact: put known",
         lambda w: view(w, T("obj:desk", "colour", "oak"))),
        ("a new item in the drawer: put present",
         lambda w: canon(w, T("obj:coin", "kind", "coin"), E("obj:coin", "in", "obj:desk"),
                         T("obj:coin", "slot", "left drawer"))),
        ("a look changes: put present",
         lambda w: canon(w, T("obj:ring", "material", "silver", timeless=False,
                              valid_from=5.0))),
        ("canon moves the coin out of the covered places: del present",
         lambda w: canon(w, E("obj:coin", "in", "place:hall", timeless=False,
                              valid_from=6.0))),
        ("the player opens the drawer: reveal, then put known (no del for the handle)",
         lambda w: view(w, T("obj:key", "kind", "key"), E("obj:key", "in", "obj:desk"))),
        ("the view's last row for a subject is retracted: del known",
         lambda w: [w.porcelain.retract(r.id, "gone")
                    for r in w.buffer.visible(entity="obj:vase", frame=VF)]),
    ]
    seqs = [_run(w, "keyed: every op", KEY, keyed)]
    # a mode change: a keyed document fed by a keyless service is reset, present null
    keyed_doc = seqs[0]["steps"][-1]["expect"]
    seqs.append(_run(w, "mode change: keyed document, keyless feed", None,
                     [("reset, present becomes null", None)], start=keyed_doc))
    seqs.append(_run(w, "keyless: present stays null", None,
                     [("reset from nothing", None),
                      ("the view gains a fact: put known",
                       lambda w: view(w, T("obj:desk", "finish", "waxed")))]))
    return {
        "schema": mirror.SCHEMA,
        "about": "Replay each sequence: start from `start`, apply every step's `answer` in "
                 "order, and compare the document to `expect` after each. Documents compare "
                 "as JSON values (object key order is free). Cursors are opaque: carry them, "
                 "never read them.",
        "world_id": WORLD_ID, "view_frame": VF,
        "sequences": seqs,
    }


def render(vectors: dict) -> str:
    return json.dumps(vectors, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        text = render(build_vectors(Path(tmp)))
    VECTORS.parent.mkdir(exist_ok=True)
    VECTORS.write_text(text, encoding="utf-8")
    print(f"wrote {VECTORS} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
