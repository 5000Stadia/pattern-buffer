"""R1-R10 graders (MICRO-EVAL-V1 §2), against the v1-final key's values.

Expected values are transcriptions of evals/household_dialogue/key.md —
grader-only; nothing here reaches any ingest path.
"""

from __future__ import annotations

from patternbuffer import World
from patternbuffer.thunks import UNKNOWN

from battery import Verdict, ent, rows_about


def _speaker_rows(w: World, eid: str, attr: str):
    return [r for r in w.buffer.visible()
            if w.registry.resolve(r.entity) == eid and r.attribute == attr]


def run_battery_micro(w: World) -> list[Verdict]:
    v: list[Verdict] = []
    add = v.append
    drill = ent(w, "drill") or "obj:drill"
    van = ent(w, "van") or "obj:van"
    cabinet = ent(w, "cabinet") or "obj:kitchen_cabinet"
    key = ent(w, "rental_key") or "obj:rental_key"
    fittings = ent(w, "fittings") or "obj:fittings_box"

    # R1 — irrealis filtering: no stated/observed FACT rows from irrealis
    # turns. Registry identity rows (kind/name/alias) are entity existence,
    # not fact claims; `assumed` is the spec's allowed hypothetical outcome.
    IDENT = {"kind", "name", "alias"}
    mm = [r for r in w.buffer.visible()
          if "multimeter" in r.entity and r.status in ("stated", "observed")
          and r.attribute not in IDENT]
    bikes = [r for r in w.buffer.visible()
             if "bike" in (r.entity + str(r.value))
             and r.attribute not in IDENT
             and r.status in ("stated", "observed")]
    ok = not mm and not bikes
    add(Verdict(1, "irrealis filtering", "PASS" if ok else "FAIL",
                None if ok else "extraction",
                f"stated/observed irrealis fact rows: multimeter={len(mm)} conditional={len(bikes)}"))

    # R2 — intention: zero rows place the drill in the van before day 4.
    drill_in = [r for r in _speaker_rows(w, drill, "in")
                if r.value == van]
    fold_d1 = w.state(drill, "in", valid_as_of=1.0)
    ok = not drill_in and fold_d1.winner is not None and "garage" in str(
        w.locate(drill, valid_as_of=1.0) + [fold_d1.winner.value])
    add(Verdict(2, "intention is not fact", "PASS" if ok else "FAIL",
                None if ok else ("shape" if drill_in else "extraction"),
                f"drill->van rows={len(drill_in)}; drill@day1={fold_d1.winner.value if fold_d1.winner else None}"))

    # R3 — self-correction: the OUTCOME is graded — folds to 4, no flag.
    # Two acceptable mechanisms: corr->retraction of an emitted 3-row, OR
    # single-utterance collapse (the model never asserts the withdrawn 3 —
    # the corr proposal correctly finds no prior and stands down).
    rental = None
    for cand in ("place:rental", "place:rental_house"):
        if any(r.entity == cand for r in w.buffer.all_rows()):
            rental = cand
            break
    fold_b = w.state(rental, "bedroom_count") if rental else None
    three_alive = rental and any(
        r.value == 3 for r in w.buffer.visible(entity=rental, attribute="bedroom_count"))
    ok = (fold_b is not None and fold_b.winner is not None
          and fold_b.winner.value == 4 and not fold_b.conflicted
          and not three_alive)
    add(Verdict(3, "self-correction grace (outcome: folds corrected, no flag)",
                "PASS" if ok else "FAIL", None if ok else "extraction",
                f"entity={rental} fold={fold_b.winner.value if fold_b and fold_b.winner else None} "
                f"conflicted={fold_b.conflicted if fold_b else None} stale-3-alive={three_alive}"))

    # R4 — cross-speaker contradiction: fuel flag fires, both alive.
    fold_f = w.state(van, "fuel") if w.state(van, "fuel").winner else \
        w.state(van, "fuel_type")
    ok = fold_f.conflicted and len(fold_f.conflicting) >= 2
    add(Verdict(4, "genuine contradiction flags (cross-speaker)",
                "PASS" if ok else "FAIL",
                None if ok else ("shape" if fold_f.winner else "extraction"),
                f"conflicted={fold_f.conflicted} parties={len(fold_f.conflicting)}"))

    # R5 — cursor humility: fittings chain excludes the office.
    chain = w.locate(fittings, valid_as_of=3.0)
    direct = w.state(fittings, "in", valid_as_of=3.0)
    in_chain = [direct.winner.value if direct.winner else None] + chain
    office = ent(w, "office") or "place:office"
    ok = van in in_chain and office not in in_chain
    add(Verdict(5, "cursor humility", "PASS" if ok else "FAIL",
                None if ok else "extraction", f"chain={in_chain}"))

    # R6 — interval time: arrival found inside, absent outside. The
    # arrival may live on the box entity or the fittings entity.
    arrived = [r for r in w.buffer.visible()
               if ("fitting" in r.entity or "box" in r.entity)
               and r.valid_from is not None and r.valid_from < 0]
    inside = any(r.valid_from <= -5.5 and (r.valid_to is None or r.valid_to > -5.5)
                 for r in arrived)
    outside = not any(r.valid_from <= -8 and (r.valid_to is None or r.valid_to > -8)
                      for r in arrived)
    ok = bool(arrived) and inside and outside
    add(Verdict(6, "fuzzy time as honest interval", "PASS" if ok else "FAIL",
                None if ok else "extraction",
                f"pre-week rows={len(arrived)} inside@-5.5={inside} outside@-8={not outside}"))

    # R7 — synonym: accrued alias 'the cupboard' on the cabinet, sourced
    # to a tier-2 receipt; second-use resolution via tier 1a.
    accrued = [r for r in w.buffer.visible()
               if r.attribute == "alias" and r.value == "the cupboard"
               and w.registry.resolve(r.entity) == cabinet]
    receipted = accrued and any(
        "refer:tier2" in str(m.value)
        for m in w.buffer.visible(entity=accrued[0].id, attribute="source"))
    kitchen = next((c for c in ("place:kitchen",) 
                    if any(r.entity == c for r in w.buffer.all_rows())), None)
    r7_first = w.refer("the cupboard", scope=kitchen)  # 018: scope-bounded
    accrued = [r for r in w.buffer.visible()
               if r.attribute == "alias" and r.value == "the cupboard"
               and w.registry.resolve(r.entity) == cabinet]
    receipted = accrued and any(
        "refer:tier2" in str(m.value)
        for m in w.buffer.visible(entity=accrued[0].id, attribute="source"))
    r7 = w.refer("the cupboard")  # second use: tier 1a, no scope needed
    ok = (r7_first.status == "resolved" and bool(accrued) and bool(receipted)
          and r7.status == "resolved" and r7.receipt.get("signals") == ["alias_exact"])
    add(Verdict(7, "vocabulary drift learns (018)", "PASS" if ok else "FAIL",
                None if ok else "extraction",
                f"accrued={bool(accrued)} receipted={receipted} second_use={r7.status}"))

    # R8 — negation: drill confirmed in garage at day ~4; still no van rows.
    fold_d4 = w.state(drill, "in", valid_as_of=4.5)
    confirm = [r for r in _speaker_rows(w, drill, "in")
               if r.valid_from is not None and r.valid_from >= 4.0]
    ok = (fold_d4.winner is not None and van != fold_d4.winner.value
          and bool(confirm))
    add(Verdict(8, "negation confirms the old state", "PASS" if ok else "FAIL",
                None if ok else "extraction",
                f"day4 confirm rows={len(confirm)} fold={fold_d4.winner.value if fold_d4.winner else None}"))

    # R9 — unknown floor: gray bin's wider contents unknown; no invention.
    bin_ = ent(w, "gray_bin") or "obj:gray_bin"
    res = w.resolve(bin_, "other_contents")
    generated = [r for r in w.buffer.all_rows() if r.status == "generated"]
    ok = res is UNKNOWN and not generated
    add(Verdict(9, "unknown stays unknown", "PASS" if ok else "FAIL",
                None if ok else "shape",
                f"resolve={'UNKNOWN' if res is UNKNOWN else res} generated_rows={len(generated)}"))

    # R10 — wall-clock rider on every STATE/EVENT row.
    from patternbuffer.classify import EVENT, STATE
    from patternbuffer.model import META_ATTRIBUTES
    missing = []
    for r in w.buffer.visible():
        if r.entity.startswith(("a:", "world:")) or r.attribute in META_ATTRIBUTES \
                or r.attribute in ("alias", "name"):
            continue
        if w.classifier.durability(r.id) in (STATE, EVENT) and r.valid_from is not None:
            if not w.buffer.visible(entity=r.id, attribute="learned_at_wallclock"):
                missing.append(r.id)
    ok = not missing
    add(Verdict(10, "wall-clock rider (A1)", "PASS" if ok else "FAIL",
                None if ok else "shape", f"missing on {len(missing)} rows"))
    return v
