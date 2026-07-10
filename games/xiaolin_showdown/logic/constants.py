"""Frozen game data — the element wheel and the card-layout constants.

Not player knobs: hand sizes, deck size, point limit, draw/deposit limits and starting points are
tunable and live in :mod:`settings` as ``XiaolinSettings``. Everything here is fixed by the rules or
by the shape of the bundled card DB.
"""

from __future__ import annotations

ELEMENTS = ("water", "fire", "wind", "earth", "metal")

# water⇄fire and wind⇄earth oppose each other; ``metal`` is neutral and has no opposite. In a duel a
# card scores +1 with a matching background, −1 against its opposite (or when the background is
# metal), 0 otherwise — see ``mechanics.scoring._element_score``.
OPPOSITES = {
    "water": "fire",
    "fire": "water",
    "wind": "earth",
    "earth": "wind",
}

# "Beginning Wu" cards (power_id < 0) are tied to a character by id == abs(power_id):
#   0     blank — the template/dummy card and deck filler/padding
#   1..4  the four playable characters' signature Wu — never in the draw pool; granted on pick
#   5     Moby Morpher, Hannibal's Wu (non-playable carrier) — IN the pool by default,
#         removed only when Hannibal is in play
# So the shuffled draw pile starts at card 5 (Moby Morpher included).
FIRST_DECK_CARD = 5
