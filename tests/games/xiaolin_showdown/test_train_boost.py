"""Summon Wu (TRAIN_BOOST): spent at the temple they shove +TRAIN_BOOST_STEP into the training bar and
are discarded. Fielded, they show what they call up — the beast follows the arena element.
"""

from __future__ import annotations

from copy import deepcopy

from termcade.core.rng import Rng

from xiaolin_showdown.logic.actions import usable_powers, use_power
from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.duel import Duel, DuelChoices
from xiaolin_showdown.logic.mechanics.powers import Mechanic, mechanic_of
from xiaolin_showdown.logic.setup import new_game
from xiaolin_showdown.logic.training import STAT_CAP, TRAIN_BOOST_STEP

TONGUE = 68  # Tongue of Saiping — summon "{beast}"
IMO = 69  # Imo Gazer — summon "a Drawing of {beast}"
ZING = 70  # Zing Zom-Bone — summon "a Horde of Zombies" (fixed), and a curse


def _seed(state, cid):
    card = deepcopy(state.catalog.card(cid))
    state.player.hand.append(card)
    return card


# --- the temple side: spend it to train ------------------------------------------


def test_spending_a_summon_shoves_the_training_bar(state):
    tongue = _seed(state, TONGUE)
    before = state.player.training
    use_power(state, tongue, is_player=True, rng=Rng(1))
    assert state.player.training == before + TRAIN_BOOST_STEP


def test_a_spent_summon_leaves_the_hand(state):
    tongue = _seed(state, TONGUE)
    use_power(state, tongue, is_player=True, rng=Rng(1))
    assert not any(mechanic_of(c.power) is Mechanic.TRAIN_BOOST for c in state.player.whole_hand)


def test_a_summon_is_hidden_once_every_stat_is_capped(state):
    _seed(state, TONGUE)
    for stat in state.player.character.stats:
        state.player.character.stats[stat] = STAT_CAP
    offered = [c for c in usable_powers(state, 1) if mechanic_of(c.power) is Mechanic.TRAIN_BOOST]
    assert not offered


# --- the board side: the summon follows the arena --------------------------------


async def _first(options):
    return options[0]


async def _no_boost(_options):
    return None


async def _one_wu(_options):
    return 1


def _duel_on(background):
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))  # Omi
    duel = Duel(state, Rng(1), DuelChoices(_first, _first, _one_wu, _no_boost, _first, _first, _first))
    duel.duel.background = background
    return duel


def test_the_animal_follows_the_arena_element():
    duel = _duel_on("water")
    assert duel._summon_display(deepcopy(duel.state.catalog.card(TONGUE)), is_player=True) == "a Pod of Seals"


def test_a_metal_arena_summons_a_troop_of_monkeys():
    duel = _duel_on("metal")
    assert duel._summon_display(deepcopy(duel.state.catalog.card(TONGUE)), is_player=True) == "a Troop of Monkeys"


def test_the_drawing_is_a_mythic_beast_of_the_arena():
    """Imo Gazer draws its own pool to life — the Four Symbols and the Qilin, one per element."""
    duel = _duel_on("wind")
    got = duel._summon_display(deepcopy(duel.state.catalog.card(IMO)), is_player=True)
    assert got == "the Azure Dragon"


def test_the_zombies_are_fixed_whatever_the_arena():
    duel = _duel_on("fire")
    assert duel._summon_display(deepcopy(duel.state.catalog.card(ZING)), is_player=True) == "a Horde of Zombies"
