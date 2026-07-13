"""The two Wu that answer the lost pile: the Rooster Booster, and the wudai weapon anyone can find.

A Wu nobody wins is *lost*, not destroyed — ``XiaolinState.lost`` keeps it. The Rooster is the only
way back out of that pile, and the rule it plays by is the whole design: the **oldest** Wu, not one
its caster picked and not one a die chose. Reading the pile freely would make it a tutor for the best
Wu anyone ever failed to win; rolling for it would make it the second Wu in this game that gambles,
and there is exactly one.

The Shimo Staff is the other half of the same idea. It is a *dragon* — it lends its stats from the
boost slot and is never fielded as a card — but it was not born in anybody's hand. It waits in the
draw pile, and a Wu you found is a Wu you can lose.
"""

from __future__ import annotations

from xiaolin_showdown.logic.actions import FIZZLE_MESSAGE, usable_powers, use_power
from xiaolin_showdown.logic.battle import Ground, Round, score_battle
from xiaolin_showdown.logic.mechanics.cards import is_one_of
from xiaolin_showdown.logic.mechanics.powers import Mechanic, is_boost_slot, mechanic_of
from xiaolin_showdown.logic.mechanics.resolve import resolve_played_power

PLAYER_FORCE = 2  # the duelist this battle is scored for; the Staff's own stats sit on top of it


def _metal_ground() -> Ground:
    """A metal arena with the elemental bonus off — this is about what a dragon *lends*, nothing else."""
    return Ground(
        stats=("force", "agility", "intellect"),
        background="metal",
        player_stats={"force": PLAYER_FORCE, "agility": 0, "intellect": 0},
        bot_stats={"force": 0, "agility": 0, "intellect": 0},
        bonus_cancelled=True,
    )

ROOSTER_BOOSTER = 43
SHIMO_STAFF = 44

FIST_OF_TEBIGONG = 6
HELMET_OF_JONG = 7


def test_the_rooster_calls_back_the_oldest_lost_wu(state, card):
    """First lost, first back — not the best, and not a roll."""
    first, second = card(FIST_OF_TEBIGONG), card(HELMET_OF_JONG)
    state.lost = [first, second]
    rooster = card(ROOSTER_BOOSTER)
    state.player.hand.append(rooster)

    use_power(state, rooster)

    assert is_one_of(first, state.player.hand)  # the one lost first
    assert state.lost == [second]  # the other still waits


def test_the_rooster_gifts_the_wu_to_whoever_spent_it(state, card):
    """It comes back into a *hand*, not onto the pile — so it is yours, not up for grabs."""
    lost = card(FIST_OF_TEBIGONG)
    state.lost = [lost]
    rooster = card(ROOSTER_BOOSTER)
    state.bot.hand.append(rooster)

    use_power(state, rooster, is_player=False)

    assert is_one_of(lost, state.bot.hand)
    assert not is_one_of(lost, state.player.hand)
    assert not state.lost


def test_the_rooster_is_not_offered_while_nothing_has_been_lost(state, card, settings):
    """A Wu is never offered against an empty list — the same rule that hides Diaskopia."""
    rooster = card(ROOSTER_BOOSTER)
    state.player.hand.append(rooster)
    state.lost = []

    assert not is_one_of(rooster, usable_powers(state, settings.actions_per_turn))

    state.lost = [card(FIST_OF_TEBIGONG)]

    assert is_one_of(rooster, usable_powers(state, settings.actions_per_turn))


def test_the_rooster_fizzles_if_it_is_fired_at_an_empty_pile_anyway(state, card):
    """Gated at the vault, but the rule stands on its own: fired over nothing, it brings nothing back.

    The Wu is still spent and the turn is still gone — a fizzle is a cost, not a refund.
    """
    rooster = card(ROOSTER_BOOSTER)
    state.player.hand.append(rooster)
    state.lost = []
    hand_before, points_before = len(state.player.hand), state.player.points

    message = use_power(state, rooster)

    assert message == FIZZLE_MESSAGE  # nothing came back
    assert len(state.player.hand) == hand_before - 1  # and the Rooster itself is gone
    assert state.player.points == points_before  # spending a power never pays


def test_the_rooster_costs_the_turns_action(state, card):
    state.lost = [card(FIST_OF_TEBIGONG)]
    rooster = card(ROOSTER_BOOSTER)
    state.player.hand.append(rooster)

    use_power(state, rooster)

    assert state.actions_taken == 1


def test_the_rooster_is_spent_not_banked(state, card):
    """A power used is discarded for no points — the Wu it brought back is the whole payment."""
    state.lost = [card(FIST_OF_TEBIGONG)]
    rooster = card(ROOSTER_BOOSTER)
    state.player.hand.append(rooster)
    before = state.player.points

    use_power(state, rooster)

    assert not is_one_of(rooster, state.player.hand)
    assert state.player.points == before


def test_the_shimo_staff_goes_into_the_boost_slot(card):
    """It is a wudai weapon: it is laid as a boost, never fielded as a Wu — like the dragon it hints at."""
    staff = card(SHIMO_STAFF)

    assert is_boost_slot(staff.power)


def test_the_shimo_staff_is_a_dragon_and_not_an_amplifier(card):
    """The distinction the whole card turns on: a dragon *lends its stats*, an amplifier lends none."""
    staff = card(SHIMO_STAFF)

    assert mechanic_of(staff.power) is Mechanic.DRAGON


def test_the_shimo_staff_waits_in_the_pile_to_be_found(catalog):
    """The one dragon nobody is born holding — so it is dealt, staked, won and lost like any Wu.

    Read off the card, not off the id: move the Staff into a character's birthright and its power id
    would go negative, which is exactly what this must catch.
    """
    staff = catalog.card(SHIMO_STAFF)

    assert staff.power.id > 0  # a birthright dragon's power id is negative


def test_the_shimo_staff_lends_the_stats_it_prints_to_the_battle(card):
    """Boosted into a battle, it adds *its own printed stats* to that side — that is what a dragon does.

    The stats are read off the card, never restated, so this pins the rule and survives a rebalance.
    An amplifier here would add nothing, which is the bug this is watching for.
    """
    staff = card(SHIMO_STAFF)
    battle = Round(stat="force")

    resolve_played_power(battle, staff, is_player=True, element=staff.element)
    score_battle(battle, _metal_ground())

    assert battle.player.result[0] == PLAYER_FORCE + staff.stats["force"]
