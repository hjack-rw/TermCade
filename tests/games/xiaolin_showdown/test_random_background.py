"""The arena as a random roll (settings.random_background, default on): revealed after the wager,
nobody's to pick — so the non-challenger is never asked for it, and a Hodoku Mouse cannot amend it.
"""

from __future__ import annotations

from termcade.core.rng import Rng

from dataclasses import replace

from factories import auto_choices, run_showdown

from xiaolin_showdown.logic.flow.battle import Round
from xiaolin_showdown.logic.schema.catalog import load_catalog
from xiaolin_showdown.logic.schema.constants import ELEMENTS
from xiaolin_showdown.logic.flow.duel import Duel
from xiaolin_showdown.logic.flow.setup import new_game
from xiaolin_showdown.logic.config.settings import XiaolinSettings


async def _background_must_not_be_asked(_options):
    raise AssertionError("the background must not be chosen when the arena is random")


def _duel(*, random_bg: bool):
    cat = load_catalog()
    rng = Rng(1)
    state = new_game(cat, rng, cat.character(1))
    settings = XiaolinSettings(**{**XiaolinSettings().__dict__, "random_background": 1 if random_bg else 0})
    choices = replace(auto_choices(), background=_background_must_not_be_asked)
    return state, Duel(state, rng, choices, settings)


async def test_a_random_arena_is_rolled_not_chosen():
    state, duel = _duel(random_bg=True)
    state.forced_priority = False  # the bot leads, so the PLAYER would answer the arena — but must not
    await run_showdown(duel, duel.settings)
    assert duel.duel.background in ELEMENTS  # got here without _background_must_not_be_asked firing


def test_the_mouse_cannot_amend_a_random_arena():
    _state, duel = _duel(random_bg=True)
    duel.duel.rounds.append(Round(stat="force"))
    duel.duel.background = "metal"
    assert duel._amend_options().elements == []


def test_the_mouse_can_amend_a_chosen_arena():
    _state, duel = _duel(random_bg=False)
    duel.duel.rounds.append(Round(stat="force"))
    duel.duel.background = "metal"
    assert duel._amend_options().elements  # the arena was picked, so the Mouse may re-set it
