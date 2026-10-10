# Pass-0 registry scorecard (par1b)

| metric | value |
|---|---|
| coverage | 28/28 |
| fragmented gold entities | 13 |
| fused registry ids | 0 |
| mentions resolved | 48/62 |
| B3 precision | 1.000 |
| B3 recall | 0.712 |
| B3 F1 | 0.832 |
| registry ids (total) | 159 |

## Fragmentation (one gold entity, 2+ ids)

- `bazaar`: `place:bazaar`, `place:bazaar_level`
- `core`: `obj:core`, `obj:master_meter_memory_core`, `obj:memory_core`
- `desk`: `obj:ilsa_desk`, `obj:ilsa_renns_desk`
- `false_drawer`: `obj:false_drawer`, `obj:ilsa_desk_false_drawer`
- `footlocker`: `obj:footlocker`, `obj:tovan_footlocker`
- `ilsa`: `person:ilsa_renn`, `person:tin_ear_clerk`
- `letter`: `obj:tovan_letter`, `obj:tovan_note`
- `personal_case`: `obj:crays_personal_case`, `obj:personal_case`
- `records_vault`: `place:records_vault`, `place:vault`
- `sela`: `person:sela`, `person:sela_voss`
- `tovan`: `person:tovan`, `person:tovan_voss`
- `vial_crate`: `obj:sample_vials`, `obj:wooden_crate_vials`
- `wellhead`: `org:wellhead`, `place:wellhead`

## Fusion (one id, 2+ gold entities)

- none

## Unresolved mentions by entity

- `maps` (2/4): 'survey maps', "tovan's aquifer maps"
- `ilsa` (1/4): 'ilsa'
- `anchor` (1/3): 'settlement of anchor'
- `false_drawer` (1/2): "ilsa's false drawer"
- `condenser_station` (1/2): "sela's condenser station"
- `cigarette_tin` (2/3): 'steel tin', 'tin of cigarettes'
- `figs` (1/4): 'twist of three dried figs'
- `vial_crate` (2/4): 'crate of twelve empty sample vials', 'vial crate'
- `fuse_tin` (2/3): 'fuse tin', 'tin of spare fuses'
- `archive` (1/2): 'archive'
