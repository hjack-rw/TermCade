"""The five Xiaolin elements and their opposition, used by duel scoring.

water⇄fire and wind⇄earth are opposites;
``metal`` is neutral (no opposite). During a duel a card's element scores +1 with a matching
background, −1 against the opposite (or when the background is metal), 0 otherwise.
"""

from __future__ import annotations

ELEMENTS = ("water", "fire", "wind", "earth", "metal")

OPPOSITES = {
    "water": "fire",
    "fire": "water",
    "wind": "earth",
    "earth": "wind",
}
