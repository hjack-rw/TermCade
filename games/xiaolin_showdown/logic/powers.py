"""In-duel card power resolution — the port of ``ENGINE.powers`` (the ``is_duel`` half).

When a card is played in a showdown it does not enter the scoring queue as itself: it enters
as an inert *stand-in* (a copy wearing a neutral power) so the queue is never re-scanned for
its power. Three things happen here, faithfully mirroring the reference:

- a **boost** card (``boost``/+1) lends no stats of its own — it amplifies the card played after it;
- a **"Moby Morpher"** (``play``/+1) turns all stats to 1 and lets the caster choose its element;
- a **negative** card curses the opponent: a mirror of it lands on *their* queue and the caster's
  copy is zeroed.

Pure: no rendering, no I/O. The reference's ``duel_table``/``_info`` side effects are dropped —
that is the screen's job. The Morpher's element is resolved by the caller and passed in as
``element`` (a human's chosen element, or the background for the bot).
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from .models import Card, Power

if TYPE_CHECKING:  # annotation only — avoids a runtime cycle with the stage machine
    from .duel import DuelState

# A played card joins the queue as a stats-carrier with this inert power, so the booster scan
# (``queue[0].power.effect != 0``) never mistakes it for a booster and it never re-triggers.
_NEUTRAL_POWER = Power(id=0, name="", trigger="hand", effect=0, description="")

# The opponent's mirror of a negative card carries no element (it must earn no elemental bonus).
# The reference used ``None``; "" scores identically in ``count_end_stats`` and keeps ``Card.element``
# a plain ``str``.
_NO_ELEMENT = ""

# Which in-duel powers act, keyed by (effect, trigger) — the ``is_duel`` slice of the reference
# switchboard. Everything else resolves as a plain (or negative) card.
_BOOST = 0  # boost/+1: amplifies the card played after it
_MORPH = 1  # play/+1 ("Moby Morpher"): all stats become 1, caster picks the element
_DUEL_CONDITIONS = {(1, "boost"): _BOOST, (1, "play"): _MORPH}


def resolve_played_power(
    duel: DuelState,
    card: Card,
    *,
    is_player: bool,
    element: str,
) -> None:
    """Resolve ``card`` played in the duel into the scoring queues (mutates ``duel`` in place).

    ``element`` is used only by a Morpher (a human's chosen element, or the background for the
    bot); every other card ignores it.
    """
    own_queue = duel.player_queue if is_player else duel.bot_queue
    opponent_queue = duel.bot_queue if is_player else duel.player_queue

    condition = _DUEL_CONDITIONS.get((card.power.effect, card.power.trigger))
    booster, booster_condition = _find_booster(own_queue)

    new_card = _stand_in(card)
    is_negative = _apply_own_power(card, new_card, condition, opponent_queue, element)

    if booster_condition == _BOOST and booster is not None:
        _apply_booster(booster, new_card, opponent_queue, is_negative=is_negative)

    if is_negative:
        new_card.stats = {stat: 0 for stat in card.stats}  # spent on the opponent's side

    own_queue.append(new_card)


def _find_booster(own_queue: list[Card]) -> tuple[Card | None, int | None]:
    """The booster (if any) at the head of the caster's queue, with its in-duel condition.

    A booster played earlier this round (stage 4) sits first, still wearing its real power;
    stand-ins carry the neutral power (effect 0), so this never picks one up by mistake.
    """
    if own_queue and own_queue[0].power.effect != 0:
        booster = own_queue[0]
        return booster, _DUEL_CONDITIONS.get((booster.power.effect, booster.power.trigger))
    return None, None


def _apply_own_power(
    card: Card,
    new_card: Card,
    condition: int | None,
    opponent_queue: list[Card],
    element: str,
) -> bool:
    """Set the stand-in's stats for the card's own power; return whether it was a negative card
    (which also drops a mirror of itself onto the opponent's queue)."""
    if condition == _BOOST:
        new_card.stats = {stat: 0 for stat in card.stats}
    elif condition == _MORPH:
        new_card.stats = {stat: 1 for stat in card.stats}
        new_card.element = element
    elif _min_stat(card) < 0:
        mirror = deepcopy(new_card)
        mirror.element = _NO_ELEMENT
        opponent_queue.append(mirror)
        return True
    return False


def _apply_booster(
    booster: Card, new_card: Card, opponent_queue: list[Card], *, is_negative: bool
) -> None:
    """A queued boost card takes on 1 (or −1, mirrored to the opponent) per stat the played card
    contributes — then is spent (zeroed) on the caster's side when the played card was negative."""
    if is_negative:
        opponent_booster = deepcopy(booster)
        opponent_booster.element = _NO_ELEMENT
        opponent_booster.stats = {s: -1 if new_card.stats[s] else 0 for s in new_card.stats}
        opponent_queue.append(opponent_booster)
        booster.stats = {s: 0 for s in booster.stats}
    else:
        booster.stats = {s: 1 if new_card.stats[s] else 0 for s in new_card.stats}


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


def _min_stat(card: Card) -> int:
    """Lowest real stat, ``None`` treated as absent (0 when the card has no stats at all).

    The reference does ``min(card.stats.values())``, which crashes on XS's None-stat cards;
    ignoring ``None`` also keeps a non-combat card from ever reading as 'negative'.
    """
    values = [v for v in card.stats.values() if v is not None]
    return min(values) if values else 0
