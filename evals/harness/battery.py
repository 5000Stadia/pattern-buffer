"""The interrogation battery: a 1:1 mirror of the letter-003 coverage
matrix (Q1..Q33), graded against the fixtures transcribed from the
v1-final bible. Verdicts: PASS / FAIL / NOT_PLANTED, with failure class
extraction (engineering, fixable) vs shape (whitepaper conversation).

Shape is reserved for invariant violations the engine itself commits:
silent merges, phantom thunk contents, frame leaks, canon mutation.
Missing or wrong extraction is extraction-class.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from patternbuffer import World
from patternbuffer.classify import CONSTITUTIVE, DISPOSITIONAL, EVENT, STATE

import fixtures as FX


@dataclass
class Verdict:
    qid: int
    title: str
    status: str  # PASS | FAIL | NOT_PLANTED
    failure_class: str | None = None  # extraction | shape
    detail: str = ""


# ----------------------------------------------------------------- helpers


def ent(w: World, key: str) -> str | None:
    """Resolve a fixture entity key to the extractor's chosen id."""
    for alias in FX.ENTITIES.get(key, ()):
        hits = w.registry.by_alias(alias)
        if len(hits) == 1:
            return next(iter(hits))
        if len(hits) > 1:
            return sorted(hits)[0]
    # Fuzzy fallback: substring over name/alias rows.
    needles = [a.lower() for a in FX.ENTITIES.get(key, ())]
    best = None
    for row in w.buffer.visible():
        if row.attribute in {"name", "alias"} and isinstance(row.value, str):
            v = row.value.lower()
            if any(n in v or v in n for n in needles):
                best = w.registry.resolve(row.entity)
                break
    return best


def chain(w: World, eid: str, day: float) -> list[str]:
    direct = w.state(eid, "in", valid_as_of=day)
    out = []
    if direct.winner is not None and direct.winner.value_type == "entity":
        out = [w.registry.resolve(direct.winner.value)]
        out += w.locate(out[0], valid_as_of=day)
    return out


def located_in_any(w: World, eid: str, day: float, keys: list[str]) -> bool:
    targets = {ent(w, k) for k in keys} - {None}
    return bool(targets & set(chain(w, eid, day)))


def rows_about(w: World, eid: str):
    return [r for r in w.buffer.visible()
            if w.registry.resolve(r.entity) == eid and not r.entity.startswith("a:")]


def all_frames(w: World) -> set[str]:
    return {r.frame for r in w.buffer.all_rows()}


# ----------------------------------------------------------------- battery


def run_battery(w: World) -> list[Verdict]:
    v: list[Verdict] = []
    add = v.append

    # ---------- SPATIAL
    depth = 0
    seen_entities = {w.registry.resolve(r.entity) for r in w.buffer.visible()
                     if not r.entity.startswith("a:")}
    for e in seen_entities:
        depth = max(depth, len(w.locate(e)))
    add(Verdict(1, "containment tree >=4 deep",
                "PASS" if depth >= 4 else "FAIL",
                None if depth >= 4 else "extraction",
                f"max depth {depth}"))

    a, b = ent(w, FX.NON_CONNECTION["a"]), ent(w, FX.NON_CONNECTION["b"])
    if a and b:
        p = w.path(a, b)
        direct = p is not None and len(p) == 2
        long_ok = p is not None and len(p) - 1 >= FX.NON_CONNECTION["long_path_min_hops"]
        ok = long_ok and not direct
        add(Verdict(2, "lateral graph: long way, no direct edge (feature 9)",
                    "PASS" if ok else "FAIL", None if ok else "extraction",
                    f"path={p}"))
    else:
        add(Verdict(2, "lateral graph (feature 9)", "FAIL", "extraction",
                    "could not resolve council tier / seed vault"))

    core = ent(w, "core")
    fixture_ok = movable_ok = False
    rv, ct = ent(w, "records_vault"), ent(w, "council_tier")
    if rv:
        for r in rows_about(w, rv):
            if r.attribute in {"in", "within"}:
                fixture_ok = w.classifier.durability(r.id) == CONSTITUTIVE
    if core:
        movable_ok = any(
            r.attribute in {"in", "within", "held_by", "carried_by"}
            and w.classifier.durability(r.id) == STATE
            for r in rows_about(w, core)
        )
    add(Verdict(3, "fixture vs movable containment",
                "PASS" if (fixture_ok or rv is None) and movable_ok else "FAIL",
                None if movable_ok else "extraction",
                f"fixture_ok={fixture_ok} movable_ok={movable_ok}"))

    maps = ent(w, "maps")
    locs = []
    if maps:
        for day in (0.5, 4.6, 10.0, 21.5):
            c = chain(w, maps, day)
            if c and (not locs or c[0] != locs[-1]):
                locs.append(c[0])
    ok = len(locs) >= 3
    add(Verdict(4, "object moving through relation types (maps chain)",
                "PASS" if ok else "FAIL", None if ok else "extraction",
                f"distinct holders over time: {locs}"))

    # ---------- DURABILITY
    anchor = ent(w, "anchor")
    reactor_verdict = Verdict(5, "deliberate constitutive contradiction flagged (feature 8)",
                              "FAIL", "extraction", "no reactor rows found")
    if anchor:
        rrows = [r for r in rows_about(w, anchor)
                 if any(h in r.attribute for h in FX.REACTOR_CONTRADICTION["attribute_hints"])
                 or (isinstance(r.value, str) and "reactor" in str(r.value).lower())]
        rrows += [r for r in w.buffer.visible()
                  if "reactor" in r.attribute and r not in rrows]
        values = {r.value for r in rrows if isinstance(r.value, (int, float))}
        if values >= {2, 3} or len(values) >= 2:
            conflicts = w.truth.scan()
            flagged = any(
                ("reactor" in c.attribute) or
                set(FX.REACTOR_CONTRADICTION["values"]) <= {
                    w.buffer.get(i).value for i in c.assertion_ids if w.buffer.get(i)
                }
                for c in conflicts
            )
            both_alive = len([r for r in rrows if r.value in (2, 3)]) >= 2
            if flagged and both_alive:
                reactor_verdict = Verdict(5, reactor_verdict.title, "PASS",
                                          detail=f"flag fired; values {sorted(values)} coexist")
            elif both_alive:
                reactor_verdict = Verdict(5, reactor_verdict.title, "FAIL", "shape",
                                          "both rows present but NO flag fired (silent coexistence)")
            else:
                reactor_verdict = Verdict(5, reactor_verdict.title, "FAIL", "shape",
                                          f"silent merge: only {values} survived")
        elif len(values) == 1:
            reactor_verdict = Verdict(5, reactor_verdict.title, "FAIL", "extraction",
                                      f"only one reactor value extracted: {values}")
    add(reactor_verdict)

    disp = [r for r in w.buffer.visible()
            if w.classifier.durability(r.id) == DISPOSITIONAL]
    add(Verdict(6, "dispositional habits (+3x utterance, feature 10 lenient)",
                "PASS" if disp else "FAIL", None if disp else "extraction",
                f"{len(disp)} dispositional rows"))

    if core:
        core_vals = []
        for r in sorted(rows_about(w, core), key=lambda r: r.valid_from or -1):
            if r.attribute in {"in", "within", "held_by", "carried_by"} and r.value not in core_vals:
                core_vals.append(r.value)
        ok = len(core_vals) >= 4
        add(Verdict(7, "attribute superseded 3+ times (core custody)",
                    "PASS" if ok else "FAIL", None if ok else "extraction",
                    f"core had {len(core_vals)} distinct holders: {core_vals}"))
    else:
        add(Verdict(7, "attribute superseded 3+ times", "FAIL", "extraction",
                    "memory core entity unresolved"))

    crisis = [r for r in w.buffer.visible()
              if re.search(r"ration|crisis|panic|reserve|short", str(r.attribute) + str(r.value), re.I)]
    add(Verdict(8, "world_defining condition (water crisis/rationing)",
                "PASS" if crisis else "FAIL", None if crisis else "extraction",
                f"{len(crisis)} crisis-condition rows"))

    moods = [r for r in w.buffer.visible()
             if r.attribute in {"mood", "emotion", "demeanor", "feeling", "state_of_mind", "nervous"}]
    bad = [r for r in moods if w.classifier.durability(r.id) == CONSTITUTIVE]
    add(Verdict(9, "transient mood -> STATE (asymmetric default)",
                "PASS" if not bad else "FAIL", None if not bad else "shape",
                f"{len(moods)} mood rows, {len(bad)} misclassified CONSTITUTIVE"))

    # ---------- TIME
    stamped = unstamped = 0
    for r in w.buffer.visible():
        if r.entity.startswith("a:"):
            continue
        d = w.classifier.durability(r.id)
        if d in {STATE, EVENT}:
            if r.valid_from is None:
                unstamped += 1
            else:
                stamped += 1
    distinct_days = len({r.valid_from for r in w.buffer.visible() if r.valid_from is not None})
    ok = unstamped == 0 and distinct_days >= 5
    add(Verdict(10, "narrative clock on the spine",
                "PASS" if ok else "FAIL",
                None if ok else ("shape" if unstamped else "extraction"),
                f"stamped={stamped} unstamped={unstamped} distinct_times={distinct_days}"))

    probe = FX.CORE_LOCATIONS[0]
    if core:
        good = located_in_any(w, core, probe["day"], probe["expect_any"])
        rejected = located_in_any(w, core, probe["day"], probe["reject"])
        rows_exist = any(r.valid_from is not None and r.valid_from <= probe["day"] + 0.5
                         for r in rows_about(w, core))
        status = "PASS" if good and not rejected else "FAIL"
        fclass = None if status == "PASS" else ("shape" if rows_exist and rejected else "extraction")
        add(Verdict(11, "off-screen reveal: valid_time != asserted_at (e25)",
                    status, fclass,
                    f"core at day {probe['day']}: chain={chain(w, core, probe['day'])}"))
    else:
        add(Verdict(11, "off-screen reveal (e25)", "FAIL", "extraction", "core unresolved"))

    future = [r for r in w.buffer.visible()
              if (r.valid_from or 0) > 21.5
              or re.search(r"condition|when_|opens_when|until", r.attribute)]
    add(Verdict(12, "future-scheduled/conditional event",
                "PASS" if future else "FAIL", None if future else "extraction",
                f"{len(future)} future/conditional rows"))

    aged = [r for r in w.buffer.visible() if re.fullmatch(r"age|years_dead|years_ago|elapsed.*", r.attribute)]
    add(Verdict(13, "derive-don't-store over time (no stored ages)",
                "PASS" if not aged else "FAIL", None if not aged else "shape",
                f"{len(aged)} stored-age rows"))

    if core:
        results = []
        for p in FX.CORE_LOCATIONS:
            okp = located_in_any(w, core, p["day"], p["expect_any"]) and \
                  not located_in_any(w, core, p["day"], p["reject"])
            results.append((p["label"], okp, chain(w, core, p["day"])))
        ok = all(r[1] for r in results)
        add(Verdict(14, "one object at three timestamps (core)",
                    "PASS" if ok else "FAIL", None if ok else "extraction",
                    "; ".join(f"{l}: {'ok' if o else c}" for l, o, c in results)))
    else:
        add(Verdict(14, "one object at three timestamps", "FAIL", "extraction", "core unresolved"))

    # ---------- FRAMES
    frames = {f for f in all_frames(w) if f.startswith("knows:")}
    populated = [f for f in frames if w.buffer.visible(frame=f)]
    canon_count = len(w.buffer.visible(frame="canon"))
    framed_count = sum(len(w.buffer.visible(frame=f)) for f in populated)
    delta_ok = canon_count > 0 and canon_count > framed_count // max(1, len(populated) or 1)
    ok = len(populated) >= 3 and delta_ok
    add(Verdict(15, ">=3 knowledge frames + canon-minus-everyone delta",
                "PASS" if ok else "FAIL", None if ok else "extraction",
                f"populated frames: {sorted(populated)}"))

    sela = ent(w, "sela")
    telling = Verdict(16, "telling scene: frame transfer, canon unchanged (feature 5)",
                      "FAIL", "extraction", "no door-log row in Sela's frame")
    if sela:
        sela_frames = [f for f in frames if w.registry.resolve(f.removeprefix("knows:")) == sela]
        for f in sela_frames:
            frows = [r for r in w.buffer.visible(frame=f)
                     if re.search(r"door|2340|badge|log", str(r.entity) + str(r.attribute) + str(r.value), re.I)]
            if frows:
                fr = frows[0]
                canon_earlier = [r for r in w.buffer.visible(frame="canon")
                                 if re.search(r"door_log|2340|badge", str(r.entity) + str(r.attribute) + str(r.value), re.I)
                                 and r.asserted_at < fr.asserted_at]
                if canon_earlier:
                    telling = Verdict(16, telling.title, "PASS",
                                      detail=f"frame row {fr.id} after canon rows; provenance retained")
                else:
                    telling = Verdict(16, telling.title, "FAIL", "extraction",
                                      "frame row exists but no earlier canon door-log rows found")
    add(telling)

    official = [r for r in w.buffer.all_rows()
                if re.search(r"thief|coward|suicide|closed", str(r.attribute) + str(r.value), re.I)]
    superseded_or_framed = any(
        r.frame != "canon" or r.status in {"retracted"} or
        w.buffer.visible(entity=r.id, attribute="retracts") != [] or
        (r.valid_to is not None)
        for r in official
    ) or (official and any("vindicat" in str(r.value).lower() or "clean" in str(r.value).lower()
                           for r in w.buffer.all_rows()))
    add(Verdict(17, "contested truth (official story vs canon)",
                "PASS" if official and superseded_or_framed else "FAIL",
                None if official and superseded_or_framed else "extraction",
                f"{len(official)} official-story rows"))

    beliefs = [r for r in w.buffer.all_rows() if r.status in {"inferred", "assumed"}]
    undermined = any(w.buffer.visible(entity=r.id, attribute="retracts") != []
                     for r in w.buffer.all_rows()) or any(
        r.status == "retracted" for r in w.buffer.all_rows())
    add(Verdict(18, "justified-but-wrong belief undermined",
                "PASS" if beliefs and undermined else ("FAIL" if beliefs else "FAIL"),
                None if beliefs and undermined else "extraction",
                f"{len(beliefs)} belief rows; retraction present: {undermined}"))

    # ---------- PROVENANCE
    statuses = {r.status for r in w.buffer.all_rows()}
    ok = "stated" in statuses and ("inferred" in statuses or "assumed" in statuses)
    add(Verdict(19, "inference/assumption distinguishable from narration",
                "PASS" if ok else "FAIL", None if ok else "extraction",
                f"statuses present: {sorted(statuses)}"))

    doc_rows = []
    for r in w.buffer.all_rows():
        for m in w.buffer.visible(entity=r.id, attribute="source"):
            if isinstance(m.value, str) and m.value.startswith("doc:"):
                doc_rows.append(r)
    gap_fold_ok = False
    refuted_loc_ok = False
    if doc_rows:
        for r in doc_rows:
            if isinstance(r.value, (int, float, dict)) and re.search(r"liter|gap|reserve|shortfall", r.attribute, re.I):
                fold = w.state(w.registry.resolve(r.entity), r.attribute)
                val = fold.winner.value if fold.winner else None
                if not fold.conflicted and isinstance(val, (int, float)) and 40000 <= val <= 45000:
                    gap_fold_ok = True
        sv, rvv = ent(w, "seed_vault"), ent(w, "records_vault")
        loc_claims = [r for r in doc_rows
                      if r.value_type == "entity" and r.value in {rvv}
                      or re.search(r"vault|kept|location", r.attribute, re.I)]
        for r in loc_claims:
            subj = w.registry.resolve(r.entity)
            fold = w.state(subj, "in")
            if fold.winner is not None and fold.winner.id != r.id:
                refuted_loc_ok = True
        if not loc_claims:
            refuted_loc_ok = None  # claim not extracted
    status = "PASS" if doc_rows and gap_fold_ok and refuted_loc_ok else "FAIL"
    add(Verdict(20, "document trust chain: per-claim fates (A4)",
                status, None if status == "PASS" else "extraction",
                f"doc rows={len(doc_rows)} quantity_converged={gap_fold_ok} "
                f"false_claim_superseded={refuted_loc_ok}"))

    # ---------- THUNKS
    sealed_results = []
    for spec in FX.SEALED_CONTAINERS:
        eid = ent(w, spec["key"])
        if eid is None:
            sealed_results.append((spec["key"], "FAIL", "extraction", "entity unresolved"))
            continue
        members = w.contents(eid)
        phantom = [m for m in members
                   if any(r.status == "generated" for r in rows_about(w, m))]
        concrete_contents = [r for r in rows_about(w, eid)
                             if r.attribute == "contents" and r.value_type != "unresolved"]
        if phantom or concrete_contents:
            sealed_results.append((spec["key"], "FAIL", "shape",
                                   f"phantom contents: {phantom or concrete_contents}"))
        else:
            sealed_results.append((spec["key"], "PASS", None, "no phantom contents"))
    n_pass = sum(1 for r in sealed_results if r[1] == "PASS")
    add(Verdict(21, "never-opened containers stay unresolved (N=2)",
                "PASS" if n_pass == 2 else "FAIL",
                None if n_pass == 2 else next((r[2] for r in sealed_results if r[2]), "extraction"),
                "; ".join(f"{k}: {s} ({d})" for k, s, _, d in sealed_results)))

    water_found = [r for r in w.buffer.all_rows()
                   if re.search(r"water_found|struck_water|aquifer_confirmed", str(r.attribute), re.I)
                   and r.status in {"stated", "observed", "generated"}]
    add(Verdict(22, "walked-away branch stays frontier (aquifer outcome)",
                "PASS" if not water_found else "FAIL",
                None if not water_found else "shape",
                f"{len(water_found)} premature aquifer-outcome rows"))

    fl = ent(w, "footlocker")
    if fl:
        at_bazaar = located_in_any(w, fl, 7.2, ["bazaar", "sela"])
        at_station = located_in_any(w, fl, 21.5, ["condenser_station", "sela"])
        moved = at_station and bool(chain(w, fl, 7.2)) and chain(w, fl, 7.2) != chain(w, fl, 21.5)
        no_contents = not [r for r in rows_about(w, fl)
                           if r.attribute == "contents" and r.value_type != "unresolved"]
        ok = moved and no_contents
        add(Verdict(23, "locked container changes hands unopened (feature 4/11)",
                    "PASS" if ok else "FAIL",
                    None if ok else ("shape" if not no_contents else "extraction"),
                    f"day7={chain(w, fl, 7.2)} day21={chain(w, fl, 21.5)} sealed={no_contents}"))
    else:
        add(Verdict(23, "locked container moves unopened", "FAIL", "extraction",
                    "footlocker unresolved"))

    # ---------- IDENTITY
    ilsa = ent(w, "ilsa")
    clerk_hits = w.registry.by_alias("the clerk with the tin ear")
    named_hits = w.registry.by_alias("ilsa renn")
    ok = bool(clerk_hits) and clerk_hits == named_hits
    add(Verdict(24, "late binding: clerk == Ilsa Renn (feature 1)",
                "PASS" if ok else "FAIL", None if ok else "extraction",
                f"clerk->{clerk_hits} named->{named_hits}"))

    if ilsa:
        names = {str(r.value).lower() for r in w.buffer.all_rows()
                 if r.attribute in {"name", "alias"}
                 and w.registry.resolve(r.entity) == ilsa}
        ok = len(names) >= 3
        add(Verdict(25, "one person referred 3+ ways",
                    "PASS" if ok else "FAIL", None if ok else "extraction",
                    f"{len(names)} referring expressions: {sorted(names)[:6]}"))
    else:
        add(Verdict(25, "one person referred 3+ ways", "FAIL", "extraction", "Ilsa unresolved"))

    sv, rvv = ent(w, "seed_vault"), ent(w, "records_vault")
    two_vaults = sv is not None and rvv is not None and sv != rvv
    r26 = w.refer("the vault")
    not_guessed = r26.status != "resolved" or not two_vaults
    add(Verdict(26, "coarse container differentiated (vault split, feature 3)",
                "PASS" if two_vaults and r26.status != "resolved" else "FAIL",
                None if two_vaults and r26.status != "resolved" else
                ("extraction" if not two_vaults else "shape"),
                f"two vaults={two_vaults}; refer('the vault')={r26.status} {r26.candidates}"))

    if core:
        r27 = w.refer("the container with the core", constraints=[("contains", core)])
        ok = r27.status == "resolved"
        add(Verdict(27, "reference by constraint only (inversion)",
                    "PASS" if ok else "FAIL", None if ok else "extraction",
                    f"resolved to {r27.entity_id} via {r27.receipt.get('signals')}"))
    else:
        add(Verdict(27, "reference by constraint only", "FAIL", "extraction", "core unresolved"))

    desk = ent(w, "desk")
    if desk:
        r28 = w.refer("the drawer", scope=desk)
        drawers = [e for e in w.contents(desk)
                   if (w.state(e, "kind").winner or None) and "drawer" in str(w.state(e, "kind").winner.value)]
        if len(drawers) >= 2:
            ok = r28.status != "resolved"
            add(Verdict(28, "two same-kind objects in scope: no silent pick",
                        "PASS" if ok else "FAIL", None if ok else "shape",
                        f"drawers={drawers} refer={r28.status}"))
        else:
            add(Verdict(28, "two same-kind objects in scope", "FAIL", "extraction",
                        f"only {len(drawers)} drawer(s) under the desk: {drawers}"))
    else:
        add(Verdict(28, "two same-kind objects in scope", "FAIL", "extraction", "desk unresolved"))

    # ---------- EVENTS
    causal = [r for r in w.buffer.all_rows() if r.attribute == "caused_by"]
    add(Verdict(29, "causal chain >=3 links",
                "PASS" if len(causal) >= 3 else "FAIL",
                None if len(causal) >= 3 else "extraction",
                f"{len(causal)} caused_by edges"))

    # ---------- MYSTERY
    corroborated = False
    for r in w.buffer.all_rows():
        fold = w.state(w.registry.resolve(r.entity), r.attribute)
        if fold.corroborated_by:
            corroborated = True
            break
    add(Verdict(30, "hidden truth, >=2 discovery paths converge (letter + core)",
                "PASS" if corroborated and doc_rows else "FAIL",
                None if corroborated and doc_rows else "extraction",
                f"corroborated key found: {corroborated}"))

    confession = [r for r in w.buffer.all_rows()
                  if re.search(r"confess|admit|broke|confront", str(r.entity) + str(r.attribute) + str(r.value), re.I)]
    add(Verdict(31, "witness with breaking condition (Marn confronted)",
                "PASS" if confession else "FAIL", None if confession else "extraction",
                f"{len(confession)} confession/confrontation rows"))

    inaction = [r for r in w.buffer.all_rows()
                if re.search(r"deplet|running_out|runs_out|schedule|cistern", str(r.entity) + str(r.attribute) + str(r.value), re.I)]
    add(Verdict(32, "consequence-of-inaction (clock material)",
                "PASS" if inaction else "FAIL", None if inaction else "extraction",
                f"{len(inaction)} depletion/clock rows"))

    # ---------- TEXTURE (negative)
    texture = [r for r in w.buffer.all_rows()
               if r.attribute in {"atmosphere", "ambience", "light_quality", "smell",
                                  "sound", "weather_feel", "lighting_color"}]
    add(Verdict(33, "sensory atmosphere did NOT become assertions",
                "PASS" if not texture else "FAIL",
                None if not texture else "extraction",
                f"{len(texture)} texture rows (should be 0)"))

    return v
