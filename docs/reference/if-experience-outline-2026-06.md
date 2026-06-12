# Interactive-fiction experience engine — brainstorm outline (founder-commissioned)

**Status:** synthesis of the PB↔Kernos exchange (letters PB-015 / K-033),
2026-06-12. Ownership per K's convergence flag: **HD's design docs
(ARC-LAYER.md, SESSION-ZERO.md in /home/k/Newproject) are the canonical
experience-layer design**; this outline is the three-way map — what
exists, what's adopted, what's net-new, and what the engine still owes.

**Product thesis (agreed r1/r2):** the engine supplies cohesion physics —
nothing forgotten, nothing contradicted, nothing invented over canon; the
experience layer supplies drama. The product is a GM that never forgets.

---

## 1. Architecture: the two-lane GM (HD's design; adopt)

- **Navigator** — sees `plot:` frames, evidence graph, pacing instrument;
  decides direction; *writes nothing, speaks nothing*.
- **Narrator** — handed a briefing of `knows:player ∪ scene facts` only;
  speaks; **cannot leak because the spoiler is not in its window**
  (structural absence applied to the renderer — closes §14's honest hole).
- **Concealment audit** (HD): post-hoc diff proving every narrated fact ∈
  briefing. Arc *concealment* is structural-by-window; arc *progress* is
  structural-by-graph (what enters `knows:player` is evidence-gated).

## 2. The five GM faculties (PB r1; each maps to shipped machinery)

remember (folds/as-of; "Previously on…" = establishing_set +
what_happened(since=last_session)) · adjudicate (deterministic state as
rules lawyer) · populate (resolver under constraints, resolution floor,
access-gated depth) · narrate (render leash + style anchors) · foreshadow
(plot: frames, evidence graph, 013 resonances, dramatic-irony delta as
the pacing instrument).

## 3. World genesis & session zero

- Sources: blank+genre kit · **derived-from-a-work** (the chapter-test
  pipeline as product: hand it a novel, play inside it) · authored module.
- Charter at genesis (stance=fiction, genre_era, title) — every world
  self-identifying.
- **Session zero = interview = ingest** (HD's unified interview design is
  canonical: which-sections-known switch, output contract, dispositional-
  spine invariant, lines-and-veils as covenants in the render path).
  Character sheet → canon; player knowledge → knows:player; arc skeleton
  → plot:.
- Settings plane (prefs, not world-facts): camera, verbosity, content
  rating, **difficulty knobs** {resolver generosity, clock aggression,
  fail policy fail-forward|hard} (PB net-new; routed to HD), **canon
  strictness**: pure-PC (utterances are actions; only adjudication
  writes) vs **co-author mode** (player declarations ingest as
  stated-with-speaker-source — the 027 conversational machinery reused
  for collaborative fiction; PB net-new; routed to HD).

## 4. Session ops (K r2)

- Turn-driven with a **world tick** per player turn (clocks, offscreen
  drives), surfaced at turn boundaries; not real-time.
- Push governed by an **aggressive relevance filter, silence default** —
  Kernos's hardest-won ops lesson; the #1 invisible failure mode is the
  filter failing open and the player tuning the GM out.
- Multiplayer: two players = two knows: frames (asymmetry free); the hard
  parts are simultaneity + per-player briefing lanes; defer past
  first-playable.
- Save = the `.world` file (ship in a bottle); suspend/resume free.

## 5. Endings

- **Novel-arc** (HD canonical): beats as world-state conditions,
  achievable_via, four-rung nudge ladder with anti-railroading guards,
  refusal-by-construction, repair-as-supersession; **conclusion shapes**
  with an evaluable premise and three outcomes incl. *early success*
  (the character delta arriving through authentic play). End-state
  detection is structural: a sufficiency condition over knows:player +
  the confrontation event (independently re-derived by PB r1 — the
  convergence that validates the shape).
- **Endless mode** (PB net-new; routed to HD): world-as-place; no global
  sufficiency set; clocks + NPC drives generate situation; **rolling
  micro-arcs** (generated plot: beats with local open/close, via the 029
  generated-through-gate doorway) prevent purposelessness; the pacing
  instrument oscillates tension; the drawer test is the product promise.
- **Post-ending:** denouement procedure (clocks freeze; epilogue =
  what_happened + character-sheet deltas; charter amended
  concluded=true/ending=<id>); then seal · **fork to
  stance=hypothetical for what-if replay** (PB net-new) · or open into
  endless (the campaign model). Tragedy is a valid authored ending.

## 6. Failure modes, ranked (K r2, from Kernos ops)

1. relevance filter failing open (invisible churn) → silence default;
2. silent degradation (ungrounded render faking confidence) → loud-fail,
   "the grid shows through";
3. canon poisoning by the narrator → two-lane split (structural);
4. pacing deadlock → HD's counter-only refusal clock;
5. loop-closure miss → 013 recoverable-forward (MAYBE_SAME_AS).

## 7. What the experience layer needs FROM the engine (PB's lane)

Shipped already: per-item frames + frame= (028), generated-with-guard
(029), what_happened windows (029), deny/reserve thunks, charter stances,
018 refer extensions, 027 speaker machinery (co-author mode's substrate).
**Open engine items, in order:**
1. **Frame-diff read** (`canon minus knows:<id>` / `frame_a minus
   frame_b`) — the pacing instrument's native query; HD double-
   materializes today; first candidate for a sixth read verb at or after
   the porcelain freeze.
2. **Accrual promotion live** (STATE→DISPOSITIONAL on repetition) —
   endless mode's "the world learns its habits" over long play; designed
   in the classifier, not yet exercised.
3. **Frame-inclusion edges** (letter-002 Q2 design; Cyc genlMt precedent)
   — NPC common-knowledge frames at scale (public:town included by every
   knows:npc); becomes load-bearing the day a world has thirty NPCs.
   None block first-playable.
