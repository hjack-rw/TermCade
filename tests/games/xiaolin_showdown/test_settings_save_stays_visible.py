"""Save must stay reachable on a screen too short to show every setting at once.

The settings panel scrolls once its rows outgrow it. Save used to be the panel's last child, so on
a phone the only way to commit a change scrolled out of sight — the player could edit everything
and then have nothing to press.
"""

from __future__ import annotations

import pytest

from termcade.ui.app import EngineApp
from termcade.ui.widgets import BoxedPanel, Button

from xiaolin_showdown.game import build_game
from xiaolin_showdown.screens.settings import SettingsScreen

pytestmark = pytest.mark.slow

# Shorter than the settings list is tall, which is the whole point — this is a phone in landscape.
_SHORT = (110, 24)


async def test_save_is_not_inside_the_scrolling_panel(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path)
    async with app.run_test(size=_SHORT) as pilot:
        app.push_screen(SettingsScreen())
        await pilot.pause()

        save = app.screen.query_one("#save", Button)
        panel = app.screen.query_one(BoxedPanel)

        assert save not in panel.walk_children(), "scrolling the settings would take Save with them"


async def test_save_is_on_screen_when_the_settings_overflow(tmp_path):
    """The panel scrolls; Save keeps its place at the bottom regardless."""
    app = EngineApp(build_game(), data_dir=tmp_path)
    async with app.run_test(size=_SHORT) as pilot:
        app.push_screen(SettingsScreen())
        await pilot.pause()

        panel = app.screen.query_one(BoxedPanel)
        panel.scroll_end(animate=False)
        await pilot.pause()

        save = app.screen.query_one("#save", Button)
        assert save.region.height > 0, "Save was not laid out at all"
        assert save.region.bottom <= app.screen.size.height, "Save fell off the bottom"


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
