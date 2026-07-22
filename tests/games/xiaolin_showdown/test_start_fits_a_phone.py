"""The start screen on a screen too narrow for the figure fonts.

The cabinet's banner is 89 columns wide and a phone held upright has about 81, so the brand was the
one thing on this screen that could not fit — it ran off the side while everything under it sat
comfortably inside.
"""

from __future__ import annotations

import pytest

from termcade.ui.app import BANNER, EngineApp

from xiaolin_showdown.game import build_game
from xiaolin_showdown.screens._logo import TITLE_ART, TITLE_ART_STACKED

pytestmark = pytest.mark.slow

_PORTRAIT = (81, 40)  # a phone held upright, at the font size the auto-fit picks
_DESKTOP = (150, 50)


def _widest(art: str) -> int:
    return max(len(line) for line in art.splitlines())


async def test_the_wordmarks_are_wider_than_a_phone(tmp_path) -> None:
    """The premise. If either of these ever shrinks, the swap below stops earning its keep."""
    assert _widest(BANNER) > _PORTRAIT[0]
    # The title survives a 390px phone with eight columns to spare and runs off a smaller one.
    assert _widest(TITLE_ART) > 60


async def test_a_narrow_screen_shows_the_compact_wordmarks(tmp_path) -> None:
    app = EngineApp(build_game(), data_dir=tmp_path)
    async with app.run_test(size=_PORTRAIT) as pilot:
        await pilot.pause()
        screen = app.screen
        assert not screen.query_one("#banner").display
        assert not screen.query_one("#title").display
        assert screen.query_one("#banner-compact").display
        assert screen.query_one("#title-compact").display


async def test_nothing_on_the_start_screen_overflows_a_phone(tmp_path) -> None:
    """The point of the exercise: every wordmark inside the screen's own width."""
    app = EngineApp(build_game(), data_dir=tmp_path)
    async with app.run_test(size=_PORTRAIT) as pilot:
        await pilot.pause()
        for wid in ("#banner-compact", "#title-compact", ".subtitle"):
            widget = app.screen.query_one(wid)
            assert widget.region.width <= _PORTRAIT[0], f"{wid} runs off the side"


async def test_a_desktop_still_gets_the_figure_fonts(tmp_path) -> None:
    """The compact pair is a concession to width, not a redesign."""
    app = EngineApp(build_game(), data_dir=tmp_path)
    async with app.run_test(size=_DESKTOP) as pilot:
        await pilot.pause()
        screen = app.screen
        assert screen.query_one("#banner").display
        assert screen.query_one("#title").display
        assert not screen.query_one("#banner-compact").display
        assert not screen.query_one("#title-compact").display


def test_the_stacked_title_is_centred_on_itself() -> None:
    """Two words of different widths in one block: without a baked-in indent the short one sits hard
    against the left edge, and the wordmark reads as broken rather than as stacked."""
    lines = [line for line in TITLE_ART_STACKED.strip("\n").splitlines() if line.strip()]
    width = max(len(line) for line in lines)
    for line in lines:
        left = len(line) - len(line.lstrip())
        right = width - len(line.rstrip())
        assert abs(left - right) <= 1, f"off centre by {left - right}: {line!r}"


async def test_the_compact_wordmarks_are_narrower_than_the_full_ones(tmp_path) -> None:
    """Width is the whole point — the brand ran off the side of the phone, not off the bottom."""
    app = EngineApp(build_game(), data_dir=tmp_path)
    async with app.run_test(size=_PORTRAIT) as pilot:
        await pilot.pause()
        for wid, full in (("#banner-compact", BANNER), ("#title-compact", TITLE_ART)):
            drawn = max(len(line) for line in str(app.screen.query_one(wid).render()).splitlines())
            assert drawn < _widest(full), f"{wid} is no narrower than the mark it replaces"
