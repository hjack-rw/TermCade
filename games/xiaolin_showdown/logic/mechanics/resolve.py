"""In-duel card power resolution — how a played card enters the scoring queues.

A played card never enters the queue as itself. It enters as an inert *stand-in*: a copy wearing a
neutral power, so nothing downstream can mistake it for a live power or fire it twice. Which rule
applies is looked up once, by :func:`~.powers.mechanic_of`:

- :attr:`~.powers.Mechanic.BOOST` — lends no stats; amplifies the card played after it.
- :attr:`~.powers.Mechanic.MORPH` — takes a fixed shape, low on the contested stat; the caster picks
  its element.
- :attr:`~.powers.Mechanic.BUFF` / :attr:`~.powers.Mechanic.MISFORTUNE` — prints no stats; the caster
  names one, and it takes the whole value, for them or against their opponent.
- :attr:`~.powers.Mechanic.NULLIFY_ELEMENT` — voids the elemental bonus for both duelists. A condition of
  the *showdown*, not of one round, so this reports it and the stage machine holds the flag.
- anything else — the printed stats.

Orthogonal to all of that: a **pure-debuff Wu** (every printed stat non-positive, at least one below
zero) curses the opponent. A mirror lands on their queue and the caster's copy is spent. A Wu with any
positive stat is NOT a curse — it is fielded on the caster's own side, positives buffing them and
negatives costing them, so a mixed ``-1/3/1`` never hands the opponent its +3. That is a property of
the card's stats, not of its power, so it is checked separately (see :func:`_is_negative`).

Pure: no rendering, no I/O. The Morpher's element is resolved by the caller and passed in (a human's
choice, or the background for the bot).
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from ..models import Card, Mechanic, Power
from .cards import index_of
from .powers import (
    ANIMATE_FIELD_STAT,
    ANIMATE_STAT,
    MORPH_ASIDE,
    MORPH_BOOST,
    MORPH_CONTESTED,
    NAMED_STAT_VALUE,
    mechanic_of,
)

if TYPE_CHECKING:
    from ..battle import Round, Side

# A played card joins the queue wearing this, so `_booster_at_head` never mistakes a stand-in for a
# live booster and no power re-triggers.
_NEUTRAL_POWER = Power(id=0, name="", mechanic=Mechanic.FILLER, description="")

def resolve_played_power(
    round_: "Round", card: Card, *, is_player: bool, element: str, stat: str | None = None,
    display_name: str | None = None,
) -> str | None:
    """Resolve ``card`` into this round's scoring queues; return the elemental flag it raised, if any.

    ``"cancel"`` (a Serpent's Tail — nothing resonates) or ``"reverse"`` (a Celestial Dial — resonance
    and opposition swap), or ``None``. The flag is a condition of the whole *showdown*, not of one
    round, so the caller owns it: a Serpent's Tail played in round one leaves the ground intangible for
    the rest of the match.

    ``element`` and ``stat`` are the two things a Wu can ask of whoever plays it: the Morpher's
    element, and the stat the Orb or the Curse pours itself into. Both are resolved by the caller —
    a human at a modal, or the bot — because this module is pure and cannot ask anyone anything.
    """
    mine, theirs = round_.sides(is_player)
    mechanic = mechanic_of(card.power)
    played = stand_in(card, display_name)
    cursed = _apply_mechanic(
        mechanic, card, played, mine, theirs, element, stat, contested=round_.stat
    )

    booster = _booster_at_head(mine.queue)
    if booster is not None:
        _apply_booster(booster, played, theirs, cursed=cursed)
        if cursed:
            mine.spent.append(booster)  # its share of the curse landed opposite, like the curse itself

    if cursed:
        played.stats = {stat: 0 for stat in card.stats}  # spent on the opponent's side
        mine.spent.append(played)

    mine.queue.append(played)
    if mechanic is Mechanic.NULLIFY_ELEMENT:
        return "cancel"
    if mechanic is Mechanic.REVERSE_ELEMENT:
        return "reverse"
    if mechanic is Mechanic.SET_ARENA:  # Monsoon Sandals — the arena becomes the chosen element
        return f"background:{element}"
    if mechanic is Mechanic.SEIZE_GROUND:  # Cube of Haniku — its caster takes the challenger's ground
        return "seize:player" if is_player else "seize:bot"
    if mechanic is Mechanic.HACK:  # Denshi Bunny — the caller checks what it's facing and acts
        return "hack:player" if is_player else "hack:bot"
    if mechanic is Mechanic.STEAL:  # Sands of Time — the caller owns both hands, this module does not
        return "steal:player" if is_player else "steal:bot"
    if mechanic is Mechanic.CONDUCT:  # Shard of Lightning — the count is read at scoring time, live
        return "conduct:player" if is_player else "conduct:bot"
    return None


def as_boost(card: Card, element: str, contested: str | None = None) -> Card:
    """A boost card's queue form — what actually rides ahead of the Wu it lifts.

    Every boost enters as a copy of itself, save the Morpher: spent as a boost it lends
    ``MORPH_BOOST`` in each stat EXCEPT the ``contested`` one, where it prints 0 — in tune (and it
    chooses its tune) the elemental bonus stands that stat up, so the boost NETS 1/1/1: the same
    law every Wu is priced by, never 1/1/1 *plus* the lift. It also puts the Morpher on the hook:
    reverse or cancel the bonus and the contested column stays down. The ``element`` is the one its
    caster names (the background, for the bot). Used by both the duel (on commit) and the bot
    (weighing a boost), so the two can never price it differently.
    """
    queued = deepcopy(card)
    if mechanic_of(card.power) is Mechanic.MORPH:
        queued.stats = {name: 0 if name == contested else MORPH_BOOST for name in queued.stats}
        queued.element = element
    elif mechanic_of(card.power) is Mechanic.ANIMATE:
        # The Heart of Jong comes alive: a flat ANIMATE_STAT form in the arena's own element (the
        # caller passes the background — the Heart never chooses). Its board name is set by the duel,
        # which owns the element→form list. Fielded as a plain Wu instead, it never reaches here.
        queued.stats = {name: ANIMATE_STAT for name in queued.stats}
        queued.element = element
    return queued


def _curse(victim: "Side", mirror: Card) -> None:
    """Land ``mirror`` on the opponent. It scores against them, and the board credits its caster."""
    victim.queue.append(_inert(mirror))
    victim.suffered.append(mirror)


def curse_from_boost(victim: "Side", mirror: Card) -> None:
    """Land Jack-Bot's boost-slot curse on the opponent — his construct, never his own reach.

    A played card's curse always lands on an untouched queue; a boost's does not — the victim's OWN
    boost may have committed to this very queue moments earlier this same cycle, sitting at its tail
    as a live ``Mechanic.BOOST`` amplifier waiting for the card they are about to field.
    ``_booster_at_head`` reads exactly that slot, so a plain append would bury it under the mirror and
    silently swallow it. Insert ahead of a live boost instead of appending after it — same idea as
    ``_amplify``, a different reason to reach for it.

    Registered into ``jack_bot`` too, alongside ``suffered`` — a mirror is inert, its power stripped,
    so that identity list is the only way the board can still tell this apart from any other curse
    landing the same cycle and join it "&", the way it joins a doubled amplifier's share "+".
    """
    inert = _inert(mirror)
    booster = _booster_at_head(victim.queue)
    if booster is not None:
        victim.queue.insert(index_of(victim.queue, booster), inert)
    else:
        victim.queue.append(inert)
    victim.suffered.append(mirror)
    victim.jack_bot.append(mirror)


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


def _set_element_as(side: "Side", element: str) -> None:
    """One Wu decrees what a side's Wu count as, for the background bonus. Two decrees that disagree
    (a Set-Element and a Cleanse both landing here) cancel: the side keeps its Wu's own elements, and
    the clash is flagged so the story can say why. Last-writer-wins would let play order decide it."""
    if side.element_as is not None and side.element_as != element:
        side.element_as = None
        side.element_cancelled = True
    else:
        side.element_as = element


def _apply_mechanic(
    mechanic: Mechanic,
    card: Card,
    played: Card,
    caster: "Side",
    opponent: "Side",
    element: str,
    stat: str | None,
    contested: str | None = None,
) -> bool:
    """Set the stand-in's stats for the card's own rule; return whether it cursed the opponent."""
    if mechanic in _NEGATIONS:
        _negate(mechanic, caster, opponent)
        return False
    if mechanic is Mechanic.CLEANSE:  # Kuzusu Atom — the opponent's Wu count as metal
        _set_element_as(opponent, "metal")
        return False
    if mechanic is Mechanic.SET_ELEMENT:  # Eye of Dashi — the caster's Wu count as their chosen element
        _set_element_as(caster, element)
        return False
    if mechanic is Mechanic.WARD:  # Monkey Staff and kin — the caster's Wu of ITS element ignore drags
        caster.ward.add(card.element)  # a set: two wards of different elements both hold
        return False
    if mechanic is Mechanic.STAT_SHIELD:  # Mikado Arms and kin — immune to curses on the stat it boosts
        caster.shielded.add(max(card.stats, key=lambda s: card.stats[s] or 0))
        return False
    if mechanic is Mechanic.BOOST:
        played.stats = {name: 0 for name in card.stats}
        return False
    if mechanic is Mechanic.MORPH:
        played.stats = _morphed(card, contested)
        played.element = element
        return False
    if mechanic is Mechanic.ANIMATE:
        # Heart of Jong fielded as a plain Wu: a middling ANIMATE_FIELD_STAT body, keeping its own name
        # and its resting metal. The stronger arena-element summon (ANIMATE_STAT) belongs to the boost
        # slot (see `as_boost`); fielded, it is just itself, come to life.
        played.stats = {name: ANIMATE_FIELD_STAT for name in card.stats}
        return False
    if mechanic in (Mechanic.BUFF, Mechanic.MISFORTUNE):
        played.stats = _poured(card, mechanic, _named(card, stat))
        # A Misfortune Wu prints no stats, so `_is_negative` cannot see what it is: the wound only
        # exists once its caster has named a stat. It curses from here instead.
        if mechanic is Mechanic.MISFORTUNE:
            _curse(opponent, deepcopy(played))
            return True
        return False
    if _is_negative(card):
        _curse(opponent, deepcopy(played))
        return True
    return False


# The three Wu that take a line off the board for one battle. Each names the side it lands on and
# the flag it raises there — the scorer reads the flags, so a Wu played after the negator is negated
# with the rest. The negators print 0/0/0: the rule is the whole of what they are.
_NEGATIONS: dict[Mechanic, tuple[bool, str]] = {
    # mechanic: (does it land on the opponent?, which line it takes)
    Mechanic.NULLIFY_STATS: (True, "base_negated"),  # Sphere of Jianyu — the duelist themselves
    Mechanic.NULLIFY_WU: (True, "offence_negated"),  # Emperor Scorpion — every Wu they played
    Mechanic.NULLIFY_CURSE: (False, "defence_negated"),  # Reversing Mirror — every curse laid on you
    Mechanic.NULLIFY_BOOST: (True, "boost_negated"),  # Star Hanabi — the opponent's boost's stats
}


def _negate(mechanic: Mechanic, caster: "Side", opponent: "Side") -> None:
    """Take a line off the board for the rest of this battle."""
    lands_opposite, line = _NEGATIONS[mechanic]
    setattr(opponent if lands_opposite else caster, line, True)


def _named(card: Card, stat: str | None) -> str:
    """The stat its caster named. Such a Wu, never asked, would pour into nothing."""
    if stat is None:
        raise ValueError(f"{card.name!r} was played without naming a stat — it would do nothing")
    return stat


def _poured(card: Card, mechanic: Mechanic, stat: str) -> dict[str, int | None]:
    """Everything into the one named stat, nothing anywhere else."""
    value = NAMED_STAT_VALUE if mechanic is Mechanic.BUFF else -NAMED_STAT_VALUE
    return {name: (value if name == stat else 0) for name in card.stats}


def _morphed(card: Card, contested: str | None) -> dict[str, int | None]:
    """What the Morpher becomes: ``MORPH_ASIDE`` everywhere, but only ``MORPH_CONTESTED`` on the
    stat the battle is fought over.

    The dip is not a penalty — it is where the Morpher's *own* power pays it back. It is the one Wu
    that chooses the element it counts as, so it can always match the arena, and the elemental bonus
    lands on the contested stat alone. Played into a coloured arena it stands the low stat back up.
    Scoring weighs the contested stat double, so the shape matters more than the sum.
    """
    return {
        name: (MORPH_CONTESTED if name == contested else MORPH_ASIDE) for name in card.stats
    }


def _booster_at_head(own_queue: list[Card]) -> Card | None:
    """The boost waiting on the Wu about to land, if any — the *last* thing queued, not the first.

    A battle can field up to three Wu, each with its own boost, laid down as boost-then-Wu pairs. So
    the live boost is always the tail: everything before it is a spent stand-in wearing the neutral
    power. Reading the head instead would fire the first boost of the battle over and over and leave
    every later one inert.
    """
    if own_queue and mechanic_of(own_queue[-1].power) is Mechanic.BOOST:
        return own_queue[-1]
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


def stand_in(card: Card, display_name: str | None = None) -> Card:
    """A scratch copy of ``card`` wearing a neutral power — safe for the duel to mutate.

    ``display_name`` overrides the copy's name on the board: a summon Wu enters the queue as the thing
    it summons (a clone, a horde) rather than as itself. The stats are untouched — flavour only."""
    return Card(
        id=card.id,
        name=display_name or card.name,
        stats=dict(card.stats),
        power=_NEUTRAL_POWER,
        element=card.element,
        type=card.type,
        points=card.points,
    )


def _is_negative(card: Card) -> bool:
    """Does the card curse the opponent? True only for a PURE debuff — every printed stat non-positive
    and at least one below zero. A card with any positive stat is a Wu you field on YOUR side (the
    positives buff you, the negatives cost you); it never lands on the opponent, or its positives would
    buff them. All-negative curses them, all-positive buffs you, mixed is a buff-with-a-drawback.

    ``None`` stats are absent, not zero: a null-stat Wu is non-combat and never reads as negative.
    """
    values = [value for value in card.stats.values() if value is not None]
    return bool(values) and max(values) <= 0 and min(values) < 0
