# MERGE-GATE-V1 part 2: scoring against the pass mark

Complete (all five registries): **True**. Pass: **True**.

| rep | no `same` on gold-different | gold-same merged (>= 8 of 11) | F1 not below default | unlabelled `same` |
|---|---|---|---|---|
| 1 | PASS | PASS (9 of 11) | PASS | 22 |
| 2 | PASS | PASS (8 of 11) | PASS | 22 |

## Pairs whose verdict differs between repetitions (29)

- `r23-run1` obj:desk_crimp_blanks / obj:seal_blanks: ['different', 'unsure']
- `r23-run1` obj:gray_stuff / obj:gray_stuff_bottle: ['different', 'unsure']
- `r23-run1` obj:seed_vault_hatch / place:wellhead_hatch: ['different', 'unsure']
- `r23-run2` doc:seed_vault_ledgers / place:seed_vault: ['unsure', 'different']
- `r26-par1b` doc:council_allocation_books / obj:inventory_ledger: ['different', 'unsure']
- `r26-par1b` doc:cray_ledgers / doc:crays_books: ['unsure', 'same']
- `r26-par1b` obj:crays_personal_case / obj:footlocker: ['unsure', 'different']
- `r26-par1b` obj:crays_personal_case / obj:memory_core_case: ['different', 'unsure']
- `r26-par1b` obj:gallery_display / obj:number_display: ['different', 'unsure']
- `r26-par2b` doc:council_allocation_books / doc:councils_books: ['unsure', 'same']
- `r26-par2b` doc:councils_books / obj:marns_books: ['different', 'unsure']
- `r26-par2b` doc:second_books / obj:crays_books: ['different', 'unsure']
- `r26-par2b` doc:vault_ledger / obj:inventory_ledger: ['same', 'unsure']
- `r26-par2b` doc:vault_ledger / place:records_vault: ['different', 'unsure']
- `r26-par2b` doc:vault_ledger / place:seed_vault: ['different', 'unsure']
- `r26-par2b` event:memory_core_theft / obj:core: ['different', 'unsure']
- `r26-par2b` event:memory_core_theft / obj:master_meter_memory_core: ['different', 'same']
- `r26-par2b` event:technicians_death / event:tovan_death: ['same', 'unsure']
- `r26-par2b` obj:bulletin_wall / obj:gallery_display: ['different', 'unsure']
- `r26-par2b` obj:core / obj:master_meter_memory_core: ['same', 'unsure']
- `r26-par2b` obj:cray_personal_case / obj:steel_document_case: ['different', 'unsure']
- `r26-par2b` obj:crays_books / obj:seed_vault_ledgers: ['different', 'unsure']
- `r26-par2b` obj:gallery_display / place:gallery: ['different', 'same']
- `r26-par2b` obj:lead_crimp_blanks / obj:seal_blanks: ['different', 'unsure']
- `r26-par2b` obj:pneumatic_ledger_racks / place:records_vault_racks: ['same', 'unsure']
- `r26-par2b` person:ilsa_renn / person:tin_ear_clerk: ['different', 'unsure']
- `r26-par2b` place:aquifer_site / place:survey_site: ['same', 'unsure']
- `r26-seq` obj:desk_crimp_blanks / obj:seal_blanks: ['unsure', 'different']
- `r26-seq` place:desert / place:salt_flats: ['unsure', 'different']

## 20 sampled unlabelled `same` pairs of 26 (not scored)

- `r26-par1b` doc:canonical_books ["the Council's books", 'the accounting', 'the books', 'the canonical books'] / doc:council_allocation_books ['the Council allocation books'] (keep doc:canonical_books; reps [1, 2]): Both describe the official Council allocation records that don't reconcile with the master meter total; 'canonical books' and 'Council allocation books' are the same document set.
- `r26-par1b` doc:cray_ledgers ["Cray's ledgers"] / doc:crays_books ["Cray's books"] (keep doc:crays_books; reps [2]): 'Ledgers' and 'books' are synonyms for the same accounting records belonging to Cray; 'Cray's books' appears in context and is the working term used.
- `r26-par1b` doc:door_log ['the door log'] / obj:door_log ['the door log'] (keep doc:door_log; reps [1, 2]): Both cards share identical name, identical context sentences, and describe the same Wellhead door access record — the doc and obj kinds are a registry duplication of one thing.
- `r26-par1b` event:marn_tribunal ["Marn's tribunal"] / org:tribunal ['the tribunal'] (keep event:marn_tribunal; reps [1, 2]): both name the single specific proceeding against Marn; org:tribunal shares context sentences with event:marn_tribunal and is the same instance, not a standing body
- `r26-par1b` event:technician_death ["the technician's death"] / event:tovan_death ["Tovan's death", 'the Voss matter'] (keep event:tovan_death; reps [1, 2]): the technician who died is Tovan Voss; both events reference the same death, and tovan_death carries fuller provenance and aliases
- `r26-par1b` org:allocation_office ['the Allocation Office', "the Council's Allocation Office"] / place:allocation_office ['the Allocation Office'] (keep org:allocation_office; reps [1, 2]): Same place split across org and place kinds — identical name, identical sentences, one real-world office; 'a' carries the more formal name 'the Council's Allocation Office'.
- `r26-par2b` doc:canonical_books ['the canonical books'] / obj:canonical_ledgers ['the canonical ledgers'] (keep obj:canonical_ledgers; reps [1, 2]): Both describe the same physical records in the vault: floor-to-ceiling official ledgers alongside seal blanks and dead administrators' files; 'canonical ledgers' is just a slightly fuller name.
- `r26-par2b` doc:second_books ['the second set of books'] / obj:seed_vault_ledgers ["ledgers in Cray's hand"] (keep obj:seed_vault_ledgers; reps [1, 2]): Both share the identical name 'the second set of books' and the same vault-ledger context quote; obj:seed_vault_ledgers carries richer aliases.
- `r26-par2b` doc:vault_ledger ['the vault inventory ledger'] / obj:inventory_ledger ["Ilsa's inventory ledger", 'the inventory ledger'] (keep obj:inventory_ledger; reps [1]): Both are the ledger Ilsa uses to record vault intake — 'Nothing comes into the vault without my hand on the ledger'; obj:inventory_ledger carries richer context and keeper attribution.
- `r26-par2b` event:badge_entry_2340 ['the 2340 badge entry'] / event:second_entry ['the 2340 entry', 'the second entry'] (keep event:badge_entry_2340; reps [1, 2]): Both name the same door-log event: the badge passage through the Wellhead hatch at 2340, called the second entry in context.
- `r26-par2b` event:dome_breach ['the dome breach'] / event:the_breach ['the breach year'] (keep event:dome_breach; reps [1, 2]): Both refer to the same historical breach of Anchor's dome in its early years; 'the breach year' is just a temporal framing of the same event.
- `r26-par2b` event:memory_core_theft ['core theft', 'memory core pulled'] / obj:master_meter_memory_core ['memory core', 'the memory core'] (keep obj:master_meter_memory_core; reps [2]): Both refer to the same physical object — the memory core pulled from the master meter; b has the fuller, more specific name.
- `r26-par2b` event:technicians_death ['the night the technician died'] / event:tovan_death ["Tovan's death", 'the night Tovan died'] (keep event:tovan_death; reps [1]): Tovan's badge is explicitly called 'the technician's guild badge,' making 'the night the technician died' and 'the night Tovan died' the same event.
- `r26-par2b` obj:gallery_display ['gallery display'] / place:gallery ['the gallery'] (keep place:gallery; reps [2]): The gallery display is the display screen/wall in the gallery — 'place:gallery' already lists 'gallery display' as an alias, and both contexts describe the same wall where data columns were shown to the settlement.
- `r26-par2b` obj:master_meter_housing ['master meter housing', 'the meter housing'] / place:meter_housing ['the old housing'] (keep obj:master_meter_housing; reps [1, 2]): Both refer to the physical casing of the master meter; 'the meter housing' (a's name) matches 'meter housing' (b's alias) directly, and the scorch context applies to the same object.
- `r26-par2b` obj:pneumatic_ledger_racks ['the pneumatic ledger racks'] / place:records_vault_racks ['the racks'] (keep obj:pneumatic_ledger_racks; reps [1]): Both contexts describe the same office with three clerks sitting near a wall of ledger racks — the clerk who 'sat nearest the racks' is sitting nearest the pneumatic ledger racks.
- `r26-par2b` org:allocation_office ['Allocation Office', "Council's Allocation Office"] / place:allocation_office ['the Allocation Office'] (keep org:allocation_office; reps [1, 2]): Both share the identical context sentence and name the same physical-and-institutional entity; the org/place split is a registry artifact.
- `r26-par2b` place:aquifer_site ['the aquifer site'] / place:southern_aquifer ['the southern aquifer site'] (keep place:southern_aquifer; reps [1, 2]): Both are the southern aquifer location tied to the Voss family survey; Tovan verified his father's site, making them the same place.
- `r26-par2b` place:condenser_facility ['condenser facility', 'the condensers'] / place:condenser_station ['condenser station', 'the condenser station'] (keep place:condenser_station; reps [1, 2]): Both describe the facility past the Rust Quarter where Sela works; 'condenser station' with alias 'sela's station' is more complete.
- `r26-seq` org:allocation_office ['Allocation Office', 'the Allocation Office', "the Council's Allocation Office"] / place:allocation_office ['Allocation Office'] (keep org:allocation_office; reps [1, 2]): Both sides describe the same named office on the Council tier that holds canonical books and records — org and physical location are the same entity here.
