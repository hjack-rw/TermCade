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

from .models import Character
from .state import XiaolinState
from .turn import bank_value


@dataclass(frozen=True)
class Outcome:
    player_points: int
    bot_points: int
    winner: Character | None  # None on a tie


def final_score(state: XiaolinState, rng: Rng) -> Outcome:
    player_points, bot_points = state.player.points, state.bot.points

    if not state.card_deck:  # the pile ran dry — leftover hand cards count toward the score
        # The hand only. A dragon Wu is inalienable — it can never be staked, lost or banked, and a
        # Wu that was never yours to spend has no business paying out at the end.
        #
        # A gamble Wu left in hand is rolled here like any other deposit: holding it to the last is
        # the same bet as banking it, made blind. It is a gamble to even keep it.
        player_points = max(0, player_points + sum(bank_value(c, rng) for c in state.player.hand))
        bot_points = max(0, bot_points + sum(bank_value(c, rng) for c in state.bot.hand))

    if player_points == bot_points:
        winner: Character | None = None
    else:
        winner = state.player.character if player_points > bot_points else state.bot.character
    return Outcome(player_points=player_points, bot_points=bot_points, winner=winner)
