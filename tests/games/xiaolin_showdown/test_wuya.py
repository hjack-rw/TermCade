"""Wuya — Witchcraft: spent Wu return to her worn one further; her action calls back the lost."""

from __future__ import annotations

from termcade.core.rng import Rng

from xiaolin_showdown.logic.actions import use_power
from xiaolin_showdown.logic.constants import WEAR_LIMIT
from xiaolin_showdown.logic.models import Character, Mechanic, Power
from xiaolin_showdown.logic.settings import XiaolinSettings
from xiaolin_showdown.logic.state import XiaolinState
from xiaolin_showdown.logic.training import can_train
from xiaolin_showdown.logic.turn import RECALL, bot_turn

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
    assert state.player.points == 2  # banked by the wear rule, not lost


def test_her_action_calls_the_oldest_lost_wu_back():
    prize = wu(4, name="Oldest")
    state = _state(duelist(), _wuya(hand=[wu(1)]), lost=[prize, wu(4, name="Newer")])
    moves = bot_turn(state, XiaolinSettings(actions_per_turn=1), rng=Rng(0))
    assert [m.action for m in moves] == [RECALL]
    assert prize in state.bot.hand
    assert [c.name for c in state.lost] == ["Newer"]


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
