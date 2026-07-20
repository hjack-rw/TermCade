"""Wuya — Witchcraft: spent Wu return to her worn one further; her action calls back the lost."""

from __future__ import annotations

from termcade.core.rng import Rng

from xiaolin_showdown.logic.actions import use_power
from xiaolin_showdown.logic.constants import WEAR_LIMIT
from xiaolin_showdown.logic.models import Character, Mechanic, Power
from xiaolin_showdown.logic.settings import XiaolinSettings
from xiaolin_showdown.logic.state import XiaolinState
from xiaolin_showdown.logic.temple_ai import WITCH_RECALL_LIMIT, WITCH_RECALL_MARGIN
from xiaolin_showdown.logic.training import can_train
from xiaolin_showdown.logic.turn import RECALL, bank_value, bot_turn

from factories import duelist, wu

WITCHCRAFT = Power(-6, "Witchcraft", Mechanic.WITCHCRAFT, "", 0)


def _wuya(**kwargs):
    witch = duelist(**kwargs)
    witch.character = Character(
        12, "Wuya", {"force": 6, "agility": 6, "intellect": 6}, WITCHCRAFT, "heylin", False, tier="boss"
    )
    return witch


def _state(player, bot, *, pile=(), lost=()) -> XiaolinState:
    state = XiaolinState(catalog=None, player=player, bot=bot, card_deck=list(pile))  # type: ignore[arg-type]
    state.lost = list(lost)
    return state


def test_a_spent_wu_returns_to_her_worn_one_further():
    chrono = wu(1, mechanic=Mechanic.DRAW, name="Falcon's Eye", points=2)
    state = _state(_wuya(hand=[chrono]), duelist(), pile=[wu(1, name="Drawn")])
    use_power(state, chrono, rng=Rng(0))
    assert chrono in state.player.hand  # restored, not discarded
    assert chrono.uses == 1


def test_the_third_witchery_vaults_the_wu():
    chrono = wu(1, mechanic=Mechanic.DRAW, name="Falcon's Eye", points=2)
    chrono.uses = WEAR_LIMIT - 1
    state = _state(_wuya(hand=[chrono]), duelist(), pile=[wu(1, name="Drawn")])
    use_power(state, chrono, rng=Rng(0))
    assert chrono not in state.player.hand
    assert state.player.points == chrono.points  # banked by the wear rule, not lost


def test_her_action_calls_the_oldest_lost_wu_back():
    # Worth the action: read off the margin, so retuning what she stoops for retunes the test.
    prize = wu(WITCH_RECALL_MARGIN, name="Oldest")
    state = _state(duelist(), _wuya(hand=[wu(1)]), lost=[prize, wu(WITCH_RECALL_MARGIN, name="Newer")])
    moves = bot_turn(state, XiaolinSettings(actions_per_turn=1), rng=Rng(0))
    assert [m.action for m in moves] == [RECALL]
    assert prize in state.bot.hand
    assert [c.name for c in state.lost] == ["Newer"]


def test_the_witchcraft_runs_out_of_recalls():
    """The recall is a resource, not a tap: a run's whole allowance is ``WITCH_RECALL_LIMIT``.

    Uncapped she never runs out of ammunition, and the only counterplay left is outrunning her to the
    point target. Read off the limit so raising the allowance raises the test with it.
    """
    worth = [wu(WITCH_RECALL_MARGIN, name=f"Lost{n}") for n in range(WITCH_RECALL_LIMIT + 1)]
    state = _state(duelist(), _wuya(hand=[wu(1)]), lost=list(worth))
    state.witch_recalls = WITCH_RECALL_LIMIT  # she has spent the run's allowance

    moves = bot_turn(state, XiaolinSettings(actions_per_turn=1), rng=Rng(0))

    assert all(m.action != RECALL for m in moves)
    assert len(state.lost) == len(worth), "the lost pile was raided past the allowance"


def test_each_recall_spends_one_of_the_allowance():
    """Guards the test above: the counter must actually climb, or the cap can never be reached."""
    state = _state(duelist(), _wuya(hand=[wu(1)]), lost=[wu(WITCH_RECALL_MARGIN, name="Oldest")])

    bot_turn(state, XiaolinSettings(actions_per_turn=1), rng=Rng(0))

    assert state.witch_recalls == 1


def test_she_banks_at_everyone_elses_rate():
    """No duelist banks at a special rate — including her.

    A "Shen Gong Wu hunger" halving her deposits was built and reverted the same day: it stopped her
    CLOSING rather than making her score less, her runs went 7.7 showdowns to 13.8, and the longer
    runs fed the player's training bar until she was the easiest boss in the tier (8.8% -> 20.8%).
    """
    rich = wu(1, name="Rich", points=5)
    assert bank_value(rich, Rng(0)) == rich.points


def test_a_scrap_is_not_worth_her_action():
    state = _state(duelist(), _wuya(hand=[wu(1), wu(1)]), lost=[wu(1, name="Scrap")])
    moves = bot_turn(state, XiaolinSettings(actions_per_turn=1), rng=Rng(0))
    assert all(m.action != RECALL for m in moves)


def test_six_across_the_board_is_still_master():
    assert not can_train(_wuya())


def test_a_chosen_opponent_overrides_the_roster_pick(catalog):
    from xiaolin_showdown.logic.setup import new_game

    state = new_game(catalog, Rng(1), catalog.character(1), roster="boss", opponent=catalog.character(12))
    assert state.bot.character.name == "Wuya"
    assert state.bot.inalienable_hand == []  # witchcraft grants no signature Wu


def test_witchcraft_is_hers_alone() -> None:
    # A plain duelist's spent Wu still leaves the hand.
    chrono = wu(1, mechanic=Mechanic.DRAW, name="Falcon's Eye", points=2)
    state = _state(duelist(hand=[chrono]), duelist(), pile=[wu(1, name="Drawn")])
    use_power(state, chrono, rng=Rng(0))
    assert chrono not in state.player.hand and state.player.points == 0
