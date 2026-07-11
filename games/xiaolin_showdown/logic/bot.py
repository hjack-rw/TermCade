"""The opponent's duel decisions — pure, RNG-injected.

Each function scores the options by ``own stat + card contribution − opponent stat`` and picks
the best, falling back to a random legal choice. ``None`` card stats count as 0, guarding the two
spots where they would otherwise crash a comparison.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from termcade.core.rng import Rng

from .constants import OPPOSITES
from .mechanics.powers import Mechanic, mechanic_of
from .mechanics.scoring import count_end_stats
from .models import Card
from .turn import duel_value


def choose_challenge(
    bot_stats: Mapping[str, int],
    challenges: Sequence[str],
    bot_hand: Sequence[Card],
    opponent_stats: Mapping[str, int],
    rng: Rng,
) -> str:
    """Pick the contested stat where the bot is strongest; else a random legal one."""
    best_stat = max(bot_stats, key=lambda s: bot_stats[s])
    best_value = max(bot_stats.values())
    for card in bot_hand:
        for stat in bot_stats:
            if stat in challenges:
                value = (card.stats[stat] or 0) + bot_stats[stat] - opponent_stats[stat]
                if value > best_value:
                    best_stat, best_value = stat, value
    return best_stat if best_stat in challenges else rng.choice(list(challenges))


def choose_background(
    bot_stats: Mapping[str, int],
    backgrounds: Sequence[str],
    hands: tuple[Sequence[Card], Sequence[Card]],
    opponent_stats: Mapping[str, int],
    rng: Rng,
) -> str:
    """Pick the element that best boosts the bot; else counter the player's dominant element."""
    bot_hand, player_hand = hands
    best_value = max(bot_stats.values())
    element: str | None = None
    for card in bot_hand:
        for stat in bot_stats:
            if card.element in backgrounds:
                value = (card.stats[stat] or 0) + bot_stats[stat] - opponent_stats[stat]
                if value > best_value:
                    best_value, element = value, card.element
    if element is not None:
        return element
    return _counter_element(player_hand, backgrounds, rng)


def _counter_element(
    player_hand: Sequence[Card], backgrounds: Sequence[str], rng: Rng
) -> str:
    """No boost available — counter the player: against a wudai lead card prefer metal or its
    opposite, otherwise counter the player's most common element."""
    if player_hand[0].type == "wudai":
        counters = ["metal", OPPOSITES.get(player_hand[0].element, "metal")]
    else:
        dominant = _most_common_element(player_hand)
        if dominant == "metal":
            non_metal = [b for b in backgrounds if b != "metal"]
            return rng.choice(non_metal) if non_metal else rng.choice(list(backgrounds))
        counters = ["metal", OPPOSITES[dominant]]

    for background in counters:
        if background in backgrounds:
            return background
    return rng.choice(list(backgrounds))


def choose_card(
    bot_stats: Mapping[str, int],
    challenge: str,
    background: str,
    bot_hand: Sequence[Card],
    opponent_stats: Mapping[str, int],
    rng: Rng,
) -> Card:
    """Play the card whose resolved value most beats the opponent on some stat; else random."""
    best: Card | None = None
    best_value = 0
    for card in bot_hand:
        mechanic = mechanic_of(card.power)
        for stat in bot_stats:
            elemental_bonus = 1 if stat == challenge else 0
            if mechanic is Mechanic.INTANGIBLE:
                elemental_bonus = 0  # playing it voids the bonus it would otherwise earn
            if mechanic is Mechanic.MORPH:
                add = 2 if stat == challenge else 1  # "moby morpher" stand-in
            else:
                value = card.stats[stat]
                add = abs(value) if value is not None and value < 0 else 0
            score = (
                count_end_stats(stat, elemental_bonus, [card], bot_stats, background, absolute=False)
                - opponent_stats[stat]
                + add
            )
            if score > best_value:
                best_value, best = score, card
    return best if best is not None else rng.choice(list(bot_hand))


def _most_common_element(hand: Sequence[Card]) -> str:
    counts: dict[str, int] = {}
    for card in hand:
        counts[card.element] = counts.get(card.element, 0) + 1
    return max(counts, key=lambda e: counts[e])


def choose_wager(options: Sequence[int], own_hand: Sequence[Card], opponent_hand: Sequence[Card]) -> int:
    """How many Wu to stake — the answer to a challenge you did not call.

    Both hands are face up, so this is a read, not a gamble. Raise when your bench is deeper: a
    best-of-3 drags out a duelist's *third* Wu, and a hand that is one monster and two trinkets
    loses a long match it would have won a short one.

    Compared rung by rung, best against best, because that is the order they will be fielded in.
    """
    if not options:
        return 1
    mine = sorted((duel_value(card) for card in own_hand), reverse=True)
    theirs = sorted((duel_value(card) for card in opponent_hand), reverse=True)

    best = min(options)
    for wager in options:
        # every rung this wager reaches: am I ahead down there?
        edge = sum(
            (mine[i] if i < len(mine) else 0) - (theirs[i] if i < len(theirs) else 0)
            for i in range(wager)
        )
        if edge > 0:
            best = wager  # deeper bench — the longer the match, the better it goes
    return best
