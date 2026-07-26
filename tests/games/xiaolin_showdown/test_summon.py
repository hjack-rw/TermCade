"""Summon Wu: fielded, they enter the board as the thing they call up, not as themselves.

Pure flavour — the stats are the Wu's own. The hand still shows the Wu; only the fielded copy on the
board takes the summoned name (``{caster}`` fills with the fielding duelist's character).
"""

from __future__ import annotations

from copy import deepcopy

from termcade.core.rng import Rng

from factories import run_showdown

from xiaolin_showdown.logic.battle import Round
from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.duel import Duel, DuelChoices
from xiaolin_showdown.logic.mechanics.resolve import resolve_played_power
from xiaolin_showdown.logic.setup import new_game
from xiaolin_showdown.logic.settings import XiaolinSettings

RING = 60  # Ring of Nine Xing — summon "Clone of {caster}"
FIST = 6  # Fist of Tebigong — a plain Wu, no summon


async def _first(options):
    return options[0]


async def _no_boost(_options):
    return None


async def _one_wu(_options):
    return 1


def _duel(character_id=1):
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(character_id))
    choices = DuelChoices(_first, _first, _one_wu, _no_boost, _first, _first, _first)
    return state, Duel(state, Rng(1), choices)


def test_summon_display_names_a_clone_of_the_caster():
    state, duel = _duel(character_id=1)  # Omi
    assert duel._summon_display(deepcopy(state.catalog.card(RING)), is_player=True) == "Clone of Omi"


def test_summon_display_uses_the_short_caster_name():
    """A long character goes by its first name in the clone — Chase Young -> Chase, not the mouthful."""
    state, duel = _duel()
    state.player.character = deepcopy(state.catalog.character(13))  # Chase_Young
    assert duel._summon_display(deepcopy(state.catalog.card(RING)), is_player=True) == "Clone of Chase"


def test_a_plain_wu_has_no_summon_display():
    state, duel = _duel()
    assert duel._summon_display(deepcopy(state.catalog.card(FIST)), is_player=True) is None


def test_a_summon_stand_in_takes_the_summoned_name_not_the_wu_name():
    cat = load_catalog()
    battle = Round()
    resolve_played_power(
        battle, deepcopy(cat.card(RING)), is_player=True, element="metal", display_name="Clone of Omi"
    )
    assert battle.player.queue[0].name == "Clone of Omi"


def test_a_plain_wu_keeps_its_own_name_on_the_board():
    cat = load_catalog()
    battle = Round()
    resolve_played_power(battle, deepcopy(cat.card(FIST)), is_player=True, element="metal")
    assert battle.player.queue[0].name == cat.card(FIST).name


async def test_fielding_the_ring_shows_a_clone_of_omi_on_the_board():
    cat = load_catalog()
    rng = Rng(1)
    state = new_game(cat, rng, cat.character(1))  # Omi
    state.player.hand = [deepcopy(cat.card(RING)), deepcopy(cat.card(FIST))]
    state.forced_priority = True

    async def _play_the_ring(playable):
        return next((c for c in playable if c.id == RING), playable[0])

    choices = DuelChoices(_first, _first, _one_wu, _no_boost, _play_the_ring, _first, _first)
    duel = Duel(state, rng, choices)

    await run_showdown(duel, XiaolinSettings())

    fielded = [c.name for r in duel.duel.rounds for c in r.player.queue]
    assert "Clone of Omi" in fielded  # the board shows the summon, not "Ring of Nine Xing"
