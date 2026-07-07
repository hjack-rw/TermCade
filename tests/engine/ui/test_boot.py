"""Smoke test: the engine boots headlessly to its placeholder scene."""

from __future__ import annotations

from termcade.ui.app import EngineApp, HelloScreen


async def test_app_boots_to_hello_scene():
    app = EngineApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, HelloScreen)
        assert app.screen.query_one("#hello")
