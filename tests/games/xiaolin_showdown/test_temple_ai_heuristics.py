"""The bot's temple-phase decision heuristics — the audit found most of ``temple_ai.py`` unpinned:
of ~13 predicates dispatched by ``choose_temple_power``, only a handful had any direct test. One
test per predicate here, each pinning the actual decision boundary (the constant it compares
against), not just a smoke check that it runs.
"""

from __future__ import annotations

from xiaolin_showdown.logic.flow import temple_ai
from xiaolin_showdown.logic.config.settings import XiaolinSettings
from xiaolin_showdown.logic.schema.models import Mechanic
from xiaolin_showdown.logic.schema.state import XiaolinState

from factories import duelist, wu

DEFAULT = XiaolinSettings()


def _state(player, bot, **kwargs) -> XiaolinState:
    return XiaolinState(catalog=None, player=player, bot=bot, **kwargs)  # type: ignore[arg-type]


# --- the Lantern: swap hands when the other one is the better arsenal by a real margin -----------


def test_worth_swapping_is_true_at_the_margin():
    me = duelist(hand=[wu(0, 0, 0)])
    them = duelist(hand=[wu(temple_ai.SWAP_MARGIN, 0, 0)])
    state = _state(me, them)
    assert temple_ai._worth_swapping(state, is_player=True) is True


def test_worth_swapping_is_false_short_of_the_margin():
    me = duelist(hand=[wu(0, 0, 0)])
    them = duelist(hand=[wu(temple_ai.SWAP_MARGIN - 1, 0, 0)])
    state = _state(me, them)
    assert temple_ai._worth_swapping(state, is_player=True) is False


def test_worth_swapping_is_false_with_no_hand_to_swap_into():
    me = duelist(hand=[wu(0, 0, 0)])
    them = duelist(hand=[])
    state = _state(me, them)
    assert temple_ai._worth_swapping(state, is_player=True) is False


# --- expected_points: the gamble Wu is the only one that isn't its own face ----------------------


def test_expected_points_is_the_gamble_spread_average():
    low, high = temple_ai.GAMBLE_SPREAD
    gamble = wu(mechanic=Mechanic.GAMBLE, points=999)  # points ignored — it's the spread that pays
    assert temple_ai.expected_points(gamble) == (low + high) / 2


def test_expected_points_is_just_the_points_otherwise():
    assert temple_ai.expected_points(wu(points=7)) == 7.0


# --- the Ruby of Ramses: a Wu for a Wu, and it pays them ------------------------------------------


def test_worth_shoving_needs_a_real_weapon():
    them = duelist(hand=[wu(temple_ai.REPULSION_THRESHOLD, 0, 0), wu(0, 0, 0)])
    state = _state(duelist(), them)
    assert temple_ai._worth_shoving(state, is_player=True) is True


def test_worth_shoving_refuses_a_weak_hand():
    them = duelist(hand=[wu(temple_ai.REPULSION_THRESHOLD - 1, 0, 0), wu(0, 0, 0)])
    state = _state(duelist(), them)
    assert temple_ai._worth_shoving(state, is_player=True) is False


def test_worth_shoving_never_empties_the_last_card():
    """A deposit may never empty a hand — theirs no more than yours."""
    them = duelist(hand=[wu(99, 0, 0)])  # a monster weapon, but it's their only card
    state = _state(duelist(), them)
    assert temple_ai._worth_shoving(state, is_player=True) is False


def test_shove_to_deck_when_the_points_would_carry_them_to_the_win():
    settings = XiaolinSettings(point_limit=10)
    them = duelist(hand=[wu(0, 0, 0, points=10)])
    them.points = 5
    state = _state(duelist(), them)
    assert temple_ai._shove_to_deck(state, settings, is_player=True) is True


def test_shove_to_deck_is_false_far_from_the_win():
    settings = XiaolinSettings(point_limit=100)
    them = duelist(hand=[wu(0, 0, 0, points=1)])
    them.points = 0
    state = _state(duelist(), them)
    assert temple_ai._shove_to_deck(state, settings, is_player=True) is False


# --- the Mind Reader Conch: buy the initiative, when it is pointing the wrong way ----------------


def test_initiative_is_wrong_on_a_tie():
    """A tie is a coin toss, and a coin toss is always worth buying out of."""
    me = duelist(hand=[])
    them = duelist(hand=[])
    state = _state(me, them)
    assert temple_ai._initiative_is_wrong(state, is_player=True) is True


def test_initiative_is_wrong_when_the_lead_disagrees_with_what_is_wanted():
    # `_wants_initiative` reads the STATS (a weak hand is glad to be rid of it); the actual lead
    # comes from card `initiative_bonus`, a wholly separate channel — so a weak hand can still hold
    # the lead it doesn't want, and that's exactly the mismatch the Conch is spent to fix.
    me = duelist(hand=[wu(0, 0, 0, bonus=3)], stats={"force": 0, "agility": 0, "intellect": 0})
    them = duelist(hand=[], stats={"force": 5, "agility": 5, "intellect": 5})
    state = _state(me, them)
    assert temple_ai._wants_initiative(state, is_player=True) is False
    assert temple_ai._initiative_is_wrong(state, is_player=True) is True


# --- Prognosis: worth casting only when this duelist would not hold the ground anyway -------------


def test_worth_foreseeing_when_trailing_on_initiative():
    # Initiative comes from card `initiative_bonus`, not from raw stats — a bonus card in the
    # opponent's hand is what actually puts them ahead.
    me = duelist(hand=[])
    them = duelist(hand=[wu(0, 0, 0, bonus=3)])
    state = _state(me, them)
    assert temple_ai._worth_foreseeing(state, is_player=True) is True


def test_worth_foreseeing_is_false_while_already_leading():
    me = duelist(hand=[wu(0, 0, 0, bonus=3)])
    them = duelist(hand=[])
    state = _state(me, them)
    assert temple_ai._worth_foreseeing(state, is_player=True) is False


# --- the Reverso: the most-recently-used Wu, back to hand, if it's worth reclaiming ---------------


def test_worth_refreshing_needs_a_real_weapon():
    state = _state(duelist(), duelist(), used=[wu(temple_ai.REFRESH_MARGIN, 0, 0)])
    assert temple_ai._worth_refreshing(state) is True


def test_worth_refreshing_refuses_a_scrap():
    state = _state(duelist(), duelist(), used=[wu(temple_ai.REFRESH_MARGIN - 1, 0, 0)])
    assert temple_ai._worth_refreshing(state) is False


def test_worth_refreshing_is_false_with_nothing_used_yet():
    state = _state(duelist(), duelist(), used=[])
    assert temple_ai._worth_refreshing(state) is False


# --- the Glove of Jisaku: the best Wu on the shelf, only if it beats a plain Draw ------------------


def test_worth_reaching_for_a_real_upgrade():
    me = duelist(deck=[wu(0, 0, 0), wu(temple_ai.ATTRACTION_MARGIN, 0, 0)])
    state = _state(me, duelist())
    assert temple_ai._worth_reaching_for(state, is_player=True) is True


def test_worth_reaching_for_is_false_short_of_the_margin():
    me = duelist(deck=[wu(0, 0, 0), wu(temple_ai.ATTRACTION_MARGIN - 1, 0, 0)])
    state = _state(me, duelist())
    assert temple_ai._worth_reaching_for(state, is_player=True) is False


def test_worth_reaching_for_is_false_with_an_empty_shelf():
    me = duelist(deck=[])
    state = _state(me, duelist())
    assert temple_ai._worth_reaching_for(state, is_player=True) is False


# --- Euthymia: the oldest lost Wu, only if it beats a plain Draw ----------------------------------


def test_worth_reviving_needs_a_real_weapon():
    state = _state(duelist(), duelist(), lost=[wu(temple_ai.REVIVAL_MARGIN, 0, 0)])
    assert temple_ai._worth_reviving(state) is True


def test_worth_reviving_refuses_a_scrap():
    state = _state(duelist(), duelist(), lost=[wu(temple_ai.REVIVAL_MARGIN - 1, 0, 0)])
    assert temple_ai._worth_reviving(state) is False


def test_worth_reviving_fizzles_on_an_empty_lost_pile():
    state = _state(duelist(), duelist(), lost=[])
    assert temple_ai._worth_reviving(state) is False


# --- Chronokinesis: a Wu off the pile, sight unseen — priced against the hand's own average --------


def test_worth_drawing_when_chrono_is_the_weakest_thing_held():
    chrono = wu(0, 0, 0, mechanic=Mechanic.DRAW)
    me = duelist(hand=[chrono, wu(10, 0, 0)])
    state = _state(me, duelist(), card_deck=[wu(0, 0, 0)])
    assert temple_ai._worth_drawing(state, DEFAULT, is_player=True) is True


def test_worth_drawing_is_false_when_chrono_already_beats_the_hand():
    chrono = wu(10, 0, 0, mechanic=Mechanic.DRAW)
    me = duelist(hand=[chrono, wu(0, 0, 0)])
    state = _state(me, duelist(), card_deck=[wu(0, 0, 0)])
    assert temple_ai._worth_drawing(state, DEFAULT, is_player=True) is False


def test_worth_drawing_is_false_with_no_pile_left():
    chrono = wu(0, 0, 0, mechanic=Mechanic.DRAW)
    me = duelist(hand=[chrono])
    state = _state(me, duelist(), card_deck=[])
    assert temple_ai._worth_drawing(state, DEFAULT, is_player=True) is False


def test_worth_drawing_is_false_with_no_chrono_in_hand():
    me = duelist(hand=[wu(0, 0, 0)])
    state = _state(me, duelist(), card_deck=[wu(0, 0, 0)])
    assert temple_ai._worth_drawing(state, DEFAULT, is_player=True) is False
