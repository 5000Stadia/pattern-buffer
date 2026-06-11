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

**Quantitative assertions to track:** ~300 souls; 2 (vs. 3 — see feature 8) reactors; 2300 / 2340 door-log timestamps; 11-year gap origin; “over forty thousand liters” (letter) refined to 41,200 liters (core); crimp 0447; half-shares/double-shares ration ratio; two-vote commutation margin; three calibration passes; three-day distance to waystation; four days core-in-drawer; six diggers, two condensers on the survey.

-----

# BIBLE ADDENDUM

*Same convention as the main bible: out-of-fiction metadata for evaluation. Sections 1–3 are reference scaffolding; section 4 is a graded-feature ruling; section 5 supersedes specific entries in the main bible above (note: the bible itself now contains a supersession — the engine ingesting this document gets a meta-example of its own problem).*

## A1. Master event spine

Time base: **Day 0 = the night of Tovan’s death** (the night the master meter went dark). Negative offsets are pre-story. Where the text gives no number, offsets are marked **approx.** or **unstated** — the engine should not assert tighter bounds than the text supports.

**Pre-story (years scale)**

- **e1** (≈20+ years pre-story): Anchor founded. Ilsa Renn serves as records officer on the founding convoy.
- **e2** (undated, “Father’s old survey,” years pre-story): Tovan and Sela’s father conducts the original southern aquifer survey. The maps descend from this event.
- **e3** (Year −11): Administrator Cray signs the Seed Vault decommission order. The reconciliation gap opens the same year. Second set of books begins, in Cray’s hand.
- **e4** (Cray’s tenure, ≈Y −11 to −7): south dome panel raised; Cistern Three dug.
- **e5** (ongoing, “the last decade”): block flow meters progressively rigged.
- **e6** (≈Y −6 to −7): Cray, dying of lung rot, asks Ilsa to burn the second books. Ilsa verbally agrees — falsely (“the only false entry I ever made by mouth instead of ink”). Cray dies. Marn inherits the Allocation office and the lie.
- **e7** (Y −6/−7 → Day 0): Ilsa continues the second books (the “second hand”).

**Tovan’s arc (lead-up to Day 0; internal order fixed, dates unstated)**

- **e8**: Tovan runs the master-total / allocation-books reconciliation six times; finds the gap.
- **e9**: Tovan writes the letter; hides it behind the binding of the condenser station logbook.
- **e10**: Tovan brings the number to Marn.
- **e11** (Day 0, before 2340, time unstated): Marn issues the instruction to Ilsa regarding the meter record. *Scope of intent deliberately ambiguous — see A2, open ambiguities.*

**Day 0 (clock times where stated)**

- **e12** (2300): Tovan enters the Wellhead (door log); services the master meter.
- **e13** (between 2300 and 2340, unstated): Tovan exits (no exit record cited in text) and walks south onto the flats, unsuited, to verify the aquifer site.
- **e14** (night, unstated): Ilsa retrieves Tovan’s badge from his guild locker.
- **e15** (2340): Ilsa enters the Wellhead on Tovan’s badge; pulls the memory core; improvised scorch on the housing. Master meter goes dark.
- **e16** (night): core placed in the false drawer of Ilsa’s desk. *[valid_time: Day 0. asserted_at: Chapter Three (e37).]*
- **e17** (Day 0 night → Day 1): Tovan dies of exposure at or near the survey site. Maps on the body; badge absent.

**Days 1–4 (Chapter One’s span)**

- **e18** (Day 1–2, approx.): body recovered; Council closes the matter as theft/coward/suicide.
- **e19** (Day 3): Sela hires the narrator (“Three days ago it had gone dark”).
- **e20** (Day 3): Wellhead visit; Pell produces maintenance log, then door log; 2300/2340 double entry discovered.
- **e21** (Day 3–4, unstated): narrator examines the body; recovers the aquifer maps.
- **e22** (Day 4): narrator confronts Marn on the Council tier; confession.
- **e23** (Day 4, evening): first assembly convenes; the true number goes up on the gallery wall; panic begins.
- **e24** (Day 4, evening — **concurrent with e23**): narrator marches Marn down to the Wellhead.
- **e25** (Day 4, evening — **concurrent with e23/e24**): Ilsa moves the core from the false drawer, down the long way, into the Seed Vault; files it in the steel document case. The “four days in the drawer” (Day 0 night → Day 4) closes exactly. *[valid_time: Day 4, during the assembly. asserted_at: Chapter Three (e37). This is the primary two-axis fold: an as-of query pinned to the assembly must place the core in transit / Seed Vault, sourced from a Chapter Three assertion.]*
- **e26** (Day 4): maps handed to Sela; door log handed to Pell.

**Day 7 (Chapter Two)**

- **e27** (dawn): Council votes rationing — half-shares general, double-shares dig crews; schedule posted at the bulletin wall.
- **e28**: Marn confined to quarters pending tribunal; Allocation seal melted before witnesses; Pell promoted deputy warden.
- **e29** (morning): guild releases Tovan’s effects to Sela; footlocker sealed under crimp 0447.
- **e30** (daytime): narrator visits the Allocation Office; meets the clerk with the tin ear (identity not yet bound); her non-answer regarding vault inventory.
- **e31** (evening, Bazaar): figs purchased (3, untouched throughout); cigarette tin 5 → 4 (one to Pell); **Pell utterance #1**; Pell tells Sela the door-log facts (frame transfer, no canon change); Sela produces Tovan’s letter; narrator reads it.

**Days ~8–10 (Chapter Three; offsets approx., text says only that a writ was obtained)**

- **e32**: Council writ obtained with Pell’s mother’s signature.
- **e33**: Records Vault searched, Ilsa attending with inventory ledger; clean — no core, no second books.
- **e34**: Pell finds SEED VAULT on the pre-Collapse schematics; connects it to Cray’s Y−11 decommission order.
- **e35**: descent the long way (gallery stairs → Bazaar service gate → dead stairs); **Pell utterance #2**.
- **e36**: Seed Vault opened (crimp worn bright from repeated cutting); discovered: vial crate (12, all empty), Cray’s ledgers plus second-hand continuation, memory core in document case, **PERSONAL case — logged, not opened**.
- **e37**: Ilsa confrontation at her desk; visible drawer opened (6 crimp blanks + spool); false drawer revealed; identity bound (the clerk = Ilsa Renn); her chronology correction asserts e11, e14–e16, e25.
- **e38**: core and books carried up the dead stairs. *(“All three of Anchor’s reactors” — the flagged contradiction site, main bible feature 8.)*

**Days ~10–14 (Chapter Four, tribunal window; approx.)**

- **e39**: second assembly; core read publicly; 41,200 L confirmed; letter’s claims corroborated (with refinement of the approximate figure).
- **e40**: tribunal — Marn exiled to the northern waystation, commuted from the flats-walk by two votes on Pell’s mother’s motion; five minutes alone with the columns; escort departs north.
- **e41**: Ilsa receives conditional pardon; reinstated as Custodian of the unified archive; archive consolidated in the Records Vault, including the PERSONAL case (still latched).
- **e42**: Sela confirmed Water Steward by acclamation.

**Day ~21 (Chapter Four close; anchored by the “three weeks” reference)**

- **e43**: survey departs the south lock — 6 diggers, 2 condensers, maps in waterproof tube on the sledge.
- **e44**: Pell commissions the new master meter; 3 calibration passes; fuse tin (4) taped inside the access panel; **Pell utterance #3**.
- **e45** (after installation, undated): TOVAN inscribed on the housing. **Actor permanently unattributed** — see A2.
- **e46** (night of e43): narrator–Sela exchange about the footlocker; opening condition stated (when the survey strikes water).
- **e47**: office coda; the gray stuff poured, not drunk.

## A2. Knowledge checkpoints

**End of Chapter One (Day 4):**

- **Narrator** knows: the gap exists; Marn’s complicity (by confession); Marn inherited rather than originated it; a badge-walk occurred at 2340 by an unidentified actor; Tovan died verifying a site; the maps’ contents. Does **not** know: that Ilsa exists in any relevant capacity; the core’s location; that Cray is the named origin; that a second set of books exists; that there are two vaults.
- **Sela** knows: brother dead and publicly vindicated; the gap (from the assembly); has the maps. Does **not** yet know the 2300/2340 specifics — she learns those at e31.
- **Pell** knows: both logs’ contents; the gap (assembly).
- **Marn** knows: everything he confessed, plus the identity of his instrument (he instructed Ilsa — e11). Does **not** know the core’s current location (asserted: never handed anything, never asked how).
- **Ilsa** knows: everything above plus e3–e7, e14–e16, e25. As of end-Ch1, she is the **only living person who knows where the core is**.

**End of Chapter Two (Day 7):**

- **Narrator** adds: letter contents (Cray, eleven years, ~40,000 L, “second books in the vault”); badge absent from the body; working theory that the core was filed, not destroyed; registered (belatedly) that the clerk’s vault answer was a non-answer; footlocker exists, sealed, 0447.
- **Sela** adds: door-log specifics (from Pell, e31); letter contents; footlocker custody.
- **Pell** adds: letter contents; new rank; the habit begins (utterance #1).
- **Marn**: static; confined. Does **not** know the letter exists.
- **Ilsa** adds: knows the investigator asked about the core against her inventory — knows the hunt is on.

**End of Chapter Four:**

- All principals (and the public, via e39–e42): core data; Cray as origin; Ilsa’s role and chronology; two vaults; tribunal outcomes; survey underway.
- **Facts true in the story that NO character knows at the end:**
1. **Who inscribed TOVAN** (e45). Confirmed: permanently unestablished. The narrator explicitly declines to investigate (“a sudden professional blindness”); no other character is shown to know. The engine must hold an event with a null/unknown agent indefinitely without backfilling a culprit.
1. **Contents of the footlocker** (crimp 0447). Unestablished for **all** characters including Sela — the guild sealed the effects before release, and no text asserts she knows the inventory. Stable thunk.
1. **Contents of the PERSONAL case.** Unestablished for all. *Note: Ilsa is a plausible knower (decade of Seed Vault custodianship), but the text never asserts it — plausibility is not canon, and an ingestion that grants her knowledge here has inferred beyond the record.*
1. **Whether the southern aquifer holds water.** Open for everyone, including the reader.
- **Deliberate open ambiguity (not a contradiction — do not flag):** the scope of Marn’s intent at e11. The text supports “instructed destruction of the record” with certainty; it never establishes whether Marn knew or intended that Tovan would die. Tovan’s death is canonically exposure during a self-chosen verification walk (e13, e17). The narrator’s line “you held it together with a dead man” is an accusation of exploitation, not an established murder. The engine should represent Marn’s culpability for the cover-up as fact and culpability for the death as unresolved.

## A3. Place adjacency (per text only — do not infer unstated edges)

- **Rust Quarter** ↔ **old highway** ↔ **salt flats**; **condenser station** lies out past the Rust Quarter. Old highway → **northern waystation** (3 days’ travel, off-map).
- **South lock** → southern flats → **aquifer survey site** (off-map).
- **Council tier** contains: **Allocation Office** (→ **Records Vault**, directly behind it), **Marn’s quarters**; the **gallery/assembly hall** adjoins via the **gallery stairs**.
- **Gallery stairs** ↔ **Bazaar level**. **Bazaar** contains the stalls and the **service gate** (behind the stalls); **bulletin wall** is outside the Bazaar.
- **Service gate** → **dead stairs** (two unlit maintenance flights) → **sub-basement** → **Seed Vault**.
- **EXPLICIT NON-CONNECTION (new, patched):** **Council tier ↮ Seed Vault.** The Seed Vault sits directly beneath the Council tier (~40 vertical feet), but the only direct shaft — the **dead elevator** — has been defunct since the Collapse breach year and was never recut. The sole route is the long way: Allocation corridor → gallery stairs → Bazaar level → service gate → dead stairs (~20 minutes with a lamp). **Pass condition:** a routing or adjacency query between Council tier and Seed Vault must return the long path, not a direct edge; vertical proximity must not be conflated with connectivity. Bonus inference the text licenses but does not state: this is the route Ilsa walked during e25, which is consistent with “the corridors were empty” — the engine may hold this as a supported inference, distinct in confidence class from asserted fact.
- **Wellhead**: “at the bottom of Anchor,” reached by corridors. Its relation to the sub-basement is **unstated** — no edge should be asserted between Wellhead and Seed Vault.
- **Narrator’s office**: within Anchor, district unstated. Deliberately underdetermined anchor.

## A4. Ruling: Tovan’s letter and “where the originals are kept”

The letter (Ch. 2) asserts the second books are kept “where the originals are kept — in the vault.” Canon resolves: originals = **Records Vault**; second books = **Seed Vault**. The co-location claim is **false**; the existence claim is **true**.

**Ruling: ratified as an intentional graded feature.** Honest provenance note: this divergence emerged organically in drafting rather than from the shopping list, and is hereby promoted to canon as a test rather than patched away — it is a better trust-chain probe than a fully accurate letter would be, because it gives the document a true claim and a false claim in the same sentence.

**Grading:**

- **Pass:** the letter’s location sub-claim is retained verbatim with document provenance (Tovan asserted it; the story observed the letter) and is marked refuted/superseded by the Chapter Three observation (e36). The existence sub-claim is marked corroborated by the same observation. One document, one sentence, two assertions, two different fates.
- **Failure modes:** (a) silently relocating the second books to the Records Vault to honor the letter; (b) retroactively editing the letter’s content to say Seed Vault; (c) discounting the entire letter as unreliable because one sub-claim failed — the quantity claim (~40,000 L) was independently confirmed and refined (41,200 L, e39), so document-level trust must be assessed per-claim, not per-source.
- Note the in-fiction explanation, for coherence: Tovan inferred the location (“I believe there is a second set of books, kept where the originals are kept”) — the letter itself hedges with “I believe,” so this is a marked inference inside a document inside the story. Three-deep provenance.

## A5. Supersessions and updates to the main bible

1. **Feature 3 (vault split), resolution of the letter’s “in the vault” — SUPERSEDED.** The main bible states the letter’s phrase “resolves (in hindsight) to the Seed Vault.” This was imprecise. Corrected: Tovan’s *intended referent* was co-location with the originals (Records Vault), and that claim is **false**; the second books’ *actual* location was the Seed Vault. The letter does not successfully refer to the Seed Vault — it unsuccessfully refers to the Records Vault. See A4 for grading. (The bible correcting itself is, intentionally left in place, one more supersession for the engine to handle.)
1. **New feature 9 — explicit non-connection** (Council tier ↮ Seed Vault, dead elevator defunct, long-way route). Patched into Chapter Three. Pass condition in A3.
1. **New feature 10 — repeated identical utterance (habit formation).** Pell speaks the exact string “Somebody, once, didn’t trust somebody else.” three times: Ch. 2 Bazaar (e31), Ch. 3 descent (e35), Ch. 4 commissioning (e44). The identical string also appears once in **Chapter One narration** (the door-log redundancy passage), and the Ch. 3 patch implies Pell picked it up from the narrator (“I didn’t have the heart to tell him where he’d picked up the line”). **Pass condition:** three spoken instances unify as one recurring utterance/habit attached to Pell, with lineage back to the Ch. 1 narration as origin; the narration instance must not be counted as Pell speaking.
1. **New feature 11 — second never-opened container.** Cray’s **PERSONAL case**: established in the Seed Vault (e36, logged — weight, dimensions, the one word — but not opened), carried forward still latched into the unified archive (e41/Ch. 4). Same pass condition as the footlocker: stable thunk, no phantom contents; additionally tests that *two* concurrent sealed containers with different custodians (Sela / Ilsa) and different opening conditions (survey strikes water / a Council vote nobody has proposed) remain distinct.
1. **Locations list — updated.** Add: dead elevator (defunct shaft, Council tier ↕ sub-basement, non-traversable), gallery stairs, service gate (behind the Bazaar stalls), dead stairs, sub-basement. The A3 adjacency graph supersedes the flat location list in the main bible for connectivity questions.
1. **Quantified singletons — unaffected** by the patches; counts and locations unchanged. The crimp-blank count (6) now also serves as a same-scene contrast object for utterance #2’s chapter.
