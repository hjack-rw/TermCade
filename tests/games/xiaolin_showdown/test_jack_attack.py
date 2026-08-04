"""Jack-bots Attack! — the Brawl: majority-of-3 scoring, independent 0-3 wager, outright prize."""

from __future__ import annotations

from termcade.core.rng import Rng

from factories import auto_choices, ground, wu

from xiaolin_showdown.logic.characters import jack
from xiaolin_showdown.logic.flow.battle import Round, score_brawl
from xiaolin_showdown.logic.schema.catalog import load_catalog
from xiaolin_showdown.logic.schema.constants import BRAWL
from xiaolin_showdown.logic.flow.duel import Duel
from xiaolin_showdown.logic.mechanics.prize import PrizeRoute
from xiaolin_showdown.logic.flow.setup import new_game


def _jack_duel(rng_seed: int = 1) -> Duel:
    cat = load_catalog()
    jack_char = next(c for c in cat.characters if c.name == "Jack_Spicer")
    state = new_game(cat, Rng(rng_seed), cat.character(1), opponent=jack_char)
    duel = Duel(state, Rng(rng_seed), auto_choices())
    duel.duel.jack_mode = jack.ATTACK_NAME
    duel.duel.challenge = BRAWL
    return duel


def test_score_brawl_wins_on_majority_of_stats_not_summed_margin():
    # Player leads force and agility (2 of 3); bot leads intellect by a landslide. A summed-margin
    # scorer (score_battle's rule) would hand the bot the battle — the Brawl must not.
    battle = Round(stat="")
    g = ground(
        player_stats={"force": 5, "agility": 5, "intellect": 1},
        bot_stats={"force": 1, "agility": 1, "intellect": 20},
    )
    score_brawl(battle, g)
    assert battle.winner is True


def test_score_brawl_stalemate_goes_to_the_challenger():
    # 1-1 with intellect an exact draw: the majority count itself ties, so it falls to the challenger.
    battle = Round(stat="")
    g = ground(
        player_stats={"force": 5, "agility": 1, "intellect": 3},
        bot_stats={"force": 1, "agility": 5, "intellect": 3},
        challenger_is_player=True,
    )
    score_brawl(battle, g)
    assert battle.winner is True

    g2 = ground(
        player_stats={"force": 5, "agility": 1, "intellect": 3},
        bot_stats={"force": 1, "agility": 5, "intellect": 3},
        challenger_is_player=False,
    )
    battle2 = Round(stat="")
    score_brawl(battle2, g2)
    assert battle2.winner is False


def test_jack_base_is_attack_stat_plus_the_metal_swing():
    duel = _jack_duel()
    duel.duel.background = "metal"
    assert duel._jack_base() == {s: jack.ATTACK_STAT + 1 for s in ("force", "agility", "intellect")}

    duel.duel.background = "fire"
    assert duel._jack_base() == {s: jack.ATTACK_STAT - 1 for s in ("force", "agility", "intellect")}


def test_jack_base_reads_neutral_before_a_background_is_decided():
    duel = _jack_duel()
    duel.duel.background = None
    assert duel._jack_base() == {s: jack.ATTACK_STAT for s in ("force", "agility", "intellect")}


def test_brawl_wager_options_include_zero():
    duel = _jack_duel()
    assert 0 in duel._brawl_wager_options(is_player=True)
    assert 0 in duel._brawl_wager_options(is_player=False)


def test_wager_targets_read_the_independent_brawl_wagers():
    duel = _jack_duel()
    duel.duel.player_wager = 0
    duel.duel.bot_wager = 3
    assert duel._wager_targets() == (0, 3)


def test_attack_awards_the_prize_outright_no_ladder():
    duel = _jack_duel()
    duel.duel.stakes = wu(1, name="Prize")
    duel.duel.winner = False  # Jack (the bot) won the Brawl
    duel.duel.rounds = [Round(stat="")]  # empty result — nowhere near any normal claim_route bar
    duel._award_prize()
    assert duel.duel.card_won is True
    assert duel.duel.prize_route is PrizeRoute.BRAWL_WON


async def test_commitment_sets_the_brawl_challenge_and_never_a_tournament():
    duel = _jack_duel(rng_seed=31)  # seed 31's first roll (2) is under ATTACK_CHANCE_WHEN_LEADING
    duel.duel.jack_mode = None  # let _commitment decide it fresh
    duel.duel.player_priority = False
    await duel._commitment()
    assert duel.duel.jack_mode == jack.ATTACK_NAME
    assert duel.duel.challenge == BRAWL
    assert not duel._is_tournament()


async def test_setup_brawl_takes_metal_directly_when_jack_picks_the_background():
    # Jack always plays metal for his own free swing rather than running the generic heuristic —
    # a real gap found via the win-rate diagnostic, not a design choice.
    duel = _jack_duel()
    duel.duel.player_priority = True  # player leads, so Jack (the non-challenger) picks the background
    await duel._setup_brawl()
    assert duel.duel.background == "metal"
