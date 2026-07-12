"""What every Wu power *does*, keyed by ``(trigger, effect)``.

The card DB stores a power as a trigger and a small integer, which says nothing about the rule it
buys. This table names each pair, says when it acts, and states the rule in one line.

It is the single source for two things that used to drift apart: the in-duel dispatch in
:mod:`.resolve`, and the test that every power in the DB is a mechanic somebody implemented — an
unnamed pair is a Wu that quietly does nothing.

The flavour names (``CHRONOKINESIS``, ``INTANGIBLE``, ...) are the powers' printed names, so a
reader can grep one straight back to the card that carries it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from termcade.core.rng import Rng

from ..models import Power


class Mechanic(StrEnum):
    """The rule a ``(trigger, effect)`` pair buys."""

    FILLER = "filler"
    INITIATIVE = "initiative"
    HAND_SIZE = "hand_size"
    HAND_FIZZLE = "hand_fizzle"
    GAMBLE = "gamble"
    CHRONOKINESIS = "chronokinesis"
    DRAGON = "dragon"
    BOOST = "boost"
    PRINTED_STATS = "printed_stats"
    MORPH = "morph"
    INTANGIBLE = "intangible"


class Timing(StrEnum):
    """When the mechanic acts. The value is the heading a player reads."""

    IN_HAND = "While it sits in your hand"
    AT_VAULT = "Spent at the vault"
    IN_DUEL = "Played in a showdown"
    NEVER = "No mechanic"


@dataclass(frozen=True)
class Rule:
    mechanic: Mechanic
    timing: Timing
    text: str


# What a GAMBLE Wu pays when it is banked, inclusive. Nobody is told this: the card shows `?`.
#
# Its DB `points` is never shown to a player either — it is the card's *expected* value, and only two
# things read it. `settings.point_limit_for` sizes the run from the deck's total points, and the bot
# ranks what to bank by them. Both would be lied to by a number the card cannot pay. Here the true
# average is 1.5 against a stored 1, so the bot slightly undervalues the card. That is the whole of
# the discrepancy, and it is deliberate: it is one Wu, in the player's favour, and rounding it away
# beats a DB migration. Widen the spread and the stored value must move with it.
#
# ⚠ THIS IS THE ONLY RANDOMNESS A DUELIST CANNOT SEE COMING, AND IT BELONGS TO EXACTLY ONE WU.
# Everything else in this game is open hands and hard choices — that is the whole pitch, and it only
# reads as a virtue while it stays true. A second card that rolls makes the first one ordinary and
# the promise false. If you are about to give another Wu a random anything: don't.
GAMBLE_SPREAD = (-2, 5)


# Keyed by (trigger, effect) — the order the DB and `Power` use, so a reader never has to flip it.
RULES: dict[tuple[str, int], Rule] = {
    ("none", 0): Rule(Mechanic.FILLER, Timing.NEVER, "Deck filler. Does nothing."),
    ("hand", 0): Rule(
        Mechanic.INITIATIVE,
        Timing.IN_HAND,
        "Adds its initiative bonus while held. Equal bonuses don't stack; different ones do, "
        "and your opponent's negatives land on you.",
    ),
    ("hand", -1): Rule(
        Mechanic.HAND_SIZE, Timing.IN_HAND, "Raises your hand limit by one while held."
    ),
    ("hand", 1): Rule(
        Mechanic.HAND_FIZZLE,
        Timing.AT_VAULT,
        "Can be spent from the vault, but its power fizzles — it is discarded for no points.",
    ),
    ("use", 0): Rule(
        Mechanic.GAMBLE,
        Timing.AT_VAULT,
        f"Nobody knows what it is worth. Deposit it and find out: anywhere from "
        f"{GAMBLE_SPREAD[0]:+d} to {GAMBLE_SPREAD[1]:+d} points.",
    ),
    ("use", 1): Rule(
        Mechanic.CHRONOKINESIS,
        Timing.AT_VAULT,
        "Spend it to draw a Wu from the pile. Depositing it forfeits that.",
    ),
    ("boost", 0): Rule(
        Mechanic.DRAGON,
        Timing.IN_DUEL,
        "Your dragon's element. Lends its stats every showdown and can never be staked or lost.",
    ),
    ("boost", 1): Rule(
        Mechanic.BOOST,
        Timing.IN_DUEL,
        "Lends no stats of its own; amplifies the card you play after it by 1 per stat that card "
        "contributes.",
    ),
    ("play", 0): Rule(Mechanic.PRINTED_STATS, Timing.IN_DUEL, "Contributes its printed stats."),
    ("play", 1): Rule(
        Mechanic.MORPH, Timing.IN_DUEL, "Every stat becomes 1, and you choose the element it counts as."
    ),
    ("play", -1): Rule(
        Mechanic.INTANGIBLE,
        Timing.IN_DUEL,
        "Voids the elemental bonus for the rest of the showdown — for both duelists, whoever "
        "played it.",
    ),
}


# Mechanics no printed card triggers. `actions.usable_powers` has a branch waiting for HAND_FIZZLE
# (`hand`/+1), and nothing in the card DB satisfies it — the branch is unreachable today. Listed here
# so the "every mechanic is reachable" test stays a guard rather than a permanent failure.
UNPRINTED: frozenset[Mechanic] = frozenset({Mechanic.HAND_FIZZLE})


def rule_of(power: Power) -> Rule:
    """The rule a power buys. Raises on a pair nobody implemented, rather than doing nothing."""
    try:
        return RULES[power.trigger, power.effect]
    except KeyError:
        raise KeyError(
            f"power {power.name!r} has no mechanic for (trigger={power.trigger!r}, "
            f"effect={power.effect}) — it would silently do nothing"
        ) from None


def mechanic_of(power: Power) -> Mechanic:
    return rule_of(power).mechanic


def is_gamble(power: Power) -> bool:
    """The joke Wu. Its stats, name and text are all ``? ? ?``, and so is what it pays."""
    return mechanic_of(power) is Mechanic.GAMBLE


def roll_gamble(rng: Rng) -> int:
    """What a GAMBLE Wu actually pays. The only roll in the game the player cannot see coming."""
    low, high = GAMBLE_SPREAD
    return rng.randint(low, high)


def is_boost_slot(power: Power) -> bool:
    """Can this Wu be played *in addition* to the card, at the power stage?

    Both boost Wu can: the dragon (``boost``/0) lends a flat 1/1/1, the amplifier (``boost``/+1)
    lends 1 per stat the card moves. What they lend differs; the slot they occupy does not.
    """
    return power.trigger == "boost"
