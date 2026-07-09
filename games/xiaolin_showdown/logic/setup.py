"""Build a fresh game.

The RNG and the player's chosen character are injected explicitly — not a seeded global RNG,
not an interactive prompt — so a run stays deterministic and testable. The RNG call order is
preserved exactly — shuffle the draw pile, then pick the bot's character — so a given seed
reproduces the identical game. Card pops consume no randomness.
"""

from __future__ import annotations

from copy import deepcopy

from termcade.core.rng import Rng

from .catalog import Catalog
from .constants import FIRST_DECK_CARD
from .models import Card, Character, Player
from .settings import XiaolinSettings
from .state import XiaolinState


def new_game(
    catalog: Catalog,
    rng: Rng,
    player_character: Character,
    *,
    settings: XiaolinSettings | None = None,
    hard_opponents: bool = False,
) -> XiaolinState:
    """A fresh vault-menu state: shuffled draw pile, both hands dealt, starting points.
    ``settings`` are the (player-chosen) settings for this run; defaults are used when omitted.
    ``hard_opponents`` picks the bot from the tougher roster instead of the easy one.
    """
    settings = settings or XiaolinSettings()
    cards = catalog.cards

    # Draw pile = the non-reserved cards, padded with blanks (card 0) to full size.
    # Hannibal Roy Bean (power id -5) reserves one extra card.
    start = FIRST_DECK_CARD + (1 if player_character.power.id == -5 else 0)
    card_order = list(range(start, len(cards)))
    card_order += [0] * (settings.max_deck_size - len(card_order))
    rng.shuffle(card_order)  # RNG call 1 — must precede the bot pick

    draw_pile = [deepcopy(cards[i]) for i in card_order[: settings.max_deck_size]]

    # A character with an inalienable card (power id in -5..-1) deals one fewer from the pile.
    has_inalienable = -6 < player_character.power.id < 0
    player = _deal(
        draw_pile,
        count=settings.starting_hand_player - int(has_inalienable),
        points=settings.starting_points_player,
        character=deepcopy(player_character),
    )
    if has_inalienable:
        player.inalienable_hand.append(deepcopy(catalog.card(abs(player_character.power.id))))

    bot_character = rng.choice(catalog.opponents(hard=hard_opponents))  # RNG call 2
    bot = _deal(
        draw_pile,
        count=settings.starting_hand_bot,
        points=settings.starting_points_bot,
        character=deepcopy(bot_character),
    )

    return XiaolinState(catalog=catalog, player=player, bot=bot, card_deck=draw_pile)


def _deal(draw_pile: list[Card], *, count: int, points: int, character: Character) -> Player:
    """Pop ``count`` cards off the top into a new player's hand (deck stays empty at start)."""
    hand = [draw_pile.pop(0) for _ in range(count)]
    return Player(character=character, hand=hand, points=points)
