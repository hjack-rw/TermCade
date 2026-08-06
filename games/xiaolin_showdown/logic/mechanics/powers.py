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

from ..schema.catalog import load_mechanic_config
from ..schema.models import Mechanic, Power

_CONFIG = load_mechanic_config()


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
# Its DB `points` is the card's *expected* value (read only by `point_limit_for` and the bot's
# ranking), not a payout the card can pay — the two are allowed to differ. Widen the spread and the
# stored value must move to match.
#
# The only randomness a duelist cannot see coming, and it belongs to exactly one Wu — a second card
# that rolls would make this one ordinary. If you are about to give another Wu a random anything: don't.
GAMBLE_SPREAD = (_CONFIG["gamble"]["low"], _CONFIG["gamble"]["high"])

# What the Orb and the Curse pour into the one stat their caster names. Both print `? ? ?` — the mark
# of a Wu whose stats are resolved when it is played — so the magnitude lives here, not in the row.
NAMED_STAT_VALUE = _CONFIG["buff"]["value"]

# How many cards ahead Teleskopia reveals in the draw pile.
SCOPE_DEPTH = _CONFIG["scry"]["depth"]

# What the Morpher becomes when it is played. It prints `? ? ?` and takes these instead: the full
# value on the two stats the battle is *not* fought over, and less on the one it is — it chooses the
# element it counts as, so the elemental bonus can land on the contested stat alone.
MORPH_ASIDE = _CONFIG["morph"]["aside"]
# The contested stat gives up exactly the elemental boost's own weight (the ±1 element match/mismatch
# swing in `battle.score_battle`) — the Morpher's chosen element lands everywhere else, never on the
# stat it picked the fight over. Not an independent balance number, and not its own DB row.
MORPH_CONTESTED = MORPH_ASIDE - 1

# What a Morpher lends when it is spent as a *boost* instead of fielded — a flat 1/1/1, in the element
# its caster names. This is the mode a wudai Moby Morpher (Hannibal's, or any found in the pool and
# laid as a boost) takes, since the inalienable slot can only ever boost.
MORPH_BOOST = _CONFIG["morph"]["boost"]

# What the Heart of Jong's animated form takes in every stat when it comes alive **in the boost slot** —
# a flat shape, no Morpher dip, always the arena's own element.
ANIMATE_STAT = _CONFIG["animate"]["stat"]
# Fielded as a plain Wu instead of boosted, the Heart is a weaker middling body — no summon, no arena
# element (it rests metal). The boost is the point; the field is a fallback.
ANIMATE_FIELD_STAT = _CONFIG["animate"]["field_stat"]

# Chase Young's Beast Form bonus on the contested stat, and how far above parity Chamelon-Bot closes
# the gap when the player leads (see `duel._chamelon_boost_card`). Both live here, not in `flow.duel`,
# so every `mechanic_config` read happens in one place — `duel` already imports this module.
BEAST_BOOST = _CONFIG["beast_form"]["boost"]
CHAMELON_MARGIN = _CONFIG["bot"]["chamelon_margin"]


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
    Mechanic.DRAW: Rule(
        Mechanic.DRAW,
        "use",
        Timing.AT_TEMPLE,
        "Spend it to draw a Wu from the pile. Depositing it forfeits that.",
    ),
    Mechanic.READ_DECK: Rule(
        Mechanic.READ_DECK,
        "use",
        Timing.AT_TEMPLE,
        "Spend it to read your opponent's personal deck. Only offered while they hold one.",
    ),
    Mechanic.SCRY: Rule(
        Mechanic.SCRY,
        "use",
        Timing.AT_TEMPLE,
        f"Spend it to look at the next {SCOPE_DEPTH} Wu in the draw pile, in the order they will "
        f"come.",
    ),
    Mechanic.ENHANCED_VISION: Rule(
        Mechanic.ENHANCED_VISION,
        "use",
        Timing.AT_TEMPLE,
        "Spend it to see the next Wu in the pile, then take or refuse initiative in the next "
        "showdown — whatever the two hands add up to.",
    ),
    Mechanic.FETCH: Rule(
        Mechanic.FETCH,
        "use",
        Timing.AT_TEMPLE,
        "Spend it to pull any one Wu out of your own deck and into your hand.",
    ),
    Mechanic.BOUNCE: Rule(
        Mechanic.BOUNCE,
        "use",
        Timing.AT_TEMPLE,
        "Spend it to shove one Wu out of your opponent's hand — deposit it (they keep the points) or "
        "bury it in their Deck (no points, but they draw it back).",
    ),
    Mechanic.LUCK: Rule(
        Mechanic.LUCK,
        "use",
        Timing.AT_TEMPLE,
        "Spend it at the temple to bring the oldest lost Wu back — into your hand, not the pile.",
    ),
    Mechanic.PROGNOSIS: Rule(
        Mechanic.PROGNOSIS,
        "use",
        Timing.AT_TEMPLE,
        "Spend it to let your opponent lead the next Showdown — but you read the challenge before they play "
        ", and keep the challenger's ground after the battle.",
    ),
    Mechanic.SEIZE_GROUND: Rule(
        Mechanic.SEIZE_GROUND,
        "play",
        Timing.IN_DUEL,
        "Field it and its caster holds the challenger's ground for the rest of the Showdown, "
        "winning every level battle — overriding a Prognosis set at the temple. Both duelists "
        "fielding one cancels it, and the ground goes back to whoever leads.",
    ),
    Mechanic.TRANSFER: Rule(
        Mechanic.TRANSFER,
        "use",
        Timing.AT_TEMPLE,
        "Spend it to swap your entire hand with your opponent's — a Wudai weapon stays with its "
        "soul's owner.",
    ),
    Mechanic.AMEND: Rule(
        Mechanic.AMEND,
        "use",
        Timing.AT_TEMPLE,
        "Spend it to take back your previous action this turn — a fumbled deposit, draw, or power, put "
        "right. One undo, and the Mouse is spent doing it; in a one-action turn there is nothing to fix.",
    ),
    Mechanic.WISH: Rule(
        Mechanic.WISH,
        "use",
        Timing.AT_TEMPLE,
        "One wish, then gone for good — no power brings it back. Deposit it for a heap of points, spend "
        "it to wish a Wu back from your Vault, or field it in a Showdown to win outright.",
    ),
    Mechanic.TRAIN_BOOST: Rule(
        Mechanic.TRAIN_BOOST,
        "use",
        Timing.AT_TEMPLE,
        "Spend it at the temple to summon help to train against — a one-time shove forward on your "
        "training bar, then it is gone. Useless once every base stat is capped.",
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
        # The magnitude is `duel.BEAST_BOOST`, which cannot be imported here — `duel` imports this
        # module. Keep the two in step by hand; the harness sweeps the constant, not this sentence.
        "Beast Form: once a showdown, +1 to the contested stat — element-free, beyond the reach of "
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
    Mechanic.BOT: Rule(
        Mechanic.BOT,
        "boost",
        Timing.IN_DUEL,
        "A construct: it lends its stats every showdown from the boost slot, and is never fielded "
        "as a Wu. Jack built it himself, so it can never be staked or lost.",
    ),
    Mechanic.INNATE: Rule(Mechanic.INNATE, "play", Timing.IN_DUEL, "Contributes its printed stats."),
    Mechanic.MORPH: Rule(
        Mechanic.MORPH,
        "play",
        Timing.IN_DUEL,
        f"Becomes {MORPH_ASIDE} in the two stats the battle is not fought over and "
        f"{MORPH_CONTESTED} in the one it is — and you choose the element it counts as.",
    ),
    Mechanic.ANIMATE: Rule(
        Mechanic.ANIMATE,
        "play",
        Timing.IN_DUEL,
        f"Fielded, a middling {ANIMATE_FIELD_STAT}/{ANIMATE_FIELD_STAT}/{ANIMATE_FIELD_STAT} body. Laid in "
        f"the boost slot it wakes a separate {ANIMATE_STAT}/{ANIMATE_STAT}/{ANIMATE_STAT} summon in the "
        f"arena's element — and the opponent may field one extra Wu to answer it.",
    ),
    Mechanic.BUFF: Rule(
        Mechanic.BUFF,
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
    Mechanic.NULLIFY_STATS: Rule(
        Mechanic.NULLIFY_STATS,
        "play",
        Timing.IN_DUEL,
        "Traps your opponent for this battle: their own stats count for nothing, and only the Wu "
        "they played answer for them.",
    ),
    Mechanic.NULLIFY_CURSE: Rule(
        Mechanic.NULLIFY_CURSE,
        "play",
        Timing.IN_DUEL,
        "Turns every curse laid on you aside for this battle. Your Defensive line counts for "
        "nothing.",
    ),
    Mechanic.NULLIFY_WU: Rule(
        Mechanic.NULLIFY_WU,
        "play",
        Timing.IN_DUEL,
        "Disarms your opponent for this battle: every Wu they played counts for nothing, and only "
        "they themselves answer for it.",
    ),
    Mechanic.NULLIFY_ELEMENT: Rule(
        Mechanic.NULLIFY_ELEMENT,
        "play",
        Timing.IN_DUEL,
        "Voids the elemental bonus for the rest of the showdown — for both duelists, whoever "
        "played it.",
    ),
    Mechanic.REVERSE_ELEMENT: Rule(
        Mechanic.REVERSE_ELEMENT,
        "play",
        Timing.IN_DUEL,
        "Reverses the elemental bonus for the rest of the showdown, for both duelists: a resonant Wu "
        "now costs, an opposed one now pays.",
    ),
    Mechanic.NULLIFY_BOOST: Rule(
        Mechanic.NULLIFY_BOOST,
        "play",
        Timing.IN_DUEL,
        "Smothers your opponent's boost for this battle: its stats count for nothing.",
    ),
    Mechanic.HACK: Rule(
        Mechanic.HACK,
        "play",
        Timing.IN_DUEL,
        "If your opponent faces you as a robot construct, you win the showdown outright. Unless "
        "it is Mala Mala Jong.",
    ),
    Mechanic.STEAL: Rule(
        Mechanic.STEAL,
        "play",
        Timing.IN_DUEL,
        "Takes your opponent's strongest hand Wu into your own hand — or a random Wu from their "
        "Deck if their hand is empty.",
    ),
    Mechanic.CONDUCT: Rule(
        Mechanic.CONDUCT,
        "play",
        Timing.IN_DUEL,
        "The stat this battle contests gets +1 for every metal Wu fielded this battle — yours or "
        "your opponent's, boosts included — and -1 for every non-metal one. The arena itself "
        "counts the same way. Can go negative. Uncapped either way.",
    ),
    Mechanic.STAT_SWAP: Rule(
        Mechanic.STAT_SWAP,
        "play",
        Timing.IN_DUEL,
        "Names a stat: swaps it between your Character and your opponent's for the rest of this "
        "Showdown. Also flips your shown affiliation for the rest of the run, until you play "
        "another Yo-Yo.",
    ),
    Mechanic.CHI_SWAP: Rule(
        Mechanic.CHI_SWAP,
        "play",
        Timing.IN_DUEL,
        "Names a stat: swaps it between your Character and your opponent's for the rest of this "
        "Showdown. Also flips your OPPONENT'S shown affiliation for the rest of the run. Held at "
        "the temple, it may instead correct your own affiliation back — exiled either way, for good.",
    ),
    Mechanic.CLEANSE: Rule(
        Mechanic.CLEANSE,
        "play",
        Timing.IN_DUEL,
        "Turns your opponent's Wu to metal for this battle — they read as metal for the background "
        "bonus, favoured nowhere but a metal arena.",
    ),
    Mechanic.SET_ELEMENT: Rule(
        Mechanic.SET_ELEMENT,
        "play",
        Timing.IN_DUEL,
        "You choose the element your own Wu count as for this battle's background bonus.",
    ),
    Mechanic.SET_ARENA: Rule(
        Mechanic.SET_ARENA,
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
    Mechanic.TREASURE: Rule(
        Mechanic.TREASURE,
        "deposit",
        Timing.AT_TEMPLE,
        "Worth a bunch of points — deposit it for the windfall. It has no power to spend, and its "
        "printed stats are all it brings to a showdown.",
    ),
    Mechanic.REFRESH: Rule(
        Mechanic.REFRESH,
        "use",
        Timing.AT_TEMPLE,
        "Spend it to bring the Wu you most recently used back into your hand, ready to spend again.",
    ),
    Mechanic.DOUBLE_TRAINING: Rule(
        Mechanic.DOUBLE_TRAINING,
        "hand",
        Timing.IN_HAND,
        "While it is in your hand, every point of training you gain counts double — a lost showdown "
        "teaches twice, if it is still in your hand once the showdown ends.",
    ),
    Mechanic.STAT_SHIELD: Rule(
        Mechanic.STAT_SHIELD,
        "play",
        Timing.IN_DUEL,
        "Field it for its printed stats, and take no curse on the stat it boosts this battle — a "
        "debuff landed on that stat counts nothing.",
    ),
    Mechanic.DOUBLE_ELEMENT: Rule(
        Mechanic.DOUBLE_ELEMENT,
        "play",
        Timing.IN_DUEL,
        "Its own elemental bonus counts double — twice the lift in tune, twice the drag against it.",
    ),
}


# Mechanics no printed card names. `actions.usable_powers` has a branch waiting for HAND_FIZZLE,
# and nothing in the card DB satisfies it — the branch is unreachable today. FILLER is a rule with
# nothing left to apply it to: an ordinary opponent's "no power" is `catalog.NO_POWER`, a synthetic
# stand-in never read from a DB row (see its own comment). Listed here so the "every mechanic is
# reachable" test stays a guard rather than a permanent failure.
UNPRINTED: frozenset[Mechanic] = frozenset({Mechanic.HAND_FIZZLE, Mechanic.FILLER})


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


SAPPHIRE_DRAGON = 74  # Agalmatosis — the one Wu a duelist cannot command; fielded, it loses the showdown


def is_uncontrolled(power: Power) -> bool:
    """The Sapphire Dragon. Fielded, it loses the showdown outright for its own summoner, and its
    stats never count (reads ``?`` like the Gamble's). Keyed to the power *id*: the name is flavour
    and has changed more than once, the id is stable. WEAK POINT: stable across renames, but a future
    renumber still breaks it — update SAPPHIRE_DRAGON when that happens."""
    return power.id == SAPPHIRE_DRAGON


EMPEROR_SCORPION = 55  # Subjugation — Mala Mala Jong's bane


def is_jong_bane(power: Power) -> bool:
    """Emperor Scorpion. Fielded against Mala Mala Jong it wins that BATTLE outright (a tournament
    leg, not the whole showdown). Id-keyed, like the Sapphire Dragon. WEAK POINT: same renumber
    exposure — update EMPEROR_SCORPION when that happens."""
    return power.id == EMPEROR_SCORPION


def roll_gamble(rng: Rng) -> int:
    """What a GAMBLE Wu actually pays. The only roll in the game the player cannot see coming."""
    low, high = GAMBLE_SPREAD
    return rng.randint(low, high)


def names_a_stat(power: Power) -> bool:
    """Does this Wu ask its caster which stat to pour itself into?

    BUFF/MISFORTUNE and both Yo-Yo forms all ask the same question of whoever plays them, so the
    duel asks it in one place.
    """
    return mechanic_of(power) in (Mechanic.BUFF, Mechanic.MISFORTUNE, Mechanic.STAT_SWAP, Mechanic.CHI_SWAP)


def chooses_element(power: Power) -> bool:
    """Does this Wu ask its caster which element to count as, for this battle's background bonus?

    The Morpher, Eye of Dashi and Monsoon Sandals all ask the same question of whoever plays them,
    so the duel and the bot's own evaluation ask it in one place.
    """
    return mechanic_of(power) in (Mechanic.MORPH, Mechanic.SET_ELEMENT, Mechanic.SET_ARENA)


def is_boost_slot(power: Power) -> bool:
    """Can this Wu be played *in addition* to the card, at the power stage?

    The dragon lends a flat 1/1/1 and the amplifier lends 1 per stat the card moves; both trigger on
    "boost". The Morpher is dual-mode — fielded it takes its 2/2/1 shape, but it may also be spent as a
    boost (a 1/1/1 of its chosen element), which is the only mode open to it in the wudai slot.
    """
    return trigger_of(power) == "boost" or mechanic_of(power) in (Mechanic.MORPH, Mechanic.ANIMATE)
