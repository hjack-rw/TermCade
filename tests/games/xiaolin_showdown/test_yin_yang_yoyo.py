"""Ying Yo-Yo / Yang Yo-Yo — names a stat, swapped with the opponent's Character for the rest of
the Showdown; flips the caster's affiliation for the rest of the run. Jack alone becomes Good Jack."""

from __future__ import annotations

from copy import deepcopy

from termcade.core.rng import Rng

from factories import auto_choices

from xiaolin_showdown.logic.characters import jack
from xiaolin_showdown.logic.flow.actions import (
    can_combine_yoyo,
    can_self_correct_yoyo,
    combine_yoyo,
    self_correct_yoyo,
)
from xiaolin_showdown.logic.flow.battle import Round
from xiaolin_showdown.logic.schema.catalog import load_catalog
from xiaolin_showdown.logic.schema.constants import YANG_YOYO_ID, YING_YOYO_ID, YIN_YANG_YOYO_ID
from xiaolin_showdown.logic.config.settings import XiaolinSettings
from xiaolin_showdown.logic.flow.duel import Duel
from xiaolin_showdown.logic.flow.setup import new_game
from xiaolin_showdown.logic.schema.state import XiaolinState
from xiaolin_showdown.logic.flow.training import raise_stat, trainable_stats

DEFAULT = XiaolinSettings()


def _duel() -> Duel:
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1), opponent=cat.character(2))
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.rounds = [Round(stat="force")]
    return duel


def _clear_yoyo_halves(duel: Duel) -> None:
    """The seeded deal can hand out a Yo-Yo half on its own; strip any so a test's own appends are
    the only ones in play."""
    stray = {YING_YOYO_ID, YANG_YOYO_ID, YIN_YANG_YOYO_ID}
    duel.state.player.hand = [card for card in duel.state.player.hand if card.id not in stray]


def _jack_duel() -> Duel:
    cat = load_catalog()
    jack_char = next(c for c in cat.characters if c.name == "Jack_Spicer")
    state = new_game(cat, Rng(1), cat.character(1), opponent=jack_char)
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.rounds = [Round(stat="force")]
    return duel


def test_swap_toggles_the_stat_and_the_caster_affiliation():
    duel = _duel()
    duel._swap_stat_and_flip(True, "force", flip_self=True)
    assert "force" in duel.duel.swapped_stats
    assert duel.state.player.yoyo_flipped is True
    assert duel.duel.yoyo_flipped_announce is True


def test_playing_another_yoyo_on_the_same_stat_flips_both_back():
    duel = _duel()
    duel._swap_stat_and_flip(True, "force", flip_self=True)
    duel._swap_stat_and_flip(True, "force", flip_self=True)
    assert "force" not in duel.duel.swapped_stats
    assert duel.state.player.yoyo_flipped is False


def test_the_bots_own_flip_does_not_announce():
    duel = _duel()
    duel._swap_stat_and_flip(False, "force", flip_self=True)
    assert duel.state.bot.yoyo_flipped is True
    assert duel.duel.yoyo_flipped_announce is False


def test_the_combined_yoyo_flips_the_opponent_not_the_caster():
    duel = _duel()
    duel._swap_stat_and_flip(True, "force", flip_self=False)
    assert duel.state.player.yoyo_flipped is False
    assert duel.state.bot.yoyo_flipped is True
    assert duel.duel.yoyo_flipped_announce is False


def test_swapped_bases_exchange_the_named_stat_only():
    duel = _duel()
    duel.state.player.character.stats["force"] = 2
    duel.state.bot.character.stats["force"] = 5
    duel.duel.swapped_stats.add("force")
    player_base, bot_base = duel._swapped_bases()
    assert player_base["force"] == 5
    assert bot_base["force"] == 2
    assert player_base["agility"] == duel.state.player.character.stats["agility"]


def test_good_jack_mirrors_evil_jacks_trained_force_and_agility():
    duel = _jack_duel()
    duel.state.bot.character.stats["force"] = 4  # fully trained (JACK_FORCE_CAP)
    duel.state.bot.character.stats["agility"] = 5  # fully trained (STAT_CAP)
    duel.state.bot.yoyo_flipped = True
    base = duel._jack_base()
    assert base["force"] == 5  # GOOD_JACK_STAT(4) + (4 - JACK_PRINTED_PHYSICAL(3))
    assert base["agility"] == 6  # GOOD_JACK_STAT(4) + (5 - 3)


def test_good_jacks_intellect_is_its_own_separate_value_not_evils_real_one():
    duel = _jack_duel()
    assert duel.state.bot.character.stats["intellect"] == 7
    duel.state.bot.yoyo_flipped = True
    base = duel._jack_base()
    assert base["intellect"] == 4


def test_good_jack_cannot_be_sent_as_a_bot_form():
    duel = _jack_duel()
    duel.state.bot.yoyo_flipped = True
    duel.duel.jack_mode = jack.AI_JACK_NAME  # a stale value from before he flipped
    duel._choose_jack_mode()
    assert duel.duel.jack_mode is None


def test_evil_jack_trains_force_and_agility_not_intellect():
    duel = _jack_duel()
    stats = trainable_stats(duel.state.bot, DEFAULT)
    assert set(stats) == {"force", "agility"}


def test_good_jack_trains_only_his_own_intellect():
    duel = _jack_duel()
    duel.state.bot.yoyo_flipped = True
    assert trainable_stats(duel.state.bot, DEFAULT) == ["intellect"]


def test_good_jack_intellect_stops_training_at_the_cap():
    duel = _jack_duel()
    duel.state.bot.yoyo_flipped = True
    duel.state.bot.good_jack_intellect = 5
    assert trainable_stats(duel.state.bot, DEFAULT) == []


def test_raising_good_jacks_intellect_also_raises_evils_real_one():
    duel = _jack_duel()
    duel.state.bot.yoyo_flipped = True
    raise_stat(duel.state.bot, "intellect")
    assert duel.state.bot.good_jack_intellect == 5
    assert duel.state.bot.character.stats["intellect"] == 8


def test_save_and_restore_round_trips_the_yoyo_fields():
    duel = _jack_duel()
    duel.state.bot.yoyo_flipped = True
    duel.state.bot.good_jack_intellect = 5
    restored = XiaolinState.restore(duel.state.snapshot(), None)
    assert restored.bot.yoyo_flipped is True
    assert restored.bot.good_jack_intellect == 5


def test_a_save_from_before_the_yoyo_ever_existed_restores_unflipped():
    duel = _jack_duel()
    snapshot = duel.state.snapshot()
    del snapshot["bot"]["yoyo_flipped"]
    del snapshot["bot"]["good_jack_intellect"]
    restored = XiaolinState.restore(snapshot, None)
    assert restored.bot.yoyo_flipped is False
    assert restored.bot.good_jack_intellect == 4


def test_can_combine_yoyo_needs_both_halves_in_hand():
    duel = _duel()
    _clear_yoyo_halves(duel)
    cat = load_catalog()
    duel.state.player.hand.append(deepcopy(cat.card(YING_YOYO_ID)))
    assert can_combine_yoyo(duel.state, 1) is False
    duel.state.player.hand.append(deepcopy(cat.card(YANG_YOYO_ID)))
    assert can_combine_yoyo(duel.state, 1) is True


def test_combine_yoyo_consumes_both_halves_and_spends_the_action():
    duel = _duel()
    _clear_yoyo_halves(duel)
    cat = load_catalog()
    duel.state.player.hand.append(deepcopy(cat.card(YING_YOYO_ID)))
    duel.state.player.hand.append(deepcopy(cat.card(YANG_YOYO_ID)))
    combined = deepcopy(cat.card(YIN_YANG_YOYO_ID))
    combine_yoyo(duel.state, combined)
    ids = [c.id for c in duel.state.player.hand]
    assert YING_YOYO_ID not in ids
    assert YANG_YOYO_ID not in ids
    assert YIN_YANG_YOYO_ID in ids
    assert duel.state.actions_taken == 1


def test_can_self_correct_yoyo_needs_the_combined_card_in_hand():
    duel = _duel()
    cat = load_catalog()
    duel.state.player.hand.append(deepcopy(cat.card(YIN_YANG_YOYO_ID)))
    assert can_self_correct_yoyo(duel.state, 1) is True


def test_self_correct_yoyo_flips_back_and_exiles_the_card():
    duel = _duel()
    duel.state.player.yoyo_flipped = True
    cat = load_catalog()
    duel.state.player.hand.append(deepcopy(cat.card(YIN_YANG_YOYO_ID)))
    self_correct_yoyo(duel.state)
    assert duel.state.player.yoyo_flipped is False
    assert all(c.id != YIN_YANG_YOYO_ID for c in duel.state.player.hand)
    assert duel.state.actions_taken == 1


def test_yin_yang_yoyo_is_never_dealt_into_a_run():
    cat = load_catalog()
    for _ in range(20):
        state = new_game(cat, Rng(_), cat.character(1), opponent=cat.character(2))
        assert all(c.id != YIN_YANG_YOYO_ID for c in state.card_deck)
        assert all(c.id != YIN_YANG_YOYO_ID for c in state.player.hand)
        assert all(c.id != YIN_YANG_YOYO_ID for c in state.bot.hand)


# --- the bot policy --------------------------------------------------------------------------------


def test_the_bot_fuses_both_halves_the_moment_it_holds_them():
    from termcade.core.settings import Difficulty

    from xiaolin_showdown.logic.flow.turn import bot_turn

    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1), opponent=cat.character(2))
    state.bot.hand = [deepcopy(cat.card(YING_YOYO_ID)), deepcopy(cat.card(YANG_YOYO_ID))]
    state.bot_actions_taken = 0
    bot_turn(state, XiaolinSettings(), rng=Rng(1), difficulty=Difficulty.HARD)
    ids = [c.id for c in state.bot.hand]
    assert YING_YOYO_ID not in ids
    assert YANG_YOYO_ID not in ids
    assert YIN_YANG_YOYO_ID in ids


def test_the_bot_does_not_fuse_holding_only_one_half():
    from termcade.core.settings import Difficulty

    from xiaolin_showdown.logic.flow.turn import bot_turn

    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1), opponent=cat.character(2))
    state.bot.hand = [deepcopy(cat.card(YING_YOYO_ID))]
    state.bot_actions_taken = 0
    bot_turn(state, XiaolinSettings(), rng=Rng(1), difficulty=Difficulty.HARD)
    ids = [c.id for c in state.bot.hand]
    assert YING_YOYO_ID in ids
    assert YIN_YANG_YOYO_ID not in ids
