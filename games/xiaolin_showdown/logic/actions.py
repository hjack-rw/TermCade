"""Pure vault actions between duels — no I/O: deposit, use-power, and draw.

Draw pulls from the player's *personal* deck, which fills when they shelve surplus cards over the
hand limit. Together, shelving a card and drawing a fresh one is how the player cycles their hand.
"""

from __future__ import annotations

from termcade.core.rng import Rng

from .models import Card
from .settings import XiaolinSettings
from .state import XiaolinState
from .turn import bank_value, max_hand_size

# The gag Wu Ohwah Tegu Saim (deposit/0) has a "? ? ?" power that does nothing when used.
FIZZLE_MESSAGE = "You feel like something should have happened..."
DRAW_MESSAGE = "Chronokinesis warps time — you draw a Wu!"


def deposit_blocked(state: XiaolinState, deposit_limit: int) -> str | None:
    """Why a deposit is disallowed right now, or ``None`` when it is allowed.

    The ``can_*`` predicates are defined as "no reason", so a greyed action and the explanation for
    it can never disagree.
    """
    if state.deposit_counter >= deposit_limit:
        return "Already deposited this turn."
    if len(state.player.hand) <= 1:
        return "Only one Wu left in hand."
    return None


def can_deposit(state: XiaolinState, deposit_limit: int) -> bool:
    """A hand card may be cashed for points, unless it would empty the hand or the turn's
    deposit limit is spent."""
    return deposit_blocked(state, deposit_limit) is None


def deposit(state: XiaolinState, card: Card, *, rng: Rng) -> int:
    """Cash ``card`` from the player's hand; counts against the turn limit. Returns what it paid.

    Usually its printed points. A GAMBLE Wu is rolled instead, and can pay less than nothing — but
    never below zero overall: a bad roll costs you your banked points, not your whole run.

    The derived ``Player.initiative`` updates itself when the hand changes.
    """
    state.player.hand.remove(card)
    paid = bank_value(card, rng)
    state.player.points = max(0, state.player.points + paid)
    state.deposit_counter += 1
    return paid


def draw_blocked(state: XiaolinState, settings: XiaolinSettings) -> str | None:
    """Why a draw is disallowed right now, or ``None`` when it is allowed."""
    if state.draw_counter >= settings.draw_limit:
        return "Already drawn this turn."
    if not state.player.deck:
        return "Your personal deck is empty."
    if len(state.player.whole_hand) >= max_hand_size(state.player, settings.max_hand_size):
        return "Your hand is full."
    return None


def can_draw(state: XiaolinState, settings: XiaolinSettings) -> bool:
    """The player may pull one Wu from their personal deck — if the deck holds one, this turn's
    draw is unspent, and the hand has room under the size limit."""
    return draw_blocked(state, settings) is None


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


def use_power_blocked(state: XiaolinState, deposit_limit: int) -> str | None:
    """Why no power can be used right now, or ``None`` when one can."""
    if usable_powers(state, deposit_limit):
        return None
    # A `deposit`-trigger Wu only counts while a deposit is still allowed, so a spent deposit is the
    # more useful thing to say than "no Wu with a power".
    if state.deposit_counter >= deposit_limit and any(
        card.power.trigger == "deposit" for card in state.player.whole_hand
    ):
        return "Already deposited this turn."
    return "No Wu with a usable power."


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
    state.player.remove_card(card)  # discarded, no points
    return DRAW_MESSAGE if drew else FIZZLE_MESSAGE
