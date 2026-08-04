"""Jack's temple AI: the instant he holds the combined Ying-Yang Yo-Yo while worn as Good Jack, flip
back to himself. Good Jack forfeits every one of his bot forms while worn, so there is no strategic
reason to stay a moment longer than the Yo-Yo makes him — unconditional, not a margin call."""

from __future__ import annotations

from copy import deepcopy

from termcade.core.rng import Rng
from termcade.core.settings import Difficulty

from factories import auto_choices

from xiaolin_showdown.logic import jack, turn
from xiaolin_showdown.logic.battle import Round
from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.constants import YIN_YANG_YOYO_ID
from xiaolin_showdown.logic.duel import Duel
from xiaolin_showdown.logic.setup import new_game
from xiaolin_showdown.logic.settings import XiaolinSettings

SETTINGS = XiaolinSettings()


def _jack_duel() -> Duel:
    cat = load_catalog()
    jack_char = next(c for c in cat.characters if c.name == "Jack_Spicer")
    state = new_game(cat, Rng(1), cat.character(1), opponent=jack_char)
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.rounds = [Round(stat="force")]
    return duel


def _hannibal_duel() -> Duel:
    cat = load_catalog()
    hannibal = next(c for c in cat.characters if c.name == "Hannibal_Roy_Bean")
    state = new_game(cat, Rng(1), cat.character(1), opponent=hannibal)
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.rounds = [Round(stat="force")]
    return duel


def _give_combined_yoyo(duel: Duel) -> None:
    cat = load_catalog()
    duel.state.bot.hand.append(deepcopy(cat.card(YIN_YANG_YOYO_ID)))


def test_flips_back_when_worn_and_holding_the_combined_yoyo():
    duel = _jack_duel()
    duel.state.bot.yoyo_flipped = True
    _give_combined_yoyo(duel)

    move = turn._self_correct_good_jack(duel.state, SETTINGS, Rng(1), Difficulty.BOSS, "Jack")

    assert move is not None
    assert duel.state.bot.yoyo_flipped is False
    assert all(c.id != YIN_YANG_YOYO_ID for c in duel.state.bot.hand)
    assert duel.state.bot_actions_taken == 1


def test_does_nothing_when_not_worn():
    duel = _jack_duel()
    _give_combined_yoyo(duel)

    move = turn._self_correct_good_jack(duel.state, SETTINGS, Rng(1), Difficulty.BOSS, "Jack")

    assert move is None
    assert duel.state.bot.yoyo_flipped is False
    assert duel.state.bot_actions_taken == 0


def test_does_nothing_without_the_combined_yoyo_in_hand():
    duel = _jack_duel()
    duel.state.bot.yoyo_flipped = True

    move = turn._self_correct_good_jack(duel.state, SETTINGS, Rng(1), Difficulty.BOSS, "Jack")

    assert move is None
    assert duel.state.bot.yoyo_flipped is True
    assert duel.state.bot_actions_taken == 0


def test_is_jack_only():
    """A different boss holding the combined Yo-Yo (however it got there) never reads this branch —
    only Jack becomes Good Jack; anyone else's `yoyo_flipped` is a plain affiliation cosmetic."""
    duel = _hannibal_duel()
    duel.state.bot.yoyo_flipped = True
    _give_combined_yoyo(duel)

    move = turn._self_correct_good_jack(duel.state, SETTINGS, Rng(1), Difficulty.BOSS, "Hannibal")

    assert move is None
    assert duel.state.bot.yoyo_flipped is True


def test_boss_order_reaches_it_ahead_of_banking():
    duel = _jack_duel()
    duel.state.bot.yoyo_flipped = True
    _give_combined_yoyo(duel)

    move = turn._boss_acts(duel.state, SETTINGS, Rng(1), Difficulty.BOSS, jack.GOOD_JACK_NAME)

    assert move is not None
    assert move.action == turn.POWER
    assert duel.state.bot.yoyo_flipped is False
