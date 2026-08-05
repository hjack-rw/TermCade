"""Frozen game data — the element wheel and the card-layout constants.

Not player knobs: hand sizes, deck size, point limit, draw/deposit limits, starting points, the wear
limit, and the training bar's shape are all tunable and live in :mod:`settings` as
``XiaolinSettings``. Everything here is fixed by the rules or by the shape of the bundled card DB.
"""

from __future__ import annotations

ELEMENTS = ("water", "fire", "wind", "earth", "metal")

# A challenge names a stat — or TOURNAMENT, which names all three. The two are spent the same way:
# three Wu is the most anyone may commit. A stat challenge fields them together in one battle; a
# tournament spends them one at a time over three, contesting a different stat each. So the choice
# is not "how many Wu" but "all at once, or spread out" — and a tournament may only be called when
# both duelists can field all three.
TOURNAMENT = "tournament"
TOURNAMENT_BATTLES = 3

# Jack-bots Attack!'s own challenge (see logic/characters/jack.py): never named, never a tournament — one
# battle, all three stats weighed at once, majority wins. A sentinel in `DuelState.challenge` the
# same way TOURNAMENT is, not a real stat.
BRAWL = "brawl"

# water⇄fire and wind⇄earth oppose each other; ``metal`` is neutral and has no opposite. In a duel a
# card scores +1 with a matching background, −1 against its opposite (or when the background is
# metal), 0 otherwise — see ``mechanics.scoring._element_score``.
OPPOSITES = {
    "water": "fire",
    "fire": "water",
    "wind": "earth",
    "earth": "wind",
}

# A character is granted its signature Wu by a card whose id sits below this line — the pool is
# every OTHER card (`setup.new_game`/`_weighted_game` filter on `card.id >= FIRST_DECK_CARD`, not on
# position, so a signature card's id only needs to be negative or small; it never has to occupy a
# hole in the pool's own contiguous run):
#   0     blank — the template/dummy card and deck filler/padding
#   1..4  the four playable characters' signature Wu — never in the draw pool; granted on pick.
#         Each *shares* its character's power (the dragon), so power_id is -1..-4 too.
#   5     Moby Morpher, Hannibal's wudai — IN the pool by default, removed only when Hannibal is in
#         play. Its power is its own ("Allomorphia", 30); Hannibal's is "Free Allomorphia" (-5).
#   -8    Jack-Bot, Jack's wudai — never in the pool. Appended after Moby Morpher, so it could not
#         reuse a low positive id the way 1-4 do; it carries its power's id directly instead (see
#         `setup._reserve_signature`).
# So the shuffled draw pile starts at card 5 (Moby Morpher included).
FIRST_DECK_CARD = 5

# The Yin/Yang Yo-Yo halves and their combined form (see logic/actions.combine_yoyo /
# self_correct_yoyo) — matched by id, not `Mechanic.STAT_SWAP`/`CHI_SWAP` alone, since a mechanic
# check can't tell "held a half" apart from "held the combined card" or from a future third Wu.
YING_YOYO_ID = 78
YANG_YOYO_ID = 79
YIN_YANG_YOYO_ID = 80


def in_pool(card_id: int) -> bool:
    """Whether a card is dealt into a run's draw pile at all.

    Every card at or above `FIRST_DECK_CARD`, except the combined Ying-Yang Yo-Yo: "change two
    Yo-Yos cards into this one card" means it is built only by combining its two halves (see
    `actions.combine_yoyo`), never drawn — the same reason a signature Wu never rides the pool on
    its own, a different mechanism for it.
    """
    return card_id >= FIRST_DECK_CARD and card_id != YIN_YANG_YOYO_ID
