"""Hand-built Wu and duelists for tests.

The *catalog* Wu (a real card, by id) is the `card` fixture in conftest. This is the other thing: a Wu
with the exact stats a test needs and nothing else true about it. Seven test files each grew their own
version of this; they are all this one, with different defaults.
"""

from __future__ import annotations

from xiaolin_showdown.logic.battle import Ground
from xiaolin_showdown.logic.constants import TOURNAMENT_BATTLES
from xiaolin_showdown.logic.duel import END
from xiaolin_showdown.logic.models import Card, Character, Mechanic, Player, Power
from xiaolin_showdown.logic.settings import XiaolinSettings

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
