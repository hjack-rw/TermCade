"""Smoke tests: the engine boots headlessly — attract scene with no game, root screen with one."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from termcade.app.game import Game
from termcade.ui.app import EngineApp, HelloScreen
from termcade.ui.screens.base import EngineScreen


async def test_app_boots_to_attract_scene_without_a_game():
    app = EngineApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, HelloScreen)
        assert app.screen.query_one("#hello")


class _ProbeScreen(EngineScreen):
    def compose(self) -> ComposeResult:
        yield Static("probe", id="probe")


class _ProbeState:
    schema_version = 1

    def snapshot(self):
        return {}

    @classmethod
    def restore(cls, data, ctx):
        return cls()


async def test_app_with_game_boots_to_root_and_wires_ctx(tmp_path):
    game = Game(game_id="probe", title="Probe", state_cls=_ProbeState, root_screen=_ProbeScreen)
    app = EngineApp(game, data_dir=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, _ProbeScreen)
        assert app.ctx is not None
        assert app.screen.ctx is app.ctx  # EngineScreen.ctx resolves to the app's context
