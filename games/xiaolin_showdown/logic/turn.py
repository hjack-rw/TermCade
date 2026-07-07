"""The vault turn — what happens on each return to the vault, between showdowns.

Keeps both hands at their size limit (surplus discarded to the personal deck, a short hand
drawn back up) and flags the run finished when a point limit is reached or the draw pile runs
dry. This is the **loop terminator** — without a vault turn between showdowns the duel loop can
strand on a hand that emptied out.

Pure and TTY-free: the player's over-limit discard is an injected callback; the bot discards at
random via ``rng``. The bot's *own* vault actions (deposit / power-up) are a separate slice.
"""

from __future__ import annotations

from typing import Callable

from termcade.core.rng import Rng

from .models import Card, Player, remove_card_from_hand
from .settings import XiaolinSettings
from .state import XiaolinState

PickDiscard = Callable[[list[Card]], Card]


def refill_hands(
    state: XiaolinState,
    settings: XiaolinSettings,
    *,
    pick_discard: PickDiscard,
    rng: Rng,
) -> None:
    """Bring both hands back to size and update ``has_ended``.

    Runs each time control returns to the vault (between showdowns). Re-balances until both hands
    are stable — loops :func:`oversee_hand_size` over both until neither reports more work.
    """
    if state.player.points >= settings.point_limit or state.bot.points >= settings.point_limit:
        state.has_ended = True

    while not (
        oversee_hand_size(state, is_player=True, settings=settings, pick_discard=pick_discard, rng=rng)
        and oversee_hand_size(state, is_player=False, settings=settings, pick_discard=pick_discard, rng=rng)
    ):
        pass


def oversee_hand_size(
    state: XiaolinState,
    *,
    is_player: bool,
    settings: XiaolinSettings,
    pick_discard: PickDiscard,
    rng: Rng,
) -> bool:
    """Nudge one duelist's hand toward its size limit by one pass; return whether it is settled.

    Over the limit → move surplus to the personal deck (player picks, bot random). Under → draw
    back up from the personal deck (capped by ``draw_limit``), or from the main pile only while the
    hand is empty (capped by ``empty_draw_limit``). Returns ``False`` when it did work and wants a
    re-check, ``True`` when balanced or unable to change further.
    """
    player = state.player if is_player else state.bot
    difference = len(player.whole_hand) - max_hand_size(player, settings.max_hand_size)
    if difference == 0:
        return True

    over_the_limit = difference > 0
    hand_was_empty = not player.whole_hand
    for iteration in range(abs(difference)):
        if over_the_limit and not state.has_ended:
            card = pick_discard(list(player.hand)) if is_player else rng.choice(player.hand)
            remove_card_from_hand(player, card)
            player.deck.append(card)
        elif player.deck and state.draw_counter < settings.draw_limit:
            player.hand.append(player.deck.pop(0))
            state.draw_counter += 1
        elif hand_was_empty and state.card_deck and iteration < settings.empty_draw_limit:
            _draw_from_main(state, player)
        else:
            return True  # can't shed or draw any more — accept the hand as it is
    return False  # did work this pass — ask the caller to re-check


def bot_turn(state: XiaolinState, settings: XiaolinSettings) -> None:
    """The bot's between-showdown vault turn.

    Up to ``deposit_limit`` actions: first swap each ``deposit``/+1 Wu for a fresh draw, then cash
    plain ``deposit``/0 Wu for their points. This is how the bot banks points toward the win — the
    player already deposits from the vault menu. No draw is attempted once the pile is empty.
    """
    deposits = 0

    for card in list(state.bot.whole_hand):  # snapshot: the hand mutates as cards leave
        if deposits >= settings.deposit_limit:
            break
        if card.power.trigger == "deposit" and card.power.effect == 1 and state.card_deck:
            _draw_from_main(state, state.bot)  # trade the power card for a fresh one
            remove_card_from_hand(state.bot, card)
            deposits += 1

    for card in list(state.bot.whole_hand):
        if deposits >= settings.deposit_limit:
            break
        if card.power.trigger == "deposit" and card.power.effect == 0:
            state.bot.points += card.points
            remove_card_from_hand(state.bot, card)
            deposits += 1


def max_hand_size(player: Player, base: int) -> int:
    """The size limit, plus one while a "Third-Arm Sash" (a hand power with effect −1) is held."""
    sash = any(c.power.trigger == "hand" and c.power.effect == -1 for c in player.whole_hand)
    return base + int(sash)


def _draw_from_main(state: XiaolinState, player: Player) -> None:
    """Emergency draw from the shared pile; emptying it ends the run."""
    player.hand.append(state.card_deck.pop(0))
    if not state.card_deck:
        state.has_ended = True
