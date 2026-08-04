"""``unlock`` — the boss-ladder cheat, reachable from the main menu.

Every other console command acts on a live run (see test_console.py); this one only touches
settings, so it has to work with no run in progress — that's the whole reason it exists.
"""

from __future__ import annotations

import pytest
from textual.widgets import Input

from termcade.core.settings import SettingsStore
from termcade.ui.app import EngineApp
from termcade.ui.screens.console import DEBUG_ENV, ConsoleScreen

from xiaolin_showdown.game import build_game
from xiaolin_showdown.logic.ladder import LADDER, progress


@pytest.fixture(autouse=True)
def _debug_build(monkeypatch):
    monkeypatch.setenv(DEBUG_ENV, "1")


async def test_the_console_opens_from_the_main_menu_with_no_run_started(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path)
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        assert app.ctx is not None
        assert app.ctx.state is None  # the main menu: no game in progress

        await pilot.press("grave_accent")
        await pilot.pause()

        assert isinstance(app.screen, ConsoleScreen)


async def test_unlock_opens_the_whole_ladder_with_no_run_in_progress(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path)
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        await pilot.press("grave_accent")
        await pilot.pause()

        app.screen.query_one("#console-input", Input).value = "unlock"
        await pilot.press("enter")
        await pilot.pause()

        assert app.ctx is not None
        assert progress(app.ctx.settings.current) == len(LADDER)


async def test_unlock_survives_a_restart(tmp_path):
    """Written into the settings file like a real ladder win, so a fresh process reads it back."""
    app = EngineApp(build_game(), data_dir=tmp_path)
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        await pilot.press("grave_accent")
        await pilot.pause()
        app.screen.query_one("#console-input", Input).value = "unlock"
        await pilot.press("enter")
        await pilot.pause()

    reloaded = SettingsStore(
        tmp_path / "settings.json",
        build_game().default_settings,
        private_options=build_game().private_options,
    ).load()

    assert progress(reloaded) == len(LADDER)
