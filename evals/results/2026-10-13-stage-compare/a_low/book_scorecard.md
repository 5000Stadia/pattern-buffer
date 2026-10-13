# Book scorecard (a_low) [through_chapter: 2]

Readers: A (Claude Sonnet, final), B (Claude Opus, final); 15 entries dropped.

through_chapter: 2; 0 correction(s) pending (stated, not yet corrected; outside the scores).

## Headline (judging order)

| # | measure | value | target |
|---|---|---|---|
| 1 | wrong merges across look-alike pairs | 0 | 0 |
| 2 | leaks | 1 | 0 |
| 3 | false beliefs in canon | 0 | 0 |
| 4 | existing scores | see the scores below |  |
| 5 | time and cost | 103.1 s, $0.377235 |  |

| measure | score |
|---|---|
| identity B3 F1 | 0.769 |
| reveals joined | 1.000 |
| look-alikes kept apart | 1.000 |
| order (mean LCS) | 0.230 |
| final container | 0.182 |
| ever in container | 0.267 |
| revealed contents placed | 0.476 |

## Identity

- B3 precision 1.000, recall 0.625, over 45 entities and 79 mentions
- split: `first_house`
- fused closures: none
- missing: `address_tag`, `alis_name`, `chamber_note`, `eren_tag`, `hall_map`, `hall_old_keeper`, `hinge`, `ledger`, `petition`, `pocket_strip`, `recipe_sheet`, `red_key_tooth`, `satchel`, `tree_fruit`, `washers`, `winter_roll`

## Look-alikes merged

- none

## Reveals not joined

- none

## Order by object

- `blue_thread` 0.000: expected tin_orchard > pell; world (none)
- `bone_comb` 1.000: expected tovan; world tovan
- `brass_map` 0.500: expected tin_box > tovan; world tin_box
- `eren_tag` 0.000: expected vellum_hall > eren_vey; world (none)
- `eren_vey` 0.000: expected vellum_hall > tin_orchard > vellum_hall > understair; world sump
- `false_bottom` 0.000: expected tin_box; world (none)
- `glass_thimble` 0.667: expected tin_box > pell > ivara; world false_bottom > tin_box > ivara
- `hall_map` 0.000: expected vellum_hall; world (none)
- `handprint_strip` 1.000: expected tin_orchard > ivara; world tin_orchard > ivara > vellum_hall
- `hinge` 0.000: expected tin_orchard; world (none)
- `ivara` 0.000: expected vellum_hall > tin_orchard > understair; world sleeping_gallery > sump
- `ledger` 0.000: expected vellum_hall; world (none)
- `nima` 0.000: expected tin_orchard; world (none)
- `paper_note` 0.000: expected tin_box; world false_bottom
- `pell` 0.500: expected vellum_hall > understair; world understair > sump > registry
- `petition` 0.000: expected vellum_hall; world (none)
- `pocket_strip` 0.000: expected vellum_hall; world (none)
- `red_key` 0.250: expected vellum_hall > tin_orchard > vellum_hall > ivara; world ivara > stone_basin
- `red_key_tooth` 0.000: expected ivara; world (none)
- `registry` 0.000: expected oru; world (none)
- `round_door` 1.000: expected sump; world sump
- `satchel` 0.000: expected vellum_hall; world (none)
- `sleeping_gallery` 1.000: expected vellum_hall; world vellum_hall
- `tin_box` 0.286: expected vellum_hall > tin_orchard > ivara > pell > vellum_hall > understair > pell; world ?obj:lost_property_shelf > ?obj:ivara_satchel > ivara > stone_basin > pell > sump
- `tovan` 0.000: expected vellum_hall; world mouth_room > sump
- `tree_fruit` 0.000: expected tin_orchard; world (none)
- `washers` 0.000: expected tin_orchard > nima; world (none)

## Leaks (target 0)

- total 1
- alias leaks: 0
- chunk leaks: 0; registry leaks: 1; ambiguous rows (not charged): 0; unmapped rows (not charged): 0
  - `pell` / 'eren vell' (reveal 2): 0 chunk-leak rows, first leaking chapter n/a, registry leak True
- aliases left out of chunk classification: none

## Beliefs

- false beliefs: 0 verified entries, 0 measured, 0 unmatched; false in canon 0 (target 0); held by the believer 0 (n/a)
- corrections: 2 verified entries; ends at the corrected value 0 of 1; claim still held after the correction 0 (target 0); 2 with an unmatched part

## Point of view

- learns: 1 entries, held by the end 0 (0.0), learned too early 0, unmatched 0
- never learns: 0 entries, violations 0 (target 0), unmatched 0

## Structured fields (entries / verified / dropped)

- alias_first_chapter: 112 / 111 / 1
- beliefs: 5 / 0 / 5
- corrections: 7 / 3 / 4
- knowledge: 4 / 1 / 3

## Not graded

- corrections: 2 entries
- false_beliefs: 5 entries
- knowledge: 3 entries
