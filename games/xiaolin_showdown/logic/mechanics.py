"""Pure game calculations (no I/O), ported from the reference ``ENGINE``/``UTILS`` math."""

from collections.abc import Mapping, Sequence

from .elements import OPPOSITES
from .models import Card, Player


def initiative(player: Player, bot: Player) -> tuple[int, int]:
    """Each side's initiative — own positive bonuses plus the opponent's negatives.

    Ported from ``sum__initiative`` (ENGINE.py:185-189): a duelist keeps their own positive
    initiative and inherits the opponent's negatives, summed over the distinct values.
    """
    player_side = [v for v in set(player.initiative) if v > 0] + [v for v in set(bot.initiative) if v < 0]
    bot_side = [v for v in set(bot.initiative) if v > 0] + [v for v in set(player.initiative) if v < 0]
    return sum(player_side), sum(bot_side)


def _element_score(element: str, background: str) -> int:
    """+1 for a card whose element matches the background, −1 against it, else 0."""
    if background == "metal":
        return 1 if element == "metal" else -1
    if element == background:
        return 1
    if element == OPPOSITES[background] or element == "metal":
        return -1
    return 0


def count_end_stats(
    stat: str,
    elemental_bonus: int,
    target_queue: Sequence[Card],
    character_stats: Mapping[str, int],
    background: str,
    *,
    absolute: bool = True,
) -> int:
    """A duelist's end value for one stat: base + queued card stats + elemental bonus.

    Ported from ``count__end_stats`` (UTILS.py:290-312). ``None`` card stats count as 0; with
    ``absolute=False`` negatives count as 0 too. The "Serpent's Tail" play card (effect −1)
    cancels the elemental bonus.
    """
    if any(c.power.effect == -1 and c.power.trigger == "play" for c in target_queue):
        elemental_bonus = 0

    stat_values: list[int] = []
    element_values: list[int] = []
    for card in target_queue:
        value = card.stats[stat]
        if absolute:
            stat_values.append(value or 0)
        else:
            stat_values.append(value if value and value > 0 else 0)
        if elemental_bonus:
            element_values.append(_element_score(card.element, background))

    return character_stats[stat] + sum(stat_values) + elemental_bonus * sum(element_values)
