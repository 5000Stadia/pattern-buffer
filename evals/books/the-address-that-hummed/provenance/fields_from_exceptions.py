"""Convert each final reader's alias_first_chapter exceptions into GRADE-LEAKS-V1
per-field verdicts. Both final readers stated they checked every alias's first
chapter (mechanically, then by reading) and listed only the wrong ones in
`bad_alias_first_chapter`; an alias of an entity they judged `ok` and did not
list is therefore "ok", a listed one is "wrong: <their reason>", and an entity
they did not judge `ok` gets no field verdicts (so its fields are dropped)."""
import json, sys

key = json.load(open(sys.argv[1]))
for path in sys.argv[2:]:
    d = json.load(open(path))
    afc = {}
    for ent, row in key["entities"].items():
        v = d["entities"].get(ent, {})
        if v.get("verdict") != "ok":
            continue
        bad = v.get("bad_alias_first_chapter") or {}
        afc[ent] = {alias: ("wrong: " + str(bad[alias]) if alias in bad else "ok")
                    for alias in row.get("alias_first_chapter", {})}
    d.setdefault("fields", {})["alias_first_chapter"] = afc
    json.dump(d, open(path, "w"), indent=1, ensure_ascii=False)
