# Alias index

159 ids, 4 segments, 373 identifying strings (15 stoplisted).

| item | count |
|---|---|
| 2 ambiguous strings | 40 |
| 4 escape candidates | 9 |
| 5 distinctness pairs (strong) | 4 (3) |
| 6 merge candidates (excluded) | 2 (0) |

## Ambiguous strings (one string, 2+ ids)

- `vault` (14 mentions): `place:records_vault`, `place:seed_vault`, `place:vault`
- `core` (10 mentions): `obj:core`, `obj:master_meter_memory_core`, `obj:memory_core`
- `assembly` (3 mentions): `event:assembly`, `event:open_assembly`, `event:the_assembly`
- `tribunal` (2 mentions, mixed kinds): `event:marn_tribunal`, `event:open_assembly`, `org:tribunal`
- `tovan` (13 mentions): `person:tovan`, `person:tovan_voss`
- `sela` (8 mentions): `person:sela`, `person:sela_voss`
- `wellhead` (7 mentions, mixed kinds): `org:wellhead`, `place:wellhead`
- `door log` (6 mentions, mixed kinds): `doc:door_log`, `obj:door_log`
- `master meter` (6 mentions): `obj:master_meter`, `obj:new_master_meter`
- `badge` (5 mentions): `obj:guild_badge`, `obj:tovan_badge`
- `books` (4 mentions): `doc:canonical_books`, `doc:council_books`
- `desert` (4 mentions): `place:flats`, `place:salt_flats`
- `flats` (4 mentions): `place:flats`, `place:salt_flats`
- `memory core` (4 mentions): `obj:master_meter_memory_core`, `obj:memory_core`
- `allocation office` (3 mentions, mixed kinds): `org:allocation_office`, `place:allocation_office`
- `case` (3 mentions): `obj:crays_personal_case`, `obj:tovan_footlocker`
- `council` (3 mentions): `org:council`, `org:the_council`
- `false drawer` (3 mentions): `obj:false_drawer`, `obj:ilsa_desk_false_drawer`
- `bazaar` (2 mentions): `place:bazaar`, `place:bazaar_level`
- `gray stuff` (2 mentions): `obj:gray_stuff`, `obj:narrators_bottle`
- `hatch` (2 mentions, mixed kinds): `obj:seed_vault_hatch`, `place:wellhead_hatch`
- `inventory ledger` (2 mentions, mixed kinds): `doc:inventory_ledger`, `obj:inventory_ledger`
- `letter` (2 mentions): `obj:tovan_letter`, `obj:tovan_note`
- `master meter's memory core` (2 mentions): `obj:master_meter_memory_core`, `obj:memory_core`
- `my office` (2 mentions): `place:narrator_office`, `place:narrators_office`
- `records vault` (2 mentions): `place:records_vault`, `place:vault`
- `administrator` (1 mentions): `person:cray`, `person:marn`
- `condensers` (1 mentions, mixed kinds): `obj:survey_condensers`, `place:condenser_site`
- `crimp 0447` (1 mentions): `obj:footlocker`, `obj:maintenance_crimp_seal`
- `footlocker` (1 mentions): `obj:footlocker`, `obj:tovan_footlocker`

## Distinctness evidence

- `person:cray` / `person:marn` (strong)
  - distinct_proper_names (strong, x1): different proper names: 'Administrator Cray' vs 'Marn'
  - co_presence (weak, x2): named in one paragraph: Cray. The name predated me. Marn's predecessor, dead six or seven years now of the lung rot, remembered around Anchor as a builder — the man who'd raised the south dome panel and dug Cistern Three. If Tovan's letter hel…
- `person:sela_voss` / `person:tovan_voss` (strong)
  - distinct_proper_names (strong, x1): different proper names: 'Sela Voss' vs 'Tovan Voss'
  - co_presence (weak, x1): named in one paragraph: Sela Voss was confirmed as Water Steward of Anchor by acclamation she did not ask for and visibly did not enjoy. Her first act was to commission the southern survey: six diggers, two condensers from her own station, and…
- `place:records_vault` / `place:seed_vault` (strong)
  - distinct_proper_names (strong, x1): different proper names: 'the Records Vault' vs 'the Seed Vault'
- `event:dome_breach` / `event:the_collapse` (weak)
  - co_presence (weak, x1): named in one paragraph: I started where paper starts, at the Allocation Office on the Council tier. The office ran on three clerks and a wall of pneumatic ledger racks older than the Collapse. Two of the clerks were Council cousins, soft and i…

## Merge candidates

- `place:bazaar_level` lists `bazaar`, the name of `place:bazaar`
- `place:vault` lists `records vault`, the name of `place:records_vault`

## Escape candidates (top 25 by frequency)

- `PERSONAL` x2 in segments [2, 3] (overlaps `obj:crays_personal_case`, `obj:personal_case`)
- `Beside` x1 in segments [2]
- `Decommissioned` x1 in segments [2]
- `Forty-one` x1 in segments [3]
- `Getting` x1 in segments [2]
- `Show` x1 in segments [0]
- `Start` x1 in segments [0]
- `Thief` x1 in segments [0]
- `Water Steward of Anchor` x1 in segments [3] (overlaps `person:sela_voss`, `place:anchor`)
