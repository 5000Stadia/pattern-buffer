# Book scorecard (full_iii)

Readers: A (Claude Sonnet, final), B (Claude Opus, final); 33 entries dropped.

## Headline (judging order)

| # | measure | value | target |
|---|---|---|---|
| 1 | wrong merges across look-alike pairs | 0 | 0 |
| 2 | leaks | 0 | 0 |
| 3 | false beliefs in canon | 0 | 0 |
| 4 | existing scores | see the scores below |  |
| 5 | time and cost | 225.4 s, $2.582379 |  |

| measure | score |
|---|---|
| identity B3 F1 | 0.757 |
| reveals joined | 1.000 |
| look-alikes kept apart | 1.000 |
| order (mean LCS) | 0.198 |
| final container | 0.231 |
| ever in container | 0.336 |
| revealed contents placed | 0.424 |

## Identity

- B3 precision 0.988, recall 0.614, over 65 entities and 113 mentions
- split: `chalk_moth`, `first_house`, `numbered_spool`, `pell`, `round_door`, `stool`
- fused closures: `place:mouth_room` = ['mouth_room', 'tin_orchard']
- missing: `address_strip`, `alis_name`, `chamber_note`, `desk_drawer`, `dining_chairs`, `door_passage`, `doorless_roll`, `eren_tag`, `grit_ring`, `hall_map`, `hall_register`, `metal_fruit`, `paper_note`, `petition`, `pocket_strip`, `recipe_note`, `red_key_tooth`, `route_mark`, `shell_wall`, `stair_landing`, `table`, `table_drawer`, `tree_fruit`, `wall_chair`

## Look-alikes merged

- none

## Reveals not joined

- none

## Order by object

- `address_strip` 0.000: expected vellum_hall; world (none)
- `alis` 1.000: expected mouth_room; world ?place:the_room_with_four_names > first_house > mouth_room+tin_orchard
- `black_thread` 0.000: expected first_house > alis; world (none)
- `blue_thread` 0.500: expected tin_orchard > pell; world mouth_room+tin_orchard
- `bone_comb` 0.250: expected tovan > nacre_stair > first_house > vellum_hall; world tovan > mouth_room+tin_orchard > tovan > ?desk of @person:tovan_sere
- `brass_map` 0.500: expected tin_box > tovan > nacre_stair > first_house > ivara > vellum_hall; world tin_box > eren_vey > nacre_stair > eren_vey > ivara
- `desk_drawer` 0.000: expected vellum_hall; world (none)
- `dining_chairs` 0.000: expected first_house; world (none)
- `door_passage` 0.000: expected understair; world (none)
- `doorless_roll` 0.000: expected vellum_hall; world (none)
- `eren_tag` 0.000: expected vellum_hall > eren_vey; world (none)
- `eren_vey` 0.333: expected vellum_hall > tin_orchard > vellum_hall > understair > nacre_stair > vellum_hall; world vellum_hall > understair > sump > understair > first_house > understair
- `false_bottom` 0.000: expected tin_box; world (none)
- `four_name_strip` 0.250: expected nacre_stair > nima > first_house > nima; world nima
- `glass_thimble` 0.571: expected tin_box > pell > ivara > understair > nacre_stair > first_house > mouth_room; world tin_box > pell > ivara > mouth_room+tin_orchard
- `grit_ring` 0.000: expected metal_fruit; world (none)
- `hall_assembly` 0.000: expected vellum_hall; world (none)
- `hall_map` 0.000: expected vellum_hall; world (none)
- `hall_record_room` 0.000: expected vellum_hall; world (none)
- `hall_register` 0.000: expected vellum_hall; world (none)
- `handprint_strip` 0.000: expected tin_orchard > ivara; world (none)
- `hinge` 1.000: expected tin_orchard; world ?obj:tray_with_ring_of_grit > mouth_room+tin_orchard
- `ivara` 0.500: expected vellum_hall > tin_orchard > understair > vellum_hall > nacre_stair > vellum_hall; world vellum_hall > understair > sump > understair > vellum_hall > mouth_room+tin_orchard
- `ledger` 0.000: expected vellum_hall; world (none)
- `metal_fruit` 0.000: expected vellum_hall > nima; world (none)
- `nima` 0.667: expected tin_orchard > nacre_stair > tin_orchard > first_house > vellum_hall > tin_orchard; world mouth_room+tin_orchard > nacre_stair > mouth_room+tin_orchard > vellum_hall
- `numbered_spool` 0.200: expected eren_vey > nacre_stair > tovan > first_house > vellum_hall; world eren_vey
- `paper_bird` 0.000: expected first_house > pell > vellum_hall; world ?obj:drawer > ?coat of @person:eren_vell
- `paper_note` 0.000: expected tin_box; world (none)
- `pell` 0.600: expected vellum_hall > understair > nacre_stair > first_house > vellum_hall; world understair > sump > understair > nacre_stair > ?place:the_room_with_four_names > vellum_hall
- `petition` 0.000: expected vellum_hall; world (none)
- `pocket_strip` 0.000: expected vellum_hall; world (none)
- `recipe_note` 0.000: expected desk_drawer; world (none)
- `recipe_sheet` 0.000: expected desk_drawer > vellum_hall > ivara; world (none)
- `red_key` 0.500: expected vellum_hall > tin_orchard > vellum_hall > ivara > tovan > ivara > nacre_stair > tin_orchard > nima > first_house > tin_box > alis; world vellum_hall > ivara > sump > ivara > tovan > ivara > tin_box > nima > tin_box
- `red_key_tooth` 0.000: expected ivara > tovan > ivara > nima > alis; world (none)
- `registry` 0.000: expected oru; world (none)
- `round_door` 1.000: expected sump; world sump
- `route_mark` 0.000: expected nacre_stair; world (none)
- `satchel` 0.000: expected vellum_hall; world ivara
- `seventh_tooth` 0.000: expected eren_vey; world false_bottom > chalk_moth
- `shell_wall` 0.000: expected nacre_stair; world (none)
- `sleeping_gallery` 1.000: expected vellum_hall; world vellum_hall
- `stair_landing` 0.000: expected nacre_stair; world (none)
- `stool` 0.000: expected first_house; world (none)
- `table` 0.000: expected first_house; world (none)
- `table_drawer` 0.000: expected first_house; world (none)
- `tin_box` 0.364: expected vellum_hall > tin_orchard > ivara > pell > vellum_hall > understair > pell > nacre_stair > first_house > alis > first_house; world satchel > ivara > vellum_hall > stone_basin > pell > first_house
- `tovan` 0.750: expected vellum_hall > nacre_stair > first_house > vellum_hall; world vellum_hall > sump > understair > ?place:the_room_with_four_names > first_house > mouth_room+tin_orchard > vellum_hall
- `tree_fruit` 0.000: expected tin_orchard; world (none)
- `wall_chair` 0.000: expected first_house; world (none)
- `washers` 0.500: expected tin_orchard > nima > nacre_stair > tin_orchard; world nima > mouth_room+tin_orchard
- `winter_roll` 0.000: expected vellum_hall; world (none)

## Leaks (target 0)

- total 0
- alias leaks: 0
- chunk leaks: 0; registry leaks: 0; ambiguous rows (not charged): 0; unmapped rows (not charged): 8
  - `pell` / 'eren vell' (reveal 2): 0 chunk-leak rows, first leaking chapter n/a, registry leak False
- aliases left out of chunk classification: none

## Beliefs

- false beliefs: 3 verified entries, 1 measured, 2 unmatched; false in canon 0 (target 0); held by the believer 0 (0.0)
  - unmatched: `false_beliefs[3]` (attribute)
  - unmatched: `false_beliefs[4]` (attribute)
- corrections: 8 verified entries; ends at the corrected value 1 of 4; claim still held after the correction 0 (target 0); 5 with an unmatched part

## Point of view

- learns: 9 entries, held by the end 0 (0.0), learned too early 0, unmatched 5
- never learns: 0 entries, violations 0 (target 0), unmatched 0

## Structured fields (entries / verified / dropped)

- alias_first_chapter: 161 / 160 / 1
- beliefs: 11 / 3 / 8
- corrections: 27 / 11 / 16
- knowledge: 20 / 9 / 11

## Not graded

- corrections: 10 entries
- false_beliefs: 8 entries
- knowledge: 11 entries
