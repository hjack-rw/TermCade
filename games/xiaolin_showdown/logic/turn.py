"""The vault turn — what happens on each return to the vault, between showdowns.

Keeps a hand from exceeding its size limit (surplus goes to the personal deck) and flags the run
finished when a point limit is reached or the draw pile runs dry. A short hand is *not* topped up
automatically — the player refills it themselves with Draw; only a fully empty hand is emergency-
drawn from the main pile, so the duel loop can still terminate rather than strand on an empty hand.
"""

from __future__ import annotations

from termcade.core.rng import Rng

from .models import Player, remove_card_from_hand
from .settings import XiaolinSettings
from .state import XiaolinState


def refill_hands(state: XiaolinState, settings: XiaolinSettings, *, rng: Rng) -> None:
    """Bring both hands within their size limit and update ``has_ended``.

    Runs each time control returns to the vault (between showdowns). Re-balances until both hands
    are stable — loops :func:`oversee_hand_size` over both until neither reports more work. The
    player's interactive over-limit discard is handled by the screen *before* this runs, so any
    shedding here (the bot's) is random.
    """
    if state.player.points >= settings.point_limit or state.bot.points >= settings.point_limit:
        state.has_ended = True

    while not (
        oversee_hand_size(state, is_player=True, settings=settings, rng=rng)
        and oversee_hand_size(state, is_player=False, settings=settings, rng=rng)
    ):
        pass


def oversee_hand_size(
    state: XiaolinState, *, is_player: bool, settings: XiaolinSettings, rng: Rng
) -> bool:
    """Nudge one duelist's hand toward its size limit by one pass; return whether it is settled.

    Over the limit → shed the surplus at random to the personal deck. Under → leave it (the player
    tops up manually with Draw), unless the hand is *empty*, which is emergency-drawn from the main
    pile. Returns ``False`` after shedding (the caller re-checks), ``True`` otherwise.
    """
    player = state.player if is_player else state.bot
    over = len(player.whole_hand) - max_hand_size(player, settings.max_hand_size)
    if over <= 0:
        if not player.whole_hand:  # only an empty hand is refilled automatically
            _emergency_fill(state, player, settings)
        return True
    if state.has_ended:
        return True  # game over — leftover cards stay, they still count toward the final score

    for _ in range(over):
        card = rng.choice(player.hand)
        remove_card_from_hand(player, card)
        player.deck.append(card)
    return False


def _emergency_fill(state: XiaolinState, player: Player, settings: XiaolinSettings) -> None:
    """Refill an empty hand from the main pile (up to ``empty_draw_limit``); emptying it ends the run."""
    limit = max_hand_size(player, settings.max_hand_size)
    for _ in range(settings.empty_draw_limit):
        if not state.card_deck or len(player.whole_hand) >= limit:
            break
        _draw_from_main(state, player)


def bot_turn(state: XiaolinState, settings: XiaolinSettings) -> list[str]:
    """The bot's between-showdown vault turn; returns a short log of what it did, for the player.

    It deposits (see :func:`_bot_deposits` — how it banks points toward the win) then refills one
    card toward the hand limit from its own deck, since it has no manual Draw as the player does.
    """
    log = _bot_deposits(state, settings)
    _bot_refill(state, settings)
    return log or [f"{state.bot.character.name.split('_')[0]} passed"]


def _bot_deposits(state: XiaolinState, settings: XiaolinSettings) -> list[str]:
    """Up to ``deposit_limit`` deposits: swap each ``deposit``/+1 Wu for a fresh draw, then cash
    plain ``deposit``/0 Wu for their points."""
    name = state.bot.character.name.split("_")[0]
    log: list[str] = []
    deposits = 0

    for card in list(state.bot.whole_hand):  # snapshot: the hand mutates as cards leave
        if deposits >= settings.deposit_limit:
            break
        if card.power.trigger == "deposit" and card.power.effect == 1 and state.card_deck:
            _draw_from_main(state, state.bot)  # trade the power card for a fresh one
            remove_card_from_hand(state.bot, card)
            deposits += 1
            log.append(f"{name} played {card.name} and drew a Wu")

    for card in list(state.bot.whole_hand):
        if deposits >= settings.deposit_limit:
            break
        if card.power.trigger == "deposit" and card.power.effect == 0:
            state.bot.points += card.points
            remove_card_from_hand(state.bot, card)
            deposits += 1
            log.append(f"{name} deposited {card.name} for {card.points} pt{'s' if card.points != 1 else ''}")
    return log


def _bot_refill(state: XiaolinState, settings: XiaolinSettings) -> None:
    """Quietly recover one shed card from the bot's personal deck (it has no manual Draw)."""
    if state.bot.deck and len(state.bot.whole_hand) < max_hand_size(state.bot, settings.max_hand_size):
        state.bot.hand.append(state.bot.deck.pop(0))


def max_hand_size(player: Player, base: int) -> int:
    """The size limit, plus one while a "Third-Arm Sash" (a hand power with effect −1) is held."""
    sash = any(c.power.trigger == "hand" and c.power.effect == -1 for c in player.whole_hand)
    return base + int(sash)


def _draw_from_main(state: XiaolinState, player: Player) -> None:
    """Emergency draw from the shared pile; emptying it ends the run."""
    player.hand.append(state.card_deck.pop(0))
    if not state.card_deck:
        state.has_ended = True
