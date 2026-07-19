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

from ..models import Mechanic, Power


class Timing(StrEnum):
    """When the mechanic acts. The value is the heading a player reads."""

    IN_HAND = "While it sits in your hand"
    AT_TEMPLE = "Spent at the temple"
    IN_DUEL = "Played in a showdown"
    NEVER = "No mechanic"


@dataclass(frozen=True)
class Rule:
    """What a mechanic is: when it fires, when it *acts*, and what it says to a player.

    ``trigger`` is the slot the duel machinery reads — a Wu is offered at the temple (``use``), sits
    in the hand (``hand``), goes down in the boost slot (``boost``) or is fielded (``play``). It used
    to be a DB column; it is a property of the mechanic, and this is the one place that says so.
    """

    mechanic: Mechanic
    trigger: str  # "none" | "hand" | "use" | "boost" | "play"
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

# What the Orb and the Curse pour into the one stat their caster names. Both print `? ? ?` — the mark
# of a Wu whose stats are resolved when it is played — so the magnitude lives here, not in the row.
#
# Worth 3 because a battle scores every stat, not just the contested one: the contested stat is
# worth 2 points and the other two 1 each (`battle.score_battle`). So pouring it into the challenge
# is the obvious line, and pouring it into the two side stats to steal 1+1 instead is the one that
# has to be *chosen*. Move this number and that choice moves with it.
NAMED_STAT_VALUE = 3

# How deep into the draw pile Teleskopia sees. Three, not one: a single card tells you what you are
# about to draw, three lets you plan a turn around it — which is the whole reason to spend a Wu on
# looking instead of banking it.
SCOPE_DEPTH = 3

# What the Morpher becomes when it is played. It prints `? ? ?` and takes these instead: the full
# value on the two stats the battle is *not* fought over, and less on the one it is.
#
# The dip is the price of the rest of the card, and the Morpher is the one Wu that can pay it: it
# chooses the element it counts as, so it always matches the arena, and the elemental bonus lands on
# the contested stat *alone* — which stands the low stat straight back up. The cost is real anyway,
# because the contested stat scores double (`battle.score_battle`) and metal arenas grant nothing.
MORPH_ASIDE = 2
MORPH_CONTESTED = 1

# What a Morpher lends when it is spent as a *boost* instead of fielded — a flat 1/1/1, in the element
# its caster names. A dragon that chooses its colour: weaker than the fielded 2/2/1 shape, but always
# in tune with the arena. This is the mode a wudai Moby Morpher (Hannibal's, or any found in the pool
# and laid as a boost) takes, since the inalienable slot can only ever boost.
MORPH_BOOST = 1


# Keyed by the mechanic itself — which is what the card DB stores. Nothing here is an integer, so
# nothing here can be a Wu that quietly does nothing because somebody picked a number twice.
RULES: dict[Mechanic, Rule] = {
    Mechanic.FILLER: Rule(Mechanic.FILLER, "none", Timing.NEVER, "Deck filler. Does nothing."),
    Mechanic.INITIATIVE: Rule(
        Mechanic.INITIATIVE,
        "hand",
        Timing.IN_HAND,
        "Adds its initiative bonus while held. Equal bonuses don't stack; different ones do, "
        "and your opponent's negatives land on you.",
    ),
    Mechanic.HAND_SIZE: Rule(
        Mechanic.HAND_SIZE, "hand", Timing.IN_HAND, "Raises your hand limit by one while held."
    ),
    Mechanic.HAND_FIZZLE: Rule(
        Mechanic.HAND_FIZZLE,
        "hand",
        Timing.AT_TEMPLE,
        "Can be spent at the temple, but its power fizzles — it is discarded for no points.",
    ),
    Mechanic.GAMBLE: Rule(
        Mechanic.GAMBLE,
        "use",
        Timing.AT_TEMPLE,
        f"Nobody knows what it is worth. Deposit it and find out: anywhere from "
        f"{GAMBLE_SPREAD[0]:+d} to {GAMBLE_SPREAD[1]:+d} points.",
    ),
    Mechanic.CHRONOKINESIS: Rule(
        Mechanic.CHRONOKINESIS,
        "use",
        Timing.AT_TEMPLE,
        "Spend it to draw a Wu from the pile. Depositing it forfeits that.",
    ),
    Mechanic.DIASKOPIA: Rule(
        Mechanic.DIASKOPIA,
        "use",
        Timing.AT_TEMPLE,
        "Spend it to read your opponent's personal deck. Only offered while they hold one.",
    ),
    Mechanic.TELESKOPIA: Rule(
        Mechanic.TELESKOPIA,
        "use",
        Timing.AT_TEMPLE,
        f"Spend it to look at the next {SCOPE_DEPTH} Wu in the draw pile, in the order they will "
        f"come.",
    ),
    Mechanic.TELEPATHEIA: Rule(
        Mechanic.TELEPATHEIA,
        "use",
        Timing.AT_TEMPLE,
        "Spend it to see the next Wu in the pile, then take or refuse initiative in the next "
        "showdown — whatever the two hands add up to.",
    ),
    Mechanic.ATTRACTION: Rule(
        Mechanic.ATTRACTION,
        "use",
        Timing.AT_TEMPLE,
        "Spend it to pull any one Wu out of your own deck and into your hand.",
    ),
    Mechanic.REPULSION: Rule(
        Mechanic.REPULSION,
        "use",
        Timing.AT_TEMPLE,
        "Spend it to shove one Wu out of your opponent's hand — deposit it (they keep the points) or "
        "bury it in their Deck (no points, but they draw it back).",
    ),
    Mechanic.EUTHYMIA: Rule(
        Mechanic.EUTHYMIA,
        "use",
        Timing.AT_TEMPLE,
        "Spend it at the temple to bring the oldest lost Wu back — into your hand, not the pile.",
    ),
    Mechanic.METEMPSYCHOSIS: Rule(
        Mechanic.METEMPSYCHOSIS,
        "use",
        Timing.AT_TEMPLE,
        "Spend it to swap your entire hand with your opponent's — a Wudai weapon stays with its "
        "soul's owner.",
    ),
    Mechanic.WITCHCRAFT: Rule(
        Mechanic.WITCHCRAFT,
        "hand",
        Timing.AT_TEMPLE,
        "Witchcraft: a Wu she spends returns to her hand, worn one further by the sorcery — the "
        "third use vaults it. Her temple turn can also call the oldest lost Wu back.",
    ),
    Mechanic.BEAST_FORM: Rule(
        Mechanic.BEAST_FORM,
        "boost",  # it reads "On Boost" on his sheet — it IS a boost, just his own, not a Wu's
        Timing.IN_DUEL,
        "Beast Form: once a showdown, +3 to the contested stat — element-free, beyond the reach of "
        "any counter. His Wu score nothing while it holds; he wagers them, never wields them.",
    ),
    Mechanic.DRAGON: Rule(
        Mechanic.DRAGON,
        "boost",
        Timing.IN_DUEL,
        "A wudai weapon: it lends its stats every showdown from the boost slot, and is never "
        "fielded as a Wu. The one your character was born holding can never be staked or lost — "
        "one found in the pile can be both.",
    ),
    Mechanic.BOOST: Rule(
        Mechanic.BOOST,
        "boost",
        Timing.IN_DUEL,
        "Lends no stats of its own; amplifies the card you play after it by 1 per stat that card "
        "contributes.",
    ),
    Mechanic.INNATE: Rule(Mechanic.INNATE, "play", Timing.IN_DUEL, "Contributes its printed stats."),
    Mechanic.MORPH: Rule(
        Mechanic.MORPH,
        "play",
        Timing.IN_DUEL,
        f"Becomes {MORPH_ASIDE} in the two stats the battle is not fought over and "
        f"{MORPH_CONTESTED} in the one it is — and you choose the element it counts as.",
    ),
    Mechanic.HYDROKINESIS: Rule(
        Mechanic.HYDROKINESIS,
        "play",
        Timing.IN_DUEL,
        f"Prints no stats. Name one when you play it, and it pours +{NAMED_STAT_VALUE} into that stat "
        f"alone.",
    ),
    Mechanic.MISFORTUNE: Rule(
        Mechanic.MISFORTUNE,
        "play",
        Timing.IN_DUEL,
        f"Prints no stats. Name one when you play it, and your opponent suffers −{NAMED_STAT_VALUE} in "
        f"that stat.",
    ),
    Mechanic.CONTAINMENT: Rule(
        Mechanic.CONTAINMENT,
        "play",
        Timing.IN_DUEL,
        "Traps your opponent for this battle: their own stats count for nothing, and only the Wu "
        "they played answer for them.",
    ),
    Mechanic.REVERSAL: Rule(
        Mechanic.REVERSAL,
        "play",
        Timing.IN_DUEL,
        "Turns every curse laid on you aside for this battle. Your Defensive line counts for "
        "nothing.",
    ),
    Mechanic.SUBJUGATION: Rule(
        Mechanic.SUBJUGATION,
        "play",
        Timing.IN_DUEL,
        "Disarms your opponent for this battle: every Wu they played counts for nothing, and only "
        "they themselves answer for it.",
    ),
    Mechanic.INTANGIBLE: Rule(
        Mechanic.INTANGIBLE,
        "play",
        Timing.IN_DUEL,
        "Voids the elemental bonus for the rest of the showdown — for both duelists, whoever "
        "played it.",
    ),
    Mechanic.DISSONANCE: Rule(
        Mechanic.DISSONANCE,
        "play",
        Timing.IN_DUEL,
        "Reverses the elemental bonus for the rest of the showdown, for both duelists: a resonant Wu "
        "now costs, an opposed one now pays.",
    ),
    Mechanic.DAMPENING: Rule(
        Mechanic.DAMPENING,
        "play",
        Timing.IN_DUEL,
        "Smothers your opponent's boost for this battle: its stats count for nothing.",
    ),
    Mechanic.TRANSMUTATION: Rule(
        Mechanic.TRANSMUTATION,
        "play",
        Timing.IN_DUEL,
        "Turns your opponent's Wu to metal for this battle — they read as metal for the background "
        "bonus, favoured nowhere but a metal arena.",
    ),
    Mechanic.CHROMASIS: Rule(
        Mechanic.CHROMASIS,
        "play",
        Timing.IN_DUEL,
        "You choose the element your own Wu count as for this battle's background bonus.",
    ),
    Mechanic.STORMFRONT: Rule(
        Mechanic.STORMFRONT,
        "play",
        Timing.IN_DUEL,
        "You choose the arena's element for the rest of the showdown.",
    ),
    Mechanic.WARD: Rule(
        Mechanic.WARD,
        "play",
        Timing.IN_DUEL,
        "Wards its own element for this battle: your Wu of that element ignore every negative "
        "background bonus — the lift still lands.",
    ),
}


# Mechanics no printed card names. `actions.usable_powers` has a branch waiting for HAND_FIZZLE,
# and nothing in the card DB satisfies it — the branch is unreachable today. Listed here
# so the "every mechanic is reachable" test stays a guard rather than a permanent failure.
UNPRINTED: frozenset[Mechanic] = frozenset({Mechanic.HAND_FIZZLE})


def rule_of(power: Power) -> Rule:
    """The rule a power buys. Raises on a mechanic nobody implemented, rather than doing nothing.

    A card's mechanic is validated when the DB is *loaded* (``Mechanic(row)`` rejects an unknown
    name), so reaching this is not a bad card — it is a mechanic somebody named and never wrote.
    """
    try:
        return RULES[power.mechanic]
    except KeyError:
        raise KeyError(
            f"power {power.name!r} names the mechanic {power.mechanic!r}, and nobody implemented it "
            f"— it would silently do nothing"
        ) from None


def mechanic_of(power: Power) -> Mechanic:
    return power.mechanic


def trigger_of(power: Power) -> str:
    """When a power fires — a property of *what it is*, no longer a column in the DB."""
    return rule_of(power).trigger


def is_gamble(power: Power) -> bool:
    """The joke Wu. Its stats, name and text are all ``? ? ?``, and so is what it pays."""
    return mechanic_of(power) is Mechanic.GAMBLE


def roll_gamble(rng: Rng) -> int:
    """What a GAMBLE Wu actually pays. The only roll in the game the player cannot see coming."""
    low, high = GAMBLE_SPREAD
    return rng.randint(low, high)


def names_a_stat(power: Power) -> bool:
    """Does this Wu ask its caster which stat to pour itself into?

    Both do — the Orb pours a gain, the Curse pours a wound. What they aim at is the same question,
    asked of whoever plays them, so the duel asks it in one place.
    """
    return mechanic_of(power) in (Mechanic.HYDROKINESIS, Mechanic.MISFORTUNE)


def is_boost_slot(power: Power) -> bool:
    """Can this Wu be played *in addition* to the card, at the power stage?

    The dragon lends a flat 1/1/1 and the amplifier lends 1 per stat the card moves; both trigger on
    "boost". The Morpher is dual-mode — fielded it takes its 2/2/1 shape, but it may also be spent as a
    boost (a 1/1/1 of its chosen element), which is the only mode open to it in the wudai slot.
    """
    return trigger_of(power) == "boost" or mechanic_of(power) is Mechanic.MORPH
