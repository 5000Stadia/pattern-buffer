# STORY BIBLE — TEST ANNOTATIONS

*This section is out-of-fiction metadata for the ingestion engine’s evaluation. It maps each planted test feature to its location in the text and states the intended pass condition.*

## Shopping-list features

**1. Late-binding identity** — “The clerk with the tin ear” is introduced unnamed in Chapter Two (Allocation Office scene; multiple references: “the clerk with the tin ear,” “a small gray woman,” “her good ear forward”). She is named **Ilsa Renn** in Chapter Three, with explicit narrative acknowledgment of the late binding (“I’d gone this long without needing it”). Chapter Three also retroactively attributes the second ledger handwriting and the badge-walk to her. **Pass condition:** all unnamed Ch. 2 references and the named Ch. 3+ entity merge into one identity; the Ch. 2 desk references should also merge with the Ch. 3 false-drawer desk.

**2. Object moving between chapters** — Two candidates, use both:

- **The memory core**: Wellhead meter (pre-story) → Ilsa’s hands at 2340 night-of-death (Ch. 1 event, Ch. 3 attribution) → false drawer of Ilsa’s desk, four days (Ch. 3 disclosure) → Seed Vault steel document case (moved during Ch. 1’s assembly scene; see feature 7) → narrator’s possession (Ch. 3) → gallery display, read publicly (Ch. 4) → unified archive in Records Vault (Ch. 4). An as-of query like “where was the core during the Chapter One assembly?” must answer *in transit / Seed Vault*, not *Wellhead* or *unknown*.
- **The aquifer maps**: Tovan’s pocket (pre-story) → narrator’s coat (Ch. 1) → Sela’s keeping (Ch. 1) → waterproof tube on dig sledge, departed south lock (Ch. 4). Cross-batch supersession across all chapter boundaries.

**3. Coarse container later differentiated** — Two planted splits:

- **“The vault”**: Chapter Two treats *the vault* as a single definite room (the Allocation Office usage, Tovan’s letter, Pell’s line “that’s where it sleeps”). Chapter Three splits it into the **Records Vault** (Council tier) and the **Seed Vault** (sub-basement, decommissioned by Cray eleven years prior). **Pass condition:** Ch. 2 references to “the vault” should be flagged as underdetermined anchors; Tovan’s letter’s “in the vault” resolves (in hindsight) to the Seed Vault, while the Allocation clerks’ usage resolves to the Records Vault.
- **The desk drawer** (secondary, same pattern at smaller scale): Ilsa’s desk reads as one-drawer in Ch. 2’s office scene (implicitly), revealed in Ch. 3 as having a visible drawer plus a **false second drawer**. Explicit lampshade in text: “One desk, two drawers. One vault, two vaults.”

**4. Container never opened** — **Tovan’s footlocker**, guild crimp seal **0447**. Established sealed in Chapter Two, explicitly carried sealed through Chapter Four (“The footlocker never got opened. I want that on the record”), with a stated future condition for opening (survey strikes water). **Pass condition:** the container’s contents remain an unresolved thunk; status *sealed* must be stable across all narrative time with no phantom contents asserted.

**5. Frame transfer without canon change** — Chapter Two, Bazaar scene: **Pell tells Sela about the double door-log entry** (2300 / 2340), which the reader and narrator learned in Chapter One. Narration explicitly marks it: “She didn’t learn anything I hadn’t already concluded, and the kid didn’t say anything the door log hadn’t already said.” **Pass condition:** Sela’s knowledge state updates; no new canonical fact is created; door-log facts retain their Ch. 1 provenance.

**6. In-fiction document** — **Tovan’s letter**, quoted verbatim in Chapter Two. The letter asserts: (a) gap opened eleven years back, (b) under Administrator Cray, (c) shortfall “something over forty thousand liters,” (d) a second set of books exists “in the vault.” **Pass condition:** these are document-asserted facts (the story observed the letter; the letter claims the facts), distinct in trust chain from narrator-observed facts. Note that Chapter Four upgrades (a)–(c) via independent corroboration by the memory core (“forty-one thousand, two hundred liters” — the core’s figure refines the letter’s approximation), and Chapter Three corroborates (d). The engine should represent the letter’s claims and the core’s confirmations as separate assertions with separate provenance that converge.

**7. Off-screen event revealed late** — During Chapter One’s climactic assembly/Wellhead sequence, **Ilsa moved the memory core from her desk’s false drawer to the Seed Vault**. This event occurs in Chapter One’s timeframe but is asserted only in Chapter Three (Ilsa’s correction of the narrator’s chronology). Also in this class: the badge-walk itself (occurred night of Tovan’s death, pre–Chapter One; perpetrator asserted only in Ch. 3) and the four days the core spent in the false drawer. **Pass condition:** valid_time (during Ch. 1 events) ≠ asserted_at (Ch. 3); the two-axis fold must place the core in the Seed Vault for as-of queries during the assembly even though no Ch. 1 text says so.

**8. Deliberate soft contradiction — FLAG EXPECTED, COUNTS AS PASS** — Chapter One states Anchor has “**two working reactors**” as fixed scene-setting. Chapter Three’s closing line states “**all three of Anchor’s reactors were humming**” as casual fixed fact, with no narrative event (repair, construction) explaining the change. This is an intentional inconsistency. **Pass condition:** the truth-maintenance system fires a conflict flag rather than silently rewriting either assertion. A silent merge to “three reactors” or “two reactors” is a failure; a flagged coexistence with both assertions and their provenance is a pass.

## Bonus tracking surface (beyond the list)

**Status changes (entity state supersession):**

- Marn: Allocation Officer → confined to quarters pending tribunal (Ch. 2) → exiled to northern waystation, commuted from flats-walk (Ch. 4). Also: Allocation seal *melted down in front of witnesses* (Ch. 2) — object destruction event.
- Pell: Wellhead duty guard (Ch. 1) → deputy warden (Ch. 2) → deputy warden + commissioner of new master meter (Ch. 4).
- Sela: condenser operator (Ch. 1) → Water Steward of Anchor (Ch. 4).
- Ilsa Renn: clerk (unnamed, Ch. 2) → identified accomplice/custodian (Ch. 3) → conditional pardon, Custodian of the unified archive, retains title “clerk” (Ch. 4).
- Tovan Voss: accused thief/suicide (Ch. 1 opening) → vindicated (Ch. 1 close) → name “clean in the record” / memorialized on meter housing (Ch. 4). Dead throughout; reputation is the mutable attribute.
- Anchor settlement: pre-revelation steady state → panic (Ch. 1) → rationing, half-shares/double-shares regime (Ch. 2) → post-tribunal reconstruction with survey underway (Ch. 4).

**Object inventory (with custody chains where applicable):**

- Master meter (original): functional → dark/memory pulled → scorched housing → replaced; housing inscribed “TOVAN” (Ch. 4, anonymous actor — deliberately unattributed agent).
- New master meter: commissioned, calibrated three times, installed in old housing (Ch. 4).
- Tovan’s badge: guild locker → Ilsa’s hands (badge-walk) → implied evidence custody; absent from body (noted Ch. 2).
- Door log & maintenance log: distinct record systems with divergent contents (Ch. 1); door log handed to Pell (Ch. 1).
- Tovan’s letter: condenser logbook binding → Sela → read by narrator (Ch. 2) → implied archive.
- Cray’s ledgers / second books: Seed Vault (decade) → narrator/Pell custody (Ch. 3) → unified archive (Ch. 4).
- The gray bottle: narrator’s office, poured Ch. 1 and Ch. 4, conspicuously not drunk in Ch. 4 — recurring object, stable location.
- Crimp seals as a class: footlocker crimp 0447 (intact throughout); Seed Vault hatch crimp (cut and re-twisted repeatedly — wear as evidence).

**Quantified singleton objects (one entity, quantity as attribute — NOT N separate entities):**

- **Paper twist of three dried figs** — Bazaar table, Ch. 2. Stable quantity (explicitly “untouched” through the scene). Pass: one object, quantity=3, location=Bazaar table, never mutated.
- **Flat steel tin of cigarettes** — narrator’s pocket, Ch. 2. Quantity **5 → 4** within the scene (one given to Pell). Pass: this is a *quantity supersession on a single entity*, not an entity split — the tin remains one object whose count attribute changes; the transferred cigarette may optionally spawn as Pell’s possession, but the tin must not fork into five tracked cigarettes.
- **Six lead crimp blanks + one spool of seal wire** — visible drawer of Ilsa’s desk, Ch. 3. Stable. Pass: two objects (a counted set of 6, a singleton spool), both contained in the *visible* drawer specifically — a containment-precision test given the false drawer two inches behind them.
- **Crate of twelve empty sample vials** — Seed Vault, by the hatch, Ch. 3. Stable; explicitly all empty. Pass: one crate entity, quantity=12, contents-of-vials=empty (a nested “contains nothing” assertion — should not hallucinate vial contents).
- **Tin of four spare fuses** — taped inside the new master meter’s access panel, Ch. 4. Stable. Pass: one object, quantity=4, with a precise sub-location (access panel interior, not “the Wellhead” generally).

Rust Quarter; condenser station; salt flats / old highway; the Wellhead; Council tier; Allocation Office; Records Vault; Seed Vault (sub-basement, two levels down past the dead elevator); the Bazaar (south dome panel, tea-colored patch-glass); bulletin wall; gallery/assembly hall; Cistern Three (named, built by Cray); southern aquifer survey site (off-map, destination); northern waystation (off-map, relay shack three days up the old highway, rain trap + repeater).

**Persons (full roster):** narrator (unnamed throughout — deliberate permanent anonymity; test that the system tolerates a never-bound identity), Sela Voss, Tovan Voss (deceased), Marn, Pell, Pell’s mother (Council member, never named — second stable unnamed identity, distinguished only by relation), Ilsa Renn (late-bound), Administrator Cray (deceased pre-story, lung rot, ~6–7 years dead; asserted historical actor), the two Council-cousin clerks (background, interchangeable by design), the Wellhead tech who wires the core (Ch. 4, anonymous functional role), survey team (six diggers, collective entity).

