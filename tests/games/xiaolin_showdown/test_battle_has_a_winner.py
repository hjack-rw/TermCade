"""Every battle has a winner. None of them can come out drawn.

A battle used to be filed as a draw whenever its points landed level — and they land level *often*,
because the contested stat counts +2 while the other two count −1 each: win the stat the battle was
called on, lose the other two, and the board reads exactly 0. A tournament could then end 0:0 with
three battles fought and nobody having won any of them, and the Wu changed hands on aggregate margin.

The formula: points, then initiative.
"""

from __future__ import annotations

import pytest

from xiaolin_showdown.logic.battle import Ground, Round, Side, score_battle
from xiaolin_showdown.logic.models import Card, Mechanic, Power

STATS = ("force", "agility", "intellect")
FLAT = {"force": 0, "agility": 0, "intellect": 0}  # characters lend nothing, so the Wu decide


def _wu(force: int, agility: int, intellect: int) -> Card:
    stats = {"force": force, "agility": agility, "intellect": intellect}
    return Card(1, "Wu", stats, Power(0, "", Mechanic.FILLER, ""), "metal", "item", 0)


def _ground(*, challenger_is_player: bool = True) -> Ground:
    # Metal on a metal arena: nothing resonates, so nothing but the printed stats moves the score.
    return Ground(
        stats=STATS,
        background="metal",
        player_stats=FLAT,
        bot_stats=FLAT,
        challenger_is_player=challenger_is_player,
    )


def _battle(mine: Card, theirs: Card) -> Round:
    return Round(stat="force", player=Side(queue=[mine]), bot=Side(queue=[theirs]))


@pytest.mark.parametrize("challenger_is_player", [True, False])
def test_the_contested_stat_against_the_other_two_is_level_and_initiative_takes_it(
    challenger_is_player,
):
    """The case that used to be a draw: force is taken (+2), the other two are lost (−1, −1).

    It IS level — that is the whole point of the contested stat counting double — and level goes to
    whoever called the challenge. It does not go to nobody.
    """
    battle = _battle(_wu(4, 0, 0), _wu(0, 1, 1))

    score_battle(battle, _ground(challenger_is_player=challenger_is_player))

    assert battle.score == 0, "this is only interesting while the points come out level"
    assert battle.winner is challenger_is_player


@pytest.mark.parametrize("challenger_is_player", [True, False])
def test_two_identical_wu_are_separated_by_initiative(challenger_is_player):
    battle = _battle(_wu(2, 2, 2), _wu(2, 2, 2))

    score_battle(battle, _ground(challenger_is_player=challenger_is_player))

    assert battle.score == 0
    assert battle.winner is challenger_is_player


def test_the_points_decide_a_battle_they_can_separate():
    """Initiative is the floor, not the rule: a battle the score separates never reaches it."""
    battle = _battle(_wu(4, 2, 0), _wu(0, 0, 1))  # +2 force, +1 agility, −1 intellect = +2

    score_battle(battle, _ground(challenger_is_player=False))  # initiative would have taken it away

    assert battle.score > 0
    assert battle.winner is True


def test_no_battle_is_ever_drawn():
    """Exhaustive over every stat line either Wu could print: not one battle comes out without a
    winner. This is the invariant a tournament's 2:1 rests on."""
    values = range(-2, 5)
    for mine in ((f, a, i) for f in values for a in values for i in values):
        for theirs in ((f, a, i) for f in values for a in values for i in values):
            battle = _battle(_wu(*mine), _wu(*theirs))
            score_battle(battle, _ground())
            assert battle.winner is not None, f"{mine} vs {theirs} came out drawn"
