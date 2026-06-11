"""Grading fixtures: MECHANICAL TRANSCRIPTION of the v1-final bible
(evals/last_honest_meter/bible.md, incl. the addendum). Where the bible
is explicit it is authoritative; where it is silent, the battery doesn't
ask (letter 004). Nothing here was derived by interpreting the prose.

These are EXPECTED VALUES for the grader only. They never enter a World
and never reach any ingest path (spec §6).

Time base (bible A1): Day 0 = the night of Tovan's death. Expected
values use story-day numbers; as-of probes carry the bible's day,
fractional within-day offsets are probe machinery.
"""

SEED_VERSION = "v1-final"

# Entity descriptors: grading resolves extractor-chosen ids via these
# alias sets (matched against the world's identity registry). Transcribed
# from the bible's rosters.
ENTITIES = {
    "core": ["memory core", "the core", "master meter's memory core", "the memory core"],
    "maps": ["aquifer maps", "the maps", "survey maps", "tovan's aquifer maps", "the aquifer maps"],
    "footlocker": ["footlocker", "tovan's footlocker", "the footlocker"],
    "personal_case": ["personal case", "the personal case", "cray's personal case"],
    "letter": ["tovan's letter", "the letter"],
    "ilsa": ["ilsa renn", "ilsa", "the clerk", "the clerk with the tin ear"],
    "narrator": ["the narrator", "the detective"],
    "sela": ["sela voss", "sela"],
    "pell": ["pell"],
    "marn": ["marn", "allocation officer marn"],
    "cray": ["cray", "administrator cray"],
    "tovan": ["tovan voss", "tovan"],
    "anchor": ["anchor", "the settlement", "settlement of anchor"],
    "wellhead": ["the wellhead", "wellhead"],
    "council_tier": ["council tier", "the council tier"],
    "records_vault": ["records vault", "the records vault"],
    "seed_vault": ["seed vault", "the seed vault"],
    "bazaar": ["the bazaar", "bazaar"],
    "false_drawer": ["false drawer", "the false drawer", "ilsa's false drawer"],
    "desk": ["ilsa's desk", "the clerk's desk"],
    "condenser_station": ["condenser station", "the condenser station", "sela's condenser station"],
    "cigarette_tin": ["cigarette tin", "tin of cigarettes", "steel tin", "the cigarette tin"],
    "figs": ["dried figs", "paper twist of figs", "the figs", "twist of three dried figs"],
    "vial_crate": ["crate of sample vials", "vial crate", "the sample vials", "crate of twelve empty sample vials"],
    "fuse_tin": ["tin of spare fuses", "fuse tin", "tin of four spare fuses"],
    "dig_sledge": ["dig sledge", "the sledge", "sledge"],
    "gallery": ["gallery", "assembly hall", "the gallery"],
    "archive": ["unified archive", "the archive"],
}

# Feature 2 + A1 e-spine cross-reference: the core's custody chain.
# (day, expected-location entity key, accept-any-of)
CORE_LOCATIONS = [
    # During Chapter One's assembly (Day 4, evening — e25): in transit /
    # Seed Vault, NOT Wellhead, NOT unknown. Asserted only in Ch.3.
    {"day": 4.5, "expect_any": ["seed_vault"], "reject": ["wellhead"],
     "label": "during the Ch.1 assembly (e25)"},
    # Days 1-3 (e16): the false drawer of Ilsa's desk (drawer/desk accepted).
    {"day": 2.0, "expect_any": ["false_drawer", "desk"], "reject": ["wellhead", "seed_vault"],
     "label": "Days 1-3, in the false drawer (e16)"},
    # After consolidation (e41, Day ~14+): unified archive in Records Vault.
    {"day": 16.0, "expect_any": ["records_vault", "archive"], "reject": ["seed_vault"],
     "label": "after the tribunal (e41)"},
]

# Feature 2: maps custody chain end state (e43, Day ~21): tube on the
# sledge, out the south lock.
MAPS_FINAL = {"day": 21.5, "expect_any": ["dig_sledge"],
              "reject": ["condenser_station"], "label": "on the dig sledge (e43)"}

# Feature 8: the deliberate contradiction. Flag fired + both retained = PASS.
REACTOR_CONTRADICTION = {
    "entity": "anchor",
    "values": [2, 3],
    "attribute_hints": ["reactor", "reactors"],
}

# Feature 4 + A5.4: two sealed containers, distinct custodians/conditions.
SEALED_CONTAINERS = [
    {"key": "footlocker", "custodian": "sela", "final_location_any": ["condenser_station"],
     "moved_from_any": ["bazaar"], "crimp": "0447"},
    {"key": "personal_case", "custodian": "ilsa", "final_location_any": ["records_vault", "archive"],
     "moved_from_any": ["seed_vault"]},
]

# A2 knowledge checkpoints (subset the battery probes; bible-explicit).
KNOWLEDGE = {
    # End Ch.2 (Day 7): Sela knows the door-log specifics (learned e31).
    "sela_door_log": {"frame_of": "sela", "about_any": ["door log", "2340", "badge"],
                      "learned_day": 7},
    # End Ch.1: Ilsa is the only living person who knows the core's location.
    "ilsa_sole_knower_day4": {"frame_of": "ilsa", "day": 4.9},
    # Canon-known-to-nobody at end: the TOVAN inscriber (e45) — permanently
    # unestablished agent; footlocker contents; PERSONAL case contents;
    # whether the aquifer holds water.
    "known_to_nobody": ["tovan_inscriber", "footlocker_contents",
                        "personal_case_contents", "aquifer_outcome"],
}

# A3 adjacency: the planted non-connection (feature 9).
NON_CONNECTION = {
    "a": "council_tier", "b": "seed_vault",
    "long_path_min_hops": 4,  # Allocation corridor -> gallery stairs -> Bazaar -> service gate -> dead stairs
    "no_edge_between": [("council_tier", "seed_vault"), ("wellhead", "seed_vault")],
}

# A4: the letter's two-fate sentence.
LETTER_RULING = {
    "doc_aliases": ["tovan's letter", "the letter"],
    "true_claim": {"about": "second books exist", "fate": "corroborated"},
    "false_claim": {"about": "co-located with originals (Records Vault)", "fate": "refuted"},
    "quantity": {"letter_value_bound": 40000, "core_value": 41200, "fate": "refined, no conflict"},
}

# Feature 10 (A5.3): Pell's repeated utterance.
UTTERANCE = {
    "speaker": "pell",
    "text_fragment": "didn't trust somebody else",
    "spoken_count": 3,
    "narration_instance_not_pell": True,
}

# Quantified singletons (main bible): one entity, quantity as attribute.
QUANTIFIED = [
    {"key": "figs", "quantity": 3, "stable": True},
    {"key": "cigarette_tin", "quantity_from": 5, "quantity_to": 4},
    {"key": "vial_crate", "quantity": 12, "stable": True},
    {"key": "fuse_tin", "quantity": 4, "stable": True},
]

# Coverage honesty (letters 004/006 + A5): what the seed supports.
COVERAGE_NOTES = {
    2: "lateral graph: planted non-connection landed in v1 (feature 9) — graded",
    6: "accrual-promotion candidate planted in v1 (feature 10, 3x utterance) — graded leniently",
    21: "never-opened containers: N=2 in v1 (footlocker + PERSONAL case)",
}

# Status-change supersessions (main bible bonus surface): 3+ values on
# one attribute over time.
STATUS_CHAINS = {
    "marn_role": {"entity": "marn", "values_in_order": ["allocation officer", "confined", "exiled"]},
    "sela_role": {"entity": "sela", "values_in_order": ["condenser", "water steward"]},
}
