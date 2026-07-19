"""Scoring math — initiative before a showdown, end values within one. Pure, no I/O."""

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence

from ..constants import OPPOSITES
from ..models import Card, Mechanic, Player
from .cards import is_one_of


def initiative(player: Player, bot: Player) -> tuple[int, int]:
    """Each side's initiative — own positive bonuses plus the opponent's negatives.

    A duelist keeps their own positive initiative and inherits the opponent's negatives,
    summed over the distinct values.
    """
    player_side = [v for v in set(player.initiative) if v > 0] + [v for v in set(bot.initiative) if v < 0]
    bot_side = [v for v in set(bot.initiative) if v > 0] + [v for v in set(player.initiative) if v < 0]
    return sum(player_side), sum(bot_side)


def _first_per_value(hand: Sequence[Card], wanted: Callable[[int], bool]) -> list[Card]:
    """One card per *distinct* bonus — a second ``+1`` adds nothing, a ``+2`` does."""
    seen: set[int] = set()
    picked = []
    for card in hand:
        bonus = card.power.initiative_bonus
        if wanted(bonus) and bonus not in seen:
            seen.add(bonus)
            picked.append(card)
    return picked


def initiative_sources(player: Player, bot: Player) -> tuple[list[Card], list[Card]]:
    """The cards actually behind each side's :func:`initiative` — its own buffs, and the
    opponent's debuffs, which land on it.

    One card per distinct bonus, mirroring the ``set(...)`` in :func:`initiative`, so the listed
    cards' bonuses always sum to the number shown. Any bonus magnitude works: ``+1`` and ``+2``
    both apply, a second ``+1`` does not.
    """
    return (
        _first_per_value(player.hand, lambda b: b > 0) + _first_per_value(bot.hand, lambda b: b < 0),
        _first_per_value(bot.hand, lambda b: b > 0) + _first_per_value(player.hand, lambda b: b < 0),
    )


def element_score(element: str, background: str) -> int:
    """+1 for a card whose element matches the background, −1 against it, else 0."""
    if background == "metal":
        return 1 if element == "metal" else -1
    if element == background:
        return 1
    if element == OPPOSITES[background] or element == "metal":
        return -1
    return 0


def contributing(cards: Iterable[Card]) -> list[Card]:
    """The cards still pulling their weight — the ones that move a stat.

    Drops the silent: a curse spends the caster's copy to zero, a booster that amplified nothing
    lends nothing, and blank deck filler never did. A ``None`` stat is *unresolved*, not zero: a
    booster at the power stage has no stats of its own yet, and stays.
    """
    return [card for card in cards if any(value is None or value for value in card.stats.values())]


def count_end_stats(
    stat: str,
    elemental_bonus: int,
    target_queue: Sequence[Card],
    character_stats: Mapping[str, int],
    background: str,
    *,
    absolute: bool = True,
    earns_bonus: Sequence[Card] | None = None,
    suffers_bonus: Sequence[Card] = (),
    element_as: str | None = None,
    ward: Collection[str] = (),
    shielded: bool = False,
) -> int:
    """A duelist's end value for one stat: base + queued card stats + elemental bonus.

    ``None`` card stats count as 0; with ``absolute=False`` negatives count as 0 too.

    The background reads two sets of cards on this side of the table, in opposite directions:

    - ``earns_bonus`` — the Wu this duelist played, that still contribute. A resonant one is worth
      more, an opposed one less. Default: every card in the queue.
    - ``suffers_bonus`` — the *curse mirrors* their opponent landed here. The same ±1, **negated**:
      a curse cast in its own element bites deeper, one the background turns against lands softer.
      The card is harming this duelist, so what helps it hurts them.

    Whether the bonus applies at all is the caller's business — a played "Serpent's Tail" voids it
    for both duelists, and that lives on the ``DuelState``.
    """
    bonus_cards = target_queue if earns_bonus is None else earns_bonus
    stat_values: list[int] = []
    for card in target_queue:
        value = card.stats[stat]
        # A stat shield (Mikado Arms and kin): a curse's debuff on the shielded stat counts nothing.
        if shielded and value and value < 0 and is_one_of(card, suffers_bonus):
            value = 0
        if absolute:
            stat_values.append(value or 0)
        else:
            stat_values.append(value if value and value > 0 else 0)

    element_total = 0
    if elemental_bonus:
        # ``element_as`` (a Kuzusu Atom / Eye of Dashi) overrides what this side's own Wu count as; the
        # curses landed on it keep the element they were cast in. A ``ward`` (Monkey Staff and kin)
        # clamps a warded-element Wu's NEGATIVE score to zero — drag ignored, lift kept.
        for card in bonus_cards:
            score = element_score(element_as or card.element, background)
            if (element_as or card.element) in ward and score < 0:
                score = 0
            if card.power.mechanic is Mechanic.DOUBLE_ELEMENT:  # Blade of the Nebula — its bonus counts double
                score *= 2
            element_total += score
        element_total -= sum(element_score(card.element, background) for card in suffers_bonus)
    return character_stats[stat] + sum(stat_values) + elemental_bonus * element_total
