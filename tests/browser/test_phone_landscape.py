"""A real phone held sideways, in the numbers that phone actually reports.

The whole class of bug this guards was invisible on a desktop browser at 1x. A 3x display rounds an
xterm cell to whole DEVICE pixels, so a cell is 4px at font 8 on a plain screen and about 4.96px
here — and a width computed from the engine's own estimate came out 20% short. The symptom was never
"the font is wrong": it was 88 columns where 110 were asked for, which is under the layout's
breakpoint, so the hand panels stacked and the state row truncated to `Deck:…`, with a third of the
display left as black bars beside it.

The other half is height. A phone's SCREEN is not what a phone shows you — the browser's own chrome
took 48px of 360 here — so a terminal free to size itself to the screen overflows the window, and
that overflow is a scrollbar in a game that is supposed to fit.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Browser

from xiaolin_showdown.game import build_game

pytestmark = [pytest.mark.browser, pytest.mark.slow]

# Measured from the device, not chosen: a Samsung reporting a 360x800 screen at 3x, whose browser
# leaves 722x312 of usable viewport once its chrome is on screen.
DEVICE = {"viewport": {"width": 722, "height": 312}, "device_scale_factor": 3,
          "is_mobile": True, "has_touch": True}

# The engine's own breakpoint: at or above this a screen lays panels side by side.
from termcade.ui.app import WIDE_COLS  # noqa: E402

_SPY = """(() => {
  const Native = window.WebSocket;
  const Spy = function (u, p) {
    const s = p ? new Native(u, p) : new Native(u);
    const send = s.send.bind(s);
    s.send = function (frame) {
      if (typeof frame === 'string' && frame.includes('resize')) {
        try { window.__cols = JSON.parse(frame)[1].width; } catch (e) { /* not ours */ }
      }
      return send(frame);
    };
    return s;
  };
  Spy.prototype = Native.prototype;
  window.WebSocket = Spy;
})()"""


@pytest.fixture
def sideways(browser: Browser, served: str):
    page = browser.new_page(**DEVICE)
    page.add_init_script(_SPY)
    page.goto(served, wait_until="networkidle")
    page.wait_for_selector(".xterm-screen", timeout=30_000)
    page.wait_for_timeout(3000)
    try:
        yield page
    finally:
        page.close()


def test_the_grid_is_wide_enough_for_the_side_by_side_layout(sideways) -> None:
    """The breakpoint, not a pixel count — this is the number that decides whether the temple's two
    hand panels sit beside each other or stack, which is what the failure actually looked like."""
    cols = sideways.evaluate("window.__cols")
    assert cols >= WIDE_COLS, f"{cols} columns puts the layout below its own breakpoint"


def test_the_grid_covers_the_width_the_cartridge_asked_for(sideways) -> None:
    cols = sideways.evaluate("window.__cols")
    assert cols >= build_game().touch_fit_size[0]


def test_the_terminal_uses_the_whole_window(sideways) -> None:
    """No black bars. The width used to be capped to the cartridge's grid so that rotating moved the
    board rather than rescaling it; the cap could only be as good as its guess at a cell, and the
    guess was wrong here."""
    width = sideways.evaluate("document.getElementById('terminal').clientWidth")
    assert width >= DEVICE["viewport"]["width"] - 4


def test_the_terminal_does_not_overflow_the_window(sideways) -> None:
    """The scrollbar. `vh` cannot express this — on mobile it means the screen, which is the very
    dimension that is wrong; the page uses `dvh`."""
    height = sideways.evaluate("document.getElementById('terminal').clientHeight")
    assert height <= DEVICE["viewport"]["height"] + 2
