"""AI Jack (steal) and Chamelon-Bot (mirror the opponent) — Jack's identity swap, decided once."""

from __future__ import annotations

from rich.text import Text
from termcade.core.rng import Rng

from factories import auto_choices, duelist, wu

from xiaolin_showdown.logic import bot, jack
from xiaolin_showdown.logic.battle import Side
from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.duel import Duel, DuelState
from xiaolin_showdown.logic.setup import new_game
from xiaolin_showdown.screens.duel_board import _jack_stats, _side_line


def _jack_duel(*, player_priority: bool) -> Duel:
    cat = load_catalog()
    jack_char = next(c for c in cat.characters if c.name == "Jack_Spicer")
    state = new_game(cat, Rng(1), cat.character(1), opponent=jack_char)
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.player_priority = player_priority
    return duel


JACK_STATS = {"force": 3, "agility": 3, "intellect": 7}
WEAK_OPPONENT = {"force": 3, "agility": 3, "intellect": 7}  # margin 0 — below CHAMELON_MARGIN
STRONG_OPPONENT = {"force": 7, "agility": 7, "intellect": 6}  # margin 7 — clears CHAMELON_MARGIN


def test_choose_jack_mode_rolls_attack_first_regardless_of_state():
    # seed 2's first randint(1, 100) is 8, under ATTACK_BASE_CHANCE (15) — verified once.
    assert bot.choose_jack_mode(True, False, JACK_STATS, WEAK_OPPONENT, 0, Rng(2)) == jack.ATTACK_NAME
    assert bot.choose_jack_mode(False, False, JACK_STATS, WEAK_OPPONENT, 0, Rng(2)) == jack.ATTACK_NAME


def test_choose_jack_mode_mirrors_when_the_player_leads_and_clears_the_margin():
    # seed 0's first randint(1, 100) is 50, over ATTACK_BASE_CHANCE — never rolls Attack! here.
    assert bot.choose_jack_mode(True, True, JACK_STATS, STRONG_OPPONENT, 0, Rng(0)) == jack.CHAMELON_NAME


def test_choose_jack_mode_stays_himself_when_the_player_leads_but_margin_is_too_thin():
    assert bot.choose_jack_mode(True, True, JACK_STATS, WEAK_OPPONENT, 0, Rng(0)) is None


def test_choose_jack_mode_steals_when_jack_leads_and_can_swap():
    assert bot.choose_jack_mode(False, True, JACK_STATS, WEAK_OPPONENT, 0, Rng(0)) == jack.AI_JACK_NAME


def test_choose_jack_mode_stays_himself_when_it_cannot_swap():
    assert bot.choose_jack_mode(True, False, JACK_STATS, WEAK_OPPONENT, 0, Rng(0)) is None
    assert bot.choose_jack_mode(False, False, JACK_STATS, WEAK_OPPONENT, 0, Rng(0)) is None


def test_attack_chance_decays_per_showdown_but_never_below_the_floor():
    assert bot._attack_chance(0) == bot.ATTACK_BASE_CHANCE
    assert bot._attack_chance(5) == bot.ATTACK_BASE_CHANCE - 5
    assert bot._attack_chance(50) == bot.ATTACK_MIN_CHANCE


def test_steal_target_takes_the_strongest_hand_card():
    weak = wu(0, name="Weak", points=1)
    strong = wu(3, name="Strong", points=3)
    assert bot.steal_target([weak, strong], [], Rng(0)) is strong


def test_steal_target_falls_back_to_a_random_deck_card_when_hand_is_empty():
    deck_card = wu(1, name="Deck")
    assert bot.steal_target([], [deck_card], Rng(0)) is deck_card


def test_steal_target_is_none_when_nothing_is_available():
    assert bot.steal_target([], [], Rng(0)) is None


async def test_commitment_picks_chamelon_bot_when_the_player_leads_and_clears_the_margin():
    duel = _jack_duel(player_priority=True)  # seed 1 never rolls Attack! on the first call
    duel.state.jack_can_swap = True
    duel.state.player.character.stats = dict(STRONG_OPPONENT)
    await duel._commitment()
    assert duel.duel.jack_mode == jack.CHAMELON_NAME


async def test_commitment_stays_himself_when_the_player_leads_but_margin_is_too_thin():
    duel = _jack_duel(player_priority=True)  # seed 1 never rolls Attack! on the first call
    duel.state.jack_can_swap = True
    await duel._commitment()
    assert duel.duel.jack_mode is None


async def test_commitment_picks_ai_jack_and_steals_when_jack_leads():
    duel = _jack_duel(player_priority=False)
    duel.state.jack_can_swap = True
    player_before, bot_before = len(duel.state.player.hand), len(duel.state.bot.hand)
    await duel._commitment()
    assert duel.duel.jack_mode == jack.AI_JACK_NAME
    assert len(duel.state.player.hand) == player_before - 1
    assert len(duel.state.bot.hand) == bot_before + 1


async def test_commitment_swap_alternation_belongs_to_ai_jack_alone():
    # AI Jack firing flips jack_can_swap to False — the "cannot spam a stand-in" rule is his.
    duel = _jack_duel(player_priority=False)  # seed 1 never rolls Attack! on the first call
    duel.state.jack_can_swap = True
    await duel._commitment()
    assert duel.duel.jack_mode == jack.AI_JACK_NAME
    assert duel.state.jack_can_swap is False

    # Chamelon-Bot firing (player leads) must never touch it — he may fire every time he clears
    # the margin, whatever jack_can_swap already reads.
    duel2 = _jack_duel(player_priority=True)
    duel2.state.jack_can_swap = False
    duel2.state.player.character.stats = dict(STRONG_OPPONENT)
    await duel2._commitment()
    assert duel2.duel.jack_mode == jack.CHAMELON_NAME
    assert duel2.state.jack_can_swap is False


def test_jack_base_mirrors_the_opponent_in_chamelon_bot():
    duel = _jack_duel(player_priority=True)
    duel.duel.jack_mode = jack.CHAMELON_NAME
    assert duel._jack_base() == duel.state.player.character.stats


def test_jack_base_is_his_own_stats_otherwise():
    duel = _jack_duel(player_priority=False)
    assert duel.duel.jack_mode is None
    assert duel._jack_base() == duel.state.bot.character.stats


def test_jack_stats_display_helper_mirrors_only_in_chamelon_mode():
    opponent = duelist(stats={"force": 9, "agility": 9, "intellect": 9})
    duel_state = DuelState()

    duel_state.jack_mode = jack.CHAMELON_NAME
    assert _jack_stats(duel_state, opponent) == {"force": 9, "agility": 9, "intellect": 9}

    duel_state.jack_mode = jack.AI_JACK_NAME
    assert _jack_stats(duel_state, opponent) is None

    duel_state.jack_mode = None
    assert _jack_stats(duel_state, opponent) is None


def test_is_construct_true_for_jong():
    duel = _jack_duel(player_priority=True)
    duel.state.player.jong_form = True
    assert duel._is_construct(duel.state.player) is True


def test_is_construct_true_for_jack_in_any_swap_mode():
    duel = _jack_duel(player_priority=True)
    for mode in (jack.AI_JACK_NAME, jack.CHAMELON_NAME):
        duel.duel.jack_mode = mode
        assert duel._is_construct(duel.state.bot) is True


def test_is_construct_false_for_jack_fighting_as_himself():
    duel = _jack_duel(player_priority=True)
    duel.duel.jack_mode = None
    assert duel._is_construct(duel.state.bot) is False


def test_is_construct_false_for_a_plain_duelist():
    duel = _jack_duel(player_priority=True)
    assert duel._is_construct(duel.state.player) is False


async def test_boost_marks_both_sides_construct_status():
    duel = _jack_duel(player_priority=True)
    duel.duel.jack_mode = jack.CHAMELON_NAME
    await duel._boost()
    assert duel.duel.round.bot.is_construct is True
    assert duel.duel.round.player.is_construct is False


async def test_jack_bot_never_deploys_while_a_swap_mode_is_active():
    duel = _jack_duel(player_priority=False)
    duel.duel.jack_mode = jack.AI_JACK_NAME  # simulate the mode already decided
    await duel._boost()
    assert duel.duel.jack_bot_name is None  # never picked, so never named


def test_side_line_shows_the_swapped_name_and_mirrored_stats():
    jack_player = duelist(name="Jack_Spicer", stats={"force": 3, "agility": 3, "intellect": 7})
    group = _side_line(
        "P2", jack_player, Side(), leads=False, challenge=None, background="metal",
        shown_name=jack.CHAMELON_NAME, shown_stats={"force": 9, "agility": 9, "intellect": 9},
    )
    header = group.renderables[0]
    assert isinstance(header, Text)
    assert jack.CHAMELON_NAME in header.plain
    assert "9" in header.plain and "3" not in header.plain  # his own 3/3/7 must not leak through
