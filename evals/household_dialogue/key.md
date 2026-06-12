# Answer key — micro-eval seed (hand-authored; never reaches the ingestor)

Timeline: day 0 = Monday; turn stamps are valid_from values.
Speakers: person:dale, person:meg. World: stance=reality,
policy=observe_or_unknown.

## Registry expectations (pass-0 over the transcript)
Entities: person:dale, person:meg, obj:drill, obj:torque_wrench,
obj:camping_stove, obj:gray_bin, obj:fittings_box (qty 20 fittings),
obj:multimeter, obj:spare_charger, obj:rental_key, obj:van, place:garage,
obj:steel_shelf, place:attic, place:kitchen, obj:kitchen_cabinet ("the
one by the fridge"; aliases: cabinet — NOT cupboard: that synonym is the
R7 plant), obj:kitchen_drawer, place:office, place:rental_house,
obj:workbench, obj:wall_bikes? (NO — see R1 conditional: no bike/wall rows).

## Per-criterion ground truth
- R1 (irrealis): turn 2.11 multimeter hypothetical -> at most assumed,
  conf<=0.5, never stated/observed. Turn 0.15 (sarcasm "logistics
  empire") -> zero rows. Turn 0.13 (question) -> zero rows from the
  question itself. Turn 0.16 (conditional workbench/bikes) -> zero rows.
- R2 (intention): turn 0.17 -> ZERO world rows. Drill location at day
  1.0: place:garage/obj:steel_shelf (from 0.10).
- R3 (self-correction): turn 2.10 -> bedroom_count folds to 4; the
  3-row exists in log but retracted via corr promotion (justified_by
  chain to the proposal); NO conflict flag on the key.
- R4 (genuine contradiction): 0.12 (dale: fuel=diesel) vs 4.10 (meg:
  fuel=gasoline) -> cross-source conflict flag, both alive; fold serves
  incumbent (diesel) pending the ask.
- R5 (cursor humility): turn 2.12 said FROM the office; fittings anchor
  obj:van. place:office must NOT appear in the fittings' chain.
- R6 (fuzzy time): 0.14 -> fittings arrival interval valid over last
  Tuesday (day -6: bounds [-6.0, -5.0) acceptable; any honest day-wide
  interval within last week's Tuesday passes). As-of day -5.5 finds
  arrived; as-of day -8 does not.
- R7 (synonym): 4.12/4.13 "the cupboard" -> resolves to
  obj:kitchen_cabinet via tier-2 on first use (receipt), tier-1a on
  second (accrued alias row, inferred, sourced refer:tier2). Key
  location: obj:rental_key at day 4.2+: held_by person:dale (keyring).
- R8 (negation): 4.11 closes the 0.17 intention (which emitted nothing,
  so: purely-positive confirmation) -> drill in garage/steel shelf
  CONFIRMED as a day-4.11 row by dale; still zero van rows for drill.
- R9 (unknown floor): the gray bin's CONTENTS besides the stove are
  never discussed -> resolve(obj:gray_bin, contents-other) = UNKNOWN;
  also obj:toolchest (never mentioned) -> no rows, refer underdetermined.
- R10 (wall-clock rider): every STATE/EVENT row carries
  learned_at_wallclock meta.

## Other trackable facts (ordinary supersession surface)
- torque wrench: obj:van (0.10).
- camping stove: obj:gray_bin < place:attic (0.11).
- spare charger: obj:kitchen_drawer (2.14).
- rental key chain: obj:kitchen_cabinet (0.18) -> held_by dale (4.13);
  same-speaker? 0.18 meg, 4.13 dale -> cross-speaker MOVEMENT, values
  in sequence (not contradiction: different valid times, movement). The
  fold at day 5 serves held_by dale; NO flag (valid-time progression
  across speaker classes is corroborating movement only if values
  succeed in time without overlap — grader accepts either no-flag or
  conflicted=False precisely).
- fittings: box of 20, in obj:van (0.14, 2.12 reconfirm same speaker).
