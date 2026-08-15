"""Save must stay reachable on a screen too short to show every setting at once.

Save sits directly under GAME SETTINGS, outside the panel itself — a deliberate choice (left-aligned
under the section, not docked to the screen edge). On a screen too short for everything, the SCREEN
scrolls to reach it, same as any other page that outgrows its window.
"""

from __future__ import annotations

import pytest

from termcade.ui.app import EngineApp
from termcade.ui.widgets import BoxedPanel, Button

from xiaolin_showdown.game import build_game
from xiaolin_showdown.screens.reference.settings import SettingsScreen

pytestmark = pytest.mark.slow

# Shorter than the settings list is tall, which is the whole point — this is a phone in landscape.
_SHORT = (110, 24)


async def test_save_is_not_inside_the_panel(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path)
    async with app.run_test(size=_SHORT) as pilot:
        app.push_screen(SettingsScreen())
        await pilot.pause()

        save = app.screen.query_one("#save", Button)
        panel = app.screen.query_one("#game-settings-panel", BoxedPanel)

        assert save not in panel.walk_children(), "Save must stay a sibling of the panel, not inside it"


async def test_save_is_reachable_by_scrolling_the_screen(tmp_path):
    """Too short for everything at once: the SCREEN scrolls, and that has to be enough to reach it."""
    app = EngineApp(build_game(), data_dir=tmp_path)
    async with app.run_test(size=_SHORT) as pilot:
        app.push_screen(SettingsScreen())
        await pilot.pause()

        app.screen.scroll_end(animate=False)
        save = app.screen.query_one("#save", Button)
        # One pause is usually enough, but the post-scroll layout reflow isn't guaranteed to land
        # within a single pump under load — poll instead of trusting a fixed wait (same class of
        # flake as hover_tooltip in tests/conftest.py, same fix: CI, 2026-08-15).
        for _ in range(30):
            await pilot.pause()
            if save.region.bottom <= app.screen.size.height:
                break

        assert save.region.height > 0, "Save was not laid out at all"
        assert save.region.bottom <= app.screen.size.height, "Save is still off-screen after scrolling"


async def test_save_still_saves_from_there(tmp_path):
    """Moving a button is only safe if it still does its job — the handler matches on id, and the
    id has to keep reaching the screen from outside the panel.

    One pause per press, because that is what a player does. Sent in a single tick the two Pressed
    messages arrive out of order: Save is a child of the screen and the toggles are children of the
    panel, so Save's bubbles one hop less and overtakes.
    """
    app = EngineApp(build_game(), data_dir=tmp_path)
    async with app.run_test(size=_SHORT) as pilot:
        app.push_screen(SettingsScreen())
        await pilot.pause()
        before = app.ctx.settings.current.difficulty

        app.screen.query_one("#difficulty", Button).press()
        await pilot.pause()
        app.screen.query_one("#save", Button).press()
        await pilot.pause()

        assert app.ctx.settings.current.difficulty != before
