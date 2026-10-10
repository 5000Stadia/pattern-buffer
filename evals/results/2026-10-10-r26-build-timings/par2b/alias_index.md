# Alias index (par2b)

167 ids, 4 segments, 276 identifying strings (8 stoplisted).

| item | count |
|---|---|
| 2 ambiguous strings | 26 |
| 4 escape candidates | 12 |
| 5 distinctness pairs (strong) | 1 (1) |
| 6 merge candidates (excluded) | 1 (0) |

## Ambiguous strings (one string, 2+ ids)

- `vault` (14 mentions): `place:records_vault`, `place:seed_vault`, `place:vault`
- `council` (4 mentions): `org:anchor_council`, `org:council`, `org:the_council`
- `flats` (4 mentions): `place:flats`, `place:salt_flats`, `place:the_flats`
- `tribunal` (3 mentions, mixed kinds): `event:marn_tribunal`, `event:tribunal`, `org:tribunal`
- `tovan` (14 mentions): `person:tovan`, `person:tovan_voss`
- `sela` (8 mentions): `person:sela`, `person:sela_voss`
- `cray` (7 mentions): `person:administrator_cray`, `person:cray`
- `wellhead` (7 mentions, mixed kinds): `org:wellhead`, `place:wellhead`
- `badge` (6 mentions): `obj:guild_badge`, `obj:tovan_badge`
- `master meter` (6 mentions): `obj:master_meter`, `obj:master_meter_new`
- `meter` (6 mentions): `obj:master_meter`, `obj:master_meter_new`
- `maps` (5 mentions, mixed kinds): `doc:aquifer_maps`, `obj:aquifer_maps`
- `memory core` (4 mentions): `obj:master_meter_memory_core`, `obj:memory_core`
- `allocation office` (3 mentions, mixed kinds): `org:allocation_office`, `place:allocation_office`
- `false drawer` (3 mentions): `place:false_drawer`, `place:ilsas_desk_false_drawer`
- `assembly` (2 mentions): `event:open_assembly`, `event:the_assembly`
- `bazaar` (2 mentions): `place:bazaar`, `place:bazaar_level`
- `gray stuff` (2 mentions): `obj:bottle`, `obj:narrator_drink`
- `guild` (2 mentions): `org:guild`, `org:tovan_guild`
- `second set of books` (2 mentions, mixed kinds): `doc:second_books`, `obj:seed_vault_ledgers`
- `footlocker` (1 mentions): `obj:footlocker`, `obj:tovan_footlocker`
- `gallery display` (1 mentions, mixed kinds): `obj:gallery_display`, `place:gallery`
- `personal case` (1 mentions): `obj:cray_personal_case`, `obj:personal_case`
- `aquifer maps` (0 mentions, mixed kinds): `doc:aquifer_maps`, `obj:aquifer_maps`
- `council cousin clerk` (0 mentions): `person:council_clerk_a`, `person:council_clerk_b`
- `meter housing` (0 mentions, mixed kinds): `obj:master_meter_housing`, `place:meter_housing`

## Distinctness evidence

- `place:records_vault` / `place:seed_vault` (strong)
  - distinct_proper_names (strong, x1): different proper names: 'the Records Vault' vs 'the Seed Vault'

## Merge candidates

- `place:bazaar_level` lists `bazaar`, the name of `place:bazaar`

## Escape candidates (top 25 by frequency)

- `Allocation` x3 in segments [1, 2] (overlaps `doc:council_allocation_books`, `event:marn_seal_destruction`, `obj:allocation_seal_marn`)
- `PERSONAL` x2 in segments [2, 3] (overlaps `obj:cray_personal_case`, `obj:personal_case`)
- `Voss` x2 in segments [0] (overlaps `person:sela_voss`, `person:tovan_voss`)
- `Beside` x1 in segments [2]
- `Decommissioned` x1 in segments [2]
- `Forty-one` x1 in segments [3]
- `Getting` x1 in segments [2]
- `Like I` x1 in segments [2]
- `Show` x1 in segments [0]
- `Start` x1 in segments [0]
- `Thief` x1 in segments [0]
- `Water Steward of Anchor` x1 in segments [3] (overlaps `person:sela_voss`, `place:anchor`)
