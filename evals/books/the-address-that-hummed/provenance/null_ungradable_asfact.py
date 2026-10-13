"""Blank the as_fact of knowledge entries whose `who` is not an entity of the
key (e.g. "everyone_present"): no learner frame exists to grade them against.
Applied once after the as_fact pass; both final readers had also marked
knowledge[16].as_fact wrong. Their field verdicts for such entries are removed."""
import json, sys
key_path, *verdict_paths = sys.argv[1:]
key = json.load(open(key_path))
blanked = [i for i, e in enumerate(key["knowledge"])
           if e.get("as_fact") is not None and e.get("who") not in key["entities"]]
for i in blanked:
    key["knowledge"][i]["as_fact"] = None
json.dump(key, open(key_path, "w"), indent=2, ensure_ascii=False)
for p in verdict_paths:
    v = json.load(open(p))
    for i in blanked:
        v.get("fields", {}).get("knowledge", {}).pop(str(i), None)
    json.dump(v, open(p, "w"), indent=1, ensure_ascii=False)
print("blanked knowledge", blanked)
