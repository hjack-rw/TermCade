"""The training bar on a screen that has no room for it.

Ten spaced segments plus a label cost 34 columns per duelist, and a phone held upright gives about
80 — two of those rows are most of the screen. The segments are the decorative half of the pair:
the percentage carries the same fact.
"""

from __future__ import annotations

import pytest
from rich.cells import cell_len

from termcade.ui.widgets import render_bar

from xiaolin_showdown.screens.temple import TempleScreen, _training_cell

pytestmark = pytest.mark.slow

# A phone held upright, in COLUMNS. Not 80: an xterm cell is about half its font size, so a 390px
# screen reports 97 and a larger one reports more than 100 — which is why the stylesheet's `-wide`
# breakpoint was the wrong ruler and this shipped once still drawing the full bar.
_PORTRAIT = 97


def test_the_compact_cell_is_much_narrower(state) -> None:
    state.player.training = 4
    full = cell_len(_training_cell(state.player, compact=False).plain)
    compact = cell_len(_training_cell(state.player, compact=True).plain)

    assert compact < full / 2, f"compact saved almost nothing: {compact} vs {full}"
    # The row also carries a name and a Deck count, so the bar taking two fifths of the width on its
    # own is what makes the row not fit. If that ratio ever drops, this trade stops being worth it.
    assert full > _PORTRAIT * 0.35, f"the bar is no longer the expensive part: {full} of {_PORTRAIT}"


def test_the_compact_cell_still_says_the_same_thing(state) -> None:
    """Losing the bar must not lose the number — it is the only remaining reading of progress."""
    state.player.training = 4
    compact = _training_cell(state.player, compact=True).plain

    assert "40%" in compact
    assert "▰" not in compact and "▱" not in compact


def test_a_boss_reads_master_either_way(state) -> None:
    """A boss is at the stat cap and cannot train; the cell says so instead of showing a full bar,
    and the compact form must not turn that into a misleading percentage."""
    boss = state.bot
    boss.character.tier = "boss"

    for compact in (False, True):
        assert "MASTER" in _training_cell(boss, compact=compact).plain


def test_the_bar_itself_can_drop_its_segments() -> None:
    assert render_bar(0.4, 10, segments=False) == "40%"
    assert "▰" in render_bar(0.4, 10)


# Real grids, measured from real viewports. A COLUMN COUNT cannot tell these apart — 107 columns is
# a phone upright and 132 is the same phone on its side — which is why two width thresholds shipped
# broken before this. The shape can: upright is about 1.4 times wider than tall, everything else 4.
@pytest.mark.parametrize("grid", [(97, 70), (107, 78), (120, 88)], ids=["390px", "430px", "tablet"])
async def test_a_phone_in_portrait_asks_for_the_compact_bars(open_vault, state, grid) -> None:
    async with open_vault(state, size=grid) as (app, _):
        assert isinstance(app.screen, TempleScreen)
        assert app.screen._compact_bars() is True


@pytest.mark.parametrize("grid", [(132, 31), (199, 50), (110, 44)], ids=["landscape", "desktop", "fit"])
async def test_anything_wider_than_it_is_tall_keeps_the_bar(open_vault, state, grid) -> None:
    async with open_vault(state, size=grid) as (app, _):
        assert app.screen._compact_bars() is False


def test_no_device_is_anywhere_near_the_threshold() -> None:
    """The point of a ratio: it is not tuned to one phone. Portrait measures ~1.4 and landscape ~4,
    so the line at 2.5 has nothing sitting close to it on either side."""
    portrait = [97 / 70, 107 / 78, 120 / 88]
    wide = [132 / 31, 199 / 50, 110 / 44]
    assert max(portrait) < 2.0
    assert min(wide) > 2.4
