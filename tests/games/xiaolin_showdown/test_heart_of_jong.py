"""Heart of Jong (ANIMATE) — the seed of Mala Mala Jong's deferred assembly.

Fielded as its own Wu it prints ?/?/? and does nothing. Laid in the boost slot it comes alive: a flat
``ANIMATE_STAT`` form, always the arena's own element (never its resting metal, unlike Tongue of
Saiping), shown on the board as the character the background calls up.
"""

from __future__ import annotations

from copy import deepcopy

from termcade.core.rng import Rng

from xiaolin_showdown.logic.battle import Round
from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.constants import ELEMENTS
from xiaolin_showdown.logic.duel import Duel, DuelChoices
from xiaolin_showdown.logic.summons import _JONG_FORMS
from xiaolin_showdown.logic.mechanics.powers import ANIMATE_STAT, is_boost_slot
from xiaolin_showdown.logic.mechanics.resolve import as_boost, resolve_played_power
from xiaolin_showdown.logic.setup import new_game
from xiaolin_showdown.logic.turn import duel_value

HEART = 74


async def _first(options):
    return options[0]


async def _no_boost(_options):
    return None


async def _one_wu(_options):
    return 1


def _duel_on(background: str) -> Duel:
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    duel = Duel(state, Rng(1), DuelChoices(_first, _first, _one_wu, _no_boost, _first, _first, _first))
    duel.duel.rounds.append(Round(stat="force"))
    duel.duel.background = background
    return duel


def test_the_heart_is_a_boost_slot_wu():
    assert is_boost_slot(load_catalog().card(HEART).power)


def test_it_prints_no_stats_of_its_own():
    """Alone it does nothing — a ?/?/? card contributes zero unless the boost slot wakes it."""
    heart = load_catalog().card(HEART)
    assert all(value is None for value in heart.stats.values())


def test_fielded_as_a_card_it_is_a_flat_metal_construct():
    """Not in the boost slot: it keeps its own name and its resting metal, a flat ANIMATE_STAT Wu — the
    summon (a named form in the arena's element) belongs to the boost slot alone."""
    battle = Round(stat="force")
    resolve_played_power(battle, deepcopy(load_catalog().card(HEART)), is_player=True, element="metal")
    stood = battle.player.queue[0]
    assert set(stood.stats.values()) == {ANIMATE_STAT}
    assert stood.name == "Heart of Jong"
    assert stood.element == "metal"


def test_as_a_boost_it_wakes_to_a_flat_form():
    woke = as_boost(deepcopy(load_catalog().card(HEART)), "fire", "force")
    assert set(woke.stats.values()) == {ANIMATE_STAT}  # flat, read off the constant — no Morpher dip


def test_the_form_always_counts_as_the_background_not_metal():
    """Unlike Tongue of Saiping (metal, dragged by the arena), the Heart's element is always the arena's."""
    woke = as_boost(deepcopy(load_catalog().card(HEART)), "water", "force")
    assert woke.element == "water"


def test_the_form_is_named_by_the_background():
    duel = _duel_on("water")
    duel._commit_boost(deepcopy(duel.state.catalog.card(HEART)), is_player=True, element="water")
    assert duel.duel.round.player.queue[-1].name == _JONG_FORMS["water"]  # Raksha


def test_every_arena_element_has_a_form():
    assert set(_JONG_FORMS) == set(ELEMENTS)


def test_a_metal_arena_calls_the_t_rex_for_anyone():
    duel = _duel_on("metal")
    duel._commit_boost(deepcopy(duel.state.catalog.card(HEART)), is_player=True, element="metal")
    assert duel.duel.round.player.queue[-1].name == "T-Rex"


def test_jacks_metal_form_is_his_own_dude_bot():
    """The dormant Jack hook: when Jack Spicer casts it on metal, his construct answers, not the T-Rex.
    He is not in the roster yet, so this stands in for the future by renaming the caster to his."""
    duel = _duel_on("metal")
    jack = deepcopy(duel.state.player.character)
    jack.name = "Jack_Spicer"
    duel.state.player.character = jack
    duel._commit_boost(deepcopy(duel.state.catalog.card(HEART)), is_player=True, element="metal")
    assert duel.duel.round.player.queue[-1].name == "Dude-Bot"


def test_the_heart_is_not_banked_as_junk():
    """It prints ?/?/? but the boost it can be is real, so the bot must not cash it for nothing."""
    assert duel_value(load_catalog().card(HEART)) > 0
