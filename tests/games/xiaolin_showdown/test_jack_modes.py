"""AI Jack (steal) and Chamelon-Bot (mirror the opponent) — Jack's identity swap, decided once."""

from __future__ import annotations

import unittest.mock

from rich.text import Text
from termcade.core.rng import Rng

from factories import auto_choices, duelist, wu

from xiaolin_showdown.logic import bot, jack
from xiaolin_showdown.logic.battle import Round, Side
from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.duel import Duel, DuelState
from xiaolin_showdown.logic.settings import XiaolinSettings
from xiaolin_showdown.logic.setup import new_game
from xiaolin_showdown.screens.duel_board import _jack_stats, _side_line


def _jack_duel(*, player_priority: bool) -> Duel:
    # seed 5: at momentum 0, the first Attack! roll misses under EITHER priority (verified once, not
    # re-derived per test) — so a bare `_commitment()` call always falls through to the stand-in split.
    cat = load_catalog()
    jack_char = next(c for c in cat.characters if c.name == "Jack_Spicer")
    state = new_game(cat, Rng(5), cat.character(1), opponent=jack_char)
    duel = Duel(state, Rng(5), auto_choices())
    duel.duel.player_priority = player_priority
    return duel


def test_choose_jack_mode_rolls_attack_first_regardless_of_state():
    # seed 31's first randint(1, 100) is 2, under ATTACK_CHANCE_WHEN_LEADING (5) — verified once.
    assert bot.choose_jack_mode(True, False, 0, Rng(31)) == jack.ATTACK_NAME
    assert bot.choose_jack_mode(False, False, 0, Rng(31)) == jack.ATTACK_NAME


def test_choose_jack_mode_mirrors_whenever_the_player_leads():
    # seed 9's first randint(1, 100) is 60, over ATTACK_CHANCE_WHEN_TRAILING (50) at momentum 0.
    # Unconditional now, `can_swap` included — the redesigned effect (see BOSSES.md) never needs a
    # margin, so there is nothing left to gate it on.
    assert bot.choose_jack_mode(True, True, 0, Rng(9)) == jack.CHAMELON_NAME
    assert bot.choose_jack_mode(True, False, 0, Rng(9)) == jack.CHAMELON_NAME


def test_choose_jack_mode_steals_when_jack_leads_and_can_swap():
    assert bot.choose_jack_mode(False, True, 0, Rng(0)) == jack.AI_JACK_NAME


def test_choose_jack_mode_stays_himself_when_jack_leads_and_cannot_swap():
    assert bot.choose_jack_mode(False, False, 0, Rng(0)) is None


def test_attack_chance_scales_with_momentum_only_when_the_player_leads():
    assert bot._attack_chance(True, 0) == bot.ATTACK_CHANCE_WHEN_TRAILING
    assert bot._attack_chance(True, 10) == bot.ATTACK_CHANCE_WHEN_TRAILING + 10
    assert bot._attack_chance(True, 1000) == bot.ATTACK_MAX_CHANCE
    assert bot._attack_chance(True, -1000) == bot.ATTACK_MIN_CHANCE
    # Jack leading ignores momentum entirely — Attack! only ever hurts him there, whatever his form.
    assert bot._attack_chance(False, 1000) == bot.ATTACK_CHANCE_WHEN_LEADING
    assert bot._attack_chance(False, -1000) == bot.ATTACK_CHANCE_WHEN_LEADING


def test_attack_chance_is_higher_when_the_player_leads():
    # The whole point of the priority split: replace Jack's weakest spot (himself, player leads)
    # far more than his strongest (himself/AI Jack, Jack leads) — see BOSSES.md.
    assert bot.ATTACK_CHANCE_WHEN_TRAILING > bot.ATTACK_CHANCE_WHEN_LEADING


def test_steal_target_takes_the_strongest_hand_card():
    weak = wu(0, name="Weak", points=1)
    strong = wu(3, name="Strong", points=3)
    assert bot.steal_target([weak, strong], [], Rng(0)) is strong


def test_steal_target_falls_back_to_a_random_deck_card_when_hand_is_empty():
    deck_card = wu(1, name="Deck")
    assert bot.steal_target([], [deck_card], Rng(0)) is deck_card


def test_steal_target_is_none_when_nothing_is_available():
    assert bot.steal_target([], [], Rng(0)) is None


async def test_commitment_picks_chamelon_bot_whenever_the_player_leads():
    duel = _jack_duel(player_priority=True)
    duel.state.jack_can_swap = True
    await duel._commitment()
    assert duel.duel.jack_mode == jack.CHAMELON_NAME


async def test_commitment_picks_ai_jack_and_steals_when_jack_leads():
    # Fires before either side has chosen a Wu — a sudden loss, not a tidy one (see
    # `screens/duel._announce_jack_steal` for the toast that keeps it from also being a surprise
    # later, when the stolen card just isn't there to pick).
    duel = _jack_duel(player_priority=False)
    duel.state.jack_can_swap = True
    player_before, bot_before = len(duel.state.player.hand), len(duel.state.bot.hand)
    await duel._commitment()
    assert duel.duel.jack_mode == jack.AI_JACK_NAME
    assert len(duel.state.player.hand) == player_before - 1
    assert len(duel.state.bot.hand) == bot_before + 1
    assert duel.duel.jack_stolen is not None


def test_resolve_ai_jack_steal_takes_the_strongest_hand_card():
    duel = _jack_duel(player_priority=False)
    duel.duel.jack_mode = jack.AI_JACK_NAME
    weak = wu(0, name="Weak", points=1)
    strong = wu(3, name="Strong", points=3)
    duel.state.player.hand = [weak, strong]
    bot_before = len(duel.state.bot.hand)
    duel._resolve_ai_jack_steal()
    assert strong not in duel.state.player.hand
    assert weak in duel.state.player.hand
    assert strong in duel.state.bot.hand
    assert len(duel.state.bot.hand) == bot_before + 1
    assert duel.duel.jack_stolen == "Strong"


def test_resolve_ai_jack_steal_takes_a_deck_card_when_hand_is_empty():
    duel = _jack_duel(player_priority=False)
    duel.duel.jack_mode = jack.AI_JACK_NAME
    buried = wu(2, name="Buried", points=2)
    duel.state.player.hand = []
    duel.state.player.deck = [buried]
    duel._resolve_ai_jack_steal()
    assert buried not in duel.state.player.deck
    assert buried in duel.state.bot.hand
    assert duel.duel.jack_stolen == "Buried"


def test_resolve_ai_jack_steal_is_a_no_op_outside_ai_jack_mode():
    duel = _jack_duel(player_priority=False)
    duel.duel.jack_mode = jack.CHAMELON_NAME
    strong = wu(3, name="Strong", points=3)
    duel.state.player.hand = [strong]
    duel._resolve_ai_jack_steal()
    assert strong in duel.state.player.hand
    assert duel.duel.jack_stolen is None


async def test_commitment_swap_alternation_belongs_to_ai_jack_alone():
    # AI Jack firing flips jack_can_swap to False — the "cannot spam a stand-in" rule is his.
    duel = _jack_duel(player_priority=False)
    duel.state.jack_can_swap = True
    await duel._commitment()
    assert duel.duel.jack_mode == jack.AI_JACK_NAME
    assert duel.state.jack_can_swap is False

    # Chamelon-Bot firing (player leads) must never touch it — it fires every time the player leads,
    # whatever jack_can_swap already reads (no margin left to gate it on).
    duel2 = _jack_duel(player_priority=True)
    duel2.state.jack_can_swap = False
    await duel2._commitment()
    assert duel2.duel.jack_mode == jack.CHAMELON_NAME
    assert duel2.state.jack_can_swap is False


def test_jack_base_is_his_own_stats_for_himself_and_chamelon_bot():
    # The mirror lives in `_bot_base` now, scoped to the one stat actually contested — `_jack_base`
    # itself is identity-agnostic except for Attack!'s flat body.
    duel = _jack_duel(player_priority=False)
    assert duel.duel.jack_mode is None
    assert duel._jack_base() == duel.state.bot.character.stats

    duel.duel.jack_mode = jack.CHAMELON_NAME
    assert duel._jack_base() == duel.state.bot.character.stats


def test_chamelon_boost_card_bumps_only_the_contested_stat():
    duel = _jack_duel(player_priority=True)
    duel.duel.jack_mode = jack.CHAMELON_NAME
    duel.duel.challenge = "force"
    duel.state.player.character.stats = {"force": 9, "agility": 2, "intellect": 2}
    card = duel._chamelon_boost_card()
    assert card is not None
    # 9 - his own 3, plus CHAMELON_MARGIN (1) past parity, not just up to it
    assert card.stats == {"force": 7, "agility": 0, "intellect": 0}
    assert card.element == ""  # never resonates or suffers — precisely the bump, nothing else


def test_chamelon_boost_card_is_none_when_nothing_to_deny():
    duel = _jack_duel(player_priority=True)
    duel.duel.jack_mode = jack.CHAMELON_NAME
    duel.duel.challenge = "force"
    duel.state.player.character.stats = {"force": 1, "agility": 2, "intellect": 2}
    assert duel._chamelon_boost_card() is None


def test_chamelon_boost_card_is_none_outside_chamelon_mode():
    duel = _jack_duel(player_priority=True)
    duel.duel.jack_mode = None
    duel.duel.challenge = "force"
    duel.state.player.character.stats = {"force": 9, "agility": 2, "intellect": 2}
    assert duel._chamelon_boost_card() is None


def test_chamelon_boost_card_is_none_once_already_spent_this_showdown():
    duel = _jack_duel(player_priority=True)
    duel.duel.jack_mode = jack.CHAMELON_NAME
    duel.duel.challenge = "force"
    duel.state.player.character.stats = {"force": 9, "agility": 2, "intellect": 2}
    duel.duel.bot.boosts_spent.append(wu(0, name="stand-in", id=jack.CHAMELON_BOOST_ID))
    assert duel._chamelon_boost_card() is None


async def test_boost_offers_the_chamelon_card_as_a_real_candidate():
    # Whether it WINS the boost this cycle is `choose_boost`'s own reach-comparison — same machinery
    # as Shimo Staff or the Heart, deliberately not preferred by default (see the module docstring).
    # This only checks it reaches that comparison at all, via a spy on the shared entry point.
    duel = _jack_duel(player_priority=True)
    duel.duel.jack_mode = jack.CHAMELON_NAME
    duel.duel.challenge = "force"
    duel.state.player.character.stats = {"force": 9, "agility": 2, "intellect": 2}
    seen: list = []
    real_choose_boost = bot.choose_boost

    def spy(battle, ground, options, playable, **kwargs):
        seen.extend(options)
        return real_choose_boost(battle, ground, options, playable, **kwargs)

    with unittest.mock.patch.object(bot, "choose_boost", spy):
        await duel._boost()
    assert any(c.id == jack.CHAMELON_BOOST_ID for c in seen)


def test_commit_boost_never_stakes_the_chamelon_card():
    duel = _jack_duel(player_priority=True)
    duel.duel.jack_mode = jack.CHAMELON_NAME
    duel.duel.challenge = "force"
    duel.state.player.character.stats = {"force": 9, "agility": 2, "intellect": 2}
    card = duel._chamelon_boost_card()
    assert card is not None
    duel.duel.rounds = [Round(stat="force")]
    duel._commit_boost(card, is_player=False, element="")
    assert any(c.id == jack.CHAMELON_BOOST_ID for c in duel.duel.round.bot.queue)
    assert not any(c.id == jack.CHAMELON_BOOST_ID for c in duel.duel.bot.stakes)


def test_commit_boost_joins_the_chamelon_card_with_ampersand_not_plus():
    from xiaolin_showdown.screens.duel_board import _cards_line

    duel = _jack_duel(player_priority=True)
    duel.duel.jack_mode = jack.CHAMELON_NAME
    duel.duel.challenge = "force"
    duel.state.player.character.stats = {"force": 9, "agility": 2, "intellect": 2}
    card = duel._chamelon_boost_card()
    assert card is not None
    duel.duel.rounds = [Round(stat="force")]
    duel._commit_boost(card, is_player=False, element="")
    bot_side = duel.duel.round.bot
    other = wu(-2, name="Sting", element="metal")
    line = _cards_line("Defensive", [*bot_side.jack_bot, other], [], None, "metal", jack_bot=bot_side.jack_bot)
    plain = line.renderables[0].plain
    assert " & " in plain
    assert " + " not in plain


async def test_setup_background_choice_reads_jacks_real_stats(monkeypatch):
    # The heuristic scores a background by the bot's OWN comparative stat edge — it must always read
    # his real stats, not a distorted identity, whatever swap mode is active.
    duel = _jack_duel(player_priority=True)
    duel.duel.jack_mode = jack.CHAMELON_NAME
    duel.settings = XiaolinSettings(**{**duel.settings.__dict__, "random_background": 0})
    captured: dict = {}

    def spy(bot_stats, *args, **kwargs):
        captured["bot_stats"] = bot_stats
        return "metal"

    monkeypatch.setattr(bot, "choose_background", spy)
    await duel._setup()
    assert captured["bot_stats"] == duel.state.bot.character.stats


def test_jack_stats_display_helper_hides_chamelon_denial_its_a_boost_not_a_base():
    # Chamelon-Bot's denial is a boost now (see `_chamelon_boost_card`), already shown on the
    # Offensive line — the header must not bake it in too, or the printed total double-counts it.
    jack_player = duelist(stats={"force": 3, "agility": 3, "intellect": 7})
    opponent = duelist(stats={"force": 9, "agility": 9, "intellect": 2})
    duel_state = DuelState()

    duel_state.jack_mode = jack.CHAMELON_NAME
    assert _jack_stats(duel_state, jack_player, opponent) is None

    duel_state.jack_mode = jack.AI_JACK_NAME
    assert _jack_stats(duel_state, jack_player, opponent) is None

    duel_state.jack_mode = None
    assert _jack_stats(duel_state, jack_player, opponent) is None


def test_jack_stats_display_helper_shows_good_jacks_override():
    # Good Jack sets no `jack_mode` while worn — the header must key off `yoyo_flipped` directly, or
    # it silently falls back to Evil Jack's raw stats mid-fight.
    duel = _jack_duel(player_priority=True)
    jack_player = duel.state.bot
    opponent = duel.state.player
    jack_player.yoyo_flipped = True
    real = jack_player.character.stats

    shown = _jack_stats(duel.duel, jack_player, opponent)

    assert shown == {
        "force": jack.GOOD_JACK_STAT + (real["force"] - jack.JACK_PRINTED_PHYSICAL),
        "agility": jack.GOOD_JACK_STAT + (real["agility"] - jack.JACK_PRINTED_PHYSICAL),
        "intellect": jack_player.good_jack_intellect,
    }


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
