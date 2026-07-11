"""In-duel card power resolution — how a played card enters the scoring queues.

A played card never enters the queue as itself. It enters as an inert *stand-in*: a copy wearing a
neutral power, so nothing downstream can mistake it for a live power or fire it twice. Which rule
applies is looked up once, by :func:`~.powers.mechanic_of`:

- :attr:`~.powers.Mechanic.BOOST` — lends no stats; amplifies the card played after it.
- :attr:`~.powers.Mechanic.MORPH` — every stat becomes 1; the caster picks its element.
- :attr:`~.powers.Mechanic.INTANGIBLE` — voids the elemental bonus for both duelists. A condition of
  the *showdown*, not of one round, so this reports it and the stage machine holds the flag.
- anything else — the printed stats.

Orthogonal to all of that: a **negative Wu** (any card whose lowest stat is below zero) curses the
opponent. A mirror lands on their queue and the caster's copy is spent. That is a property of the
card's stats, not of its power, so it is checked separately.

Pure: no rendering, no I/O. The Morpher's element is resolved by the caller and passed in (a human's
choice, or the background for the bot).
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from ..models import Card, Power
from .cards import index_of
from .powers import Mechanic, mechanic_of

if TYPE_CHECKING:  # annotation only — avoids a runtime cycle with the stage machine
    from ..duel import Round, Side

# A played card joins the queue wearing this, so `_booster_at_head` never mistakes a stand-in for a
# live booster and no power re-triggers.
_NEUTRAL_POWER = Power(id=0, name="", trigger="none", effect=0, description="")

def resolve_played_power(round_: "Round", card: Card, *, is_player: bool, element: str) -> bool:
    """Resolve ``card`` into this round's scoring queues; return whether it voided the elemental bonus.

    The bonus is a condition of the whole *showdown*, not of one round, so the caller owns that flag
    — a Serpent's Tail played in round one leaves the ground intangible for the rest of the match.
    """
    mine, theirs = round_.sides(is_player)
    mechanic = mechanic_of(card.power)
    played = _stand_in(card)
    cursed = _apply_mechanic(mechanic, card, played, theirs, element)

    booster = _booster_at_head(mine.queue)
    if booster is not None:
        _apply_booster(booster, played, theirs, cursed=cursed)

    if cursed:
        played.stats = {stat: 0 for stat in card.stats}  # spent on the opponent's side

    mine.queue.append(played)
    return mechanic is Mechanic.INTANGIBLE


def _curse(victim: "Side", mirror: Card) -> None:
    """Land ``mirror`` on the opponent. It scores against them, and the board credits its caster."""
    victim.queue.append(_inert(mirror))
    victim.suffered.append(mirror)


def _amplify(victim: "Side", mirror: Card) -> None:
    """A booster's share of the curse it just doubled.

    Slotted *left* of that curse, the way a booster precedes the card it boosts everywhere else.
    Order never reaches scoring — it is a sum — so this is purely how the board must read.
    """
    cursed = victim.suffered[-1]
    victim.queue.insert(index_of(victim.queue, cursed), _inert(mirror))
    victim.suffered.insert(index_of(victim.suffered, cursed), mirror)
    victim.amplifiers.append(mirror)


def _inert(mirror: Card) -> Card:
    """Strip a mirror of the power that could fire again on the side it lands on.

    Otherwise a mirrored booster at the head of the victim's queue reads as *their* booster and
    amplifies the card they play next. The **element** stays: it is what the Wu is, and a colour that
    changed when a card crossed the table would be a lie. It earns no bonus on the side it lands on
    because it is not in that duelist's ``earns_bonus`` set — see :func:`~.scoring.count_end_stats`.
    """
    mirror.power = _NEUTRAL_POWER
    return mirror


def _apply_mechanic(
    mechanic: Mechanic, card: Card, played: Card, opponent: "Side", element: str
) -> bool:
    """Set the stand-in's stats for the card's own rule; return whether it cursed the opponent."""
    if mechanic is Mechanic.BOOST:
        played.stats = {stat: 0 for stat in card.stats}
        return False
    if mechanic is Mechanic.MORPH:
        played.stats = {stat: 1 for stat in card.stats}
        played.element = element
        return False
    if _is_negative(card):
        _curse(opponent, deepcopy(played))
        return True
    return False


def _booster_at_head(own_queue: list[Card]) -> Card | None:
    """The booster played this round, if any. It sits first, still wearing its real power."""
    if own_queue and mechanic_of(own_queue[0].power) is Mechanic.BOOST:
        return own_queue[0]
    return None


def _apply_booster(booster: Card, played: Card, opponent: "Side", *, cursed: bool) -> None:
    """The booster takes on 1 per stat the played card contributes — or −1, mirrored onto the
    opponent, when the played card was a curse, which also spends the booster."""
    if cursed:
        opponent_booster = deepcopy(booster)
        opponent_booster.stats = {stat: -1 if played.stats[stat] else 0 for stat in played.stats}
        _amplify(opponent, opponent_booster)
        booster.stats = {stat: 0 for stat in booster.stats}
    else:
        booster.stats = {stat: 1 if played.stats[stat] else 0 for stat in played.stats}


def _stand_in(card: Card) -> Card:
    """A scratch copy of ``card`` wearing a neutral power — safe for the duel to mutate."""
    return Card(
        id=card.id,
        name=card.name,
        stats=dict(card.stats),
        power=_NEUTRAL_POWER,
        element=card.element,
        type=card.type,
        points=card.points,
    )


def _is_negative(card: Card) -> bool:
    """Does the card curse the opponent? True when any printed stat is below zero.

    ``None`` stats are absent, not zero: a null-stat Wu is non-combat and never reads as negative.
    """
    values = [value for value in card.stats.values() if value is not None]
    return bool(values) and min(values) < 0
