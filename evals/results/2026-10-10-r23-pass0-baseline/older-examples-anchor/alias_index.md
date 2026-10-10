# Alias index (older-examples-anchor)

109 ids, 4 segments, 173 identifying strings (3 stoplisted).

| item | count |
|---|---|
| 2 ambiguous strings | 4 |
| 4 escape candidates | 11 |
| 5 distinctness pairs (strong) | 2 (1) |
| 6 merge candidates (excluded) | 1 (0) |

## Ambiguous strings (one string, 2+ ids)

- `allocation office` (3 mentions, mixed kinds): `org:allocation_office`, `place:allocation_office`
- `door` (3 mentions): `obj:door_log_system`, `obj:wellhead_hatch`
- `ilsa renn` (2 mentions): `person:ilsa_renn`, `person:tin_ear_clerk`
- `council cousin clerk` (0 mentions): `person:council_cousin_clerk_a`, `person:council_cousin_clerk_b`

## Distinctness evidence

- `obj:coolant_pipes` / `obj:green_telltales` (strong)
  - coordination (strong, x1): The Wellhead sat at the bottom of Anchor like a heart in a ribcage, all coolant pipes and green telltales.
- `obj:door_log_system` / `obj:wellhead_hatch` (weak)
  - co_presence (weak, x2): named in one paragraph: The door log and the maintenance log are kept by different systems, which is the kind of redundancy that survives an apocalypse because somebody, once, didn't trust somebody else. The maintenance log said Tovan, then no…

## Merge candidates

- `person:tin_ear_clerk` lists `ilsa renn`, the name of `person:ilsa_renn`

## Escape candidates (top 25 by frequency)

- `Allocation` x2 in segments [1, 2] (overlaps `obj:block_meters`, `obj:marn_allocation_seal`, `org:allocation_office`)
- `PERSONAL` x2 in segments [2, 3] (overlaps `obj:personal_case`)
- `Voss` x2 in segments [0] (overlaps `event:tovan_death`, `person:sela_voss`, `person:tovan_voss`)
- `Beside` x1 in segments [2]
- `Decommissioned` x1 in segments [2]
- `Forty-one` x1 in segments [3]
- `Getting` x1 in segments [2]
- `Show` x1 in segments [0]
- `Start` x1 in segments [0]
- `Thief` x1 in segments [0]
- `Water Steward of Anchor` x1 in segments [3] (overlaps `place:anchor`)
