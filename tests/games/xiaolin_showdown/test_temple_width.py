"""The temple's state row, measured against the width it is actually given.

A landscape phone reports 110 columns — wider than some laptops — so no width breakpoint fires for
it, and it used to spend 40 of those columns on margins meant for a desktop. The duelist row needs
about 90 and was handed 70, so Deck and Initiative truncated to their own labels: a value replaced
by the word introducing it, which is the one thing a label must never cost.
"""

from __future__ import annotations

import pytest

from termcade.core.rng import Rng
from termcade.ui.app import EngineApp
from xiaolin_showdown.game import build_game
from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.setup import new_game
from xiaolin_showdown.screens.temple import TempleScreen

pytestmark = pytest.mark.slow

# A landscape phone at either font size: the column count is the same, only the row count moves.
LANDSCAPE = (110, 31)
# Salvador Cumo is the longest playable name, which is what makes the row worth measuring.
LONG_NAME = 7


async def _temple(app, pilot, size):
    await pilot.pause()
    catalog = load_catalog()
    app.ctx.state = new_game(catalog, Rng(1234), catalog.character(LONG_NAME), roster="boss")
    app.push_screen(TempleScreen())
    for _ in range(6):
        await pilot.pause()


def _state_rows(app) -> list[str]:
    region = app.screen.query_one("#state").region
    strips = app.screen._compositor.render_strips(app.size)
    return [
        "".join(segment.text for segment in strips[y])[region.x : region.right]
        for y in range(region.y, region.bottom)
    ]


async def test_a_phone_gives_the_state_row_most_of_its_grid(tmp_path, monkeypatch):
    """Not a fixed number — a proportion, so the test says "the margins are not the point" rather
    than restating whatever the stylesheet currently says."""
    monkeypatch.setenv("TERMCADE_TOUCH", "1")
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=LANDSCAPE) as pilot:
        await _temple(app, pilot, LANDSCAPE)
        width = app.screen.query_one("#state").size.width
        assert width >= LANDSCAPE[0] * 0.9, f"the row got {width} of {LANDSCAPE[0]} columns"


async def test_nothing_in_the_state_row_truncates_on_a_phone(tmp_path, monkeypatch):
    """The ellipsis is the whole symptom. Rich puts it wherever it ran out of room, so its presence
    anywhere in the row means something the player needed was dropped."""
    monkeypatch.setenv("TERMCADE_TOUCH", "1")
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=LANDSCAPE) as pilot:
        await _temple(app, pilot, LANDSCAPE)
        rows = _state_rows(app)
    assert not any("…" in row for row in rows), f"the row was cut: {rows}"


async def test_a_phone_shows_the_duelist_by_their_first_name(tmp_path, monkeypatch):
    monkeypatch.setenv("TERMCADE_TOUCH", "1")
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=LANDSCAPE) as pilot:
        await _temple(app, pilot, LANDSCAPE)
        rows = _state_rows(app)
    assert any("SALVADOR" in row for row in rows)
    assert not any("SALVADOR CUMO" in row for row in rows)


async def test_a_desktop_still_gets_the_whole_name(tmp_path, monkeypatch):
    """`-touch` is the switch, and a terminal is not a phone however narrow the window gets."""
    monkeypatch.delenv("TERMCADE_TOUCH", raising=False)
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 45)) as pilot:
        await _temple(app, pilot, (150, 45))
        rows = _state_rows(app)
    assert any("SALVADOR CUMO" in row for row in rows)
