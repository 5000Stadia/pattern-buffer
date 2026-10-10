# Pass-0 identity after seeding and reconcile (par2b)

| metric | value |
|---|---|
| coverage | 27/28 |
| fragmented gold entities | 7 |
| fused registry ids | 1 |
| mentions resolved | 45/62 |
| B3 precision | 0.984 |
| B3 recall | 0.661 |
| B3 F1 | 0.791 |
| registry ids (total) | 147 |

## Fragmentation (one gold entity, 2+ ids)

- `core`: `obj:core`, `obj:master_meter_memory_core`
- `desk`: `place:ilsa_desk`, `place:ilsas_desk`
- `false_drawer`: `place:false_drawer`, `place:ilsas_desk_false_drawer`
- `ilsa`: `person:ilsa_renn`, `person:tin_ear_clerk`
- `letter`: `doc:tovan_letter`, `obj:tovan_letter`
- `maps`: `doc:aquifer_maps`, `obj:aquifer_maps`
- `wellhead`: `org:wellhead`, `place:wellhead`

## Fusion (one id, 2+ gold entities)

- `place:records_vault`: `records_vault`, `seed_vault`

## Unresolved mentions by entity

- `maps` (2/4): 'survey maps', "tovan's aquifer maps"
- `ilsa` (1/4): 'clerk with the tin ear'
- `anchor` (1/3): 'settlement of anchor'
- `false_drawer` (1/2): "ilsa's false drawer"
- `condenser_station` (1/2): "sela's condenser station"
- `cigarette_tin` (2/3): 'steel tin', 'tin of cigarettes'
- `figs` (3/4): 'figs', 'paper twist of figs', 'twist of three dried figs'
- `vial_crate` (3/4): 'crate of sample vials', 'crate of twelve empty sample vials', 'vial crate'
- `fuse_tin` (1/3): 'tin of spare fuses'
- `archive` (2/2): 'archive', 'unified archive'
