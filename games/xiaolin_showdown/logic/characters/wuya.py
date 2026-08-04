"""Wuya's own witchcraft: the recall — the one piece of her power that isn't just a shared-mechanic
table entry (see ``mechanics.powers.Mechanic.WITCHCRAFT`` for the rest: the return-to-hand and the
wear it costs, both generic ``WITCHCRAFT`` rules any card carrying it would follow the same way).
"""

from __future__ import annotations

from ..schema.state import XiaolinState
from ..flow.turn import duel_value

# What the oldest lost Wu must be worth before Wuya's witchcraft spends her temple action on the
# recall. She pays no Wu (unlike the Rooster), so the bar sits under the Rooster's own REVIVAL_MARGIN
# (see temple_ai.py) — but an action is still a deposit not made, and a scrap is not worth one.
WITCH_RECALL_MARGIN = 3

# How many Wu the witchcraft may call back in a whole run. The recall is a RESOURCE, not a tap: with
# no ceiling she never runs out of ammunition and the counterplay collapses to outrunning her to the
# point target. A cap lets her spend it greedily — the margin stays low, so she takes what is worth
# taking — and then it is gone. Raising the margin instead reached the same win rate by tuning the
# signature mechanic into almost never firing, which is a footnote, not a boss.
WITCH_RECALL_LIMIT = 3

# Wuya's Witchcraft senses the Shen Gong Wu: she flies the Early Bird on a shorter initiative lead
# than anyone else needs — her bond feels the moment to snatch the pile rather than outrunning them to
# it. This is her tempo edge now that the flat +1 initiative is gone; the value is a balance knob.
WITCH_EARLY_BIRD_GAP = 2


def recall_index(state: XiaolinState) -> int:
    """Which lost Wu Wuya's witchcraft calls back — the most valuable, the one her bond finds first.

    The single source of truth for the pick: :func:`worth_recalling` reads it to gate the action and
    ``turn._recall_witchcraft`` pops it. Index-based, so the same Wu is judged and taken by identity.
    """
    return max(range(len(state.lost)), key=lambda i: duel_value(state.lost[i]))


def worth_recalling(state: XiaolinState) -> bool:
    """Wuya's recall: the most valuable Wu in the lost pile, against the action it costs.

    Spent, not owned — ``WITCH_RECALL_LIMIT`` of them in a run, and the run is the whole allowance.
    """
    if state.witch_recalls >= WITCH_RECALL_LIMIT:
        return False
    return bool(state.lost) and duel_value(state.lost[recall_index(state)]) >= WITCH_RECALL_MARGIN
