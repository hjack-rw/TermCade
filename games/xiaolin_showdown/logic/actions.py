"""Pure vault actions between duels — no I/O: deposit, use-power, and draw.

Draw pulls from the player's *personal* deck, which fills when they shelve surplus cards over the
hand limit. Together, shelving a card and drawing a fresh one is how the player cycles their hand.
"""

from __future__ import annotations

from .models import Card, remove_card_from_hand
from .settings import XiaolinSettings
from .state import XiaolinState
from .turn import max_hand_size

# The gag Wu Ohwah Tegu Saim (deposit/0) has a "? ? ?" power that does nothing when used.
FIZZLE_MESSAGE = "You feel like something should have happened..."
DRAW_MESSAGE = "Chronokinesis warps time — you draw a Wu!"


def can_deposit(state: XiaolinState, deposit_limit: int) -> bool:
    """A hand card may be cashed for points, unless it would empty the hand or the turn's
    deposit limit is spent."""
    return len(state.player.hand) > 1 and state.deposit_counter < deposit_limit


def deposit(state: XiaolinState, card: Card) -> None:
    """Cash ``card`` from the player's hand for its points; counts against the turn limit.

    The derived ``Player.initiative`` updates itself when the hand changes.
    """
    state.player.hand.remove(card)
    state.player.points += card.points
    state.deposit_counter += 1


def can_draw(state: XiaolinState, settings: XiaolinSettings) -> bool:
    """The player may pull one Wu from their personal deck — if the deck holds one, this turn's
    draw is unspent, and the hand has room under the size limit."""
    return (
        bool(state.player.deck)
        and state.draw_counter < settings.draw_limit
        and len(state.player.whole_hand) < max_hand_size(state.player, settings.max_hand_size)
    )


def draw(state: XiaolinState) -> Card:
    """Pull the top Wu of the player's personal deck into their hand; counts against the turn limit."""
    card = state.player.deck.pop(0)
    state.player.hand.append(card)
    state.draw_counter += 1
    return card


def usable_powers(state: XiaolinState, deposit_limit: int) -> list[Card]:
    """Wu whose power the player can actively use now: a hand power-up (``hand``/+1), or a
    ``deposit``-trigger Wu while a deposit is still allowed this turn."""
    can_dep = can_deposit(state, deposit_limit)
    return [
        card
        for card in state.player.whole_hand
        if (card.power.trigger == "hand" and card.power.effect > 0)
        or (card.power.trigger == "deposit" and can_dep)
    ]


def use_power(state: XiaolinState, card: Card) -> str:
    """Fire ``card``'s power, then discard it for **no points**; return a line describing what
    happened.

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
