"""Pure vault actions between duels — no I/O.

Ported from the reference's ``can__deposit`` / ``player__draws__or__deposits`` (deposit path).
Draw is deferred: the reference's draw pulls from the player's *personal* deck, which only fills
from over-limit discards in the duel turn flow — so it is inert until that lands.
"""

from __future__ import annotations

from .models import Card
from .state import XiaolinState


def can_deposit(state: XiaolinState, deposit_limit: int) -> bool:
    """A hand card may be cashed for points, unless it would empty the hand or the turn's
    deposit limit is spent (ENGINE.py can__deposit)."""
    return len(state.player.hand) > 1 and state.deposit_counter < deposit_limit


def deposit(state: XiaolinState, card: Card) -> None:
    """Cash ``card`` from the player's hand for its points; counts against the turn limit.

    (ENGINE ``remove__card__from__hand`` with ``give_points=True``; the derived ``Player.initiative``
    updates itself when the hand changes.)
    """
    state.player.hand.remove(card)
    state.player.points += card.points
    state.deposit_counter += 1
