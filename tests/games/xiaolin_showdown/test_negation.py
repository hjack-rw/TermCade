"""The three Wu that take a line off the board: the Sphere, the Scorpion, and the Mirror.

An end value is made of three things a Wu can reach — the duelist's own stats, the Wu they played,
and the curses laid on them. Each of these three negates exactly one of the three, for exactly one
battle. They print 0/0/0: the rule is the whole of what they are.

A negated line is *absent*, not zero. Its cards lend no stats and read no element, so they earn no
background bonus either — the tests below score with the bonus live, which is where that difference
shows.
"""

from __future__ import annotations

from xiaolin_showdown.logic.battle import Ground, Round, score_battle
from xiaolin_showdown.logic.mechanics.resolve import resolve_played_power

SPHERE_OF_JIANYU = 32  # negates the opponent's own stats
REVERSING_MIRROR = 33  # negates the curses laid on you
EMPEROR_SCORPION = 34  # negates every Wu the opponent played

FIST_OF_TEBIGONG = 6  # a plain Wu: force only, and its stats are the whole of it
TWO_TON_TUNIC = 17  # a plain Wu with negative force — a curse; the mirror lands on the opponent

# Read off the cards, never restated. A negation test is about what is *taken away*, so it must keep
# holding when the card it takes it from is rebalanced.

STATS = ("force", "agility", "intellect")
PLAYER_BASE = {"force": 2, "agility": 3, "intellect": 4}
BOT_BASE = {"force": 3, "agility": 3, "intellect": 3}


def _ground(*, bonus_cancelled: bool = True) -> Ground:
    return Ground(
        stats=STATS,
        background="metal",
        player_stats=PLAYER_BASE,
        bot_stats=BOT_BASE,
        bonus_cancelled=bonus_cancelled,
    )


def _force(battle: Round) -> tuple[int, int]:
    """Both duelists' end value on force, the contested stat."""
    score_battle(battle, _ground())
    return battle.player.result[0], battle.bot.result[0]


def test_without_a_negation_a_duelist_is_their_stats_and_their_wu(card):
    """The baseline the other tests are read against: their own force, plus the Fist's."""
    fist = card(FIST_OF_TEBIGONG)
    battle = Round(stat="force")
    resolve_played_power(battle, fist, is_player=False, element="metal")

    assert _force(battle)[1] == BOT_BASE["force"] + fist.stats["force"]


def test_the_sphere_takes_the_opponents_own_stats(card):
    """Trapped: only the Wu they played still answer for them."""
    battle = Round(stat="force")
    resolve_played_power(battle, card(FIST_OF_TEBIGONG), is_player=False, element="metal")
    resolve_played_power(battle, card(SPHERE_OF_JIANYU), is_player=True, element="metal")

    assert _force(battle)[1] == card(FIST_OF_TEBIGONG).stats["force"]  # no base — only the Fist


def test_the_scorpion_takes_every_wu_the_opponent_played(card):
    """Disarmed: only they themselves answer for it."""
    battle = Round(stat="force")
    resolve_played_power(battle, card(FIST_OF_TEBIGONG), is_player=False, element="metal")
    resolve_played_power(battle, card(EMPEROR_SCORPION), is_player=True, element="metal")

    assert _force(battle)[1] == 3  # 3 base, no Wu


def test_the_mirror_turns_aside_the_curses_laid_on_you(card):
    """A Two-Ton Tunic cast at you is −4 force. Held up to a Mirror it is nothing at all."""
    battle = Round(stat="force")
    resolve_played_power(battle, card(TWO_TON_TUNIC), is_player=False, element="metal")
    resolve_played_power(battle, card(REVERSING_MIRROR), is_player=True, element="metal")

    assert _force(battle)[0] == 2  # the player's own base, unhurt


def test_a_curse_bites_when_no_mirror_is_up(card):
    """The other half of the pair — without it, the Mirror's test proves nothing."""
    battle = Round(stat="force")
    resolve_played_power(battle, card(TWO_TON_TUNIC), is_player=False, element="metal")

    tunic_force = card(TWO_TON_TUNIC).stats["force"]  # negative: it is a wound
    assert _force(battle)[0] == PLAYER_BASE["force"] + tunic_force


def test_the_sphere_leaves_the_caster_untouched(card):
    """It traps the *opponent*. A Wu that hurt whoever played it would be a bug, not a cost."""
    battle = Round(stat="force")
    resolve_played_power(battle, card(SPHERE_OF_JIANYU), is_player=True, element="metal")

    assert _force(battle)[0] == 2  # the player's own base, intact


def test_a_negation_lands_on_a_wu_played_after_it(card):
    """Read at scoring, not when played: a duelist cannot dodge the Scorpion by fielding late.

    A three-Wu wager is laid down one Wu at a time, so the order somebody happened to choose must
    not decide what survives.
    """
    battle = Round(stat="force")
    resolve_played_power(battle, card(EMPEROR_SCORPION), is_player=True, element="metal")
    resolve_played_power(battle, card(FIST_OF_TEBIGONG), is_player=False, element="metal")

    assert _force(battle)[1] == 3  # the Fist came second, and still counts for nothing


def test_a_negated_wu_earns_no_elemental_bonus(card):
    """Absent, not zeroed. A Wu that is not on the table cannot resonate with the ground it is not
    standing on — so the bonus goes with the stats."""
    battle = Round(stat="force")
    resolve_played_power(battle, card(FIST_OF_TEBIGONG), is_player=False, element="metal")
    resolve_played_power(battle, card(EMPEROR_SCORPION), is_player=True, element="metal")

    score_battle(battle, _ground(bonus_cancelled=False))  # metal Wu, metal ground: +1, if it counted

    assert battle.bot.result[0] == 3  # 3 base — the Fist brought neither its stats nor its element
