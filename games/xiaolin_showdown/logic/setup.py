"""Build a fresh game.

The RNG and the player's chosen character are injected explicitly — not a seeded global RNG,
not an interactive prompt — so a run stays deterministic and testable. The RNG call order is
preserved exactly — shuffle the draw pile, then pick the bot's character — so a given seed
reproduces the identical game. Card pops consume no randomness.
"""

from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass, replace

from termcade.core.rng import Rng

from .catalog import Catalog
from .constants import FIRST_DECK_CARD
from .mechanics.cards import held_as_wudai
from .models import Card, Character, Player
from .settings import XiaolinSettings, deck_size_for, point_limit_for
from .state import XiaolinState
from .turn import duel_value

# Weighted-subset deal (prototype, flag-gated). A run deals a weighted sample of the pool instead of
# the whole thing, so a game stays concise as the pool grows. Sizes are the Wu left in the DRAW PILE
# after the opening hands; the boss stays short (tighter, swingier), the rest run a little longer.
_PILE_SIZE = {"easy": 40, "hard": 40, "boss": 30}

# Deal weight = how likely a Wu is dealt into a run. Points (so the deck can reach the target) and duel
# strength (so the fights stay sharp) both pull it up; the base keeps every Wu reachable. Points lead,
# since meeting the limit is the harder constraint.
@dataclass(frozen=True)
class _DealWeights:
    base: int
    points: int
    duel: int


_BASE_WEIGHTS = _DealWeights(base=1, points=2, duel=1)

# Per-opponent scenario overrides: some opponents are beaten by a different deck than the default deals,
# so their matchup skews the deal. Boss-only in practice — a scenario needs the opponent known before
# the deal, which holds only for a CHOSEN opponent (bosses are picked, never dealt); a randomly dealt
# roster gets the default. Wuya's Witchcraft recycles spent Wu, so game LENGTH feeds her; a point-richer
# deck races her to the target before the grind pays off, lifting her back above Chase (the final wall).
_SCENARIOS: dict[str, _DealWeights] = {
    "Wuya": replace(_BASE_WEIGHTS, points=4),
}


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
    cards = catalog.cards
    # Omitted settings mean "the shipped game": the pool-derived deck and target, which the weighted
    # deal below then supersedes. Deriving them (not the hardcoded field defaults) keeps that true as
    # the pool grows, so a default run is never mistaken for a customised one.
    settings = settings or XiaolinSettings(
        max_deck_size=deck_size_for(cards), point_limit=point_limit_for(cards)
    )

    # The shipped game deals a weighted subset of the pool, so a run stays concise as the pool grows.
    # A player who set their own deck size or win target opts out of it into a custom game (dealt the
    # whole pool at their numbers) — guardrail, not lock, the same stance the mercy rule takes.
    pile = _pile_size(roster)
    if pile > 0 and not _player_set_their_own_deal(settings, cards):
        return _weighted_game(catalog, rng, player_character, settings, roster, opponent, pile)

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


def _weighted_game(
    catalog: Catalog,
    rng: Rng,
    player_character: Character,
    settings: XiaolinSettings,
    roster: str,
    opponent: Character | None,
    pile_size: int,
) -> XiaolinState:
    """A concise run: deal a weighted subset of the pool, sized so length holds as the pool grows.

    ``pile_size`` Wu remain in the draw pile after the opening hands; the win target follows the dealt
    subset (a smaller deck banks a nearer target). RNG call order matches :func:`new_game` — the deal
    consumes randomness (call 1), then the bot is picked (call 2) — so seeds line up across both paths.
    """
    poolable = [deepcopy(catalog.cards[i]) for i in range(FIRST_DECK_CARD, len(catalog.cards))]
    wanted = pile_size + settings.starting_hand_player + settings.starting_hand_bot
    # A scenario needs the opponent known before the deal; that holds only for a CHOSEN opponent, which
    # bosses always are. A randomly dealt roster (opponent is None) has no scenario and takes the default.
    weights = _SCENARIOS.get(opponent.name, _BASE_WEIGHTS) if opponent is not None else _BASE_WEIGHTS
    game_deck = _weighted_sample(poolable, min(wanted, len(poolable)), rng, weights)  # RNG call 1
    dealt = settings.starting_hand_player + settings.starting_hand_bot
    target = point_limit_for(game_deck, dealt=dealt)  # off the whole subset, before dealing thins it

    player = deepcopy(player_character)
    bot = deepcopy(opponent) if opponent is not None else deepcopy(rng.choice(catalog.opponents(roster)))  # RNG call 2

    player_sig = _reserve_signature(game_deck, player)
    bot_sig = _reserve_signature(game_deck, bot)
    player_duelist = _deal(
        game_deck, catalog, player, player_sig,
        count=settings.starting_hand_player, points=settings.starting_points_player,
    )
    bot_duelist = _deal(
        game_deck, catalog, bot, bot_sig,
        count=settings.starting_hand_bot, points=settings.starting_points_bot,
    )

    state = XiaolinState(catalog=catalog, player=player_duelist, bot=bot_duelist, card_deck=game_deck)
    state.point_limit = target
    return state


def _weighted_sample(cards: list[Card], k: int, rng: Rng, deal_weights: _DealWeights) -> list[Card]:
    """Draw ``k`` distinct Wu by weight (cumulative-weight roulette): the heavier a card, the likelier
    it lands, and the earlier. Uses only :meth:`Rng.randint`, so the draw rides the seeded stream and a
    save replays it exactly. With uniform weights this is a plain shuffle-and-take.
    """
    pool = list(cards)
    weights = [_deck_weight(card, deal_weights) for card in pool]
    drawn: list[Card] = []
    for _ in range(min(k, len(pool))):
        roll = rng.randint(1, sum(weights))
        running = 0
        for index, weight in enumerate(weights):
            running += weight
            if roll <= running:
                drawn.append(pool.pop(index))
                weights.pop(index)
                break
    return drawn


def _deck_weight(card: Card, weights: _DealWeights) -> int:
    """A Wu's odds of being dealt into a run: point-rich and duel-strong Wu are likelier, so a dealt
    deck can reach its target and still field sharp fights, while the base keeps every Wu reachable.
    The blend is the matchup's :class:`_DealWeights`; measured play sets them, not a guess.
    """
    return weights.base + weights.points * card.points + weights.duel * duel_value(card)


def _player_set_their_own_deal(settings: XiaolinSettings, cards: list[Card]) -> bool:
    """True when the player set their own deck size or win target, opting into a custom game.

    Those two settings are pool-DERIVED by default (:func:`deck_size_for`, :func:`point_limit_for`); a
    value that differs is a deliberate override, and the weighted deal steps aside to honor it literally
    — the same signal :func:`~.settings.save_note` uses to star a customised save.
    """
    return (
        settings.max_deck_size != deck_size_for(cards)
        or settings.point_limit != point_limit_for(cards)
    )


def _pile_size(roster: str) -> int:
    """How many Wu to leave in the draw pile after the opening hands, or ``0`` for the whole pool.

    The per-roster table (:data:`_PILE_SIZE`) is live by default. ``XS_PILE`` is a measurement override:
    an integer forces that size on every roster (for sweeps), and ``"full"`` (or ``0``) deals the whole
    pool, the pre-weighting baseline the harness compares against.
    """
    override = os.environ.get("XS_PILE")
    if override is None:
        return _PILE_SIZE.get(roster, 0)
    if override == "full":
        return 0
    return int(override)
