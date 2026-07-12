"""The Music toggle on the Settings screen — it has to persist AND take effect on Save.

Boots the real app, so it is a slow test. The player used is a stand-in that records what it was
asked to do: the suite runs muted, and a test that actually played a sound would be worse than one
that failed.
"""

from __future__ import annotations

from array import array
from dataclasses import replace

import pytest

from termcade.core.audio import MUSIC_OPTION
from termcade.ui.app import EngineApp
from termcade.ui.widgets import Button

from xiaolin_showdown.game import build_game
from xiaolin_showdown.screens.settings import SettingsScreen

pytestmark = pytest.mark.slow


class SpyPlayer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def play_loop(self, wav: bytes) -> None:
        self.calls.append("play")

    def play_once(self, pcm: array) -> None:
        self.calls.append("sfx")

    def stop(self) -> None:
        self.calls.append("stop")

    def close(self) -> None:
        self.calls.append("close")


async def _open_settings(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path)
    return app


async def test_saving_with_music_off_persists_the_option(tmp_path):
    app = await _open_settings(tmp_path)
    async with app.run_test(size=(150, 50)) as pilot:
        app._player = SpyPlayer()
        app.push_screen(SettingsScreen())
        await pilot.pause()

        app.screen.query_one("#music", Button).press()
        app.screen.query_one("#save", Button).press()
        await pilot.pause()

    assert app.ctx.settings.current.options[MUSIC_OPTION] is False


async def test_turning_music_off_stops_it_there_and_then(tmp_path):
    """Not on the next launch — the player expects the silence when they hit Save."""
    app = await _open_settings(tmp_path)
    async with app.run_test(size=(150, 50)) as pilot:
        spy = SpyPlayer()
        app._player = spy
        app.push_screen(SettingsScreen())
        await pilot.pause()

        app.screen.query_one("#music", Button).press()
        app.screen.query_one("#save", Button).press()
        await pilot.pause()

        assert "stop" in spy.calls


async def test_turning_music_back_on_replays_it_without_re_rendering(tmp_path):
    """The theme costs the better part of a second to synthesize; a toggle must reuse the bytes."""
    app = await _open_settings(tmp_path)
    spy = SpyPlayer()
    # Both before mount, on purpose. Mounting starts the render worker whenever no theme is
    # cached, and that worker would land a second later and overwrite the stub — the reuse path
    # this test exists to check would never be the thing that ran.
    app._player = spy
    app._theme = b"RIFF-already-rendered"
    async with app.run_test(size=(150, 50)) as pilot:
        current = app.ctx.settings.current
        app.ctx.settings.save(
            replace(current, options={**current.options, MUSIC_OPTION: False})
        )

        app.push_screen(SettingsScreen())
        await pilot.pause()
        app.screen.query_one("#music", Button).press()  # back to ON
        app.screen.query_one("#save", Button).press()
        await pilot.pause()

        # Not `calls[-1]`: every button press now sounds a click, so the theme's "play" is no
        # longer the last thing the player heard. What must hold is that it played at all, and
        # that it played the bytes we already had rather than synthesizing them again.
        assert "play" in spy.calls
        assert app._theme == b"RIFF-already-rendered"
