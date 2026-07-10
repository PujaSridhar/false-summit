"""Narrative layer. Canned lines for now; Gemini swaps in behind the same
functions without touching the game loop."""

RIVAL = "Dax"

TAUNTS = {
    1: f"{RIVAL}: 'Nice lap today. Saw you parked at the café — crown's "
       "comfy up here by the way.'",
    2: f"{RIVAL}: 'The causeway isn't about legs, it's about engine. You "
       "don't have one.'",
    3: f"{RIVAL}: 'Posted from the summit. You'd know what it looks like "
       "if you ever got there fast enough.'",
    4: f"{RIVAL}: 'Rollers PR while you were \"sick\". Some of us show up.'",
    5: f"{RIVAL}: 'Three seasons I've held the Corona. Bring a ladder.'",
}

UNDER_REVIEW = ("MANUAL REVIEW. Your time would take the crown — so the "
                "integrity team pulled the file. A human is going to look at "
                "this. You can stand pat, quietly edit the file… or withdraw.")

REVIEW_SURVIVED = ("The reviewer stared at your file for a long time. Then the "
                   "crown changed hands. You got away with it. Almost like it "
                   "never happened — almost.")

REVIEW_CAUGHT = ("The second look found what the first missed. Flagged, "
                 "delisted, and there's a thread about you on the club forum.")

EDIT_CAUGHT = ("You edited a file the reviewer had already seen. The database "
               "keeps every version — the diff between then and now IS the "
               "confession. There was never a version of this where editing "
               "worked.")

WITHDRAWN = ("Upload withdrawn. The crown stays with Dax, the review closes, "
             "and nobody looks at you. Yet.")

CAUGHT = [
    "FLAGGED. The leaderboard entry is gone and there's a red banner on your profile.",
    "The integrity bot doesn't gloat. It just posts the evidence where everyone can see it.",
]

WIN = [
    "Crown taken. It sits a little heavy, doesn't it?",
    "Leaderboard updated. Nobody suspects a thing. You'll still know.",
]

TOO_SLOW = [
    "Upload clean, time honest — and the crown stays with Dax. That's the problem.",
]


def taunt(level_id):
    return TAUNTS.get(level_id, f"{RIVAL} is waiting.")


def verdict(caught, beat_rival):
    if caught:
        return CAUGHT[0]
    if beat_rival:
        return WIN[0]
    return TOO_SLOW[0]
