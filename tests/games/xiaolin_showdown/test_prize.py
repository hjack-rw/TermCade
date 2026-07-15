"""Four ways to claim the revealed Wu — and the one where nobody does.

Winning the showdown settles who keeps their own Wu. Taking the *prize* has to be earned, and this is
the file that pins how. Every route is read off a battle's three end values (or, for the fourth, off
the ground the fight happened on), so each test builds those directly rather than playing a duel.
"""

from __future__ import annotations

import pytest

from xiaolin_showdown.logic.battle import Round
from xiaolin_showdown.logic.mechanics.prize import PrizeRoute, claim_route
from xiaolin_showdown.logic.models import Card
from factories import run_showdown, wu

THRESHOLD = 7  # the shipped `prize_threshold`; a decisive blow must reach 8


def _battle(*end_values: int, stat: str = "force") -> Round:
    """A battle already scored, with the winner's three end values set."""
    battle = Round(stat=stat)
    battle.player.result = list(end_values)
    battle.bot.result = [0, 0, 0]
    return battle


def _wu(element: str) -> Card:
    return wu(1, 0, 0, element=element, id=1)


def _claim(rounds, background="metal", cancelled=False):
    return claim_route(
        rounds,
        winner_is_player=True,
        background=background,
        threshold=THRESHOLD,
        bonus_cancelled=cancelled,
    )


# --- route 1: a decisive blow ------------------------------------------------------


def test_one_stat_over_the_threshold_takes_the_wu():
    assert _claim([_battle(8, 0, 0)]) is PrizeRoute.DECISIVE_BLOW


def test_the_threshold_itself_is_not_enough():
    """`prize_threshold` is the bar you must *beat*, not meet — 7 loses, 8 wins."""
    assert _claim([_battle(7, 0, 0)]) is not PrizeRoute.DECISIVE_BLOW


# --- route 2: a broad win ----------------------------------------------------------


def test_two_stats_one_below_the_bar_take_the_wu():
    assert _claim([_battle(7, 7, 0)]) is PrizeRoute.BROAD_WIN


def test_one_stat_one_below_the_bar_is_not_enough():
    assert _claim([_battle(7, 0, 0)]) is None


# --- route 3: total command --------------------------------------------------------


def test_all_three_stats_two_below_the_bar_take_the_wu():
    assert _claim([_battle(6, 6, 6)]) is PrizeRoute.TOTAL_COMMAND


def test_two_of_three_at_that_height_is_not_enough():
    assert _claim([_battle(6, 6, 5)]) is None


# --- the routes are tried in order -------------------------------------------------


def test_a_decisive_blow_is_named_even_when_a_broader_route_also_qualifies():
    """The routes are a ladder, and a player is told the best rung they reached."""
    assert _claim([_battle(9, 8, 8)]) is PrizeRoute.DECISIVE_BLOW


# --- route 4: in tune with the arena -----------------------------------------------


def test_a_wu_that_belonged_on_the_ground_claims_it_after_a_scrappy_win():
    """The only route you can aim at *during* the showdown: win ugly, but win where you belong."""
    battle = _battle(1, 1, 1)  # nowhere near any stat bar
    battle.player.queue = [_wu("water")]

    assert _claim([battle], background="water") is PrizeRoute.IN_TUNE


def test_a_wu_that_moves_no_stat_is_still_standing_on_the_ground():
    """Resonance asks what you BROUGHT, not what it did once it got there.

    Straight off a real board: a water dragon and two metal Wu on a water canal — one of the metal Wu
    a negation, which prints 0/0/0 and moves nothing. The sum is +1 −1 −1 = −1, and the duelist is not
    in tune with anything. It used to read only the Wu whose stats still moved, so the silent metal was
    dropped, the sum came to +1, and a player who fielded two lumps of metal in a canal was told they
    had won the Wu by being in tune with the water.
    """
    silent_metal = _wu("metal")
    silent_metal.stats = {"force": 0, "agility": 0, "intellect": 0}  # a negation Wu: 0/0/0 printed

    battle = _battle(1, 1, 1)  # nowhere near any stat bar — only resonance could claim this
    battle.player.queue = [_wu("water"), _wu("metal"), silent_metal]

    assert _claim([battle], background="water") is None


def test_a_curse_you_cast_is_a_wu_you_brought_to_the_ground():
    """It prints on the OPPONENT's Defensive line — that is where it landed, not who played it.

    The caster's own copy is spent to zero, so the Wu is absent from their Offensive line entirely.
    Reading only your own side loses every curse you fielded: a duelist could stand in a water canal
    throwing metal at their opponent and still be told they were in tune with the water.
    """
    battle = _battle(1, 1, 1)  # nowhere near any stat bar — only resonance could claim this
    battle.player.queue = [_wu("water")]  # what the player's Offensive line shows: +1
    battle.bot.suffered = [_wu("metal"), _wu("metal")]  # two metal curses the PLAYER cast: −1 −1

    assert _claim([battle], background="water") is None


def test_a_wu_at_odds_with_the_ground_claims_nothing():
    battle = _battle(1, 1, 1)
    battle.player.queue = [_wu("fire")]  # fire on water: opposed

    assert _claim([battle], background="water") is None


def test_metal_is_at_odds_with_every_coloured_ground():
    """Metal is reliable everywhere and favoured almost nowhere — this is the price of that."""
    battle = _battle(1, 1, 1)
    battle.player.queue = [_wu("metal")]

    assert _claim([battle], background="water") is None


def test_a_serpents_tail_vetoes_the_elemental_claim():
    """If the ground has stopped resonating, nobody was in tune with anything."""
    battle = _battle(1, 1, 1)
    battle.player.queue = [_wu("water")]

    assert _claim([battle], background="water", cancelled=True) is None


def test_the_stat_routes_survive_a_serpents_tail():
    """It vetoes only the elemental claim. A blow is a blow, resonance or not."""
    battle = _battle(8, 0, 0)
    battle.player.queue = [_wu("water")]

    assert _claim([battle], background="water", cancelled=True) is PrizeRoute.DECISIVE_BLOW


# --- nobody took it ----------------------------------------------------------------


def test_a_narrow_win_on_hostile_ground_loses_the_wu():
    battle = _battle(2, 2, 2)
    battle.player.queue = [_wu("metal")]

    assert _claim([battle], background="fire") is None


def test_a_battle_that_never_scored_is_not_read():
    """`result` fills only once a battle is full. An empty one says nothing, and must not crash."""
    assert _claim([Round(stat="force")]) is None


# --- the tournament: three battles, three chances ----------------------------------


def test_a_tournament_claims_the_wu_on_any_one_of_its_battles():
    """Three battles mean three bites at the ladder — win *one* of them hard and the Wu is yours.

    This is why a tournament is the prize play: it commits three Wu where a wager is usually one, and
    the extra commitment buys the extra chances.
    """
    rounds = [_battle(1, 1, 1), _battle(8, 0, 0), _battle(2, 0, 0)]

    assert _claim(rounds) is PrizeRoute.DECISIVE_BLOW


def test_a_tournament_won_narrowly_everywhere_still_loses_the_wu():
    rounds = [_battle(2, 2, 2), _battle(3, 1, 1), _battle(2, 2, 1)]

    assert _claim(rounds, background="fire") is None


# --- a Wu nobody won is LOST, not destroyed -----------------------------------------


async def test_a_prize_nobody_claims_goes_to_the_lost_pile(catalog, settings):
    """It leaves play. It does not leave existence — the Rooster Booster reaches for it later.

    Driven through a real showdown, because the lost pile is filled by the duel's end phase and the
    point of the test is that the Wu is *somewhere* when the dust settles.
    """
    from termcade.core.rng import Rng

    from xiaolin_showdown.logic.duel import Duel, DuelChoices
    from xiaolin_showdown.logic.setup import new_game

    async def first(options):
        return options[0]

    async def no_boost(_options):
        return None

    async def element(background):
        return background

    choices = DuelChoices(first, first, first, no_boost, first, element, first)

    for seed in range(1, 30):  # find a showdown the prize does not move in — most of them
        state = new_game(catalog, Rng(seed), catalog.character(1), settings=settings)
        duel = Duel(state, Rng(seed), choices, settings)

        await run_showdown(duel, settings)

        if not duel.duel.card_won:
            assert duel.duel.prize_route is None
            assert state.lost, "the Wu nobody won vanished instead of being lost"
            assert state.lost[-1] is duel.duel.stakes
            return

    pytest.fail("no showdown in 30 seeds left the prize unclaimed — cannot test the lost pile")


async def test_a_prize_that_is_claimed_never_reaches_the_lost_pile(catalog, settings):
    """Guards the test above: winning the Wu must not also file it under lost."""
    from termcade.core.rng import Rng

    from xiaolin_showdown.logic.duel import Duel, DuelChoices
    from xiaolin_showdown.logic.setup import new_game

    async def first(options):
        return options[0]

    async def no_boost(_options):
        return None

    async def element(background):
        return background

    choices = DuelChoices(first, first, first, no_boost, first, element, first)

    for seed in range(1, 40):
        state = new_game(catalog, Rng(seed), catalog.character(1), settings=settings)
        duel = Duel(state, Rng(seed), choices, settings)

        await run_showdown(duel, settings)

        if duel.duel.card_won:
            assert duel.duel.prize_route is not None
            assert not state.lost
            return

    pytest.fail("no showdown in 40 seeds claimed the prize — cannot test the winning path")
