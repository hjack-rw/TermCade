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
from .mechanics.cards import held_as_wudai
from .models import Card, Character, Player
from .settings import XiaolinSettings
from .state import XiaolinState


def new_game(
    catalog: Catalog,
    rng: Rng,
    player_character: Character,
    *,
    settings: XiaolinSettings | None = None,
    roster: str = "easy",
    opponent: Character | None = None,
) -> XiaolinState:
    """A fresh temple-menu state: shuffled draw pile, both hands dealt, starting points.
    ``settings`` are the (player-chosen) settings for this run; defaults are used when omitted.
    ``roster`` picks the opponent tier — ``'easy'``, ``'hard'`` or ``'boss'`` — and ``opponent``
    overrides the roster's random pick with a CHOSEN one: a boss is picked, never dealt.
    """
    settings = settings or XiaolinSettings()
    cards = catalog.cards

    # Draw pile = the pool (ids FIRST_DECK_CARD..N), padded with blanks (card 0) to full size.
    card_order = list(range(FIRST_DECK_CARD, len(cards)))
    card_order += [0] * (settings.max_deck_size - len(card_order))
    rng.shuffle(card_order)  # RNG call 1 — must precede the bot pick

    draw_pile = [deepcopy(cards[i]) for i in card_order[: settings.max_deck_size]]

    # Pick the opponent right after the shuffle (RNG call 2). Dealing consumes no RNG, so knowing both
    # duelists before any hand is dealt does not disturb the call order — and it must be known, so a
    # boss's signature Wu is pulled from the pool before the player could draw it. A CHOSEN opponent
    # (the boss picker) skips the pick and its RNG call: the choice was the player's, not the stream's.
    player = deepcopy(player_character)
    bot = deepcopy(opponent) if opponent is not None else deepcopy(rng.choice(catalog.opponents(roster)))  # RNG call 2

    # Reserve each duelist's signature Wu out of the pile *before* either hand is dealt.
    player_sig = _reserve_signature(draw_pile, player)
    bot_sig = _reserve_signature(draw_pile, bot)

    player_duelist = _deal(
        draw_pile, catalog, player, player_sig,
        count=settings.starting_hand_player, points=settings.starting_points_player,
    )
    bot_duelist = _deal(
        draw_pile, catalog, bot, bot_sig,
        count=settings.starting_hand_bot, points=settings.starting_points_bot,
    )

    return XiaolinState(catalog=catalog, player=player_duelist, bot=bot_duelist, card_deck=draw_pile)


def _reserve_signature(draw_pile: list[Card], character: Character) -> int | None:
    """A signature power (id −5..−1) ties a character to the Wu ``abs(id)``, which is theirs by right.

    Pull that Wu out of the pool so it can never be drawn by anyone: ids 1-4 (the playable signatures)
    never ride in the pool, but id 5 (Moby Morpher, Hannibal's) does by default. Returns the Wu's id,
    or ``None`` when the character carries no signature. Wuya's Witchcraft sits at −6 ON PURPOSE:
    a character power that grants no Wu lives outside the signature range.
    """
    if not -6 < character.power.id < 0:
        return None
    signature = abs(character.power.id)
    for index, card in enumerate(draw_pile):
        if card.id == signature:
            del draw_pile[index]
            break
    return signature


def _deal(
    draw_pile: list[Card],
    catalog: Catalog,
    character: Character,
    signature: int | None,
    *,
    count: int,
    points: int,
) -> Player:
    """Deal an opening hand, granting the character's signature Wu inalienably if it carries one.

    The signature Wu is granted to the inalienable slot — always in hand, never staked, lost or banked
    — and costs one card off the dealt hand. The deck stays empty at start.
    """
    hand = [draw_pile.pop(0) for _ in range(count - (1 if signature is not None else 0))]
    player = Player(character=character, hand=hand, points=points)
    if signature is not None:
        player.inalienable_hand.append(held_as_wudai(deepcopy(catalog.card(signature))))
    return player
