"""The Hodoku Mouse fielded in a showdown (AMEND at play): rewrite one term of the current round.

Fired when the player fields the Mouse, after the reveal, before the round is weighed — the contested
stat, the arena, or the challenger's ground. It fights as its own 1/1/1 too. Only the player amends.
"""

from __future__ import annotations

from copy import deepcopy

from termcade.core.rng import Rng

from dataclasses import replace

from factories import auto_choices, run_showdown

from xiaolin_showdown.logic.flow.battle import Round
from xiaolin_showdown.logic.schema.catalog import load_catalog
from xiaolin_showdown.logic.flow.duel import Amend, Duel
from xiaolin_showdown.logic.mechanics.resolve import resolve_played_power
from xiaolin_showdown.logic.flow.setup import new_game
from xiaolin_showdown.logic.config.settings import XiaolinSettings

MOUSE = 66  # Hodoku Mouse — amend/play
FIST = 6  # Fist of Tebigong — a plain Wu, no power of its own
BRAS = 16  # Bras Finger — a plain 1/1/1, to swap in


def _duel_with_a_round(stat="force", background="metal"):
    """A Duel parked on one open round with known terms — for exercising ``_apply_amend`` directly."""
    cat = load_catalog()
    rng = Rng(1)
    state = new_game(cat, rng, cat.character(1))
    duel = Duel(state, rng, auto_choices())
    duel.duel.challenge = stat
    duel.duel.background = background
    duel.duel.rounds.append(Round(stat=stat))
    return state, duel


def test_amend_switches_the_contested_stat():
    _state, duel = _duel_with_a_round(stat="force")
    duel._apply_amend(Amend("challenge", "agility"))
    assert duel.duel.round.stat == "agility"


def test_amend_recolours_the_arena():
    _state, duel = _duel_with_a_round(background="metal")
    duel._apply_amend(Amend("background", "fire"))
    assert duel.duel.background == "fire"


def test_amend_takes_the_challengers_ground():
    state, duel = _duel_with_a_round()
    duel._apply_amend(Amend("initiative"))
    assert state.conch_tiebreak is True


def test_amend_raises_the_wager():
    _state, duel = _duel_with_a_round()
    duel.duel.wager = 1
    duel._apply_amend(Amend("wager", "2"))
    assert duel.duel.wager == 2


def test_amend_swaps_a_fielded_wu_for_one_in_hand():
    """The pulled Wu's stand-in in the queue becomes the Wu swapped in, and the two change places
    between the field and the hand."""
    cat = load_catalog()
    rng = Rng(1)
    state = new_game(cat, rng, cat.character(1))
    duel = Duel(state, rng, auto_choices())
    duel.duel.rounds.append(Round(stat="force"))

    fielded = deepcopy(cat.card(FIST))  # already down this battle
    duel.duel.player.stakes.append(fielded)
    resolve_played_power(duel.duel.round, fielded, is_player=True, element="metal")
    bench = deepcopy(cat.card(BRAS))
    state.player.hand.append(bench)

    duel._apply_amend(Amend("swap", swap_out=fielded, swap_in=bench))

    assert any(c.id == BRAS for c in duel.duel.round.player.queue)  # the new Wu took the field
    assert any(c.id == FIST for c in state.player.hand)  # the pulled Wu is back in hand


def test_amend_options_exclude_the_terms_already_set():
    _state, duel = _duel_with_a_round(stat="force", background="metal")
    options = duel._amend_options()
    assert "force" not in options.stats
    assert "metal" not in options.elements


def test_amend_only_ever_raises_the_wager_never_lowers_it():
    """Post-reveal you cannot un-field, so the offered counts are all above the current wager."""
    _state, duel = _duel_with_a_round()
    duel.duel.wager = 2
    assert all(n > 2 for n in duel._amend_options().wagers)


async def test_a_fielded_mouse_rewrites_the_round_it_is_played_in():
    cat = load_catalog()
    rng = Rng(1)
    state = new_game(cat, rng, cat.character(1))
    state.player.hand = [deepcopy(cat.card(MOUSE)), deepcopy(cat.card(FIST))]
    state.forced_priority = True  # the player leads and names the challenge

    async def _challenge(_options):
        return "force"

    async def _play_the_mouse(playable):
        # The bot names the wager (the player leads), so there may be a second Wu to field — play the
        # Mouse whenever it is still in hand, the Fist otherwise.
        return next((c for c in playable if c.id == MOUSE), playable[0])

    async def _amend(_options):
        return Amend("challenge", "agility")

    choices = replace(auto_choices(), challenge=_challenge, card=_play_the_mouse, amend=_amend)
    duel = Duel(state, rng, choices)

    await run_showdown(duel, XiaolinSettings())

    assert duel.duel.rounds[0].stat == "agility"  # the Mouse switched the contest, after the reveal
