"""The temple's numbered actions are clickable, not only typeable.

The panel reads as a list of keyboard shortcuts, and on a terminal it is one. On a phone there is no
number row, so without a click target those nine actions are the only things in the game a touch
player cannot reach.
"""

from __future__ import annotations

from rich.style import Style

from xiaolin_showdown.screens.temple import _ACTION_BY_KEY, _action_cell
from termcade.ui.screens.log import GameLogScreen


def _click_meta(text) -> str | None:
    for span in text.spans:
        if isinstance(span.style, Style) and span.style.meta.get("@click"):
            return span.style.meta["@click"]
    return None


def test_every_numbered_action_has_a_binding_to_click(tmp_path) -> None:
    """Read off BINDINGS, so a rebound key cannot leave its click pointing at the old action."""
    assert set(_ACTION_BY_KEY) == {str(n) for n in range(1, 10)}


def test_a_live_action_carries_the_same_action_its_key_runs() -> None:
    assert _click_meta(_action_cell("7. Game Log", {})) == "screen.game_log()"


def test_a_blocked_action_is_not_clickable() -> None:
    """Pressing its key does nothing, so neither should tapping it."""
    assert _click_meta(_action_cell("2. Draw a Card", {"2": "Your deck is empty."})) is None


async def test_clicking_an_action_opens_its_screen(open_vault, state) -> None:
    """The whole point: a tap gets you there, with no key pressed."""
    async with open_vault(state) as (app, pilot):
        panel = app.screen.query_one("#actions")
        region = panel.region
        target = next(
            (x, y)
            for y in range(region.y, region.bottom)
            for x in range(region.x, region.right)
            if "screen.game_log()" == app.screen.get_style_at(x, y).meta.get("@click")
        )

        await pilot.click("#actions", offset=(target[0] - region.x, target[1] - region.y))
        await pilot.pause()

        assert isinstance(app.screen, GameLogScreen)


async def test_committing_a_showdown_does_not_crash_the_duel(tmp_path) -> None:
    """The commit calls `hide_back` to take the touch player's way out away. Nothing covered that
    path, so deleting the method left every duel crashing on its first Continue while the suite
    stayed green."""
    from termcade.core.rng import Rng
    from termcade.ui.app import EngineApp
    from xiaolin_showdown.game import build_game
    from xiaolin_showdown.logic.catalog import load_catalog
    from xiaolin_showdown.logic.setup import new_game
    from xiaolin_showdown.screens.duel import DuelScreen
    from xiaolin_showdown.screens.temple import TempleScreen

    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(154, 36)) as pilot:
        await pilot.pause()
        catalog = load_catalog()
        app.ctx.state = new_game(catalog, Rng(1234), catalog.character(1))
        app.push_screen(TempleScreen())
        await pilot.pause()
        app.switch_screen(DuelScreen())
        await pilot.pause()
        await pilot.pause()

        await pilot.press("enter")  # commit: the showdown begins and there is no retreat
        await pilot.pause()
        await pilot.pause()

        assert app.is_running
        assert app.screen.BACK_ALLOWED is False
