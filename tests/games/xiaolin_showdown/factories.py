"""Hand-built Wu and duelists for tests.

The *catalog* Wu (a real card, by id) is the `card` fixture in conftest. This is the other thing: a Wu
with the exact stats a test needs and nothing else true about it. Seven test files each grew their own
version of this; they are all this one, with different defaults.
"""

from __future__ import annotations

from xiaolin_showdown.logic.flow.battle import Ground
from xiaolin_showdown.logic.schema.constants import TOURNAMENT_BATTLES
from xiaolin_showdown.logic.flow.duel import END, DuelChoices
from xiaolin_showdown.logic.mechanics.powers import mechanic_of
from xiaolin_showdown.logic.schema.models import Card, Character, Mechanic, Player, Power
from xiaolin_showdown.logic.config.settings import XiaolinSettings

STATS = ("force", "agility", "intellect")
NO_STATS = dict.fromkeys(STATS, 0)


def ground(
    *,
    background: str = "metal",
    player_stats: dict[str, int] | None = None,
    bot_stats: dict[str, int] | None = None,
    **terms: object,
) -> Ground:
    """A battle's Ground with ``stats`` fixed to the game's three and characters that lend nothing —
    a metal arena, no resonance to read. ``**terms`` sets Ground's flags (``bonus_cancelled``,
    ``challenger_is_player``, ``bonus_reversed``)."""
    return Ground(
        stats=STATS,
        background=background,
        player_stats=dict(player_stats or NO_STATS),
        bot_stats=dict(bot_stats or NO_STATS),
        **terms,  # type: ignore[arg-type]
    )


async def run_showdown(duel, settings: XiaolinSettings | None = None) -> int:
    """Advance the stage machine until the End, and return the stage it ended on.

    The bound is DERIVED, not guessed: commitment, setup, resolvement and end, plus a boost+card pair
    for every Wu fielded (a tournament's three, or the widest wager). It comes to 10, and the longest
    showdown a real game plays is 10 — the bound is exact, and it moves when the machine does. Seven
    tests each carried a magic ``guard < 40`` instead: a fact about the machine, kept anywhere but
    next to it.
    """
    rules = settings or XiaolinSettings()
    limit = 4 + 2 * max(rules.max_wager, TOURNAMENT_BATTLES)

    for _ in range(limit):
        stage = await duel.advance()
        if stage == END:
            return stage
    raise AssertionError(f"the showdown never reached its End in {limit} stages")


def wu(
    force: int | None = 0,
    agility: int | None = 0,
    intellect: int | None = 0,
    *,
    mechanic: Mechanic = Mechanic.INNATE,
    element: str = "metal",
    points: int = 0,
    bonus: int = 0,
    name: str = "Wu",
    type: str = "item",
    id: int = 0,
) -> Card:
    """A built Wu. ``bonus`` is the power's ``initiative_bonus``."""
    stats = {"force": force, "agility": agility, "intellect": intellect}
    return Card(id, name, stats, Power(0, "", mechanic, "", bonus), element, type, points)


def character(
    stats: dict[str, int] | None = None, *, name: str = "C", tier: str | None = None
) -> Character:
    """A blank duelist's character — no stats of its own, so the Wu decide."""
    return Character(0, name, dict(stats or NO_STATS), wu().power, "xiaolin", True, tier=tier)


def duelist(*, hand: list[Card] | None = None, deck: list[Card] | None = None, **char) -> Player:
    return Player(character=character(**char), hand=list(hand or []), deck=list(deck or []))


# --- scripted duel choices ----------------------------------------------------------------------
# The stage machine awaits its choices; these async callbacks take the first legal option and never
# boost — enough to drive a headless showdown. `auto_choices()` assembles them; a test overrides one
# with `dataclasses.replace(auto_choices(), card=my_picker)`. Seven files each grew their own copies.


async def first(options):
    return options[0]  # challenge / background / stat: the first legal option


async def first_card(playable):
    return playable[0]


async def no_boost(_options):
    return None


async def one_wu(options):
    return options[0]  # the smallest legal stake


async def water(_background):
    return "water"


def auto_choices() -> DuelChoices:
    return DuelChoices(
        challenge=first, background=first, wager=one_wu,
        boost=no_boost, card=first_card, element=water, stat=first,
    )


# --- real catalog Wu that share a mechanic with siblings ------------------------------------------
# `card_ids.py` is generated from the DB and only covers a mechanic exactly one pool Wu carries — see
# its own docstring. These mechanics have several Wu; a test that needs one SPECIFIC one (not just
# "any Wu with this mechanic") picks it here, by whatever actually singles it out, so the reason is
# written down in one place instead of re-derived in every test file that needs it.


def plain_wu(catalog) -> Card:
    """INNATE has six plain Wu (a Wu whose stats ARE its power, no queued effect). This is the one
    with a positive force stat — Fist of Tebigong today, whatever a DB edit renames it to tomorrow."""
    return next(
        c for c in catalog.cards if mechanic_of(c.power) is Mechanic.INNATE and c.stats["force"] > 0
    )


def plain_wu_agility(catalog) -> Card:
    """The same INNATE family, positive agility instead — a second plain Wu distinct from
    :func:`plain_wu`, for tests that need two."""
    return next(
        c for c in catalog.cards if mechanic_of(c.power) is Mechanic.INNATE and c.stats["agility"] > 0
    )


def cursed_wu(catalog) -> Card:
    """The INNATE Wu with negative force — a curse baked into its own stats, not a queued power."""
    return next(
        c for c in catalog.cards if mechanic_of(c.power) is Mechanic.INNATE and c.stats["force"] < 0
    )


def initiative_wu(catalog, bonus: int, *, exclude: Card | None = None) -> Card:
    """An INITIATIVE Wu at exactly ``bonus`` — several share any given magnitude, so pass ``exclude``
    (a Wu already picked) when a test needs two *distinct* Wu at the same bonus."""
    return next(
        c
        for c in catalog.cards
        if mechanic_of(c.power) is Mechanic.INITIATIVE
        and c.power.initiative_bonus == bonus
        and c is not exclude
    )


def summon_wu(catalog, summon: str) -> Card:
    """A TRAIN_BOOST Wu by its ``power.summon`` template — the six share the mechanic, but each names
    a different thing when it is spent (``"{beast}"``, ``"a Horde of Zombies"``, ...)."""
    return next(c for c in catalog.cards if c.power.summon == summon)
