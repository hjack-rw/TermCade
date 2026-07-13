"""A showdown is fought in a named place — flavour over the element, never a rule.

The duelist still names a bare element, exactly as before. The place is drawn from that element's
pool and shown in its place, coloured by the element that scores. Nothing here may reach scoring.
"""

from __future__ import annotations

import pytest

from termcade.core.rng import Rng

from xiaolin_showdown.logic.constants import ELEMENTS
from xiaolin_showdown.logic.duel import Duel, DuelChoices, DuelState
from xiaolin_showdown.logic.models import Background
from xiaolin_showdown.logic.setup import new_game


def _choices() -> DuelChoices:
    async def first(options):
        return options[0]

    async def no_boost(_options):
        return None

    async def wager(options):
        return options[0]  # the smallest legal stake — one Wu, one exchange

    async def element(background):
        return background

    async def stat(options):
        return options[0]

    return DuelChoices(first, first, wager, no_boost, first, element, stat)


async def _setup(catalog, seed: int) -> DuelState:
    """Play Commitment and Setup for real, so the element is named the way the game names it."""
    state = new_game(catalog, Rng(seed), catalog.character(1))
    duel = Duel(state, Rng(seed), _choices())
    await duel.advance()  # Commitment
    await duel.advance()  # Setup — the element is named, and the place drawn
    return duel.duel


# --- the pool ----------------------------------------------------------------------


def test_a_place_belongs_to_every_element_it_names():
    """The two columns are a set of tags, not a rank — either name can summon the place."""
    sunflower = Background(1, "Sunflower Field", "fire", "earth")

    assert sunflower.belongs_to("fire")
    assert sunflower.belongs_to("earth")
    assert not sunflower.belongs_to("water")


def test_every_element_can_summon_a_place(catalog):
    """An element with an empty pool would show a bare element name — or crash."""
    for element in ELEMENTS:
        assert catalog.backgrounds_for(element), f"{element} has no places"


def test_a_pool_holds_only_places_that_name_that_element(catalog):
    for element in ELEMENTS:
        for place in catalog.backgrounds_for(element):
            assert place.belongs_to(element)


def test_a_dual_element_place_sits_in_both_pools(catalog):
    dual = next(b for b in catalog.backgrounds if b.sec_element)

    assert dual in catalog.backgrounds_for(dual.element)
    assert dual in catalog.backgrounds_for(dual.sec_element)


# --- the draw ----------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(1, 11))
async def test_the_place_is_drawn_from_the_named_element(catalog, seed):
    """The heart of it: a duelist who names WATER may never be sent somewhere dry."""
    duel = await _setup(catalog, seed)

    place = next(b for b in catalog.backgrounds if b.name == duel.background_name)

    assert place.belongs_to(duel.background)


async def test_the_same_seed_draws_the_same_place(catalog):
    """Off the seeded RNG, so a seed replays the same board — as everything else does."""
    first = await _setup(catalog, 7)
    again = await _setup(catalog, 7)

    assert first.background_name == again.background_name
    assert first.background_name is not None


async def test_different_seeds_draw_different_places(catalog):
    """Guards the test above: a constant would satisfy it just as well."""
    names = {(await _setup(catalog, seed)).background_name for seed in range(1, 20)}

    assert len(names) > 1


# --- flavour only ------------------------------------------------------------------


async def test_the_named_element_survives_the_draw(catalog):
    """The place is a costume. What scores is the element the duelist named, and that must not move."""
    duel = await _setup(catalog, 3)

    assert duel.background in ELEMENTS


async def test_drawing_the_place_does_not_disturb_the_duel_rng(catalog):
    """The whole promise: this is decoration.

    The place comes off a *sub-stream*. Drawing it from the duel's own RNG would shift every roll
    after it — every coin toss, every bot choice — so a purely cosmetic feature would quietly change
    how the game plays, and a seed would stop meaning what it meant.
    """
    state = new_game(catalog, Rng(5), catalog.character(1))
    rng = Rng(5)
    duel = Duel(state, rng, _choices())
    await duel.advance()  # Commitment

    before = rng.get_state()
    await duel.advance()  # Setup — draws a place
    after = rng.get_state()

    assert duel.duel.background_name is not None  # a place really was drawn
    assert before == after  # ...and the duel's own stream never moved


def test_a_spawned_stream_leaves_its_parent_untouched():
    """Guards the mechanism itself, at the engine level."""
    rng = Rng(1)
    before = rng.get_state()

    child = rng.spawn("flavour")
    child.choice([1, 2, 3, 4, 5])

    assert rng.get_state() == before


def test_the_same_parent_and_label_spawn_the_same_stream():
    assert Rng(9).spawn("bg").choice(range(1000)) == Rng(9).spawn("bg").choice(range(1000))


def test_a_different_label_spawns_a_different_stream():
    """Guards the test above: a constant child would satisfy it."""
    draws = {Rng(9).spawn(label).choice(range(10_000)) for label in ("a", "b", "c", "d")}

    assert len(draws) > 1
