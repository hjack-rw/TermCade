"""The Lore book on screen: it opens, it turns, and it goes back.

`test_lore.py` covers the pure split. This drives the real screen, which is the half a loader test
cannot see — a book that loads perfectly and crashes on open is still a broken book.
"""

from __future__ import annotations

import pytest
from termcade.ui.app import EngineApp
from textual.widgets import Static

from xiaolin_showdown.game import build_game
from xiaolin_showdown.logic.lore import PAGE_COLS, PAGE_ROWS
from xiaolin_showdown.screens.lore import LoreScreen
from xiaolin_showdown.screens.start import StartScreen

pytestmark = pytest.mark.slow


async def _boot(app, pilot):
    for _ in range(50):
        if app.screen_stack and isinstance(app.screen, StartScreen):
            return
        await pilot.pause()
    raise AssertionError("start screen never appeared")


async def _open_lore(app, pilot):
    await _boot(app, pilot)
    await pilot.click("#lore")
    await pilot.pause()
    assert isinstance(app.screen, LoreScreen)


async def test_the_lore_button_opens_the_book(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _open_lore(app, pilot)


async def test_the_book_opens_on_the_contents(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _open_lore(app, pilot)

        assert "Introduction" in str(app.screen.query_one("#lore-page", Static).render())


async def test_turning_forward_leaves_the_contents(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _open_lore(app, pilot)
        page = app.screen._page

        await pilot.press("right")
        await pilot.pause()

        assert app.screen._page == page + 1


async def test_a_number_jumps_to_that_chapter(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _open_lore(app, pilot)

        await pilot.press("3")
        await pilot.pause()

        chapter, index = app.screen._pages[app.screen._page]
        assert chapter is app.screen._book[2]
        assert index == 0


async def test_the_page_contract_matches_what_the_screen_actually_draws(tmp_path):
    """`PAGE_COLS`/`PAGE_ROWS` are what the overflow guard measures against, so they have to BE the
    drawing area. Let the CSS change without them and the guard silently checks a page nobody sees."""
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _open_lore(app, pilot)

        drawn = app.screen.query_one("#lore-page", Static).content_size

        assert (drawn.width, drawn.height) == (PAGE_COLS, PAGE_ROWS)


async def test_escape_returns_to_the_start_screen(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _open_lore(app, pilot)

        await pilot.press("escape")
        await pilot.pause()

        assert isinstance(app.screen, StartScreen)
