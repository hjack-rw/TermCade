"""Fixtures for Xiaolin Showdown: the card catalog, a dealt game, and the vault on screen."""

from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy

import pytest

from termcade.core.rng import Rng
from termcade.ui.app import EngineApp

from xiaolin_showdown.game import build_game
from xiaolin_showdown.logic.catalog import Catalog, load_catalog
from xiaolin_showdown.logic.models import Card
from xiaolin_showdown.logic.settings import XiaolinSettings
from xiaolin_showdown.logic.setup import new_game
from xiaolin_showdown.logic.state import XiaolinState
from xiaolin_showdown.screens.temple import TempleScreen

SEED = 1234


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    """The bundled card DB. Read-only — take copies through the ``card`` fixture."""
    return load_catalog()


@pytest.fixture
def card(catalog: Catalog):
    """A fresh copy of a catalog card, since duel and hand code mutate cards in place."""

    def _card(card_id: int) -> Card:
        return deepcopy(catalog.card(card_id))

    return _card


@pytest.fixture
def settings() -> XiaolinSettings:
    return XiaolinSettings()


@pytest.fixture
def state(catalog: Catalog) -> XiaolinState:
    """A freshly dealt game: Omi against a seeded opponent."""
    return new_game(catalog, Rng(SEED), catalog.character(1))


@pytest.fixture
def open_vault(tmp_path):
    """Boot the app straight onto the vault for a prepared ``state``, tooltips enabled.

    Yields ``(app, pilot)``. Pushing the screen directly skips the start menu, which would need
    clicking and is not what these tests are about.
    """

    @asynccontextmanager
    async def _open_vault(state: XiaolinState, size: tuple[int, int] = (150, 50)):
        app = EngineApp(build_game(), data_dir=tmp_path, seed=SEED)
        async with app.run_test(size=size, tooltips=True) as pilot:
            await pilot.pause()
            app.ctx.state = state
            app.push_screen(TempleScreen())
            await pilot.pause()
            await pilot.pause()
            yield app, pilot

    return _open_vault
