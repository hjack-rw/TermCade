"""Wuya — Witchcraft: spent Wu return to her worn one further; her action calls back the lost."""

from __future__ import annotations

from termcade.core.rng import Rng

from xiaolin_showdown.logic.flow.actions import use_power
from xiaolin_showdown.logic.schema.models import Character, Mechanic, Power
from xiaolin_showdown.logic.config.settings import XiaolinSettings
from xiaolin_showdown.logic.schema.state import XiaolinState
from xiaolin_showdown.logic.characters.wuya import WITCH_RECALL_LIMIT, WITCH_RECALL_MARGIN
from xiaolin_showdown.logic.flow.training import can_train
from xiaolin_showdown.logic.flow.turn import RECALL, bot_turn
from xiaolin_showdown.logic.flow.values import bank_value

from factories import duelist, wu

WITCHCRAFT = Power(-6, "Witchcraft", Mechanic.WITCHCRAFT, "", 0)
DEFAULT = XiaolinSettings()
WEAR_LIMIT = DEFAULT.wear_limit


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
    use_power(state, chrono, DEFAULT, rng=Rng(0))
    assert chrono in state.player.hand  # restored, not discarded
    assert chrono.uses == 1


def test_the_third_witchery_vaults_the_wu():
    chrono = wu(1, mechanic=Mechanic.DRAW, name="Falcon's Eye", points=2)
    chrono.uses = WEAR_LIMIT - 1
    state = _state(_wuya(hand=[chrono]), duelist(), pile=[wu(1, name="Drawn")])
    use_power(state, chrono, DEFAULT, rng=Rng(0))
    assert chrono not in state.player.hand
    assert state.player.points == chrono.points  # banked by the wear rule, not lost


def test_her_action_calls_the_most_valuable_lost_wu_back():
    # Worth read off the margin, so retuning what she stoops for retunes the test. Her bond finds the
    # best Wu, not the oldest: a scrap sits ahead of the prize in the pile and is left behind.
    prize = wu(WITCH_RECALL_MARGIN + 2, name="Prize")
    state = _state(duelist(), _wuya(hand=[wu(1)]), lost=[wu(WITCH_RECALL_MARGIN, name="Scrap"), prize])
    moves = bot_turn(state, XiaolinSettings(actions_per_turn_bot=1), rng=Rng(0))
    assert [m.action for m in moves] == [RECALL]
    assert prize in state.bot.hand
    assert [c.name for c in state.lost] == ["Scrap"]


def test_the_witchcraft_runs_out_of_recalls():
    """The recall is a resource, not a tap: a run's whole allowance is ``WITCH_RECALL_LIMIT``.

    Uncapped she never runs out of ammunition, and the only counterplay left is outrunning her to the
    point target. Read off the limit so raising the allowance raises the test with it.
    """
    worth = [wu(WITCH_RECALL_MARGIN, name=f"Lost{n}") for n in range(WITCH_RECALL_LIMIT + 1)]
    state = _state(duelist(), _wuya(hand=[wu(1)]), lost=list(worth))
    state.witch_recalls = WITCH_RECALL_LIMIT  # she has spent the run's allowance

    moves = bot_turn(state, XiaolinSettings(actions_per_turn_bot=1), rng=Rng(0))

    assert all(m.action != RECALL for m in moves)
    assert len(state.lost) == len(worth), "the lost pile was raided past the allowance"


def test_each_recall_spends_one_of_the_allowance():
    """Guards the test above: the counter must actually climb, or the cap can never be reached."""
    state = _state(duelist(), _wuya(hand=[wu(1)]), lost=[wu(WITCH_RECALL_MARGIN, name="Oldest")])

    bot_turn(state, XiaolinSettings(actions_per_turn_bot=1), rng=Rng(0))

    assert state.witch_recalls == 1


def test_she_banks_at_everyone_elses_rate():
    """No duelist banks at a special rate — including her.

    A special deposit-rate penalty for her was built and reverted the same day: it made her runs
    longer without making her lose more, which only worked against her difficulty. This pins the
    reversion.
    """
    rich = wu(1, name="Rich", points=5)
    assert bank_value(rich, Rng(0)) == rich.points


def test_a_scrap_is_not_worth_her_action():
    state = _state(duelist(), _wuya(hand=[wu(1), wu(1)]), lost=[wu(1, name="Scrap")])
    moves = bot_turn(state, XiaolinSettings(actions_per_turn_bot=1), rng=Rng(0))
    assert all(m.action != RECALL for m in moves)


def test_six_across_the_board_is_still_master():
    assert not can_train(_wuya(), DEFAULT)


def test_a_chosen_opponent_overrides_the_roster_pick(catalog):
    from xiaolin_showdown.logic.flow.setup import new_game

    state = new_game(catalog, Rng(1), catalog.character(1), roster="boss", opponent=catalog.character(12))
    assert state.bot.character.name == "Wuya"
    assert state.bot.inalienable_hand == []  # witchcraft grants no signature Wu


def test_witchcraft_is_hers_alone() -> None:
    # A plain duelist's spent Wu still leaves the hand.
    chrono = wu(1, mechanic=Mechanic.DRAW, name="Falcon's Eye", points=2)
    state = _state(duelist(hand=[chrono]), duelist(), pile=[wu(1, name="Drawn")])
    use_power(state, chrono, DEFAULT, rng=Rng(0))
    assert chrono not in state.player.hand and state.player.points == 0
