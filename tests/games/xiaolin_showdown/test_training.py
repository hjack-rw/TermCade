"""The training bar: losses and spent turns fill it; a full bar raises one stat, then climbs again.

The payout leaves the bar showing full until the turn turns over — only then does it reset to 0 and
start climbing toward the next raise. Nothing ever trains past the stat cap.
"""

from __future__ import annotations

from xiaolin_showdown.logic.config.settings import XiaolinSettings
from xiaolin_showdown.logic.flow.actions import train, train_blocked
from xiaolin_showdown.logic.schema.models import Mechanic, Player, Power
from xiaolin_showdown.logic.schema.state import XiaolinState
from xiaolin_showdown.logic.flow.training import (
    add_progress,
    boss_loss_fill,
    can_train,
    payout_ready,
    pick_stat,
    raise_stat,
    record_showdown,
    trainable_stats,
    turn_over,
)

from factories import duelist, wu

DEFAULT = XiaolinSettings()
STAT_CAP = DEFAULT.stat_cap
TRAIN_LENGTH = DEFAULT.train_length_player
JACK_LOSS_FILL = DEFAULT.train_length_bot  # one defeat is a full bar — see training.record_showdown
JACK_FORCE_CAP = DEFAULT.stat_cap - 1  # one below the universal cap — see training._JACK_FORCE_MARGIN


def _state(player: Player, bot: Player) -> XiaolinState:
    return XiaolinState(catalog=None, player=player, bot=bot, card_deck=[])  # type: ignore[arg-type]


def _capped() -> Player:
    return duelist(stats={"force": STAT_CAP, "agility": STAT_CAP, "intellect": STAT_CAP})


def test_losing_a_showdown_fills_the_losers_bar():
    state = _state(duelist(stats={"force": 2}), duelist())
    record_showdown(state, DEFAULT, player_won=False)
    assert (state.player.training, state.bot.training) == (1, 0)


def test_winning_teaches_the_winner_nothing():
    state = _state(duelist(stats={"force": 2}), duelist())
    record_showdown(state, DEFAULT, player_won=True)
    assert state.player.training == 0


def test_a_duelist_at_the_cap_never_accrues_progress():
    boss = _capped()
    add_progress(boss, DEFAULT, TRAIN_LENGTH)
    assert boss.training == 0


def test_progress_clamps_at_a_full_bar():
    player = duelist(stats={"force": 2})
    add_progress(player, DEFAULT, TRAIN_LENGTH + 5)
    assert player.training == TRAIN_LENGTH


def test_a_full_bar_waits_for_its_stat_pick():
    player = duelist(stats={"force": 2})
    assert add_progress(player, DEFAULT, TRAIN_LENGTH) and payout_ready(player, DEFAULT)


def test_the_payout_raises_the_chosen_stat():
    player = duelist(stats={"force": 2, "agility": 3})
    player.training = TRAIN_LENGTH
    raise_stat(player, "agility")
    assert player.character.stats["agility"] == 4


def test_the_bar_shows_full_until_the_turn_turns_over():
    player = duelist(stats={"force": 2})
    player.training = TRAIN_LENGTH
    raise_stat(player, "force")
    assert player.training == TRAIN_LENGTH and not payout_ready(player, DEFAULT)
    turn_over(player)
    assert player.training == 0


def test_a_taken_payout_blocks_the_climb_until_the_reset():
    player = duelist(stats={"force": 2})
    player.training = TRAIN_LENGTH
    raise_stat(player, "force")
    assert not add_progress(player, DEFAULT)
    turn_over(player)
    assert add_progress(player, DEFAULT) is False and player.training == 1


def test_training_repeats_after_the_reset():
    player = duelist(stats={"force": 1, "agility": 1, "intellect": 1})
    for expected in (2, 3):
        player.training = TRAIN_LENGTH
        raise_stat(player, "force")
        turn_over(player)
        assert player.character.stats["force"] == expected and can_train(player, DEFAULT)


def test_only_stats_under_the_cap_are_on_offer():
    player = duelist(stats={"force": STAT_CAP, "agility": 3, "intellect": 4})
    assert trainable_stats(player, DEFAULT) == ["agility", "intellect"]


def test_the_bot_shores_up_its_lowest_stat_with_room():
    bot = duelist(stats={"force": STAT_CAP, "agility": 2, "intellect": 1})
    assert pick_stat(bot, DEFAULT) == "intellect"


def test_the_bots_loss_payout_is_taken_on_the_spot():
    state = _state(duelist(), duelist(stats={"force": 1, "agility": 3, "intellect": 3}))
    state.bot.training = TRAIN_LENGTH - 1
    assert record_showdown(state, DEFAULT, player_won=True) == "force"
    assert state.bot.character.stats["force"] == 2


def _jack(stats: dict[str, int]) -> Player:
    player = duelist(stats=stats, tier="boss")
    player.character.power = Power(-8, "Jack-Bot", Mechanic.BOT, "")
    return player


def test_jacks_own_loss_teaches_him_the_whole_bar_at_once():
    # JACK_LOSS_FILL == TRAIN_LENGTH: one defeat is a full bar, not a partial fill — the only boss
    # for whom a single loss ever pays out on the spot from empty.
    state = _state(duelist(), _jack({"force": 3, "agility": 3, "intellect": 7}))
    assert record_showdown(state, DEFAULT, player_won=True) == "force"
    assert state.bot.character.stats["force"] == 4


def test_a_normal_boss_still_uses_the_shared_boss_rate_not_jacks():
    # Same tier="boss", same starting bar — a non-Jack boss's own power keeps him off this constant
    # entirely; the standard boss_loss_fill (double the ordinary fill) still gates him.
    state = _state(duelist(), duelist(stats={"force": 3, "agility": 3, "intellect": 3}, tier="boss"))
    assert record_showdown(state, DEFAULT, player_won=True) is None
    assert state.bot.training < JACK_LOSS_FILL


def test_jacks_force_caps_below_stat_cap_while_agility_does_not():
    # "Stronger is the acceptable gap" — force stops at JACK_FORCE_CAP even though STAT_CAP is
    # higher; agility trains all the way to STAT_CAP, same as any dragon.
    jack = _jack({"force": JACK_FORCE_CAP, "agility": STAT_CAP - 1, "intellect": 7})
    assert trainable_stats(jack, DEFAULT) == ["agility"]
    jack.training = TRAIN_LENGTH
    raise_stat(jack, pick_stat(jack, DEFAULT))
    assert jack.character.stats == {"force": JACK_FORCE_CAP, "agility": STAT_CAP, "intellect": 7}


def test_the_players_loss_payout_waits_for_their_choice():
    state = _state(duelist(stats={"force": 2}), duelist())
    state.player.training = TRAIN_LENGTH - 1
    assert record_showdown(state, DEFAULT, player_won=False) is None
    assert payout_ready(state.player, DEFAULT)


def test_the_train_action_spends_the_turns_action():
    state = _state(duelist(stats={"force": 2}), duelist())
    train(state, DEFAULT)
    assert (state.actions_taken, state.player.training) == (1, 1)


def test_a_waiting_payout_is_claimable_even_on_a_spent_turn():
    state = _state(duelist(stats={"force": 2}), duelist())
    state.player.training = TRAIN_LENGTH
    state.actions_taken = 1
    assert train_blocked(state, 1, DEFAULT) is None


def test_a_spent_turn_blocks_plain_training():
    state = _state(duelist(stats={"force": 2}), duelist())
    state.actions_taken = 1
    assert train_blocked(state, 1, DEFAULT) is not None


def test_every_stat_at_the_cap_blocks_the_action():
    state = _state(_capped(), duelist())
    assert train_blocked(state, 1, DEFAULT) is not None


def test_a_just_taken_payout_blocks_the_action_until_the_reset():
    state = _state(duelist(stats={"force": 2}), duelist())
    state.player.training = TRAIN_LENGTH
    raise_stat(state.player, "force")
    assert train_blocked(state, 1, DEFAULT) is not None


def test_a_wu_never_unlocks_training():
    # Held Wu raise a duelist's fielded stats, never the base stats training reads.
    player = _capped()
    player.hand.append(wu(2, 2, 2))
    assert not can_train(player, DEFAULT)


def test_the_bot_spends_its_temple_turn_on_a_nearly_full_bar():
    from termcade.core.rng import Rng
    from xiaolin_showdown.logic.flow.turn import TRAIN, bot_turn

    state = _state(duelist(), duelist(stats={"force": 1, "agility": 3, "intellect": 3}))
    state.bot.hand = [wu(1), wu(1)]
    state.bot.deck = [wu(1)]
    state.bot.training = TRAIN_LENGTH - 1
    moves = bot_turn(state, XiaolinSettings(actions_per_turn_bot=1), rng=Rng(0))
    assert [m.action for m in moves] == [TRAIN]
    assert state.bot.character.stats["force"] == 2


def test_the_turnover_resets_a_cashed_bar():
    from termcade.core.rng import Rng
    from xiaolin_showdown.logic.flow.turn import refill_hands

    state = _state(duelist(stats={"force": 2}, hand=[wu(1), wu(1)]), duelist(hand=[wu(1), wu(1)]))
    state.player.training = TRAIN_LENGTH
    raise_stat(state.player, "force")
    refill_hands(state, XiaolinSettings(), rng=Rng(0))
    assert state.player.training == 0 and not state.player.just_trained


def test_a_loss_to_a_boss_teaches_double():
    state = _state(duelist(stats={"force": 2}), duelist(tier="boss"))
    record_showdown(state, DEFAULT, player_won=False)
    assert state.player.training == boss_loss_fill(DEFAULT)


def test_a_boss_run_gives_the_player_three_actions():
    from xiaolin_showdown.logic.config.settings import BOSS_PLAYER_ACTIONS, player_actions

    boss_run = _state(duelist(), duelist(tier="boss"))
    plain_run = _state(duelist(), duelist())
    assert player_actions(boss_run, XiaolinSettings()) == BOSS_PLAYER_ACTIONS
    assert player_actions(plain_run, XiaolinSettings()) == XiaolinSettings().actions_per_turn_player


def test_the_boss_itself_gets_no_extra_actions():
    # The budget is the PLAYER's; the opponent loop reads the settings' own count.
    from termcade.core.rng import Rng
    from xiaolin_showdown.logic.flow.turn import bot_turn

    state = _state(duelist(), duelist(tier="boss", stats={"force": 5}, hand=[wu(1)], deck=[wu(1)]))
    bot_turn(state, XiaolinSettings(actions_per_turn_bot=1), rng=Rng(0))
    assert state.bot_actions_taken <= 1


def test_the_console_fill_command_readies_the_payout():
    from types import SimpleNamespace

    from termcade.core.settings import Settings
    from xiaolin_showdown.console import fill

    state = _state(duelist(stats={"force": 2}), duelist())
    fill(SimpleNamespace(state=state, settings=SimpleNamespace(current=Settings())), [])
    assert payout_ready(state.player, DEFAULT)


def test_a_save_keeps_the_bar_and_the_raised_stats(state):
    state.player.training = TRAIN_LENGTH
    stat = trainable_stats(state.player, DEFAULT)[0]
    raise_stat(state.player, stat)
    trained = state.player.character.stats[stat]
    restored = XiaolinState.restore(state.snapshot(), None)
    assert restored.player.training == TRAIN_LENGTH
    assert restored.player.just_trained
    assert restored.player.character.stats[stat] == trained
