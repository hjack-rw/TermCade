"""Pure vault actions between duels — no I/O.

Ported from the reference's ``can__deposit`` / ``player__draws__or__deposits`` (deposit path) and
``player__uses__power``. Draw is deferred: the reference's draw pulls from the player's *personal*
deck, which only fills from over-limit discards in the duel turn flow — so it is inert until that lands.
"""

from __future__ import annotations

from .models import Card, remove_card_from_hand
from .state import XiaolinState

# The gag Wu Ohwah Tegu Saim (deposit/0) has a "? ? ?" power that does nothing when used.
FIZZLE_MESSAGE = "You feel like something should have happened..."
DRAW_MESSAGE = "Chronokinesis warps time — you draw a Wu!"


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


def usable_powers(state: XiaolinState, deposit_limit: int) -> list[Card]:
    """Wu whose power the player can actively use now (ENGINE ``power__choice``, non-duel): a hand
    power-up (``hand``/+1), or a ``deposit``-trigger Wu while a deposit is still allowed this turn."""
    can_dep = can_deposit(state, deposit_limit)
    return [
        card
        for card in state.player.whole_hand
        if (card.power.trigger == "hand" and card.power.effect > 0)
        or (card.power.trigger == "deposit" and can_dep)
    ]


def use_power(state: XiaolinState, card: Card) -> str:
    """Fire ``card``'s power (non-duel ``ENGINE.powers``), then discard it for **no points**;
    return a line describing what happened.

    Distinct from :func:`deposit`, which banks the Wu for its points. Only Chronokinesis
    (``deposit``/+1) does something — it draws a Wu; every other power just fizzles.
    """
    if card.power.trigger != "deposit":  # a hand power-up is passive — nothing to trigger, kept
        return FIZZLE_MESSAGE

    drew = card.power.effect == 1 and bool(state.card_deck)
    if drew:
        state.player.hand.append(state.card_deck.pop(0))
        if not state.card_deck:
            state.has_ended = True
    state.deposit_counter += 1
    remove_card_from_hand(state.player, card)  # discarded, no points
    return DRAW_MESSAGE if drew else FIZZLE_MESSAGE
