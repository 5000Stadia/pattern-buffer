# Pass-0 identity after seeding and reconcile (par1b)

| metric | value |
|---|---|
| coverage | 28/28 |
| fragmented gold entities | 4 |
| fused registry ids | 1 |
| mentions resolved | 48/62 |
| B3 precision | 0.984 |
| B3 recall | 0.712 |
| B3 F1 | 0.826 |
| registry ids (total) | 135 |

## Fragmentation (one gold entity, 2+ ids)

- `desk`: `obj:ilsa_desk`, `obj:ilsa_renns_desk`
- `ilsa`: `person:ilsa_renn`, `person:tin_ear_clerk`
- `vial_crate`: `obj:sample_vials`, `obj:wooden_crate_vials`
- `wellhead`: `org:wellhead`, `place:wellhead`

## Fusion (one id, 2+ gold entities)

- `place:records_vault`: `records_vault`, `seed_vault`

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
