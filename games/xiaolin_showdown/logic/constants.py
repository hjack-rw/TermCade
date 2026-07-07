"""Structural constants — values tied to the card-data layout, not player knobs.

Player-tunable rules (hand sizes, deck size, point limit, draw/deposit limits, starting
points) live in :mod:`settings` as ``XiaolinSettings`` and are edited as engine settings. Only
genuinely structural values remain here.
"""

from __future__ import annotations

# "Beginning Wu" cards (power_id < 0) are tied to a character by id == abs(power_id):
#   0     blank — the template/dummy card (reference GameData.dummy) and deck filler/padding
#   1..4  the four playable characters' signature Wu — never in the draw pool; granted on pick
#   5     Moby Morpher, Hannibal's Wu (non-playable carrier) — IN the pool by default,
#         removed only when Hannibal is in play (ENGINE.py:44)
# So the shuffled draw pile starts at card 5 (Moby Morpher included).
FIRST_DECK_CARD = 5
