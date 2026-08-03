"""Jack's flee: concede a showdown he lost fighting as himself. The prize still resolves through
the normal ladder, unaffected — the only thing fleeing spares him is his own wager. Capped per run,
never in a swap mode."""

from __future__ import annotations

from termcade.core.rng import Rng

from factories import auto_choices, wu

from xiaolin_showdown.logic import bot, jack
from xiaolin_showdown.logic.battle import Round, Side
from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.duel import Duel
from xiaolin_showdown.logic.mechanics.prize import PrizeRoute
from xiaolin_showdown.logic.setup import new_game


def _jack_duel(rng_seed: int = 1) -> Duel:
    cat = load_catalog()
    jack_char = next(c for c in cat.characters if c.name == "Jack_Spicer")
    state = new_game(cat, Rng(rng_seed), cat.character(1), opponent=jack_char)
    return Duel(state, Rng(rng_seed), auto_choices())


def test_choose_to_flee_stops_at_the_cap():
    assert bot.choose_to_flee(0) is True
    assert bot.choose_to_flee(bot.JACK_FLEE_CAP - 1) is True
    assert bot.choose_to_flee(bot.JACK_FLEE_CAP) is False


async def test_resolvement_flees_when_jack_loses_fighting_as_himself():
    duel = _jack_duel()
    duel.duel.jack_mode = None
    duel.duel.rounds = [Round(stat="", score=1)]  # the player's side leads
    await duel._resolvement()
    assert duel.duel.winner is True
    assert duel.duel.jack_fled is True
    assert duel.state.jack_flees_used == 1


async def test_resolvement_never_flees_past_the_cap():
    duel = _jack_duel()
    duel.duel.jack_mode = None
    duel.state.jack_flees_used = bot.JACK_FLEE_CAP
    duel.duel.rounds = [Round(stat="", score=1)]
    await duel._resolvement()
    assert duel.duel.jack_fled is False


async def test_resolvement_never_flees_in_a_swap_mode():
    duel = _jack_duel()
    duel.duel.jack_mode = jack.AI_JACK_NAME
    duel.duel.rounds = [Round(stat="", score=1)]
    await duel._resolvement()
    assert duel.duel.jack_fled is False


async def test_resolvement_never_flees_when_jack_wins():
    duel = _jack_duel()
    duel.duel.jack_mode = None
    duel.duel.rounds = [Round(stat="", score=-1)]  # the bot's side leads
    await duel._resolvement()
    assert duel.duel.winner is False
    assert duel.duel.jack_fled is False


def test_award_prize_still_lets_the_player_claim_it_when_fled():
    duel = _jack_duel()
    duel.duel.stakes = wu(1, name="Prize")
    duel.duel.winner = True
    duel.duel.jack_fled = True
    bar = duel.settings.prize_threshold + 1
    duel.duel.rounds = [Round(stat="", player=Side(result=[bar, 0, 0]))]
    duel._award_prize()
    assert duel.duel.card_won is True
    assert duel.duel.prize_route is PrizeRoute.DECISIVE_BLOW


async def test_end_keeps_jacks_wager_when_fled():
    duel = _jack_duel()
    duel.duel.winner = True
    duel.duel.jack_fled = True
    staked = duel.state.bot.hand[0]
    duel.duel.bot.stakes = [staked]
    before = len(duel.state.bot.hand)
    await duel._end()
    assert staked in duel.state.bot.hand
    assert len(duel.state.bot.hand) == before


async def test_end_takes_the_wager_normally_when_not_fled():
    duel = _jack_duel()
    duel.duel.winner = True
    duel.duel.jack_fled = False
    staked = duel.state.bot.hand[0]
    duel.duel.bot.stakes = [staked]
    await duel._end()
    assert staked not in duel.state.bot.hand
    assert staked in duel.state.player.hand
