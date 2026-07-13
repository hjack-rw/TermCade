"""The width of a field is the size of the bet.

Every wagered Wu lands at once and they are summed, and the loser forfeits every Wu they fielded **to
the winner**. So a best-of-three is not a bigger best-of-one: it is the same fight at triple stakes.

That is what the opponent has to price. It takes the *widest field it is still ahead in* — and when it
is behind in all of them, the narrowest bet on offer, which is what a person does when they are losing.

The hands here are **built**, not drawn from the pool, and that is deliberate. The decisive case is a
duelist ahead at one Wu and behind at two — and the printed pool cannot express it: ``duel_value``
ceilings at 5 and a dozen Wu sit on that ceiling, so "one monster" is never actually bigger than the
other hand's best. Reaching for the catalog here tests the wrong branch. It did: the monster hand
refused the wide bet through the *losing* fallback, and the case the whole rule exists for went
uncovered while the test read green.
"""

from __future__ import annotations

import pytest

from xiaolin_showdown.logic.bot import choose_wager
from xiaolin_showdown.logic.models import Card, Mechanic, Power
from xiaolin_showdown.logic.turn import duel_value

_PLAIN = Power(id=0, name="", mechanic=Mechanic.PRINTED_STATS, description="")


def wu(force: int) -> Card:
    """A Wu worth exactly ``force`` in a showdown — ``duel_value`` sums the magnitudes a card prints."""
    return Card(
        id=0,
        name=f"Wu({force})",
        stats={"force": force, "agility": 0, "intellect": 0},
        power=_PLAIN,
        element="metal",
        type="item",
        points=1,
    )


@pytest.fixture(autouse=True)
def _a_built_wu_is_worth_what_it_prints():
    """Every hand below is built on this. If ``duel_value`` ever stops agreeing, fail *here* — rather
    than letting each test quietly measure a margin it did not mean."""
    assert [duel_value(wu(n)) for n in (0, 3, 5)] == [0, 3, 5]


def test_a_deep_bench_takes_the_wide_bet():
    """Three Wu that all carry their weight: widening stakes more on a fight it is already winning."""
    deep = [wu(5), wu(5), wu(5)]
    thin = [wu(1), wu(1), wu(1)]

    assert choose_wager([1, 2, 3], deep, thin) == 3


def test_one_monster_and_two_trinkets_refuses_the_wide_bet():
    """Ahead at one Wu, behind at two — the case the rule exists for.

    The monster wins the narrow fight outright. Widening drags the trinkets in, hands the field back,
    and stakes two more Wu on losing it. The old rung-by-rung rule could not see this.
    """
    spiky = [wu(5), wu(0), wu(0)]  # margins: +2 at one Wu, -1 at two, -4 at three
    steady = [wu(3), wu(3), wu(3)]

    assert choose_wager([1, 2, 3], spiky, steady) == 1


def test_it_widens_only_as_far_as_it_stays_ahead():
    """Ahead at one and at two, behind at three: it takes the two.

    The edge of the rule. A duelist that widened to the maximum whenever it led *at all* passes every
    other test in this file and fails this one.
    """
    two_good = [wu(5), wu(5), wu(0)]
    steady = [wu(4), wu(3), wu(3)]
    #   one Wu:    5 - 4 = +1   ahead
    #   two Wu:   10 - 7 = +3   ahead
    # three Wu:   10 - 10 = 0   level, and level is not ahead — so the third Wu stays in hand

    assert choose_wager([1, 2, 3], two_good, steady) == 2


def test_a_duelist_behind_on_every_front_takes_the_smallest_bet():
    """Losing is not a reason to stake more. It is the reason to stake less."""
    weak = [wu(1), wu(1), wu(1)]
    strong = [wu(5), wu(5), wu(5)]

    assert choose_wager([1, 2, 3], weak, strong) == 1


def test_a_level_field_is_no_reason_to_raise():
    """Equal hands carry a margin of zero, and zero is not ahead.

    Both hands come from one pool, so this is the *common* case rather than a corner — and it is why
    the rule reads ``margin > 0`` and not ``>= 0``. A coin flip is not a bet worth trebling.
    """
    assert choose_wager([1, 2, 3], [wu(3), wu(3), wu(3)], [wu(3), wu(3), wu(3)]) == 1


def test_it_never_stakes_a_width_it_was_not_offered():
    """The options are the hands' floor — a duelist can never be made to stake what they do not hold."""
    deep = [wu(5), wu(5), wu(5)]
    thin = [wu(1), wu(1), wu(1)]

    assert choose_wager([1, 2], deep, thin) == 2  # it would take three; three is not on the table


def test_no_options_at_all_is_a_single_wu():
    assert choose_wager([], [wu(5)], [wu(1)]) == 1
