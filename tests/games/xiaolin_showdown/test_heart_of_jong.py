"""Heart of Jong (ANIMATE) — the seed of Mala Mala Jong's deferred assembly.

Fielded as its own Wu it prints ?/?/? and does nothing. Laid in the boost slot it comes alive: a flat
``ANIMATE_STAT`` form, always the arena's own element (never its resting metal, unlike Tongue of
Saiping), shown on the board as the character the background calls up.
"""

from __future__ import annotations

from copy import deepcopy

from termcade.core.rng import Rng

from factories import auto_choices

from xiaolin_showdown.logic import wear
from xiaolin_showdown.logic.battle import Round
from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.constants import ELEMENTS
from xiaolin_showdown.logic.duel import Duel
from xiaolin_showdown.logic.summons import _JONG_FORMS
from xiaolin_showdown.logic.mechanics.powers import ANIMATE_FIELD_STAT, ANIMATE_STAT, is_boost_slot
from xiaolin_showdown.logic.mechanics.resolve import as_boost, resolve_played_power
from xiaolin_showdown.logic.setup import new_game
from xiaolin_showdown.logic.turn import duel_value

HEART = 74


def _duel_on(background: str) -> Duel:
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.rounds.append(Round(stat="force"))
    duel.duel.background = background
    return duel


def test_the_heart_is_a_boost_slot_wu():
    assert is_boost_slot(load_catalog().card(HEART).power)


def test_it_prints_no_stats_of_its_own():
    """Alone it does nothing — a ?/?/? card contributes zero unless the boost slot wakes it."""
    heart = load_catalog().card(HEART)
    assert all(value is None for value in heart.stats.values())


def test_fielded_as_a_card_it_is_a_middling_metal_body():
    """Not in the boost slot: it keeps its own name and its resting metal, a flat ANIMATE_FIELD_STAT body
    — weaker than the boosted summon (a named form in the arena's element), which belongs to the boost."""
    battle = Round(stat="force")
    resolve_played_power(battle, deepcopy(load_catalog().card(HEART)), is_player=True, element="metal")
    stood = battle.player.queue[0]
    assert set(stood.stats.values()) == {ANIMATE_FIELD_STAT}
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


def test_boosting_the_heart_flags_the_summoner():
    duel = _duel_on("metal")
    duel._commit_boost(deepcopy(duel.state.catalog.card(HEART)), is_player=True, element="metal")
    assert duel.duel.round.heart_summoner is True  # the far side is now owed a balance Wu


async def test_a_boosted_heart_lets_the_opponent_field_an_off_wager_wu():
    """The counter: the side that did NOT boost may field one extra Wu — it scores, but is never staked."""
    duel = _duel_on("metal")
    duel.duel.round.heart_summoner = True  # the player boosted the Heart; the bot answers
    before_queue = len(duel.duel.round.bot.queue)
    before_stakes = len(duel.duel.bot.stakes)
    await duel._offer_balance(duel.duel.round)
    assert len(duel.duel.round.bot.queue) == before_queue + 1  # a fighter joined the bot's side
    assert len(duel.duel.bot.stakes) == before_stakes  # ...off the wager — it cannot be lost
    assert len(duel.duel.bot.off_wager) == 1  # ...but held for wear, so it cannot be spammed


async def test_the_off_wager_wu_still_wears():
    """It is never lost, but it is used: it rides the same wear count as any Wu, so it deposits out."""
    duel = _duel_on("metal")
    duel.duel.round.heart_summoner = True
    await duel._offer_balance(duel.duel.round)
    answered = duel.duel.bot.off_wager[0]
    before = answered.uses
    wear.record_showdown(duel.state.bot, duel.duel.bot.off_wager, rng=duel.rng)
    assert answered.uses == before + 1  # one showdown answered, one use spent


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
