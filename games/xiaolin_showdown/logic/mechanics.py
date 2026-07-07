"""Pure game calculations (no I/O), ported from the reference ``ENGINE``/``UTILS`` math."""

from __future__ import annotations

from .models import Player


def initiative(player: Player, bot: Player) -> tuple[int, int]:
    """Each side's initiative — own positive bonuses plus the opponent's negatives.

    Ported from ``sum__initiative`` (ENGINE.py:185-189): a duelist keeps their own positive
    initiative and inherits the opponent's negatives, summed over the distinct values.
    """
    player_side = [v for v in set(player.initiative) if v > 0] + [v for v in set(bot.initiative) if v < 0]
    bot_side = [v for v in set(bot.initiative) if v > 0] + [v for v in set(player.initiative) if v < 0]
    return sum(player_side), sum(bot_side)
