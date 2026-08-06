"""Wuya's own witchcraft: the recall — the one piece of her power that isn't just a shared-mechanic
table entry (see ``mechanics.powers.Mechanic.WITCHCRAFT`` for the rest: the return-to-hand and the
wear it costs, both generic ``WITCHCRAFT`` rules any card carrying it would follow the same way).
"""

from __future__ import annotations

from ..schema.catalog import load_mechanic_config
from ..schema.state import XiaolinState
from ..flow.turn import duel_value

_WITCHCRAFT = load_mechanic_config()["witchcraft"]

# What the oldest lost Wu must be worth before Wuya's witchcraft spends her temple action on the
# recall. She pays no Wu (unlike the Rooster), so the bar sits under the Rooster's own REVIVAL_MARGIN
# (see temple_ai.py).
WITCH_RECALL_MARGIN = _WITCHCRAFT["recall_margin"]

# How many Wu the witchcraft may call back in a whole run — a capped resource, not a tap.
WITCH_RECALL_LIMIT = _WITCHCRAFT["recall_limit"]

# Wuya flies the Early Bird on a shorter initiative lead than anyone else needs.
WITCH_EARLY_BIRD_GAP = _WITCHCRAFT["early_bird_gap"]


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
