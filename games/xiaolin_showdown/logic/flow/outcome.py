"""Final scoring — who won when the run ends.

Given the finished state, work out each side's final points and the winner. When the draw pile is
spent, a duelist's leftover *hand* is cashed into their score; when the run ended on the point limit
instead, the pile still has cards and hands are not counted.

Takes the run's RNG, because a gamble Wu still in hand is rolled here — holding it to the last is
the same bet as banking it, made blind.
"""

from __future__ import annotations

from dataclasses import dataclass

from termcade.core.rng import Rng

from ..schema.models import Character
from ..schema.state import XiaolinState
from . import bot
from .turn import bank_value


@dataclass(frozen=True)
class Outcome:
    player_points: int
    bot_points: int
    winner: Character | None  # None on a tie


def final_score(state: XiaolinState, rng: Rng) -> Outcome:
    player_points, bot_points = state.player.points, state.bot.points

    if not state.card_deck:  # the pile ran dry — leftover hand cards count toward the score
        # The hand only — a dragon Wu is inalienable and never has business paying out here. A
        # gamble Wu left in hand is rolled like any other deposit.
        player_points = max(0, player_points + sum(bank_value(c, rng) for c in state.player.hand))
        bot_points = max(0, bot_points + sum(bank_value(c, rng) for c in state.bot.hand))

    # Mala Mala Jong: reaching the end still in the form wins outright, whatever the points say (see
    # logic/characters/jong.py). If somehow both wear it, neither claim stands and points decide.
    if bot.is_jong(state.player) and not bot.is_jong(state.bot):
        return Outcome(player_points, bot_points, state.player.character)
    if bot.is_jong(state.bot) and not bot.is_jong(state.player):
        return Outcome(player_points, bot_points, state.bot.character)

    if player_points == bot_points:
        winner: Character | None = None
    else:
        winner = state.player.character if player_points > bot_points else state.bot.character
    return Outcome(player_points=player_points, bot_points=bot_points, winner=winner)
