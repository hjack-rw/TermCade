"""Final scoring — who won when the run ends.

Pure: given the finished state, work out each side's final points and the winner. When the draw
pile is spent, a duelist's leftover hand cards are cashed into their score; when the run ended on
the point limit instead, the pile still has cards and hands are not counted.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Character
from .state import XiaolinState


@dataclass(frozen=True)
class Outcome:
    player_points: int
    bot_points: int
    winner: Character | None  # None on a tie


def final_score(state: XiaolinState) -> Outcome:
    player_points, bot_points = state.player.points, state.bot.points

    if not state.card_deck:  # the pile ran dry — leftover hand cards count toward the score
        player_points += sum(card.points for card in state.player.whole_hand)
        bot_points += sum(card.points for card in state.bot.whole_hand)

    if player_points == bot_points:
        winner: Character | None = None
    else:
        winner = state.player.character if player_points > bot_points else state.bot.character
    return Outcome(player_points=player_points, bot_points=bot_points, winner=winner)
