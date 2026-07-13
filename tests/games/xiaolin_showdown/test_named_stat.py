"""The Wu that print no stats and are told one: the Orb of Tornami, and Kaijin's Curse.

Both pour their whole value into a single stat their caster names — the Orb into their own, the
Curse into their opponent's. The rule that makes the naming a *choice* rather than a formality lives
in ``battle.score_battle``: a battle scores all three stats, the contested one for 2 points and the
other two for 1 each. So the contested stat is the obvious pour, and taking the two side stats
instead wins the battle just as well.
"""

from __future__ import annotations

import pytest

from xiaolin_showdown.logic.battle import Ground, Round, score_battle
from xiaolin_showdown.logic.bot import choose_stat
from xiaolin_showdown.logic.mechanics.powers import NAMED_STAT_VALUE
from xiaolin_showdown.logic.mechanics.resolve import resolve_played_power

ORB_OF_TORNAMI = 28
KAIJINS_CURSE = 29

STATS = ("force", "agility", "intellect")


def _ground(stat_totals: dict[str, int] | None = None, background: str = "metal") -> Ground:
    """A board with the elemental bonus switched off, so only the pour is being measured.

    Left on, it would ride along: the bonus lands on the *contested* stat for every card a duelist
    contributes, whichever stat that card poured itself into. A water Orb on a metal ground is −1 on
    the challenge before it has done anything — real, and tested elsewhere, but not this rule.
    """
    blank = {stat: 0 for stat in STATS}
    return Ground(
        stats=STATS,
        background=background,
        player_stats=stat_totals or dict(blank),
        bot_stats=dict(blank),
        bonus_cancelled=True,
    )


def test_the_orb_pours_everything_into_the_named_stat(card):
    duel = Round()

    resolve_played_power(duel, card(ORB_OF_TORNAMI), is_player=True, element="water", stat="agility")

    assert duel.player.queue[0].stats["agility"] == NAMED_STAT_VALUE


def test_the_orb_leaves_the_stats_it_was_not_named(card):
    duel = Round()

    resolve_played_power(duel, card(ORB_OF_TORNAMI), is_player=True, element="water", stat="agility")

    played = duel.player.queue[0]
    assert (played.stats["force"], played.stats["intellect"]) == (0, 0)


def test_the_curse_wounds_the_opponent_in_the_named_stat(card):
    """Its stats *become the enemy's debuffs*: the mirror lands on their side of the table."""
    duel = Round()

    resolve_played_power(duel, card(KAIJINS_CURSE), is_player=True, element="metal", stat="force")

    assert duel.bot.queue[0].stats["force"] == -NAMED_STAT_VALUE


def test_the_curse_costs_its_caster_the_wu_it_spends(card):
    """A curse empties the caster's own copy — the wound is dealt opposite, not held."""
    duel = Round()

    resolve_played_power(duel, card(KAIJINS_CURSE), is_player=True, element="metal", stat="force")

    assert duel.player.queue[0].stats["force"] == 0


def test_a_named_stat_wu_played_without_a_stat_raises(card):
    """It prints `? ? ?`. Played unasked it would pour into nothing and quietly do nothing at all."""
    with pytest.raises(ValueError, match="without naming a stat"):
        resolve_played_power(Round(), card(ORB_OF_TORNAMI), is_player=True, element="water")


# --- why the naming is a choice ---------------------------------------------------


def test_pouring_into_the_contested_stat_takes_the_double_point(card):
    battle = Round(stat="force")
    resolve_played_power(battle, card(ORB_OF_TORNAMI), is_player=True, element="metal", stat="force")

    score_battle(battle, _ground())

    assert battle.score == 2  # the contested stat, worth double


def test_pouring_into_one_side_stat_takes_only_a_single_point(card):
    """The cost of ignoring the challenge: a side stat pays 1, not 2."""
    battle = Round(stat="force")
    resolve_played_power(
        battle, card(ORB_OF_TORNAMI), is_player=True, element="metal", stat="agility"
    )

    score_battle(battle, _ground())

    assert battle.score == 1


def test_the_bot_pours_into_the_contested_stat_when_nothing_argues_otherwise(card):
    """Not hardcoded — the bot plays every stat out and keeps the best. On an empty board that is
    the contested one, because it scores double."""
    battle = Round(stat="intellect")

    assert choose_stat(battle, _ground(), card(ORB_OF_TORNAMI)) == "intellect"


def test_the_bot_abandons_the_contested_stat_when_it_cannot_win_it(card):
    """The exception the choice exists for: the player's character is so far ahead on the contested
    stat that +3 cannot close it, so the Orb is worth more taking a side stat the bot can still win.
    """
    battle = Round(stat="force")
    ground = _ground({"force": 99, "agility": 0, "intellect": 0})

    assert choose_stat(battle, ground, card(ORB_OF_TORNAMI)) != "force"
