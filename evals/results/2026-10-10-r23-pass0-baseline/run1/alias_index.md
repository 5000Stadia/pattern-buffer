# Alias index (run1)

95 ids, 4 segments, 174 identifying strings (3 stoplisted).

| item | count |
|---|---|
| 2 ambiguous strings | 3 |
| 4 escape candidates | 11 |
| 5 distinctness pairs (strong) | 1 (1) |
| 6 merge candidates (excluded) | 1 (0) |

## Ambiguous strings (one string, 2+ ids)

- `vault` (15 mentions): `place:records_vault`, `place:seed_vault`, `place:vault`
- `assembly` (3 mentions): `event:anchor_panic`, `event:open_assembly`
- `ilsa renn` (2 mentions): `person:ilsa_renn`, `person:tin_ear_clerk`

## Distinctness evidence

- `place:records_vault` / `place:seed_vault` (strong)
  - distinct_proper_names (strong, x1): different proper names: 'Records Vault' vs 'Seed Vault'

## Merge candidates

- `person:tin_ear_clerk` lists `ilsa renn`, the name of `person:ilsa_renn`

## Escape candidates (top 25 by frequency)

- `PERSONAL` x2 in segments [2, 3] (overlaps `obj:personal_case`)
- `Voss` x2 in segments [0] (overlaps `event:tovan_death`, `person:sela_voss`, `person:tovan_voss`)
- `Allocation` x1 in segments [2] (overlaps `org:allocation_office`, `person:marn`, `place:allocation_corridor`)
- `Beside` x1 in segments [2]
- `Decommissioned` x1 in segments [2]
- `Forty-one` x1 in segments [3]
- `Getting` x1 in segments [2]
- `Show` x1 in segments [0]
- `Start` x1 in segments [0]
- `Thief` x1 in segments [0]
- `Water Steward of Anchor` x1 in segments [3] (overlaps `place:anchor`)
