# Audit of key.json against ch01-ch12 ("The Weather That Would Not Leave")

Read-only pass. Chapter numbers are N; quotes are short.

## 1. Wrong gold (key contradicted by, or unsupported by, the text)

1. **`iven` alias "the old Listener" is wrong.** It names Vey: ch6 Nemi "When the old Listener was put below the House", ch11 "The old Listener knew the words already", ch12 "bring the old Listener back from the rooms". Iven is "the town's appointed Listener" (ch2). Move the alias to `vey`. Also drop bare "Listener" from `iven`: ch2 "The title Listener belonged to anyone who could hear", and Vey, Mara and Or are all Listeners.
2. **`same_as` vey reveal chapter 8 is late.** Ch4 the woman answers "Vey", "I was the other Listener", and Or ties her scar to the first Listener's portrait. Ch5 Iven: "Her name was Vey Orin." / "The woman on the causeway?" / "Perhaps." Ch8 ("Vey Orin is the woman with the copper hand") only confirms. The same applies to knowledge entry "oruva learns Vey Orin is the woman with a copper hand", ch8. Use 4 (name) or 5 (Vey Orin). The ch8 sentence is a confirmation, not the reveal.
3. **`same_as` mara alias is not a pre-reveal alias.** "the hooded clerk who carried jars" appears only at the reveal (ch9). Pre-reveal phrasings are ch7 "the hooded person who had walked into the Room Below Mouth" and ch8 "the hooded visitor". The text reveals the identity in ch8 (Vael: "A clerk called Mara"), and ch9 confirms in person. Use alias "the hooded visitor" (or "hooded person") with reveal chapter 8. Also add the ch7 reveal that Mara Senn (the register assistant) is Or's mother (Vael: "Your mother's name").
4. **"Mara was dead" correction (stated 7, corrected 9) is mistimed.** The belief runs from ch1 ("losing her") and is explicit in ch7 ("died when Or was six, or so the ledger said"). Vael corrects it in ch7 ("She did not die"). Ch8 muddies this ("Is she alive?" "I don't know"). Ch9 is the in-person confirmation. The knowledge entry "oruva learns Mara is her mother ... falsely recorded as dead", ch9, should be split. Ch7 Vael says she is her mother and not dead. Ch9 Or learns she is alive.
5. **`false_beliefs` "vael believes the first drop was a trick of the lanterns" is a lie, not a belief.** Ch4: "Or ... understood that Vael had lied"; Vael says "I was wrong to say there was no water". Ch8 Vael: "I know what people need to believe." Its `corrections` entry has `stated_chapter` 8 but the first statement is the ch4 notice ("The first drop, the notice said, had been a trick of the lanterns"). Remove it from `false_beliefs` and set `stated_chapter` 4.
6. **`false_beliefs` cale "Returning the flask to the tree could restore the orchard", corrected 10, is unsupported.** In ch10 Cale still says "The flask is needed beneath it." The nearest correction is ch11 narration ("Now he understood..."). Also the ch3 narrator already says "He was mistaken". Also "from_chapter 3" is when it is stated, not when he began believing it. Re-time to 3 -> 11 or drop.
7. **Vael's orchard-theft belief timing.** The key has 2 -> 10, but ch7 "She did not say the orchard had stolen it" and ch8 "Vael had not been trying to destroy the orchard" show it weakening before ch10. Ch10 is still the explicit statement ("the tree was a lid, not a thief"), so keep 10 but expect graders to see drift from 7.
8. **`knowledge` nemi, ch6.** Nemi already knows this and tells it; she does not learn it. Convert to a learner entry: Or learns (ch6, Nemi) that Nemi carried the key when the first Listener was put below the House.
9. **`knowledge` iven, ch10** ("The storm needs a path through town") is Iven asserting, not learning. In ch7 he and Or already read the route.
10. **Holdings errors.**
   - `blue_tooth` oruva `from_chapter` 3 should be 2. Nemi passes the tin case holding the tooth to Or at the end of ch2 ("The tin case slipped into Or's coat pocket"). The key leaves a gap in ch2-3.
   - `blue_tooth` vael 4-8: in ch4 Vael puts it in the blue bowl under a glass lid in the Counting Room. In ch5 "Iven was alone. The tooth remained beneath the glass lid". Vael is not holding it in ch5-7. Better as a location (tooth in blue bowl, in Counting Room, 4-7). Iven holds it from ch8 ("Iven held the blue tooth").
   - `first_jar` oruva 1-5: Or puts it back on the lowest shelf (end of ch1) and it is on its shelf in ch4. She hides it in the flour sack only in ch5, and carries it again in ch8. Evidence "She lifted the jar." proves only a moment. Replace with a location/holding timeline.
   - `tin_case` oruva 2-11 conflicts with ch10 ("Nemi joined them at the causeway, with her six-lidded box in one hand and the tin case in the other") and ch10 end ("Nemi gave the empty tin case to Tavin"). Ch11 then has "Nemi left the tin case in the hidden room". The text contradicts itself here. Do not grade the tin case after ch9. Recommend oruva 2-9 and note it is unreliable afterwards.
   - `six_lidded_box` nemi 10-11: Nemi holds it from ch6 ("pulled out a narrow metal box with six sliding lids") and in ch12. Use 6-null.
   - `rain_vial` oruva 6-10: Or poured it into the cracked jar in ch7 and again onto the soil in ch10 ("Or poured the contents of the old rain vial"), while in ch10 "The red-thread vial was empty now, but Nemi kept it tied to her apron". The text is incoherent. Hold 6-9 and treat later as unreliable.
   - `black_seed` oruva 6-12: in ch12 Nemi has the seed in her box, then "Nemi's seed grew a narrow stem" (in a pot). Another seed has "taken hold in the seam between two stones" in the courtyard (Or watering it). The text has one seed in three places. End the oruva holding at 10.
   - `black_iron_key` vael 5-11: ch5 ends "Vael closed the chamber door but left the key in its lock". Ch11 says "removed the black iron key from her collar. She had been carrying it for years" and then "The black iron key had already been left in its lock." Also Nemi says in ch6 that she carried the key as a child. This is self-contradictory text, so keep the 11 handover but flag it.
   - `old_map` vael 7-10: the quote "Vael placed the folded map on the chair" is not holding evidence (use "Vael took the map" / "slipped it into the inside pocket of her collar", ch8). Also `first_chapter` 5 is wrong: the first physical map is ch7 (ch4's "map" is a metaphor/drawing).
11. **`containers` problems.**
   - `tin_case` revealed ch3 with the tooth: the tooth is already in the case in ch2 ("tucked the cloth into a tin case"), so revealed 2.
   - `portrait_wall` is typed "object" and the portrait is not an entity. Its location is incoherent: ch4 "hung in the House of Folded Water", ch5 "hanging above the door" in the Counting Room, ch6 "wall behind the scratched portrait". Don't assert a place for it.
12. **`hidden_chamber` merges three different rooms.**
   - The carved-names chamber behind the disused cistern door off the western corridor, "the room under the room" (ch5, ch6, ch9, ch7 "the room beneath the room"). Called "the lower room" in ch5, which collides with the `room_below_mouth` alias "the lower room".
   - Mara's room: panel on the north wall of the Room Below Mouth, with a cot, basin and coats (ch9, "hidden chamber", "small chamber").
   - Vey's chair room at the end of the Drowned Stair passage, with the chair and copper-wire spool (ch7, "a small room"). Ch12's "hidden room ... The chair remained ... the cot had been made" fuses the second and third, which the text itself does by sloppiness.
   The key evidence is for the first, but the aliases "small room" and "hidden chamber" belong to the others. Split into three entities.
13. **`market_court`: first_chapter 7 is wrong; it appears in ch1** ("leading toward the market court") and ch6. Its location row is `from_chapter` 12; use 1.
14. **`basin` collides with other basins.** There is the "basin of packed salt" under the causeway ("salt basin", ch3, ch12) and "measuring basins" (ch1). Ch10 puts the old basin "beyond town", while ch6 and ch11 put it under the market court. The alias "basin" will bind to the wrong thing. Add a separate `salt_basin` place; do not assert basin geography beyond ch11.
15. **`pell` first_chapter 2 should be 1** (ch1 "Pell was asleep in a chair").
16. **Two unrelated "chipped/repaired cup" objects.** Mara's repaired cup (ch9, left beside the cot, ch11) and the child's "chipped cup" left at the basin (ch11-12). Ch12 also has "the small cup on the shelf" in the hidden room. Not in the key, but see section 2.
17. **`ors` aliases "the town" and `listening_road` aliases "the route"/"the old route"** are too generic.
18. **Alias collision on "flask"/"the flask".** The key assigns it to `answer_flask`. But ch3-4 and ch10 "the flask" is the tree flask ("The flask is under the bark", "That flask is the rain's first vessel"). Ch5 "the green flask" also gestures at the tree flask. Remove bare "flask"/"the flask" from `answer_flask` and mark ambiguous.
19. **Over-broad aliases will mis-ground.** "Or" (substring of nearly every word), "jar", "key", "case", "box", "map", "ring", "seed", "tree", "branch", "chart", "spool". "spool" also names the copper-wire spool in ch7.
20. **`cracked jar`/`old jar` ambiguity.** In ch7 Tavin also finds "a crack in its base" jar. In ch5 there is a second "nameless jar" (the empty jar with the scratched label, found behind the ledgers; its label later shows a road toward the west).

## 2. Missing gold that matters

**Entities missing**
- **blue bowl** ("blue-black bowl" ch2, "blue bowl" ch4/5/8/10/12): holds the tooth under a glass lid; ends on a windowsill (ch8); in the Counting Room (ch12). A prominent moving object and container.
- **flour sack**: holds the jar (ch1, ch5 "Or showed her the flour sack, and the jar within it", ch8). This is a clear later-revealed container.
- **nameless jar** (ch5), **portrait** ("scratched portrait", ch4-6), **old cistern / cistern beneath the tree** (ch1-3, ch7, ch11), **causeway** (ch3+), **salt basin**, **west court / west gate** (ch6, ch8, ch9), **public hall** (ch2, ch7-10), **archive alcove** (ch2, ch6), **Mara's hidden room**, **Vey's chair room**, **chair + copper-wire spool** (ch7), **copper plate** (Mara's left thumb, ch9; handed to Vael, ch10), **letter** (ch9, left under the cup, ch11), **Mara's repaired cup / Tavin's clay cup / the child's chipped cup**, **the notice** (reed-paper, ch1; torn down, ch11), **paper boat** (ch7), **wooden stool** (ch5).
- **No holdings or locations at all for** `copper_ring`, `roof_chart`, `broken_branch`, `blue_paper`, or the first jar's shelf. The ring moves a lot: Nemi's box (ch6) -> Or -> bridge, then "gone" (ch6) -> ledge behind a panel in the House drain (ch9) -> carved chamber -> Nemi -> tin case -> Mara (ch10). The branch is carried by Cale (ch1, ch3), laid at the tree roots (ch3), carried again (ch10), laid at the cistern mouth and then set on the lid by Nemi (ch11), and placed by the House door (ch12). The roof chart goes Pell -> Or (ch8), also "Vael gave it to Or" (ch8), then Cale (ch10).
- **Containers missing:** the jar held the blue tooth (revealed ch1: "A blue tooth fell into her palm"); the tooth is in the blue bowl (ch4); the jar in the flour sack (ch5); the hollow under the first shelf (ch1 "a hollow beneath the shelf"); Mara's bundle (map of the House, list, letter, ch9); the spool-of-copper-wire tag (ch7); the stone in the market court hides a black glass disk (ch7); the drain ledge holds the ring (ch9).
- **Tree branch count:** ch1 notice drawing shows seven branches, "In life, it had nine", explained in ch3 ("Two had been added"). Ch11 then says "the tree had nine branches now". This is a stated-then-reconciled fact worth a correction entry.

**Aliases missing**
- `vey`: "the woman with the copper hand" (ch8, with "the", unlike the key's "a"; the brief's own example), "the woman on the causeway" (ch3, 5, 8), "Vey of the Orchard" (ch7), "the woman in the orchard" (ch9), "the missing first Listener" (ch8), "the old Listener" (moved from iven).
- `mara`: "the hooded person" (ch7), "the visitor" (ch7-8), "the hooded visitor" (ch8; the key has this alias but not in `same_as`).
- `vael`: "the chief clerk" (ch1: "The chief clerk said no one touches the first shelf"), only plausibly Vael; and "Oruva's aunt" (ch2). The relationship is "aunt by the town's loose use of kinship, though no blood joined them".
- `tin_case`: "Nemi's tin case" (ch3, ch9); `blue_tooth`: "tooth ... closed eye" description; none needed.
- `oruva`: "Oruva", bare, never appears except as "ORUVA" (ch9 cup); "the third name" (ch7-8 = Or) is not an alias; "the child in the House" (ch9 letter).
- `tide_spoon`: "her mother's" spoon (ch1: "had been her mother's"); no holder row before Or.

**Identity reveals / look-alikes missing**
- **same_as** `["oruva","the third Listener",8]` (the missing third name is Oruva; "Oruva Senn" is written beneath the ink). `["mara","the assistant who died in a fever",7]` and `["mara","the person you called mother",7]`. `["vey","the other Listener",4]` (ch2: "the other had not been seen for years").
- **not_same missing:** Iven Orri / Vey Orin (near-identical surnames, both "Listener"); Vael Senn / Mara Senn / Oruva Senn (three Senns); Cale (copper glove, right hand) / Vey (real copper-plated right hand) / Mara (copper plate on left thumb), the "three copper hands"; Vey / Mara (both carry the crescent scar: ch3 scar "once noticed on someone in the House ... hood", ch4 scar on Vey, ch9 scar on Mara); Pell / Rell (Pell the roof tender, Tavin Rell); Tavin's cracked cup vs Mara's repaired cup; tree flask vs Iven's green flask.
- **Who never learns:** Or keeps Vey's warning from Cale (ch3: "She did not tell Cale that the woman with a copper hand had warned her"), hides Mara from Vael (ch9 "Have you seen anyone?" "No."), and has not decided whether to tell Tavin (ch7 end); Tavin and Pell never learn Or's status. The `knowledge` section lacks any "never learns" entries, which the brief's "some learn things others never do" needs.

## 3. Wrong merges/splits

- **`hidden_chamber`** merges three rooms (see 1.12). Biggest structural gold error.
- **`room_below_mouth` alias "the lower room"** also names the carved-names chamber in ch5 ("After Vael left the lower room, Or stayed beside the carved names") and ch9 ("put in the lower room"). Remove it or disambiguate.
- **`first_jar` conflates** the singing jar (First North Drizzle), the "cracked jar" of ch4-11, and (alias "old jar") the old ledger-based references. These are the same jar by the text; but Tavin's cracked jar (ch7) and the nameless jar (ch5) are distinct and unkeyed.
- **`tree_flask` vs `answer_flask`** are correctly two. But "the first vessel" (key alias on tree_flask) is also a different object in ch11 ("the first vessel's lid lodged in a root").
- **`basin`** merges salt basin, old market basin and black-glass bowl/disk (ch7 "black glass disk", ch12 "black-glass bowl"). Split `salt_basin`.
- **`blue_paper` alias "small, flat fish"**: a transformation (ch11), not a merge. Keep, but a grader may treat it as a separate entity.
- **`oldest_tree` alias "tree" / "the old tree"**: "the tree" is generic. OK to merge since there is one named tree.
- **`vael` aliases "the weather clerk"**: matches "weather clerks" plural. Drop.
- **`mara` aliases "mother", "her mother", "your mother"** also match Nemi's mother (ch6 "My mother painted that", ch11 "My mother sold it a place") and Vael's mother ("Vael's first mother signed it", ch6) and Cale's grandmother. Disambiguate in notes.
- No two separate key people are secretly one person. Mara = Vey is not supported by the text ("Vey was there before me"), though the shared scar invites it.

## 4. Brief compliance

- **Word counts:** 24,698 total. Per chapter 1,812-2,231 (ch11 is the short one at 1,812; ch3 2,231). Met. Chapter headers `# Chapter N: Title` are present.
- **Cast:** 9 named people (Oruva, Vael, Nemi, Cale, Iven, Vey, Mara, Tavin, Pell). Met, at the low end. Places: 11 named (Ors, House of Folded Water, Room Below Mouth, Silt Choir, Low Weather, Counting Room, Bell Orchard, Drowned Stair, Red Channel, dye-house, market court) plus unnamed. Met, at the top of the range if the court is counted. Objects: well over 10. Met.
- **Many reference styles:** met. Examples: "Oruva Senn / Or / the third Listener", "Vey Orin / Vey of the Orchard / the woman with a copper hand / the first Listener", Cale "Keeper".
- **Similar names or same title:** met. Three Senns; Orri/Orin/Oruva/Or; "Listener" held by four people. The brief's confusion element is genuinely present.
- **Same-person reveal:** met but weak for Vey. She names herself in ch4, so "the woman with a copper hand = Vey" is not much of a reveal; the identity with the portrait's first Listener and "Vey Orin" lands in ch5-8. The Mara = hooded visitor = mother reveal (ch7-9) and Or = third Listener (ch8) are real reveals.
- **Moving objects:** met (tooth, ring, branch, tin case, key, map, chart).
- **3+ containers revealed later:** met in the text (tooth in jar ch1; flask in the tree hollow ch3; flask in wall behind portrait ch6; six-lidded box contents ch6; jar in flour sack ch5; hidden rooms ch5/7/9). The key encodes only part, and omits the jar-contained-tooth and flour-sack ones.
- **Differing knowledge:** met in the text, thin in the key (see section 2).
- **False belief held most of the book:** met in the text but the key's candidate is weak. The best one is Or's belief that her mother is dead (ch1 implied, ch7 explicit, corrected ch7/9) and the key omits it. Vael's orchard belief is real but softens by ch7/8.
- **Early fact corrected:** met ("the old weather took something" ch1 -> ch3; "the orchard stole rain" ch2 -> ch10; "no water/trick of the lanterns" ch4 -> ch10-12).

## 5. Safety, originality, coherence

- **Real people/brands/borrowed characters:** none found. Names (Ors, Oruva, Vael, Cale Rusk, Nemi Tallow, Iven Orri, Vey Orin, Mara Senn, Tavin Rell, Pell) read as invented. "Cale", "Mara" and "Vael" are generic fantasy-style names, not distinctive borrowings. No setting or plot echo of a known work.
- **Instructions aimed at an AI reader:** none (greps for AI/model/system-prompt/ignore found nothing). In-world meta lines ("Do not write this down." ch5, "reading instructions aloud" ch3, labels "Witness, Passage, Return" ch10) are story content.
- **Offensive content:** none.
- **Coherence:** a readable weather-fantasy with a distinct premise (town stores weather in labelled jars; the storm is a witness; the bargain was altered). But it is not a clean story. The text has many internal contradictions that make some gold ungradable:
  - Mara's death date: "died when Or was six" and "died in a fever the year Or was born" (both ch7); ch8 Or says "I was born after Mara disappeared".
  - Vael's account flips between ch7 ("She did not die"), ch8 ("I don't know") and ch5 ("There wasn't one" bargain, then "I said there was a story").
  - Tin case, seed, vial, key and ring positions contradict across ch9-12 (above).
  - The portrait's location; the basin "beyond town" versus under the market court; Iven "an old person" versus "a child" when the portrait was painted over.
  - Several chapters (3, 5, 6, 8, 10) end with a stack of late paragraphs that restate or re-time earlier scenes (ch10: they are already at the causeway, then "Before they left the courtyard"), and ch3 has "Or tucked the tooth away" / "returned the tooth to the case" after the tooth is out of the case on the spoon.
  - The ending is gentle, with no resolution of the cast's fates beyond the storm leaving.

## Verdict: USABLE AFTER THESE KEY FIXES

The book meets the brief and is safe. The key needs the edits below, and the grader should avoid rows on the contradictory facts flagged in 1.10 and section 5 (mark them "do not grade").

Exact JSON edits (apply to key.json; the text uses curly apostrophes, so use ’ in any quote containing one, e.g. "Your mother’s name."):

1. entities.iven.aliases: remove `"Listener"` and `"the old Listener"`.
2. entities.vey.aliases: add `"the old Listener"`, `"the woman with the copper hand"`, `"the woman on the causeway"`, `"Vey of the Orchard"`, `"the woman in the orchard"`, `"the missing first Listener"`.
3. entities.mara.aliases: add `"the hooded person"`, `"the visitor"`.
4. entities.vael.aliases: remove `"the weather clerk"`; add `"the chief clerk"` only if you accept it as Vael.
5. entities.pell.first_chapter -> 1. entities.market_court.first_chapter -> 1. entities.old_map.first_chapter -> 7.
6. entities.answer_flask.aliases: remove `"flask"`, `"the flask"`.
7. entities.room_below_mouth.aliases: remove `"the lower room"`.
8. Replace entities.hidden_chamber with three entities: `carved_chamber` (aliases `"room under the room"`, `"the room under the room"`, `"the room beneath the room"`; first_chapter 5), `mara_room` (aliases `"hidden chamber"`, `"the hidden chamber"`, `"small chamber"`, `"hidden room"`; first_chapter 9), `vey_room` (aliases `"small room"`; first_chapter 7). Locations: `carved_chamber` in `house` from 5 (evidence unchanged), `mara_room` in `room_below_mouth` from 9, `vey_room` in `drowned_stair` from 7.
9. Add entities `blue_bowl` (object; aliases `"blue bowl"`, `"blue-black bowl"`, `"the blue bowl"`; first 2), `flour_sack` (object; `"flour sack"`; first 1), `nameless_jar` (object; `"nameless jar"`; first 5), `salt_basin` (place; `"salt basin"`; first 3).
10. same_as: change `["vey","the woman with a copper hand",8]` to `["vey","the woman with a copper hand",4]`; change `["mara","the hooded clerk who carried jars",9]` to `["mara","the hooded visitor",8]`; add `["oruva","the third Listener",8]` and `["vey","the other Listener",4]`.
11. not_same: add `["iven","vey","Iven Orri and Vey Orin: near-identical surnames and both called Listener"]`, `["vael","mara","Vael Senn and Mara Senn share a surname"]`, `["cale","vey","Cale wears a copper glove; Vey's hand is plated copper"]`.
12. holdings: change blue_tooth oruva `from_chapter` 3 -> 2; delete the blue_tooth vael row (4-8); change first_jar oruva row to `"from_chapter":5,"to_chapter":5` with evidence `"Or showed her the flour sack, and the jar within it."`; change tin_case oruva `to_chapter` 11 -> 9; change six_lidded_box nemi `from_chapter` 10 -> 6, `to_chapter` null; change rain_vial oruva `to_chapter` 10 -> 9; change black_seed oruva `to_chapter` 12 -> 10; change old_map vael row evidence to `"Vael folded the map and slipped it into the inside pocket of her collar."` (ch8, from_chapter 8).
13. locations: change market_court `from_chapter` 12 -> 1; add `{"entity":"blue_bowl","in":"counting_room","from_chapter":4,"to_chapter":7,"evidence":"Vael led the tooth into the Counting Room and placed it in the blue bowl beneath a glass lid."}` (verify that quote in ch4).
14. containers: change tin_case/blue_tooth `revealed_chapter` 3 -> 2; add `{"container":"first_jar","contents":["blue_tooth"],"revealed_chapter":1,"evidence":"A blue tooth fell into her palm."}` and `{"container":"flour_sack","contents":["first_jar"],"revealed_chapter":5,"evidence":"Or showed her the flour sack, and the jar within it."}` and `{"container":"blue_bowl","contents":["blue_tooth"],"revealed_chapter":4,"evidence":"Vael put the tooth inside the blue bowl and covered it with her ledger."}`.
15. knowledge: replace the nemi row with `{"who":"oruva","learns":"Nemi carried the key when the first Listener was put below the House.","chapter":6,"evidence":"When the old Listener was put below the House, I was the one who carried the key."}`; replace the mother row with `{"who":"oruva","learns":"Mara Senn, recorded as dead, is her mother and did not die.","chapter":7,"evidence":"Your mother's name."}` and `{"who":"oruva","learns":"Her mother Mara Senn is alive.","chapter":9,"evidence":"I am still your mother."}`; change the Vey-identity row to chapter 4 with evidence `"I was the other Listener."`.
16. false_beliefs: delete the vael "trick of the lanterns" row; add `{"who":"oruva","believes":"Her mother Mara Senn is dead.","from_chapter":1,"corrected_chapter":9}`; change cale row to `"corrected_chapter":11`.
17. corrections: change "trick of the lanterns" `stated_chapter` 8 -> 4 (evidence stays ch10 "Yes."); change "Mara Senn was dead." `stated_chapter` 7 -> 1, `corrected_chapter` 9 -> 7, or keep 9 and add a ch7 row, and add `{"claim":"The oldest tree has seven branches.","stated_chapter":1,"corrected_chapter":3,"evidence":"The oldest tree had nine branches, but the drawing on the notice had only seven."}`.
18. Mark as "do not grade (text contradicts itself)": tin_case after ch9, black_seed after ch10, rain_vial after ch9, black_iron_key 5-11, Mara's death date, basin location in ch10, portrait location.
