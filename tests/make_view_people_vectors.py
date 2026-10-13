"""Generates tests/vectors/view-feed-people-v1.json (VIEW-PEOPLE-V1 test 9).

The same layout as view-feed-v1.json (see make_view_vectors.py), over the people
fixture, with the people layer on: each sequence is `{start document, feed
answers, the document after each}` for R47's JS `apply` to replay. The Python
`apply` is checked against the same file by tests/test_view_people.py, which also
fails if this generator's output differs from the committed file.

Run `python tests/make_view_people_vectors.py` to rewrite it (after a deliberate
change to the document shape).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from manor_fixture import E, T, canon, view  # noqa: E402
from patternbuffer import mirror  # noqa: E402
from people_fixture import ATTRS, KEY, VF, WORLD_ID, build_people  # noqa: E402

VECTORS = HERE / "vectors" / "view-feed-people-v1.json"


def _empty() -> dict:
    return {"schema": mirror.SCHEMA, "world_id": WORLD_ID, "view_frame": VF,
            "at": None, "cursor": None, "known": {}, "present": None}


def _retract(w, entity: str, attribute: str) -> None:
    for row in w.buffer.visible(entity=entity, attribute=attribute):
        w.porcelain.retract(row.id, "gone")


def _run(w, name: str, key, people, steps: list[tuple[str, object]],
         start: dict | None = None) -> dict:
    """One sequence: the first step is a reset from `start`; each later step
    mutates the world (a callable) and feeds from the cursor the document holds."""
    doc = start if start is not None else _empty()
    out = {"name": name, "start": doc, "steps": []}
    for label, mutate in steps:
        if callable(mutate):
            mutate(w)
        answer = mirror.feed(w, VF, doc["cursor"], key=key, people=people)
        doc = mirror.apply(doc, answer)
        out["steps"].append({"name": label, "answer": answer, "expect": doc})
    return out


def build_vectors(tmp: Path) -> dict:
    w = build_people(tmp)
    every_op = [
        ("reset from nothing (no cursor)", None),
        ("nothing changed: empty ops", None),
        ("an author moves the cook: put people, no known op",
         lambda w: canon(w, E("person:cook", "in", "place:bedroom", timeless=False,
                              valid_from=5.0))),
        ("a person's fact changes: put people",
         lambda w: canon(w, T("person:mara", "posture", "sitting", timeless=False,
                              valid_from=6.0))),
        ("a person is carried into another room: place follows the carrier",
         lambda w: canon(w, E("person:nanny", "in", "place:bedroom", timeless=False,
                              valid_from=7.0))),
        ("a new person appears: put people",
         lambda w: canon(w, T("person:maid", "kind", "person"),
                         E("person:maid", "in", "place:hall"),
                         T("person:maid", "posture", "dusting"))),
        ("the drifter's only fact is retracted: del people",
         lambda w: _retract(w, "person:drifter", "posture")),
        ("the view gains a fact and a person moves: put known and put people",
         lambda w: (view(w, T("obj:desk", "colour", "oak")),
                    canon(w, E("person:maid", "in", "place:kitchen", timeless=False,
                               valid_from=8.0)))),
    ]
    seqs = [_run(w, "keyed, people on: every op", KEY, ATTRS, every_op)]
    on_doc = seqs[0]["steps"][-1]["expect"]
    seqs.append(_run(w, "mode change: people on, then off", KEY, None,
                     [("reset, the people key is removed", None)], start=on_doc))
    off_doc = seqs[-1]["steps"][-1]["expect"]
    seqs.append(_run(w, "mode change: people off, then on", KEY, ATTRS,
                     [("reset, the people layer appears", None)], start=off_doc))
    seqs.append(_run(w, "attribute list changes", KEY, ("posture",),
                     [("reset, only posture crosses", None),
                      ("a person's posture changes: put people",
                       lambda w: canon(w, T("person:mara", "posture", "leaning",
                                            timeless=False, valid_from=9.0)))],
                     start=mirror.apply(_empty(), mirror.feed(w, VF, None, key=KEY,
                                                              people=ATTRS))))
    seqs.append(_run(w, "keyless, position only", None, (),
                     [("reset from nothing: no handles, no present layer", None),
                      ("a person moves: put people",
                       lambda w: canon(w, E("person:cook", "in", "place:hall",
                                            timeless=False, valid_from=10.0)))]))
    return {
        "schema": mirror.SCHEMA,
        "about": "Replay each sequence: start from `start`, apply every step's `answer` in "
                 "order, and compare the document to `expect` after each. Documents compare "
                 "as JSON values (object key order is free). Cursors are opaque: carry them, "
                 "never read them. These answers carry `people_on`; a document has a "
                 "`people` key exactly while its latest answer said so.",
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
